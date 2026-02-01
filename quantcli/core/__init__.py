"""核心模块 - 因子计算、回测引擎、数据管理

Modules:
- data: 数据获取、缓存、清洗
- factor: 因子计算引擎
- backtest: 回测引擎 (基于 Backtrader)
"""

from .data import (
    DataManager,
    DataConfig,
    DataQualityReport,
)

from .factor import (
    FactorEngine,
    Factor,
    FactorEvaluation,
    FactorRegistry,
)

from .backtest import (
    BacktestEngine,
    BacktestConfig,
    BacktestResult,
    Strategy,
    Trade,
    quick_backtest,
    run_from_dm,
)

__all__ = [
    # Data
    "DataManager",
    "DataConfig",
    "DataQualityReport",
    # Factor
    "FactorEngine",
    "Factor",
    "FactorEvaluation",
    "FactorRegistry",
    # Backtest
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "Strategy",
    "Trade",
    "quick_backtest",
    "run_from_dm",
]
