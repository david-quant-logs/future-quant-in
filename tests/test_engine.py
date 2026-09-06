from __future__ import annotations

import pandas as pd

from localbt import FQ001Spec
from localbt.engine import run_fq001


def _bars(closes: list[float], opens: list[float] | None = None) -> tuple[pd.DataFrame, pd.Series]:
    n = len(closes)
    dates = pd.bdate_range("2020-01-01", periods=n)
    opens = opens or [c * 0.999 for c in closes]
    rows = [
        {
            "date": dates[i],
            "contract": "C2005",
            "open": opens[i],
            "high": max(opens[i], closes[i]),
            "low": min(opens[i], closes[i]),
            "close": closes[i],
            "volume": 1000,
            "open_interest": 5000,
        }
        for i in range(n)
    ]
    bars = pd.DataFrame(rows)
    return bars, bars.set_index("date")["contract"]


def test_signal_does_not_use_same_day_close():
    # Slow grind up so lookback is long; last day close crashes, open is still high.
    closes = [1000 + i for i in range(40)] + [900]
    opens = [1000 + i for i in range(40)] + [1040]
    bars, dominant = _bars(closes, opens)
    spec = FQ001Spec(
        lookback=20,
        hold_bars=1,
        stop_frac=0.99,
        long_only=True,
        min_abs_return=0.0,
        start_cash=50_000,
        commission_rate=0.0,
        slippage_ticks=0,
    )
    result = run_fq001(bars, dominant, spec)
    last = result.daily.iloc[-1]
    assert last["direction"] == 1
    assert last["signal"] > 0


def test_stop_flattens_and_cools_down():
    # Strong uptrend then a gap down through 2% at the open.
    closes = [2000.0 + i for i in range(25)] + [2024.0, 1800.0, 1800.0, 1800.0]
    opens = [2000.0 + i for i in range(25)] + [2024.0, 1700.0, 1800.0, 1800.0]
    bars, dominant = _bars(closes, opens)
    spec = FQ001Spec(
        lookback=5,
        hold_bars=1,
        stop_frac=0.02,
        cooldown_bars=2,
        long_only=True,
        min_abs_return=0.0,
        start_cash=20_000,
        slippage_ticks=0,
    )
    result = run_fq001(bars, dominant, spec)
    assert result.stops >= 1
    stop_days = [t.date for t in result.trades if t.reason == "stop"]
    assert stop_days
    after = result.daily.loc[result.daily.index > stop_days[0]].head(2)
    assert (after["direction"] == 0).all()


def test_margin_skip_when_cash_too_small():
    closes = [2400 + i for i in range(30)]
    bars, dominant = _bars(closes)
    spec = FQ001Spec(lookback=5, hold_bars=1, min_abs_return=0.0, start_cash=100, margin_rate=0.12, lots=1)
    result = run_fq001(bars, dominant, spec)
    assert result.margin_skips >= 1
    assert int(result.positions.abs().sum()) == 0


