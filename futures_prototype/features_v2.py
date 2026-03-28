from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}
TIME_COLUMN_CANDIDATES = [
    "date",
    "datetime",
    "time",
    "timestamp",
    "trade_time",
    "bar_time",
    "candle_begin_time",
]


def load_ohlcv(path: str, timeframe: str | None = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    time_col = _find_time_column(df.columns)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if time_col is None:
        raise ValueError(f"missing time column, expected one of: {TIME_COLUMN_CANDIDATES}")
    out = df.copy()
    if time_col != "date":
        out = out.rename(columns={time_col: "date"})
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date").reset_index(drop=True)
    if timeframe:
        out = resample_ohlcv(out, timeframe)
    return out


def _find_time_column(columns: pd.Index | list[str]) -> str | None:
    colset = set(columns)
    for name in TIME_COLUMN_CANDIDATES:
        if name in colset:
            return name
    lowered = {str(col).lower(): col for col in columns}
    for name in TIME_COLUMN_CANDIDATES:
        if name in lowered:
            return str(lowered[name])
    return None


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    rule = normalize_timeframe(timeframe)
    if rule is None:
        return df.copy().reset_index(drop=True)
    out = df.copy().sort_values("date").set_index("date")
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    resampled = out.resample(rule, label="right", closed="right").agg(agg)
    resampled = resampled.dropna(subset=["open", "high", "low", "close"]).reset_index()
    return resampled


def normalize_timeframe(timeframe: str | None) -> str | None:
    if timeframe is None:
        return None
    text = str(timeframe).strip().lower()
    mapping = {
        "1m": "1min",
        "3m": "3min",
        "5m": "5min",
        "10m": "10min",
        "15m": "15min",
        "30m": "30min",
        "45m": "45min",
        "60m": "60min",
        "1h": "60min",
        "2h": "120min",
        "4h": "240min",
        "1d": "1D",
        "d": "1D",
        "day": "1D",
    }
    if text in mapping:
        return mapping[text]
    return timeframe


def add_core_features(df: pd.DataFrame, breakout_lookback_bars: int = 20) -> pd.DataFrame:
    out = df.copy()
    out["prev_close"] = out["close"].shift(1)
    out["ret_1"] = out["close"].pct_change()
    out["log_ret_1"] = np.log(out["close"]).diff()

    out["true_range"] = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - out["prev_close"]).abs(),
            (out["low"] - out["prev_close"]).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr_14"] = out["true_range"].rolling(14).mean()
    out["rv_10"] = out["log_ret_1"].rolling(10).std() * np.sqrt(252)
    out["rv_20"] = out["log_ret_1"].rolling(20).std() * np.sqrt(252)

    out["vol_ma_20"] = out["volume"].rolling(20).mean()
    out["vol_std_20"] = out["volume"].rolling(20).std()
    out["volume_ratio_20"] = out["volume"] / out["vol_ma_20"].replace(0, np.nan)
    out["volume_zscore_20"] = (out["volume"] - out["vol_ma_20"]) / out["vol_std_20"].replace(0, np.nan)

    out["rolling_high"] = out["high"].rolling(breakout_lookback_bars).max().shift(1)
    out["rolling_low"] = out["low"].rolling(breakout_lookback_bars).min().shift(1)

    out["close_location_in_bar"] = (out["close"] - out["low"]) / (out["high"] - out["low"]).replace(0, np.nan)
    out["bar_return"] = (out["close"] - out["open"]) / out["open"].replace(0, np.nan)
    out["range_pct"] = (out["high"] - out["low"]) / out["close"].replace(0, np.nan)

    out["ema_8"] = out["close"].ewm(span=8, adjust=False).mean()
    out["ema_20"] = out["close"].ewm(span=20, adjust=False).mean()
    out["trend_slope"] = (out["ema_8"] - out["ema_20"]) / out["ema_20"].replace(0, np.nan)

    out["movement_efficiency_3"] = movement_efficiency(out["close"], out["true_range"], 3)
    out["movement_efficiency_5"] = movement_efficiency(out["close"], out["true_range"], 5)
    out["volume_displacement_ratio_3"] = volume_displacement_ratio(out["close"], out["volume"], 3)
    out["volume_displacement_ratio_5"] = volume_displacement_ratio(out["close"], out["volume"], 5)
    out["vdr_z_20"] = zscore(out["volume_displacement_ratio_3"], 20)

    out["price_vs_ema20"] = (out["close"] - out["ema_20"]) / out["ema_20"].replace(0, np.nan)
    out["momentum_3"] = out["close"].pct_change(3)
    out["momentum_5"] = out["close"].pct_change(5)

    return out.replace([np.inf, -np.inf], np.nan)


def movement_efficiency(close: pd.Series, true_range: pd.Series, window: int) -> pd.Series:
    net_move = close.diff(window).abs()
    path = true_range.rolling(window).sum().replace(0, np.nan)
    return net_move / path


def volume_displacement_ratio(close: pd.Series, volume: pd.Series, window: int, eps: float = 1e-8) -> pd.Series:
    rolling_volume = volume.rolling(window).sum()
    price_change = close.diff(window).abs()
    return rolling_volume / np.maximum(price_change, eps)


def zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=max(5, window // 2)).mean()
    std = series.rolling(window, min_periods=max(5, window // 2)).std().replace(0, np.nan)
    return (series - mean) / std
