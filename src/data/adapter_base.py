"""
数据适配器基类：不同数据源统一成 Bar 列表或 DataFrame。
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from .models import Bar


class DataAdapterBase(ABC):
    """数据适配器基类。"""

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        freq: str = "1d",
    ) -> List[Bar]:
        """
        拉取历史 K 线。
        :param symbol: 标的代码（如 000001.SZ、AAPL）
        :param start: 开始时间
        :param end: 结束时间
        :param freq: 周期，如 1d, 1h, 5m
        :return: Bar 列表，按时间升序
        """
        pass

    @abstractmethod
    def get_symbols_list(self) -> List[str]:
        """返回该数据源支持的标的列表或配置的标的池。"""
        pass
