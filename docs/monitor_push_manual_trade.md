# 无 API 时的方案：监控 + 推送提醒，人工下单

适用于：券商不给开 API、或不想用 API，操作频率不高（一天几次即可）的场景。**不需要爬券商页面**，用公开行情 + 推送即可。

---

## 一、思路

1. **行情从哪来**：用**公开数据**（yfinance、AkShare 等）拿当前价，不依赖券商接口，也**不用爬浏览器**。
2. **谁在算信号**：本仓库的 `run_monitor.py` 已实现「按参考价 + 比例，涨卖跌买」逻辑，只差「有信号时发一条推送」。
3. **谁在下单**：收到推送后，你**自己打开券商 APP/网页**手动买或卖，一天操作几次完全够用。

**要不要爬浏览器？**  
- **不必要**：价格用公开行情即可；推送里写「建议买入 / 建议卖出、当前价多少、参考价多少」就够你手动操作了。  
- **只有在你非要「从券商页面读持仓/资金」时才需要**：例如脚本里要显示「当前持仓 X 元、建议再买 Y 元」。那可以用浏览器自动化（如 Playwright）去读券商页面，但页面一改就要维护选择器，成本高，一般不做。

---

## 二、A 股时的频率与时段

- **轮询间隔**：不必像加密货币 1 分钟一次，**5 分钟甚至 15 分钟**足够；一天也就开盘 4 小时，轮询次数有限。
- **只在交易时段跑**：用 cron 或任务计划，只在 9:30–11:30、13:00–15:00 执行脚本；或脚本内判断时间，非时段直接退出。
- **T+1**：策略上「建议卖」只在你已有持仓、且非当日买入时才有意义，可在推送文案里加一句「若今日未买则可忽略卖出提醒」之类的说明。

---

## 三、本仓库里怎么接推送

`run_monitor.py` 已经：读参考价 → 取价 → 策略推荐 → 打印。  
只需在**有信号时**（`direction` 不为空）多调一次推送接口即可。

### 1. 可选推送方式（国内常用）

| 方式 | 说明 | 配置 |
|------|------|------|
| **Server 酱** | 微信通知，免费版有次数限制 | 注册取 `sendkey`，发 HTTP GET |
| **Bark** | iOS 推送 | 装 Bark App，取 device key，发 HTTP GET |
| **企业微信 / 钉钉 / 飞书** | 推送到群或自己 | 建群机器人得 Webhook URL，脚本已内置格式 |
| **Telegram** | 需能访问 | Bot Token + Chat ID，发 POST |

脚本里只要在「有买/卖建议」时发一条 HTTP 请求即可，无需爬取任何页面。

### 2. 运行方式

- **本机循环**（适合开着电脑时）：  
  `python run_monitor.py --symbol 000001.SZ --ratio 1 --interval 300 --push serverchan`  
  每 300 秒查一次，有信号就推送（具体参数见下节）。
- **仅交易时段**：用 cron，例如每 5 分钟、且只在 9–15 点：  
  `*/5 9-14 * * 1-5 cd /path/to/stock_trading_bot && python run_monitor.py --symbol 000001.SZ --ratio 1 --push serverchan >> monitor.log 2>&1`  
  （具体时间按你所在时区、开盘时间微调。）

### 3. 推送内容建议

标题示例：`[A股] 建议买入 000001` 或 `[A股] 建议卖出 000001`。  
正文示例：`当前价 12.34，参考价 12.00，涨 2.8%，建议卖出。请自行打开券商 APP 操作。`  
这样你收到后就知道该买还是该卖、大概什么价位，不需要脚本去读券商页面。

---

## 四、脚本用法（已支持 --push）

在 `run_monitor.py` 里已增加可选参数 `--push`，**只有出现买/卖信号时**才会发一条推送。

### 1. 推送方式与环境变量（国内推荐：企业微信 / 钉钉 / 飞书）

| `--push` 值   | 说明       | 环境变量 |
|---------------|------------|----------|
| **wecom**     | 企业微信群机器人 | `WECOM_WEBHOOK_URL` |
| **dingtalk**  | 钉钉群机器人   | `DINGTALK_WEBHOOK_URL` |
| **feishu**    | 飞书群机器人   | `FEISHU_WEBHOOK_URL` |
| serverchan    | Server 酱（微信） | `SERVERCHAN_SENDKEY` |
| bark          | Bark（iOS）     | `BARK_DEVICE_KEY`   |
| webhook       | 自定义 URL，POST JSON | `PUSH_WEBHOOK_URL` |

**企业微信**：群聊 → 添加群机器人 → 复制 Webhook 地址，形如 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`  
**钉钉**：群设置 → 智能群助手 → 添加机器人 → 自定义 → 复制 Webhook  
**飞书**：群设置 → 群机器人 → 添加机器人 → 自定义机器人 → 复制 Webhook，形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxx`

在 `.env` 里配置**当前使用的推送方式**对应变量即可，例如：

```bash
# 国内通讯（任选一个）
WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key
# DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=你的token
# FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/你的hook_id

# 其他
# SERVERCHAN_SENDKEY=你的sendkey
# BARK_DEVICE_KEY=你的Bark设备key
# PUSH_WEBHOOK_URL=https://...
```

### 2. 运行示例

```bash
# 只监控、不推送
python run_monitor.py --symbol 000001.SZ --ratio 1 --interval 300

# A 股：每 5 分钟检查，有信号推送到企业微信（交易需手动）
python run_monitor.py --symbol 000001.SZ --ratio 1 --interval 300 --push wecom

# 钉钉
python run_monitor.py --symbol 000001.SZ --ratio 1 --interval 300 --push dingtalk

# 飞书
python run_monitor.py --symbol 000001.SZ --ratio 1 --interval 300 --push feishu

# Server 酱 / Bark
python run_monitor.py --symbol 000001.SZ --ratio 1 --interval 300 --push serverchan
python run_monitor.py --symbol AAPL --ratio 0.5 --interval 600 --push bark
```

推送内容会包含：建议买/卖、当前价、参考价、一句「请打开券商 APP 手动操作」。

### 3. A 股标的符号

yfinance 可用沪深代码，例如 `000001.SZ`（深圳）、`600000.SH`（上海）。若本机 yfinance 对某代码取不到价，可换用 AkShare 等（需在脚本里接好数据源）。

---

## 五、小结

- **可以**用「监控行情 + 推送提醒 + 人工下单」的方式，不依赖券商 API，也**不需要爬取浏览器**（行情用公开数据即可）。
- 操作频率低、一天几回完全没问题；A 股把轮询间隔加大、只在交易时段跑即可。
- 本仓库已有 `run_monitor.py`，加上「有信号时发推送」（见下一节的脚本改动）即可用；推送方式任选一种（Server 酱 / Bark / 企业微信 / 钉钉等）。

已在 `run_monitor.py` 中实现 `--push wecom|dingtalk|feishu|serverchan|bark|webhook`；**全自动：取行情、算信号、发推送；交易需收到提醒后手动打开券商 APP 操作。**
