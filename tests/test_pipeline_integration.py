"""管道集成测试 - 测试真实数据场景

覆盖之前发现的问题:
1. akshare 中文列名映射
2. 列名别名（netprofitmargin -> net_profit_margin）
3. baostock 阈值格式（小数）
4. 因子路径解析
5. max 函数支持
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestColumnNameAlias:
    """列名别名测试 - 用户友好名称映射到实际数据列名"""

    def test_evaluate_screening_with_alias(self):
        """测试筛选条件支持用户友好列名"""
        from quantcli.factors import FactorPipeline
        from quantcli.parser.constants import COLUMN_ALIASES

        # 创建模拟数据（模拟 baostock 返回的数据，使用实际列名）
        fund_data = pd.DataFrame({
            "symbol": ["600001", "600002", "600003", "600004", "600005"],
            "roe": [0.15, 0.08, 0.20, 0.05, 0.12],  # 小数格式 (15% = 0.15)
            "net_profit_margin": [0.10, 0.03, 0.15, 0.02, 0.08],
            "gross_profit_margin": [0.35, 0.20, 0.40, 0.15, 0.30],
        })

        # 创建临时策略文件（使用用户友好名称）
        import tempfile
        import yaml
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                "name": "测试别名",
                "screening": {
                    "conditions": ["roe > 0.1", "netprofitmargin > 0.05", "grossprofitmargin > 0.3"],
                    "limit": 100
                },
                "ranking": {"weights": {}, "normalize": "zscore"},
            }, f)
            strategy_path = f.name

        try:
            pipeline = FactorPipeline(strategy_path)
            candidates = pipeline.screening_only(["600001", "600002", "600003", "600004", "600005"], fund_data)

            # 筛选条件: roe > 0.1 AND netprofitmargin > 0.05 AND grossprofitmargin > 0.3
            # 600001: roe=0.15>0.1, net=0.10>0.05, gross=0.35>0.3 -> pass
            # 600002: roe=0.08<0.1 -> fail
            # 600003: roe=0.20>0.1, net=0.15>0.05, gross=0.40>0.3 -> pass
            # 600004: roe=0.05<0.1 -> fail
            # 600005: roe=0.12>0.1, net=0.08>0.05, gross=0.30=0.3 -> fail (严格大于)
            assert len(candidates) == 2
            assert "600001" in candidates
            assert "600003" in candidates
        finally:
            os.unlink(strategy_path)

    def test_column_aliases_mapping(self):
        """测试别名映射包含所有常见列名"""
        from quantcli.parser.constants import COLUMN_ALIASES

        # 验证关键别名存在
        assert "roe" in COLUMN_ALIASES
        assert "netprofitmargin" in COLUMN_ALIASES
        assert "grossprofitmargin" in COLUMN_ALIASES

        # 验证映射值存在
        assert COLUMN_ALIASES["roe"] == "roe"
        assert COLUMN_ALIASES["netprofitmargin"] == "net_profit_margin"
        assert COLUMN_ALIASES["grossprofitmargin"] == "gross_profit_margin"


class TestAkshareColumnMapping:
    """AKShare 列名映射测试"""

    def test_stock_list_columns_renamed(self):
        """测试股票列表列名重命名逻辑"""
        # 模拟 akshare 返回中文列名
        df = pd.DataFrame({
            "代码": ["600519", "000001"],
            "名称": ["贵州茅台", "平安银行"],
        })

        # 应用重命名逻辑
        df = df.rename(columns={"代码": "symbol", "名称": "name"})

        # 验证列名被正确重命名
        assert "symbol" in df.columns
        assert "name" in df.columns
        assert "代码" not in df.columns
        assert "名称" not in df.columns

    def test_stock_list_columns_english_default(self):
        """测试列名是英文格式（兼容不同版本 akshare）"""
        import pandas as pd

        # 模拟英文列名（某些 akshare 版本）
        df = pd.DataFrame({
            "code": ["600519", "000001"],
            "name": ["贵州茅台", "平安银行"],
        })

        # 应该也能正确处理
        df = df.rename(columns={"code": "symbol", "name": "name"})

        assert "symbol" in df.columns
        assert "name" in df.columns


class TestBaostockDataFormat:
    """Baostock 数据格式测试"""

    def test_roe_percentage_format(self):
        """测试 ROE 为小数格式 (15% = 0.15)"""
        import tempfile
        import yaml
        from quantcli.factors.pipeline import FactorPipeline

        # 模拟 baostock 返回的小数格式数据
        fund_data = pd.DataFrame({
            "symbol": ["600001", "600002"],
            "roe": [0.1289, 0.0920],  # 12.89%, 9.20%
        })

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                "name": "测试百分比",
                "screening": {
                    "conditions": ["roe > 0.1"],  # 10% = 0.1
                    "limit": 100
                },
                "ranking": {"weights": {}, "normalize": "zscore"},
            }, f)
            strategy_path = f.name

        try:
            pipeline = FactorPipeline(strategy_path)
            candidates = pipeline.screening_only(["600001", "600002"], fund_data)

            # 600001: roe=0.1289>0.1 -> pass
            # 600002: roe=0.0920<0.1 -> fail
            assert len(candidates) == 1
            assert "600001" in candidates
        finally:
            os.unlink(strategy_path)

    def test_roe_percentile_values(self):
        """测试不同 ROE 阈值的筛选结果"""
        import tempfile
        import yaml
        from quantcli.factors.pipeline import FactorPipeline

        # 模拟不同 ROE 值的股票
        fund_data = pd.DataFrame({
            "symbol": ["A", "B", "C", "D", "E"],
            "roe": [0.05, 0.10, 0.15, 0.20, 0.25],  # 5%, 10%, 15%, 20%, 25%
        })

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                "name": "测试阈值",
                "screening": {
                    "conditions": ["roe > 0.15"],  # 筛选 ROE > 15%
                    "limit": 100
                },
                "ranking": {"weights": {}, "normalize": "zscore"},
            }, f)
            strategy_path = f.name

        try:
            pipeline = FactorPipeline(strategy_path)
            candidates = pipeline.screening_only(["A", "B", "C", "D", "E"], fund_data)

            # 只有 ROE > 0.15 的股票通过筛选
            # A: 0.05 < 0.15 -> fail
            # B: 0.10 < 0.15 -> fail
            # C: 0.15 = 0.15 -> fail (严格大于)
            # D: 0.20 > 0.15 -> pass
            # E: 0.25 > 0.15 -> pass
            assert len(candidates) == 2
            assert "D" in candidates
            assert "E" in candidates
        finally:
            os.unlink(strategy_path)


class TestFactorPathResolution:
    """因子路径解析测试"""

    def test_resolve_factor_path_from_examples(self):
        """测试从 examples/strategies 解析 factors/ 路径"""
        from quantcli.factors.loader import resolve_factor_path

        # 策略在 examples/strategies，因子在 examples/factors
        base_path = "/path/to/examples/strategies/test.yaml"
        factor_ref = "factors/technicals/ma10_deviation.yaml"

        result = resolve_factor_path(base_path, factor_ref)

        # 应该尝试多个搜索目录
        assert "factors" in result or factor_ref in result

    def test_resolve_nested_factor_path(self):
        """测试嵌套因子路径解析"""
        from quantcli.factors.loader import resolve_factor_path

        base_path = "/path/to/project/examples/strategies/my_strategy.yaml"
        factor_ref = "factors/technicals/ma10.yaml"

        result = resolve_factor_path(base_path, factor_ref)

        # 验证返回的是路径字符串
        assert isinstance(result, str)
        assert result.endswith(".yaml")


class TestMaxFunction:
    """max 函数测试"""

    def test_max_function_in_formula(self):
        """测试因子表达式中的 max 函数"""
        from quantcli.parser import Formula
        import numpy as np

        # 创建测试数据
        df = pd.DataFrame({
            "close": [100, 102, 105, 103, 110, 108, 112],
        })

        # 测试 max 函数
        formula = Formula("max(close)", name="test_max")
        result = formula.compute(df)

        # max 应该返回最后一个值（最大值）
        assert not pd.isna(result.iloc[-1])
        assert result.iloc[-1] == 112.0

    def test_rolling_max_in_formula(self):
        """测试 rolling_max 函数"""
        from quantcli.parser import Formula

        df = pd.DataFrame({
            "close": [100, 102, 105, 103, 110, 108, 112],
        })

        formula = Formula("rolling_max(close, 3)", name="test_rolling_max")
        result = formula.compute(df)

        # rolling_max(3) 应该返回每3个窗口的最大值
        assert len(result) == len(df)
        assert result.iloc[-1] == 112  # 最后3个: 110, 108, 112 -> max=112


class TestFullPipelineIntegration:
    """完整管道集成测试"""

    def test_pipeline_with_mock_data(self):
        """使用 mock 数据测试完整管道"""
        import tempfile
        import yaml
        from quantcli.factors.pipeline import FactorPipeline
        from quantcli.utils import today
        from datetime import timedelta

        # 创建临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建因子文件
            ma10_content = """name: MA10偏离度
