#!/usr/bin/env python3
"""
OKX（欧易）现货：定时监控 + 涨卖跌买。可只推荐，也可实盘下单（需配置 API）。
环境变量：OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE（实盘下单时必填）
用法：
  python run_okx_live.py --symbol BTC/USDT --ratio 1 --interval 300   # 每 5 分钟检查，只推荐
  python run_okx_live.py --symbol BTC/USDT --ratio 1 --execute         # 一次检查并真实下单（慎用）
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 从项目根目录的 .env 加载配置（若有）
_env_file = Path(__file__).resolve().parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        pass


def get_price_from_okx(broker, symbol: str) -> float:
    ex = broker._get_exchange()
    ticker = ex.fetch_ticker(symbol)
    return float(ticker.get("last") or ticker.get("close") or 0)


def get_price_fallback(symbol: str) -> float:
    import yfinance as yf
    sym = "BTC-USD" if "BTC" in symbol else symbol.replace("/", "-")
    hist = yf.Ticker(sym).history(period="1d")
    if hist is not None and not hist.empty:
        return float(hist["Close"].iloc[-1])
    return 0.0


def load_ref(ref_file: Path, symbol: str):
    if not ref_file.exists():
        return None
    try:
        data = json.loads(ref_file.read_text(encoding="utf-8"))
        return data.get(symbol)
    except Exception:
        return None


def save_ref(ref_file: Path, symbol: str, new_ref: float):
    try:
        data = json.loads(ref_file.read_text(encoding="utf-8")) if ref_file.exists() else {}
    except Exception:
        data = {}
    data[symbol] = new_ref
    ref_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="OKX：涨卖跌买监控，可选实盘下单")
    parser.add_argument("--symbol", default="BTC/USDT", help="交易对，如 BTC/USDT")
    parser.add_argument("--ratio", type=float, default=1.0, help="触发比例%%")
    parser.add_argument("--interval", type=float, default=0, help="循环间隔秒，0 表示只跑一次")
    parser.add_argument("--execute", action="store_true", help="是否真实下单（否则只打印推荐）")
    parser.add_argument("--demo", action="store_true", help="使用 OKX 模拟盘")
    args = parser.parse_args()

    from src.strategy import SimpleThresholdStrategy
    from src.strategy.base import SignalDirection
    from src.execution import OKXBroker
    from src.execution.order import OrderSide

    api_key = os.environ.get("OKX_API_KEY", "").strip()
    api_secret = os.environ.get("OKX_API_SECRET", "").strip()
    passphrase = os.environ.get("OKX_PASSPHRASE", "").strip()

    if args.execute and (not api_key or not api_secret or not passphrase):
        print("实盘下单需设置环境变量 OKX_API_KEY、OKX_API_SECRET、OKX_PASSPHRASE")
        return 1

    ref_file = Path(".monitor_ref.json")
    strategy = SimpleThresholdStrategy(ratio_pct=args.ratio, reference_price=load_ref(ref_file, args.symbol))

    if api_key and api_secret and passphrase:
        try:
            broker = OKXBroker(api_key=api_key, api_secret=api_secret, passphrase=passphrase, demo=args.demo)
            account = broker.get_account()
            price = get_price_from_okx(broker, args.symbol)
            print(f"[OKX] {args.symbol} 当前价: {price:.4f}  权益约: {account.equity:.2f} USDT")
        except Exception as e:
            print("OKX API 失败:", e)
            return 1
    else:
        price = get_price_fallback(args.symbol)
        print(f"[行情] {args.symbol} 当前价: {price:.4f} (yfinance)")

    if price <= 0:
        print("无法获取价格")
        return 1

    text, direction, new_ref = strategy.recommend(price)
    print("推荐:", text)
    if direction is not None:
        print("操作方向:", "卖出" if direction == SignalDirection.FLAT else "买入")
        if args.execute and api_key and api_secret and passphrase:
            broker = OKXBroker(api_key=api_key, api_secret=api_secret, passphrase=passphrase, demo=args.demo)
            account = broker.get_account()
            if direction == SignalDirection.LONG:
                cost = min(account.cash * 0.95, account.equity * 0.2)
                if cost > 10:
                    qty = cost / price
                    order = broker.submit_order(args.symbol, OrderSide.BUY, qty, price=None, reason=text)
                    print("下单结果:", order.state, order.filled_quantity, order.filled_avg_price or "")
                else:
                    print("余额不足或比例过小，未下单")
            else:
                pos = account.positions.get(args.symbol)
                if pos and pos.quantity > 0:
                    order = broker.submit_order(args.symbol, OrderSide.SELL, pos.quantity, price=None, reason=text)
                    print("下单结果:", order.state, order.filled_quantity, order.filled_avg_price or "")
                else:
                    print("无该币种持仓，未下单")

    save_ref(ref_file, args.symbol, new_ref)

    if args.interval > 0:
        print(f"\n{args.interval} 秒后再次检查...")
        time.sleep(args.interval)
        return main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
