# DB Diagnostic PgSQL 扩展开发计划

## 背景

`/dbdiagnostic/` 当前已经支持 PgSQL 的进程状态、事务信息、锁信息和发布订阅，其中这几类诊断 SQL 已接入 `DBDiagnosticSQLTemplate`，可以在 Django admin 中配置默认 SQL。

现有页面仍保留了 MySQL 时代的通用 tab：

- 进程状态
- Top表空间
- 事务信息
- 锁信息
- 发布订阅

PgSQL 当前已经打通：

- 进程状态：`pgsql_processlist`
- 事务信息：`pgsql_trx`
- 锁信息：`pgsql_trxandlocks`
- 发布订阅：`pgsql_pubsub`

PgSQL 尚未补齐：

- PgSQL Top 表空间

后续还需要增加 PgSQL 专属诊断能力，包括复制状态、Replication Slot、Autovacuum 风险、进度视图、Top SQL、等待事件聚合和索引诊断。

## 目标范围

本计划只定义开发顺序和落地边界，不直接修改功能代码。

计划新增能力：

- PgSQL 会话取消和终止
- PgSQL 事务信息
- PgSQL Top 表空间
- PgSQL 复制状态
- PgSQL Replication Slot
- PgSQL Autovacuum 和膨胀风险
- PgSQL Progress 进度视图
- PgSQL Top SQL
- PgSQL 等待事件聚合
- PgSQL 索引诊断

## 开发原则

- 优先补齐现有 tab，减少页面结构变化。
- 优先复用现有权限：
  - `sql.process_view`
  - `sql.process_kill`
  - `sql.tablespace_view`
  - `sql.trx_view`
  - `sql.trxandlocks_view`
- PgSQL 会话管理下新增查询型能力必须接入 `DBDiagnosticSQLTemplate`，统一从 `/admin/sql/dbdiagnosticsqltemplate/` 维护 SQL。
- 后台自定义 SQL 仍只允许单条 `SELECT`。
- PgSQL 诊断 SQL 不直接写死为唯一实现，engine 必须提供代码内置回退 SQL；后台启用配置存在时优先使用后台 SQL。
- PgSQL tab 能拆分就尽量拆分为 `sql/templates/dbdiagnostic/*.html` include 模板，减少对 `dbdiagnostic.html` 主模板的修改。
- PgSQL 前端列定义必须保持 PgSQL 专属，不复用 MySQL 结果列；避免被 MySQL 字段命名、排序字段和详情 formatter 影响。
- 能独立为 PgSQL 实现的 JS/HTML 逻辑尽量独立，降低后续与上游代码合并冲突。
- 新增诊断类型需要同步更新：
  - `DBDiagnosticSQLTemplate.DIAGNOSTIC_TYPE_CHOICES`
  - `sql/engines/pgsql.py`
  - `sql/db_diagnostic.py`
  - `sql/urls.py`
  - 前端 tab include 模板和 PgSQL 专属列定义
  - `src/init_sql/v1.14.0_pgsql_metrics.sql`
  - 单元测试
  - 本文档
- 涉及 Archery 元数据库结构或默认配置批量修改前，必须先按 `agent.md` 约定备份开发库。

## 分阶段计划

### 第一阶段：补齐现有页面能力

#### 1. PgSQL 会话取消和终止

状态：

- 已实现。
- PgSQL 页面单独显示“取消查询”按钮，调用 `pg_cancel_backend(pid)`。
- PgSQL 页面单独显示置灰的“终止会话”按钮，暂不允许点击，避免误断连接。
- PgSQL engine 的 `kill()` 保持终止语义，调用 `pg_terminate_backend(pid)`；后端能力已使用 `test-8` 验证通过，但页面暂不开放。

目标：

- 进程状态 tab 选择 PgSQL 实例时，可以选择 `pid` 并执行取消查询或终止连接。

后端计划：

- 已在 `sql/engines/pgsql.py` 增加：
  - `get_kill_command(thread_ids, thread_ids_check=True)`
  - `get_cancel_command(thread_ids, thread_ids_check=True)`
  - `cancel_backend(thread_ids, thread_ids_check=True)`
  - `terminate_backend(thread_ids, thread_ids_check=True)`
  - `kill(thread_ids, thread_ids_check=True)`，执行 `pg_terminate_backend(pid)`
