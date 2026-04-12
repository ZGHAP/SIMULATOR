from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def run_event_backtest(signal_df: pd.DataFrame, fee_bps: float = 2.0) -> tuple[pd.DataFrame, dict]:
    out = signal_df.copy().sort_values("date").reset_index(drop=True)
    out["exec_position"] = out["position"].shift(1).fillna(0)
    out["next_ret"] = out["close"].pct_change().shift(-1)
    out["turnover"] = out["exec_position"].diff().abs().fillna(out["exec_position"].abs())

    fee_rate = fee_bps / 10000.0
    out["gross_pnl"] = out["exec_position"] * out["next_ret"]
    out["cost"] = out["turnover"] * fee_rate
    out["net_pnl"] = out["gross_pnl"] - out["cost"]
    out["equity"] = (1.0 + out["net_pnl"].fillna(0.0)).cumprod()

    metrics = summarize_backtest(out)
    return out, metrics


def summarize_backtest(df: pd.DataFrame) -> dict:
    pnl = df["net_pnl"].dropna()
    if pnl.empty:
        return {"rows": int(len(df)), "error": "no pnl rows"}

    equity = (1.0 + pnl).cumprod()
    peak = equity.cummax()
    drawdown = equity / peak - 1.0

    ann_factor = 252 * 16
    avg = pnl.mean()
    vol = pnl.std(ddof=0)
    sharpe = np.nan if vol == 0 else avg / vol * np.sqrt(ann_factor)

    return {
        "rows": int(len(df)),
        "entries": int(df["entry_signal"].sum()),
        "exits": int(df["exit_signal"].sum()),
        "avg_abs_position": float(df["exec_position"].abs().mean()),
        "cum_return": float(equity.iloc[-1] - 1.0),
        "ann_return": float(avg * ann_factor),
        "ann_vol": float(vol * np.sqrt(ann_factor)),
        "sharpe": None if pd.isna(sharpe) else float(sharpe),
        "max_drawdown": float(drawdown.min()),
        "win_rate": float((pnl > 0).mean()),
    }


def save_json(payload: dict, path: str) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output
