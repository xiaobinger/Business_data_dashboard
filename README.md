# 📊 Business Data Dashboard

业务数据看板桌面工具，基于 Flask + ECharts 构建，支持多数据源查询、图表钻取、主题切换，集成 Nacos 配置中心、Redis 查询缓存与 MySQL 元数据管理。

---

## ✨ 功能特性

- **多数据源管理**：支持 MySQL、PostgreSQL、SQLite，通过 Nacos 统一管理连接配置
- **灵活查询**：自定义 SQL、维度切换（年/月/日）、多数据源合并查询
- **图表钻取**：双击图表区域可按时间维度逐级下钻（年→月→日），面包屑导航回溯
- **多种图表**：折线图、柱状图、饼图、散点图、面积图，支持全屏查看
- **主题系统**：双层主题架构，全局色调 + 看板色调独立切换，过渡动画自动跟随
- **查询缓存**：基于 Redis 的查询结果缓存，相同查询条件直接命中缓存，支持强制刷新
- **快捷查询**：保存常用查询条件，一键快速执行，数据持久化到 MySQL
- **脚本管理**：SQL 脚本模板管理，支持参数化查询，数据持久化到 MySQL
- **系统设置**：前端可视化配置 Nacos 连接信息、缓存过期时间，实时检测连接状态

---

## 🏗 项目结构

```
data_dashboard/
├── main.py                  # 应用入口，启动 Flask 服务
├── config/
│   └── __init__.py          # 全局配置、Nacos/Redis/元数据库配置读取、JSON 工具函数
├── api/
│   ├── __init__.py
│   └── routes.py            # Flask 路由，所有后端 API 端点
├── core/
│   ├── __init__.py
│   ├── cache.py             # Redis 查询缓存（动态导入，降级为内存缓存）
│   ├── nacos_config.py      # Nacos 配置中心客户端（适配 v3.x async API）
│   ├── meta_store.py        # 元数据库管理（快捷查询、脚本的 MySQL 持久化）
│   ├── db_manager.py        # 数据库连接管理、SQL 执行
│   ├── query_engine.py      # 查询引擎，维度参数构建、合并查询
│   ├── data_merger.py       # 多数据源数据合并
│   └── ssh_tunnel.py        # SSH 隧道，支持通过跳板机连接数据库
├── static/
│   └── index.html           # 前端单页面（HTML + CSS + JS）
├── data/                    # 运行时数据目录（git 忽略）
│   └── app_config.json      # Nacos 连接配置（引导配置）
├── deploy.sh                # 远程部署脚本（启动/停止/重启/日志/清理）
├── Jenkinsfile              # Jenkins CI/CD 流水线
├── requirements.txt         # Python 依赖
└── .gitignore
```

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- MySQL 服务（元数据存储：快捷查询、脚本管理）
- Redis 服务（查询缓存）
- Nacos 服务（配置中心）

### 本地运行

```bash
# 克隆仓库
git clone https://github.com/xiaobinger/Business_data_dashboard.git
cd Business_data_dashboard

# 安装依赖
pip install -r requirements.txt

# 启动应用
python main.py
```

启动后自动打开浏览器访问 `http://127.0.0.1:9527`。

### 首次配置

1. 启动后点击工具栏 **⚙ 系统设置** 按钮
2. 填写 Nacos 连接信息（Server Addresses、Username、Password 等）
3. 点击 **保存并重连**，确认 Nacos、Redis、元数据库均显示已连接
4. 数据库连接、Redis 连接、元数据库连接配置均在 Nacos 上管理

---

## ⚙ 配置说明

### 配置架构

```
本地 app_config.json          Nacos 配置中心
┌───────────────────┐        ┌──────────────────────────────┐
│ Nacos 连接信息     │        │ data_dashboard_connections    │ ← 数据库连接配置
│  server_addresses  │        │ data_dashboard_redis          │ ← Redis 连接配置
│  username/password │ ────→  │ data_dashboard_meta           │ ← 元数据库连接配置
│  namespace/group   │        │                              │
│  data_id           │        └──────────────────────────────┘
│  redis_data_id     │
│  meta_data_id      │
│ cache_ttl          │
└───────────────────┘
```

**本地只存 Nacos 自身的连接信息**（引导配置），数据库连接、Redis 连接、元数据库连接统一从 Nacos 读取。

### 配置优先级

