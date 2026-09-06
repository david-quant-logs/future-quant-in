from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from dataclasses import replace

from localbt import (
    FQ001Spec,
    FQ002Spec,
    FQ003Spec,
    SPEC,
    SPEC_FQ002,
    SPEC_FQ003,
    PRODUCT_MULT,
    PRODUCT_TICK,
)
from localbt.fetch import annualized_roll


@dataclass
class Trade:
    date: pd.Timestamp
    contract: str
    action: str
    direction: int
    price: float
    lots: int
    cash_flow: float
    reason: str


@dataclass
class BacktestResult:
    equity: pd.Series
    positions: pd.Series
    trades: list[Trade]
    daily: pd.DataFrame
    spec: FQ001Spec | FQ002Spec | FQ003Spec = field(default_factory=FQ001Spec)
    bankrupt: bool = False
    margin_skips: int = 0
    stops: int = 0
    rolls: int = 0


@dataclass(frozen=True)
class FQ002Signal:
    """T-1 carry for the next session. `as_of` is the last complete bar, not today."""

    as_of: pd.Timestamp
    contract: str
    far_contract: str
    roll: float | None
    target: int
    last_close: float | None


@dataclass(frozen=True)
class FQ003Signal:
    """T-1 basis-momentum for the next session. `as_of` is the last complete bar."""

    as_of: pd.Timestamp
    contract: str
    far_contract: str
    bm: float | None
    target: int
    last_close: float | None


def run_fq001(
    bars: pd.DataFrame,
    dominant: pd.Series,
    spec: FQ001Spec = SPEC,
    *,
    start: str | None = None,
    end: str | None = None,
) -> BacktestResult:
    """Daily TSMOM on the live dominant corn contract. Signal uses T-1 close, fill at T open."""
    panel = _index_bars(bars)
    dates = _trading_dates(dominant, start, end)
    cash = spec.start_cash
    direction = 0
    lots = 0
    entry = 0.0
    held = None
    cooldown = 0
    bars_held = 0
    entry_hold = spec.hold_bars
    bankrupt = False
    margin_skips = 0
    stops = 0
    rolls = 0
    trades: list[Trade] = []
    equity_rows: list[dict] = []

    for i, day in enumerate(dates):
        if bankrupt:
            equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
            continue

        contract = str(dominant.loc[day])
        row = _bar(panel, contract, day)
        if row is None:
            equity_rows.append(_row(day, cash, direction, lots, held, 0.0, cash, 0))
            continue

        open_px = float(row["open"])
        close_px = float(row["close"])

        if held and held != contract:
            old = _bar(panel, held, day)
            exit_px = float(old["open"]) if old is not None else _last_close(panel, held, day)
            cash, trades = _close(
                day, held, direction, lots, entry, exit_px, cash, spec, trades, "roll"
            )
            rolls += 1
            direction, lots, entry, held = 0, 0, 0.0, contract
            bars_held = 0

        mark_open = open_px if held == contract else close_px
        unreal_open = _unreal(direction, lots, entry, mark_open, spec)
        equity_open = cash + unreal_open

        if cooldown > 0:
            if lots:
                cash, trades = _close(
                    day, contract, direction, lots, entry, open_px, cash, spec, trades, "cooldown"
                )
                direction, lots, entry = 0, 0, 0.0
            cooldown -= 1
            bars_held = 0
            held = contract
            equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
            continue

        if lots and equity_open > 0 and unreal_open < -spec.stop_frac * equity_open:
            cash, trades = _close(
                day, contract, direction, lots, entry, open_px, cash, spec, trades, "stop"
            )
            direction, lots, entry = 0, 0, 0.0
            cooldown = spec.cooldown_bars
            bars_held = 0
            stops += 1
            held = contract
            if cash <= 0:
                bankrupt = True
            equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
            continue

        signal = _signal(panel, contract, dates, i, spec.lookback)
        slow = _signal(panel, contract, dates, i, spec.confirm_lookback) if spec.confirm_lookback else None
        regime = _regime(signal, slow)
        target, hold_need = _regime_target(panel, contract, dates, i, spec, signal, slow, regime)
        # Hold length is frozen at entry. Recomputing it from today's regime
        # would cut a 20-day bull hold as soon as the market turns choppy.
        # Optional: still flatten when both windows have turned down.
        allow = lots == 0 or bars_held >= entry_hold or (
            spec.flatten_on_bear and regime == "bear" and lots > 0
        )
        if not allow:
            bars_held += 1
        else:
            if target != direction or (target != 0 and lots == 0):
                if lots:
                    cash, trades = _close(
                        day, contract, direction, lots, entry, open_px, cash, spec, trades, "signal"
                    )
                    direction, lots, entry = 0, 0, 0.0
                    bars_held = 0
                if cash <= 0:
                    bankrupt = True
                    held = contract
                    equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
                    continue
                if target != 0:
                    opened = _open(day, contract, target, spec.lots, open_px, cash, spec, trades)
                    if opened is None:
                        margin_skips += 1
                    else:
                        cash, direction, lots, entry, trades = opened
                        bars_held = 1
                        entry_hold = hold_need
            elif lots:
                bars_held = 1
                entry_hold = hold_need

        held = contract
        unreal_close = _unreal(direction, lots, entry, close_px, spec)
        equity = cash + unreal_close
        if equity <= 0:
            if lots:
                cash, trades = _close(
                    day, contract, direction, lots, entry, close_px, cash, spec, trades, "bust"
                )
                direction, lots, entry = 0, 0, 0.0
            bankrupt = True
            equity = cash
        equity_rows.append(
            _row(day, cash, direction, lots, held, unreal_close, equity, signal)
        )

    daily = pd.DataFrame(equity_rows).set_index("date")
    return _result(daily, trades, spec, bankrupt, margin_skips, stops, rolls)


