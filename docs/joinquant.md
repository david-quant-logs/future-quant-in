# 聚宽约定

Cursor 不能连聚宽网页机。本机改 `strategy.py`，粘贴到聚宽跑，数字抄回 `iterations/`。

## 每个策略必须有

```python
set_subportfolios([SubPortfolioConfig(cash=10000, type='futures')])
set_option('use_real_price', True)
if 'backtest' in str(getattr(getattr(context, 'run_params', None), 'type', '') or '').lower():
    set_option('avoid_future_data', True)
```

- 下单用 `get_dominant_future('C')` 返回的真实合约（如 `C2601.XDCE`）。
- **禁止**对 `C9999.XDCE` 这类主力占位符下单；占位符只用于基准和 `reference_security`。
- 平仓时 `side` 与原持仓相同，目标手数 0。写成相反 `side` 会开反向仓而不是平仓。
- 期货 `UserPosition` **没有** `.pnl`。止损用 `(price - avg_cost) * total_amount * contract_multiplier`（多头）。
- 主力切换时先平旧合约，再在新主力上开仓。
- 不可 pickle 的对象放 `process_initialize`。
- 手续费和跳数滑点写死，不允许零成本夏普进看板。

## 日频无前视

开盘后调度（如 `09:05`），信号只用**已经收盘**的日线，不含当天。回测必须开 `avoid_future_data`。模拟盘该选项无效。`initialize` 里 `is_trade()` 在 00:00 经常还是 False，会误设选项并打 WARNING；用 `context.run_params.type` 含 `backtest` 再设。

## 回测设置建议

- 初始资金：10000
- 频率：天
- 基准：对应品种连续合约，如 `C9999.XDCE`
- 区间：至少覆盖一轮完整农产品季节（建议 ≥ 5 年），另留最近 1 年做样本外

## 模拟盘三步里的聚宽

过门后先挂**自动模拟**。再在聚宽打开模拟通知或邮件，信号到了在 App 里按规则手搓 1 手，用来确认能执行。数字每月抄回 [paper/FQ-002-observe.md](../paper/FQ-002-observe.md)（或对应策略观察页）。满 3 个月才评估 SimNow 自动。门槛见 [gates.md](gates.md)。