type: technical
expr: "(close - ma(close, 10)) / ma(close, 10)"
direction: negative
"""
            factors_dir = os.path.join(tmpdir, "factors")
            os.makedirs(factors_dir)
            with open(os.path.join(factors_dir, "ma10.yaml"), "w") as f:
                f.write(ma10_content)

            # 创建策略文件（使用相对路径引用因子）
            strategy_content = {
                "name": "集成测试策略",
                "screening": {
                    "conditions": [],
                    "limit": 100
                },
                "ranking": {
                    "weights": {"factors/ma10.yaml": 1.0},
                    "normalize": "zscore"
                },
                "output": {"limit": 10}
            }
            strategy_path = os.path.join(tmpdir, "strategy.yaml")
            with open(strategy_path, "w") as f:
                yaml.dump(strategy_content, f)

            # 创建测试价格数据
            np.random.seed(42)
            n = 60
            dates = [(today() - timedelta(days=60 - i)).strftime("%Y-%m-%d") for i in range(n)]
            close = 100 + np.cumsum(np.random.randn(n))

            price_data = {
                "600519": pd.DataFrame({
                    "symbol": ["600519"] * n,
                    "date": dates,
                    "close": close,
                    "open": close * (1 + np.random.randn(n) * 0.01),
                    "high": close * (1 + abs(np.random.randn(n) * 0.01)),
                    "low": close * (1 - abs(np.random.randn(n) * 0.01)),
                    "volume": np.random.randint(1000000, 10000000, n),
                }),
            }

            pipeline = FactorPipeline(strategy_path)
            results = pipeline.run(
                symbols=["600519"],
                date=today(),
                price_data=price_data,
                fundamental_data=pd.DataFrame(),
                limit=10
            )

            # 验证结果
            assert "symbol" in results.columns
            assert "score" in results.columns
            assert len(results) <= 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