def run_fq002(
    bars: pd.DataFrame,
    dominant: pd.Series,
    nxt: pd.Series,
    spec: FQ002Spec,
    *,
    start: str | None = None,
    end: str | None = None,
) -> BacktestResult:
    """Time-series carry on the dominant contract. Roll uses T-1 closes of T-1's curve."""
    panel = _index_bars(bars)
    dates = _trading_dates(dominant, start, end)
    cash = spec.start_cash
    direction = 0
    lots = 0
    entry = 0.0
    held = None
    cooldown = 0
    bars_held = 0
    entry_hold = spec.hold_bars
    bankrupt = False
    margin_skips = 0
    stops = 0
    rolls = 0
    trades: list[Trade] = []
    equity_rows: list[dict] = []

    for i, day in enumerate(dates):
        if bankrupt:
            equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
            continue

        contract = str(dominant.loc[day])
        row = _bar(panel, contract, day)
        if row is None:
            equity_rows.append(_row(day, cash, direction, lots, held, 0.0, cash, 0))
            continue

        open_px = float(row["open"])
        close_px = float(row["close"])

        if held and held != contract:
            old = _bar(panel, held, day)
            exit_px = float(old["open"]) if old is not None else _last_close(panel, held, day)
            cash, trades = _close(
                day, held, direction, lots, entry, exit_px, cash, spec, trades, "roll"
            )
            rolls += 1
            direction, lots, entry, held = 0, 0, 0.0, contract
            bars_held = 0

        mark_open = open_px if held == contract else close_px
        unreal_open = _unreal(direction, lots, entry, mark_open, spec)
        equity_open = cash + unreal_open

        if cooldown > 0:
            if lots:
                cash, trades = _close(
                    day, contract, direction, lots, entry, open_px, cash, spec, trades, "cooldown"
                )
                direction, lots, entry = 0, 0, 0.0
            cooldown -= 1
            bars_held = 0
            held = contract
            equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
            continue

        if lots and equity_open > 0 and unreal_open < -spec.stop_frac * equity_open:
            cash, trades = _close(
                day, contract, direction, lots, entry, open_px, cash, spec, trades, "stop"
            )
            direction, lots, entry = 0, 0, 0.0
            cooldown = spec.cooldown_bars
            bars_held = 0
            stops += 1
            held = contract
            if cash <= 0:
                bankrupt = True
            equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
            continue

        roll = _carry_signal(panel, dominant, nxt, dates, i, spec.underlying)
        target = _carry_target(roll, spec)
        allow = lots == 0 or bars_held >= entry_hold or (
            spec.flatten_on_contango and lots > 0 and target == 0
        )
        if not allow:
            bars_held += 1
        else:
            if target != direction or (target != 0 and lots == 0):
                if lots:
                    cash, trades = _close(
                        day, contract, direction, lots, entry, open_px, cash, spec, trades, "signal"
                    )
                    direction, lots, entry = 0, 0, 0.0
                    bars_held = 0
                if cash <= 0:
                    bankrupt = True
                    held = contract
                    equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
                    continue
                if target != 0:
                    opened = _open(day, contract, target, spec.lots, open_px, cash, spec, trades)
                    if opened is None:
                        margin_skips += 1
                    else:
                        cash, direction, lots, entry, trades = opened
                        bars_held = 1
                        entry_hold = spec.hold_bars
            elif lots:
                bars_held = 1
                entry_hold = spec.hold_bars

        held = contract
        unreal_close = _unreal(direction, lots, entry, close_px, spec)
        equity = cash + unreal_close
        if equity <= 0:
            if lots:
                cash, trades = _close(
                    day, contract, direction, lots, entry, close_px, cash, spec, trades, "bust"
                )
                direction, lots, entry = 0, 0, 0.0
            bankrupt = True
            equity = cash
        equity_rows.append(
            _row(day, cash, direction, lots, held, unreal_close, equity, roll if roll is not None else 0.0)
        )

    daily = pd.DataFrame(equity_rows).set_index("date")
    return _result(daily, trades, spec, bankrupt, margin_skips, stops, rolls)


