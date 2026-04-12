from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import numpy as np
import pandas as pd

from config import StrategyConfig


# Bar labels at which new entries are blocked (session close bars).
_SESSION_CLOSE_HHMM: frozenset = frozenset({"14:45", "02:15"})


def _is_session_close_bar(date_value: Any) -> bool:
    try:
        return str(date_value)[11:16] in _SESSION_CLOSE_HHMM
    except Exception:
        return False


@dataclass
class EngineContext:
    active_position: int = 0  # -1 short, 0 flat, 1 long
    entry_price: float | None = None
    entry_index: int | None = None
    entry_setup_type: str | None = None
    breakout_level: float | None = None
    cooldown_until: int = -1
    last_failure_reason: str | None = None
    trend_anchor_price: float | None = None
    trend_anchor_index: int | None = None


def run_signal_engine(df: pd.DataFrame, config: StrategyConfig, instrument: str = "UNKNOWN") -> pd.DataFrame:
    out = df.copy().reset_index(drop=True)
    _init_output_columns(out, instrument)
    ctx = EngineContext()

    for i in range(len(out)):
        row = out.iloc[i]
        out.at[i, "state"] = infer_state(i, out, ctx)
        out.at[i, "cooldown_flag"] = i <= ctx.cooldown_until
        out.at[i, "bars_since_entry"] = np.nan if ctx.entry_index is None else i - ctx.entry_index

        evaluate_breakout_candidate(out, i, config)
        evaluate_pullback_reconfirm_candidate(out, i, config, ctx)

        if ctx.active_position != 0:
            monitor_live_position(out, i, config, ctx)
        else:
            maybe_enter_position(out, i, config, ctx)

        finalize_action(out, i, ctx)

    return out


def _init_output_columns(df: pd.DataFrame, instrument: str) -> None:
    defaults = {
        "instrument": instrument,
        "state": "observe",
        "setup_type": "none",
        "side": "flat",
        "setup_score": np.nan,
        "breakout_level": np.nan,
        "entry_candidate_price": np.nan,
        "hard_stop_price": np.nan,
        "bars_since_setup": np.nan,
        "bars_since_entry": np.nan,
        "volume_ratio": np.nan,
        "movement_efficiency": np.nan,
        "vol_follow_through_ratio": np.nan,
        "failure_risk_flag": False,
        "cooldown_flag": False,
        "action_suggestion": "observe",
        "entry_signal": False,
        "exit_signal": False,
        "failure_reason": None,
        "position": 0,
        "position_side": "flat",
        "close_hold_ratio": np.nan,
        "expansion_pct": np.nan,
        "disagreement_flag": False,
        "trend_score": np.nan,
        "prior_trend_score": np.nan,
        "pullback_depth_pct": np.nan,
        "candidate_long": False,
        "candidate_short": False,
    }
    for col, value in defaults.items():
        df[col] = value


def infer_state(i: int, df: pd.DataFrame, ctx: EngineContext) -> str:
    if i <= ctx.cooldown_until:
        return "cooldown"
    if ctx.active_position != 0:
        return "position_live"
    if ctx.last_failure_reason:
        return "observe_after_exit"
    return "observe"


def evaluate_breakout_candidate(df: pd.DataFrame, i: int, config: StrategyConfig) -> None:
    row = df.iloc[i]
    if pd.isna(row.get("rolling_high")) or pd.isna(row.get("rolling_low")):
        return

    up_break = row["close"] > row["rolling_high"]
    down_break = row["close"] < row["rolling_low"]
    if not up_break and not down_break:
        return

    side = 1 if up_break else -1
    level = row["rolling_high"] if up_break else row["rolling_low"]
    expansion_pct = ((row["close"] - level) / level) * side
    close_hold_ratio = _calc_close_hold_ratio(row, level, side)
    volume_ratio = row.get("volume_ratio_20", np.nan)
    volume_z = row.get("volume_zscore_20", np.nan)
    trend_score = _trend_score(row, side)

    breakout_score = np.nanmean([
        _bounded_score(expansion_pct / max(config.min_expansion_pct, 1e-8)),
        _bounded_score(close_hold_ratio / max(config.min_close_hold_ratio, 1e-8)),
        _bounded_score(volume_ratio / max(config.min_volume_ratio, 1e-8)),
        _bounded_score((volume_z + 3.0) / (config.min_volume_zscore + 3.0)),
        _bounded_score((trend_score + 1.0) / 2.0),
    ])

    df.at[i, "setup_type"] = "confirmed_breakout"
    df.at[i, "side"] = "long" if side > 0 else "short"
    df.at[i, "setup_score"] = breakout_score
    df.at[i, "breakout_level"] = level
    df.at[i, "entry_candidate_price"] = row["close"]
    df.at[i, "hard_stop_price"] = row["close"] * (1 - config.hard_stop_pct * side)
    df.at[i, "bars_since_setup"] = 0
    df.at[i, "volume_ratio"] = volume_ratio
    df.at[i, "movement_efficiency"] = row.get("movement_efficiency_3", np.nan)
    df.at[i, "close_hold_ratio"] = close_hold_ratio
    df.at[i, "expansion_pct"] = expansion_pct
    df.at[i, "trend_score"] = trend_score

    if side > 0:
        df.at[i, "candidate_long"] = breakout_score >= config.min_breakout_score
    else:
        df.at[i, "candidate_short"] = breakout_score >= config.min_breakout_score


