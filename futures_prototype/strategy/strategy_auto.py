#!/usr/bin/env python3
"""
strategy_auto.py — Automated version of the manual SC breakout strategy.

Replicates observed decision patterns from ~2,600 manual trades:
  - Flag-bar breakout entry: high+2t (long) / low-2t (short)
  - Direction: momentum-follow (price up → long, price down → short)
  - Filters: hour, month, day-count, post-stop cooldown
  - Exit: hard stop 20t, session flat at 14:45/02:15, or take-profit
  - Best hours: 09h(long), 13h, 01h, 23h(long only), 02h(short only)
  - Avoid: 21h shorts, 10-11h, Feb/Dec/Jun
  - Max 2 trades per session-day; skip if already stopped today
"""
from __future__ import annotations

import argparse
from pathlib import Path

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from features_v2 import add_core_features, load_ohlcv


TICK_SIZE = 0.1
STOP_TICKS = 20.0
FLAG_OFFSET_TICKS = 2.0
SESSION_CLOSE_TIMES = {"14:45", "02:15"}

# Hours allowed to enter, and which sides are permitted
HOUR_RULES: dict[int, set[str]] = {
    0:  {"long", "short"},
    1:  {"long", "short"},
    2:  {"short"},           # 02h short avg +10.5t; long avg -2.2t
    9:  {"long", "short"},
    13: {"long", "short"},
    14: {"long", "short"},
    22: {"long", "short"},
    23: {"long"},            # 23h long +711t; short -379t
}

# Calendar filters from historical data
BAD_MONTHS = {2, 6, 12}     # Feb, Jun, Dec — structural losers
BAD_DOW = set()             # no day of week filtered (Wednesday is weak but not excluded)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _is_session_close(ts: pd.Timestamp) -> bool:
    return f"{ts.hour:02d}:{ts.minute:02d}" in SESSION_CLOSE_TIMES


def _session_key(ts: pd.Timestamp) -> str:
    """Morning session = day of last 21:00 open. Groups overnight + day together."""
    if ts.hour < 3:
        return str(ts.date() - pd.Timedelta(days=1)) + "_night"
    if ts.hour < 15:
        return str(ts.date()) + "_day"
    return str(ts.date()) + "_night"


# ---------------------------------------------------------------------------
# flag-bar selector
# ---------------------------------------------------------------------------

def _pick_flag_bar(df: pd.DataFrame, i: int) -> int | None:
    """
    Use the previous completed bar as the flag bar — mirrors simulator behaviour
    where the user views bar i-1 and sets trigger above its high / below its low.
    Falls back to the highest-volume bar in the last 3 bars if the previous bar
    has an unusually small range (likely an inside bar / noise bar).
    """
    if i < 2:
        return None
    prev = df.iloc[i - 1]
    atr = prev.get("atr_14", None)
    bar_range = float(prev["high"]) - float(prev["low"])
    # If previous bar range < 30% of ATR, it's a tiny bar — look back a bit more
    if atr is not None and not pd.isna(atr) and bar_range < 0.3 * float(atr):
        lookback = min(4, i)
        candidates = df.iloc[i - lookback: i - 1]
        if candidates.empty:
            return i - 1
        return int(candidates["true_range"].idxmax())
    return i - 1


def _direction(df: pd.DataFrame, i: int, flag_idx: int) -> str | None:
    """
    Direction = momentum of the last 3 completed bars (use i-1 as last bar,
    not i, because bar i is still forming when the order is placed).

    Matches observed pattern: 78% long when price moved up, 80% short when down.
    """
    if i < 4:
        return None
    # momentum_3 at bar i-1 = close[i-1] vs close[i-4]
    mom = float(df.iloc[i - 1]["momentum_3"])
    if mom > 0:
        return "long"
    elif mom < 0:
        return "short"
    return None


