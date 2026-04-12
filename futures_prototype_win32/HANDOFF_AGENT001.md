# HANDOFF_AGENT001.md

> 给 `agent001` 的项目交接文档。
> 目标是让另一个 agent 不依赖长聊天上下文，也能直接继续开发。

---

## 1. 项目一句话定义

这是一个面向**国内期货 intraday** 的 **15分钟单周期主观趋势代理模型** 项目。

目标不是发明全新策略，而是把用户已有的主观交易 edge 结构化、程序化，并最终扩展到更多可覆盖品种。

当前优先级是：
- 先把交易语言翻译成系统语言
- 先验证数据能否支撑这些定义
- 先做可审阅的规则引擎和扫描器
- 暂时不追求“回测漂亮”

---

## 2. 用户交易哲学摘要（非常重要）

这部分是整个项目最关键的“设计约束”。

### 2.1 用户主要做什么
用户最常用的是两类 setup：

1. **突破跟踪**
2. **回撤再上**（本质上是前者的延续，而不是独立均值回归）

但用户并不是做“价格突破某个数值就直接进”的传统 breakout。

用户风格更接近：
- 先突破
- 再出现明显扩张
- 再看周期结束时是否守得住
- 还要看巨量确认
- 然后才进

也就是：
**确认后再进，宁可牺牲成本，换确定性。**

---

### 2.2 用户不接受的东西

#### 不接受 1：多周期确认
用户明确表示：
- 一个周期就是一根 K 线
- 15m、1h、日线属于不同概率空间
- 不存在“大周期天然更准确”的事实
- 越短周期，信号常常越直接、越可靠

因此本项目必须遵守：
- **单周期闭环**
- 不用 1h / 日线确认 15m 信号
- 如果以后做 1h 或日线，应当是独立模型，而不是多周期套娃

#### 不接受 2：把止损等于反手
用户明确认为：
- 如果所谓“止损信号”足够强到需要止损，那理论上应该直接反手
- 但实盘中反手常常导致两头挨打
- 所以退出和反手必须严格分离

系统设计原则：
- `exit != reverse`
- 退出后默认进入 `observe_after_exit`
- 反手必须满足独立 setup
- 默认不允许由止损直接触发反手

---

### 2.3 用户如何定义“错”

用户的认错机制主要有两类：

#### A. 硬止损
- 通常约 2%
- 若进场后一个 bar 内被扫到，直接认输
- 并重新评估市场状态

重点：
- 这是风险边界，不是信号翻转
- 触发后应回到观察态

#### B. 动量 / 波动失效
用户非常看重这一点：
- 波动率有聚集性
- 强波动之后理应出现更强波动，至少应该继续推进
- 如果突然波动急降，多半意味着有分歧
- 如果此时成交量还很大，则更说明是高分歧拉锯，而不是共识推进

用户对“好趋势”的理解是：
- 价格位移大
- 推进高效
- 不需要持续高量对敲
- 更像从一个量峰迁移到低阻力区域

用户对“坏趋势/假趋势”的理解是：
- 量很大
- 但价格不怎么走
- 推进效率下降
- 市场进入拉锯和分歧

因此项目里要重点保留两个代理概念：
- `movement_efficiency`
- `volume_displacement_ratio`

---

### 2.4 用户的止损观
用户明确说过：

> 止损更多是进攻准备。
> 宁可止损错了，也不能止损慢了。

这意味着：
- 止损的核心作用不是“证明看错”
- 而是回收风险预算、释放行动能力、保留对下一次机会的响应权

系统实现上必须体现：
- 退出优先于自我证明
- 退出后优先恢复空仓观察能力
- 错误仓位不能长期占用风险预算和决策带宽

这也是项目为什么强调：
- `observe_after_exit`
- `cooldown`
- 不自动反手

---

## 3. 当前模型边界

当前模型只做：
- 15m intraday
- 单品种扫描 / 单品种状态机 / 单品种最小回测骨架
- confirmed breakout / pullback reconfirm
- 基于 OHLCV 的代理特征

