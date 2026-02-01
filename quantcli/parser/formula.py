"""公式解析器 - 将因子表达式解析为可执行的函数

支持语法:
- 字段引用: close, open, high, low, volume, amount, returns
- 数学运算: +, -, *, /, ** (幂)
- 比较运算: >, <, ==, !=, >=, <=
- 逻辑运算: &, |, ~ (与, 或, 非)
- 内置函数: delay, ma, ema, rolling_std, rank, zscore, rsi, etc.

示例:
    formula = Formula("close / delay(close, 20) - 1")
    result = formula.compute(df)
"""

import re
import pandas as pd
from typing import Dict, Any, Callable, List, Optional, Union

from ..utils import get_logger

logger = get_logger(__name__)

# 类型定义
Array = Any


class FormulaError(Exception):
    """公式解析/计算错误"""
    pass


# =============================================================================
# 内置函数定义
# =============================================================================

def _validate_numeric(*args):
    """验证参数是否为数值类型"""
    for arg in args:
        if not isinstance(arg, (int, float)):
            raise FormulaError(f"Expected numeric value, got {type(arg)}")


def delay(x: Array, n: int) -> Array:
    """延时函数 - 获取前n个周期的值"""
    return x.shift(n)


def ma(x: Array, n: int, min_periods: Optional[int] = None) -> Array:
    """简单移动平均"""
    min_periods = min_periods or n
    return x.rolling(window=n, min_periods=min_periods).mean()


def ema(x: Array, n: int, adjust: bool = True) -> Array:
    """指数移动平均"""
    return x.ewm(span=n, adjust=adjust).mean()


def wma(x: Array, n: int) -> Array:
    """加权移动平均 (线性权重)"""
    weights = range(1, n + 1)
    return x.rolling(window=n, min_periods=n).apply(
        lambda vals: sum(weights * vals) / sum(weights), raw=True
    )


def rolling_std(x: Array, n: int, min_periods: Optional[int] = None) -> Array:
    """滚动标准差"""
    min_periods = min_periods or n
    return x.rolling(window=n, min_periods=min_periods).std()


def rolling_sum(x: Array, n: int, min_periods: Optional[int] = None) -> Array:
    """滚动求和"""
    min_periods = min_periods or n
    return x.rolling(window=n, min_periods=min_periods).sum()


def rolling_mean(x: Array, n: int, min_periods: Optional[int] = None) -> Array:
    """滚动均值 (同 ma)"""
    return ma(x, n, min_periods)


def rolling_max(x: Array, n: int, min_periods: Optional[int] = None) -> Array:
    """滚动最大值"""
    min_periods = min_periods or n
    return x.rolling(window=n, min_periods=n).max()


def rolling_min(x: Array, n: int, min_periods: Optional[int] = None) -> Array:
    """滚动最小值"""
    min_periods = min_periods or n
    return x.rolling(window=n, min_periods=n).min()


def ts_argmax(x: Array, n: int) -> Array:
    """滚动窗口内最大值的位置 (0-indexed from n-1 down to 0)"""
    import pandas as pd
    # 使用 rolling apply 计算 argmax
    def argmax_func(window):
        if pd.isna(window).all():
            return float('nan')
        return len(window) - 1 - window[::-1].argmax()
    return x.rolling(window=n, min_periods=n).apply(argmax_func, raw=True)


def ts_argmin(x: Array, n: int) -> Array:
    """滚动窗口内最小值的位置 (0-indexed from n-1 down to 0)"""
    import pandas as pd
    def argmin_func(window):
        if pd.isna(window).all():
            return float('nan')
        return len(window) - 1 - window[::-1].argmin()
    return x.rolling(window=n, min_periods=n).apply(argmin_func, raw=True)


def rank(x: Array) -> Array:
    """横截面排序 (0-1 归一化)"""
    return x.rank(pct=True)


