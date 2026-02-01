"""数据同步模块

提供通用的数据同步框架，支持从不同数据源同步数据到 MySQL。

使用示例:
    >>> from quantcli.datasources import create_sync
    >>> sync = create_sync("gm", token="your_token")
    >>> sync.sync_daily(["600519"], date(2024, 1, 1))
"""

from .base import DataSync, create_sync
from .gm import GmSync

__all__ = ["DataSync", "GmSync", "create_sync"]
