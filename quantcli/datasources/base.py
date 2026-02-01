"""数据源抽象接口

设计原则：
- 统一返回类型（统一返回 DataFrame）
- 简洁的接口定义
- 缓存逻辑统一由 Mixin 处理
"""

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Protocol, runtime_checkable
from dataclasses import dataclass
import pandas as pd


@dataclass
class DataRequest:
    """数据请求参数"""
    start_date: date
    end_date: date
    symbols: Optional[List[str]] = None
    fields: Optional[List[str]] = None
    freq: str = "daily"


@dataclass
class StockInfo:
    """股票基本信息"""
    symbol: str
    name: str
    exchange: str  # "SSE" | "SZSE"
    market: str    # "上海" | "深圳"
    list_date: Optional[date] = None
    delist_date: Optional[date] = None
    status: str = "active"


@dataclass
class DataSourceConfig:
    """数据源配置"""
    name: str
    use_cache: bool = True
    cache_dir: Optional[str] = None


@runtime_checkable
class PriceDataSource(Protocol):
    """价格数据源接口"""

    @abstractmethod
    def get_daily(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """获取日线数据

        Returns:
            DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume', 'amount'])
        """
        ...

    @abstractmethod
    def get_index_daily(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """获取指数日线

        Returns:
            DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        """
        ...

    @abstractmethod
    def get_intraday(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        period: str = "5"
    ) -> pd.DataFrame:
        """获取分钟级数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            period: 分钟周期 ("1", "5", "15", "30", "60")

        Returns:
            DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        """
        ...


@runtime_checkable
class StockListSource(Protocol):
    """股票列表接口"""

    @abstractmethod
    def get_stock_list(self, market: str = "all") -> pd.DataFrame:
        """获取股票列表

        Args:
            market: "all" | "上海" | "深圳"

        Returns:
            DataFrame(columns=['symbol', 'name', 'exchange', 'market'])
        """
        ...

    @abstractmethod
    def get_trading_calendar(self, exchange: str = "SSE") -> List[date]:
        """获取交易日历"""
        ...


@runtime_checkable
class FundamentalSource(Protocol):
    """基本面数据接口"""

    @abstractmethod
    def get_fundamental(
        self,
        symbols: List[str],
        date: date
    ) -> pd.DataFrame:
        """获取基本面数据

        Returns:
            DataFrame(columns=['symbol', 'roe', 'netprofitmargin', ...])
        """
        ...

    @abstractmethod
    def get_dupont_analysis(
        self,
        symbols: List[str],
        start_year: int,
        end_year: int
    ) -> pd.DataFrame:
        """获取杜邦分析"""
        ...


class DataSource(ABC):
    """数据源基类（推荐使用 Protocol 定义接口）"""

    name: str = "base"
    config: DataSourceConfig

    def __init__(self, config: Optional[DataSourceConfig] = None):
        self.config = config or DataSourceConfig(name=self.name)

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "status": "ok",
            "source": self.name,
            "timestamp": datetime.now().isoformat(),
            "config": {
                "use_cache": self.config.use_cache,
            }
        }


class CachedDataSourceMixin:
    """缓存 Mixin - 自动为数据源添加缓存支持

    使用方法:
        class MyDataSource(CachedDataSourceMixin, DataSource):
            def get_daily(self, symbol, start, end):
                # 1. 先检查缓存
                cached = self._get_cache(f"daily_{symbol}_{start}_{end}")
                if cached is not None:
                    return cached

                # 2. 从 API 获取
                df = self._fetch_from_api(symbol, start, end)

                # 3. 写入缓存
                self._set_cache(f"daily_{symbol}_{start}_{end}", df)
                return df
    """

    def _get_cache(self, key: str) -> Optional[pd.DataFrame]:
        """读取缓存（子类实现）"""
        raise NotImplementedError

    def _set_cache(self, key: str, df: pd.DataFrame) -> None:
        """写入缓存（子类实现）"""
        raise NotImplementedError

    def _clear_cache(self, pattern: str = "*") -> int:
        """清理缓存（子类实现）"""
        raise NotImplementedError


def create_datasource(name: str, **kwargs) -> DataSource:
    """工厂函数: 创建数据源实例"""
    sources = {
        "akshare": "quantcli.datasources.akshare:AkshareDataSource",
        "baostock": "quantcli.datasources.baostock:BaostockDataSource",
        "mixed": "quantcli.datasources.mixed:MixedDataSource",
        "mysql": "quantcli.datasources.mysql:MySQLDataSource",
    }

    if name not in sources:
        raise ValueError(f"Unknown data source: {name}. Available: {list(sources.keys())}")

    # 动态导入
    module_path, class_name = sources[name].split(":")
    from importlib import import_module
    module = import_module(module_path)
    cls = getattr(module, class_name)

    return cls(**kwargs)
