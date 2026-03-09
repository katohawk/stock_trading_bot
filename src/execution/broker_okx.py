"""
OKX（欧易）现货执行层：用 ccxt 连接 OKX，实现 BrokerBase。
需要 API Key + Secret + Passphrase（创建 API 时自己设的密码），资金在 OKX 即可自动化下单。
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..risk.risk_manager import AccountState, PositionState
from .order import Order, OrderState, OrderSide
from .broker_base import BrokerBase


def _ccxt_state_to_order_state(status: str) -> OrderState:
    s = (status or "").lower()
    if s in ("open", "pending", "live"):
        return OrderState.SUBMITTED
    if s in ("closed", "filled"):
        return OrderState.FILLED
    if s in ("canceled", "cancelled"):
        return OrderState.CANCELLED
    if s in ("rejected", "expired"):
        return OrderState.REJECTED
    return OrderState.PENDING


class OKXBroker(BrokerBase):
    """
    OKX 现货。初始化传入 api_key / api_secret / passphrase（建议环境变量）。
    Passphrase 为创建 API 时自己设置的密码，OKX 必填。
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self._exchange = None
        self._orders: Dict[str, Order] = {}

    def _get_exchange(self):
        if self._exchange is not None:
            return self._exchange
        import ccxt
        self._exchange = ccxt.okx({
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "password": self.passphrase,
        })
        # 避免 OKX 返回中 None 币种导致 ccxt parse_market 报错 (NoneType + str)
        self._exchange.options["loadMarkets"] = False
        self._apply_load_markets_fallback()
        return self._exchange

    def _apply_load_markets_fallback(self):
        """当 load_markets 因 OKX 返回 None 币种报错时，改为“不加载市场”并让 market(symbol) 返回最小占位。"""
        ex = self._exchange
        _original_load_markets = ex.load_markets
        _original_market = ex.market

        def _patched_load_markets():
            if getattr(ex, "_ccxt_okx_no_parse_markets", False):
                return
            try:
                _original_load_markets()
            except TypeError as e:
                if "NoneType" in str(e) and "str" in str(e):
                    ex.markets = {}
                    ex.markets_by_id = {}
                    ex._ccxt_okx_no_parse_markets = True
                else:
                    raise

        def _minimal_market(symbol: str) -> dict:
            parts = symbol.split("/") if "/" in symbol else (symbol, "USDT")
            base, quote = parts[0], parts[1] if len(parts) > 1 else "USDT"
            inst_id = base + "-" + quote
            return {
                "id": inst_id,
                "symbol": symbol,
                "base": base,
                "quote": quote,
                "spot": True,
                "contract": False,
                "precision": {"amount": 8, "price": 8},
            }

        def _patched_market(symbol: str):
            if getattr(ex, "_ccxt_okx_no_parse_markets", False):
                return _minimal_market(symbol)
            return _original_market(symbol)

        ex.load_markets = _patched_load_markets
        ex.market = _patched_market

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
        bal = None
        try:
            bal = ex.fetch_balance()
        except TypeError as e:
            err = str(e)
            if "NoneType" in err and "str" in err:
                try:
                    old_load = ex.options.get("loadMarkets")
                    ex.options["loadMarkets"] = False
                    bal = ex.fetch_balance()
                except Exception:
                    bal = self._fetch_balance_fallback(ex)
                    if bal and bal.get("total"):
                        ex.options["loadMarkets"] = False
                finally:
                    ex.options["loadMarkets"] = old_load
            else:
                raise
        if bal is None:
            bal = {"total": {}}
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

    def _fetch_balance_fallback(self, ex) -> dict:
        """当 fetch_balance 因 ccxt 解析 None 报错时，直接调 OKX 账户接口拿余额。"""
        try:
            # OKX v5: GET /api/v5/account/balance
            res = ex.private_get_account_balance()
            if res.get("code") != "0":
                return {"total": {}}
            data = res.get("data") or []
            if not data:
                return {"total": {}}
            details = (data[0] or {}).get("details") or []
            total = {}
            for d in details:
                ccy = (d.get("ccy") or "").strip().upper()
                if not ccy:
                    continue
                eq = float(d.get("eq") or d.get("cashBal") or d.get("availBal") or 0)
                if ccy not in total:
                    total[ccy] = 0.0
                total[ccy] += eq
            return {"total": total}
        except Exception:
            return {"total": {}}

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
