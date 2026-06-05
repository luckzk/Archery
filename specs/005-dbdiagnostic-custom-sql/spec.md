# DB Diagnostic 自定义 SQL 功能说明

## 背景

`/dbdiagnostic/` 是 Archery 的会话管理和问题诊断页面，目前包含进程状态、表空间、锁信息、长事务等分区。

本次改动针对 PgSQL 增加了三个能力：

- PgSQL 进程状态支持后台自定义 SQL。
- PgSQL 锁信息支持后台自定义 SQL，并使用 PgSQL 专属列展示阻塞链。
- PgSQL 发布订阅支持后台自定义 SQL，并在锁信息右侧新增“发布订阅”tab。

管理入口放在 Django admin 的 SQL app 下：

```text
/admin/sql/dbdiagnosticsqltemplate/
```

该入口名称为：`DB诊断自定义SQL`。

## 为什么需要新表

自定义 SQL 需要持久保存，不能只写在代码或前端里，因此新增了 Archery 元数据库表：

```text
dbdiagnostic_sql_template
```

该表保存 `/dbdiagnostic/` 页面不同数据库、不同诊断分区要执行的 SQL 配置。

当前支持的诊断分区：

```text
pgsql_processlist    PgSQL进程状态
pgsql_trxandlocks    PgSQL锁信息
pgsql_pubsub          PgSQL发布订阅
```

当前本地开发库已写入两条默认配置：

```text
pgsql_processlist     PgSQL进程状态默认SQL
pgsql_trxandlocks     PgSQL锁信息默认SQL
pgsql_pubsub           PgSQL发布订阅默认SQL
```

这次建表只新增配置表，不会重建库，不会删除已有用户、实例、权限、工单等数据。建表前已按约定备份开发库。

## 数据模型

模型位置：`sql/models.py`

模型名：`DBDiagnosticSQLTemplate`

表名：`dbdiagnostic_sql_template`

主要字段：

| 字段 | 含义 |
| --- | --- |
| `db_type` | 数据库类型，目前主要使用 `pgsql` |
| `diagnostic_type` | 诊断分区，例如 `pgsql_processlist`、`pgsql_trxandlocks`、`pgsql_pubsub` |
| `template_name` | 配置名称 |
| `description` | 配置说明 |
| `sql` | 自定义 SQL |
| `db_name` | 查询数据库，PgSQL 默认 `postgres` |
| `enabled` | 是否启用 |
| `timeout_ms` | SQL 超时时间，单位毫秒 |
| `create_time` | 创建时间 |
| `update_time` | 更新时间 |

唯一约束：

```text
(db_type, diagnostic_type, template_name)
```

## Admin 页面

Admin 注册位置：`sql/admin.py`

页面地址：

```text
/admin/sql/dbdiagnosticsqltemplate/
```

页面分区：

### 基础信息

包含：

- `数据库类型`
- `诊断分区`
- `配置名称`
- `配置说明`
- `是否启用`

### SQL

包含：

- `SQL`
- `查询数据库`
- `SQL超时毫秒`

约定：

- 只允许单条 `SELECT`。
- PgSQL 进程状态 SQL 可以使用 `$state_not_idle$` 占位符。
- 发布订阅 SQL 不需要占位符，必须返回前端列定义所需字段。
- 页面选择 `Not Idle` 时，后端会把 `$state_not_idle$` 替换为：

```sql
and psa.state<>'idle'
```

- 页面选择其他状态时，后端会把 `$state_not_idle$` 替换为空字符串。

### 输出字段约定

Admin 页面中已写说明，后续维护 SQL 时必须保证输出字段和前端列定义匹配。

## 执行链路

### PgSQL 进程状态

前端入口：`/dbdiagnostic/` 的进程状态 tab。

请求接口：

```text
/db_diagnostic/process/
```

后端入口：`sql/db_diagnostic.py` 的 `process()`。

该接口会调用实例 engine 的：

```python
query_engine.processlist(command_type=command_type, **request_kwargs)
```

PgSQL 实现位置：`sql/engines/pgsql.py` 的 `processlist()`。

执行逻辑：

1. 读取启用的后台配置：

```python
DBDiagnosticSQLTemplate.objects.filter(
    db_type="pgsql",
    diagnostic_type="pgsql_processlist",
    enabled=True,
).order_by("-update_time", "-id").first()
```

2. 如果找到配置，使用后台配置的 SQL。
3. 如果没有配置，回落到代码内置 SQL。
4. 替换 `$state_not_idle$` 占位符。
5. 校验 SQL 必须是单条 `SELECT`。
6. 执行 SQL。
7. 校验必要输出字段。
8. 返回给前端表格。

