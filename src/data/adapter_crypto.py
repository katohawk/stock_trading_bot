"""
加密货币 K 线：通过 ccxt 拉取交易所历史数据（如 OKX）。
支持 1m/5m/15m/1h/1d，便于高抛低吸的快速周期。
"""
from datetime import datetime
from typing import List

from .models import Bar
from .adapter_base import DataAdapterBase


# ccxt 周期与交易所内部 interval 的常见映射
CCXT_TIMEFRAME_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


class CryptoAdapter(DataAdapterBase):
    """
    通过 ccxt 拉取加密货币 K 线。
    exchange_id: 如 'okx'
    symbol: 如 'BTC/USDT', 'ETH/USDT'
    """

    def __init__(
        self,
        exchange_id: str = "okx",
        symbols: List[str] | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
    ):
        self.exchange_id = exchange_id
        self.symbols = symbols or ["BTC/USDT"]
        self.api_key = api_key
        self.api_secret = api_secret
        self._exchange = None

    def _get_exchange(self):
        if self._exchange is not None:
            return self._exchange
        import ccxt
        exchange_class = getattr(ccxt, self.exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"ccxt 不支持的交易所: {self.exchange_id}")
        kwargs = {}
        if self.api_key:
            kwargs["apiKey"] = self.api_key
        if self.api_secret:
            kwargs["secret"] = self.api_secret
        self._exchange = exchange_class(**kwargs)
        return self._exchange

    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        freq: str = "5m",
    ) -> List[Bar]:
        timeframe = CCXT_TIMEFRAME_MAP.get(freq, "5m")
        exchange = self._get_exchange()
        since_ts = int(start.timestamp() * 1000)
        all_ohlcv = []
        while since_ts < int(end.timestamp() * 1000):
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ts, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since_ts = ohlcv[-1][0] + 1
            if len(ohlcv) < 1000:
                break
        bars = []
        for row in all_ohlcv:
            ts_ms, o, h, l, c, v = row[0], row[1], row[2], row[3], row[4], row[5]
            dt = datetime.utcfromtimestamp(ts_ms / 1000.0)
            if dt > end:
                break
            if dt >= start:
                bars.append(
                    Bar(
                        symbol=symbol,
                        datetime=dt,
                        open=float(o),
                        high=float(h),
                        low=float(l),
                        close=float(c),
                        volume=float(v),
                    )
                )
        return bars

    def get_symbols_list(self) -> List[str]:
        return list(self.symbols)