- 已在 `sql/db_diagnostic.py` 的 `kill_session()` 中增加 `pgsql` 分支。
- 已新增 `cancel_session()` 接口，专用于 PgSQL 取消查询。

前端计划：

- 在 `sql/templates/dbdiagnostic.html` 的会话选择逻辑中支持 PgSQL `pid`。
- 非 PgSQL 实例继续显示原有“终止会话”按钮。
- PgSQL 实例显示“取消查询”和置灰的“终止会话”两个专属按钮。

权限：

- 复用 `sql.process_kill`。

风险：

- `pg_terminate_backend` 会断开连接，可能回滚事务。
- 第一版建议默认使用 `pg_cancel_backend`，降低误操作影响。

#### 2. PgSQL 事务信息

状态：

- 已实现。
- 后端在 `PgSQLEngine.get_long_transaction()` 中查询 `pg_stat_activity`。
- 已接入 `DBDiagnosticSQLTemplate`，诊断类型为 `pgsql_trx`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护 SQL。
- 前端 “事务信息” tab 已按实例类型选择列定义，PgSQL 使用专属字段展示长事务和 `idle in transaction`。
- 事务信息 HTML 已拆到 `sql/templates/dbdiagnostic/trx_tab.html`，主页面通过 include 引入。

目标：

- “事务信息” tab 支持 PgSQL，展示长事务和 `idle in transaction`。

后端计划：

- 已在 `sql/engines/pgsql.py` 增加 `get_long_transaction()`。
- 查询来源优先使用 `pg_stat_activity`。
- 结果按事务持续时间倒序。
- 后台 SQL 支持 `$thread_time$` 占位符，用于替换默认长事务阈值秒数。

建议字段：

| 字段 | 含义 |
| --- | --- |
| `pid` | 后端进程 ID |
| `datname` | 数据库 |
| `usename` | 用户 |
| `application_name` | 应用名 |
| `client_addr` | 客户端地址 |
| `state` | 会话状态 |
| `xact_start` | 事务开始时间 |
| `transaction_duration_seconds` | 事务持续秒数 |
| `query_start` | SQL 开始时间 |
| `query_duration_seconds` | SQL 持续秒数 |
| `backend_xmin` | 后端 xmin |
| `wait_event_type` | 等待事件类型 |
| `wait_event` | 等待事件 |
| `query` | 当前 SQL |

前端计划：

- 已在 `dbdiagnostic.html` 的事务信息列定义中增加 PgSQL 分支。
- 详情展开展示格式化后的 `query`。

权限：

- 复用 `sql.trx_view`。

#### 3. PgSQL Top 表空间

状态：

- 已实现。
- 后端在 `PgSQLEngine.tablespace()` 和 `tablespace_count()` 中查询 PostgreSQL 表级空间占用。
- 已接入 `DBDiagnosticSQLTemplate`，诊断类型为 `pgsql_tablespace`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护 SQL。
- 表空间 HTML 已拆到 `sql/templates/dbdiagnostic/tablespace_tab.html`，主页面通过 include 引入。
- 前端 `Top表空间` tab 已增加 PgSQL 专属列定义，不复用 MySQL 列。

目标：

- “Top表空间” tab 支持 PgSQL，展示表级空间占用和 vacuum 相关信息。

后端计划：

- 已在 `sql/engines/pgsql.py` 增加：
  - `tablespace(offset=0, row_count=14)`
  - `tablespace_count()`
- 已新增诊断类型：`pgsql_tablespace`。
- 默认 SQL 已接入 `DBDiagnosticSQLTemplate`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护。
- engine 查询方法优先读取后台 SQL，后台无启用配置时使用代码内置回退 SQL。
- 后台 SQL 支持 `$limit$`、`$offset$`、`$schema_name$` 占位符，用于服务端分页和 Schema 过滤。
- `$schema_name$` 为空字符串时表示全部 Schema；非空时仅查询对应 Schema。
- 表空间查询支持选择数据库，数据库来自 PgSQL 实例 `get_all_databases()`，Schema 来自所选数据库 `get_all_schemas()`。
- 查询来源：
  - `pg_class`
  - `pg_namespace`
  - `pg_roles`
  - `pg_stat_user_tables`
  - `pg_total_relation_size`
  - `pg_relation_size`
  - `pg_indexes_size`