必要输出字段：

```text
pid
datname
usename
state
query
```

这些是最低要求。为了前端完整展示，建议输出当前 PgSQL 进程状态默认字段：

```text
pid
block_pids
leader_pid
datname
usename
application_name
state
client_addr
elapsed_time_seconds
elapsed_time
query
wait_event_type
wait_event
query_start
backend_start
client_hostname
client_port
transaction_start_time
state_change
backend_xid
backend_xmin
backend_type
```

前端列定义在：`common/static/dbdiagnostic/js/db_info.js` 的 `pgsqlDiagnosticInfo.fieldsProcesslist`。

### PgSQL 锁信息

前端入口：`/dbdiagnostic/` 的锁信息 tab。

请求接口：

```text
/db_diagnostic/trxandlocks/
```

后端入口：`sql/db_diagnostic.py` 的 `trxandlocks()`。

PgSQL 分支：

```python
elif instance.db_type == "pgsql":
    query_result = query_engine.trxandlocks()
```

PgSQL 实现位置：`sql/engines/pgsql.py` 的 `trxandlocks()`。

执行逻辑：

1. 读取启用的后台配置：

```python
DBDiagnosticSQLTemplate.objects.filter(
    db_type="pgsql",
    diagnostic_type="pgsql_trxandlocks",
    enabled=True,
).order_by("-update_time", "-id").first()
```

2. 如果找到配置，使用后台配置的 SQL。
3. 如果没有配置，回落到代码内置 SQL。
4. 校验 SQL 必须是单条 `SELECT`。
5. 执行 SQL。
6. 校验必要输出字段。
7. 返回给前端 PgSQL 专属锁信息表格。

必要输出字段：

```text
waiting_pid
blocking_pid
blocking_chain
waiting_query
blocking_query
```

完整建议输出字段：

```text
waiting_pid
blocking_pid
blocking_chain
database_name
waiting_user
blocking_user
waiting_application
blocking_application
waiting_client_addr
blocking_client_addr
waiting_state
blocking_state
wait_event_type
wait_event
lock_type
waiting_lock_mode
blocking_lock_mode
lock_object
waiting_duration_seconds
waiting_xact_start
waiting_query_start
blocking_xact_start
blocking_query_start
waiting_query
blocking_query
```

前端 PgSQL 锁信息专属列定义在：`sql/templates/dbdiagnostic.html` 的 `lockListTableInfos` 中 `pgsql` 分支。

详情展开会格式化展示：

- `waiting_query`
- `blocking_query`
- `blocking_chain`

### PgSQL 发布订阅

前端入口：`/dbdiagnostic/` 的发布订阅 tab，位于“锁信息”右侧。

请求接口：

```text
/db_diagnostic/pubsub/
```

后端入口：`sql/db_diagnostic.py` 的 `pubsub()`。

该接口仅支持 PgSQL 实例，调用 `sql/engines/pgsql.py` 的 `pubsub()`。

执行逻辑：

1. 读取启用的后台配置：

```python
DBDiagnosticSQLTemplate.objects.filter(
    db_type="pgsql",
    diagnostic_type="pgsql_pubsub",
    enabled=True,
).order_by("-update_time", "-id").first()
```

2. 如果找到配置，使用后台配置的 SQL。
3. 如果没有配置，回落到代码内置 SQL。
4. 校验 SQL 必须是单条 `SELECT`。
5. 执行 SQL。
6. 校验必要输出字段。
7. 返回给前端 PgSQL 发布订阅表格。

必要输出字段：

```text
object_type
object_name
enabled
owner_name
database_name
```

完整建议输出字段：

```text
object_type
object_name
enabled
owner_name
database_name
publication_names
table_name
operations
subscription_pid
slot_name
sync_commit
received_lsn
latest_end_lsn
last_msg_send_time
last_msg_receipt_time
latest_end_time
lag_seconds
conninfo
```

默认 SQL 同时查询 `pg_publication`、`pg_publication_tables`、`pg_subscription`、`pg_stat_subscription`。订阅连接信息中的 `password=...` 会被替换为 `password=****`。

前端 HTML 在：`sql/templates/dbdiagnostic/pubsub_tab.html`。

前端列定义和加载逻辑在：`common/static/dbdiagnostic/js/pubsub.js` 的 `pubsubListTableInfos` 和 `get_pubsub_list()`。

## SQL 校验逻辑

