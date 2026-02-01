"""Baostock 数据源适配器

Baostock 是稳定的中国股票历史数据接口，适合批量下载。
官网: http://www.baostock.com

特点：
- 日线数据稳定
- 财务数据（杜邦分析、利润表等）稳定
- 适合批量下载
- 无需登录/Token
- 支持文件缓存 (data/cache/fundamentals/)

注意：
- 每天晚上 18:00 更新当天数据
- 有并发限制，请勿过于频繁请求
"""

from datetime import date, datetime
from typing import List, Optional, Dict, Any
import pandas as pd

from ..utils import get_logger, format_date
from .base import DataSource, DataRequest, StockInfo
from .cache import FundamentalsCache

logger = get_logger(__name__)


class BaostockDataSource(DataSource):
    """Baostock 数据源实现"""

    name = "baostock"

    def __init__(self, use_cache: bool = True):
        """初始化

        Args:
            use_cache: 是否使用文件缓存，默认 True
        """
        try:
            import baostock as bs
            self._bs = bs
            self._login()
        except ImportError:
            raise ImportError(
                "baostock not installed. Run: pip install baostock"
            )

        # 缓存
        self._cache = FundamentalsCache(enabled=use_cache)

    def __del__(self):
        """登出"""
        try:
            if hasattr(self, '_bs'):
                self._bs.logout()
        except Exception:
            pass

    def _login(self):
        """登录"""
        lg = self._bs.login()
        if lg.error_code != '0':
            raise RuntimeError(f"Baostock 登录失败: {lg.error_msg}")

    def _to_bs_symbol(self, symbol: str) -> str:
        """转换为 baostock 格式"""
        symbol = symbol.replace(".SH", "").replace(".SZ", "")
        if symbol.startswith(("6", "5", "9")):
            return f"sh.{symbol}"
        return f"sz.{symbol}"

    def _to_bs_date(self, d) -> str:
        """转换为 baostock 日期格式"""
        if isinstance(d, date):
            return d.strftime("%Y-%m-%d")
        return str(d)

    def get_daily(
        self,
        symbol: str,
        start_date,
        end_date,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取日线数据"""
        bs_symbol = self._to_bs_symbol(symbol)
        start_str = self._to_bs_date(start_date)
        end_str = self._to_bs_date(end_date)

        # 字段映射
        field_map = {
            "date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "amount": "amount",
        }

        # 构建字段字符串
        if fields:
            selected = [field_map.get(f, f) for f in fields if f in field_map]
        else:
            selected = list(field_map.values())

        try:
            rs = self._bs.query_history_k_data_plus(
                bs_symbol,
                ",".join(selected),
                start_date=start_str,
                end_date=end_str,
                frequency="d"
            )

            if rs.error_code != '0':
                raise RuntimeError(f"查询失败: {rs.error_msg}")

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                return pd.DataFrame(columns=selected)

            df = pd.DataFrame(data_list, columns=rs.fields)

            # 转换数值列
            for col in df.columns:
                if col != "date":
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # 转换日期
            df["date"] = pd.to_datetime(df["date"]).dt.date

            return df

        except Exception as e:
            raise RuntimeError(f"获取 {symbol} 日线数据失败: {e}")

    def get_stock_list(self, market: str = "all") -> List[StockInfo]:
        """获取股票列表"""
        try:
            rs = self._bs.query_all_stock()

            if rs.error_code != '0':
                raise RuntimeError(f"查询失败: {rs.error_msg}")

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                return []

            df = pd.DataFrame(data_list, columns=rs.fields)

            stocks = []
            for _, row in df.iterrows():
                code = str(row.get("code", ""))
                name = str(row.get("name", ""))

                # 判断交易所
                if code.startswith("sh."):
                    exchange = "SSE"
                    market_type = "上海"
                elif code.startswith("sz."):
                    exchange = "SZSE"
                    market_type = "深圳"
                else:
                    continue

                if market != "all" and market != market_type:
                    continue

                # 提取纯代码
                symbol = code.replace("sh.", "").replace("sz.", "")

                stocks.append(StockInfo(
                    symbol=symbol,
                    name=name,
                    exchange=exchange,
                    market=market_type,
                ))

            return stocks

        except Exception as e:
            raise RuntimeError(f"获取股票列表失败: {e}")

    def get_trading_calendar(self, exchange: str = "SSE") -> List[date]:
        """获取交易日历"""
        # Baostock 没有直接的交易日历，可以从日线数据推断
        # 这里暂时返回空列表，由其他数据源提供
        logger.warning("Baostock 不提供交易日历，请使用 akshare 的 tool_trade_date_hist_sina")
        return []

    def get_index_daily(
        self,
        symbol: str,
        start_date,
        end_date
    ) -> pd.DataFrame:
        """获取指数数据"""
        # Baostock 主要支持股票数据，指数数据有限
        raise NotImplementedError(
            f"{self.name}: 暂不支持指数数据，请使用 akshare 的 stock_zh_index_daily_tx"
        )

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 尝试查询一只股票
            rs = self._bs.query_history_k_data_plus(
                "sh.600519",
                "date,close",
                start_date="2024-01-01",
                end_date="2024-01-01",
                frequency="d"
            )
            if rs.error_code == '0':
                return {"status": "ok", "source": self.name}
            else:
                return {"status": "error", "source": self.name, "error": rs.error_msg}
        except Exception as e:
            return {"status": "error", "source": self.name, "error": str(e)}

    def get_fina_indicator(
        self,
        symbols: List[str],
        report_type: str = "latest"
    ) -> pd.DataFrame:
        """获取杜邦分析数据"""
        results = []

        for symbol in symbols:
            bs_symbol = self._to_bs_symbol(symbol)

            try:
                # 获取最新几期数据
                for year in range(2022, 2025):
                    for quarter in [1, 2, 3, 4]:
                        rs = self._bs.query_dupont_data(bs_symbol, year, quarter)

                        if rs.error_code != '0':
                            continue

                        while rs.next():
                            row = rs.get_row_data()
                            results.append({
                                "symbol": symbol,
                                "year": year,
                                "quarter": quarter,
                                "roe": float(row[3]) if row[3] else None,
                                "netprofitmargin": float(row[7]) if row[7] else None,
                            })

            except Exception as e:
                logger.warning(f"获取 {symbol} 杜邦数据失败: {e}")
                continue

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        return df

    def get_dupont_analysis(
        self,
        symbols: List[str],
        start_year: int = 2022,
        end_year: int = 2024
    ) -> pd.DataFrame:
        """批量获取杜邦分析数据（带缓存）

        Args:
            symbols: 股票代码列表
            start_year: 开始年份
            end_year: 结束年份

        Returns:
            DataFrame with columns: symbol, roe, netprofitmargin, etc.
        """
        all_data = []

        for symbol in symbols:
            # 尝试从缓存读取
            cache_key = f"dupont_{symbol}_{start_year}_{end_year}"
            cached = self._cache.get(cache_key) if self._cache.enabled else None

            if cached is not None:
                logger.debug(f"缓存命中: {symbol}")
                all_data.append(cached)
                continue

            # 从 API 获取
            bs_symbol = self._to_bs_symbol(symbol)

            symbol_data = []
            for year in range(start_year, end_year + 1):
                for quarter in [1, 2, 3, 4]:
                    try:
                        rs = self._bs.query_dupont_data(bs_symbol, year, quarter)

                        if rs.error_code != '0':
                            continue

                        while rs.next():
                            row = rs.get_row_data()
                            symbol_data.append({
                                "symbol": symbol,
                                "pub_date": row[1],
                                "stat_date": row[2],
                                "roe": float(row[3]) if row[3] else None,
                                "asset_equity_ratio": float(row[4]) if row[4] else None,
                                "asset_turnover": float(row[5]) if row[5] else None,
                                "net_profit_margin": float(row[6]) if row[6] else None,
                                "gross_profit_margin": float(row[7]) if row[7] else None,
                                "tax_burden": float(row[8]) if row[8] else None,
                                "interest_burden": float(row[9]) if row[9] else None,
                                "ebit_to_nprofit": float(row[10]) if row[10] else None,
                            })

                    except Exception as e:
                        logger.warning(f"获取 {symbol} {year}Q{quarter} 数据失败: {e}")
                        continue

            if symbol_data:
                df = pd.DataFrame(symbol_data)
                # 写入缓存
                self._cache.set(cache_key, df)
                all_data.append(df)

        if not all_data:
            return pd.DataFrame()

        return pd.concat(all_data, ignore_index=True)

    def get_profit_data(
        self,
        symbols: List[str],
        start_year: int = 2022,
        end_year: int = 2024
    ) -> pd.DataFrame:
        """批量获取利润表数据（带缓存）"""
        all_data = []

        for symbol in symbols:
            # 尝试从缓存读取
            cache_key = f"profit_{symbol}_{start_year}_{end_year}"
            cached = self._cache.get(cache_key) if self._cache.enabled else None

            if cached is not None:
                logger.debug(f"缓存命中: {symbol}")
                all_data.append(cached)
                continue

            # 从 API 获取
            bs_symbol = self._to_bs_symbol(symbol)

            symbol_data = []
            for year in range(start_year, end_year + 1):
                for quarter in [1, 2, 3, 4]:
                    try:
                        rs = self._bs.query_profit_data(bs_symbol, year, quarter)

                        if rs.error_code != '0':
                            continue

                        while rs.next():
                            row = rs.get_row_data()
                            symbol_data.append({
                                "symbol": symbol,
                                "pub_date": row[1],
                                "net_profits": float(row[2]) if row[2] else None,
                                "net_profits_yr": float(row[3]) if row[3] else None,
                                "dt_net_profits": float(row[4]) if row[4] else None,
                                "total_revenue": float(row[5]) if row[5] else None,
                                "revenue_yr": float(row[6]) if row[6] else None,
                            })

                    except Exception as e:
                        continue

            if symbol_data:
                df = pd.DataFrame(symbol_data)
                self._cache.set(cache_key, df)
                all_data.append(df)

        if not all_data:
            return pd.DataFrame()

        return pd.concat(all_data, ignore_index=True)

    def get_growth_data(
        self,
        symbols: List[str],
        start_year: int = 2022,
        end_year: int = 2024
    ) -> pd.DataFrame:
        """批量获取成长能力数据（带缓存）"""
        all_data = []

        for symbol in symbols:
            # 尝试从缓存读取
            cache_key = f"growth_{symbol}_{start_year}_{end_year}"
            cached = self._cache.get(cache_key) if self._cache.enabled else None

            if cached is not None:
                logger.debug(f"缓存命中: {symbol}")
                all_data.append(cached)
                continue

            # 从 API 获取
            bs_symbol = self._to_bs_symbol(symbol)

            symbol_data = []
            for year in range(start_year, end_year + 1):
                for quarter in [1, 2, 3, 4]:
                    try:
                        rs = self._bs.query_growth_data(bs_symbol, year, quarter)

                        if rs.error_code != '0':
                            continue

                        while rs.next():
                            row = rs.get_row_data()
                            symbol_data.append({
                                "symbol": symbol,
                                "pub_date": row[1],
                                "net_profits_growth": float(row[2]) if row[2] else None,
                                "revenue_growth": float(row[3]) if row[3] else None,
                                "total_assets_growth": float(row[4]) if row[4] else None,
                            })

                    except Exception as e:
                        continue

            if symbol_data:
                df = pd.DataFrame(symbol_data)
                self._cache.set(cache_key, df)
                all_data.append(df)

        if not all_data:
            return pd.DataFrame()

        return pd.concat(all_data, ignore_index=True)

    def get_valuation(
        self,
        symbols: List[str],
        date
    ) -> pd.DataFrame:
        """获取估值数据（从日线数据计算）"""
        # Baostock 没有直接的估值数据接口
        # 可以从日线数据中提取最新收盘价
        raise NotImplementedError(
            f"{self.name}: 暂不支持估值数据，请使用 akshare (需要东方财富接口)"
        )

    def get_fundamental(
        self,
        symbols: List[str],
        date,
        indicators: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """获取合并基本面数据"""
        # 批量下载杜邦分析数据
        df = self.get_dupont_analysis(symbols)

        if df.empty:
            return df

        # 按股票代码分组，取最新数据
        latest = df.groupby("symbol").last().reset_index()

        return latest
