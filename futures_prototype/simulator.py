from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import csv
import json
import os
import sys
import termios
import tty
import uuid

import numpy as np
import pandas as pd

from features_v2 import add_core_features, load_ohlcv
from terminal_kline import TerminalKlineRenderer, ViewerConfig, clear_screen


ARROW_UP = "UP"
ARROW_DOWN = "DOWN"
ARROW_LEFT = "LEFT"
ARROW_RIGHT = "RIGHT"


@dataclass
class SimPosition:
    side: int = 0
    entry_price: float | None = None
    entry_time: str | None = None
    entry_bar_index: int | None = None
    setup_label: str | None = None
    reason_label: str | None = None
    quality: str | None = None
    entry_note: str | None = None


@dataclass
class SimAction:
    session_id: str
    instrument: str
    timeframe: str | None
    bar_index: int
    timestamp: str
    action: str
    position_before: int
    position_after: int
    price_reference: float
    setup_label: str | None
    reason_label: str | None
    quality: str | None
    note: str | None
    key_used: str | None


@dataclass
class SimTrade:
    session_id: str
    instrument: str
    timeframe: str | None
    entry_time: str
    exit_time: str
    side: str
    entry_price: float
    exit_price: float
    bars_held: int
    gross_return: float
    setup_label: str | None
    entry_reason_label: str | None
    entry_quality: str | None
    exit_reason_label: str | None
    entry_note: str | None
    exit_note: str | None


