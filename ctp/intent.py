"""FQ-002-v2 daily order plan. Same allow/stop/hold rules as localbt.engine.run_fq002."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from localbt import FQ002Spec, SPEC_FQ002
from localbt.engine import FQ002Signal


@dataclass
class CtpFillState:
    as_of: str | None = None
    contract: str | None = None
    direction: int = 0
    lots: int = 0
    bars_held: int = 0
    entry: float = 0.0
    cooldown: int = 0
    equity: float = 10_000.0

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: dict | None) -> CtpFillState:
        if not raw:
            return cls()
        return cls(
            as_of=raw.get("as_of"),
            contract=raw.get("contract"),
            direction=int(raw.get("direction") or 0),
            lots=int(raw.get("lots") or 0),
            bars_held=int(raw.get("bars_held") or 0),
            entry=float(raw.get("entry") or 0.0),
            cooldown=int(raw.get("cooldown") or 0),
            equity=float(raw.get("equity") or 10_000.0),
        )


@dataclass(frozen=True)
class PlannedOrder:
    lab_contract: str
    direction: str
    offset: str
    volume: int
    reason: str


@dataclass(frozen=True)
class FQ002Plan:
    signal_as_of: str
    contract: str
    roll: float | None
    target: int
    allow: bool
    orders: tuple[PlannedOrder, ...]
    next_state: CtpFillState
    note: str


def plan_fq002(
    signal: FQ002Signal,
    state: CtpFillState,
    spec: FQ002Spec | None = None,
    *,
    mark: float | None = None,
) -> FQ002Plan:
    spec = spec or SPEC_FQ002
    px = float(mark if mark is not None else (signal.last_close or 0.0))
    direction = int(state.direction)
    lots = int(state.lots)
    entry = float(state.entry)
    held = state.contract
    bars_held = int(state.bars_held)
    cooldown = int(state.cooldown)
    equity = float(state.equity or spec.start_cash)
    contract = signal.contract
    target = int(signal.target)
    orders: list[PlannedOrder] = []
    as_of = str(pd_timestamp(signal.as_of))
    allow = False

    def flatten(reason: str) -> None:
        nonlocal direction, lots, entry, bars_held
        if lots and held:
            orders.append(_flatten_order(held, direction, lots, reason))
        direction, lots, entry, bars_held = 0, 0, 0.0, 0

    if cooldown > 0:
        flatten("cooldown")
        nxt = CtpFillState(
            as_of=as_of,
            contract=contract,
            cooldown=cooldown - 1,
            equity=equity,
        )
        return FQ002Plan(as_of, contract, signal.roll, target, False, tuple(orders), nxt, "cooldown")

    if lots and px > 0 and equity > 0:
        unreal = direction * (px - entry) * spec.multiplier * lots
        if unreal < -spec.stop_frac * equity:
            flatten("stop")
            nxt = CtpFillState(
                as_of=as_of,
                contract=contract,
                cooldown=spec.cooldown_bars,
                equity=equity,
            )
            return FQ002Plan(as_of, contract, signal.roll, target, True, tuple(orders), nxt, "stop")

    if held and held != contract and lots:
        flatten("roll")
        held = contract

    allow = lots == 0 or bars_held >= spec.hold_bars or (
        spec.flatten_on_contango and lots > 0 and target == 0
    )
    note = "hold window"
    if not allow:
        bars_held += 1
    else:
        if target != direction or (target != 0 and lots == 0):
            if lots:
                flatten("signal")
            if target != 0 and px > 0:
                orders.append(
                    PlannedOrder(
                        lab_contract=contract,
                        direction="long" if target > 0 else "short",
                        offset="open",
                        volume=spec.lots,
                        reason="signal",
                    )
                )
                direction, lots, entry, bars_held = target, spec.lots, px, 1
            note = "signal"
        elif lots:
            bars_held = 1
            note = "hold reset"

    nxt = CtpFillState(
        as_of=as_of,
        contract=contract,
        direction=direction,
        lots=lots,
        bars_held=bars_held,
        entry=entry,
        cooldown=0,
        equity=equity,
    )
    return FQ002Plan(as_of, contract, signal.roll, target, allow, tuple(orders), nxt, note)


def _flatten_order(contract: str, direction: int, lots: int, reason: str) -> PlannedOrder:
    return PlannedOrder(
        lab_contract=contract,
        direction="short" if direction > 0 else "long",
        offset="close",
        volume=lots,
        reason=reason,
    )


def pd_timestamp(value) -> str:
    text = str(value)
    return text[:10]