建议字段：

| 字段 | 含义 |
| --- | --- |
| `schema_name` | schema |
| `table_name` | 表名 |
| `owner_name` | owner |
| `total_size` | 总空间 |
| `table_size` | 表数据空间 |
| `index_size` | 索引空间 |
| `toast_size` | TOAST 空间 |
| `estimated_rows` | PostgreSQL 统计估算行数 |
| `dead_tuples` | dead tuples |
| `stats_status` | 统计状态 |
| `last_vacuum` | 最近手动 vacuum |
| `last_autovacuum` | 最近 autovacuum |
| `last_analyze` | 最近手动 analyze |
| `last_autoanalyze` | 最近 autoanalyze |

前端计划：

- 已在 `tablespaceListTableInfos` 中增加 `pgsql` 列定义。
- 排序字段优先使用 `total_size` 或额外提供 `total_size_bytes`。
- PgSQL 表空间列定义保持专属，不复用 MySQL 的 `table_schema/table_name/engine` 固定字段假设。
- 已拆出 `sql/templates/dbdiagnostic/tablespace_tab.html` include。
- PgSQL 表空间 tab 已增加数据库和 Schema 下拉框，与查询按钮放在同一行；默认空值查询默认库和全部 Schema。

权限：

- 复用 `sql.tablespace_view`。

### 第二阶段：复制链路诊断

#### 4. PgSQL 复制状态

状态：

- 已实现。
- 已新增 `/db_diagnostic/pgsql_replication/` 接口。
- 已在 `PgSQLEngine.replication_status()` 中查询 `pg_stat_replication`。
- 已接入 `DBDiagnosticSQLTemplate`，诊断类型为 `pgsql_replication`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护 SQL。
- 已新增 `sql/templates/dbdiagnostic/replication_tab.html` include。
- 前端列定义和加载逻辑在 `common/static/dbdiagnostic/js/replication.js`。

目标：

- 新增 PgSQL 复制状态诊断，展示主库到备库的流复制状态和延迟。

后端计划：

- 新增接口：`/db_diagnostic/pgsql_replication/`
- 在 `sql/engines/pgsql.py` 增加 `replication_status()`。
- 新增诊断类型：`pgsql_replication`。
- 默认 SQL 必须接入 `DBDiagnosticSQLTemplate`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护。
- engine 查询方法优先读取后台 SQL，后台无启用配置时使用代码内置回退 SQL。

查询来源：

- `pg_stat_replication`

建议字段：

| 字段 | 含义 |
| --- | --- |
| `pid` | walsender PID |
| `usename` | 复制用户 |
| `application_name` | standby 应用名 |
| `client_addr` | standby 地址 |
| `state` | 复制状态 |
| `sync_state` | 同步状态 |
| `sent_lsn` | 已发送 LSN |
| `write_lsn` | 已写入 LSN |
| `flush_lsn` | 已刷盘 LSN |
| `replay_lsn` | 已回放 LSN |
| `write_lag` | 写入延迟 |
| `flush_lag` | 刷盘延迟 |
| `replay_lag` | 回放延迟 |
| `backend_start` | 后端启动时间 |

前端计划：

- 新增 `sql/templates/dbdiagnostic/replication_tab.html` include。
- 列定义使用 PgSQL 复制状态专属字段，不复用其他数据库 tab 的列。

#### 5. PgSQL Replication Slot

状态：

- 已实现。
- 已新增 `/db_diagnostic/pgsql_replication_slots/` 接口。
- 已在 `PgSQLEngine.replication_slots()` 中查询 `pg_replication_slots`。
- 已接入 `DBDiagnosticSQLTemplate`，诊断类型为 `pgsql_replication_slots`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护 SQL。
- 已新增 `sql/templates/dbdiagnostic/replication_slots_tab.html` include。
- 前端列定义和加载逻辑在 `common/static/dbdiagnostic/js/replication.js`。

目标：

- 展示 replication slot 状态和 WAL 保留风险。

后端计划：

