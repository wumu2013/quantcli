"""MySQL 数据源 - 基于数据库的回测数据源

设计目标：
- 快速查询：支持索引，按股票代码和日期范围高效查询
- 数据同步：从 akshare/baostock 同步数据到 MySQL
- 回测友好：支持批量读取多只股票数据

表结构：
- daily_prices: 日线数据
- stock_list: 股票列表
- trading_calendar: 交易日历
- fundamental_data: 基本面数据

使用示例：
    >>> ds = create_datasource("mysql")
    >>> df = ds.get_daily("600519", date(2024,1,1), date(2024,1,31))
    >>> ds.sync_from_akshare()  # 从 akshare 同步数据
"""

import os
from datetime import date, datetime
from typing import List, Optional, Dict, Any
import pandas as pd

from ..utils import get_logger, format_date
from .base import DataSource, DataSourceConfig

logger = get_logger(__name__)


class MySQLDataSource(DataSource):
    """MySQL 数据源 - 基于数据库的回测数据源"""

    name = "mysql"

    # 默认连接配置
    DEFAULT_CONFIG = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "quantcli"),
        "table_prefix": os.getenv("MYSQL_TABLE_PREFIX", ""),
    }

    def __init__(
        self,
        host: str = None,
        port: int = None,
        user: str = None,
        password: str = None,
        database: str = None,
        table_prefix: str = None,
        use_cache: bool = False,
        autocommit: bool = True,
    ):
        """初始化 MySQL 数据源

        Args:
            host: MySQL 主机地址
            port: MySQL 端口
            user: 用户名
            password: 密码
            database: 数据库名
            table_prefix: 表前缀（用于区分不同项目的数据）
            use_cache: 是否使用缓存（对数据库源通常不需要）
            autocommit: 是否自动提交
        """
        config_dict = {
            "host": host or self.DEFAULT_CONFIG["host"],
            "port": port or self.DEFAULT_CONFIG["port"],
            "user": user or self.DEFAULT_CONFIG["user"],
            "password": password or self.DEFAULT_CONFIG["password"],
            "database": database or self.DEFAULT_CONFIG["database"],
            "table_prefix": table_prefix or self.DEFAULT_CONFIG["table_prefix"],
        }
        super().__init__(DataSourceConfig(name=self.name, use_cache=use_cache))

        self._config = config_dict
        self._prefix = config_dict["table_prefix"]
        self._autocommit = autocommit
        self._conn = None

        # 初始化数据库表
        self._init_tables()

    def _get_connection(self):
        """获取数据库连接"""
        if self._conn is None or not self._conn.open:
            import pymysql
            self._conn = pymysql.connect(
                host=self._config["host"],
                port=self._config["port"],
                user=self._config["user"],
                password=self._config["password"],
                database=self._config["database"],
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=self._autocommit,
            )
        return self._conn

    def _table(self, name: str) -> str:
        """获取带前缀的表名"""
        return f"{self._prefix}{name}"

    def _init_tables(self):
        """初始化数据库表"""
        conn = self._get_connection()
        tables = {
            self._table("daily_prices"): """
                CREATE TABLE IF NOT EXISTS {table} (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    trade_date DATE NOT NULL,
                    open DECIMAL(10, 2),
                    high DECIMAL(10, 2),
                    low DECIMAL(10, 2),
                    close DECIMAL(10, 2),
                    volume BIGINT,
                    amount DECIMAL(20, 2),
                    UNIQUE KEY uk_symbol_date (symbol, trade_date),
                    INDEX idx_symbol (symbol),
                    INDEX idx_trade_date (trade_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            self._table("stock_list"): """
                CREATE TABLE IF NOT EXISTS {table} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL UNIQUE,
                    name VARCHAR(100),
                    exchange VARCHAR(10),
                    market VARCHAR(20),
                    list_date DATE,
                    status VARCHAR(20) DEFAULT 'active',
                    INDEX idx_exchange (exchange),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            self._table("trading_calendar"): """
                CREATE TABLE IF NOT EXISTS {table} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    trade_date DATE NOT NULL UNIQUE,
                    exchange VARCHAR(10),
                    is_trading_day TINYINT(1) DEFAULT 1,
                    INDEX idx_exchange_date (exchange, trade_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            self._table("fundamental_data"): """
                CREATE TABLE IF NOT EXISTS {table} (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    report_date DATE NOT NULL,
                    roe DECIMAL(10, 4),
                    netprofitmargin DECIMAL(10, 4),
                    grossprofitmargin DECIMAL(10, 4),
                    pe_ttm DECIMAL(10, 2),
                    pb DECIMAL(10, 2),
                    UNIQUE KEY uk_symbol_date (symbol, report_date),
                    INDEX idx_symbol (symbol),
                    INDEX idx_report_date (report_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            self._table("intraday_prices"): """
                CREATE TABLE IF NOT EXISTS {table} (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    trade_date DATE NOT NULL,
                    trade_time TIME NOT NULL,
                    period VARCHAR(10) NOT NULL COMMENT '周期: 1min/5min/15min/30min/60min',
                    open DECIMAL(10, 2),
                    high DECIMAL(10, 2),
                    low DECIMAL(10, 2),
                    close DECIMAL(10, 2),
                    volume BIGINT,
                    amount DECIMAL(20, 2),
                    UNIQUE KEY uk_symbol_datetime_period (symbol, trade_date, trade_time, period),
                    INDEX idx_symbol (symbol),
                    INDEX idx_date_period (trade_date, period)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        }

        with conn.cursor() as cursor:
            for table_name, sql in tables.items():
                try:
                    cursor.execute(sql.format(table=table_name))
                    logger.info(f"Table {table_name} ready")
                except Exception as e:
                    logger.warning(f"Failed to create table {table_name}: {e}")

    # ==================== 价格数据 ====================

    def get_daily(
        self,
        symbol: str,
        start_date,
        end_date,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取日线数据"""
        conn = self._get_connection()
        start_str = format_date(start_date, "%Y-%m-%d")
        end_str = format_date(end_date, "%Y-%m-%d")

        sql = f"""
            SELECT symbol, trade_date, open, high, low, close, volume, amount
            FROM {self._table('daily_prices')}
            WHERE symbol = %s AND trade_date BETWEEN %s AND %s
            ORDER BY trade_date
        """

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (symbol, start_str, end_str))
                rows = cursor.fetchall()

            if not rows:
                return pd.DataFrame(columns=['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount'])

            df = pd.DataFrame(rows)
            df = df.rename(columns={
                'trade_date': 'date',
                'amount': 'amount'
            })
            df['date'] = pd.to_datetime(df['date']).dt.date
            return df
        except Exception as e:
            logger.error(f"Failed to get daily data: {e}")
            return pd.DataFrame(columns=['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount'])

    def get_multi_daily(
        self,
        symbols: List[str],
        start_date,
        end_date
    ) -> Dict[str, pd.DataFrame]:
        """批量获取多只股票的日线数据（回测优化）"""
        if not symbols:
            return {}

        conn = self._get_connection()
        start_str = format_date(start_date, "%Y-%m-%d")
        end_str = format_date(end_date, "%Y-%m-%d")

        placeholders = ",".join(["%s"] * len(symbols))
        sql = f"""
            SELECT symbol, trade_date, open, high, low, close, volume, amount
            FROM {self._table('daily_prices')}
            WHERE symbol IN ({placeholders}) AND trade_date BETWEEN %s AND %s
            ORDER BY symbol, trade_date
        """

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(symbols) + (start_str, end_str))
                rows = cursor.fetchall()

            # 按股票分组
            result = {}
            df = pd.DataFrame(rows)
            if not df.empty:
                df = df.rename(columns={'trade_date': 'date'})
                df['date'] = pd.to_datetime(df['date']).dt.date
                for symbol in symbols:
                    symbol_df = df[df['symbol'] == symbol].copy()
                    if not symbol_df.empty:
                        result[symbol] = symbol_df

            return result
        except Exception as e:
            logger.error(f"Failed to get multi daily data: {e}")
            return {}

    def get_index_daily(
        self,
        symbol: str,
        start_date,
        end_date
    ) -> pd.DataFrame:
        """获取指数日线数据"""
        # 指数也存储在 daily_prices 表中
        return self.get_daily(symbol, start_date, end_date)

    # ==================== 分钟级数据 ====================

    def get_intraday(
        self,
        symbol: str,
        start_date: date = None,
        end_date: date = None,
        period: str = "5"
    ) -> pd.DataFrame:
        """获取分钟级数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            period: 分钟周期 ("1", "5", "15", "30", "60")

        Returns:
            DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume', 'amount'])
        """
        conn = self._get_connection()

        # 默认范围：最近 5 个交易日
        from datetime import timedelta
        if end_date is None:
            end_date = date.today() - timedelta(1)
        if start_date is None:
            start_date = end_date - timedelta(10)

        start_str = format_date(start_date, "%Y-%m-%d")
        end_str = format_date(end_date, "%Y-%m-%d")

        sql = f"""
            SELECT symbol, trade_date, trade_time, period,
                   open, high, low, close, volume, amount
            FROM {self._table('intraday_prices')}
            WHERE symbol = %s AND trade_date BETWEEN %s AND %s AND period = %s
            ORDER BY trade_date, trade_time
        """

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (symbol, start_str, end_str, period))
                rows = cursor.fetchall()

            if not rows:
                return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume', 'amount'])

            df = pd.DataFrame(rows)
            # 合并日期和时间
            df['datetime'] = pd.to_datetime(df['trade_date'].astype(str) + ' ' + df['trade_time'].astype(str))
            df = df.rename(columns={'datetime': 'date'})
            df = df.drop(columns=['trade_date', 'trade_time', 'period', 'symbol'])

            return df[['date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        except Exception as e:
            logger.error(f"Failed to get intraday data: {e}")
            return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume', 'amount'])

    def get_multi_intraday(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date,
        period: str = "5"
    ) -> Dict[str, pd.DataFrame]:
        """批量获取多只股票的分钟级数据（回测优化）"""
        if not symbols:
            return {}

        conn = self._get_connection()
        start_str = format_date(start_date, "%Y-%m-%d")
        end_str = format_date(end_date, "%Y-%m-%d")

        placeholders = ",".join(["%s"] * len(symbols))
        sql = f"""
            SELECT symbol, trade_date, trade_time, period,
                   open, high, low, close, volume, amount
            FROM {self._table('intraday_prices')}
            WHERE symbol IN ({placeholders}) AND trade_date BETWEEN %s AND %s AND period = %s
            ORDER BY symbol, trade_date, trade_time
        """

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(symbols) + (start_str, end_str, period))
                rows = cursor.fetchall()

            result = {}
            df = pd.DataFrame(rows)
            if not df.empty:
                df['datetime'] = pd.to_datetime(df['trade_date'].astype(str) + ' ' + df['trade_time'].astype(str))
                df = df.rename(columns={'datetime': 'date'})
                for symbol in symbols:
                    symbol_df = df[df['symbol'] == symbol].copy()
                    if not symbol_df.empty:
                        symbol_df = symbol_df.drop(columns=['trade_date', 'trade_time', 'period', 'symbol'])
                        result[symbol] = symbol_df[['date', 'open', 'high', 'low', 'close', 'volume', 'amount']]

            return result
        except Exception as e:
            logger.error(f"Failed to get multi intraday data: {e}")
            return {}

    def sync_intraday_from_akshare(
        self,
        symbol: str,
        start_date: date = None,
        end_date: date = None,
        period: str = "5"
    ):
        """从 akshare 同步分钟级数据到 MySQL

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            period: 分钟周期 ("1", "5", "15", "30", "60")
        """
        from .akshare import AkshareDataSource
        from datetime import timedelta

        akshare = AkshareDataSource(use_cache=True)

        if end_date is None:
            end_date = date.today() - timedelta(1)
        if start_date is None:
            start_date = end_date - timedelta(5)

        df = akshare.get_intraday(symbol, start_date, end_date, period)

        if df.empty:
            logger.warning(f"No intraday data for {symbol}")
            return

        conn = self._get_connection()
        with conn.cursor() as cursor:
            for _, row in df.iterrows():
                # 解析日期时间
                dt = pd.to_datetime(row['date'])
                trade_date = dt.date()
                trade_time = dt.time()

                cursor.execute(f"""
                    INSERT INTO {self._table('intraday_prices')}
                    (symbol, trade_date, trade_time, period, open, high, low, close, volume, amount)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    open = VALUES(open),
                    high = VALUES(high),
                    low = VALUES(low),
                    close = VALUES(close),
                    volume = VALUES(volume),
                    amount = VALUES(amount)
                """, (
                    symbol,
                    trade_date,
                    trade_time,
                    period,
                    row['open'],
                    row['high'],
                    row['low'],
                    row['close'],
                    row.get('volume', 0),
                    row.get('amount', 0)
                ))

        logger.info(f"Synced {len(df)} intraday records for {symbol}")

    # ==================== 股票列表和日历 ====================

    def get_stock_list(self, market: str = "all") -> pd.DataFrame:
        """获取股票列表"""
        conn = self._get_connection()

        sql = f"SELECT symbol, name, exchange, market, list_date, status FROM {self._table('stock_list')}"
        params = []

        if market == "上海":
            sql += " WHERE exchange = 'SSE'"
        elif market == "深圳":
            sql += " WHERE exchange = 'SZSE'"

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params) if params else None)
                rows = cursor.fetchall()

            df = pd.DataFrame(rows)
            if df.empty:
                return pd.DataFrame(columns=['symbol', 'name', 'exchange', 'market', 'list_date', 'status'])
            return df
        except Exception as e:
            logger.error(f"Failed to get stock list: {e}")
            return pd.DataFrame(columns=['symbol', 'name', 'exchange', 'market', 'list_date', 'status'])

    def get_trading_calendar(self, exchange: str = "SSE") -> List[date]:
        """获取交易日历"""
        conn = self._get_connection()

        sql = f"""
            SELECT trade_date FROM {self._table('trading_calendar')}
            WHERE exchange = %s AND is_trading_day = 1
            ORDER BY trade_date
        """

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (exchange,))
                rows = cursor.fetchall()

            return [row['trade_date'] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get trading calendar: {e}")
            return []

    # ==================== 基本面数据 ====================

    def get_fundamental(
        self,
        symbols: List[str],
        date,
        indicators: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取基本面数据"""
        conn = self._get_connection()
        date_str = format_date(date, "%Y-%m-%d")

        placeholders = ",".join(["%s"] * len(symbols))
        sql = f"""
            SELECT symbol, report_date, roe, netprofitmargin, grossprofitmargin, pe_ttm, pb
            FROM {self._table('fundamental_data')}
            WHERE symbol IN ({placeholders}) AND report_date <= %s
            ORDER BY symbol, report_date DESC
        """

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(symbols) + (date_str,))
                rows = cursor.fetchall()

            if not rows:
                return pd.DataFrame(columns=['symbol', 'report_date', 'roe', 'netprofitmargin', 'grossprofitmargin', 'pe_ttm', 'pb'])

            # 取每个股票的最新数据
            df = pd.DataFrame(rows)
            df = df.groupby('symbol').first().reset_index()
            return df
        except Exception as e:
            logger.error(f"Failed to get fundamental data: {e}")
            return pd.DataFrame(columns=['symbol', 'report_date', 'roe', 'netprofitmargin', 'grossprofitmargin', 'pe_ttm', 'pb'])

    # ==================== 数据同步 ====================

    def sync_from_akshare(self, start_date: date = None, end_date: date = None, symbols: List[str] = None):
        """从 akshare 同步日线数据到 MySQL

        Args:
            start_date: 开始日期（默认从 2020-01-01 开始）
            end_date: 结束日期（默认到昨天）
            symbols: 股票列表（默认同步所有股票）
        """
        from .akshare import AkshareDataSource

        if start_date is None:
            start_date = date(2020, 1, 1)
        if end_date is None:
            from datetime import timedelta
            end_date = date.today() - timedelta(1)

        akshare = AkshareDataSource(use_cache=True)

        # 获取股票列表
        if symbols is None:
            stock_list = akshare.get_stock_list()
            symbols = stock_list['symbol'].tolist()[:100]  # 限制数量避免超时

        conn = self._get_connection()
        total = len(symbols)
        synced = 0

        for symbol in symbols:
            try:
                df = akshare.get_daily(symbol, start_date, end_date)
                if df.empty:
                    continue

                # 插入数据库
                with conn.cursor() as cursor:
                    for _, row in df.iterrows():
                        cursor.execute(f"""
                            INSERT INTO {self._table('daily_prices')}
                            (symbol, trade_date, open, high, low, close, volume, amount)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            open = VALUES(open),
                            high = VALUES(high),
                            low = VALUES(low),
                            close = VALUES(close),
                            volume = VALUES(volume),
                            amount = VALUES(amount)
                        """, (
                            symbol,
                            row['date'],
                            row['open'],
                            row['high'],
                            row['low'],
                            row['close'],
                            row.get('volume', 0),
                            row.get('amount', 0)
                        ))

                synced += 1
                if synced % 10 == 0:
                    logger.info(f"Synced {synced}/{total} symbols")
            except Exception as e:
                logger.warning(f"Failed to sync {symbol}: {e}")

        logger.info(f"Sync complete: {synced}/{total} symbols")

    def sync_trading_calendar(self, exchange: str = "SSE"):
        """同步交易日历"""
        from .akshare import AkshareDataSource

        akshare = AkshareDataSource(use_cache=True)
        trading_days = akshare.get_trading_calendar(exchange)

        conn = self._get_connection()
        with conn.cursor() as cursor:
            for day in trading_days:
                cursor.execute(f"""
                    INSERT INTO {self._table('trading_calendar')}
                    (trade_date, exchange, is_trading_day)
                    VALUES (%s, %s, 1)
                    ON DUPLICATE KEY UPDATE is_trading_day = 1
                """, (day, exchange))

        logger.info(f"Synced {len(trading_days)} trading days")

    # ==================== 辅助方法 ====================

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) as cnt FROM {self._table('daily_prices')}")
                result = cursor.fetchone()
                daily_count = result['cnt']

            return {
                "status": "ok",
                "source": self.name,
                "database": self._config["database"],
                "daily_prices_count": daily_count,
            }
        except Exception as e:
            return {"status": "error", "source": self.name, "error": str(e)}

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
