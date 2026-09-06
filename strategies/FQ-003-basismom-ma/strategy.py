# FQ-003-v2 淀粉基差动量（近远端 242 日）
# 粘贴到聚宽。不要对 CS9999.XDCE 下单。
# 回测起始日建议 2016-01-01，前 lookback 根为信号预热，与本地 load 起点对齐。


def initialize(context):
    set_option('use_real_price', True)
    if not is_trade():
        set_option('avoid_future_data', True)
    set_subportfolios([SubPortfolioConfig(cash=10000, type='futures')])
    set_benchmark('CS9999.XDCE')
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

    g.underlying = 'CS'
    g.ref = 'CS9999.XDCE'
    g.lookback = 242
    g.hold_bars = 20
    g.flatten_on_negative_bm = False
    g.lots = 1
    g.stop_frac = 0.08
    g.cooldown_bars = 5
    g.cooldown_left = 0
    g.bars_held = 0
    g.held_contract = None
    g.near_rets = []
    g.far_rets = []
    g.roll_near = None
    g.roll_far = None
    g.near_px = None
    g.far_px = None
    g.pending_near = None
    g.pending_far = None

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
    if not contract:
        return None
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


def _prod_m1(rets):
    x = 1.0
    for r in rets:
        x *= 1.0 + r
    return x - 1.0


def _push(rets, contract, prev_px):
    if not contract or prev_px is None or prev_px <= 0:
        return
    px = _close_of(contract)
    if px is None:
        return
    rets.append(px / prev_px - 1.0)
    if len(rets) > g.lookback:
        del rets[0]


def rebalance(context):
    contract = get_dominant_future(g.underlying)
    if not contract:
        return

    _push(g.near_rets, g.roll_near, g.near_px)
    _push(g.far_rets, g.roll_far, g.far_px)

    if g.held_contract and g.held_contract != contract:
        flatten(context, g.held_contract)
        g.bars_held = 0
        g.held_contract = contract

    if g.cooldown_left > 0:
        flatten(context, contract)
        g.held_contract = contract
        g.bars_held = 0
        g.cooldown_left -= 1
        _rotate_legs(contract)
        return

    long_amt = _amount(context.portfolio.long_positions, contract)
    pos_pnl = _pnl(context.portfolio.long_positions, contract)
    equity = context.portfolio.total_value
    if long_amt > 0 and equity > 0 and pos_pnl < -g.stop_frac * equity:
        flatten(context, contract)
        g.held_contract = contract
        g.bars_held = 0
        g.cooldown_left = g.cooldown_bars
        _rotate_legs(contract)
        return

    in_pos = long_amt > 0
    bm = None
    if len(g.near_rets) >= g.lookback and len(g.far_rets) >= g.lookback:
        bm = _prod_m1(g.near_rets[-g.lookback :]) - _prod_m1(g.far_rets[-g.lookback :])
    target = 1 if (bm is not None and bm > 0) else 0
    allow = (not in_pos) or g.bars_held >= g.hold_bars or (
        g.flatten_on_negative_bm and in_pos and target == 0
    )
    if not allow:
        g.bars_held += 1
        g.held_contract = contract
        _rotate_legs(contract)
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
    _rotate_legs(contract)
    log.info('FQ-003-v2 %s bm=%s tgt=%s far=%s' % (contract, bm, target, g.pending_far))


def _rotate_legs(today_near):
    g.roll_near = g.pending_near
    g.near_px = _close_of(g.roll_near) if g.roll_near else None
    g.pending_near = today_near
    g.roll_far = g.pending_far
    g.far_px = _close_of(g.roll_far) if g.roll_far else None
    g.pending_far = _next_liquid(today_near)
