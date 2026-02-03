"""股票代码工具类

统一处理三种代码格式：
- MySQL (新):  市场+代码，如 "SH600519", "SZ000001"
- MySQL (旧):  纯数字，如 "600519"（兼容）
- 掘金:       前缀.代码，如 "SHSE.600519"
- Akshare:    小写前缀.代码，如 "sh.600519"
"""

from typing import List, Optional


# ==================== 新格式：市场前缀 ====================

def format(symbol: str, prefix: str = "SH") -> str:
    """将任意格式转换为指定前缀的 MySQL 格式

    Args:
        symbol: 任意格式
        prefix: 市场前缀，"SH" 或 "SZ"

    Returns:
        带前缀格式，如 "SH600519", "SZ000001"
    """
    code = extract_code(symbol)
    market = prefix.upper()

    if market not in ("SH", "SZ"):
        market = "SH"

    return f"{market}{code}"


def format_sh(symbol: str) -> str:
    """转换为上海格式"""
    return format(symbol, "SH")


def format_sz(symbol: str) -> str:
    """转换为深圳格式"""
    return format(symbol, "SZ")


def format_batch(symbols: List[str], prefix: str = "SH") -> List[str]:
    """批量转换为指定前缀格式"""
    return [format(s, prefix) for s in symbols]


# ==================== 提取纯代码 ====================

def extract_code(symbol: str) -> str:
    """从任意格式提取纯代码

    Args:
        symbol: 任意格式

    Returns:
        纯代码，如 "600519"
    """
    if not symbol:
        return ""

    # 处理带前缀格式 (SH600519, SHSE.600519, sh.600519)
    if len(symbol) >= 8:
        # 检查是否已经是新格式 SH600519
        if symbol[:2] in ("SH", "SZ") and symbol[2:].isdigit():
            return symbol[2:]
        # 检查是否掘金/Akshare 格式
        if "." in symbol:
            return symbol.split(".")[-1]

    # 处理旧格式纯数字
    return symbol


def extract_prefix(symbol: str) -> str:
    """从带前缀格式提取市场前缀

    Args:
        symbol: 带前缀格式，如 "SH600519"

    Returns:
        "SH" 或 "SZ"
    """
    if not symbol:
        return "SH"

    # 新格式
    if symbol[:2] in ("SH", "SZ"):
        return symbol[:2]

    # 掘金/Akshare 格式
    if "." in symbol:
        prefix = symbol.split(".")[0].upper()
        if prefix in ("SHSE", "SH"):
            return "SH"
        if prefix in ("SZSE", "SZ"):
            return "SZ"

    # 纯数字格式
    return get_market_by_code(symbol)


# ==================== 格式转换 ====================

def to_gm(symbol: str) -> str:
    """任意格式转掘金格式

    Args:
        symbol: 任意格式

    Returns:
        掘金格式，如 "SHSE.600519"
    """
    code = extract_code(symbol)
    prefix = extract_prefix(symbol).upper()

    if prefix == "SH":
        return f"SHSE.{code}"
    else:
        return f"SZSE.{code}"


def to_mysql(symbol: str) -> str:
    """任意格式转 MySQL 格式（新格式，带前缀）

    Args:
        symbol: 任意格式

    Returns:
        MySQL 新格式，如 "SH600519"
    """
    code = extract_code(symbol)
    prefix = extract_prefix(symbol).upper()

    if prefix == "SH":
        return f"SH{code}"
    else:
        return f"SZ{code}"


def to_akshare(symbol: str) -> str:
    """任意格式转 Akshare 格式

    Args:
        symbol: 任意格式

    Returns:
        Akshare 格式，如 "sh.600519"
    """
    code = extract_code(symbol)
    prefix = extract_prefix(symbol).upper()

    if prefix == "SH":
        return f"sh.{code}"
    else:
        return f"sz.{code}"


def to_gm_from_mysql(symbol: str) -> str:
    """MySQL 格式转掘金格式"""
    return to_gm(symbol)


def to_mysql_from_gm(symbol: str) -> str:
    """掘金格式转 MySQL 格式"""
    return to_mysql(symbol)


def to_mysql_from_akshare(symbol: str) -> str:
    """Akshare 格式转 MySQL 格式"""
    return to_mysql(symbol)


# ==================== 批量转换 ====================

def to_gm_batch(symbols: List[str]) -> List[str]:
    """批量转为掘金格式"""
    return [to_gm(s) for s in symbols]


def to_mysql_batch(symbols: List[str]) -> List[str]:
    """批量转为 MySQL 格式"""
    return [to_mysql(s) for s in symbols]


