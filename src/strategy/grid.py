"""
网格策略（高抛低吸）：在价格区间内分档，跌穿某档买入、涨穿某档卖出。
适合震荡市、加密货币短线快速操作；仅输出信号，不直接下单。
"""
from typing import Optional

import pandas as pd

from .base import StrategyBase, Signal, SignalDirection


class GridStrategy(StrategyBase):
    def __init__(
        self,
        grid_low: float,
        grid_high: float,
        num_grids: int = 10,
    ):
        if grid_low >= grid_high or num_grids < 1:
            raise ValueError("grid_low < grid_high and num_grids >= 1")
        self.grid_low = grid_low
        self.grid_high = grid_high
        self.num_grids = num_grids
        self._levels = [
            grid_low + (grid_high - grid_low) * i / num_grids
            for i in range(num_grids + 1)
        ]

    def get_params(self) -> dict:
        return {
            "grid_low": self.grid_low,
            "grid_high": self.grid_high,
            "num_grids": self.num_grids,
        }

    def next(
        self,
        symbol: str,
        bar: pd.Series,
        history: pd.DataFrame,
        context: dict,
    ) -> Optional[Signal]:
        if history is None or len(history) < 1:
            return None
        prev_close = float(history["close"].iloc[-1])
        close = float(bar["close"])
        dt = history.index[-1]
        # 当前持仓权重（总持仓市值 / 权益）
        positions = context.get("positions") or {}
        equity = context.get("equity") or 1.0
        position_value = sum(
            getattr(p, "market_value", 0) if hasattr(p, "market_value") else 0
            for p in positions.values()
        )
        position_weight = position_value / equity if equity and equity > 0 else 0.0

        # 向下穿越档位：价格从档位上方跌到下方 -> 买
        n_down = sum(1 for L in self._levels if prev_close >= L > close)
        # 向上穿越档位：价格从档位下方涨到上方 -> 卖
        n_up = sum(1 for L in self._levels if prev_close <= L < close)

        if n_up > 0:
            return Signal(
                symbol=symbol,
                direction=SignalDirection.FLAT,
                weight=0.0,
                datetime=dt,
                price=close,
                reason=f"grid_sell n_up={n_up} levels",
            )
        if n_down > 0:
            add_weight = min(1.0 - position_weight, n_down / self.num_grids)
            if add_weight <= 0:
                return None
            return Signal(
                symbol=symbol,
                direction=SignalDirection.LONG,
                weight=position_weight + add_weight,
                datetime=dt,
                price=close,
                reason=f"grid_buy n_down={n_down} levels",
            )
        return None
