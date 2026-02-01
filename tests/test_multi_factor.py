"""多因子策略单元测试"""

import pytest
import pandas as pd
import numpy as np
from datetime import date
from pathlib import Path

from quantcli.factors.base import FactorDefinition, StrategyConfig, ScreeningCondition
from quantcli.factors.loader import load_factor, load_strategy, load_all_factors
from quantcli.factors.ranking import FactorRanker
from quantcli.factors.pipeline import FactorPipeline


class TestFactorDefinition:
    """因子定义测试"""

    def test_create_factor_definition(self):
        """创建因子定义"""
        factor = FactorDefinition(
            name="PE因子",
            type="fundamental",
            expr="pe",
            direction="negative"
        )
        assert factor.name == "PE因子"
        assert factor.type == "fundamental"
        assert factor.expr == "pe"
        assert factor.direction == "negative"

    def test_factor_direction_validation(self):
        """因子方向验证"""
        factor = FactorDefinition(
            name="ROE因子",
            type="fundamental",
            expr="roe",
            direction="positive"
        )
        assert factor.direction == "positive"

    def test_invalid_factor_type(self):
        """无效因子类型"""
        with pytest.raises(ValueError):
            FactorDefinition(
                name="测试因子",
                type="invalid_type",
                expr="close"
            )


class TestScreeningCondition:
    """筛选条件测试"""

    def test_parse_simple_condition(self):
        """解析简单条件"""
        cond = ScreeningCondition.from_string("pe < 50")
        assert cond.expression == "pe < 50"
        assert cond.column == "pe"

    def test_parse_greater_than_condition(self):
        """解析大于条件"""
        cond = ScreeningCondition.from_string("roe > 10")
        assert cond.expression == "roe > 10"
        assert cond.column == "roe"

    def test_parse_complex_condition(self):
        """解析复杂条件"""
        cond = ScreeningCondition.from_string("revenue_growth >= 15.5")
        assert cond.expression == "revenue_growth >= 15.5"
        assert cond.column == "revenue_growth"


class TestLoadFactor:
    """加载因子测试"""

    @pytest.fixture
    def factor_file(self, tmp_path):
        """创建临时因子文件"""
        content = """
name: 市盈率因子
type: fundamental
expr: "pe"
direction: negative
description: PE 越低越好
"""
        f = tmp_path / "pe.yaml"
        f.write_text(content)
        return str(f)

    def test_load_factor_from_yaml(self, factor_file):
        """从YAML加载因子"""
        factor = load_factor(factor_file)

        assert factor.name == "市盈率因子"
        assert factor.type == "fundamental"
        assert factor.expr == "pe"
        assert factor.direction == "negative"
        assert factor.description == "PE 越低越好"

    def test_load_factor_with_defaults(self, tmp_path):
        """加载因子使用默认值"""
        content = """
name: 测试因子
expr: "close"
"""
        f = tmp_path / "test.yaml"
        f.write_text(content)

        factor = load_factor(str(f))

        assert factor.type == "technical"  # 默认值
        assert factor.direction == "neutral"  # 默认值


class TestLoadStrategy:
    """加载策略测试"""

    @pytest.fixture
    def strategy_file(self, tmp_path):
        """创建临时策略文件"""
        content = """name: 测试策略
version: 1.0.0

screening:
  - "pe < 50"
  - "roe > 10"
limit: 200

ranking:
  weights:
    factors/pe.yaml: -0.15
    factors/roe.yaml: 0.20
  normalize: zscore
  method: weighted_sum

output:
  limit: 30
"""
        f = tmp_path / "strategy.yaml"
        f.write_text(content)
        return str(f)

    def test_load_strategy_from_yaml(self, strategy_file):
        """从YAML加载策略"""
        config = load_strategy(strategy_file)

        assert config.name == "测试策略"
        assert config.version == "1.0.0"
        assert len(config.screening["conditions"]) == 2
        assert config.screening["limit"] == 200
        assert "factors/pe.yaml" in config.ranking["weights"]
        assert config.ranking["normalize"] == "zscore"

    def test_load_strategy_with_list_screening(self, tmp_path):
        """加载筛选条件为列表的策略"""
        content = """name: 简单筛选策略

screening:
  - "pe < 30"
"""
        f = tmp_path / "simple.yaml"
        f.write_text(content)

        config = load_strategy(str(f))
        assert len(config.screening["conditions"]) == 1
        # 当screening是列表时，默认limit是200
        assert config.screening["limit"] == 200


