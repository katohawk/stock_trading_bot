# OKX（欧易）操作教程：API 配置与自动化

资金在 **OKX** 时，用本仓库的 OKX 执行层做「涨卖跌买」定时监控与可选实盘下单。

---

## 一、在 OKX 创建 API（必做）

### 1. 登录 OKX

- 打开 [OKX 官网](https://www.okx.com) 或 App，登录账户。
- 确保账户已完成身份认证（KYC），否则 API 可能受限。

### 2. 创建 API Key

1. 网页端：右上角 **个人中心** → **API** → **创建 API**。  
   App：**我的** → **API 管理** → **创建 API**。
2. 选择 **交易** 类型（本仓库只用现货，不勾选提现）。
3. 设置 **Passphrase**：自己设一个 8–32 位密码并牢记，创建后无法查看，只用于 API 请求签名。
4. 完成安全验证（邮箱/手机/谷歌验证等）。
5. 创建成功后保存三样（Secret 只显示一次）：
   - **API Key**
   - **Secret Key**
   - **Passphrase**（你刚设的密码）

### 3. 权限与安全建议

- **权限**：只勾选 **交易**，不要勾选 **提现**，降低风险。
- **IP 白名单**（推荐）：在 API 管理里绑定你跑脚本的服务器或电脑公网 IP，避免 Key 泄露后被异地调用。

---

## 二、配置 Key 和密钥（两种方式任选）

OKX 需要三样：**API Key**、**Secret Key（密钥）**、**Passphrase**。  
其中 Passphrase 是你在「创建 API」时自己设的 8–32 位密码，不是 OKX 生成的，请务必记住。

### 方式一：用 .env 文件（推荐，只配一次）

1. 在项目根目录（`stock_trading_bot/`）下，复制示例文件并改名为 `.env`：
   ```bash
   cd stock_trading_bot
   cp .env.example .env
   ```
2. 用记事本或 VS Code 打开 `.env`，按下面格式填入（等号后面不要加空格）：
   ```
   OKX_API_KEY=你的API Key
   OKX_API_SECRET=你的Secret密钥
   OKX_PASSPHRASE=你创建API时自己设的密码
   ```
3. 保存后，运行 `python run_okx_live.py` 时会自动读取。`.env` 已在 `.gitignore` 里，不会被提交到 Git。

若未安装 `python-dotenv`，先执行：`pip install python-dotenv`。  
**注意**：脚本只会读取项目根目录下的 **`.env`** 文件，不会读 `.env.example`。请复制 `cp .env.example .env` 后编辑 `.env` 填入密钥；勿把真实密钥写在 `.env.example` 里（该文件可能被提交到 Git）。

### 方式二：用终端环境变量

每次新开终端都要执行一次（Linux/macOS）：

```bash
export OKX_API_KEY="你的 API Key"
export OKX_API_SECRET="你的 Secret 密钥"
export OKX_PASSPHRASE="你创建 API 时设的密码"
```

Windows PowerShell：

```powershell
$env:OKX_API_KEY="你的 API Key"
$env:OKX_API_SECRET="你的 Secret 密钥"
$env:OKX_PASSPHRASE="你创建 API 时设的密码"
```

---

## 三、安装依赖与运行

### 1. 安装

```bash
cd stock_trading_bot
pip install -r requirements.txt
```

需要 `ccxt`（requirements 里已有）。

### 2. 只推荐、不下单（不配 API 也能跑）

不设环境变量时，用 yfinance 拿价格，只打印「建议买/卖/观望」：

```bash
python run_okx_live.py --symbol BTC/USDT --ratio 1
```

### 3. 用 OKX 行情 + 只推荐

设置好 `OKX_API_KEY`、`OKX_API_SECRET`、`OKX_PASSPHRASE` 后，会从 OKX 拉当前价和权益，但仍只推荐、不下单：

```bash
python run_okx_live.py --symbol BTC/USDT --ratio 1 --interval 300
```

`--interval 300` 表示每 300 秒（5 分钟）检查一次，循环运行。

### 4. 实盘下单（慎用）

确认逻辑无误后再加 `--execute`，会按推荐在 OKX 现货市价买卖：

```bash
python run_okx_live.py --symbol BTC/USDT --ratio 1 --execute
```

- 涨 ≥ 比例（默认 1%）→ 市价卖出该币种持仓。
- 跌 ≥ 比例 → 用约 20% 权益或 95% USDT 余额市价买入。

建议先用 **OKX 模拟盘** 验证：

```bash
export OKX_API_KEY="模拟盘 API Key"
export OKX_API_SECRET="模拟盘 Secret"
export OKX_PASSPHRASE="模拟盘 Passphrase"
python run_okx_live.py --symbol BTC/USDT --ratio 1 --execute --demo
```

OKX 模拟盘需在官网单独申请模拟账户并创建 API，请求时加 `x-simulated-trading: 1`（本仓库 `--demo` 已处理）。

---

## 四、参数说明

| 参数 | 含义 | 示例 |
|------|------|------|
| `--symbol` | 交易对 | `BTC/USDT`、`ETH/USDT` |
| `--ratio` | 触发比例（%） | `1` 表示涨跌 1% 触发 |
| `--interval` | 循环间隔（秒），0 表示只跑一次 | `300` |
| `--execute` | 是否真实下单 | 不加则只推荐 |
| `--demo` | 是否用 OKX 模拟盘 | 需配模拟盘 API |

参考价会保存在当前目录的 `.monitor_ref.json`，下次运行会沿用，实现「相对上次价涨了卖、跌了买」。

---

## 五、代码对应关系

- **执行层**：`src/execution/broker_okx.py` 里的 `OKXBroker`，用 ccxt 连接 OKX 现货，实现下单、撤单、查单、查余额。
- **入口脚本**：`run_okx_live.py`，读环境变量、拉价格、调用 `SimpleThresholdStrategy.recommend()`，可选调用 `OKXBroker.submit_order()` 下单。
- **数据**：若需 OKX K 线回测，可用 `CryptoAdapter(exchange_id="okx", ...)` 拉历史数据（与币安同一套 Bar 结构）。

---

## 六、常见问题

- **API 报错 "Invalid API Key"**：检查 Key/Secret/Passphrase 是否完整、是否有多余空格、是否对应实盘/模拟盘。
- **报错 "Account mode does not support"**：OKX 账户模式要支持现货交易，在 OKX 账户设置里确认。
- **不想实盘先试**：用 `--demo` 并配置模拟盘 API，或只跑不加 `--execute`，看推荐结果即可。

总结：在 OKX 创建 API（交易权限、设 Passphrase）→ 配置三个环境变量 → 用 `run_okx_live.py` 只推荐或加 `--execute` 实盘下单；建议先用模拟盘或小资金验证。