- 新增接口：`/db_diagnostic/pgsql_replication_slots/`
- 在 `sql/engines/pgsql.py` 增加 `replication_slots()`。
- 新增诊断类型：`pgsql_replication_slots`。
- 默认 SQL 必须接入 `DBDiagnosticSQLTemplate`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护。
- engine 查询方法优先读取后台 SQL，后台无启用配置时使用代码内置回退 SQL。

查询来源：

- `pg_replication_slots`

建议字段：

| 字段 | 含义 |
| --- | --- |
| `slot_name` | slot 名称 |
| `slot_type` | slot 类型 |
| `database_name` | 数据库 |
| `active` | 是否活跃 |
| `active_pid` | 活跃 PID |
| `restart_lsn` | restart LSN |
| `confirmed_flush_lsn` | confirmed flush LSN |
| `retained_wal_bytes` | 保留 WAL 字节数 |
| `wal_status` | WAL 状态 |
| `safe_wal_size` | 安全 WAL 大小 |

前端计划：

- 可以和复制状态放在同一个 “复制状态” tab 内，也可以拆成 “复制Slot” tab。
- 第一版建议拆成独立 tab，字段更清晰。
- 如拆成独立 tab，模板路径建议为 `sql/templates/dbdiagnostic/replication_slots_tab.html`。

### 第三阶段：维护和性能诊断

#### 6. PgSQL Autovacuum 和膨胀风险

状态：已实现。

目标：

- 展示表级 dead tuple、vacuum/analyze 时间和 xid 年龄风险。

后端计划：

- 新增接口：`/db_diagnostic/pgsql_vacuum/`
- 在 `sql/engines/pgsql.py` 增加 `vacuum_risk()`。
- 新增诊断类型：`pgsql_vacuum`。
- 默认 SQL 必须接入 `DBDiagnosticSQLTemplate`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护。
- engine 查询方法优先读取后台 SQL，后台无启用配置时使用代码内置回退 SQL。

查询来源：

- `pg_stat_user_tables`
- `pg_class`
- `pg_namespace`

建议字段：

| 字段 | 含义 |
| --- | --- |
| `schema_name` | schema |
| `table_name` | 表名 |
| `n_live_tup` | live tuples |
| `n_dead_tup` | dead tuples |
| `dead_tuple_ratio` | dead tuple 比例 |
| `last_vacuum` | 最近手动 vacuum |
| `last_autovacuum` | 最近 autovacuum |
| `last_analyze` | 最近手动 analyze |
| `last_autoanalyze` | 最近 autoanalyze |
| `relfrozenxid_age` | relfrozenxid 年龄 |

前端计划：

- 新增 `sql/templates/dbdiagnostic/vacuum_tab.html` include。
- 列定义使用 PgSQL vacuum 风险专属字段。
- 前端逻辑已拆到 `common/static/dbdiagnostic/js/vacuum.js`，复用数据库和 Schema 过滤接口，并使用 `/db_diagnostic/pgsql_vacuum/` 做服务端分页。

#### 7. PgSQL Progress 进度视图

状态：已实现。

目标：

- 展示正在运行的 vacuum、create index、analyze 等维护任务进度。

后端计划：

- 新增接口：`/db_diagnostic/pgsql_progress/`
- 在 `sql/engines/pgsql.py` 增加 `progress_status()`。
- 新增诊断类型：`pgsql_progress`。
- 默认 SQL 必须接入 `DBDiagnosticSQLTemplate`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护。
- engine 查询方法优先读取后台 SQL，后台无启用配置时使用代码内置回退 SQL。

查询来源：

- `pg_stat_progress_vacuum`
- `pg_stat_progress_create_index`
- `pg_stat_progress_analyze`

建议字段：

| 字段 | 含义 |
| --- | --- |
| `progress_type` | 进度类型 |
| `pid` | PID |
| `database_name` | 数据库 |
| `relation_name` | 对象名称 |
| `phase` | 当前阶段 |
| `progress_percent` | 进度百分比 |
| `blocks_done` | 已处理块 |
| `blocks_total` | 总块 |
| `query` | 当前 SQL |

前端计划：

- 新增 `sql/templates/dbdiagnostic/progress_tab.html` include。
- 列定义使用 PgSQL progress 视图专属字段。
- 前端逻辑已拆到 `common/static/dbdiagnostic/js/progress.js`，通过 `/db_diagnostic/pgsql_progress/` 加载当前运行中的维护任务。

