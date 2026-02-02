# MySQL 数据源说明

**版本:** v1.2.0

回测引擎使用 MySQL 作为数据源，以提供高效的批量数据查询能力。

## 环境配置

### 1. 安装 MySQL

```bash
# macOS
brew install mysql
brew services start mysql

# 或使用 Docker
docker run -d --name mysql-quantcli \
  -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=password \
  -e MYSQL_DATABASE=quantcli \
  mysql:8.0
```

### 2. 创建数据库和用户

```sql
-- 登录 MySQL
mysql -u root -p

-- 创建数据库
CREATE DATABASE quantcli CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建用户（可选）
CREATE USER 'quantcli'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON quantcli.* TO 'quantcli'@'localhost';
FLUSH PRIVILEGES;
```

### 3. 配置环境变量

```bash
# ~/.bashrc 或 ~/.zshrc
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD=your_password
export MYSQL_DATABASE=quantcli
export MYSQL_TABLE_PREFIX=  # 可选，表前缀
```

### 4. 安装依赖

```bash
pip install pymysql
# 或重新安装 quantcli（已包含 pymysql）
pip install -e .
```

## 数据库表结构

### 1. 日线数据表 (daily_prices)

```sql
CREATE TABLE IF NOT EXISTS daily_prices (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL COMMENT '股票代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    open DECIMAL(10, 2) COMMENT '开盘价',
    high DECIMAL(10, 2) COMMENT '最高价',
    low DECIMAL(10, 2) COMMENT '最低价',
    close DECIMAL(10, 2) COMMENT '收盘价',
    volume BIGINT COMMENT '成交量',
    amount DECIMAL(20, 2) COMMENT '成交额',
    UNIQUE KEY uk_symbol_date (symbol, trade_date),
    INDEX idx_symbol (symbol),
    INDEX idx_trade_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**说明**：
- `symbol`: 股票代码，如 `600519`、`000001`
- `trade_date`: 交易日期
- 价格字段精度：2位小数
- 唯一索引确保每日每只股票只有一条记录

### 2. 股票列表表 (stock_list)

```sql
CREATE TABLE IF NOT EXISTS stock_list (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE COMMENT '股票代码',
    name VARCHAR(100) COMMENT '股票名称',
    exchange VARCHAR(10) COMMENT '交易所 (SSE/SZSE)',
    market VARCHAR(20) COMMENT '市场 (上海/深圳)',
    list_date DATE COMMENT '上市日期',
    status VARCHAR(20) DEFAULT 'active' COMMENT '状态',
    INDEX idx_exchange (exchange),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 3. 交易日历表 (trading_calendar)

```sql
CREATE TABLE IF NOT EXISTS trading_calendar (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trade_date DATE NOT NULL UNIQUE COMMENT '交易日期',
    exchange VARCHAR(10) COMMENT '交易所',
    is_trading_day TINYINT(1) DEFAULT 1 COMMENT '是否交易日',
    INDEX idx_exchange_date (exchange, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4. 基本面数据表 (fundamental_data)

```sql
CREATE TABLE IF NOT EXISTS fundamental_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL COMMENT '股票代码',
    report_date DATE NOT NULL COMMENT '报告期',
    roe DECIMAL(10, 4) COMMENT '净资产收益率',
    netprofitmargin DECIMAL(10, 4) COMMENT '净利润率',
    grossprofitmargin DECIMAL(10, 4) COMMENT '毛利率',
    pe_ttm DECIMAL(10, 2) COMMENT '市盈率 TTM',
    pb DECIMAL(10, 2) COMMENT '市净率',
    UNIQUE KEY uk_symbol_date (symbol, report_date),
    INDEX idx_symbol (symbol),
    INDEX idx_report_date (report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 5. 分钟级数据表 (intraday_prices)

```sql
CREATE TABLE IF NOT EXISTS intraday_prices (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL COMMENT '股票代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    trade_time TIME NOT NULL COMMENT '交易时间',
    period VARCHAR(10) NOT NULL COMMENT '周期: 1min/5min/15min/30min/60min',
    open DECIMAL(10, 2) COMMENT '开盘价',
    high DECIMAL(10, 2) COMMENT '最高价',
    low DECIMAL(10, 2) COMMENT '最低价',
    close DECIMAL(10, 2) COMMENT '收盘价',
    volume BIGINT COMMENT '成交量',
    amount DECIMAL(20, 2) COMMENT '成交额',
    UNIQUE KEY uk_symbol_datetime_period (symbol, trade_date, trade_time, period),
    INDEX idx_symbol (symbol),
    INDEX idx_date_period (trade_date, period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**说明**：
- `period`: 支持 `1min`, `5min`, `15min`, `30min`, `60min`
- 唯一索引确保同一周期内每分钟只有一条记录
- 单只股票一天约 240 条记录（4 小时交易时间）

## 数据同步

### 从 Akshare 同步日线数据

```python
from quantcli.datasources import create_datasource
from datetime import date

# 创建 MySQL 数据源
ds = create_datasource("mysql")

# 同步日线数据（可选：指定日期范围和股票列表）
ds.sync_from_akshare(
    start_date=date(2020, 1, 1),    # 开始日期
    end_date=date(2024, 12, 31),    # 结束日期
    symbols=["600519", "000001", "000002"]  # 可选：指定股票
)

# 同步交易日历
ds.sync_trading_calendar(exchange="SSE")
```

### 同步分钟级数据

```python
from quantcli.datasources import create_datasource
from datetime import date

ds = create_datasource("mysql")

# 同步 5 分钟级数据
ds.sync_intraday_from_akshare(
    symbol="600519",
    start_date=date(2024, 1, 1),
    end_date=date(2024, 1, 31),
    period="5"  # 1/5/15/30/60
)

# 批量同步多只股票的分钟数据
for symbol in ["600519", "000001", "000002"]:
    ds.sync_intraday_from_akshare(
        symbol=symbol,
        period="5"
    )
```

### 同步股票列表

股票列表会在同步日线数据时自动关联。

## 数据同步工具 (create_sync)

`create_sync` 是通用的数据同步工具，支持从多个数据源同步数据到 MySQL。

### 支持的数据源

| 数据源 | 说明 | 需要 Token |
|--------|------|------------|
| `gm` | 掘金量化 | 是 |
| `akshare` | Akshare | 否 |
| `baostock` | Baostock (同 akshare) | 否 |

### 快速开始

#### 方式 1：使用环境变量（默认连接）

```python
from quantcli.datasources import create_sync
from datetime import date

# 创建同步器（使用默认 MySQL 连接）
sync = create_sync("gm", token="your_gm_token")

# 查看同步进度
progress = sync.get_progress("600519")
print(f"600519 最新日期: {progress}")
```

#### 方式 2：直接传入 MySQL 连接参数

```python
from quantcli.datasources import create_sync
from datetime import date

# 创建同步器（指定 MySQL 连接）
sync = create_sync(
    "akshare",  # 数据源
    mysql_host="192.168.1.100",      # MySQL 主机
    mysql_port=3307,                 # MySQL 端口
    mysql_user="quant",              # 用户名
    mysql_password="secret",         # 密码
    mysql_database="quantdb",        # 数据库名
    mysql_table_prefix="prod_"       # 表前缀（可选）
)

# 同步日线数据
result = sync.sync_daily(
    symbols=["600519", "000001"],
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31)
)
print(result)
# {'600519': 240, '000001': 238}
```

### API 参考

```python
create_sync(
    source: str,                     # 数据源: "gm", "akshare", "baostock"
    token: str = None,               # API token (仅 gm 需要)
    mysql_host: str = None,          # MySQL 主机地址
    mysql_port: int = None,          # MySQL 端口
    mysql_user: str = None,          # MySQL 用户名
    mysql_password: str = None,      # MySQL 密码
    mysql_database: str = None,      # MySQL 数据库名
    mysql_table_prefix: str = None,  # 表前缀
) -> DataSync
```

**说明**：
- 如果不传 MySQL 参数，则使用环境变量配置
- 传入 `None` 的参数会回退到环境变量或默认值
- 表前缀可用于区分不同项目的数据表（如 `prod_daily_prices`）

### 批量同步日线

```python
from quantcli.datasources import create_sync
from datetime import date

sync = create_sync("gm", token="your_token")

# 同步多只股票的日线数据
result = sync.sync_daily(
    symbols=["600519", "000001", "000002"],
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31)
)
print(result)
# {'600519': 240, '000001': 238, '000002': 235}
```

### 批量同步分钟线

```python
from quantcli.datasources import create_sync
from datetime import date