当前模型明确不做：
- 多周期确认
- 组合层风险预算
- 跨品种 lead-lag
- L2 / orderbook 直接建模
- 反手交易
- 黑盒 ML 主模型

理由：
- 先验证定义和数据
- 先做人可读、可审阅、可调的研究原型

---

## 4. 当前工作区文件地图

### 核心文档
- `futures_prototype/TEMPLATE_15M_TREND_AGENT_V0.md`
  - 当前项目的策略模板文档
- `futures_prototype/HANDOFF_AGENT001.md`
  - 本交接文档
- `futures_prototype/template_params.example.yaml`
  - 参数占位样例

### 当前主线代码
- `futures_prototype/config.py`
  - 策略参数 dataclass
  - 支持读取 JSON / 简单 YAML
- `futures_prototype/features_v2.py`
  - 15m 单周期特征工程
- `futures_prototype/engine.py`
  - 状态机 + setup 检测 + 持仓后监控 + failure 分类
- `futures_prototype/scanner.py`
  - 扫描器和候选汇总
- `futures_prototype/backtest_v2.py`
  - 最小事件驱动回测骨架
- `futures_prototype/run_template_project.py`
  - 项目入口脚本

### 旧原型（保留参考）
- `features.py`
- `regime.py`
- `alpha.py`
- `portfolio.py`
- `backtest.py`
- `run_demo.py`

旧原型是早期“趋势 + 均值回归切换”的思路，
**不代表当前用户风格主线**，开发时应以 `*_v2` 和模板文档为准。

---

## 5. 当前代码实现说明

## 5.1 `config.py`
提供 `StrategyConfig`。

当前参数都是模板值，不是定稿。
重点参数包括：
- `breakout_lookback_bars`
- `expand_window_bars`
- `follow_through_bars`
- `hard_stop_pct`
- `min_expansion_pct`
- `min_close_hold_ratio`
- `min_volume_ratio`
- `min_volume_zscore`
- `max_pullback_depth_pct`
- `min_movement_efficiency`
- `max_volume_displacement_ratio_z`
- `cooldown_bars_after_failure`

注意：
- 这些参数目前是“可跑的占位值”
- 后续应基于真实数据和用户反馈调整

---

## 5.2 `features_v2.py`
当前基于 OHLCV 构建以下几类特征：

### 结构类
- `rolling_high`
- `rolling_low`
- `close_location_in_bar`

### 波动类
- `true_range`
- `atr_14`
- `rv_10`
- `rv_20`

### 量能类
- `volume_ratio_20`
- `volume_zscore_20`

### 趋势 / 动量类
- `ema_8`
- `ema_20`
- `trend_slope`
- `momentum_3`
- `momentum_5`

### 代理微观结构类
- `movement_efficiency_3`
- `movement_efficiency_5`
- `volume_displacement_ratio_3`
- `volume_displacement_ratio_5`
- `vdr_z_20`

这里的设计核心是：
在拿不到 L2 / orderbook 的前提下，尽量用 OHLCV 做“推进效率 / 分歧”的代理。

---

## 5.3 `engine.py`
这是当前项目的核心。

### 当前做了什么
- 初始化输出字段
- 根据 rolling high/low 检测 breakout 候选
- 根据 prior trend + pullback + reconfirm 检测回撤再确认候选
- 在 flat 状态下决定是否进场
- 在 live position 状态下做 failure 监控
- 支持 cooldown
- 退出后回到观察而不是直接反手

### 当前 failure 类型
- `hard_stop_failure`
- `momentum_decay_failure`
- `disagreement_failure`
- `time_expiry_failure`

### 当前 action suggestion
- `observe`
- `candidate_long`
- `candidate_short`
- `enter_long`
- `enter_short`
- `exit_to_flat`

### 需要重点审阅的地方
接手开发时，优先审这几个函数：
- `evaluate_breakout_candidate`
- `evaluate_pullback_reconfirm_candidate`
- `maybe_enter_position`
- `monitor_live_position`

这些函数目前只是**第一版骨架**，很可能需要按用户交易语言继续细化。

