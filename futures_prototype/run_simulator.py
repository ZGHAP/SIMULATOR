#!/usr/bin/env python3
from __future__ import annotations

import argparse

from simulator import TradeSimulator


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay market data and collect subjective trading track records")
    parser.add_argument("--input", required=True, help="Path to OHLCV csv")
    parser.add_argument("--instrument", default=None, help="Instrument name override")
    parser.add_argument("--timeframe", default=None, help="Timeframe label override, e.g. 1m/5m/15m")
    parser.add_argument("--start", type=int, default=0, help="Start bar index (used when no saved state exists)")
    parser.add_argument("--end", type=int, default=None, help="End bar index (exclusive)")
    parser.add_argument("--lookback", type=int, default=30, help="Rolling naked-K snapshot window")
    parser.add_argument("--chart-height", type=int, default=18, help="Terminal K-line chart height")
    parser.add_argument("--out-dir", default="output/sim", help="Where to save track-record logs and state")
    parser.add_argument("--tick-size", type=float, default=1.0, help="Tick size for PnL display, e.g. 1, 0.5, 0.2")
    parser.add_argument("--position-size", type=int, default=1, help="Display position size, e.g. 1, 2, 3")
    parser.add_argument("--no-resume", action="store_true", help="Start a fresh replay instead of loading saved state")
    args = parser.parse_args()

    sim = TradeSimulator(
        input_path=args.input,
        instrument=args.instrument,
        timeframe=args.timeframe,
        lookback=args.lookback,
        chart_height=args.chart_height,
        out_dir=args.out_dir,
        tick_size=args.tick_size,
        position_size=args.position_size,
        resume=not args.no_resume,
    )
    try:
        sim.run(start=args.start, end=args.end)
    finally:
        paths = sim.save(args.out_dir)
        print("\nsaved files:")
        for key, value in paths.items():
            print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
