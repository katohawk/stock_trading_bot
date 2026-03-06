"""
执行层基类：策略+风控输出目标仓位/订单列表，执行层负责变成真实订单。
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from ..strategy.base import Signal
from ..risk.risk_manager import AccountState
from .order import Order, OrderSide


class BrokerBase(ABC):
    """券商/执行接口：回测用模拟实现，实盘用真实 API。"""

    @abstractmethod
    def submit_order(self, symbol: str, side: OrderSide, quantity: float, price: Optional[float] = None, reason: str = "") -> Order:
        """下单，返回订单对象（含 order_id）。"""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """撤单。"""
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """查询订单状态。"""
        pass

    @abstractmethod
    def get_account(self) -> AccountState:
        """获取账户状态（资金、持仓）。"""
        pass

    @abstractmethod
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """未完成订单列表。"""
        pass

    def sync_orders(self) -> None:
        """拉取最新订单状态（实盘需轮询券商）。"""
        pass