def evaluate_pullback_reconfirm_candidate(df: pd.DataFrame, i: int, config: StrategyConfig, ctx: EngineContext) -> None:
    if i < max(config.pullback_lookback_bars, 5):
        return
    row = df.iloc[i]

    prev_window = df.iloc[max(0, i - config.pullback_lookback_bars):i]
    if prev_window.empty:
        return

    price_now = row["close"]
    local_high = prev_window["high"].max()
    local_low = prev_window["low"].min()
    ema20 = row.get("ema_20", np.nan)

    long_prior = (prev_window["close"].iloc[-1] > prev_window["close"].iloc[0]) and (row["close"] > ema20)
    short_prior = (prev_window["close"].iloc[-1] < prev_window["close"].iloc[0]) and (row["close"] < ema20)
    if not long_prior and not short_prior:
        return

    side = 1 if long_prior else -1
    swing_extreme = local_high if side > 0 else local_low
    pullback_ref = prev_window["low"].min() if side > 0 else prev_window["high"].max()
    if pd.isna(swing_extreme) or pd.isna(pullback_ref):
        return

    trend_span = abs(local_high - local_low)
    if trend_span <= 0:
        return
    pullback_depth_pct = abs(swing_extreme - pullback_ref) / max(abs(swing_extreme), 1e-8)
    reconfirm_strength = ((price_now - ema20) / ema20) * side if pd.notna(ema20) and ema20 != 0 else np.nan
    prior_trend_score = _bounded_score(abs(prev_window["close"].pct_change(len(prev_window) - 1).iloc[-1]) / 0.03)

    volume_ratio = row.get("volume_ratio_20", np.nan)
    close_strength = row.get("close_location_in_bar", np.nan) if side > 0 else 1 - row.get("close_location_in_bar", np.nan)
    score = np.nanmean([
        _bounded_score(prior_trend_score / max(config.min_prior_trend_score, 1e-8)),
        _bounded_score(config.max_pullback_depth_pct / max(pullback_depth_pct, 1e-8)),
        _bounded_score(volume_ratio / max(config.min_reconfirm_volume_ratio, 1e-8)),
        _bounded_score(close_strength / max(config.min_reconfirm_close_strength, 1e-8)),
        _bounded_score((reconfirm_strength + 0.03) / 0.06),
    ])

    if score < config.min_reconfirm_score:
        return

    existing_score = df.at[i, "setup_score"]
    if pd.notna(existing_score) and existing_score >= score:
        return

    df.at[i, "setup_type"] = "pullback_reconfirm"
    df.at[i, "side"] = "long" if side > 0 else "short"
    df.at[i, "setup_score"] = score
    df.at[i, "entry_candidate_price"] = price_now
    df.at[i, "hard_stop_price"] = price_now * (1 - config.hard_stop_pct * side)
    df.at[i, "volume_ratio"] = volume_ratio
    df.at[i, "movement_efficiency"] = row.get("movement_efficiency_3", np.nan)
    df.at[i, "prior_trend_score"] = prior_trend_score
    df.at[i, "pullback_depth_pct"] = pullback_depth_pct
    if side > 0:
        df.at[i, "candidate_long"] = True
    else:
        df.at[i, "candidate_short"] = True


def maybe_enter_position(df: pd.DataFrame, i: int, config: StrategyConfig, ctx: EngineContext) -> None:
    if i <= ctx.cooldown_until:
        return
    row = df.iloc[i]
    if _is_session_close_bar(row.get("date")):
        return
    side = row["side"]
    setup_type = row["setup_type"]
    score = row["setup_score"]
    if setup_type == "none" or pd.isna(score):
        return
    if setup_type == "confirmed_breakout" and score < config.min_breakout_score:
        return
    if setup_type == "pullback_reconfirm" and score < config.min_reconfirm_score:
        return

    direction = 1 if side == "long" else -1
    ctx.active_position = direction
    ctx.entry_price = row["close"]
    ctx.entry_index = i
    ctx.entry_setup_type = setup_type
    ctx.breakout_level = row["breakout_level"] if pd.notna(row["breakout_level"]) else row["close"]
    ctx.last_failure_reason = None
    if setup_type in {"confirmed_breakout", "pullback_reconfirm"}:
        ctx.trend_anchor_price = row["close"]
        ctx.trend_anchor_index = i

    df.at[i, "entry_signal"] = True
    df.at[i, "action_suggestion"] = "enter_long" if direction > 0 else "enter_short"
    df.at[i, "position"] = direction
    df.at[i, "position_side"] = side


