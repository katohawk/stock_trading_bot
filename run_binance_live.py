#!/usr/bin/env python3
"""
币安现货：定时监控 + 涨卖跌买。可只推荐，也可实盘下单（需配置 API）。
环境变量：BINANCE_API_KEY, BINANCE_API_SECRET（实盘下单时必填）
用法：
  python run_binance_live.py --symbol BTC/USDT --ratio 1 --interval 300   # 每 5 分钟检查，只推荐
  python run_binance_live.py --symbol BTC/USDT --ratio 1 --execute         # 一次检查并真实下单（慎用）
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    parser = argparse.ArgumentParser(description="币安：涨卖跌买监控，可选实盘下单")
    parser.add_argument("--symbol", default="BTC/USDT", help="交易对，如 BTC/USDT")
    parser.add_argument("--ratio", type=float, default=1.0, help="触发比例%%")
    parser.add_argument("--interval", type=float, default=0, help="循环间隔秒，0 表示只跑一次")
    parser.add_argument("--execute", action="store_true", help="是否真实下单（否则只打印推荐）")
    parser.add_argument("--testnet", action="store_true", help="使用币安测试网")
    args = parser.parse_args()

    from src.strategy import SimpleThresholdStrategy
    from src.strategy.base import SignalDirection
    from src.execution import BinanceBroker
    from src.execution.order import OrderSide

    api_key = os.environ.get("BINANCE_API_KEY", "").strip()
    api_secret = os.environ.get("BINANCE_API_SECRET", "").strip()

    if args.execute and (not api_key or not api_secret):
        print("实盘下单需设置环境变量 BINANCE_API_KEY 和 BINANCE_API_SECRET")
        return 1

    # 当前价：有 API 则从币安拉，否则用策略内参考价比较（需之前跑过并保存了参考价）
    if api_key and api_secret:
        try:
            broker = BinanceBroker(api_key=api_key, api_secret=api_secret, testnet=args.testnet)
            account = broker.get_account()
            # 从币安 ticker 拿最新价
            ex = broker._get_exchange()
            ticker = ex.fetch_ticker(args.symbol)
            price = float(ticker.get("last") or ticker.get("close") or 0)
            print(f"[币安] {args.symbol} 当前价: {price:.4f}  权益约: {account.equity:.2f} USDT")
        except Exception as e:
            print("币安 API 失败:", e)
            return 1
    else:
        import yfinance as yf
        sym = "BTC-USD" if "BTC" in args.symbol else args.symbol.replace("/", "-")
        price = float(yf.Ticker(sym).history(period="1d").iloc[-1]["Close"])
        print(f"[行情] {args.symbol} 当前价: {price:.4f} (yfinance)")

    strategy = SimpleThresholdStrategy(ratio_pct=args.ratio, reference_price=None)
    # 从文件读上次参考价（与 run_monitor 一致）
    ref_file = Path(".monitor_ref.json")
    if ref_file.exists():
        try:
            import json
            data = json.loads(ref_file.read_text(encoding="utf-8"))
            strategy.reference_price = data.get(args.symbol)
        except Exception:
            pass
    text, direction, new_ref = strategy.recommend(price)
    print("推荐:", text)
    if direction is not None:
        print("操作方向:", "卖出" if direction == SignalDirection.FLAT else "买入")
        if args.execute and api_key and api_secret:
            broker = BinanceBroker(api_key=api_key, api_secret=api_secret, testnet=args.testnet)
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

    if ref_file.exists():
        import json
        try:
            data = json.loads(ref_file.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        data[args.symbol] = new_ref
        ref_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.interval > 0:
        import time
        print(f"\n{args.interval} 秒后再次检查...")
        time.sleep(args.interval)
        return main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
