"""
回测引擎：按时间顺序推进，用当时可见数据算信号 -> 风控 -> 模拟成交。
含手续费、滑点，输出收益曲线与指标。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd

from ..strategy.base import StrategyBase, Signal, SignalDirection
from ..risk.risk_manager import RiskManager, RiskConfig, AccountState, PositionState

from .metrics import compute_metrics


@dataclass
class BacktestConfig:
    initial_cash: float = 1_000_000.0
    commission_rate: float = 0.0003  # 万三
    slippage_pct: float = 0.001  # 0.1%
    risk_config: Optional[RiskConfig] = None


class BacktestEngine:
    def __init__(
        self,
        strategy: StrategyBase,
        config: BacktestConfig,
        risk_config: Optional[RiskConfig] = None,
    ):
        self.strategy = strategy
        self.config = config
        self.risk = RiskManager(risk_config or config.risk_config or RiskConfig())
        self.equity_curve: List[tuple] = []
        self.trades: List[dict] = []

    def run(
        self,
        data: pd.DataFrame,
        symbol: str,
    ) -> Dict[str, Any]:
        """
        单标的回测。data 为 DataFrame，索引为 datetime，列含 open/high/low/close/volume。
        """
        cash = self.config.initial_cash
        positions: Dict[str, PositionState] = {}
        self.equity_curve = []
        self.trades = []
        daily_pnl = 0.0
        start_of_day_equity = cash
        daily_trade_count = 0
        last_date = None
        consecutive_loss_days = 0

        def rollover_day(next_date: str, current_equity: float) -> None:
            nonlocal last_date, consecutive_loss_days, daily_pnl, daily_trade_count, start_of_day_equity
            if last_date is not None and daily_pnl < 0:
                consecutive_loss_days += 1
            elif last_date is not None:
                consecutive_loss_days = 0
            start_of_day_equity = current_equity
            daily_pnl = 0.0
            daily_trade_count = 0
            last_date = next_date

        for i in range(len(data)):
            if i == 0:
                continue
            history = data.iloc[: i + 1]
            bar = data.iloc[i]
            dt = data.index[i]
            if hasattr(dt, "date"):
                current_date = dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10]
            else:
                current_date = str(dt)[:10]

            if last_date is None:
                last_date = current_date
            elif last_date != current_date:
                prev_price = float(data.iloc[i - 1]["close"])
                prev_pos_value = sum(
                    p.quantity * (prev_price if p.symbol == symbol else p.current_price)
                    for p in positions.values()
                )
                rollover_day(current_date, cash + prev_pos_value)

            # 当前价格（用 close 模拟）
            price = float(bar["close"])
            current_prices = {symbol: price}
            pos_value = sum(p.quantity * current_prices.get(p.symbol, p.current_price) for p in positions.values())
            equity = cash + pos_value
            daily_pnl = equity - start_of_day_equity
            account = AccountState(
                cash=cash,
                positions=dict(positions),
                equity=equity,
                daily_pnl=daily_pnl,
                daily_trade_count=daily_trade_count,
                consecutive_loss_days=consecutive_loss_days,
                last_trading_date=current_date,
            )
            # 更新持仓的 current_price
            for p in account.positions.values():
                p.current_price = current_prices.get(p.symbol, p.current_price)

            # 风控：止损/止盈
            for sig in self.risk.check_stop_loss(account, current_prices):
                if sig.symbol in positions:
                    pos = positions.pop(sig.symbol)
                    fill_price = price * (1 - self.config.slippage_pct)
                    commission = pos.quantity * fill_price * self.config.commission_rate
                    realized_pnl = pos.quantity * (fill_price - pos.avg_cost) - commission
                    cash += pos.quantity * fill_price - commission
                    daily_pnl += realized_pnl
                    self.trades.append({"datetime": dt, "symbol": sig.symbol, "side": "sell", "qty": pos.quantity, "price": fill_price, "commission": commission, "pnl": realized_pnl, "reason": sig.reason})
                    daily_trade_count += 1

            # 策略信号（只用当前 bar 之前的数据，避免前视）
            context = {"cash": cash, "equity": equity, "positions": dict(positions)}
            signal = self.strategy.next(symbol, bar, history.iloc[:-1], context)
            if signal:
                signal = self.risk.apply(signal, account, current_prices)
            if signal:
                if signal.direction == SignalDirection.LONG:
                    # 按目标仓位处理：target_value = weight * equity，与当前持仓的差额用于下单
                    target_value = signal.weight * equity
                    current_value = positions[symbol].quantity * price if symbol in positions else 0.0
                    delta_value = target_value - current_value
                    if delta_value > 1e-6:  # 加仓
                        cost = min(delta_value, cash)
                        if cost > 0:
                            qty = cost / (price * (1 + self.config.slippage_pct))
                            commission = cost * self.config.commission_rate
                            fill_price = price * (1 + self.config.slippage_pct)
                            cash -= cost + commission
                            if symbol in positions:
                                pos = positions[symbol]
                                total_qty = pos.quantity + qty
                                new_avg = (pos.quantity * pos.avg_cost + qty * fill_price) / total_qty
                                positions[symbol] = PositionState(symbol=symbol, quantity=total_qty, avg_cost=new_avg, current_price=price, opened_at=pos.opened_at)
                            else:
                                positions[symbol] = PositionState(symbol=symbol, quantity=qty, avg_cost=fill_price, current_price=price, opened_at=dt)
                            daily_trade_count += 1
                            self.trades.append({"datetime": dt, "symbol": symbol, "side": "buy", "qty": qty, "price": fill_price, "commission": commission, "reason": signal.reason})
                    elif delta_value < -1e-6 and symbol in positions:  # 减仓
                        pos = positions[symbol]
                        sell_value = min(-delta_value, pos.quantity * price)
                        sell_qty = sell_value / (price * (1 - self.config.slippage_pct))
                        sell_qty = min(sell_qty, pos.quantity)
                        if sell_qty > 0:
                            fill_price = price * (1 - self.config.slippage_pct)
                            commission = sell_qty * fill_price * self.config.commission_rate
                            realized_pnl = sell_qty * (fill_price - pos.avg_cost) - commission
                            cash += sell_qty * fill_price - commission
                            daily_pnl += realized_pnl
                            if sell_qty >= pos.quantity:
                                del positions[symbol]
                            else:
                                positions[symbol] = PositionState(symbol=symbol, quantity=pos.quantity - sell_qty, avg_cost=pos.avg_cost, current_price=price, opened_at=pos.opened_at)
                            daily_trade_count += 1
                            self.trades.append({"datetime": dt, "symbol": symbol, "side": "sell", "qty": sell_qty, "price": fill_price, "commission": commission, "pnl": realized_pnl, "reason": signal.reason})
                elif signal.direction == SignalDirection.FLAT and symbol in positions:
                    pos = positions.pop(symbol)
                    fill_price = price * (1 - self.config.slippage_pct)
                    commission = pos.quantity * fill_price * self.config.commission_rate
                    realized_pnl = pos.quantity * (fill_price - pos.avg_cost) - commission
                    cash += pos.quantity * fill_price - commission
                    daily_pnl += realized_pnl
                    self.trades.append({"datetime": dt, "symbol": symbol, "side": "sell", "qty": pos.quantity, "price": fill_price, "commission": commission, "pnl": realized_pnl, "reason": signal.reason})
                    daily_trade_count += 1

            # 更新权益（策略可能改变了 cash/positions）
            pos_value = sum(p.quantity * current_prices.get(p.symbol, p.current_price) for p in positions.values())
            equity = cash + pos_value
            daily_pnl = equity - start_of_day_equity

            self.equity_curve.append((dt, equity))

        # 最后平掉所有仓
        for sym, pos in list(positions.items()):
            price = float(data.iloc[-1]["close"]) * (1 - self.config.slippage_pct)
            commission = pos.quantity * price * self.config.commission_rate
            realized_pnl = pos.quantity * (price - pos.avg_cost) - commission
            cash += pos.quantity * price - commission
            self.trades.append({"datetime": data.index[-1], "symbol": sym, "side": "sell", "qty": pos.quantity, "price": price, "commission": commission, "pnl": realized_pnl, "reason": "close"})
        final_equity = cash

        equity_df = pd.DataFrame(self.equity_curve, columns=["datetime", "equity"]).set_index("datetime")
        trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()
        metrics = compute_metrics(equity_df, self.config.initial_cash, trades_df)
        return {
            "equity_curve": equity_df,
            "trades": trades_df,
            "final_equity": final_equity,
            "metrics": metrics,
        }
