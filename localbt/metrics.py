from __future__ import annotations

import math

import pandas as pd

from localbt.engine import BacktestResult

TRADING_DAYS = 242


def summarize(result: BacktestResult, *, oos_start: str | None = None) -> dict:
    equity = result.equity.dropna()
    stats = _window_stats(equity, result.spec.start_cash)
    stats.update(
        {
            "trades": _round_trips(result),
            "stops": result.stops,
            "rolls": result.rolls,
            "margin_skips": result.margin_skips,
            "bankrupt": result.bankrupt,
            "min_equity": float(equity.min()) if not equity.empty else math.nan,
            "max_equity": float(equity.max()) if not equity.empty else math.nan,
            "start": str(equity.index[0].date()) if len(equity) else "",
            "end": str(equity.index[-1].date()) if len(equity) else "",
            "bars": int(len(equity)),
        }
    )
    if oos_start and not equity.empty:
        oos = equity[equity.index >= pd.Timestamp(oos_start)]
        ins = equity[equity.index < pd.Timestamp(oos_start)]
        stats["in_sample"] = _window_stats(ins, result.spec.start_cash)
        stats["out_of_sample"] = _window_stats(oos, float(ins.iloc[-1]) if len(ins) else result.spec.start_cash)
        stats["oos_start"] = oos_start
    return stats


def _window_stats(equity: pd.Series, start_cash: float) -> dict:
    if equity.empty or start_cash <= 0:
        return {
            "total_return": math.nan,
            "ann_return": math.nan,
            "sharpe": math.nan,
            "max_drawdown": math.nan,
            "end_equity": math.nan,
        }
    rets = equity.pct_change().dropna()
    total = float(equity.iloc[-1] / start_cash - 1.0)
    years = max(len(equity) / TRADING_DAYS, 1e-9)
    ann = (1.0 + total) ** (1.0 / years) - 1.0 if equity.iloc[-1] > 0 else -1.0
    sharpe = math.nan
    if len(rets) > 2 and float(rets.std(ddof=1)) > 0:
        sharpe = float(rets.mean() / rets.std(ddof=1) * math.sqrt(TRADING_DAYS))
    dd = float((equity / equity.cummax() - 1.0).min())
    return {
        "total_return": total,
        "ann_return": ann,
        "sharpe": sharpe,
        "max_drawdown": dd,
        "end_equity": float(equity.iloc[-1]),
    }


def _round_trips(result: BacktestResult) -> int:
    return sum(1 for t in result.trades if t.action == "close")
