# 策略总表

编号 `FQ-NNN` 三位流水，永不复用。同一策略的改规则用 `FQ-001-v1`、`v2`、`v3`。

| 编号 | 当前版本 | 目录 | 规则 | 状态 | 本地回测 | 聚宽模拟 |
| --- | --- | --- | --- | --- | --- | --- |
| FQ-001 | v3 | [FQ-001-tsmom-c](strategies/FQ-001-tsmom-c/) | 玉米 20 日动量 + 60 日确认 | backtest（冻结，未挂模拟） | [v1](strategies/FQ-001-tsmom-c/iterations/v1.md) / [v2](strategies/FQ-001-tsmom-c/iterations/v2.md) / [v3](strategies/FQ-001-tsmom-c/iterations/v3.md) / [v4 否决](strategies/FQ-001-tsmom-c/iterations/v4.md) | — |
| FQ-002 | v2 | [FQ-002-carry-m](strategies/FQ-002-carry-m/) | 豆粕展期，升水即平 | paper 步骤 1（自动模拟，满 3 个月约 2026-12-02） | [v1](strategies/FQ-002-carry-m/iterations/v1.md) / [v2](strategies/FQ-002-carry-m/iterations/v2.md) | 已挂；观察 [paper/FQ-002-observe.md](paper/FQ-002-observe.md) |
| FQ-003 | v2 | [FQ-003-basismom-ma](strategies/FQ-003-basismom-ma/) | 淀粉近远端 242 日基差动量 | research（v1/v3 否决，v2 未过门；不挂模拟） | [v1 否决](strategies/FQ-003-basismom-ma/iterations/v1.md) / [v2](strategies/FQ-003-basismom-ma/iterations/v2.md) / [v3 否决](strategies/FQ-003-basismom-ma/iterations/v3.md) | — |

文献：[FQ-001](research/FQ-001-tsmom-c.md) · [FQ-002](research/FQ-002-carry-m.md) · [FQ-003](research/FQ-003-basismom-ma.md)
