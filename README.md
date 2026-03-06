# 股票交易机器人（回测 + 实盘）

从数据、策略、风控到回测/实盘执行的完整链路，支持 A 股、美股与加密货币（OKX/币安）。

- **快速开始**：安装依赖 → 配置 `.env`（见下方「如何运行项目」）→ 单次运行或**自动轮询**。
- **自动轮询命令（OKX，每 5 分钟检查并下单，默认涨跌 0.5% 触发）**：
  ```bash
  python run_okx_live.py --symbol BTC/USDT --execute --interval 300
  ```

## 结构

```
stock_trading_bot/
├── config.example.yaml   # 配置示例（含股票与加密货币）
├── docs/
│   ├── AI_OVERVIEW.md        # 【给 AI 看】项目与 OKX 脚本总览、状态文件、规则公式、改哪里
│   ├── trading_rules_core.md # OKX 核心交易规则与可调参数
│   ├── crypto_trading.md
│   ├── recommended_services.md # 推荐服务：数据、执行、定时、通知
│   ├── binance_automation.md  # 钱在币安：自动化方案与备选平台
│   └── okx_automation.md     # OKX（欧易）操作教程
├── requirements.txt
├── run_backtest.py       # 股票回测
├── run_live.py           # 股票模拟/实盘
├── run_crypto_backtest.py # 加密货币网格回测
├── run_monitor.py        # 定时监控：涨卖跌买只推荐不下单，--push 支持企业微信/钉钉/飞书（交易手动）
├── run_binance_live.py   # 币安现货：监控+可选实盘下单
├── run_okx_live.py       # OKX（欧易）现货：监控+可选实盘下单
└── src/
    ├── data/             # 数据层：A 股 / 美股 / 加密货币(ccxt)
    ├── strategy/         # 策略层：双均线、突破、网格(高抛低吸)
    ├── risk/
    ├── backtest/
    └── execution/
```

## 安装

```bash
cd stock_trading_bot
pip install -r requirements.txt
```

---

## 如何运行项目

### 1. 配置 API（实盘/OKX 时必做）

在项目根目录复制 `.env.example` 为 `.env`，填入 OKX 或币安 API：

```bash
cp .env.example .env
# 编辑 .env，填写 OKX_API_KEY、OKX_API_SECRET、OKX_PASSPHRASE（OKX 必填三项）
```

### 2. 单次运行

| 用途 | 命令 |
|------|------|
| 只查推荐、不下单（OKX 行情） | `python run_okx_live.py --symbol BTC/USDT` |
| 只查推荐、不下单（币安） | `python run_binance_live.py --symbol BTC/USDT` |
| 一次检查并真实下单（OKX） | `python run_okx_live.py --symbol BTC/USDT --execute` |
| 股票回测 | `python run_backtest.py` |
| 加密货币网格回测 | `python run_crypto_backtest.py` |

`--ratio` 默认 **0.5**（涨跌 0.5% 触发，适合比特币）；可改为 `0.3`、`1`、`2` 等。

### 3. 自动轮询（常驻运行）

让程序**按固定间隔**反复检查行情并执行推荐（有信号就买/卖），用 `--interval 秒数`：

**OKX 自动轮询（推荐，涨卖跌买 + 有信号就下单，默认 0.5% 触发）：**

```bash
python run_okx_live.py --symbol BTC/USDT --execute --interval 300
```

- 每 **300 秒（5 分钟）** 检查一次，有“建议买入/卖出”时自动市价下单。
- 想只推荐、不下单：去掉 `--execute`：
  ```bash
  python run_okx_live.py --symbol BTC/USDT --interval 300
  ```

**币安自动轮询：**

```bash
python run_binance_live.py --symbol BTC/USDT --execute --interval 300
```

**用 cron 定时跑（每 5 分钟跑一次，跑完就退出）：**

```bash
# 编辑 crontab：crontab -e，加入一行（路径改成你的实际路径）
*/5 * * * * cd /Users/hekun/Downloads/stock_trading_bot && python run_okx_live.py --symbol BTC/USDT --execute >> /tmp/okx_bot.log 2>&1
```

### 4. 能覆盖手续费的推荐参数（OKX/币安现货）

交易所市价单约 **0.1% / 笔**，一买一卖约 **0.2%**。要覆盖手续费，单次「跌买→涨卖」的价差需大于 0.2%，建议留一点余量。

| 参数 | 建议范围 | 说明 |
|------|----------|------|
| **触发比例 `--ratio`** | **≥ 0.3，推荐 0.5** | 涨跌 0.5% 触发时，一来回约 1% 价差，扣 0.2% 手续费仍有空间；0.25 也能覆盖但余量小。 |
| **轮询间隔 `--interval`** | **60～120 秒** | 太密（如 30s）容易频繁触发、手续费叠加；60～120s 兼顾响应和限频。 |

