"""Screening 执行器 - 从 MySQL 数据中筛选股票

用于掘金量化策略 init 阶段，从 MySQL 获取数据并执行筛选。
"""

import pandas as pd
from datetime import date, timedelta
from typing import Dict, List, Optional

from ..utils import get_logger
from .base import StrategyConfig
from .loader import load_strategy
from .screening import ScreeningEvaluator
from .compute import FactorComputer

logger = get_logger(__name__)


class ScreeningExecutor:
    """Screening 执行器

    从 MySQL 数据源执行策略的筛选阶段（screening），返回满足条件的股票列表。

    Attributes:
        config: 策略配置
        mysql: MySQL 数据源
        evaluator: 筛选条件评估器
        computer: 因子计算器（用于日线条件）

    使用示例:
        >>> from quantcli.factors import ScreeningExecutor
        >>> from quantcli.datasources import MySQLDataSource
        >>>
        >>> def init(context):
        ...     mysql = MySQLDataSource()
        ...     screener = ScreeningExecutor(
        ...         "examples/strategies/ma10_yinliang_intraday.yaml",
        ...         mysql
        ...     )
        ...     context.symbols = screener.run()
        ...     context.subscribe(context.symbols)
    """

    def __init__(self, config_path: str, mysql_datasource):
        """初始化 ScreeningExecutor

        Args:
            config_path: 策略配置文件路径
            mysql_datasource: MySQLDataSource 实例
        """
        self.config = load_strategy(config_path)
        self.mysql = mysql_datasource
        self.evaluator = ScreeningEvaluator()
        self.computer = FactorComputer()

    def run(
        self,
        symbols: Optional[List[str]] = None,
        lookback_days: int = 30
    ) -> List[str]:
        """执行 screening

        从 MySQL 获取数据，执行基本面和日线条件筛选。

        Args:
            symbols: 初始股票列表（None 则从 stock_list 获取全部）
            lookback_days: 日线数据回溯天数

        Returns:
            筛选后的股票代码列表
        """
        end_date = self._get_last_trading_day()

        # 1. 获取股票列表
        if symbols is None:
            symbols = self._get_stock_list()
            if not symbols:
                logger.warning("没有获取到股票列表")
                return []

        logger.info(f"初始股票数量: {len(symbols)}")

        # 2. 基本面筛选
        candidates = self._fundamental_screening(symbols, end_date)
        if not candidates:
            logger.warning("基本面筛选后无候选股票")
            return []

        logger.info(f"基本面筛选后: {len(candidates)}")

        # 3. 日线筛选
        candidates = self._daily_screening(candidates, end_date, lookback_days)
        if not candidates:
            logger.warning("日线筛选后无候选股票")
            return []

        logger.info(f"日线筛选后: {len(candidates)}")

        # 4. 应用 limit
        limit = self.config.screening.get("limit")
        if limit and len(candidates) > limit:
            candidates = candidates[:limit]
            logger.info(f"限制到: {len(candidates)}")

        return candidates

    def run_fundamental_only(
        self,
        symbols: Optional[List[str]] = None
    ) -> List[str]:
        """仅执行基本面筛选

        Args:
            symbols: 初始股票列表

        Returns:
            满足基本面条件的股票列表
        """
        end_date = self._get_last_trading_day()

        if symbols is None:
            symbols = self._get_stock_list()

        return self._fundamental_screening(symbols, end_date)

    def run_daily_only(
        self,
        symbols: List[str],
        lookback_days: int = 30
    ) -> List[str]:
        """仅执行日线筛选

        Args:
            symbols: 股票列表
            lookback_days: 回溯天数

        Returns:
            满足日线条件的股票列表
        """
        end_date = self._get_last_trading_day()
        return self._daily_screening(symbols, end_date, lookback_days)

    def _get_stock_list(self) -> List[str]:
        """获取股票列表"""
        try:
            df = self.mysql.get_stock_list()
            if df.empty:
                return []
            return df['symbol'].tolist()
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return []

    def _get_last_trading_day(self) -> date:
        """获取最近交易日"""
        try:
            calendar = self.mysql.get_trading_calendar()
            if calendar:
                return calendar[-1]
        except Exception as e:
            logger.warning(f"获取交易日历失败: {e}")

        # 降级：返回昨天
        return date.today() - timedelta(1)

    def _fundamental_screening(
        self,
        symbols: List[str],
        end_date: date
    ) -> List[str]:
        """基本面筛选"""
        conditions = self.config.screening.get("fundamental_conditions", [])

        if not conditions:
            return symbols

        # 获取基本面数据
        try:
            fundamental = self.mysql.get_fundamental(symbols, end_date)
        except Exception as e:
            logger.error(f"获取基本面数据失败: {e}")
            return symbols

        if fundamental.empty:
            logger.warning("基本面数据为空")
            return symbols

        # 应用别名并筛选
        processed_df = self.evaluator.apply_aliases(fundamental)
        candidates = self.evaluator.filter_by_conditions(
            conditions, processed_df
        )

        return candidates

    def _daily_screening(
        self,
        symbols: List[str],
        end_date: date,
        lookback_days: int
    ) -> List[str]:
        """日线筛选"""
        conditions = self.config.screening.get("daily_conditions", [])

        if not conditions:
            return symbols

        # 获取日线数据
        try:
            start_date = end_date - timedelta(lookback_days)
            price_data = self.mysql.get_multi_daily(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date
            )
        except Exception as e:
            logger.error(f"获取日线数据失败: {e}")
            return symbols

        if not price_data:
            logger.warning("日线数据为空")
            return symbols

        # 合并所有股票数据
        dfs = []
        for symbol, df in price_data.items():
            if df.empty:
                continue
            df = df.copy()
            df['symbol'] = symbol
            dfs.append(df)

        if not dfs:
            return symbols

        all_data = pd.concat(dfs, ignore_index=True)

        # 获取最新一天的数据
        latest_date = all_data['date'].max()
        latest_data = all_data[all_data['date'] == latest_date].copy()

        if latest_data.empty:
            return symbols

        # 提取需要的因子
        factor_names = self.computer.get_factor_names_from_conditions(
            conditions, {'close', 'open', 'high', 'low', 'volume', 'date', 'symbol'}
        )

        if factor_names:
            # 计算需要的因子
            computed_factors = self._compute_factors_for_screening(
                list(factor_names), price_data, symbols
            )

            # 将因子值写入 latest_data
            for symbol, values in computed_factors.items():
                mask = latest_data['symbol'] == symbol
                for name, value in values.items():
                    latest_data.loc[mask, name] = value

        # 评估条件
        passed = self.evaluator.evaluate(conditions, latest_data)

        # 收集通过的股票
        candidates = [
            s for s in symbols
            if s in latest_data['symbol'].values and
            passed.get(latest_data[latest_data['symbol'] == s].index[0], True)
        ]

        return candidates

    def _compute_factors_for_screening(
        self,
        factor_names: List[str],
        price_data: Dict[str, pd.DataFrame],
        symbols: List[str]
    ) -> Dict[str, Dict[str, float]]:
        """为筛选条件计算因子值"""
        results = {}

        for symbol in symbols:
            if symbol not in price_data:
                continue

            df = price_data[symbol]
            if df.empty:
                continue

            symbol_results = {}
            for factor_name in factor_names:
                try:
                    # 从 config.factors 中查找因子定义
                    factor = self._find_factor_by_name(factor_name)
                    if not factor:
                        continue

                    from ..parser import Formula
                    formula = Formula(factor.expr, name=factor_name)
                    result = formula.compute(df)

                    if not result.empty:
                        symbol_results[factor_name] = float(result.iloc[-1])
                except Exception as e:
                    logger.debug(f"计算因子 {factor_name} 失败: {e}")

            if symbol_results:
                results[symbol] = symbol_results

        return results

    def _find_factor_by_name(self, factor_name: str):
        """从配置中查找因子定义"""
        factors = self.config.factors or []

        for f in factors:
            # 支持因子对象或字典
            if hasattr(f, 'name') and f.name == factor_name:
                return f
            elif isinstance(f, dict) and f.get('name') == factor_name:
                from .base import FactorDefinition
                return FactorDefinition(**f)

            # 支持路径匹配
            if factor_name in str(f).lower():
                if hasattr(f, 'name'):
                    return f
                elif isinstance(f, dict):
                    from .base import FactorDefinition
                    return FactorDefinition(**f)

        return None
