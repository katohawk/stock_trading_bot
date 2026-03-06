"""
实盘券商桩：对接真实券商 API 时的接口占位，便于同一套“信号->执行”逻辑切换。
实际对接时替换为 VN.py、Alpaca、盈透等。
"""
from typing import Dict, List, Optional

from ..risk.risk_manager import AccountState
from .order import Order, OrderSide
from .broker_base import BrokerBase


class LiveBrokerStub(BrokerBase):
    """
    实盘券商占位实现。真实使用时需：
    - 配置 API key / 证书（环境变量或配置文件）
    - 实现 submit_order -> 调用券商 REST/WebSocket 下单
    - 实现 get_order / sync_orders -> 轮询或推送订单状态
    - 实现 get_account -> 查询资金与持仓
    """

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url or "https://api.example.com"

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: Optional[float] = None,
        reason: str = "",
    ) -> Order:
        raise NotImplementedError(
            "实盘下单需对接券商 API。请替换为 VN.py、Alpaca、盈透等实现，或配置 LiveBroker 子类。"
        )

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("实盘撤单需对接券商 API。")

    def get_order(self, order_id: str) -> Optional[Order]:
        raise NotImplementedError("实盘查单需对接券商 API。")

    def get_account(self) -> AccountState:
        raise NotImplementedError("实盘查资金/持仓需对接券商 API。")

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        raise NotImplementedError("实盘未成交订单需对接券商 API。")

    def sync_orders(self) -> None:
        pass
