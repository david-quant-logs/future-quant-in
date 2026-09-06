from __future__ import annotations

import pandas as pd

from localbt.engine import BacktestResult


def yearly_returns(equity: pd.Series, start_cash: float) -> pd.Series:
    eq = equity.copy()
    eq.index = pd.to_datetime(eq.index)
    yearly = eq.resample("YE").last()
    out = yearly.pct_change()
    if len(yearly):
        out.iloc[0] = yearly.iloc[0] / start_cash - 1.0
    return out.dropna(how="all")


def stability(equity: pd.Series, start_cash: float) -> dict:
    yrs = yearly_returns(equity, start_cash).dropna()
    if yrs.empty:
        return {}
    total = float(equity.iloc[-1] / start_cash - 1.0)
    best = float(yrs.max())
    worst = float(yrs.min())
    contrib = best / total if total not in (0, 0.0) else float("nan")
    return {
        "year_count": int(len(yrs)),
        "year_mean": float(yrs.mean()),
        "year_std": float(yrs.std(ddof=1)) if len(yrs) > 1 else 0.0,
        "worst_year": worst,
        "best_year": best,
        "best_year_share_of_total": contrib,
        "positive_years": int((yrs > 0).sum()),
        "flat_or_down_years": int((yrs <= 0.02).sum()),
    }


def regime_pnl(result: BacktestResult) -> pd.DataFrame:
    """Split daily PnL by 20d/60d sign regime using the stored signal path on equity changes."""
    daily = result.daily.copy()
    daily.index = pd.to_datetime(daily.index)
    daily["pnl"] = daily["equity"].diff().fillna(0.0)
    return daily
