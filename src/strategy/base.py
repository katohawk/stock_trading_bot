"""
策略只输出信号（标的、方向、建议仓位比例），不直接下单。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

import pandas as pd


class SignalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"  # 平仓/空仓


@dataclass
class Signal:
    """单条交易信号。"""

    symbol: str
    direction: SignalDirection
    weight: float  # 建议仓位比例，0~1
    datetime: datetime
    price: float  # 触发时价格，供回测/实盘参考
    reason: str = ""
    valid_until: Optional[datetime] = None  # 可选有效期


class StrategyBase(ABC):
    @abstractmethod
    def next(
        self,
        symbol: str,
        bar: pd.Series,
        history: pd.DataFrame,
        context: dict,
    ) -> Optional[Signal]:
        """
        根据当前 bar 与历史数据生成信号（若有）。
        :param symbol: 标的
        :param bar: 当前 bar 的 Series（open/high/low/close/volume）
        :param history: 当前时刻之前的历史 DataFrame（含 datetime 索引）
        :param context: 策略可用的上下文（如当前仓位、资金等）
        :return: 若产生信号则返回 Signal，否则 None
        """
        pass

    def get_params(self) -> dict:
        """返回策略参数字典，便于回测调参与配置持久化。"""
        return {}