def latest_fq002_signal(
    bars: pd.DataFrame,
    dominant: pd.Series,
    nxt: pd.Series,
    spec: FQ002Spec | None = None,
) -> FQ002Signal:
    """Roll and target for the *next* session, using the last complete bar as T-1.

    Does not use a same-day close that has not finished. Contract is the last
    known dominant (live OI for today is unknown before the session).
    """
    spec = spec or SPEC_FQ002
    panel = _index_bars(bars)
    dates = _trading_dates(dominant, None, None)
    if len(dates) < 1:
        raise ValueError("没有主力映射，无法计算 FQ-002 信号")
    prev = dates[-1]
    if prev not in dominant.index or prev not in nxt.index:
        raise ValueError(f"{prev.date()} 缺少主力或次近月")
    near = str(dominant.loc[prev])
    far = str(nxt.loc[prev])
    near_row = _bar(panel, near, prev)
    far_row = _bar(panel, far, prev)
    roll = None
    last_close = None
    if near_row is not None and far_row is not None:
        last_close = float(near_row["close"])
        roll = annualized_roll(
            float(near_row["close"]),
            float(far_row["close"]),
            near,
            far,
            spec.underlying,
        )
    return FQ002Signal(
        as_of=prev,
        contract=near,
        far_contract=far,
        roll=roll,
        target=_carry_target(roll, spec),
        last_close=last_close,
    )


