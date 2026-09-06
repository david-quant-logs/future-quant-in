from __future__ import annotations

import pandas as pd

from localbt import FQ003Spec
from localbt.engine import latest_fq003_signal, run_fq003
from localbt.fetch import build_dominant_map, build_next_map


def _two_legs(
    *,
    n: int = 40,
    near0: float = 2000.0,
    far0: float = 2000.0,
    near_step: float = 8.0,
    far_step: float = 1.0,
    last_near_close: float | None = None,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    dates = pd.bdate_range("2020-01-01", periods=n)
    rows = []
    near_px = near0
    far_px = far0
    for i, day in enumerate(dates):
        near_px = near0 + i * near_step
        far_px = far0 + i * far_step
        near_close = last_near_close if last_near_close is not None and i == n - 1 else near_px
        rows.append(
            {
                "date": day,
                "product": "MA",
                "contract": "MA2005",
                "open": near_px * 0.999,
                "high": max(near_px, near_close),
                "low": min(near_px, near_close) * 0.998,
                "close": near_close,
                "volume": 5000,
                "open_interest": 8000,
            }
        )
        rows.append(
            {
                "date": day,
                "product": "MA",
                "contract": "MA2009",
                "open": far_px * 0.999,
                "high": far_px,
                "low": far_px * 0.998,
                "close": far_px,
                "volume": 2000,
                "open_interest": 3000,
            }
        )
    bars = pd.DataFrame(rows)
    dominant = build_dominant_map(bars, "MA")
    nxt = build_next_map(bars, dominant, "MA")
    return bars, dominant, nxt


def _spec(**kwargs) -> FQ003Spec:
    base = dict(
        lookback=5,
        hold_bars=1,
        stop_frac=0.99,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    base.update(kwargs)
    return FQ003Spec(**base)


def test_positive_bm_goes_long():
    bars, dominant, nxt = _two_legs()
    result = run_fq003(bars, dominant, nxt, _spec())
    assert int((result.positions > 0).sum()) > 20
    assert int((result.positions < 0).sum()) == 0


def test_negative_bm_stays_flat_when_long_only():
    bars, dominant, nxt = _two_legs(near_step=1.0, far_step=8.0)
    result = run_fq003(bars, dominant, nxt, _spec())
    assert int((result.positions != 0).sum()) == 0


def test_signal_does_not_use_same_day_close():
    bars, dominant, nxt = _two_legs(last_near_close=1500.0)
    result = run_fq003(bars, dominant, nxt, _spec())
    last = result.daily.iloc[-1]
    assert last["direction"] == 1
    assert last["signal"] > 0


def test_warmup_has_no_position():
    bars, dominant, nxt = _two_legs(n=8)
    result = run_fq003(bars, dominant, nxt, _spec(lookback=5))
    # First valid BM needs lookback+1 overnight returns, so first 6 sessions stay flat.
    assert int((result.daily.iloc[:6]["direction"] != 0).sum()) == 0


def test_flatten_on_negative_bm_exits_before_hold_ends():
    dates = pd.bdate_range("2020-01-01", periods=40)
    rows = []
    near_px, far_px = 2000.0, 2000.0
    for i, day in enumerate(dates):
        if i < 18:
            near_px += 8
            far_px += 1
        else:
            near_px -= 6
            far_px += 4
        rows.append(
            {
                "date": day,
                "product": "MA",
                "contract": "MA2005",
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
                "product": "MA",
                "contract": "MA2009",
                "open": far_px * 0.999,
                "high": far_px,
                "low": far_px * 0.998,
                "close": far_px,
                "volume": 2000,
                "open_interest": 3000,
            }
        )
    bars = pd.DataFrame(rows)
    dominant = build_dominant_map(bars, "MA")
    nxt = build_next_map(bars, dominant, "MA")
    kept = _spec(lookback=5, hold_bars=20, flatten_on_negative_bm=False)
    cut = _spec(lookback=5, hold_bars=20, flatten_on_negative_bm=True, version="v3")
    kept_days = int((run_fq003(bars, dominant, nxt, kept).positions > 0).sum())
    cut_days = int((run_fq003(bars, dominant, nxt, cut).positions > 0).sum())
    assert cut_days < kept_days


def test_latest_signal_matches_last_bar():
    bars, dominant, nxt = _two_legs()
    spec = _spec()
    result = run_fq003(bars, dominant, nxt, spec)
    sig = latest_fq003_signal(bars, dominant, nxt, spec)
    last = result.daily.iloc[-1]
    assert sig.target == int(last["direction"])
    assert sig.bm is not None
    assert abs(float(sig.bm) - float(last["signal"])) < 1e-12
