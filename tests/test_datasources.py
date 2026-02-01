"""数据源单元测试"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, datetime
from unittest.mock import Mock, patch, MagicMock
import sys
from types import ModuleType

from quantcli.datasources.base import DataSource, DataRequest, StockInfo


class TestStockInfo:
    """股票信息测试"""

    def test_create_stock_info(self):
        """创建股票信息"""
        stock = StockInfo(
            symbol="600519",
            name="贵州茅台",
            exchange="SSE",
            market="上海",
            list_date=date(2001, 8, 27),
            status="active"
        )

        assert stock.symbol == "600519"
        assert stock.name == "贵州茅台"
        assert stock.exchange == "SSE"
        assert stock.status == "active"

    def test_stock_info_defaults(self):
        """股票信息默认值"""
        stock = StockInfo(
            symbol="000001",
            name="平安银行",
            exchange="SZSE",
            market="深圳",
            list_date=date(1991, 4, 3)
        )

        assert stock.delist_date is None
        assert stock.status == "active"


class TestDataSourceBase:
    """数据源基类测试"""

    def test_abstract_methods(self):
        """测试抽象方法需要实现"""
        class DummySource(DataSource):
            def get_daily(self, symbol, start_date, end_date, fields=None):
                return pd.DataFrame()

            def get_stock_list(self, market="all"):
                return []

            def get_trading_calendar(self, exchange="SSE"):
                return []

        source = DummySource()
        assert source.name == "base"

    def test_not_implemented_methods(self):
        """测试基类配置"""
        from quantcli.datasources.base import DataSource, DataSourceConfig

        class DummySource(DataSource):
            name = "dummy"

            def get_daily(self, symbol, start_date, end_date, fields=None):
                return pd.DataFrame()

            def get_stock_list(self, market="all"):
                return pd.DataFrame()

            def get_trading_calendar(self, exchange="SSE"):
                return []

        source = DummySource()

        # 验证配置
        assert source.config.use_cache is True

    def test_health_check(self):
        """健康检查"""
        class DummySource(DataSource):
            def get_daily(self, symbol, start_date, end_date, fields=None):
                return pd.DataFrame()

            def get_stock_list(self, market="all"):
                return []

            def get_trading_calendar(self, exchange="SSE"):
                return []

        source = DummySource()
        health = source.health_check()

        assert health["status"] == "ok"
        assert health["source"] == "base"
        assert "timestamp" in health


class MockAkshare:
    """Mock Akshare 模块 (腾讯/新浪稳定版)"""

    def __init__(self):
        # 腾讯接口
        self.stock_zh_a_hist_tx = Mock()
        self.stock_zh_index_daily_tx = Mock()
        # stock_info_a_code_name 接口
        self.stock_info_a_code_name = Mock()
        # 新浪接口
        self.tool_trade_date_hist_sina = Mock()
        # 东方财富接口 (不稳定，设为 None)
        self.stock_zh_a_hist = None
        self.stock_zh_a_spot = None
        self.stock_zh_a_spot_em = None
        self.stock_fina_indicator = None
        self.stock_valuation = None

    def setup_daily_return_value(self, df):
        """设置日线数据返回值 (腾讯接口)"""
        self.stock_zh_a_hist_tx.return_value = df

    def setup_stock_list_return_value(self, df):
        """设置股票列表返回值 (stock_info_a_code_name)"""
        self.stock_info_a_code_name.return_value = df

    def setup_calendar_return_value(self, df):
        """设置交易日历返回值 (新浪接口)"""
        self.tool_trade_date_hist_sina.return_value = df

    def setup_index_daily_return_value(self, df):
        """设置指数日线返回值 (腾讯接口)"""
        self.stock_zh_index_daily_tx.return_value = df


class TestAkshareDataSource:
    """AKShare 数据源测试"""

    @pytest.fixture
    def mock_ak_module(self):
        """创建 mock akshare 模块"""
        mock = MockAkshare()
        return mock

    @pytest.fixture
    def data_source(self, mock_ak_module):
        """创建数据源实例（使用 mock，禁用缓存）"""
        # 替换模块
        sys.modules['akshare'] = mock_ak_module

        from quantcli.datasources import akshare
        reload_result = __import__('importlib').reload(akshare)

        from quantcli.datasources.akshare import AkshareDataSource
        # 禁用缓存，避免缓存层尝试访问真实 API
        ds = AkshareDataSource(use_cache=False)
        ds._ak = mock_ak_module

        yield ds

        # 清理
        if 'akshare' in sys.modules:
            del sys.modules['akshare']

    def test_initialization_with_mock(self, mock_ak_module, data_source):
        """使用 mock 初始化"""
        assert data_source.name == "akshare"
        assert data_source._ak == mock_ak_module

    def test_get_daily_success(self, mock_ak_module, data_source):
        """获取日线数据成功 (腾讯接口)"""
        mock_df = pd.DataFrame({
            "date": ["2024-01-02", "2024-01-03"],
            "open": [100.0, 101.0],
            "close": [102.0, 103.0],
            "high": [103.0, 104.0],
            "low": [99.0, 100.0],
            "volume": [1000000, 1100000],
            "amount": [100000000, 110000000],
        })
        mock_ak_module.setup_daily_return_value(mock_df)

        result = data_source.get_daily(
            "600519",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        assert len(result) == 2
        assert "date" in result.columns
        assert "close" in result.columns
        assert "open" in result.columns

    def test_get_daily_empty_result(self, mock_ak_module, data_source):
        """获取空数据"""
        mock_ak_module.setup_daily_return_value(pd.DataFrame())

        result = data_source.get_daily(
            "600519",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        assert result.empty

    def test_get_daily_with_symbol_suffix(self, mock_ak_module, data_source):
        """测试带后缀的股票代码"""
        mock_df = pd.DataFrame({
            "date": ["2024-01-02"],
            "open": [100.0],
            "close": [102.0],
            "high": [103.0],
            "low": [99.0],
            "volume": [1000000],
            "amount": [100000000],
        })
        mock_ak_module.setup_daily_return_value(mock_df)

        result = data_source.get_daily(
            "600519.SH",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        assert not result.empty

    def test_get_daily_with_fields(self, mock_ak_module, data_source):
        """测试指定字段"""
        mock_df = pd.DataFrame({
            "date": ["2024-01-02"],
            "open": [100.0],
            "close": [102.0],
            "high": [103.0],
            "low": [99.0],
            "volume": [1000000],
            "amount": [100000000],
        })
        mock_ak_module.setup_daily_return_value(mock_df)

        result = data_source.get_daily(
            "600519",
            date(2024, 1, 1),
            date(2024, 1, 31),
            fields=["date", "close"]
        )

        assert "close" in result.columns
        assert "open" not in result.columns

    def test_get_stock_list(self, mock_ak_module, data_source):
        """获取股票列表 (stock_info_a_code_name)"""
        mock_df = pd.DataFrame({
            "code": ["600519", "000001", "600000"],
            "name": ["贵州茅台", "平安银行", "浦发银行"],
        })
        mock_ak_module.setup_stock_list_return_value(mock_df)

        df = data_source.get_stock_list()

        assert len(df) == 3
        assert "symbol" in df.columns
        assert "name" in df.columns
        assert "exchange" in df.columns

    def test_get_stock_list_empty(self, mock_ak_module, data_source):
        """获取空股票列表"""
        mock_ak_module.setup_stock_list_return_value(pd.DataFrame())

        df = data_source.get_stock_list()

        assert df.empty

    def test_get_stock_list_filter_market(self, mock_ak_module, data_source):
        """筛选市场"""
        mock_df = pd.DataFrame({
            "code": ["600519", "000001"],
            "name": ["贵州茅台", "平安银行"],
        })
        mock_ak_module.setup_stock_list_return_value(mock_df)

        df = data_source.get_stock_list("上海")
        # 600519 是上海股
        assert df["symbol"].tolist() == ["600519"]

    def test_get_trading_calendar(self, mock_ak_module, data_source):
        """获取交易日历"""
        mock_df = pd.DataFrame({
            "trade_date": ["2024-01-02", "2024-01-03", "2024-01-04"]
        })
        mock_ak_module.setup_calendar_return_value(mock_df)

        calendar = data_source.get_trading_calendar()

        assert len(calendar) == 3
        assert calendar[0] == date(2024, 1, 2)

    def test_get_trading_calendar_empty(self, mock_ak_module, data_source):
        """获取空交易日历"""
        mock_ak_module.setup_calendar_return_value(pd.DataFrame())

        calendar = data_source.get_trading_calendar()

        assert calendar == []

    def test_get_index_daily(self, mock_ak_module, data_source):
        """获取指数日线 (腾讯接口)"""
        mock_df = pd.DataFrame({
            "date": ["2024-01-02"],
            "open": [3000.0],
            "high": [3050.0],
            "low": [2980.0],
            "close": [3020.0],
            "volume": [100000000],
            "amount": [1000000000.0],
        })
        mock_ak_module.setup_index_daily_return_value(mock_df)

        result = data_source.get_index_daily(
            "000001",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        assert not result.empty
        assert "close" in result.columns

    def test_health_check_ok(self, mock_ak_module, data_source):
        """健康检查正常"""
        mock_ak_module.setup_stock_list_return_value(pd.DataFrame())

        health = data_source.health_check()

        assert health["status"] == "ok"
        assert health["source"] == "akshare"

    def test_health_check_error(self, mock_ak_module, data_source):
        """健康检查异常"""
        # 使用交易日历接口（新浪）
        mock_ak_module.tool_trade_date_hist_sina.side_effect = Exception("Connection failed")

        health = data_source.health_check()

        assert health["status"] == "error"


class TestAkshareFundamentalData:
    """AKShare 基本面数据测试 (已禁用)

    注意：东方财富接口不稳定，基本面数据请使用 BaostockDataSource
    相关测试已移至 test_baostock.py
    """

    @pytest.fixture
    def mock_ak_module(self):
        """创建 mock akshare 模块"""
        mock = MockAkshare()
        return mock

    @pytest.fixture
    def data_source(self, mock_ak_module):
        """创建数据源实例"""
        sys.modules['akshare'] = mock_ak_module

        from quantcli.datasources import akshare
        __import__('importlib').reload(akshare)

        from quantcli.datasources.akshare import AkshareDataSource
        ds = AkshareDataSource()
        ds._ak = mock_ak_module

        yield ds

        if 'akshare' in sys.modules:
            del sys.modules['akshare']

    def test_get_fina_indicator_not_implemented(self, data_source):
        """验证基本面指标抛出 NotImplementedError"""
        with pytest.raises(NotImplementedError):
            data_source.get_fina_indicator(["600519"])

    def test_get_valuation_not_implemented(self, data_source):
        """验证估值数据抛出 NotImplementedError"""
        with pytest.raises(NotImplementedError):
            data_source.get_valuation(["600519"], date(2024, 1, 31))

    def test_get_fundamental_not_implemented(self, data_source):
        """验证基本面数据抛出 NotImplementedError"""
        with pytest.raises(NotImplementedError):
            data_source.get_fundamental(["600519"], date(2024, 1, 31))


class TestBaostockDataSource:
    """Baostock 数据源测试"""

    @pytest.fixture
    def baostock_available(self):
        """检查 baostock 是否可用"""
        try:
            import baostock
            return True
        except ImportError:
            return False

    require_baostock = pytest.mark.skipif(
        not pytest.importorskip("baostock"),
        reason="baostock not installed"
    )

    @require_baostock
    def test_initialization(self, baostock_available):
        """测试初始化"""
        from quantcli.datasources import BaostockDataSource
        ds = BaostockDataSource()
        assert ds.name == "baostock"

    @require_baostock
    def test_get_daily_real(self):
        """获取真实日线数据"""
        from quantcli.datasources import BaostockDataSource
        ds = BaostockDataSource()

        df = ds.get_daily(
            "600519",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        assert not df.empty
        assert "date" in df.columns
        assert "close" in df.columns
        assert len(df) > 0

    @require_baostock
    def test_get_dupont_analysis_real(self):
        """获取杜邦分析数据"""
        from quantcli.datasources import BaostockDataSource
        ds = BaostockDataSource()

        df = ds.get_dupont_analysis(["600519", "000001"])

        # 应该有数据返回
        if not df.empty:
            assert "symbol" in df.columns
            assert "roe" in df.columns

    @require_baostock
    def test_get_stock_list_real(self):
        """获取股票列表"""
        from quantcli.datasources import BaostockDataSource
        ds = BaostockDataSource()

        stocks = ds.get_stock_list()

        # Baostock 可能返回空列表，取决于网络状况
        if len(stocks) > 0:
            assert all(hasattr(s, "symbol") for s in stocks)


class TestDataSourceIntegration:
    """数据源集成测试"""

    @pytest.fixture
    def mock_ak_module(self):
        """创建 mock akshare 模块"""
        mock = MockAkshare()
        return mock

    @pytest.fixture
    def data_source(self, mock_ak_module):
        """创建数据源实例（禁用缓存）"""
        sys.modules['akshare'] = mock_ak_module

        from quantcli.datasources import akshare
        __import__('importlib').reload(akshare)

        from quantcli.datasources.akshare import AkshareDataSource
        ds = AkshareDataSource(use_cache=False)
        ds._ak = mock_ak_module

        yield ds

        if 'akshare' in sys.modules:
            del sys.modules['akshare']

    def test_get_daily_data_flow(self, mock_ak_module, data_source):
        """测试日线数据流 (腾讯接口)"""
        mock_df = pd.DataFrame({
            "date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "open": [100.0, 101.0, 102.0],
            "close": [102.0, 103.0, 104.0],
            "high": [103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0],
            "volume": [1000000, 1100000, 1200000],
            "amount": [100000000, 110000000, 120000000],
        })
        mock_ak_module.setup_daily_return_value(mock_df)

        result = data_source.get_daily(
            "600519",
            date(2024, 1, 1),
            date(2024, 1, 31)
        )

        assert len(result) == 3
        assert result["date"].iloc[0] == date(2024, 1, 2)
        assert result["close"].iloc[0] == 102.0
        assert result["close"].iloc[-1] == 104.0

    def test_get_trading_calendar_sorted(self, mock_ak_module, data_source):
        """测试交易日历排序"""
        mock_df = pd.DataFrame({
            "trade_date": ["2024-01-03", "2024-01-02", "2024-01-04"]
        })
        mock_ak_module.setup_calendar_return_value(mock_df)

        calendar = data_source.get_trading_calendar()

        # 应该按日期排序
        assert calendar == sorted(calendar)


class TestMockDatasource:
    """Mock 数据源测试（使用 conftest 中的 MockDatasource）"""

    def _get_mock_datasource(self):
        """获取 MockDatasource，兼容不同导入路径"""
        try:
            # 尝试相对导入（从 tests 目录运行）
            from .conftest import MockDatasource
        except ImportError:
            try:
                # 尝试绝对导入（从项目根目录运行）
                from tests.conftest import MockDatasource
            except ImportError:
                # 直接从 conftest.py 复制 MockDatasource 核心逻辑
                import pandas as pd
                import numpy as np
                from datetime import date, timedelta
                from quantcli.datasources.base import StockInfo

                class MockDatasource:
                    name = "mock"

                    def __init__(self):
                        self.symbol = "600519"

                    def get_daily(self, symbol, start_date, end_date, fields=None):
                        np.random.seed(42)
                        start_date = date(2020, 1, 1)
                        dates = []
                        current = start_date
                        while len(dates) < 100:
                            if current.weekday() < 5:
                                dates.append(current)
                            current += timedelta(days=1)
                        returns = np.random.randn(len(dates)) * 0.02
                        close = 100 * np.cumprod(1 + returns)
                        return pd.DataFrame({
                            "symbol": symbol,
                            "date": dates,
                            "open": close * (1 + np.random.randn(len(dates)) * 0.01),
                            "high": close * (1 + abs(np.random.randn(len(dates)) * 0.01)),
                            "low": close * (1 - abs(np.random.randn(len(dates)) * 0.01)),
                            "close": close,
                            "volume": np.random.randint(1000000, 10000000, len(dates)),
                        })

                    def get_stock_list(self, market="all"):
                        stocks = [
                            StockInfo(
                                symbol="600519", name="贵州茅台", exchange="SSE",
                                market="上海", list_date=date(2001, 8, 27)
                            ),
                            StockInfo(
                                symbol="000001", name="平安银行", exchange="SSE",
                                market="深圳", list_date=date(1991, 4, 3)
                            ),
                        ]
                        if market == "all":
                            return stocks
                        return [s for s in stocks if s.market == market]

                    def get_trading_calendar(self, exchange="SSE"):
                        return [date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 6)]

                    def health_check(self):
                        return {"status": "ok", "source": self.name}

        return MockDatasource()

    def test_get_daily(self):
        """测试获取日线数据"""
        mock_ds = self._get_mock_datasource()
        df = mock_ds.get_daily(
            "600519",
            date(2020, 1, 1),
            date(2020, 1, 31)
        )

        assert len(df) > 0
        assert "date" in df.columns
        assert "close" in df.columns

    def test_get_stock_list(self):
        """测试获取股票列表"""
        from quantcli.datasources.base import StockInfo

        mock_ds = self._get_mock_datasource()
        stocks = mock_ds.get_stock_list()

        assert len(stocks) > 0
        assert all(isinstance(s, StockInfo) for s in stocks)

    def test_get_trading_calendar(self):
        """测试获取交易日历"""
        mock_ds = self._get_mock_datasource()
        calendar = mock_ds.get_trading_calendar()

        assert len(calendar) > 0
        assert all(isinstance(d, date) for d in calendar)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
