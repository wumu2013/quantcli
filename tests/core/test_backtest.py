"""core/backtest.py 单元测试"""

import pytest
import pandas as pd
import numpy as np
from datetime import date

# 延迟导入
pytest.importorskip("backtrader")

from quantcli.core import (
    BacktestEngine, BacktestConfig, BacktestResult, Trade
)
from quantcli.core.backtest import Strategy, quick_backtest


class TestBacktestConfig:
    """BacktestConfig 测试"""

    def test_default_config(self):
        config = BacktestConfig()
        assert config.initial_capital == 1000000.0
        assert config.fee == 0.0003

    def test_custom_config(self):
        config = BacktestConfig(
            initial_capital=500000,
            fee=0.001
        )
        assert config.initial_capital == 500000


class TestTrade:
    """Trade 测试"""

    def test_trade_creation(self):
        trade = Trade(
            date=date(2024, 1, 30),
            symbol="600519",
            side="buy",
            price=100.0,
            quantity=100,
            fee=30.0
        )
        assert trade.date == date(2024, 1, 30)
        assert trade.symbol == "600519"


class TestBacktestResult:
    """BacktestResult 测试"""

    def test_result_defaults(self):
        result = BacktestResult()
        assert result.total_return == 0.0
        assert result.sharpe == 0.0

    def test_result_to_dict(self):
        result = BacktestResult(
            total_return=0.1,
            annual_return=0.05
        )
        d = result.to_dict()
        assert d["total_return"] == 0.1


class TestBacktestEngine:
    """BacktestEngine 测试"""

    def test_engine_creation(self):
        config = BacktestConfig()
        engine = BacktestEngine(config)
        assert engine.config is config

    def test_add_data(self, sample_price_data):
        config = BacktestConfig()
        engine = BacktestEngine(config)
        engine.add_data("600519", sample_price_data)
        assert "600519" in engine._data_feeds


class TestBacktestEngineStrategy:
    """BacktestEngine 策略测试"""

    def test_engine_with_data(self, sample_price_data):
        """测试引擎添加数据"""
        config = BacktestConfig(initial_capital=100000)
        engine = BacktestEngine(config)
        engine.add_data("600519", sample_price_data)
        assert "600519" in engine._data_feeds


class TestYAMLBacktestConfig:
    """YAMLBacktest 配置测试"""

    def test_backtest_config_from_dict(self):
        """测试从字典创建回测配置"""
        from quantcli.factors.base import BacktestConfig, BacktestEntryConfig, BacktestExitRule

        data = {
            "entry": {"price": "open_next", "timing": "immediate"},
            "exit": [
                {"rule": "timed", "hold_days": 1, "time": "10:00"},
                {"rule": "close"}
            ],
            "capital": 500000,
            "fee": 0.001
        }
        config = BacktestConfig.from_dict(data)

        assert config.capital == 500000
        assert config.fee == 0.001
        assert config.entry.price == "open_next"
        assert len(config.exit) == 2
        assert config.exit[0].hold_days == 1
        assert config.exit[0].rule == "timed"

    def test_backtest_entry_config(self):
        """测试买入配置"""
        from quantcli.factors.base import BacktestEntryConfig

        # 简单格式
        config = BacktestEntryConfig.from_dict("open_next")
        assert config.price == "open_next"

        # 完整格式
        config = BacktestEntryConfig.from_dict({"price": "open_today", "timing": "close"})
        assert config.price == "open_today"
        assert config.timing == "close"

    def test_backtest_exit_rule(self):
        """测试卖出规则"""
        from quantcli.factors.base import BacktestExitRule

        # 简单格式
        rule = BacktestExitRule.from_dict("10:00")
        assert rule.rule == "time_of_day"
        assert rule.time == "10:00"

        # 完整格式
        rule = BacktestExitRule.from_dict({"rule": "timed", "hold_days": 3, "price": "close"})
        assert rule.rule == "timed"
        assert rule.hold_days == 3


class TestYAMLBacktestEngine:
    """YAMLBacktestEngine 集成测试"""

    def test_engine_creation(self, sample_price_data):
        """测试引擎创建"""
        from quantcli.core.backtest import YAMLBacktestEngine, BacktestConfig

        # 创建 Mock源
        class MockDataSource:
            def get_daily(self, symbol, start, end):
                return sample_price_data

            def get_trading_calendar(self):
                return [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                    date(2024, 1, 5),
                ]

            def get_stock_list(self, market="all"):
                return pd.DataFrame({"symbol": ["600519"], "name": ["贵州茅台"]})

        ds = MockDataSource()
        config = BacktestConfig(initial_capital=100000)
        engine = YAMLBacktestEngine(ds, config)

        assert engine.config.initial_capital == 100000
        assert engine.positions == {}

    def test_backtest_result_metrics(self):
        """测试回测结果指标计算"""
        from quantcli.core.backtest import BacktestResult

        # 模拟交易记录
        trades = pd.DataFrame({
            "date": [date(2024, 1, 2), date(2024, 1, 3)],
            "symbol": ["600519", "600519"],
            "side": ["buy", "sell"],
            "price": [100.0, 105.0],
            "quantity": [100, 100],
            "fee": [10.0, 10.5],
            "pnl": [0, 490.0]
        })

        # 模拟资金曲线
        equity = pd.DataFrame({
            "date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
            ],
            "equity": [100000, 100990, 101980]
        })

        result = BacktestResult(
            total_return=0.0198,
            annual_return=0.15,
            max_drawdown=0.02,
            sharpe=1.2,
            sortino=0.8,
            win_rate=1.0,
            profit_factor=10.0,
            total_trades=2,
            trades=trades,
            equity_curve=equity
        )

        assert result.total_return == pytest.approx(0.0198, rel=0.01)
        assert result.win_rate == 1.0
        assert result.total_trades == 2


class TestYAMLBacktestStrategy:
    """YAML 策略配置测试"""

    def test_strategy_config_with_backtest(self):
        """测试策略配置包含回测配置"""
        from quantcli.factors.base import StrategyConfig

        data = {
            "name": "测试策略",
            "version": "1.0.0",
            "screening": {
                "fundamental_conditions": ["roe > 0.1"],
                "daily_conditions": ["close > ma10"],
                "limit": 50
            },
            "backtest": {
                "entry": {"price": "open_next"},
                "exit": [{"rule": "timed", "hold_days": 1}],
                "capital": 200000,
                "fee": 0.0005
            }
        }

        config = StrategyConfig.from_dict(data)

        assert config.name == "测试策略"
        assert config.backtest.capital == 200000
        assert config.backtest.entry.price == "open_next"
        assert config.backtest.exit[0].hold_days == 1
