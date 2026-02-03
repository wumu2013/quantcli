"""
掘金量化日内 ranking 策略示例

在 init 阶段执行 screening，在 on_bar 中执行 ranking。
支持动态筛选股票池和实时因子排名。

使用方法:
    1. 配置 MySQL 环境变量
    2. 运行: python examples/strategies/gm_intraday_ranking.py
"""

from datetime import date, timedelta
from quantcli.models.bar import MinuteBar
from quantcli.factors.screening_executor import ScreeningExecutor
from quantcli.factors.ranking_executor import RankingExecutor
from quantcli.datasources import MySQLDataSource
from quantcli.utils.symbol_utils import to_gm

# ==================== 策略配置 ====================

# 策略配置文件
CONFIG_PATH = "examples/strategies/ma10_yinliang_intraday.yaml"

# 固定股票池（MySQL 格式，可替换为你的自选股）
SYMBOLS = [
    '600519', '000001', '600036', '601398', '601988',  # 金融
    '600900', '600750', '600104', '601933', '600309',  # 消费
    '000725', '000063', '600703', '600460', '002594',  # 科技
    # ... 添加更多股票
]

# 转换为掘金格式
GM_SYMBOLS = [to_gm(s) for s in SYMBOLS]

# 分钟周期
PERIOD = "5"  # 5分钟周期

# ranking 频率（每 N 根 bar 执行一次）
RANKING_INTERVAL = 12  # 每小时执行一次 (12 * 5min = 60min)


# ==================== 掘金策略模板 ====================

# 注意：以下代码需要运行在掘金量化环境中
# 如果在本地测试，请注释掉 run_strategy 调用

try:
    from gm.api import strategy, set_token
    import os

    # 设置掘金 token
    GM_TOKEN = os.getenv("GM_TOKEN", "")
    if GM_TOKEN:
        set_token(GM_TOKEN)

    @strategy(
        name="日内 ranking 选股策略",
        init_symbols=GM_SYMBOLS,
        symbols=GM_SYMBOLS,
        frequency=f"{PERIOD}f",
        settings={
            "trade_ruler": {"enabled": True}
        }
    )
    def init(context):
        """策略初始化 - 在这里执行 screening"""
        print("=" * 50)
        print("策略初始化")
        print("=" * 50)

        # 初始化 MySQL 连接
        context.mysql = MySQLDataSource()
        print(f"MySQL 连接: {context.mysql._config['database']}")

        # === Screening 阶段 (init) ===
        print("\n[1/2] 执行 Screening...")
        context.screener = ScreeningExecutor(
            config_path=CONFIG_PATH,
            mysql_datasource=context.mysql
        )

        # 执行 screening（从 MySQL 获取数据并筛选）
        context.symbols = context.screener.run(
            symbols=None,  # 默认从 stock_list 获取全部
            lookback_days=30
        )

        if not context.symbols:
            print("警告: Screening 结果为空!")
            context.symbols = SYMBOLS[:10]  # 降级使用预设列表

        print(f"Screening 结果: {len(context.symbols)} 只股票")

        # 转换为掘金格式并订阅
        gm_symbols = [to_gm(s) for s in context.symbols]
        context.subscribe(gm_symbols)
        print(f"订阅股票: {gm_symbols[:5]}...")

        # === Ranking 阶段 (on_bar 中执行) ===
        print("\n[2/2] 初始化 RankingExecutor...")
        context.ranking_executor = RankingExecutor(
            config_path=CONFIG_PATH,
            mysql_datasource=context.mysql
        )

        # ranking 执行计数
        context.bar_count = 0

        print("\n策略初始化完成!")
        print(f"- Screening 候选: {len(context.symbols)} 只")
        print(f"- 分钟周期: {PERIOD} 分钟")
        print(f"- ranking 频率: 每 {RANKING_INTERVAL} 根 bar")

    def on_bar(context, bars):
        """on_bar 事件处理"""
        context.bar_count += 1

        for bar in bars:
            # 1. 转换为 MinuteBar dataclass（symbol 转 MySQL 格式）
            mysql_symbol = bar.symbol.split('.')[-1]
            minute_bar = MinuteBar.from_gm_bar(mysql_symbol, bar, PERIOD)

            # 2. 同步当前 bar 到 MySQL
            context.mysql.sync_minute_bar(minute_bar)

        # 3. 每隔 N 根 bar 执行一次 ranking
        if context.bar_count % RANKING_INTERVAL == 0:
            last_bar = bars[-1]
            mysql_symbol = last_bar.symbol.split('.')[-1]
            minute_bar = MinuteBar.from_gm_bar(mysql_symbol, last_bar, PERIOD)

            try:
                # 执行 ranking（仅对筛选后的股票）
                result = context.ranking_executor.run_on_bar(
                    bar=minute_bar,
                    candidate_symbols=context.symbols,
                    lookback_days=20
                )

                if result.empty:
                    print(f"[Bar {context.bar_count}] 无有效数据")
                    return

                # 4. 交易逻辑
                top_n = 5
                top_stocks = result.head(top_n)

                print(f"\n{'='*50}")
                print(f"[Bar {context.bar_count}] Ranking 结果")
                print(f"{'='*50}")
                print(f"候选: {len(context.symbols)} 只 | 有效: {len(result)} 只")
                print(f"\nTop {top_n}:")
                for _, row in top_stocks.iterrows():
                    print(f"  {row['symbol']}: score={row['score']:.4f}")

                # 买入 top 1
                symbol = top_stocks.iloc[0]['symbol']
                score = top_stocks.iloc[0]['score']

                # 获取当前持仓
                positions = context.get_positions()
                position_symbols = [p['symbol'] for p in positions]

                # 卖出不在 top 5 的持仓
                for pos in positions:
                    if pos['symbol'] not in top_stocks['symbol'].values:
                        context.order_target_percent(pos['symbol'], 0, 0, order_type='market')
                        print(f"卖出: {pos['symbol']}")

                # 买入 top 1
                if symbol not in position_symbols:
                    context.order_target_percent(symbol, 0.2, 0, order_type='market')
                    print(f"买入: {symbol} @ {score:.4f}")

            except Exception as e:
                print(f"ranking 执行失败: {e}")
                import traceback
                traceback.print_exc()

    def on_execution(context, execution):
        print(f"成交: {execution['symbol']} {execution['side']} {execution['exec_price']}")

    def on_order_status(context, order):
        if order['status'] == 'filled':
            print(f"订单成交: {order['symbol']} {order['side']} @ {order['avg_price']}")

    # 运行策略
    if __name__ == "__main__":
        from gm.api import run

        print("\n" + "=" * 50)
        print("启动日内 Ranking 选股策略")
        print("=" * 50)
        print(f"策略配置: {CONFIG_PATH}")
        print(f"股票池: 动态筛选")
        print(f"分钟周期: {PERIOD} 分钟")
        print("=" * 50 + "\n")

        run()

except ImportError:
    print("掘金 SDK 未安装，跳过策略运行")
    print("如需运行策略，请安装: pip install gm.api")