sync = create_sync("gm", token="your_token")

# 同步 5 分钟线
result = sync.sync_minute(
    symbols=["600519", "000001"],
    period="5",           # 1/5/15/30/60
    start_date=date(2024, 1, 1),
    end_date=date(2024, 1, 31)
)
print(result)
# {'600519': 4800, '000001': 4750}
```

### 一次性批量同步

```python
# 同步日线和多周期分钟线
result = sync.sync_all(
    symbols=["600519", "000001"],
    start_date=date(2024, 1, 1),
    periods=["1", "5", "15"]  # 同步 1/5/15 分钟线
)
print(result)
# {'daily': {...}, 'minute': {'1': {...}, '5': {...}, '15': {...}}}
```

### on_bar 事件中实时同步

在掘金量化策略的 `on_bar` 回调中实时同步数据到 MySQL：

```python
# coding=utf-8
from __future__ import print_function, absolute_import
from gm.api import *
from quantcli.datasources import create_sync


def init(context):
    # 初始化同步器
    context.sync = create_sync("gm", token='your_token_id')

    # 订阅股票
    context.symbols = ['SHSE.600000', 'SHSE.600519']
    for symbol in context.symbols:
        subscribe(symbols=symbol, frequency='1d')
        subscribe(symbols=symbol, frequency='60s')