#### 8. PgSQL Top SQL

状态：暂缓占位。当前环境未安装 `pg_stat_statements` 插件，本项先只保留规划，不新增接口、tab 或默认模板；后续插件安装并启用后再开发。

目标：

- 基于 `pg_stat_statements` 展示耗时、调用次数和 IO 消耗最高的 SQL。

后端计划：

- 新增接口：`/db_diagnostic/pgsql_top_sql/`
- 在 `sql/engines/pgsql.py` 增加 `top_sql()`。
- 新增诊断类型：`pgsql_top_sql`。
- 默认 SQL 必须接入 `DBDiagnosticSQLTemplate`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护。
- engine 查询方法优先读取后台 SQL，后台无启用配置时使用代码内置回退 SQL。

查询来源：

- `pg_stat_statements`

建议字段：

| 字段 | 含义 |
| --- | --- |
| `userid` | 用户 ID |
| `dbid` | 数据库 ID |
| `calls` | 调用次数 |
| `total_exec_time` | 总执行时间 |
| `mean_exec_time` | 平均执行时间 |
| `max_exec_time` | 最大执行时间 |
| `rows` | 返回行数 |
| `shared_blks_hit` | shared buffer 命中块 |
| `shared_blks_read` | shared buffer 读取块 |
| `temp_blks_written` | 临时块写入 |
| `query` | SQL |

兼容要求：

- 未安装 `pg_stat_statements` 时，接口应返回清晰错误提示，不影响其他 tab。

前端计划：

- 新增 `sql/templates/dbdiagnostic/top_sql_tab.html` include。
- 详情展开展示格式化后的完整 SQL。

#### 9. PgSQL 等待事件聚合

状态：已实现。

目标：

- 从 `pg_stat_activity` 聚合当前等待事件，快速判断实例是否卡在锁、IO、客户端等待等问题。

后端计划：

- 新增接口：`/db_diagnostic/pgsql_wait_events/`
- 在 `sql/engines/pgsql.py` 增加 `wait_event_summary()`。
- 新增诊断类型：`pgsql_wait_events`。
- 默认 SQL 必须接入 `DBDiagnosticSQLTemplate`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护。
- engine 查询方法优先读取后台 SQL，后台无启用配置时使用代码内置回退 SQL。

查询来源：

- `pg_stat_activity`

建议字段：

| 字段 | 含义 |
| --- | --- |
| `state` | 会话状态 |
| `wait_event_type` | 等待事件类型 |
| `wait_event` | 等待事件 |
| `session_count` | 会话数量 |
| `max_wait_seconds` | 最大等待秒数 |
| `max_query_seconds` | 最大查询秒数 |

前端计划：

- 新增 `sql/templates/dbdiagnostic/wait_events_tab.html` include。
- 列定义使用 PgSQL 等待事件聚合专属字段。
- 前端逻辑已拆到 `common/static/dbdiagnostic/js/wait_events.js`，通过 `/db_diagnostic/pgsql_wait_events/` 加载当前等待事件聚合。

#### 10. PgSQL 索引诊断

状态：已实现。

目标：

- 展示未使用索引、invalid index、大索引排行和 seq scan 高的对象。

后端计划：

- 新增接口：`/db_diagnostic/pgsql_indexes/`
- 在 `sql/engines/pgsql.py` 增加 `index_diagnostic()`。
- 新增诊断类型：`pgsql_indexes`。
- 默认 SQL 必须接入 `DBDiagnosticSQLTemplate`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护。
- engine 查询方法优先读取后台 SQL，后台无启用配置时使用代码内置回退 SQL。

查询来源：

- `pg_stat_user_indexes`
- `pg_index`
- `pg_class`
- `pg_namespace`
- `pg_stat_user_tables`

建议字段：

| 字段 | 含义 |
| --- | --- |
| `diagnostic_type` | 诊断类型 |
| `schema_name` | schema |
| `table_name` | 表名 |
| `index_name` | 索引名 |
| `index_size` | 索引大小 |
| `idx_scan` | 索引扫描次数 |
| `seq_scan` | 顺序扫描次数 |
| `is_valid` | 索引是否有效 |
| `is_unique` | 是否唯一索引 |
| `reason` | 诊断原因 |