def run_fq003(
    bars: pd.DataFrame,
    dominant: pd.Series,
    nxt: pd.Series,
    spec: FQ003Spec,
    *,
    start: str | None = None,
    end: str | None = None,
) -> BacktestResult:
    """Time-series basis-momentum on the dominant contract. Signal uses overnight-held legs through T-1."""
    panel = _index_bars(bars)
    all_dates = _trading_dates(dominant, None, None)
    dates = _trading_dates(dominant, start, end)
    near_rets = _leg_returns(panel, dominant, all_dates)
    far_rets = _leg_returns(panel, nxt, all_dates)
    loc = {pd.Timestamp(d): i for i, d in enumerate(all_dates)}
    cash = spec.start_cash
    direction = 0
    lots = 0
    entry = 0.0
    held = None
    cooldown = 0
    bars_held = 0
    entry_hold = spec.hold_bars
    bankrupt = False
    margin_skips = 0
    stops = 0
    rolls = 0
    trades: list[Trade] = []
    equity_rows: list[dict] = []

    for day in dates:
        if bankrupt:
            equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
            continue

        contract = str(dominant.loc[day])
        row = _bar(panel, contract, day)
        if row is None:
            equity_rows.append(_row(day, cash, direction, lots, held, 0.0, cash, 0))
            continue

        open_px = float(row["open"])
        close_px = float(row["close"])

        if held and held != contract:
            old = _bar(panel, held, day)
            exit_px = float(old["open"]) if old is not None else _last_close(panel, held, day)
            cash, trades = _close(
                day, held, direction, lots, entry, exit_px, cash, spec, trades, "roll"
            )
            rolls += 1
            direction, lots, entry, held = 0, 0, 0.0, contract
            bars_held = 0

        mark_open = open_px if held == contract else close_px
        unreal_open = _unreal(direction, lots, entry, mark_open, spec)
        equity_open = cash + unreal_open

        if cooldown > 0:
            if lots:
                cash, trades = _close(
                    day, contract, direction, lots, entry, open_px, cash, spec, trades, "cooldown"
                )
                direction, lots, entry = 0, 0, 0.0
            cooldown -= 1
            bars_held = 0
            held = contract
            equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
            continue

        if lots and equity_open > 0 and unreal_open < -spec.stop_frac * equity_open:
            cash, trades = _close(
                day, contract, direction, lots, entry, open_px, cash, spec, trades, "stop"
            )
            direction, lots, entry = 0, 0, 0.0
            cooldown = spec.cooldown_bars
            bars_held = 0
            stops += 1
            held = contract
            if cash <= 0:
                bankrupt = True
            equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
            continue

        i = loc.get(pd.Timestamp(day))
        bm = _bm_at(near_rets, far_rets, i, spec.lookback) if i is not None else None
        target = _bm_target(bm, spec)
        allow = lots == 0 or bars_held >= entry_hold or (
            spec.flatten_on_negative_bm and lots > 0 and target == 0
        )
        if not allow:
            bars_held += 1
        else:
            if target != direction or (target != 0 and lots == 0):
                if lots:
                    cash, trades = _close(
                        day, contract, direction, lots, entry, open_px, cash, spec, trades, "signal"
                    )
                    direction, lots, entry = 0, 0, 0.0
                    bars_held = 0
                if cash <= 0:
                    bankrupt = True
                    held = contract
                    equity_rows.append(_row(day, cash, 0, 0, held, 0.0, cash, 0))
                    continue
                if target != 0:
                    opened = _open(day, contract, target, spec.lots, open_px, cash, spec, trades)
                    if opened is None:
                        margin_skips += 1
                    else:
                        cash, direction, lots, entry, trades = opened
                        bars_held = 1
                        entry_hold = spec.hold_bars
            elif lots:
                bars_held = 1
                entry_hold = spec.hold_bars

        held = contract
        unreal_close = _unreal(direction, lots, entry, close_px, spec)
        equity = cash + unreal_close
        if equity <= 0:
            if lots:
                cash, trades = _close(
                    day, contract, direction, lots, entry, close_px, cash, spec, trades, "bust"
                )
                direction, lots, entry = 0, 0, 0.0
            bankrupt = True
            equity = cash
        equity_rows.append(
            _row(day, cash, direction, lots, held, unreal_close, equity, bm if bm is not None else 0.0)
        )

    daily = pd.DataFrame(equity_rows).set_index("date")
    return _result(daily, trades, spec, bankrupt, margin_skips, stops, rolls)


def latest_fq003_signal(
    bars: pd.DataFrame,
    dominant: pd.Series,
    nxt: pd.Series,
    spec: FQ003Spec | None = None,
) -> FQ003Signal:
    """Basis-momentum and target for the *next* session, using complete bars only."""
    spec = spec or SPEC_FQ003
    panel = _index_bars(bars)
    dates = _trading_dates(dominant, None, None)
    if len(dates) < 2:
        raise ValueError("没有足够的主力映射，无法计算 FQ-003 信号")
    near_rets = _leg_returns(panel, dominant, dates)
    far_rets = _leg_returns(panel, nxt, dates)
    prev = dates[-1]
    bm = _bm_at(near_rets, far_rets, len(dates) - 1, spec.lookback)
    near = str(dominant.loc[prev])
    far = str(nxt.loc[prev]) if prev in nxt.index else ""
    near_row = _bar(panel, near, prev)
    last_close = float(near_row["close"]) if near_row is not None else None
    return FQ003Signal(
        as_of=prev,
        contract=near,
        far_contract=far,
        bm=bm,
        target=_bm_target(bm, spec),
        last_close=last_close,
    )


