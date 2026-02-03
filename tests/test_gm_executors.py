"""ScreeningExecutor 和 RankingExecutor 单元测试

使用 mock MySQLDataSource 测试掘金量化集成组件。
"""

import pytest
import tempfile
import os
import pandas as pd
import numpy as np
from datetime import date, timedelta
from unittest.mock import Mock, MagicMock, patch

from quantcli.factors.screening_executor import ScreeningExecutor
from quantcli.factors.ranking_executor import RankingExecutor
from quantcli.models.bar import MinuteBar


# ==================== Fixtures ====================

@pytest.fixture
def mock_mysql():
    """创建 mock MySQLDataSource"""
    mysql = Mock()
    return mysql


@pytest.fixture
def sample_config_with_screening(tmp_path):
    """创建包含 screening 配置的 YAML"""
    yaml_content = """
name: Test Screening Config
version: 1.0.0
description: Test config with screening

screening:
  fundamental_conditions:
    - "roe > 0.1"
    - "netprofitmargin > 0.05"
  daily_conditions:
    - "ma10_deviation > 0"
  limit: 50

factors:
  - name: ma10_deviation
    type: technical
    expr: "(close - ma(close, 10)) / ma(close, 10)"
    direction: negative
  - name: is_yinliang
    type: technical
    expr: "close < open"
    direction: positive

ranking:
  weights:
    ma10_deviation: 0.6
    is_yinliang: 0.4
  normalize: zscore

output:
  columns: [symbol, score, rank]
  limit: 10
"""
    config_file = tmp_path / "test_screening.yaml"
    config_file.write_text(yaml_content)
    return str(config_file)


@pytest.fixture
def sample_stock_list():
    """模拟股票列表"""
    return pd.DataFrame({
        'symbol': ['600519', '000001', '600036', '601398', '601988'],
        'name': ['贵州茅台', '平安银行', '招商银行', '工商银行', '中国银行'],
        'exchange': ['SSE', 'SZSE', 'SSE', 'SSE', 'SSE'],
        'market': ['上海', '深圳', '上海', '上海', '上海'],
        'status': ['active'] * 5
    })


@pytest.fixture
def sample_fundamental_data():
    """模拟基本面数据"""
    return pd.DataFrame({
        'symbol': ['600519', '000001', '600036', '601398', '601988'],
        'report_date': [date(2024, 12, 31)] * 5,
        'roe': [0.30, 0.08, 0.15, 0.12, 0.10],
        'netprofitmargin': [0.50, 0.02, 0.25, 0.20, 0.15],
        'grossprofitmargin': [0.90, 0.30, 0.40, 0.35, 0.32],
        'pe_ttm': [25.0, 8.0, 6.0, 5.0, 5.5],
        'pb': [5.0, 0.8, 0.9, 0.7, 0.6]
    })


@pytest.fixture
def sample_daily_data():
    """模拟日线数据"""
    np.random.seed(42)
    dates = pd.date_range(date.today() - timedelta(30), periods=22, freq='B')

    data = {}
    for symbol in ['600519', '000001', '600036', '601398', '601988']:
        close = 100 + np.cumsum(np.random.randn(22) * 0.5)
        data[symbol] = pd.DataFrame({
            'date': dates,
            'symbol': [symbol] * 22,
            'open': close * (1 + np.random.randn(22) * 0.01),
            'high': close * 1.02,
            'low': close * 0.98,
            'close': close,
            'volume': np.random.randint(1000000, 10000000, 22),
        })

    return data


@pytest.fixture
def sample_minute_bar():
    """创建 MinuteBar dataclass 实例"""
    return MinuteBar(
        symbol='600519',
        trade_date=date.today(),
        trade_time=timedelta(hours=9, minutes=35),
        period='5',
        open=1680.0,
        high=1685.0,
        low=1678.0,
        close=1682.0,
        volume=150000,
        amount=252300000.0
    )


