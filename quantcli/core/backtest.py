"""回测模块 - 基于 Backtrader

功能:
1. 回测引擎 (BacktestEngine)
2. 策略基类 (Strategy)
3. 回测结果 (BacktestResult)

Usage:
    >>> from quantcli.core import BacktestEngine, Strategy, BacktestConfig
    >>> from quantcli.core.data import DataManager
    >>> config = BacktestConfig(initial_capital=1000000, fee=0.0003)
    >>> engine = BacktestEngine(dm, config)
    >>> engine.add_data("600519", df)
    >>> result = engine.run(DualMAStrategy)
"""

import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Type, Union
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import numpy as np

import backtrader as bt
from backtrader import Strategy as BtStrategy

from ..utils import get_logger, parse_date, format_date
from ..datasources import create_datasource

logger = get_logger(__name__)


# =============================================================================
# 配置类
# =============================================================================

@dataclass
class BacktestConfig:
    """回测配置"""
    initial_capital: float = 1000000.0  # 初始资金
    fee: float = 0.0003                  # 手续费率
    slippage: float = 0.0005             # 滑点
    benchmark: str = "000300.SH"         # 基准指数
    start_date: Optional[Any] = None     # 开始日期
    end_date: Optional[Any] = None       # 结束日期
    timezone: str = "Asia/Shanghai"      # 时区


@dataclass
class Trade:
    """交易记录"""
    date: Any
    symbol: str
    side: str  # "buy" / "sell"
    price: float
    quantity: int
    fee: float
    pnl: Optional[float] = None


@dataclass
class BacktestResult:
    """回测结果

    Attributes:
        total_return: 总收益率
        annual_return: 年化收益率
        max_drawdown: 最大回撤
        sharpe: 夏普比率
        sortino: 索提诺比率
        win_rate: 胜率
        profit_factor: 盈亏比
        total_trades: 总交易次数
        trades: 交易记录 DataFrame
        equity_curve: 资金曲线 DataFrame
    """
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    trades: pd.DataFrame = None
    equity_curve: pd.DataFrame = None
    benchmark_curve: pd.DataFrame = None

    def __post_init__(self):
        if self.trades is None:
            self.trades = pd.DataFrame()
        if self.equity_curve is None:
            self.equity_curve = pd.DataFrame()

    def to_dict(self) -> Dict:
        return {
            "total_return": self.total_return,
            "annual_return": self.annual_return,
            "max_drawdown": self.max_drawdown,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
        }


# =============================================================================
# 数据源适配器
# =============================================================================

class PandasData(bt.feeds.PandasData):
    """Pandas 数据源适配器 - 将 DataFrame 转换为 Backtrader 格式"""

    params = (
        ("datetime", None),
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("close", "close"),
        ("volume", "volume"),
        ("openinterest", -1),
    )


class MultiData(bt.feeds.PandasData):
    """多标的数据源"""

    params = (
        ("datetime", None),
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("close", "close"),
        ("volume", "volume"),
    )


# =============================================================================
# 策略基类
# =============================================================================

class Strategy(BtStrategy):
    """策略基类 - 继承 Backtrader Strategy

    子类示例:
        >>> class DualMA(Strategy):
        >>>     name = "双均线策略"
        >>>     params = {"fast": 5, "slow": 20}
        >>>
        >>>     def __init__(self):
        >>>         super().__init__()
        >>>         self.ma_fast = bt.indicators.SMA(self.data.close, period=self.params.fast)
        >>>         self.ma_slow = bt.indicators.SMA(self.data.close, period=self.params.slow)
        >>>
        >>>     def next(self):
        >>>         if self.ma_fast[0] > self.ma_slow[0] and self.ma_fast[-1] <= self.ma_slow[-1]:
        >>>             self.buy()
        >>>         elif self.ma_fast[0] < self.ma_slow[0] and self.ma_fast[-1] >= self.ma_slow[-1]:
        >>>             self.sell()
    """

    name = "BaseStrategy"
    params = {}

    def __init__(self):
        super().__init__()
        # 订单记录
        self.order = None
        self.trade_log = []

        # 交易统计
        self.wins = 0
        self.losses = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0

    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.trade_log.append({
                    "date": self.datas[0].datetime.date(0),
                    "symbol": self.datas[0]._name,
                    "side": "buy",
                    "price": order.executed.price,
                    "quantity": order.executed.size,
                    "fee": order.executed.comm,
                })
            else:
                pnl = (order.executed.price - order.orders[0].created.price) * order.executed.size if len(self) > 1 else 0
                self.trade_log.append({
                    "date": self.datas[0].datetime.date(0),
                    "symbol": self.datas[0]._name,
                    "side": "sell",
                    "price": order.executed.price,
                    "quantity": order.executed.size,
                    "fee": order.executed.comm,
                    "pnl": pnl,
                })

                # 更新统计
                if pnl > 0:
                    self.wins += 1
                    self.gross_profit += pnl
                else:
                    self.losses += 1
                    self.gross_loss += abs(pnl)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            logger.warning(f"Order rejected: {order.status}")

        self.order = None

    def log(self, txt, dt=None):
        """日志输出"""
        dt = dt or self.datas[0].datetime.date(0)
        logger.info(f"{dt}: {txt}")

    def notify_trade(self, trade):
        """交易完成通知"""
        if trade.isclosed:
            logger.info(f"Trade: {trade.getdataname()} - PnL: {trade.pnl:.2f}")


