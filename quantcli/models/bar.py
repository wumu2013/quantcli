"""K线数据模型 - 统一掘金 Bar 对象和字典格式"""

from dataclasses import dataclass
from datetime import date, time, datetime
from typing import Optional


@dataclass
class MinuteBar:
    """分钟K线 dataclass - 统一掘金 Bar 对象和字典格式

    Attributes:
        symbol: 股票代码
        trade_date: 交易日期
        trade_time: 交易时间
        period: 分钟周期 ("1", "5", "15", "30", "60")
        open: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        volume: 成交量
        amount: 成交额
        eob: Bar 结束时间戳
    """
    symbol: str
    trade_date: date
    trade_time: time
    period: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float = 0.0
    eob: Optional[datetime] = None

    @classmethod
    def from_gm_bar(cls, symbol: str, bar, period: str = "5") -> "MinuteBar":
        """从 gm.api.Bar 对象创建 MinuteBar

        Args:
            symbol: 股票代码
            bar: gm.api.Bar 对象
            period: 分钟周期

        Returns:
            MinuteBar 实例
        """
        eob = bar.eob
        if isinstance(eob, str):
            eob = datetime.fromisoformat(eob.replace('Z', '+08:00'))
        return cls(
            symbol=symbol,
            trade_date=eob.date(),
            trade_time=eob.time(),
            period=period,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            amount=getattr(bar, 'amount', 0),
            eob=eob
        )

    @classmethod
    def from_dict(cls, symbol: str, data: dict, period: str = "5") -> "MinuteBar":
        """从字典创建 MinuteBar

        Args:
            symbol: 股票代码
            data: 字典格式的 bar 数据
            period: 分钟周期

        Returns:
            MinuteBar 实例
        """
        eob = data.get('eob')
        if isinstance(eob, str):
            eob = datetime.fromisoformat(eob.replace('Z', '+08:00'))
        elif eob is None:
            # 尝试从 trade_date 和 trade_time 构建
            trade_date = data.get('trade_date')
            trade_time = data.get('trade_time')
            if isinstance(trade_date, str):
                trade_date = datetime.fromisoformat(trade_date).date()
            if isinstance(trade_time, str):
                trade_time = datetime.fromisoformat(trade_time).time()
            if trade_date and trade_time:
                eob = datetime.combine(trade_date, trade_time)
            else:
                eob = None

        return cls(
            symbol=symbol,
            trade_date=data.get('trade_date') or eob.date() if eob else date.min,
            trade_time=data.get('trade_time') or eob.time() if eob else time.min,
            period=period,
            open=data['open'],
            high=data['high'],
            low=data['low'],
            close=data['close'],
            volume=data['volume'],
            amount=data.get('amount', 0),
            eob=eob
        )

    def to_dataframe_row(self) -> dict:
        """转换为 DataFrame 单行

        Returns:
            适合 DataFrame 追加的字典
        """
        return {
            "symbol": self.symbol,
            "date": self.trade_date,
            "time": self.trade_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount
        }

    def to_mysql_row(self) -> tuple:
        """转换为 MySQL 插入行的元组

        Returns:
            (symbol, trade_date, trade_time, period, open, high, low, close, volume, amount)
        """
        return (
            self.symbol,
            self.trade_date,
            self.trade_time,
            self.period,
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
            self.amount
        )


@dataclass
class DailyBar:
    """日K线 dataclass - 统一掘金 Bar 对象和字典格式

    Attributes:
        symbol: 股票代码
        trade_date: 交易日期
        open: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        volume: 成交量
        amount: 成交额
        eob: Bar 结束时间戳
    """
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float = 0.0
    eob: Optional[datetime] = None

    @classmethod
    def from_gm_bar(cls, symbol: str, bar) -> "DailyBar":
        """从 gm.api.Bar 对象创建 DailyBar

        Args:
            symbol: 股票代码
            bar: gm.api.Bar 对象

        Returns:
            DailyBar 实例
        """
        eob = bar.eob
        if isinstance(eob, str):
            eob = datetime.fromisoformat(eob.replace('Z', '+08:00'))
        return cls(
            symbol=symbol,
            trade_date=eob.date() if eob else date.today(),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            amount=getattr(bar, 'amount', 0),
            eob=eob
        )

    @classmethod
    def from_dict(cls, symbol: str, data: dict) -> "DailyBar":
        """从字典创建 DailyBar

        Args:
            symbol: 股票代码
            data: 字典格式的 bar 数据

        Returns:
            DailyBar 实例
        """
        eob = data.get('eob')
        if isinstance(eob, str):
            eob = datetime.fromisoformat(eob.replace('Z', '+08:00'))

        trade_date = data.get('trade_date')
        if isinstance(trade_date, str):
            trade_date = datetime.fromisoformat(trade_date).date()
        elif trade_date is None and eob:
            trade_date = eob.date()

        return cls(
            symbol=symbol,
            trade_date=trade_date or date.today(),
            open=data['open'],
            high=data['high'],
            low=data['low'],
            close=data['close'],
            volume=data['volume'],
            amount=data.get('amount', 0),
            eob=eob
        )

    def to_mysql_row(self) -> tuple:
        """转换为 MySQL 插入行的元组

        Returns:
            (symbol, trade_date, open, high, low, close, volume, amount)
        """
        return (
            self.symbol,
            self.trade_date,
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
            self.amount
        )
