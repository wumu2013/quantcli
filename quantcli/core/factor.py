"""因子引擎 - 因子计算、评估、管理

功能:
1. 因子定义和注册
2. 因子计算 (向量化)
3. 因子评估 (IC分析、分位数分析、衰减分析)
4. 因子正交化、中性化

Usage:
    >>> from quantcli.core import FactorEngine, Factor
    >>> engine = FactorEngine(dm)
    >>> engine.register(Factor(name="momentum", formula="close / delay(close, 20) - 1"))
    >>> result = engine.compute("momentum", df)
    >>> ic = engine.evaluate_ic("momentum", df)
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import numpy as np

from .data import DataManager, DataConfig
from ..parser import Formula, compute_factor
from ..utils import get_logger, parse_date

logger = get_logger(__name__)


@dataclass
class Factor:
    """因子定义（核心引擎使用）"""
    name: str
    formula: str
    description: str = ""
    category: str = "custom"
    params: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"

    def __post_init__(self):
        if not self.name:
            raise ValueError("Factor name is required")
        if not self.formula:
            raise ValueError("Factor formula is required")

    @classmethod
    def from_factor_definition(cls, fd) -> "Factor":
        """从 FactorDefinition 创建 Factor"""
        return cls(
            name=fd.name,
            formula=fd.expr,
            description=fd.description,
            category=fd.type,
            params=fd.params,
        )


@dataclass
class FactorEvaluation:
    """因子评估结果"""
    factor_name: str
    evaluated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # IC 统计
    ic_mean: float = 0.0
    ic_std: float = 0.0
    ic_ir: float = 0.0
    ic_positive_ratio: float = 0.0
    t_stat: float = 0.0
    p_value: float = 1.0

    # 收益统计
    period_returns: Dict[str, float] = field(default_factory=dict)

    # 衰减分析
    decay: Dict[str, float] = field(default_factory=dict)

    # 分位数收益
    quantile_returns: Dict[str, float] = field(default_factory=dict)
    long_short_return: float = 0.0

    # 元数据
    universe: str = ""
    start_date: Optional = None
    end_date: Optional = None
    sample_size: int = 0

    def to_dict(self) -> Dict:
        return {
            "factor_name": self.factor_name,
            "evaluated_at": self.evaluated_at,
            "ic_stats": {
                "ic_mean": self.ic_mean,
                "ic_std": self.ic_std,
                "ic_ir": self.ic_ir,
                "ic_positive_ratio": self.ic_positive_ratio,
                "t_stat": self.t_stat,
                "p_value": self.p_value,
            },
            "period_returns": self.period_returns,
            "decay": self.decay,
            "quantile_returns": self.quantile_returns,
            "long_short_return": self.long_short_return,
            "universe": self.universe,
            "sample_size": self.sample_size,
        }


class FactorRegistry:
    """因子注册表"""

    def __init__(self):
        self._factors: Dict[str, Factor] = {}

    def register(self, factor):
        """注册因子（支持 Factor 或 FactorDefinition）"""
        # 如果是 FactorDefinition，转换为 Factor
        if hasattr(factor, 'type') and hasattr(factor, 'expr'):
            factor = Factor.from_factor_definition(factor)

        if factor.name in self._factors:
            logger.warning(f"Factor {factor.name} already exists, overwriting")
        self._factors[factor.name] = factor
        logger.info(f"Registered factor: {factor.name}")

    def get(self, name: str) -> Optional[Factor]:
        return self._factors.get(name)

    def list_all(self) -> List[str]:
        return list(self._factors.keys())

    def load_from_file(self, path: Union[str, Path]):
        """从文件加载因子"""
        path = Path(path)
        if path.suffix == ".yaml":
            self._load_yaml(path)
        elif path.suffix == ".qf":
            self._load_qf(path)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

    def _load_yaml(self, path: Path):
        """从YAML加载"""
        import yaml
        with open(path, "r") as f:
            data = yaml.safe_load(f)

        items = data if isinstance(data, list) else [data]
        for item in items:
            self.register(Factor(
                name=item["name"],
                formula=item["formula"],
                description=item.get("description", ""),
                category=item.get("category", "custom"),
                params=item.get("params", {}),
                tags=item.get("tags", []),
            ))

    def _load_qf(self, path: Path):
        """从.qf文件加载"""
        import yaml
        with open(path, "r") as f:
            data = yaml.safe_load(f)

        self.register(Factor(
            name=data["name"],
            formula=data["formula"],
            description=data.get("description", ""),
            category=data.get("meta", {}).get("category", "custom"),
            params=data.get("params", {}),
            tags=data.get("meta", {}).get("tags", []),
        ))

    def save_to_file(self, path: Union[str, Path], names: Optional[List[str]] = None):
        """保存因子到文件"""
        factors = [self._factors[n] for n in (names or self.list_all()) if n in self._factors]

        import yaml
        data = [{
            "name": f.name,
            "formula": f.formula,
            "description": f.description,
            "category": f.category,
            "params": f.params,
            "tags": f.tags,
        } for f in factors]

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


class FactorEngine:
    """因子计算引擎"""

    def __init__(
        self,
        dm: Optional[DataManager] = None,
        config: Optional[DataConfig] = None,
        registry: Optional[FactorRegistry] = None
    ):
        self.dm = dm
        self.config = config or DataConfig()
        self.registry = registry or FactorRegistry()
        self._factor_cache: Dict[str, pd.Series] = {}

    def set_data_manager(self, dm: DataManager):
        """设置数据管理器"""
        self.dm = dm

    def register(self, factor: Factor):
        """注册因子"""
        self.registry.register(factor)

    def register_from_file(self, path: Union[str, Path]):
        """从文件注册因子"""
        self.registry.load_from_file(path)

    def compute(
        self,
        name: str,
        data: Union[pd.DataFrame, Dict[str, pd.Series]],
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> pd.Series:
        """计算单个因子"""
        factor = self.registry.get(name)
        formula = factor.formula if factor else name

        cache_key = f"{name}_{id(data)}"
        if use_cache and cache_key in self._factor_cache:
            return self._factor_cache[cache_key].copy()

        if isinstance(data, dict):
            data = pd.DataFrame(data)

        all_params = {}
        if factor and factor.params:
            all_params.update(factor.params)
        if params:
            all_params.update(params)

        try:
            result = compute_factor(formula, data, params=all_params)
        except Exception as e:
            raise RuntimeError(f"Failed to compute factor '{name}': {e}")

        if isinstance(result, pd.DataFrame):
            result = result.iloc[:, 0]

        result = result.dropna()

        if use_cache:
            self._factor_cache[cache_key] = result.copy()

        return result.copy()

    def compute_batch(
        self,
        names: List[str],
        data: Union[pd.DataFrame, Dict[str, pd.Series]],
        params: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """批量计算多个因子"""
        results = {}
        for name in names:
            try:
                results[name] = self.compute(name, data, params=params)
            except Exception as e:
                logger.error(f"Failed to compute factor '{name}': {e}")

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        return df.dropna(how="all")

    def get_factor_data(
        self,
        name: str,
        start_date,
        end_date,
        universe: Optional[List[str]] = None,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """获取因子数据（自动从数据源获取价格数据）"""
        if self.dm is None:
            raise ValueError("DataManager not set. Call set_data_manager() first.")

        if universe:
            price_df = self.dm.get_daily_batch(universe, start_date, end_date, use_cache=use_cache)
        else:
            stocks = self.dm.get_universe("all")
            symbols = [s.symbol for s in stocks[:100]]
            price_df = self.dm.get_daily_batch(symbols, start_date, end_date, use_cache=use_cache)

        if price_df.empty:
            return pd.DataFrame()

        price_df = price_df.set_index(["date", "symbol"]).unstack()
        factor_series = self.compute(name, price_df)

        result = factor_series.to_frame(name=name).reset_index()
        result = result.melt(id_vars=["date"], var_name="symbol", value_name=name)

        return result

    # =============================================================================
    # 因子评估
    # =============================================================================

    def evaluate_ic(
        self,
        name: str,
        data: Union[pd.DataFrame, Dict[str, pd.Series]],
        forward_periods: List[int] = [1, 5, 10, 20]
    ) -> Dict[str, Any]:
        """评估因子的信息系数 (IC)"""
        factor = self.compute(name, data)

        if isinstance(data, dict):
            returns = data.get("returns")
        else:
            returns = data.get("returns") if isinstance(data, pd.DataFrame) else None

        if returns is None:
            raise ValueError("Data must contain 'returns' column for IC evaluation")

        results = {"factor_name": name, "period_returns": {}, "decay": {}}

        for period in forward_periods:
            future_returns = returns.shift(-period)
            valid = factor.notna() & future_returns.notna()
            if valid.sum() < 10:
                logger.warning(f"Insufficient data for period {period}")
                continue

            ic = factor[valid].corr(future_returns[valid])
            results["period_returns"][f"{period}d"] = ic

        ic_values = list(results["period_returns"].values())
        if ic_values:
            results["ic_stats"] = {
                "ic_mean": np.mean(ic_values),
                "ic_std": np.std(ic_values),
                "ic_ir": np.mean(ic_values) / np.std(ic_values) if np.std(ic_values) > 0 else 0,
            }

        return results

    def evaluate_quantiles(
        self,
        name: str,
        data: Union[pd.DataFrame, Dict[str, pd.Series]],
        groups: int = 10,
        period: int = 1
    ) -> Dict[str, Any]:
        """分位数分析"""
        factor = self.compute(name, data)

        if isinstance(data, dict):
            returns = data.get("returns")
        else:
            returns = data.get("returns") if isinstance(data, pd.DataFrame) else None

        if returns is None:
            raise ValueError("Data must contain 'returns' column")

        future_returns = returns.shift(-period)
        valid = factor.notna() & future_returns.notna()
        valid_factor = factor[valid]
        valid_returns = future_returns[valid]

        if len(valid_factor) < 100:
            raise ValueError("Insufficient data for quantile analysis")

        try:
            quantile_labels = pd.qcut(valid_factor, q=groups, labels=[f"Q{i+1}" for i in range(groups)])
        except ValueError:
            quantile_labels = pd.qcut(valid_factor, q=groups, labels=[f"Q{i+1}" for i in range(groups)], duplicates="drop")

        quantile_returns = {}
        for q in quantile_labels.unique():
            mask = quantile_labels == q
            quantile_returns[q] = valid_returns[mask].mean()

        long_short = quantile_returns.get(f"Q{groups}", 0) - quantile_returns.get("Q1", 0)

        return {
            "factor_name": name,
            "groups": groups,
            "quantile_returns": quantile_returns,
            "long_short_return": long_short,
            "sample_size": valid.sum(),
        }

    def evaluate_full(
        self,
        name: str,
        data: Union[pd.DataFrame, Dict[str, pd.Series]],
        forward_periods: List[int] = [1, 5, 10, 20],
        decay_periods: List[int] = [0, 1, 2, 3, 5]
    ) -> FactorEvaluation:
        """完整因子评估"""
        factor = self.compute(name, data)

        if isinstance(data, dict):
            returns = data.get("returns")
        else:
            returns = data.get("returns") if isinstance(data, pd.DataFrame) else None

        eval_result = FactorEvaluation(factor_name=name)

        if returns is not None:
            ic_values = []
            for period in forward_periods:
                future_returns = returns.shift(-period)
                valid = factor.notna() & future_returns.notna()
                if valid.sum() > 10:
                    ic = factor[valid].corr(future_returns[valid])
                    ic_values.append(ic)
                    eval_result.period_returns[f"-{period}d"] = ic

            if ic_values:
                eval_result.ic_mean = np.mean(ic_values)
                eval_result.ic_std = np.std(ic_values)
                eval_result.ic_ir = eval_result.ic_mean / eval_result.ic_std if eval_result.ic_std > 0 else 0

            try:
                quant = self.evaluate_quantiles(name, data)
                eval_result.quantile_returns = quant.get("quantile_returns", {})
                eval_result.long_short_return = quant.get("long_short_return", 0)
            except Exception as e:
                logger.warning(f"Quantile analysis failed: {e}")

            for lag in decay_periods:
                lagged_factor = factor.shift(lag)
                valid = lagged_factor.notna() & returns.notna()
                if valid.sum() > 10:
                    ic = lagged_factor[valid].corr(returns[valid])
                    eval_result.decay[f"lag_{lag}"] = ic

        eval_result.sample_size = factor.notna().sum()
        return eval_result

    # =============================================================================
    # 因子处理
    # =============================================================================

    def orthogonalize(
        self,
        factors: Union[str, List[str], pd.DataFrame],
        method: str = "gs"
    ) -> pd.DataFrame:
        """因子正交化"""
        if isinstance(factors, str):
            factor_names = [factors]
            data = self.compute_batch(factor_names, {})
        elif isinstance(factors, list):
            factor_names = factors
            data = self.compute_batch(factors, {})
        else:
            data = factors
            factor_names = list(data.columns)

        if data.empty:
            return data

        # Gram-Schmidt 正交化
        def gram_schmidt(df):
            n = len(df.columns)
            result = pd.DataFrame(index=df.index)

            for i, col in enumerate(df.columns):
                v = df[col].values
                for j in range(i):
                    v = v - result.iloc[:, j].values * np.corrcoef(v, result.iloc[:, j].values)[0, 1] * result.iloc[:, j].values.std()
                v = v - np.nanmean(v)
                if np.nanstd(v) > 0:
                    result[col] = v / np.nanstd(v)
                else:
                    result[col] = 0
            return result

        if method == "gs":
            return gram_schmidt(data)
        raise ValueError(f"Unknown orthogonalization method: {method}")

    def neutralize(self, factor: pd.Series, by: str = "industry") -> pd.Series:
        """因子中性化"""
        return factor - factor.groupby(level="date").transform("mean")

    def clear_cache(self):
        """清理因子缓存"""
        self._factor_cache.clear()
        logger.info("Factor cache cleared")

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "status": "ok",
            "registered_factors": self.registry.list_all(),
            "cache_size": len(self._factor_cache),
        }
