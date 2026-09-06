"""Run FQ-001 locally. Versions: v1–v4. Default is the current freeze (v3)."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from localbt import SPEC, SPEC_V1, SPEC_V2, SPEC_V3, SPEC_V4
from localbt.engine import run_fq001, run_fq001_rotate
from localbt.fetch import build_dominant_map, load_or_fetch
from localbt.report import write_iteration
from localbt.scan import scan_corn

ROOT = Path(__file__).resolve().parent
CHART = ROOT / "output" / "fq001_equity.png"
VERSIONS = {"v1": SPEC_V1, "v2": SPEC_V2, "v3": SPEC_V3, "v4": SPEC_V4}


def synthetic_bars(n: int = 400) -> tuple[pd.DataFrame, pd.Series]:
    dates = pd.bdate_range("2018-01-01", periods=n)
    px = 2000.0
    rows = []
    for i, day in enumerate(dates):
        px = px * (1.002 if i % 40 < 28 else 0.997)
        o = px * 0.999
        c = px
        rows.append(
            {
                "date": day,
                "product": "C",
                "contract": "C1805",
                "open": o,
                "high": max(o, c) * 1.002,
                "low": min(o, c) * 0.998,
                "close": c,
                "volume": 10_000,
                "open_interest": 50_000,
            }
        )
    bars = pd.DataFrame(rows)
    dominant = bars.set_index("date")["contract"]
    return bars, dominant


def main() -> None:
    parser = argparse.ArgumentParser(description="FQ-001 local backtest")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--scan", action="store_true", help="compare FQ-001-v1 corn variants")
    parser.add_argument("--version", default="v3", choices=sorted(VERSIONS))
    parser.add_argument("--refresh", action="store_true", help="ignore csv cache")
    args = parser.parse_args()
    spec = VERSIONS[args.version]

    if args.synthetic:
        bars, dominant = synthetic_bars()
        source = "synthetic (sanity only)"
        result = run_fq001(bars, dominant, spec, start=args.start, end=args.end)
    elif args.scan:
        bars = load_or_fetch("C", start="2016-01-01", end=args.end, cache=not args.refresh)
        dominant = build_dominant_map(bars, "C")
        rows = scan_corn(bars, dominant, start=args.start)
        print(f"{'name':<28} {'end':>8} {'sharpe':>7} {'dd':>8} {'oosSh':>7} {'oosRet':>8} {'n':>4} {'stop':>4}")
        for row in rows:
            print(
                f"{row['name']:<28} {row['end']:8.0f} {row['sharpe']:7.2f} {row['dd']:8.1%} "
                f"{row['oos_sharpe']:7.2f} {row['oos_ret']:8.1%} {row['trades']:4d} {row['stops']:4d}"
            )
        return
    else:
        book = {}
        for product in spec.universe:
            bars = load_or_fetch(product, start="2016-01-01", end=args.end, cache=not args.refresh)
            book[product] = (bars, build_dominant_map(bars, product))
        source = "Sina via AkShare; " + ", ".join(
            f"{p}:{book[p][0]['contract'].nunique()} ctr" for p in spec.universe
        )
        if len(spec.universe) == 1:
            bars, dominant = book[spec.universe[0]]
            result = run_fq001(bars, dominant, spec, start=args.start, end=args.end)
        else:
            result = run_fq001_rotate(book, spec, start=args.start, end=args.end)

    notes = {
        "v1": "FQ-001-v1：玉米日频多空，止损 2%。",
        "v2": "FQ-001-v2：玉米持有 20 日、只做多、止损 8%。",
        "v3": "FQ-001-v3：玉米 20 日动量须 60 日同向确认，持有 20 日、只做多、止损 8%。篮子轮换试过，已否决。",
        "v4": "FQ-001-v4：v3 趋势单拿满持有期；熊市不开新仓；震荡只在均线下方超卖时做多（持有更短）。",
    }[args.version]
    iter_path = ROOT / "strategies" / "FQ-001-tsmom-c" / "iterations" / f"{args.version}.md"
    stats = write_iteration(
        iter_path, result, source=source, extra_notes=notes, title=f"FQ-001-{args.version}"
    )
    _chart(result.equity, args.version)
    print(f"wrote {iter_path}")
    print(f"end equity {stats['end_equity']:.0f} sharpe {stats['sharpe']} dd {stats['max_drawdown']}")
    print(f"verdict: {stats['verdict']}")


def _chart(equity: pd.Series, version: str) -> None:
    CHART.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(equity.index, equity.values, color="#1f4e79", lw=1.2)
    ax.axhline(SPEC.start_cash, color="#999", lw=0.8, ls="--")
    ax.set_title(f"FQ-001-{version} equity (local, 10k)")
    ax.set_ylabel("CNY")
    fig.tight_layout()
    fig.savefig(CHART, dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