# ---------------------------------------------------------------------------
# main backtest
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    tick_size: float = TICK_SIZE,
    stop_ticks: float = STOP_TICKS,
    flag_offset_ticks: float = FLAG_OFFSET_TICKS,
) -> pd.DataFrame:
    stop_dist = stop_ticks * tick_size
    flag_offset = flag_offset_ticks * tick_size

    trades = []

    # Per-session tracking
    session_trade_count: dict[str, int] = {}
    session_stopped: dict[str, bool] = {}

    # Pending flag order
    pending: dict | None = None
    position: dict | None = None

    for i in range(20, len(df)):
        row = df.iloc[i]
        ts: pd.Timestamp = row["date"]
        hhmm = f"{ts.hour:02d}:{ts.minute:02d}"
        sess = _session_key(ts)

        # ----------------------------------------------------------------
        # 1. Manage open position — check stop and session flat first
        # ----------------------------------------------------------------
        if position is not None:
            ep = position["entry_price"]
            side = position["side"]
            bar_open = float(row["open"])
            bar_high = float(row["high"])
            bar_low = float(row["low"])
            bar_close = float(row["close"])
            entry_bar = position["entry_bar"]

            # Adjust stop check on entry bar (pre-fill wick fix)
            is_entry_bar = (i == entry_bar)
            chk_low  = bar_close if (is_entry_bar and side == 1  and bar_open < ep) else bar_low
            chk_high = bar_close if (is_entry_bar and side == -1 and bar_open > ep) else bar_high

            stopped = False
            if side == 1 and chk_low <= ep - stop_dist:
                xp = bar_open if bar_open < ep - stop_dist else ep - stop_dist
                trades.append(_make_trade(position, i, ts, xp, "hard_stop", tick_size))
                session_stopped[sess] = True
                position = None
                pending = None
                stopped = True

            elif side == -1 and chk_high >= ep + stop_dist:
                xp = bar_open if bar_open > ep + stop_dist else ep + stop_dist
                trades.append(_make_trade(position, i, ts, xp, "hard_stop", tick_size))
                session_stopped[sess] = True
                position = None
                pending = None
                stopped = True

            # Session flat
            if not stopped:
                prev_hhmm = f"{df.iloc[i-1]['date'].hour:02d}:{df.iloc[i-1]['date'].minute:02d}"
                if prev_hhmm in SESSION_CLOSE_TIMES:
                    trades.append(_make_trade(position, i, ts, bar_close, "session_flat", tick_size))
                    position = None
                    pending = None

        # Cancel pending at session boundary
        if pending is not None:
            prev_hhmm = f"{df.iloc[i-1]['date'].hour:02d}:{df.iloc[i-1]['date'].minute:02d}"
            if prev_hhmm in SESSION_CLOSE_TIMES:
                pending = None

        # ----------------------------------------------------------------
        # 2. Check pending flag order fill
        # ----------------------------------------------------------------
        if pending is not None and position is None:
            bar_open = float(row["open"])
            if pending["side"] == "long" and float(row["high"]) >= pending["trigger"]:
                fill = bar_open if bar_open > pending["trigger"] else pending["trigger"]
                position = {"side": 1, "entry_price": fill, "entry_time": ts,
                            "entry_bar": i, "entry_reason": "flag_breakout_long"}
                pending = None
            elif pending["side"] == "short" and float(row["low"]) <= pending["trigger"]:
                fill = bar_open if bar_open < pending["trigger"] else pending["trigger"]
                position = {"side": -1, "entry_price": fill, "entry_time": ts,
                            "entry_bar": i, "entry_reason": "flag_breakout_short"}
                pending = None

        # ----------------------------------------------------------------
        # 3. Decide whether to place a new flag order this bar
        # ----------------------------------------------------------------
        if position is None and pending is None:
            hour = ts.hour
            month = ts.month

            # Calendar filters
            if month in BAD_MONTHS:
                continue
            if ts.dayofweek in BAD_DOW:
                continue

            # Hour filter — only trade allowed hours
            if hour not in HOUR_RULES:
                continue

            # Daily trade count cap (max 2 per session)
            n_trades = session_trade_count.get(sess, 0)
            if n_trades >= 2:
                continue

            # Post-stop cooldown — skip rest of session after a stop
            if session_stopped.get(sess, False):
                continue

            # Direction decision
            direction = _direction(df, i, i)
            if direction is None:
                continue

            # Hour-direction filter
            if direction not in HOUR_RULES[hour]:
                continue

            # Additional filter: avoid 21h shorts (38% stop rate)
            if hour == 21 and direction == "short":
                continue

            # Additional filter: avoid 10-11h (negative avg pnl)
            if hour in {10, 11}:
                # only take if strong momentum (top/bottom 30% of recent momentum)
                mom = float(row["momentum_3"])
                mom_threshold = df["momentum_3"].rolling(100).std().iloc[i]
                if pd.isna(mom_threshold) or abs(mom) < 0.5 * mom_threshold:
                    continue

            # Pick flag bar and set trigger
            flag_idx = _pick_flag_bar(df, i)
            if flag_idx is None:
                continue
            flag_bar = df.iloc[flag_idx]
            current_close = float(row["close"])

            if direction == "long":
                trigger = float(flag_bar["high"]) + flag_offset
                # Skip if price already at or above trigger (would fill instantly
                # with no room — leads to same-bar stops)
                if current_close >= trigger - flag_offset:
                    continue
                # Skip if trigger is more than 2× ATR away (too far, won't fill)
                atr = row.get("atr_14", None)
                if atr and not pd.isna(atr) and (trigger - current_close) > 2.5 * float(atr):
                    continue
            else:
                trigger = float(flag_bar["low"]) - flag_offset
                if current_close <= trigger + flag_offset:
                    continue
                atr = row.get("atr_14", None)
                if atr and not pd.isna(atr) and (current_close - trigger) > 2.5 * float(atr):
                    continue

            pending = {
                "side": direction,
                "trigger": trigger,
                "flag_bar_idx": flag_idx,
                "placed_bar": i,
                "placed_time": ts,
            }
            session_trade_count[sess] = n_trades + 1

    return pd.DataFrame(trades)


