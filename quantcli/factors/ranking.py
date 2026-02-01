"""因子权重排序引擎

支持:
- Z-Score 标准化
- Min-Max 标准化
- 权重融合计算
- 必要条件过滤
- 加分项计算
"""

import re

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any

from ..utils import get_logger
from .base import FactorDefinition, BonusCondition
from ..parser import Formula

logger = get_logger(__name__)

# 导出常量供其他模块使用
from ..parser.constants import BUILTIN_FUNCTIONS


class FactorRanker:
    """因子权重排序引擎"""

    def __init__(self, normalize: str = "zscore"):
        """初始化

        Args:
            normalize: 标准化方法 "zscore" | "minmax" | "none"
        """
        self.normalize = normalize

    def normalize_series(self, series: pd.Series) -> pd.Series:
        """标准化因子值

        Args:
            series: 原始因子值

        Returns:
            标准化后的因子值
        """
        if self.normalize == "none":
            return series

        # 处理 NaN 和常量
        series = series.copy()
        series = series.replace([np.inf, -np.inf], np.nan)

        if self.normalize == "zscore":
            # Z-Score 标准化
            mean = series.mean()
            std = series.std()
            if std == 0 or pd.isna(std):
                return series - mean
            return (series - mean) / std

        elif self.normalize == "minmax":
            # Min-Max 标准化
            min_val = series.min()
            max_val = series.max()
            if max_val == min_val or pd.isna(max_val):
                return series - min_val
            return (series - min_val) / (max_val - min_val)

        return series

    def compute_factor_value(
        self,
        factor: FactorDefinition,
        data: pd.DataFrame
    ) -> pd.Series:
        """计算因子值

        Args:
            factor: 因子定义
            data: 包含所有列的 DataFrame

        Returns:
            因子值 Series
        """
        try:
            formula = Formula(factor.expr, name=factor.name)
            result = formula.compute(data)
            return result
        except Exception as e:
            logger.error(f"Failed to compute factor {factor.name}: {e}")
            return pd.Series(np.nan, index=data.index)

    def compute_all_factors(
        self,
        factors: Dict[str, FactorDefinition],
        data: pd.DataFrame
    ) -> pd.DataFrame:
        """计算所有因子值

        Args:
            factors: 因子定义字典
            data: 包含价格和基本面数据的 DataFrame

        Returns:
            因子值 DataFrame，列名是因子引用路径
        """
        results = {}

        for factor_ref, factor in factors.items():
            # 计算因子值
            factor_values = self.compute_factor_value(factor, data)

            # 标准化
            normalized = self.normalize_series(factor_values)

            # 应用方向：负向因子取反
            if factor.direction == "negative":
                normalized = -normalized

            results[factor_ref] = normalized

        return pd.DataFrame(results)

    def fusion(
        self,
        factor_data: pd.DataFrame,
        weights: Dict[str, float]
    ) -> pd.Series:
        """权重融合计算得分

        Args:
            factor_data: 因子值 DataFrame
            weights: 权重字典

        Returns:
            最终得分 Series
        """
        if factor_data.empty:
            return pd.Series(np.nan, index=factor_data.index)

        # 确保权重和为 1（可选）
        total_weight = sum(abs(w) for w in weights.values())
        if total_weight > 0:
            normalized_weights = {k: w / total_weight for k, w in weights.items()}
        else:
            normalized_weights = weights

        # 计算加权得分
        scores = pd.Series(0.0, index=factor_data.index)

        for factor_ref, weight in normalized_weights.items():
            if factor_ref in factor_data.columns:
                factor_values = factor_data[factor_ref].fillna(0)
                scores += factor_values * weight

        return scores

    def rank(
        self,
        factors: Dict[str, FactorDefinition],
        weights: Dict[str, float],
        data: pd.DataFrame,
        ascending: bool = False
    ) -> pd.DataFrame:
        """计算因子得分并排名

        Args:
            factors: 因子定义字典
            weights: 权重字典
            data: 包含所有列的 DataFrame
            ascending: 是否升序排列

        Returns:
            包含因子值和得分的 DataFrame
        """
        # 计算所有因子值
        factor_data = self.compute_all_factors(factors, data)

        # 权重融合
        scores = self.fusion(factor_data, weights)

        # 合并结果
        result = pd.DataFrame(index=data.index)
        result["score"] = scores

        # 添加因子值
        for col in factor_data.columns:
            result[col] = factor_data[col]

        # 添加排名
        result["rank"] = result["score"].rank(ascending=ascending, pct=True)

        return result.sort_values("score", ascending=not ascending)