class TradeSimulator:
    def __init__(
        self,
        input_path: str,
        instrument: str | None = None,
        timeframe: str | None = None,
        lookback: int = 30,
        chart_height: int = 18,
        out_dir: str = "output/sim",
        tick_size: float = 1.0,
        position_size: int = 1,
        resume: bool = True,
    ) -> None:
        self.input_path = input_path
        self.instrument = instrument or Path(input_path).stem.upper()
        self.timeframe = timeframe
        self.lookback = lookback
        self.chart_height = chart_height
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.tick_size = float(tick_size) if float(tick_size) > 0 else 1.0
        self.position_size = max(1, int(position_size))
        raw = load_ohlcv(input_path, timeframe=timeframe)
        self.df = add_core_features(raw)
        self.renderer = TerminalKlineRenderer(
            ViewerConfig(window=lookback, height=chart_height, candle_width=2, gap=0, y_padding_ratio=0.05, color=True, unicode=True)
        )
        self.state_path = self.out_dir / f"{self.instrument}_{self.timeframe or 'unknown'}_state.json"
        self.session_id = uuid.uuid4().hex[:12]
        self.position = SimPosition()
        self.actions: list[SimAction] = []
        self.trades: list[SimTrade] = []
        self.snapshots: list[dict[str, Any]] = []
        self.current_index = 0
        self.start_index = 0
        self.end_index = len(self.df)
        self._resume_enabled = resume
        if resume:
            self._load_state_if_exists()

    def run(self, start: int = 0, end: int | None = None) -> None:
        if not self._resume_enabled or not self.actions:
            self.current_index = max(self.current_index, start)
        self.start_index = self.current_index
        self.end_index = len(self.df) if end is None else min(end, len(self.df))

        while self.current_index < self.end_index:
            row = self.df.iloc[self.current_index]
            self._print_bar(self.current_index, row)
            key = self._read_key()
            if key in {"q", "Q", "CTRL_C"}:
                print("quit session")
                break
            result = self._interpret_key(key)
            if result is None:
                continue
            action, key_used = result
            reason_label = None
            setup_label = None
            quality = None
            note = None
            self._apply_action(self.current_index, row, action, setup_label, reason_label, quality, note, key_used=key_used)
            self.current_index += 1
            self._save_state()

        self._save_state()

    def save(self, out_dir: str | None = None) -> dict[str, str]:
        output = Path(out_dir) if out_dir else self.out_dir
        output.mkdir(parents=True, exist_ok=True)

        actions_path = output / f"{self.instrument}_{self.session_id}_actions.csv"
        trades_path = output / f"{self.instrument}_{self.session_id}_trades.csv"
        snapshots_path = output / f"{self.instrument}_{self.session_id}_snapshots.jsonl"
        summary_path = output / f"{self.instrument}_{self.session_id}_summary.json"

        self._write_csv(actions_path, [asdict(x) for x in self.actions])
        self._write_csv(trades_path, [asdict(x) for x in self.trades])
        with snapshots_path.open("w", encoding="utf-8") as f:
            for item in self.snapshots:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        summary = {
            "session_id": self.session_id,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "actions": len(self.actions),
            "trades": len(self.trades),
            "lookback": self.lookback,
            "current_index": self.current_index,
            "open_position": asdict(self.position),
            "input_path": self.input_path,
            "state_path": str(self.state_path),
        }
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "actions": str(actions_path),
            "trades": str(trades_path),
            "snapshots": str(snapshots_path),
            "summary": str(summary_path),
            "state": str(self.state_path),
        }

    def _load_state_if_exists(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.session_id = payload.get("session_id") or self.session_id
        self.current_index = int(payload.get("current_index", 0))
        self.position = SimPosition(**payload.get("position", {}))
        self.actions = [SimAction(**item) for item in payload.get("actions", [])]
        self.trades = [SimTrade(**item) for item in payload.get("trades", [])]
        self.snapshots = payload.get("snapshots", [])

    def _save_state(self) -> None:
        payload = {
            "session_id": self.session_id,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "input_path": self.input_path,
            "lookback": self.lookback,
            "chart_height": self.chart_height,
            "current_index": self.current_index,
            "tick_size": self.tick_size,
            "position_size": self.position_size,
            "position": asdict(self.position),
            "actions": [asdict(x) for x in self.actions],
            "trades": [asdict(x) for x in self.trades],
            "snapshots": self.snapshots,
        }
        self.state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _interpret_key(self, key: str) -> tuple[str, str] | None:
        if key == ARROW_UP:
            return "long", "UP"
        if key == ARROW_DOWN:
            return "short", "DOWN"
        if key == ARROW_RIGHT:
            return "skip", "RIGHT"
        if key == ARROW_LEFT:
            return "flat", "LEFT"
        return None

    def _read_key(self) -> str:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            first = sys.stdin.read(1)
            if first == "\x03":
                return "CTRL_C"
            if first == "\x1b":
                second = sys.stdin.read(1)
                third = sys.stdin.read(1)
                if second == "[":
                    if third == "A":
                        return ARROW_UP
                    if third == "B":
                        return ARROW_DOWN
                    if third == "C":
                        return ARROW_RIGHT
                    if third == "D":
                        return ARROW_LEFT
                return "ESC"
            return first
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            first = sys.stdin.read(1)
            if first == "\x03":
                return "CTRL_C"
            if first == "\x1b":
                second = sys.stdin.read(1)
                third = sys.stdin.read(1)
                if second == "[":
                    if third == "A":
                        return ARROW_UP
                    if third == "B":
                        return ARROW_DOWN
                    if third == "C":
                        return ARROW_RIGHT
                    if third == "D":
                        return ARROW_LEFT
                return "ESC"
            return first
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    @staticmethod
    def _is_session_close_bar(row: pd.Series) -> bool:
        try:
            return str(row.get("date", ""))[11:16] in {"14:45", "02:15"}
        except Exception:
            return False

    def _apply_action(
        self,
        i: int,
        row: pd.Series,
        action: str,
        setup_label: str | None,
        reason_label: str | None,
        quality: str | None,
        note: str | None,
        key_used: str | None = None,
    ) -> None:
        price = float(row["close"])
        timestamp = str(row["date"])
        before = self.position.side
        after = before

        # Block new entries on session close bars; convert to skip silently.
        if action in {"long", "short"} and self._is_session_close_bar(row):
            action = "skip"

        if action == "long":
            if before == -1:
                self._close_trade(i, row, reason_label or "reverse_to_long", note)
            if self.position.side == 0:
                self.position = SimPosition(
                    side=1,
                    entry_price=price,
                    entry_time=timestamp,
                    entry_bar_index=i,
                    setup_label=setup_label,
                    reason_label=reason_label,
                    quality=quality,
                    entry_note=note,
                )
            after = self.position.side
        elif action == "short":
            if before == 1:
                self._close_trade(i, row, reason_label or "reverse_to_short", note)
            if self.position.side == 0:
                self.position = SimPosition(
                    side=-1,
                    entry_price=price,
                    entry_time=timestamp,
                    entry_bar_index=i,
                    setup_label=setup_label,
                    reason_label=reason_label,
                    quality=quality,
                    entry_note=note,
                )
            after = self.position.side
        elif action == "flat":
            if before != 0:
                self._close_trade(i, row, reason_label, note)
            after = self.position.side
        elif action in {"hold", "note", "skip"}:
            after = before

        sim_action = SimAction(
            session_id=self.session_id,
            instrument=self.instrument,
            timeframe=self.timeframe,
            bar_index=i,
            timestamp=timestamp,
            action=action,
            position_before=before,
            position_after=after,
            price_reference=price,
            setup_label=setup_label,
            reason_label=reason_label,
            quality=quality,
            note=note,
            key_used=key_used,
        )
        self.actions.append(sim_action)
        self.snapshots.append(self._make_snapshot(i, row, action, setup_label, reason_label, quality, note, before, key_used))

    def _close_trade(self, i: int, row: pd.Series, reason_label: str | None, note: str | None) -> None:
        if self.position.side == 0 or self.position.entry_price is None or self.position.entry_time is None or self.position.entry_bar_index is None:
            self.position = SimPosition()
            return
        exit_price = float(row["close"])
        gross_return = ((exit_price - self.position.entry_price) / self.position.entry_price) * self.position.side
        trade = SimTrade(
            session_id=self.session_id,
            instrument=self.instrument,
            timeframe=self.timeframe,
            entry_time=self.position.entry_time,
            exit_time=str(row["date"]),
            side="long" if self.position.side > 0 else "short",
            entry_price=float(self.position.entry_price),
            exit_price=exit_price,
            bars_held=i - self.position.entry_bar_index,
            gross_return=float(gross_return),
            setup_label=self.position.setup_label,
            entry_reason_label=self.position.reason_label,
            entry_quality=self.position.quality,
            exit_reason_label=reason_label,
            entry_note=self.position.entry_note,
            exit_note=note,
        )
        self.trades.append(trade)
        self.position = SimPosition()

    def _make_snapshot(
        self,
        i: int,
        row: pd.Series,
        action: str,
        setup_label: str | None,
        reason_label: str | None,
        quality: str | None,
        note: str | None,
        position_before: int,
        key_used: str | None,
    ) -> dict[str, Any]:
        start = max(0, i - self.lookback + 1)
        lookback_df = self.df.iloc[start:i + 1].copy()
        return {
            "session_id": self.session_id,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "bar_index": i,
            "timestamp": str(row["date"]),
            "position_before": position_before,
            "position_after": self.position.side,
            "action": action,
            "setup_label": setup_label,
            "reason_label": reason_label,
            "quality": quality,
            "note": note,
            "key_used": key_used,
            "current_bar": {
                "open": _to_native(row.get("open")),
                "high": _to_native(row.get("high")),
                "low": _to_native(row.get("low")),
                "close": _to_native(row.get("close")),
                "volume": _to_native(row.get("volume")),
            },
            "snapshot_30bars": _records_to_native(
                lookback_df[["date", "open", "high", "low", "close", "volume"]].to_dict(orient="records")
            ),
        }

    def _print_bar(self, i: int, row: pd.Series) -> None:
        pos = {1: "LONG", -1: "SHORT", 0: "FLAT"}[self.position.side]
        start = max(0, i - self.lookback + 1)
        window_df = self.df.iloc[start:i + 1][["date", "open", "high", "low", "close", "volume"]].copy()
        clear_screen()
        ticks = self._unrealized_ticks(row)
        total_ticks = self._realized_ticks()
        net_ticks = total_ticks + ticks
        print(f"session={self.session_id}  idx={i}/{self.end_index - 1}  instrument={self.instrument}  timeframe={self.timeframe or 'unknown'}")
        print(f"pos={pos} x{self.position_size} ({self.position.side:+d})  open={ticks:+.1f}t  total={total_ticks:+.1f}t  net={net_ticks:+.1f}t  tick={self.tick_size:g}  resume_state={self.state_path}")
        print(self.renderer.render(window_df, instrument=self.instrument, timeframe=self.timeframe))
        print(f"current: O={row['open']:.4f} H={row['high']:.4f} L={row['low']:.4f} C={row['close']:.4f} V={row['volume']}")
        print()
        print("keys: ↑=long  ↓=short  ←=flat  →=skip  q/Ctrl-C=quit")
        print("no reason input now; just feed action signals")

    def _unrealized_pnl(self, row: pd.Series) -> float:
        if self.position.side == 0 or self.position.entry_price is None:
            return 0.0
        return ((float(row['close']) - self.position.entry_price) / self.position.entry_price) * self.position.side

    def _unrealized_ticks(self, row: pd.Series) -> float:
        if self.position.side == 0 or self.position.entry_price is None:
            return 0.0
        return ((float(row['close']) - self.position.entry_price) / self.tick_size) * self.position.side

    def _realized_ticks(self) -> float:
        total = 0.0
        for t in self.trades:
            side = 1 if t.side == "long" else -1
            total += ((float(t.exit_price) - float(t.entry_price)) / self.tick_size) * side
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


def _records_to_native(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: _to_native(v) for k, v in row.items()} for row in records]


def _to_native(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.floating, np.integer)):
        if pd.isna(value):
            return None
        return value.item()
    if isinstance(value, pd.Timestamp):
        return str(value)
    if pd.isna(value):
        return None
    return value
