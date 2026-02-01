"""core/factor.py 单元测试"""

import pytest
import pandas as pd
import numpy as np
from quantcli.core import FactorEngine, Factor, FactorRegistry


class TestFactor:
    """Factor 测试"""

    def test_factor_creation(self):
        factor = Factor(
            name="test_factor",
            formula="close / ma(close, 20)",
            description="Test factor",
            category="momentum"
        )
        assert factor.name == "test_factor"
        assert factor.formula == "close / ma(close, 20)"

    def test_factor_validation(self):
        with pytest.raises(ValueError):
            Factor(name="", formula="close")


class TestFactorRegistry:
    """FactorRegistry 测试"""

    def test_registry_creation(self):
        registry = FactorRegistry()
        assert len(registry.list_all()) == 0

    def test_registry_register(self):
        registry = FactorRegistry()
        factor = Factor(name="test", formula="close")
        registry.register(factor)
        assert "test" in registry.list_all()

    def test_registry_get(self):
        registry = FactorRegistry()
        factor = Factor(name="test", formula="close")
        registry.register(factor)
        retrieved = registry.get("test")
        assert retrieved is not None
        assert retrieved.name == "test"

    def test_registry_overwrite(self):
        registry = FactorRegistry()
        f1 = Factor(name="test", formula="close")
        f2 = Factor(name="test", formula="volume")
        registry.register(f1)
        registry.register(f2)
        assert registry.get("test").formula == "volume"


class TestFactorEngine:
    """FactorEngine 测试"""

    def test_engine_creation(self):
        engine = FactorEngine()
        assert engine.registry is not None

    def test_engine_register(self):
        engine = FactorEngine()
        engine.register(Factor(name="test", formula="close"))
        assert engine.registry.get("test") is not None

    def test_compute_single_factor(self, sample_factor_df):
        engine = FactorEngine()
        result = engine.compute("close", sample_factor_df)
        assert len(result) == len(sample_factor_df)

    def test_compute_batch(self, sample_factor_df):
        engine = FactorEngine()
        result = engine.compute_batch(["close", "volume"], sample_factor_df)
        assert "close" in result.columns
        assert "volume" in result.columns


class TestFactorEngineEvaluation:
    """FactorEngine 因子评估测试"""

    def test_evaluate_ic(self, sample_factor_data):
        engine = FactorEngine()
        result = engine.evaluate_ic("factor", sample_factor_data)
        assert "factor_name" in result
        assert "ic_stats" in result

    def test_evaluate_quantiles(self, sample_factor_data):
        engine = FactorEngine()
        result = engine.evaluate_quantiles("factor", sample_factor_data)
        assert "factor_name" in result
        assert "quantile_returns" in result

    def test_evaluate_full(self, sample_factor_data):
        engine = FactorEngine()
        result = engine.evaluate_full("factor", sample_factor_data)
        assert result.factor_name == "factor"
        assert hasattr(result, "ic_mean")


class TestFactorEngineCache:
    """FactorEngine 缓存测试"""

    def test_clear_cache(self, sample_factor_df):
        engine = FactorEngine()
        engine.compute("close", sample_factor_df)
        engine.clear_cache()
        assert engine.health_check()["cache_size"] == 0

    def test_health_check(self):
        engine = FactorEngine()
        health = engine.health_check()
        assert health["status"] == "ok"
        assert "registered_factors" in health
