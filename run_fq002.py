"""Run FQ-002 locally. Default is the current freeze (v2)."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from localbt import SPEC_FQ002, SPEC_FQ002_V1, SPEC_FQ002_V2, SPEC_V3
from localbt.engine import run_fq001, run_fq002
from localbt.fetch import build_dominant_map, build_next_map, load_or_fetch
from localbt.report import write_iteration
from localbt.stability import yearly_returns, stability

ROOT = Path(__file__).resolve().parent
CHART = ROOT / "output" / "fq002_equity.png"
VERSIONS = {"v1": SPEC_FQ002_V1, "v2": SPEC_FQ002_V2}


def main() -> None:
    parser = argparse.ArgumentParser(description="FQ-002 local backtest")
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
    result = run_fq002(bars, dominant, nxt, spec, start=args.start, end=args.end)

    notes = {
        "v1": "FQ-002-v1：豆粕主力，T-1 年化展期收益>0 做多 1 手，持有 20 日，止损 8%。不做空、不横截面排序。",
        "v2": "FQ-002-v2：相对 v1，展期收益转负（升水）即平，不等待 20 日持有期满。",
    }[args.version]
    iter_path = ROOT / "strategies" / "FQ-002-carry-m" / "iterations" / f"{args.version}.md"
    stats = write_iteration(
        iter_path, result, source=source, extra_notes=notes, title=f"FQ-002-{args.version}"
    )
    _chart(result.equity, args.version)

    corn = load_or_fetch("C", start="2016-01-01", end=args.end, cache=True)
    corn_dom = build_dominant_map(corn, "C")
    mom = run_fq001(corn, corn_dom, SPEC_V3, start=args.start, end=args.end)
    aligned = pd.concat(
        {"carry": result.equity.pct_change(), "tsmom": mom.equity.pct_change()},
        axis=1,
    ).dropna()
    corr = float(aligned["carry"].corr(aligned["tsmom"])) if len(aligned) > 5 else float("nan")
    yrs = yearly_returns(result.equity, spec.start_cash)
    st = stability(result.equity, spec.start_cash)
    extra = [
        "",
        "## 分年",
        "",
        "| 年 | 收益 |",
        "| --- | --- |",
    ]
    for ts, ret in yrs.items():
        extra.append(f"| {ts.year} | {ret:+.1%} |")
    extra += [
        "",
        f"与 FQ-001-v3 日收益相关：{corr:.3f}。年收益标准差 {st.get('year_std', float('nan')):.1%}，最差一年 {st.get('worst_year', float('nan')):+.1%}。",
        f"有仓天数占比 {(result.positions != 0).mean():.1%}。最佳年占累计收益比例 {st.get('best_year_share_of_total', float('nan')):.0%}。",
        "",
    ]
    eq = result.equity
    pre = eq[eq.index < "2022-01-01"]
    during = eq[eq.index < "2023-01-01"]
    if len(pre) and len(during):
        y2022 = float(during.iloc[-1] - pre.iloc[-1])
        total = float(eq.iloc[-1] - spec.start_cash)
        if total != 0:
            extra.insert(-1, f"2022 年人民币盈亏占累计盈利：{y2022 / total:.0%}。")
            extra.append("")
    iter_path.write_text(iter_path.read_text(encoding="utf-8") + "\n".join(extra), encoding="utf-8")

    print(f"wrote {iter_path}")
    print(f"end equity {stats['end_equity']:.0f} sharpe {stats['sharpe']} dd {stats['max_drawdown']}")
    print(f"verdict: {stats['verdict']}")
    print(f"daily return corr vs FQ-001-v3: {corr:.3f}")


def _chart(equity: pd.Series, version: str) -> None:
    CHART.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(equity.index, equity.values, color="#1f4e79", lw=1.2)
    ax.axhline(SPEC_FQ002.start_cash, color="#999", lw=0.8, ls="--")
    ax.set_title(f"FQ-002-{version} equity (local, 10k, soymeal carry)")
    ax.set_ylabel("CNY")
    fig.tight_layout()
    fig.savefig(CHART, dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
