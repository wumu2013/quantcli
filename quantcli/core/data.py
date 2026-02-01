"""数据管理模块 - 数据获取、缓存、清洗

功能:
1. 数据获取 - 多数据源统一接口
2. 数据缓存 - Parquet 持久化，支持增量更新
3. 数据清洗 - 填充NA、异常值处理、过滤ST/停牌等

Usage:
    >>> from quantcli.core import DataManager, DataConfig
    >>> dm = DataManager(DataConfig(source="akshare"))
    >>> df = dm.get_daily("600519", date(2020,1,1), date(2024,1,1))
    >>> df = dm.clean(df, fillna="ffill", outlier="clip")
"""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..datasources import create_datasource, DataSource, StockInfo
from ..utils import (
    get_logger, project_root, ensure_dir, format_size,
    parse_date, today
)

logger = get_logger(__name__)


@dataclass
class DataConfig:
    """数据管理配置"""
    source: str = "akshare"
    cache_dir: str = "./data"
    parallel: int = 4

    # 清洗配置
    fillna: str = "ffill"
    outlier_method: str = "clip"
    outlier_threshold: float = 5.0

    # 过滤配置
    filter_st: bool = True
    filter_new: int = 60
    filter_suspended: bool = True

    # 输出配置
    output_format: str = "parquet"
    compression: str = "snappy"