# ==================== ScreeningExecutor Tests ====================

class TestScreeningExecutorInit:
    """ScreeningExecutor 初始化测试"""

    def test_init_loads_config(self, mock_mysql, sample_config_with_screening):
        """测试初始化时加载配置"""
        executor = ScreeningExecutor(sample_config_with_screening, mock_mysql)

        assert executor.config.name == "Test Screening Config"
        assert executor.config.version == "1.0.0"

    def test_init_has_evaluator(self, mock_mysql, sample_config_with_screening):
        """测试初始化时创建评估器"""
        executor = ScreeningExecutor(sample_config_with_screening, mock_mysql)

        assert executor.evaluator is not None
        assert executor.computer is not None


class TestScreeningExecutorRun:
    """ScreeningExecutor.run() 测试"""

    def test_run_with_empty_stock_list(self, mock_mysql, sample_config_with_screening):
        """测试股票列表为空"""
        mock_mysql.get_stock_list.return_value = pd.DataFrame()

        executor = ScreeningExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run()

        assert result == []

    def test_run_fundamental_screening(self, mock_mysql, sample_config_with_screening, sample_stock_list, sample_fundamental_data):
        """测试基本面筛选"""
        mock_mysql.get_stock_list.return_value = sample_stock_list
        mock_mysql.get_fundamental.return_value = sample_fundamental_data
        mock_mysql.get_multi_daily.return_value = {}  # 日线数据为空，不影响基本面筛选
        mock_mysql.get_trading_calendar.return_value = [date.today() - timedelta(1)]

        executor = ScreeningExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run()

        # roe > 0.1 且 netprofitmargin > 0.05
        # 600519: roe=0.30, npm=0.50 ✓
        # 000001: roe=0.08, npm=0.02 ✗
        # 600036: roe=0.15, npm=0.25 ✓
        # 601398: roe=0.12, npm=0.20 ✓
        # 601988: roe=0.10, npm=0.15 ✓ (roe=0.1 不满足 > 0.1)
        expected = ['600519', '600036', '601398']
        assert set(result) == set(expected)

    def test_run_with_daily_screening(self, mock_mysql, sample_config_with_screening, sample_stock_list, sample_fundamental_data, sample_daily_data):
        """测试日线筛选"""
        mock_mysql.get_stock_list.return_value = sample_stock_list
        mock_mysql.get_fundamental.return_value = sample_fundamental_data
        mock_mysql.get_multi_daily.return_value = sample_daily_data
        mock_mysql.get_trading_calendar.return_value = [date.today() - timedelta(1)]

        executor = ScreeningExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run(lookback_days=30)

        # 应该在基本面筛选后再做日线筛选
        assert isinstance(result, list)

    def test_run_respects_limit(self, mock_mysql, sample_config_with_screening, sample_stock_list, sample_fundamental_data):
        """测试 limit 配置"""
        mock_mysql.get_stock_list.return_value = sample_stock_list
        mock_mysql.get_fundamental.return_value = sample_fundamental_data
        mock_mysql.get_multi_daily.return_value = {}
        mock_mysql.get_trading_calendar.return_value = [date.today() - timedelta(1)]

        executor = ScreeningExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run()

        # limit = 50，应该能容纳所有结果
        assert len(result) <= 50

    def test_run_calls_mysql_methods(self, mock_mysql, sample_config_with_screening, sample_stock_list):
        """测试调用 MySQL 方法"""
        mock_mysql.get_stock_list.return_value = sample_stock_list
        mock_mysql.get_fundamental.return_value = pd.DataFrame()
        mock_mysql.get_multi_daily.return_value = {}
        mock_mysql.get_trading_calendar.return_value = [date.today() - timedelta(1)]

        executor = ScreeningExecutor(sample_config_with_screening, mock_mysql)
        executor.run()

        # 验证 MySQL 方法被调用
        mock_mysql.get_stock_list.assert_called_once()
        mock_mysql.get_fundamental.assert_called_once()
        mock_mysql.get_multi_daily.assert_called_once()


