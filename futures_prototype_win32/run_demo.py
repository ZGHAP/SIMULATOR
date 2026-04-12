#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from features import add_features, load_ohlcv_csv
from regime import classify_regime
from alpha import build_alpha
from portfolio import build_portfolio
from backtest import run_backtest, save_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Futures subjective-style quant prototype")
    parser.add_argument("--input", required=True, help="Path to futures OHLCV csv")
    parser.add_argument("--signals-out", default="output/signals.csv", help="Where to save signal dataframe")
    parser.add_argument("--metrics-out", default="output/metrics.json", help="Where to save metrics json")
    parser.add_argument("--fee-bps", type=float, default=2.0, help="Round-trip-ish turnover cost in bps")
    args = parser.parse_args()

    price_df = load_ohlcv_csv(args.input)
    feat_df = add_features(price_df)
    regime_df = classify_regime(feat_df)
    alpha_df = build_alpha(regime_df)
    portfolio_df = build_portfolio(alpha_df)
    bt_df, metrics = run_backtest(portfolio_df, fee_bps=args.fee_bps)

    signals_path = Path(args.signals_out)
    signals_path.parent.mkdir(parents=True, exist_ok=True)
    bt_df.to_csv(signals_path, index=False)

    metrics_path = save_metrics(metrics, args.metrics_out)

    print(f"saved signals: {signals_path}")
    print(f"saved metrics: {metrics_path}")
    print("latest rows:")
    print(
        bt_df[[
            "date",
            "close",
            "market_regime",
            "volatility_state",
            "liquidity_state",
            "alpha_raw",
            "alpha_confidence",
            "target_position",
            "side",
        ]].tail(10).to_string(index=False)
    )
    print("\nmetrics:")
    for k, v in metrics.items():
        print(f"- {k}: {v}")


if __name__ == "__main__":
    main()