@dataclass
class DataQualityReport:
    """数据质量报告"""
    total_rows: int
    null_count: Dict[str, int]
    outlier_count: Dict[str, int]
    st_filtered: int
    suspended_filtered: int
    new_stock_filtered: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class DataManager:
    """数据管理器"""

    def __init__(self, config: Optional[DataConfig] = None):
        self.config = config or DataConfig()
        self._datasource: Optional[DataSource] = None
        self._cache_metadata: Dict[str, Any] = {}

        # 使用 utils 中的路径工具
        self.cache_dir = Path(self.config.cache_dir)
        self._init_cache_dir()

    def _init_cache_dir(self):
        """初始化缓存目录"""
        ensure_dir(self.cache_dir / "raw" / "stock_daily")
        ensure_dir(self.cache_dir / "features")
        ensure_dir(self.cache_dir / "cache")

        self._metadata_file = self.cache_dir / "cache" / "metadata.json"
        self._load_metadata()

    def _load_metadata(self):
        """加载元数据"""
        if self._metadata_file.exists():
            try:
                with open(self._metadata_file, "r") as f:
                    self._cache_metadata = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load metadata: {e}")
                self._cache_metadata = {}
        else:
            self._cache_metadata = {}

    def _save_metadata(self):
        """保存元数据"""
        with open(self._metadata_file, "w") as f:
            json.dump(self._cache_metadata, f, indent=2)

    @property
    def datasource(self) -> DataSource:
        """懒加载数据源"""
        if self._datasource is None:
            self._datasource = create_datasource(self.config.source)
        return self._datasource

    # =============================================================================
    # 数据获取
    # =============================================================================

    def get_daily(
        self,
        symbol: str,
        start_date,
        end_date,
        use_cache: bool = True,
        **kwargs
    ) -> pd.DataFrame:
        """获取单只股票日线数据"""
        cache_file = self.cache_dir / "raw" / "stock_daily" / f"{symbol}.parquet"

        # 检查缓存
        if use_cache and cache_file.exists():
            cached = self._load_cached_range(cache_file)
            if cached is not None:
                mask = (cached["date"] >= start_date) & (cached["date"] <= end_date)
                result = cached[mask].copy()
                if not result.empty:
                    return result

        # 从数据源获取
        df = self.datasource.get_daily(symbol, start_date, end_date, **kwargs)

        if df.empty:
            logger.warning(f"No data for {symbol}")
            return df

        # 缓存数据
        if use_cache:
            self._save_to_cache(cache_file, df, f"stock_daily_{symbol}")

        return df

    def get_daily_batch(
        self,
        symbols: List[str],
        start_date,
        end_date,
        use_cache: bool = True,
        parallel: bool = False
    ) -> pd.DataFrame:
        """批量获取多只股票日线数据"""
        if not symbols:
            return pd.DataFrame()

        all_data = []

        if parallel and len(symbols) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.config.parallel) as executor:
                futures = [
                    executor.submit(self.get_daily, s, start_date, end_date, use_cache)
                    for s in symbols
                ]
                for i, future in enumerate(futures):
                    symbol = symbols[i]
                    try:
                        df = future.result()
                        if not df.empty:
                            df = df.copy()
                            df["symbol"] = symbol
                            all_data.append(df)
                    except Exception as e:
                        logger.error(f"Failed to fetch {symbol}: {e}")
        else:
            for symbol in symbols:
                df = self.get_daily(symbol, start_date, end_date, use_cache)
                if not df.empty:
                    df = df.copy()
                    df["symbol"] = symbol
                    all_data.append(df)

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        result = result.sort_values(["symbol", "date"]).reset_index(drop=True)
        return result

    def get_universe(
        self,
        universe: str = "all",
        market: str = "all",
        use_cache: bool = True
    ) -> List[StockInfo]:
        """获取股票池"""
        cache_file = self.cache_dir / "cache" / f"stock_list_{market}.json"

        if use_cache and cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    return [StockInfo(**s) for s in data]
            except Exception as e:
                logger.warning(f"Failed to load cached stock list: {e}")

        stocks = self.datasource.get_stock_list(market)

        if universe != "all":
            stocks = self._filter_universe(stocks, universe)

        if use_cache:
            cache_data = [s.__dict__ for s in stocks]
            with open(cache_file, "w") as f:
                json.dump(cache_data, f, indent=2, default=str)

        return stocks

    def get_trading_calendar(
        self,
        exchange: str = "SSE",
        use_cache: bool = True
    ) -> List:
        """获取交易日历"""
        cache_file = self.cache_dir / "cache" / f"trading_calendar_{exchange}.json"

        if use_cache and cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    return [parse_date(d) for d in json.load(f)]
            except Exception as e:
                logger.warning(f"Failed to load trading calendar: {e}")

        trading_days = self.datasource.get_trading_calendar(exchange)

        if use_cache:
            with open(cache_file, "w") as f:
                json.dump([d.isoformat() for d in trading_days], f)

        return trading_days

    def get_index_daily(
        self,
        symbol: str,
        start_date,
        end_date,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """获取指数日线数据"""
        cache_file = self.cache_dir / "raw" / "index_daily" / f"{symbol}.parquet"

        if use_cache and cache_file.exists():
            cached = self._load_cached_range(cache_file)
            if cached is not None:
                mask = (cached["date"] >= start_date) & (cached["date"] <= end_date)
                result = cached[mask].copy()
                if not result.empty:
                    return result

        df = self.datasource.get_index_daily(symbol, start_date, end_date)

        if use_cache and not df.empty:
            self._save_to_cache(cache_file, df, f"index_daily_{symbol}")

        return df

    def _filter_universe(self, stocks: List[StockInfo], universe: str) -> List[StockInfo]:
        """根据股票池名称过滤股票"""
        return stocks

    # =============================================================================
    # 数据缓存
    # =============================================================================

    def _load_cached_range(self, cache_file: Path) -> Optional[pd.DataFrame]:
        """加载缓存文件的日期范围数据"""
        if not cache_file.exists():
            return None

        try:
            df = pd.read_parquet(cache_file)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.date
            return df
        except Exception as e:
            logger.warning(f"Failed to load cache {cache_file}: {e}")
            return None

    def _save_to_cache(self, cache_file: Path, df: pd.DataFrame, cache_key: str):
        """保存数据到缓存"""
        ensure_dir(cache_file.parent)

        df_copy = df.copy()
        if "date" in df_copy.columns:
            df_copy["date"] = pd.to_datetime(df_copy["date"]).dt.date

        # 追加写入
        if cache_file.exists():
            try:
                existing = pd.read_parquet(cache_file)
                df_copy = pd.concat([existing, df_copy]).drop_duplicates(
                    subset=["date"] if "symbol" not in df_copy.columns else ["date", "symbol"],
                    keep="last"
                )
            except Exception:
                pass

        df_copy.to_parquet(cache_file, compression=self.config.compression)

        self._cache_metadata[cache_key] = {
            "last_updated": datetime.now().isoformat(),
            "rows": len(df_copy)
        }
        self._save_metadata()

        logger.debug(f"Cached {len(df_copy)} rows to {cache_file}")

    def clear_cache(self, older_than: Optional[int] = None, pattern: Optional[str] = None) -> int:
        """清理缓存"""
        count = 0
        raw_dir = self.cache_dir / "raw"

        if older_than:
            from datetime import timedelta
            cutoff = today() - timedelta(days=older_than)
            for cache_file in raw_dir.rglob("*.parquet"):
                mtime = parse_date(cache_file.stat().st_mtime)
                if mtime < cutoff:
                    cache_file.unlink()
                    count += 1
        elif pattern:
            for cache_file in raw_dir.rglob(pattern):
                if cache_file.is_file():
                    cache_file.unlink()
                    count += 1
        else:
            for cache_file in raw_dir.rglob("*.parquet"):
                cache_file.unlink()
                count += 1
            ensure_dir(self.cache_dir / "features")

        logger.info(f"Cleared {count} cache files")
        return count

    def get_cache_size(self) -> Dict[str, str]:
        """获取缓存大小信息"""
        sizes = {}
        for path in self.cache_dir.rglob("*.parquet"):
            if path.is_file():
                relative = str(path.relative_to(self.cache_dir))
                sizes[relative] = format_size(path.stat().st_size)

        sizes["_total"] = format_size(sum(path.stat().st_size for path in self.cache_dir.rglob("*.parquet") if path.is_file()))
        return sizes

    # =============================================================================
    # 数据清洗
    # =============================================================================

    def clean(
        self,
        df: pd.DataFrame,
        fillna: Optional[str] = None,
        outlier: Optional[str] = None,
        filter_st: Optional[bool] = None,
        filter_suspended: Optional[bool] = None,
        filter_new: Optional[int] = None,
        inplace: bool = False
    ) -> pd.DataFrame:
        """数据清洗"""
        if not inplace:
            df = df.copy()

        report = DataQualityReport(
            total_rows=len(df),
            null_count={},
            outlier_count={},
            st_filtered=0,
            suspended_filtered=0,
            new_stock_filtered=0
        )

        # 空值填充
        fillna_method = fillna if fillna is not None else self.config.fillna
        if fillna_method and fillna_method != "none":
            df, null_counts = self._fillna(df, fillna_method)
            report.null_count = null_counts

        # 异常值处理
        outlier_method = outlier if outlier is not None else self.config.outlier_method
        if outlier_method and outlier_method != "none":
            df, outlier_counts = self._handle_outliers(df, outlier_method)
            report.outlier_count = outlier_counts

        # 过滤ST
        filter_st_flag = filter_st if filter_st is not None else self.config.filter_st
        if filter_st_flag:
            original_len = len(df)
            df = self._filter_st(df)
            report.st_filtered = original_len - len(df)

        # 过滤停牌
        filter_suspended_flag = filter_suspended if filter_suspended is not None else self.config.filter_suspended
        if filter_suspended_flag:
            original_len = len(df)
            df = self._filter_suspended(df)
            report.suspended_filtered = original_len - len(df)

        # 过滤新股
        filter_new_days = filter_new if filter_new is not None else self.config.filter_new
        if filter_new_days and filter_new_days > 0:
            original_len = len(df)
            df = self._filter_new_stocks(df, filter_new_days)
            report.new_stock_filtered = original_len - len(df)

        logger.info(f"Data cleaned: {report}")
        return df

    def _fillna(self, df: pd.DataFrame, method: str) -> tuple:
        """空值填充"""
        null_counts = {}
        numeric_cols = df.select_dtypes(include=["float64", "int64"]).columns

        for col in numeric_cols:
            null_counts[col] = df[col].isna().sum()
            if null_counts[col] > 0:
                if method == "ffill":
                    df[col] = df[col].ffill()
                elif method == "bfill":
                    df[col] = df[col].bfill()
                elif method == "zero":
                    df[col] = df[col].fillna(0)
                elif method == "drop":
                    df = df.dropna(subset=[col])

        return df, null_counts

    def _handle_outliers(self, df: pd.DataFrame, method: str) -> tuple:
        """异常值处理"""
        outlier_counts = {}
        threshold = self.config.outlier_threshold

        numeric_cols = df.select_dtypes(include=["float64", "int64"]).columns
        for col in numeric_cols:
            if df[col].isna().all():
                continue

            mean = df[col].mean()
            std = df[col].std()

            if std == 0:
                continue

            z_scores = abs((df[col] - mean) / std)
            mask = z_scores > threshold
            outlier_counts[col] = mask.sum()

            if outlier_counts[col] > 0:
                if method == "clip":
                    lower = mean - threshold * std
                    upper = mean + threshold * std
                    df[col] = df[col].clip(lower, upper)
                elif method == "nan":
                    df.loc[mask, col] = float("nan")

        return df, outlier_counts

    def _filter_st(self, df: pd.DataFrame) -> pd.DataFrame:
        """过滤ST股票"""
        if "symbol" not in df.columns:
            return df
        return df

    def _filter_suspended(self, df: pd.DataFrame) -> pd.DataFrame:
        """过滤停牌股票"""
        if "volume" not in df.columns:
            return df
        return df[df["volume"] > 0]

    def _filter_new_stocks(self, df: pd.DataFrame, min_days: int) -> pd.DataFrame:
        """过滤新股"""
        if "symbol" not in df.columns or "date" not in df.columns:
            return df

        first_trade = df.groupby("symbol")["date"].min()
        cutoff_date = df["date"].max() - pd.Timedelta(days=min_days)
        valid_symbols = first_trade[first_trade <= cutoff_date].index
        return df[df["symbol"].isin(valid_symbols)]

    def quality_report(self, df: pd.DataFrame) -> DataQualityReport:
        """生成数据质量报告"""
        return self.clean(df, fillna="none", outlier="none", inplace=False)

    # =============================================================================
    # 健康检查
    # =============================================================================

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            status = self.datasource.health_check()
            return {
                **status,
                "cache": self.get_cache_size(),
                "config": {"source": self.config.source, "cache_dir": str(self.cache_dir)}
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