| 配置项 | 来源 | 说明 |
|-------|------|------|
| Nacos 连接信息 | `data/app_config.json` | 本地引导，启动时连接 Nacos |
| 数据库连接 | Nacos `data_dashboard_connections` | 只从 Nacos 读写 |
| Redis 连接 | Nacos `data_dashboard_redis` | 只从 Nacos 读写 |
| 元数据库连接 | Nacos `data_dashboard_meta` | 只从 Nacos 读写 |
| 缓存过期时间 | `data/app_config.json` | 本地存储 |

### 环境变量覆盖

环境变量优先级最高，可覆盖 Nacos 中的配置：

| 环境变量 | 说明 |
|---------|------|
| `REDIS_HOST` | Redis 主机 |
| `REDIS_PORT` | Redis 端口 |
| `REDIS_DB` | Redis 数据库编号 |
| `REDIS_PASSWORD` | Redis 密码 |
| `META_DB_HOST` | 元数据库主机 |
| `META_DB_PORT` | 元数据库端口 |
| `META_DB_USER` | 元数据库用户名 |
| `META_DB_PASSWORD` | 元数据库密码 |
| `META_DB_NAME` | 元数据库库名 |
| `NACOS_SERVER_ADDRESSES` | Nacos 地址 |
| `NACOS_NAMESPACE` | Nacos 命名空间 |
| `NACOS_GROUP` | Nacos 分组 |
| `NACOS_DATA_ID` | Nacos 连接配置 Data ID |
| `NACOS_USERNAME` | Nacos 用户名 |
| `NACOS_PASSWORD` | Nacos 密码 |
| `NACOS_REDIS_DATA_ID` | Nacos Redis 配置 Data ID |
| `NACOS_META_DATA_ID` | Nacos 元数据库配置 Data ID |

### Nacos 配置格式

**数据库连接配置**（Data ID: `data_dashboard_connections`）：

```json
[
  {
    "name": "生产库",
    "db_type": "mysql",
    "host": "192.168.10.100",
    "port": 3306,
    "database": "business_db",
    "username": "readonly",
    "password": "your_password",
    "ssh_tunnel": null
  }
]
```

**Redis 连接配置**（Data ID: `data_dashboard_redis`）：

```json
{
  "host": "192.168.10.204",
  "port": 6379,
  "db": 0,
  "password": "your_password"
}
```

**元数据库连接配置**（Data ID: `data_dashboard_meta`）：

```json
{
  "host": "192.168.10.100",
  "port": 3306,
  "username": "dashboard_meta",
  "password": "your_password",
  "database": "data_dashboard_meta"
}
```

> 元数据库用于持久化存储快捷查询和脚本配置。系统启动时会自动建表，如果表为空则插入内置的种子数据。

---

## 🗄 元数据库

快捷查询和脚本通过 MySQL 元数据库管理，使用 SQLAlchemy ORM 映射。

### 表结构

**quick_queries** — 快捷查询表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 自增主键 |
| name | VARCHAR(255) | 快捷查询名称（唯一） |
| script_name | VARCHAR(255) | 关联的脚本名称 |
| conn_name | VARCHAR(255) | 数据源连接名称 |
| merge_names | JSON | 合并数据源列表 |
| merge_mode | VARCHAR(50) | 合并模式（aggregate/separate） |
| merge_key | VARCHAR(255) | 合并键 |
| hide_fields | JSON | 隐藏字段列表 |
| dimension | VARCHAR(50) | 维度（day/month/year） |
| dp_year | INT | 日期选择器-年 |
| dp_month | INT | 日期选择器-月 |
| dp_year_start | INT | 年份范围-起始 |
| dp_year_end | INT | 年份范围-结束 |
| custom_params | JSON | 自定义参数 |
| layout_count | INT | 图表布局数量 |
| chart_configs | JSON | 图表配置列表 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

**scripts** — 脚本表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 自增主键 |
| name | VARCHAR(255) | 脚本名称（唯一） |
| sql | TEXT | SQL 模板（支持 `{{参数}}` 占位符） |
| chart_type | VARCHAR(50) | 默认图表类型 |
| conn_name | VARCHAR(255) | 默认数据源 |
| merge_conn_names | JSON | 合并数据源列表 |
| description | TEXT | 脚本描述 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### 种子数据

系统首次启动时，如果表为空会自动插入以下种子数据：

- **快捷查询**：「商户进件数年度汇总统计」「商户交易年度统计」
- **脚本**：「商户进件情况」「商户交易统计」

---

