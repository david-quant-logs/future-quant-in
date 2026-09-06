# FQ-002-v2 豆粕展期收益（升水即平）
# 粘贴到聚宽。不要对 M9999.XDCE 下单。


def initialize(context):
    set_option('use_real_price', True)
    kind = ''
    rp = getattr(context, 'run_params', None)
    if rp is not None:
        kind = str(getattr(rp, 'type', '') or '')
    if 'backtest' in kind.lower():
        set_option('avoid_future_data', True)
    set_subportfolios([SubPortfolioConfig(cash=10000, type='futures')])
    set_benchmark('M9999.XDCE')
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

    g.underlying = 'M'
    g.ref = 'M9999.XDCE'
    g.hold_bars = 20
    g.flatten_on_contango = True
    g.lots = 1
    g.stop_frac = 0.08
    g.cooldown_bars = 5
    g.cooldown_left = 0
    g.bars_held = 0
    g.held_contract = None
    g.sig_near = None
    g.sig_far = None

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


def flatten(context, contract):
    if not contract:
        return
    if _amount(context.portfolio.long_positions, contract) > 0:
        order_target(contract, 0, side='long')
    if _amount(context.portfolio.short_positions, contract) > 0:
        order_target(contract, 0, side='short')


def open_long(context, contract):
    if _amount(context.portfolio.short_positions, contract) > 0:
        order_target(contract, 0, side='short')
    order_target(contract, g.lots, side='long')


def _root(contract):
    return str(contract).split('.')[0]


def _ym(contract):
    text = _root(contract)
    digits = ''.join(ch for ch in text if ch.isdigit())
    if len(digits) < 4:
        return None
    yy = int(digits[-4:-2])
    mm = int(digits[-2:])
    if mm < 1 or mm > 12:
        return None
    return (2000 + yy) * 12 + mm


def _close_of(contract):
    hist = attribute_history(
        contract,
        1,
        '1d',
        ['close'],
        skip_paused=True,
        df=True,
    )
    if hist is None or len(hist) < 1:
        return None
    px = float(hist['close'].iloc[-1])
    if px <= 0:
        return None
    return px


def _oi_of(contract):
    hist = attribute_history(
        contract,
        1,
        '1d',
        ['open_interest'],
        skip_paused=True,
        df=True,
    )
    if hist is None or len(hist) < 1:
        return 0.0
    return float(hist['open_interest'].iloc[-1])


def _next_liquid(dominant):
    near_ym = _ym(dominant)
    if near_ym is None:
        return None
    try:
        listed = get_future_contracts(g.underlying)
    except Exception:
        listed = get_future_contracts(dominant)
    if not listed:
        return None
    best = None
    best_oi = -1.0
    for item in listed:
        far_ym = _ym(item)
        if far_ym is None or far_ym <= near_ym:
            continue
        oi = _oi_of(item)
        if oi > best_oi:
            best_oi = oi
            best = item
    return best


def _ann_roll(near, far):
    n = _close_of(near)
    f = _close_of(far)
    n_ym = _ym(near)
    f_ym = _ym(far)
    if n is None or f is None or n_ym is None or f_ym is None:
        return None
    months = f_ym - n_ym
    if months <= 0:
        return None
    days = months * 30.0
    return (n - f) / f * (365.0 / days)


def rebalance(context):
    contract = get_dominant_future(g.underlying)
    if not contract:
        return

    if g.held_contract and g.held_contract != contract:
        flatten(context, g.held_contract)
        g.bars_held = 0
        g.held_contract = contract

    if g.cooldown_left > 0:
        flatten(context, contract)
        g.held_contract = contract
        g.bars_held = 0
        g.cooldown_left -= 1
        g.sig_near = contract
        g.sig_far = _next_liquid(contract)
        return

    long_amt = _amount(context.portfolio.long_positions, contract)
    pos_pnl = _pnl(context.portfolio.long_positions, contract)
    equity = context.portfolio.total_value
    if long_amt > 0 and equity > 0 and pos_pnl < -g.stop_frac * equity:
        flatten(context, contract)
        g.held_contract = contract
        g.bars_held = 0
        g.cooldown_left = g.cooldown_bars
        g.sig_near = contract
        g.sig_far = _next_liquid(contract)
        return

    in_pos = long_amt > 0
    if not g.sig_near or not g.sig_far:
        # 模拟盘第一天没有昨日缓存；用当前主力 + 次近月的 T-1 收盘，与本地 latest_fq002_signal 对齐。
        g.sig_near = contract
        g.sig_far = _next_liquid(contract)
    roll = _ann_roll(g.sig_near, g.sig_far)
    target = 1 if (roll is not None and roll > 0) else 0
    allow = (not in_pos) or g.bars_held >= g.hold_bars or (
        g.flatten_on_contango and in_pos and target == 0
    )
    if not allow:
        g.bars_held += 1
        g.held_contract = contract
        g.sig_near = contract
        g.sig_far = _next_liquid(contract)
        log.info('FQ-002-v2 hold %s roll=%s tgt=%s far=%s' % (contract, roll, target, g.sig_far))
        return

    if target == 1 and not in_pos:
        open_long(context, contract)
        g.bars_held = 1
    elif target == 0 and in_pos:
        flatten(context, contract)
        g.bars_held = 0
    elif in_pos:
        g.bars_held = 1

    g.held_contract = contract
    log.info('FQ-002-v2 %s roll=%s tgt=%s far=%s' % (contract, roll, target, g.sig_far))
    g.sig_near = contract
    g.sig_far = _next_liquid(contract)
