# 15分钟单周期主观趋势代理模型模板 v0.1

> 目标：先做一份**可审阅、可替换、可落地**的模板。
> 这不是最终策略，也不是回测承诺，而是一份把主观交易语言翻译成系统语言的骨架。

---

## 0. 顶层定位

该模型服务于如下目标：

- 覆盖更多期货品种，而不是只盯少数几个
- 复用交易员已有 edge，而不是发明全新风格
- 优先复制“识错 / 纠错 / 保持机动性”的能力
- 只在**单一周期**内定义 setup、验证 setup、管理持仓

当前版本默认周期：
- **15m intraday**

原则：
- 不做多周期确认
- 不把止损等同于反手
- 止损优先保证下一次进攻自由
- 宁可止损早，不可止损慢

---

## 1. 交易哲学模板

### 1.1 交易类型
当前只保留两类多头/空头对称交易：

1. **confirmed_breakout**
   - 突破后不是立刻追
   - 先看扩张、守住、量能确认
   - 确认后再进

2. **pullback_reconfirm**
   - 已有强趋势成立
   - 中途出现回撤/整理
   - 之后再次转强并确认，再跟进

> 注：回撤再上不是独立均值回归逻辑，而是趋势延续逻辑的一部分。

### 1.2 止损观
止损的目的不是证明看错，而是：

- 回收风险预算
- 恢复空仓观察能力
- 为下一次进攻做准备

因此：
- `exit` 只表示退出当前仓位
- `reverse` 必须由独立反向 setup 触发
- 默认不允许“由止损直接反手”

### 1.3 时间观
- 一个周期 = 一根 15m K 线
- 所有时间规则都用 `bar 数` 表达
- 不引入更大周期做过滤

---

## 2. 状态机模板

每个品种在任意时刻都处于以下状态之一：

1. `observe`
   - 观察态，无有效进攻条件

2. `break_attempt`
   - 刚突破关键位，但尚未确认有效

3. `expansion_confirmed`
   - 突破后出现足够强的价格扩张

4. `hold_confirmed`
   - 扩张后收盘/阶段结束位置守得住

5. `trend_live`
   - 趋势已确认，可进入候选池

6. `pullback`
   - 已确认趋势中的回撤/整理阶段

7. `reconfirm_attempt`
   - 回撤后再次发起上攻/下杀，但仍待确认

8. `position_live`
   - 持仓进行中

9. `observe_after_exit`
   - 刚退出后重新观察，不立即反手

10. `cooldown`
   - 短期内该品种/该 setup 暂不参与

---

## 3. setup 定义模板

## 3.1 setup A: confirmed_breakout

### 概念定义
不是“价格碰到关键位就追”，而是：
- 突破
- 扩张
- 守住
- 放量确认
- 然后才进

### 结构字段
- `breakout_level`
- `breakout_bar_index`
- `breakout_side` = long / short
- `expansion_window_bars`
- `hold_window_bars`
- `volume_confirm_window_bars`

### 必要条件（模板）
1. 当前 bar 价格突破关键位
2. 在 `N_expand` 根 bar 内出现足够扩张
3. 在确认 bar 收盘时仍守住突破方向
4. 成交量显著放大

### 待定参数
- `N_expand`: [待定]
- `min_expansion_pct`: [待定]
- `min_close_hold_ratio`: [待定]
- `min_volume_ratio`: [待定]

---

## 3.2 setup B: pullback_reconfirm

### 概念定义
不是抄底回调，而是：
- 先有已确认趋势
- 回撤没有破坏核心结构
- 再次放量转强/转弱
- 再次守住后跟进

### 结构字段
- `prior_trend_score`
- `pullback_depth_pct`
- `pullback_bars`
- `reconfirm_bar_index`
- `reconfirm_volume_ratio`
- `reconfirm_close_strength`

### 必要条件（模板）
1. 前序趋势已确认存在
2. 回撤深度处于可接受区间
3. 回撤过程未破坏失效位
4. 再次发力时有量能确认
5. 再次发力后收盘位置够强

### 待定参数
- `min_prior_trend_score`: [待定]
- `max_pullback_depth_pct`: [待定]
- `max_pullback_bars`: [待定]
- `min_reconfirm_volume_ratio`: [待定]
- `min_reconfirm_close_strength`: [待定]

---

## 4. 入场模板

## 4.1 入场动作
只允许三种：
- `enter_long`
- `enter_short`
- `stay_flat`

