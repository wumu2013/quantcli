# QuantCLI Documentation

## QuantCLI - Multi-Factor Stock Selection CLI Tool

**QuantCLI** is a command-line tool designed for quantitative research and multi-factor stock selection.

### Key Features

- **Multi-Stage Filter Pipeline**: Three-stage filtering (fundamental → price → factors)
- **40+ Built-in Factors**: Alpha101 factor library included
- **Formula Parser**: 40+ built-in functions (delay, ma, ema, rank, zscore, etc.)
- **IC/IR Analysis**: Evaluate factor effectiveness
- **Backtesting**: Strategy backtesting support (MySQL required)
- **AI Agent Friendly**: JSON output mode, idempotent APIs

### Quick Start

```bash
# Install from PyPI (recommended)
pip install quantcli

# Or install from source
git clone https://github.com/wumo2013/quantcli.git
cd quantcli
pip install -e .

# Verify installation
quantcli --help
```

### Basic Usage

```bash
# Run a strategy
quantcli filter run -f examples/strategies/pe_roe_ma10.yaml --top 50

# Compute a single factor
quantcli factor run -n momentum -e "(close / delay(close, 20)) - 1"

# Analyze factor effectiveness (IC/IR)
quantcli analyze ic -e "(close / delay(close, 20)) - 1" -n "20日动量" --period 5

# List available expressions
quantcli expr list
```

---

## Claude Code Skill

QuantCLI provides a **Claude Code Skill** for AI agents to help users create multi-factor stock selection strategies.

### Download Skill

**[Download skill.md](https://raw.githubusercontent.com/wumu2013/quantcli/main/docs/skill.md)** - Claude Code Skill file for multi-factor strategy creation

### Install Skill

1. Download the skill file above
2. Copy to your Claude Code skills directory:
   ```bash
   mkdir -p ~/.claude/skills/skill-multi-factor-strategy
   cp skill.md ~/.claude/skills/skill-multi-factor-strategy/
   ```
3. Restart Claude Code and invoke with `/multi-factor-strategy`

### Skill Features

- Guides users through strategy creation workflow
- Generates independent YAML configuration files
- Supports 40+ built-in Alpha101 factors
- Provides factor selection recommendations based on strategy goals

---

## Documentation

- [CLI Guide](cli_guide.md) - Complete CLI command reference

---

## Links

- **Homepage**: http://make.datavoid.fun/quantcli/
- **GitHub**: https://github.com/wumo2013/quantcli
- **PyPI**: https://pypi.org/project/quantcli/
- **Issues**: https://github.com/wumo2013/quantcli/issues
