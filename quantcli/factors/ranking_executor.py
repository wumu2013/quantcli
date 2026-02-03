"""on_bar 环境的 ranking 执行器

用于掘金量化策略的 on_bar 事件中执行因子排名。
"""

import pandas as pd
from datetime import date, timedelta
from typing import Dict, List, Optional

from ..utils import get_logger
from .base import StrategyConfig
from .loader import load_strategy, load_all_factors
from .ranking import FactorRanker, ScoringEngine
from .compute import FactorComputer
from ..models.bar import MinuteBar

logger = get_logger(__name__)


class RankingExecutor:
    """on_bar 环境的 ranking 执行器

    在掘金量化的 on_bar 事件中执行因子排名。

    Attributes:
        config: 策略配置
        mysql: MySQL 数据源
        computer: 因子计算器
        scorer: 评分引擎
        ranker: 排名引擎
        ranking_weights: ranking 权重配置
        output_config: 输出配置

    使用示例:
        >>> from quantcli.factors import RankingExecutor
        >>> from quantcli.datasources import MySQLDataSource
        >>>
        >>> def init(context):
        ...     context.mysql = MySQLDataSource()
        ...     context.executor = RankingExecutor(
        ...         "examples/strategies/ma10_yinliang_intraday.yaml",
        ...         context.mysql
        ...     )
        >>>
        >>> def on_bar(context, bars):
        ...     for bar in bars:
        ...         result = context.executor.run_on_bar(
        ...             bar=bar,
        ...             candidate_symbols=context.symbols,
        ...             lookback_days=20
        ...         )
    """

    def __init__(self, config_path: str, mysql_datasource):
        """初始化 RankingExecutor

        Args:
            config_path: 策略配置文件路径
            mysql_datasource: MySQLDataSource 实例
        """
        self.config = load_strategy(config_path)
        self.mysql = mysql_datasource
        self.computer = FactorComputer()

        normalize = self.config.ranking.get("normalize", "zscore")
        self.scorer = ScoringEngine(normalize=normalize)
        self.ranker = FactorRanker(normalize=normalize)

        # 提取 ranking 配置
        self.ranking_config = self.config.ranking
        self.ranking_weights = self.ranking_config.get("weights", {})
        self.output_config = self.config.output

        # 加载外部因子文件
        self._load_factors()

    def _load_factors(self):
        """加载 ranking 阶段的因子定义"""
        external_refs = {}
        for key in self.ranking_weights.keys():
            if "/" in key or key.endswith(".yaml") or "\\" in key:
                external_refs[key] = None

        self.ranking_factors = {}
        if external_refs:
            self.ranking_factors = load_all_factors(external_refs, self.config_path)

    def run_on_bar(
        self,
        bar: MinuteBar,
        candidate_symbols: List[str],
        lookback_days: int = 20
    ) -> pd.DataFrame:
        """在 on_bar 中执行 ranking

        Args:
            bar: 当前触发的 MinuteBar
            candidate_symbols: 候选股票列表（固定股票池）
            lookback_days: 回溯天数

        Returns:
            排名后的 DataFrame，包含 [symbol, score, rank, ...因子列]
        """
        period = bar.period
        trade_date = bar.trade_date

        # 1. 获取候选股票的历史分钟数据
        price_data = self._fetch_price_data(candidate_symbols, lookback_days, period, trade_date)

        if not price_data:
            logger.warning("没有获取到价格数据")
            return pd.DataFrame()

        # 2. 将当前 bar 追加到对应股票数据中
        price_data = self._append_bar(price_data, bar)

        # 3. 执行 ranking
        return self._run_ranking(candidate_symbols, price_data)

    def _fetch_price_data(
        self,
        symbols: List[str],
        lookback_days: int,
        period: str,
        end_date: date = None
    ) -> Dict[str, pd.DataFrame]:
        """获取股票池的历史分钟数据

        Args:
            symbols: 股票代码列表
            lookback_days: 回溯天数
            period: 分钟周期
            end_date: 结束日期，默认到当前交易日

        Returns:
            {symbol: DataFrame} 字典
        """
        if end_date is None:
            from datetime import date as date_cls
            end_date = date_cls.today()

        start_date = end_date - timedelta(days=lookback_days)

        # 从 MySQL 批量查询
        return self.mysql.get_pool_minute_data(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            period=period
        )

    def _append_bar(
        self,
        price_data: Dict[str, pd.DataFrame],
        bar: MinuteBar
    ) -> Dict[str, pd.DataFrame]:
        """将当前 bar 追加到价格数据中

        Args:
            price_data: 现有的价格数据字典
            bar: 当前 MinuteBar

        Returns:
            更新后的价格数据字典
        """
        symbol = bar.symbol

        if symbol not in price_data:
            # 新股票，创建新的 DataFrame
            df = pd.DataFrame([bar.to_dataframe_row()])
        else:
            df = price_data[symbol].copy()
            # 移除同一时间点的旧数据
            df = df[~((df['date'] == bar.trade_date) & (df['time'] == bar.trade_time))]
            # 追加新数据
            new_row = pd.DataFrame([bar.to_dataframe_row()])
            df = pd.concat([df, new_row], ignore_index=True)

        # 确保列顺序正确
        df = df[['symbol', 'date', 'time', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        df = df.sort_values(['date', 'time']).reset_index(drop=True)

        price_data[symbol] = df
        return price_data

    def _run_ranking(
        self,
        candidates: List[str],
        price_data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """执行 ranking 阶段

        Args:
            candidates: 候选股票列表
            price_data: 价格数据字典

        Returns:
            排名后的 DataFrame
        """
        if not candidates or not price_data:
            return pd.DataFrame()

        # 过滤有效的候选股票
        valid_symbols = [s for s in candidates if s in price_data and not price_data[s].empty]
        if not valid_symbols:
            return pd.DataFrame()

        # 计算所有因子
        factor_data = self.computer.compute_all_factors(
            self.ranking_factors, price_data, {}, valid_symbols
        )

        if factor_data.empty:
            logger.warning("没有有效数据用于排名")
            return pd.DataFrame()

        # 获取 conditions 和 bonuses
        conditions = self.ranking_config.get("conditions", {})
        bonuses = self.ranking_config.get("bonuses", [])

        # 执行评分
        if conditions or bonuses:
            result = self.scorer.compute(
                self.ranking_factors,
                self.ranking_weights,
                factor_data,
                conditions=conditions,
                bonuses=bonuses
            )
        else:
            result = self.ranker.rank(
                self.ranking_factors,
                self.ranking_weights,
                factor_data
            )

        # 添加 symbol 列
        result["symbol"] = factor_data["symbol"].values

        # 应用输出配置
        return self._apply_output_config(result)

    def _apply_output_config(self, result: pd.DataFrame) -> pd.DataFrame:
        """应用输出配置

        Args:
            result: 排名结果 DataFrame

        Returns:
            过滤和排序后的 DataFrame
        """
        if result.empty:
            return result

        output_limit = self.output_config.get("limit", 30)
        columns = self.output_config.get("columns", ["symbol", "score", "rank"])

        # 确保包含必要列
        for col in ["symbol", "score", "rank"]:
            if col not in columns:
                columns.insert(0, col)

        # 只保留存在的列
        available_columns = [c for c in columns if c in result.columns]
        result = result[available_columns]

        # 限制数量
        if output_limit:
            result = result.head(output_limit)

        return result
