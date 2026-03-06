# 股票交易机器人（回测 + 实盘）

从数据、策略、风控到回测/实盘执行的完整链路，支持 A 股与美股。

## 结构

```
stock_trading_bot/
├── config.example.yaml   # 配置示例（含股票与加密货币）
├── docs/
│   ├── crypto_trading.md
│   ├── recommended_services.md # 推荐服务：数据、执行、定时、通知
│   ├── binance_automation.md  # 钱在币安：自动化方案与备选平台
│   └── okx_automation.md     # OKX（欧易）操作教程
├── requirements.txt
├── run_backtest.py       # 股票回测
├── run_live.py           # 股票模拟/实盘
├── run_crypto_backtest.py # 加密货币网格回测
├── run_monitor.py        # 定时监控：涨卖跌买只推荐不下单
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
  python run_monitor.py --symbol AAPL --ratio 0.5 --interval 300   # 每 300 秒跑一次
  ```
  参考价保存在 `.monitor_ref.json`，下次比较用。
- **推荐服务**：数据（yfinance/交易所）、执行（券商/交易所 API）、定时（cron / `--interval` / 云函数）、通知（邮件/Telegram/钉钉）见 [docs/recommended_services.md](docs/recommended_services.md)。

## 风险与合规

- 不保证盈利；实盘前请充分回测与模拟。
- A 股需遵守账户实名与监管要求；美股需注意 PDT 等规则。
- 仅使用可承受亏损的资金。
