"""
币安现货执行层：用 ccxt 连接 Binance，实现 BrokerBase。
需要 API Key + Secret（只开现货交易、可勾选禁止提现），资金在币安即可自动化下单。
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..risk.risk_manager import AccountState, PositionState
from .order import Order, OrderState, OrderSide
from .broker_base import BrokerBase


def _ccxt_state_to_order_state(status: str) -> OrderState:
    s = (status or "").lower()
    if s in ("open", "pending"):
        return OrderState.SUBMITTED
    if s in ("closed", "filled"):
        return OrderState.FILLED
    if s in ("canceled", "cancelled"):
        return OrderState.CANCELLED
    if s in ("rejected", "expired"):
        return OrderState.REJECTED
    return OrderState.PENDING


class BinanceBroker(BrokerBase):
    """
    币安现货。初始化传入 api_key / api_secret（建议环境变量）。
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self._exchange = None
        self._orders: Dict[str, Order] = {}

    def _get_exchange(self):
        if self._exchange is not None:
            return self._exchange
        import ccxt
        self._exchange = ccxt.binance({
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "options": {"defaultType": "spot"},
        })
        if self.testnet:
            self._exchange.set_sandbox_mode(True)
        return self._exchange

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: Optional[float] = None,
        reason: str = "",
    ) -> Order:
        ex = self._get_exchange()
        order_type = "limit" if price is not None and price > 0 else "market"
        amount = quantity
        if amount <= 0:
            o = Order(order_id="", symbol=symbol, side=side, quantity=quantity, state=OrderState.REJECTED, reason="qty<=0")
            o.reason = reason or "qty<=0"
            return o
        try:
            result = ex.create_order(
                symbol=symbol,
                type=order_type,
                side=side.value,
                amount=amount,
                price=price,
                params={"newOrderRespType": "FULL"} if "binance" in ex.id else {},
            )
        except Exception as e:
            o = Order(order_id="", symbol=symbol, side=side, quantity=quantity, state=OrderState.REJECTED, reason=str(e))
            return o
        broker_id = result.get("id") or result.get("orderId") or ""
        filled = float(result.get("filled", 0) or 0)
        avg_price = float(result.get("average") or result.get("price") or 0)
        state = _ccxt_state_to_order_state(result.get("status"))
        o = Order(
            order_id=broker_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            state=state,
            filled_quantity=filled,
            filled_avg_price=avg_price,
            broker_order_id=broker_id,
            reason=reason,
        )
        self._orders[broker_id] = o
        return o

    def cancel_order(self, order_id: str) -> bool:
        if not order_id:
            return False
        o = self._orders.get(order_id)
        if o and o.symbol and not o.is_done():
            try:
                self._get_exchange().cancel_order(order_id, o.symbol)
                o.state = OrderState.CANCELLED
                return True
            except Exception:
                pass
        return False

    def get_order(self, order_id: str) -> Optional[Order]:
        if not order_id:
            return self._orders.get(order_id)
        o = self._orders.get(order_id)
        if o is None or o.is_done():
            return o
        try:
            ex = self._get_exchange()
            res = ex.fetch_order(order_id, o.symbol)
            o.state = _ccxt_state_to_order_state(res.get("status"))
            o.filled_quantity = float(res.get("filled", 0) or 0)
            o.filled_avg_price = float(res.get("average") or res.get("price") or 0)
        except Exception:
            pass
        return o

    def get_account(self) -> AccountState:
        ex = self._get_exchange()
        bal = ex.fetch_balance()
        cash = 0.0
        positions = {}
        totals = bal.get("total") or {}
        for c, data in totals.items():
            if c is None:
                continue
            total = float(data or 0)
            if total <= 0:
                continue
            c = str(c).upper()
            if c in ("USDT", "BUSD", "USD", "USDC"):
                cash += total
                continue
            try:
                pair = f"{c}/USDT"
                ticker = ex.fetch_ticker(pair)
                price = float(ticker.get("last") or ticker.get("close") or 0)
            except Exception:
                price = 0.0
            positions[pair] = PositionState(
                symbol=pair,
                quantity=total,
                avg_cost=price,
                current_price=price,
                opened_at=datetime.now(timezone.utc),
            )
        equity = cash + sum(p.quantity * p.current_price for p in positions.values())
        return AccountState(cash=cash, positions=positions, equity=equity)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        ex = self._get_exchange()
        try:
            raw = ex.fetch_open_orders(symbol) if symbol else ex.fetch_open_orders()
        except Exception:
            return []
        out = []
        for r in raw:
            oid = r.get("id") or r.get("orderId") or ""
            sym = r.get("symbol", "")
            side = OrderSide.BUY if (r.get("side") or "").lower() == "buy" else OrderSide.SELL
            amt = float(r.get("amount") or r.get("remaining") or 0)
            pr = float(r.get("price") or 0) or None
            o = Order(order_id=oid, symbol=sym, side=side, quantity=amt, price=pr, state=OrderState.SUBMITTED, broker_order_id=oid)
            self._orders[oid] = o
            out.append(o)
        return out

    def sync_orders(self) -> None:
        for oid, o in self._orders.items():
            if not o.is_done():
                self.get_order(oid)
