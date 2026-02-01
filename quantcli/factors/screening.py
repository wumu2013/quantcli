"""筛选条件评估器

职责:
- 应用列名别名映射
- 评估筛选条件表达式
"""

import pandas as pd
from typing import Dict, List, Optional, Union

from ..utils import get_logger
from .base import ScreeningCondition
from ..parser import Formula
from ..parser.constants import COLUMN_ALIASES

logger = get_logger(__name__)


class ScreeningEvaluator:
    """筛选条件评估器"""

    def __init__(self, aliases: Optional[Dict[str, str]] = None):
        """初始化

        Args:
            aliases: 列名别名映射，如果为 None 使用默认别名
        """
        self.aliases = aliases or COLUMN_ALIASES

    def apply_aliases(self, df: pd.DataFrame) -> pd.DataFrame:
        """应用列名别名映射

        确保条件表达式中使用的别名列（如 netprofitmargin）能被 Formula 解析器找到。
        策略：
        1. 如果 DataFrame 有实际列名（如 net_profit_margin），添加别名列（如 netprofitmargin）
        2. 如果 DataFrame 有别名列但没有实际列名，添加实际列名

        Args:
            df: 原始 DataFrame

        Returns:
            包含别名列的 DataFrame
        """
        if df.empty:
            return df

        df = df.copy()

        for alias, actual in self.aliases.items():
            # 如果有实际列名但没有别名列，添加别名列
            if actual in df.columns and alias not in df.columns:
                df[alias] = df[actual]
                logger.debug(f"Added alias column: {alias} -> {actual}")
            # 如果有别名列但没有实际列名，添加实际列名
            elif alias in df.columns and actual not in df.columns:
                df[actual] = df[alias]
                logger.debug(f"Added actual column: {actual} -> {alias}")

        return df

    def evaluate(
        self,
        conditions: List[Union[ScreeningCondition, str]],
        data: pd.DataFrame
    ) -> pd.Series:
        """评估筛选条件

        Args:
            conditions: 筛选条件列表（ScreeningCondition 对象或字符串）
            data: 包含数据的 DataFrame

        Returns:
            满足条件的布尔 Series
        """
        if not conditions:
            return pd.Series(True, index=data.index)

        passed = pd.Series(True, index=data.index)

        for condition in conditions:
            # 支持 ScreeningCondition 对象或字符串
            if hasattr(condition, 'expression'):
                expr_str = condition.expression
            else:
                expr_str = condition

            try:
                # 使用 Formula 解析器评估表达式
                formula = Formula(expr_str)
                result = formula.compute(data)
                # 确保结果是布尔类型
                if result.dtype != bool:
                    result = result.astype(bool)
                passed = passed & result
            except Exception as e:
                logger.warning(f"Failed to evaluate condition '{expr_str}': {e}")
                # 条件评估失败时不过滤
                continue

        return passed

    def filter_by_conditions(
        self,
        conditions: List[Union[ScreeningCondition, str]],
        df: pd.DataFrame,
        symbol_column: str = "symbol"
    ) -> List[str]:
        """根据筛选条件过滤数据，返回通过的股票列表

        Args:
            conditions: 筛选条件列表
            df: 包含 symbol 列和数据的 DataFrame
            symbol_column: 股票代码列名

        Returns:
            满足条件的股票代码列表
        """
        if not conditions or df.empty:
            if symbol_column in df.columns:
                return df[symbol_column].tolist()
            return df.index.tolist()

        # 应用别名
        processed_df = self.apply_aliases(df.copy())

        # 评估条件
        passed = self.evaluate(conditions, processed_df)

        # 收集通过的股票
        candidates = []
        for idx, row in processed_df.iterrows():
            symbol = row.get(symbol_column) if symbol_column in row.index else idx
            if symbol is None:
                continue
            if passed.get(idx, True):
                candidates.append(symbol)

        return candidates
