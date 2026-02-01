# QuantCLI 使用手册

**版本:** v1.1.0

QuantCLI 是一款**多因子选股**命令行工具，支持多阶段筛选、因子权重融合、条件过滤和加分项评分。

---

## 目录

1. [安装](#安装)
2. [快速开始](#快速开始)
3. [AI 友好功能](#ai-友好功能)
4. [多因子策略配置](#多因子策略配置)
5. [公式语法](#公式语法)
6. [CLI 命令参考](#cli-命令参考)
7. [完整示例](#完整示例)

---

## 安装

### 系统要求

- Python 3.9+
- pip

### 安装步骤

```bash
# 克隆项目
git clone https://github.com/quantcli/quantcli.git
cd quantcli

# 安装依赖
pip install -e .

# 验证安装
quantcli --help
```

---

## 快速开始

### 1. 查看帮助

```bash
quantcli --help
```

### 2. 运行多因子筛选

```bash
# 使用内置策略进行筛选
quantcli filter run -f examples/strategies/pe_roe_ma10.yaml --top 30

# 筛选指定股票
quantcli filter run -f examples/strategies/value_stocks.yaml --symbols "600519,000001,600036"

# 查看所有内置因子
quantcli factors list
```

### 3. 查看帮助

```bash
# 查看筛选命令帮助
quantcli filter --help

# 查看子命令帮助
quantcli filter run --help
```

---

## AI 友好功能

QuantCLI 设计之初就考虑了 AI Agent 的使用场景，支持结构化输出和批量操作。

### JSON 输出模式

所有命令支持 `--json` 参数，以机器可解析的格式输出：

```bash
# 人类友好模式 (默认)
$ quantcli analyze ic -e "(close/delay(close,20))-1" -n "20日动量"
==================================================
IC/IR Analysis Results
==================================================
  Overall IC:     +0.0321
  Rolling IC Mean: +0.0285
  IR (annualized): +0.47
  评级:           ★★☆ 中等因子

# AI 友好模式
$ quantcli analyze ic -e "(close/delay(close,20))-1" --json
{"status": "success", "ic_mean": 0.0285, "ir": 0.47, ...}
```

### Analyze 命令 - 因子有效性分析

```bash
# 单因子 IC/IR 分析
quantcli analyze ic -e "(close / delay(close, 20)) - 1" -n "20日动量" --period 5 --json

# 批量分析因子库
quantcli analyze batch -d ./examples/alpha101/alpha/ --top 10 --json
```

### IC/IR 评估标准

| 指标 | 含义 | 阈值 |
|------|------|------|
| **IC** | 因子与未来收益的秩相关 | \|IC\| > 0.05 有效 |
| **IR** | IC 均值/标准差（年化） | IR > 0.5 稳定 |

### Alpha101 因子库示例

QuantCLI 内置了 **40 个 Alpha101 因子**，可直接在策略中引用：

```bash
# 查看所有内置因子
quantcli factors list

# 运行 Alpha101 复合策略
quantcli filter run -f examples/alpha101/alpha101_composite.yaml --top 30

# 批量分析 Alpha101 因子有效性
quantcli analyze batch -d examples/alpha101/alpha/ --top 10
```

**使用内置因子示例：**
```yaml
factors:
  - alpha101/alpha_001   # 20日创新高后转跌
  - alpha101/alpha_008   # 资金流入
  - alpha101/alpha_029   # 5日动量

ranking:
  weights:
    alpha101/alpha_001: 0.4
    alpha101/alpha_008: 0.3
    alpha101/alpha_029: 0.3
  normalize: zscore
```

### 推荐的 AI 工作流

```bash
#!/bin/bash
# AI Agent 自动化因子研究

# 1. 批量分析因子有效性
quantcli analyze batch -d ./examples/alpha101/alpha/ \
  --period 5 \
  --top 20 \
  --output factor_ranking.csv

# 2. 使用高 IR 因子构建策略
# AI 解析 factor_ranking.csv，筛选 IR > 0.3 的因子

# 3. 运行策略回测
quantcli filter run -f my_strategy.yaml --top 30 --json

# 4. 解析回测结果
cat results.json | jq '.metrics.sharpe'
```

### Claude Code Skill

QuantCLI 提供了 Claude Code Skill，可被 AI Agent 直接调用：

```markdown
/skill multi-factor-strategy --goal "低估+高ROE" --output strategy.yaml
```

详见 [Skill 文档](product_design.md#33-skill-定义)

---

## 多因子策略配置

### 完整配置示例

```yaml
# 10日线阴线回调选股策略
name: 10日线阴线因子
version: 1.0.0
description: 10日线阴线回调选股策略因子

# ==================== 阶段1: 因子定义 ====================
factors:
  # 阴线标识
  - name: is_yinliang
    type: technical
    expr: "close < open"
    description: 阴线标识 (True=阴线)
    direction: positive

  # 10日线偏离度
  - name: ma10_deviation
    type: technical
    expr: "(close - ma(close, 10)) / ma(close, 10)"
    description: 股价相对10日线偏离度
    direction: negative

  # 量比
  - name: volume_ratio
    type: technical
    expr: "volume / ma(volume, 5)"
    description: 相对5日均量
    direction: negative

  # 10日线斜率 (5日变化)
  - name: ma10_slope
    type: technical
    expr: "(ma(close, 10) - delay(ma(close, 10), 5)) / delay(ma(close, 10), 5)"
    description: 10日线斜率
    direction: positive

  # 5日内放量次数
  - name: volume_surge_5d
    type: technical
    expr: "rolling_sum(where(volume / ma(volume, 5) > 1.2, 1, 0), 5)"
    description: 5日内放量(>1.2倍均量)次数
    direction: positive

# ==================== 阶段2: 排名/评分 ====================
ranking:
  # 权重配置（权重为0表示只用于筛选不参与评分）
  weights:
    is_yinliang: 0          # 只做条件筛选
    ma10_deviation: 0.5     # 核心因子
    volume_ratio: 0.2       # 辅助因子
    ma10_slope: 0.2         # 辅助因子
    volume_surge_5d: 0.1    # 辅助因子

  # 标准化方法: zscore | minmax | none
  normalize: zscore

  # 必要条件（必须满足才计入评分）
  conditions:
    is_yinliang: true           # 必须阴线
    ma10_slope: {min: 0}        # 10日线向上
    ma10_deviation: {min: -0.1} # 不能偏离太远

  # 加分项（满足条件时额外加分）
  bonuses:
    # 缩量加分
    - condition: "volume_ratio < 0.8"
      weight: 1
      description: 缩量加分

    # 回调10日线附近加分
    - condition: "ma10_deviation > -0.03 and ma10_deviation < 0.01"
      weight: 2
      description: 回调10日线附近加分

    # 历史放量加分
    - condition: "volume_surge_5d >= 1"
      weight: 1
      description: 历史放量加分

# ==================== 阶段3: 输出配置 ====================
output:
  columns: [symbol, score, is_yinliang, ma10_deviation, volume_ratio, ma10_slope]
  sort_by: score
  limit: 30
```

### 配置字段说明

#### factors - 因子定义（支持两种配置方式）

**注意：`factors` 配置在策略顶层，`ranking` 中只配置权重**

```yaml
# 方式1: 内联因子定义（dict）
factors:
  - name: ma10_deviation
    type: technical
    expr: "(close - ma(close, 10)) / ma(close, 10)"
    direction: negative
    description: "10日线偏离度"

  # 方式2: 外部引用（string，引用 factors/ 目录下的文件，需包含 .yaml 后缀）
  - factors/alpha_001.yaml
  - factors/alpha_002.yaml

ranking:
  weights:
    ma10_deviation: 0.5
    factors/alpha_001.yaml: 0.3
    factors/alpha_002.yaml: 0.2
  normalize: zscore
```

| 字段 | 必填 | 说明 |
|------|------|------|
| name | 是 | 因子名称（英文标识符） |
| type | 否 | 因子类型: technical, fundamental, intraday |
| expr | 是 | 因子表达式（内联定义时必填） |
| direction | 否 | 方向: positive(越大越好), negative(越小越好), neutral |
| description | 否 | 因子描述 |

**配置方式对比：**

| 方式 | 类型 | 示例 | 说明 |
|------|------|------|------|
| **内联定义** | `dict` | `{name: xxx, expr: "..."}` | 直接在 YAML 中定义表达式 |
| **外部引用** | `str` | `factors/alpha_001.yaml` | 从 `factors/` 目录加载因子文件 |

**加载器自动识别规则** (`loader.py:176-198`)：
- `dict` 对象 → 提取 name, expr, direction 创建内联因子
- `str` 字符串 → 从 `factors/` 目录加载外部因子文件（需包含 `.yaml` 后缀）

**示例：混用两种方式**

```yaml
factors:
  # 内联定义：自定义因子
  - name: custom_momentum
    expr: "close / delay(close, 20) - 1"
    direction: positive
  # 外部引用：因子库文件（包含 .yaml 后缀）
  - factors/alpha_001.yaml
  - factors/alpha_008.yaml

ranking:
  weights:
    custom_momentum: 0.3
    factors/alpha_001.yaml: 0.4
    factors/alpha_008.yaml: 0.3
  normalize: zscore
```

#### ranking - 排名配置

| 字段 | 说明 |
|------|------|
| weights | 因子权重字典，权重为0表示仅用于筛选 |
| normalize | 标准化方法: zscore, minmax, none |
| conditions | 必要条件字典，不满足则 score=NaN |
| bonuses | 加分项列表，满足条件额外加分 |

#### conditions - 必要条件格式

```yaml
# 布尔条件
is_yinliang: true   # 必须为 True
is_yinliang: false  # 必须为 False

# 范围条件
ma10_slope: {min: 0}           # >= 0
ma10_deviation: {max: 0.1}     # <= 0.1
ma10_deviation: {min: -0.1, max: 0.1}  # -0.1 <= x <= 0.1
```

#### bonuses - 加分项格式

```yaml
bonuses:
  - condition: "column < value"        # 简单条件
    weight: 1.0                         # 加分权重
    description: 说明文字              # 可选

  # 复合条件
  - condition: "col1 > 0 and col2 < 1"
    weight: 2.0
```

---

## 公式语法

### 基础语法

因子表达式支持算术运算、函数调用和条件表达式。

```python
# 算术运算
close + volume
close * 2
(close - open) / open

# 函数调用
ma(close, 20)
ema(close, 12)
delay(close, 1)

# 条件表达式
where(close > open, 1, 0)  # 阳线返回1，阴线返回0
```

### 内置函数

#### 时间序列函数

| 函数 | 说明 | 示例 |
|------|------|------|
| delay(x, n) | 延时 n 天 | `delay(close, 5)` |
| ma(x, n) | 简单移动平均 | `ma(close, 20)` |
| ema(x, n) | 指数移动平均 | `ema(close, 12)` |
| wma(x, n) | 加权移动平均 | `wma(close, 5)` |
| sma(x, n) | 简单移动平均 | `sma(close, 10)` |
| rolling_std(x, n) | 滚动标准差 | `rolling_std(close, 20)` |
| rolling_sum(x, n) | 滚动求和 | `rolling_sum(volume, 5)` |
| rolling_mean(x, n) | 滚动均值 | `rolling_mean(close, 10)` |

#### 统计函数

| 函数 | 说明 | 示例 |
|------|------|------|
| rank(x) | 横截面排序 (0-1) | `rank(close)` |
| zscore(x) | Z-Score 标准化 | `zscore(close)` |
| quantile(x, q) | 分位数 (0-1) | `quantile(close, 0.3)` |
| correlation(x, y, n) | 滚动相关系数 | `correlation(close, volume, 20)` |
| covariance(x, y, n) | 滚动协方差 | `covariance(close, volume, 20)` |

#### 技术指标函数

| 函数 | 说明 | 示例 |
|------|------|------|
| rsi(x, n) | 相对强弱指数 | `rsi(close, 14)` |
| macd(x, fast, slow, signal) | MACD | `macd(close)` |
| boll(x, n, k) | 布林带 (返回中轨) | `boll(close, 20, 2)` |
| boll_upper(x, n, k) | 布林带上轨 | `boll_upper(close, 20, 2)` |
| boll_lower(x, n, k) | 布林带下轨 | `boll_lower(close, 20, 2)` |
| atr(h, l, c, n) | 真实波幅 | `atr(high, low, close, 14)` |
| kdj(h, l, c, n, m1, m2) | KDJ 指标 | `kdj(high, low, close)` |
| obv(close, volume) | 能量潮 | `obv(close, volume)` |

#### 交叉函数

| 函数 | 说明 | 示例 |
|------|------|------|
| cross_up(a, b) | 金叉 (a 上穿 b) | `cross_up(ma_fast, ma_slow)` |
| cross_down(a, b) | 死叉 (a 下穿 b) | `cross_down(ma_fast, ma_slow)` |

#### 逻辑函数

| 函数 | 说明 | 示例 |
|------|------|------|
| where(cond, t, f) | 条件取值 | `where(close > open, 1, 0)` |
| sign(x) | 符号函数 (-1, 0, 1) | `sign(close - ma(close, 10))` |
| abs_val(x) | 绝对值 | `abs_val(close - open)` |
| clamp(x, min, max) | 限制范围 | `clamp(rsi(close, 14), 20, 80)` |

#### 基础行情列

| 列名 | 说明 |
|------|------|
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| volume | 成交量 |
| amount | 成交额 |
| date | 日期 |

### 常用因子表达式

```python
# 动量因子
(close / delay(close, 20)) - 1

# 改进版动量 (除以波动率)
(close / delay(close, 20)) / rolling_std(close / delay(close, 20), 20)

# 价格相对位置
close / ma(close, 20)

# 波动率因子
rolling_std(close, 20) / ma(close, 20)

# RSI
rsi(close, 14)

# 成交量加权价格
volume * close / rolling_sum(volume, 20)

# 布林带偏离
(close - boll(close, 20, 2)) / (boll_upper(close, 20, 2) - boll_lower(close, 20, 2))

# 阴线标识
where(close < open, 1, 0)

# 放量
volume / ma(volume, 5)

# 10日线斜率
(ma(close, 10) - delay(ma(close, 10), 5)) / delay(ma(close, 10), 5)
```

---

## CLI 命令参考

### quantcli analyze - 因子有效性分析

#### 单因子 IC/IR 分析

```bash
quantcli analyze ic -e EXPRESSION -n NAME [OPTIONS]
```

| 选项 | 说明 |
|------|------|
| -e, --expr | 因子表达式 [required] |
| -n, --name | 因子名称 |
| --symbol | 股票代码 (默认 600519) |
| --start | 开始日期 (默认 2020-01-01) |
| --end | 结束日期 |
| --period | 未来收益周期 (默认 5 天) |
| --window | 滚动 IC 窗口 (默认 60 天) |
| --method | IC 计算方法: pearson/spearman (默认 spearman) |
| --json | JSON 格式输出 |

**示例:**

```bash
# 20日动量因子 IC 分析
quantcli analyze ic -e "(close / delay(close, 20)) - 1" -n "20日动量" --period 5

# JSON 输出 (AI 推荐)
quantcli analyze ic -e "(close / delay(close, 20)) - 1" -n "20日动量" --json

# 10日未来收益
quantcli analyze ic -e "(close / delay(close, 20)) - 1" --period 10
```

#### 批量因子分析

```bash
quantcli analyze batch -d DIRECTORY [OPTIONS]
```

| 选项 | 说明 |
|------|------|
| -d, --dir | 因子目录 [required] |
| --symbol | 股票代码 |
| --start | 开始日期 |
| --end | 结束日期 |
| --period | 未来收益周期 (默认 5 天) |
| --window | 滚动 IC 窗口 (默认 60 天) |
| --top | 显示前 N 名 (默认 10) |
| --output | 输出文件 (CSV) |
| --json | JSON 格式输出 |

**示例:**

```bash
# 批量分析 Alpha101 因子
quantcli analyze batch -d examples/alpha101/alpha/ --top 10

# 输出到 CSV
quantcli analyze batch -d examples/alpha101/alpha/ -o ic_results.csv

# JSON 输出
quantcli analyze batch -d examples/alpha101/alpha/ --json
```

**输出示例:**

```
Rank  Factor Name               IC(total)   IC(mean)    IR      Rating
1     ALPHA_005                 +0.0421     +0.0385     +0.68    ★★★
2     ALPHA_009                 +0.0382     +0.0352     +0.55    ★★★
3     ALPHA_003                 +0.0215     +0.0198     +0.31    ★★☆
```

### quantcli filter - 多因子筛选

#### 运行筛选

```bash
quantcli filter run -f CONFIG_FILE [OPTIONS]
```

| 选项 | 说明 |
|------|------|
| -f, --file | 策略配置文件路径 |
| --symbols | 股票列表 (逗号分隔) |
| --top | 输出前 N 名 |
| --no-intraday | 禁用分钟数据 |

**示例:**

```bash
# 使用策略文件筛选
quantcli filter run -f examples/ma10_yinliang.yaml --top 30

# 筛选指定股票
quantcli filter run -f examples/ma10_yinliang.yaml --symbols "600519,000001,600036"

# 获取前10名
quantcli filter run -f examples/ma10_yinliang.yaml --top 10
```

### quantcli factor - 因子计算

#### 运行单个因子

```bash
quantcli factor run -n NAME -e EXPRESSION [OPTIONS]
```

| 选项 | 说明 |
|------|------|
| -n, --name | 因子名称 |
| -e, --expr | 因子表达式 |
| --symbol | 股票代码 |
| --start | 开始日期 |
| --end | 结束日期 |
| --output | 输出文件 |

**示例:**

```bash
# 20日动量因子
quantcli factor run -n momentum -e "(close / delay(close, 20)) - 1"

# RSI 因子
quantcli factor run -n rsi -e "rsi(close, 14)"

# 保存结果
quantcli factor run -n momentum -e "(close / delay(close, 20)) - 1" --output ./momentum.csv
```

#### 评估因子 IC

```bash
quantcli factor eval ic NAME [OPTIONS]
```

**示例:**

```bash
# IC 分析
quantcli factor eval ic momentum

# 带日期范围
quantcli factor eval ic momentum --start 2020-01-01 --end 2024-01-01
```

### quantcli data - 数据管理

#### 获取数据

```bash
quantcli data fetch SYMBOL --start DATE [OPTIONS]
```

| 选项 | 说明 |
|------|------|
| SYMBOL | 股票代码 |
| --start | 开始日期 |
| --end | 结束日期 |
| --source | 数据源 |
| --output | 输出文件 |

**示例:**

```bash
# 获取股票数据
quantcli data fetch 600519 --start 2020-01-01 --end 2024-01-01

# 保存到文件
quantcli data fetch 600519 --start 2020-01-01 --output ./data.csv
```

#### 缓存管理

```bash
# 列出缓存
quantcli data cache ls

# 清理缓存
quantcli data cache clean [--older-than N]
```

#### 健康检查

```bash
quantcli data health
```

### quantcli backtest - 回测引擎

#### 运行回测

```bash
quantcli backtest run -s STRATEGY [OPTIONS]
```

| 选项 | 说明 |
|------|------|
| -s, --strategy | 策略文件或内置策略名 |
| --symbol | 股票代码 |
| --start | 开始日期 |
| --end | 结束日期 |
| --capital | 初始资金 |
| --fee | 手续费率 |

**示例:**

```bash
# 使用内置均线策略
quantcli backtest run -s ma_cross --start 2020-01-01

# 自定义参数
quantcli backtest run -s ma_cross --start 2020-01-01 --capital 500000 --fee 0.001
```

### quantcli config - 配置管理

```bash
# 查看配置
quantcli config show

# 设置配置
quantcli config set KEY VALUE
```

### quantcli expr - 可用表达式列表

```bash
# 列出所有函数和字段
quantcli expr list

# 列出所有内置函数
quantcli expr functions

# 列出所有字段别名
quantcli expr columns
```

**示例:**

```bash
# 查看所有可用表达式
quantcli expr list

# 查看函数列表
quantcli expr functions

# 查看字段别名
quantcli expr columns

# JSON 格式输出 (AI 推荐)
quantcli expr list --json
```

**输出示例:**

```
==================================================
Available Expressions
==================================================

Functions (30):
  abs             clamp           correlation     cross_down
  cross_up        delay           ema             if
  ...

Columns (9):
  - asset_equity_ratio
  - debt_to_assets
  - gross_profit_margin
  ...
```

---

## 完整示例

### 示例1: 基础多因子策略（内联因子定义）

创建策略文件 `my_strategy.yaml`:

```yaml
name: 我的多因子策略
version: 1.0.0

factors:
  - name: momentum_20
    type: technical
    expr: "(close / delay(close, 20)) - 1"
    direction: positive

  - name: rsi_14
    type: technical
    expr: "rsi(close, 14)"
    direction: negative

  - name: volume_ratio
    type: technical
    expr: "volume / ma(volume, 5)"
    direction: negative

ranking:
  weights:
    momentum_20: 0.4
    rsi_14: 0.3
    volume_ratio: 0.3
  normalize: zscore

output:
  limit: 20
```

运行:

```bash
quantcli filter run -f my_strategy.yaml --top 20
```

### 示例2: 引用外部因子文件

这是一个完整的价值回归策略示例，引用外部因子文件：

#### 策略文件 `strategies/pe_roe_ma10.yaml`

```yaml
name: PE+ROE+MA10 价值回归策略
version: 1.0.0
description: 基本面筛选 + 技术面权重排序

# 阶段1: 筛选（简单表达式）
screening:
  conditions:
    - "roe > 0.10"              # ROE > 10%
    - "netprofitmargin > 0.05"  # 净利润率 > 5%
  limit: 200

# 阶段2: 权重排序（引用因子文件）
ranking:
  weights:
    factors/fundamentals/roe.yaml: 0.30
    factors/fundamentals/netprofitmargin.yaml: 0.20
    factors/technicals/ma10_deviation.yaml: 0.30
    factors/technicals/momentum_20d.yaml: 0.20
  normalize: zscore

output:
  columns: [symbol, score, rank, roe, netprofitmargin, ma10_deviation]
  limit: 30
```

#### 对应的因子文件

**`factors/fundamentals/roe.yaml`**
```yaml
name: 净资产收益率因子
type: fundamental
expr: "roe"
direction: positive
description: ROE 越高越好
```

**`factors/fundamentals/netprofitmargin.yaml`**
```yaml
name: 净利润率因子
type: fundamental
expr: "netprofitmargin"
direction: positive
description: 净利润率越高越好
```

**`factors/technicals/ma10_deviation.yaml`**
```yaml
name: 10日线偏离度因子
type: technical
expr: "(close - ma(close, 10)) / ma(close, 10)"
direction: negative
description: 回调到10日线附近加分（负值表示在均线下方）
```

**`factors/technicals/momentum_20d.yaml`**
```yaml
name: 20日动量因子
type: technical
expr: "(close / delay(close, 20)) - 1"
direction: positive
description: 20日累计涨幅
```

运行策略:

```bash
quantcli filter run -f strategies/pe_roe_ma10.yaml --top 30
```

### 示例3: 带条件筛选的策略

```yaml
name: 精选低估成长
version: 1.0.0

factors:
  - name: roe
    type: fundamental
    expr: "roe"
    direction: positive

  - name: pe
    type: fundamental
    expr: "pe"
    direction: negative

  - name: revenue_growth
    type: fundamental
    expr: "revenue_yoy"
    direction: positive

ranking:
  weights:
    roe: 0.4
    pe: 0.3
    revenue_growth: 0.3
  conditions:
    roe: {min: 0.1}           # ROE >= 10%
    pe: {max: 30}             # PE <= 30
    revenue_growth: {min: 0.05}  # 营收增长 >= 5%

output:
  limit: 50
```

### 示例4: 评分+加分项策略

```yaml
name: 强势股回调策略
version: 1.0.0

factors:
  - name: ma10_deviation
    type: technical
    expr: "(close - ma(close, 10)) / ma(close, 10)"
    direction: negative

  - name: is_yinliang
    type: technical
    expr: "close < open"
    direction: positive

  - name: volume_ratio
    type: technical
    expr: "volume / ma(volume, 5)"
    direction: negative

ranking:
  weights:
    ma10_deviation: 0.5
    is_yinliang: 0
    volume_ratio: 0.2
  conditions:
    is_yinliang: true
  bonuses:
    - condition: "volume_ratio < 0.8"
      weight: 1.0
      description: 缩量
    - condition: "ma10_deviation > -0.05 and ma10_deviation < 0"
      weight: 2.0
      description: 回调到10日线附近

output:
  limit: 30
```

### 完整研究流程

```bash
# 1. 获取股票列表和价格数据
quantcli data fetch 600519 --start 2020-01-01 --end 2024-01-01
quantcli data fetch 000001 --start 2020-01-01 --end 2024-01-01

# 2. 运行多因子筛选
quantcli filter run -f examples/ma10_yinliang.yaml --top 30

# 3. 查看筛选结果
cat results.csv

# 4. 对入选股票进行因子评估
quantcli factor eval ic momentum_20 --symbol 600519

# 5. 回测入选股票池
quantcli backtest run -s ma_cross --symbol 600519 --start 2021-01-01
```

---

## 常见问题

### Q: 因子计算失败?

A: 检查因子表达式语法：
```bash
# 使用 verbose 模式
quantcli -v factor run -n test -e "close" --symbol 600519
```

### Q: 筛选结果为空?

A: 检查条件设置是否过于严格：
- 减少 conditions 中的必要条件
- 放宽 conditions 的数值范围

### Q: 数据获取失败?

A: 检查网络连接和数据源：
```bash
quantcli data health
```

---

## 参考

- 项目主页: https://github.com/quantcli/quantcli
- 示例配置: `examples/ma10_yinliang.yaml`

---

*最后更新: 2026-02-01*
