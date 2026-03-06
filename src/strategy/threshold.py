"""
最简规则：按比例 + 间隔，涨了就卖、跌了就买。
- 当前价相对参考价涨了 ≥ ratio_pct → 建议卖
- 当前价相对参考价跌了 ≥ ratio_pct → 建议买
- 操作后（或首次）把参考价更新为当前价，便于定时监控重复使用。
"""
from typing import Optional

import pandas as pd

from .base import StrategyBase, Signal, SignalDirection


class SimpleThresholdStrategy(StrategyBase):
    """
    参数:
      ratio_pct: 触发比例，如 1.0 表示 1%，涨 1% 卖、跌 1% 买
      reference_price: 参考价；None 时用 history 最后一根 close 初始化
    """

    def __init__(self, ratio_pct: float = 1.0, reference_price: Optional[float] = None):
        if ratio_pct <= 0:
            raise ValueError("ratio_pct 应为正数")
        self.ratio_pct = ratio_pct
        self.ratio = ratio_pct / 100.0
        self.reference_price = reference_price

    def get_params(self) -> dict:
        return {"ratio_pct": self.ratio_pct, "reference_price": self.reference_price}

    def set_reference(self, price: float) -> None:
        """更新参考价（监控脚本在“建议”后调用，便于下次比较）。"""
        self.reference_price = price

    def next(
        self,
        symbol: str,
        bar: pd.Series,
        history: pd.DataFrame,
        context: dict,
    ) -> Optional[Signal]:
        if history is None or len(history) < 1:
            return None
        close = float(bar["close"])
        ref = self.reference_price
        if ref is None:
            ref = float(history["close"].iloc[-1])
            self.reference_price = ref
        dt = history.index[-1]

        if close >= ref * (1 + self.ratio):
            self.reference_price = close
            return Signal(
                symbol=symbol,
                direction=SignalDirection.FLAT,
                weight=0.0,
                datetime=dt,
                price=close,
                reason=f"threshold_sell up {self.ratio_pct}% ref={ref:.2f} now={close:.2f}",
            )
        if close <= ref * (1 - self.ratio):
            self.reference_price = close
            return Signal(
                symbol=symbol,
                direction=SignalDirection.LONG,
                weight=1.0,
                datetime=dt,
                price=close,
                reason=f"threshold_buy down {self.ratio_pct}% ref={ref:.2f} now={close:.2f}",
            )
        return None

    def recommend(self, current_price: float) -> tuple[str, Optional[SignalDirection], float]:
        """
        仅做推荐、不依赖 K 线：用当前价与 reference_price 比较。
        返回 (建议文案, 方向或 None, 新参考价)。
        """
        ref = self.reference_price
        if ref is None or ref <= 0:
            self.reference_price = current_price
            return ("暂无参考价，已记录当前价为参考", None, current_price)
        if current_price >= ref * (1 + self.ratio):
            self.reference_price = current_price
            return (
                f"涨了 ≥{self.ratio_pct}%，建议卖出（参考 {ref:.2f} -> 当前 {current_price:.2f}）",
                SignalDirection.FLAT,
                current_price,
            )
        if current_price <= ref * (1 - self.ratio):
            self.reference_price = current_price
            return (
                f"跌了 ≥{self.ratio_pct}%，建议买入（参考 {ref:.2f} -> 当前 {current_price:.2f}）",
                SignalDirection.LONG,
                current_price,
            )
        return ("涨跌未达比例，观望", None, ref)
