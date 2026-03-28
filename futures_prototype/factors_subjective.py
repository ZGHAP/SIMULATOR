from __future__ import annotations

"""
主观交易信号识别因子（第一版）
================================

这个文件不是拿来“直接预测收益”的。
它的目标更接近：

1. 识别当前 30 根窗口属于什么地形；
2. 识别当前 bar / 最近几根 bar 是否出现了“足够推动交易”的变化；
3. 把这些变化组织成几个用户可读的信号家族分数。

设计原则
--------
- 优先可解释，不优先复杂度；
- 注释尽量用交易语言，而不是只写数值计算；
- 第一版更像“因子字典 + 家族打分器”，不是最终策略；
- 不把最终 pnl 直接当作标签，避免 hindsight bias。

当前信号家族
------------
- continuation: 推进中继型
- release: 压缩释放型
- reconfirm: 再确认型
- reversal: 失效后反向卡位型
- noise: 噪音排除类（不是交易信号，而是负向过滤）
"""

import numpy as np
import pandas as pd


def add_subjective_factors(df: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """
    为 OHLCV + core features DataFrame 追加第一版主观交易识别因子。

    Parameters
    ----------
    df:
        通常来自 `load_ohlcv(...)` + `add_core_features(...)` 的结果。
    window:
        识别“入场前状态”时参考的主窗口长度，默认 30 根。

    Returns
    -------
    DataFrame
        在原始输入基础上追加一批基础因子和信号家族分数。
    """
    out = df.copy()

    # ------------------------------------------------------------------
    # 1) 基础形态因子：先把每根 K 线拆成交易员真正会看的组成部分。
    # ------------------------------------------------------------------
    # 实体大小：不是方向，只是“这根 bar 到底有没有实质推进”。
    out["body_abs"] = (out["close"] - out["open"]).abs()

    # 上下影线：用来区分“实体推进”和“插针/博弈/扫单感”。
    out["upper_wick"] = out["high"] - out[["open", "close"]].max(axis=1)
    out["lower_wick"] = out[["open", "close"]].min(axis=1) - out["low"]

    # 影线占整个 range 的比例。
    total_range = (out["high"] - out["low"]).replace(0, np.nan)
    out["body_range_ratio"] = out["body_abs"] / total_range
    out["upper_wick_ratio"] = out["upper_wick"] / total_range
    out["lower_wick_ratio"] = out["lower_wick"] / total_range

    # 同向推进计数：交易员常看的不是单根 bar，而是“最近是不是一串同向在推”。
    out["bull_bar"] = (out["close"] > out["open"]).astype(float)
    out["bear_bar"] = (out["close"] < out["open"]).astype(float)
    out["bull_count_5"] = out["bull_bar"].rolling(5, min_periods=1).sum()
    out["bear_count_5"] = out["bear_bar"].rolling(5, min_periods=1).sum()

    # ------------------------------------------------------------------
    # 2) 地形因子：先判断市场背景，而不是一上来就问该不该做。
    # ------------------------------------------------------------------
    out["window_high_30"] = out["high"].rolling(window, min_periods=max(10, window // 2)).max()
    out["window_low_30"] = out["low"].rolling(window, min_periods=max(10, window // 2)).min()
    out["window_range_30"] = (out["window_high_30"] - out["window_low_30"]).replace(0, np.nan)

    # 当前 close 在 30 根窗口中的位置。靠上、靠下、还是在中间噪音区。
    out["close_pos_in_window_30"] = (out["close"] - out["window_low_30"]) / out["window_range_30"]

    # 30 根窗口趋势斜率：不是最终信号，只是判断背景更像上推、下压还是横盘。
    out["trend_slope_30"] = rolling_slope(out["close"], window)

    # 短波动 / 长波动 比例：用来感知“是不是压缩了”。
    short_range = total_range.rolling(5, min_periods=3).mean()
    long_range = total_range.rolling(20, min_periods=10).mean().replace(0, np.nan)
    out["range_contraction_ratio_5_20"] = short_range / long_range

    # 窗口中线附近停留程度。很多“不是你的交易”的状态都发生在区间中部。
    out["mid_zone_distance"] = (out["close_pos_in_window_30"] - 0.5).abs()

    # ------------------------------------------------------------------
    # 3) 触发因子：当前 bar / 最近几根有没有变化到达“可试探阈值”。
    # ------------------------------------------------------------------
    # 释放强度：当前 range 是否显著高于近期背景。
    out["range_expansion_ratio"] = total_range / long_range

    # 收盘质量：实体不够、收得不好，很多看起来热闹的 bar 其实不值得交易。
    out["close_quality_bull"] = out["close_location_in_bar"]
    out["close_quality_bear"] = 1.0 - out["close_location_in_bar"]

    # 恢复力度：若是顺势恢复型，最近 3/5 根应该开始出现更高效率的位移。
    out["resume_strength_3"] = (
        positive_clip(out["momentum_3"]) * positive_clip(out["movement_efficiency_3"])
    )
    out["resume_strength_5"] = (
        positive_clip(out["momentum_5"]) * positive_clip(out["movement_efficiency_5"])
    )

    # 回撤深度：中继型通常允许回撤，但不应深到把前面推进意义完全抹掉。
    out["pullback_depth_ratio_5"] = pullback_depth_ratio(out["close"], 5)

    # 再确认：不是第一次突破，而是前面试过一次后，重新站稳。
    out["distance_above_prev_high"] = (out["close"] - out["rolling_high"]) / out["close"].replace(0, np.nan)
    out["distance_below_prev_low"] = (out["rolling_low"] - out["close"]) / out["close"].replace(0, np.nan)
    out["reaccept_high_score"] = positive_clip(out["distance_above_prev_high"])
    out["reaccept_low_score"] = positive_clip(out["distance_below_prev_low"])

    # 失效切换：原方向如果“该推进没推进”，就会从效率和收盘质量上先变差。
    out["disagreement_proxy"] = disagreement_proxy(total_range, out["body_abs"])
    out["trend_fade_proxy"] = negative_clip(out["movement_efficiency_3"] - out["movement_efficiency_5"])

    # ------------------------------------------------------------------
    # 3.5) 用户新增的“小趋势逆转态”专用因子
    # ------------------------------------------------------------------
    # 这组因子对应用户明确描述的事件链：
    # 1. 先有一次明显下杀（大阴 / 大下影）
    # 2. 紧接着出现快速强反弹
    # 3. 再次下探但不破前低
    # 4. 最终收在反弹区相对高位
    # 它本质上是 failed breakdown -> re-accept -> micro reversal。

    # A. 第一次下杀是否足够明显。
    # 允许两种表达：
    # - 大阴实体下杀
    # - 长下影的剧烈下探
    selloff_body = bounded_score((-out["bar_return"]).fillna(0) / 0.012)
    selloff_range = bounded_score((out["range_expansion_ratio"] - 1.0).fillna(0) / 1.5)
    selloff_tail = bounded_score((out["lower_wick_ratio"] - 0.35).fillna(0) / 0.45)
    out["failed_breakdown_seed_score"] = bounded_score(
        0.45 * selloff_body +
        0.30 * selloff_range +
        0.25 * selloff_tail
    )

    # B. 下杀后是否马上出现强反弹。
    # 这里强调“急反”——实体、收盘质量、效率都要明显改善。
    prior_seed = out["failed_breakdown_seed_score"].shift(1).rolling(3, min_periods=1).max()
    rebound_impulse = bounded_score(out["bar_return"].fillna(0) / 0.012)
    rebound_close = bounded_score((out["close_quality_bull"] - 0.55).fillna(0) / 0.45)
    rebound_eff = bounded_score((out["movement_efficiency_3"] - 0.15).fillna(0) / 0.55)
    out["fast_rebound_score"] = bounded_score(
        0.35 * prior_seed +
        0.25 * rebound_impulse +
        0.20 * rebound_close +
        0.20 * rebound_eff
    )

    # C. 第二次下探但不破前低。
    # 用最近几根的最低点做二次测试，要求：
    # - 新低没有明显跌破前次极值
    # - 当前 close 已重新站回测试低点之上
    local_min_3 = out["low"].rolling(3, min_periods=1).min()
    prev_local_min_3 = local_min_3.shift(1).rolling(4, min_periods=1).min()
    hold_above_low = (out["close"] - local_min_3) / (total_range.replace(0, np.nan))
    no_new_low_score = bounded_score(1.0 - negative_clip((prev_local_min_3 - local_min_3) / out["close"].replace(0, np.nan) / 0.004))
    hold_after_retest = bounded_score((hold_above_low - 0.35).fillna(0) / 0.65)
    rebound_memory = out["fast_rebound_score"].shift(1).rolling(4, min_periods=1).max()
    out["second_test_hold_score"] = bounded_score(
        0.35 * rebound_memory +
        0.35 * no_new_low_score.fillna(0) +
        0.30 * hold_after_retest.fillna(0)
    )

    # D. 第二次分歧检验：反弹后的再次上冲失败，但空头也未重新接管。
    # 这一步对应用户说的：红线再冲后失败，随后一个绿线扛住，下跌动量消散。
    recent_rebound_memory = out["fast_rebound_score"].shift(1).rolling(5, min_periods=1).max()
    breakout_try = bounded_score((out["close_pos_in_window_30"] - 0.58).fillna(0) / 0.32)
    failed_up_close = bounded_score((0.70 - out["close_quality_bull"]).fillna(0) / 0.70)
    failed_up_body = bounded_score((0.55 - out["body_range_ratio"]).fillna(0) / 0.55)
    bearish_retake_fail = bounded_score((out["close_quality_bull"] - 0.52).fillna(0) / 0.48)
    out["second_disagreement_absorption_score"] = bounded_score(
        0.20 * recent_rebound_memory +
        0.20 * breakout_try +
        0.20 * failed_up_close +
        0.15 * failed_up_body +
        0.25 * bearish_retake_fail
    )

    # E. 最终是否守在“反弹区相对高位”。
    # 不是要求创新高，而是要求回到反弹带里的高位并站稳。
    rebound_high_5 = out["high"].rolling(5, min_periods=2).max()
    rebound_low_5 = out["low"].rolling(5, min_periods=2).min()
    rebound_zone_range = (rebound_high_5 - rebound_low_5).replace(0, np.nan)
    rebound_zone_hold = (out["close"] - rebound_low_5) / rebound_zone_range
    out["rebound_zone_hold_score"] = bounded_score(
        0.40 * bounded_score((rebound_zone_hold - 0.60).fillna(0) / 0.40) +
        0.30 * bounded_score((out["close_quality_bull"] - 0.55).fillna(0) / 0.45) +
        0.30 * out["second_disagreement_absorption_score"]
    )

    # 最终组合：小趋势逆转态总分。
    out["micro_reversal_long_score"] = bounded_score(
        0.16 * out["failed_breakdown_seed_score"] +
        0.24 * out["fast_rebound_score"] +
        0.20 * out["second_test_hold_score"] +
        0.18 * out["second_disagreement_absorption_score"] +
        0.22 * out["rebound_zone_hold_score"]
    )

    # 先做一版可审阅的规则触发：不是最终交易系统，而是“像不像会出手”。
    out["rule_big_selloff"] = out["failed_breakdown_seed_score"] >= 0.55
    out["rule_fast_rebound"] = out["fast_rebound_score"] >= 0.50
    out["rule_second_test_hold"] = out["second_test_hold_score"] >= 0.52
    out["rule_second_disagreement_absorb"] = out["second_disagreement_absorption_score"] >= 0.50
    out["rule_rebound_zone_hold"] = out["rebound_zone_hold_score"] >= 0.56
    out["rule_close_entry_long"] = (
        out["rule_big_selloff"] &
        out["rule_fast_rebound"] &
        out["rule_second_test_hold"] &
        out["rule_second_disagreement_absorb"] &
        out["rule_rebound_zone_hold"] &
        (out["micro_reversal_long_score"] >= 0.58)
    )

    # 额外路径判断：若已出现明显利润、但回撤仍受控，则允许“多赌一周期”。
    rebound_range = (out["high"].rolling(3, min_periods=2).max() - out["low"].rolling(3, min_periods=2).min()).replace(0, np.nan)
    pullback_from_high = (out["high"].rolling(3, min_periods=2).max() - out["close"]) / rebound_range
    out["micro_reversal_extend_score"] = bounded_score(
        0.45 * bounded_score((out["range_expansion_ratio"] - 1.05).fillna(0) / 1.2) +
        0.30 * bounded_score(0.45 - pullback_from_high.fillna(1.0)) +
        0.25 * out["rebound_zone_hold_score"]
    )

    # ------------------------------------------------------------------
    # 4) 信号家族评分：先做规则型分数组合，后面再考虑统计校准。
    # ------------------------------------------------------------------
    out["trend_push_up_score"] = bounded_score(
        0.45 * positive_clip(out["trend_slope_30"]) +
        0.25 * positive_clip(out["close_pos_in_window_30"] - 0.55) +
        0.30 * positive_clip(out["movement_efficiency_5"])
    )

    out["trend_push_down_score"] = bounded_score(
        0.45 * positive_clip(-out["trend_slope_30"]) +
        0.25 * positive_clip(0.45 - out["close_pos_in_window_30"]) +
        0.30 * positive_clip(out["movement_efficiency_5"])
    )

    # 压缩不是突破信号，只是说明市场在憋。压缩越明显、位置越靠边，后续释放越值得看。
    out["compression_score"] = bounded_score(
        0.60 * positive_clip(1.0 - out["range_contraction_ratio_5_20"]) +
        0.40 * positive_clip(out["mid_zone_distance"] - 0.10)
    )

    # continuation: 已有方向，回撤不深，恢复 bar 收盘质量好，且效率重新上来。
    out["continuation_score"] = bounded_score(
        0.30 * out["trend_push_up_score"].combine(out["trend_push_down_score"], max) +
        0.20 * positive_clip(0.35 - out["pullback_depth_ratio_5"]) +
        0.25 * out[["resume_strength_3", "resume_strength_5"]].max(axis=1) +
        0.25 * out[["close_quality_bull", "close_quality_bear"]].max(axis=1)
    )

    # release: 压缩明显 + 当前 bar 真正扩张 + 收盘站得住。
    out["release_score"] = bounded_score(
        0.35 * out["compression_score"] +
        0.35 * positive_clip(out["range_expansion_ratio"] - 1.10) +
        0.30 * out[["close_quality_bull", "close_quality_bear"]].max(axis=1)
    )

    # reconfirm: 前面已经有过突破记忆，现在重新站回方向一侧。
    out["reconfirm_score"] = bounded_score(
        0.35 * out[["reaccept_high_score", "reaccept_low_score"]].max(axis=1) +
        0.25 * out[["close_quality_bull", "close_quality_bear"]].max(axis=1) +
        0.20 * out[["trend_push_up_score", "trend_push_down_score"]].max(axis=1) +
        0.20 * positive_clip(out["range_expansion_ratio"] - 0.95)
    )

    # reversal: 原方向效率变差、分歧上升、当前 bar 对侧收盘质量强。
    out["reversal_score"] = bounded_score(
        0.25 * out["disagreement_proxy"] +
        0.20 * out["trend_fade_proxy"] +
        0.20 * out[["close_quality_bull", "close_quality_bear"]].max(axis=1) +
        0.35 * out["micro_reversal_long_score"]
    )

    # noise: 趋势不清、压缩不明显、扩张也不干净，通常更像用户会 skip 的场景。
    out["noise_score"] = bounded_score(
        0.35 * positive_clip(0.08 - out["mid_zone_distance"]) +
        0.25 * positive_clip(0.20 - out["body_range_ratio"]) +
        0.20 * positive_clip(1.05 - out["range_expansion_ratio"]) +
        0.20 * positive_clip(0.15 - out[["trend_push_up_score", "trend_push_down_score"]].max(axis=1))
    )

    # ------------------------------------------------------------------
    # 5) 总信号层：不是最终交易规则，只是把“像不像你的交易”压成可读分数。
    # ------------------------------------------------------------------
    out["signal_score"] = bounded_score(
        0.30 * out[["continuation_score", "release_score", "reconfirm_score", "reversal_score"]].max(axis=1) +
        0.20 * out[["trend_push_up_score", "trend_push_down_score"]].max(axis=1) +
        0.20 * positive_clip(out["range_expansion_ratio"] - 1.0) +
        0.15 * out[["close_quality_bull", "close_quality_bear"]].max(axis=1) +
        0.15 * positive_clip(1.0 - out["noise_score"])
    )

    # 方向偏置：这里只给“更像 long 还是 short”的代理，不是确定信号。
    out["long_bias_score"] = bounded_score(
        0.45 * out["trend_push_up_score"] +
        0.20 * positive_clip(out["close_quality_bull"] - 0.55) +
        0.20 * out["reaccept_high_score"] +
        0.15 * positive_clip(out["resume_strength_3"])
    )
    out["short_bias_score"] = bounded_score(
        0.45 * out["trend_push_down_score"] +
        0.20 * positive_clip(out["close_quality_bear"] - 0.55) +
        0.20 * out["reaccept_low_score"] +
        0.15 * positive_clip(-out["momentum_3"])
    )

    out["signal_family"] = infer_signal_family(out)

    # 路径代理：不是未来真值，而是后续哪条路更可能发生的先验风险提示。
    out["fast_failure_risk"] = bounded_score(
        0.35 * out["noise_score"] +
        0.30 * positive_clip(0.20 - out[["close_quality_bull", "close_quality_bear"]].max(axis=1)) +
        0.20 * positive_clip(0.20 - out[["trend_push_up_score", "trend_push_down_score"]].max(axis=1)) +
        0.15 * positive_clip(0.90 - out["range_expansion_ratio"])
    )
    out["expansion_4_8_proxy"] = bounded_score(
        0.35 * out[["continuation_score", "release_score", "reconfirm_score"]].max(axis=1) +
        0.30 * positive_clip(out["range_expansion_ratio"] - 1.05) +
        0.20 * out[["close_quality_bull", "close_quality_bear"]].max(axis=1) +
        0.15 * out[["trend_push_up_score", "trend_push_down_score"]].max(axis=1)
    )
    out["overhold_risk_proxy"] = bounded_score(
        0.40 * positive_clip(1.0 - out["expansion_4_8_proxy"]) +
        0.30 * positive_clip(out["signal_score"] - 0.45) +
        0.30 * positive_clip(out["range_expansion_ratio"] - 1.20) * positive_clip(0.30 - out[["close_quality_bull", "close_quality_bear"]].max(axis=1))
    )

    return out.replace([np.inf, -np.inf], np.nan)


def rolling_slope(series: pd.Series, window: int) -> pd.Series:
    """
    交易含义
    --------
    用最简单的滚动线性回归斜率，近似表达“窗口内整体有没有明显方向”。

    为什么不是直接看涨跌幅
    ----------------------
    因为交易员看趋势时，不只看终点和起点，
    还会在意中间是不是大体顺着一条斜线推进。

    实现备注
    --------
    rolling.apply 在窗口前段会传入“短于完整窗口”的数组，
    所以 x 轴长度必须跟当前 values 实时匹配，不能偷懒固定写死。
    """

    def _slope(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        x = np.arange(len(values), dtype=float)
        return np.polyfit(x, values, 1)[0]

    return series.rolling(window, min_periods=max(10, window // 2)).apply(_slope, raw=True)


def pullback_depth_ratio(close: pd.Series, window: int) -> pd.Series:
    """
    交易含义
    --------
    衡量最近回撤相对前一段推进是不是“太深”。

    直觉
    ----
    对 continuation 类型信号来说，回撤允许存在，
    但如果回撤幅度已经吃掉前面推进的大部分，
    那它更像结构被打坏，而不是健康中继。
    """
    prev_move = close.diff(window).abs().replace(0, np.nan)
    recent_drawdown = (close.rolling(window, min_periods=2).max() - close).abs()
    return recent_drawdown / prev_move


def disagreement_proxy(total_range: pd.Series, body_abs: pd.Series) -> pd.Series:
    """
    交易含义
    --------
    这是“高波动但低效率”的代理。

    直觉
    ----
    如果一根或最近几根 bar 的 range 很大，
    但实体并不大，常常意味着市场有明显分歧和来回拉扯。
    这种状态不一定马上反转，但至少说明原趋势没那么干净了。
    """
    return bounded_score((total_range - body_abs) / total_range.replace(0, np.nan))


def bounded_score(series: pd.Series | np.ndarray) -> pd.Series:
    """把任意连续值裁到 0~1 之间，方便做家族分数。"""
    return pd.Series(np.clip(series, 0.0, 1.0), index=getattr(series, "index", None))


def positive_clip(series: pd.Series | np.ndarray) -> pd.Series:
    """只保留正向信息，负值一律视作 0。"""
    return bounded_score(series)


def negative_clip(series: pd.Series | np.ndarray) -> pd.Series:
    """把“越负越危险”的信息翻成正数分数。"""
    return bounded_score(-np.asarray(series))


def infer_signal_family(df: pd.DataFrame) -> pd.Series:
    """
    给每一行分配一个“当前更像哪类信号家族”的标签。

    注意
    ----
    这只是第一版粗分类，不代表最终策略标签。
    它的价值是帮助后续做“同类信号 -> 不同结果路径”的统计。
    """
    scores = pd.DataFrame(
        {
            "continuation": df["continuation_score"],
            "release": df["release_score"],
            "reconfirm": df["reconfirm_score"],
            "reversal": df["reversal_score"],
            "noise": df["noise_score"],
        },
        index=df.index,
    )
    return scores.idxmax(axis=1)
