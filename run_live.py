#!/usr/bin/env python3
"""
实盘/模拟盘入口：定时拉行情 -> 策略+风控 -> 执行层下单。
默认使用 SimulatedBroker 模拟盘；实盘需替换为真实券商实现。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datetime import datetime, timedelta

from src.data import AkShareAdapter, bars_to_dataframe
from src.strategy import DualMAStrategy
from src.strategy.base import SignalDirection
from src.risk import RiskManager, RiskConfig
from src.execution import SimulatedBroker, OrderSide


def main():
    symbol = "000001"
    adapter = AkShareAdapter(symbols=[symbol])
    end = datetime.now()
    start = end - timedelta(days=60)
    bars = adapter.get_bars(symbol, start, end, freq="1d")
    if not bars:
        print("无历史数据")
        return
    data = bars_to_dataframe(bars, symbol)

    strategy = DualMAStrategy(short_window=5, long_window=20)
    risk_config = RiskConfig(max_position_pct=0.25, stop_loss_pct=0.05)
    risk = RiskManager(risk_config)
    broker = SimulatedBroker(initial_cash=1_000_000.0, slippage_pct=0.001, commission_rate=0.0003)
    broker.set_prices({symbol: float(data.iloc[-1]["close"])})

    # 用最近一根 K 线生成信号
    bar = data.iloc[-1]
    history = data.iloc[:-1]
    account = broker.get_account()
    context = {"cash": account.cash, "equity": account.equity, "positions": account.positions}
    signal = strategy.next(symbol, bar, history, context)
    if signal:
        signal = risk.apply(signal, account, {symbol: float(bar["close"])})
    if not signal:
        print("无信号，不下单")
        return
    if signal.direction == SignalDirection.LONG:
        qty = int((signal.weight * account.equity) / (float(bar["close"]) * 100) * 100)  # 整手
        if qty > 0:
            order = broker.submit_order(symbol, OrderSide.BUY, qty, reason=signal.reason)
            print(f"模拟下单: {order.side} {order.filled_quantity} @ {order.filled_avg_price:.2f} state={order.state}")
    elif signal.direction == SignalDirection.FLAT:
        pos = account.positions.get(symbol)
        if pos and pos.quantity > 0:
            order = broker.submit_order(symbol, OrderSide.SELL, pos.quantity, reason=signal.reason)
            print(f"模拟平仓: {order.side} {order.filled_quantity} @ {order.filled_avg_price:.2f} state={order.state}")
    print("账户:", broker.get_account().equity)


if __name__ == "__main__":
    main()
