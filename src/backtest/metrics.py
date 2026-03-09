"""
回测指标：收益曲线、最大回撤、夏普、胜率、交易次数等。
"""
from typing import Dict, Any

import pandas as pd
import numpy as np


def compute_metrics(
    equity_curve: pd.DataFrame,
    initial_cash: float,
    trades: pd.DataFrame,
    risk_free_rate: float = 0.02,
) -> Dict[str, Any]:
    if equity_curve is None or equity_curve.empty:
        return {}
    eq = equity_curve["equity"]
    returns = eq.pct_change().dropna()
    total_return = (eq.iloc[-1] / initial_cash - 1) if initial_cash > 0 else 0
    # 最大回撤
    cummax = eq.cummax()
    drawdown = (eq - cummax) / cummax.replace(0, np.nan)
    max_drawdown = drawdown.min() if not drawdown.empty else 0
    # 年化与夏普（按日频近似）
    if len(returns) > 0 and returns.std() > 0:
        ann_return = (1 + total_return) ** (252 / max(len(returns), 1)) - 1
        sharpe = (returns.mean() - risk_free_rate / 252) / returns.std() * np.sqrt(252)
    else:
        ann_return = total_return
        sharpe = 0.0
    # 交易统计
    if trades is not None and not trades.empty and "side" in trades.columns:
        buys = trades[trades["side"] == "buy"]
        sells = trades[trades["side"] == "sell"]
        n_trades = len(buys) + len(sells)
        if "pnl" in trades.columns:
            win_trades = (trades["pnl"] > 0).sum()
            loss_trades = (trades["pnl"] < 0).sum()
        else:
            win_trades = 0
            loss_trades = 0
        closed_trades = win_trades + loss_trades
        win_rate = win_trades / closed_trades if closed_trades else 0.0
    else:
        n_trades = 0
        win_rate = 0.0
    return {
        "total_return": total_return,
        "annualized_return": ann_return,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe,
        "n_trades": n_trades,
        "win_rate": win_rate,
        "final_equity": float(eq.iloc[-1]) if len(eq) else initial_cash,
    }
