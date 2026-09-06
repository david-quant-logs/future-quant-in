"""Small pre-registered FQ-001 variant scan on cached corn (and optional basket)."""

from __future__ import annotations

from dataclasses import replace

from localbt import FQ001Spec, SPEC_V1, SPEC_V2, SPEC_V4
from localbt.engine import run_fq001
from localbt.metrics import summarize


def corn_variants() -> list[tuple[str, FQ001Spec]]:
    return [
        ("FQ-001-v1", SPEC_V1),
        ("v1_hold20_ls_stop2", replace(SPEC_V1, hold_bars=20)),
        ("v1_daily_ls_stop8", replace(SPEC_V1, stop_frac=0.08)),
        ("FQ-001-v2", SPEC_V2),
        ("FQ-001-v3", replace(SPEC_V2, confirm_lookback=60)),
        ("FQ-001-v4", SPEC_V4),
        ("v2_plus_dead2", replace(SPEC_V2, min_abs_return=0.02)),
        ("v2_but_longshort", replace(SPEC_V2, long_only=False)),
    ]


def scan_corn(bars, dominant, start: str = "2018-01-01") -> list[dict]:
    rows = []
    for name, spec in corn_variants():
        result = run_fq001(bars, dominant, spec, start=start)
        stats = summarize(result, oos_start="2025-01-01")
        oos = stats.get("out_of_sample") or {}
        rows.append(
            {
                "name": name,
                "end": stats.get("end_equity"),
                "sharpe": stats.get("sharpe"),
                "dd": stats.get("max_drawdown"),
                "oos_sharpe": oos.get("sharpe"),
                "oos_ret": oos.get("total_return"),
                "trades": stats.get("trades"),
                "stops": stats.get("stops"),
                "bust": result.bankrupt,
            }
        )
    return rows
