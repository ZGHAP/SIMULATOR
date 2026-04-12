#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from backtest_v2 import run_event_backtest, save_json
from config import StrategyConfig
from scanner import scan_instrument, summarize_candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="15m single-timeframe futures trend agent template")
    parser.add_argument("--input", required=True, help="Path to OHLCV csv")
    parser.add_argument("--instrument", default=None, help="Optional instrument name override")
    parser.add_argument("--config", default=None, help="Optional JSON config path")
    parser.add_argument("--signals-out", default="output/template_signals.csv")
    parser.add_argument("--candidates-out", default="output/template_candidates.csv")
    parser.add_argument("--metrics-out", default="output/template_metrics.json")
    parser.add_argument("--fee-bps", type=float, default=2.0)
    args = parser.parse_args()

    config = StrategyConfig.from_json(args.config)
    signal_df = scan_instrument(args.input, config=config, instrument=args.instrument)
    candidates_df = summarize_candidates(signal_df, top_n=50)
    bt_df, metrics = run_event_backtest(signal_df, fee_bps=args.fee_bps)

    signals_out = Path(args.signals_out)
    signals_out.parent.mkdir(parents=True, exist_ok=True)
    bt_df.to_csv(signals_out, index=False)

    candidates_out = Path(args.candidates_out)
    candidates_out.parent.mkdir(parents=True, exist_ok=True)
    candidates_df.to_csv(candidates_out, index=False)

    save_json({"config": config.to_dict(), "metrics": metrics}, args.metrics_out)

    print(f"saved signals    : {signals_out}")
    print(f"saved candidates : {candidates_out}")
    print(f"saved metrics    : {args.metrics_out}")
    print("\nlatest candidate rows:")
    if candidates_df.empty:
        print("(no candidates)")
    else:
        print(candidates_df.head(10).to_string(index=False))
    print("\nmetrics:")
    for key, value in metrics.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
