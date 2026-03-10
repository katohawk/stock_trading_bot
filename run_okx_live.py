#!/usr/bin/env python3
"""
OKX 自动化交易脚本：参考价涨卖跌买 + 盈利硬约束 + 三秒价格确认 + 市价保护 + 持久化 .monitor_ref.json。
API Key 存放在 .env。详细中文日志。
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_env_file = Path(__file__).resolve().parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        pass

# ---------- 常量 -----------
DUST_QTY = 1e-8                  # 持仓量低于此视为 0（粉尘不参与买卖与成本）
MIN_PROFIT_RATIO = 0.003           # 卖出硬约束：扣费后至少 0.3% 利润
PRICE_SAMPLES = 3                  # 三秒价格确认：取样次数
PRICE_SAMPLE_INTERVAL = 1.0        # 取样间隔（秒）
SPIKE_STD_THRESHOLD_PCT = 0.001    # 3 次均价标准差 > 0.1% 判定插针
MAX_SLIPPAGE = 0.001               # 市价保护：买一卖一价差超过 0.1% 暂缓
COOLDOWN_SEC_DEFAULT = 60          # 同币种两次下单最小间隔（秒）
SELL_FEE_COMP_PCT_DEFAULT = 0.2    # 上一笔买入后卖出时额外比例补偿（%）
EXEC_QUALITY_THRESHOLD_PCT = 0.1   # 成交价与下单时均价偏差超此阈值计为一次不良
EXEC_PAUSE_SEC_DEFAULT = 300       # 连续 3 次不良后自动暂停秒数

MONITOR_REF_FILE = Path(__file__).resolve().parent / ".monitor_ref.json"
SESSION_PNL_FILE = Path(__file__).resolve().parent / ".session_pnl.json"

# 成交质量：连续不良次数（进程内，连续 3 次超差则暂停 5 分钟）
_consecutive_bad_exec = 0


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [日志] {msg}")


def load_state(symbol: str) -> dict:
    """从 .monitor_ref.json 读取 reference_price、avg_cost、position_qty。"""
    if not MONITOR_REF_FILE.exists():
        return {}
    try:
        data = json.loads(MONITOR_REF_FILE.read_text(encoding="utf-8"))
        raw = data.get(symbol)
        if isinstance(raw, dict):
            return raw
        # 旧格式或误存为数字等：只保留 reference_price 或视为空
        if raw is not None and isinstance(raw, (int, float)):
            return {"reference_price": float(raw)}
        return {}
    except Exception as e:
        _log(f"读取 .monitor_ref.json 失败: {e}")
        return {}


def save_state(
    symbol: str,
    reference_price: float = None,
    avg_cost: float = None,
    position_qty: float = None,
    last_order_time: float = None,
    last_trade_side: str = None,
) -> None:
    """将 reference_price、avg_cost、position_qty、last_order_time、last_trade_side 同步写入 .monitor_ref.json。"""
    try:
        data = json.loads(MONITOR_REF_FILE.read_text(encoding="utf-8")) if MONITOR_REF_FILE.exists() else {}
    except Exception:
        data = {}
    if symbol not in data or not isinstance(data[symbol], dict):
        data[symbol] = {}
    if reference_price is not None:
        data[symbol]["reference_price"] = reference_price
    if avg_cost is not None:
        data[symbol]["avg_cost"] = avg_cost
    if position_qty is not None:
        data[symbol]["position_qty"] = position_qty
        if position_qty == 0:
            data[symbol].pop("avg_cost", None)  # 空仓时清掉成本，避免残留导致误判
    if last_order_time is not None:
        data[symbol]["last_order_time"] = last_order_time
    if last_trade_side is not None:
        data[symbol]["last_trade_side"] = last_trade_side
    MONITOR_REF_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _log("已持久化 .monitor_ref.json: %s reference_price=%s avg_cost=%s position_qty=%s" % (symbol, reference_price, avg_cost, position_qty))


def get_price_from_okx(broker, symbol: str) -> float:
    """优先用公开 ticker 接口（不触发 load_markets），避免 ccxt 解析 None 币种报错。"""
    ex = broker._get_exchange()
    try:
        inst_id = symbol.replace("/", "-")
        res = ex.public_get_market_ticker(params={"instId": inst_id})
        if res.get("code") == "0" and res.get("data"):
            d = res["data"][0]
            last = d.get("last") or d.get("lastPx") or d.get("lastPx") or 0
            if last:
                return float(last)
    except Exception:
        pass
    ticker = ex.fetch_ticker(symbol)
    return float(ticker.get("last") or ticker.get("close") or 0)


def get_price_from_okx_with_retry(broker, symbol: str, max_retries: int = 3) -> float:
    for attempt in range(max_retries):
        try:
            return get_price_from_okx(broker, symbol)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err or "limit" in err:
                wait = 2 ** attempt
                _log(f"API 限频，第 {attempt + 1}/{max_retries} 次重试，{wait}s 后重试...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("获取价格重试次数用尽")


def fetch_three_price_samples(broker, symbol: str, sample_interval: float = PRICE_SAMPLE_INTERVAL, n: int = PRICE_SAMPLES):
    """每隔 1 秒取样一次，连续 3 次，返回 (均价, 标准差, 是否插针)。"""
    samples = []
    for i in range(n):
        try:
            p = get_price_from_okx_with_retry(broker, symbol)
            samples.append(p)
            _log(f"  价格取样 {i + 1}/{n}: {p:.4f}")
        except Exception as e:
            _log(f"  取样 {i + 1} 失败: {e}")
            return None, None, True
        if i < n - 1:
            time.sleep(sample_interval)
    import statistics
    avg = sum(samples) / len(samples)
    try:
        std = statistics.stdev(samples)
    except Exception:
        std = 0.0
    # 标准差 / 均价 > 0.1% 判定为插针
    is_spike = (avg > 0 and (std / avg) > SPIKE_STD_THRESHOLD_PCT)
    _log(f"  三秒价格确认: 均价={avg:.4f} 标准差={std:.4f} 标准差/均价={std/avg*100:.3f}% 判定插针={is_spike}")
    return avg, std, is_spike


def get_bid_ask(broker, symbol: str) -> tuple:
    """获取买一卖一价，返回 (bid1, ask1)。用公开接口避免 load_markets 触发 None 解析。"""
    ex = broker._get_exchange()
    try:
        inst_id = symbol.replace("/", "-")
        res = ex.public_get_market_books(params={"instId": inst_id, "sz": "1"})
        if res.get("code") != "0" or not res.get("data"):
            raise ValueError("no data")
        item = res["data"][0]
        bids = item.get("bids") or []
        asks = item.get("asks") or []
        bid1 = float(bids[0][0]) if bids else 0.0
        ask1 = float(asks[0][0]) if asks else 0.0
        return bid1, ask1
    except Exception:
        ob = ex.fetch_order_book(symbol, limit=1)
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        bid1 = float(bids[0][0]) if bids else 0.0
        ask1 = float(asks[0][0]) if asks else 0.0
        return bid1, ask1


def check_slippage_ok(broker, symbol: str, max_slippage: float = MAX_SLIPPAGE) -> bool:
    """市价保护：价差超过 max_slippage 则暂缓。返回 True 表示可下单。"""
    bid1, ask1 = get_bid_ask(broker, symbol)
    if bid1 <= 0 or ask1 <= 0:
        _log("  市价保护: 无法获取买卖盘，跳过校验")
        return True
    spread = ask1 - bid1
    mid = (bid1 + ask1) / 2
    spread_pct = spread / mid if mid else 0
    _log(f"  市价保护: 买一={bid1:.4f} 卖一={ask1:.4f} 价差={spread_pct*100:.3f}% 上限={max_slippage*100:.2f}%")
    if spread_pct > max_slippage:
        _log("  市价保护: 价差过大，暂缓下单")
        return False
    return True


def get_price_fallback(symbol: str) -> float:
    import yfinance as yf
    sym = "BTC-USD" if "BTC" in symbol else symbol.replace("/", "-")
    hist = yf.Ticker(sym).history(period="1d")
    if hist is not None and not hist.empty:
        return float(hist["Close"].iloc[-1])
    return 0.0


def load_session_pnl():
    if not SESSION_PNL_FILE.exists():
        return None, 0.0
    try:
        data = json.loads(SESSION_PNL_FILE.read_text(encoding="utf-8"))
        return data.get("session_start_equity"), float(data.get("cumulative_fee", 0))
    except Exception:
        return None, 0.0


def save_session_pnl(session_start_equity: float, cumulative_fee: float):
    data = {"session_start_equity": session_start_equity, "cumulative_fee": cumulative_fee}
    SESSION_PNL_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sell_profit_ok(price: float, avg_cost: float, taker_fee_rate: float) -> bool:
    """盈利硬约束：至少覆盖双边手续费并留出最小缓冲，避免小波动反复磨损。"""
    if avg_cost is None or avg_cost <= 0:
        return True
    profit_ratio = (price - avg_cost) / avg_cost
    min_profit_ratio = max(MIN_PROFIT_RATIO, taker_fee_rate * 2 + 0.001)
    ok = profit_ratio > min_profit_ratio
    _log(f"  盈利硬约束: 当前价={price:.4f} 持仓成本={avg_cost:.4f} 利润率={profit_ratio*100:.3f}% 需>{min_profit_ratio*100:.2f}% 通过={ok}")
    return ok


def check_execution_quality(exec_price: float, fill_price: float, threshold_pct: float, pause_sec: float) -> None:
    """记录成交价与下单时均价偏差；连续 3 次超阈值则暂停 pause_sec 秒。"""
    global _consecutive_bad_exec
    if exec_price <= 0:
        return
    deviation_pct = (fill_price - exec_price) / exec_price * 100
    _log(f"  成交质量: 下单时均价={exec_price:.4f} 成交价={fill_price:.4f} 偏差={deviation_pct:+.3f}%")
    if abs(deviation_pct) > threshold_pct:
        _consecutive_bad_exec += 1
        _log(f"  成交价偏差超过阈值 {threshold_pct}%，当前连续次数={_consecutive_bad_exec}")
        if _consecutive_bad_exec >= 3:
            _log("  成交价偏差连续 3 次超阈值，自动暂停 %d 分钟以避开剧烈波动" % (pause_sec / 60))
            time.sleep(pause_sec)
            _consecutive_bad_exec = 0
    else:
        _consecutive_bad_exec = 0


def wait_for_order_fill(broker, order, timeout_sec: float = 30, poll_interval: float = 2):
    """下单后轮询订单状态直到成交/撤单/拒单或超时。返回更新后的 order。"""
    from src.execution.order import OrderState
    if order.is_done():
        return order
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        time.sleep(poll_interval)
        o = broker.get_order(order.broker_order_id or order.order_id)
        if o is None:
            break
        order = o
        if order.is_done():
            _log(f"  订单 {order.broker_order_id} 状态: {order.state}")
            return order
    _log(f"  订单 {order.broker_order_id} 轮询超时({timeout_sec}s)，当前状态: {order.state}")
    return order


def run_once(args) -> int:
    """执行一轮检查与下单，返回退出码。"""
    from src.strategy import SimpleThresholdStrategy
    from src.strategy.base import SignalDirection
    from src.execution import OKXBroker
    from src.execution.order import OrderSide, OrderState

    api_key = os.environ.get("OKX_API_KEY", "").strip()
    api_secret = os.environ.get("OKX_API_SECRET", "").strip()
    passphrase = os.environ.get("OKX_PASSPHRASE", "").strip()

    if not api_key or not api_secret or not passphrase:
        _log("请在 .env 或 API 配置页设置 OKX_API_KEY、OKX_API_SECRET、OKX_PASSPHRASE")
        return 1

    state = load_state(args.symbol)
    ref_price = state.get("reference_price")
    avg_cost = state.get("avg_cost")  # 持仓成本，与文档一致
    position_qty = state.get("position_qty", 0) or 0
    if (position_qty or 0) < DUST_QTY:
        position_qty = 0
    last_order_time = state.get("last_order_time") or 0
    last_trade_side = state.get("last_trade_side") or ""

    strategy = SimpleThresholdStrategy(ratio_pct=args.ratio, reference_price=ref_price)

    broker = None
    if api_key and api_secret and passphrase:
        api_ok = False
        for attempt in range(2):
            try:
                broker = broker or OKXBroker(api_key=api_key, api_secret=api_secret, passphrase=passphrase)
                account = broker.get_account()
                price = get_price_from_okx_with_retry(broker, args.symbol)
                session_start, cumulative_fee = load_session_pnl()
                if session_start is None:
                    session_start = account.equity
                    save_session_pnl(session_start, cumulative_fee)
                pos = account.positions.get(args.symbol)
                qty_from_ex = (pos.quantity if pos else 0) or 0
                if qty_from_ex >= DUST_QTY and not (position_qty or 0):
                    position_qty = qty_from_ex
                    if not avg_cost or avg_cost <= 0:
                        avg_cost = price
                    save_state(args.symbol, position_qty=position_qty, avg_cost=avg_cost)
                    _log("已从交易所同步持仓: 数量=%s 成本(估)=%.4f" % (position_qty, avg_cost))
                elif qty_from_ex < DUST_QTY and (position_qty or avg_cost):
                    position_qty = 0
                    save_state(args.symbol, position_qty=0)
                    _log("交易所持仓为粉尘或空仓，已置空本地持仓与成本")
                pnl = account.equity - session_start
                net_pnl = pnl - cumulative_fee
                _log(f"{args.symbol} 当前价={price:.4f} 权益={account.equity:.2f} USDT 本次运行收益={pnl:+.2f} USDT 累计手续费(估)={cumulative_fee:.2f} USDT 净收益={net_pnl:+.2f} USDT")
                api_ok = True
                break
            except TypeError as e:
                err_msg = str(e)
                if "NoneType" in err_msg and "str" in err_msg and attempt == 0:
                    _log("OKX/ccxt 解析返回遇到 None 币种(已知兼容问题)，3 秒后重试...")
                    time.sleep(3)
                else:
                    _log("OKX API 失败: %s" % err_msg)
                    return 1
            except Exception as e:
                _log("OKX API 失败: %s" % e)
                return 1
        if not api_ok:
            return 1

    if price <= 0:
        _log("无法获取价格，退出")
        return 1

    if (
        (position_qty or 0) < DUST_QTY
        and ref_price
        and ref_price > 0
        and args.empty_rebase_up_pct > 0
        and price >= ref_price * (1 + args.empty_rebase_up_pct / 100.0)
    ):
        old_ref = ref_price
        ref_price = price
        strategy.set_reference(ref_price)
        save_state(args.symbol, reference_price=ref_price, position_qty=0)
        _log(
            "空仓上行重定锚: 当前价较参考价上涨已达 %.2f%%，参考价从 %.2f 上调到 %.2f"
            % (args.empty_rebase_up_pct, old_ref, ref_price)
        )

    # 明确当前是「等买」还是「等卖」，方便看日志
    if (position_qty or 0) < DUST_QTY:
        ref_hint = f"参考价={ref_price:.2f}" if ref_price else "参考价=当前价"
        _log(f"当前状态: 仅 USDT，等待跌 {args.ratio}% 触发买入（{ref_hint}）")
        if ref_price and ref_price > 0:
            buy_trigger = ref_price * (1 - args.ratio / 100.0)
            _log(f"  买入触发价={buy_trigger:.2f}（当前价≤此价才买），当前价={price:.2f}")
    else:
        cost_hint = f"成本约={avg_cost:.2f}" if avg_cost else ""
        effective_sell_ratio = args.ratio + (args.sell_fee_compensation_pct if last_trade_side == "buy" else 0.0)
        if last_trade_side == "buy":
            _log(
                f"当前状态: 持有 BTC 约 {position_qty}，等待涨 {effective_sell_ratio}% 触发卖出（基础 {args.ratio}% + 手续费补偿 {args.sell_fee_compensation_pct}%）（{cost_hint}）"
            )
        else:
            _log(f"当前状态: 持有 BTC 约 {position_qty}，等待涨 {args.ratio}% 触发卖出（{cost_hint}）")
        sell_ref = ref_price or avg_cost
        if sell_ref and sell_ref > 0:
            sell_trigger = sell_ref * (1 + effective_sell_ratio / 100.0)
            _log(f"  卖出触发价={sell_trigger:.2f}（当前价≥此价才卖），当前价={price:.2f}")

    text, direction, new_ref = strategy.recommend(price)
    # 非对称比例：上一笔是买入时，卖出需额外涨幅（手续费补偿）才触发
    if direction == SignalDirection.FLAT and last_trade_side == "buy" and ref_price and ref_price > 0:
        min_sell_ratio = (args.ratio + args.sell_fee_compensation_pct) / 100.0
        if price < ref_price * (1 + min_sell_ratio):
            direction = None
            text = "涨幅未达比例+手续费补偿，观望（上一笔为买入，需多涨 %.2f%% 再卖）" % (args.sell_fee_compensation_pct,)
    # 空仓时若价格上涨到“卖出阈值”，不应把参考价继续上抬，否则买入触发价会一路追涨。
    if direction == SignalDirection.FLAT and (position_qty or 0) < DUST_QTY:
        direction = None
        new_ref = ref_price
        text = "空仓但价格已涨过参考价，继续等待回落买入；本次不更新参考价"
    _log(f"推荐: {text}")
    if direction is None and (position_qty or 0) < DUST_QTY:
        _log("（当前无持仓，下次触发为买入）")

    executed = False
    if direction is not None:
        _log(f"操作方向: {'卖出' if direction == SignalDirection.FLAT else '买入'}")

        if broker is not None:
            elapsed = time.time() - last_order_time
            if elapsed < args.cooldown_sec:
                _log("冷静期未满，跳过本次下单（距上次 %.1f 秒，需至少 %.0f 秒）" % (elapsed, args.cooldown_sec))
            else:
                # 三秒价格确认：每隔 1 秒取样，共 3 次
                _log("开始三秒价格确认（每隔 1 秒取样，共 3 次）...")
                exec_price, _std, is_spike = fetch_three_price_samples(broker, args.symbol, PRICE_SAMPLE_INTERVAL, PRICE_SAMPLES)
                if exec_price is None or is_spike:
                    _log("插针判定: 3 次均价标准差 > 0.1%，取消本次下单")
                else:
                    account = broker.get_account()
                    # 市价保护
                    if not check_slippage_ok(broker, args.symbol, args.max_slippage):
                        _log("市价保护: 买一卖一价差过大，暂缓下单")
                    else:
                        if direction == SignalDirection.LONG:
                            amount_usdt = min(args.buy_amount_usdt, account.cash * 0.98)
                            if amount_usdt >= args.min_buy_usdt:
                                qty = amount_usdt / exec_price
                                try:
                                    order = broker.submit_order(args.symbol, OrderSide.BUY, qty, price=None, reason=text)
                                    if not order.is_done():
                                        order = wait_for_order_fill(broker, order, timeout_sec=30, poll_interval=2)
                                    if order.state == OrderState.FILLED and order.filled_quantity and order.filled_avg_price:
                                        fill_qty = order.filled_quantity
                                        fill_price = order.filled_avg_price
                                        fee_est = fill_qty * fill_price * args.taker_fee_rate
                                        session_start, cum_fee = load_session_pnl()
                                        if session_start is not None:
                                            save_session_pnl(session_start, cum_fee + fee_est)
                                        if position_qty and avg_cost:
                                            new_avg = (avg_cost * position_qty + fill_price * fill_qty) / (position_qty + fill_qty)
                                            new_qty = position_qty + fill_qty
                                        else:
                                            new_avg = fill_price
                                            new_qty = fill_qty
                                        save_state(args.symbol, reference_price=fill_price, avg_cost=new_avg, position_qty=new_qty, last_order_time=time.time(), last_trade_side="buy")
                                        check_execution_quality(exec_price, fill_price, args.exec_quality_threshold_pct, args.exec_pause_sec)
                                        _log(f"买入成交: 数量={fill_qty} 成交价={fill_price:.2f} 成交额={fill_qty * fill_price:.2f} USDT 本次手续费(估)={fee_est:.2f} USDT 更新持仓成本={new_avg:.4f} 持仓量={new_qty}")
                                        executed = True
                                    else:
                                        _log(f"下单结果: {order.state} {order.reason or ''}")
                                except Exception as e:
                                    _log(f"下单异常: {e}")
                            else:
                                _log("余额不足或低于最小下单额，未下单（可用 USDT=%.2f 需>=%.2f）" % (account.cash, args.min_buy_usdt))
                        else:
                            # 卖出：持仓为粉尘/空仓则只更新参考价；否则做盈利硬约束再卖
                            if (position_qty or 0) < DUST_QTY:
                                _log("持仓为粉尘或空仓，仅更新参考价，不卖出")
                                save_state(args.symbol, reference_price=new_ref, position_qty=0)
                                executed = True
                            elif not sell_profit_ok(exec_price, avg_cost, args.taker_fee_rate):
                                _log("卖出跳过: 扣费后利润空间不足，不卖出")
                            else:
                                pos = account.positions.get(args.symbol)
                                if pos and (pos.quantity or 0) >= DUST_QTY:
                                    try:
                                        order = broker.submit_order(args.symbol, OrderSide.SELL, pos.quantity, price=None, reason=text)
                                        if not order.is_done():
                                            order = wait_for_order_fill(broker, order, timeout_sec=30, poll_interval=2)
                                        if order.state == OrderState.FILLED and order.filled_quantity and order.filled_avg_price:
                                            sell_price = order.filled_avg_price
                                            sell_qty = order.filled_quantity
                                            trade_value = sell_qty * sell_price
                                            fee_est = trade_value * args.taker_fee_rate
                                            session_start, cum_fee = load_session_pnl()
                                            if session_start is not None:
                                                save_session_pnl(session_start, cum_fee + fee_est)
                                            avg = avg_cost or sell_price
                                            expected_return_pct = (sell_price - avg) / avg * 100
                                            after_fee_return_pct = expected_return_pct - 2 * args.taker_fee_rate * 100
                                            _log(f"卖出成交: 数量={sell_qty} 成交价={sell_price:.2f} 成交额={trade_value:.2f} USDT 本次手续费(估)={fee_est:.2f} USDT")
                                            _log(f"预期收益率: {expected_return_pct:.2f}%  |  扣费后收益: {after_fee_return_pct:.2f}%")
                                            save_state(args.symbol, reference_price=sell_price, avg_cost=None, position_qty=0.0, last_order_time=time.time(), last_trade_side="sell")
                                            check_execution_quality(exec_price, sell_price, args.exec_quality_threshold_pct, args.exec_pause_sec)
                                            executed = True
                                        else:
                                            _log(f"下单结果: {order.state} {order.reason or ''}")
                                    except Exception as e:
                                        _log(f"下单异常: {e}")
                                else:
                                    _log("无该币种持仓，未下单")

    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="OKX：涨卖跌买（盈利硬约束 + 三秒确认 + 市价保护）")
    parser.add_argument("--symbol", default="BTC/USDT", help="交易对")
    parser.add_argument("--ratio", type=float, default=0.5, help="触发比例%%")
    parser.add_argument("--interval", type=float, default=0, help="轮询间隔秒")
    parser.add_argument("--taker-fee-rate", type=float, default=0.001, help="吃单费率")
    parser.add_argument("--buy-amount-usdt", type=float, default=50.0, help="每次买入固定 USDT")
    parser.add_argument("--min-buy-usdt", type=float, default=10.0, help="低于此金额(USDT)不下单")
    parser.add_argument("--max-slippage", type=float, default=MAX_SLIPPAGE, help="市价保护：价差上限")
    parser.add_argument("--cooldown-sec", type=float, default=COOLDOWN_SEC_DEFAULT, help="同币种两次下单最小间隔(秒)")
    parser.add_argument("--sell-fee-compensation-pct", type=float, default=SELL_FEE_COMP_PCT_DEFAULT, help="上一笔买入后卖出时额外触发比例%%(手续费补偿)")
    parser.add_argument("--empty-rebase-up-pct", type=float, default=1.0, help="空仓时若价格较参考价上涨超过此%%，则上调参考价避免一直等旧低点；0 表示关闭")
    parser.add_argument("--exec-quality-threshold-pct", type=float, default=EXEC_QUALITY_THRESHOLD_PCT, help="成交价与下单时均价偏差超此%%计为不良")
    parser.add_argument("--exec-pause-sec", type=float, default=EXEC_PAUSE_SEC_DEFAULT, help="连续3次不良后自动暂停秒数")
    return parser


def main():
    args = build_parser().parse_args()
    while True:
        code = run_once(args)
        if code != 0 or args.interval <= 0:
            return code
        _log(f"{args.interval} 秒后再次检查...")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
