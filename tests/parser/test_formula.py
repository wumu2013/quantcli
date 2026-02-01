"""parser/formula.py 单元测试"""

import pytest
import pandas as pd
import numpy as np
from quantcli.parser import (
    Formula, FormulaError, compute_factor,
    delay, ma, ema, wma, rolling_std, rolling_sum,
    rank, zscore, quantile,
    rsi, macd, bollinger_bands, atr,
    cross_up, cross_down,
    abs_val, sign, clamp,
)


class TestFormulaBasic:
    """Formula 基础测试"""

    def test_formula_simple_expression(self, sample_factor_df):
        formula = Formula("close")
        result = formula.compute(sample_factor_df)
        assert len(result) == len(sample_factor_df)

    def test_formula_arithmetic(self, sample_factor_df):
        formula = Formula("close * 2")
        result = formula.compute(sample_factor_df)
        expected = sample_factor_df["close"] * 2
        np.testing.assert_array_almost_equal(result.values, expected.values)

    def test_formula_addition(self, sample_factor_df):
        formula = Formula("close + volume")
        result = formula.compute(sample_factor_df)
        expected = sample_factor_df["close"] + sample_factor_df["volume"]
        np.testing.assert_array_almost_equal(result.values, expected.values)

    def test_formula_invalid_expression(self):
        with pytest.raises(FormulaError):
            Formula("invalid syntax @#$%")

    def test_compute_factor_convenience(self, sample_factor_df):
        result = compute_factor("close / 2", sample_factor_df)
        expected = sample_factor_df["close"] / 2
        np.testing.assert_array_almost_equal(result.values, expected.values)


class TestDelay:
    """delay 函数测试"""

    def test_delay_1(self, sample_factor_df):
        result = delay(sample_factor_df["close"], 1)
        expected = sample_factor_df["close"].shift(1)
        np.testing.assert_array_equal(result.values[1:], expected.values[1:])

    def test_delay_5(self, sample_factor_df):
        result = delay(sample_factor_df["close"], 5)
        assert result.isna().sum() >= 5


class TestMA:
    """ma 函数测试"""

    def test_ma_5(self, sample_factor_df):
        result = ma(sample_factor_df["close"], 5)
        expected = sample_factor_df["close"].rolling(5).mean()
        np.testing.assert_array_almost_equal(result.values, expected.values)

    def test_ma_with_min_periods(self, sample_factor_df):
        result = ma(sample_factor_df["close"], 10, min_periods=3)
        # 应该比正常的 ma 有更多的非空值
        assert result.notna().sum() > 0


class TestEMA:
    """ema 函数测试"""

    def test_ema_basic(self, sample_factor_df):
        result = ema(sample_factor_df["close"], 10)
        expected = sample_factor_df["close"].ewm(span=10).mean()
        np.testing.assert_array_almost_equal(result.values, expected.values)


class TestWMA:
    """wma 函数测试"""

    def test_wma_basic(self, sample_factor_df):
        result = wma(sample_factor_df["close"], 5)
        assert len(result) == len(sample_factor_df)
        # WMA 应该比 SMA 对最新价格更敏感
        assert result.iloc[-1] != ma(sample_factor_df["close"], 5).iloc[-1]


class TestRollingStd:
    """rolling_std 函数测试"""

    def test_rolling_std_5(self, sample_factor_df):
        result = rolling_std(sample_factor_df["close"], 5)
        expected = sample_factor_df["close"].rolling(5).std()
        np.testing.assert_array_almost_equal(result.values, expected.values)


class TestRollingSum:
    """rolling_sum 函数测试"""

    def test_rolling_sum_5(self, sample_factor_df):
        result = rolling_sum(sample_factor_df["close"], 5)
        expected = sample_factor_df["close"].rolling(5).sum()
        np.testing.assert_array_almost_equal(result.values, expected.values)


class TestRank:
    """rank 函数测试"""

    def test_rank_range(self, sample_factor_df):
        result = rank(sample_factor_df["close"])
        assert result.min() >= 0
        assert result.max() <= 1


class TestZscore:
    """zscore 函数测试"""

    def test_zscore_mean(self, sample_factor_df):
        result = zscore(sample_factor_df["close"])
        # 去除 NaN 后均值接近 0
        clean_result = result.dropna()
        assert abs(clean_result.mean()) < 0.1

    def test_zscore_std(self, sample_factor_df):
        result = zscore(sample_factor_df["close"])
        clean_result = result.dropna()
        assert abs(clean_result.std() - 1) < 0.1


class TestQuantile:
    """quantile 函数测试"""

    def test_quantile_range(self, sample_factor_df):
        result = quantile(sample_factor_df["close"], 1)
        assert result.min() >= 0
        assert result.max() <= 1


class TestRSI:
    """rsi 函数测试"""

    def test_rsi_range(self, sample_factor_df):
        result = rsi(sample_factor_df["close"], 14)
        clean = result.dropna()
        assert clean.min() >= 0
        assert clean.max() <= 100

    def test_rsi_values(self, sample_factor_df):
        # 稳定上涨的价格 RSI 应该接近 100
        df = pd.DataFrame({"close": list(range(100, 200))})
        result = rsi(df["close"], 14)
        assert result.iloc[-1] > 90


