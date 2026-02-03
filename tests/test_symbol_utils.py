"""symbol_utils 单元测试

覆盖各种代码格式转换场景：
- MySQL 新格式: SH600519, SZ000001, SZ510500
- MySQL 旧格式: 600519, 000001, 510500
- 掘金格式: SHSE.600519, SZSE.000001
- Akshare 格式: sh.600519, sz.000001
"""

import pytest
from quantcli.utils.symbol_utils import (
    # 格式转换
    format, format_sh, format_sz, format_batch,
    extract_code, extract_prefix,
    to_gm, to_mysql, to_akshare,
    to_gm_batch, to_mysql_batch, to_akshare_batch,
    normalize, normalize_batch,
    # 市场判断
    get_market, get_type,
    # 类型判断
    is_shanghai, is_shenzhen,
    is_stock, is_etf, is_index, is_gem,
    is_new_format, is_old_format,
    # 过滤
    filter_a_shares, filter_etfs, filter_index,
    filter_shanghai, filter_shenzhen,
    filter_new_format, filter_old_format,
    # 兼容
    to_old_mysql, from_old_mysql,
    # 内部函数
    get_market_by_code,
)


class TestExtractCode:
    """测试 extract_code - 提取纯代码"""

    def test_mysql_new_format(self):
        """MySQL 新格式: SH600519, SZ000001"""
        assert extract_code("SH600519") == "600519"
        assert extract_code("SZ000001") == "000001"
        assert extract_code("SH510500") == "510500"
        assert extract_code("SZ159915") == "159915"

    def test_mysql_old_format(self):
        """MySQL 旧格式: 纯数字"""
        assert extract_code("600519") == "600519"
        assert extract_code("000001") == "000001"
        assert extract_code("510500") == "510500"

    def test_gm_format(self):
        """掘金格式: SHSE.600519"""
        assert extract_code("SHSE.600519") == "600519"
        assert extract_code("SZSE.000001") == "000001"
        assert extract_code("SHSE.510500") == "510500"

    def test_akshare_format(self):
        """Akshare 格式: sh.600519"""
        assert extract_code("sh.600519") == "600519"
        assert extract_code("sz.000001") == "000001"
        assert extract_code("sz.510500") == "510500"

    def test_empty(self):
        """空字符串"""
        assert extract_code("") == ""
        assert extract_code(None) == ""  # type: ignore

    def test_edge_cases(self):
        """边界情况"""
        assert extract_code("6") == "6"
        assert extract_code("600519") == "600519"


class TestExtractPrefix:
    """测试 extract_prefix - 提取市场前缀"""

    def test_mysql_new_format(self):
        """MySQL 新格式"""
        assert extract_prefix("SH600519") == "SH"
        assert extract_prefix("SZ000001") == "SZ"

    def test_gm_format(self):
        """掘金格式"""
        assert extract_prefix("SHSE.600519") == "SH"
        assert extract_prefix("SZSE.000001") == "SZ"

    def test_akshare_format(self):
        """Akshare 格式"""
        assert extract_prefix("sh.600519") == "SH"
        assert extract_prefix("sz.000001") == "SZ"

    def test_mysql_old_format(self):
        """MySQL 旧格式 - 根据代码判断"""
        assert extract_prefix("600519") == "SH"  # 6开头是上海
        assert extract_prefix("000001") == "SZ"  # 0开头是深圳
        assert extract_prefix("510500") == "SH"  # 5开头是上海 ETF
        assert extract_prefix("159915") == "SZ"  # 15开头是深圳 ETF


class TestFormat:
    """测试 format - 格式化为 MySQL 新格式"""

    def test_default_prefix(self):
        """默认前缀 SH"""
        assert format("600519") == "SH600519"
        assert format("SHSE.600519") == "SH600519"
        assert format("sh.600519") == "SH600519"

    def test_explicit_prefix(self):
        """指定前缀"""
        assert format("000001", "SZ") == "SZ000001"
        assert format("000001", "SH") == "SH000001"  # 强制改前缀
        assert format("600519", "SZ") == "SZ600519"  # 强制改前缀

    def test_invalid_prefix(self):
        """无效前缀"""
        assert format("600519", "INVALID") == "SH600519"  # 降级为 SH

    def test_format_sh(self):
        """format_sh 快捷函数"""
        assert format_sh("600519") == "SH600519"
        assert format_sh("SZ000001") == "SH000001"  # 强制改

    def test_format_sz(self):
        """format_sz 快捷函数"""
        assert format_sz("600519") == "SZ600519"
        assert format_sz("SH600519") == "SZ600519"  # 强制改

    def test_format_batch(self):
        """批量格式化"""
        symbols = ["600519", "000001", "510500"]
        result = format_batch(symbols, "SH")
        assert result == ["SH600519", "SH000001", "SH510500"]