---

## 5.4 `scanner.py`
负责：
- 加载输入数据
- 跑 feature 工程
- 跑 signal engine
- 汇总候选

它现在适合：
- 单品种审阅
- 看最新候选是否“像人话”
- 给未来多品种扫描器做基础

---

## 5.5 `backtest_v2.py`
当前只是一个最小事件驱动回测骨架。

它的作用是：
- 粗略验证规则有没有产生合理行为
- 输出基础绩效和 entry/exit 数量

它当前**不是生产级回测**，存在大量简化：
- 没有主力连续切换处理
- 没有 session 细分
- 没有细致手续费 / 滑点建模
- 没有品种差异化成本

不要把当前回测结果当正式策略结论。

---

## 6. 当前已知薄弱点 / 不确定点

以下是接手时最值得优先打磨的部分。

### 6.1 breakout 定义还偏简化
用户的真实 breakout 不是：
- `close > rolling_high` 就完事

而是：
- 破位
- 扩张
- 守住
- 巨量确认
- 再进

当前代码已经开始往这个方向靠，但仍然偏模板化，后续要进一步：
- 更明确区分“破位”和“确认完成”
- 更严格定义 expansion / hold
- 更细化巨量确认逻辑

### 6.2 pullback reconfirm 还比较粗
当前是基于 prior window 的近似实现。
后续应进一步显式化：
- 前趋势锚点
- 回撤深度
- 回撤持续 bar 数
- 再起的放量与收盘强度

### 6.3 disagreement 只是代理定义
目前 `disagreement_failure` 主要依赖：
- `movement_efficiency`
- `vdr_z_20`

这是一个合理起点，但不是最终版。
后续需要用真实数据验证：
- 这些代理量是否真的能映射用户说的“高量低位移、高分歧、拉锯”

### 6.4 时间逻辑还可以更精炼
用户的时间观很明确：
- 一个周期就是一根 bar
- 如果几个 bar 内没继续，就应重新观察

当前 `follow_through_bars` / `time_expiry_failure` 已经有框架，
但后续可能要区分：
- breakout 后的时间窗
- reconfirm 后的时间窗
- 不同 failure 的冷却方式

---

## 7. 当前推荐开发顺序

如果 `agent001` 继续开发，建议按这个顺序推进：

### 第 1 步：拿真实 15m 数据跑通
目标：
- 确认输入数据格式
- 看输出字段是否合理
- 看有没有明显 bug / 空值 / 不连贯状态切换

优先检查：
- `template_signals.csv`
- `template_candidates.csv`
- `template_metrics.json`

### 第 2 步：人工抽样审 setup
选一些典型样本，人工核对：
- breakout 候选是不是“像用户会做的突破”
- reconfirm 候选是不是“像趋势中的回撤再上”
- disagreement exit 是否看起来像“量大但不走”的坏结构

### 第 3 步：重构 setup 状态细节
建议下一版重点增强：
- breakout 的阶段字段
- expansion 与 hold 的显式状态切换
- 更明确的 `break_attempt -> expansion_confirmed -> hold_confirmed -> trend_live`

### 第 4 步：加入图形审阅工具
建议新增：
- 候选 setup 标注图
- entry / exit / failure reason 可视化

因为用户是主观交易员，这一步会极大提高审阅效率。

### 第 5 步：再谈统计验证
在 setup 定义没有“看起来像人”之前，
不要急着做复杂收益优化。

---

## 8. 推荐的下一批代码任务

下面这些任务最适合接着做。

### Task A. 新增可视化模块
建议文件：
- `plot_review.py`

目标：
- 画价格、volume、候选信号、entry/exit、failure reason
- 让用户能一眼看出定义是否合理

### Task B. 强化 breakout 状态机
建议在 `engine.py` 中进一步显式化：
- `break_attempt`
- `expansion_confirmed`
- `hold_confirmed`
- `trend_live`

当前虽然有状态概念，但实现还偏结果导向，不够阶段化。

