# QuantCLI 产品设计文档

**版本:** v1.1.0
**状态:** 设计中
**作者:** QuantCLI Team
**最后更新:** 2024-02-01

---

## 目录

1. [产品概述](#1-产品概述)
2. [核心设计原则](#2-核心设计原则)
3. [AI 友好设计](#3-ai-友好设计)
4. [命令行设计](#4-命令行设计)
5. [文件格式规范](#5-文件格式规范)
6. [公式语法设计](#6-公式语法设计)
7. [功能模块详解](#7-功能模块详解)
8. [错误处理与用户引导](#8-错误处理与用户引导)
9. [技术架构](#9-技术架构)
10. [发布路线图](#10-发布路线图)
11. [功能优先级矩阵](#11-功能优先级矩阵)

---

## 1. 产品概述

### 1.1 产品定位

QuantCLI 是一款专注于**因子挖掘与回测**的命令行工具，为个人量化研究者提供轻量、高效、可复现的研究环境。

| 维度 | 描述 |
|------|------|
| **产品定位** | 轻量级量化研究CLI工具 / AI Agent 友好框架 |
| **目标用户** | 个人quant、宽客学生、兼职投资者、AI Agent |
| **核心价值** | 快速验证想法，降低研究门槛，AI 可编程 |
| **差异化** | 简单优先、脚本化、互操作性、AI First |

### 1.2 解决的问题

| 痛点 | QuantCLI 解决方案 |
|------|-------------------|
| 现有工具太重 | 纯命令行，零UI依赖 |
| 学习成本高 | 80%场景用20%功能覆盖 |
| 不可复现 | 配置文件即文档 |
| 数据管理混乱 | 自动缓存，增量计算 |
| 结果难以追溯 | 完整版本控制和结果归档 |
| AI 难以集成 | 结构化输出、Skill 封装、YAML 驱动 |

### 1.3 使用场景

```bash
# 场景1: AI 快速验证因子想法
quantcli factor run -n momentum -e "(close / delay(close, 20)) - 1"

# 场景2: AI 批量因子扫描
quantcli analyze batch -d ./factors --min_ic 0.03 --top 20

# 场景3: 完整回测流程
quantcli backtest run -s dual_ma.yaml --start 2020-01-01

# 场景4: AI Skill 驱动的策略生成
/skill multi-factor-strategy --goal "低估+高ROE" --output strategy.yaml

# 场景5: CI/CD 中的自动化回测
quantcli backtest run -s strategy.yaml --output json | jq '.metrics.sharpe'
```

### 1.4 AI Agent 集成模式

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI Agent 集成架构                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│   │ Claude Code │    │  GitHub     │    │   OpenAI    │        │
│   │   Agent     │    │   Copilot   │    │   Agent     │        │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘        │
│          │                  │                  │                 │
│          └────────────┬─────┴────────────┬────┘                 │
│                       │                  │                       │
│                  CLAUDE.md           Skill 定义                  │
│                  (项目上下文)        (Agent Prompt)              │
│                       │                  │                       │
│                       └─────────┬────────┘                       │
│                                 │                                │
│                          quantcli CLI                            │
│                    (结构化输入/输出)                              │
│                                 │                                │
│          ┌──────────────────────┼──────────────────────┐        │
│          │                      │                      │        │
│      数据层              因子层              回测层              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心设计原则

### 2.1 设计哲学

```
┌─────────────────────────────────────────────────────────────┐
│                     Let it Crash                            │
│  • 强制正确，不容忍小错误                                    │
│  • 快速失败，快速修复                                        │
│  • 简洁优于复杂                                              │
│  • AI 可理解优于人类可读 (但要兼顾)                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 五大原则

| 原则 | 说明 | 实践 |
|------|------|------|
| **简单优先** | 80%场景用20%功能覆盖 | 常用命令一键完成 |
| **脚本化** | 所有操作可复现 | YAML配置驱动 |
| **增量式** | 数据缓存，支持断点续算 | Parquet列式存储 |
| **互操作性** | 输入输出标准化 | CSV/JSON/Parquet |
| **AI First** | 专为AI Agent优化 | 结构化输出 + Skill |

### 2.3 YAGNI原则

```
You Aren't Gonna Need It

克制过度配置化的冲动:
• 不做超前设计
• 不添加"将来可能用到"的功能
• 先解决今天的问题
• AI 不需要的功能就不做
```

### 2.4 DataFrame First

```python
# 所有 API 返回/接受 pd.DataFrame
# 不接受 List[Dict] 或其他复杂嵌套结构

# ✅ 正确
df = ds.get_daily("600519", date(2024,1,1), date(2024,1,31))
# 返回: DataFrame [date, open, high, low, close, volume]

# ❌ 错误
result = get_data_as_nested_dict()
# AI 难以解析和操作
```

---

## 3. AI 友好设计

### 3.1 AI First 设计原则

```
┌─────────────────────────────────────────────────────────────┐
│                 AI First 四大支柱                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1️⃣  结构化输出                                             │
│      • 默认 JSON 输出模式                                    │
│      • 明确的 schema 定义                                    │
│      • 错误码 + 可执行建议                                    │
│                                                              │
│  2️⃣  Skill 封装                                             │
│      • Claude Code Skill 格式                                │
│      • 可被 AI Agent 直接调用                                 │
│      • 自描述的 prompt 模板                                   │
│                                                              │
│  3️⃣  幂等性设计                                              │
│      • 相同输入 → 相同输出                                    │
│      • 可重试的 CLI 调用                                      │
│      • 无状态或少状态                                         │
│                                                              │
│  4️⃣  上下文感知                                              │
│      • 支持 --verbose 调试                                    │
│      • 支持 --quiet 静默模式                                  │
│      • 支持 --json 机器输出                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 输出模式设计

```bash
# 人类友好模式 (默认)
$ quantcli analyze ic -e "(close/delay(close,20))-1" -n "20日动量"
==================================================
IC/IR Analysis Results
==================================================
  Overall IC:     +0.0321
  Rolling IC Mean: +0.0285
  IR (annualized): +0.47
  IC > 0 ratio:   56.2%
  评级:           ★★☆ 中等因子

# AI 友好模式 (JSON)
$ quantcli analyze ic -e "(close/delay(close,20))-1" --json
{
  "status": "success",
  "factor": {
    "name": "20日动量",
    "expr": "(close / delay(close, 20)) - 1"
  },
  "ic_analysis": {
    "ic_total": 0.0321,
    "ic_mean": 0.0285,
    "ic_std": 0.0852,
    "ir": 0.47,
    "ic_positive_ratio": 0.562,
    "samples": 180
  },
  "rating": {
    "score": "★★☆",
    "label": "中等因子",
    "effectiveness": "moderate"
  },
  "timestamp": "2024-02-01T10:30:00+08:00"
}
```

### 3.3 Skill 定义

```yaml
# skills/multi-factor-strategy.yaml
name: multi-factor-strategy
description: |
  引导创建多因子选股策略，生成可独立运行的 YAML 配置文件。
  将因子研究、回测验证、策略执行整合为标准化流程。

parameters:
  - name: goal
    type: string
    description: 策略目标描述，如 "低估+高ROE" 或 "动量+反转"
    required: true
  - name: output
    type: string
    description: 输出策略文件路径
    default: strategy.yaml

prompt: |
  你是一位量化研究员。请根据用户的需求创建多因子选股策略。

  用户需求: {{goal}}

  因子配置支持两种方式（可混用）:

  **方式1: 内联因子定义**
  ```yaml
  factors:
    - name: ma10_deviation
      expr: "(close - ma(close, 10)) / ma(close, 10)"
      direction: negative
  ```

  **方式2: 外部引用**
  ```yaml
  factors:
    - alpha_001    # 引用 factors/alpha_001.yaml
    - alpha_008
  ```

  请按照以下步骤:
  1. 分析需求，确定核心因子类型
  2. 设计因子表达式（使用内联定义或引用外部因子）
  3. 设置筛选条件和权重
  4. 生成 YAML 配置文件

  输出示例:
  ```yaml
  name: xxx策略
  version: 1.0.0
  screening:
    fundamental_conditions:
      - "pe_ttm < 20"
      - "roe > 0.1"
  ranking:
    factors:
      - name: custom_factor
        expr: "close / delay(close, 20) - 1"
      - alpha_001
    weights:
      custom_factor: 0.5
      alpha_001: 0.5
  ```

  最终输出: YAML 配置文件路径 {{output}}
```

### 3.4 CLAUDE.md 集成

```markdown
<!-- 项目 CLAUDE.md 中添加 -->

## AI Agent 快速入口

```bash
# 创建多因子策略 (使用 Skill)
/skill multi-factor-strategy --goal "低估+高ROE"

# 运行因子有效性分析
quantcli analyze ic -e "<表达式>" --period 5 --json

# 批量筛选高 IC 因子
quantcli analyze batch -d ./factors --top 10 --json
```

## 推荐的 AI 工作流

1. **因子发现**: 使用 `analyze batch` 扫描因子库
2. **因子验证**: 使用 `analyze ic` 单因子分析
3. **策略构建**: 使用 `/skill multi-factor-strategy`
4. **回测验证**: 使用 `backtest run --json`
5. **结果解析**: 解析 JSON 输出，提取关键指标
```

### 3.5 错误码体系 (AI 友好)

| 错误码 | 类型 | 说明 | AI 建议 |
|--------|------|------|---------|
| `1001` | DATA_SYMBOL_NOT_FOUND | 股票代码不存在 | 检查 symbol 格式，建议使用 `data list` 获取有效列表 |
| `1002` | DATA_DATE_RANGE | 日期范围无效 | 检查 start/end 格式，建议 YYYY-MM-DD |
| `1003` | DATA_SOURCE_UNAVAILABLE | 数据源不可用 | 检查配置，使用 `config show` 查看数据源设置 |
| `2001` | FORMULA_SYNTAX_ERROR | 公式语法错误 | 检查表达式语法，参考 `formula --help` |
| `2002` | FORMULA_DIVISION_ZERO | 除零错误 | 添加 `where(cond, t, f)` 保护 |
| `2003` | FACTOR_DEPENDENCY_MISSING | 因子依赖缺失 | 确保依赖因子已定义 |
| `3001` | BACKTEST_CONFIG_ERROR | 回测配置错误 | 检查 YAML 格式，参考示例 |
| `3002` | BACKTEST_DATA_INSUFFICIENT | 数据不足 | 扩大日期范围 |
| `9001` | CONFIG_NOT_FOUND | 配置不存在 | 使用 `config init` 初始化 |
| `9002` | PERMISSION_DENIED | 权限错误 | 检查文件读写权限 |

```json
// 错误输出格式 (JSON)
{
  "status": "error",
  "error_code": "2001",
  "error_type": "FORMULA_SYNTAX_ERROR",
  "message": "函数 'ma' 缺少必需参数: period",
  "location": {
    "file": "factors/test.yaml",
    "line": 5,
    "column": 12
  },
  "suggestion": {
    "description": "ma 函数需要两个参数: ma(x, n)",
    "example": "ma(close, 20)",
    "fix": "将表达式改为: ma(close, 20)"
  },
  "documentation": "https://quantcli.dev/docs/formula-syntax#ma",
  "timestamp": "2024-02-01T10:30:00+08:00"
}
```

### 3.6 幂等性设计

```bash
# 可重试的 CLI 调用
# 相同参数 → 相同结果 (缓存命中时)

# 首次运行 (慢)
$ quantcli factor run -n momentum -e "(close/delay(close,20))-1" --start 2020-01-01
# 计算因子...

# 二次运行 (快，缓存命中)
$ quantcli factor run -n momentum -e "(close/delay(close,20))-1" --start 2020-01-01
# 使用缓存: 0.01s

# 强制重新计算
$ quantcli factor run -n momentum -e "(close/delay(close,20))-1" --start 2020-01-01 --force
```

---

## 4. 命令行设计

### 4.1 命令结构

```
quantcli <command> <subcommand> [OPTIONS] [ARGS]

# AI 友好选项
--json        # JSON 模式输出 (AI 推荐)
--verbose     # 详细日志 (调试)
--quiet       # 静默模式 (CI/CD)
```

### 4.2 命令速览

| 命令 | 功能 | AI 优先级 |
|------|------|-----------|
| `quantcli analyze` | IC/IR 因子分析 | P0 (新增) |
| `quantcli filter` | 多阶段因子筛选 | P0 |
| `quantcli data` | 数据获取与管理 | P0 |
| `quantcli factor` | 因子定义与计算 | P0 |
| `quantcli backtest` | 回测引擎 | P0 |
| `quantcli config` | 配置管理 | P0 |

### 4.3 Analyze 命令 (AI 核心)

```bash
# 单因子 IC/IR 分析
quantcli analyze ic -e "<表达式>" -n "<因子名>" --period 5 --json

# 批量因子分析 (筛选有效因子)
quantcli analyze batch -d ./factors --min_ic 0.03 --top 20 --json

# 参数说明
--expr, -e        # 因子表达式 [required]
--name, -n        # 因子名称
--period          # 未来收益周期 (默认 5 天)
--window          # 滚动 IC 窗口 (默认 60 天)
--method          # IC 计算方法: pearson/spearman (默认 spearman)
--min_ic          # 最小 IC 阈值 (批量筛选用)
--top             # 显示 Top N 结果
--json            # JSON 格式输出
```

### 4.4 Filter 命令 (多阶段筛选)

```bash
# 多阶段因子筛选
quantcli filter run -f strategy.yaml --top 50 --json

# 仅执行筛选阶段
quantcli filter screening -f strategy.yaml --output candidates.txt
```

### 4.5 数据命令 `data`

```bash
# 下载数据
quantcli data fetch --source akshare --symbol 600519 --start 2020-01-01

# 列出缓存
quantcli data cache ls

# 清理缓存
quantcli data cache clean --older-than 30d
```

### 4.6 因子命令 `factor`

```bash
# 运行单个因子
quantcli factor run -n my_factor --expr "close / ma(close, 20)"

# 从文件运行因子
quantcli factor run-file -f factors/momentum.yaml --symbol 600519
```

### 4.7 回测命令 `backtest`

```bash
# 运行回测 (YAML 策略)
quantcli backtest run -s strategy.yaml --start 2020-01-01 --json

# 单股票回测
quantcli backtest run -s strategy.yaml --symbol 600519 --json
```

### 4.8 配置命令 `config`

```bash
# 查看配置
quantcli config show

# 设置数据源
quantcli config set data.source akshare
```

---

## 5. 文件格式规范

### 5.1 项目目录结构

```
quantcli/
├── data/                    # 数据缓存
│   ├── raw/                # 原始数据 (Parquet)
│   │   └── stock_daily/
│   └── cache/              # 计算缓存
├── factors/                # 因子定义 (YAML)
│   ├── fundamentals/       # 基本面因子
│   ├── technicals/         # 技术因子
│   └── alpha101/           # Alpha101 因子库
├── strategies/             # 策略文件 (YAML)
│   └── dual_ma.yaml
├── results/                # 运行结果
│   └── backtest_xxx/
│       ├── config.yaml
│       ├── trades.csv
│       ├── equity_curve.csv
│       ├── summary.json    # AI 友好格式
│       └── report.html
├── skills/                 # AI Skill 定义
│   ├── multi-factor-strategy.yaml
│   └── gmqd-strategy.yaml
├── CLAUDE.md              # AI Agent 上下文
├── quantcli.yaml          # 全局配置
└── README.md
```

### 5.2 因子文件格式

```yaml
# factors/technicals/momentum_20d.yaml
name: 20日动量因子
type: technical
expr: "(close / delay(close, 20)) - 1"
direction: positive  # positive / negative (AI 需知)
description: 20日累计涨幅
category: momentum
```

### 5.3 策略文件格式

```yaml
# strategies/pe_roe_ma10.yaml
name: PE-ROE-MA10 选股策略
version: 1.0.0
description: 基本面筛选 + 技术面权重排序

screening:
  conditions:
    - "roe > 0.10"
    - "netprofitmargin > 0.05"
  limit: 200

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

### 5.4 AI 结果格式 (JSON)

```json
// results/backtest_xxx/summary.json
{
  "backtest_id": "bt_20240201_143022_abc123",
  "created": "2024-02-01T14:30:22+08:00",
  "config": {
    "strategy": "strategies/dual_ma.yaml",
    "start": "2020-01-01",
    "end": "2024-01-30",
    "initial_capital": 1000000,
    "fee": 0.0003
  },
  "metrics": {
    "returns": {
      "total": 0.358,
      "annual": 0.072,
      "monthly": [
        {"month": "2020-01", "return": 0.02}
      ]
    },
    "risk": {
      "max_drawdown": -0.156,
      "volatility": 0.18
    },
    "ratios": {
      "sharpe": 1.23,
      "sortino": 1.58,
      "calmar": 0.46
    },
    "trading": {
      "win_rate": 0.56,
      "profit_factor": 1.72,
      "total_trades": 156
    }
  },
  "grade": {
    "overall": "B+",
    "sharpe": "A",
    "max_drawdown": "B-",
    "win_rate": "B"
  }
}
```

---

## 6. 公式语法设计

### 6.1 设计原则

```
1. 简洁性 > 完整性
2. 单行表达式优先
3. Python 表达式兼容
4. AI 可解析 (无歧义)
```

### 6.2 内置函数

| 函数 | 说明 | 示例 |
|------|------|------|
| `delay(x, n)` | 延时 n 期 | `delay(close, 5)` |
| `ma(x, n)` | 简单移动平均 | `ma(close, 10)` |
| `ema(x, n)` | 指数移动平均 | `ema(close, 12)` |
| `rolling_std(x, n)` | 滚动标准差 | `rolling_std(close, 20)` |
| `rolling_sum(x, n)` | 滚动求和 | `rolling_sum(volume, 5)` |
| `rank(x)` | 横截面排序 (0-1) | `rank(close)` |
| `zscore(x)` | 标准化 | `zscore(close)` |
| `rsi(x, n=14)` | 相对强弱指数 | `rsi(close, 14)` |
| `correlation(x, y, n)` | 滚动相关性 | `correlation(close, volume, 20)` |
| `cross_up(a, b)` | 金叉 | `cross_up(ma5, ma20)` |
| `where(cond, t, f)` | 条件赋值 | `where(rsi < 30, 1, 0)` |
| `sign(x)` | 符号函数 | `sign(close - open)` |
| `clamp(x, min, max)` | 限制范围 | `clamp(close, 0, 1000)` |

### 6.3 表达式示例

```python
# 动量因子
"(close / delay(close, 20)) - 1"

# 均线偏离度
"(close - ma(close, 10)) / ma(close, 10)"

# RSI 策略
"where(rsi(close, 14) < 30, 1, 0)"

# 量价关系
"(close - open) * volume"
```

---

## 7. 功能模块详解

### 7.1 Analyze 模块 (AI 核心)

| 功能 | 说明 | AI 优先级 |
|------|------|-----------|
| IC 分析 | 信息系数统计 | P0 |
| IR 分析 | 信息比率计算 | P0 |
| 批量扫描 | 多因子有效性排序 | P0 |
| 有效性评级 | IC/IR 综合评级 | P0 |

### 7.2 Filter 模块

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 多阶段筛选 | 基本面 → 日线 → 因子 | P0 |
| 条件过滤 | 表达式条件筛选 | P0 |
| 权重排序 | 因子加权融合 | P0 |

### 7.3 数据管理模块

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 多数据源 | Akshare/Baostock/MySQL | P0 |
| 数据缓存 | Parquet 列式存储 | P0 |
| 数据清洗 | 缺失值/异常值处理 | P1 |

### 7.4 因子模块

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 公式解析 | 表达式解析 | P0 |
| 因子计算 | 向量化计算 | P0 |
| 因子库 | Alpha101 等 | P0 |

### 7.5 回测模块

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 回测引擎 | 事件驱动 | P0 |
| 回测指标 | 夏普/回撤/胜率 | P0 |
| 单股票回测 | 快速验证 | P0 |

---

## 8. 错误处理与用户引导

### 8.1 错误输出格式

```json
{
  "status": "error",
  "error_code": "2001",
  "error_type": "FORMULA_SYNTAX_ERROR",
  "message": "函数 'ma' 缺少必需参数: period",
  "location": {
    "file": "factors/test.yaml",
    "line": 5,
    "column": 12
  },
  "suggestion": {
    "description": "ma 函数需要两个参数: ma(x, n)",
    "example": "ma(close, 20)",
    "fix": "将表达式改为: ma(close, 20)"
  },
  "documentation": "https://quantcli.dev/docs/formula-syntax#ma",
  "timestamp": "2024-02-01T10:30:00+08:00"
}
```

### 8.2 首次使用引导

```bash
$ quantcli --help

QuantCLI v0.1.0 - 量化因子挖掘与回测工具

AI 快速开始:
  /skill multi-factor-strategy --goal "低估+高ROE"
  quantcli analyze ic -e "(close/delay(close,20))-1" --json
  quantcli filter run -f examples/strategies/pe_roe_ma10.yaml --top 30

文档:
  quantcli --help           # 查看所有命令
  quantcli <cmd> --help     # 查看命令帮助
  docs/cli_guide.md         # 详细文档
```

---

## 9. 技术架构

### 9.1 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI 层                                   │
│  Click (命令解析) → Rich (美化输出) → JSON 模式 (AI 输出)        │
├─────────────────────────────────────────────────────────────────┤
│                        Core 层                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Analyze    │  │  Backtest   │  │    Data     │             │
│  │  Engine     │  │   Engine    │  │   Manager   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
├─────────────────────────────────────────────────────────────────┤
│                       Parser 层                                  │
│  FormulaParser (40+ 函数)                                        │
├─────────────────────────────────────────────────────────────────┤
│                        Storage 层                                │
│  SQLite (元数据) + Parquet (行情/因子数据)                       │
├─────────────────────────────────────────────────────────────────┤
│                      DataSource 层                               │
│  AkshareAdapter | BaostockAdapter | MySQLAdapter                │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.10+ | 量化生态最完善 |
| CLI 框架 | Click | 简单灵活，命令分组 |
| 数据存储 | Parquet | 列式存储，高压缩比 |
| 数据查询 | Polars | 高性能向量化 |
| 计算引擎 | NumPy | 向量化计算 |
| 配置 | PyYAML | 简单易读，AI 可解析 |

---

## 10. 发布路线图

### v0.2.0 - AI 友好版本

**目标:** 80% 研究场景 + AI Agent 友好

| 功能 | 状态 | 说明 |
|------|------|------|
| Analyze 命令 | ✅ | IC/IR 分析 |
| JSON 输出 | ✅ | 结构化输出 |
| Skill 定义 | ✅ | Claude Code 集成 |
| 批量因子扫描 | ✅ | 有效性排序 |
| Alpha101 因子库 | ✅ | 10+ 示例因子 |

### v0.3.0 - 完整研究版本

**目标:** 覆盖 95% 研究场景

| 功能 | 状态 | 说明 |
|------|------|------|
| 多阶段筛选 | 🔄 | Filter 命令 |
| 回测引擎 | 🔄 | YAML 策略 |
| 因子库扩展 | 🔄 | 50+ 因子 |
| MySQL 数据源 | 🔄 | 性能优化 |

---

## 11. 功能优先级矩阵

### 11.1 优先级定义

| 优先级 | 说明 | 目标用户 |
|--------|------|---------|
| **P0** | 核心功能，MVP必备 | 所有用户 + AI |
| **P1** | 高频功能，提升体验 | 大多数用户 |
| **P2** | 高级功能，专业场景 | 专业用户 |

### 11.2 AI 相关功能优先级

| 模块 | 功能 | 优先级 | AI 价值 |
|------|------|--------|---------|
| **Analyze** | IC/IR 分析 | P0 | 高 |
| **Analyze** | 批量扫描 | P0 | 高 |
| **Analyze** | 有效性评级 | P0 | 高 |
| **Filter** | 多阶段筛选 | P0 | 高 |
| **Filter** | 权重排序 | P0 | 高 |
| **Factor** | 公式解析 | P0 | 中 |
| **Backtest** | YAML 回测 | P0 | 高 |
| **Data** | 多数据源 | P0 | 低 |

---

## 附录

### A. AI 工作流示例

```bash
#!/bin/bash
# AI Agent 自动化因子研究工作流

# 1. 加载因子库
FACTORS_DIR="./factors/alpha101"

# 2. 批量分析因子有效性
echo "=== 批量因子分析 ==="
quantcli analyze batch -d "$FACTORS_DIR" \
  --period 5 \
  --window 60 \
  --top 20 \
  --output factor_ranking.csv

# 3. 筛选有效因子
EFFECTIVE_FACTORS=$(cat factor_ranking.csv | \
  jq -r '.[] | select(.ir > 0.3) | .name')

# 4. 生成策略配置
echo "=== 生成策略配置 ==="
cat > strategy.yaml << EOF
name: AI筛选因子策略
version: 1.0.0
screening:
  limit: 500
ranking:
  weights:
EOF

# 5. 运行回测
echo "=== 运行回测 ==="
quantcli backtest run -s strategy.yaml \
  --start 2020-01-01 \
  --json | jq '.metrics'
```

### B. Claude Code Skill 使用示例

```markdown
用户: 创建一个小市值+高ROE的选股策略

AI Agent:
```
/skill multi-factor-strategy --goal "小市值+高ROE" --output my_strategy.yaml
```

输出:
```
已生成策略文件: my_strategy.yaml

策略配置:
  - 筛选条件:
    - market_cap < 50亿
    - roe > 0.15
  - 排序因子:
    - market_cap: -0.4 (小市值)
    - roe: 0.6 (高ROE)

运行回测:
  quantcli backtest run -s my_strategy.yaml --start 2020-01-01 --json
```
```

### C. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2024-01-30 | 初始设计文档 |
| 1.1.0 | 2024-02-01 | 添加 AI 友好设计章节 |

---

*文档最后更新: 2024-02-01*