class TestToGm:
    """测试 to_gm - 转换为掘金格式"""

    def test_from_mysql_new(self):
        """从 MySQL 新格式转换"""
        assert to_gm("SH600519") == "SHSE.600519"
        assert to_gm("SZ000001") == "SZSE.000001"

    def test_from_mysql_old(self):
        """从 MySQL 旧格式转换"""
        assert to_gm("600519") == "SHSE.600519"
        assert to_gm("000001") == "SZSE.000001"

    def test_from_gm_format(self):
        """从掘金格式转换（透传）"""
        assert to_gm("SHSE.600519") == "SHSE.600519"
        assert to_gm("SZSE.000001") == "SZSE.000001"

    def test_from_akshare(self):
        """从 Akshare 格式转换"""
        assert to_gm("sh.600519") == "SHSE.600519"
        assert to_gm("sz.000001") == "SZSE.000001"

    def test_batch(self):
        """批量转换"""
        symbols = ["SH600519", "SZ000001", "510500"]
        result = to_gm_batch(symbols)
        assert result == ["SHSE.600519", "SZSE.000001", "SHSE.510500"]


class TestToMysql:
    """测试 to_mysql - 转换为 MySQL 新格式"""

    def test_from_gm(self):
        """从掘金格式转换"""
        assert to_mysql("SHSE.600519") == "SH600519"
        assert to_mysql("SZSE.000001") == "SZ000001"

    def test_from_akshare(self):
        """从 Akshare 格式转换"""
        assert to_mysql("sh.600519") == "SH600519"
        assert to_mysql("sz.000001") == "SZ000001"

    def test_from_old_mysql(self):
        """从 MySQL 旧格式转换"""
        assert to_mysql("600519") == "SH600519"
        assert to_mysql("000001") == "SZ000001"

    def test_etf(self):
        """ETF 格式"""
        assert to_mysql("510500") == "SH510500"  # 上海 ETF
        assert to_mysql("159915") == "SZ159915"  # 深圳 ETF
        assert to_mysql("SHSE.510500") == "SH510500"

    def test_batch(self):
        """批量转换"""
        symbols = ["SHSE.600519", "SZSE.000001", "sh.510500"]
        result = to_mysql_batch(symbols)
        assert result == ["SH600519", "SZ000001", "SH510500"]


class TestToAkshare:
    """测试 to_akshare - 转换为 Akshare 格式"""

    def test_from_gm(self):
        """从掘金格式转换"""
        assert to_akshare("SHSE.600519") == "sh.600519"
        assert to_akshare("SZSE.000001") == "sz.000001"

    def test_from_mysql_new(self):
        """从 MySQL 新格式转换"""
        assert to_akshare("SH600519") == "sh.600519"
        assert to_akshare("SZ000001") == "sz.000001"

    def test_from_mysql_old(self):
        """从 MySQL 旧格式转换"""
        assert to_akshare("600519") == "sh.600519"
        assert to_akshare("000001") == "sz.000001"

    def test_batch(self):
        """批量转换"""
        symbols = ["SH600519", "SZ000001", "600519"]
        result = to_akshare_batch(symbols)
        assert result == ["sh.600519", "sz.000001", "sh.600519"]


class TestNormalize:
    """测试 normalize - 统一格式"""

    def test_various_formats(self):
        """各种格式统一为 MySQL 新格式"""
        assert normalize("600519") == "SH600519"
        assert normalize("SH600519") == "SH600519"
        assert normalize("SHSE.600519") == "SH600519"
        assert normalize("sh.600519") == "SH600519"

    def test_batch(self):
        """批量统一"""
        symbols = ["600519", "SHSE.000001", "sz.510500"]
        result = normalize_batch(symbols)
        # 注意:
        # - 600519 -> SH600519 (6xxx 是上海)
        # - SHSE.000001 -> SH000001 (SHSE 是上海交易所)
        # - sz.510500 -> SZ510500 (sz 是深圳)
        assert result == ["SH600519", "SH000001", "SZ510500"]