### Task C. 把 pullback reconfirm 改成更真实的事件链
当前更像“窗口规则”。
后续应更像：
- 先有 live trend
- 再有 pullback
- 再有 reconfirm attempt
- 再确认 entry

### Task D. 提升 config 与参数实验能力
建议：
- 支持从 YAML/JSON 更完整加载
- 增加配置导出
- 允许不同品种有不同参数模板

### Task E. 多品种扫描入口
建议新增一个批处理脚本：
- 输入一个目录下的多个 15m csv
- 输出最新候选 ranking

这会更贴近用户“扩大覆盖市场”的目标。

---

## 9. 如何运行当前项目

在工作区下：

```bash
cd /Users/fhu/.openclaw/workspace-trader/futures_prototype
python3 run_template_project.py --input /path/to/your/futures.csv
```

可选参数：

```bash
python3 run_template_project.py \
  --input /path/to/your/futures.csv \
  --instrument AU \
  --config /path/to/config.json \
  --signals-out output/template_signals.csv \
  --candidates-out output/template_candidates.csv \
  --metrics-out output/template_metrics.json
```

当前 `config.py` 也支持简单 YAML。

---

## 10. 当前 git 提交

当前与此项目相关的关键 commit：

- `a24b5e7`
  - Add 15m trend agent template and prototype scaffold
- `99a333c`
  - Implement 15m single-timeframe trend agent scaffold

建议接手前先看这两个提交对应的文件。

---

## 11. 给 agent001 的一句话建议

不要急着优化收益，先判断这套规则输出的候选、退出、失败分类，
**是不是像一个成熟主观趋势交易员会真正说出来的话。**

如果“不像”，先改定义；
如果“像”，再谈统计验证。

---

## 12. 未来可能扩展，但现在先别急

后续可能的扩展方向：
- L2 / orderbook 增强版 disagreement 检测
- 主力连续与 session-aware 版本
- 多品种 ranking 扫描器
- setup 级别统计验证
- 半自动审阅面板

但在用户真实数据审阅前，不建议过早展开。

---

## 13. 2026-03-27 新增：主观交易 track record 工具链（优先级很高）

项目方向已经发生明显调整：

**用户当前最在意的不是“开发策略”，而是把自己已经验证过的主观手法稳定采样成 track record。**

因此，agent001 接手时请把注意力优先放在：
- 显示层是否可靠
- 回放录入是否顺手
- 记录文件是否稳定
- 如何从历史动作中反推“入场前状态的一致性”

而不是先去改策略逻辑或回测因子。

### 13.1 当前已做出的工具

#### A. 终端 K 线查看器（保留作轻量工具）
- `futures_prototype/terminal_kline.py`
- `futures_prototype/run_terminal_kline.py`

说明：
- 能看滚动 30 根 K 线
- 但用户明确反馈：终端字符栅格会扭曲比例
- 因此 **终端版只适合轻量调试和录入，不适合精确看图**

#### B. 终端回放采样器
- `futures_prototype/simulator.py`
- `futures_prototype/run_simulator.py`
- `futures_prototype/start_sim.sh`

当前交互：
- `↑` long
- `↓` short
- `←` flat
- `→` skip
- `q` / `Ctrl-C` 退出并保留进度

显示：
- `open` = 当前持仓未实现 ticks
- `total` = 已实现累计 ticks
- `net` = open + total
- 显示 `LONG/SHORT/FLAT`、`POSITION_SIZE`、`TICK_SIZE`

#### C. 网页版回放器（当前最重要）
- `futures_prototype/web_replay_server.py`
- `futures_prototype/start_web_replay.sh`

这是当前主力工具。用户明确要求精确 K 线比例，因此优先用浏览器版。

当前功能：
- 读取 `~/livedata/${SYMBOL}.csv`
- 真正按 `TIMEFRAME` 重采样（1m/5m/15m/1h 等）
- 浏览器 canvas 精确绘制 30 根 K 线
- 键盘 `↑ ↓ ← →` 记录 `long / short / flat / skip`
- 局域网访问（默认 `0.0.0.0:8765`）
- 继续写入现有 `output/sim/*` 记录文件
- 右侧显示：
  - Position
  - Open PnL
  - Total PnL
  - Net PnL
  - Current OHLC
  - Recent actions
