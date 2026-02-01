# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**QuantCLI** - A multi-factor stock selection CLI tool for quantitative research.

**AI Agent Friendly**: Designed for AI Agent integration with:
- JSON output mode (`--json`) for structured data
- Claude Code Skill support (`/skill multi-factor-strategy`)
- Idempotent APIs for safe retries
- Alpha101 factor library examples

**Target Users**: Individual quant researchers, students, part-time investors, AI Agents

## Core Design Principles

- **Let it Crash**: Fail fast, fail loud. No tolerance for silent errors. Force correctness.
- **YAGNI**: You Aren't Gonna Need It. Resist over-engineering. Solve today's problems.
- **80/20 Rule**: 80% of use cases covered by 20% of features.
- **DataFrame First**: All APIs return/accept `pd.DataFrame`, not `List[Dict]`.

## Architecture

```
quantcli/
├── datasources/      # 数据源适配器 (akshare, baostock, mixed, mysql)
├── parser/           # 公式表达式解析器 (40+ 内置函数)
│   ├── formula.py    # 核心解析器
│   └── constants.py  # BUILTIN_FUNCTIONS, COLUMN_ALIASES
├── core/             # 核心引擎
│   ├── data.py       # DataManager: 缓存、清洗
│   ├── factor.py     # FactorEngine, Factor, FactorRegistry
│   └── backtest.py   # BacktestEngine, YAMLBacktestEngine
├── factors/          # 因子配置 (推荐使用新 API)
│   ├── base.py       # 数据类 (FactorDefinition, StrategyConfig, BacktestConfig)
│   ├── loader.py     # load_strategy(), load_factor(), load_all_factors()
│   ├── screening.py  # ScreeningEvaluator
│   ├── compute.py    # FactorComputer (返回 DataFrame)
│   ├── ranking.py    # FactorRanker, ScoringEngine
│   └── pipeline.py   # FactorPipeline: 多阶段编排
├── cli.py            # CLI 入口点
└── utils/            # 工具函数
```

### Multi-Stage Filter Pipeline Flow

```
Stage 1: fundamental_data → fundamental_conditions → candidates
Stage 2: price_data → daily_conditions → filtered candidates
Stage 3: factors → weight fusion + conditions + bonuses → ranked results
```

## CLI Commands

```bash
# Filter 命令 (推荐) - 多阶段因子筛选
quantcli filter run -f examples/strategies/pe_roe_ma10.yaml --top 50

# Factor 命令 - 单因子计算
quantcli factor run -n momentum -e "(close / delay(close, 20)) - 1"
quantcli factor run-file -f examples/strategies/pe_roe_ma10.yaml --symbol 600519

# Analyze 命令 - IC/IR 因子有效性分析
quantcli analyze ic -e "(close / delay(close, 20)) - 1" -n "20日动量" --period 5
quantcli analyze batch -d examples/alpha101/alpha/ --top 10

# Data 命令
quantcli data fetch 600519 --start 2020-01-01
quantcli data cache ls

# Expr 命令 - 列出可用表达式
quantcli expr list          # 列出所有函数和字段
quantcli expr functions     # 列出内置函数 (30个)
quantcli expr columns       # 列出字段别名 (9个)

# Backtest 命令 (强制使用 MySQL 数据源)
quantcli backtest run -s examples/strategies/my_strategy.yaml --start 2020-01-01
quantcli backtest run -s strategy.yaml --symbol 600519  # 单股票回测
```

## Key APIs (NEW - Recommended)

### Load Strategy
```python
from quantcli.factors.loader import load_strategy, load_all_factors
from quantcli.factors.compute import FactorComputer
from quantcli.factors.ranking import ScoringEngine

# Load strategy config
config = load_strategy("examples/strategies/pe_roe_ma10.yaml")
inline_factors = config.ranking.get("inline_factors", [])
weights = config.ranking.get("weights", {})
conditions = config.ranking.get("conditions", {})
bonuses = config.ranking.get("bonuses", [])

# Compute factors (returns DataFrame)
computer = FactorComputer()
factor_df = computer.compute_all_factors(
    {f.name: f for f in inline_factors},
    price_data,  # Dict[str, pd.DataFrame]
    {},          # intraday_data
    candidates   # List[str]
)

# Score with conditions and bonuses
scorer = ScoringEngine(normalize="zscore")
result = scorer.compute(factors, weights, factor_df, conditions=conditions, bonuses=bonuses)
```

### YAML Configuration (examples/strategies/pe_roe_ma10.yaml)
```yaml
name: PE-ROE-MA10 选股策略
version: 1.0.0

screening:
  fundamental_conditions:   # Stage 1: 财务条件筛选
    - "pe_ttm < 20"
    - "pe_ttm > 0"
    - "roe > 0.1"
  daily_conditions:         # Stage 2: 价格条件筛选
    - "close > ma10"

ranking:
  weights:                  # 权重融合 (0 = 仅过滤)
    pe_ttm: -0.3            # 负权重: 低估值
    roe: 0.5                # 正权重: 高ROE
    ma10_deviation: 0.2     # 正权重: 站上均线
  normalize: zscore

output:
  limit: 50

# 回测配置 (可选)
backtest:
  entry:
    price: open_next  # open_today / open_next
  exit:
    - rule: timed
      hold_days: 1    # 持有N天后卖出
      time: "10:00"   # 触发时间
    - rule: close     # 收盘卖出
  capital: 1000000
  fee: 0.0003
```

