"""factors/loader.py 单元测试 - 使用新 API"""

import pytest
import tempfile
import os
import pandas as pd
import numpy as np

from quantcli.factors.loader import (
    load_strategy,
    load_factor,
    load_all_factors,
    FactorDefinition,
    StrategyConfig,
    ScreeningCondition,
    BonusCondition,
)
from quantcli.factors.compute import FactorComputer
from quantcli.factors.ranking import ScoringEngine


@pytest.fixture
def sample_price_data():
    """生成合成价格数据"""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=100, freq="B")

    close = 100 + np.cumsum(np.random.randn(100) * 0.5)
    open_ = close * (1 + np.random.randn(100) * 0.01)
    volume = np.random.randint(1000000, 10000000, 100)

    return pd.DataFrame({
        "date": dates,
        "symbol": ["600519"] * 100,
        "open": open_,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def sample_yaml_config(tmp_path):
    """创建示例 YAML 配置文件（新格式）"""
    yaml_content = """
name: Test Factor Config
version: 1.0.0
description: Test config for unit tests

# 因子定义
factors:
  - name: ma10_deviation
    type: technical
    expr: "(close - ma(close, 10)) / ma(close, 10)"
    description: 10日线偏离度
    direction: negative

  - name: is_yinliang
    type: technical
    expr: "close < open"
    description: 阴线标识
    direction: positive

  - name: volume_ratio
    type: technical
    expr: "volume / ma(volume, 5)"
    description: 量比
    direction: negative

# 排名配置
ranking:
  weights:
    ma10_deviation: 0.5
    is_yinliang: 0.3
    volume_ratio: 0.2
  normalize: zscore
  conditions:
    is_yinliang: true
  bonuses:
    - condition: "volume_ratio < 0.8"
      weight: 0.1
      description: 缩量加分

output:
  columns: [symbol, score, ma10_deviation]
  limit: 10
"""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(yaml_content)
    return str(config_file)


class TestLoadStrategy:
    """load_strategy 测试"""

    def test_load_basic_config(self, sample_yaml_config):
        """测试加载基本配置"""
        config = load_strategy(sample_yaml_config)

        assert config.name == "Test Factor Config"
        assert config.version == "1.0.0"

    def test_load_factor_details(self, sample_yaml_config):
        """测试因子详情"""
        config = load_strategy(sample_yaml_config)

        inline_factors = config.ranking.get("inline_factors", [])
        assert len(inline_factors) == 3

        factor = inline_factors[0]
        assert factor.name == "ma10_deviation"
        assert "ma(close, 10)" in factor.expr
        assert factor.direction == "negative"

    def test_load_ranking_config(self, sample_yaml_config):
        """测试排名配置"""
        config = load_strategy(sample_yaml_config)

        ranking = config.ranking
        assert ranking["normalize"] == "zscore"
        assert "ma10_deviation" in ranking["weights"]

    def test_load_conditions_and_bonuses(self, sample_yaml_config):
        """测试条件配置"""
        config = load_strategy(sample_yaml_config)

        conditions = config.ranking.get("conditions", {})
        assert "is_yinliang" in conditions
        assert conditions["is_yinliang"] is True

        bonuses = config.ranking.get("bonuses", [])
        assert len(bonuses) == 1
        assert bonuses[0].condition == "volume_ratio < 0.8"


class TestLoadFactor:
    """load_factor 测试"""

    def test_load_factor_from_yaml(self, sample_yaml_config):
        """测试加载单个因子文件"""
        # 使用策略文件中的因子
        config = load_strategy(sample_yaml_config)
        inline_factors = config.ranking.get("inline_factors", [])

        assert len(inline_factors) == 3
        for f in inline_factors:
            assert isinstance(f, FactorDefinition)


class TestComputeFactors:
    """FactorComputer 测试"""

    def test_compute_single_factor(self, sample_yaml_config, sample_price_data):
        """测试计算单个因子"""
        config = load_strategy(sample_yaml_config)
        weights = config.ranking.get("weights", {})
        factors = {k: None for k in weights.keys()}

        computer = FactorComputer()
        results = computer.compute_all_factors(
            {"ma10_deviation": config.ranking["inline_factors"][0]},
            {"600519": sample_price_data},
            {},
            ["600519"]
        )

        assert isinstance(results, pd.DataFrame)
        assert len(results) == 1
        assert "ma10_deviation" in results.columns

    def test_compute_multiple_factors(self, sample_yaml_config, sample_price_data):
        """测试计算多个因子"""
        config = load_strategy(sample_yaml_config)
        factors = {f.name: f for f in config.ranking.get("inline_factors", [])}

        computer = FactorComputer()
        results = computer.compute_all_factors(
            factors,
            {"600519": sample_price_data},
            {},
            ["600519"]
        )

        assert isinstance(results, pd.DataFrame)
        assert len(results) == 1
        for name in ["ma10_deviation", "is_yinliang", "volume_ratio"]:
            assert name in results.columns

    def test_compute_boolean_factor(self, sample_yaml_config, sample_price_data):
        """测试布尔类型因子"""
        config = load_strategy(sample_yaml_config)
        factors = {f.name: f for f in config.ranking.get("inline_factors", [])}

        computer = FactorComputer()
        results = computer.compute_all_factors(
            factors,
            {"600519": sample_price_data},
            {},
            ["600519"]
        )

        # is_yinliang 返回布尔值或 0/1 数值
        is_yinliang = results["is_yinliang"].iloc[0]
        assert is_yinliang in (0, 1, True, False, 0.0, 1.0)


class TestScoringEngine:
    """ScoringEngine 测试"""

    def test_score_with_bonus(self, sample_yaml_config, sample_price_data):
        """测试带加分项的评分"""
        config = load_strategy(sample_yaml_config)
        factors = {f.name: f for f in config.ranking.get("inline_factors", [])}
        weights = config.ranking.get("weights", {})
        bonuses = config.ranking.get("bonuses", [])

        computer = FactorComputer()
        factor_data = computer.compute_all_factors(
            factors,
            {"600519": sample_price_data},
            {},
            ["600519"]
        )

        scorer = ScoringEngine(normalize="zscore")
        result = scorer.compute(
            factors, weights, factor_data,
            conditions=config.ranking.get("conditions", {}),
            bonuses=bonuses
        )

        assert "score" in result.columns
        assert len(result) == len(factor_data)

    def test_score_required_condition(self, sample_yaml_config, sample_price_data):
        """测试必要条件筛选"""
        config = load_strategy(sample_yaml_config)
        factors = {f.name: f for f in config.ranking.get("inline_factors", [])}
        weights = config.ranking.get("weights", {})
        conditions = config.ranking.get("conditions", {})

        computer = FactorComputer()
        factor_data = computer.compute_all_factors(
            factors,
            {"600519": sample_price_data},
            {},
            ["600519"]
        )

        scorer = ScoringEngine(normalize="zscore")
        result = scorer.compute(
            factors, weights, factor_data,
            conditions=conditions
        )

        # 不满足 is_yinliang 的行 score 应为 NaN
        yinliang_false = result[result["is_yinliang"] == False]
        assert yinliang_false["score"].isna().all()


class TestFactorDefinition:
    """FactorDefinition 数据类测试"""

    def test_factor_definition_defaults(self):
        """测试默认值"""
        factor = FactorDefinition(
            name="test",
            type="technical",
            expr="close"
        )
        assert factor.description == ""
        assert factor.direction == "neutral"
        assert factor.params == {}

    def test_factor_definition_custom(self):
        """测试自定义值"""
        factor = FactorDefinition(
            name="momentum",
            type="technical",
            expr="close / delay(close, 20) - 1",
            description="动量因子",
            direction="positive",
            params={"window": 20}
        )
        assert factor.name == "momentum"
        assert factor.type == "technical"
        assert factor.description == "动量因子"
        assert factor.direction == "positive"


class TestBonusCondition:
    """BonusCondition 数据类测试"""

    def test_bonus_condition_defaults(self):
        """测试默认值"""
        bonus = BonusCondition(
            condition="volume_ratio < 0.8",
            weight=0.1
        )
        assert bonus.description == ""

    def test_bonus_condition_with_description(self):
        """测试带描述的加分项"""
        bonus = BonusCondition(
            condition="volume_ratio < 0.8",
            weight=0.1,
            description="缩量加分"
        )
        assert bonus.description == "缩量加分"


class TestFactorConfigMethods:
    """因子配置方式测试 - 内联定义 vs 外部引用"""

    def test_inline_factor_definition(self, tmp_path):
        """测试方式1: 内联因子定义 (dict)"""
        yaml_content = """
name: Inline Factor Test
version: 1.0.0
factors:
  - name: custom_momentum
    type: technical
    expr: "close / delay(close, 20) - 1"
    direction: positive
    description: "20日动量"
  - name: ma10_deviation
    type: technical
    expr: "(close - ma(close, 10)) / ma(close, 10)"
    direction: negative
ranking:
  weights:
    custom_momentum: 0.6
    ma10_deviation: 0.4
  normalize: zscore
"""
        config_file = tmp_path / "inline_test.yaml"
        config_file.write_text(yaml_content)

        config = load_strategy(str(config_file))

        # 验证内联因子被正确解析
        inline_factors = config.ranking.get("inline_factors", [])
        assert len(inline_factors) == 2

        factor_names = [f.name for f in inline_factors]
        assert "custom_momentum" in factor_names
        assert "ma10_deviation" in factor_names

        # 验证因子详情
        custom_factor = next(f for f in inline_factors if f.name == "custom_momentum")
        assert "close / delay(close, 20) - 1" in custom_factor.expr
        assert custom_factor.direction == "positive"
        assert custom_factor.description == "20日动量"

    def test_external_reference(self, tmp_path):
        """测试方式2: 外部引用 (string)"""
        # 创建外部因子文件
        factors_dir = tmp_path / "factors"
        factors_dir.mkdir()
        alpha_file = factors_dir / "alpha_001.yaml"
        alpha_file.write_text("""
name: ALPHA_001
type: technical
expr: "rank(ts_argmax(where(close == delay(close, 1), 0, close), 20)) - 0.5"
direction: positive
description: "经典反转因子"
""")

        # 创建引用外部因子的策略（factors 在顶层，使用 factors/ 前缀，包含 .yaml 后缀）
        yaml_content = f"""
name: External Reference Test
version: 1.0.0
factors:
  - factors/alpha_001.yaml
ranking:
  weights:
    factors/alpha_001.yaml: 1.0
  normalize: zscore
"""
        config_file = tmp_path / "external_test.yaml"
        config_file.write_text(yaml_content)

        config = load_strategy(str(config_file))

        # 验证外部引用被正确解析
        external_refs = config.ranking.get("external_refs", [])
        assert "factors/alpha_001.yaml" in external_refs

        # 验证外部因子被加载（使用 weights dict）
        weights = config.ranking.get("weights", {})
        all_factors = load_all_factors(weights, str(config_file))
        assert "factors/alpha_001.yaml" in all_factors
        assert all_factors["factors/alpha_001.yaml"].name == "ALPHA_001"

    def test_mixed_inline_and_external(self, tmp_path):
        """测试混用两种方式"""
        # 创建外部因子文件
        factors_dir = tmp_path / "factors"
        factors_dir.mkdir()
        alpha_file = factors_dir / "alpha_001.yaml"
        alpha_file.write_text("""
name: ALPHA_001
type: technical
expr: "rank(ts_argmax(where(close == delay(close, 1), 0, close), 20)) - 0.5"
direction: positive
""")

        # 混用策略（factors 在顶层，使用 factors/ 前缀，包含 .yaml 后缀）
        yaml_content = f"""
name: Mixed Test
version: 1.0.0
factors:
  - name: custom_factor
    expr: "close / delay(close, 10) - 1"
  - factors/alpha_001.yaml
  - factors/alpha_008.yaml
ranking:
  weights:
    custom_factor: 0.3
    factors/alpha_001.yaml: 0.4
    factors/alpha_008.yaml: 0.3
  normalize: zscore
"""
        config_file = tmp_path / "mixed_test.yaml"
        config_file.write_text(yaml_content)

        config = load_strategy(str(config_file))

        # 验证内联因子
        inline_factors = config.ranking.get("inline_factors", [])
        assert len(inline_factors) == 1
        assert inline_factors[0].name == "custom_factor"

        # 验证外部引用
        external_refs = config.ranking.get("external_refs", [])
        assert "factors/alpha_001.yaml" in external_refs
        assert "factors/alpha_008.yaml" in external_refs

        # 验证权重配置
        weights = config.ranking.get("weights", {})
        assert weights["custom_factor"] == 0.3
        assert weights["factors/alpha_001.yaml"] == 0.4
        assert weights["factors/alpha_008.yaml"] == 0.3

    def test_loader_auto_detect_config_type(self, tmp_path):
        """测试加载器自动识别配置类型"""
        yaml_content = """
name: Auto Detect Test
version: 1.0.0
factors:
  - name: inline_factor
    expr: "close"
  - external_factor_1
  - external_factor_2
ranking:
  weights:
    inline_factor: 0.5
    external_factor_1: 0.3
    external_factor_2: 0.2
"""
        config_file = tmp_path / "auto_test.yaml"
        config_file.write_text(yaml_content)

        config = load_strategy(str(config_file))

        # 内联因子列表应该有1个
        inline_factors = config.ranking.get("inline_factors", [])
        assert len(inline_factors) == 1
        assert inline_factors[0].name == "inline_factor"

        # 外部引用列表应该有2个
        external_refs = config.ranking.get("external_refs", [])
        assert len(external_refs) == 2
        assert "external_factor_1" in external_refs
        assert "external_factor_2" in external_refs