class TestGetMarket:
    """测试 get_market - 获取市场"""

    def test_shanghai(self):
        """上海市场"""
        assert get_market("SH600519") == "SHSE"
        assert get_market("600519") == "SHSE"
        assert get_market("SHSE.600519") == "SHSE"

    def test_shenzhen(self):
        """深圳市场"""
        assert get_market("SZ000001") == "SZSE"
        assert get_market("000001") == "SZSE"
        assert get_market("SZSE.000001") == "SZSE"

    def test_etf(self):
        """ETF"""
        assert get_market("SH510500") == "SHSE"
        assert get_market("SZ159915") == "SZSE"


class TestGetType:
    """测试 get_type - 获取类型"""

    def test_stock(self):
        """股票"""
        assert get_type("600519") == "stock"
        assert get_type("SH600519") == "stock"
        # 000001 是上证指数，不是股票
        assert get_type("000001") == "index"

    def test_etf(self):
        """ETF"""
        assert get_type("510500") == "etf"
        assert get_type("SH510500") == "etf"
        assert get_type("159915") == "etf"
        assert get_type("SZ159915") == "etf"
        assert get_type("160119") == "etf"

    def test_index(self):
        """指数"""
        assert get_type("000001") == "index"  # 上证指数
        assert get_type("399001") == "index"  # 深证成指
        assert get_type("399006") == "index"  # 创业板指
        assert get_type("000016") == "index"  # 上证50
        assert get_type("000300") == "index"  # 沪深300


class TestIsFunctions:
    """测试各种 is_* 判断函数"""

    def test_is_shanghai(self):
        assert is_shanghai("SH600519") is True
        assert is_shanghai("600519") is True
        assert is_shanghai("SZ000001") is False

    def test_is_shenzhen(self):
        assert is_shenzhen("SZ000001") is True
        assert is_shenzhen("000001") is True
        assert is_shenzhen("SH600519") is False

    def test_is_stock(self):
        assert is_stock("600519") is True
        assert is_stock("SH600519") is True
        assert is_stock("510500") is False  # ETF

    def test_is_etf(self):
        assert is_etf("510500") is True
        assert is_etf("SH510500") is True
        assert is_etf("159915") is True
        assert is_etf("600519") is False  # 股票

    def test_is_index(self):
        assert is_index("000001") is True
        assert is_index("399001") is True
        assert is_index("600519") is False

    def test_is_gem(self):
        """创业板"""
        assert is_gem("300001") is True
        assert is_gem("SZ300001") is True
        assert is_gem("600519") is False

    def test_is_new_format(self):
        """新格式"""
        assert is_new_format("SH600519") is True
        assert is_new_format("SZ000001") is True
        assert is_new_format("600519") is False  # 旧格式
        assert is_new_format("SHSE.600519") is False  # 掘金格式

    def test_is_old_format(self):
        """旧格式"""
        assert is_old_format("600519") is True
        assert is_old_format("000001") is True
        assert is_old_format("SH600519") is False


class TestFilter:
    """测试过滤函数"""

    def test_filter_a_shares(self):
        """只保留 A 股（不含创业板和 ETF）"""
        symbols = ["600519", "000001", "300001", "510500"]
        result = filter_a_shares(symbols)
        # A 股只包含 6xxx 和 0xxx 开头，不含创业板(3xxx)和ETF(5xxx)
        assert result == ["600519", "000001"]

    def test_filter_etfs(self):
        """只保留 ETF"""
        symbols = ["600519", "510500", "159915", "000001"]
        result = filter_etfs(symbols)
        assert result == ["510500", "159915"]

    def test_filter_index(self):
        """只保留指数"""
        symbols = ["600519", "000001", "399001", "510500"]
        result = filter_index(symbols)
        assert result == ["000001", "399001"]

    def test_filter_shanghai(self):
        """只保留上海"""
        symbols = ["SH600519", "SZ000001", "SH510500"]
        result = filter_shanghai(symbols)
        assert result == ["SH600519", "SH510500"]

    def test_filter_shenzhen(self):
        """只保留深圳"""
        symbols = ["SH600519", "SZ000001", "SZ159915"]
        result = filter_shenzhen(symbols)
        assert result == ["SZ000001", "SZ159915"]

    def test_filter_new_format(self):
        """只保留新格式"""
        symbols = ["SH600519", "600519", "SZ000001", "SHSE.000001"]
        result = filter_new_format(symbols)
        assert result == ["SH600519", "SZ000001"]

    def test_filter_old_format(self):
        """只保留旧格式"""
        symbols = ["SH600519", "600519", "SZ000001"]
        result = filter_old_format(symbols)
        assert result == ["600519"]


