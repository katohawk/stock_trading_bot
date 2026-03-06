"""
双均线策略：短期均线上穿长期均线做多，下穿做空/平仓。
只输出信号，不直接下单。
"""
from typing import Optional

import pandas as pd

from .base import StrategyBase, Signal, SignalDirection


class DualMAStrategy(StrategyBase):
    def __init__(self, short_window: int = 5, long_window: int = 20):
        self.short_window = short_window
        self.long_window = long_window

    def get_params(self) -> dict:
        return {"short_window": self.short_window, "long_window": self.long_window}

    def next(
        self,
        symbol: str,
        bar: pd.Series,
        history: pd.DataFrame,
        context: dict,
    ) -> Optional[Signal]:
        if history is None or len(history) < self.long_window:
            return None
        close = history["close"]
        short_ma = close.rolling(self.short_window).mean()
        long_ma = close.rolling(self.long_window).mean()
        # 当前 bar 的索引对应最新
        s = short_ma.iloc[-1]
        l = long_ma.iloc[-1]
        s_prev = short_ma.iloc[-2]
        l_prev = long_ma.iloc[-2]
        dt = history.index[-1]
        price = float(bar["close"])
        # 上穿：做多
        if s_prev <= l_prev and s > l:
            return Signal(
                symbol=symbol,
                direction=SignalDirection.LONG,
                weight=1.0,
                datetime=dt,
                price=price,
                reason=f"dual_ma_cross_up s={s:.2f} l={l:.2f}",
            )
        # 下穿：平仓
        if s_prev >= l_prev and s < l:
            return Signal(
                symbol=symbol,
                direction=SignalDirection.FLAT,
                weight=0.0,
                datetime=dt,
                price=price,
                reason=f"dual_ma_cross_down s={s:.2f} l={l:.2f}",
            )
        return None