def run_fq001_rotate(
    book: dict[str, tuple[pd.DataFrame, pd.Series]],
    spec: FQ001Spec = SPEC,
    *,
    start: str | None = None,
    end: str | None = None,
) -> BacktestResult:
    """1-lot rotation: hold the universe member with the strongest lookback return (long-only default)."""
    panels = {p: _index_bars(bars) for p, (bars, _dom) in book.items()}
    dominants = {p: dom for p, (_bars, dom) in book.items()}
    dates = _shared_dates(dominants, start, end)
    cash = spec.start_cash
    direction = 0
    lots = 0
    entry = 0.0
    held_contract = None
    held_product = None
    cooldown = 0
    bars_held = 0
    bankrupt = False
    margin_skips = 0
    stops = 0
    rolls = 0
    trades: list[Trade] = []
    equity_rows: list[dict] = []

    for i, day in enumerate(dates):
        if bankrupt:
            equity_rows.append(_row(day, cash, 0, 0, held_contract, 0.0, cash, 0))
            continue

        if held_product and held_contract:
            live = _live(spec, held_product)
            today_dom = str(dominants[held_product].loc[day]) if day in dominants[held_product].index else None
            if today_dom and today_dom != held_contract and lots:
                old = _bar(panels[held_product], held_contract, day)
                exit_px = float(old["open"]) if old is not None else _last_close(panels[held_product], held_contract, day)
                cash, trades = _close(day, held_contract, direction, lots, entry, exit_px, cash, live, trades, "roll")
                rolls += 1
                direction, lots, entry = 0, 0, 0.0
                held_contract = today_dom
                bars_held = 0

        mark_spec = _live(spec, held_product) if held_product else spec
        mark_row = None
        if held_product and held_contract:
            mark_row = _bar(panels[held_product], held_contract, day)
        mark_open = float(mark_row["open"]) if mark_row is not None else 0.0
        unreal_open = _unreal(direction, lots, entry, mark_open, mark_spec) if mark_row is not None else 0.0
        equity_open = cash + unreal_open

        if cooldown > 0:
            if lots and held_product and held_contract and mark_row is not None:
                cash, trades = _close(
                    day, held_contract, direction, lots, entry, mark_open, cash, mark_spec, trades, "cooldown"
                )
                direction, lots, entry = 0, 0, 0.0
            cooldown -= 1
            bars_held = 0
            equity_rows.append(_row(day, cash, 0, 0, held_contract, 0.0, cash, 0))
            continue

        if lots and equity_open > 0 and unreal_open < -spec.stop_frac * equity_open and mark_row is not None:
            cash, trades = _close(
                day, held_contract, direction, lots, entry, mark_open, cash, mark_spec, trades, "stop"
            )
            direction, lots, entry = 0, 0, 0.0
            cooldown = spec.cooldown_bars
            bars_held = 0
            stops += 1
            if cash <= 0:
                bankrupt = True
            equity_rows.append(_row(day, cash, 0, 0, held_contract, 0.0, cash, 0))
            continue

        scores = _score_universe(book, panels, dominants, dates, i, spec)
        best_product, best_signal = _best_long(scores, spec)
        allow = lots == 0 or bars_held >= spec.hold_bars

        if not allow:
            bars_held += 1
        else:
            target_dir = 1 if best_product else 0
            switch = (best_product != held_product) or (target_dir != direction) or (target_dir != 0 and lots == 0)
            if switch:
                if lots and held_product and held_contract:
                    px = mark_open if mark_row is not None else _last_close(panels[held_product], held_contract, day)
                    cash, trades = _close(
                        day, held_contract, direction, lots, entry, px, cash, mark_spec, trades, "signal"
                    )
                    direction, lots, entry = 0, 0, 0.0
                    bars_held = 0
                if cash <= 0:
                    bankrupt = True
                    equity_rows.append(_row(day, cash, 0, 0, held_contract, 0.0, cash, 0))
                    continue
                if best_product:
                    new_contract = str(dominants[best_product].loc[day])
                    new_row = _bar(panels[best_product], new_contract, day)
                    if new_row is None:
                        margin_skips += 1
                    else:
                        opened = _open(
                            day,
                            new_contract,
                            1,
                            spec.lots,
                            float(new_row["open"]),
                            cash,
                            _live(spec, best_product),
                            trades,
                        )
                        if opened is None:
                            margin_skips += 1
                            held_product, held_contract = None, None
                        else:
                            cash, direction, lots, entry, trades = opened
                            held_product, held_contract = best_product, new_contract
                            bars_held = 1
                else:
                    held_product, held_contract = None, None
            elif lots:
                bars_held = 1

        close_px = float(mark_row["close"]) if mark_row is not None else entry
        if held_product and held_contract:
            close_row = _bar(panels[held_product], held_contract, day)
            if close_row is not None:
                close_px = float(close_row["close"])
                mark_spec = _live(spec, held_product)
        unreal_close = _unreal(direction, lots, entry, close_px, mark_spec)
        equity = cash + unreal_close
        if equity <= 0:
            if lots and held_product and held_contract:
                cash, trades = _close(
                    day, held_contract, direction, lots, entry, close_px, cash, mark_spec, trades, "bust"
                )
                direction, lots, entry = 0, 0, 0.0
            bankrupt = True
            equity = cash
        equity_rows.append(
            _row(day, cash, direction, lots, held_contract, unreal_close, equity, best_signal)
        )

    daily = pd.DataFrame(equity_rows).set_index("date")
    return _result(daily, trades, spec, bankrupt, margin_skips, stops, rolls)


