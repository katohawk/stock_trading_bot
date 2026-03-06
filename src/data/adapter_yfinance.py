"""
美股（或 Yahoo 支持的标的）历史 K 线：yfinance 适配器。
"""
from datetime import datetime
from typing import List

import pandas as pd

from .models import Bar
from .adapter_base import DataAdapterBase


class YFinanceAdapter(DataAdapterBase):
    def __init__(self, symbols: List[str] | None = None):
        self.symbols = symbols or []

    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        freq: str = "1d",
    ) -> List[Bar]:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        # 映射：1d -> 1d, 1h -> 1h 等
        interval_map = {"1d": "1d", "1h": "1h", "5m": "5m", "1m": "1m"}
        interval = interval_map.get(freq, "1d")
        df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
        if df is None or df.empty:
            return []

        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        bars = []
        for ts, row in df.iterrows():
            if hasattr(ts, "to_pydatetime"):
                dt = ts.to_pydatetime()
            else:
                dt = ts
            bars.append(
                Bar(
                    symbol=symbol,
                    datetime=dt,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return bars

    def get_symbols_list(self) -> List[str]:
        return list(self.symbols)
