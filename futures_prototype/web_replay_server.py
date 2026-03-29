#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import errno
import json
import uuid
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from features_v2 import add_core_features, load_ohlcv
from simulator import SimAction, SimPosition, SimTrade, _records_to_native, _to_native


@dataclass
class ReplayState:
    session_id: str
    instrument: str
    timeframe: str | None
    input_path: str
    lookback: int
    tick_size: float
    position_size: int
    current_index: int
    position: SimPosition
    actions: list[SimAction]
    trades: list[SimTrade]
    snapshots: list[dict[str, Any]]


class ReplayStore:
    def __init__(
        self,
        input_path: str,
        instrument: str | None,
        timeframe: str | None,
        lookback: int,
        out_dir: str,
        tick_size: float,
        position_size: int,
        resume: bool,
    ) -> None:
        self.input_path = input_path
        self.instrument = instrument or Path(input_path).stem.upper()
        self.timeframe = timeframe
        self.lookback = lookback
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.tick_size = float(tick_size) if float(tick_size) > 0 else 1.0
        self.position_size = max(1, int(position_size))
        raw = load_ohlcv(input_path, timeframe=timeframe)
        self.df = add_core_features(raw)
        self.state_path = self.out_dir / f"{self.instrument}_{self.timeframe or 'unknown'}_state.json"
        self._pending_entry_reason: str | None = None
        self._flag_order: dict | None = None
        self._flag_ready: dict | None = None
        self._needs_full_save: bool = False
        self.state = ReplayState(
            session_id=uuid.uuid4().hex[:12],
            instrument=self.instrument,
            timeframe=self.timeframe,
            input_path=self.input_path,
            lookback=self.lookback,
            tick_size=self.tick_size,
            position_size=self.position_size,
            current_index=0,
            position=SimPosition(),
            actions=[],
            trades=[],
            snapshots=[],
        )
        if resume:
            self._load_state_if_exists()

    def _load_state_if_exists(self) -> None:
        if not self.state_path.exists():
            return
        raw = self.state_path.read_text(encoding="utf-8").strip()
        if not raw:
            return
        payload = json.loads(raw)
        sid = payload.get("session_id") or self.state.session_id
        # Reload actions and trades from their CSV files (state.json no longer stores them).
        actions: list[SimAction] = []
        trades: list[SimTrade] = []
        actions_path = self.out_dir / f"{self.instrument}_{sid}_actions.csv"
        trades_path  = self.out_dir / f"{self.instrument}_{sid}_trades.csv"
        if actions_path.exists() and actions_path.stat().st_size > 0:
            import csv as _csv
            with actions_path.open(newline="", encoding="utf-8") as f:
                for row in _csv.DictReader(f):
                    try:
                        actions.append(SimAction(**{k: (None if v == "" else v) for k, v in row.items()}))
                    except Exception:
                        pass
        if trades_path.exists() and trades_path.stat().st_size > 0:
            import csv as _csv
            with trades_path.open(newline="", encoding="utf-8") as f:
                for row in _csv.DictReader(f):
                    try:
                        trades.append(SimTrade(**{k: (None if v == "" else v) for k, v in row.items()}))
                    except Exception:
                        pass
        self.state = ReplayState(
            session_id=sid,
            instrument=payload.get("instrument") or self.instrument,
            timeframe=payload.get("timeframe") or self.timeframe,
            input_path=payload.get("input_path") or self.input_path,
            lookback=int(payload.get("lookback", self.lookback)),
            tick_size=float(payload.get("tick_size", self.tick_size)),
            position_size=int(payload.get("position_size", self.position_size)),
            current_index=int(payload.get("current_index", 0)),
            position=SimPosition(**payload.get("position", {})),
            actions=actions,
            trades=trades,
            snapshots=[],
        )
        # Sync flush counters so _append_csv knows what's already written.
        setattr(self, f"_flushed_{actions_path.stem}", len(actions))
        setattr(self, f"_flushed_{trades_path.stem}", len(trades))

    def save(self, force: bool = False) -> dict[str, str]:
        """Write to disk only when forced (session close) or explicitly requested.
        Lightweight checkpoint always written so resume works after crash."""
        actions_path = self.out_dir / f"{self.instrument}_{self.state.session_id}_actions.csv"
        trades_path = self.out_dir / f"{self.instrument}_{self.state.session_id}_trades.csv"
        snapshots_path = self.out_dir / f"{self.instrument}_{self.state.session_id}_snapshots.jsonl"
        summary_path = self.out_dir / f"{self.instrument}_{self.state.session_id}_summary.json"

        if force:
            # Full flush: rewrite CSVs with everything in memory.
            self._write_csv(actions_path, [asdict(x) for x in self.state.actions])
            self._write_csv(trades_path, [asdict(x) for x in self.state.trades])
            if snapshots_path.exists():
                snapshots_path.unlink()

        # Always write lightweight checkpoint so resume works.
        payload = {
            "session_id": self.state.session_id,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "input_path": self.input_path,
            "lookback": self.lookback,
            "current_index": self.state.current_index,
            "tick_size": self.state.tick_size,
            "position_size": self.state.position_size,
            "position": asdict(self.state.position),
            "actions_count": len(self.state.actions),
            "trades_count": len(self.state.trades),
        }
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        if force:
            summary_path.write_text(json.dumps({
                **payload,
                "open_position": asdict(self.state.position),
                "state_path": str(self.state_path),
            }, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "actions": str(actions_path),
            "trades": str(trades_path),
            "snapshots": str(snapshots_path),
            "summary": str(summary_path),
            "state": str(self.state_path),
        }

    def view(self) -> dict[str, Any]:
        i = min(self.state.current_index, len(self.df) - 1)
        row = self.df.iloc[i]
        auto_stop_note = self._apply_hard_stop(i, row)
        auto_flat_note = None
        auto_flag_note = None
        if not auto_stop_note:
            auto_flat_note = self._apply_forced_session_flat(i, row)
        if not auto_stop_note and not auto_flat_note:
            auto_flag_note = self._apply_flag_breakout(i, row)
            # If flag just filled, immediately check stop on the same bar.
            if auto_flag_note and not auto_stop_note:
                auto_stop_note = self._apply_hard_stop(i, row)
        self._last_save_error: dict[str, str] | None = None
        if auto_stop_note or auto_flat_note or auto_flag_note:
            try:
                force = self._needs_full_save
                self._needs_full_save = False
                self.save(force=force)
            except OSError as e:
                if e.errno == errno.ENOSPC:
                    self._last_save_error = {
                        "saveError": "disk_full",
                        "saveErrorDetail": f"No space left on device while writing replay outputs to {self.out_dir}",
                    }
                else:
                    raise
        start = max(0, i - self.lookback + 1)
        window_df = self.df.iloc[start:i + 1][["date", "open", "high", "low", "close", "volume"]].copy()
        return {
            "sessionId": self.state.session_id,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "index": i,
            "total": len(self.df),
            "lookback": self.lookback,
            "tickSize": self.state.tick_size,
            "positionSize": self.state.position_size,
            "position": {
                "side": self.state.position.side,
                "label": {1: "LONG", -1: "SHORT", 0: "FLAT"}[self.state.position.side],
                "entryPrice": self.state.position.entry_price,
                "unrealizedTicks": self._unrealized_ticks(float(row["close"])),
            },
            "totalPnlTicks": self._realized_ticks(),
            "netPnlTicks": self._realized_ticks() + self._unrealized_ticks(float(row["close"])),
            "currentBar": {k: _to_native(row.get(k)) for k in ["date", "open", "high", "low", "close", "volume"]},
            "windowBars": _records_to_native(window_df.to_dict(orient="records")),
            "recentActions": [asdict(x) for x in self.state.actions[-10:]],
            "autoStopNote": auto_stop_note,
            "autoFlatNote": auto_flat_note,
            "autoFlagNote": auto_flag_note,
            "flagOrder": self._flag_order,
        }

    @staticmethod
    def _is_session_close_bar(row: Any) -> bool:
        try:
            return str(row.get("date", ""))[11:16] in {"14:45", "02:15"}
        except Exception:
            return False

    def set_flag_order(self, bar_date: str, side: str) -> dict[str, Any]:
        """Set a pending breakout order on a specific bar."""
        target = bar_date[:16]
        bar_idx = None
        for idx, d in enumerate(self.df["date"]):
            if str(d)[:16] == target:
                bar_idx = idx
                break
        if bar_idx is None:
            return self.view()
        bar = self.df.iloc[bar_idx]
        trigger = float(bar["high"]) + 2 * self.state.tick_size if side == "long" else float(bar["low"]) - 2 * self.state.tick_size
        self._flag_order = {
            "bar_date": str(bar["date"])[:16],
            "bar_idx": bar_idx,
            "trigger_price": trigger,
            "side": side,
            "bar_high": float(bar["high"]),
            "bar_low": float(bar["low"]),
        }
        return self.view()

    def cancel_flag_order(self) -> dict[str, Any]:
        self._flag_order = None
        return self.view()

    def _apply_flag_breakout(self, i: int, row: Any) -> str | None:
        fo = self._flag_order
        if fo is None or self.state.position.side != 0:
            return None
        if i <= fo["bar_idx"]:
            return None
        trigger = fo["trigger_price"]
        side = fo["side"]
        bar_open = float(row["open"])
        if side == "long" and float(row["high"]) >= trigger:
            fill = bar_open if bar_open > trigger else trigger
            timestamp = str(row["date"])
            self.state.position = SimPosition(side=1, entry_price=fill, entry_time=timestamp, entry_bar_index=i)
            self._pending_entry_reason = "flag_breakout_long"
            self._flag_order = None
            self._flag_ready = None
            return f"flag breakout long triggered @ {fill:g}"
        elif side == "short" and float(row["low"]) <= trigger:
            fill = bar_open if bar_open < trigger else trigger
            timestamp = str(row["date"])
            self.state.position = SimPosition(side=-1, entry_price=fill, entry_time=timestamp, entry_bar_index=i)
            self._pending_entry_reason = "flag_breakout_short"
            self._flag_order = None
            self._flag_ready = None
            return f"flag breakout short triggered @ {fill:g}"
        return None

    def apply(self, action: str) -> dict[str, Any]:
        i = self.state.current_index
        if i >= len(self.df):
            return self.view()
        row = self.df.iloc[i]
        price = float(row["close"])
        timestamp = str(row["date"])

        # Q: cancel pending flag (first press) or unwind position (second press).
        # Cancel flag before auto-stop runs so it doesn't interfere.
        if action == "q":
            if self._flag_order is not None:
                self._flag_order = None
                self._flag_ready = None
                self.save()
                return self.view()
            # No flag — fall through as "flat" so it uses the same fast path as left arrow.
            action = "flat"

        stop_note = self._apply_hard_stop(i, row)
        if not stop_note:
            flag_note = self._apply_flag_breakout(i, row)
            # If flag just filled, immediately check stop on the same bar.
            if flag_note:
                stop_note = self._apply_hard_stop(i, row)
        before = self.state.position.side
        after = before

        if action == "cancel_flag":
            self._flag_order = None
            self.save()
            return self.view()

        # Cancel all pending orders on session close bar regardless of action.
        if self._is_session_close_bar(row):
            self._flag_order = None
            self._flag_ready = None

        if action == "breakout_long":
            # Set pending order: fill only when a future bar's high >= current bar's high + 2t
            trigger = float(row["high"]) + 2 * self.state.tick_size
            self._flag_order = {
                "bar_date": timestamp[:16],
                "bar_idx": i,
                "trigger_price": trigger,
                "side": "long",
                "bar_high": float(row["high"]),
                "bar_low": float(row["low"]),
            }
            self._flag_ready = None
            after = before
        elif action == "breakout_short":
            # Set pending order: fill only when a future bar's low <= current bar's low - 2t
            trigger = float(row["low"]) - 2 * self.state.tick_size
            self._flag_order = {
                "bar_date": timestamp[:16],
                "bar_idx": i,
                "trigger_price": trigger,
                "side": "short",
                "bar_high": float(row["high"]),
                "bar_low": float(row["low"]),
            }
            self._flag_ready = None
            after = before
        elif action == "long":
            if before == -1:
                self._close_trade(i, row)
            if self.state.position.side == 0:
                self.state.position = SimPosition(side=1, entry_price=price, entry_time=timestamp, entry_bar_index=i)
            after = self.state.position.side
        elif action == "short":
            if before == 1:
                self._close_trade(i, row)
            if self.state.position.side == 0:
                self.state.position = SimPosition(side=-1, entry_price=price, entry_time=timestamp, entry_bar_index=i)
            after = self.state.position.side
        elif action == "flat":
            if before != 0:
                self._close_trade(i, row)
            after = self.state.position.side
        elif action == "skip":
            after = before
        else:
            return self.view()

        # Skip the redundant sim_action if hard stop already logged its own action.
        if not stop_note:
            sim_action = SimAction(
                session_id=self.state.session_id,
                instrument=self.instrument,
                timeframe=self.timeframe,
                bar_index=i,
                timestamp=timestamp,
                action=action,
                position_before=before,
                position_after=after,
                price_reference=price,
                setup_label=None,
                reason_label=None,
                quality=None,
                note=None,
                key_used=action.upper(),
            )
            self.state.actions.append(sim_action)
        # Only advance the bar on skip (right arrow); all other actions stay on current bar.
        if action == "skip":
            self.state.current_index = min(i + 1, len(self.df))
        try:
            force = self._needs_full_save
            self._needs_full_save = False
            self.save(force=force)
        except OSError as e:
            if e.errno == errno.ENOSPC:
                return {
                    **self.view(),
                    "saveError": "disk_full",
                    "saveErrorDetail": f"No space left on device while writing replay outputs to {self.out_dir}",
                }
            raise
        return self.view()

    def _make_snapshot(self, i: int, row: Any, action: str, position_before: int) -> dict[str, Any]:
        start = max(0, i - self.lookback + 1)
        lookback_df = self.df.iloc[start:i + 1][["date", "open", "high", "low", "close", "volume"]].copy()
        return {
            "session_id": self.state.session_id,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "bar_index": i,
            "timestamp": str(row["date"]),
            "position_before": position_before,
            "position_after": self.state.position.side,
            "action": action,
            "current_bar": {k: _to_native(row.get(k)) for k in ["open", "high", "low", "close", "volume"]},
            "snapshot_30bars": _records_to_native(lookback_df.to_dict(orient="records")),
        }

    def _apply_hard_stop(self, i: int, row: Any) -> str | None:
        p = self.state.position
        if p.side == 0 or p.entry_price is None or p.entry_time is None or p.entry_bar_index is None:
            return None
        bar_open = float(row["open"])
        stop_distance = 20.0 * self.state.tick_size
        timestamp = str(row["date"])
        before_side = p.side
        if p.side > 0:
            stop_price = float(p.entry_price) - stop_distance
            if float(row["low"]) <= stop_price:
                exit_price = bar_open if bar_open < stop_price else stop_price
                note = f"long stop @ {'gap' if bar_open < stop_price else 'entry-20t'} {exit_price:g}"
                self._close_trade(i, row, exit_price=exit_price, exit_reason_label="hard_stop_entry_minus_20", exit_note=note)
                self.state.actions.append(SimAction(
                    session_id=self.state.session_id, instrument=self.instrument,
                    timeframe=self.timeframe, bar_index=i, timestamp=timestamp,
                    action="stop", position_before=before_side, position_after=0,
                    price_reference=exit_price, setup_label=None, reason_label="hard_stop_entry_minus_20",
                    quality=None, note=note, key_used=None,
                ))
                self._needs_full_save = True
                return f"auto stop: long exit @ {exit_price:g}"
        elif p.side < 0:
            stop_price = float(p.entry_price) + stop_distance
            if float(row["high"]) >= stop_price:
                exit_price = bar_open if bar_open > stop_price else stop_price
                note = f"short stop @ {'gap' if bar_open > stop_price else 'entry+20t'} {exit_price:g}"
                self._close_trade(i, row, exit_price=exit_price, exit_reason_label="hard_stop_entry_plus_20", exit_note=note)
                self.state.actions.append(SimAction(
                    session_id=self.state.session_id, instrument=self.instrument,
                    timeframe=self.timeframe, bar_index=i, timestamp=timestamp,
                    action="stop", position_before=before_side, position_after=0,
                    price_reference=exit_price, setup_label=None, reason_label="hard_stop_entry_plus_20",
                    quality=None, note=note, key_used=None,
                ))
                self._needs_full_save = True
                return f"auto stop: short exit @ {exit_price:g}"
        return None

    def _apply_forced_session_flat(self, i: int, row: Any) -> str | None:
        if i <= 0:
            return None
        prev_hhmm = str(self.df.iloc[i - 1].get("date", ""))[11:16]
        if prev_hhmm not in {"14:45", "02:15"}:
            return None
        # Cancel all pending orders at session boundary.
        self._flag_order = None
        self._flag_ready = None
        p = self.state.position
        if p.side == 0 or p.entry_price is None or p.entry_time is None or p.entry_bar_index is None:
            return None
        exit_price = float(row["close"])
        note = f"forced flat on bar after {prev_hhmm} @ close {exit_price:g}"
        self._close_trade(i, row, exit_price=exit_price, exit_reason_label="forced_session_flat_close", exit_note=note)
        self._needs_full_save = True
        return f"auto flat: after {prev_hhmm} bar @ close {exit_price:g}"

    def _close_trade(self, i: int, row: Any, exit_price: float | None = None, exit_reason_label: str | None = None, exit_note: str | None = None) -> None:
        p = self.state.position
        if p.side == 0 or p.entry_price is None or p.entry_time is None or p.entry_bar_index is None:
            self.state.position = SimPosition()
            return
        final_exit_price = float(exit_price) if exit_price is not None else float(row["close"])
        trade = SimTrade(
            session_id=self.state.session_id,
            instrument=self.instrument,
            timeframe=self.timeframe,
            entry_time=p.entry_time,
            exit_time=str(row["date"]),
            side="long" if p.side > 0 else "short",
            entry_price=float(p.entry_price),
            exit_price=final_exit_price,
            bars_held=i - p.entry_bar_index,
            gross_return=((final_exit_price - p.entry_price) / p.entry_price) * p.side,
            setup_label=None,
            entry_reason_label=self._pending_entry_reason,
            entry_quality=None,
            exit_reason_label=exit_reason_label,
            entry_note=None,
            exit_note=exit_note,
        )
        self.state.trades.append(trade)
        self._pending_entry_reason = None
        self.state.position = SimPosition()

    def _unrealized_ticks(self, last_price: float) -> float:
        p = self.state.position
        if p.side == 0 or p.entry_price is None:
            return 0.0
        return ((last_price - p.entry_price) / self.state.tick_size) * p.side

    def _realized_ticks(self) -> float:
        total = 0.0
        for t in self.state.trades:
            side = 1 if t.side == 'long' else -1
            total += ((float(t.exit_price) - float(t.entry_price)) / self.state.tick_size) * side
        return total

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)