def _make_trade(
    position: dict,
    exit_bar: int,
    exit_time: pd.Timestamp,
    exit_price: float,
    exit_reason: str,
    tick_size: float,
) -> dict:
    side = position["side"]
    ep = position["entry_price"]
    xp = exit_price
    pnl_ticks = ((xp - ep) / tick_size) * side
    return {
        "entry_time": position["entry_time"],
        "exit_time": exit_time,
        "side": "long" if side == 1 else "short",
        "entry_price": ep,
        "exit_price": xp,
        "bars_held": exit_bar - position["entry_bar"],
        "pnl_ticks": pnl_ticks,
        "exit_reason": exit_reason,
        "entry_reason": position.get("entry_reason", ""),
    }


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def report(trades: pd.DataFrame) -> None:
    if trades.empty:
        print("No trades generated.")
        return

    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["win"] = trades["pnl_ticks"] > 0
    trades["year"] = trades["entry_time"].dt.year
    trades["hour"] = trades["entry_time"].dt.hour
    trades["is_stop"] = trades["exit_reason"] == "hard_stop"

    wins = trades[trades["win"]]; losses = trades[~trades["win"]]
    pf = wins["pnl_ticks"].sum() / abs(losses["pnl_ticks"].sum()) if len(losses) else float("inf")

    print("=" * 55)
    print("STRATEGY BACKTEST — SC99 BREAKOUT (auto)")
    print("=" * 55)
    print(f"Trades : {len(trades)}")
    print(f"WR     : {len(wins)/len(trades):.1%}")
    print(f"PF     : {pf:.3f}")
    print(f"Total  : {trades['pnl_ticks'].sum():+.1f}t")
    print(f"Avg W  : {wins['pnl_ticks'].mean():+.2f}t   Avg L: {losses['pnl_ticks'].mean():+.2f}t")
    print(f"MaxW   : {wins['pnl_ticks'].max():+.1f}t   MaxL: {losses['pnl_ticks'].min():+.1f}t")
    print(f"StopRate: {trades['is_stop'].mean():.0%}")
    print()

    print("-- By exit reason --")
    for r, g in trades.groupby("exit_reason"):
        w = g[g["win"]]
        print(f"  {r:20s}: n={len(g):4d}  WR={len(w)/len(g):.0%}  Avg={g['pnl_ticks'].mean():+.2f}t  Total={g['pnl_ticks'].sum():+.1f}t")

    print()
    print("-- By year --")
    for y, g in trades.groupby("year"):
        w = g[g["win"]]
        print(f"  {y}: n={len(g):4d}  WR={len(w)/len(g):.0%}  Total={g['pnl_ticks'].sum():+.1f}t")

    print()
    print("-- By hour --")
    for h, g in trades.groupby("hour"):
        w = g[g["win"]]; st = g["is_stop"].sum()
        print(f"  {h:02d}h: n={len(g):4d}  WR={len(w)/len(g):.0%}  StopRate={st/len(g):.0%}  Avg={g['pnl_ticks'].mean():+.2f}t")

    print()
    print("-- By side --")
    for s, g in trades.groupby("side"):
        w = g[g["win"]]
        print(f"  {s:5s}: n={len(g):4d}  WR={len(w)/len(g):.0%}  Total={g['pnl_ticks'].sum():+.1f}t")

    print()
    print("-- Bars held --")
    bb = pd.cut(trades["bars_held"], bins=[0,1,2,3,5,10,999], labels=["1","2","3","4-5","6-10","11+"])
    for b, g in trades.groupby(bb, observed=True):
        w = g[g["win"]]
        print(f"  {b:5s}: n={len(g):4d}  WR={len(w)/len(g):.0%}  Avg={g['pnl_ticks'].mean():+.2f}t")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Auto strategy backtest")
    p.add_argument("--input", required=True, help="Path to OHLCV CSV")
    p.add_argument("--timeframe", default="15m")
    p.add_argument("--tick-size", type=float, default=0.1)
    p.add_argument("--stop-ticks", type=float, default=20.0)
    p.add_argument("--out", default=None, help="Save trades CSV to this path")
    args = p.parse_args()

    print(f"Loading {args.input} ...")
    raw = load_ohlcv(args.input, timeframe=args.timeframe)
    df = add_core_features(raw)
    print(f"Bars: {len(df)}  from {df['date'].iloc[0]} to {df['date'].iloc[-1]}")

    trades = run_backtest(df, tick_size=args.tick_size, stop_ticks=args.stop_ticks)
    report(trades)

    if args.out:
        trades.to_csv(args.out, index=False)
        print(f"\nTrades saved → {args.out}")


if __name__ == "__main__":
    main()