def on_bar(context, bars):
    """每根 bar 触发时同步数据到 MySQL"""
    for bar in bars:
        # 同步日线数据
        context.sync.sync_bar(bar.symbol, bar)

        # 同步 5 分钟线数据
        context.sync.sync_minute_bar(bar.symbol, bar, period="5")

        # 策略逻辑
        if bar.close > bar.open:
            print(f"买入信号: {bar.symbol}")


def on_backtest_finished(context, indicator):
    context.sync.close()
    print("数据同步完成")


if __name__ == '__main__':
    run(
        strategy_id='strategy_id',
        filename='main.py',
        mode=MODE_LIVE,  # 实时模式
        token='your_token_id',
    )
```

### on_bar 方法说明

| 方法 | 说明 |
|------|------|
| `sync_bar(symbol, bar)` | 同步日线 Bar，支持 Bar 对象或字典 |
| `sync_minute_bar(symbol, bar, period="5")` | 同步分钟线 Bar，period 可选 1/5/15/30/60 |

### 同步进度查询

```python
# 查询单只股票的同步进度
progress = sync.get_progress("600519")
# 返回: date(2024, 12, 31) 或 None

# 查询分钟线进度
progress_minute = sync.get_progress_minute("600519", "5")
```

### Akshare 同步

```python
from quantcli.datasources import create_sync
from datetime import date

# 方式 1：使用环境变量
sync = create_sync("akshare")

# 方式 2：指定 MySQL 连接
sync = create_sync(
    "akshare",
    mysql_host="localhost",
    mysql_user="root",
    mysql_password="",
    mysql_database="quantcli",
    mysql_table_prefix="test_"
)

# 同步日线
sync.sync_daily(["600519", "000001"], date(2024, 1, 1))

# 同步分钟线
sync.sync_minute(["600519"], "5", date(2024, 1, 1))

# 同步基本面
sync.sync_fundamental(["600519"])

