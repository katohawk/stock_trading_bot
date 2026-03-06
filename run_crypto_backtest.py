#!/usr/bin/env python3
"""
加密货币（如 BTC）网格策略回测：高抛低吸、快速周期。
数据源：优先 ccxt（Binance 等），若无则用 yfinance BTC-USD 日线演示。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datetime import datetime, timedelta

from src.data import bars_to_dataframe
from src.strategy import GridStrategy
from src.risk import RiskConfig
from src.backtest import BacktestEngine, BacktestConfig


def load_crypto_bars(symbol: str, start: datetime, end: datetime, freq: str):
    """优先 ccxt，失败则用 yfinance BTC-USD。"""
    try:
        from src.data import CryptoAdapter
        adapter = CryptoAdapter(exchange_id="binance", symbols=[symbol])
        return adapter.get_bars(symbol, start, end, freq=freq)
    except Exception as e:
        print(f"ccxt 不可用 ({e})，改用 yfinance BTC-USD 日线演示")
        import yfinance as yf
        # yfinance 用 BTC-USD，日线
        ticker = yf.Ticker("BTC-USD")
        df = ticker.history(start=start, end=end, interval="1d", auto_adjust=True)
        if df is None or df.empty:
            return []
        from src.data.models import Bar
        bars = []
        for ts, row in df.iterrows():
            dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            bars.append(Bar(symbol=symbol, datetime=dt, open=float(row["Open"]), high=float(row["High"]),
                           low=float(row["Low"]), close=float(row["Close"]), volume=float(row["Volume"])))
        return bars


def main():
    symbol = "BTC/USDT"
    end = datetime.now()
    start = end - timedelta(days=90)
    freq = "5m"

    print("拉取加密货币 K 线...")
    bars = load_crypto_bars(symbol, start, end, freq)
    if not bars:
        print("无数据")
        return
    data = bars_to_dataframe(bars, symbol)
    print(f"数据: {data.index[0]} ~ {data.index[-1]}, {len(data)} 根 K 线")

    low = float(data["low"].min())
    high = float(data["high"].max())
    grid_low = low * 0.98
    grid_high = high * 1.02
    print(f"网格区间: {grid_low:.0f} ~ {grid_high:.0f}")

    strategy = GridStrategy(grid_low=grid_low, grid_high=grid_high, num_grids=10)
    risk_config = RiskConfig(max_position_pct=1.0, max_total_position_pct=1.0, max_daily_trades=200)
    bt_config = BacktestConfig(initial_cash=100_000.0, commission_rate=0.001, slippage_pct=0.0005, risk_config=risk_config)
    engine = BacktestEngine(strategy=strategy, config=bt_config, risk_config=risk_config)
    result = engine.run(data, symbol)

    m = result["metrics"]
    print("\n--- 加密货币网格回测 ---")
    print(f"总收益: {m.get('total_return', 0):.2%}")
    print(f"最大回撤: {m.get('max_drawdown', 0):.2%}")
    print(f"交易次数: {m.get('n_trades', 0)}")
    print(f"期末权益: {result['final_equity']:.2f}")


if __name__ == "__main__":
    main()
