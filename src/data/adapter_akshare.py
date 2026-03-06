"""
A 股历史 K 线：AkShare 适配器。
标的格式建议：000001.SZ / 600000.SH，或 000001、600000（自动补交易所）。
"""
from datetime import datetime
from typing import List

from .models import Bar
from .adapter_base import DataAdapterBase


class AkShareAdapter(DataAdapterBase):
    def __init__(self, symbols: List[str] | None = None):
        self.symbols = symbols or []

    def _normalize_symbol(self, symbol: str) -> str:
        """转为 AkShare 使用的格式：不带 .SZ/.SH 的 6 位代码。"""
        s = symbol.strip().upper()
        if "." in s:
            s = s.split(".")[0]
        return s

    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        freq: str = "1d",
    ) -> List[Bar]:
        import akshare as ak

        code = self._normalize_symbol(symbol)
        # AkShare 日线接口：stock_zh_a_hist(symbol, start_date, end_date, adjust="qfq")
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")

        if freq != "1d":
            # 分钟线可用 stock_zh_a_hist_min_em，这里仅实现日线
            raise NotImplementedError("AkShare 适配器当前仅支持日线 freq='1d'")

        df = ak.stock_zh_a_hist(symbol=code, start_date=start_str, end_date=end_str, adjust="qfq")
        if df is None or df.empty:
            return []

        # 列名：日期 开盘 收盘 最高 最低 成交量 ...
        df = df.rename(columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
        })
        bars = []
        for _, row in df.iterrows():
            dt = row["date"]
            if isinstance(dt, str):
                dt = datetime.strptime(dt[:10], "%Y-%m-%d")
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
