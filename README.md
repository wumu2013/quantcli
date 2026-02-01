# QuantCLI

**QuantCLI** 是一款专注于**多因子选股**的命令行工具，为个人量化研究者提供轻量、高效、可复现的研究环境。

**AI Agent 友好**: QuantCLI 专为 AI Agent 优化，支持结构化输出、幂等性设计和 Skill 集成。

## 核心功能

- **多因子筛选**: 多阶段因子筛选、权重融合、条件过滤、加分项评分
- **因子计算**: 40+ 内置函数，支持表达式解析
- **IC/IR 分析**: 因子有效性评估，批量扫描高有效性因子
- **回测引擎**: 基于 Backtrader，支持单股票/多因子回测
- **多数据源**: AKShare、Baostock、MySQL
- **AI 友好**: JSON 输出、Skill 集成、Claude Code 支持
- **内置因子库**: 40 个 Alpha101 因子，即点即用

## 安装

```bash
pip install quantcli
```

## 快速开始

```bash
# 查看帮助
quantcli --help

# 多因子筛选 (推荐)
quantcli filter run -f examples/strategies/pe_roe_ma10.yaml --top 30

# 查看所有内置因子
quantcli factors list

# IC/IR 因子有效性分析
quantcli analyze ic -e "(close / delay(close, 20)) - 1" -n "20日动量" --json

# 批量分析因子库
quantcli analyze batch -d examples/alpha101/alpha/ --top 10

# 获取数据
quantcli data fetch 600519 --start 2020-01-01 --end 2024-01-01

# 运行因子
quantcli factor run -n momentum -e "(close / delay(close, 20)) - 1"

# 回测策略
quantcli backtest run -s ma_cross --start 2020-01-01
```

## AI Agent 使用

### JSON 输出模式

所有命令支持 `--json` 参数，以机器可解析的格式输出：

```bash
# IC/IR 分析
quantcli analyze ic -e "(close/delay(close,20))-1" --json
# {"status": "success", "ic_mean": 0.0285, "ir": 0.47, ...}

# 批量因子分析
quantcli analyze batch -d examples/alpha101/alpha/ --json
```

### IC/IR 评估标准

| 指标 | 含义 | 阈值 |
|------|------|------|
| **IC** | 因子与未来收益的秩相关 | \|IC\| > 0.05 有效 |
| **IR** | IC 均值/标准差（年化） | IR > 0.5 稳定 |

### Alpha101 内置因子库

内置 **40 个 WorldQuant Alpha101 因子**，可直接引用：

```bash
# 查看所有内置因子
quantcli factors list

# 运行 Alpha101 复合策略
quantcli filter run -f examples/alpha101/alpha101_composite.yaml --top 30

# 批量分析因子有效性
quantcli analyze batch -d examples/alpha101/alpha/ --top 10
```

**使用内置因子：**
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

### Claude Code Skill

```markdown
/skill multi-factor-strategy --goal "低估+高ROE" --output strategy.yaml
```

## 多因子筛选示例

创建策略文件 `strategy.yaml`:

```yaml
name: PE-ROE-MA10 选股策略
version: 1.0.0

screening:
  fundamental_conditions:
    - "pe_ttm < 20"
    - "pe_ttm > 0"
    - "roe > 0.1"
  daily_conditions:
    - "close > ma10"

ranking:
  weights:
    pe_ttm: -0.3      # 负权重: 低估值
    roe: 0.5          # 正权重: 高ROE
    ma10_deviation: 0.2
  normalize: zscore

output:
  limit: 50
```

运行筛选:

```bash
quantcli filter run -f strategy.yaml --top 50
```

## 命令

| 命令 | 功能 |
|------|------|
| `quantcli analyze` | IC/IR 因子有效性分析 |
| `quantcli filter` | 多因子筛选 |
| `quantcli factor` | 因子计算与评估 |
| `quantcli factors` | 内置因子管理 |
| `quantcli data` | 数据获取与管理 |
| `quantcli backtest` | 回测引擎 |
| `quantcli config` | 配置管理 |

## AI Skill

`multi-factor-strategy` skill 用于**引导创建多因子选股策略**，生成可独立运行的 YAML 配置文件。

**目的**: 将因子研究、回测验证、策略执行整合为标准化流程，通过 YAML 配置实现:
- 多阶段筛选 (基本面 → 技术面 → 因子评分)
- 权重融合与条件过滤
- 策略可复现、可版本控制
- AI Agent 可直接调用

## 文档

详见 [docs/cli_guide.md](docs/cli_guide.md)

## 许可证

MIT License
