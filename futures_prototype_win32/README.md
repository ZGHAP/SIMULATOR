# futures_prototype

一个面向期货市场的“主观交易代理”研究骨架。

当前主线已经切到：
- **15m 单周期**
- **确认型突破 / 回撤再确认**
- **退出不等于反手**
- **止损优先保证下一次进攻自由**

## 当前可运行部分

### 文档模板
- `TEMPLATE_15M_TREND_AGENT_V0.md`：策略蓝图模板
- `HANDOFF_AGENT001.md`：给协作 agent 的详细交接文档
- `SIMULATOR_SPEC.md`：仿真交易记录器规格
- `template_params.example.yaml`：参数占位样例

### 可运行代码
- `config.py`：策略参数
- `features_v2.py`：15m 单周期特征工程
- `engine.py`：状态机 + setup 检测 + 持仓后监控
- `scanner.py`：扫描器与候选汇总
- `backtest_v2.py`：最小事件驱动回测骨架
- `run_template_project.py`：规则项目入口
- `simulator.py`：行情回放 + 人工交易记录器
- `run_simulator.py`：模拟器入口
- `terminal_kline.py`：终端 K 线渲染器（滚动 30 根窗口）
- `run_terminal_kline.py`：终端 K 线查看器入口
- `factors_subjective.py`：第一版主观交易识别因子（带交易含义注释）
- `run_subjective_factors.py`：主观因子导出入口

### 旧原型（保留作参考）
- `features.py`
- `regime.py`
- `alpha.py`
- `portfolio.py`
- `backtest.py`
- `run_demo.py`

## 当前这版实现了什么

- 用 OHLCV 跑通单品种扫描
- 识别两类候选 setup：
  - `confirmed_breakout`
  - `pullback_reconfirm`
- 生成状态 / 建议动作 / 持仓 / 失败原因等字段
- 实现几类退出：
  - `hard_stop_failure`
  - `momentum_decay_failure`
  - `disagreement_failure`
  - `time_expiry_failure`
- 输出最小候选清单与回测指标

## 输入数据格式

CSV 至少包含：
- `date`
- `open`
- `high`
- `low`
- `close`
- `volume`

## 快速开始

```bash
cd /Users/fhu/.openclaw/workspace-trader/futures_prototype
python3 run_template_project.py --input /path/to/your/futures.csv
```

可选指定输出：

```bash
python3 run_template_project.py \
  --input /path/to/your/futures.csv \
  --signals-out output/template_signals.csv \
  --candidates-out output/template_candidates.csv \
  --metrics-out output/template_metrics.json
```

如果后面要自定义参数，当前支持读取 JSON：

```bash
python3 run_template_project.py \
  --input /path/to/your/futures.csv \
  --config /path/to/config.json
```

## 主观交易识别因子（第一版）

如果你想先把“像不像你的交易”落成一组可读因子，而不是直接做策略，可以先跑：

```bash
cd /Users/fhu/.openclaw/workspace-trader/futures_prototype
python3 run_subjective_factors.py --input ~/livedata/AG99.csv --timeframe 15m
```

默认会输出：

- `output/subjective_factors.csv`

当前因子分成几层：
- 地形因子：趋势 / 压缩 / 噪音 / 转换
- 触发因子：恢复 / 释放 / 再确认 / 失效切换
- 家族分数：`continuation / release / reconfirm / reversal / noise`
- 路径代理：`fast_failure_risk / expansion_4_8_proxy / overhold_risk_proxy`

说明：
- 这不是最终策略，也不是收益预测器
- 它的目标是识别“当前状态像不像用户会出手试探的交易”
- 注释尽量使用交易语言，方便后续继续校正

## 终端 K 线查看器

可以直接把 OHLCV csv 渲染成终端里的滚动 K 线窗口：

```bash
cd /Users/fhu/.openclaw/workspace-trader/futures_prototype
python3 run_terminal_kline.py --input /path/to/your/futures.csv --timeframe 15m
```

常用参数：

```bash
python3 run_terminal_kline.py \
  --input /path/to/your/futures.csv \
  --timeframe 5m \
  --window 30 \
  --height 20 \
  --candle-width 2 \
  --watch --interval 2
```

