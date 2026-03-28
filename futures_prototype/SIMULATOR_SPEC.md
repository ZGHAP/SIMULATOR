# SIMULATOR_SPEC.md

> 15m 行情回放 + 人工交易记录器（最小可用版）规格说明。

---

## 1. 目标

这个模拟器的目标不是先做高保真交易终端，而是：

- 用真实历史行情回放，采集用户的主观交易决策
- 自动生成结构化交易记录
- 为后续“从行为反推规则”提供足够样本

核心思想：
- 真实成交记录可能样本太少
- 但如果用户能在行情回放里做仿真交易，就能快速生成高质量决策样本

---

## 2. 当前版本定位

当前版本只做：
- 命令行交互
- 单品种
- 单周期（默认 15m）
- bar-by-bar 回放
- 手动输入交易动作
- 自动记录日志

当前版本先不做：
- 图形界面
- K线可视化
- 鼠标点选下单
- 多品种同时回放
- 实时撮合 / 盘口级模拟

---

## 3. 支持的输入

CSV 至少包含：
- `date`
- `open`
- `high`
- `low`
- `close`
- `volume`

可选字段：
- `open_interest`

---

## 4. 交互动作

## 4.1 交易动作
- `long`：开多 / 转为多头持仓
- `short`：开空 / 转为空头持仓
- `flat`：平仓到空仓
- `hold`：保持当前持仓

## 4.2 标签动作
用户可为当前决策打标签：

### setup 标签
- `confirmed_breakout`
- `pullback_reconfirm`
- `trend_resume`
- `none`

### exit reason 标签
- `hard_stop`
- `momentum_decay`
- `disagreement`
- `time_expiry`
- `free_capital`
- `other`

### skip / no-trade 标签
- `no_confirmation`
- `volume_not_right`
- `hold_not_good_enough`
- `disagreement`
- `too_late`
- `not_my_setup`

用户也可以输入自由备注。

---

## 5. 输出文件

模拟器运行后，至少输出三个文件。

## 5.1 `actions.csv`
逐步记录每一次用户动作。

字段示例：
- `session_id`
- `instrument`
- `bar_index`
- `timestamp`
- `action`
- `position_before`
- `position_after`
- `price_reference`
- `setup_label`
- `reason_label`
- `note`

## 5.2 `trades.csv`
按开平仓配对后的交易记录。

字段示例：
- `session_id`
- `instrument`
- `entry_time`
- `exit_time`
- `side`
- `entry_price`
- `exit_price`
- `bars_held`
- `gross_return`
- `setup_label`
- `exit_reason_label`
- `entry_note`
- `exit_note`

## 5.3 `snapshots.jsonl`
每个动作时刻的上下文快照。

字段示例：
- `session_id`
- `instrument`
- `bar_index`
- `timestamp`
- `position_before`
- `action`
- `current_bar`
- `lookback_bars`
- `derived_features`
- `setup_label`
- `reason_label`
- `note`

这个文件用于后续做：
- 规则蒸馏
- 行为聚类
- 模仿模型训练

---

## 6. 回放机制

### 6.1 默认模式
- 从某个起始 bar 开始
- 每次展示当前 bar 信息
- 等待用户输入动作
- 输入后推进到下一根 bar

### 6.2 展示内容
每个 bar 至少展示：
- timestamp
- open / high / low / close
- volume
- 当前持仓
- 已实现 pnl
- 未实现 pnl
- 最近 N 根 bar 摘要

### 6.3 lookback 摘要
为了让命令行模式仍然可读，可展示：
- 最近 5 根 bar 的 close / range / volume
- 是否创 rolling high / low
- 简单 volume ratio / movement efficiency

---

## 7. 设计原则

### 7.1 记录比撮合更重要
当前模拟器优先保证：
- 决策动作有记录
- 理由有记录
- 上下文有记录

而不是先追求：
- 最真实的成交细节
- 最精确的滑点模型

### 7.2 标签要少而有用
标签太多会让用户不想打。
当前先采用有限标签集 + 自由备注。

### 7.3 要允许“看了但不做”
这是关键。
如果用户只记录成交，模型会缺失大量过滤信息。
所以必须支持：
- `hold`
- `no_trade` 类理由
- 主动标记“这不是我的 setup”

---

## 8. 后续扩展方向

### Phase 2
- 增加 K 线图和成交量图
- 增加快捷键
- 增加候选信号辅助显示

### Phase 3
- 多品种切换
- 自动插入当前规则引擎候选信号
- 用户对候选做 approve / reject

### Phase 4
- 将模拟器样本直接接入规则反推流水线

---

## 9. 当前实现文件建议

- `simulator.py`：核心模拟器逻辑
- `run_simulator.py`：CLI 入口
- `SIMULATOR_SPEC.md`：本说明文档

---

## 10. 成功标准

最小成功标准不是“盈利”，而是：
- 用户能顺畅地做一段行情回放
- 系统能稳定生成结构化动作日志
- 生成的数据足够支持后续反推规则
