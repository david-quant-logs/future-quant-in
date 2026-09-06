from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class FQ001Spec:
    lookback: int = 20
    hold_bars: int = 20
    lots: int = 1
    stop_frac: float = 0.08
    cooldown_bars: int = 5
    long_only: bool = True
    min_abs_return: float = 0.0
    start_cash: float = 10_000.0
    multiplier: float = 10.0
    tick: float = 1.0
    slippage_ticks: float = 1.0
    commission_rate: float = 0.0001
    margin_rate: float = 0.12
    underlying: str = "C"
    universe: tuple[str, ...] = ("C",)
    version: str = "v2"
    confirm_lookback: int = 0
    regime_switch: bool = False
    chop_reversion: bool = False
    chop_z: float = 1.5
    chop_hold_bars: int = 5
    flatten_on_bear: bool = False


SPEC_V1 = FQ001Spec(
    hold_bars=1,
    stop_frac=0.02,
    long_only=False,
    min_abs_return=0.0,
    universe=("C",),
    version="v1",
)
SPEC_V001 = SPEC_V1

SPEC_V2 = FQ001Spec(
    hold_bars=20,
    stop_frac=0.08,
    long_only=True,
    min_abs_return=0.0,
    universe=("C",),
    version="v2",
)

SPEC_V3 = replace(
    SPEC_V2,
    confirm_lookback=60,
    universe=("C",),
    version="v3",
)

SPEC_V4 = replace(
    SPEC_V3,
    regime_switch=True,
    chop_reversion=True,
    chop_z=1.5,
    chop_hold_bars=5,
    version="v4",
)

SPEC = SPEC_V3


@dataclass(frozen=True)
class FQ002Spec:
    hold_bars: int = 20
    lots: int = 1
    stop_frac: float = 0.08
    cooldown_bars: int = 5
    long_only: bool = True
    min_ann_roll: float = 0.0
    start_cash: float = 10_000.0
    multiplier: float = 10.0
    tick: float = 1.0
    slippage_ticks: float = 1.0
    commission_rate: float = 0.0001
    margin_rate: float = 0.12
    underlying: str = "M"
    universe: tuple[str, ...] = ("M",)
    version: str = "v1"
    flatten_on_contango: bool = False


SPEC_FQ002_V1 = FQ002Spec()
SPEC_FQ002_V2 = FQ002Spec(flatten_on_contango=True, version="v2")
SPEC_FQ002 = SPEC_FQ002_V2


@dataclass(frozen=True)
class FQ003Spec:
    lookback: int = 242
    hold_bars: int = 20
    lots: int = 1
    stop_frac: float = 0.08
    cooldown_bars: int = 5
    long_only: bool = True
    min_bm: float = 0.0
    start_cash: float = 10_000.0
    multiplier: float = 10.0
    tick: float = 1.0
    slippage_ticks: float = 1.0
    commission_rate: float = 0.0001
    margin_rate: float = 0.12
    underlying: str = "MA"
    universe: tuple[str, ...] = ("MA",)
    version: str = "v1"
    flatten_on_negative_bm: bool = False


SPEC_FQ003_V1 = FQ003Spec()
SPEC_FQ003_V2 = FQ003Spec(underlying="CS", universe=("CS",), version="v2")
SPEC_FQ003_V3 = FQ003Spec(
    underlying="CS",
    universe=("CS",),
    flatten_on_negative_bm=True,
    version="v3",
)
SPEC_FQ003 = SPEC_FQ003_V2

CORN_MONTHS = (1, 3, 5, 7, 9, 11)

PRODUCT_MONTHS = {
    "C": CORN_MONTHS,
    "M": (1, 3, 5, 7, 8, 9, 11),
    "CS": CORN_MONTHS,
    "MA": tuple(range(1, 13)),
    "TA": tuple(range(1, 13)),
}

PRODUCT_MULT = {"C": 10.0, "M": 10.0, "CS": 10.0, "MA": 10.0, "TA": 5.0}
PRODUCT_TICK = {"C": 1.0, "M": 1.0, "CS": 1.0, "MA": 1.0, "TA": 2.0}
PRODUCT_REF = {
    "C": "C9999.XDCE",
    "M": "M9999.XDCE",
    "CS": "CS9999.XDCE",
    "MA": "MA9999.XZCE",
    "TA": "TA9999.XZCE",
}