## Development Commands

```bash
# Install dependencies
python3 -m pip install -e .

# Run all tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=quantcli --cov-report=term-missing

# Run single test file
pytest tests/test_factors.py -v

# Run single test
pytest tests/test_factors.py::TestComputeFactors::test_compute_single_factor -v

# Run CLI help
quantcli --help
```

## Formula Syntax

```python
# Builtin functions
delay(x, n)       # Shift
ma(x, n)          # Moving average
ema(x, n)         # Exponential MA
ts_std(x, n)      # Rolling std
ts_sum(x, n)      # Rolling sum
ts_rank(x, n)     # Time-series rank
ts_ave(x, n)      # Time-series average
rank(x)           # Cross-sectional rank (0-1)
zscore(x)         # Standardization
rsi(x, n=14)
correlation(x, y, n)
signed_power(x, n)
ts_decayexp(x, n)
cross_up(a, b)    # Golden cross
where(cond, t, f) # Ternary operator
sign(x)           # Sign function
clamp(x, min, max)

# Screening (simple expressions)
"roe > 0.1"
"netprofitmargin > 0.05"
"close < open"  # Boolean factor
```

## Built-in Alpha101 Factor Library

**40 built-in factors** located at `quantcli/factors/alpha101/`:

```bash
# 使用内置因子 (简写格式)
alpha101/alpha_001  ~ alpha_040

# 加载内置因子示例
from quantcli.factors.loader import load_all_factors

weights = {
    'alpha101/alpha_001': 0.3,  # 创新高反转
    'alpha101/alpha_008': 0.3,  # 资金流入
    'alpha101/alpha_029': 0.4,  # 5日动量
}
factors = load_all_factors(weights, '/path/to/strategy')
```

## IC/IR Analysis

```bash
# 单因子分析
quantcli analyze ic -e "(close / delay(close, 20)) - 1" -n "20日动量" --period 5

# 批量分析
quantcli analyze batch -d examples/alpha101/alpha/ --top 10
```

| IC Absolute Value | Effectiveness |
|-------------------|---------------|
| > 0.1 | Strong |
| 0.05 - 0.1 | Moderate |
| < 0.02 | Invalid |

| IR Value | Stability |
|----------|-----------|
| > 0.5 | Stable |
| 0.3 - 0.5 | Moderate |
| < 0.3 | Unstable |

## Important Notes

- DataFrame columns: lowercase with underscores (`close`, `symbol`)
- `__init__.py` imports should be minimal
- Tests use synthetic data (fixtures in `tests/conftest.py`)
- Default data source: `mixed` (Akshare for prices, Baostock for fundamentals)
- Cache files: `data/cache/{prices,stocklist,calendar,fundamentals}/`
- Fundamental data uses decimal format (0.15 = 15%)
- Use `load_strategy()` for new code (not `load_config`)
- `FactorComputer.compute_all_factors()` returns `pd.DataFrame`
- Backtest: Use `--symbol` for single stock backtest, otherwise multi-factor screening

## MySQL Data Source (required for backtest)

**回测强制使用 MySQL 数据源**，需要先配置环境变量并同步数据。

```bash
# 配置环境变量
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD=your_password
export MYSQL_DATABASE=quantcli
export MYSQL_TABLE_PREFIX=
```

```python
# 使用 MySQL 数据源
from quantcli.datasources import create_datasource

ds = create_datasource("mysql")

# 同步数据（首次使用前必须执行）
ds.sync_from_akshare(start_date=date(2020, 1, 1))
ds.sync_trading_calendar()

# 日线数据查询
df = ds.get_daily("600519", date(2024,1,1), date(2024,1,31))

# 批量获取多只股票（回测优化）
price_data = ds.get_multi_daily(
    symbols=["600519", "000001"],
    start_date=date(2024,1,1),
    end_date=date(2024,1,31)
)

# 分钟级数据查询
df_5min = ds.get_intraday("600519", date(2024,1,15), date(2024,1,16), period="5")

# 批量获取分钟数据
intraday_data = ds.get_multi_intraday(
    symbols=["600519", "000001"],
    start_date=date(2024,1,15),
    period="5"
)
```

### MySQL Tables
| Table | Purpose |
|-------|---------|
| `daily_prices` | 日线数据 |
| `intraday_prices` | 分钟级数据 (1/5/15/30/60min) |
| `stock_list` | 股票列表 |
| `trading_calendar` | 交易日历 |
| `fundamental_data` | 基本面数据 |

## Documentation

See [docs/cli_guide.md](docs/cli_guide.md) for:
- Complete YAML configuration reference
- Full formula function documentation (40+ functions)
- External factor file usage pattern
- Step-by-step examples
