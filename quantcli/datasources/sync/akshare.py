"""Akshare 数据同步器

从 Akshare API 同步数据到 MySQL。

使用示例:
    >>> from quantcli.datasources import create_sync
    >>> sync = create_sync("akshare")
    >>> sync.sync_daily(["600519", "000001"], date(2024, 1, 1))
"""

from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class AkshareSync:
    """Akshare 数据同步器

    使用 Akshare 获取数据，写入 MySQL。
    """

    name = "akshare"

    def __init__(
        self,
        token: str = None,
        mysql=None,
        autocommit: bool = True
    ):
        """初始化 Akshare 同步器

        Args:
            token: 保留参数（Akshare 不需要 token）
            mysql: MySQLDataSource 实例，传入 None 则自动创建
            autocommit: 是否自动提交
        """
        from quantcli.datasources import MySQLDataSource

        self._token = token
        self._mysql = mysql or MySQLDataSource(autocommit=autocommit)
        self._ak = None  # 延迟初始化

    def _init_ak(self):
        """初始化 Akshare"""
        if self._ak is None:
            import akshare as ak
            self._ak = ak

    def _get_daily_table(self) -> str:
        return self._mysql._table("daily_prices")

    def _get_minute_table(self) -> str:
        return self._mysql._table("intraday_prices")

    def _get_fundamental_table(self) -> str:
        return self._mysql._table("fundamental_data")

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
        self._init_ak()
        import akshare as ak

        if end_date is None:
            end_date = date.today() - timedelta(days=1)

        result = {}
        conn = self._mysql._get_connection()
        table = self._get_daily_table()

        for symbol in symbols:
            # 转换代码格式 (600519 -> sh600519)
            if symbol.startswith("6"):
                ak_symbol = f"sh{symbol}"
            else:
                ak_symbol = f"sz{symbol}"

            # 检查进度
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
                if ak_symbol.startswith("sh"):
                    data = ak.stock_zh_a_hist(
                        symbol=symbol,
                        period="daily",
                        start_date=actual_start.strftime("%Y%m%d"),
                        end_date=end_date.strftime("%Y%m%d"),
                        adjust="qfq"
                    )
                else:
                    data = ak.stock_zh_a_hist(
                        symbol=symbol,
                        period="daily",
                        start_date=actual_start.strftime("%Y%m%d"),
                        end_date=end_date.strftime("%Y%m%d"),
                        adjust="qfq"
                    )

                if data.empty:
                    result[symbol] = 0
                    continue

                # 写入数据库
                count = 0
                with conn.cursor() as cursor:
                    for _, row in data.iterrows():
                        trade_date = datetime.strptime(str(row['日期']), "%Y-%m-%d").date()

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
                            row['开盘'],
                            row['最高'],
                            row['最低'],
                            row['收盘'],
                            row['成交量'],
                            row['成交额']
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
        self._init_ak()
        import akshare as ak

        if end_date is None:
            end_date = date.today() - timedelta(days=1)
        if start_date is None:
            start_date = end_date - timedelta(days=5)

        period_map = {
            "1": "1",
            "5": "5",
            "15": "15",
            "30": "30",
            "60": "60"
        }

        if period not in period_map:
            raise ValueError(f"Invalid period: {period}. Valid: {list(period_map.keys())}")

        result = {}
        conn = self._mysql._get_connection()
        table = self._get_minute_table()

        for symbol in symbols:
            # 转换代码格式
            if symbol.startswith("6"):
                ak_symbol = f"sh{symbol}"
            else:
                ak_symbol = f"sz{symbol}"

            try:
                # Akshare 分钟线需要按日获取
                count = 0
                current = start_date

                while current <= end_date:
                    try:
                        data = ak.stock_zh_a_minute(
                            symbol=symbol,
                            period=period_map[period],
                            start_date=current.strftime("%Y%m%d"),
                            end_date=current.strftime("%Y%m%d")
                        )

                        if data is None or data.empty:
                            current += timedelta(days=1)
                            continue

                        # 写入数据库
                        with conn.cursor() as cursor:
                            for _, row in data.iterrows():
                                # 解析时间
                                time_str = str(row['时间'])  # 格式: "09:30"
                                trade_time = datetime.strptime(time_str, "%H:%M").time()

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
                                    current,
                                    trade_time,
                                    period,
                                    row['开盘'],
                                    row['最高'],
                                    row['最低'],
                                    row['收盘'],
                                    row.get('成交量', 0),
                                    row.get('成交额', 0)
                                ))
                                count += 1

                    except Exception as e:
                        # 单日数据可能不存在，继续下一日
                        pass

                    current += timedelta(days=1)

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
        """同步基本面数据"""
        self._init_ak()
        import akshare as ak

        if report_date is None:
            report_date = date.today()

        result = {}
        conn = self._mysql._get_connection()
        table = self._get_fundamental_table()

        for symbol in symbols:
            try:
                # 获取最新财报数据
                df = ak.stock_financial_analysis_indicator(
                    symbol=symbol,
                    indicator="报告期"
                )

                if df.empty:
                    result[symbol] = 0
                    continue

                count = 0
                with conn.cursor() as cursor:
                    for _, row in df.iterrows():
                        report_date_val = datetime.strptime(str(row['公告日期']), "%Y-%m-%d").date()

                        cursor.execute(f"""
                            INSERT INTO {table}
                            (symbol, report_date, roe, netprofitmargin, grossprofitmargin, pe_ttm, pb)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            roe = VALUES(roe),
                            netprofitmargin = VALUES(netprofitmargin),
                            grossprofitmargin = VALUES(grossprofitmargin),
                            pe_ttm = VALUES(pe_ttm),
                            pb = VALUES(pb)
                        """, (
                            symbol,
                            report_date_val,
                            row.get('净资产收益率'),
                            row.get('净利润率'),
                            row.get('毛利率'),
                            row.get('市盈率(PE)'),
                            row.get('市净率(PB)'),
                        ))
                        count += 1

                result[symbol] = count
                logger.info(f"{symbol}: synced {count} fundamental records")

            except Exception as e:
                logger.error(f"Failed to sync fundamental for {symbol}: {e}")
                result[symbol] = -1

        return result

    # ==================== 批量同步 ====================

    def sync_all(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date = None,
        periods: List[str] = None,
        include_fundamental: bool = False
    ) -> Dict[str, Dict]:
        """批量同步

        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            periods: 分钟周期列表，默认 ["5"]
            include_fundamental: 是否同步基本面

        Returns:
            同步结果
        """
        result = {"daily": {}, "minute": {}, "fundamental": {}}

        result["daily"] = self.sync_daily(symbols, start_date, end_date)

        if periods is None:
            periods = ["5"]

        for period in periods:
            result["minute"][period] = self.sync_minute(symbols, period, start_date, end_date)

        if include_fundamental:
            result["fundamental"] = self.sync_fundamental(symbols)

        return result

    def close(self):
        """关闭连接"""
        self._mysql.close()
