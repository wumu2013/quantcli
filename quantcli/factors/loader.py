"""因子配置加载器

支持加载:
- 单个因子文件 (factors/*.yaml)
- 策略配置文件 (strategies/*.yaml)
- 多阶段筛选配置 (fundamental_conditions, daily_conditions, ranking)
"""

import yaml
from pathlib import Path
from typing import Dict

from ..utils import get_logger
from .base import FactorDefinition, StrategyConfig, ScreeningCondition, BonusCondition

logger = get_logger(__name__)


__all__ = [
    # 新 API
    "load_factor",
    "load_strategy",
    "load_all_factors",
    "FactorDefinition",
    "StrategyConfig",
    "ScreeningCondition",
    "BonusCondition",
]


def load_factor(path: str) -> FactorDefinition:
    """加载单个因子文件

    Args:
        path: YAML 文件路径

    Returns:
        FactorDefinition 对象

    Example:
        # factors/pe.yaml
        name: 市盈率因子
        type: fundamental
        expr: "pe"
        direction: negative
        description: PE 越低越好
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return FactorDefinition(
        name=data["name"],
        type=data.get("type", "technical"),
        expr=data["expr"],
        direction=data.get("direction", "neutral"),
        description=data.get("description", ""),
        params=data.get("params", {}),
    )


def load_strategy(path: str) -> StrategyConfig:
    """加载策略配置

    Args:
        path: YAML 文件路径

    Returns:
        StrategyConfig 对象

    Example:
        # 统一格式
        name: 日内策略
        version: 1.0.0

        # 阶段1: 筛选条件
        screening:
          fundamental_conditions:
            - "roe > 0.1"
            - "netprofitmargin > 0.05"
          daily_conditions:
            - "ma10_slope > 0"
          limit: 50

        # 阶段2: 因子定义（内联或外部引用）
        factors:
          - name: ma10_deviation
            expr: "(close - ma(close, 10)) / ma(close, 10)"
            direction: negative
          - factors/intraday/is_yinliang.yaml

        # 阶段3: 排名/评分
        ranking:
          weights:
            ma10_deviation: 0.5
            is_yinliang: 0.3
          normalize: zscore
          conditions:           # 必要条件（可选）
            is_yinliang: true
          bonuses:              # 加分项（可选）
            - condition: "volume_ratio < 0.8"
              weight: 0.1
              description: 缩量加分

        output:
          limit: 30
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # 解析筛选条件
    screening = data.get("screening", {})
    screening_config = {}

    if isinstance(screening, list):
        # 旧格式：screening 直接是条件列表
        screening_config["conditions"] = [
            ScreeningCondition.from_string(expr) if isinstance(expr, str) else expr
            for expr in screening
        ]
        screening_config["limit"] = data.get("limit", 200)
    elif isinstance(screening, dict):
        # 解析 conditions（旧格式兼容）
        conditions = screening.get("conditions", [])
        screening_config["conditions"] = [
            ScreeningCondition.from_string(expr) if isinstance(expr, str) else expr
            for expr in conditions
        ]

        # 解析 fundamental_conditions
        fundamental_conds = screening.get("fundamental_conditions", [])
        screening_config["fundamental_conditions"] = [
            ScreeningCondition.from_string(expr) if isinstance(expr, str) else expr
            for expr in fundamental_conds
        ]

        # 解析 daily_conditions
        daily_conds = screening.get("daily_conditions", [])
        screening_config["daily_conditions"] = [
            ScreeningCondition.from_string(expr) if isinstance(expr, str) else expr
            for expr in daily_conds
        ]

        screening_config["limit"] = screening.get("limit", 200)
    else:
        screening_config = {"conditions": [], "limit": 200}

    # 解析 ranking 配置
    ranking = data.get("ranking", {})

    # 解析 weights
    weights = ranking.get("weights", {})
    parsed_weights = {}
    for key, value in weights.items():
        if isinstance(value, (int, float)):
            parsed_weights[key] = float(value)
        elif isinstance(value, str):
            try:
                parsed_weights[key] = float(value)
            except ValueError:
                logger.warning(f"Invalid weight value: {key}: {value}")
        else:
            logger.warning(f"Invalid weight type: {key}: {type(value)}")
    ranking["weights"] = parsed_weights

    # 解析 conditions（必要条件）
    ranking["conditions"] = ranking.get("conditions", {})

    # 解析 bonuses（加分项）
    bonuses = ranking.get("bonuses", [])
    if bonuses:
        ranking["bonuses"] = [
            BonusCondition.from_dict(b) for b in bonuses
        ]

    # 解析 inline factors（内联因子定义）
    factors = data.get("factors", [])
    if factors:
        # 检测是内联列表（dict）还是外部引用列表（string）
        inline_factors = []
        external_refs = {}
        for f in factors:
            if isinstance(f, dict):
                # 内联因子定义
                inline_factors.append(FactorDefinition(
                    name=f["name"],
                    type=f.get("type", "technical"),
                    expr=f["expr"],
                    direction=f.get("direction", "neutral"),
                    description=f.get("description", ""),
                    params=f.get("params", {}),
                ))
            elif isinstance(f, str):
                # 外部引用
                external_refs[f] = None  # 占位，后面会加载
            else:
                logger.warning(f"Invalid factor definition: {f}")
        ranking["inline_factors"] = inline_factors
        ranking["external_refs"] = list(external_refs.keys())

    # 解析分钟级配置
    intraday = data.get("intraday", {})
    intraday_weights = intraday.get("weights", {})
    intraday["weights"] = {
        k: float(v) for k, v in intraday_weights.items()
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.replace('.', '').isdigit())
    }

    return StrategyConfig(
        name=data["name"],
        version=data.get("version", "1.0.0"),
        screening=screening_config,
        ranking=ranking,
        intraday=intraday,
        output=data.get("output", {}),
    )


