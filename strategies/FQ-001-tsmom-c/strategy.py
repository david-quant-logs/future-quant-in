# FQ-001-v3 玉米 20 日动量，60 日确认
# 粘贴到聚宽。不要对 C9999.XDCE 下单。


def initialize(context):
    set_option('use_real_price', True)
    kind = ''
    rp = getattr(context, 'run_params', None)
    if rp is not None:
        kind = str(getattr(rp, 'type', '') or '')
    if 'backtest' in kind.lower():
        set_option('avoid_future_data', True)
    set_subportfolios([SubPortfolioConfig(cash=10000, type='futures')])
    set_benchmark('C9999.XDCE')
    set_order_cost(
        OrderCost(
            open_commission=0.0001,
            close_commission=0.0001,
            close_today_commission=0.0001,
            min_commission=0,
        ),
        type='futures',
    )
    set_slippage(StepRelatedSlippage(1), type='futures')

    g.underlying = 'C'
    g.ref = 'C9999.XDCE'
    g.lookback = 20
    g.confirm_lookback = 60
    g.hold_bars = 20
    g.lots = 1
    g.stop_frac = 0.08
    g.cooldown_bars = 5
    g.cooldown_left = 0
    g.bars_held = 0
    g.held_contract = None

    run_daily(rebalance, time='09:05', reference_security=g.ref)


def process_initialize(context):
    pass


def _amount(positions, contract):
    if contract in positions:
        return positions[contract].total_amount
    return 0


def _multiplier(contract):
    try:
        info = get_security_info(contract)
        m = getattr(info, 'contract_multiplier', None)
        if m:
            return float(m)
    except Exception:
        pass
    return 10.0


def _pnl(positions, contract):
    # 期货 UserPosition 没有 .pnl，用现价相对开仓均价 * 手数 * 合约乘数。
    if contract not in positions:
        return 0.0
    pos = positions[contract]
    amt = float(pos.total_amount or 0)
    if amt == 0:
        return 0.0
    price = float(getattr(pos, 'price', 0) or 0)
    cost = float(getattr(pos, 'avg_cost', 0) or 0)
    if price <= 0 or cost <= 0:
        return 0.0
    return (price - cost) * amt * _multiplier(contract)


def flatten(contract):
    if not contract:
        return
    order_target(contract, 0, side='long')
    order_target(contract, 0, side='short')


def open_long(contract):
    order_target(contract, 0, side='short')
    order_target(contract, g.lots, side='long')


def _past_ret(contract, lookback):
    hist = attribute_history(
        contract,
        lookback + 1,
        '1d',
        ['close'],
        skip_paused=True,
        df=True,
    )
    if hist is None or len(hist) < lookback + 1:
        return None
    closes = hist['close'].values
    if closes[0] == 0:
        return None
    return closes[-1] / closes[0] - 1.0


def rebalance(context):
    contract = get_dominant_future(g.underlying)
    if not contract:
        return

    if g.held_contract and g.held_contract != contract:
        flatten(g.held_contract)
        g.bars_held = 0
        g.held_contract = contract

    if g.cooldown_left > 0:
        flatten(contract)
        g.held_contract = contract
        g.bars_held = 0
        g.cooldown_left -= 1
        return

    long_amt = _amount(context.portfolio.long_positions, contract)
    pos_pnl = _pnl(context.portfolio.long_positions, contract)
    equity = context.portfolio.total_value
    if long_amt > 0 and equity > 0 and pos_pnl < -g.stop_frac * equity:
        flatten(contract)
        g.held_contract = contract
        g.bars_held = 0
        g.cooldown_left = g.cooldown_bars
        return

    in_pos = long_amt > 0
    allow = (not in_pos) or g.bars_held >= g.hold_bars
    if not allow:
        g.bars_held += 1
        g.held_contract = contract
        return

    fast = _past_ret(contract, g.lookback)
    slow = _past_ret(contract, g.confirm_lookback)
    target = 1 if (fast is not None and slow is not None and fast > 0 and slow > 0) else 0

    if target == 1 and not in_pos:
        open_long(contract)
        g.bars_held = 1
    elif target == 0 and in_pos:
        flatten(contract)
        g.bars_held = 0
    elif in_pos:
        g.bars_held = 1

    g.held_contract = contract
    log.info('FQ-001-v3 %s fast=%s slow=%s tgt=%s' % (contract, fast, slow, target))
