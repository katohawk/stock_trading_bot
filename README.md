# OKX 交易机器人（涨卖跌买 + 实盘）

仅支持 **OKX（欧易）** 现货：配置 API 后按比例涨卖跌买、自动实盘下单。

- **快速开始**：安装依赖 → 配置 `.env`（OKX API）→ 启动 Web 控制台或命令行轮询。
- **Web 控制台（推荐）**：`python server.py --port 5555`，浏览器打开 http://127.0.0.1:5555/，可启动/暂停、改参数、看日志、配置 API。
- **命令行轮询**：每 N 秒检查行情并实盘下单，例如每 5 分钟：
  ```bash
  python run_okx_live.py --symbol BTC/USDT --interval 300
  ```

## 结构

```
stock_trading_bot/
├── config.example.yaml   # 配置示例
├── docs/
│   ├── AI_OVERVIEW.md        # 【给 AI 看】项目与 OKX 脚本总览、状态文件、规则公式
│   ├── trading_rules_core.md # OKX 核心交易规则与可调参数
│   ├── okx_automation.md     # OKX 操作教程
│   └── ...
├── requirements.txt
├── server.py            # Web 控制台（启动/暂停/参数/日志/API 配置）
├── run_okx_live.py      # OKX 现货：涨卖跌买实盘下单
├── run_backtest.py      # 股票回测（可选）
├── run_crypto_backtest.py # 加密货币网格回测（可选）
├── run_monitor.py       # 定时监控只推荐（可选，不依赖 OKX）
└── src/
    ├── data/
    ├── strategy/
    ├── risk/
    ├── backtest/
    └── execution/       # OKXBroker 等
```

## 安装

```bash
cd stock_trading_bot
pip install -r requirements.txt
```

## 如何运行

### 1. 配置 OKX API（必做）

在项目根目录复制 `.env.example` 为 `.env`，填入 OKX 三项：

```bash
cp .env.example .env
# 编辑 .env：OKX_API_KEY、OKX_API_SECRET、OKX_PASSPHRASE
```

也可在 Web 控制台「API 配置」页填写（留空不修改已有项）。

### 2. Web 控制台（推荐）

```bash
python server.py --port 5555
```

浏览器打开 http://127.0.0.1:5555/：启动/暂停、改交易对与参数、看实时日志；未配置 API 时先到「API 配置」填写。

如需让 Web 控制台在异常退出后自动重启，最多重启 3 次：

```bash
chmod +x scripts/run_server_supervised.sh scripts/stop_server_supervised.sh
./scripts/run_server_supervised.sh
```

默认会自动转为后台运行并监听 `0.0.0.0:5555`，异常退出后每 10 秒重启一次，最多重启 3 次。若想前台运行便于观察，可用：

```bash
FOREGROUND=1 ./scripts/run_server_supervised.sh
```

日志文件：

- `logs/server.log`
- `logs/server_supervisor.log`

### 3. 命令行单次 / 轮询

| 用途 | 命令 |
|------|------|
| 单次检查并下单 | `python run_okx_live.py --symbol BTC/USDT` |
| 每 60 秒轮询并下单 | `python run_okx_live.py --symbol BTC/USDT --interval 60` |
| 每 5 分钟轮询 | `python run_okx_live.py --symbol BTC/USDT --interval 300` |

`--ratio` 默认 **0.5**（涨跌 0.5% 触发）；可改为 `0.3`、`1`、`2` 等。

### 4. 能覆盖手续费的推荐参数

交易所市价单约 **0.1% / 笔**，一买一卖约 **0.2%**。单次「跌买→涨卖」价差建议 ≥ 0.3%，推荐 **0.5%**。

| 参数 | 建议 | 说明 |
|------|------|------|
| **触发比例 `--ratio`** | **≥ 0.5** | 涨跌 0.5% 触发，一来回约 1% 价差，扣 0.2% 手续费仍有空间。 |
| **轮询间隔 `--interval`** | **60～300 秒** | 太密易限频；60～120s 兼顾响应与稳定。 |

示例：

```bash
python run_okx_live.py --symbol BTC/USDT --ratio 0.5 --interval 60
```

### 5. 交易规则简述

以 `run_okx_live.py --symbol BTC/USDT --ratio 0.5 --interval 60` 为例：

| 项目 | 规则 |
|------|------|
| **标的** | 只做 BTC/USDT 现货。 |
| **参考价** | 内部维护「参考价」；首次运行 = 当前价；每次**触发买或卖**后更新为**当时成交价**。 |
| **何时买** | 当前价 **≤ 参考价 × (1 − 0.5%)** → 市价买入。 |
| **何时卖** | 当前价 **≥ 参考价 × (1 + 0.5%)** → 市价卖出（全部持仓）。 |
| **买多少** | 由参数「每次买入 USDT」等控制；至少满足最小下单额才下单。 |
| **轮询** | 每 **60 秒**取价，满足条件即触发一次买或卖。 |

详细规则与可调参数见 [docs/trading_rules_core.md](docs/trading_rules_core.md)、[docs/okx_automation.md](docs/okx_automation.md)。

## 回测（可选）

- **股票回测**：`python run_backtest.py`（默认 A 股示例，可改配置）。
- **加密货币网格回测**：`python run_crypto_backtest.py`（需 ccxt，可改为 OKX 数据源）。

## 风险与合规

- 不保证盈利；实盘前请充分了解规则与风险。
- 仅使用可承受亏损的资金。
