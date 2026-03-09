# 腾讯云新加坡服务器部署指南（OKX 交易机器人）

本文给出在**腾讯云新加坡区**一台新服务器上，从零部署 OKX 交易机器人 Web 控制台的完整步骤，可直接按顺序执行，或作为「操作提示词」交给运维/AI 执行。

---

## 一、前置条件

- 已购买腾讯云 **云服务器 CVM**，地域选 **新加坡**，系统建议 **Ubuntu 22.04** 或 **Debian 11**。
- 已获取服务器 **公网 IP**、**SSH 登录方式**（密钥或密码）。
- 本机可 SSH 登录：`ssh root@<公网IP>` 或 `ssh ubuntu@<公网IP>`。

---

## 二、服务器环境准备

### 2.1 登录并更新系统（可选）

```bash
ssh root@<你的公网IP>
apt update && apt upgrade -y
```

### 2.2 安装 Python 3.10+ 与 git

```bash
apt install -y python3 python3-pip python3-venv git
python3 --version   # 确认 >= 3.10
```

### 2.3 创建运行用户（推荐，非 root）

```bash
adduser --disabled-password --gecos "" botuser
# 若需 sudo：usermod -aG sudo botuser
su - botuser
```

以下步骤若非特别说明，均在 `botuser` 家目录下操作。

---

## 三、部署项目代码

### 3.1 克隆仓库

```bash
cd ~
git clone https://github.com/katohawk/stock_trading_bot.git
cd stock_trading_bot
```

（若仓库为私有，需先配置 SSH key 或使用 HTTPS + 个人访问令牌。）

### 3.2 创建虚拟环境并安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3.3 配置环境变量（OKX API）

```bash
cp .env.example .env
chmod 600 .env
nano .env   # 或 vi / vim
```

在 `.env` 中填写（保存后勿提交到 git）：

```
OKX_API_KEY=你的Key
OKX_API_SECRET=你的Secret
OKX_PASSPHRASE=你的Passphrase
```

保存退出。

### 3.4 验证可运行

```bash
source venv/bin/activate
python server.py --host 0.0.0.0 --port 5555
```

浏览器访问 `http://<公网IP>:5555/`，能看到控制台即表示服务正常。`Ctrl+C` 停止。

---

## 四、开放防火墙端口（腾讯云 + 系统）

### 4.1 腾讯云安全组

- 登录 [腾讯云控制台](https://console.cloud.tencent.com/) → 云服务器 → 安全组。
- 找到该 CVM 绑定的安全组 → 编辑规则 → **入站规则** → 添加：
  - 协议：TCP
  - 端口：5555
  - 来源：若仅自己用填本机公网 IP，若需多端访问可填 `0.0.0.0/0`（有安全风险，建议配合强密码或 VPN）。
- 保存。

### 4.2 本机防火墙（若启用了 ufw）

```bash
sudo ufw allow 5555/tcp
sudo ufw status
sudo ufw enable   # 若尚未启用
```

---

## 五、后台常驻运行（systemd）

### 5.1 创建 systemd 服务文件

```bash
sudo nano /etc/systemd/system/okx-bot.service
```

写入（注意替换 `botuser` 与项目路径）：

```ini
[Unit]
Description=OKX Trading Bot Web Console
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/stock_trading_bot
Environment=PATH=/home/botuser/stock_trading_bot/venv/bin
ExecStart=/home/botuser/stock_trading_bot/venv/bin/python server.py --host 0.0.0.0 --port 5555
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

保存退出。

### 5.2 启用并启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable okx-bot
sudo systemctl start okx-bot
sudo systemctl status okx-bot
```

查看日志：`sudo journalctl -u okx-bot -f`

---

## 六、可选：Nginx 反代 + HTTPS

若希望通过域名 + HTTPS 访问（推荐）：

1. 安装 Nginx：`sudo apt install -y nginx`
2. 申请证书（腾讯云 SSL 或 Let’s Encrypt）。
3. 新增站点配置，例如 `/etc/nginx/sites-available/okx-bot`：

```nginx
server {
    listen 443 ssl;
    server_name 你的域名;
    ssl_certificate     /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:5555;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用站点并重载 Nginx：`sudo ln -s /etc/nginx/sites-available/okx-bot /etc/nginx/sites-enabled/`，`sudo nginx -t && sudo systemctl reload nginx`。安全组放行 443。

---

## 七、安全建议

- **不要**把 `.env` 提交到 git；生产环境仅放在服务器本地，权限 `600`。
- 若 5555 对公网开放，建议：限制安全组来源 IP，或只用 Nginx + HTTPS + 强密码/二次验证。
- 定期 `git pull` 更新代码后重启服务：`sudo systemctl restart okx-bot`。
- 如需备份：备份 `.env`、`.monitor_ref.json`、`.session_pnl.json` 即可。

---

## 八、常用命令速查

| 操作           | 命令 |
|----------------|------|
| 启动服务       | `sudo systemctl start okx-bot` |
| 停止服务       | `sudo systemctl stop okx-bot` |
| 重启服务       | `sudo systemctl restart okx-bot` |
| 查看状态       | `sudo systemctl status okx-bot` |
| 查看实时日志   | `sudo journalctl -u okx-bot -f` |
| 更新代码后重启 | `cd ~/stock_trading_bot && git pull && sudo systemctl restart okx-bot` |

---

## 九、给 AI/运维的「操作提示词」精简版

可直接把下面整段作为提示词交给助手执行：

```
在腾讯云新加坡的一台 Ubuntu 22.04 CVM 上部署 OKX 交易机器人：

1. 用 root 或 ubuntu 登录后：安装 python3、python3-pip、python3-venv、git。
2. 创建用户 botuser，在 botuser 家目录克隆仓库：git clone https://github.com/katohawk/stock_trading_bot.git，进入目录。
3. 创建 venv，pip install -r requirements.txt；复制 .env.example 为 .env，在 .env 中填写 OKX_API_KEY、OKX_API_SECRET、OKX_PASSPHRASE。
4. 用 systemd 配置服务：WorkingDirectory 和 User 指向 botuser 与项目路径，ExecStart 用 venv 里的 python 执行 server.py --host 0.0.0.0 --port 5555，Restart=always。enable 并 start 服务。
5. 腾讯云安全组入站放行 TCP 5555（来源按需限制）；本机若开 ufw 则 ufw allow 5555/tcp。
6. 验证：浏览器访问 http://<公网IP>:5555/ 能看到 Web 控制台即可。
```

完成以上步骤后，即可在腾讯云新加坡服务器上通过 `http://<公网IP>:5555/`（或配置的域名）使用 OKX 交易机器人。
