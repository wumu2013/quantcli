"""QuantCLI 命令行界面

提供数据获取、因子计算、回测和配置管理命令。

Usage:
    quantcli --help
    quantcli data fetch --symbol 600519 --start 2020-01-01
    quantcli factor run -n momentum -e "(close / delay(close, 20)) - 1"
    quantcli backtest run -s dual_ma.py --start 2020-01-01
"""

import sys
from datetime import date, timedelta
from typing import Optional, Tuple

import click
import pandas as pd
from tabulate import tabulate

from .core import DataManager, DataConfig, FactorEngine, BacktestEngine, BacktestConfig, Strategy
from .factors import FactorDefinition
from .utils import parse_date, format_date, today, get_logger, TimeContext

logger = get_logger(__name__)


# =============================================================================
# 通用选项
# =============================================================================

def verbose_option(f):
    """Verbose output option"""
    def callback(ctx, param, value):
        ctx.ensure_object(dict)
        ctx.obj["verbose"] = value
        if value:
            import logging
            logging.basicConfig(level=logging.DEBUG)
    return click.option("-v", "--verbose", is_flag=True, help="Enable verbose output", callback=callback)(f)


def date_type(s: str) -> date:
    """Click type for date validation"""
    try:
        return parse_date(s)
    except Exception:
        raise click.BadParameter(f"Invalid date: {s}. Use YYYY-MM-DD format")


# =============================================================================
# 主命令
# =============================================================================

@click.group()
@click.version_option(version="0.1.0", prog_name="quantcli")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output", default=False)
@click.pass_context
def quantcli(ctx, verbose):
    """QuantCLI - 量化因子挖掘与回测工具"""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    logger.info(f"QuantCLI v0.1.0 started")


# =============================================================================
# Data 命令
# =============================================================================

@quantcli.group()
def data():
    """数据获取与管理"""
    pass