前端计划：

- 新增 `sql/templates/dbdiagnostic/indexes_tab.html` include。
- 列定义使用 PgSQL 索引诊断专属字段。
- 前端逻辑已拆到 `common/static/dbdiagnostic/js/indexes.js`，复用数据库和 Schema 过滤接口，并使用 `/db_diagnostic/pgsql_indexes/` 做服务端分页。

#### 11. PgSQL 插件展示

状态：已实现。

目标：

- 展示当前数据库可用和已安装的 PostgreSQL extension，便于确认 `pg_stat_statements`、`pg_trgm` 等插件状态。

后端实现：

- 新增接口：`/db_diagnostic/pgsql_extensions/`
- 在 `sql/engines/pgsql.py` 增加 `extension_status()`。
- 新增诊断类型：`pgsql_extensions`。
- 默认 SQL 接入 `DBDiagnosticSQLTemplate`，可在 `/admin/sql/dbdiagnosticsqltemplate/` 维护。

查询来源：

- `pg_available_extensions`
- `pg_extension`
- `pg_namespace`

建议字段：

| 字段 | 含义 |
| --- | --- |
| `extension_name` | 插件名 |
| `installed` | 是否已安装 |
| `default_version` | 默认版本 |
| `installed_version` | 安装版本 |
| `schema_name` | 安装 schema |
| `description` | 插件说明 |

前端实现：

- 新增 `sql/templates/dbdiagnostic/extensions_tab.html` include。
- 前端逻辑拆到 `common/static/dbdiagnostic/js/extensions.js`。
- 支持数据库过滤，查看不同数据库的 extension 安装状态。

## 页面设计建议

第一阶段尽量不新增大面积页面结构：

- 进程状态：增强 PgSQL 会话操作。
- 事务信息：已拆出 `dbdiagnostic/trx_tab.html`，PgSQL 使用专属列定义。
- Top表空间：增加 PgSQL 专属列定义；如继续扩展交互，应拆出 `dbdiagnostic/tablespace_tab.html`。

第二、三阶段可新增 PgSQL 专属 tab：

- 复制状态
- 复制Slot
- Vacuum风险
- 进度视图
- Top SQL
- 等待事件
- 索引诊断
- 插件展示

如果 tab 过多，可以后续改为 PgSQL 诊断二级导航，但第一版建议先保持 Bootstrap tab 的现有实现方式，降低改造范围。

PgSQL 页面拆分约束：

- 新增 PgSQL tab 时，优先新增 `sql/templates/dbdiagnostic/<name>_tab.html` 并在主模板 include。
- 主模板 `sql/templates/dbdiagnostic.html` 只保留导航、公共实例选择、公共弹窗和必要的 tab include，不继续堆大段 tab HTML。
- PgSQL 专属列定义和详情 formatter 不复用 MySQL 字段；必要时拆独立 JS 文件，避免主模板变成多数据库列定义混合区。
- 已存在但尚未拆分的通用 tab，新增 PgSQL 专属能力时优先评估是否顺手拆出 include，降低后续合并冲突。

Schema 过滤约束：

- 不做全局 Schema 选择器，避免误导实例级、会话级诊断。
- 对象级诊断可以单独提供 Schema 输入框，例如 Top 表空间、Vacuum 风险、索引诊断。
- 会话级或实例级诊断不建议加 Schema 过滤，例如进程状态、事务信息、锁信息、复制状态、Replication Slot、等待事件聚合。
- 对象级后台 SQL 使用 `$schema_name$` 占位符；空字符串表示全部 Schema。
- 后端必须校验 Schema 输入，只允许安全的标识符字符，再替换到 SQL 模板。

## 代码链路

现有相关路径：

