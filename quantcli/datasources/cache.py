"""数据源缓存基类

提供基于文件的缓存功能，适合基本面等更新频率低的数据。

使用示例:
    >>> cache = DataSourceCache("fundamentals", ttl=86400)  # 24小时过期
    >>> df = cache.get("600519_dupont")  # 尝试读取缓存
    >>> if df is None:
    >>>     df = fetch_from_api()  # API 获取
    >>>     cache.set("600519_dupont", df)  # 写入缓存
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Optional, Any, Dict
import pandas as pd

from ..utils import get_logger, data_dir, ensure_dir

logger = get_logger(__name__)


class DataSourceCache:
    """数据源缓存管理器

    Args:
        cache_type: 缓存类型 (会创建 data/cache/{type} 目录)
        ttl: 缓存过期时间 (秒)，默认 24 小时
        enabled: 是否启用缓存，默认 True
    """

    def __init__(
        self,
        cache_type: str = "datasource",
        ttl: int = 86400,  # 24小时
        enabled: bool = True
    ):
        self.cache_type = cache_type
        self.ttl = ttl
        self.enabled = enabled
        self.cache_dir = data_dir("cache") / cache_type
        ensure_dir(self.cache_dir)

    def _make_key(self, key: str) -> str:
        """生成缓存文件名"""
        # 使用 MD5 避免特殊字符问题
        hash_key = hashlib.md5(key.encode()).hexdigest()[:16]
        return f"{hash_key}.parquet"

    def _get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / self._make_key(key)

    def _is_expired(self, path: Path) -> bool:
        """检查缓存是否过期"""
        if not path.exists():
            return True

        # 检查文件年龄
        age = time.time() - path.stat().st_ctime
        return age > self.ttl

    def get(self, key: str) -> Optional[pd.DataFrame]:
        """读取缓存

        Args:
            key: 缓存键

        Returns:
            缓存的 DataFrame，不存在或已过期返回 None
        """
        if not self.enabled:
            return None

        try:
            path = self._get_cache_path(key)

            if self._is_expired(path):
                logger.debug(f"缓存已过期: {key}")
                return None

            if not path.exists():
                logger.debug(f"缓存不存在: {key}")
                return None

            df = pd.read_parquet(path)
            logger.debug(f"缓存命中: {key}, {len(df)} 行")
            return df

        except Exception as e:
            logger.warning(f"读取缓存失败: {key}, {e}")
            return None

    def set(self, key: str, df: pd.DataFrame) -> bool:
        """写入缓存

        Args:
            key: 缓存键
            df: 要缓存的 DataFrame

        Returns:
            是否成功
        """
        if not self.enabled:
            return False

        if df is None or df.empty:
            return False

        try:
            path = self._get_cache_path(key)
            df.to_parquet(path, index=False)
            logger.debug(f"缓存写入: {key}, {len(df)} 行")
            return True

        except Exception as e:
            logger.warning(f"写入缓存失败: {key}, {e}")
            return False

    def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            path = self._get_cache_path(key)
            if path.exists():
                path.unlink()
                logger.debug(f"缓存删除: {key}")
            return True
        except Exception as e:
            logger.warning(f"删除缓存失败: {key}, {e}")
            return False

    def clear(self) -> int:
        """清空所有缓存

        Returns:
            删除的文件数量
        """
        count = 0
        for path in self.cache_dir.glob("*.parquet"):
            try:
                path.unlink()
                count += 1
            except Exception as e:
                logger.warning(f"删除缓存失败: {path}, {e}")
        logger.info(f"已清空 {count} 个缓存文件")
        return count

    def cleanup(self, max_age: Optional[int] = None) -> int:
        """清理过期缓存

        Args:
            max_age: 最大年龄 (秒)，默认使用 ttl

        Returns:
            删除的文件数量
        """
        max_age = max_age or self.ttl
        cutoff = time.time() - max_age
        count = 0

        for path in self.cache_dir.glob("*.parquet"):
            try:
                if path.stat().st_ctime < cutoff:
                    path.unlink()
                    count += 1
            except Exception as e:
                logger.warning(f"清理缓存失败: {path}, {e}")

        logger.info(f"已清理 {count} 个过期缓存文件")
        return count

    def stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        files = list(self.cache_dir.glob("*.parquet"))
        total_size = sum(f.stat().st_size for f in files if f.exists())

        # 计算过期文件
        now = time.time()
        expired = sum(
            1 for f in files
            if f.exists() and (now - f.stat().st_ctime) > self.ttl
        )

        return {
            "cache_dir": str(self.cache_dir),
            "file_count": len(files),
            "total_size": total_size,
            "expired_count": expired,
            "ttl": self.ttl,
            "enabled": self.enabled,
        }

    def get_or_fetch(
        self,
        key: str,
        fetch_func,
        transform_func=None
    ) -> pd.DataFrame:
        """获取缓存或重新获取

        Args:
            key: 缓存键
            fetch_func: 获取数据的函数 (无参数)
            transform_func: 数据转换函数 (可选)

        Returns:
            DataFrame
        """
        # 尝试从缓存获取
        df = self.get(key)

        if df is not None:
            return df

        # 从 API 获取
        df = fetch_func()

        if df is not None and not df.empty:
            # 写入缓存
            self.set(key, df)

            # 可选转换
            if transform_func:
                df = transform_func(df)

        return df


class FundamentalsCache(DataSourceCache):
    """基本面数据专用缓存

    特点：
    - TTL: 24 小时 (财报按季度发布)
    - 存储格式: Parquet (高效压缩)
    """

    def __init__(self, enabled: bool = True):
        super().__init__(
            cache_type="fundamentals",
            ttl=86400,  # 24小时
            enabled=enabled
        )

    def get_dupont(self, symbol: str) -> Optional[pd.DataFrame]:
        """获取杜邦分析缓存"""
        return self.get(f"dupont_{symbol}")

    def set_dupont(self, symbol: str, df: pd.DataFrame) -> bool:
        """缓存杜邦分析数据"""
        return self.set(f"dupont_{symbol}", df)

    def get_profit(self, symbol: str) -> Optional[pd.DataFrame]:
        """获取利润数据缓存"""
        return self.get(f"profit_{symbol}")

    def set_profit(self, symbol: str, df: pd.DataFrame) -> bool:
        """缓存利润数据"""
        return self.set(f"profit_{symbol}", df)

    def get_growth(self, symbol: str) -> Optional[pd.DataFrame]:
        """获取成长数据缓存"""
        return self.get(f"growth_{symbol}")

    def set_growth(self, symbol: str, df: pd.DataFrame) -> bool:
        """缓存成长数据"""
        return self.set(f"growth_{symbol}", df)


class PriceCache(DataSourceCache):
    """价格数据缓存 (短期 TTL)"""

    def __init__(self, enabled: bool = True):
        super().__init__(
            cache_type="prices",
            ttl=3600,  # 1小时
            enabled=enabled
        )

    def get_daily(self, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """获取日线数据缓存

        Args:
            symbol: 股票代码 (如 600519)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            缓存的 DataFrame 或 None
        """
        key = f"daily_{symbol}_{start_date}_{end_date}"
        return self.get(key)

    def set_daily(self, symbol: str, start_date: str, end_date: str, df: pd.DataFrame) -> bool:
        """缓存日线数据"""
        key = f"daily_{symbol}_{start_date}_{end_date}"
        return self.set(key, df)

    def get_index(self, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """获取指数数据缓存"""
        key = f"index_{symbol}_{start_date}_{end_date}"
        return self.get(key)

    def set_index(self, symbol: str, start_date: str, end_date: str, df: pd.DataFrame) -> bool:
        """缓存指数数据"""
        key = f"index_{symbol}_{start_date}_{end_date}"
        return self.set(key, df)


class StockListCache(DataSourceCache):
    """股票列表缓存 (中等 TTL)"""

    def __init__(self, enabled: bool = True):
        super().__init__(
            cache_type="stocklist",
            ttl=3600 * 6,  # 6小时
            enabled=enabled
        )

    def get_list(self, market: str = "all") -> Optional[pd.DataFrame]:
        """获取股票列表缓存

        Args:
            market: 市场类型 (all, 上海, 深圳)

        Returns:
            缓存的 DataFrame 或 None
        """
        key = f"stocklist_{market}"
        return self.get(key)

    def set_list(self, market: str = "all", df: pd.DataFrame = None) -> bool:
        """缓存股票列表"""
        key = f"stocklist_{market}"
        return self.set(key, df)


class TradingCalendarCache(DataSourceCache):
    """交易日历缓存 (长期 TTL)"""

    def __init__(self, enabled: bool = True):
        super().__init__(
            cache_type="calendar",
            ttl=86400 * 7,  # 7天
            enabled=enabled
        )

    def get_calendar(self, exchange: str = "SSE") -> Optional[pd.DataFrame]:
        """获取交易日历缓存"""
        key = f"calendar_{exchange}"
        return self.get(key)

    def set_calendar(self, exchange: str = "SSE", df: pd.DataFrame = None) -> bool:
        """缓存交易日历"""
        key = f"calendar_{exchange}"
        return self.set(key, df)


def make_cache_key(prefix: str, **kwargs) -> str:
    """便捷函数：生成缓存键

    Args:
        prefix: 前缀
        **kwargs: 参数 (会自动排序)

    Returns:
        缓存键字符串

    Example:
        >>> make_cache_key("daily", symbol="600519", start="2024-01-01")
        'daily_symbol=600519_start=2024-01-01'
    """
    parts = [prefix]
    for k, v in sorted(kwargs.items()):
        parts.append(f"{k}={v}")
    return "_".join(parts)
