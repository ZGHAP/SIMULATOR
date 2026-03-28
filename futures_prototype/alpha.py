from __future__ import annotations

import numpy as np
import pandas as pd


def build_alpha(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    trend_signal = (
        0.40 * _safe_z(out["mom_20"], 126)
        + 0.30 * _safe_z(out["mom_60"], 252)
        + 0.20 * _safe_z(out["breakout_20"], 126)
        + 0.10 * _safe_z(out["dist_ema30"], 126)
    )

    mr_core = -_safe_z(out["dist_ema30"], 126)
    mr_stretch = -_safe_z(out["dist_ema60"], 252)
    mr_exhaust = -_safe_z(out["ret_1"].rolling(3).sum(), 126)
    meanrev_signal = 0.50 * mr_core + 0.30 * mr_stretch + 0.20 * mr_exhaust

    out["alpha_trend"] = np.where(
        out["market_regime"] == "trend_down",
        -trend_signal.abs(),
        np.where(out["market_regime"] == "trend_up", trend_signal.abs(), 0.5 * trend_signal),
    )
    out["alpha_meanrev"] = np.where(out["market_regime"] == "range", meanrev_signal, 0.35 * meanrev_signal)

    out["alpha_raw"] = np.where(out["market_regime"] == "range", out["alpha_meanrev"], out["alpha_trend"])
    out["alpha_direction"] = np.sign(out["alpha_raw"])
    out["alpha_confidence"] = out["alpha_raw"].abs().clip(0, 3) / 3.0

    return out


def _safe_z(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=max(20, window // 4)).mean()
    std = series.rolling(window, min_periods=max(20, window // 4)).std().replace(0, np.nan)
    return ((series - mean) / std).clip(-3, 3)