def _live(spec: FQ001Spec, product: str) -> FQ001Spec:
    return replace(
        spec,
        multiplier=PRODUCT_MULT[product],
        tick=PRODUCT_TICK[product],
        underlying=product,
    )


def _shared_dates(
    dominants: dict[str, pd.Series],
    start: str | None,
    end: str | None,
) -> list[pd.Timestamp]:
    idx = None
    for series in dominants.values():
        cur = pd.DatetimeIndex(pd.to_datetime(series.index)).sort_values()
        idx = cur if idx is None else idx.intersection(cur)
    if idx is None:
        return []
    if start:
        idx = idx[idx >= pd.Timestamp(start)]
    if end:
        idx = idx[idx <= pd.Timestamp(end)]
    return list(idx)


def _score_universe(book, panels, dominants, dates, i, spec) -> dict[str, float | None]:
    day = dates[i]
    out: dict[str, float | None] = {}
    for product in spec.universe:
        if product not in dominants or day not in dominants[product].index:
            out[product] = None
            continue
        contract = str(dominants[product].loc[day])
        out[product] = _signal(panels[product], contract, dates, i, spec.lookback)
    return out


def _best_long(scores: dict[str, float | None], spec: FQ001Spec) -> tuple[str | None, float | None]:
    ranked = [(p, s) for p, s in scores.items() if s is not None]
    if not ranked:
        return None, None
    product, signal = max(ranked, key=lambda x: x[1])
    if spec.long_only and signal <= spec.min_abs_return:
        return None, signal
    if not spec.long_only:
        product, signal = max(ranked, key=lambda x: abs(x[1]))
        if abs(signal) <= spec.min_abs_return:
            return None, signal
        return product, signal
    return product, signal


def _result(daily, trades, spec, bankrupt, margin_skips, stops, rolls) -> BacktestResult:
    return BacktestResult(
        equity=daily["equity"],
        positions=daily["direction"],
        trades=trades,
        daily=daily,
        spec=spec,
        bankrupt=bankrupt,
        margin_skips=margin_skips,
        stops=stops,
        rolls=rolls,
    )


def _index_bars(bars: pd.DataFrame) -> pd.DataFrame:
    work = bars.copy()
    work["date"] = pd.to_datetime(work["date"])
    return work.set_index(["contract", "date"]).sort_index()


def _trading_dates(dominant: pd.Series, start: str | None, end: str | None) -> list[pd.Timestamp]:
    idx = pd.DatetimeIndex(pd.to_datetime(dominant.index)).sort_values()
    if start:
        idx = idx[idx >= pd.Timestamp(start)]
    if end:
        idx = idx[idx <= pd.Timestamp(end)]
    return list(idx)


