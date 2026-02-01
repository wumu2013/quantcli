"""混合数据源 - 自动选择最稳定的接口

设计原则：
- 日线数据：akshare (腾讯接口)
- 股票列表：akshare (stock_info_a_code_name)
- 交易日历：akshare (新浪接口)
- 指数数据：akshare (腾讯接口)
- 基本面数据：baostock

使用示例：
    >>> ds = create_datasource("mixed")  # 或直接使用 MixedDataSource
    >>> # 行情数据
    >>> df = ds.get_daily("600519", date(2024,1,1), date(2024,1,31))
    >>> # 基本面数据
    >>> df = ds.get_fundamental(["600519"], date(2024,1,31))
"""

from datetime import date
from typing import List, Optional, Dict, Any
import pandas as pd

from ..utils import get_logger
from .base import DataSource, DataSourceConfig

logger = get_logger(__name__)


class MixedDataSource(DataSource):
    """混合数据源 - 自动选择最稳定的接口

    整合多个数据源的优势：
    - akshare: 行情数据 (腾讯/东方财富稳定接口)
    - baostock: 基本面数据 (杜邦分析、利润表等)
    """

    name = "mixed"

    def __init__(self, prefer_baostock: bool = True, use_cache: bool = True):
        """初始化混合数据源

        Args:
            prefer_baostock: 基本面数据是否优先使用 baostock
            use_cache: 是否使用缓存
        """
        super().__init__(DataSourceConfig(name=self.name, use_cache=use_cache))
        self._prefer_baostock = prefer_baostock
        self._init_data_sources()

    def _init_data_sources(self):
        """初始化底层数据源"""
        from .akshare import AkshareDataSource
        from .baostock import BaostockDataSource

        self._akshare = AkshareDataSource(use_cache=self.config.use_cache)
        self._baostock = BaostockDataSource(use_cache=self.config.use_cache)

    # ==================== 价格数据 (akshare) ====================

    def get_daily(
        self,
        symbol: str,
        start_date,
        end_date,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取日线数据 (akshare 腾讯接口)"""
        return self._akshare.get_daily(symbol, start_date, end_date, fields)

    def get_index_daily(
        self,
        symbol: str,
        start_date,
        end_date
    ) -> pd.DataFrame:
        """获取指数日线数据 (akshare 腾讯接口)"""
        return self._akshare.get_index_daily(symbol, start_date, end_date)

    # ==================== 股票列表和日历 (akshare) ====================

    def get_stock_list(self, market: str = "all") -> pd.DataFrame:
        """获取股票列表

        Returns:
            DataFrame(columns=['symbol', 'name', 'exchange', 'market'])
        """
        return self._akshare.get_stock_list(market)

    def get_trading_calendar(self, exchange: str = "SSE") -> List[date]:
        """获取交易日历"""
        return self._akshare.get_trading_calendar(exchange)

    # ==================== 基本面数据 (baostock) ====================

    def get_fundamental(
        self,
        symbols: List[str],
        date,
        indicators: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取基本面数据 (baostock)"""
        df = self._baostock.get_dupont_analysis(symbols)
        if df.empty:
            return df
        return df.groupby("symbol").last().reset_index()

    def get_dupont_analysis(
        self,
        symbols: List[str],
        start_year: int = 2022,
        end_year: int = 2024
    ) -> pd.DataFrame:
        """获取杜邦分析数据 (baostock)"""
        return self._baostock.get_dupont_analysis(symbols, start_year, end_year)

    def get_profit_data(
        self,
        symbols: List[str],
        start_year: int = 2022,
        end_year: int = 2024
    ) -> pd.DataFrame:
        """获取利润表数据 (baostock)"""
        return self._baostock.get_profit_data(symbols, start_year, end_year)

    def get_growth_data(
        self,
        symbols: List[str],
        start_year: int = 2022,
        end_year: int = 2024
    ) -> pd.DataFrame:
        """获取成长能力数据 (baostock)"""
        return self._baostock.get_growth_data(symbols, start_year, end_year)

    def get_intraday(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        period: str = "5"
    ) -> pd.DataFrame:
        """获取分钟级数据 (akshare)"""
        return self._akshare.get_intraday(symbol, start_date, end_date, period)

    # ==================== 辅助方法 ====================

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        results = {"status": "ok", "source": self.name, "components": {}}

        for name, ds in [("akshare", self._akshare), ("baostock", self._baostock)]:
            try:
                health = ds.health_check()
                results["components"][name] = health["status"]
            except Exception as e:
                results["components"][name] = f"error: {e}"

        if any("error" in str(v) for v in results["components"].values()):
            results["status"] = "degraded"

        return results

    def get_data_summary(self) -> Dict[str, Any]:
        """获取数据源摘要"""
        return {
            "name": self.name,
            "price_data": {"source": "akshare", "interface": "stock_zh_a_hist_tx"},
            "stock_list": {"source": "akshare", "interface": "stock_info_a_code_name"},
            "fundamental_data": {"source": "baostock"},
        }


# 便捷工厂函数
def create_mixed_datasource(**kwargs) -> MixedDataSource:
    """创建混合数据源实例"""
    return MixedDataSource(**kwargs)
