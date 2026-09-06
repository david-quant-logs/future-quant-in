"""Run FQ-003 locally. Default is the current attempt (v2)."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from localbt import SPEC_FQ003, SPEC_FQ003_V1, SPEC_FQ003_V2, SPEC_FQ003_V3, SPEC_FQ002, SPEC_V3
from localbt.engine import run_fq001, run_fq002, run_fq003
from localbt.fetch import build_dominant_map, build_next_map, load_or_fetch
from localbt.report import write_iteration
from localbt.stability import yearly_returns, stability

ROOT = Path(__file__).resolve().parent
CHART = ROOT / "output" / "fq003_equity.png"
VERSIONS = {"v1": SPEC_FQ003_V1, "v2": SPEC_FQ003_V2, "v3": SPEC_FQ003_V3}


def main() -> None:
    parser = argparse.ArgumentParser(description="FQ-003 local backtest")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--version", default="v2", choices=sorted(VERSIONS))
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    spec = VERSIONS[args.version]

    bars = load_or_fetch(spec.underlying, start="2016-01-01", end=args.end, cache=not args.refresh)
    dominant = build_dominant_map(bars, spec.underlying)
    nxt = build_next_map(bars, dominant, spec.underlying)
    source = f"Sina via AkShare; {spec.underlying}:{bars['contract'].nunique()} ctr"
    result = run_fq003(bars, dominant, nxt, spec, start=args.start, end=args.end)

    notes = {
        "v1": "FQ-003-v1：甲醇主力，近端策略 242 日复利减远端策略 242 日复利>0 做多 1 手，持有 20 日，止损 8%。不做空、不横截面排序。",
        "v2": "FQ-003-v2：同一套 242 日基差动量，品种从甲醇换成淀粉。不改窗口、持有、止损。",
        "v3": "FQ-003-v3：相对 v2，基差动量转负即平，不等待 20 日持有期满。",
    }[args.version]
    iter_path = ROOT / "strategies" / "FQ-003-basismom-ma" / "iterations" / f"{args.version}.md"
    stats = write_iteration(
        iter_path, result, source=source, extra_notes=notes, title=f"FQ-003-{args.version}"
    )
    _chart(result.equity, args.version, spec.underlying)

    extra = [
        "",
        "## 分年",
        "",
        "| 年 | 收益 |",
        "| --- | --- |",
    ]
    yrs = yearly_returns(result.equity, spec.start_cash)
    for ts, ret in yrs.items():
        extra.append(f"| {ts.year} | {ret:+.1%} |")
    st = stability(result.equity, spec.start_cash)
    extra += [
        "",
        f"年收益标准差 {st.get('year_std', float('nan')):.1%}，最差一年 {st.get('worst_year', float('nan')):+.1%}。",
        f"有仓天数占比 {(result.positions != 0).mean():.1%}。最佳年占累计收益比例 {st.get('best_year_share_of_total', float('nan')):.0%}。",
        "",
    ]
    extra.extend(_corr_lines(result, args.start, args.end))
    iter_path.write_text(iter_path.read_text(encoding="utf-8") + "\n".join(extra), encoding="utf-8")

    print(f"wrote {iter_path}")
    print(f"end equity {stats['end_equity']:.0f} sharpe {stats['sharpe']} dd {stats['max_drawdown']}")
    print(f"verdict: {stats['verdict']}")


def _corr_lines(result, start: str, end: str | None) -> list[str]:
    lines = []
    try:
        corn = load_or_fetch("C", start="2016-01-01", end=end, cache=True)
        meal = load_or_fetch("M", start="2016-01-01", end=end, cache=True)
        corn_dom = build_dominant_map(corn, "C")
        meal_dom = build_dominant_map(meal, "M")
        meal_nxt = build_next_map(meal, meal_dom, "M")
        mom = run_fq001(corn, corn_dom, SPEC_V3, start=start, end=end)
        carry = run_fq002(meal, meal_dom, meal_nxt, SPEC_FQ002, start=start, end=end)
        bm = result.equity.pct_change()
        aligned_m = pd.concat({"bm": bm, "tsmom": mom.equity.pct_change()}, axis=1, sort=False).dropna()
        aligned_c = pd.concat({"bm": bm, "carry": carry.equity.pct_change()}, axis=1, sort=False).dropna()
        corr_m = float(aligned_m["bm"].corr(aligned_m["tsmom"])) if len(aligned_m) > 5 else float("nan")
        corr_c = float(aligned_c["bm"].corr(aligned_c["carry"])) if len(aligned_c) > 5 else float("nan")
        lines.append(f"与 FQ-001-v3 日收益相关：{corr_m:.3f}。与 FQ-002-v2 日收益相关：{corr_c:.3f}。")
        lines.append("")
        print(f"daily return corr vs FQ-001-v3: {corr_m:.3f}")
        print(f"daily return corr vs FQ-002-v2: {corr_c:.3f}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"与前两条相关未计算：{exc}")
        lines.append("")
    return lines


def _chart(equity: pd.Series, version: str, underlying: str) -> None:
    CHART.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(equity.index, equity.values, color="#1f4e79", lw=1.2)
    ax.axhline(SPEC_FQ003.start_cash, color="#999", lw=0.8, ls="--")
    ax.set_title(f"FQ-003-{version} equity (local, 10k, {underlying} basis-momentum)")
    ax.set_ylabel("CNY")
    fig.tight_layout()
    fig.savefig(CHART, dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
