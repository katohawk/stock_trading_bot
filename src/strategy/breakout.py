"""
突破策略：价格突破过去 N 根 K 线最高做多，跌破最低平仓。
只输出信号，不直接下单。
"""
from typing import Optional

import pandas as pd

from .base import StrategyBase, Signal, SignalDirection


class BreakoutStrategy(StrategyBase):
    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def get_params(self) -> dict:
        return {"lookback": self.lookback}

    def next(
        self,
        symbol: str,
        bar: pd.Series,
        history: pd.DataFrame,
        context: dict,
    ) -> Optional[Signal]:
        if history is None or len(history) < self.lookback:
            return None
        high = history["high"].iloc[-self.lookback : -1].max()
        low = history["low"].iloc[-self.lookback : -1].min()
        dt = history.index[-1]
        close = float(bar["close"])
        # 突破前高做多
        if close > high:
            return Signal(
                symbol=symbol,
                direction=SignalDirection.LONG,
                weight=1.0,
                datetime=dt,
                price=close,
                reason=f"breakout_high close={close:.2f} high={high:.2f}",
            )
        # 跌破前低平仓
        if close < low:
            return Signal(
                symbol=symbol,
                direction=SignalDirection.FLAT,
                weight=0.0,
                datetime=dt,
                price=close,
                reason=f"breakout_low close={close:.2f} low={low:.2f}",
            )
        return None
