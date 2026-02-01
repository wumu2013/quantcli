"""数据验证工具

提供 DataFrame 和数据类型验证功能:
- Schema 验证
- 列检查
- 值范围检查
- 类型检查

Usage:
    >>> from quantcli.utils import validate_schema, check_columns
    >>> validate_schema(df, required=["date", "close"])
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Union, Callable
from dataclasses import dataclass
from enum import Enum

import pandas as pd
import numpy as np


class ValidationError(Exception):
    """验证错误"""
    pass


class ValidationWarning(Exception):
    """验证警告"""
    pass


# =============================================================================
# 验证结果
# =============================================================================

@dataclass
class ValidationResult:
    """验证结果"""
    passed: bool
    errors: List[str]
    warnings: List[str]
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def __bool__(self):
        return self.passed


# =============================================================================
# 列验证
# =============================================================================

def check_columns(
    df: pd.DataFrame,
    required: Optional[List[str]] = None,
    optional: Optional[List[str]] = None,
    forbidden: Optional[List[str]] = None,
    allow_extra: bool = True
) -> ValidationResult:
    """检查 DataFrame 列

    Args:
        df: DataFrame
        required: 必须包含的列
        optional: 可选的列
        forbidden: 不应包含的列
        allow_extra: 是否允许额外列

    Returns:
        ValidationResult
    """
    errors = []
    warnings = []
    columns = set(df.columns)

    required = set(required or [])
    optional = set(optional or [])
    forbidden = set(forbidden or [])

    # 检查必需列
    missing = required - columns
    if missing:
        errors.append(f"Missing required columns: {sorted(missing)}")

    # 检查可选列
    present_optional = optional & columns
    if not present_optional:
        warnings.append(f"No optional columns found from {sorted(optional)}")

    # 检查禁止列
    forbidden_present = forbidden & columns
    if forbidden_present:
        errors.append(f"Forbidden columns found: {sorted(forbidden_present)}")

    # 检查额外列
    extra = columns - required - optional
    if extra and not allow_extra:
        errors.append(f"Extra columns not allowed: {sorted(extra)}")

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def require_columns(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """确保 DataFrame 包含指定列

    Args:
        df: DataFrame
        columns: 必需的列

    Returns:
        DataFrame

    Raises:
        ValidationError: 缺少必需列
    """
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValidationError(f"Missing required columns: {missing}")
    return df


# =============================================================================
# 类型验证
# =============================================================================

def check_dtypes(
    df: pd.DataFrame,
    expected: Dict[str, Union[type, str, tuple]]
) -> ValidationResult:
    """检查列数据类型

    Args:
        df: DataFrame
        expected: {列名: 期望类型}

    Returns:
        ValidationResult
    """
    errors = []
    warnings = []

    for col, expected_type in expected.items():
        if col not in df.columns:
            continue

        actual_dtype = df[col].dtype

        # 解析期望类型
        if isinstance(expected_type, str):
            if expected_type == "numeric":
                is_valid = np.issubdtype(actual_dtype, np.number)
            elif expected_type == "integer":
                is_valid = np.issubdtype(actual_dtype, np.integer)
            elif expected_type == "float":
                is_valid = np.issubdtype(actual_dtype, np.floating)
            elif expected_type == "datetime":
                is_valid = np.issubdtype(actual_dtype, np.datetime64)
            elif expected_type == "string":
                is_valid = np.issubdtype(actual_dtype, np.str_)
            else:
                is_valid = str(actual_dtype) == expected_type
        elif isinstance(expected_type, (type, tuple)):
            is_valid = isinstance(df[col].iloc[0], expected_type) if len(df) > 0 else False
        else:
            is_valid = False

        if not is_valid:
            errors.append(
                f"Column '{col}': expected {expected_type}, got {actual_dtype}"
            )

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=[]
    )


def as_numeric(
    df: pd.DataFrame,
    columns: List[str],
    errors: str = "raise"
) -> pd.DataFrame:
    """将列转换为数值类型

    Args:
        df: DataFrame
        columns: 要转换的列
        errors: 处理方式 ('raise', 'coerce', 'ignore')

    Returns:
        转换后的 DataFrame
    """
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors=errors)
    return df


def as_datetime(
    df: pd.DataFrame,
    columns: List[str],
    errors: str = "raise"
) -> pd.DataFrame:
    """将列转换为日期时间类型

    Args:
        df: DataFrame
        columns: 要转换的列
        errors: 处理方式 ('raise', 'coerce', 'ignore')

    Returns:
        转换后的 DataFrame
    """
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors=errors)
    return df


# =============================================================================
# 值验证
# =============================================================================

def check_range(
    df: pd.DataFrame,
    column: str,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    allow_nan: bool = False,
    allow_inf: bool = False
) -> ValidationResult:
    """检查列的值范围

    Args:
        df: DataFrame
        column: 列名
        min_val: 最小值
        max_val: 最大值
        allow_nan: 是否允许 NaN
        allow_inf: 是否允许无穷

    Returns:
        ValidationResult
    """
    errors = []
    warnings = []

    if column not in df.columns:
        return ValidationResult(False, [f"Column '{column}' not found"], [])

    col = df[column]

    # 检查 NaN
    nan_count = col.isna().sum()
    if nan_count > 0 and not allow_nan:
        errors.append(f"Column '{column}': {nan_count} NaN values found")

    # 检查无穷
    if not allow_inf:
        inf_count = np.isinf(col).sum()
        if inf_count > 0:
            errors.append(f"Column '{column}': {inf_count} infinite values found")

    # 检查范围
    if min_val is not None:
        below = (col < min_val).sum()
        if below > 0:
            errors.append(f"Column '{column}': {below} values below {min_val}")

    if max_val is not None:
        above = (col > max_val).sum()
        if above > 0:
            errors.append(f"Column '{column}': {above} values above {max_val}")

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=[]
    )


def check_positive(
    df: pd.DataFrame,
    columns: List[str],
    allow_zero: bool = True
) -> ValidationResult:
    """检查列是否全为正数"""
    errors = []

    for col in columns:
        if col not in df.columns:
            continue

        if allow_zero:
            invalid = (df[col] < 0).sum()
        else:
            invalid = (df[col] <= 0).sum()

        if invalid > 0:
            errors.append(f"Column '{col}': {invalid} non-positive values")

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=[]
    )


def check_no_duplicates(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None
) -> ValidationResult:
    """检查是否有重复行/值

    Args:
        df: DataFrame
        columns: 要检查的列，None=检查所有列

    Returns:
        ValidationResult
    """
    errors = []

    if columns is None:
        duplicates = df.duplicated().sum()
    else:
        duplicates = df.duplicated(subset=columns).sum()

    if duplicates > 0:
        errors.append(f"Found {duplicates} duplicate rows")

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=[]
    )


# =============================================================================
# 自定义验证
# =============================================================================

def validate(
    df: pd.DataFrame,
    rules: List[Callable[[pd.DataFrame], ValidationResult]]
) -> ValidationResult:
    """应用验证规则列表

    Args:
        df: DataFrame
        rules: 验证函数列表

    Returns:
        合并的 ValidationResult
    """
    all_errors = []
    all_warnings = []

    for rule in rules:
        result = rule(df)
        all_errors.extend(result.errors)
        all_warnings.extend(result.warnings)

    return ValidationResult(
        passed=len(all_errors) == 0,
        errors=all_errors,
        warnings=all_warnings
    )


def schema_validator(required: Dict[str, Any]) -> Callable[[pd.DataFrame], ValidationResult]:
    """创建 Schema 验证器

    Args:
        required: Schema 定义 {列名: 验证器}

    Returns:
        验证函数
    """
    def validate_schema(df: pd.DataFrame) -> ValidationResult:
        errors = []
        warnings = []

        for col, validator in required.items():
            if col not in df.columns:
                errors.append(f"Missing column: {col}")
                continue

            # 应用验证器
            if callable(validator):
                result = validator(df[col])
                if isinstance(result, ValidationResult):
                    errors.extend(result.errors)
                    warnings.extend(result.warnings)
                elif isinstance(result, bool):
                    if not result:
                        errors.append(f"Column '{col}' failed validation")

        return ValidationResult(
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    return validate_schema


# =============================================================================
# 数据质量报告
# =============================================================================

def quality_report(df: pd.DataFrame) -> Dict[str, Any]:
    """生成数据质量报告

    Args:
        df: DataFrame

    Returns:
        质量报告字典
    """
    report = {
        "shape": df.shape,
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "null_counts": df.isna().sum().to_dict(),
        "null_ratio": (df.isna().sum() / len(df)).to_dict(),
        "memory_usage": df.memory_usage(deep=True).sum(),
    }

    # 数值列统计
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) > 0:
        report["numeric_stats"] = {
            "describe": df[numeric_cols].describe().to_dict(),
            "correlations": df[numeric_cols].corr().to_dict()
        }

    return report


# =============================================================================
# 便捷验证函数
# =============================================================================

def assert_columns(df: pd.DataFrame, columns: List[str]):
    """断言 DataFrame 包含指定列"""
    result = check_columns(df, required=columns)
    if not result:
        raise ValidationError(result.errors)


def assert_no_null(df: pd.DataFrame, columns: Optional[List[str]] = None):
    """断言 DataFrame 没有空值"""
    if columns is None:
        null_count = df.isna().sum().sum()
    else:
        null_count = df[columns].isna().sum().sum()

    if null_count > 0:
        raise ValidationError(f"Found {null_count} null values")


def assert_range(
    df: pd.DataFrame,
    column: str,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None
):
    """断言列值在指定范围内"""
    result = check_range(df, column, min_val, max_val)
    if not result:
        raise ValidationError(result.errors)
