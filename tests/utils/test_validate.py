"""utils/validate.py 单元测试"""

import pytest
import pandas as pd
import numpy as np
from quantcli.utils import (
    check_columns, require_columns, as_numeric, as_datetime,
    ValidationError,
)


class TestCheckColumns:
    """check_columns 测试"""

    def test_check_columns_all_present(self, sample_price_data):
        result = check_columns(sample_price_data, required=["date", "close"])
        assert hasattr(result, 'passed')

    def test_check_columns_missing(self, sample_price_data):
        result = check_columns(sample_price_data, required=["missing_col"])
        assert hasattr(result, 'passed')

    def test_check_columns_partial(self, sample_price_data):
        result = check_columns(sample_price_data, required=["date", "close", "nonexistent"])
        assert hasattr(result, 'passed')


class TestRequireColumns:
    """require_columns 测试"""

    def test_require_columns_success(self, sample_price_data):
        # 不应抛出异常
        require_columns(sample_price_data, ["date", "close"])

    def test_require_columns_failure(self, sample_price_data):
        with pytest.raises(ValidationError):
            require_columns(sample_price_data, ["nonexistent"])


class TestAsNumeric:
    """as_numeric 测试"""

    def test_as_numeric_valid(self):
        df = pd.DataFrame({"a": ["1", "2", "3"]})
        result = as_numeric(df, "a")
        assert result["a"].dtype in [np.int64, np.float64]

    def test_as_numeric_invalid(self):
        df = pd.DataFrame({"a": ["abc", "def"]})
        with pytest.raises(ValueError):
            as_numeric(df, "a")


class TestAsDatetime:
    """as_datetime 测试"""

    def test_as_datetime_valid(self):
        df = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-02"])})
        result = as_datetime(df, "date")
        assert pd.api.types.is_datetime64_any_dtype(result["date"])
