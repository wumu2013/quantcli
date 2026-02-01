"""因子计算器

职责:
- 为筛选条件计算因子值
- 为排名阶段计算所有因子值
- 支持日线和分钟因子混合计算
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Set

from ..utils import get_logger
from .base import FactorDefinition
from ..parser import Formula
from ..parser.constants import BUILTIN_FUNCTIONS

logger = get_logger(__name__)


class FactorComputer:
    """因子计算器"""

    def __init__(self, builtin_functions: Optional[Set[str]] = None):
        """初始化

        Args:
            builtin_functions: 内置函数集合，用于区分因子和函数
        """
        self.builtin_functions = builtin_functions or BUILTIN_FUNCTIONS

    def find_factor_by_name(
        self,
        factor_name: str,
        factors: Dict[str, FactorDefinition]
    ) -> Optional[FactorDefinition]:
        """根据因子名查找因子定义

        Args:
            factor_name: 因子名
            factors: 因子定义字典

        Returns:
            FactorDefinition 或 None
        """
        for ref, factor in factors.items():
            # 通过文件名匹配（如 "ma10_deviation" 在路径中）
            if factor_name in ref.lower():
                return factor
        return None

    def get_factor_names_from_conditions(
        self,
        conditions: List,
        data_columns: Optional[Set[str]] = None
    ) -> Set[str]:
        """从条件表达式中提取因子名

        Args:
            conditions: 条件列表
            data_columns: 数据中已有的列名

        Returns:
            需要计算的因子名集合
        """
        if data_columns is None:
            data_columns = {'close', 'open', 'high', 'low', 'volume'}

        factor_names = set()
        import re

        for condition in conditions:
            expr_str = condition.expression if hasattr(condition, 'expression') else condition
            matches = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', expr_str)

            for m in matches:
                if m not in self.builtin_functions and m not in data_columns:
                    factor_names.add(m)

        return factor_names

    def compute_factors_for_screening(
        self,
        factor_names: List[str],
        factors: Dict[str, FactorDefinition],
        price_data: Dict[str, pd.DataFrame],
        candidates: List[str]
    ) -> Dict[str, Dict[str, float]]:
        """为筛选条件计算因子值

        Args:
            factor_names: 需要计算的因子名列表
            factors: 因子定义字典
            price_data: 价格数据字典
            candidates: 候选股票列表

        Returns:
            {symbol: {factor_name: value}} 字典
        """
        results = {}

        for symbol in candidates:
            if symbol not in price_data:
                continue

            symbol_data = price_data[symbol]
            if symbol_data.empty:
                continue

            symbol_results = {}
            for factor_name in factor_names:
                factor = self.find_factor_by_name(factor_name, factors)
                if not factor:
                    continue

                try:
                    formula = Formula(factor.expr, name=factor_name)
                    result = formula.compute(symbol_data)
                    if not result.empty:
                        symbol_results[factor_name] = float(result.iloc[-1])
                except Exception as e:
                    logger.warning(f"Failed to compute factor {factor_name} for {symbol}: {e}")

            if symbol_results:
                results[symbol] = symbol_results

        return results

    def compute_all_factors(
        self,
        factors: Dict[str, FactorDefinition],
        price_data: Dict[str, pd.DataFrame],
        intraday_data: Optional[Dict[str, pd.DataFrame]] = None,
        candidates: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """计算所有因子值（日线和分钟混合）

        Args:
            factors: 因子定义字典
            price_data: 日线价格数据
            intraday_data: 分钟数据（可选）
            candidates: 候选股票列表

        Returns:
            包含因子值的 DataFrame
        """
        if candidates is None:
            candidates = list(price_data.keys())

        rows = []

        for symbol in candidates:
            row = {"symbol": symbol}

            # 日线因子
            if symbol in price_data:
                daily_df = price_data[symbol]
                for ref, factor in factors.items():
                    if factor.type == "intraday":
                        continue

                    try:
                        formula = Formula(factor.expr, name=factor.name)
                        result = formula.compute(daily_df)
                        if not result.empty:
                            row[factor.name] = float(result.iloc[-1])
                    except Exception as e:
                        logger.warning(f"Failed to compute daily factor {factor.name}: {e}")

            # 分钟因子
            if intraday_data and symbol in intraday_data:
                intraday_df = intraday_data[symbol]
                if not intraday_df.empty:
                    for ref, factor in factors.items():
                        if factor.type != "intraday":
                            continue

                        try:
                            formula = Formula(factor.expr, name=factor.name)
                            result = formula.compute(intraday_df)
                            if not result.empty:
                                row[factor.name] = float(result.iloc[-1])
                        except Exception as e:
                            logger.warning(f"Failed to compute intraday factor {factor.name}: {e}")

            rows.append(row)

        if rows:
            return pd.DataFrame(rows)
        return pd.DataFrame(columns=["symbol"])

    def merge_factor_results(
        self,
        factor_data: List[Dict],
        screening_factors: Optional[Dict[str, Dict[str, float]]] = None
    ) -> pd.DataFrame:
        """合并因子计算结果

        Args:
            factor_data: 排名阶段的因子计算结果
            screening_factors: 筛选阶段计算的因子值

        Returns:
            合并后的 DataFrame
        """
        if not factor_data:
            return pd.DataFrame()

        df = pd.DataFrame(factor_data)

        # 合并筛选阶段计算的因子值
        if screening_factors:
            for symbol, factor_values in screening_factors.items():
                mask = df["symbol"] == symbol
                if mask.any():
                    for name, value in factor_values.items():
                        if name not in df.columns:
                            df.loc[mask, name] = value

        return df

    def compute_inline_factors(
        self,
        inline_factors: List[FactorDefinition],
        price_data: Dict[str, pd.DataFrame],
        intraday_data: Optional[Dict[str, pd.DataFrame]] = None,
        candidates: Optional[List[str]] = None
    ) -> Dict[str, FactorDefinition]:
        """计算内联因子定义

        Args:
            inline_factors: 内联因子定义列表
            price_data: 日线价格数据
            intraday_data: 分钟数据（可选）
            candidates: 候选股票列表

        Returns:
            因子定义字典（key 为因子名）
        """
        if not inline_factors:
            return {}

        if candidates is None:
            candidates = list(price_data.keys())

        # 转换为字典格式，key 为因子名
        result = {}

        for symbol in candidates:
            if symbol not in price_data:
                continue

            daily_df = price_data[symbol]
            if daily_df.empty:
                continue

            for factor in inline_factors:
                # 避免重复计算
                if factor.name in result:
                    continue

                try:
                    # 检查因子类型
                    if factor.type == "intraday" and intraday_data and symbol in intraday_data:
                        df = intraday_data[symbol]
                    else:
                        df = daily_df

                    if df.empty:
                        continue

                    formula = Formula(factor.expr, name=factor.name)
                    result_df = formula.compute(df)
                    if not result_df.empty:
                        # 验证因子值有效（非全 NaN）
                        if not result_df.isna().all():
                            result[factor.name] = factor
                except Exception as e:
                    logger.warning(f"Failed to compute inline factor {factor.name}: {e}")

        return result
