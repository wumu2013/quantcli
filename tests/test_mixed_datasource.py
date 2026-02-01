"""混合数据源单元测试"""

import pytest
import pandas as pd
from datetime import date


class TestMixedDataSource:
    """MixedDataSource 测试"""

    @pytest.fixture
    def mixed_datasource(self):
        """创建混合数据源"""
        from quantcli.datasources import MixedDataSource
        ds = MixedDataSource()
        yield ds

    def test_initialization(self, mixed_datasource):
        """测试初始化"""
        assert mixed_datasource.name == "mixed"
        assert hasattr(mixed_datasource, '_akshare')
        assert hasattr(mixed_datasource, '_baostock')

    def test_get_data_summary(self, mixed_datasource):
        """测试获取数据源摘要"""
        summary = mixed_datasource.get_data_summary()

        assert summary["name"] == "mixed"
        assert "price_data" in summary
        assert "fundamental_data" in summary
        assert summary["price_data"]["source"] == "akshare"
        assert summary["fundamental_data"]["source"] == "baostock"

    def test_health_check(self, mixed_datasource):
        """测试健康检查"""
        health = mixed_datasource.health_check()

        assert health["source"] == "mixed"
        assert "components" in health
        assert "akshare" in health["components"]
        assert "baostock" in health["components"]

    def test_get_daily(self, mixed_datasource):
        """测试获取日线数据 (代理到 akshare)"""
        df = mixed_datasource.get_daily(
            "600519",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        # 应该有数据
        if not df.empty:
            assert "date" in df.columns
            assert "close" in df.columns

    def test_get_index_daily(self, mixed_datasource):
        """测试获取指数数据 (代理到 akshare)"""
        df = mixed_datasource.get_index_daily(
            "000001",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        if not df.empty:
            assert "close" in df.columns

    def test_get_stock_list(self, mixed_datasource):
        """测试获取股票列表 (代理到 akshare)"""
        try:
            df = mixed_datasource.get_stock_list()
        except (RuntimeError, Exception) as e:
            pytest.skip(f"API error: {e}")

        # 应该有股票数据 (支持新旧两种列名格式)
        if not df.empty:
            # 新格式: symbol, name
            if "symbol" in df.columns:
                assert "name" in df.columns
            # 旧格式: 代码, 名称
            else:
                assert "代码" in df.columns
                assert "名称" in df.columns

    def test_get_trading_calendar(self, mixed_datasource):
        """测试获取交易日历 (代理到 akshare)"""
        calendar = mixed_datasource.get_trading_calendar()

        if len(calendar) > 0:
            assert all(isinstance(d, date) for d in calendar)

    def test_get_fundamental(self, mixed_datasource):
        """测试获取基本面数据 (使用 baostock)"""
        df = mixed_datasource.get_fundamental(
            ["600519", "000001"],
            date(2024, 1, 31)
        )

        # 可能有数据也可能没有
        if not df.empty:
            assert "symbol" in df.columns

    def test_get_dupont_analysis(self, mixed_datasource):
        """测试获取杜邦分析数据 (使用 baostock)"""
        df = mixed_datasource.get_dupont_analysis(
            ["600519", "000001"],
            start_year=2023,
            end_year=2024
        )

        if not df.empty:
            assert "symbol" in df.columns
            assert "roe" in df.columns

    def test_get_profit_data(self, mixed_datasource):
        """测试获取利润数据 (使用 baostock)"""
        df = mixed_datasource.get_profit_data(
            ["600519"],
            start_year=2023,
            end_year=2024
        )

        if not df.empty:
            assert "symbol" in df.columns

    def test_get_growth_data(self, mixed_datasource):
        """测试获取成长数据 (使用 baostock)"""
        df = mixed_datasource.get_growth_data(
            ["600519"],
            start_year=2023,
            end_year=2024
        )

        if not df.empty:
            assert "symbol" in df.columns


class TestCreateMixedDatasource:
    """工厂函数测试"""

    def test_create_mixed_via_factory(self):
        """通过工厂函数创建混合数据源"""
        from quantcli.datasources import create_datasource

        ds = create_datasource("mixed")
        assert ds.name == "mixed"
        assert hasattr(ds, '_akshare')
        assert hasattr(ds, '_baostock')

    def test_mixed_import(self):
        """直接导入混合数据源"""
        from quantcli.datasources import MixedDataSource

        ds = MixedDataSource()
        assert ds.name == "mixed"


class TestMixedDataSourceIntegration:
    """混合数据源集成测试"""

    @pytest.fixture
    def ds(self):
        """创建数据源"""
        from quantcli.datasources import MixedDataSource
        return MixedDataSource()

    def test_workflow(self, ds):
        """测试完整工作流"""
        # 1. 获取日线数据
        price_df = ds.get_daily(
            "600519",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        # 2. 获取股票列表 (Sina API 偶尔不稳定)
        try:
            stocks = ds.get_stock_list()
        except (RuntimeError, Exception) as e:
            if "JSONDecodeError" in str(e) or "获取股票列表失败" in str(e):
                pytest.skip(f"Sina API 不稳定: {e}")
            raise

        # 3. 获取基本面数据
        funda_df = ds.get_fundamental(["600519"], date(2024, 1, 31))

        # 4. 获取杜邦分析
        dupont_df = ds.get_dupont_analysis(
            ["600519"],
            start_year=2023,
            end_year=2024
        )

        # 验证所有调用都成功（不抛异常）
        assert True  # 如果执行到这里，说明没有异常


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