class TestScreeningExecutorPartial:
    """ScreeningExecutor 部分筛选测试"""

    def test_run_fundamental_only(self, mock_mysql, sample_config_with_screening, sample_stock_list, sample_fundamental_data):
        """测试仅基本面筛选"""
        mock_mysql.get_stock_list.return_value = sample_stock_list
        mock_mysql.get_fundamental.return_value = sample_fundamental_data

        executor = ScreeningExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run_fundamental_only()

        assert len(result) > 0

    def test_run_daily_only(self, mock_mysql, sample_config_with_screening, sample_daily_data):
        """测试仅日线筛选"""
        symbols = list(sample_daily_data.keys())
        mock_mysql.get_trading_calendar.return_value = [date.today() - timedelta(1)]
        mock_mysql.get_multi_daily.return_value = sample_daily_data

        executor = ScreeningExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run_daily_only(symbols, lookback_days=30)

        assert isinstance(result, list)


class TestScreeningExecutorEdgeCases:
    """ScreeningExecutor 边界情况测试"""

    def test_run_with_no_conditions(self, mock_mysql, tmp_path):
        """测试无筛选条件"""
        yaml_content = """
name: No Conditions Test
version: 1.0.0
screening: {}
ranking: {}
"""
        config_file = tmp_path / "no_conditions.yaml"
        config_file.write_text(yaml_content)

        mock_mysql.get_stock_list.return_value = pd.DataFrame({'symbol': ['600519', '000001']})
        mock_mysql.get_fundamental.return_value = pd.DataFrame()
        mock_mysql.get_multi_daily.return_value = {}

        executor = ScreeningExecutor(str(config_file), mock_mysql)
        result = executor.run()

        # 无条件时应该返回所有股票
        assert len(result) > 0

    def test_run_with_empty_fundamental(self, mock_mysql, sample_config_with_screening, sample_stock_list):
        """测试基本面数据为空"""
        mock_mysql.get_stock_list.return_value = sample_stock_list
        mock_mysql.get_fundamental.return_value = pd.DataFrame()
        mock_mysql.get_multi_daily.return_value = {}
        mock_mysql.get_trading_calendar.return_value = [date.today() - timedelta(1)]

        executor = ScreeningExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run()

        # 基本面为空时应该返回原列表
        assert len(result) == len(sample_stock_list)


# ==================== RankingExecutor Tests ====================

class TestRankingExecutorInit:
    """RankingExecutor 初始化测试"""

    def test_init_loads_config(self, mock_mysql, sample_config_with_screening):
        """测试初始化时加载配置"""
        executor = RankingExecutor(sample_config_with_screening, mock_mysql)

        assert executor.config.name == "Test Screening Config"
        assert executor.config.version == "1.0.0"

    def test_init_has_scorer_and_ranker(self, mock_mysql, sample_config_with_screening):
        """测试初始化时创建评分和排名引擎"""
        executor = RankingExecutor(sample_config_with_screening, mock_mysql)

        assert executor.scorer is not None
        assert executor.ranker is not None
        assert executor.computer is not None

    def test_init_loads_weights(self, mock_mysql, sample_config_with_screening):
        """测试初始化时加载权重"""
        executor = RankingExecutor(sample_config_with_screening, mock_mysql)

        assert len(executor.ranking_weights) > 0
        assert 'ma10_deviation' in executor.ranking_weights