def ts_rank(x: Array, n: int) -> Array:
    """滚动窗口内的横截面排名 (0-1 归一化)"""
    return x.rolling(window=n, min_periods=n).apply(lambda v: pd.Series(v).rank(pct=True).iloc[-1], raw=True)


def ts_ave(x: Array, n: int) -> Array:
    """滚动均值 (同 ma)"""
    return ma(x, n)


def ts_sum(x: Array, n: int) -> Array:
    """滚动求和"""
    return rolling_sum(x, n)


def ts_min(x: Array, n: int) -> Array:
    """滚动最小值 (同 rolling_min)"""
    return rolling_min(x, n)


def ts_max(x: Array, n: int) -> Array:
    """滚动最大值 (同 rolling_max)"""
    return rolling_max(x, n)


def ts_decayexp(x: Array, n: float) -> Array:
    """指数衰减加权"""
    import numpy as np
    weights = np.exp(np.linspace(0, -1, len(x)))
    return x.ewm(span=n, adjust=False).mean()


def signed_power(x: Array, n: float) -> Array:
    """符号幂函数: 保留符号，计算绝对值的n次方"""
    import numpy as np
    return np.sign(x) * np.abs(x) ** n


def sma(x: Array, n: int) -> Array:
    """简单移动平均 (同 ma)"""
    return ma(x, n)


def zscore(x: Array, n: Optional[int] = None) -> Array:
    """标准化 (Z-Score)"""
    if n is None:
        return (x - x.mean()) / x.std()
    return (x - ma(x, n)) / rolling_std(x, n)


def quantile(x: Array, q: float) -> Array:
    """分位数转换"""
    return x.rank(pct=True) * q


def correlation(x: Array, y: Array, n: int) -> Array:
    """滚动相关性"""
    return x.rolling(window=n).corr(y)


def covariance(x: Array, y: Array, n: int) -> Array:
    """滚动协方差"""
    return x.rolling(window=n).cov(y)


def regression(x: Array, y: Array, n: int) -> tuple:
    """滚动线性回归 (OLS)"""
    import numpy as np

    result_alpha = x.rolling(window=n).corr(y) * 0
    result_beta = x.rolling(window=n).corr(y) * 0

    for i in range(n - 1, len(x)):
        window_x = x.iloc[i - n + 1:i + 1].values
        window_y = y.iloc[i - n + 1:i + 1].values
        alpha, beta = np.linalg.lstsq(
            np.column_stack([np.ones(n), window_x]),
            window_y,
            rcond=None
        )[0]
        result_alpha.iloc[i] = alpha
        result_beta.iloc[i] = beta

    return result_alpha, result_beta


# =============================================================================
# 技术指标
# =============================================================================