def monitor_live_position(df: pd.DataFrame, i: int, config: StrategyConfig, ctx: EngineContext) -> None:
    row = df.iloc[i]
    direction = ctx.active_position
    assert direction != 0
    df.at[i, "position"] = direction
    df.at[i, "position_side"] = "long" if direction > 0 else "short"

    entry_price = ctx.entry_price or row["close"]
    bars_since_entry = i - (ctx.entry_index or i)
    hard_stop_price = entry_price * (1 - config.hard_stop_pct * direction)
    df.at[i, "hard_stop_price"] = hard_stop_price

    stop_hit = (row["low"] <= hard_stop_price) if direction > 0 else (row["high"] >= hard_stop_price)
    if bars_since_entry <= 1 and stop_hit:
        _trigger_exit(df, i, ctx, "hard_stop_failure", config)
        return

    move_eff = row.get("movement_efficiency_3", np.nan)
    vdr_z = row.get("vdr_z_20", np.nan)
    volume_ratio = row.get("volume_ratio_20", np.nan)
    df.at[i, "movement_efficiency"] = move_eff
    df.at[i, "volume_ratio"] = volume_ratio

    disagreement = pd.notna(vdr_z) and vdr_z > config.max_volume_displacement_ratio_z and pd.notna(move_eff) and move_eff < config.min_movement_efficiency
    df.at[i, "disagreement_flag"] = disagreement
    if disagreement:
        df.at[i, "failure_risk_flag"] = True
        _trigger_exit(df, i, ctx, "disagreement_failure", config)
        return

    if bars_since_entry >= 1:
        past_window = df.iloc[max(0, i - config.follow_through_bars): i + 1]
        if len(past_window) >= 2:
            past_vol = past_window["rv_10"].iloc[:-1].mean()
            current_vol = past_window["rv_10"].iloc[-1]
            ratio = current_vol / past_vol if pd.notna(past_vol) and past_vol not in (0, np.nan) else np.nan
            df.at[i, "vol_follow_through_ratio"] = ratio

    if bars_since_entry >= config.follow_through_bars:
        follow_move = ((row["close"] - entry_price) / entry_price) * direction
        vol_ratio = df.at[i, "vol_follow_through_ratio"]
        if (pd.notna(follow_move) and follow_move < config.min_expansion_pct * 0.5) or (pd.notna(vol_ratio) and vol_ratio < 0.8):
            _trigger_exit(df, i, ctx, "momentum_decay_failure", config)
            return

    if bars_since_entry > config.follow_through_bars + 1:
        follow_move = ((row["close"] - entry_price) / entry_price) * direction
        if pd.notna(follow_move) and follow_move <= 0:
            _trigger_exit(df, i, ctx, "time_expiry_failure", config)
            return


def _trigger_exit(df: pd.DataFrame, i: int, ctx: EngineContext, reason: str, config: StrategyConfig) -> None:
    df.at[i, "exit_signal"] = True
    df.at[i, "failure_reason"] = reason
    df.at[i, "action_suggestion"] = "exit_to_flat"
    df.at[i, "failure_risk_flag"] = True
    df.at[i, "position"] = 0
    df.at[i, "position_side"] = "flat"

    ctx.active_position = 0
    ctx.entry_price = None
    ctx.entry_index = None
    ctx.entry_setup_type = None
    ctx.breakout_level = None
    ctx.last_failure_reason = reason
    if reason in {"disagreement_failure", "hard_stop_failure"}:
        ctx.cooldown_until = i + config.cooldown_bars_after_failure


def finalize_action(df: pd.DataFrame, i: int, ctx: EngineContext) -> None:
    if df.at[i, "exit_signal"]:
        return
    if df.at[i, "entry_signal"]:
        return
    if df.at[i, "candidate_long"]:
        df.at[i, "action_suggestion"] = "candidate_long"
    elif df.at[i, "candidate_short"]:
        df.at[i, "action_suggestion"] = "candidate_short"
    else:
        df.at[i, "action_suggestion"] = "observe"



def _calc_close_hold_ratio(row: pd.Series, level: float, side: int) -> float:
    expansion = ((row["high"] - level) / level) if side > 0 else ((level - row["low"]) / level)
    if not pd.notna(expansion) or expansion <= 0:
        return np.nan
    hold = ((row["close"] - level) / level) if side > 0 else ((level - row["close"]) / level)
    return hold / expansion if expansion else np.nan


def _trend_score(row: pd.Series, side: int) -> float:
    slope = row.get("trend_slope", np.nan)
    mom3 = row.get("momentum_3", np.nan)
    mom5 = row.get("momentum_5", np.nan)
    score = np.nanmean([
        0.5 + np.clip((slope * side) / 0.01, -1, 1) * 0.5 if pd.notna(slope) else np.nan,
        0.5 + np.clip((mom3 * side) / 0.02, -1, 1) * 0.5 if pd.notna(mom3) else np.nan,
        0.5 + np.clip((mom5 * side) / 0.03, -1, 1) * 0.5 if pd.notna(mom5) else np.nan,
    ])
    return float(score) if pd.notna(score) else np.nan


def _bounded_score(value: float) -> float:
    if pd.isna(value):
        return np.nan
    return float(np.clip(value, 0.0, 1.5) / 1.5)
