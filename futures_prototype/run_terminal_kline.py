#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

from terminal_kline import TerminalKlineRenderer, ViewerConfig, clear_screen, infer_instrument, load_frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a rolling terminal K-line window from OHLCV csv")
    parser.add_argument("--input", required=True, help="Path to OHLCV csv")
    parser.add_argument("--instrument", default=None, help="Instrument label override")
    parser.add_argument("--timeframe", default=None, help="Timeframe label override, e.g. 1m/5m/15m")
    parser.add_argument("--window", type=int, default=30, help="Rolling bar window")
    parser.add_argument("--height", type=int, default=20, help="Chart height in rows")
    parser.add_argument("--candle-width", type=int, default=2, help="Character width per candle")
    parser.add_argument("--gap", type=int, default=0, help="Gap between candles")
    parser.add_argument("--padding", type=float, default=0.05, help="Y-axis padding ratio")
    parser.add_argument("--tail", type=int, default=None, help="Render only the latest N rows before taking the rolling window")
    parser.add_argument("--watch", action="store_true", help="Watch the csv and refresh continuously")
    parser.add_argument("--interval", type=float, default=2.0, help="Refresh interval seconds when --watch is set")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    parser.add_argument("--ascii", action="store_true", help="Use ASCII chars instead of unicode")
    args = parser.parse_args()

    config = ViewerConfig(
        window=args.window,
        height=args.height,
        candle_width=args.candle_width,
        gap=args.gap,
        y_padding_ratio=args.padding,
        color=not args.no_color,
        unicode=not args.ascii,
    )
    renderer = TerminalKlineRenderer(config)
    instrument = args.instrument or infer_instrument(args.input)

    def render_once() -> None:
        df = load_frame(args.input, timeframe=args.timeframe)
        if args.tail is not None:
            df = df.tail(args.tail).reset_index(drop=True)
        clear_screen()
        print(renderer.render(df, instrument=instrument, timeframe=args.timeframe))

    if not args.watch:
        render_once()
        return

    try:
        while True:
            render_once()
            time.sleep(max(args.interval, 0.2))
    except KeyboardInterrupt:
        print("\nexit viewer")


if __name__ == "__main__":
    main()
