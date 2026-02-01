"""datasources/base.py 单元测试"""

import pytest
from datetime import date
from quantcli.datasources import (
    DataSource, StockInfo, DataRequest, create_datasource, AkshareDataSource
)


class TestStockInfo:
    """StockInfo 测试"""

    def test_stock_info_creation(self):
        stock = StockInfo(
            symbol="600519",
            name="贵州茅台",
            exchange="SSE",
            market="上海",
            list_date=date(2001, 8, 27)
        )
        assert stock.symbol == "600519"
        assert stock.name == "贵州茅台"


class TestDataSource:
    """DataSource 基类测试"""

    def test_data_source_creation(self):
        """DataSource 可以直接实例化"""
        ds = DataSource()
        assert ds.name == "base"
        assert ds.config.name == "base"

    def test_data_source_with_config(self):
        """带配置的 DataSource"""
        from quantcli.datasources.base import DataSourceConfig
        config = DataSourceConfig(name="test", use_cache=False)
        ds = DataSource(config)
        assert ds.config.name == "test"
        assert ds.config.use_cache is False


class TestDataRequest:
    """DataRequest 测试"""

    def test_data_request_creation(self):
        request = DataRequest(
            start_date=date(2023, 1, 1),
            end_date=date(2024, 1, 1),
            symbols=["600519"]
        )
        assert request.start_date == date(2023, 1, 1)
        assert request.symbols == ["600519"]


class TestCreateDatasource:
    """create_datasource 工厂函数测试"""

    def test_create_akshare(self):
        ds = create_datasource("akshare")
        assert isinstance(ds, AkshareDataSource)

    def test_create_unknown_source(self):
        with pytest.raises(ValueError) as exc_info:
            create_datasource("unknown_source")
        assert "Unknown data source" in str(exc_info.value)


class TestAkshareDataSource:
    """AkshareDataSource 测试"""

    def test_akshare_creation(self):
        ds = AkshareDataSource()
        assert ds is not None

    def test_akshare_health_check(self):
        ds = AkshareDataSource()
        result = ds.health_check()
        assert "status" in result
