"""
模拟券商：用于回测或本地模拟盘，订单立即按当前价成交（可加滑点）。
"""
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from ..risk.risk_manager import AccountState, PositionState
from .order import Order, OrderState, OrderSide
from .broker_base import BrokerBase


class SimulatedBroker(BrokerBase):
    def __init__(
        self,
        initial_cash: float = 1_000_000.0,
        slippage_pct: float = 0.001,
        commission_rate: float = 0.0003,
    ):
        self.cash = initial_cash
        self.positions: Dict[str, PositionState] = {}
        self.orders: Dict[str, Order] = {}
        self.slippage_pct = slippage_pct
        self.commission_rate = commission_rate
        self._prices: Dict[str, float] = {}  # 当前价格，由外部 set_prices 更新

    def set_prices(self, prices: Dict[str, float]) -> None:
        self._prices = dict(prices)

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: Optional[float] = None,
        reason: str = "",
    ) -> Order:
        order_id = str(uuid.uuid4())
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            reason=reason,
        )
        self.orders[order_id] = order
        # 模拟立即成交
        p = self._prices.get(symbol, price or 0)
        if p <= 0:
            order.state = OrderState.REJECTED
            return order
        if side == OrderSide.BUY:
            fill_price = p * (1 + self.slippage_pct)
            cost = quantity * fill_price * (1 + self.commission_rate)
            if cost <= self.cash:
                self.cash -= cost
                existing = self.positions.get(symbol)
                if existing:
                    total_qty = existing.quantity + quantity
                    new_avg = (existing.quantity * existing.avg_cost + quantity * fill_price) / total_qty
                    self.positions[symbol] = PositionState(
                        symbol=symbol,
                        quantity=total_qty,
                        avg_cost=new_avg,
                        current_price=p,
                        opened_at=existing.opened_at,
                    )
                else:
                    self.positions[symbol] = PositionState(
                        symbol=symbol,
                        quantity=quantity,
                        avg_cost=fill_price,
                        current_price=p,
                        opened_at=datetime.utcnow(),
                    )
                order.state = OrderState.FILLED
                order.filled_quantity = quantity
                order.filled_avg_price = fill_price
            else:
                order.state = OrderState.REJECTED
        else:
            fill_price = p * (1 - self.slippage_pct)
            pos = self.positions.get(symbol)
            if pos and pos.quantity >= quantity:
                self.cash += quantity * fill_price * (1 - self.commission_rate)
                if pos.quantity == quantity:
                    del self.positions[symbol]
                else:
                    self.positions[symbol] = PositionState(
                        symbol=symbol,
                        quantity=pos.quantity - quantity,
                        avg_cost=pos.avg_cost,
                        current_price=p,
                        opened_at=pos.opened_at,
                    )
                order.state = OrderState.FILLED
                order.filled_quantity = quantity
                order.filled_avg_price = fill_price
            else:
                order.state = OrderState.REJECTED
        order.updated_at = datetime.utcnow()
        return order

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self.orders and not self.orders[order_id].is_done():
            self.orders[order_id].state = OrderState.CANCELLED
            self.orders[order_id].updated_at = datetime.utcnow()
            return True
        return False

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)

    def get_account(self) -> AccountState:
        pos_value = sum(p.quantity * self._prices.get(p.symbol, p.current_price) for p in self.positions.values())
        for p in self.positions.values():
            p.current_price = self._prices.get(p.symbol, p.current_price)
        equity = self.cash + pos_value
        return AccountState(
            cash=self.cash,
            positions=dict(self.positions),
            equity=equity,
        )

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        out = [o for o in self.orders.values() if not o.is_done()]
        if symbol:
            out = [o for o in out if o.symbol == symbol]
        return out

    def sync_orders(self) -> None:
        pass
