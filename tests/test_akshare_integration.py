"""Akshare 数据源集成测试

使用稳定的腾讯/新浪接口：
- 日线数据: stock_zh_a_hist_tx (腾讯)
- 股票列表: stock_zh_a_spot (新浪)
- 交易日历: tool_trade_date_hist_sina (新浪)
- 指数日线: stock_zh_index_daily_tx (腾讯)

这些测试会实际调用 akshare API，用于验证数据获取功能正常工作。
"""

import pytest
import pandas as pd
from datetime import date, timedelta
from quantcli.datasources.akshare import AkshareDataSource


def check_akshare_available():
    """检查 akshare 是否可用（不实际调用 API）"""
    try:
        import akshare
        return True
    except ImportError:
        return False


require_network = pytest.mark.skipif(
    not check_akshare_available(),
    reason="akshare not installed"
)


class TestAkshareIntegration:
    """Akshare 实际 API 集成测试"""

    @pytest.fixture
    def datasource(self):
        ds = AkshareDataSource()
        yield ds

    @require_network
    def test_health_check(self, datasource):
        """健康检查"""
        health = datasource.health_check()
        assert health["status"] == "ok"
        assert health["source"] == "akshare"

    @require_network
    def test_get_daily_real(self, datasource):
        """获取真实日线数据（腾讯接口）"""
        df = datasource.get_daily(
            "600519",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        assert not df.empty, "应该获取到数据"
        assert "date" in df.columns
        assert "close" in df.columns
        assert "open" in df.columns
        assert len(df) > 0

    @require_network
    def test_get_daily_with_suffix(self, datasource):
        """测试带后缀的股票代码"""
        df = datasource.get_daily(
            "600519.SH",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        assert not df.empty
        assert "close" in df.columns

    @require_network
    def test_get_daily_sz_stock(self, datasource):
        """测试深圳股票"""
        df = datasource.get_daily(
            "000001",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        if not df.empty:
            assert "close" in df.columns

    @require_network
    def test_get_stock_list_real(self, datasource):
        """获取真实股票列表（新浪接口）"""
        stocks = datasource.get_stock_list()

        assert len(stocks) > 0, "应该获取到股票列表"
        assert all(hasattr(s, "symbol") for s in stocks)
        assert all(hasattr(s, "name") for s in stocks)
        assert all(hasattr(s, "exchange") for s in stocks)

        # 验证股票代码格式
        for stock in stocks[:10]:
            assert len(stock.symbol) >= 6
            assert stock.exchange in ["SSE", "SZSE"]

    @require_network
    def test_get_stock_list_filter_sh(self, datasource):
        """筛选上海市场股票"""
        sh_stocks = datasource.get_stock_list("上海")

        assert len(sh_stocks) > 0
        for stock in sh_stocks:
            assert stock.market == "上海"

    @require_network
    def test_get_stock_list_filter_sz(self, datasource):
        """筛选深圳市场股票"""
        sz_stocks = datasource.get_stock_list("深圳")

        assert len(sz_stocks) > 0
        for stock in sz_stocks:
            assert stock.market == "深圳"

    @require_network
    def test_get_trading_calendar_real(self, datasource):
        """获取真实交易日历（新浪接口）"""
        calendar = datasource.get_trading_calendar()

        assert len(calendar) > 0, "应该获取到交易日历"
        assert all(isinstance(d, date) for d in calendar)

        # 一年应该有至少200个交易日
        assert len(calendar) >= 200

        # 验证日期排序
        assert calendar == sorted(calendar)

    @require_network
    def test_get_index_daily_sh(self, datasource):
        """获取上证指数数据（腾讯接口）"""
        df = datasource.get_index_daily(
            "000001",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        assert not df.empty, "应该获取到指数数据"
        assert "close" in df.columns

    @require_network
    def test_get_index_daily_sz(self, datasource):
        """获取深证成指数据"""
        df = datasource.get_index_daily(
            "399001",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        if not df.empty:
            assert "close" in df.columns


class TestAkshareDataQuality:
    """数据质量测试"""

    @pytest.fixture
    def datasource(self):
        ds = AkshareDataSource()
        yield ds

    @require_network
    def test_daily_data_not_future_dated(self, datasource):
        """验证数据不包含未来日期"""
        df = datasource.get_daily(
            "600519",
            date(2023, 1, 1),
            date(2023, 12, 31)
        )

        if not df.empty:
            today = date.today()
            future_dates = df[df["date"] > today]
            assert len(future_dates) == 0

    @require_network
    def test_daily_price_positive(self, datasource):
        """验证价格数据为正"""
        df = datasource.get_daily(
            "600519",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        if not df.empty:
            assert (df["close"] > 0).all(), "收盘价应该都为正"
            assert (df["open"] > 0).all(), "开盘价应该都为正"
            assert (df["high"] > 0).all(), "最高价应该都为正"
            assert (df["low"] > 0).all(), "最低价应该都为正"

    @require_network
    def test_daily_high_ge_low(self, datasource):
        """验证最高价 >= 最低价"""
        df = datasource.get_daily(
            "600519",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        if not df.empty:
            assert (df["high"] >= df["low"]).all()

    @require_network
    def test_daily_amount_positive(self, datasource):
        """验证成交额为正"""
        df = datasource.get_daily(
            "600519",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        if not df.empty and "amount" in df.columns:
            assert (df["amount"] >= 0).all()


class TestAkshareEdgeCases:
    """边界情况测试"""

    @pytest.fixture
    def datasource(self):
        ds = AkshareDataSource()
        yield ds

    @require_network
    def test_invalid_symbol(self, datasource):
        """测试无效股票代码"""
        df = datasource.get_daily(
            "000000",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )
        # 应该返回空 DataFrame
        assert df.empty

    @require_network
    def test_empty_date_range(self, datasource):
        """测试空日期范围"""
        df = datasource.get_daily(
            "600519",
            date(2024, 12, 31),
            date(2024, 1, 1)
        )
        assert df.empty

    @require_network
    def test_future_date_range(self, datasource):
        """测试未来日期范围"""
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        df = datasource.get_daily("600519", start_date, end_date)

        if not df.empty:
            assert df["date"].min() >= start_date
            assert df["date"].max() <= end_date

    @require_network
    def test_get_stock_list_all_markets(self, datasource):
        """获取所有市场股票并验证分布"""
        all_stocks = datasource.get_stock_list()
        sh_stocks = datasource.get_stock_list("上海")
        sz_stocks = datasource.get_stock_list("深圳")

        assert len(all_stocks) == len(sh_stocks) + len(sz_stocks)

    @require_network
    def test_trading_calendar_completeness(self, datasource):
        """验证交易日历完整性"""
        calendar = datasource.get_trading_calendar()

        assert len(calendar) > 0
        assert len(calendar) == len(set(calendar))
        assert None not in calendar

    @require_network
    def test_index_not_found(self, datasource):
        """测试不存在的指数"""
        df = datasource.get_index_daily(
            "999999",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )
        # 可能返回空 DataFrame 或抛出异常
        assert df.empty or "error" in str(type(df)).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
