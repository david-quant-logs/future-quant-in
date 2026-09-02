# 聚宽约定

Cursor 不能连聚宽网页机。本机改 `strategy.py`，粘贴到聚宽跑，数字抄回 `iterations/`。

## 每个策略必须有

```python
set_subportfolios([SubPortfolioConfig(cash=10000, type='futures')])
set_option('use_real_price', True)
set_option('avoid_future_data', True)
```

- 下单用 `get_dominant_future('C')` 返回的真实合约（如 `C2601.XDCE`）。
- **禁止**对 `C9999.XDCE` 这类主力占位符下单；占位符只用于基准和 `reference_security`。
- 平仓时 `side` 与原持仓相同，目标手数 0。写成相反 `side` 会开反向仓而不是平仓。
- 主力切换时先平旧合约，再在新主力上开仓。
- 不可 pickle 的对象放 `process_initialize`。
- 手续费和跳数滑点写死，不允许零成本夏普进看板。

## 日频无前视

开盘后调度（如 `09:05`），信号只用**已经收盘**的日线，不含当天。`avoid_future_data` 必须开。

## 回测设置建议

- 初始资金：10000
- 频率：天
- 基准：对应品种连续合约，如 `C9999.XDCE`
- 区间：至少覆盖一轮完整农产品季节（建议 ≥ 5 年），另留最近 1 年做样本外
