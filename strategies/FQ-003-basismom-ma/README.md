# FQ-003 甲醇时间序列基差动量

编号始终是 **FQ-003**。规则迭代用 `v1`、`v2`。当前冻结 **v1**。

文献：[research/FQ-003-basismom-ma.md](../../research/FQ-003-basismom-ma.md)

| 版本 | 规则 | 记录 |
| --- | --- | --- |
| FQ-003-v1（否决） | 甲醇 242 日基差动量，持有 20 日 | [v1](iterations/v1.md) |
| FQ-003-v2（当前对照，未过门） | 同一因子，淀粉 CS | [v2](iterations/v2.md) |
| FQ-003-v3（否决） | v2 + BM 转负即平 | [v3](iterations/v3.md) |

```powershell
python run_fq003.py --version v1
python run_fq003.py --version v2
python run_fq003.py --version v3
```

FQ-002 聚宽模拟未满 3 个月（约 2026-12-02）。本条即使本地过门也不挂模拟，更不要 `run_*_ctp.py --send`。门槛见 [docs/gates.md](../../docs/gates.md)。
