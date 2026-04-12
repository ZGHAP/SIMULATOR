from __future__ import annotations

import numpy as np
import pandas as pd


def classify_regime(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["trend_strength"] = (
        0.45 * _clip_z(out["mom_20"], 126)
        + 0.35 * _clip_z(out["mom_60"], 252)
        + 0.20 * _clip_z((out["ema_10"] - out["ema_30"]) / out["ema_30"], 126)
    )

    out["volatility_score"] = _clip_z(out["rv_20"], 126)
    out["liquidity_score"] = _clip_z(out["vol_ratio_20"], 126)

    out["volatility_state"] = np.select(
        [out["volatility_score"] <= -0.5, out["volatility_score"] >= 0.8],
        ["low", "high"],
        default="normal",
    )

    out["liquidity_state"] = np.select(
        [out["liquidity_score"] <= -0.7, out["liquidity_score"] >= 0.7],
        ["thin", "active"],
        default="normal",
    )

    up_cond = (out["trend_strength"] >= 0.75) & (out["close"] > out["ema_30"])
    down_cond = (out["trend_strength"] <= -0.75) & (out["close"] < out["ema_30"])

    out["market_regime"] = np.select(
        [up_cond, down_cond],
        ["trend_up", "trend_down"],
        default="range",
    )

    return out


def _clip_z(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=max(20, window // 4)).mean()
    std = series.rolling(window, min_periods=max(20, window // 4)).std().replace(0, np.nan)
    z = (series - mean) / std
    return z.clip(-3, 3)