| 类型 | 路径 |
| --- | --- |
| 页面模板 | `sql/templates/dbdiagnostic.html` |
| 事务信息子模板 | `sql/templates/dbdiagnostic/trx_tab.html` |
| 发布订阅子模板 | `sql/templates/dbdiagnostic/pubsub_tab.html` |
| 复制状态子模板 | `sql/templates/dbdiagnostic/replication_tab.html` |
| 复制Slot子模板 | `sql/templates/dbdiagnostic/replication_slots_tab.html` |
| Vacuum风险子模板 | `sql/templates/dbdiagnostic/vacuum_tab.html` |
| Progress进度子模板 | `sql/templates/dbdiagnostic/progress_tab.html` |
| 等待事件子模板 | `sql/templates/dbdiagnostic/wait_events_tab.html` |
| 索引诊断子模板 | `sql/templates/dbdiagnostic/indexes_tab.html` |
| 插件展示子模板 | `sql/templates/dbdiagnostic/extensions_tab.html` |
| 前端列定义 | `common/static/dbdiagnostic/js/db_info.js` |
| 发布订阅前端逻辑 | `common/static/dbdiagnostic/js/pubsub.js` |
| 复制链路前端逻辑 | `common/static/dbdiagnostic/js/replication.js` |
| Vacuum风险前端逻辑 | `common/static/dbdiagnostic/js/vacuum.js` |
| Progress进度前端逻辑 | `common/static/dbdiagnostic/js/progress.js` |
| 等待事件前端逻辑 | `common/static/dbdiagnostic/js/wait_events.js` |
| 索引诊断前端逻辑 | `common/static/dbdiagnostic/js/indexes.js` |
| 插件展示前端逻辑 | `common/static/dbdiagnostic/js/extensions.js` |
| 接口入口 | `sql/db_diagnostic.py` |
| 路由 | `sql/urls.py` |
| PgSQL engine | `sql/engines/pgsql.py` |
| 自定义 SQL 模型 | `sql/models.py` |
| Admin 配置 | `sql/admin.py` |
| 默认 SQL 初始化 | `src/init_sql/v1.14.0_pgsql_metrics.sql` |
| 单元测试 | `sql/engines/tests.py`、`sql/tests.py` |

后续建议新增模板路径：

| 诊断项 | 建议模板 |
| --- | --- |
| PgSQL Top 表空间 | `sql/templates/dbdiagnostic/tablespace_tab.html` |
| PgSQL 复制状态 | `sql/templates/dbdiagnostic/replication_tab.html` |
| PgSQL Replication Slot | `sql/templates/dbdiagnostic/replication_slots_tab.html` |
| PgSQL Vacuum 风险 | `sql/templates/dbdiagnostic/vacuum_tab.html` |
| PgSQL Progress | `sql/templates/dbdiagnostic/progress_tab.html` |
| PgSQL Top SQL | `sql/templates/dbdiagnostic/top_sql_tab.html` |
| PgSQL 等待事件 | `sql/templates/dbdiagnostic/wait_events_tab.html` |
| PgSQL 索引诊断 | `sql/templates/dbdiagnostic/indexes_tab.html` |
| PgSQL 插件展示 | `sql/templates/dbdiagnostic/extensions_tab.html` |

## 验证计划

每个阶段至少执行：

```bash
python -m py_compile sql/db_diagnostic.py sql/engines/pgsql.py sql/models.py sql/admin.py
```

```bash
DEBUG=true SECRET_KEY=dev-debug-secret-dev-debug-secret-123456 DATABASE_URL=mysql://root:QzLmNpRw%21%40%23S@127.0.0.1:23309/archery CACHE_URL=redis://127.0.0.1:6379/0 .venv/bin/python manage.py check
```

涉及页面展示时：

```bash
/home/opc/node/restart_archery_debug.sh
```

访问：

```text
http://127.0.0.1:9123/login/
```

并使用测试账号验证：

```text
用户名：zkiss
密码：Aa9213..99!
```

## 接手开发注意点

- 当前计划还没有实现代码，后续开发前需要重新检查工作区状态。
- 新增或修改 `DBDiagnosticSQLTemplate` 默认配置前，需要确认是否影响当前开发库；如涉及迁移或导入 SQL，先备份。
- `pg_stat_statements` 依赖扩展，不能假设所有实例都安装。
- 部分 PgSQL 视图字段随版本变化，默认 SQL 要兼容 PostgreSQL 常见版本；无法兼容时应返回清晰错误。
- `pg_terminate_backend` 属于高风险操作，不能和 `pg_cancel_backend` 混用为同一个无提示动作。
- 前端表格不是动态读取 SQL 字段生成，新增诊断项时必须同步维护列定义。