默认不允许：
- `reverse_long_to_short`
- `reverse_short_to_long`

## 4.2 入场前检查项

### A. 结构确认
- 是否已完成 breakout / reconfirm 的基本结构

### B. 扩张确认
- 是否出现了足够强的位移

### C. 守住确认
- 当前 bar 收盘是否仍支持该 thesis

### D. 量能确认
- 是否出现“有推动力的量”

### E. 可交易性检查
- 是否满足最小流动性要求
- 是否处于 cooldown
- 是否已有持仓占用

---

## 5. 持仓后监控模板

持仓后不再看“预测”，而是看 thesis 是否继续成立。

## 5.1 监控维度

### 1. 硬止损
- 若入场后一个 bar 内快速触达硬止损阈值
- 直接退出
- 回到 `observe_after_exit`

默认模板参数：
- `hard_stop_pct = 2%`（待人工确认）

### 2. 动量延续
- 强波动之后是否仍有更强波动 / 至少持续波动
- 若数个 bar 内无法延续，则 thesis 降级

### 3. 波动聚集
- 若入场后波动率迅速塌缩
- 说明聚集性未延续
- 需要重新观察

### 4. 价格推进效率
- 价格是否在低摩擦、高效率地迁移
- 若出现高量低位移，说明拉锯和分歧增加

### 5. 时间失效
- 若在 `N_follow` 根 bar 内没有出现应有 follow-through
- 退出到 flat

---

## 6. 错误分类模板

退出不等于看反。退出只说明当前 thesis 不值得继续持有。

### 6.1 `hard_stop_failure`
定义：
- 入场后短时间内直接被打到风险底线

动作：
- 立即平仓
- 状态切换到 `observe_after_exit`
- 强制重新评估市场状态

### 6.2 `momentum_decay_failure`
定义：
- 入场后未出现预期中的进一步扩张
- 波动率/动量明显衰减

动作：
- 平仓或减仓后归零（模板先取归零）
- 重新观察

### 6.3 `disagreement_failure`
定义：
- 成交量依然较大
- 但价格位移效率显著下降
- 市场进入拉锯/分歧态

动作：
- 快速退出
- 不立即反手
- 可进入短期 cooldown

### 6.4 `time_expiry_failure`
定义：
- 在约定 bar 数内没有完成应有演化

动作：
- 平仓
- 回到观察态

---

## 7. 数据字段模板

以下字段按优先级分层。

## 7.1 必需字段（最低可行版本）
这些通常从标准 K 线数据可得：
- `date`
- `open`
- `high`
- `low`
- `close`
- `volume`

## 7.2 强烈建议字段
若数据能取到，质量会明显提升：
- `open_interest`
- 分时成交量分布
- session 信息（日盘/夜盘）
- 主力连续/合约切换信息

## 7.3 可选增强字段
若未来能拿到，可提高“分歧识别”质量：
- L2 order book
- 主动买/主动卖量
- bid/ask queue 变化
- 成交价在盘口量峰之间的迁移信息
- microprice / imbalance

> 注：当前模板必须允许在拿不到 L2 的前提下先运行。

---

## 8. 特征定义模板

## 8.1 结构类
- `rolling_high_N`
- `rolling_low_N`
- `breakout_distance`
- `close_location_in_bar`

## 8.2 扩张类
- `expansion_pct_from_level`
- `expansion_speed_bars`
- `range_expansion_ratio`

## 8.3 守住类
- `close_hold_ratio`
- `post_break_retrace_ratio`

## 8.4 量能类
- `volume_ratio_N`
- `volume_zscore_N`
- `segment_volume_ratio`

## 8.5 波动/效率类
- `realized_vol_N`
- `vol_follow_through_ratio`
- `movement_efficiency`
- `volume_displacement_ratio`

## 8.6 时间类
- `bars_since_entry`
- `bars_since_breakout`
- `bars_since_reconfirm`

---

## 9. 关键特征的候选定义

以下定义先给模板版，后续可替换。

## 9.1 movement_efficiency
```text
movement_efficiency = abs(close_t - entry_price) / sum(true_range_since_entry)
```
解释：
- 值越高，说明净位移相对于路径摩擦越高
- 值越低，说明来回震荡多、推进效率差

## 9.2 volume_displacement_ratio
```text
volume_displacement_ratio = rolling_volume / max(abs(price_change), epsilon)
```
解释：
- 若量大但价不动，则该值上升
- 可作为高分歧/低效率推进的代理指标

