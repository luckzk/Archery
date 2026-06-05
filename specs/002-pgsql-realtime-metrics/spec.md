# PostgreSQL状态实时指标

## 背景

`/dashboard/pgsql_metrics/` 用于查看 PostgreSQL 实例的状态指标。当前设计不再使用定时任务预采集，也不把指标结果落库；页面选择实例后，后端实时执行后台维护的指标 SQL，并把本次查询结果直接返回给页面展示。

这份文档只描述 PostgreSQL 状态实时指标功能。其他功能应单独建文档，保持“一功能一文档”。

## 功能入口

页面入口：

```text
/dashboard/pgsql_metrics/
```

页面模板：

```text
common/templates/pgsql_metric_status.html
```

菜单入口：

```text
common/templates/base.html
```

路由：

```text
sql/urls.py
```

当前相关路由：

```python
path("dashboard/pgsql_metrics/", dashboard.PgSQLMetricStatusPage)
path("dashboard/pgsql_metrics/instances/", dashboard.PgSQLMetricInstancesApi)
path("dashboard/pgsql_metrics/api/", dashboard.PgSQLMetricStatusApi)
```

## 使用流程

1. 用户进入 `/dashboard/pgsql_metrics/`。
2. 页面请求 `/dashboard/pgsql_metrics/instances/` 获取当前用户可见的 PostgreSQL 实例。
3. 用户选择一个实例。
4. 页面请求 `/dashboard/pgsql_metrics/api/?instance_id=<实例ID>`。
5. 后端读取启用的 PostgreSQL 指标定义。
6. 后端筛选出适用于该实例的指标。
7. 后端在选中的 PostgreSQL 实例上实时执行每条指标 SQL。
8. 页面展示每条指标的状态、值、行数、耗时和错误信息。

## 权限和实例可见性

页面和接口使用 `sql.menu_dashboard` 权限。

实例列表来自：

```python
user_instances(request.user, db_type=["pgsql"])
```

逻辑在：

```text
sql/utils/resource_group.py
```

含义：

- 用户有 `sql.query_all_instances` 权限时，可以看到全部实例。
- 否则通过用户资源组和实例资源组的交集判断可见性。
- 本功能只展示 `db_type='pgsql'` 的实例。

## 数据模型

指标定义模型：

```text
sql/models.py -> PgSQLMetricDefinition
```

数据库表：

```text
pgsql_metric_definition
```

核心字段：

| 字段 | 含义 |
| --- | --- |
| `metric_key` | 指标唯一标识 |
| `metric_name` | 页面展示名称 |
| `description` | 指标说明、依赖视图、权限要求 |
| `sql` | 实时执行的指标 SQL |
| `db_name` | 指定采集数据库，空值使用实例默认库 |
| `value_column` | 指标值取值列，建议为 `value` |
| `enabled` | 是否启用 |
| `timeout_ms` | 单条 SQL 超时时间 |
| `instances` | 指定适用实例，多对多 |

指标和实例关系表：

```text
pgsql_metric_definition_instances
```

关系规则：

- 指标没有指定实例：对所有当前用户可见的 PostgreSQL 实例可用。
- 指标指定了实例：只对指定的 PostgreSQL 实例可用。

判断逻辑：

```python
def metric_applies_to_instance(metric, instance):
    selected_instances = metric.instances.filter(db_type="pgsql")
    return not selected_instances.exists() or selected_instances.filter(pk=instance.pk).exists()
```

## 指标 SQL 录入约定

指标 SQL 由人工在后台维护。

后台入口：

```text
/admin/sql/pgsqlmetricdefinition/
```

代码位置：

```text
sql/admin.py -> PgSQLMetricDefinitionAdmin
```

输入约定：

- SQL 只能是单条 `SELECT`。
- 不允许多语句。
- 不允许 `INSERT`、`UPDATE`、`DELETE`、`DDL`。
- SQL 在页面选择的 PostgreSQL 实例上执行。
- `db_name` 为空时，使用实例配置的默认库；实例默认库也为空时，PgSQL 引擎使用 `postgres`。
- 当前不支持页面传入额外 SQL 参数。

输出约定：

- SQL 至少返回一列。
- 推荐返回一列并命名为 `value`。
- 如果 `value_column` 配置的列存在，页面指标值取该列首行值。
- 如果 `value_column` 为空或列不存在，页面指标值取首行首列。
- 完整结果会作为 `value_json.columns` 和 `value_json.rows` 返回，便于后续扩展详情展示。

推荐 SQL 示例：

```sql
SELECT count(*) AS value FROM pg_stat_activity WHERE wait_event_type = 'Lock';
```

## 实时查询实现

核心代码：