# 健康检查
health = sync._mysql.health_check()
print(health)
```

## 使用示例

### Python API

```python
from quantcli.datasources import create_datasource
from datetime import date

# 创建数据源
ds = create_datasource("mysql")

# 获取单只股票日线
df = ds.get_daily("600519", date(2024, 1, 1), date(2024, 1, 31))
print(df.head())
#     symbol       date   open   high    low  close    volume      amount
# 0  600519 2024-01-02  1680  1700  1670  1690  1234567  2.08e+09
# ...

# 批量获取多只股票（回测优化）
price_data = ds.get_multi_daily(
    symbols=["600519", "000001", "000002"],
    start_date=date(2024, 1, 1),
    end_date=date(2024, 1, 31)
)
# 返回: {"600519": DataFrame, "000001": DataFrame, "000002": DataFrame}

# 获取交易日历
trading_days = ds.get_trading_calendar()
print(f"交易日数量: {len(trading_days)}")

# 获取分钟级数据
df = ds.get_intraday(
    symbol="600519",
    start_date=date(2024, 1, 15),
    end_date=date(2024, 1, 16),
    period="5"  # 5分钟级别
)
print(df.head())
#                     date   open   high    low  close   volume      amount
# 0 2024-01-15 09:30:00  1700  1705  1698  1702  12345  2.10e+07
# ...

# 批量获取多只股票分钟数据（回测优化）
intraday_data = ds.get_multi_intraday(
    symbols=["600519", "000001"],
    start_date=date(2024, 1, 15),
    end_date=date(2024, 1, 16),
    period="5"
)
# 返回: {"600519": DataFrame, "000001": DataFrame}

# 健康检查
health = ds.health_check()
print(health)
# {'status': 'ok', 'source': 'mysql', 'database': 'quantcli', 'daily_prices_count': 1250000}
```

### CLI 命令

```bash
# 回测（自动使用 MySQL 数据源）
quantcli backtest run -s examples/strategies/my_strategy.yaml --start 2024-01-01

# 指定单只股票回测
quantcli backtest run -s strategy.yaml --symbol 600519 --start 2024-01-01
```

## 性能优化

### 1. 索引优化

表已包含以下索引：
- `daily_prices`: `(symbol, trade_date)` 唯一索引
- `stock_list`: `symbol` 唯一索引
- `trading_calendar`: `(exchange, trade_date)` 索引
- `fundamental_data`: `(symbol, report_date)` 唯一索引

### 2. 查询优化

**批量查询**（推荐用于回测）：
```python
# 避免循环查询
for symbol in symbols:
    df = ds.get_daily(symbol, start, end)  # 慢：N 次查询

# 使用批量查询
price_data = ds.get_multi_daily(symbols, start, end)  # 快：1 次查询
```

**日期范围查询**：
```python
# 尽量使用合理的日期范围
df = ds.get_daily("600519", date(2024, 1, 1), date(2024, 12, 31))
```

### 3. 连接池配置

对于高并发场景，可以配置连接池：

```python
from DBUtils.PooledDB import PooledDB
import pymysql

pool = PooledDB(
    creator=pymysql,
    maxconnections=10,
    mincached=2,
    maxcached=5,
    blocking=True,
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DATABASE,
    charset='utf8mb4'
)
```

## 数据维护

### 查看数据量

```sql
-- 查看日线数据量
SELECT COUNT(*) as total FROM daily_prices;
-- 查看每只股票数据量
SELECT symbol, COUNT(*) as cnt FROM daily_prices GROUP BY symbol ORDER BY cnt DESC LIMIT 10;
-- 查看日期范围
SELECT MIN(trade_date) as start_date, MAX(trade_date) as end_date FROM daily_prices;
```

### 清理数据

```sql
-- 删除指定日期范围的数据
DELETE FROM daily_prices WHERE trade_date < '2020-01-01';

-- 重置所有数据
TRUNCATE TABLE daily_prices;
```

### 备份数据

```bash
mysqldump -u root -p quantcli > quantcli_backup.sql

