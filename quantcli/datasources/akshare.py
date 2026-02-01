"""AKShare 数据源适配器

使用稳定的接口：
- 日线数据: stock_zh_a_hist_tx (腾讯)
- 股票列表: stock_info_a_code_name
- 交易日历: tool_trade_date_hist_sina (新浪)
- 指数日线: stock_zh_index_daily_tx (腾讯)

文档: https://akshare.xyz/
"""

from datetime import date
from typing import List, Optional, Dict, Any
import pandas as pd

from ..utils import get_logger, format_date
from .base import DataSource, DataSourceConfig, StockInfo
from .cache import PriceCache, StockListCache, TradingCalendarCache

logger = get_logger(__name__)


class AkshareDataSource(DataSource):
    """AKShare 数据源实现（稳定版本）"""

    name = "akshare"

    def __init__(self, use_cache: bool = True):
        """初始化

        Args:
            use_cache: 是否使用缓存，默认 True
        """
        super().__init__(DataSourceConfig(name=self.name, use_cache=use_cache))

        try:
            import akshare as ak
            self._ak = ak
        except ImportError:
            raise ImportError("akshare not installed. Run: pip install akshare")

        # 缓存实例
        self._price_cache = PriceCache(enabled=use_cache)
        self._stocklist_cache = StockListCache(enabled=use_cache)
        self._calendar_cache = TradingCalendarCache(enabled=use_cache)

    # ==================== 工具方法 ====================

    def _to_tx_symbol(self, symbol: str) -> str:
        """转换为腾讯股票代码格式"""
        symbol = symbol.replace(".SH", "").replace(".SZ", "")
        return f"sh{symbol}" if symbol.startswith(("6", "5", "9")) else f"sz{symbol}"

    def _to_index_tx_symbol(self, symbol: str) -> str:
        """转换为腾讯指数代码格式"""
        symbol = symbol.replace(".SH", "").replace(".SZ", "")
        return f"sh{symbol}" if symbol.startswith(("6", "5", "9")) else f"sz{symbol}"

    def _market_filter(
        self,
        df: pd.DataFrame,
        market: str
    ) -> pd.DataFrame:
        """过滤股票市场"""
        if market == "all":
            return df

        is_sh = df["symbol"].str.startswith(("6", "5", "9"))
        if market == "上海":
            return df[is_sh]
        return df[~is_sh]

    # ==================== 核心接口 ====================

    def get_daily(
        self,
        symbol: str,
        start_date,
        end_date,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取A股日线数据（腾讯接口）"""
        start_str = format_date(start_date, "%Y-%m-%d")
        end_str = format_date(end_date, "%Y-%m-%d")
        cache_key = f"{symbol}_{start_str}_{end_str}"

        # 1. 尝试缓存
        if self.config.use_cache:
            cached = self._price_cache.get(cache_key)
            if cached is not None:
                return self._filter_fields(cached, fields) if fields else cached

        # 2. API 调用
        tx_symbol = self._to_tx_symbol(symbol)
        df = self._ak.stock_zh_a_hist_tx(
            symbol=tx_symbol,
            start_date=format_date(start_date, "%Y%m%d"),
            end_date=format_date(end_date, "%Y%m%d")
        )

        if df.empty:
            return df

        df["date"] = pd.to_datetime(df["date"]).dt.date

        # 3. 写入缓存
        if self.config.use_cache:
            self._price_cache.set(cache_key, df)

        return self._filter_fields(df, fields) if fields else df

    def get_index_daily(
        self,
        symbol: str,
        start_date,
        end_date
    ) -> pd.DataFrame:
        """获取指数日线数据（腾讯接口）"""
        start_str = format_date(start_date, "%Y-%m-%d")
        end_str = format_date(end_date, "%Y-%m-%d")
        cache_key = f"idx_{symbol}_{start_str}_{end_str}"

        if self.config.use_cache:
            cached = self._price_cache.get(cache_key)
            if cached is not None:
                return cached

        tx_symbol = self._to_index_tx_symbol(symbol)
        df = self._ak.stock_zh_index_daily_tx(symbol=tx_symbol)

        if df.empty:
            return df

        df["date"] = pd.to_datetime(df["date"]).dt.date

        if self.config.use_cache:
            self._price_cache.set(cache_key, df)

        return df

    def get_intraday(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        period: str = "5"
    ) -> pd.DataFrame:
        """获取分钟级数据

        Args:
            symbol: 股票代码，如 "600519"
            start_date: 开始日期
            end_date: 结束日期
            period: 分钟周期，支持 "1", "5", "15", "30", "60"

        Returns:
            DataFrame with columns: [date, open, high, low, close, volume]
        """
        import akshare as ak
        from datetime import datetime, timedelta

        # 默认获取最近5个交易日
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=10)

        try:
            # 使用 akshare 获取分钟数据
            df = ak.stock_zh_a_hist_min_em(
                symbol=symbol,
                period=period,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust="qfq"
            )

            if df.empty:
                return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])

            # 标准化列名
            df = df.rename(columns={
                "时间": "date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount"
            })

            # 转换日期格式
            df["date"] = pd.to_datetime(df["date"])

            # 确保数值列是数值类型
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            return df

        except Exception as e:
            logger.warning(f"Failed to get intraday data for {symbol}: {e}")
            return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])

    def get_stock_list(self, market: str = "all") -> pd.DataFrame:
        """获取A股股票列表

        Returns:
            DataFrame(columns=['symbol', 'name', 'exchange', 'market'])
        """
        if self.config.use_cache:
            cached = self._stocklist_cache.get_list(market)
            if cached is not None:
                return cached

        df = self._ak.stock_info_a_code_name()
        if df.empty:
            return pd.DataFrame(columns=['symbol', 'name', 'exchange', 'market'])

        # 转换格式：akshare 可能返回中文列名
        df = df.rename(columns={"代码": "symbol", "名称": "name"})
        # 兼容旧版本可能返回英文列名
        if "symbol" not in df.columns:
            df = df.rename(columns={"code": "symbol", "name": "name"})
        df["exchange"] = df["symbol"].apply(
            lambda x: "SSE" if x.startswith(("6", "5", "9")) else "SZSE"
        )
        df["market"] = df["exchange"].apply(lambda x: "上海" if x == "SSE" else "深圳")

        # 过滤
        df = self._market_filter(df, market)

        if self.config.use_cache:
            self._stocklist_cache.set_list(market, df)

        return df

    def get_trading_calendar(self, exchange: str = "SSE") -> List[date]:
        """获取交易日历"""
        if self.config.use_cache:
            cached = self._calendar_cache.get_calendar(exchange)
            if cached is not None:
                return sorted(pd.to_datetime(cached["trade_date"]).dt.date.tolist())

        df = self._ak.tool_trade_date_hist_sina()
        if df.empty:
            return []

        trading_dates = pd.to_datetime(df["trade_date"]).dt.date.tolist()

        if self.config.use_cache:
            self._calendar_cache.set_calendar(exchange, df)

        return sorted(trading_dates)

    # ==================== 辅助方法 ====================

    def _filter_fields(
        self,
        df: pd.DataFrame,
        fields: Optional[List[str]]
    ) -> pd.DataFrame:
        """过滤字段"""
        if not fields:
            return df
        available = ["date", "open", "high", "low", "close", "volume", "amount"]
        return df[[f for f in fields if f in available]]

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            self._ak.tool_trade_date_hist_sina()
            return {
                "status": "ok",
                "source": self.name,
                "cache": self.config.use_cache
            }
        except Exception as e:
            return {"status": "error", "source": self.name, "error": str(e)}

    # ==================== 不支持的接口 ====================

    def get_fundamental(
        self,
        symbols: List[str],
        date,
        indicators: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """基本面数据请使用 baostock 数据源"""
        raise NotImplementedError(
            "Use baostock datasource for fundamental data: "
            "create_datasource('baostock') or create_datasource('mixed')"
        )

    def get_fina_indicator(
        self,
        symbols: List[str],
        report_type: str = "latest"
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "Use baostock datasource for financial indicators"
        )

    def get_valuation(
        self,
        symbols: List[str],
        date
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "Use baostock datasource for valuation data"
        )