INDEX_HTML = r'''<!doctype html>
<html><head><meta charset="utf-8"><title>Replay</title>
<style>
body{margin:0;font:14px system-ui;background:#0b0f14;color:#d6dde6;display:grid;grid-template-columns:1fr 320px;height:100vh}
#left{padding:12px} #right{border-left:1px solid #223;padding:12px;overflow:auto} canvas{background:#111722;border:1px solid #334;width:100%;height:calc(100vh - 32px)}
.k{color:#8aa0b4}.v{color:#fff}.btn{display:inline-block;padding:4px 8px;border:1px solid #445;border-radius:6px;margin:2px}
pre{white-space:pre-wrap;word-break:break-word}
</style></head>
<body>
<div id="left"><canvas id="cv" width="1200" height="760"></canvas></div>
<div id="right">
<div><span class="btn">Ctrl+click select bar</span><span class="btn" style="color:#37d67a">↑ flag long break</span><span class="btn" style="color:#ff5c5c">↓ flag short break</span><span class="btn">← cancel flag or flat</span><span class="btn">→ skip</span><span class="btn" style="color:#4fc3f7">Ctrl+↑/↓ BO current bar</span><span class="btn">Esc cancel flag only</span></div>
<h3 id="title"></h3>
<div><span class="k">Position:</span> <span id="pos" class="v"></span></div>
<div><span class="k">Open PnL:</span> <span id="pnl" class="v"></span></div>
<div><span class="k">Total PnL:</span> <span id="totalPnl" class="v"></span></div>
<div><span class="k">Net PnL:</span> <span id="netPnl" class="v"></span></div>
<div><span class="k">Current:</span> <span id="bar" class="v"></span></div>
<div><span class="k">Index:</span> <span id="idx" class="v"></span></div>
<div><span class="k">Auto stop:</span> <span id="autoStop" class="v"></span></div>
<div><span class="k">Auto flat:</span> <span id="autoFlat" class="v"></span></div>
<div><span class="k">Flag order:</span> <span id="flagOrder" class="v">-</span></div>
<div><span class="k">Flag trigger:</span> <span id="autoFlag" class="v">-</span></div>
<h4>Recent actions</h4><pre id="actions"></pre>
</div>
<script>
const cv = document.getElementById('cv'); const ctx = cv.getContext('2d');
let state = null; let flagPopup = null; let pendingFlagBar = null;
async function load(){ const r = await fetch('/api/state'); state = await r.json(); render(); }
async function act(action){ const r = await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})}); state = await r.json(); render(); }
function removeFlagPopup(){ if(flagPopup){flagPopup.remove();flagPopup=null;} }
async function setFlag(barDate,side){ removeFlagPopup(); pendingFlagBar=null; const r=await fetch('/api/flag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bar_date:barDate,side})}); state=await r.json(); render(); }
async function cancelFlag(){ removeFlagPopup(); pendingFlagBar=null; const r=await fetch('/api/flag/cancel',{method:'POST'}); state=await r.json(); render(); }
cv.addEventListener('click',(e)=>{
  if(!e.ctrlKey||!state) return; e.preventDefault();
  const bars=state.windowBars; if(!bars||!bars.length) return;
  const rect=cv.getBoundingClientRect(); const scaleX=cv.width/rect.width;
  const mx=(e.clientX-rect.left)*scaleX;
  const usableW=cv.width-60-20; const step=usableW/bars.length;
  const idx=Math.floor((mx-60)/step);
  if(idx<0||idx>=bars.length) return;
  const b=bars[idx]; const tk=state.tickSize;
  const boL=(b.high+2*tk).toFixed(0); const boS=(b.low-2*tk).toFixed(0);
  pendingFlagBar=b;
  removeFlagPopup();
  const d=document.createElement('div'); d.id='flagpopup';
  d.style.cssText='position:fixed;left:'+(e.clientX+6)+'px;top:'+(e.clientY-10)+'px;background:#141e2d;border:1px solid #445;border-radius:8px;padding:10px 14px;z-index:200;min-width:180px;box-shadow:0 4px 16px #000a';
  d.innerHTML='<div style="color:#8aa0b4;font-size:11px;margin-bottom:8px">'+(b.date||'').slice(0,16)+'<br><span style="color:#a9b7c6">H:'+b.high+' L:'+b.low+'</span></div>'
    +'<div style="display:flex;gap:6px;margin-bottom:6px">'
    +'<div style="flex:1;padding:7px 6px;background:#1a3328;color:#37d67a;border:1px solid #37d67a55;border-radius:5px;font-size:13px;text-align:center"><div>▲ Long break</div><div style="font-size:10px;color:#6db;margin-top:2px">@ '+boL+'</div><div style="font-size:10px;color:#4a8;margin-top:3px;font-weight:bold">press ↑</div></div>'
    +'<div style="flex:1;padding:7px 6px;background:#331a1a;color:#ff5c5c;border:1px solid #ff5c5c55;border-radius:5px;font-size:13px;text-align:center"><div>▼ Short break</div><div style="font-size:10px;color:#d88;margin-top:2px">@ '+boS+'</div><div style="font-size:10px;color:#a44;margin-top:3px;font-weight:bold">press ↓</div></div>'
    +'</div>'
    +'<div style="color:#555;font-size:10px;text-align:center">← to cancel &nbsp;|&nbsp; Esc to dismiss</div>';
  document.body.appendChild(d); flagPopup=d;
});
document.addEventListener('click',(e)=>{ if(flagPopup&&!flagPopup.contains(e.target)&&!e.ctrlKey) removeFlagPopup(); });
function px(v,min,max,h,padTop,padBottom){ return padTop + (max-v)/(max-min||1)*(h-padTop-padBottom); }
function render(){ if(!state) return; const bars=state.windowBars; const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); ctx.fillStyle='#111722'; ctx.fillRect(0,0,w,h);
 const pad={l:60,r:20,t:20,b:40}; const hi=Math.max(...bars.map(b=>b.high)); const lo=Math.min(...bars.map(b=>b.low)); const span=Math.max(hi-lo,1e-9); const top=hi+span*0.05; const bot=lo-span*0.05;
 const usableW=w-pad.l-pad.r; const step=usableW/bars.length; const bodyW=Math.max(6, step*0.65);
 const showRangeLabel = step >= 22;
 ctx.strokeStyle='#2a3342'; ctx.fillStyle='#8aa0b4'; ctx.font='12px system-ui';
 for(let i=0;i<6;i++){ const p=top-(top-bot)*i/5; const y=px(p,bot,top,h,pad.t,pad.b); ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(w-pad.r,y); ctx.stroke(); ctx.fillText(p.toFixed(1),8,y+4); }
 bars.forEach((b,i)=>{ const x=pad.l+i*step+step/2; const yo=px(b.open,bot,top,h,pad.t,pad.b), yc=px(b.close,bot,top,h,pad.t,pad.b), yh=px(b.high,bot,top,h,pad.t,pad.b), yl=px(b.low,bot,top,h,pad.t,pad.b); const bull=b.close>=b.open; ctx.strokeStyle=bull?'#37d67a':'#ff5c5c'; ctx.fillStyle=bull?'#37d67a':'#ff5c5c'; ctx.beginPath(); ctx.moveTo(x,yh); ctx.lineTo(x,yl); ctx.stroke(); const topy=Math.min(yo,yc), bh=Math.max(2,Math.abs(yc-yo)); ctx.fillRect(x-bodyW/2,topy,bodyW,bh); const hhmm=(b.date||'').slice(11,16); if(hhmm==='14:45' || hhmm==='02:15'){ ctx.strokeStyle='#ffd54f'; ctx.lineWidth=2; ctx.strokeRect(x-bodyW/2-2,topy-2,bodyW+4,bh+4); ctx.lineWidth=1; } if(i===bars.length-1){ ctx.strokeStyle='#4db3ff'; ctx.lineWidth=2; ctx.strokeRect(x-bodyW/2-2,topy-2,bodyW+4,bh+4); ctx.lineWidth=1; }
   const isLast=i===bars.length-1; const inLast5=i>=bars.length-5; ctx.save(); ctx.textAlign='center';
   if(inLast5){ ctx.fillStyle=isLast?'#4db3ff':'#a9b7c6'; ctx.font=(isLast?'11':'10')+'px system-ui'; ctx.fillText(b.high.toFixed(0),x,Math.max(12,yh-5)); ctx.fillStyle=isLast?'#4db3ff':'#7a8a9a'; ctx.fillText(b.low.toFixed(0),x,Math.min(h-pad.b+13,yl+13)); }
   const rng=(b.high-b.low).toFixed(0); ctx.fillStyle=isLast?'#ffd700':'#556070'; ctx.font=(isLast?'bold 11':'9')+'px system-ui'; ctx.fillText(rng,x,Math.min(h-pad.b-2,yl+(inLast5?26:14))); ctx.restore();
 });
 if(bars.length>0&&state.position.side===0){ const lb=bars[bars.length-1]; const boL=lb.high+2*state.tickSize; const boS=lb.low-2*state.tickSize; const x0=pad.l,x1=cv.width-pad.r; const yBL=px(boL,bot,top,h,pad.t,pad.b); const yBS=px(boS,bot,top,h,pad.t,pad.b); ctx.save(); ctx.setLineDash([5,3]); ctx.lineWidth=1; ctx.strokeStyle='rgba(55,214,122,0.55)'; ctx.beginPath(); ctx.moveTo(x0,yBL); ctx.lineTo(x1,yBL); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle='#37d67a'; ctx.font='10px system-ui'; ctx.textAlign='right'; ctx.fillText('Ctrl↑ BO@'+boL.toFixed(0),x1-4,yBL-3); ctx.setLineDash([5,3]); ctx.strokeStyle='rgba(255,92,92,0.55)'; ctx.beginPath(); ctx.moveTo(x0,yBS); ctx.lineTo(x1,yBS); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle='#ff5c5c'; ctx.fillText('Ctrl↓ BO@'+boS.toFixed(0),x1-4,yBS+12); ctx.restore(); }
 if(state.flagOrder){ const fo=state.flagOrder; const tp=fo.trigger_price; const col=fo.side==='long'?'#37d67a':'#ff5c5c'; const x0=pad.l,x1=cv.width-pad.r; const yF=px(tp,bot,top,h,pad.t,pad.b); ctx.save(); ctx.setLineDash([8,4]); ctx.lineWidth=2; ctx.strokeStyle=col; ctx.beginPath(); ctx.moveTo(x0,yF); ctx.lineTo(x1,yF); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle=col; ctx.font='bold 11px system-ui'; ctx.textAlign='right'; ctx.fillText('FLAG '+(fo.side==='long'?'▲':'▼')+' @'+tp.toFixed(0)+' (Esc cancel)',x1-4,yF+(fo.side==='long'?-4:13)); const bd=(fo.bar_date||'').slice(0,16); for(let bi=0;bi<bars.length;bi++){ if((bars[bi].date||'').slice(0,16)===bd){ const bx=pad.l+bi*step+step/2; const flagY=fo.side==='long'?px(bars[bi].high,bot,top,h,pad.t,pad.b)-14:px(bars[bi].low,bot,top,h,pad.t,pad.b)+14; ctx.fillStyle=col; ctx.font='bold 14px system-ui'; ctx.textAlign='center'; ctx.fillText(fo.side==='long'?'▲':'▼',bx,flagY); break; } } ctx.restore(); }
 const foEl=document.getElementById('flagOrder'); if(state.flagOrder){ const fo=state.flagOrder; foEl.textContent=fo.side.toUpperCase()+' @ '+fo.trigger_price.toFixed(0)+' (flag: '+(fo.bar_date||'').slice(5,16)+')'; foEl.style.color=fo.side==='long'?'#37d67a':'#ff5c5c'; }else{ foEl.textContent='-'; foEl.style.color='#fff'; }
 document.getElementById('autoFlag').textContent=state.autoFlagNote||'-';
 document.getElementById('title').textContent=`${state.instrument} ${state.timeframe||''}`;
 document.getElementById('pos').textContent=`${state.position.label} x${state.positionSize} (${state.position.side>0?'+1':state.position.side<0?'-1':'0'})`;
 document.getElementById('pnl').textContent=`${state.position.unrealizedTicks.toFixed(1)}t @ tick=${state.tickSize}`;
 document.getElementById('totalPnl').textContent=`${state.totalPnlTicks.toFixed(1)}t`;
 document.getElementById('netPnl').textContent=`${state.netPnlTicks.toFixed(1)}t`;
 const b=state.currentBar; document.getElementById('bar').textContent=`O ${b.open} H ${b.high} L ${b.low} C ${b.close}`;
 document.getElementById('idx').textContent=`${state.index}/${state.total-1} ${b.date}`;
 document.getElementById('autoStop').textContent=state.autoStopNote||'-';
 document.getElementById('autoFlat').textContent=state.autoFlatNote||'-';
 document.getElementById('actions').textContent=(state.recentActions||[]).slice().reverse().map(a=>{
   const side=a.position_after>0?'▲LONG':a.position_after<0?'▼SHORT':'FLAT';
   const dir=a.position_after>0?'L':a.position_after<0?'S':'—';
   const price=a.price_reference!=null?(' @ '+parseFloat(a.price_reference).toFixed(0)):'';
   const note=a.note?(' | '+a.note):'';
   const ts=(a.timestamp||'').slice(5,16);
   return `${ts} ${side}${price}${note}`;
 }).join('\n');
 }
 window.addEventListener('keydown', (e)=>{ if(e.repeat) return; if(e.key==='Escape'){removeFlagPopup(); pendingFlagBar=null; return;} if(e.key==='ArrowUp'||e.key==='ArrowDown'||e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault(); if(e.ctrlKey&&e.key==='ArrowUp'){act('breakout_long')} else if(e.ctrlKey&&e.key==='ArrowDown'){act('breakout_short')} else if(e.key==='ArrowUp'&&pendingFlagBar){setFlag(pendingFlagBar.date,'long')} else if(e.key==='ArrowDown'&&pendingFlagBar){setFlag(pendingFlagBar.date,'short')} else if(e.key==='ArrowLeft'){removeFlagPopup(); pendingFlagBar=null; act('q')} else if(e.key==='ArrowRight'){act('skip')}} });
 load();
</script></body></html>'''


