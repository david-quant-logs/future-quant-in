# FQ-002 豆粕时间序列展期收益

编号始终是 **FQ-002**。规则迭代用 `v1`、`v2`。当前冻结 **v2**。

文献：[research/FQ-002-carry-m.md](../../research/FQ-002-carry-m.md)

| 版本 | 规则 | 记录 |
| --- | --- | --- |
| FQ-002-v1 | 贴水做多，持有满 20 日 | [v1](iterations/v1.md) |
| FQ-002-v2（当前） | v1 + 升水即平 | [v2](iterations/v2.md) |

```powershell
python run_fq002.py --version v1
python run_fq002.py --version v2
python run_fq002_ctp.py
```

当前是**步骤 1**：聚宽自动模拟（2026-09-02 起，满 3 个月约 2026-12-02）。通知用聚宽自带，你在 App 手搓。月记：[paper/FQ-002-observe.md](../../paper/FQ-002-observe.md)。步骤 2 之前不要 `run_fq002_ctp.py --send`。门槛见 [docs/gates.md](../../docs/gates.md)。