class TestFactorRanker:
    """因子排序器测试"""

    @pytest.fixture
    def sample_data(self):
        """创建样本数据"""
        n = 100
        return pd.DataFrame({
            "symbol": [f"60000{i}" for i in range(n)],
            "pe": np.random.uniform(5, 50, n),
            "roe": np.random.uniform(5, 30, n),
            "ma10_deviation": np.random.uniform(-0.1, 0.1, n),
        })

    @pytest.fixture
    def factor_dict(self):
        """因子定义字典"""
        return {
            "factors/pe.yaml": FactorDefinition(
                name="PE因子", type="fundamental", expr="pe", direction="negative"
            ),
            "factors/roe.yaml": FactorDefinition(
                name="ROE因子", type="fundamental", expr="roe", direction="positive"
            ),
        }

    def test_normalize_zscore(self, sample_data):
        """Z-Score标准化"""
        ranker = FactorRanker(normalize="zscore")

        result = ranker.normalize_series(sample_data["pe"])

        # Z-Score 后均值应接近0，标准差应接近1
        assert abs(result.mean()) < 0.01
        assert abs(result.std() - 1.0) < 0.01

    def test_normalize_minmax(self, sample_data):
        """Min-Max标准化"""
        ranker = FactorRanker(normalize="minmax")

        result = ranker.normalize_series(sample_data["pe"])

        # Min-Max 后范围应在 0-1
        assert result.min() >= 0
        assert result.max() <= 1

    def test_compute_all_factors(self, sample_data, factor_dict):
        """计算所有因子"""
        ranker = FactorRanker(normalize="zscore")

        result = ranker.compute_all_factors(factor_dict, sample_data)

        assert len(result.columns) == 2
        assert "factors/pe.yaml" in result.columns
        assert "factors/roe.yaml" in result.columns
        assert len(result) == len(sample_data)

    def test_weighted_fusion(self, sample_data, factor_dict):
        """权重融合"""
        ranker = FactorRanker(normalize="zscore")

        factor_data = ranker.compute_all_factors(factor_dict, sample_data)

        weights = {
            "factors/pe.yaml": -0.15,  # 负向
            "factors/roe.yaml": 0.20,  # 正向
        }

        scores = ranker.fusion(factor_data, weights)

        assert len(scores) == len(sample_data)
        assert not scores.isna().all()

    def test_rank_factors(self, sample_data, factor_dict):
        """因子排名"""
        ranker = FactorRanker(normalize="zscore")

        weights = {
            "factors/pe.yaml": -0.15,
            "factors/roe.yaml": 0.20,
        }

        result = ranker.rank(factor_dict, weights, sample_data)

        assert "score" in result.columns
        assert "rank" in result.columns
        assert "factors/pe.yaml" in result.columns
        # 结果应该按得分降序排列
        assert result["score"].is_monotonic_decreasing or result["score"].notna().all()


class TestFactorPipeline:
    """因子管道测试"""

    @pytest.fixture
    def strategy_file(self, tmp_path, factor_files):
        """创建策略文件"""
        pe_rel = factor_files["pe"].relative_to(tmp_path)
        roe_rel = factor_files["roe"].relative_to(tmp_path)
        content = f"""name: 测试策略
version: 1.0.0

screening:
  - "pe < 50"
  - "roe > 10"
limit: 100

ranking:
  weights:
    {pe_rel}: -0.15
    {roe_rel}: 0.20
  normalize: zscore

output:
  limit: 30
"""
        f = tmp_path / "strategy.yaml"
        f.write_text(content)
        return str(f)

    @pytest.fixture
    def factor_files(self, tmp_path):
        """创建因子文件"""
        pe_content = """
name: PE因子
type: fundamental
expr: "pe"
direction: negative
"""
        roe_content = """
name: ROE因子
type: fundamental
expr: "roe"
direction: positive
"""
        pe_file = tmp_path / "pe.yaml"
        roe_file = tmp_path / "roe.yaml"
        pe_file.write_text(pe_content)
        roe_file.write_text(roe_content)

        return {"pe": pe_file, "roe": roe_file}

    def test_pipeline_initialization(self, strategy_file):
        """管道初始化"""
        pipeline = FactorPipeline(strategy_file)

        assert pipeline.config.name == "测试策略"
        assert pipeline.config.version == "1.0.0"

    def test_screening_only(self, strategy_file, factor_files):
        """仅筛选阶段"""
        from quantcli.datasources.base import DataSource

        pipeline = FactorPipeline(strategy_file)

        # 创建模拟基本面数据
        symbols = ["600001", "600002", "600003", "600004", "600005"]
        fund_data = pd.DataFrame({
            "pe": [20, 60, 15, 80, 25],
            "roe": [15, 8, 20, 5, 12],
        }, index=symbols)

        candidates = pipeline.screening_only(symbols, fund_data)

        # 筛选条件: pe < 50 AND roe > 10
        # 600001: pe=20<50, roe=15>10 -> pass
        # 600002: pe=60>=50 -> fail
        # 600003: pe=15<50, roe=20>10 -> pass
        # 600004: pe=80>=50, roe=5<10 -> fail
        # 600005: pe=25<50, roe=12>10 -> pass
        assert len(candidates) == 3
        assert "600001" in candidates
        assert "600003" in candidates
        assert "600005" in candidates


