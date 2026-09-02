# FQ-001 玉米 20 日时间序列动量
# 粘贴到聚宽研究/策略。不要对 C9999.XDCE 下单。


def initialize(context):
    set_option('use_real_price', True)
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
    g.lots = 1
    g.stop_frac = 0.02
    g.cooldown_bars = 5
    g.cooldown_left = 0
    g.held_contract = None

    run_daily(rebalance, time='09:05', reference_security=g.ref)


def process_initialize(context):
    pass


def _amount(positions, contract):
    if contract in positions:
        return positions[contract].total_amount
    return 0


def _pnl(positions, contract):
    if contract in positions:
        return positions[contract].pnl
    return 0


def flatten(contract):
    order_target(contract, 0, side='long')
    order_target(contract, 0, side='short')


def set_one_lot(contract, direction):
    if direction > 0:
        order_target(contract, 0, side='short')
        order_target(contract, g.lots, side='long')
    elif direction < 0:
        order_target(contract, 0, side='long')
        order_target(contract, g.lots, side='short')
    else:
        flatten(contract)


def rebalance(context):
    contract = get_dominant_future(g.underlying)
    if not contract:
        log.info('FQ-001 no dominant contract')
        return

    if g.held_contract and g.held_contract != contract:
        log.info('FQ-001 roll %s -> %s' % (g.held_contract, contract))
        flatten(g.held_contract)
        g.held_contract = contract

    if g.cooldown_left > 0:
        flatten(contract)
        g.held_contract = contract
        g.cooldown_left -= 1
        log.info('FQ-001 cooldown left %s' % g.cooldown_left)
        return

    long_amt = _amount(context.portfolio.long_positions, contract)
    short_amt = _amount(context.portfolio.short_positions, contract)
    pos_pnl = _pnl(context.portfolio.long_positions, contract) + _pnl(
        context.portfolio.short_positions, contract
    )
    equity = context.portfolio.total_value
    if (long_amt > 0 or short_amt > 0) and equity > 0 and pos_pnl < -g.stop_frac * equity:
        log.info('FQ-001 stop pnl=%s equity=%s' % (pos_pnl, equity))
        flatten(contract)
        g.held_contract = contract
        g.cooldown_left = g.cooldown_bars
        return

    hist = attribute_history(
        contract,
        g.lookback + 1,
        '1d',
        ['close'],
        skip_paused=True,
        df=True,
    )
    if hist is None or len(hist) < g.lookback + 1:
        log.info('FQ-001 not enough bars on %s' % contract)
        return

    closes = hist['close'].values
    if closes[0] == 0:
        return
    past_ret = closes[-1] / closes[0] - 1.0
    if past_ret > 0:
        direction = 1
    elif past_ret < 0:
        direction = -1
    else:
        direction = 0

    set_one_lot(contract, direction)
    g.held_contract = contract
    log.info('FQ-001 %s ret=%s dir=%s' % (contract, past_ret, direction))