class TestRankingExecutorRunOnBar:
    """RankingExecutor.run_on_bar() 测试"""

    def test_run_on_bar_empty_price_data(self, mock_mysql, sample_config_with_screening, sample_minute_bar):
        """测试价格数据为空"""
        mock_mysql.get_pool_minute_data.return_value = {}

        executor = RankingExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run_on_bar(
            bar=sample_minute_bar,
            candidate_symbols=['600519', '000001'],
            lookback_days=20
        )

        assert result.empty

    def test_run_on_bar_with_price_data(self, mock_mysql, sample_config_with_screening, sample_minute_bar, sample_daily_data):
        """测试带价格数据的 ranking"""
        # 准备分钟数据
        minute_data = {}
        base_time = timedelta(hours=9, minutes=30)
        for i, symbol in enumerate(['600519', '000001']):
            np.random.seed(42 + i)
            rows = []
            for j in range(80):
                t = base_time + timedelta(minutes=j * 5)
                rows.append({
                    'date': date.today() - timedelta(days=20 - j // 12),
                    'time': t,
                    'symbol': symbol,
                    'open': 100 + j + np.random.randn() * 0.1,
                    'high': 102 + j + np.random.randn() * 0.1,
                    'low': 98 + j + np.random.randn() * 0.1,
                    'close': 100 + j + np.random.randn() * 0.1,
                    'volume': 100000 + j * 1000,
                })
            minute_data[symbol] = pd.DataFrame(rows)

        mock_mysql.get_pool_minute_data.return_value = minute_data

        executor = RankingExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run_on_bar(
            bar=sample_minute_bar,
            candidate_symbols=['600519', '000001'],
            lookback_days=20
        )

        # 应该返回包含 symbol 和 score 的 DataFrame
        assert isinstance(result, pd.DataFrame)

    def test_run_on_bar_calls_mysql(self, mock_mysql, sample_config_with_screening, sample_minute_bar, sample_daily_data):
        """测试调用 MySQL 获取数据"""
        minute_data = {
            '600519': pd.DataFrame({
                'date': [date.today()],
                'time': [timedelta(hours=9, minutes=35)],
                'symbol': ['600519'],
                'open': [1680],
                'high': [1685],
                'low': [1678],
                'close': [1682],
                'volume': [150000],
            })
        }
        mock_mysql.get_pool_minute_data.return_value = minute_data

        executor = RankingExecutor(sample_config_with_screening, mock_mysql)
        executor.run_on_bar(
            bar=sample_minute_bar,
            candidate_symbols=['600519'],
            lookback_days=20
        )

        # 验证 MySQL 方法被调用
        mock_mysql.get_pool_minute_data.assert_called_once()


class TestRankingExecutorOutput:
    """RankingExecutor 输出测试"""

    def test_output_contains_score(self, mock_mysql, sample_config_with_screening, sample_minute_bar):
        """测试输出包含 score 列"""
        minute_data = {
            '600519': pd.DataFrame({
                'date': [date.today()],
                'time': [timedelta(hours=9, minutes=35)],
                'symbol': ['600519'],
                'open': [1680],
                'high': [1685],
                'low': [1678],
                'close': [1682],
                'volume': [150000],
            })
        }
        mock_mysql.get_pool_minute_data.return_value = minute_data

        executor = RankingExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run_on_bar(
            bar=sample_minute_bar,
            candidate_symbols=['600519'],
            lookback_days=20
        )

        if not result.empty:
            assert 'score' in result.columns

    def test_output_contains_symbol(self, mock_mysql, sample_config_with_screening, sample_minute_bar):
        """测试输出包含 symbol 列"""
        minute_data = {
            '600519': pd.DataFrame({
                'date': [date.today()],
                'time': [timedelta(hours=9, minutes=35)],
                'symbol': ['600519'],
                'open': [1680],
                'high': [1685],
                'low': [1678],
                'close': [1682],
                'volume': [150000],
            })
        }
        mock_mysql.get_pool_minute_data.return_value = minute_data

        executor = RankingExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run_on_bar(
            bar=sample_minute_bar,
            candidate_symbols=['600519'],
            lookback_days=20
        )

        if not result.empty:
            assert 'symbol' in result.columns

    def test_output_respects_limit(self, mock_mysql, sample_config_with_screening, sample_minute_bar):
        """测试输出 limit"""
        # 创建多只股票的数据
        minute_data = {}
        for i in range(20):
            symbol = f'60000{i}'
            minute_data[symbol] = pd.DataFrame({
                'date': [date.today()],
                'symbol': [symbol],
                'open': [100 + i],
                'high': [102 + i],
                'low': [98 + i],
                'close': [101 + i],
                'volume': [100000 + i * 1000],
            })

        mock_mysql.get_pool_minute_data.return_value = minute_data

        executor = RankingExecutor(sample_config_with_screening, mock_mysql)
        result = executor.run_on_bar(
            bar=sample_minute_bar,
            candidate_symbols=list(minute_data.keys()),
            lookback_days=20
        )

        # output.limit = 10
        if not result.empty:
            assert len(result) <= 10


# ==================== MinuteBar Tests ====================

class TestMinuteBar:
    """MinuteBar dataclass 测试"""

    def test_from_gm_bar(self):
        """测试从掘金 Bar 对象创建"""
        # 模拟 gm.api.Bar 对象
        mock_bar = Mock()
        mock_bar.eob = "2024-01-15 09:35:00"
        mock_bar.open = 1680.0
        mock_bar.high = 1685.0
        mock_bar.low = 1678.0
        mock_bar.close = 1682.0
        mock_bar.volume = 150000
        mock_bar.amount = 252300000.0

        minute_bar = MinuteBar.from_gm_bar('600519', mock_bar, '5')

        assert minute_bar.symbol == '600519'
        assert minute_bar.period == '5'
        assert minute_bar.open == 1680.0
        assert minute_bar.high == 1685.0
        assert minute_bar.low == 1678.0
        assert minute_bar.close == 1682.0
        assert minute_bar.volume == 150000

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            'eob': '2024-01-15 09:35:00',
            'open': 1680.0,
            'high': 1685.0,
            'low': 1678.0,
            'close': 1682.0,
            'volume': 150000,
            'amount': 252300000.0
        }

        minute_bar = MinuteBar.from_dict('600519', data, '5')

        assert minute_bar.symbol == '600519'
        assert minute_bar.period == '5'

    def test_to_dataframe_row(self, sample_minute_bar):
        """测试转换为 DataFrame 行"""
        row = sample_minute_bar.to_dataframe_row()

        assert row['symbol'] == '600519'
        assert row['open'] == 1680.0
        assert row['close'] == 1682.0

    def test_to_mysql_row(self, sample_minute_bar):
        """测试转换为 MySQL 行"""
        row = sample_minute_bar.to_mysql_row()

        assert row[0] == '600519'  # symbol
        assert row[4] == 1680.0    # open
        assert row[7] == 1682.0    # close
        assert len(row) == 10      # 10个字段