# 恢复
mysql -u root -p quantcli < quantcli_backup.sql
```

## 常见问题

### Q: 连接失败

**错误**: `2003, Can't connect to MySQL server`

**解决**:
1. 检查 MySQL 服务是否运行
2. 检查 host 和 port 配置
3. 检查防火墙设置

```bash
# 检查 MySQL 状态
brew services list | grep mysql
# 或
docker ps | grep mysql
```

### Q: 权限错误

**错误**: `1045, Access denied`

**解决**: 检查用户名和密码配置，确保用户有对应数据库的访问权限。

### Q: 数据为空

**解决**: 运行数据同步

```python
from quantcli.datasources import create_datasource

ds = create_datasource("mysql")
ds.sync_from_akshare(start_date=date(2020, 1, 1))
```

## AI 友好使用

### 幂等性设计

MySQL 数据源的 API 设计遵循幂等性原则，AI Agent 可以安全地重试：

```python
# 相同的查询总是返回相同的结果
df1 = ds.get_daily("600519", date(2024,1,1), date(2024,1,31))
df2 = ds.get_daily("600519", date(2024,1,1), date(2024,1,31))
# df1.equals(df2) == True
```

### 批量查询优化

AI Agent 应使用批量查询以提高效率：

```python
# ✅ 推荐：批量查询
price_data = ds.get_multi_daily(
    symbols=["600519", "000001", "600036"],
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31)
)
# 返回: Dict[str, DataFrame]

# ❌ 避免：循环查询
for symbol in symbols:
    df = ds.get_daily(symbol, start, end)  # 慢
```

### JSON 输出格式

健康检查返回 JSON 兼容格式：

```python
health = ds.health_check()
# {
#     "status": "ok",
#     "source": "mysql",
#     "database": "quantcli",
#     "daily_prices_count": 1250000,
#     "intraday_prices_count": 300000000
# }
```

## 完整配置示例

### 环境变量配置

```bash
# ~/.bashrc 或 ~/.zshrc
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_USER=quantcli
export MYSQL_PASSWORD=secure_password_here
export MYSQL_DATABASE=quantcli
export MYSQL_TABLE_PREFIX=
```

### 代码中使用连接参数

```python
from quantcli.datasources import create_sync
from quantcli.datasources import create_datasource
from datetime import date, timedelta

# === 使用 create_sync 同步数据 ===

# 同步到远程 MySQL
sync = create_sync(
    "akshare",
    mysql_host="192.168.1.100",
    mysql_port=3306,
    mysql_user="quant",
    mysql_password="secret",
    mysql_database="quantdb",
    mysql_table_prefix="prod_"
)

# 同步数据
sync.sync_daily(["600519", "000001"], date(2024, 1, 1), date(2024, 12, 31))

# === 使用 create_datasource 查询数据 ===

# 连接到 MySQL
ds = create_datasource("mysql")

# 检查数据量
health = ds.health_check()
print(f"数据记录数: {health.get('daily_prices_count', 0)}")

# 获取最近 100 个交易日的数据
end_date = date.today() - timedelta(1)
start_date = end_date - timedelta(100)
df = ds.get_daily("600519", start_date, end_date)
print(f"获取 {len(df)} 条记录")
```

### 远程 MySQL 连接示例

```python
# 连接到生产环境数据库
sync = create_sync(
    "gm",
    token="your_gm_token",
    mysql_host="prod-db.example.com",
    mysql_port=3306,
    mysql_user="app_user",
    mysql_password="your_password",
    mysql_database="quant_production",
    mysql_table_prefix=""  # 生产环境无前缀
)

# 同步数据到生产环境
sync.sync_daily(["600519"], date(2025, 1, 1))

# 连接到测试环境数据库
test_sync = create_sync(
    "akshare",
    mysql_host="localhost",
    mysql_database="quant_test",
    mysql_table_prefix="test_"  # 测试环境使用前缀
)

# 同步数据到测试环境
test_sync.sync_daily(["600519"], date(2025, 1, 1))
```