## 🔌 API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/connections` | GET | 获取所有数据库连接 |
| `/api/connections` | POST | 新增数据库连接 |
| `/api/connections/<name>` | PUT | 更新连接配置 |
| `/api/connections/<name>` | DELETE | 删除连接 |
| `/api/connections/<name>/test` | POST | 测试连接 |
| `/api/connections/<name>/tables` | GET | 获取表列表 |
| `/api/connections/<name>/tables/<table>/columns` | GET | 获取字段列表 |
| `/api/scripts` | GET | 获取脚本列表 |
| `/api/scripts` | POST | 新增脚本 |
| `/api/scripts/<name>` | PUT | 更新脚本 |
| `/api/scripts/<name>` | DELETE | 删除脚本 |
| `/api/parse-params` | POST | 解析 SQL 中的参数 |
| `/api/parse-columns` | POST | 解析 SQL 中的列名 |
| `/api/execute` | POST | 执行查询（支持缓存、钻取参数） |
| `/api/quick-queries` | GET | 获取快捷查询列表 |
| `/api/quick-queries` | POST | 新增快捷查询 |
| `/api/quick-queries/<name>` | PUT | 更新快捷查询 |
| `/api/quick-queries/<name>` | DELETE | 删除快捷查询 |
| `/api/app-config` | GET | 获取系统配置 |
| `/api/app-config` | POST | 更新系统配置并重连 |
| `/api/app-config/test-redis` | POST | 测试 Redis 连接 |
| `/api/app-config/test-nacos` | POST | 测试 Nacos 连接 |

### 查询缓存机制

- 每次查询以所有查询参数的 MD5 哈希作为缓存 key
- 相同查询条件直接从 Redis 返回缓存结果
- 前端传递 `force_refresh: true` 可跳过缓存强制重新查询
- 看板区域刷新按钮（↻）触发强制刷新并更新缓存

---

## 🎨 主题系统

采用双层 CSS 变量架构：

- **全局主题**（`data-global-theme`）：控制整体页面色调（dark/light 等）
- **看板主题**（`data-theme`）：控制图表区域色调，独立于全局主题

切换看板色调时，图表颜色、过渡动画、加载效果自动跟随变化。

---

## 📦 部署

### Jenkins CI/CD

项目包含 `Jenkinsfile`，流水线流程：

```
拉取代码 → 打包 tar.gz → SCP 到远程服务器 → 解压覆盖 → 重启应用
```

**Jenkins 配置步骤**：

1. 确保 Jenkins 服务器到目标服务器（192.168.10.172）已配置 SSH 免密登录
2. 新建 Pipeline 任务，SCM 指向本仓库，Script Path 填 `Jenkinsfile`
3. 可配置 GitHub Webhook 实现推送自动构建

### 手动部署

```bash
# 上传代码到远程服务器
scp -r ./ root@192.168.10.172:/opt/data_dashboard/

# 登录远程服务器
ssh root@192.168.10.172

# 启动应用
cd /opt/data_dashboard
chmod +x deploy.sh
./deploy.sh start

# 查看实时日志
./deploy.sh log

# 重启应用
./deploy.sh restart

# 清理 30 天前的日志
./deploy.sh rotate 30
```

### 部署脚本命令

| 命令 | 说明 |
|------|------|
| `./deploy.sh start` | 启动应用（自动创建 venv、安装依赖） |
| `./deploy.sh stop` | 停止应用 |
| `./deploy.sh restart` | 重启应用 |
| `./deploy.sh status` | 查看运行状态 |
| `./deploy.sh log` | 实时查看当天日志 |
| `./deploy.sh rotate [天数]` | 清理 N 天前的旧日志 |

### 日志管理

- 日志文件存放在 `logs/` 目录
- 按天自动分割，命名格式：`data_dashboard_2026-05-22.log`
- 通过 `./deploy.sh rotate` 定期清理过期日志

---

## 🔧 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Flask、SQLAlchemy、Pandas |
| 前端 | ECharts、原生 HTML/CSS/JS |
| 缓存 | Redis（降级为内存缓存） |
| 配置中心 | Nacos（nacos-sdk-python v3.x） |
| 元数据存储 | MySQL（快捷查询、脚本持久化） |
| 数据库 | MySQL、PostgreSQL、SQLite |
| 部署 | Jenkins Pipeline、Shell 脚本 |

---

## 📋 依赖

```
flask>=3.0.0
SQLAlchemy>=2.0.0
pandas>=2.0.0
pymysql>=1.1.0
numpy>=1.26.0
paramiko>=3.0.0
redis>=5.0.0
nacos-sdk-python>=1.0.0
```

---

## 📄 许可

MIT License