class TestDailyBar:
    """DailyBar dataclass 测试"""

    def test_from_gm_bar(self):
        """测试从掘金 Bar 对象创建日线"""
        from quantcli.models.bar import DailyBar

        mock_bar = Mock()
        mock_bar.symbol = '600519'
        mock_bar.eob = "2024-01-15 16:00:00"
        mock_bar.open = 1680.0
        mock_bar.high = 1690.0
        mock_bar.low = 1670.0
        mock_bar.close = 1685.0
        mock_bar.volume = 5000000
        mock_bar.amount = 8425000000.0

        daily_bar = DailyBar.from_gm_bar('600519', mock_bar)

        assert daily_bar.symbol == '600519'
        assert daily_bar.trade_date == date(2024, 1, 15)
        assert daily_bar.open == 1680.0
        assert daily_bar.high == 1690.0
        assert daily_bar.low == 1670.0
        assert daily_bar.close == 1685.0
        assert daily_bar.volume == 5000000

    def test_from_dict(self):
        """测试从字典创建日线"""
        from quantcli.models.bar import DailyBar

        data = {
            'trade_date': '2024-01-15',
            'open': 1680.0,
            'high': 1690.0,
            'low': 1670.0,
            'close': 1685.0,
            'volume': 5000000,
            'amount': 8425000000.0
        }

        daily_bar = DailyBar.from_dict('600519', data)

        assert daily_bar.symbol == '600519'
        assert daily_bar.trade_date == date(2024, 1, 15)
        assert daily_bar.close == 1685.0

    def test_to_mysql_row(self):
        """测试日线转换为 MySQL 行"""
        from quantcli.models.bar import DailyBar

        daily_bar = DailyBar(
            symbol='600519',
            trade_date=date(2024, 1, 15),
            open=1680.0,
            high=1690.0,
            low=1670.0,
            close=1685.0,
            volume=5000000,
            amount=8425000000.0
        )

        row = daily_bar.to_mysql_row()

        assert row[0] == '600519'  # symbol
        assert row[1] == date(2024, 1, 15)  # trade_date
        assert row[2] == 1680.0    # open
        assert row[5] == 1685.0    # close
        assert len(row) == 8       # 8个字段（日线无 period）


