"""公式解析模块

支持解析因子表达式并计算因子值。

Usage:
    >>> from quantcli.parser import Formula, compute_factor
    >>> formula = Formula("(close / delay(close, 20)) - 1")
    >>> result = formula.compute(df)
"""

from .formula import (
    Formula,
    FormulaError,
    compute_factor,
    batch_compute,
    # 内置函数
    delay,
    ma,
    ema,
    wma,
    rolling_std,
    rolling_sum,
    rolling_mean,
    rolling_max,
    rolling_min,
    rank,
    zscore,
    quantile,
    correlation,
    covariance,
    regression,
    # 技术指标
    rsi,
    macd,
    bollinger_bands,
    stoch,
    atr,
    # 事件
    cross_up,
    cross_down,
    breakout_high,
    breakout_low,
    # 条件
    where,
    if_,
    # 数学函数
    abs_val,
    sign,
    clamp,
)

__all__ = [
    "Formula",
    "FormulaError",
    "compute_factor",
    "batch_compute",
    # 内置函数
    "delay", "ma", "ema", "wma",
    "rolling_std", "rolling_sum", "rolling_mean", "rolling_max", "rolling_min",
    "rank", "zscore", "quantile",
    "correlation", "covariance", "regression",
    # 技术指标
    "rsi", "macd", "bollinger_bands", "stoch", "atr",
    # 事件
    "cross_up", "cross_down", "breakout_high", "breakout_low",
    # 条件
    "where", "if_",
    # 数学函数
    "abs_val", "sign", "clamp",
]
