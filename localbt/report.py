from __future__ import annotations

from pathlib import Path

import pandas as pd

from localbt.engine import BacktestResult
from localbt.metrics import summarize


def write_iteration(
    path: Path,
    result: BacktestResult,
    *,
    source: str,
    extra_notes: str = "",
    title: str = "001",
) -> dict:
    stats = summarize(result, oos_start="2025-01-01")
    verdict = _verdict(stats, result)
    ins = stats.get("in_sample") or {}
    oos = stats.get("out_of_sample") or {}
    lines = [
        f"# {title} 本地回测（不依赖聚宽）",
        "",
        f"- 日期：{pd.Timestamp.today().strftime('%Y-%m-%d')}",
        f"- 区间：{stats['start']} → {stats['end']}（{stats['bars']} 根日线）",
        "- 样本外区间：2025-01-01 → 区间末",
        "- 频率：日（T-1 收盘信号，T 开盘成交）",
        "- 初始资金：10000",
        "- 手续费 / 滑点 / 保证金：费率 0.0001 / 边、1 跳滑点、保证金 12%",
        f"- 数据：{source}",
        f"- 夏普：{_pct(stats['sharpe'], False)}",
        f"- 年化：{_pct(stats['ann_return'])}",
        f"- 最大回撤：{_pct(stats['max_drawdown'])}",
        f"- 期末权益：{stats['end_equity']:.0f}",
        f"- 交易次数（平仓笔）：{stats['trades']}",
        f"- 止损次数：{stats['stops']}",
        f"- 换月次数：{stats['rolls']}",
        f"- 保证金不足跳过：{stats['margin_skips']}",
        f"- 是否打穿 / 爆仓：{'是' if result.bankrupt else '否'}；最低权益 {stats['min_equity']:.0f}",
        f"- 样本内夏普 / 回撤：{_pct(ins.get('sharpe'), False)} / {_pct(ins.get('max_drawdown'))}",
        f"- 样本外夏普 / 回撤：{_pct(oos.get('sharpe'), False)} / {_pct(oos.get('max_drawdown'))}",
        "- 聚宽分享链接：—（本次以本地结论为准）",
        f"- 结论：{verdict}",
        f"- 备注：{extra_notes}".rstrip() if extra_notes else "- 备注：",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    stats["verdict"] = verdict
    return stats


def _verdict(stats: dict, result: BacktestResult) -> str:
    oos = stats.get("out_of_sample") or {}
    if result.bankrupt:
        return "退役（1 万资金下回测打穿）"
    if stats["trades"] < 10:
        return "再改（交易过少，结果不可信）"
    if stats["max_drawdown"] < -0.5:
        return "再改（回撤超过 50%，1 万账户难存活）"
    oos_sharpe = oos.get("sharpe")
    if oos_sharpe is not None and oos_sharpe == oos_sharpe and oos_sharpe < 0.25:
        if oos_sharpe < 0:
            return "再改（样本外夏普为负，先不进模拟）"
        return "再改（样本外刚转正，先不进模拟）"
    if stats["sharpe"] == stats["sharpe"] and stats["sharpe"] > 0 and stats["max_drawdown"] > -0.35:
        return "可考虑进模拟（本地过门，仍需自己看权益曲线）"
    return "再改（全样本风险调整后不明显）"


def _pct(value, is_pct: bool = True) -> str:
    if value is None:
        return "n/a"
    try:
        if value != value:
            return "n/a"
    except TypeError:
        return "n/a"
    if is_pct:
        return f"{100 * float(value):.1f}%"
    return f"{float(value):.2f}"