# =============================================================================
# 回测引擎
# =============================================================================

class BacktestEngine:
    """回测引擎 - 封装 Cerebro

    Usage:
        >>> engine = BacktestEngine(dm, config)
        >>> engine.add_data("600519", df)  # df 包含 open/high/low/close/volume
        >>> result = engine.run(DualMAStrategy)
    """

    def __init__(
        self,
        config: Optional[BacktestConfig] = None
    ):
        """初始化回测引擎

        Args:
            config: 回测配置
        """
        self.config = config or BacktestConfig()
        self.cerebro = bt.Cerebro()

        # 设置资金
        self.cerebro.broker.setcash(self.config.initial_capital)

        # 设置手续费
        self.cerebro.broker.setcommission(commission=self.config.fee)

        # 设置滑点
        self.cerebro.broker.set_slippage_perc(self.config.slippage)

        # 分析器
        self.cerebro.addanalyzer(bt.analyzers.DrawDown)
        self.cerebro.addanalyzer(bt.analyzers.SharpeRatio, riskfreerate=0.02, annualize=True)
        self.cerebro.addanalyzer(bt.analyzers.Returns)
        self.cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")

        # 交易记录
        self.cerebro.addobserver(bt.observers.Trades)

        # 数据源
        self._data_feeds: Dict[str, Any] = {}

    def add_data(
        self,
        symbol: str,
        df: pd.DataFrame,
        fromdate: Optional[Any] = None,
        todate: Optional[Any] = None
    ):
        """添加数据源

        Args:
            symbol: 股票代码
            df: DataFrame (必须包含: date, open, high, low, close, volume)
            fromdate: 开始日期
            todate: 结束日期
        """
        # 确保日期列
        df = df.copy()
        if "date" in df.columns:
            df["datetime"] = pd.to_datetime(df["date"])
            df.set_index("datetime", inplace=True)
        elif not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # 过滤日期
        if fromdate:
            df = df[df.index >= parse_date(fromdate)]
        if todate:
            df = df[df.index <= parse_date(todate)]

        # 创建数据源
        data = PandasData(dataname=df, datetime=None)
        data._name = symbol

        self.cerebro.adddata(data)
        self._data_feeds[symbol] = data

        logger.info(f"Added data: {symbol} ({len(df)} rows)")

    def add_data_from_datasource(
        self,
        symbol: str,
        dm: Any,
        start_date: Any,
        end_date: Any
    ):
        """从 DataManager 添加数据

        Args:
            symbol: 股票代码
            dm: DataManager 实例
            start_date: 开始日期
            end_date: 结束日期
        """
        df = dm.get_daily(symbol, start_date, end_date)
        if not df.empty:
            self.add_data(symbol, df, start_date, end_date)

    def run(
        self,
        strategy_cls: Type[Strategy],
        **strategy_params
    ) -> BacktestResult:
        """运行回测

        Args:
            strategy_cls: 策略类 (继承 Strategy)
            **strategy_params: 策略参数

        Returns:
            BacktestResult: 回测结果
        """
        # 添加策略
        self.cerebro.addstrategy(strategy_cls, **strategy_params)

        # 设置分析器
        if not self.cerebro.analyzers:
            self.cerebro.addanalyzer(bt.analyzers.DrawDown)
            self.cerebro.addanalyzer(bt.analyzers.SharpeRatio)

        # 运行回测
        results = self.cerebro.run()

        # 获取策略结果
        strategy_result = results[0]

        # 构建结果
        backtest_result = self._build_result(strategy_result)

        logger.info(f"Backtest finished: Return={backtest_result.total_return:.2%}, "
                    f"MaxDD={backtest_result.max_drawdown:.2%}, "
                    f"Sharpe={backtest_result.sharpe:.2f}")

        return backtest_result

    def _build_result(self, strategy_result: Strategy) -> BacktestResult:
        """构建回测结果"""
        # 获取分析器数据
        analyzers = strategy_result.analyzers

        # 最大回撤
        dd = analyzers.drawdown.get_analysis()
        max_drawdown = dd.get("max", {}).get("drawdown", 0) / 100 if dd else 0

        # 夏普比率
        sharpe = analyzers.sharperatio.get_analysis()
        sharpe_ratio = sharpe.get("sharperatio", 0)

        # 时间收益
        time_returns = analyzers.time_return.get_analysis()
        returns_series = pd.Series(time_returns)

        # 计算收益指标
        total_return = (1 + returns_series).prod() - 1 if len(returns_series) > 0 else 0

        # 年化收益率 (假设252交易日)
        n_years = len(returns_series) / 252
        annual_return = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0

        # 索提诺比率
        downside_returns = returns_series[returns_series < 0]
        downside_std = downside_returns.std() if len(downside_returns) > 0 else 0
        sortino = (annual_return - 0.02) / downside_std if downside_std > 0 else 0

        # 交易统计
        trades_df = pd.DataFrame(strategy_result.trade_log)
        if not trades_df.empty:
            total_trades = len(trades_df)
            wins = (trades_df.get("pnl", 0) > 0).sum() if "pnl" in trades_df.columns else 0
            win_rate = wins / total_trades if total_trades > 0 else 0

            profit = trades_df[trades_df.get("pnl", 0) > 0]["pnl"].sum() if "pnl" in trades_df.columns else 0
            loss = abs(trades_df[trades_df.get("pnl", 0) < 0]["pnl"].sum()) if "pnl" in trades_df.columns else 1
            profit_factor = profit / loss if loss > 0 else 0
        else:
            total_trades = 0
            win_rate = 0
            profit_factor = 0

        # 资金曲线
        equity_curve = self._get_equity_curve(strategy_result)

        return BacktestResult(
            total_return=total_return,
            annual_return=annual_return,
            max_drawdown=max_drawdown,
            sharpe=sharpe_ratio,
            sortino=sortino,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            trades=trades_df,
            equity_curve=equity_curve,
        )

    def _get_equity_curve(self, strategy_result: Strategy) -> pd.DataFrame:
        """获取资金曲线"""
        try:
            analyzer = strategy_result.analyzers.timers
            if hasattr(analyzer, "get_analysis"):
                data = analyzer.get_analysis()
                if data:
                    dates = [datetime.fromtimestamp(k / 1000) for k in data.keys()]
                    values = list(data.values())
                    return pd.DataFrame({
                        "date": dates,
                        "equity": values
                    }).set_index("date")
        except Exception as e:
            logger.debug(f"Could not get equity curve: {e}")

        # 备选方案: 使用 broker value
        try:
            values = []
            dates = []
            for i, data in enumerate(strategy_result.datas[0]):
                dates.append(strategy_result.datas[0].datetime.date(i))
                values.append(strategy_result.broker.getvalue())

            return pd.DataFrame({
                "date": dates,
                "equity": values
            }).set_index("date")
        except:
            pass

        return pd.DataFrame()

    def plot(self, **kwargs):
        """绘图

        Args:
            **kwargs: backtrader plot 参数
        """
        self.cerebro.plot(**kwargs)


