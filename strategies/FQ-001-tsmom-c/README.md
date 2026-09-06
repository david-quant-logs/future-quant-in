# FQ-001 20 日动量

编号始终是 **FQ-001**。规则迭代用 `v1` / `v2` / `v3` / `v4`。当前冻结 **v3**。

| 版本 | 规则 | 记录 |
| --- | --- | --- |
| FQ-001-v1 | 玉米日频多空，止损 2% | [v1](iterations/v1.md) |
| FQ-001-v2 | 玉米持有 20 日、只做多、止损 8% | [v2](iterations/v2.md) |
| FQ-001-v3（当前） | 玉米 20 日动量 + 60 日确认 | [v3](iterations/v3.md) |
| FQ-001-v4（否决） | 按行情切换：牛市趋势 / 熊市空仓 / 震荡超卖做多 | [v4](iterations/v4.md) |

```powershell
python run_fq001.py --version v1
python run_fq001.py --version v2
python run_fq001.py --version v3
python run_fq001.py --version v4
```
