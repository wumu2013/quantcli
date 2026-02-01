"""数据源模块

支持多个数据源的适配器，包括:
- akshare: 免费财经数据接口 (使用腾讯/新浪接口，优先日线/股票列表/交易日历)
- baostock: 东方财富Baostock (稳定，适合批量下载基本面数据)
- mixed: 混合数据源 (自动选择最稳定的接口，整合 akshare 和 baostock)

缓存:
- DataSourceCache: 通用数据源缓存 (Parquet 格式)
- FundamentalsCache: 基本面数据专用缓存 (24h TTL)

数据同步 (sync):
- create_sync: 工厂函数，创建数据同步器
- GmSync: 掘金量化数据同步器
"""

from .base import DataSource, StockInfo, DataRequest
from .akshare import AkshareDataSource
from .baostock import BaostockDataSource
from .mixed import MixedDataSource, create_mixed_datasource
from .mysql import MySQLDataSource
from .cache import (
    DataSourceCache,
    FundamentalsCache,
    PriceCache,
    StockListCache,
    TradingCalendarCache,
    make_cache_key,
)
from .sync import create_sync, GmSync, DataSync

__all__ = [
    # 数据源
    "DataSource",
    "StockInfo",
    "DataRequest",
    "AkshareDataSource",
    "BaostockDataSource",
    "MixedDataSource",
    "MySQLDataSource",
    "create_mixed_datasource",
    # 缓存
    "DataSourceCache",
    "FundamentalsCache",
    "PriceCache",
    "StockListCache",
    "TradingCalendarCache",
    "make_cache_key",
    # 数据同步
    "DataSync",
    "GmSync",
    "create_sync",
]


def create_datasource(name: str, **kwargs) -> DataSource:
    """工厂函数: 创建数据源实例

    Args:
        name: 数据源名称 ("akshare", "baostock", "mixed", "mysql")
        **kwargs: 额外配置参数

    Returns:
        DataSource 实例

    Examples:
        >>> # 日常行情数据
        >>> ds = create_datasource("akshare")
        >>> df = ds.get_daily("600519", date(2020,1,1), date(2024,1,1))

        >>> # 基本面数据使用 baostock
        >>> ds = create_datasource("baostock")
        >>> df = ds.get_dupont_analysis(["600519", "000001"])

        >>> # 混合模式 - 一个数据源搞定所有
        >>> ds = create_datasource("mixed")

        >>> # MySQL 数据源（回测推荐）
        >>> ds = create_datasource("mysql")
    """
    sources = {
        "akshare": AkshareDataSource,
        "baostock": BaostockDataSource,
        "mixed": MixedDataSource,
        "mysql": MySQLDataSource,
    }

    if name not in sources:
        raise ValueError(
            f"Unknown data source: {name}. "
            f"Available: {list(sources.keys())}"
        )

    return sources[name](**kwargs)
