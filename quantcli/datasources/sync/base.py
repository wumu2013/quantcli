"""数据同步抽象基类

定义统一的同步接口，支持从任意数据源同步数据到 MySQL。
"""

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import List, Dict, Optional, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from quantcli.datasources.mysql import MySQLDataSource


class DataSync(ABC):
    """数据同步基类

    设计原则:
    - 策略模式：支持不同数据源的实现
    - 增量同步：自动从上次截止日期开始同步
    - 幂等写入：使用 ON DUPLICATE KEY UPDATE 避免重复
    """

    name: str = "base"

    def __init__(self, token: str = None, mysql: "MySQLDataSource" = None):
        """初始化同步器

        Args:
            token: API token (部分数据源需要)
            mysql: MySQLDataSource 实例，传入 None 则自动创建
        """
        self._token = token
        if mysql is None:
            from ..mysql import MySQLDataSource
            mysql = MySQLDataSource()
        self._mysql = mysql

    @property
    def mysql(self) -> "MySQLDataSource":
        """获取 MySQL 数据源"""
        return self._mysql

    # ==================== 抽象方法 ====================

    @abstractmethod
    def sync_daily(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date = None
    ) -> Dict[str, int]:
        """同步日线数据

        Args:
            symbols: 股票代码列表
            start_date: 开始日期（如果已有数据，则从最新日期开始）
            end_date: 结束日期，默认到昨天

        Returns:
            {"symbol": records_count, ...}
        """

    @abstractmethod
    def sync_minute(
        self,
        symbols: List[str],
        period: str,
        start_date: date,
        end_date: date = None
    ) -> Dict[str, int]:
        """同步分钟线数据

        Args:
            symbols: 股票代码列表
            period: 分钟周期 ("1", "5", "15", "30", "60")
            start_date: 开始日期
            end_date: 结束日期，默认到昨天

        Returns:
            {"symbol": records_count, ...}
        """

    @abstractmethod
    def sync_fundamental(
        self,
        symbols: List[str],
        report_date: date = None
    ) -> Dict[str, int]:
        """同步基本面数据

        Args:
            symbols: 股票代码列表
            report_date: 报表日期，默认最新

        Returns:
            {"symbol": records_count, ...}
        """

    @abstractmethod
    def get_progress(self, symbol: str) -> Optional[date]:
        """获取同步进度（最新日期）

        Args:
            symbol: 股票代码

        Returns:
            最新同步日期，未同步过则返回 None
        """

    # ==================== 辅助方法 ====================

    def _adjust_start_date(
        self,
        symbol: str,
        table: str,
        start_date: date
    ) -> date:
        """调整开始日期，实现增量同步

        Args:
            symbol: 股票代码
            table: 表名
            start_date: 用户指定的开始日期

        Returns:
            实际的开始日期（取用户指定和最新已有日期的较大值）
        """
        latest = self.get_progress(symbol)
        if latest and latest >= start_date:
            # 日期 +1，从下一天开始
            from datetime import timedelta
            return latest + timedelta(days=1)
        return start_date

    def _get_daily_table(self) -> str:
        """获取日线表名"""
        return self._mysql._table("daily_prices")

    def _get_minute_table(self) -> str:
        """获取分钟线表名"""
        return self._mysql._table("intraday_prices")

    def _get_fundamental_table(self) -> str:
        """获取基本面表名"""
        return self._mysql._table("fundamental_data")


# ==================== 工厂函数 ====================

def create_sync(source: str, token: str = None) -> DataSync:
    """创建同步器

    Args:
        source: 数据源名称 ("gm", "akshare", "baostock")
        token: API token (部分数据源需要)

    Returns:
        DataSync 实例

    Raises:
        ValueError: 不支持的数据源
    """
    source = source.lower()

    if source == "gm":
        from .gm import GmSync
        return GmSync(token=token)

    elif source == "akshare":
        from .akshare import AkshareSync
        return AkshareSync(token=token)

    elif source == "baostock":
        from .baostock import BaostockSync
        return BaostockSync(token=token)

    else:
        raise ValueError(f"Unsupported sync source: {source}. "
                         f"Supported: gm, akshare, baostock")