class TestCompatible:
    """测试兼容函数"""

    def test_to_old_mysql(self):
        """转为旧格式"""
        assert to_old_mysql("SH600519") == "600519"
        assert to_old_mysql("SZ000001") == "000001"
        assert to_old_mysql("600519") == "600519"

    def test_from_old_mysql(self):
        """从旧格式转为新格式"""
        assert from_old_mysql("600519") == "SH600519"
        assert from_old_mysql("600519", "SZ") == "SZ600519"
        assert from_old_mysql("000001") == "SH000001"  # 默认 SH


class TestGetMarketByCode:
    """测试 get_market_by_code - 根据代码判断市场"""

    def test_shanghai_codes(self):
        """上海代码"""
        assert get_market_by_code("600519") == "SH"
        assert get_market_by_code("500500") == "SH"  # ETF

    def test_shenzhen_codes(self):
        """深圳代码"""
        assert get_market_by_code("000001") == "SZ"
        assert get_market_by_code("300001") == "SZ"  # 创业板
        assert get_market_by_code("159915") == "SZ"  # 深圳 ETF

    def test_empty(self):
        """空代码"""
        assert get_market_by_code("") == "SH"


class TestComplexScenarios:
    """复杂场景测试"""

    def test_all_formats_to_gm(self):
        """所有格式转掘金"""
        formats = [
            "600519",        # MySQL 旧
            "SH600519",      # MySQL 新
            "SHSE.600519",   # 掘金
            "sh.600519",     # Akshare
        ]
        results = to_gm_batch(formats)
        assert all(r == "SHSE.600519" for r in results)

    def test_all_formats_to_mysql(self):
        """所有格式转 MySQL 新格式"""
        formats = [
            "600519",        # MySQL 旧
            "SH600519",      # MySQL 新
            "SHSE.600519",   # 掘金
            "sh.600519",     # Akshare
        ]
        results = to_mysql_batch(formats)
        assert all(r == "SH600519" for r in results)

    def test_all_formats_to_akshare(self):
        """所有格式转 Akshare"""
        formats = [
            "600519",        # MySQL 旧
            "SH600519",      # MySQL 新
            "SHSE.600519",   # 掘金
            "sh.600519",     # Akshare
        ]
        results = to_akshare_batch(formats)
        assert all(r == "sh.600519" for r in results)

    def test_mixed_sh_sz(self):
        """混合上海深圳"""
        symbols = ["600519", "000001", "510500", "159915"]
        result = normalize_batch(symbols)
        assert result == ["SH600519", "SZ000001", "SH510500", "SZ159915"]


class TestEdgeCases:
    """边界情况测试"""

    def test_empty_list(self):
        """空列表"""
        assert normalize_batch([]) == []
        assert to_gm_batch([]) == []
        assert filter_etfs([]) == []

    def test_special_characters(self):
        """特殊字符 - 不完全匹配时返回原值"""
        # 因为不完全匹配格式，返回原值
        assert extract_code("SH600519!") == "SH600519!"

    def test_lowercase_prefixes(self):
        """小写前缀"""
        assert extract_prefix("sh.600519") == "SH"
        assert extract_prefix("sz.000001") == "SZ"

    def test_uppercase_prefixes(self):
        """大写前缀"""
        assert extract_prefix("SH.600519") == "SH"  # 错误格式但能处理
        assert extract_prefix("SZ.000001") == "SZ"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