class ScoringEngine:
    """评分引擎：处理必要条件和加分项"""

    def __init__(self, normalize: str = "zscore"):
        """初始化

        Args:
            normalize: 标准化方法 "zscore" | "minmax" | "none"
        """
        self.normalize = normalize
        self.ranker = FactorRanker(normalize)

    def _evaluate_condition(
        self,
        condition: str,
        data: pd.DataFrame
    ) -> pd.Series:
        """评估单个条件表达式

        Args:
            condition: 条件表达式，如 "volume_ratio < 0.8"
            data: 包含所有列的 DataFrame

        Returns:
            布尔 Series，True 表示满足条件
        """
        try:
            # 替换 'and' 为 '&' 以支持复合条件
            # 简单的替换：将有空格的 'and' 替换为 '&'
            import re
            condition = re.sub(r'\band\b', '&', condition)

            # 修复 & 的优先级问题：a > x & b < y 会被解析为 a > (x & b) < y
            # 需要添加括号：a > x & a < y 改为 (a > x) & (a < y)
            # 检测模式：变量 比较符 数字 & 变量 比较符 数字
            condition = self._fix_and_condition(condition)

            formula = Formula(condition)
            result = formula.compute(data)
            # 确保结果是布尔类型
            if result.dtype != bool:
                result = result.astype(bool)
            return result
        except Exception as e:
            logger.error(f"Failed to evaluate condition '{condition}': {e}")
            return pd.Series(False, index=data.index)

    def _fix_and_condition(self, condition: str) -> str:
        """修复复合条件的 & 优先级问题

        将 "a > x & a < y" 改为 "(a > x) & (a < y)"
        """
        import re
        # 匹配模式: 变量 比较符 值 & 变量 比较符 值
        pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)\s*(<=|>=|==|!=|<|>)\s*([-+]?\d*\.?\d+)\s*&\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(<=|>=|==|!=|<|>)\s*([-+]?\d*\.?\d+)'

        def replacer(match):
            var1 = match.group(1)
            op1 = match.group(2)
            val1 = match.group(3)
            var2 = match.group(4)
            op2 = match.group(5)
            val2 = match.group(6)

            # 如果是同一个变量，添加括号
            if var1 == var2:
                return f'({var1} {op1} {val1}) & ({var2} {op2} {val2})'
            return match.group(0)

        return re.sub(pattern, replacer, condition)

    def apply_conditions(
        self,
        factor_data: pd.DataFrame,
        conditions: Dict[str, Any]
    ) -> pd.Series:
        """应用必要条件，不满足则 score=0

        Args:
            factor_data: 包含因子值的 DataFrame
            conditions: 条件字典，如 {"is_yinliang": true, "ma10_slope": {"min": 0}}

        Returns:
            布尔 Series，满足所有条件为 True
        """
        if not conditions or factor_data.empty:
            return pd.Series(True, index=factor_data.index)

        passed = pd.Series(True, index=factor_data.index)

        for col, expected in conditions.items():
            if col not in factor_data.columns:
                logger.warning(f"Condition column '{col}' not in data")
                passed = passed & False
                continue

            if expected is True:
                # 布尔条件：必须是 True
                mask = factor_data[col].fillna(0).astype(bool)
                passed = passed & mask
            elif expected is False:
                # 布尔条件：必须是 False
                mask = ~factor_data[col].fillna(0).astype(bool)
                passed = passed & mask
            elif isinstance(expected, dict):
                # 范围条件
                if "min" in expected:
                    passed = passed & (factor_data[col] >= expected["min"])
                if "max" in expected:
                    passed = passed & (factor_data[col] <= expected["max"])
            else:
                # 直接比较
                passed = passed & (factor_data[col] == expected)

        return passed

    def apply_bonuses(
        self,
        factor_data: pd.DataFrame,
        bonuses: List[BonusCondition]
    ) -> pd.Series:
        """应用加分项

        Args:
            factor_data: 包含因子值的 DataFrame
            bonuses: 加分条件列表

        Returns:
            额外分数 Series
        """
        if not bonuses or factor_data.empty:
            return pd.Series(0.0, index=factor_data.index)

        bonus_scores = pd.Series(0.0, index=factor_data.index)

        for bonus in bonuses:
            try:
                # 直接在因子值上评估条件（不使用 Formula 解析）
                # 条件格式: "column < value" 或 "column > value" 等
                mask = self._evaluate_simple_condition(bonus.condition, factor_data)
                bonus_scores = bonus_scores + mask.astype(float) * bonus.weight
            except Exception as e:
                logger.error(f"Failed to apply bonus '{bonus.condition}': {e}")

        return bonus_scores

    def _evaluate_simple_condition(
        self,
        condition: str,
        factor_data: pd.DataFrame
    ) -> pd.Series:
        """简化条件评估

        支持格式: "column < value", "column > value", "column <= value",
                 "column >= value", "column == value", "column != value"
                 "column1 < value1 & column2 > value2" (复合条件)

        Args:
            condition: 条件表达式
            factor_data: 包含因子值的 DataFrame

        Returns:
            布尔 Series
        """
        if factor_data.empty:
            return pd.Series(False, index=factor_data.index)

        # 预处理：将 "and" 替换为 "&", "or" 替换为 "|"
        condition = condition.replace(' and ', ' & ').replace(' or ', ' | ')

        # 解析复合条件（用 & 或 | 分隔）
        tokens = []
        current = ""
        paren_depth = 0

        for char in condition:
            if char == '(':
                paren_depth += 1
                current += char
            elif char == ')':
                paren_depth -= 1
                current += char
            elif char in '&|' and paren_depth == 0:
                if current.strip():
                    tokens.append(current.strip())
                tokens.append(char)
                current = ""
            else:
                current += char

        if current.strip():
            tokens.append(current.strip())

        # 递归评估
        def eval_tokens(tokens_list, op):
            """评估 token 列表，op 是连接符 (& 或 |)"""
            if not tokens_list:
                return pd.Series(True, index=factor_data.index)

            if len(tokens_list) == 1:
                return _eval_single(tokens_list[0])

            idx = None
            for i, t in enumerate(tokens_list):
                if t == op:
                    idx = i
                    break

            if idx is None:
                # 没有找到指定操作符，尝试另一个
                op = '&' if op == '|' else '|'
                for i, t in enumerate(tokens_list):
                    if t == op:
                        idx = i
                        break

            if idx is None:
                return _eval_single(tokens_list[0])

            left = eval_tokens(tokens_list[:idx], op)
            right = eval_tokens(tokens_list[idx + 1:], op)

            if op == '&':
                return left & right
            else:
                return left | right

        def _eval_single(expr: str) -> pd.Series:
            """评估单个简单条件"""
            expr = expr.strip()

            # 匹配: 列名 比较符 值
            pattern = r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*(<=|>=|==|!=|<|>)\s*([-+]?\d*\.?\d+)$'

            match = re.match(pattern, expr)
            if not match:
                # 可能是带括号的复合条件，尝试解析
                if '(' in expr and ')' in expr:
                    inner = expr.strip().strip('()')
                    return eval_tokens([inner], '&')
                logger.debug(f"Invalid condition format: {expr}")
                return pd.Series(True, index=factor_data.index)

            col = match.group(1)
            op = match.group(2)
            val = float(match.group(3))

            if col not in factor_data.columns:
                logger.debug(f"Column '{col}' not in data for condition: {expr}")
                return pd.Series(False, index=factor_data.index)

            col_values = factor_data[col]

            if op == '<':
                return col_values < val
            elif op == '<=':
                return col_values <= val
            elif op == '>':
                return col_values > val
            elif op == '>=':
                return col_values >= val
            elif op == '==':
                return col_values == val
            elif op == '!=':
                return col_values != val

            return pd.Series(False, index=factor_data.index)

        return eval_tokens(tokens_list=tokens, op='&')

    def compute(
        self,
        factors: Dict[str, FactorDefinition],
        weights: Dict[str, float],
        factor_data: pd.DataFrame,
        conditions: Dict[str, Any] = None,
        bonuses: List[BonusCondition] = None,
        ascending: bool = False
    ) -> pd.DataFrame:
        """综合计算：权重融合 + 条件过滤 + 加分

        Args:
            factors: 因子定义字典
            weights: 权重字典
            factor_data: 包含因子值的 DataFrame
            conditions: 必要条件（可选）
            bonuses: 加分项列表（可选）
            ascending: 是否升序排列

        Returns:
            包含因子值、得分、排名的 DataFrame
        """
        if factor_data.empty:
            return pd.DataFrame()

        # 提取 symbol 列用于结果
        has_symbol = "symbol" in factor_data.columns
        symbols = factor_data["symbol"].values if has_symbol else None

        # 权重融合得到基础分数（只对数值列）
        numeric_cols = [c for c in factor_data.columns if c != "symbol"]
        if numeric_cols:
            factor_values = factor_data[numeric_cols]
            base_scores = self.ranker.fusion(factor_values, weights)
        else:
            base_scores = pd.Series(0.0, index=factor_data.index)

        # 应用加分项
        bonus_scores = self.apply_bonuses(factor_data, bonuses)
        final_scores = base_scores + bonus_scores

        # 应用必要条件
        passed = self.apply_conditions(factor_data, conditions)

        # 构建结果
        n = len(factor_data)
        result = pd.DataFrame(index=range(n))
        result["base_score"] = base_scores.values
        result["bonus_score"] = bonus_scores.values
        result["score"] = final_scores.values
        result["passed"] = passed.values

        # 不通过的分数设为 NaN
        passed_mask = passed.values
        result.loc[~passed_mask, "score"] = np.nan

        # 添加因子值
        for col in numeric_cols:
            result[col] = factor_data[col].values

        # 添加 symbol
        if has_symbol:
            result["symbol"] = symbols

        # 添加排名
        valid_mask = result["score"].notna()
        if valid_mask.any():
            valid_scores = result.loc[valid_mask, "score"]
            ranks = valid_scores.rank(ascending=ascending, pct=True)
            result.loc[valid_mask, "rank"] = ranks.values

        return result.sort_values("score", ascending=not ascending, na_position="last")
