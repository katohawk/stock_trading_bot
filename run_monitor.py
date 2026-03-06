#!/usr/bin/env python3
"""
定时监控：按比例“涨了就卖、跌了就买”，只推荐不自动下单；有信号时推送，交易需人工操作。
全自动：取行情、算信号、发推送。手动：打开券商/APP 下单。
用法：
  python run_monitor.py --symbol 000001.SZ --ratio 1 --interval 300 --push wecom   # A 股 + 企业微信
  python run_monitor.py --symbol 000001.SZ --ratio 1 --interval 300 --push dingtalk # 钉钉
  python run_monitor.py --symbol 000001.SZ --ratio 1 --interval 300 --push feishu   # 飞书
参考价保存在 .monitor_ref.json。推送环境变量见 docs/monitor_push_manual_trade.md
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _http_post_json(url: str, payload: dict, timeout: int = 10) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    urllib.request.urlopen(req, timeout=timeout)


def push_notify(title: str, body: str, method: str) -> None:
    """有信号时推送提醒。method: wecom | dingtalk | feishu | serverchan | bark | webhook。依赖环境变量。"""
    content = f"{title}\n\n{body}"
    if method == "wecom":
        url = os.environ.get("WECOM_WEBHOOK_URL", "").strip()
        if not url:
            print("未设置 WECOM_WEBHOOK_URL，跳过推送", file=sys.stderr)
            return
        try:
            _http_post_json(url, {"msgtype": "text", "text": {"content": content}})
        except Exception as e:
            print("企业微信推送失败:", e, file=sys.stderr)
    elif method == "dingtalk":
        url = os.environ.get("DINGTALK_WEBHOOK_URL", "").strip()
        if not url:
            print("未设置 DINGTALK_WEBHOOK_URL，跳过推送", file=sys.stderr)
            return
        try:
            _http_post_json(url, {"msgtype": "text", "text": {"content": content}})
        except Exception as e:
            print("钉钉推送失败:", e, file=sys.stderr)
    elif method == "feishu":
        url = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
        if not url:
            print("未设置 FEISHU_WEBHOOK_URL，跳过推送", file=sys.stderr)
            return
        try:
            _http_post_json(url, {"msg_type": "text", "content": {"text": content}})
        except Exception as e:
            print("飞书推送失败:", e, file=sys.stderr)
    elif method == "serverchan":
        key = os.environ.get("SERVERCHAN_SENDKEY", "").strip()
        if not key:
            print("未设置 SERVERCHAN_SENDKEY，跳过推送", file=sys.stderr)
            return
        url = f"https://sctapi.ftqq.com/{key}.send?title={urllib.parse.quote(title)}&desp={urllib.parse.quote(body)}"
        try:
            req = urllib.request.Request(url)
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            print("Server酱推送失败:", e, file=sys.stderr)
    elif method == "bark":
        key = os.environ.get("BARK_DEVICE_KEY", "").strip()
        if not key:
            print("未设置 BARK_DEVICE_KEY，跳过推送", file=sys.stderr)
            return
        url = f"https://api.day.app/{key}/{urllib.parse.quote(title)}/{urllib.parse.quote(body)}"
        try:
            req = urllib.request.Request(url)
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            print("Bark 推送失败:", e, file=sys.stderr)
    elif method == "webhook":
        url = os.environ.get("PUSH_WEBHOOK_URL", "").strip()
        if not url:
            print("未设置 PUSH_WEBHOOK_URL，跳过推送", file=sys.stderr)
            return
        try:
            _http_post_json(url, {"title": title, "text": body})
        except Exception as e:
            print("Webhook 推送失败:", e, file=sys.stderr)


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
    parser.add_argument("--push", choices=("wecom", "dingtalk", "feishu", "serverchan", "bark", "webhook"), default=None,
                        help="有信号时推送：wecom=企业微信, dingtalk=钉钉, feishu=飞书, serverchan, bark, webhook")
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
        if args.push:
            action = "建议卖出" if direction.value == "flat" else "建议买入"
            title = f"[{args.symbol}] {action}"
            body = f"{text}\n当前价: {price:.4f}  参考价: {ref_price or '无'}\n请打开券商 APP 手动操作。"
            push_notify(title, body, args.push)
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
