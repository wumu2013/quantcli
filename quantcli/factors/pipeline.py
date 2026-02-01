"""多阶段因子筛选管道

支持:
- 阶段1: 基本面筛选 (fundamental_conditions)
- 阶段2: 日线筛选 (daily_conditions)
- 阶段3: 权重排序 (因子融合)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import date

from ..utils import get_logger
from .base import StrategyConfig
from .loader import load_strategy, load_all_factors
from .ranking import FactorRanker, ScoringEngine
from .screening import ScreeningEvaluator
from .compute import FactorComputer

logger = get_logger(__name__)


class FactorPipeline:
    """多阶段因子筛选管道"""

    def __init__(self, config_path: str, aliases: Optional[Dict[str, str]] = None):
        """初始化

        Args:
            config_path: 策略配置文件路径
            aliases: 列名别名映射（可选）
        """
        self.config_path = config_path
        self.config = load_strategy(config_path)
        normalize = self.config.ranking.get("normalize", "zscore")
        self.ranker = FactorRanker(normalize=normalize)
        self.scorer = ScoringEngine(normalize=normalize)
        self.screening_evaluator = ScreeningEvaluator(aliases)
        self.computer = FactorComputer()

    def run(
        self,
        symbols: List[str],
        date: date,
        price_data: Dict[str, pd.DataFrame],
        fundamental_data: pd.DataFrame,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """执行两阶段筛选（旧版兼容）

        Args:
            symbols: 股票代码列表
            date: 截止日期
            price_data: 价格数据字典，symbol -> DataFrame
            fundamental_data: 基本面数据 DataFrame

        Returns:
            筛选后的结果 DataFrame
        """
        # 阶段1: 基本面筛选
        screening_conditions = self.config.screening.get("conditions", [])
        screening_limit = self.config.screening.get("limit", 200)

        # 准备基本面列用于排名
        extra_columns = {}
        if not fundamental_data.empty:
            fund_df = self.screening_evaluator.apply_aliases(fundamental_data.copy())
            if "symbol" in fund_df.columns:
                fund_df = fund_df.set_index("symbol")
            # 将基本面列转换为 series 字典
            for col in fund_df.columns:
                extra_columns[col] = fund_df[col]

        if screening_conditions and extra_columns:
            candidates = self.screening_evaluator.filter_by_conditions(
                screening_conditions,
                fundamental_data.copy() if "symbol" in fundamental_data.columns else
                fundamental_data.reset_index().rename(columns={"index": "symbol"})
            )
        else:
            candidates = symbols

        logger.info(f"筛选后候选股票数量: {len(candidates)}")

        # 限制候选数量
        if len(candidates) > screening_limit:
            candidates = candidates[:screening_limit]

        if not candidates:
            return pd.DataFrame()

        # 阶段2: 权重排序
        return self._rank_candidates(candidates, price_data, extra_columns, limit)

    def run_multi_stage(
        self,
        symbols: List[str],
        date: date,
        price_data: Dict[str, pd.DataFrame],
        intraday_data: Dict[str, pd.DataFrame],
        fundamental_data: pd.DataFrame,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """执行多阶段筛选（基本面 → 日线 → 排名）

        Args:
            symbols: 股票代码列表
            date: 截止日期
            price_data: 日线价格数据字典，symbol -> DataFrame
            intraday_data: 分钟数据字典，symbol -> DataFrame
            fundamental_data: 基本面数据 DataFrame

        Returns:
            筛选后的结果 DataFrame
        """
        screening_config = self.config.screening
        screening_limit = screening_config.get("limit", 200)

        # 加载 ranking 因子
        ranking_config = self.config.ranking
        ranking_weights = ranking_config.get("weights", {})
        if not ranking_weights:
            logger.warning("没有 ranking 配置")
            return pd.DataFrame()

        # 区分外部文件引用和内联因子
        external_refs = {}
        for key in ranking_weights.keys():
            if "/" in key or key.endswith(".yaml") or "\\" in key:
                external_refs[key] = None

        # 加载外部因子文件
        ranking_factors = {}
        if external_refs:
            ranking_factors = load_all_factors(external_refs, self.config_path)

        # ==================== 阶段1: 基本面筛选 ====================
        candidates = self._stage1_fundamental_screening(
            symbols, fundamental_data, screening_config
        )

        if not candidates:
            logger.warning("没有满足基本面条件的股票")
            return pd.DataFrame()

        # ==================== 阶段2: 日线筛选 ====================
        candidates = self._stage2_daily_screening(
            candidates, price_data, screening_config, ranking_factors
        )

        if not candidates:
            logger.warning("没有满足日线条件的股票")
            return pd.DataFrame()

        # 限制候选数量
        if len(candidates) > screening_limit:
            candidates = candidates[:screening_limit]
            logger.info(f"限制候选数量到: {len(candidates)}")

        # ==================== 阶段3: 排名计算 ====================
        return self._stage3_ranking(
            candidates, price_data, intraday_data, ranking_factors, ranking_weights, limit
        )

    def _stage1_fundamental_screening(
        self,
        symbols: List[str],
        fundamental_data: pd.DataFrame,
        screening_config: Dict
    ) -> List[str]:
        """阶段1: 基本面筛选"""
        conditions = screening_config.get("fundamental_conditions", [])

        if not conditions or fundamental_data.empty:
            return symbols

        fund_df = self.screening_evaluator.apply_aliases(fundamental_data.copy())
        candidates = self.screening_evaluator.filter_by_conditions(conditions, fund_df)

        logger.info(f"基本面筛选后候选: {len(candidates)}")
        return candidates

    def _stage2_daily_screening(
        self,
        candidates: List[str],
        price_data: Dict[str, pd.DataFrame],
        screening_config: Dict,
        ranking_factors: Dict
    ) -> List[str]:
        """阶段2: 日线数据筛选"""
        conditions = screening_config.get("daily_conditions", [])

        if not conditions or not price_data:
            return candidates

        # 收集价格数据
        price_data_list = []
        for symbol in candidates:
            if symbol in price_data:
                df = price_data[symbol].copy()
                df["symbol"] = symbol
                price_data_list.append(df)

        if not price_data_list:
            return candidates

        price_df = pd.concat(price_data_list, ignore_index=True)
        latest_date = price_df["date"].max()
        latest_df = price_df[price_df["date"] == latest_date].copy()

        if latest_df.empty:
            return candidates

        # 计算需要的因子
        factor_names = self.computer.get_factor_names_from_conditions(
            conditions, {'close', 'open', 'high', 'low', 'volume', 'date', 'symbol'}
        )

        if factor_names:
            screening_factors = self.computer.compute_factors_for_screening(
                list(factor_names), ranking_factors, price_data, candidates
            )

            # 将因子值写入 latest_df
            for symbol, values in screening_factors.items():
                mask = latest_df["symbol"] == symbol
                for name, value in values.items():
                    latest_df.loc[mask, name] = value

        # 评估条件
        passed = self.screening_evaluator.evaluate(conditions, latest_df)

        # 收集通过的股票
        result = [
            s for s in candidates
            if s in latest_df["symbol"].values and
            passed.get(latest_df[latest_df["symbol"] == s].index[0], True)
        ]

        logger.info(f"日线筛选后候选: {len(result)}")
        return result

    def _stage3_ranking(
        self,
        candidates: List[str],
        price_data: Dict[str, pd.DataFrame],
        intraday_data: Dict[str, pd.DataFrame],
        factors: Dict,
        weights: Dict,
        limit: Optional[int]
    ) -> pd.DataFrame:
        """阶段3: 排名计算

        支持:
        - 权重融合
        - 必要条件过滤 (conditions)
        - 加分项 (bonuses)
        - 内联因子定义
        """
        # 将 weights 的 key 从文件路径转换为因子名
        weights_by_name = {}
        for key, weight in weights.items():
            if "/" in key or key.endswith(".yaml") or "\\" in key:
                # 文件路径，尝试转换为因子名
                if key in factors:
                    factor_name = factors[key].name
                    weights_by_name[factor_name] = weight
                else:
                    # 文件路径但在 factors 中找不到，尝试用 key 作为因子名
                    weights_by_name[key] = weight
            else:
                # 已经是因子名
                weights_by_name[key] = weight

        # 检查是否有内联因子定义
        inline_factors = self.config.ranking.get("inline_factors", [])
        if inline_factors:
            # 计算内联因子并合并
            computed_inline = self.computer.compute_inline_factors(
                inline_factors, price_data, intraday_data, candidates
            )
            if computed_inline:
                factors = {**factors, **computed_inline}
                # 更新权重配置中的 key
                for name in computed_inline.keys():
                    if name not in weights_by_name:
                        weights_by_name[name] = 0.0

        # 过滤掉无法加载的因子
        valid_factors = {}
        for name, factor in factors.items():
            if name in weights_by_name or name in [f.name for f in self.config.ranking.get("inline_factors", [])]:
                valid_factors[name] = factor
        factors = valid_factors

        # 计算所有因子
        factor_data = self.computer.compute_all_factors(
            factors, price_data, intraday_data, candidates
        )

        if not factor_data:
            logger.warning("没有有效数据用于排名")
            return pd.DataFrame()

        result_df = pd.DataFrame(factor_data)

        # 获取 conditions 和 bonuses
        conditions = self.config.ranking.get("conditions", {})
        bonuses = self.config.ranking.get("bonuses", [])

        # 使用 ScoringEngine 计算（传入已计算的因子 DataFrame）
        if conditions or bonuses:
            # 使用 ScoringEngine.compute() 的 precomputed_factors 参数
            result = self.scorer.compute(
                factors, weights_by_name, result_df,
                conditions=conditions,
                bonuses=bonuses,
                precomputed_factors=result_df
            )
        else:
            # 简单权重融合
            result = self.ranker.rank(factors, weights_by_name, result_df)

        # 添加 symbol 列
        result["symbol"] = result_df["symbol"].values

        # 输出配置
        output_config = self.config.output
        output_limit = limit or output_config.get("limit", 30)
        columns = output_config.get("columns", ["symbol", "score", "rank"])

        # 确保包含必要列
        for col in ["symbol", "score", "rank"]:
            if col not in columns:
                columns.insert(0, col)

        available_columns = [c for c in columns if c in result.columns]
        result = result[available_columns]

        if output_limit:
            result = result.head(output_limit)

        return result

    def _rank_candidates(
        self,
        candidates: List[str],
        price_data: Dict[str, pd.DataFrame],
        extra_columns: Dict[str, pd.Series],
        limit: Optional[int]
    ) -> pd.DataFrame:
        """内部方法: 对候选股票进行排名"""
        weights = self.config.ranking.get("weights", {})
        factors = {}

        # 区分外部文件引用和内联因子
        # 外部文件引用通常包含路径分隔符（如 "/" 或 ".yaml"）
        external_refs = {}
        inline_factor_names = set()

        for key in weights.keys():
            if "/" in key or key.endswith(".yaml") or "\\" in key:
                external_refs[key] = None
            else:
                inline_factor_names.add(key)

        # 加载外部因子文件
        if external_refs:
            factors = load_all_factors(external_refs, self.config_path)

        # 检查是否有内联因子定义
        inline_factors = self.config.ranking.get("inline_factors", [])
        if inline_factors:
            # 计算内联因子
            computed_inline = self.computer.compute_inline_factors(
                inline_factors, price_data, {}, candidates
            )
            if computed_inline:
                # 合并内联因子到 factors（key 为因子名）
                for name, factor in computed_inline.items():
                    factors[name] = factor
                # 确保权重配置中有对应的 key
                for name in computed_inline.keys():
                    if name not in weights:
                        weights[name] = 0.0

        # 收集价格数据
        price_data_list = []
        for symbol in candidates:
            if symbol in price_data:
                df = price_data[symbol].copy()
                df["symbol"] = symbol
                price_data_list.append(df)

        if not price_data_list:
            return pd.DataFrame()

        price_df = pd.concat(price_data_list, ignore_index=True)
        latest_df = price_df[price_df["date"] == price_df["date"].max()].copy()

        if latest_df.empty:
            return pd.DataFrame()

        # 合并额外列
        for name, series in extra_columns.items():
            latest_df[name] = latest_df["symbol"].map(series)

        # 获取 conditions 和 bonuses
        conditions = self.config.ranking.get("conditions", {})
        bonuses = self.config.ranking.get("bonuses", [])

        # 计算排名
        if conditions or bonuses:
            result = self.scorer.compute(
                factors, weights, latest_df,
                conditions=conditions,
                bonuses=bonuses,
                precomputed_factors=latest_df
            )
        else:
            result = self.ranker.rank(factors, weights, latest_df)

        result["symbol"] = latest_df["symbol"].values

        # 输出配置
        output_config = self.config.output
        output_limit = limit or output_config.get("limit", 30)
        columns = output_config.get("columns", ["symbol", "score", "rank"])

        for col in ["symbol", "score", "rank"]:
            if col not in columns:
                columns.insert(0, col)

        available_columns = [c for c in columns if c in result.columns]
        result = result[available_columns]

        if output_limit:
            result = result.head(output_limit)

        return result

    def screening_only(
        self,
        symbols: List[str],
        fundamental_data: pd.DataFrame
    ) -> List[str]:
        """仅执行筛选阶段

        Args:
            symbols: 股票代码列表
            fundamental_data: 基本面数据 DataFrame

        Returns:
            满足条件的股票代码列表
        """
        conditions = self.config.screening.get("conditions", [])

        if not conditions or fundamental_data.empty:
            return symbols

        fund_df = self.screening_evaluator.apply_aliases(fundamental_data.copy())
        return self.screening_evaluator.filter_by_conditions(conditions, fund_df)
