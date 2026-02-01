"""core/data.py 单元测试"""

import pytest
from datetime import date
from quantcli.core import DataManager, DataConfig


class TestDataConfig:
    """DataConfig 测试"""

    def test_default_config(self):
        config = DataConfig()
        assert config.source == "akshare"
        assert config.fillna == "ffill"

    def test_custom_config(self):
        config = DataConfig(
            source="custom",
            fillna="zero",
            parallel=8
        )
        assert config.source == "custom"
        assert config.fillna == "zero"


class TestDataManager:
    """DataManager 测试"""

    def test_dm_creation(self):
        dm = DataManager()
        assert dm is not None

    def test_dm_with_custom_cache_dir(self, tmp_path):
        config = DataConfig(cache_dir=str(tmp_path))
        dm = DataManager(config)
        assert dm.cache_dir.exists()


class TestDataManagerCleaning:
    """DataManager 数据清洗测试"""

    def test_clean_fillna_ffill(self, df_with_missing):
        dm = DataManager()
        result = dm.clean(df_with_missing, fillna="ffill")
        assert result["close"].isna().sum() == 0

    def test_clean_fillna_zero(self, df_with_missing):
        dm = DataManager()
        result = dm.clean(df_with_missing, fillna="zero")
        assert result["close"].isna().sum() == 0
        assert result["close"].iloc[2] == 0

    def test_clean_returns_copy(self, df_with_missing):
        dm = DataManager()
        result = dm.clean(df_with_missing, inplace=False)
        # 原始数据不应被修改
        assert result["close"].isna().sum() < df_with_missing["close"].isna().sum()


class TestDataManagerCache:
    """DataManager 缓存测试"""

    def test_clear_cache(self, tmp_path):
        dm = DataManager()
        dm.cache_dir = tmp_path / "cache_test"
        dm._init_cache_dir()

        count = dm.clear_cache()
        assert isinstance(count, int)

    def test_get_cache_size(self, tmp_path):
        dm = DataManager()
        dm.cache_dir = tmp_path / "cache_test"
        dm._init_cache_dir()

        sizes = dm.get_cache_size()
        assert "_total" in sizes
