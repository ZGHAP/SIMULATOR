#!/usr/bin/env python3
from __future__ import annotations

"""
最小入口：把第一版主观交易识别因子跑出来。

这个脚本目前只做两件事：
1. 读取 OHLCV，并补上 core features + subjective factors；
2. 导出一个 CSV，方便肉眼审和后续分析。

故意不做的事：
- 不直接下交易结论
- 不直接自动回测
- 不把 signal_score 当成最终买卖点
"""

import argparse
from pathlib import Path

from features_v2 import add_core_features, load_ohlcv
from factors_subjective import add_subjective_factors


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate first-pass subjective trading factors")
    parser.add_argument("--input", required=True, help="Path to OHLCV csv")
    parser.add_argument("--timeframe", default=None, help="Optional resample timeframe, e.g. 15m")
    parser.add_argument("--window", type=int, default=30, help="Lookback window used by subjective factors")
    parser.add_argument("--output", default="output/subjective_factors.csv", help="Where to save the factor table")
    args = parser.parse_args()

    df = load_ohlcv(args.input, timeframe=args.timeframe)
    df = add_core_features(df)
    df = add_subjective_factors(df, window=args.window)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    preview_cols = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "signal_family",
        "signal_score",
        "long_bias_score",
        "short_bias_score",
        "continuation_score",
        "release_score",
        "reconfirm_score",
        "reversal_score",
        "noise_score",
        "failed_breakdown_seed_score",
        "fast_rebound_score",
        "second_test_hold_score",
        "second_disagreement_absorption_score",
        "rebound_zone_hold_score",
        "micro_reversal_long_score",
        "micro_reversal_extend_score",
        "rule_big_selloff",
        "rule_fast_rebound",
        "rule_second_test_hold",
        "rule_second_disagreement_absorb",
        "rule_rebound_zone_hold",
        "rule_close_entry_long",
        "expansion_4_8_proxy",
        "fast_failure_risk",
        "overhold_risk_proxy",
    ]
    preview_cols = [c for c in preview_cols if c in df.columns]

    print(f"saved factors to: {out_path}")
    print(df[preview_cols].tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