# =============================================================================
# 便捷函数
# =============================================================================

def quick_backtest(
    symbol: str,
    df: pd.DataFrame,
    strategy_cls: Type[Strategy],
    initial_capital: float = 1000000.0,
    fee: float = 0.0003,
    **strategy_params
) -> BacktestResult:
    """快速回测 - 单行代码运行回测

    Args:
        symbol: 股票代码
        df: 数据 DataFrame
        strategy_cls: 策略类
        initial_capital: 初始资金
        fee: 手续费率
        **strategy_params: 策略参数

    Returns:
        BacktestResult
    """
    config = BacktestConfig(initial_capital=initial_capital, fee=fee)
    engine = BacktestEngine(config)
    engine.add_data(symbol, df)
    return engine.run(strategy_cls, **strategy_params)


def run_from_dm(
    dm: Any,
    symbol: str,
    strategy_cls: Type[Strategy],
    start_date: Any,
    end_date: Any,
    initial_capital: float = 1000000.0,
    fee: float = 0.0003,
    **strategy_params
) -> BacktestResult:
    """从 DataManager 运行回测

    Args:
        dm: DataManager 实例
        symbol: 股票代码
        strategy_cls: 策略类
        start_date: 开始日期
        end_date: 结束日期
        initial_capital: 初始资金
        fee: 手续费率
        **strategy_params: 策略参数
    """
    config = BacktestConfig(
        initial_capital=initial_capital,
        fee=fee,
        start_date=start_date,
        end_date=end_date
    )
    engine = BacktestEngine(config)
    engine.add_data_from_datasource(symbol, dm, start_date, end_date)
    return engine.run(strategy_cls, **strategy_params)