def resolve_factor_path(base_path: str, factor_ref: str) -> str:
    """解析因子文件路径

    查找顺序：
    1. 从策略文件所在目录
    2. 从 examples 目录
    3. 从内置因子库 (alpha101/*)

    Args:
        base_path: 策略配置路径
        factor_ref: 因子引用（如 "factors/pe.yaml"、"alpha101/alpha_001" 或 "./factors/pe.yaml"）

    Returns:
        完整的因子文件路径
    """
    from ..utils import builtin_factors_dir

    factor_path = Path(factor_ref)

    # 如果是绝对路径，直接返回
    if factor_path.is_absolute():
        return factor_ref

    # 简写格式支持：alpha101/alpha_xxx -> factors/alpha101/alpha_xxx.yaml
    if str(factor_ref).startswith("alpha101/"):
        alpha_name = Path(factor_ref).name
        if not alpha_name.endswith(".yaml"):
            alpha_name = f"{alpha_name}.yaml"
        full_path = builtin_factors_dir() / "alpha101" / alpha_name
        if full_path.exists():
            return str(full_path)

    # 可能的查找目录
    search_dirs = [
        Path(base_path).parent,  # 策略文件所在目录
        Path(base_path).parent / "..",  # 项目根目录
    ]

    for search_dir in search_dirs:
        search_dir = search_dir.resolve()
        # 如果路径以 factors/ 开头，从搜索目录查找
        if str(factor_ref).startswith("factors/"):
            full_path = search_dir / factor_ref
            if full_path.exists():
                return str(full_path)
        # 尝试直接拼接
        full_path = search_dir / factor_ref
        if full_path.exists():
            return str(full_path)

    # 如果都找不到，尝试从内置因子库查找
    builtin_path = builtin_factors_dir() / f"{factor_ref}.yaml"
    if builtin_path.exists():
        return str(builtin_path)

    # 返回默认路径
    base_dir = Path(base_path).parent
    return str(base_dir / factor_ref)


def load_factor_from_ref(base_path: str, factor_ref: str) -> FactorDefinition:
    """从引用加载因子文件

    Args:
        base_path: 策略配置路径
        factor_ref: 因子引用

    Returns:
        FactorDefinition 对象
    """
    factor_path = resolve_factor_path(base_path, factor_ref)
    return load_factor(factor_path)


def load_all_factors(weights: Dict[str, float], base_path: str) -> Dict[str, FactorDefinition]:
    """加载所有权重引用的因子

    Args:
        weights: 权重配置，key 是因子引用
        base_path: 策略配置路径

    Returns:
        因子定义字典
    """
    factors = {}
    for factor_ref in weights.keys():
        try:
            factor = load_factor_from_ref(base_path, factor_ref)
            factors[factor_ref] = factor
        except Exception as e:
            logger.error(f"Failed to load factor {factor_ref}: {e}")
    return factors