**可直接用的命令（覆盖手续费较稳）：**

```bash
python run_okx_live.py --symbol BTC/USDT --ratio 0.5 --execute --interval 60
```

- 每 **60 秒** 检查一次，涨跌 **0.5%** 触发买卖，单次来回价差约 1%，利于覆盖约 0.2% 手续费。

### 5. 该命令下的交易规则说明

以 `python run_okx_live.py --symbol BTC/USDT --ratio 0.5 --execute --interval 60` 为例：

| 项目 | 规则 |
|------|------|
| **标的** | `--symbol BTC/USDT`：只做 BTC 兑 USDT 现货。 |
| **参考价** | 程序内部维护一个「参考价」。首次运行 = 当前价；之后每次**触发买或卖**后，参考价更新为**当时成交价**。 |
| **何时买** | 当前价 **≤ 参考价 × (1 − 0.5%)**，即相对参考价**跌了 ≥0.5%** → 发「建议买入」并（在 `--execute` 时）**市价买入**。 |
| **何时卖** | 当前价 **≥ 参考价 × (1 + 0.5%)**，即相对参考价**涨了 ≥0.5%** → 发「建议卖出」并（在 `--execute` 时）**市价卖出**。 |
| **买多少** | 买入金额 = min(可用 USDT × 95%, 账户权益 × 20%)，且至少 10 USDT 才下单；按当前价折算数量后**市价单**买入。 |
| **卖多少** | 卖出时：**全部**卖出该交易对当前持仓（BTC 全部换成 USDT）。 |
| **轮询** | 每 **60 秒**（`--interval 60`）取一次最新价，和当前参考价比较，满足上述条件就触发一次买或卖。 |

**简单理解**：参考价相当于「上次动手时的价格」；比它跌 0.5% 就买一单，比它涨 0.5% 就清仓卖。每次触发后参考价更新，避免在同一位置反复买卖。

---

## 回测

```bash
python run_backtest.py
```

默认拉取 A 股 000001 近两年日线，用双均线策略+风控回测，输出总收益、年化、最大回撤、夏普、交易次数等。

## 模拟盘

```bash
python run_live.py
```

使用 `SimulatedBroker` 按当前数据生成一次信号并模拟下单，不连真实券商。

## 实盘

实盘需自行对接券商 API（如 VN.py、Alpaca、盈透等），实现 `BrokerBase` 并替换 `run_live.py` 中的 broker。`LiveBrokerStub` 仅为占位，会抛出 `NotImplementedError`。

## 加密货币（比特币等）高抛低吸

- **思路与实现**：见 [docs/crypto_trading.md](docs/crypto_trading.md)，包含 24/7 行情、网格策略、快速操作要点。
- **数据**：`CryptoAdapter`（ccxt）拉取交易所 K 线，支持 1m/5m/15m/1h/1d。
- **策略**：`GridStrategy` 在设定价格区间内分档，跌穿档位买、涨穿档位卖，适合震荡市高抛低吸。
- **回测**：`python run_crypto_backtest.py`（需 `pip install ccxt`，默认 Binance BTC/USDT 5m）。

## 配置

复制 `config.example.yaml` 为 `config.yaml`，修改标的、策略参数、风控与回测参数。当前入口脚本仍以代码内默认为主，可按需从 YAML 读取。

## 最简规则：涨卖跌买 + 定时监控 + 推荐服务

- **规则**：设定一个**比例**（如 1%），相对**参考价**涨了 ≥ 该比例就建议卖，跌了 ≥ 该比例就建议买；每次建议后更新参考价为当前价。
- **策略**：`SimpleThresholdStrategy`（参数 `ratio_pct`），可回测也可只做推荐。
- **定时监控**（只推荐、不自动下单）：
  ```bash
  python run_monitor.py --symbol BTC-USD --ratio 1          # 一次
  python run_monitor.py --symbol 000001.SZ --ratio 1 --interval 300 --push wecom   # A 股 + 每 5 分钟 + 推送到企业微信（交易需手动）
  python run_monitor.py --symbol AAPL --ratio 0.5 --interval 300   # 每 300 秒跑一次
  # --push 可选：wecom / dingtalk / feishu / serverchan / bark / webhook，见 docs/monitor_push_manual_trade.md
  ```
  参考价保存在 `.monitor_ref.json`，下次比较用。
- **推荐服务**：数据（yfinance/交易所）、执行（券商/交易所 API）、定时（cron / `--interval` / 云函数）、通知（邮件/Telegram/钉钉）见 [docs/recommended_services.md](docs/recommended_services.md)。

## 风险与合规

- 不保证盈利；实盘前请充分回测与模拟。
- A 股需遵守账户实名与监管要求；美股需注意 PDT 等规则。
- 仅使用可承受亏损的资金。