- 特定时间戳高亮：`14:45`、`02:15`
- 最新 bar 蓝框高亮

用户当前明确偏好：
- **精确看图用网页版**
- **终端版不要再作为主要显示工具**

---

## 14. 当前 track record 分析口径（非常重要）

用户明确纠正过一个分析误区：

> 交易看的是一致性，不是只挑最强盈利样本讲故事。
> 很多交易本来就是试探单。
> 入场前的状态足够推动交易，后续 pnl 本来就不确定。

因此，agent001 后续分析时必须遵守：

### 不要这样做
- 不要只挑最赚钱几笔 / 最亏几笔来定义手法
- 不要把“赚钱图形”误当成“信号本身”
- 不要先按 hindsight 解释图，再倒推策略

### 应该这样做
- 先看**入场前 30 根窗口**
- 先问：为什么这个状态足以让用户出手试探？
- 再看后续结果如何分布：
  - 直接展开
  - 试探失败
  - 震荡后失效
  - 拖持有
- 核心目标是识别：
  - **同类信号 → 不同结果路径**

用户最认可的表述是：

> **信号是一致的，但后续 pnl 是不确定的。**

---

## 15. 当前 AG99 15m 活 state 的最新统计（基于 `AG99_15m_state.json`）

这是 2026-03-27 当前会话里最新一次完整统计的结果；agent001 接手时应优先重新读取 `output/sim/AG99_15m_state.json`，不要只看旧 session 文件。

### 最新快照（当时）
- `session_id`: `e593f2247554`
- `current_index`: `4528`
- `actions`: `4528`
- `trades`: `312`
- 当前空仓

### 总体结果
- total ticks: `+293`
- win rate: `45.83%`
- median ticks: `-1`
- avg ticks: `+0.939`

### by side
- long: 199 笔，win rate `48.2%`，sum ticks `+277`
- short: 113 笔，win rate `41.6%`，sum ticks `+16`

### 最关键的结构性发现
按持有 bars 分桶：
- `1` bar: `-135 ticks`
- `2-3` bars: `-46 ticks`
- `4-8` bars: `+657 ticks`
- `9-20` bars: `+21 ticks`
- `21+` bars: `-204 ticks`

这说明：

> **当前这套手法最有效的兑现窗口非常集中在 4–8 bars。**

也就是说，它更像：
- 不是超短 scalp
- 也不是长时间趋势死拿
- 而是**中短程展开型试探/跟随**

对于接手者，这个统计很重要，因为它提示：
- 太短的交易总体在亏
- 太长的拖持有总体也在亏
- 真正赚钱主要集中在 4–8 bars 的窗口内

这条不是最终真理，但它是当前全样本里最强的统计信号。

---

## 16. agent001 接手时的建议流程

### Step 1. 先确认工具可用
优先检查：
- `./start_web_replay.sh` 能否启动
- 局域网访问是否正常
- 网页中的 PnL 三项（open / total / net）是否正常显示
- `14:45` / `02:15` 高亮是否存在

### Step 2. 分析时优先读活 state
优先读：
- `futures_prototype/output/sim/AG99_15m_state.json`

不要先读：
- 某个旧的 `AG99_<session_id>_trades.csv`

原因：
- 活 state 才是当前网页/回放正在累积的真实最新数据

### Step 3. 先看全样本，再看局部
推荐顺序：
1. 全样本统计（尤其持有 bars 分桶）
2. 再看入场前 30 根窗口的一致性
3. 最后才看个别极端盈利/亏损样本

### Step 4. 如果要继续改 UI
优先级建议：
1. 保持比例正确
2. 保持局域网可访问
3. 保持录入稳定
4. 其次才是额外花哨指标

因为用户现在最痛的点始终是：
- 图形必须可信
- 交互必须顺手
- 样本必须能沉淀
