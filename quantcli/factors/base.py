"""因子定义基础类"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class FactorType(str, Enum):
    """因子类型"""
    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"
    INTRADAY = "intraday"
    COMPOSITE = "composite"


class FactorDirection(str, Enum):
    """因子方向"""
    POSITIVE = "positive"      # 值越高越好
    NEGATIVE = "negative"      # 值越低越好
    NEUTRAL = "neutral"        # 无方向性


@dataclass
class FactorDefinition:
    """因子定义

    Attributes:
        name: 因子名称
        type: 因子类型 (fundamental/technical)
        expr: 因子表达式
        direction: 因子方向 (positive/negative/neutral)
        description: 因子描述
        params: 可选参数
    """
    name: str
    type: str
    expr: str
    direction: str = "neutral"
    description: str = ""
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """验证参数"""
        if self.type not in [t.value for t in FactorType]:
            raise ValueError(f"Invalid factor type: {self.type}")
        if self.direction not in [d.value for d in FactorDirection]:
            raise ValueError(f"Invalid factor direction: {self.direction}")


@dataclass
class ScreeningStage:
    """筛选阶段配置

    Attributes:
        conditions: 简化的条件列表（向后兼容）
        fundamental_conditions: 基本面条件（需要基本面数据）
        daily_conditions: 日线条件（需要日线数据）
        limit: 候选数量限制
    """
    conditions: List[str] = field(default_factory=list)
    fundamental_conditions: List[str] = field(default_factory=list)
    daily_conditions: List[str] = field(default_factory=list)
    limit: int = 200

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScreeningStage":
        """从字典创建筛选阶段配置"""
        if isinstance(data, list):
            # 兼容旧格式：直接是条件列表
            return cls(conditions=data)
        return cls(
            conditions=data.get("conditions", []),
            fundamental_conditions=data.get("fundamental_conditions", []),
            daily_conditions=data.get("daily_conditions", []),
            limit=data.get("limit", 200),
        )


@dataclass
class IntradayStage:
    """分钟级阶段配置

    Attributes:
        weights: 因子权重配置
        normalize: 标准化方法
    """
    weights: Dict[str, float] = field(default_factory=dict)
    normalize: str = "zscore"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntradayStage":
        """从字典创建分钟级配置"""
        return cls(
            weights=data.get("weights", {}),
            normalize=data.get("normalize", "zscore"),
        )


# 回测配置类 (需要在 StrategyConfig 之前定义)
@dataclass
class BacktestEntryConfig:
    """回测买入配置

    Attributes:
        price: 买入价格类型 (open_today/open_next)
        timing: 买入时机 (immediate/close)
    """
    price: str = "open_next"  # open_today=当天开盘, open_next=次日开盘
    timing: str = "immediate"  # immediate=立即, close=收盘

    @classmethod
    def from_dict(cls, data: Any) -> "BacktestEntryConfig":
        if isinstance(data, str):
            return cls(price=data)
        return cls(
            price=data.get("price", "open_next"),
            timing=data.get("timing", "immediate"),
        )


@dataclass
class BacktestExitRule:
    """回测卖出规则

    Attributes:
        rule: 规则类型 (timed/time_of_day/close)
        hold_days: 持有天数
        time: 触发时间 (如 "10:00")
        price: 卖出价格 (open/close)
    """
    rule: str = "timed"
    hold_days: int = 1
    time: str = "10:00"
    price: str = "close"

    @classmethod
    def from_dict(cls, data: Any) -> "BacktestExitRule":
        if isinstance(data, str):
            return cls(rule="time_of_day", time=data)
        return cls(
            rule=data.get("rule", "timed"),
            hold_days=data.get("hold_days", 1),
            time=data.get("time", "10:00"),
            price=data.get("price", "close"),
        )


@dataclass
class BacktestConfig:
    """回测配置"""
    entry: BacktestEntryConfig = None
    exit: List[BacktestExitRule] = None
    capital: float = 1000000.0
    fee: float = 0.0003
    intraday_data: bool = False

    def __post_init__(self):
        if self.entry is None:
            self.entry = BacktestEntryConfig()
        if self.exit is None:
            self.exit = [BacktestExitRule(rule="close")]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BacktestConfig":
        entry_data = data.get("entry", {})
        exit_data = data.get("exit", [])
        exit_rules = []
        if isinstance(exit_data, list):
            for rule in exit_data:
                exit_rules.append(BacktestExitRule.from_dict(rule))
        elif isinstance(exit_data, dict):
            exit_rules.append(BacktestExitRule.from_dict(exit_data))
        return cls(
            entry=BacktestEntryConfig.from_dict(entry_data) if entry_data else BacktestEntryConfig(),
            exit=exit_rules,
            capital=data.get("capital", 1000000.0),
            fee=data.get("fee", 0.0003),
            intraday_data=data.get("intraday_data", False),
        )


@dataclass
class StrategyConfig:
    """策略配置

    Attributes:
        name: 策略名称
        version: 版本号
        description: 策略描述
        screening: 筛选条件列表
        ranking: 权重配置
        intraday: 分钟级配置（可选）
        output: 输出配置
        backtest: 回测配置（可选）
    """
    name: str
    version: str = "1.0.0"
    description: str = ""
    screening: Dict[str, Any] = field(default_factory=dict)
    ranking: Dict[str, Any] = field(default_factory=dict)
    intraday: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    backtest: BacktestConfig = None

    def __post_init__(self):
        if self.backtest is None:
            self.backtest = BacktestConfig()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyConfig":
        """从字典创建策略配置"""
        backtest_data = data.get("backtest", {})
        backtest_config = BacktestConfig.from_dict(backtest_data) if backtest_data else BacktestConfig()

        return cls(
            name=data["name"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            screening=data.get("screening", {}),
            ranking=data.get("ranking", {}),
            intraday=data.get("intraday", {}),
            output=data.get("output", {}),
            backtest=backtest_config,
        )


@dataclass
class ScreeningCondition:
    """筛选条件

    Attributes:
        expression: 表达式字符串，如 "pe < 50"
        column: 涉及的列名
    """
    expression: str
    column: str

    @classmethod
    def from_string(cls, expr: str) -> "ScreeningCondition":
        """从字符串解析筛选条件"""
        import re
        # 提取列名（简单的变量名匹配）
        match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*[<>=!]+', expr)
        if match:
            column = match.group(1)
        else:
            column = ""
        return cls(expression=expr, column=column)


@dataclass
class BonusCondition:
    """加分条件

    Attributes:
        condition: 条件表达式字符串，如 "volume_ratio < 0.8"
        weight: 加分权重
        description: 条件描述
    """
    condition: str
    weight: float
    description: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BonusCondition":
        """从字典创建加分条件"""
        return cls(
            condition=data["condition"],
            weight=float(data["weight"]),
            description=data.get("description", "")
        )


@dataclass
class BacktestEntryConfig:
    """回测买入配置

    Attributes:
        price: 买入价格类型 (open_today/open_next)
        timing: 买入时机 (immediate/close)
    """
    price: str = "open_next"  # open_today=当天开盘, open_next=次日开盘
    timing: str = "immediate"  # immediate=立即, close=收盘

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BacktestEntryConfig":
        if isinstance(data, str):
            # 简单格式: "open_next" 或 "open_today"
            return cls(price=data)
        return cls(
            price=data.get("price", "open_next"),
            timing=data.get("timing", "immediate"),
        )


@dataclass
class BacktestExitRule:
    """回测卖出规则

    Attributes:
        rule: 规则类型 (timed/time_of_day/close)
        hold_days: 持有天数
        time: 触发时间 (如 "10:00")
        price: 卖出价格 (open/close)
    """
    rule: str = "timed"  # timed=持有N天后, time_of_day=指定时间, close=收盘
    hold_days: int = 1  # 持有N个交易日
    time: str = "10:00"  # 触发时间
    price: str = "close"  # 卖出价格

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BacktestExitRule":
        if isinstance(data, str):
            # 简单格式: "10:00" 表示 time_of_day 规则
            return cls(rule="time_of_day", time=data)
        return cls(
            rule=data.get("rule", "timed"),
            hold_days=data.get("hold_days", 1),
            time=data.get("time", "10:00"),
            price=data.get("price", "close"),
        )


@dataclass
class BacktestConfig:
    """回测配置

    Attributes:
        entry: 买入配置
        exit: 卖出规则列表
        capital: 初始资金
        fee: 手续费率
        intraday_data: 是否使用分钟数据
    """
    entry: BacktestEntryConfig = None
    exit: List[BacktestExitRule] = None
    capital: float = 1000000.0
    fee: float = 0.0003
    intraday_data: bool = False  # 是否使用分钟级数据

    def __post_init__(self):
        if self.entry is None:
            self.entry = BacktestEntryConfig()
        if self.exit is None:
            self.exit = [BacktestExitRule(rule="close")]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BacktestConfig":
        entry_data = data.get("entry", {})
        exit_data = data.get("exit", [])

        # 解析 exit 规则
        exit_rules = []
        if isinstance(exit_data, list):
            for rule in exit_data:
                exit_rules.append(BacktestExitRule.from_dict(rule))
        elif isinstance(exit_data, dict):
            exit_rules.append(BacktestExitRule.from_dict(exit_data))

        return cls(
            entry=BacktestEntryConfig.from_dict(entry_data) if entry_data else BacktestEntryConfig(),
            exit=exit_rules,
            capital=data.get("capital", 1000000.0),
            fee=data.get("fee", 0.0003),
            intraday_data=data.get("intraday_data", False),
        )
