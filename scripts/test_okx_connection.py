#!/usr/bin/env python3
"""仅测试 OKX API 是否连通，不下单、不写任何配置。"""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

env_file = root / ".env"
if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        print("[.env] 已加载", env_file)
    except ImportError:
        print("[.env] 未安装 python-dotenv，请执行: pip install python-dotenv")
else:
    print("[.env] 未找到", env_file)

api_key = os.environ.get("OKX_API_KEY", "").strip()
api_secret = os.environ.get("OKX_API_SECRET", "").strip()
passphrase = os.environ.get("OKX_PASSPHRASE", "").strip()

print("OKX_API_KEY:     ", "已设置" if api_key else "未设置")
print("OKX_API_SECRET:  ", "已设置" if api_secret else "未设置")
print("OKX_PASSPHRASE:  ", "已设置" if passphrase else "未设置")

if not all([api_key, api_secret, passphrase]):
    print("\n请检查 .env 中 OKX_API_KEY、OKX_API_SECRET、OKX_PASSPHRASE 是否都填写且无空格。")
    sys.exit(1)

print("\n正在连接 OKX...")
try:
    from src.execution import OKXBroker
    broker = OKXBroker(api_key=api_key, api_secret=api_secret, passphrase=passphrase)
    account = broker.get_account()
    print("连接成功！")
    print("  账户权益(约):", round(account.equity, 2), "USDT")
    print("  可用(USDT等):", round(account.cash, 2))
    print("  持仓数量:", len(account.positions))
    if account.positions:
        for sym, pos in list(account.positions.items())[:5]:
            print("    ", sym, ":", round(pos.quantity, 6), "@", round(pos.current_price, 2))
except Exception as e:
    print("连接失败:", e)
    sys.exit(1)
