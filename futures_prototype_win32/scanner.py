from __future__ import annotations

from pathlib import Path
import pandas as pd

from config import StrategyConfig
from features_v2 import add_core_features, load_ohlcv
from engine import run_signal_engine


SCAN_COLUMNS = [
    "instrument",
    "date",
    "state",
    "setup_type",
    "side",
    "setup_score",
    "breakout_level",
    "entry_candidate_price",
    "hard_stop_price",
    "bars_since_setup",
    "bars_since_entry",
    "volume_ratio",
    "movement_efficiency",
    "vol_follow_through_ratio",
    "failure_risk_flag",
    "cooldown_flag",
    "failure_reason",
    "action_suggestion",
    "position",
    "position_side",
]


def scan_instrument(input_path: str, config: StrategyConfig | None = None, instrument: str | None = None) -> pd.DataFrame:
    config = config or StrategyConfig()
    instrument = instrument or Path(input_path).stem.upper()
    price_df = load_ohlcv(input_path, timeframe=config.timeframe)
    feat_df = add_core_features(price_df, breakout_lookback_bars=config.breakout_lookback_bars)
    signal_df = run_signal_engine(feat_df, config=config, instrument=instrument)
    return signal_df


def summarize_candidates(signal_df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    candidates = signal_df[signal_df["action_suggestion"].isin(["candidate_long", "candidate_short", "enter_long", "enter_short"])].copy()
    if candidates.empty:
        return candidates
    cols = [c for c in SCAN_COLUMNS if c in candidates.columns]
    return candidates.sort_values(["date", "setup_score"], ascending=[False, False])[cols].head(top_n).reset_index(drop=True)