@data.command("fetch")
@click.argument("symbol", type=str)
@click.option("--start", type=date_type, required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", type=date_type, default=None, help="End date (YYYY-MM-DD)")
@click.option("--source", type=click.Choice(["akshare", "baostock", "mixed"]), default="mixed", help="Data source")
@click.option("--use-cache/--no-cache", default=True, help="Use cache")
@click.option("--output", type=click.Path(), default=None, help="Output file path")
@click.pass_context
def data_fetch(ctx, symbol, start, end, source, use_cache, output):
    """获取股票日线数据"""
    if end is None:
        end = today()

    click.echo(f"Fetching {symbol} data from {format_date(start)} to {format_date(end)}...")

    config = DataConfig(source=source)
    dm = DataManager(config)

    try:
        df = dm.get_daily(symbol, start, end, use_cache=use_cache)

        if df.empty:
            click.echo(f"No data found for {symbol}")
            return

        click.echo(f"Retrieved {len(df)} rows")

        # 数据统计
        if "close" in df.columns:
            click.echo(f"Close: {df['close'].min():.2f} - {df['close'].max():.2f}")

        # 输出到文件
        if output:
            if output.endswith(".csv"):
                df.to_csv(output, index=False)
            elif output.endswith(".parquet"):
                df.to_parquet(output, index=False)
            else:
                df.to_csv(output, index=False)
            click.echo(f"Saved to {output}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@data.group("cache")
@click.pass_context
def data_cache():
    """缓存管理"""
    pass


@data_cache.command("ls")
@click.pass_context
def data_cache_ls(ctx):
    """列出缓存文件"""
    config = DataConfig()
    dm = DataManager(config)
    sizes = dm.get_cache_size()

    if not sizes or "_total" not in sizes:
        click.echo("No cached data found")
        return

    rows = []
    for k, v in sizes.items():
        if k != "_total":
            rows.append([k, v])

    if rows:
        click.echo("Cached files:")
        click.echo(tabulate(rows, headers=["File", "Size"], tablefmt="simple"))
    else:
        click.echo("No cached files found")

    click.echo(f"\nTotal: {sizes.get('_total', '0')}")


@data_cache.command("clean")
@click.option("--older-than", type=int, default=None, help="Remove files older than N days")
@click.pass_context
def data_cache_clean(ctx, older_than):
    """清理缓存文件"""
    config = DataConfig()
    dm = DataManager(config)

    count = dm.clear_cache(older_than=older_than)
    click.echo(f"Cleaned {count} cache files")


@data.command("health")
@click.pass_context
def data_health(ctx):
    """检查数据源健康状态"""
    config = DataConfig()
    dm = DataManager(config)
    health = dm.health_check()

    click.echo("Data Manager Health:")
    for k, v in health.items():
        if k == "cache":
            continue
        click.echo(f"  {k}: {v}")


# =============================================================================
# Factors 命令 - 列出内置因子
# =============================================================================

@quantcli.group()
def factors():
    """内置因子管理"""
    pass


@factors.command("list")
@click.option("--json", is_flag=True, help="Output as JSON")
@click.pass_context
def factors_list(ctx, json):
    """列出所有内置 Alpha101 因子"""
    from .utils import builtin_factors_dir

    builtin_dir = builtin_factors_dir() / "alpha101"

    if not builtin_dir.exists():
        click.echo("No built-in factors found")
        return

    # 加载所有因子
    factors = []
    for f in sorted(builtin_dir.glob("alpha_*.yaml")):
        import yaml
        with open(f, "r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
            factors.append({
                "name": data.get("name", f.stem),
                "type": data.get("type", "technical"),
                "direction": data.get("direction", "neutral"),
                "description": data.get("description", ""),
                "file": f"alpha101/{f.name}"
            })

    if json:
        import json
        click.echo(json.dumps({"status": "success", "count": len(factors), "factors": factors}, ensure_ascii=False, indent=2))
        return

    click.echo(f"Built-in Alpha101 Factors ({len(factors)} total):\n")
    click.echo(f"{'File':<22} {'Type':<12} {'Direction':<10} Description")
    click.echo("-" * 60)
    for f in factors:
        click.echo(f"{f['file']:<22} {f['type']:<12} {f['direction']:<10} {f['description']}")


# =============================================================================
# Factor 命令
# =============================================================================

@quantcli.group()
def factor():
    """因子定义与计算"""
    pass


@factor.command("run")
@click.option("--name", "-n", required=True, help="Factor name")
@click.option("--expr", "-e", required=True, help="Factor expression/formula")
@click.option("--symbol", default="600519", help="Stock symbol for testing")
@click.option("--start", type=date_type, default="2020-01-01", help="Start date")
@click.option("--end", type=date_type, default=None, help="End date")
@click.option("--output", type=click.Path(), default=None, help="Output file path")
@click.pass_context
def factor_run(ctx, name, expr, symbol, start, end, output):
    """运行因子计算"""
    if end is None:
        end = today()

    click.echo(f"Computing factor '{name}'...")

    # 创建引擎
    config = DataConfig()
    dm = DataManager(config)
    engine = FactorEngine(dm)

    # 注册因子
    factor = FactorDefinition(name=name, type="technical", expr=expr)
    engine.register(factor)

    # 获取数据
    df = dm.get_daily(symbol, start, end)
    if df.empty:
        click.echo(f"No data for {symbol}")
        return

    # 添加 returns 列
    if "close" in df.columns:
        df = df.copy()
        df["returns"] = df["close"].pct_change()

    # 计算因子
    try:
        result = engine.compute(name, df)

        click.echo(f"Factor computed: {len(result)} values")
        if not result.empty:
            click.echo(f"  Mean: {result.mean():.4f}")
            click.echo(f"  Std: {result.std():.4f}")
            click.echo(f"  Min: {result.min():.4f}")
            click.echo(f"  Max: {result.max():.4f}")

        # 保存结果
        if output:
            result_df = result.reset_index()
            result_df.columns = ["date", name]
            result_df.to_csv(output, index=False)
            click.echo(f"Saved to {output}")

    except Exception as e:
        click.echo(f"Error computing factor: {e}", err=True)
        sys.exit(1)


@factor.command("eval")
@click.argument("name", type=str)
@click.option("--symbol", default="600519", help="Stock symbol")
@click.option("--start", type=date_type, default="2020-01-01", help="Start date")
@click.option("--end", type=date_type, default=None, help="End date")
@click.option("--method", type=click.Choice(["ic", "quantile", "full"]), default="ic", help="Evaluation method")
@click.pass_context
def factor_eval(ctx, name, symbol, start, end, method):
    """评估因子表现"""
    if end is None:
        end = today()

    click.echo(f"Evaluating factor '{name}'...")

    config = DataConfig()
    dm = DataManager(config)
    engine = FactorEngine(dm)

    df = dm.get_daily(symbol, start, end)
    if df.empty:
        click.echo(f"No data for {symbol}")
        return

    # 添加 returns 列
    df = df.copy()
    df["returns"] = df["close"].pct_change()

    try:
        if method == "ic":
            result = engine.evaluate_ic(name, df)
            click.echo(f"\nIC Analysis for {name}:")
            if "ic_stats" in result:
                stats = result["ic_stats"]
                click.echo(f"  IC Mean: {stats.get('ic_mean', 0):.4f}")
                click.echo(f"  IC Std: {stats.get('ic_std', 0):.4f}")
                click.echo(f"  IC IR: {stats.get('ic_ir', 0):.4f}")

        elif method == "quantile":
            result = engine.evaluate_quantiles(name, df)
            click.echo(f"\nQuantile Analysis for {name}:")
            click.echo(f"  Groups: {result.get('groups', 10)}")
            click.echo(f"  Long-Short Return: {result.get('long_short_return', 0):.4f}")

        elif method == "full":
            result = engine.evaluate_full(name, df)
            click.echo(f"\nFull Evaluation for {name}:")
            click.echo(f"  IC Mean: {result.ic_mean:.4f}")
            click.echo(f"  IC IR: {result.ic_ir:.4f}")
            click.echo(f"  Sample Size: {result.sample_size}")

    except Exception as e:
        click.echo(f"Error evaluating factor: {e}", err=True)
        sys.exit(1)


@factor.command("list")
@click.pass_context
def factor_list(ctx):
    """列出已注册的因子"""
    engine = FactorEngine()
    factors = engine.registry.list_all()

    if not factors:
        click.echo("No factors registered")
        return

    click.echo("Registered factors:")
    for name in factors:
        factor = engine.registry.get(name)
        if factor:
            click.echo(f"  - {name}: {factor.formula[:50]}...")


@factor.command("run-file")
@click.option("--file", "-f", required=True, type=click.Path(exists=True), help="Factor config YAML file")
@click.option("--symbol", default="600519", help="Stock symbol for testing")
@click.option("--start", type=date_type, default="2020-01-01", help="Start date")
@click.option("--end", type=date_type, default=None, help="End date")
@click.option("--output", type=click.Path(), default=None, help="Output file path")
@click.pass_context
def factor_run_file(ctx, file, symbol, start, end, output):
    """从 YAML 配置文件运行因子计算"""
    from .factors import load_strategy, FactorComputer

    if end is None:
        end = today()

    click.echo(f"Loading factor config from {file}...")

    try:
        config = load_strategy(file)
        click.echo(f"Config: {config.name} (v{config.version})")

        # 创建数据管理器
        config_data = DataConfig()
        dm = DataManager(config_data)

        # 获取数据
        df = dm.get_daily(symbol, start, end)
        if df.empty:
            click.echo(f"No data for {symbol}")
            return

        click.echo(f"Data: {len(df)} rows")

        # 获取权重配置中的因子
        weights = config.ranking.get("weights", {})
        from .factors.loader import load_all_factors
        factors = load_all_factors(weights, file)

        # 计算因子
        computer = FactorComputer()
        factor_data = computer.compute_all_factors(factors, {symbol: df}, {}, [symbol])

        # 显示结果
        click.echo("\nFactor Results:")
        if factor_data:
            for row in factor_data:
                for name, value in row.items():
                    if name != "symbol":
                        click.echo(f"  {name}: {value:.4f}" if isinstance(value, (int, float)) else f"  {name}: {value}")

        # 保存结果
        if output and factor_data:
            result_df = pd.DataFrame(factor_data)
            result_df.to_csv(output, index=False)
            click.echo(f"\nSaved to {output}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@factor.command("score")
@click.option("--file", "-f", required=True, type=click.Path(exists=True), help="Factor config YAML file")
@click.option("--symbols", default=None, help="Stock symbols (comma-separated)")
@click.option("--start", type=date_type, default="2020-01-01", help="Start date")
@click.option("--end", type=date_type, default=None, help="End date")
@click.option("--top", type=int, default=None, help="Show top N results")
@click.option("--output", type=click.Path(), default=None, help="Output file path")
@click.pass_context
def factor_score(ctx, file, symbols, start, end, top, output):
    """根据 YAML 配置文件对股票进行评分选股"""
    from .factors import load_strategy, FactorPipeline

    if end is None:
        end = today()

    click.echo(f"Loading factor config from {file}...")

    try:
        config = load_strategy(file)
        click.echo(f"Config: {config.name} (v{config.version})")

        # 创建数据管理器
        config_data = DataConfig()
        dm = DataManager(config_data)

        # 解析股票列表
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(",")]
        else:
            symbol_list = ["600519"]

        click.echo(f"Fetching data for {len(symbol_list)} symbols...")

        # 获取多只股票数据
        stock_data = {}
        for symbol in symbol_list:
            df = dm.get_daily(symbol, start, end)
            if not df.empty:
                stock_data[symbol] = df

        if not stock_data:
            click.echo("No data found for any symbol")
            return

        click.echo(f"Got data for {len(stock_data)} symbols")

        # 使用 Pipeline 执行评分
        pipeline = FactorPipeline(file)
        results = pipeline.run(symbol_list, end, stock_data, pd.DataFrame(), limit=top)

        if results.empty:
            click.echo("No results")
            return

        # 显示结果
        click.echo("\n=== Scoring Results ===")
        click.echo(results.to_string(index=False))

        # 保存结果
        if output:
            results.to_csv(output, index=False)
            click.echo(f"\nSaved to {output}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        import traceback
        if ctx.obj.get("verbose"):
            traceback.print_exc()
        sys.exit(1)


# =============================================================================
# Filter 命令
# =============================================================================

@quantcli.group()
def filter():
    """多阶段因子筛选"""
    pass


@filter.command("run")
@click.option("--file", "-f", required=True, type=click.Path(exists=True), help="Strategy config YAML file")
@click.option("--symbols", default=None, help="Stock symbols (comma-separated, default: all)")
@click.option("--start", type=date_type, default=None, help="Start date for price data (default: 60 days ago)")
@click.option("--end", type=date_type, default=None, help="End date for price data")
@click.option("--as-of", type=date_type, default=None, help="Time baseline date (for filtering as of this date)")
@click.option("--fundamental-date", type=date_type, default=None, help="Date for fundamental data")
@click.option("--top", type=int, default=None, help="Show top N results")
@click.option("--output", type=click.Path(), default=None, help="Output file path")
@click.option("--intraday/--no-intraday", default=True, help="Enable intraday data fetching")
@click.pass_context
def filter_run(ctx, file, symbols, start, end, as_of, fundamental_date, top, output, intraday):
    """运行多阶段因子筛选（基本面筛选 + 日线筛选 + 权重排序）"""
    from .factors.pipeline import FactorPipeline
    from .datasources import create_datasource

    # 设置时间基线
    if as_of is not None:
        TimeContext.set_date(as_of)
        click.echo(f"Time baseline set to: {format_date(as_of)}")

    if end is None:
        end = today()
    if start is None:
        start = end - timedelta(days=60)  # 默认最近60天
    if fundamental_date is None:
        fundamental_date = end

    click.echo(f"Loading strategy config from {file}...")

    try:
        pipeline = FactorPipeline(file)
        click.echo(f"Strategy: {pipeline.config.name} (v{pipeline.config.version})")

        # 检查是否为多阶段配置
        screening_config = pipeline.config.screening
        is_multi_stage = bool(screening_config.get("fundamental_conditions") or
                              screening_config.get("daily_conditions"))
        intraday_config = getattr(pipeline.config, 'intraday', {})
        has_intraday = bool(intraday_config.get("weights", {}))

        # 解析股票列表
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(",")]
        else:
            # 获取全部股票
            click.echo("Fetching all stock symbols...")
            source = create_datasource("mixed")
            stocks_df = source.get_stock_list()
            symbol_list = stocks_df["symbol"].tolist()
            click.echo(f"Found {len(symbol_list)} stocks")

        if not symbol_list:
            click.echo("No symbols to filter")
            return

        # ==================== 多阶段流程 ====================
        if is_multi_stage and intraday and has_intraday:
            # 完整多阶段流程：基本面 → 日线 → 分钟
            click.echo("Running multi-stage filtering...")

            # 阶段1: 基本面筛选
            click.echo(f"\n=== Stage 1: Fundamental Screening ===")
            click.echo(f"Fetching fundamental data for {len(symbol_list)} symbols...")
            source = create_datasource("mixed")
            fundamental_data = source.get_fundamental(symbol_list, fundamental_date)
            click.echo(f"Got fundamental data for {len(fundamental_data)} symbols")

            # 基本面条件筛选
            fundamental_conditions = screening_config.get("fundamental_conditions", [])
            candidates = pipeline.screening_only(symbol_list, fundamental_data) if fundamental_conditions else symbol_list
            if fundamental_conditions:
                click.echo(f"After fundamental screening: {len(candidates)}")

            if not candidates:
                click.echo("No candidates after fundamental screening")
                return

            # 阶段2: 日线筛选
            click.echo(f"\n=== Stage 2: Daily Screening ===")
            daily_conditions = screening_config.get("daily_conditions", [])
            if daily_conditions:
                # 只对候选获取日线数据
                click.echo(f"Fetching daily data for {len(candidates)} candidates...")
                dm = DataManager(DataConfig(source="mixed"))

                price_data = {}
                for symbol in candidates:
                    try:
                        df = dm.get_daily(symbol, start, end)
                        if not df.empty:
                            df = df.copy()
                            df["returns"] = df["close"].pct_change()
                            price_data[symbol] = df
                    except Exception as e:
                        logger.warning(f"Failed to get daily data for {symbol}: {e}")
                        continue

                click.echo(f"Got daily data for {len(price_data)} symbols")

                # 执行日线条件筛选
                if price_data and daily_conditions:
                    # 收集价格数据
                    candidate_price_data = []
                    for symbol in candidates:
                        if symbol in price_data:
                            df = price_data[symbol].copy()
                            df["symbol"] = symbol
                            candidate_price_data.append(df)

                    if candidate_price_data:
                        price_df = pd.concat(candidate_price_data, ignore_index=True)
                        latest_date = price_df["date"].max()
                        latest_df = price_df[price_df["date"] == latest_date].copy()

                        passed = pipeline._evaluate_screening(daily_conditions, latest_df)
                        candidates = [
                            s for s in candidates
                            if s in latest_df["symbol"].values and
                               passed.get(latest_df[latest_df["symbol"] == s].index[0], True)
                        ]
                        click.echo(f"After daily screening: {len(candidates)}")
            else:
                price_data = {}

            if not candidates:
                click.echo("No candidates after daily screening")
                return

            # 阶段3: 分钟级排名
            click.echo(f"\n=== Stage 3: Intraday Ranking ===")
            click.echo(f"Fetching intraday data for {len(candidates)} candidates...")
            source = create_datasource("mixed")

            intraday_data = {}
            for symbol in candidates:
                try:
                    df = source.get_intraday(symbol, start, end)
                    if not df.empty:
                        intraday_data[symbol] = df
                except Exception as e:
                    logger.warning(f"Failed to get intraday data for {symbol}: {e}")
                    continue

            click.echo(f"Got intraday data for {len(intraday_data)} symbols")

            # 执行分钟级排名
            results = pipeline.run_multi_stage(
                symbols=candidates,
                date=fundamental_date,
                price_data=price_data,
                intraday_data=intraday_data,
                fundamental_data=fundamental_data,
                limit=top
            )

        elif is_multi_stage:
            # 简化的多阶段：基本面 → 日线
            click.echo("Running simplified multi-stage filtering...")

            # 阶段1: 基本面
            click.echo(f"\n=== Stage 1: Fundamental Screening ===")
            click.echo(f"Fetching fundamental data for {len(symbol_list)} symbols...")
            source = create_datasource("mixed")
            fundamental_data = source.get_fundamental(symbol_list, fundamental_date)
            click.echo(f"Got fundamental data for {len(fundamental_data)} symbols")

            candidates = pipeline.screening_only(symbol_list, fundamental_data)
            click.echo(f"After fundamental screening: {len(candidates)}")

            if not candidates:
                click.echo("No candidates after fundamental screening")
                return

            # 阶段2: 日线
            click.echo(f"\n=== Stage 2: Daily Screening ===")
            click.echo(f"Fetching daily data for {len(candidates)} candidates...")
            dm = DataManager(DataConfig(source="mixed"))

            price_data = {}
            for symbol in candidates:
                try:
                    df = dm.get_daily(symbol, start, end)
                    if not df.empty:
                        df = df.copy()
                        df["returns"] = df["close"].pct_change()
                        price_data[symbol] = df
                except Exception as e:
                    logger.warning(f"Failed to get daily data for {symbol}: {e}")
                    continue

            click.echo(f"Got daily data for {len(price_data)} symbols")

            # 获取分钟数据（用于混合 ranking）
            click.echo(f"Fetching intraday data for {len(candidates)} candidates...")
            intraday_data = {}
            for symbol in candidates:
                try:
                    df = source.get_intraday(symbol, start, end)
                    if not df.empty:
                        intraday_data[symbol] = df
                except Exception as e:
                    logger.warning(f"Failed to get intraday data for {symbol}: {e}")
                    continue

            click.echo(f"Got intraday data for {len(intraday_data)} symbols")

            results = pipeline.run_multi_stage(
                symbols=candidates,
                date=fundamental_date,
                price_data=price_data,
                intraday_data=intraday_data,
                fundamental_data=fundamental_data,
                limit=top
            )

        else:
            # 原有单阶段流程
            click.echo("Running single-stage filtering...")

            click.echo(f"Fetching fundamental data for {len(symbol_list)} symbols...")
            source = create_datasource("mixed")
            fundamental_data = source.get_fundamental(symbol_list, fundamental_date)
            click.echo(f"Got fundamental data for {len(fundamental_data)} symbols")

            candidates = pipeline.screening_only(symbol_list, fundamental_data)
            click.echo(f"Candidates after screening: {len(candidates)}")

            if not candidates:
                click.echo("No candidates after screening")
                return

            click.echo(f"Fetching price data for {len(candidates)} candidates...")
            dm = DataManager(DataConfig(source="mixed"))

            price_data = {}
            for symbol in candidates:
                try:
                    df = dm.get_daily(symbol, start, end)
                    if not df.empty:
                        df = df.copy()
                        df["returns"] = df["close"].pct_change()
                        price_data[symbol] = df
                except Exception as e:
                    logger.warning(f"Failed to get data for {symbol}: {e}")
                    continue

            click.echo(f"Got price data for {len(price_data)} symbols")

            results = pipeline.run(
                symbols=candidates,
                date=fundamental_date,
                price_data=price_data,
                fundamental_data=fundamental_data,
                limit=top
            )

        if results.empty:
            click.echo("No results")
            return

        # 显示结果
        click.echo("\n=== Filter Results ===")
        click.echo(results.to_string(index=False))

        # 保存结果
        if output:
            results.to_csv(output, index=False)
            click.echo(f"\nSaved to {output}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        import traceback
        if ctx.obj.get("verbose"):
            traceback.print_exc()
        sys.exit(1)
    finally:
        TimeContext.reset()


@filter.command("screening")
@click.option("--file", "-f", required=True, type=click.Path(exists=True), help="Strategy config YAML file")
@click.option("--symbols", default=None, help="Stock symbols (comma-separated)")
@click.option("--fundamental-date", type=date_type, default=None, help="Date for fundamental data")
@click.option("--output", type=click.Path(), default=None, help="Output file path")
@click.pass_context
def filter_screening(ctx, file, symbols, fundamental_date, output):
    """仅执行筛选阶段"""
    from .factors.pipeline import FactorPipeline
    from .datasources import create_datasource

    if fundamental_date is None:
        fundamental_date = today()

    click.echo(f"Loading strategy config from {file}...")

    try:
        pipeline = FactorPipeline(file)
        click.echo(f"Strategy: {pipeline.config.name}")

        # 解析股票列表
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(",")]
        else:
            source = create_datasource("mixed")
            stocks_df = source.get_stock_list()
            symbol_list = stocks_df["symbol"].tolist()

        # 获取基本面数据
        source = create_datasource("mixed")
        fundamental_data = source.get_fundamental(symbol_list, fundamental_date)

        # 执行筛选
        candidates = pipeline.screening_only(symbol_list, fundamental_data)

        click.echo(f"\nScreening Results: {len(candidates)} stocks passed")
        if candidates:
            click.echo(", ".join(candidates[:50]))
            if len(candidates) > 50:
                click.echo(f"... and {len(candidates) - 50} more")

        # 保存结果
        if output:
            with open(output, "w") as f:
                for s in candidates:
                    f.write(f"{s}\n")
            click.echo(f"\nSaved to {output}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# =============================================================================
# Backtest 命令
# =============================================================================

@quantcli.group()
def backtest():
    """回测引擎"""
    pass


@backtest.command("run")
@click.option("--strategy", "-s", required=True, type=str, help="Strategy file (.yaml)")
@click.option("--symbol", "-t", default=None, help="Target symbol (optional, for single stock backtest)")
@click.option("--start", type=date_type, default="2020-01-01", help="Start date")
@click.option("--end", type=date_type, default=None, help="End date")
@click.option("--as-of", type=date_type, default=None, help="Time baseline date (for backtesting as of this date)")
@click.option("--capital", type=float, default=None, help="Initial capital (default from strategy)")
@click.option("--fee", type=float, default=None, help="Transaction fee rate (default from strategy)")
@click.option("--datasource", "-d", type=str, default="mysql", help="Data source (default: mysql)")
@click.pass_context
def backtest_run(ctx, strategy, symbol, start, end, as_of, capital, fee, datasource):
    """运行回测 (YAML 策略文件)"""
    from pathlib import Path

    # 回测强制要求使用 MySQL 数据源
    if datasource != "mysql":
        click.echo(f"Error: Backtest requires MySQL data source, got: {datasource}", err=True)
        click.echo("\nBacktest must use MySQL for efficient batch data loading.", err=True)
        click.echo("Please configure MySQL environment variables:", err=True)
        click.echo("  export MYSQL_HOST=localhost", err=True)
        click.echo("  export MYSQL_PORT=3306", err=True)
        click.echo("  export MYSQL_USER=root", err=True)
        click.echo("  export MYSQL_PASSWORD=xxx", err=True)
        click.echo("  export MYSQL_DATABASE=quantcli", err=True)
        sys.exit(1)

    # 设置时间基线
    if as_of is not None:
        TimeContext.set_date(as_of)
        click.echo(f"Time baseline set to: {format_date(as_of)}")

    if end is None:
        end = today()

    strategy_path = Path(strategy)

    # 验证文件存在且是 YAML
    if not strategy_path.exists():
        click.echo(f"Error: Strategy file not found: {strategy}", err=True)
        sys.exit(1)

    if strategy_path.suffix != ".yaml":
        click.echo(f"Error: Only .yaml strategy files are supported: {strategy}", err=True)
        sys.exit(1)

    _run_yaml_backtest(ctx, strategy, symbol, start, end, capital, fee)

    TimeContext.reset()


def _run_yaml_backtest(ctx, strategy_path, symbol, start, end, capital, fee):
    """运行 YAML 策略回测 (MySQL 数据源)"""
    from quantcli.core.backtest import YAMLBacktestEngine
    from quantcli.datasources import create_datasource

    datasource = "mysql"

    if symbol:
        click.echo(f"Running strategy backtest for symbol: {symbol}")
    else:
        click.echo(f"Running strategy backtest...")
    click.echo(f"Strategy: {strategy_path}")
    click.echo(f"Data source: {datasource}")

    # 创建数据源并检查就绪状态
    try:
        ds = create_datasource(datasource)
        health = ds.health_check()

        if health.get("status") != "ok":
            click.echo(f"Error: Data source '{datasource}' is not ready", err=True)
            error_info = health.get("error", "Unknown error")
            click.echo(f"  {error_info}", err=True)
            click.echo("\nHint: Make sure MySQL is running and environment variables are set:", err=True)
            click.echo("  export MYSQL_HOST=localhost", err=True)
            click.echo("  export MYSQL_USER=root", err=True)
            click.echo("  export MYSQL_PASSWORD=xxx", err=True)
            click.echo("  export MYSQL_DATABASE=quantcli", err=True)
            sys.exit(1)

        # 显示数据源状态
        if "daily_prices_count" in health:
            click.echo(f"  Daily prices: {health['daily_prices_count']} records")

    except ImportError as e:
        click.echo(f"Error: MySQL data source not available: {e}", err=True)
        click.echo("  Install pymysql: pip install pymysql", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: Failed to connect to MySQL: {e}", err=True)
        sys.exit(1)

    # 创建回测引擎
    bt_config = BacktestConfig(
        initial_capital=capital or 1000000.0,
        fee=fee or 0.0003
    )
    engine = YAMLBacktestEngine(ds, bt_config)

    # 加载策略
    try:
        engine.load_strategy(strategy_path)
    except Exception as e:
        click.echo(f"Error loading strategy: {e}", err=True)
        sys.exit(1)

    # 如果指定了 symbol，修改策略配置进行单股票回测
    if symbol:
        engine.strategy_config.backtest.entry = engine.strategy_config.backtest.entry or type(engine.strategy_config.backtest.entry)()
        # 将筛选条件改为只包含指定股票
        engine.strategy_config.screening = {"conditions": []}
        engine.target_symbol = symbol

    # 覆盖策略配置的资金和费率
    if capital is not None:
        engine.config.initial_capital = capital
    if fee is not None:
        engine.config.fee = fee

    # 运行回测
    try:
        result = engine.run(start, end)

        click.echo(f"\n=== Backtest Results ===")
        click.echo(f"Strategy: {engine.strategy_config.name}")
        click.echo(f"Period: {start} to {end}")
        click.echo(f"Total Return: {result.total_return:.2%}")
        click.echo(f"Annual Return: {result.annual_return:.2%}")
        click.echo(f"Max Drawdown: {result.max_drawdown:.2%}")
        click.echo(f"Sharpe Ratio: {result.sharpe:.2f}")
        click.echo(f"Win Rate: {result.win_rate:.2%}")
        click.echo(f"Total Trades: {result.total_trades}")

        if not result.trades.empty and len(result.trades) > 0:
            click.echo(f"\n=== Recent Trades ===")
            recent = result.trades.tail(10)
            for _, trade in recent.iterrows():
                pnl_str = f"PnL: {trade.get('pnl', 0):.2f}" if 'pnl' in trade else ""
                click.echo(f"{trade['date']} {trade['symbol']} {trade['side']} "
                          f"@{trade['price']:.2f} qty={trade['quantity']} {pnl_str}")

    except Exception as e:
        import traceback
        click.echo(f"Error running backtest: {e}", err=True)
        traceback.print_exc()
        sys.exit(1)


@backtest.command("list")
@click.pass_context
def backtest_list(ctx):
    """列出历史回测结果"""
    click.echo("Historical backtests:")
    click.echo("(Not implemented yet)")


# =============================================================================
# Analyze 命令 - 因子 IC/IR 分析
# =============================================================================

@quantcli.group()
def analyze():
    """因子分析与评估"""
    pass


def _compute_ic(factor_values: pd.Series, forward_returns: pd.Series, method: str = 'spearman') -> float:
    """计算信息系数 IC"""
    valid_idx = factor_values.dropna().index.intersection(forward_returns.dropna().index)
    if len(valid_idx) < 10:
        return np.nan

    fv = factor_values.loc[valid_idx]
    fr = forward_returns.loc[valid_idx]

    if method == 'spearman':
        return fv.corr(fr, method='spearman')
    return fv.corr(fr)


def _compute_rolling_ic(factor_values: pd.Series, forward_returns: pd.Series,
                         window: int = 60, method: str = 'spearman') -> pd.Series:
    """计算滚动 IC 序列"""
    ic_list = []
    dates = factor_values.dropna().index

    for i in range(window, len(dates)):
        start_idx = i - window
        end_idx = i

        window_fv = factor_values.iloc[start_idx:end_idx]
        window_fr = forward_returns.iloc[start_idx:end_idx]

        ic = _compute_ic(window_fv, window_fr, method)
        if not np.isnan(ic):
            ic_list.append({'date': dates[i], 'ic': ic})

    return pd.DataFrame(ic_list).set_index('date')['ic']


def _compute_ir(ic_series: pd.Series, annualized: bool = True) -> Tuple[float, float, float]:
    """计算信息比率 IR"""
    ic_mean = ic_series.mean()
    ic_std = ic_series.std()

    if np.isnan(ic_mean) or np.isnan(ic_std) or ic_std == 0:
        return np.nan, ic_mean, ic_std

    ir = ic_mean / ic_std

    if annualized:
        # 年化 IR
        n_periods = len(ic_series)
        years = n_periods / 252
        if years > 0:
            ir = ir * np.sqrt(years)
            ic_mean = ic_mean * np.sqrt(252)

    return ir, ic_mean, ic_std


@analyze.command("ic")
@click.option("--expr", "-e", required=True, help="Factor expression")
@click.option("--name", "-n", default="factor", help="Factor name")
@click.option("--symbol", default="600519", help="Stock symbol")
@click.option("--start", type=date_type, default="2020-01-01", help="Start date")
@click.option("--end", type=date_type, default=None, help="End date")
@click.option("--period", type=int, default=5, help="Forward return period (days)")
@click.option("--window", type=int, default=60, help="Rolling IC window")
@click.option("--method", type=click.Choice(["pearson", "spearman"]), default="spearman", help="IC calculation method")
@click.pass_context
def analyze_ic(ctx, expr, name, symbol, start, end, period, window, method):
    """计算因子 IC（信息系数）和 IR（信息比率）"""
    from .parser.formula import FormulaParser

    if end is None:
        end = today()

    click.echo(f"Analyzing factor: {name}")
    click.echo(f"Expression: {expr}")
    click.echo(f"Symbol: {symbol}, Period: {start} to {end}")
    click.echo(f"Forward period: {period} days, Window: {window}")

    # 获取数据
    config = DataConfig()
    dm = DataManager(config)
    df = dm.get_daily(symbol, start, end)

    if df.empty:
        click.echo(f"No data for {symbol}", err=True)
        sys.exit(1)

    click.echo(f"Data rows: {len(df)}")

    # 准备数据
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    # 计算未来收益
    close = df['close']
    forward_returns = close.shift(-period) / close - 1

    # 计算因子值
    parser = FormulaParser()
    try:
        factor_values = parser.evaluate(expr, df)
        if isinstance(factor_values, pd.DataFrame):
            factor_values = factor_values.iloc[:, 0]
    except Exception as e:
        click.echo(f"Error evaluating expression: {e}", err=True)
        sys.exit(1)

    # 整体 IC
    ic_total = _compute_ic(factor_values, forward_returns, method)

    # 滚动 IC
    ic_rolling = _compute_rolling_ic(factor_values, forward_returns, window, method)

    # IR
    ir, ic_mean, ic_std = _compute_ir(ic_rolling)

    # IC 正值占比
    ic_positive_pct = (ic_rolling > 0).sum() / len(ic_rolling) * 100 if len(ic_rolling) > 0 else 0

    # 显示结果
    click.echo(f"\n{'='*50}")
    click.echo(f"IC/IR Analysis Results")
    click.echo(f"{'='*50}")
    click.echo(f"  Overall IC ({method}):    {ic_total:+.4f}" if not np.isnan(ic_total) else "  Overall IC:    N/A")
    click.echo(f"  Rolling IC Mean (ann):     {ic_mean:+.4f}")
    click.echo(f"  Rolling IC Std:           {ic_std:+.4f}")
    click.echo(f"  IR (annualized):          {ir:+.4f}" if not np.isnan(ir) else "  IR:             N/A")
    click.echo(f"  IC > 0 ratio:             {ic_positive_pct:.1f}%")
    click.echo(f"  Samples:                  {len(ic_rolling)}")

    # 有效性评级
    click.echo(f"\n  Effectiveness Rating:")
    ic_abs = abs(ic_mean)
    ir_abs = abs(ir) if not np.isnan(ir) else 0

    if ic_abs > 0.1 or ir_abs > 0.5:
        rating = "★★★ Strong Factor"
    elif ic_abs > 0.05 or ir_abs > 0.3:
        rating = "★★☆ Moderate Factor"
    elif ic_abs > 0.02:
        rating = "★☆☆ Weak Factor"
    else:
        rating = "☆☆☆ Invalid Factor"

    click.echo(f"    {rating}")

    # IC 方向提示
    if ic_total > 0.02:
        click.echo(f"    Direction: Positive (long bias)")
    elif ic_total < -0.02:
        click.echo(f"    Direction: Negative (short bias)")
    else:
        click.echo(f"    Direction: Neutral")


@analyze.command("batch")
@click.option("--dir", "-d", required=True, help="Factor directory to analyze")
@click.option("--symbol", default="600519", help="Stock symbol")
@click.option("--start", type=date_type, default="2020-01-01", help="Start date")
@click.option("--end", type=date_type, default=None, help="End date")
@click.option("--period", type=int, default=5, help="Forward return period (days)")
@click.option("--window", type=int, default=60, help="Rolling IC window")
@click.option("--top", type=int, default=10, help="Show top N factors")
@click.option("--output", type=click.Path(), default=None, help="Output CSV file")
@click.pass_context
def analyze_batch(ctx, dir, symbol, start, end, period, window, top, output):
    """批量分析目录下所有因子并排序"""
    from pathlib import Path
    import yaml

    if end is None:
        end = today()

    factor_dir = Path(dir)
    if not factor_dir.exists():
        click.echo(f"Directory not found: {dir}", err=True)
        sys.exit(1)

    # 查找所有 YAML 文件
    yaml_files = list(factor_dir.glob("*.yaml")) + list(factor_dir.glob("*.yml"))
    if not yaml_files:
        click.echo(f"No YAML files found in {dir}", err=True)
        sys.exit(1)

    click.echo(f"Found {len(yaml_files)} factor files in {dir}")
    click.echo(f"Analyzing with period={period}d, window={window}...\n")

    # 获取数据
    config = DataConfig()
    dm = DataManager(config)
    df = dm.get_daily(symbol, start, end)

    if df.empty:
        click.echo(f"No data for {symbol}", err=True)
        sys.exit(1)

    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    close = df['close']
    forward_returns = close.shift(-period) / close - 1

    parser = FormulaParser()

    results = []
    for fp in yaml_files:
        try:
            with open(fp) as f:
                factor_def = yaml.safe_load(f)

            name = factor_def.get('name', fp.stem)
            expr = factor_def.get('expr')

            if not expr:
                continue

            # 计算因子
            factor_values = parser.evaluate(expr, df)
            if isinstance(factor_values, pd.DataFrame):
                factor_values = factor_values.iloc[:, 0]

            # IC 分析
            ic_rolling = _compute_rolling_ic(factor_values, forward_returns, window)
            ir, ic_mean, ic_std = _compute_ir(ic_rolling)
            ic_positive_pct = (ic_rolling > 0).sum() / len(ic_rolling) * 100 if len(ic_rolling) > 0 else 0
            ic_total = _compute_ic(factor_values, forward_returns)

            results.append({
                'name': name,
                'file': str(fp),
                'ic_total': ic_total,
                'ic_mean': ic_mean,
                'ic_std': ic_std,
                'ir': ir,
                'ic_positive_pct': ic_positive_pct,
                'samples': len(ic_rolling)
            })

        except Exception as e:
            logger.warning(f"Failed to analyze {fp}: {e}")
            continue

    if not results:
        click.echo("No factors analyzed successfully")
        sys.exit(1)

    # 按 IR 排序
    results.sort(key=lambda x: abs(x.get('ir', 0) or 0), reverse=True)

    # 显示结果
    click.echo(f"{'Rank':<4} {'Factor Name':<25} {'IC(total)':<10} {'IC(mean)':<10} {'IR':<10} {'Rating'}")
    click.echo("-" * 80)

    for i, r in enumerate(results[:top], 1):
        ic_total = r.get('ic_total')
        ic_mean = r.get('ic_mean', 0) or 0
        ir = r.get('ir', 0) or 0

        ic_total_str = f"{ic_total:+.4f}" if ic_total and not np.isnan(ic_total) else "N/A"
        ic_mean_str = f"{ic_mean:+.4f}"
        ir_str = f"{ir:+.4f}" if ir and not np.isnan(ir) else "N/A"

        # 评级
        if abs(ir) > 0.5:
            rating = "★★★"
        elif abs(ir) > 0.3:
            rating = "★★☆"
        elif abs(ir) > 0.1:
            rating = "★☆☆"
        else:
            rating = "☆☆☆"

        click.echo(f"{i:<4} {r['name']:<25} {ic_total_str:<10} {ic_mean_str:<10} {ir_str:<10} {rating}")

    # 保存结果
    if output:
        results_df = pd.DataFrame(results)
        results_df.to_csv(output, index=False)
        click.echo(f"\nSaved to {output}")


# =============================================================================
# Config 命令
# =============================================================================

@quantcli.group()
def config():
    """配置管理"""
    pass


@config.command("show")
@click.pass_context
def config_show(ctx):
    """显示当前配置"""
    config = DataConfig()
    click.echo("QuantCLI Configuration:")
    click.echo(f"  data.source: {config.source}")
    click.echo(f"  data.cache_dir: {config.cache_dir}")
    click.echo(f"  data.parallel: {config.parallel}")
    click.echo(f"  data.fillna: {config.fillna}")
    click.echo(f"  data.outlier_method: {config.outlier_method}")
    click.echo(f"  data.outlier_threshold: {config.outlier_threshold}")


@config.command("set")
@click.argument("key", type=str)
@click.argument("value", type=str)
@click.pass_context
def config_set(ctx, key, value):
    """设置配置项"""
    click.echo(f"Setting {key} = {value}")
    # TODO: 实现配置持久化
    click.echo("(Configuration persistence not implemented yet)")


# =============================================================================
# 辅助函数
# =============================================================================

# 入口点
# =============================================================================

def main():
    """CLI 入口点"""
    quantcli(obj={})


if __name__ == "__main__":
    main()
