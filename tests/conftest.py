"""共享 fixtures - 测试数据生成器"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Optional
from unittest.mock import MagicMock, patch


def _generate_price_df(symbol: str = "600519", n: int = 100, seed: int = 42) -> pd.DataFrame:
    """生成合成价格数据"""
    np.random.seed(seed)
    start_date = date(2023, 1, 1)

    # 生成交易日
    dates = []
    current = start_date
    while len(dates) < n:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    # 价格随机游走
    returns = np.random.randn(len(dates)) * 0.02
    close = 100 * np.cumprod(1 + returns)
    open_ = close * (1 + np.random.randn(len(dates)) * 0.01)
    high = np.maximum(open_, close) * (1 + abs(np.random.randn(len(dates)) * 0.01))
    low = np.minimum(open_, close) * (1 - abs(np.random.randn(len(dates)) * 0.01))
    volume = np.random.randint(1000000, 10000000, len(dates))

    return pd.DataFrame({
        "symbol": symbol,
        "date": dates,
        "open": np.round(open_, 2),
        "high": np.round(high, 2),
        "low": np.round(low, 2),
        "close": np.round(close, 2),
        "volume": volume,
    })


def _generate_index_df(symbol: str = "000300.SH", n: int = 100, seed: int = 42) -> pd.DataFrame:
    """生成合成指数数据"""
    np.random.seed(seed)
    start_date = date(2023, 1, 1)

    dates = []
    current = start_date
    while len(dates) < n:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    close = 4000 + np.cumsum(np.random.randn(len(dates)) * 10)

    return pd.DataFrame({
        "symbol": symbol,
        "date": dates,
        "close": np.round(close, 2),
    })


class MockDatasource:
    """统一的 Mock DataSource"""

    name = "mock"

    def __init__(self, symbol: str = "600519"):
        from dataclasses import dataclass
        from datetime import date

        @dataclass
        class MockStockInfo:
            symbol: str
            name: str
            exchange: str
            market: str
            list_date: date
            delist_date: date = None
            status: str = "active"

        self.symbol = symbol
        self._daily_data = _generate_price_df(symbol)
        self._index_data = _generate_index_df()
        self._stock_list = [
            MockStockInfo(
                symbol="600519", name="贵州茅台", exchange="SSE",
                market="上海", list_date=date(2001, 8, 27)
            ),
            MockStockInfo(
                symbol="000001", name="平安银行", exchange="SSE",
                market="深圳", list_date=date(1991, 4, 3)
            ),
        ]
        self._trading_calendar = [
            date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5),
            date(2023, 1, 6), date(2023, 1, 9), date(2023, 1, 10),
        ]

    def get_daily(self, symbol: str, start_date, end_date, fields=None) -> pd.DataFrame:
        df = _generate_price_df(symbol)
        df["date"] = pd.to_datetime(df["date"])
        mask = (df["date"] >= pd.to_datetime(start_date)) & (df["date"] <= pd.to_datetime(end_date))
        return df[mask].copy()

    def get_index_daily(self, symbol: str, start_date, end_date) -> pd.DataFrame:
        df = _generate_index_df(symbol)
        df["date"] = pd.to_datetime(df["date"])
        mask = (df["date"] >= pd.to_datetime(start_date)) & (df["date"] <= pd.to_datetime(end_date))
        return df[mask].copy()

    def get_stock_list(self, market: str = "all"):
        if market == "all":
            return self._stock_list
        return [s for s in self._stock_list if s.market == market]

    def get_trading_calendar(self, exchange: str = "SSE"):
        return self._trading_calendar

    def health_check(self):
        return {"status": "ok", "source": self.name}


@pytest.fixture
def mock_datasource():
    """统一的 Mock DataSource fixture"""
    return MockDatasource()


@pytest.fixture
def mock_datasource_cls():
    """返回 MockDatasource 类，可自定义 symbol"""
    def _create(symbol: str = "600519"):
        return MockDatasource(symbol)
    return _create


@pytest.fixture
def sample_price_data():
    """生成合成价格数据 (OHLCV)"""
    return _generate_price_df()


@pytest.fixture
def sample_multi_stock_data():
    """生成多股票价格数据"""
    np.random.seed(42)
    symbols = ["600519", "000001", "000002", "600000", "600036"]
    all_data = []

    for i, symbol in enumerate(symbols):
        df = _generate_price_df(symbol, seed=42 + i)
        all_data.append(df)

    return pd.concat(all_data, ignore_index=True)


@pytest.fixture
def sample_factor_data():
    """生成因子数据 (用于 IC 分析)"""
    np.random.seed(42)
    n = 252

    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    factor = np.random.randn(n)
    returns = factor * 0.1 + np.random.randn(n) * 0.02

    return pd.DataFrame({
        "date": dates,
        "factor": factor,
        "returns": returns,
    })


@pytest.fixture
def sample_factor_df():
    """生成因子 DataFrame (多列)"""
    np.random.seed(42)
    n = 252
    dates = pd.date_range("2023-01-01", periods=n, freq="B")

    return pd.DataFrame({
        "date": dates,
        "close": np.cumsum(np.random.randn(n)) + 100,
        "volume": np.random.randint(1000000, 10000000, n),
        "returns": np.random.randn(n) * 0.02,
    })


@pytest.fixture
def empty_df():
    """空 DataFrame"""
    return pd.DataFrame(columns=["date", "close", "volume"])


@pytest.fixture
def df_with_missing():
    """包含缺失值的 DataFrame"""
    return pd.DataFrame({
        "date": pd.date_range("2023-01-01", periods=10, freq="B"),
        "close": [100.0, 101.0, np.nan, 103.0, np.nan, 105.0, 106.0, np.nan, 108.0, 109.0],
        "volume": [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000],
    })


@pytest.fixture
def df_with_outliers():
    """包含异常值的 DataFrame"""
    return pd.DataFrame({
        "date": pd.date_range("2023-01-01", periods=10, freq="B"),
        "close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 500.0],
        "volume": [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000],
    })
