"""测试时间工具模块"""

from datetime import date, datetime
import pytest

from quantcli.utils.time import (
    TimeContext, today, now,
    parse_date, format_date,
    months_between, days_between
)


class TestTimeContext:
    """TimeContext 测试类"""

    def setup_method(self):
        """每个测试前重置 TimeContext"""
        TimeContext.reset()

    def teardown_method(self):
        """每个测试后重置 TimeContext"""
        TimeContext.reset()

    def test_today_without_context(self):
        """测试未设置上下文时 today() 返回当前日期"""
        result = today()
        assert isinstance(result, date)
        assert result == date.today()

    def test_now_without_context(self):
        """测试未设置上下文时 now() 返回当前日期时间"""
        result = now()
        assert isinstance(result, datetime)
        assert result.date() == date.today()

    def test_set_date(self):
        """测试设置基准日期"""
        target_date = date(2023, 12, 31)
        TimeContext.set_date(target_date)

        assert TimeContext.get_date() == target_date
        assert today() == target_date

    def test_reset(self):
        """测试重置基准日期"""
        TimeContext.set_date(date(2023, 12, 31))
        assert today() == date(2023, 12, 31)

        TimeContext.reset()
        assert today() == date.today()

    def test_get_date_for_price(self):
        """测试获取价格数据日期（日精度）"""
        target_date = date(2023, 12, 31)
        TimeContext.set_date(target_date)

        assert TimeContext.get_date_for_price() == date(2023, 12, 31)

    def test_get_date_for_fundamental(self):
        """测试获取基本面数据日期（月精度）"""
        target_date = date(2023, 12, 15)  # 月中
        TimeContext.set_date(target_date)

        # 应该降级到月初
        assert TimeContext.get_date_for_fundamental() == date(2023, 12, 1)

    def test_get_date_for_fundamental_month_start(self):
        """测试月初日期保持不变"""
        target_date = date(2023, 12, 1)
        TimeContext.set_date(target_date)

        assert TimeContext.get_date_for_fundamental() == date(2023, 12, 1)

    def test_get_date_for_fundamental_year_end(self):
        """测试年末日期"""
        target_date = date(2023, 12, 31)
        TimeContext.set_date(target_date)

        assert TimeContext.get_date_for_fundamental() == date(2023, 12, 1)

    def test_set_date_twice(self):
        """测试重复设置日期"""
        TimeContext.set_date(date(2023, 6, 15))
        TimeContext.set_date(date(2023, 12, 31))

        assert today() == date(2023, 12, 31)

    def test_context_isolation(self):
        """测试上下文隔离"""
        # 设置日期A
        TimeContext.set_date(date(2023, 1, 1))
        assert today() == date(2023, 1, 1)

        # 重置后应该恢复
        TimeContext.reset()
        assert today() == date.today()

        # 设置日期B
        TimeContext.set_date(date(2024, 6, 15))
        assert today() == date(2024, 6, 15)

    def test_context_without_date(self):
        """测试不设置日期时回退到今天"""
        TimeContext.reset()

        result = TimeContext.get_date()
        assert result == date.today()


class TestDateFunctions:
    """日期函数测试"""

    def test_parse_date_formats(self):
        """测试多种日期格式解析"""
        assert parse_date("2024-01-30") == date(2024, 1, 30)
        assert parse_date("20240130") == date(2024, 1, 30)
        assert parse_date("2024/01/30") == date(2024, 1, 30)
        assert parse_date(date(2024, 1, 30)) == date(2024, 1, 30)

    def test_format_date(self):
        """测试日期格式化"""
        d = date(2024, 1, 30)
        assert format_date(d) == "2024-01-30"
        assert format_date(d, "%Y%m%d") == "20240130"

    def test_months_between(self):
        """测试月数计算"""
        assert months_between("2024-01-01", "2024-12-31") == 11
        assert months_between("2023-12-01", "2024-01-31") == 1
        assert months_between("2023-01-01", "2024-01-01") == 12

    def test_days_between(self):
        """测试天数计算"""
        assert days_between("2024-01-01", "2024-01-10") == 9
        # 逆序返回负值
        assert days_between("2024-01-10", "2024-01-01") == -9
        assert days_between("2024-01-01", "2024-01-01", include_end=True) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