def rsi(x: Array, n: int = 14) -> Array:
    """相对强弱指数 (RSI)"""
    delta = x.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)

    avg_gain = gain.ewm(com=n - 1, min_periods=n).mean()
    avg_loss = loss.ewm(com=n - 1, min_periods=n).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(x: Array, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """MACD 指标"""
    ema_fast = ema(x, fast)
    ema_slow = ema(x, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line, macd_line - signal_line


def bollinger_bands(x: Array, n: int = 20, k: float = 2) -> tuple:
    """布林带"""
    middle = ma(x, n)
    std = rolling_std(x, n)
    return middle + k * std, middle, middle - k * std


def stoch(high: Array, low: Array, close: Array, n: int = 14) -> tuple:
    """随机指标 (Stochastic)"""
    lowest_low = low.rolling(window=n, min_periods=n).min()
    highest_high = high.rolling(window=n, min_periods=n).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    return k, ma(k, 3)


def atr(high: Array, low: Array, close: Array, n: int = 14) -> Array:
    """真实波幅 (ATR)"""
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = tr1.combine(tr2, max).combine(tr3, max)
    return ma(tr, n)


# =============================================================================
# 事件函数
# =============================================================================

def cross_up(a: Array, b: Array) -> Array:
    """金叉 - a 上穿 b"""
    return (a > b) & (a.shift(1) <= b.shift(1))


def cross_down(a: Array, b: Array) -> Array:
    """死叉 - a 下穿 b"""
    return (a < b) & (a.shift(1) >= b.shift(1))


def breakout_high(x: Array, n: int) -> Array:
    """突破n日高点"""
    return x == rolling_max(x, n)


def breakout_low(x: Array, n: int) -> Array:
    """突破n日低点"""
    return x == rolling_min(x, n)


# =============================================================================
# 条件函数
# =============================================================================

def where(condition: Array, value_true: Any, value_false: Any) -> Array:
    """条件赋值"""
    import numpy as np
    result = np.where(condition, value_true, value_false)
    # 如果结果是 numpy array，转回 pandas Series 以支持链式调用
    if isinstance(result, np.ndarray):
        if hasattr(condition, 'index'):
            return pd.Series(result, index=condition.index)
        return pd.Series(result)
    return result


def if_(*args) -> Array:
    """嵌套条件函数"""
    if len(args) < 3:
        raise FormulaError("if_ requires at least 3 arguments")
    if len(args) % 2 == 0:
        raise FormulaError("if_ requires odd number of arguments")

    n = len(args)
    result = args[-1]

    for i in range(n - 2, -1, -2):
        result = where(args[i], args[i + 1], result)

    return result


def abs_val(x: Array) -> Array:
    """绝对值"""
    return x.abs()


def sign(x: Array) -> Array:
    """符号函数：返回 -1 (负), 0 (零), 1 (正)"""
    return (x > 0).astype(int) - (x < 0).astype(int)


def clamp(x: Array, min_val: float, max_val: float) -> Array:
    """限制值范围"""
    return x.clip(lower=min_val, upper=max_val)


def max_val(x: Array) -> Array:
    """返回序列最大值（单值Series）"""
    return pd.Series([x.max()], index=[x.index[-1]])


# =============================================================================
# 内置函数映射
# =============================================================================

BUILTIN_FUNCTIONS: Dict[str, Callable] = {
    # 延时和移动平均
    "delay": delay, "ma": ma, "ema": ema, "wma": wma,

    # 滚动统计
    "rolling_std": rolling_std, "rolling_sum": rolling_sum,
    "rolling_mean": rolling_mean, "rolling_max": rolling_max, "rolling_min": rolling_min,

    # 标准化和排名
    "rank": rank, "zscore": zscore, "quantile": quantile,

    # 相关性
    "correlation": correlation, "covariance": covariance, "regression": regression,

    # 技术指标
    "rsi": rsi, "macd": macd,
    "bollinger_upper": lambda x, n=20, k=2: bollinger_bands(x, n, k)[0],
    "bollinger_lower": lambda x, n=20, k=2: bollinger_bands(x, n, k)[2],
    "stoch_k": lambda h, l, c, n=14: stoch(h, l, c, n)[0],
    "stoch_d": lambda h, l, c, n=14: stoch(h, l, c, n)[1],
    "atr": atr,

    # 事件
    "cross_up": cross_up, "cross_down": cross_down,
    "breakout_high": breakout_high, "breakout_low": breakout_low,

    # 条件
    "where": where, "if_": if_,

    # 数学函数
    "abs": abs_val, "sign": sign, "clamp": clamp,
    "max": max_val,
}


# =============================================================================
# 公式解析器
# =============================================================================

class Formula:
    """因子公式解析器"""

    def __init__(self, expression: str, name: str = "anonymous"):
        self.expression = expression.strip()
        self.name = name
        self._compiled: Optional[Callable] = None
        self._parse()

    def _parse(self):
        """解析表达式为可执行函数"""
        try:
            code = self._compile_to_code()
            self._compiled = compile(code, "<formula>", "eval")
        except SyntaxError as e:
            raise FormulaError(f"Syntax error in formula: {e}")

    def _compile_to_code(self) -> str:
        """将公式表达式编译为 Python 代码"""
        expr = self.expression

        # 处理 let 变量定义
        var_defs = []
        while expr.startswith("let "):
            match = re.match(r'let\s+(\w+)\s*=\s*(.+?)(?:\s+let\s|\s*$)', expr, re.DOTALL)
            if not match:
                raise FormulaError("Invalid let statement")
            var_name = match.group(1)
            var_expr = match.group(2).strip()
            var_defs.append((var_name, var_expr))
            expr = expr[match.end():].strip()

        # 转换运算符 (管道操作)
        if "|> " in expr:
            parts = [p.strip() for p in expr.split("|>")]
            result = parts[0]
            for part in parts[1:]:
                match = re.match(r'(\w+)\s*\((.*)\)', part.strip())
                if match:
                    func_name = match.group(1)
                    args = match.group(2).replace(".", result)
                    result = f"{func_name}({args})"
            expr = result

        return expr

    def _create_context(self, data: Dict[str, Array]) -> Dict[str, Any]:
        """创建计算上下文"""
        from .constants import BUILTIN_FUNCTIONS
        # 导入所有内置函数
        from .formula import (
            ma, ema, delay, zscore, rank, where, if_,
            abs_val, sign, clamp, rolling_std, rolling_sum,
            correlation, cross_up, cross_down,
            rolling_max, rolling_min, rolling_mean,
            ts_argmax, ts_argmin,
            ts_rank, ts_ave, ts_sum, ts_min, ts_max,
            ts_decayexp, signed_power, sma,
        )
        ctx = {
            'ma': ma, 'ema': ema, 'delay': delay, 'zscore': zscore,
            'rank': rank, 'where': where, 'if': if_,
            'abs': abs_val, 'sign': sign, 'clamp': clamp, 'max': max_val,
            'rolling_std': rolling_std, 'rolling_sum': rolling_sum,
            'correlation': correlation, 'cross_up': cross_up,
            'cross_down': cross_down,
            'rolling_max': rolling_max, 'rolling_min': rolling_min,
            'rolling_mean': rolling_mean,
            'ts_argmax': ts_argmax, 'ts_argmin': ts_argmin,
            'ts_rank': ts_rank, 'ts_ave': ts_ave, 'ts_sum': ts_sum,
            'ts_min': ts_min, 'ts_max': ts_max,
            'ts_decayexp': ts_decayexp, 'signed_power': signed_power,
            'sma': sma,
        }
        ctx.update(data)
        return ctx

    def compute(self, df, params: Optional[Dict[str, Any]] = None,
                context: Optional[Dict[str, Any]] = None) -> Array:
        """计算公式结果"""
        if self._compiled is None:
            raise FormulaError("Formula not compiled")

        # 从 DataFrame 提取数据
        data = {col: df[col] for col in df.columns} if hasattr(df, "columns") else dict(df)

        ctx = self._create_context(data)
        if context:
            ctx.update(context)
        if params:
            ctx["params"] = params

        try:
            return eval(self._compiled, {"__builtins__": {}}, ctx)
        except Exception as e:
            raise FormulaError(f"Evaluation error: {e}")

    def __repr__(self) -> str:
        return f"Formula({self.name!r})"


def compute_factor(expression: str, df, params: Optional[Dict[str, Any]] = None) -> Array:
    """便捷函数: 计算单个因子"""
    return Formula(expression).compute(df, params=params)


def batch_compute(expressions: Dict[str, str], df) -> Dict[str, Array]:
    """批量计算多个因子"""
    results = {}
    for name, expr in expressions.items():
        try:
            results[name] = compute_factor(expr, df)
        except FormulaError as e:
            raise FormulaError(f"Failed to compute factor '{name}': {e}")
    return results
