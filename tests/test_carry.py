from __future__ import annotations

import pandas as pd

from localbt import FQ002Spec
from localbt.engine import run_fq002
from localbt.fetch import annualized_roll, build_dominant_map, build_next_map, contract_month_index


def _two_contracts(*, near_px: float, far_px: float, n: int = 40) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    dates = pd.bdate_range("2020-01-01", periods=n)
    rows = []
    for day in dates:
        rows.append(
            {
                "date": day,
                "product": "M",
                "contract": "M2005",
                "open": near_px * 0.999,
                "high": near_px,
                "low": near_px * 0.998,
                "close": near_px,
                "volume": 5000,
                "open_interest": 8000,
            }
        )
        rows.append(
            {
                "date": day,
                "product": "M",
                "contract": "M2007",
                "open": far_px * 0.999,
                "high": far_px,
                "low": far_px * 0.998,
                "close": far_px,
                "volume": 2000,
                "open_interest": 3000,
            }
        )
    bars = pd.DataFrame(rows)
    dominant = build_dominant_map(bars, "M")
    nxt = build_next_map(bars, dominant, "M")
    return bars, dominant, nxt


def test_month_index_and_positive_roll():
    assert contract_month_index("M", "M2005") == 2020 * 12 + 5
    roll = annualized_roll(3100, 3000, "M2005", "M2007", "M")
    assert roll is not None and roll > 0


def test_next_map_picks_later_month():
    bars, dominant, nxt = _two_contracts(near_px=3100, far_px=3000)
    assert (dominant == "M2005").all()
    assert (nxt == "M2007").all()


def test_backwardation_goes_long():
    bars, dominant, nxt = _two_contracts(near_px=3100, far_px=3000)
    spec = FQ002Spec(
        hold_bars=1,
        stop_frac=0.99,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    result = run_fq002(bars, dominant, nxt, spec)
    assert int((result.positions > 0).sum()) > 20
    assert int((result.positions < 0).sum()) == 0


def test_contango_stays_flat_when_long_only():
    bars, dominant, nxt = _two_contracts(near_px=3000, far_px=3200)
    spec = FQ002Spec(
        hold_bars=1,
        stop_frac=0.99,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    result = run_fq002(bars, dominant, nxt, spec)
    assert int((result.positions != 0).sum()) == 0


def test_flatten_on_contango_exits_before_hold_ends():
    dates = pd.bdate_range("2020-01-01", periods=35)
    rows = []
    for i, day in enumerate(dates):
        near, far = (3100.0, 3000.0) if i < 18 else (3000.0, 3200.0)
        rows.append(
            {
                "date": day,
                "product": "M",
                "contract": "M2005",
                "open": near * 0.999,
                "high": near,
                "low": near * 0.998,
                "close": near,
                "volume": 5000,
                "open_interest": 8000,
            }
        )
        rows.append(
            {
                "date": day,
                "product": "M",
                "contract": "M2007",
                "open": far * 0.999,
                "high": far,
                "low": far * 0.998,
                "close": far,
                "volume": 2000,
                "open_interest": 3000,
            }
        )
    bars = pd.DataFrame(rows)
    dominant = build_dominant_map(bars, "M")
    nxt = build_next_map(bars, dominant, "M")
    kept = FQ002Spec(
        hold_bars=20,
        stop_frac=0.99,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
        flatten_on_contango=False,
    )
    cut = FQ002Spec(
        hold_bars=20,
        stop_frac=0.99,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
        flatten_on_contango=True,
        version="v2",
    )
    kept_days = int((run_fq002(bars, dominant, nxt, kept).positions > 0).sum())
    cut_days = int((run_fq002(bars, dominant, nxt, cut).positions > 0).sum())
    assert cut_days < kept_days
    tail = run_fq002(bars, dominant, nxt, cut).daily.iloc[-10:]
    assert int((tail["direction"] != 0).sum()) == 0


def test_roll_signal_does_not_use_same_day_close():
    dates = pd.bdate_range("2020-01-01", periods=25)
    rows = []
    for i, day in enumerate(dates):
        near = 3000.0
        far = 3200.0 if i < 24 else 2500.0
        rows.append(
            {
                "date": day,
                "product": "M",
                "contract": "M2005",
                "open": near * 0.999,
                "high": near,
                "low": near * 0.998,
                "close": near,
                "volume": 5000,
                "open_interest": 8000,
            }
        )
        rows.append(
            {
                "date": day,
                "product": "M",
                "contract": "M2007",
                "open": far * 0.999,
                "high": far,
                "low": far * 0.998,
                "close": far,
                "volume": 2000,
                "open_interest": 3000,
            }
        )
    bars = pd.DataFrame(rows)
    dominant = build_dominant_map(bars, "M")
    nxt = build_next_map(bars, dominant, "M")
    spec = FQ002Spec(
        hold_bars=1,
        stop_frac=0.99,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    result = run_fq002(bars, dominant, nxt, spec)
    assert int(result.daily.iloc[-1]["direction"]) == 0
