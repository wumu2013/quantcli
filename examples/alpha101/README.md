# WorldQuant Alpha 101 因子库

## 概述

WorldQuant Alpha 101 是全球最经典、最广泛应用的开源量价因子库之一，由 WorldQuant 研究院开发并公开，包含 101 个核心因子，覆盖趋势、反转、波动、资金流向、动量等六大类。

## 目录结构

```
alpha101/
├── alpha/                    # 单因子定义文件
│   ├── alpha_001.yaml       # 经典反转因子
│   ├── alpha_002.yaml       # 量价变化因子
│   ├── alpha_003.yaml       # 波动率反转因子
│   ├── alpha_004.yaml       # 资金流向因子
│   ├── alpha_005.yaml       # 均线交叉趋势因子
│   ├── alpha_006.yaml       # 价格位置因子
│   ├── alpha_007.yaml       # 成交量波动率因子
│   ├── alpha_008.yaml       # 资金净流因子
│   ├── alpha_009.yaml       # 12月动量因子
│   └── alpha_010.yaml       # 均价偏离因子
├── alpha101_composite.yaml  # 复合策略（多因子等权）
├── alpha101_trend.yaml      # 趋势跟踪策略
├── alpha101_reversal.yaml   # 均值回归策略
└── README.md                # 本文档
```

## 因子分类

| 因子 | 类别 | 说明 |
|------|------|------|
| ALPHA_001 | 反转 | 20日创新高后转跌 |
| ALPHA_002 | 反转 | 阴线（价格下跌） |
| ALPHA_003 | 波动率 | 短期波动率偏低 |
| ALPHA_002 | 资金流 | 下跌放量 |
| ALPHA_005 | 趋势 | 均线偏离度增加 |
| ALPHA_006 | 动量 | 收盘价在当日高位 |
| ALPHA_007 | 波动率 | 成交量波动异常 |
| ALPHA_008 | 资金流 | 资金净流入 |
| ALPHA_009 | 动量 | 12月累计收益 |
| ALPHA_010 | 反转 | 短期回调机会 |

## 使用方法

### 筛选策略
```bash
# 运行复合策略
quantcli filter run -f alpha101_composite.yaml --top 30

# 运行趋势策略
quantcli filter run -f alpha101_trend.yaml --top 30

# 运行反转策略
quantcli filter run -f alpha101_reversal.yaml --top 30
```

### IC/IR 因子有效性分析

```bash
# 单因子 IC/IR 分析
quantcli analyze ic -e "(close / delay(close, 20)) - 1" -n "20日动量" --period 5

# 批量分析目录下所有因子（显示 Top 10）
quantcli analyze batch -d alpha/ --top 10 --output ic_results.csv

# 批量分析 Alpha101 因子（10日未来收益，90日滚动窗口）
quantcli analyze batch -d alpha/ --period 10 --window 90 --top 10
```

#### IC/IR 评估标准

| 指标 | 含义 | 阈值 |
|------|------|------|
| **IC** | 因子与未来收益的秩相关 | \|IC\| > 0.05 有效 |
| **IR** | IC 均值/标准差（年化） | IR > 0.5 稳定 |
| **IC > 0 占比** | IC 为正的比例 | > 55% 稳定 |

#### 输出示例
```
==================================================
IC/IR Analysis Results
==================================================
  Overall IC (spearman):    +0.0321
  Rolling IC Mean (ann):     +0.0285
  Rolling IC Std:           +0.0852
  IR (annualized):          +0.47
  IC > 0 ratio:             56.2%
  Samples:                  180

  Effectiveness Rating:
    ★★☆ Moderate Factor

  Direction: Positive (long bias)
```

## 因子特性

- **低相关性**：101个因子间平均相关性约15.9%
- **数据要求低**：仅需OHLCV公开数据
- **可复现性高**：明确的数学定义
- **多周期适配**：支持日线、周线等多周期

## 扩展更多因子

如需添加更多Alpha 101因子，请参考 `alpha/*.yaml` 文件格式：

```yaml
name: ALPHA_XXX 因子名称
type: alpha101
expr: "因子表达式（使用内置函数）"
direction: positive  # positive/negative
category: trend|reversal|volatility|flow|momentum
description: |
  因子详细说明
```