def to_akshare_batch(symbols: List[str]) -> List[str]:
    """批量转为 Akshare 格式"""
    return [to_akshare(s) for s in symbols]


# ==================== 统一格式 ====================

def normalize(symbol: str) -> str:
    """任意格式统一转换为 MySQL 新格式（带前缀）

    Args:
        symbol: 任意格式

    Returns:
        MySQL 新格式，如 "SH600519"
    """
    return to_mysql(symbol)


def normalize_batch(symbols: List[str]) -> List[str]:
    """批量统一转换"""
    return [normalize(s) for s in symbols]


# ==================== 市场判断 ====================

def get_market(symbol: str) -> str:
    """获取市场

    Args:
        symbol: 任意格式

    Returns:
        "SHSE" / "SZSE"
    """
    prefix = extract_prefix(symbol)
    if prefix == "SH":
        return "SHSE"
    return "SZSE"


def get_type(symbol: str) -> str:
    """获取类型

    Args:
        symbol: 任意格式

    Returns:
        "stock" / "etf" / "index"
    """
    code = extract_code(symbol)
    return _get_type_by_code(code)


# ==================== 类型判断 ====================

def is_shanghai(symbol: str) -> bool:
    """是否上海市场"""
    return get_market(symbol) == "SHSE"


def is_shenzhen(symbol: str) -> bool:
    """是否深圳市场"""
    return get_market(symbol) == "SZSE"


def is_stock(symbol: str) -> bool:
    """是否股票"""
    return get_type(symbol) == "stock"


def is_etf(symbol: str) -> bool:
    """是否 ETF"""
    return get_type(symbol) == "etf"


def is_index(symbol: str) -> bool:
    """是否指数"""
    return get_type(symbol) == "index"


def is_gem(symbol: str) -> bool:
    """是否创业板"""
    code = extract_code(symbol)
    return code.startswith("3")


def is_new_format(symbol: str) -> bool:
    """是否新格式（带前缀）"""
    return len(symbol) >= 8 and symbol[:2] in ("SH", "SZ") and symbol[2:].isdigit()


def is_old_format(symbol: str) -> bool:
    """是否旧格式（纯数字）"""
    return symbol.isdigit()


# ==================== 过滤 ====================

def filter_a_shares(symbols: List[str]) -> List[str]:
    """只保留 A 股（不含创业板）"""
    return [s for s in symbols if _is_a_share_by_code(extract_code(s))]


def filter_etfs(symbols: List[str]) -> List[str]:
    """只保留 ETF"""
    return [s for s in symbols if is_etf(s)]


def filter_index(symbols: List[str]) -> List[str]:
    """只保留指数"""
    return [s for s in symbols if is_index(s)]


def filter_shanghai(symbols: List[str]) -> List[str]:
    """只保留上海"""
    return [s for s in symbols if is_shanghai(s)]


def filter_shenzhen(symbols: List[str]) -> List[str]:
    """只保留深圳"""
    return [s for s in symbols if is_shenzhen(s)]


def filter_new_format(symbols: List[str]) -> List[str]:
    """只保留新格式"""
    return [s for s in symbols if is_new_format(s)]


def filter_old_format(symbols: List[str]) -> List[str]:
    """只保留旧格式"""
    return [s for s in symbols if is_old_format(s)]


# ==================== 兼容旧格式 ====================

def to_old_mysql(symbol: str) -> str:
    """转为旧格式（纯数字，用于兼容）"""
    return extract_code(symbol)


def from_old_mysql(symbol: str, default_prefix: str = "SH") -> str:
    """从旧格式转为新格式

    Args:
        symbol: 旧格式纯数字
        default_prefix: 默认前缀
    """
    return format(symbol, default_prefix)


# ==================== 内部函数 ====================

def get_market_by_code(code: str) -> str:
    """根据代码判断市场"""
    if not code:
        return "SH"

    if code.startswith("6") or code.startswith("5"):
        return "SH"
    return "SZ"


def _get_type_by_code(code: str) -> str:
    """根据代码判断类型"""
    if not code:
        return "stock"

    # 指数
    if code in ("000001", "399001", "399006", "000016", "000300"):
        return "index"

    # ETF: 沪 5xxxxx, 深 15xxxxx/16xxxxx
    if code.startswith("5") and len(code) == 6:
        return "etf"
    if (code.startswith("15") or code.startswith("16")) and len(code) == 6:
        return "etf"

    # 创业板
    if code.startswith("3"):
        return "stock"

    return "stock"


def _is_a_share_by_code(code: str) -> bool:
    """根据代码判断是否 A 股（不含创业板）"""
    return code.startswith("6") or code.startswith("0")