说明：
- 默认滚动显示最近 30 根 K 线
- 纵轴按窗口内 high/low 自适应，并加 5% padding
- 每根 K 线默认占 2 列字符，避免压成细线
- 自动兼容常见时间列名：`date` / `datetime` / `time` / `timestamp` / `trade_time` / `bar_time` / `candle_begin_time`
- `--timeframe` 现在会真的按周期聚合，例如把 1m 原始数据重采样成 5m / 15m / 1h
- `--ascii` 可切到纯 ASCII 字符
- `--no-color` 可关闭 ANSI 颜色

## 网页版回放器

如果你更在意 K 线比例和像素级显示，可以直接启动本地网页版：

```bash
cd /Users/fhu/.openclaw/workspace-trader/futures_prototype
./start_web_replay.sh
```

默认会：
- 从 `~/livedata/${SYMBOL}.csv` 读取行情
- 真正按 `TIMEFRAME` 聚合
- 在浏览器中绘制 30 根精确 K 线
- 用键盘 `↑ ↓ ← →` 记录 `long / short / flat / skip`
- 继续写入现有的 `output/sim/*` track record 文件
- 默认监听 `0.0.0.0:8765`，方便同一局域网内其他设备访问

可改字段：
- `SYMBOL`
- `TIMEFRAME`
- `LOOKBACK`
- `OUT_DIR`
- `TICK_SIZE`
- `POSITION_SIZE`
- `HOST`
- `PORT`
- `EXTRA_ARGS`

局域网内访问时：
1. 运行 `./start_web_replay.sh`
2. 在本机查看 IP：`ipconfig getifaddr en0`
3. 其他设备打开：`http://<你的IP>:8765`

如果 `en0` 没结果，再试：`ipconfig getifaddr en1`

## 仿真交易采样器

可以直接用历史行情回放，人工做仿真交易并自动留痕：

```bash
cd /Users/fhu/.openclaw/workspace-trader/futures_prototype
./start_sim.sh
```

默认脚本在 `start_sim.sh` 里，直接改顶部这些字段即可：
- `SYMBOL`
- `TIMEFRAME`
- `INPUT_DIR`
- `LOOKBACK`
- `CHART_HEIGHT`
- `OUT_DIR`
- `TICK_SIZE`
- `POSITION_SIZE`
- `EXTRA_ARGS`

如果你还是想手动跑底层命令：

```bash
python3 run_simulator.py --input ~/livedata/RB99.csv --timeframe 1m
```

交互方式（单键模式）：

- `↑`：进买 / `long`
- `↓`：进卖 / `short`
- `←`：平仓 / `flat`
- `→`：跳过 / `skip`
- `q` / `Ctrl-C`：退出，保留当前进度

现在不再输入原因码，只记录你的动作和对应的 30 根裸 K 快照。
后面如果我从图形和你的成交里识别到“按你的规律本来该做但没做”的位置，再单独拿出来问你。

说明：
- 默认保存最近 `30` 根裸 K 快照到 `snapshot_30bars`
- `skip` 也会被记录，方便保留“不做”的样本
- 界面会显示当前头寸方向和数量，例如 `LONG x2`，以及按 `tick` 计算的浮动盈亏 `pnl=xx.xt`
- `tick size` 可通过 `start_sim.sh` 里的 `TICK_SIZE` 或命令行 `--tick-size` 设置
- 头寸显示数量可通过 `POSITION_SIZE` 或命令行 `--position-size` 设置
- 会自动写入 `output/sim/*_state.json`，下次重跑默认从上次 bar 继续，不用重新来过
- 如需强制从头开始，可加 `--no-resume`

输出到 `output/sim/` 下，至少包括：
- `*_actions.csv`
- `*_trades.csv`
- `*_snapshots.jsonl`
- `*_summary.json`
- `*_state.json`

## 这版故意没做的事

- 多周期确认
- 反手逻辑
- 黑盒预测模型
- 组合层风险预算
- 跨品种联动
- L2 / orderbook 直接建模
- 图形化仿真界面

## 目的

这版不是为了先跑出漂亮收益，而是为了先验证三件事：
- 数据能不能支撑定义
- 定义像不像真实交易语言
- 哪些字段必须换代理变量