```text
sql/utils/pgsql_metrics.py
```

主要函数：

| 函数 | 作用 |
| --- | --- |
| `validate_metric_sql()` | 校验单条 SELECT |
| `query_pgsql_metrics_for_instance()` | 查询一个实例适用的全部指标 |
| `query_metric_for_instance()` | 在实例上执行单条指标 SQL |
| `pick_metric_value()` | 从结果集中提取指标值 |
| `seed_builtin_pgsql_metrics()` | 初始化内置指标定义 |

实时接口返回结构：

```json
{
  "status": 0,
  "msg": "ok",
  "count": 9,
  "data": {
    "instance_id": 1,
    "instance_name": "test-9",
    "host": "127.0.0.1",
    "port": 5432,
    "db_name": "postgres",
    "success": 8,
    "failed": 1,
    "metrics": [
      {
        "metric_key": "pgsql_lock_waiting_count",
        "metric_name": "锁等待数量",
        "description": "当前处于锁等待状态的会话数量。",
        "status": "success",
        "value": "0",
        "value_json": {
          "columns": ["value"],
          "rows": [{"value": 0}]
        },
        "row_count": 1,
        "error": "",
        "elapsed_ms": 12
      }
    ]
  }
}
```

## 错误处理

每条指标独立执行，单条失败不会影响其他指标。

失败时该指标返回：

```json
{
  "status": "failed",
  "value": "",
  "value_json": {},
  "row_count": 0,
  "error": "错误信息",
  "elapsed_ms": 3
}
```

错误信息会经过敏感词过滤，包含 `password`、`passwd`、`secret`、`token`、`host=`、`user=` 时会隐藏。

PgSQL 引擎连接失败时，`sql/engines/pgsql.py` 已处理 `conn` 为空的情况，避免真实连接错误被 `conn` 未定义错误覆盖。

## 已移除的旧设计

旧设计是：

1. 定时任务周期执行指标 SQL。
2. 结果写入 `pgsql_metric_latest_result`。
3. 页面读取最新结果表展示。

当前设计已去掉这条链路：

- 不再使用 `PgSQLMetricLatestResult` 模型。
- 不再创建 `pgsql_metric_latest_result` 表。
- 不再使用 `add_pgsql_metrics_schedule()`。
- 不再使用 `collect_pgsql_metrics()` 定时采集入口。
- 页面不再读取历史结果，只展示本次实时查询结果。

保留的是指标定义表 `pgsql_metric_definition`，因为后台仍需要维护指标 SQL。

## 初始化 SQL

初始化文件：

```text
src/init_sql/v1.14.0_pgsql_metrics.sql
```

该文件只负责：

- 创建 `pgsql_metric_definition`。
- 创建 `pgsql_metric_definition_instances`。
- 插入内置指标模板。

不再创建结果表。

## 开发和验证

系统检查：

```bash
DEBUG=true SECRET_KEY=dev-debug-secret-dev-debug-secret-123456 DATABASE_URL=mysql://root:123456@127.0.0.1:3306/archery CACHE_URL=redis://127.0.0.1:6379/0 .venv/bin/python manage.py check
```

语法检查示例：

```bash
python -m py_compile common/dashboard.py sql/models.py sql/admin.py sql/utils/pgsql_metrics.py sql/engines/pgsql.py
```

修改 Python、Admin、模板后重启 debug 服务：

```bash
/home/opc/node/restart_archery_debug.sh
```

页面验证：

```text
http://127.0.0.1:9123/dashboard/pgsql_metrics/
```

接口验证：

```text
/dashboard/pgsql_metrics/instances/
/dashboard/pgsql_metrics/api/?instance_id=<实例ID>
```

## 继续开发建议

后续如果继续扩展，优先考虑以下方向：

- 给单条指标增加详情弹窗，展示 `value_json` 完整结果。
- 给指标增加分类字段，例如连接、锁、复制、事务。
- 给页面增加只看失败、只看某类指标的过滤。
- 给后台增加“测试指标 SQL”按钮，在保存前选择一个 PgSQL 实例试跑。
- 如果未来需要历史趋势，再单独设计历史表，不要复用实时页面的响应结构硬塞存储逻辑。

## 注意事项

- Archery 元数据库是 MySQL，只保存指标定义和实例配置。
- 页面选择的 PgSQL 实例是业务数据库实例，不是 Archery 元数据库。
- 指标 SQL 在业务 PgSQL 实例上执行，需要确保实例账号有读取对应系统视图的权限。
- 指标 SQL 人工维护时要避免高成本查询，必须设置合理 `timeout_ms`。
- 如果某个指标只适合部分实例，应在后台的“指定实例”里明确选择，避免全局执行失败。