PgSQL engine 中新增了内部方法：

```python
_validate_dbdiagnostic_sql(sql)
_query_dbdiagnostic_sql(...)
_get_dbdiagnostic_sql_template(diagnostic_type)
```

校验规则：

- SQL 不能为空。
- 只允许单条 SQL。
- 只允许 `SELECT`。
- 执行后必须包含必要输出字段。

如果字段缺失，会返回错误：

```text
自定义SQL缺少必要输出字段：xxx
```

页面会弹出“数据加载失败”并展示错误信息。

## 默认 SQL

默认 SQL 存在两处：

1. 代码内置回退 SQL：`sql/engines/pgsql.py`
2. 初始化 SQL 默认配置：`src/init_sql/v1.14.0_pgsql_metrics.sql`

初始化 SQL 会创建表：

```sql
CREATE TABLE IF NOT EXISTS dbdiagnostic_sql_template (...)
```

并插入默认配置：

```text
PgSQL进程状态默认SQL
PgSQL锁信息默认SQL
PgSQL发布订阅默认SQL
```

如果后台配置被删除或禁用，代码仍会使用内置 SQL 回退，保证页面基本可用。

## 操作说明

### 修改 PgSQL 进程状态 SQL

1. 打开 `/admin/sql/dbdiagnosticsqltemplate/`。
2. 找到 `diagnostic_type=pgsql_processlist` 的配置。
3. 修改 SQL。
4. 确保 SQL 返回必要字段：

```text
pid
datname
usename
state
query
```

5. 如果需要支持 `Not Idle` 过滤，SQL 中保留 `$state_not_idle$` 占位符。
6. 保存。
7. 打开 `/dbdiagnostic/` 验证进程状态 tab。

### 修改 PgSQL 锁信息 SQL

1. 打开 `/admin/sql/dbdiagnosticsqltemplate/`。
2. 找到 `diagnostic_type=pgsql_trxandlocks` 的配置。
3. 修改 SQL。
4. 确保 SQL 返回必要字段：

```text
waiting_pid
blocking_pid
blocking_chain
waiting_query
blocking_query
```

5. 保存。
6. 打开 `/dbdiagnostic/` 验证锁信息 tab。

### 修改 PgSQL 发布订阅 SQL

1. 打开 `/admin/sql/dbdiagnosticsqltemplate/`。
2. 找到 `diagnostic_type=pgsql_pubsub` 的配置。
3. 修改 SQL。
4. 确保 SQL 返回必要字段：

```text
object_type
object_name
enabled
owner_name
database_name
```

5. 保存。
6. 打开 `/dbdiagnostic/` 验证发布订阅 tab。

## 验证方式

### Python 语法检查

```bash
python -m py_compile sql/models.py sql/admin.py sql/engines/pgsql.py sql/db_diagnostic.py
```

### Django 系统检查

```bash
DEBUG=true SECRET_KEY=dev-debug-secret-dev-debug-secret-123456 DATABASE_URL=mysql://root:QzLmNpRw%21%40%23S@127.0.0.1:23309/archery CACHE_URL=redis://127.0.0.1:6379/0 .venv/bin/python manage.py check
```

### 查看配置表

```bash
docker exec archery-mysql80 mysql -uroot -p'QzLmNpRw!@#S' archery -e "SELECT id, db_type, diagnostic_type, template_name, enabled, timeout_ms FROM dbdiagnostic_sql_template ORDER BY id;"
```

### 重启 debug 服务

当前 debug 服务使用 `--noreload`，修改 Python、admin、模板后需要重启：

```bash
/home/opc/node/restart_archery_debug.sh
```

访问：

```text
http://127.0.0.1:9123/login/
```

## 接手开发注意点

- 这个功能当前先支持 PgSQL；后续要加其他数据库，可以扩展 `DBDiagnosticSQLTemplate.DIAGNOSTIC_TYPE_CHOICES`。
- 前端表格不是动态读 SQL 字段生成的，仍依赖前端列定义。
- 新增诊断类型时，需要同时处理：
  - admin choices
  - engine 执行方法
  - 必要字段校验
  - 前端列定义
  - 页面请求接口和路由
  - 初始化 SQL 默认配置
- PgSQL 锁信息目前使用 PgSQL 专属列，不复用 MySQL 的中文字段。
- PgSQL 锁信息的阻塞链由 SQL 返回 `blocking_chain`，前端只负责展示。
- 后台 SQL 只能配置查询，不支持 DML/DDL。
- 修改开发库结构前必须先备份 Archery 元数据库。
