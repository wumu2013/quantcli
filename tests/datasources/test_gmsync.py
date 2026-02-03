"""GmSync 单元测试

测试掘金量化数据同步器的核心功能。
由于依赖外部 API 和数据库，使用 mock 进行隔离测试。
"""

import pytest
from datetime import date, datetime, time
from unittest.mock import Mock, patch, MagicMock
import os


class TestGmSyncCreation:
    """GmSync 创建测试"""

    def test_create_gmsync_with_token(self):
        """带 token 创建 GmSync"""
        with patch('quantcli.datasources.MySQLDataSource') as MockMySQL:
            mock_mysql = Mock()
            MockMySQL.return_value = mock_mysql

            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync(token="test_token")

            assert sync._token == "test_token"

    def test_create_gmsync_from_env(self):
        """从环境变量获取 token"""
        with patch.dict(os.environ, {"GM_TOKEN": "env_token"}):
            with patch('quantcli.datasources.MySQLDataSource') as MockMySQL:
                mock_mysql = Mock()
                MockMySQL.return_value = mock_mysql

                from quantcli.datasources.sync.gm import GmSync
                sync = GmSync()

                assert sync._token == "env_token"


class TestGmSyncPeriodMap:
    """分钟周期映射测试"""

    def test_period_map_values(self):
        """验证周期映射"""
        from quantcli.datasources.sync.gm import GmSync

        assert GmSync.PERIOD_MAP["1"] == "60s"
        assert GmSync.PERIOD_MAP["5"] == "300s"
        assert GmSync.PERIOD_MAP["15"] == "900s"
        assert GmSync.PERIOD_MAP["30"] == "1800s"
        assert GmSync.PERIOD_MAP["60"] == "3600s"


class TestGmSyncProgress:
    """进度查询测试"""

    def test_get_progress_found(self):
        """查询到进度"""
        mock_mysql = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = {'latest': date(2024, 1, 15)}
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_mysql._get_connection.return_value = mock_conn
        mock_mysql._table.return_value = "daily_prices"

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync()

            result = sync.get_progress("600519")

            assert result == date(2024, 1, 15)

    def test_get_progress_not_found(self):
        """未查到进度"""
        mock_mysql = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_mysql._get_connection.return_value = mock_conn
        mock_mysql._table.return_value = "daily_prices"

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync()

            result = sync.get_progress("600519")

            assert result is None


class TestGmSyncBar:
    """on_bar 同步测试"""

    def test_sync_bar_with_object(self):
        """使用 Bar 对象同步"""
        mock_mysql = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_mysql._get_connection.return_value = mock_conn
        mock_mysql._table.return_value = "daily_prices"

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync()

            # 创建 mock Bar 对象
            mock_bar = Mock()
            mock_bar.symbol = "SHSE.600519"
            mock_bar.eob = datetime(2024, 1, 15, 15, 0, 0)
            mock_bar.open = 100.0
            mock_bar.high = 102.0
            mock_bar.low = 99.0
            mock_bar.close = 101.0
            mock_bar.volume = 1000000
            mock_bar.amount = 100000000.0

            # 新 API: sync_bar(bar)，不再需要 symbol 参数
            result = sync.sync_bar(mock_bar)

            assert result is True
            mock_cursor.execute.assert_called_once()

    def test_sync_bar_with_dict(self):
        """使用字典同步"""
        mock_mysql = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_mysql._get_connection.return_value = mock_conn
        mock_mysql._table.return_value = "daily_prices"

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync()

            # 字典需要包含 symbol
            bar_dict = {
                'symbol': '600519',
                'eob': '2024-01-15T15:00:00',
                'open': 100.0,
                'high': 102.0,
                'low': 99.0,
                'close': 101.0,
                'volume': 1000000,
                'amount': 100000000.0
            }

            # 新 API: sync_bar(bar_dict)
            result = sync.sync_bar(bar_dict)

            assert result is True

    def test_sync_bar_failure(self):
        """同步失败"""
        mock_mysql = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.execute.side_effect = Exception("DB error")
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_mysql._get_connection.return_value = mock_conn
        mock_mysql._table.return_value = "daily_prices"

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync()

            mock_bar = Mock()
            mock_bar.symbol = "600519"
            mock_bar.eob = datetime(2024, 1, 15, 15, 0, 0)
            mock_bar.open = 100.0
            mock_bar.high = 102.0
            mock_bar.low = 99.0
            mock_bar.close = 101.0
            mock_bar.volume = 1000000
            mock_bar.amount = 0

            # 新 API: sync_bar(bar)
            result = sync.sync_bar(mock_bar)

            assert result is False


class TestGmSyncMinuteBar:
    """分钟线同步测试"""

    def test_sync_minute_bar(self):
        """同步分钟线 Bar"""
        mock_mysql = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_mysql._get_connection.return_value = mock_conn
        mock_mysql._table.return_value = "intraday_prices"

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync()

            mock_bar = Mock()
            mock_bar.symbol = "600519"
            mock_bar.eob = datetime(2024, 1, 15, 14, 30, 0)
            mock_bar.open = 100.0
            mock_bar.high = 102.0
            mock_bar.low = 99.0
            mock_bar.close = 101.0
            mock_bar.volume = 10000
            mock_bar.amount = 1000000.0
            mock_bar.period = "5"

            # 新 API: sync_minute_bar(bar)
            result = sync.sync_minute_bar(mock_bar)

            assert result is True


class TestGmSyncFundamental:
    """基本面同步测试"""

    def test_sync_fundamental_not_implemented(self):
        """掘金不支持基本面"""
        mock_mysql = Mock()

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync()

            result = sync.sync_fundamental(["600519"])

            assert result["600519"] == -1


class TestGmSyncClose:
    """资源清理测试"""

    def test_close(self):
        """关闭连接"""
        mock_mysql = Mock()

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync()

            sync.close()

            mock_mysql.close.assert_called_once()


class TestGmSyncTableNames:
    """表名测试"""

    def test_get_daily_table(self):
        """获取日线表名"""
        mock_mysql = Mock()
        mock_mysql._table.return_value = "quantcli_daily_prices"

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync()

            assert sync._get_daily_table() == "quantcli_daily_prices"

    def test_get_minute_table(self):
        """获取分钟线表名"""
        mock_mysql = Mock()
        mock_mysql._table.return_value = "quantcli_intraday_prices"

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync()

            assert sync._get_minute_table() == "quantcli_intraday_prices"


class TestCreateSync:
    """工厂函数测试"""

    def test_create_sync_gm(self):
        """创建 GmSync"""
        mock_mysql = Mock()

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources import create_sync

            sync = create_sync("gm")
            assert sync.name == "gm"

    def test_create_sync_invalid_source(self):
        """无效数据源"""
        mock_mysql = Mock()

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources import create_sync

            with pytest.raises(ValueError) as exc_info:
                create_sync("invalid_source")

            assert "Unsupported sync source" in str(exc_info.value)


class TestGmSyncMinute:
    """分钟线批量同步测试"""

    def test_sync_minute_invalid_period(self):
        """无效周期参数"""
        mock_mysql = Mock()

        with patch('quantcli.datasources.MySQLDataSource', return_value=mock_mysql):
            from quantcli.datasources.sync.gm import GmSync
            sync = GmSync()

            with pytest.raises(ValueError) as exc_info:
                sync.sync_minute(["600519"], "99", date(2024, 1, 1))

            assert "Invalid period" in str(exc_info.value)
