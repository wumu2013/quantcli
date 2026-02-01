"""掘金量化数据同步器

从掘金量化 API 同步数据到 MySQL。

使用示例:
    >>> from quantcli.datasources import create_sync
    >>> sync = create_sync("gm", token="your_token")
    >>> sync.sync_daily(["600519", "000001"], date(2024, 1, 1))
"""

from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class GmSync:
    """掘金量化数据同步器

    使用掘金 SDK 的 history() API 获取数据，写入 MySQL。
    """

    name = "gm"

    # 分钟周期映射
    PERIOD_MAP = {
        "1": "60s",
        "5": "300s",
        "15": "900s",
        "30": "1800s",
        "60": "3600s",
    }

    def __init__(
        self,
        token: str = None,
        mysql=None,
        autocommit: bool = True
    ):
        """初始化掘金同步器

        Args:
            token: 掘金 API token
            mysql: MySQLDataSource 实例，传入 None 则自动创建
            autocommit: 是否自动提交
        """
        from quantcli.datasources import MySQLDataSource

        self._token = token or self._get_token_from_env()
        self._mysql = mysql or MySQLDataSource(autocommit=autocommit)
        self._gm = None  # 延迟初始化 gm.api

    def _get_token_from_env(self) -> str:
        """从环境变量获取 token"""
        import os
        return os.getenv("GM_TOKEN", "")

    def _init_gm(self):
        """初始化掘金 API"""
        if self._gm is None:
            from gm.api import set_token
            set_token(self._token)
            self._gm = True

    def _get_daily_table(self) -> str:
        return self._mysql._table("daily_prices")

    def _get_minute_table(self) -> str:
        return self._mysql._table("intraday_prices")

    # ==================== 进度查询 ====================

    def get_progress(self, symbol: str) -> Optional[date]:
        """获取同步进度"""
        conn = self._mysql._get_connection()
        table = self._get_daily_table()

        sql = f"SELECT MAX(trade_date) as latest FROM {table} WHERE symbol = %s"

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (symbol,))
                result = cursor.fetchone()
                return result['latest'] if result else None
        except Exception as e:
            logger.warning(f"Failed to get progress for {symbol}: {e}")
            return None

    def get_progress_minute(self, symbol: str, period: str) -> Optional[date]:
        """获取分钟线同步进度"""
        conn = self._mysql._get_connection()
        table = self._get_minute_table()

        sql = f"SELECT MAX(trade_date) as latest FROM {table} WHERE symbol = %s AND period = %s"

        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (symbol, period))
                result = cursor.fetchone()
                return result['latest'] if result else None
        except Exception as e:
            logger.warning(f"Failed to get minute progress for {symbol}: {e}")
            return None

    # ==================== 日线同步 ====================

    def sync_daily(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date = None
    ) -> Dict[str, int]:
        """同步日线数据

        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期，默认到昨天

        Returns:
            {"symbol": records_count, ...}
        """
        self._init_gm()
        from gm.api import history, ADJUST_PREV

        if end_date is None:
            end_date = date.today() - timedelta(days=1)

        result = {}
        conn = self._mysql._get_connection()
        table = self._get_daily_table()

        for symbol in symbols:
            # 检查已有进度，增量同步
            latest = self.get_progress(symbol)
            if latest and latest >= start_date:
                actual_start = latest + timedelta(days=1)
            else:
                actual_start = start_date

            if actual_start > end_date:
                logger.info(f"{symbol}: already up to date")
                result[symbol] = 0
                continue

            try:
                data = history(
                    symbol=symbol,
                    frequency='1d',
                    start_time=f"{actual_start} 09:30:00",
                    end_time=f"{end_date} 16:00:00",
                    fields='symbol,open,high,low,close,volume,amount,eob',
                    adjust=ADJUST_PREV,
                    df=True
                )

                if data.empty:
                    result[symbol] = 0
                    continue

                # 写入数据库
                count = 0
                with conn.cursor() as cursor:
                    for _, row in data.iterrows():
                        trade_date = row['eob'].date() if isinstance(row['eob'], datetime) else row['eob']

                        cursor.execute(f"""
                            INSERT INTO {table}
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
                            trade_date,
                            row['open'],
                            row['high'],
                            row['low'],
                            row['close'],
                            row.get('volume', 0),
                            row.get('amount', 0)
                        ))
                        count += 1

                result[symbol] = count
                logger.info(f"{symbol}: synced {count} daily records")

            except Exception as e:
                logger.error(f"Failed to sync daily for {symbol}: {e}")
                result[symbol] = -1

        return result

    # ==================== 分钟线同步 ====================

    def sync_minute(
        self,
        symbols: List[str],
        period: str = "5",
        start_date: date = None,
        end_date: date = None
    ) -> Dict[str, int]:
        """同步分钟线数据

        Args:
            symbols: 股票代码列表
            period: 分钟周期 ("1", "5", "15", "30", "60")
            start_date: 开始日期，默认 5 天前
            end_date: 结束日期，默认到昨天

        Returns:
            {"symbol": records_count, ...}
        """
        # 先检查 period 参数，再初始化 gm
        if period not in self.PERIOD_MAP:
            raise ValueError(f"Invalid period: {period}. Valid: {list(self.PERIOD_MAP.keys())}")

        self._init_gm()
        from gm.api import history, ADJUST_PREV

        gm_period = self.PERIOD_MAP[period]

        if end_date is None:
            end_date = date.today() - timedelta(days=1)
        if start_date is None:
            start_date = end_date - timedelta(days=5)

        result = {}
        conn = self._mysql._get_connection()
        table = self._get_minute_table()

        for symbol in symbols:
            # 检查进度
            latest = self.get_progress_minute(symbol, period)
            if latest and latest >= start_date:
                actual_start = latest + timedelta(days=1)
            else:
                actual_start = start_date

            if actual_start > end_date:
                logger.info(f"{symbol}: minute data already up to date")
                result[symbol] = 0
                continue

            try:
                data = history(
                    symbol=symbol,
                    frequency=gm_period,
                    start_time=f"{actual_start} 09:30:00",
                    end_time=f"{end_date} 16:00:00",
                    fields='symbol,open,high,low,close,volume,amount,eob',
                    adjust=ADJUST_PREV,
                    df=True
                )

                if data.empty:
                    result[symbol] = 0
                    continue

                # 写入数据库
                count = 0
                with conn.cursor() as cursor:
                    for _, row in data.iterrows():
                        dt = row['eob']
                        if isinstance(dt, str):
                            dt = datetime.fromisoformat(dt.replace('Z', '+08:00'))
                        trade_date = dt.date()
                        trade_time = dt.time()

                        cursor.execute(f"""
                            INSERT INTO {table}
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
                        count += 1

                result[symbol] = count
                logger.info(f"{symbol}: synced {count} {period}min records")

            except Exception as e:
                logger.error(f"Failed to sync minute for {symbol}: {e}")
                result[symbol] = -1

        return result

    # ==================== 基本面同步 ====================

    def sync_fundamental(
        self,
        symbols: List[str],
        report_date: date = None
    ) -> Dict[str, int]:
        """同步基本面数据（掘金不支持，暂未实现）"""
        logger.warning("GmSync.sync_fundamental: not implemented (Gm SDK doesn't provide fundamental data)")
        return {symbol: -1 for symbol in symbols}

    # ==================== 批量同步 ====================

    def sync_all(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date = None,
        periods: List[str] = None
    ) -> Dict[str, Dict[str, int]]:
        """批量同步日线和分钟线

        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            periods: 分钟周期列表，默认 ["1", "5", "15"]

        Returns:
            {"daily": {...}, "minute": {"1": {...}, "5": {...}}}
        """
        result = {"daily": {}, "minute": {}}

        # 同步日线
        result["daily"] = self.sync_daily(symbols, start_date, end_date)

        # 同步分钟线
        if periods is None:
            periods = ["1", "5", "15"]

        for period in periods:
            result["minute"][period] = self.sync_minute(symbols, period, start_date, end_date)

        return result

    def close(self):
        """关闭连接"""
        self._mysql.close()

    # ==================== on_bar 事件同步 ====================

    def sync_bar(self, symbol: str, bar) -> bool:
        """同步单根日线 bar 到 MySQL

        用于 on_bar 事件中实时同步数据。

        Args:
            symbol: 股票代码
            bar: gm.api.Bar 对象或字典

        Returns:
            是否成功

        使用示例:
            >>> def on_bar(context, bars):
            ...     for bar in bars:
            ...         context.sync.sync_bar(bar.symbol, bar)
        """
        conn = self._mysql._get_connection()
        table = self._get_daily_table()

        try:
            # 提取 bar 数据（支持对象和字典）
            if hasattr(bar, 'eob'):
                # Bar 对象
                eob = bar.eob
                trade_date = eob.date() if isinstance(eob, datetime) else eob
                open_ = bar.open
                high = bar.high
                low = bar.low
                close = bar.close
                volume = bar.volume
                amount = getattr(bar, 'amount', 0)
            else:
                # 字典
                eob = bar.get('eob')
                if isinstance(eob, str):
                    eob = datetime.fromisoformat(eob.replace('Z', '+08:00'))
                trade_date = eob.date() if isinstance(eob, datetime) else eob
                open_ = bar.get('open')
                high = bar.get('high')
                low = bar.get('low')
                close = bar.get('close')
                volume = bar.get('volume', 0)
                amount = bar.get('amount', 0)

            with conn.cursor() as cursor:
                cursor.execute(f"""
                    INSERT INTO {table}
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
                    trade_date,
                    open_,
                    high,
                    low,
                    close,
                    volume,
                    amount
                ))
            return True

        except Exception as e:
            logger.error(f"sync_bar failed for {symbol}: {e}")
            return False

    def sync_minute_bar(self, symbol: str, bar, period: str = "5") -> bool:
        """同步单根分钟线 bar 到 MySQL

        用于 on_bar 事件中实时同步分钟数据。

        Args:
            symbol: 股票代码
            bar: gm.api.Bar 对象或字典
            period: 分钟周期 ("1", "5", "15", "30", "60")

        Returns:
            是否成功

        使用示例:
            >>> def on_bar(context, bars):
            ...     for bar in bars:
            ...         context.sync.sync_minute_bar(bar.symbol, bar, period="5")
        """
        conn = self._mysql._get_connection()
        table = self._get_minute_table()

        try:
            # 提取 bar 数据
            if hasattr(bar, 'eob'):
                eob = bar.eob
                if isinstance(eob, str):
                    eob = datetime.fromisoformat(eob.replace('Z', '+08:00'))
                trade_date = eob.date()
                trade_time = eob.time()
                open_ = bar.open
                high = bar.high
                low = bar.low
                close = bar.close
                volume = bar.volume
                amount = getattr(bar, 'amount', 0)
            else:
                eob = bar.get('eob')
                if isinstance(eob, str):
                    eob = datetime.fromisoformat(eob.replace('Z', '+08:00'))
                trade_date = eob.date()
                trade_time = eob.time()
                open_ = bar.get('open')
                high = bar.get('high')
                low = bar.get('low')
                close = bar.get('close')
                volume = bar.get('volume', 0)
                amount = bar.get('amount', 0)

            with conn.cursor() as cursor:
                cursor.execute(f"""
                    INSERT INTO {table}
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
                    open_,
                    high,
                    low,
                    close,
                    volume,
                    amount
                ))
            return True

        except Exception as e:
            logger.error(f"sync_minute_bar failed for {symbol}: {e}")
            return False
