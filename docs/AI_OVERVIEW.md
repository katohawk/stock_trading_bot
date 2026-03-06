# 项目总览（供 AI 快速理解）

本文档面向其他 AI：用最少篇幅说明项目是什么、OKX 实盘脚本怎么跑、状态存在哪、规则公式是什么、改哪里能改行为。

---

## 项目是什么

- **stock_trading_bot**：从数据、策略、风控到回测/实盘的完整链路，支持 A 股、美股、加密货币（OKX/币安）。
- **你最常改的**：OKX 现货「涨卖跌买」实盘脚本 `run_okx_live.py`，逻辑集中在一个文件，无复杂依赖。

---

## OKX 实盘入口与用法

| 项目 | 说明 |
|------|------|
| **入口脚本** | `run_okx_live.py`（项目根目录） |
| **依赖** | `.env` 中 `OKX_API_KEY`、`OKX_API_SECRET`、`OKX_PASSPHRASE`；`src.execution.OKXBroker`、`src.strategy.SimpleThresholdStrategy` |
| **只查推荐、不下单** | `python run_okx_live.py --symbol BTC/USDT` |
| **真实下单** | `python run_okx_live.py --symbol BTC/USDT --execute` |
| **轮询（如每 5 分钟）** | `python run_okx_live.py --symbol BTC/USDT --execute --interval 300` |
| **常用参数** | `--symbol` 交易对；`--ratio` 触发比例%（默认 0.5）；`--buy-amount-usdt` 每次买入 USDT（默认 50）；`--max-slippage` 市价保护上限（默认 0.001）；`--taker-fee-rate` 吃单费率（默认 0.001） |

---

## 状态与持久化（读/写哪里）

| 文件 | 用途 | 结构示例 |
|------|------|----------|
| **.monitor_ref.json** | **唯一状态文件**：参考价、持仓成本、持仓量。每次**成交后**写入。 | `{ "BTC/USDT": { "reference_price": 97000, "avg_cost": 96800, "position_qty": 0.001 } }` |
| **.session_pnl.json** | 当次运行会话：期初权益、累计手续费(估)。用于算净收益。 | `{ "session_start_equity": 1000, "cumulative_fee": 0.5 }` |
| **.env** | API 密钥，不提交。 | `OKX_API_KEY=... OKX_API_SECRET=... OKX_PASSPHRASE=...` |

- **参考价 reference_price**：仅在实际**成交后**更新（防插针/滑点取消时不会更新）。
- **持仓成本 avg_cost**：买入成交后按加权平均更新；卖出清仓后置空（或视为 0）。
- 若从旧版迁移：此前若用 `.okx_state.json`，可把其内 `reference_price`、`avg_holding_price`、`position_qty` 抄到 `.monitor_ref.json`（`avg_holding_price` → `avg_cost`）。

---

## 规则公式（与代码一致）

### 1. 信号（何时买、何时卖）

- **参考价**：来自 `.monitor_ref.json` 的 `reference_price`；首次无则用当前价。
- **买信号**：当前价 ≤ 参考价 × (1 − ratio/100)。
- **卖信号**：当前价 ≥ 参考价 × (1 + ratio/100)，且通过「盈利硬约束」才真正下单。

### 2. 盈利硬约束（卖出必须满足）

- 变量：**avg_cost** = `.monitor_ref.json` 中的 `avg_cost`（持仓成本）。
- 条件：**(当前价 − avg_cost) / avg_cost > 0.003**（即扣费后至少 0.3% 利润）。
- 不满足则打日志并**不卖出**。代码常量：`MIN_PROFIT_RATIO = 0.003`。

### 3. 三秒价格确认（防插针）

- 信号触发且 `--execute` 时：**每隔 1 秒取一次价，共 3 次**。
- 判定：3 个价格的**标准差 / 均价 > 0.1%** → 视为插针，**取消本次下单**（不更新参考价）。
- 代码常量：`PRICE_SAMPLES = 3`，`PRICE_SAMPLE_INTERVAL = 1.0`，`SPIKE_STD_THRESHOLD_PCT = 0.001`。

### 4. 市价保护（滑点）

- **max_slippage**：默认 0.001（0.1%）。下单前取买一、卖一。
- 若 **(卖一 − 买一) / 中间价 > max_slippage** → **暂缓下单**，打日志。
- 代码常量：`MAX_SLIPPAGE = 0.001`；命令行 `--max-slippage` 可覆盖。

### 5. 执行顺序（同脚本内顺序）

1. 取当前价 → 策略推荐（买/卖/观望）。
2. 若有信号且 `--execute`：**三秒价格确认**（3 次取样）→ 若插针则**取消**。
3. **市价保护**（买一卖一价差）→ 过大则**暂缓**。
4. 若是**卖出**：**盈利硬约束**（0.3%）→ 不通过则**不卖**。
5. 下单（市价）；**成交后**写回 `.monitor_ref.json`（reference_price、avg_cost、position_qty）。

---

## 关键代码位置（便于 AI 修改）

| 功能 | 文件 | 位置/函数 |
|------|------|-----------|
| 状态读写 | `run_okx_live.py` | `load_state()` / `save_state()`，`MONITOR_REF_FILE` |
| 盈利硬约束 | `run_okx_live.py` | `sell_profit_ok()`，常量 `MIN_PROFIT_RATIO` |
| 三秒取样与插针判定 | `run_okx_live.py` | `fetch_three_price_samples()`，`SPIKE_STD_THRESHOLD_PCT` |
| 市价保护 | `run_okx_live.py` | `get_bid_ask()`、`check_slippage_ok()`，`MAX_SLIPPAGE` |
| 策略信号 | `run_okx_live.py` | `SimpleThresholdStrategy(ratio_pct=..., reference_price=...)`，`strategy.recommend(price)` |
| OKX 下单 | `src/execution/broker_okx.py` | `OKXBroker.submit_order()` |
| 订单状态 | `src/execution/order.py` | `OrderState.FILLED` 等 |

---

## 日志与排查

- 所有关键步骤打 **中文日志**，前缀 `[日志]`。
- 包含：触发原因、盈利校验结果、三秒取样与插针判定、滑点检查、是否下单/取消、成交结果（含预期收益率、扣费后收益）。

---

## 其他文档

- **规则细节/可调参数**：`docs/trading_rules_core.md`（与本文档规则一致，参数表更全）。
- **OKX 使用与配置**：`docs/okx_automation.md`。
- **项目安装与运行**：根目录 `README.md`。

把本文档 + `trading_rules_core.md` 交给其他 AI，即可在不动回测/股票逻辑的前提下，只改 OKX 实盘行为（阈值、文件、新增检查等）。