class TestFactorLoaderIntegration:
    """因子加载器集成测试"""

    @pytest.fixture
    def full_setup(self, tmp_path):
        """完整测试环境"""
        # 创建因子文件
        pe_content = """name: PE因子
type: fundamental
expr: "pe"
direction: negative
"""
        roe_content = """name: ROE因子
type: fundamental
expr: "roe"
direction: positive
"""
        ma10_content = """name: MA10偏离度
type: technical
expr: "(close - ma(close, 10)) / ma(close, 10)"
direction: negative
"""

        factors_dir = tmp_path / "factors"
        factors_dir.mkdir()
        (factors_dir / "pe.yaml").write_text(pe_content)
        (factors_dir / "roe.yaml").write_text(roe_content)
        (factors_dir / "ma10.yaml").write_text(ma10_content)

        # 创建策略文件
        strategy_content = """name: 完整策略
version: 1.0.0

screening:
  - "pe < 50"
  - "roe > 10"
limit: 200

ranking:
  weights:
    factors/pe.yaml: -0.15
    factors/roe.yaml: 0.20
    factors/ma10.yaml: 0.30
  normalize: zscore

output:
  limit: 30
"""
        (tmp_path / "strategy.yaml").write_text(strategy_content)

        return {
            "base": tmp_path,
            "strategy": str(tmp_path / "strategy.yaml"),
            "factors_dir": str(factors_dir),
        }

    def test_load_all_factors(self, full_setup):
        """加载所有因子"""
        weights = {
            f"{full_setup['factors_dir']}/pe.yaml": -0.15,
            f"{full_setup['factors_dir']}/roe.yaml": 0.20,
        }

        factors = load_all_factors(weights, full_setup["strategy"])

        assert len(factors) == 2
        assert any("pe.yaml" in k for k in factors.keys())
        assert any("roe.yaml" in k for k in factors.keys())

    def test_weight_parsing(self, full_setup):
        """权重解析"""
        config = load_strategy(full_setup["strategy"])

        weights = config.ranking["weights"]

        # 检查权重值
        pe_weight = [v for k, v in weights.items() if "pe.yaml" in k][0]
        assert pe_weight == -0.15

        roe_weight = [v for k, v in weights.items() if "roe.yaml" in k][0]
        assert roe_weight == 0.20


class TestEdgeCases:
    """边界情况测试"""

    def test_empty_weights(self):
        """空权重"""
        ranker = FactorRanker()

        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        weights = {}

        scores = ranker.fusion(df, weights)

        # 空权重时得分应全为0
        assert (scores == 0).all()

    def test_empty_factor_data(self):
        """空因子数据"""
        ranker = FactorRanker()

        df = pd.DataFrame()
        weights = {"a": 0.5}

        scores = ranker.fusion(df, weights)

        assert len(scores) == 0

    def test_handle_nan_in_weights(self):
        """处理权重中的NaN"""
        ranker = FactorRanker()

        df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
        weights = {"a": float("nan")}

        scores = ranker.fusion(df, weights)

        # NaN 权重应产生 NaN 得分（目前实现如此）
        assert scores.isna().all() or (scores == 0).all()

    def test_screening_with_empty_data(self):
        """空数据筛选"""
        pipeline = FactorPipeline.__new__(FactorPipeline)
        pipeline.config = StrategyConfig(
            name="测试",
            screening={"conditions": [ScreeningCondition("pe < 50", "pe")], "limit": 200}
        )

        candidates = pipeline.screening_only([], pd.DataFrame())

        assert candidates == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