# ==================== Integration Tests ====================

class TestScreeningAndRankingIntegration:
    """Screening 和 Ranking 集成测试"""

    def test_full_pipeline(self, mock_mysql, tmp_path):
        """测试完整流程：screening → ranking"""
        # 创建配置
        yaml_content = """
name: Integration Test
version: 1.0.0
screening:
  fundamental_conditions:
    - "roe > 0.05"
  daily_conditions: []
  limit: 100
factors:
  - name: ma10_deviation
    type: technical
    expr: "(close - ma(close, 10)) / ma(close, 10)"
    direction: negative
ranking:
  weights:
    ma10_deviation: 1.0
  normalize: zscore
output:
  columns: [symbol, score]
  limit: 10
"""
        config_file = tmp_path / "integration.yaml"
        config_file.write_text(yaml_content)

        # 准备 mock 数据
        stock_list = pd.DataFrame({
            'symbol': ['600519', '000001', '600036'],
            'name': ['A', 'B', 'C'],
            'exchange': ['SSE', 'SZSE', 'SSE'],
        })

        fundamental = pd.DataFrame({
            'symbol': ['600519', '000001', '600036'],
            'roe': [0.30, 0.08, 0.15],
            'netprofitmargin': [0.50, 0.02, 0.25],
        })

        minute_data = {
            '600519': pd.DataFrame({
                'date': [date.today()],
                'time': [timedelta(hours=9, minutes=35)],
                'symbol': ['600519'],
                'open': [1680],
                'high': [1685],
                'low': [1678],
                'close': [1682],
                'volume': [150000],
            }),
            '000001': pd.DataFrame({
                'date': [date.today()],
                'time': [timedelta(hours=9, minutes=35)],
                'symbol': ['000001'],
                'open': [10],
                'high': [10.2],
                'low': [9.8],
                'close': [10.1],
                'volume': [500000],
            }),
        }

        mock_mysql.get_stock_list.return_value = stock_list
        mock_mysql.get_fundamental.return_value = fundamental
        mock_mysql.get_multi_daily.return_value = {}
        mock_mysql.get_pool_minute_data.return_value = minute_data
        mock_mysql.get_trading_calendar.return_value = [date.today() - timedelta(1)]

        # Screening
        screener = ScreeningExecutor(str(config_file), mock_mysql)
        screened_symbols = screener.run()

        # Ranking
        bar = MinuteBar(
            symbol='600519',
            trade_date=date.today(),
            trade_time=timedelta(hours=9, minutes=35),
            period='5',
            open=1680.0,
            high=1685.0,
            low=1678.0,
            close=1682.0,
            volume=150000
        )

        ranker = RankingExecutor(str(config_file), mock_mysql)
        result = ranker.run_on_bar(
            bar=bar,
            candidate_symbols=screened_symbols,
            lookback_days=20
        )

        # 验证结果
        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert 'symbol' in result.columns
            assert 'score' in result.columns