# =============================================================================
# YAML 策略回测引擎
# =============================================================================

class YAMLBacktestEngine:
    """基于 YAML 策略配置的回测引擎

    功能:
    1. 加载 YAML 策略文件（含筛选条件和回测规则）
    2. 执行多阶段筛选获取候选股票
    3. 按规则执行买入/卖出
    4. 生成回测报告

    Usage:
        >>> from quantcli.core.backtest import YAMLBacktestEngine
        >>> from quantcli.datasources import create_datasource
        >>> engine = YAMLBacktestEngine(create_datasource("mixed"))
        >>> engine.load_strategy("examples/strategies/my_strategy.yaml")
        >>> result = engine.run()
    """

    def __init__(
        self,
        datasource,
        config: Optional[BacktestConfig] = None
    ):
        """初始化引擎

        Args:
            datasource: 数据源实例 (需实现 get_daily/get_intraday)
            config: 回测配置
        """
        self.datasource = datasource
        self.config = config or BacktestConfig()
        self.strategy_config = None
        self.positions: Dict[str, Dict] = {}  # 当前持仓
        self.trades: List[Dict] = []  # 交易记录
        self.equity_curve: List[Dict] = []  # 资金曲线

    def load_strategy(self, path: str) -> "YAMLBacktestEngine":
        """加载策略配置"""
        from quantcli.factors.loader import load_strategy as yaml_load
        self.strategy_config = yaml_load(path)
        logger.info(f"Loaded strategy: {self.strategy_config.name}")
        return self

    def set_strategy_config(self, config: "StrategyConfig") -> "YAMLBacktestEngine":
        """直接设置策略配置"""
        self.strategy_config = config
        return self

    def run(
        self,
        start_date: Any,
        end_date: Any = None,
        capital: Optional[float] = None
    ) -> BacktestResult:
        """运行回测

        Args:
            start_date: 开始日期
            end_date: 结束日期 (默认到今天)
            capital: 初始资金 (覆盖策略配置)

        Returns:
            BacktestResult: 回测结果
        """
        if self.strategy_config is None:
            raise ValueError("Strategy not loaded. Use load_strategy() first.")

        # 1. 执行筛选获取候选股票
        candidates = self._run_screening(start_date, end_date)

        if not candidates:
            logger.warning("No candidates found from screening")
            return BacktestResult()

        logger.info(f"Screening found {len(candidates)} candidates")

        # 2. 获取数据并执行回测
        self._run_backtest_loop(candidates, start_date, end_date, capital or self.config.initial_capital)

        # 3. 生成结果
        return self._build_result()

    def _run_screening(
        self,
        start_date: Any,
        end_date: Any
    ) -> List[str]:
        """执行筛选流程获取候选股票列表"""
        from quantcli.factors.screening import ScreeningEvaluator

        # 如果指定了目标股票，直接返回
        if hasattr(self, 'target_symbol') and self.target_symbol:
            return [self.target_symbol]

        # 转换日期
        start_dt = self._parse_date(start_date)
        end_dt = self._parse_date(end_date or date.today())

        # 获取所有股票列表
        stock_list = self.datasource.get_stock_list()
        if stock_list.empty:
            logger.warning("No stock list available")
            return []

        symbols = stock_list['symbol'].tolist()
        candidates = symbols

        # strategy_config.screening 是字典
        screening = self.strategy_config.screening or {}
        fund_conditions = screening.get("fundamental_conditions", [])
        daily_conditions = screening.get("daily_conditions", [])

        # Step 1: 基本面筛选
        if fund_conditions:
            # 获取基本面数据
            fund_data = self.datasource.get_fundamentals(symbols)
            if not fund_data.empty:
                evaluator = ScreeningEvaluator()
                passed = evaluator.evaluate(fund_conditions, fund_data)
                candidates = fund_data.loc[passed, 'symbol'].tolist()
                logger.info(f"After fundamental screening: {len(candidates)} candidates")

        # Step 2: 日线条件筛选
        if candidates and daily_conditions:
            # 获取日线数据
            daily_data = self.datasource.get_multi_daily(candidates, start_dt, end_dt)
            filtered = []
            for symbol, df in daily_data.items():
                if df.empty:
                    continue
                evaluator = ScreeningEvaluator()
                passed = evaluator.evaluate(daily_conditions, df)
                if passed.any():
                    filtered.append(symbol)
            candidates = filtered
            logger.info(f"After daily screening: {len(candidates)} candidates")

        return candidates[:100]  # 限制候选数量

    def _run_backtest_loop(
        self,
        candidates: List[str],
        start_date: Any,
        end_date: Any,
        capital: float
    ):
        """执行回测主循环

        Args:
            candidates: 候选股票列表
            start_date: 开始日期
            end_date: 结束日期
            capital: 初始资金
        """
        from datetime import datetime, timedelta
        from quantcli.parser.formula import Formula

        # 获取交易日历
        trading_days = self.datasource.get_trading_calendar()
        if not trading_days:
            logger.warning("No trading days available")
            return

        # 转换日期
        start_dt = self._parse_date(start_date)
        end_dt = self._parse_date(end_date or date.today())

        # 筛选交易日期范围
        trading_days = [d for d in trading_days if start_dt <= d <= end_dt]

        # 初始化资金
        cash = capital
        self.positions = {}
        self.trades = []
        self.equity_curve = []

        # 回测配置
        bt_config = self.strategy_config.backtest
        entry_price = bt_config.entry.price
        exit_rules = bt_config.exit

        # 遍历每个交易日
        for i, current_date in enumerate(trading_days):
            equity = self._calculate_equity(cash)
            self.equity_curve.append({
                "date": current_date,
                "equity": equity,
                "cash": cash
            })

            # 处理卖出信号
            positions_to_close = self._check_exit_signals(
                current_date, i, trading_days, exit_rules
            )
            for symbol in positions_to_close:
                cash = self._close_position(
                    symbol, current_date, cash, exit_rules
                )

            # 处理买入信号 (只在筛选结果中买入)
            # 注意: 这里简化处理，实际应该根据策略信号买入
            for symbol in candidates[:10]:  # 最多持有10只
                if symbol not in self.positions:
                    price = self._get_price(symbol, current_date, entry_price)
                    if price > 0 and cash >= price * 100:  # 至少买100股
                        self.positions[symbol] = {
                            "entry_date": current_date,
                            "entry_price": price,
                            "quantity": int(cash / price / 10)  # 10% 仓位
                        }
                        cash -= self.positions[symbol]["quantity"] * price * (1 + self.config.fee)
                        self.trades.append({
                            "date": current_date,
                            "symbol": symbol,
                            "side": "buy",
                            "price": price,
                            "quantity": self.positions[symbol]["quantity"],
                            "fee": price * self.positions[symbol]["quantity"] * self.config.fee
                        })
                        break  # 每只候选股票只买一次

    def _check_exit_signals(
        self,
        current_date,
        day_index: int,
        trading_days: List,
        exit_rules: List["BacktestExitRule"]
    ) -> List[str]:
        """检查卖出信号"""
        to_close = []
        for symbol, pos in self.positions.items():
            entry_date = pos["entry_date"]
            hold_days = (current_date - entry_date).days if isinstance(current_date, date) else 0

            for rule in exit_rules:
                if rule.rule == "timed" and hold_days >= rule.hold_days:
                    to_close.append(symbol)
                    break
                elif rule.rule == "close":
                    # 收盘卖出 (每天收盘时检查)
                    to_close.append(symbol)
                    break

        return to_close

    def _close_position(
        self,
        symbol: str,
        current_date: Any,
        cash: float,
        exit_rules: List["BacktestExitRule"]
    ) -> float:
        """平仓并返回剩余资金"""
        if symbol not in self.positions:
            return cash

        pos = self.positions[symbol]
        price = self._get_price(symbol, current_date, "close")

        if price > 0:
            quantity = pos["quantity"]
            fee = price * quantity * self.config.fee
            pnl = (price - pos["entry_price"]) * quantity - fee

            cash += price * quantity - fee
            self.trades.append({
                "date": current_date,
                "symbol": symbol,
                "side": "sell",
                "price": price,
                "quantity": quantity,
                "fee": fee,
                "pnl": pnl,
                "entry_price": pos["entry_price"],
                "hold_days": (current_date - pos["entry_date"]).days if isinstance(current_date, date) else 0
            })

        del self.positions[symbol]
        return cash

    def _get_price(
        self,
        symbol: str,
        date: Any,
        price_type: str
    ) -> float:
        """获取指定日期的价格"""
        try:
            df = self.datasource.get_daily(symbol, date, date)
            if df.empty:
                return 0.0

            if price_type == "open":
                return float(df.iloc[0]["open"])
            elif price_type == "close":
                return float(df.iloc[0]["close"])
            elif price_type == "open_next":
                # 次日开盘价 (查找下一天)
                trading_days = self.datasource.get_trading_calendar()
                if trading_days:
                    try:
                        idx = trading_days.index(self._parse_date(date))
                        if idx + 1 < len(trading_days):
                            next_day = trading_days[idx + 1]
                            df = self.datasource.get_daily(symbol, next_day, next_day)
                            if not df.empty:
                                return float(df.iloc[0]["open"])
                    except ValueError:
                        pass
            return float(df.iloc[0]["close"])
        except Exception as e:
            logger.debug(f"Failed to get price for {symbol}: {e}")
            return 0.0

    def _calculate_equity(self, cash: float) -> float:
        """计算当前权益"""
        from datetime import date as date_type
        total = cash
        for symbol, pos in self.positions.items():
            price = self._get_price(symbol, date_type.today(), "close")
            total += price * pos["quantity"]
        return total

    def _parse_date(self, d: Any) -> "date":
        """解析日期"""
        from datetime import date as date_type
        if isinstance(d, date_type):
            return d
        if isinstance(d, str):
            return date_type.fromisoformat(d)
        return d

    def _build_result(self) -> BacktestResult:
        """构建回测结果"""
        if not self.equity_curve:
            return BacktestResult()

        # 计算收益曲线
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df["date"] = pd.to_datetime(equity_df["date"])
        equity_df = equity_df.set_index("date").sort_index()

        # 计算收益指标
        returns = equity_df["equity"].pct_change().dropna()
        total_return = (equity_df["equity"].iloc[-1] / equity_df["equity"].iloc[0]) - 1

        # 年化收益率
        n_days = len(equity_df)
        n_years = n_days / 252
        annual_return = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0

        # 最大回撤
        cumulative = (1 + returns).cumprod()
        rolling_max = cumulative.cummax()
        drawdown = (cumulative - rolling_max) / rolling_max
        max_drawdown = abs(drawdown.min())

        # 夏普比率
        sharpe = returns.mean() / returns.std() * (252 ** 0.5) if returns.std() > 0 else 0

        # 交易统计
        trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()
        win_rate = 0.0
        profit_factor = 0.0
        total_trades = 0

        if not trades_df.empty and "pnl" in trades_df.columns:
            total_trades = len(trades_df)
            wins = (trades_df["pnl"] > 0).sum()
            win_rate = wins / total_trades if total_trades > 0 else 0

            profits = trades_df[trades_df["pnl"] > 0]["pnl"].sum()
            losses = abs(trades_df[trades_df["pnl"] < 0]["pnl"].sum())
            profit_factor = profits / losses if losses > 0 else 0

        return BacktestResult(
            total_return=total_return,
            annual_return=annual_return,
            max_drawdown=max_drawdown,
            sharpe=sharpe,
            sortino=0.0,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            trades=trades_df,
            equity_curve=equity_df.reset_index(),
        )
