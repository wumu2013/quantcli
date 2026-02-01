"""Parser constants and built-in functions"""

# Builtin functions used in formula expressions
BUILTIN_FUNCTIONS = frozenset({
    'ma', 'ema', 'delay', 'zscore', 'rank', 'where', 'if',
    'abs', 'sign', 'clamp', 'max', 'rolling_std', 'rolling_sum',
    'correlation', 'cross_up', 'cross_down', 'sma', 'sgn',
    'rolling_max', 'rolling_min', 'rolling_mean',
    'ts_argmax', 'ts_argmin',
    # Alpha101 functions
    'ts_rank', 'ts_ave', 'ts_sum', 'ts_min', 'ts_max',
    'ts_decayexp', 'signed_power',
})

# Column name aliases for fundamental data
COLUMN_ALIASES = {
    # User-friendly -> Actual column names
    "roe": "roe",
    "pe": "pe",
    "pb": "pb",
    # Profit margins
    "netprofitmargin": "net_profit_margin",
    "grossprofitmargin": "gross_profit_margin",
    "net_profit_margin": "net_profit_margin",
    "gross_profit_margin": "gross_profit_margin",
    # Baostock column names (common aliases)
    "debt_to_assets": "asset_equity_ratio",  # 资产负债率
    "asset_equity_ratio": "asset_equity_ratio",
}
