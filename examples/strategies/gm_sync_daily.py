"""
掘金量化全市场日线同步脚本

在 on_bar 事件中将全市场日线数据同步到 MySQL。

使用方法:
    1. 配置 MySQL 环境变量
    2. 运行: python examples/strategies/gm_sync_daily.py

注意: 需要安装掘金 SDK (gm.api)
"""

import os
from datetime import date, timedelta
from quantcli.models.bar import DailyBar
from quantcli.datasources import create_sync, MySQLDataSource
from quantcli.utils.symbol_utils import to_mysql, to_gm, normalize

# ==================== 配置 ====================

# MySQL 连接（环境变量或直接配置）
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "quantcli"),
}

# 掘金 Token
GM_TOKEN = os.getenv("GM_TOKEN", "")

# 每次订阅数量（掘金限制每次最多 200 只）
BATCH_SIZE = 200


# ==================== 掘金策略 ====================

try:
    from gm.api import strategy, set_token

    if GM_TOKEN:
        set_token(GM_TOKEN)

    @strategy(
        name="全市场日线同步",
        symbols=[],  # 动态订阅
        frequency='1d',
        settings={
            "trade_ruler": {"enabled": False}
        }
    )
    def init(context):
        """策略初始化"""
        # 创建 MySQL 连接获取股票列表
        mysql = MySQLDataSource(**MYSQL_CONFIG)

        # 获取全市场股票列表
        stock_list = mysql.get_stock_list()
        all_symbols = stock_list['symbol'].tolist()

        print(f"MySQL: {MYSQL_CONFIG['database']}@{MYSQL_CONFIG['host']}")
        print(f"全市场股票: {len(all_symbols)} 只")

        # 转换为掘金格式
        gm_symbols = [to_gm(s) for s in all_symbols]

        # 创建同步器
        context.sync = create_sync("gm", token=GM_TOKEN, **MYSQL_CONFIG)

        # 同步状态
        context.sync_count = 0
        context.last_sync_date = None
        context.all_symbols = gm_symbols
        context.mysql_symbols = all_symbols
        context.current_batch = 0

        # 分批订阅
        total_batches = (len(gm_symbols) + BATCH_SIZE - 1) // BATCH_SIZE
        symbols_batch = gm_symbols[:BATCH_SIZE]

        print(f"分 {total_batches} 批订阅，每批 {BATCH_SIZE} 只")
        print(f"第 1/{total_batches} 批: {symbols_batch[:5]}...")

        context.subscribe(symbols=symbols_batch, frequency='1d')

    def on_bar(context, bars):
        """on_bar 事件 - 同步每根日线"""
        for bar in bars:
            # 转换为 MySQL 格式的代码
            mysql_symbol = to_mysql(bar.symbol)

            # 创建 DailyBar（使用 MySQL 格式的 symbol）
            daily_bar = DailyBar.from_gm_bar(mysql_symbol, bar)

            if daily_bar.trade_date == context.last_sync_date:
                continue

            success = context.sync.sync_bar(daily_bar)

            if success:
                context.sync_count += 1
                context.last_sync_date = daily_bar.trade_date

                if context.sync_count % 100 == 0:
                    print(f"已同步 {context.sync_count} 条")

        # 检查是否需要订阅下一批
        if context.bar_count >= len(context.all_symbols) / BATCH_SIZE:
            start = (context.current_batch + 1) * BATCH_SIZE
            if start < len(context.all_symbols):
                end = min(start + BATCH_SIZE, len(context.all_symbols))
                next_batch = context.all_symbols[start:end]
                context.current_batch += 1

                total_batches = (len(context.all_symbols) + BATCH_SIZE - 1) // BATCH_SIZE
                print(f"订阅第 {context.current_batch + 1}/{total_batches} 批: {next_batch[:5]}...")

                context.subscribe(symbols=next_batch, frequency='1d')

    def on_backtest_finished(context, indicator):
        print(f"\n同步完成! 共 {context.sync_count} 条日线数据")

    if __name__ == "__main__":
        from gm.api import run

        print("=" * 50)
        print("掘金量化 - 全市场日线同步")
        print("=" * 50)

        run()

except ImportError:
    print("掘金 SDK 未安装")
    print("安装: pip install gm.api")