def test_long_only_never_shorts():
    closes = [2000 - i for i in range(40)]
    bars, dominant = _bars(closes)
    spec = FQ001Spec(
        lookback=5,
        hold_bars=1,
        stop_frac=0.99,
        long_only=True,
        min_abs_return=0.0,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    result = run_fq001(bars, dominant, spec)
    assert int((result.positions < 0).sum()) == 0


def test_hold_bars_skips_daily_flips():
    closes = []
    px = 2000
    for _ in range(6):
        for _ in range(8):
            px += 15
            closes.append(px)
        for _ in range(8):
            px -= 15
            closes.append(px)
    bars, dominant = _bars(closes)
    daily = FQ001Spec(
        lookback=3,
        hold_bars=1,
        stop_frac=0.99,
        long_only=False,
        min_abs_return=0.0,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    held = FQ001Spec(
        lookback=3,
        hold_bars=8,
        stop_frac=0.99,
        long_only=False,
        min_abs_return=0.0,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    n_daily = sum(1 for t in run_fq001(bars, dominant, daily).trades if t.reason == "signal")
    n_held = sum(1 for t in run_fq001(bars, dominant, held).trades if t.reason == "signal")
    assert n_held <= n_daily
    held_days = int((run_fq001(bars, dominant, held).positions != 0).sum())
    daily_days = int((run_fq001(bars, dominant, daily).positions != 0).sum())
    assert held_days >= daily_days


def test_confirm_lookback_blocks_fast_only_long():
    # 20-day up, 60-day still down: long-only v3 should stay flat.
    closes = [2000 - i for i in range(50)] + [1940 + i for i in range(25)]
    bars, dominant = _bars(closes)
    spec = FQ001Spec(
        lookback=20,
        confirm_lookback=60,
        hold_bars=1,
        stop_frac=0.99,
        long_only=True,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    result = run_fq001(bars, dominant, spec)
    assert int((result.positions != 0).sum()) == 0


def test_chop_reversion_is_long_only():
    # Oscillate around a mean so 20d and 60d disagree, with a deep dip.
    closes = []
    px = 2000.0
    for i in range(90):
        px += 8 if (i // 7) % 2 == 0 else -9
        closes.append(px)
    bars, dominant = _bars(closes)
    spec = FQ001Spec(
        lookback=20,
        confirm_lookback=60,
        hold_bars=20,
        stop_frac=0.99,
        long_only=True,
        regime_switch=True,
        chop_reversion=True,
        chop_z=0.5,
        chop_hold_bars=5,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    result = run_fq001(bars, dominant, spec)
    assert int((result.positions < 0).sum()) == 0


def test_hold_length_frozen_at_entry():
    # Long grind higher, then a choppy drop. A 20-day bull hold must not
    # flatten just because today's regime flipped to chop.
    closes = [1800 + i * 4 for i in range(80)] + [2120 - (i % 6) * 8 for i in range(25)]
    bars, dominant = _bars(closes)
    spec = FQ001Spec(
        lookback=20,
        confirm_lookback=60,
        hold_bars=20,
        stop_frac=0.99,
        long_only=True,
        regime_switch=True,
        chop_reversion=False,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    result = run_fq001(bars, dominant, spec)
    long_days = int((result.positions > 0).sum())
    assert long_days >= 20


def test_flatten_on_bear_exits_before_hold_ends():
    up = [1800 + i * 5 for i in range(80)]
    down = [up[-1] - i * 25 for i in range(40)]
    closes = up + down
    bars, dominant = _bars(closes)
    kept = FQ001Spec(
        lookback=20,
        confirm_lookback=60,
        hold_bars=20,
        stop_frac=0.99,
        long_only=True,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    cut = FQ001Spec(
        lookback=20,
        confirm_lookback=60,
        hold_bars=20,
        stop_frac=0.99,
        long_only=True,
        flatten_on_bear=True,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
    )
    kept_days = int((run_fq001(bars, dominant, kept).positions != 0).sum())
    cut_days = int((run_fq001(bars, dominant, cut).positions != 0).sum())
    assert cut_days < kept_days


def test_rotate_picks_stronger_product():
    from localbt.engine import run_fq001_rotate

    dates = pd.bdate_range("2020-01-01", periods=50)
    weak = [2000 + i * 0.2 for i in range(50)]
    strong = [2000 + i * 8 for i in range(50)]

    def make(closes, contract):
        rows = [
            {
                "date": dates[i],
                "product": contract[0],
                "contract": contract,
                "open": closes[i] * 0.999,
                "high": closes[i],
                "low": closes[i] * 0.998,
                "close": closes[i],
                "volume": 1000,
                "open_interest": 5000,
            }
            for i in range(50)
        ]
        bars = pd.DataFrame(rows)
        return bars, bars.set_index("date")["contract"]

    spec = FQ001Spec(
        lookback=5,
        hold_bars=5,
        stop_frac=0.99,
        long_only=True,
        min_abs_return=0.0,
        start_cash=50_000,
        slippage_ticks=0,
        commission_rate=0.0,
        universe=("C", "M"),
        version="v3",
    )
    book = {"C": make(weak, "C2005"), "M": make(strong, "M2005")}
    result = run_fq001_rotate(book, spec)
    held = result.daily["contract"].dropna()
    assert (held == "M2005").sum() > (held == "C2005").sum()
