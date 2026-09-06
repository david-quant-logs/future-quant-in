# future-quant-in

国内商品期货中低频策略实验室。回测和模拟在[聚宽](https://www.joinquant.com/)完成；本仓库存策略代码、文献笔记和迭代记录。

**当前聚宽模拟：FQ-002-v2 豆粕展期**（2026-09-02 挂盘，满 3 个月约 2026-12-02）。FQ-001 玉米动量已冻结、未挂模拟。一次只挂一条模拟。过门后走三步：聚宽模拟 → 阿里云接 SimNow 自动 → 实盘自动另议。见 [docs/gates.md](docs/gates.md)。

1 万本金到 5 万是以后评估实盘时的资金目标，不是本仓库的验收标准。小资金期货容错极低，赛马看的是：规则可复现、计入成本后是否仍有效、1 万保证金会不会被打穿。

## 当前策略

| 编号 | 主题 | 状态 |
| --- | --- | --- |
| [FQ-002](strategies/FQ-002-carry-m/) | 豆粕展期收益（FQ-002-v2，升水即平） | **paper（聚宽自动模拟）** |
| [FQ-001](strategies/FQ-001-tsmom-c/) | 玉米 20 日动量（FQ-001-v3） | backtest（冻结，未挂模拟） |
| [FQ-003](strategies/FQ-003-basismom-ma/) | 淀粉基差动量（FQ-003-v2） | research（不挂模拟） |

模拟观察：[paper/FQ-002-observe.md](paper/FQ-002-observe.md) · 赛马表：[paper/leaderboard.md](paper/leaderboard.md) · 总表：[STRATEGY_INDEX.md](STRATEGY_INDEX.md)

## 流水线

论文调研 → 冻结新手最小方案 → 聚宽日频代码 → 回测迭代 → 过门则挂**一条**聚宽模拟（自动 → 通知+手搓 → 满 3 个月）→ 再谈阿里云 SimNow → 实盘另议。

调研协议：[docs/research-protocol.md](docs/research-protocol.md)

## 本地回测（主结论）

不依赖聚宽网页回测。FQ-002 与 `strategies/FQ-002-carry-m/strategy.py` 对齐。都是 T-1 信号、T 开盘成交、1 手、1 万本金。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
python run_fq002.py
```

`--synthetic` 只检查引擎，不当作绩效。真实数据来自新浪合约日线（AkShare），按持仓量选每日主力。结果写入对应 `iterations/`。

## 聚宽用法

1. 打开 [strategies/FQ-002-carry-m/strategy.py](strategies/FQ-002-carry-m/strategy.py)。
2. 全文粘贴到聚宽研究/策略编辑器。
3. 账户类型必须是期货，初始资金 10000。约定见 [docs/joinquant.md](docs/joinquant.md)。
4. 把回测数字写回 `strategies/FQ-002-carry-m/iterations/`；模拟数字写回 [paper/FQ-002-observe.md](paper/FQ-002-observe.md)。

Cursor 连不上聚宽网页机。逻辑在本机改，数字从聚宽抄回来。

## 本地 CTP 仿真（SimNow）

步骤 2（阿里云自动）之前只测登录，默认 dry-run，不对 SimNow 自动发单。账号密码只放本机 `%USERPROFILE%\.cursor\secrets\`，禁止进 git。实盘前置拒绝。见 [docs/ctp.md](docs/ctp.md)、[docs/gates.md](docs/gates.md)。

```powershell
pip install -r requirements-ctp.txt
python run_ctp_probe.py
python run_fq002_ctp.py
```

## 不进 GitHub 的内容

知乎 / 微信 / 小红书草稿只放仓库外的 `C:\Project\notes`。API key、token、SimNow 密码只放 `%USERPROFILE%\.cursor\secrets\`。
