"""工具函数模块

提供通用的辅助功能:
- logger: 日志配置
- time: 日期时间处理
- path: 路径管理
- validate: 数据验证

Usage:
    >>> from quantcli.utils import get_logger, parse_date, project_root
    >>> from quantcli.utils import validate_schema, check_columns
"""

# Logger
from .logger import (
    setup_logger,
    get_logger,
    set_level,
    log_performance,
    disable,
    enable,
    format_duration,
)

# Time
from .time import (
    parse_date,
    parse_datetime,
    format_date,
    today,
    now,
    TimeContext,
    is_trading_day,
    get_next_trading_day,
    get_prev_trading_day,
    trading_days_between,
    generate_trading_days,
    add_trading_days,
    days_between,
    weeks_between,
    months_between,
    years_between,
    this_week_start,
    this_month_start,
    this_quarter_start,
    this_year_start,
    this_year_end,
)

# Path
from .path import (
    project_root,
    set_project_root,
    data_dir,
    raw_data_dir,
    cache_dir,
    features_dir,
    factors_dir,
    builtin_factors_dir,
    strategies_dir,
    results_dir,
    logs_dir,
    tests_dir,
    ensure_dir,
    ensure_parent_dir,
    find_files,
    find_file,
    file_age,
    file_size,
    format_size,
    temp_dir,
    temp_file,
)

# Validate
from .validate import (
    ValidationError,
    ValidationResult,
    check_columns,
    require_columns,
    check_dtypes,
    check_range,
    check_positive,
    check_no_duplicates,
    as_numeric,
    as_datetime,
    validate,
    schema_validator,
    quality_report,
    assert_columns,
    assert_no_null,
    assert_range,
)

__all__ = [
    # Logger
    "setup_logger",
    "get_logger",
    "set_level",
    "log_performance",
    "disable",
    "enable",
    "format_duration",
    # Time
    "parse_date",
    "parse_datetime",
    "format_date",
    "today",
    "now",
    "TimeContext",
    "is_trading_day",
    "get_next_trading_day",
    "get_prev_trading_day",
    "trading_days_between",
    "generate_trading_days",
    "add_trading_days",
    "days_between",
    "weeks_between",
    "months_between",
    "years_between",
    "this_week_start",
    "this_month_start",
    "this_quarter_start",
    "this_year_start",
    "this_year_end",
    # Path
    "project_root",
    "set_project_root",
    "data_dir",
    "raw_data_dir",
    "cache_dir",
    "features_dir",
    "factors_dir",
    "builtin_factors_dir",
    "strategies_dir",
    "results_dir",
    "logs_dir",
    "tests_dir",
    "ensure_dir",
    "ensure_parent_dir",
    "find_files",
    "find_file",
    "file_age",
    "file_size",
    "format_size",
    "temp_dir",
    "temp_file",
    # Validate
    "ValidationError",
    "ValidationResult",
    "check_columns",
    "require_columns",
    "check_dtypes",
    "check_range",
    "check_positive",
    "check_no_duplicates",
    "as_numeric",
    "as_datetime",
    "validate",
    "schema_validator",
    "quality_report",
    "assert_columns",
    "assert_no_null",
    "assert_range",
]
