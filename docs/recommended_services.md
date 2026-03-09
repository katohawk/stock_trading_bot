# 推荐服务：数据、执行、定时与通知

按「一定比例 + 间隔，涨了就卖、跌了就买」做定时监控时，可选用以下类型的服务。

---

## 一、数据（查当前价 / 历史 K 线）

| 类型     | 服务/方式           | 说明 |
|----------|----------------------|------|
| 股票     | yfinance            | 免费，美股/A 股部分标的，本仓库已用 |
| 股票     | AkShare / Tushare   | A 股行情，本仓库已接 AkShare |
| 加密货币 | 交易所 REST/WebSocket | Binance、OKX、Bybit 等，ccxt 统一接口 |
| 加密货币 | yfinance (BTC-USD 等) | 免费，本仓库监控脚本默认用这个 |

---

## 二、执行（真正下单）

| 类型     | 服务/方式           | 说明 |
|----------|----------------------|------|
| 股票 A 股 | 券商官方 API、VN.py | 需开户，按券商文档对接 |
| 股票美股 | Alpaca、盈透(IB)    | Alpaca 有免费模拟与实盘 API |
| 加密货币 | Binance、OKX、Coinbase、Bybit | 注册后开 API Key，用 ccxt 或官方 SDK 下单 |

**注意**：只做「推荐」、不自动下单时，不需要对接执行层，用上面的数据拿到价格即可。

---

## 三、定时监控（按间隔跑）

| 方式           | 说明 |
|----------------|------|
| **本机 cron**  | `crontab -e`，例如每 5 分钟：`*/5 * * * * cd /path/to/stock_trading_bot && python run_monitor.py >> monitor.log 2>&1` |
| **本机循环**   | `python run_monitor.py --interval 300`，进程内每 300 秒跑一次 |
| **systemd timer** | Linux 下用 systemd 替代 cron，便于看日志和重启 |
| **云函数**     | 阿里云/腾讯云 定时触发器、AWS Lambda + EventBridge，按分钟/小时触发一次跑脚本 |
| **云容器**     | 若跑在服务器上，用 cron 或脚本内 `--interval` 即可 |

---

## 四、通知（把推荐推给你）

| 方式        | 说明 |
|-------------|------|
| **终端/日志** | 当前做法：`run_monitor.py` 打印到 stdout，重定向到文件或 cron 发邮件 |
| **邮件**    | 用 `mail` 或 Python smtplib，脚本结束时把「推荐」发到邮箱 |
| **Telegram**| 发到 Bot：调 Telegram Bot API 发一条消息（推荐内容 + 方向） |
| **企业微信/钉钉** | 调 Webhook 把推荐推到群或自己 |
| **Bark / 其他推送** | iOS Bark、Server 酱等，HTTP 请求即可 |

---

## 五、本仓库里的用法小结

- **最简规则**：`SimpleThresholdStrategy`，参数 `ratio_pct`（如 1 表示 1%），涨 ≥1% 建议卖、跌 ≥1% 建议买，参考价随推荐更新。
- **定时监控**：`python run_monitor.py [--symbol BTC-USD] [--ratio 1] [--interval 300]`，只输出推荐、不下单；参考价存 `.monitor_ref.json`。
- **推荐服务组合**：数据用 yfinance（或交易所 API）→ 本机 cron 或 `--interval` 定时跑 → 把打印结果接到邮件/Telegram/钉钉即可。

如需把「推荐」接到 Telegram 等，可在 `run_monitor.py` 里在打印后加一次 HTTP 请求（或调现成推送库）。

## 本仓库：OKX 实盘

本仓库仅支持 **OKX（欧易）** 现货：配置 `OKX_API_KEY`、`OKX_API_SECRET`、`OKX_PASSPHRASE` 后，用 `run_okx_live.py` 或 Web 控制台（`server.py`）即可涨卖跌买、自动实盘下单。完整步骤见 [docs/okx_automation.md](docs/okx_automation.md)。
