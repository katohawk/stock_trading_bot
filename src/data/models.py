"""
统一 K 线 / Bar 结构，供回测与实盘共用。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd


@dataclass
class Bar:
    """单根 K 线（Bar）统一结构。"""

    symbol: str
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    # 可选：除权因子等
    adj_factor: Optional[float] = None

    def to_series(self) -> pd.Series:
        return pd.Series(
            {
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "close": self.close,
                "volume": self.volume,
            },
            name=self.datetime,
        )


def bars_to_dataframe(bars: list[Bar], symbol: str) -> pd.DataFrame:
    """将 Bar 列表转为统一 DataFrame，索引为 datetime。"""
    if not bars:
        return pd.DataFrame()
    rows = [
        {
            "symbol": b.symbol,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        }
        for b in bars
    ]
    df = pd.DataFrame(rows)
    df["datetime"] = [b.datetime for b in bars]
    df = df.set_index("datetime")
    return df


# 类型别名：多标的 Bar 序列，key 为 symbol
BarSeries = dict[str, pd.DataFrame]
