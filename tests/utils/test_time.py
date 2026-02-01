"""utils/time.py 单元测试"""

import pytest
from datetime import date, datetime, timedelta
from quantcli.utils import (
    parse_date, parse_datetime, format_date, today, now,
    add_trading_days, days_between,
)


class TestParseDate:
    """parse_date 测试"""

    def test_parse_string_date(self):
        result = parse_date("2024-01-30")
        assert result == date(2024, 1, 30)

    def test_parse_string_with_time(self):
        # parse_date 现在支持带时间的字符串
        result = parse_date("2024-01-30 10:30:00")
        assert result == date(2024, 1, 30)

    def test_parse_date_object(self):
        input_date = date(2024, 1, 30)
        result = parse_date(input_date)
        assert result == input_date

    def test_parse_datetime_object(self):
        input_dt = datetime(2024, 1, 30, 10, 30)
        result = parse_date(input_dt)
        assert result == date(2024, 1, 30)

    def test_parse_invalid_string(self):
        with pytest.raises((ValueError, TypeError)):
            parse_date("invalid-date")


class TestFormatDate:
    """format_date 测试"""

    def test_format_date(self):
        result = format_date(date(2024, 1, 30))
        assert result == "2024-01-30"

    def test_format_with_format_string(self):
        result = format_date(date(2024, 1, 30), "%Y/%m/%d")
        assert result == "2024/01/30"


class TestToday:
    """today 测试"""

    def test_today_returns_date(self):
        result = today()
        assert isinstance(result, date)
        assert result == date.today()


class TestNow:
    """now 测试"""

    def test_now_returns_datetime(self):
        result = now()
        assert isinstance(result, datetime)


class TestAddTradingDays:
    """add_trading_days 测试"""

    def test_add_trading_days_positive(self):
        # 周五 -> 周二 (跳过周末)
        friday = date(2024, 1, 26)
        result = add_trading_days(friday, 2)
        assert result == date(2024, 1, 30)

    def test_add_trading_days_zero(self):
        monday = date(2024, 1, 29)
        result = add_trading_days(monday, 0)
        assert result == monday


class TestDaysBetween:
    """days_between 测试"""

    def test_days_between_same_day(self):
        d1 = date(2024, 1, 30)
        result = days_between(d1, d1)
        assert result == 0

    def test_days_between_positive(self):
        d1 = date(2024, 1, 1)
        d2 = date(2024, 1, 31)
        result = days_between(d1, d2)
        assert result == 30
