"""
风控层：仓位、止损、熔断。策略信号 -> 风控 -> 目标仓位/订单列表。
回测与实盘共用同一套规则。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from ..strategy.base import Signal, SignalDirection


@dataclass
class RiskConfig:
    """风控参数。"""

    max_position_pct: float = 0.25  # 单标的最大仓位比例
    max_total_position_pct: float = 1.0  # 总仓位上限
    max_daily_trades: int = 20  # 单日最大开仓次数
    stop_loss_pct: float = 0.05  # 止损比例，如 0.05 表示 -5%
    take_profit_pct: Optional[float] = 0.10  # 止盈比例，None 表示不设
    daily_loss_limit_pct: Optional[float] = 0.05  # 单日亏损熔断，如 -5%
    consecutive_loss_days_limit: int = 3  # 连续亏损 N 天则停止交易
    circuit_breaker: bool = True  # 是否启用熔断


@dataclass
class PositionState:
    """单标的持仓状态（供风控与回测使用）。"""

    symbol: str
    quantity: float
    avg_cost: float
    current_price: float
    opened_at: datetime

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def pnl_pct(self) -> float:
        if self.avg_cost <= 0:
            return 0.0
        return (self.current_price - self.avg_cost) / self.avg_cost


@dataclass
class AccountState:
    """账户状态（供风控判断）。"""

    cash: float
    positions: Dict[str, PositionState]
    equity: float  # 总权益
    daily_pnl: float = 0.0
    daily_trade_count: int = 0
    consecutive_loss_days: int = 0
    last_trading_date: Optional[str] = None  # YYYY-MM-DD


class RiskManager:
    def __init__(self, config: RiskConfig):
        self.config = config

    def apply(
        self,
        signal: Signal,
        account: AccountState,
        current_prices: Dict[str, float],
    ) -> Optional[Signal]:
        """
        对信号做风控过滤，返回通过后的信号或 None（拒绝/熔断）。
        """
        if not signal:
            return None
        # 熔断：单日亏损超限
        if self.config.circuit_breaker and self.config.daily_loss_limit_pct is not None:
            if account.equity > 0 and account.daily_pnl / account.equity <= -abs(self.config.daily_loss_limit_pct):
                return None
        # 熔断：连续亏损 N 天
        if self.config.circuit_breaker and account.consecutive_loss_days >= self.config.consecutive_loss_days_limit:
            return None
        # 单日开仓次数
        if signal.direction == SignalDirection.LONG and account.daily_trade_count >= self.config.max_daily_trades:
            return None
        # 单标仓位上限
        pos = account.positions.get(signal.symbol)
        pos_value = pos.market_value if pos else 0.0
        if signal.direction == SignalDirection.LONG:
            new_value = pos_value + (signal.weight * account.equity)
            if account.equity > 0 and new_value / account.equity > self.config.max_position_pct:
                signal = Signal(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    weight=self.config.max_position_pct - (pos_value / account.equity) if account.equity > 0 else 0,
                    datetime=signal.datetime,
                    price=signal.price,
                    reason=signal.reason + ";capped_by_risk",
                )
        # 总仓位上限
        total_pos = sum(p.market_value for p in account.positions.values())
        if signal.direction == SignalDirection.LONG and account.equity > 0:
            new_total = total_pos + signal.weight * account.equity
            if new_total / account.equity > self.config.max_total_position_pct:
                allowed = max(0, self.config.max_total_position_pct * account.equity - total_pos) / account.equity
                if allowed <= 0:
                    return None
                signal = Signal(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    weight=min(signal.weight, allowed),
                    datetime=signal.datetime,
                    price=signal.price,
                    reason=signal.reason + ";capped_total",
                )
        return signal

    def check_stop_loss(
        self,
        account: AccountState,
        current_prices: Dict[str, float],
    ) -> List[Signal]:
        """
        根据当前价格检查持仓是否触发止损/止盈，返回需平仓的信号列表。
        """
        out = []
        for symbol, pos in account.positions.items():
            price = current_prices.get(symbol, pos.current_price)
            pnl_pct = (price - pos.avg_cost) / pos.avg_cost if pos.avg_cost > 0 else 0
            # 止损
            if pnl_pct <= -abs(self.config.stop_loss_pct):
                out.append(
                    Signal(
                        symbol=symbol,
                        direction=SignalDirection.FLAT,
                        weight=0.0,
                        datetime=datetime.utcnow(),
                        price=price,
                        reason=f"stop_loss pnl_pct={pnl_pct:.2%}",
                    )
                )
            # 止盈
            if self.config.take_profit_pct is not None and pnl_pct >= self.config.take_profit_pct:
                out.append(
                    Signal(
                        symbol=symbol,
                        direction=SignalDirection.FLAT,
                        weight=0.0,
                        datetime=datetime.utcnow(),
                        price=price,
                        reason=f"take_profit pnl_pct={pnl_pct:.2%}",
                    )
                )
        return out
