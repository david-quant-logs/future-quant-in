# future-quant-in

国内商品期货中低频策略实验室。回测和模拟在[聚宽](https://www.joinquant.com/)完成；本仓库存策略代码、文献笔记和迭代记录。

一次只推进一条策略。上一条进入模拟盘或明确退役后，才开下一条的论文调研。短期不做实盘；模拟池凑满 10 条后再评估。

1 万本金到 5 万是以后评估实盘时的资金目标，不是本仓库的验收标准。小资金期货容错极低，赛马看的是：规则可复现、计入成本后是否仍有效、1 万保证金会不会被打穿。

## 当前策略

| 编号 | 主题 | 状态 |
| --- | --- | --- |
| [FQ-001](strategies/FQ-001-tsmom-c/) | 玉米 20 日时间序列动量 | backtest（待首次聚宽回测） |

总表：[STRATEGY_INDEX.md](STRATEGY_INDEX.md)

## 流水线

论文调研 → 冻结新手最小方案 → 聚宽日频代码 → 回测迭代 → 过门则挂**一条**模拟。

调研协议：[docs/research-protocol.md](docs/research-protocol.md)

## 聚宽用法

1. 打开对应目录的 `strategy.py`。
2. 全文粘贴到聚宽研究/策略编辑器。
3. 账户类型必须是期货，初始资金 10000。约定见 [docs/joinquant.md](docs/joinquant.md)。
4. 把回测数字写回 `strategies/FQ-NNN-*/iterations/`。

Cursor 连不上聚宽网页机。逻辑在本机改，数字从聚宽抄回来。

## 知乎草稿

研究文稿放在仓库外的 `C:\Project\notes`，不进 git。
