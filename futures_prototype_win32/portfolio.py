from __future__ import annotations

import numpy as np
import pandas as pd


def build_portfolio(df: pd.DataFrame, min_confidence: float = 0.18) -> pd.DataFrame:
    out = df.copy()

    out["risk_scale"] = 1.0
    out.loc[out["volatility_state"] == "high", "risk_scale"] *= 0.55
    out.loc[out["volatility_state"] == "low", "risk_scale"] *= 0.90
    out.loc[out["liquidity_state"] == "thin", "risk_scale"] *= 0.50
    out.loc[out["liquidity_state"] == "active", "risk_scale"] *= 1.05

    out["trade_allowed"] = True
    out.loc[out["alpha_confidence"] < min_confidence, "trade_allowed"] = False
    out.loc[out["atr_14"].isna() | out["rv_20"].isna(), "trade_allowed"] = False

    raw_position = out["alpha_direction"] * out["alpha_confidence"] * out["risk_scale"]
    out["target_position"] = np.where(out["trade_allowed"], raw_position.clip(-1.0, 1.0), 0.0)

    out["side"] = np.select(
        [out["target_position"] > 0.05, out["target_position"] < -0.05],
        ["long", "short"],
        default="flat",
    )

    return out