def _bar(panel: pd.DataFrame, contract: str, day: pd.Timestamp) -> pd.Series | None:
    key = (contract, pd.Timestamp(day))
    if key not in panel.index:
        return None
    return panel.loc[key]


def _last_close(panel: pd.DataFrame, contract: str, day: pd.Timestamp) -> float:
    block = panel.loc[contract]
    block = block[block.index < pd.Timestamp(day)]
    if block.empty:
        raise RuntimeError(f"No prior close for {contract} before {day.date()}")
    return float(block["close"].iloc[-1])


def _signal(
    panel: pd.DataFrame,
    contract: str,
    dates: list[pd.Timestamp],
    i: int,
    lookback: int,
) -> float | None:
    """Past lookback-day simple return using only bars that have already closed (dates[:i])."""
    if i < 1:
        return None
    if contract not in panel.index.get_level_values(0):
        return None
    block = panel.loc[contract]
    closed_through = dates[i - 1]
    hist = block[block.index <= closed_through]["close"].dropna()
    if len(hist) < lookback + 1:
        return None
    old = float(hist.iloc[-(lookback + 1)])
    last = float(hist.iloc[-1])
    if old == 0:
        return None
    return last / old - 1.0


def _target(signal: float | None, spec: FQ001Spec) -> int:
    if signal is None:
        return 0
    if abs(signal) < spec.min_abs_return:
        return 0
    signed = int(np.sign(signal))
    if spec.long_only and signed < 0:
        return 0
    return signed


def _regime(fast: float | None, slow: float | None) -> str | None:
    if fast is None or slow is None:
        return None
    if fast > 0 and slow > 0:
        return "bull"
    if fast < 0 and slow < 0:
        return "bear"
    return "chop"


def _regime_target(panel, contract, dates, i, spec, fast, slow, regime) -> tuple[int, int]:
    """Return (target direction, hold bars to apply)."""
    if not spec.regime_switch:
        if spec.confirm_lookback and spec.long_only:
            if fast is None or slow is None:
                return 0, spec.hold_bars
            if fast <= 0 or slow <= 0:
                return 0, spec.hold_bars
        return _target(fast, spec), spec.hold_bars
    if regime == "bull":
        return 1, spec.hold_bars
    if regime == "bear":
        return 0, spec.hold_bars
    if regime == "chop" and spec.chop_reversion:
        z = _ma_z(panel, contract, dates, i, window=spec.lookback)
        if z is None:
            return 0, spec.chop_hold_bars
        # Fade dips only. Corn shorts already failed in v1; fading rallies
        # on a 10k 1-lot book is a switch, not a hedge.
        if z <= -spec.chop_z:
            return 1, spec.chop_hold_bars
        return 0, spec.chop_hold_bars
    return 0, spec.hold_bars


def _ma_z(panel, contract, dates, i, window: int = 20) -> float | None:
    if i < 1 or contract not in panel.index.get_level_values(0):
        return None
    block = panel.loc[contract]
    hist = block[block.index <= dates[i - 1]]
    if len(hist) < window + 1:
        return None
    closes = hist["close"].astype(float)
    highs = hist["high"].astype(float)
    lows = hist["low"].astype(float)
    prev = closes.shift(1)
    tr = pd.concat(
        [(highs - lows).abs(), (highs - prev).abs(), (lows - prev).abs()],
        axis=1,
    ).max(axis=1)
    atr = float(tr.iloc[-window:].mean())
    ma = float(closes.iloc[-window:].mean())
    last = float(closes.iloc[-1])
    if atr <= 0:
        return None
    return (last - ma) / atr


def _carry_signal(panel, dominant, nxt, dates, i, product: str) -> float | None:
    if i < 1:
        return None
    prev = dates[i - 1]
    if prev not in dominant.index or prev not in nxt.index:
        return None
    near = str(dominant.loc[prev])
    far = str(nxt.loc[prev])
    near_row = _bar(panel, near, prev)
    far_row = _bar(panel, far, prev)
    if near_row is None or far_row is None:
        return None
    return annualized_roll(
        float(near_row["close"]),
        float(far_row["close"]),
        near,
        far,
        product,
    )


