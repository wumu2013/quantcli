"""日志配置工具

提供统一的日志配置，支持:
- 控制台输出 (带颜色)
- 文件日志 (自动分割日期)
- 模块级别隔离

Usage:
    >>> from quantcli.utils import get_logger
    >>> logger = get_logger(__name__)
    >>> logger.info("Hello, quant!")
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import os

# 默认日志格式
DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 日志级别映射
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class ColorFormatter(logging.Formatter):
    """带颜色的日志格式化器"""

    # ANSI 颜色代码
    COLORS = {
        "DEBUG": "\033[36m",  # 青色
        "INFO": "\033[32m",   # 绿色
        "WARNING": "\033[33m",  # 黄色
        "ERROR": "\033[31m",  # 红色
        "CRITICAL": "\033[35m",  # 紫色
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # 添加颜色
        levelname = record.levelname
        if levelname in self.COLORS and sys.stdout.isatty():
            record.msg = (
                f"{self.COLORS[levelname]}{record.msg}{self.RESET}"
            )
        return super().format(record)


def setup_logger(
    name: str = "quantcli",
    level: str = "INFO",
    log_dir: Optional[Path] = None,
    file_size: Optional[int] = None,
    backup_count: int = 5,
    console: bool = True
) -> logging.Logger:
    """配置并返回日志器

    Args:
        name: 日志器名称
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: 日志文件目录 (None=不写入文件)
        file_size: 单个日志文件大小限制 (bytes)，None=按天分割
        backup_count: 保留的日志文件数量
        console: 是否输出到控制台

    Returns:
        配置好的 Logger 对象
    """
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVELS.get(level.upper(), logging.INFO))

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 清除现有处理器
    logger.handlers.clear()

    # 格式器
    formatter = ColorFormatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT)

    # 控制台处理器
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(LOG_LEVELS.get(level.upper(), logging.INFO))
        logger.addHandler(console_handler)

    # 文件处理器
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / f"{name}.log"

        if file_size:
            # 按大小分割
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=file_size,
                backupCount=backup_count,
                encoding="utf-8"
            )
        else:
            # 按天分割
            file_handler = TimedRotatingFileHandler(
                log_file,
                when="midnight",
                backupCount=backup_count,
                encoding="utf-8"
            )

        file_handler.setFormatter(formatter)
        file_handler.setLevel(LOG_LEVELS.get(level.upper(), logging.INFO))
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """获取日志器 (推荐使用此函数)

    Args:
        name: 模块名称，通常使用 __name__

    Returns:
        Logger 实例
    """
    # 如果根日志器已配置，直接获取
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return logging.getLogger(name)

    # 否则初始化根日志器
    setup_logger()
    return logging.getLogger(name)


def log_performance(logger: logging.Logger, stage: str, start_time: float):
    """记录性能日志

    Args:
        logger: 日志器
        stage: 阶段名称
        start_time: 开始时间 (from time.time())
    """
    elapsed = time() - start_time
    logger.info(f"[{stage}] 耗时: {format_duration(elapsed)}")


# 便捷设置函数
def set_level(level: str, logger_name: Optional[str] = None):
    """设置日志级别

    Args:
        level: 级别名称
        logger_name: 指定日志器名称，None=根日志器
    """
    log_level = LOG_LEVELS.get(level.upper(), logging.INFO)
    if logger_name:
        logging.getLogger(logger_name).setLevel(log_level)
    else:
        logging.getLogger().setLevel(log_level)


def disable():
    """禁用所有日志"""
    logging.disable(logging.CRITICAL)


def enable():
    """启用所有日志"""
    logging.getLogger().setLevel(logging.DEBUG)


# 临时导入 time 模块用于 log_performance
from time import time


def format_duration(seconds: float) -> str:
    """格式化时间间隔

    Args:
        seconds: 秒数

    Returns:
        可读的时间字符串
    """
    if seconds < 1:
        return f"{seconds*1000:.1f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}min"
    else:
        return f"{seconds/3600:.1f}h"