def make_handler(store: ReplayStore):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(INDEX_HTML.encode("utf-8"))
                return
            if parsed.path == "/api/state":
                self._json(store.view())
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/action":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length) if length else b"{}"
                payload = json.loads(body.decode("utf-8"))
                self._json(store.apply(payload.get("action", "skip")))
                return
            if parsed.path == "/api/flag":
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length) if length else b"{}"
                payload = json.loads(body.decode("utf-8"))
                self._json(store.set_flag_order(payload.get("bar_date", ""), payload.get("side", "long")))
                return
            if parsed.path == "/api/flag/cancel":
                self._json(store.cancel_flag_order())
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _json(self, payload: Any):
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    return Handler


def main() -> None:
    p = argparse.ArgumentParser(description="Web replay for precise K-line display")
    p.add_argument("--input", required=True)
    p.add_argument("--instrument", default=None)
    p.add_argument("--timeframe", default=None)
    p.add_argument("--lookback", type=int, default=30)
    p.add_argument("--out-dir", default="output/sim")
    p.add_argument("--tick-size", type=float, default=1.0)
    p.add_argument("--position-size", type=int, default=1)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-resume", action="store_true")
    args = p.parse_args()

    store = ReplayStore(
        input_path=args.input,
        instrument=args.instrument,
        timeframe=args.timeframe,
        lookback=args.lookback,
        out_dir=args.out_dir,
        tick_size=args.tick_size,
        position_size=args.position_size,
        resume=not args.no_resume,
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store))
    print(f"web replay ready: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