def _carry_target(roll: float | None, spec: FQ002Spec) -> int:
    if roll is None:
        return 0
    if roll > spec.min_ann_roll:
        return 1
    if not spec.long_only and roll < -spec.min_ann_roll:
        return -1
    return 0


def _overnight_return(
    panel: pd.DataFrame,
    cmap: pd.Series,
    prev: pd.Timestamp,
    today: pd.Timestamp,
) -> float | None:
    if prev not in cmap.index:
        return None
    held = str(cmap.loc[prev])
    a = _bar(panel, held, prev)
    b = _bar(panel, held, today)
    if a is None or b is None:
        return None
    pa = float(a["close"])
    pb = float(b["close"])
    if pa <= 0 or pb <= 0:
        return None
    return pb / pa - 1.0


def _leg_returns(
    panel: pd.DataFrame,
    cmap: pd.Series,
    dates: list[pd.Timestamp],
) -> list[float | None]:
    out: list[float | None] = [None]
    for i in range(1, len(dates)):
        out.append(_overnight_return(panel, cmap, dates[i - 1], dates[i]))
    return out


def _compound_minus_one(rets: list[float]) -> float:
    x = 1.0
    for r in rets:
        x *= 1.0 + r
    return x - 1.0


def _bm_at(
    near_rets: list[float | None],
    far_rets: list[float | None],
    i: int,
    lookback: int,
) -> float | None:
    """BM for trading on dates[i], using overnight returns through dates[i-1]."""
    if i < lookback + 1:
        return None
    nwin = near_rets[i - lookback : i]
    fwin = far_rets[i - lookback : i]
    if any(r is None for r in nwin) or any(r is None for r in fwin):
        return None
    return _compound_minus_one([float(r) for r in nwin]) - _compound_minus_one(
        [float(r) for r in fwin]
    )


def _bm_target(bm: float | None, spec: FQ003Spec) -> int:
    if bm is None:
        return 0
    if bm > spec.min_bm:
        return 1
    if not spec.long_only and bm < -spec.min_bm:
        return -1
    return 0


def _unreal(direction: int, lots: int, entry: float, mark: float, spec: FQ001Spec) -> float:
    if direction == 0 or lots == 0:
        return 0.0
    return direction * (mark - entry) * spec.multiplier * lots


def _slip(direction: int, raw: float, spec: FQ001Spec, *, opening: bool) -> float:
    # Buy when opening a long or closing a short; sell otherwise.
    buying = (opening and direction > 0) or ((not opening) and direction < 0)
    delta = spec.slippage_ticks * spec.tick
    return raw + delta if buying else raw - delta


def _commission(price: float, lots: int, spec: FQ001Spec) -> float:
    return spec.commission_rate * price * spec.multiplier * lots


def _close(
    day: pd.Timestamp,
    contract: str,
    direction: int,
    lots: int,
    entry: float,
    raw_price: float,
    cash: float,
    spec: FQ001Spec,
    trades: list[Trade],
    reason: str,
) -> tuple[float, list[Trade]]:
    if direction == 0 or lots == 0:
        return cash, trades
    px = _slip(direction, raw_price, spec, opening=False)
    pnl = direction * (px - entry) * spec.multiplier * lots
    fee = _commission(px, lots, spec)
    cash = cash + pnl - fee
    trades.append(
        Trade(day, contract, "close", direction, px, lots, pnl - fee, reason)
    )
    return cash, trades


def _open(
    day: pd.Timestamp,
    contract: str,
    direction: int,
    lots: int,
    raw_price: float,
    cash: float,
    spec: FQ001Spec,
    trades: list[Trade],
) -> tuple[float, int, int, float, list[Trade]] | None:
    px = _slip(direction, raw_price, spec, opening=True)
    fee = _commission(px, lots, spec)
    margin = px * spec.multiplier * lots * spec.margin_rate
    if cash - fee < margin:
        return None
    cash = cash - fee
    trades.append(Trade(day, contract, "open", direction, px, lots, -fee, "signal"))
    return cash, direction, lots, px, trades


def _row(day, cash, direction, lots, held, unreal, equity, signal) -> dict:
    return {
        "date": pd.Timestamp(day),
        "cash": cash,
        "direction": direction,
        "lots": lots,
        "contract": held,
        "unreal": unreal,
        "equity": equity,
        "signal": signal,
    }
