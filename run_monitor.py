#!/usr/bin/env python3
"""
定时监控：按比例“涨了就卖、跌了就买”，只给出推荐不自动下单。
用法：
  python run_monitor.py                    # 默认 BTC-USD, 1% 比例
  python run_monitor.py --symbol AAPL      # 美股
  python run_monitor.py --ratio 0.5         # 0.5% 触发
  python run_monitor.py --interval 300     # 每 300 秒跑一次（循环）
参考价会保存在 .monitor_ref.json，下次比较用。
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def get_price(symbol: str, market: str) -> float:
    if market == "crypto" or symbol.upper() in ("BTC/USDT", "BTC-USD", "ETH/USDT", "ETH-USD"):
        try:
            import yfinance as yf
            s = "BTC-USD" if "BTC" in symbol.upper() else symbol.replace("/", "-")
            t = yf.Ticker(s)
            hist = t.history(period="1d", interval="1m")
            if hist is not None and not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        hist = t.history(period="5d")
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"获取价格失败: {e}", file=sys.stderr)
    return 0.0


def main():
    parser = argparse.ArgumentParser(description="涨卖跌买监控，只推荐不下单")
    parser.add_argument("--symbol", default="BTC-USD", help="标的，如 BTC-USD / AAPL")
    parser.add_argument("--ratio", type=float, default=1.0, help="触发比例%%，如 1 表示 1%%")
    parser.add_argument("--ref-file", default=".monitor_ref.json", help="参考价存储文件")
    parser.add_argument("--interval", type=float, default=0, help="循环间隔秒，0 表示只跑一次")
    args = parser.parse_args()

    ref_path = Path(args.ref_file)
    ref_data = {}
    if ref_path.exists():
        try:
            ref_data = json.loads(ref_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    key = args.symbol
    ref_price = ref_data.get(key)

    from src.strategy import SimpleThresholdStrategy
    strategy = SimpleThresholdStrategy(ratio_pct=args.ratio, reference_price=ref_price)
    price = get_price(args.symbol, "crypto" if "BTC" in key or "ETH" in key else "stock")
    if price <= 0:
        print("无法获取价格，请检查标的与网络")
        return 1
    text, direction, new_ref = strategy.recommend(price)
    print(f"[{args.symbol}] 当前价: {price:.4f}  参考价: {ref_price or '无'}")
    print("推荐:", text)
    if direction is not None:
        print("操作方向:", "卖出" if direction.value == "flat" else "买入")
    ref_data[key] = new_ref
    try:
        ref_path.write_text(json.dumps(ref_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print("保存参考价失败:", e, file=sys.stderr)

    if args.interval > 0:
        print(f"\n{args.interval} 秒后再次检查...")
        time.sleep(args.interval)
        return main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