class TestMACD:
    """macd 函数测试"""

    def test_macd_returns_tuple(self, sample_factor_df):
        result = macd(sample_factor_df["close"])
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_macd_components(self, sample_factor_df):
        macd_line, signal, hist = macd(sample_factor_df["close"])
        assert len(macd_line) == len(sample_factor_df)
        assert len(signal) == len(sample_factor_df)
        assert len(hist) == len(sample_factor_df)


class TestBollingerBands:
    """bollinger_bands 函数测试"""

    def test_bollinger_returns_tuple(self, sample_factor_df):
        result = bollinger_bands(sample_factor_df["close"])
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_bollinger_middle(self, sample_factor_df):
        upper, middle, lower = bollinger_bands(sample_factor_df["close"], n=20)
        # 中轨应该是移动平均
        clean = middle.dropna()
        assert clean.min() > 0


class TestATR:
    """atr 函数测试"""

    def test_atr_positive(self, sample_factor_df):
        result = atr(sample_factor_df["close"], sample_factor_df["close"], sample_factor_df["close"], 14)
        clean = result.dropna()
        assert (clean >= 0).all()


class TestCross:
    """cross_up/cross_down 函数测试"""

    def test_cross_up(self, sample_factor_df):
        slow = ma(sample_factor_df["close"], 10)
        fast = ma(sample_factor_df["close"], 5)
        result = cross_up(fast, slow)
        assert result.dtype == bool

    def test_cross_down(self, sample_factor_df):
        slow = ma(sample_factor_df["close"], 10)
        fast = ma(sample_factor_df["close"], 5)
        result = cross_down(fast, slow)
        assert result.dtype == bool


class TestFormulaComplex:
    """复合公式测试"""

    def test_momentum(self, sample_factor_df):
        """动量因子: (close / delay(close, 20)) - 1"""
        formula = Formula("(close / delay(close, 20)) - 1")
        result = formula.compute(sample_factor_df)
        # 20日前的价格应该存在
        assert result.notna().sum() > 0

    def test_ma_crossover_signal(self, sample_factor_df):
        """均线交叉信号"""
        formula = Formula("cross_up(ma(close, 5), ma(close, 20))")
        result = formula.compute(sample_factor_df)
        assert result.dtype == bool

    def test_rank_and_zscore(self, sample_factor_df):
        """排名和标准化组合"""
        formula = Formula("zscore(rank(close))")
        result = formula.compute(sample_factor_df)
        clean = result.dropna()
        assert abs(clean.mean()) < 0.5


class TestFormulaWithParams:
    """带参数的公式测试"""

    def test_compute_with_params(self, sample_factor_df):
        """测试 compute_factor 时传入参数"""
        result = compute_factor("close", sample_factor_df)
        assert len(result) == len(sample_factor_df)


class TestAbs:
    """abs_val 函数测试"""

    def test_abs_positive(self, sample_factor_df):
        result = abs_val(sample_factor_df["close"])
        assert (result >= 0).all()

    def test_abs_negative_to_positive(self):
        s = pd.Series([-1, -2, -3, 1, 2, 3])
        result = abs_val(s)
        expected = pd.Series([1, 2, 3, 1, 2, 3])
        np.testing.assert_array_equal(result.values, expected.values)

    def test_abs_in_formula(self, sample_factor_df):
        formula = Formula("abs(close - ma(close, 5))")
        result = formula.compute(sample_factor_df)
        # 忽略 NaN 值后检查
        clean = result.dropna()
        assert (clean >= 0).all()


class TestSign:
    """sign 函数测试"""

    def test_sign_positive(self):
        s = pd.Series([1, 2, 3])
        result = sign(s)
        assert (result == 1).all()

    def test_sign_negative(self):
        s = pd.Series([-1, -2, -3])
        result = sign(s)
        assert (result == -1).all()

    def test_sign_zero(self):
        s = pd.Series([0, 0, 0])
        result = sign(s)
        assert (result == 0).all()

    def test_sign_mixed(self):
        s = pd.Series([-1, 0, 1])
        result = sign(s)
        expected = pd.Series([-1, 0, 1])
        np.testing.assert_array_equal(result.values, expected.values)

    def test_sign_in_formula(self, sample_factor_df):
        formula = Formula("sign(close - delay(close, 1))")
        result = formula.compute(sample_factor_df)
        assert result.dtype in [int, float]


class TestClamp:
    """clamp 函数测试"""

    def test_clamp_lower_bound(self):
        s = pd.Series([-5, -2, 0, 2, 5])
        result = clamp(s, -2, 2)
        expected = pd.Series([-2, -2, 0, 2, 2])
        np.testing.assert_array_equal(result.values, expected.values)

    def test_clamp_no_change(self):
        s = pd.Series([0, 1, 2])
        result = clamp(s, -5, 5)
        np.testing.assert_array_equal(result.values, s.values)

    def test_clamp_in_formula(self, sample_factor_df):
        formula = Formula("clamp(zscore(close), -2, 2)")
        result = formula.compute(sample_factor_df)
        clean = result.dropna()
        assert (clean >= -2).all() and (clean <= 2).all()
