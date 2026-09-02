# 聚宽期货策略初始化模板。复制后改品种与逻辑，不要另起一套账户设置。
# 本文件不能直接跑；真正下单的代码在 strategies/FQ-NNN-*/strategy.py。


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
    run_daily(rebalance, time='09:05', reference_security='C9999.XDCE')


def process_initialize(context):
    pass


def rebalance(context):
    contract = get_dominant_future('C')
    if not contract:
        return
    # 下单只用 contract，不用 C9999.XDCE
    pass
