"""
订单与状态机：已报 -> 部分成交 -> 完全成交/撤单/拒单。
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderState(str, Enum):
    PENDING = "pending"       # 待报
    SUBMITTED = "submitted"  # 已报
    PARTIAL = "partial"      # 部分成交
    FILLED = "filled"        # 完全成交
    CANCELLED = "cancelled"  # 已撤
    REJECTED = "rejected"    # 拒单


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    """订单。"""

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: Optional[float] = None  # None 表示市价
    state: OrderState = OrderState.PENDING
    filled_quantity: float = 0.0
    filled_avg_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    reason: str = ""
    broker_order_id: Optional[str] = None  # 券商返回的订单号

    def is_done(self) -> bool:
        return self.state in (OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED)