## 9.3 close_hold_ratio
```text
close_hold_ratio = (close - breakout_level) / max(expansion_from_breakout, epsilon)
```
解释：
- 用于衡量扩张后的成果保留了多少

## 9.4 vol_follow_through_ratio
```text
vol_follow_through_ratio = future_realized_vol_k / past_realized_vol_k
```
解释：
- 用于判断强波动之后是否仍有波动延续

---

## 10. 扫描器输出模板

每个品种每根 15m bar 输出一行，至少包含：

- `instrument`
- `timestamp`
- `state`
- `setup_type`
- `side`
- `setup_score`
- `breakout_level`
- `entry_candidate_price`
- `hard_stop_price`
- `bars_since_setup`
- `volume_ratio`
- `movement_efficiency`
- `vol_follow_through_ratio`
- `failure_risk_flag`
- `cooldown_flag`
- `action_suggestion`

其中：
- `setup_type` ∈ {`confirmed_breakout`, `pullback_reconfirm`, `none`}
- `action_suggestion` ∈ {`observe`, `candidate_long`, `candidate_short`, `enter_long`, `enter_short`, `exit_to_flat`}

---

## 11. 参数区模板

本节所有参数都先占位，等你回来后按经验和数据可得性校正。

```yaml
timeframe: 15m
hard_stop_pct: 0.02
breakout_lookback_bars: TBD
expand_window_bars: TBD
hold_window_bars: TBD
follow_through_bars: TBD
min_expansion_pct: TBD
min_close_hold_ratio: TBD
min_volume_ratio: TBD
min_volume_zscore: TBD
max_pullback_depth_pct: TBD
max_pullback_bars: TBD
min_movement_efficiency: TBD
max_volume_displacement_ratio: TBD
cooldown_bars_after_failure: TBD
```

---

## 12. 数据可行性检查清单

你明天主要可以先看这一段。

### 最低可行性（能否先跑起来）
- [ ] 是否有稳定 15m OHLCV 数据
- [ ] 是否能拿到较完整的 volume
- [ ] 是否能区分主力连续或至少有稳定连续合约
- [ ] 是否能处理日夜盘切换

### 提升质量（但非必须）
- [ ] open interest 是否可得
- [ ] 更细成交分布是否可得
- [ ] L2 / order book 是否可得
- [ ] 交易时段标签是否可得

### 如果拿不到，也能先用代理变量
- orderbook flow 拿不到 -> 用 `movement_efficiency` + `volume_displacement_ratio` 代理
- 没有主动买卖量 -> 用 bar 级价格位移 / 成交量关系做代理
- 没有详细 session 标签 -> 先统一处理，后续再拆

---

## 13. 第一阶段实现建议

先做最小版，不要一开始就上复杂机器学习。

### Phase 1: 规则模板版
- 用 15m OHLCV 跑通
- 输出状态机与候选 setup
- 不急着优化收益
- 先验证数据是否能支撑这些定义

### Phase 2: 可视化审阅版
- 对每个候选 setup 画图
- 标出 breakout、expansion、hold、entry、exit
- 人工检查是否像真实交易语言

### Phase 3: 扫描器版
- 同时扫描多个期货品种
- 输出排序清单
- 让交易员先拿它做半自动观察

### Phase 4: 统计验证版
- 评估不同 setup 条件下的后续延续概率
- 看哪些定义最有解释力

---

## 14. 当前模板刻意不做的事

以下内容先不并入 v0.1：
- 多周期确认
- 反手逻辑
- 复杂黑盒预测模型
- 组合层风险预算
- 跨品种 lead-lag
- 纯盘口级超短交易

原因：
- 先把主干逻辑做对
- 先验证数据可得性
- 先确定你的定义和代理特征是否合理

---

## 15. 明天审阅时建议重点看什么

建议你优先检查：

1. **状态机是否像你的真实思考流程**
2. **setup 定义是否抓到了“确认后再进”的本质**
3. **退出分类是否符合你的识错逻辑**
4. **哪些特征是你觉得靠谱的代理变量，哪些不是**
5. **哪些数据在现实里拿不到，需要换定义**
6. **哪些参数应该固定，哪些应该品种化**

---

## 16. 备注

这个模板的目标不是“先做漂亮回测”，而是：

- 先把主观语言结构化
- 再检查数据是否承载得住
- 然后再打磨定义
- 最后才谈统计验证和交易实现

如果这个模板方向对，下一版就可以进入：
- 字段字典
- 规则伪代码
- 样例图
- 最小回测框架
