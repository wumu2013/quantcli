"""日期时间工具

提供统一的日期时间处理功能:
- 日期解析和格式化
- 交易日判断
- 日期范围生成
- 时间间隔计算

Usage:
    >>> from quantcli.utils import parse_date, is_trading_day, trading_days_between
    >>> dt = parse_date("2024-01-30")
    >>> is_trading_day(dt, "2024-01-30")
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Union, TYPE_CHECKING
import re

if TYPE_CHECKING:
    from dataclasses import dataclass
else:
    # Python 3.9+ has dataclass in typing, but for compatibility use dataclasses
    from dataclasses import dataclass


# =============================================================================
# TimeContext - 时间基线
# =============================================================================

@dataclass
class TimeContext:
    """时间上下文 - 用于回测时注入历史时间

    Usage:
        >>> from quantcli.utils.time import TimeContext, today
        >>> TimeContext.set_date(date(2023, 12, 31))
        >>> today()
        datetime.date(2023, 12, 31)
        >>> TimeContext.reset()
        >>> today()
        datetime.date(2025, 1, 31)  # 当前日期
    """
    _instance: Optional["TimeContext"] = None

    def __init__(self, reference_date: Optional[date] = None):
        self.reference_date = reference_date

    @classmethod
    def get_date(cls) -> date:
        """获取基准日期，未设置则返回今天"""
        if cls._instance is not None and cls._instance.reference_date is not None:
            return cls._instance.reference_date
        return date.today()

    @classmethod
    def set_date(cls, d: date):
        """设置基准日期"""
        if cls._instance is None:
            cls._instance = TimeContext()
        cls._instance.reference_date = d

    @classmethod
    def reset(cls):
        """重置基准日期"""
        cls._instance = None

    @classmethod
    def get_date_for_price(cls) -> date:
        """获取价格数据的基准日期（日精度）"""
        return cls.get_date()

    @classmethod
    def get_date_for_fundamental(cls) -> date:
        """获取基本面数据的基准日期（月精度，降级到月初）"""
        d = cls.get_date()
        return date(d.year, d.month, 1)


def today() -> date:
    """获取今天的日期（受 TimeContext 影响）"""
    return TimeContext.get_date()


def now() -> datetime:
    """获取当前datetime（受 TimeContext 影响）"""
    d = TimeContext.get_date()
    return datetime.combine(d, datetime.min.time())


# 日期格式常量
DATE_FMT = "%Y-%m-%d"
DATETIME_FMT = "%Y-%m-%d %H:%M:%S"
COMPACT_FMT = "%Y%m%d"

# 常见日期格式列表
DATE_FORMATS = [
    DATE_FMT,           # 2024-01-30
    COMPACT_FMT,        # 20240130
    "%Y/%m/%d",         # 2024/01/30
    "%d/%m/%Y",         # 30/01/2024
    "%m-%d",            # 01-30 (月-日)
    "%Y%m",             # 202401 (年月)
]


def parse_date(
    d: Union[str, date, datetime],
    fmt: Optional[str] = None
) -> date:
    """解析日期字符串为 date 对象

    Args:
        d: 日期字符串或 date/datetime 对象
        fmt: 指定格式，None=尝试多种格式

    Returns:
        date 对象

    Raises:
        ValueError: 无法解析日期

    Examples:
        >>> parse_date("2024-01-30")
        >>> parse_date("20240130")
        >>> parse_date(date(2024, 1, 30))
    """
    # datetime 必须在 date 之前检查，因为 datetime 是 date 的子类
    if isinstance(d, datetime):
        return d.date()

    if isinstance(d, date):
        return d

    if isinstance(d, str):
        d = d.strip()

        # 尝试指定格式
        if fmt:
            try:
                return datetime.strptime(d, fmt).date()
            except ValueError:
                pass

        # 尝试多种格式 (包含 datetime 格式)
        formats_to_try = DATE_FORMATS + [DATETIME_FMT]
        for f in formats_to_try:
            try:
                return datetime.strptime(d, f).date()
            except ValueError:
                continue

    raise ValueError(f"Cannot parse date: {d}")


def parse_datetime(d: Union[str, date, datetime]) -> datetime:
    """解析为 datetime 对象"""
    if isinstance(d, datetime):
        return d
    if isinstance(d, date):
        return datetime.combine(d, datetime.min.time())

    d = d.strip()
    for fmt in [DATETIME_FMT, DATE_FMT, COMPACT_FMT]:
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {d}")


def format_date(d: Union[date, datetime], fmt: str = DATE_FMT) -> str:
    """格式化日期为字符串

    Args:
        d: date/datetime 对象
        fmt: 输出格式

    Returns:
        格式化的日期字符串
    """
    if isinstance(d, datetime):
        return d.strftime(fmt)
    return d.strftime(fmt)


def to_date(d: Union[str, date, datetime]) -> date:
    """统一转换为 date 对象 (别名)"""
    return parse_date(d)


# =============================================================================
# 交易日相关
# =============================================================================

# A 股节假日 (简化版，实际应查询数据源)
FIXED_HOLIDAYS = [
    # 元旦
    (1, 1),
    (1, 2),
    # 春节
    (1, 21), (1, 22), (1, 23), (1, 24), (1, 25), (1, 26), (1, 27),
    # 清明节
    (4, 4), (4, 5), (4, 6),
    # 劳动节
    (5, 1), (5, 2), (5, 3), (5, 4),
    # 端午节
    (6, 22), (6, 23), (6, 24),
    # 中秋节
    (9, 29), (9, 30), (10, 1), (10, 2), (10, 3), (10, 4),
    # 国庆节
    (10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7),
]

# 周末
WEEKEND = (5, 6)  # Saturday, Sunday


def is_trading_day(
    d: Union[date, datetime, str],
    trading_calendar: Optional[List[date]] = None
) -> bool:
    """判断是否为交易日

    Args:
        d: 日期
        trading_calendar: 交易日历列表，None=使用内置简易判断

    Returns:
        是否为交易日
    """
    dt = parse_date(d)

    # 如果提供了交易日历，直接查询
    if trading_calendar:
        return dt in trading_calendar

    # 简易判断: 排除周末
    if dt.weekday() >= 5:
        return False

    # 排除固定节假日 (简化版)
    if (dt.month, dt.day) in FIXED_HOLIDAYS:
        return False

    return True


def get_next_trading_day(
    d: Union[date, datetime, str],
    trading_calendar: Optional[List[date]] = None,
    n: int = 1
) -> date:
    """获取第 n 个下一个交易日

    Args:
        d: 起始日期
        trading_calendar: 交易日历
        n: 跳过多少个交易日

    Returns:
        下一个交易日
    """
    dt = parse_date(d)
    calendar_set = set(trading_calendar) if trading_calendar else None

    count = 0
    while count < n:
        dt += timedelta(days=1)
        if is_trading_day(dt, calendar_set):
            count += 1

    return dt


def get_prev_trading_day(
    d: Union[date, datetime, str],
    trading_calendar: Optional[List[date]] = None,
    n: int = 1
) -> date:
    """获取第 n 个上一个交易日

    Args:
        d: 起始日期
        trading_calendar: 交易日历
        n: 跳过多少个交易日

    Returns:
        上一个交易日
    """
    dt = parse_date(d)
    calendar_set = set(trading_calendar) if trading_calendar else None

    count = 0
    while count < n:
        dt -= timedelta(days=1)
        if is_trading_day(dt, calendar_set):
            count += 1

    return dt


def trading_days_between(
    start: Union[date, str],
    end: Union[date, str],
    trading_calendar: Optional[List[date]] = None
) -> int:
    """计算两个日期之间的交易日数量

    Args:
        start: 开始日期
        end: 结束日期
        trading_calendar: 交易日历

    Returns:
        交易日数量
    """
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    calendar_set = set(trading_calendar) if trading_calendar else None

    count = 0
    dt = start_dt
    while dt <= end_dt:
        if is_trading_day(dt, calendar_set):
            count += 1
        dt += timedelta(days=1)

    return count


def generate_trading_days(
    start: Union[date, str],
    end: Union[date, str],
    trading_calendar: Optional[List[date]] = None
) -> List[date]:
    """生成日期范围内的交易日列表

    Args:
        start: 开始日期
        end: 结束日期
        trading_calendar: 交易日历

    Returns:
        交易日列表
    """
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    calendar_set = set(trading_calendar) if trading_calendar else None

    result = []
    dt = start_dt
    while dt <= end_dt:
        if is_trading_day(dt, calendar_set):
            result.append(dt)
        dt += timedelta(days=1)

    return result


# =============================================================================
# 时间间隔
# =============================================================================

def add_trading_days(
    d: Union[date, str],
    n: int,
    trading_calendar: Optional[List[date]] = None
) -> date:
    """加减交易日

    Args:
        d: 起始日期
        n: 天数 (正数=未来, 负数=过去)
        trading_calendar: 交易日历

    Returns:
        结果日期
    """
    if n >= 0:
        return get_next_trading_day(d, trading_calendar, n)
    else:
        return get_prev_trading_day(d, trading_calendar, -n)


def days_between(
    start: Union[date, str],
    end: Union[date, str],
    include_end: bool = False
) -> int:
    """计算两个日期之间的自然日数量

    Args:
        start: 开始日期
        end: 结束日期
        include_end: 是否包含结束日期

    Returns:
        天数
    """
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    delta = (end_dt - start_dt).days
    if include_end:
        delta += 1
    return delta


def weeks_between(start: Union[date, str], end: Union[date, str]) -> int:
    """计算周数"""
    return days_between(start, end) // 7


def months_between(start: Union[date, str], end: Union[date, str]) -> int:
    """计算月数"""
    start_dt = parse_date(start)
    end_dt = parse_date(end)
    return (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)


def years_between(start: Union[date, str], end: Union[date, str]) -> float:
    """计算年数 (精确到月)"""
    return months_between(start, end) / 12


# =============================================================================
# 时间序列相关
# =============================================================================

def align_to_trading_days(
    dates: List[date],
    trading_calendar: Optional[List[date]] = None
) -> List[date]:
    """对齐到交易日 (只保留交易日)"""
    calendar_set = set(trading_calendar) if trading_calendar else None
    return [d for d in dates if is_trading_day(d, calendar_set)]


def fill_missing_trading_days(
    df,
    date_column: str = "date",
    trading_calendar: Optional[List[date]] = None,
    method: str = "ffill"
) -> date:
    """填充缺失的交易日

    Args:
        df: DataFrame
        date_column: 日期列名
        trading_calendar: 交易日历
        method: 填充方法 (ffill, bfill, None=不填充)

    Returns:
        填充后的 DataFrame
    """
    import pandas as pd

    dates = pd.to_datetime(df[date_column])
    min_date = dates.min()
    max_date = dates.max()

    full_range = pd.date_range(min_date, max_date, freq="B")  # 工作日

    # 过滤到交易日历
    if trading_calendar:
        trading_set = set(trading_calendar)
        full_range = [d for d in full_range if d.date() in trading_set]

    # 重新索引
    df = df.set_index(date_column)
    df = df.reindex(full_range)

    if method:
        if method == "ffill":
            df = df.ffill()
        elif method == "bfill":
            df = df.bfill()

    df = df.reset_index().rename(columns={"index": date_column})

    return df


# =============================================================================
# 便捷函数
# =============================================================================

def this_week_start() -> date:
    """本周第一天 (周一)"""
    today_dt = date.today()
    monday = today_dt - timedelta(days=today_dt.weekday())
    return monday


def this_month_start() -> date:
    """本月第一天"""
    today_dt = date.today()
    return date(today_dt.year, today_dt.month, 1)


def this_quarter_start() -> date:
    """本季度第一天"""
    today_dt = date.today()
    quarter = (today_dt.month - 1) // 3
    first_month = quarter * 3 + 1
    return date(today_dt.year, first_month, 1)


def this_year_start() -> date:
    """本年第一天"""
    return date(date.today().year, 1, 1)


def this_year_end() -> date:
    """本年最后一天"""
    year = date.today().year
    return date(year, 12, 31)
