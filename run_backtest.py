#!/usr/bin/env python3
"""
回测入口：拉取历史数据 -> 策略+风控 -> 回测引擎 -> 输出指标与收益曲线。
"""
import sys
from pathlib import Path

# 保证项目根在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from datetime import datetime, timedelta
import pandas as pd

from src.data import AkShareAdapter, YFinanceAdapter, bars_to_dataframe
from src.strategy import DualMAStrategy, BreakoutStrategy
from src.risk import RiskManager, RiskConfig
from src.backtest import BacktestEngine, BacktestConfig, compute_metrics


def load_data(market: str, symbol: str, start: datetime, end: datetime):
    if market == "a":
        adapter = AkShareAdapter(symbols=[symbol])
        bars = adapter.get_bars(symbol, start, end, freq="1d")
    else:
        adapter = YFinanceAdapter(symbols=[symbol])
        bars = adapter.get_bars(symbol, start, end, freq="1d")
    if not bars:
        return None
    return bars_to_dataframe(bars, symbol)


def main():
    market = "a"
    symbol = "000001"
    end = datetime.now()
    start = end - timedelta(days=365 * 2)

    print("拉取数据...")
    data = load_data(market, symbol, start, end)
    if data is None or data.empty:
        print("无数据，请检查标的与时间范围")
        return
    print(f"数据范围: {data.index[0]} ~ {data.index[-1]}, {len(data)} 根K线")

    strategy = DualMAStrategy(short_window=5, long_window=20)
    risk_config = RiskConfig(
        max_position_pct=0.25,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
        daily_loss_limit_pct=0.05,
    )
    bt_config = BacktestConfig(
        initial_cash=1_000_000.0,
        commission_rate=0.0003,
        slippage_pct=0.001,
        risk_config=risk_config,
    )
    engine = BacktestEngine(strategy=strategy, config=bt_config, risk_config=risk_config)
    result = engine.run(data, symbol)

    m = result["metrics"]
    print("\n--- 回测结果 ---")
    print(f"总收益: {m.get('total_return', 0):.2%}")
    print(f"年化收益: {m.get('annualized_return', 0):.2%}")
    print(f"最大回撤: {m.get('max_drawdown', 0):.2%}")
    print(f"夏普比率: {m.get('sharpe_ratio', 0):.2f}")
    print(f"交易次数: {m.get('n_trades', 0)}")
    print(f"期末权益: {result['final_equity']:.2f}")
    if not result["trades"].empty:
        print("\n最近 5 笔交易:")
        print(result["trades"].tail().to_string())


if __name__ == "__main__":
    main()
