from __future__ import annotations

import numpy as np
import pandas as pd


def load_ohlcv_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date").reset_index(drop=True)
    return out


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ret_1"] = out["close"].pct_change()
    out["log_ret_1"] = np.log(out["close"]).diff()

    out["ema_10"] = out["close"].ewm(span=10, adjust=False).mean()
    out["ema_30"] = out["close"].ewm(span=30, adjust=False).mean()
    out["ema_60"] = out["close"].ewm(span=60, adjust=False).mean()

    out["mom_5"] = out["close"].pct_change(5)
    out["mom_20"] = out["close"].pct_change(20)
    out["mom_60"] = out["close"].pct_change(60)

    out["range_hl"] = (out["high"] - out["low"]) / out["close"].replace(0, np.nan)
    out["atr_14"] = _atr(out, 14)
    out["rv_20"] = out["log_ret_1"].rolling(20).std() * np.sqrt(252)

    out["vol_ma_20"] = out["volume"].rolling(20).mean()
    out["vol_ratio_20"] = out["volume"] / out["vol_ma_20"]

    out["dist_ema30"] = (out["close"] - out["ema_30"]) / out["ema_30"].replace(0, np.nan)
    out["dist_ema60"] = (out["close"] - out["ema_60"]) / out["ema_60"].replace(0, np.nan)
    out["breakout_20"] = out["close"] / out["high"].rolling(20).max().shift(1) - 1
    out["breakdown_20"] = out["close"] / out["low"].rolling(20).min().shift(1) - 1

    return out.replace([np.inf, -np.inf], np.nan)


def _atr(df: pd.DataFrame, window: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window).mean()
