# PgSQL 参数模板合并交接文档

## 背景

本次改动把 PostgreSQL 参数展示 SQL 的维护入口合并到 Archery 默认的实例参数模板后台：

- 新入口：`/admin/sql/paramtemplate/`
- 旧入口：`/admin/sql/pgsqlparamquery/` 不再作为 admin 页面暴露
- 前台展示入口仍是：`/instanceparam/`

改动目标是让 MySQL 和 PgSQL 都从同一个“实例参数模板配置”入口维护，但两者的配置模式不同：

- MySQL：模板里配置具体参数名、默认值、有效值、是否支持修改。
- PgSQL：模板里配置一条或多条展示 SQL，SQL 返回参数列表和说明。

## 用户操作方式

### 添加 MySQL 参数模板

进入 `/admin/sql/paramtemplate/add/`：

1. `数据库类型` 选择 `mysql`。
2. 填写 `参数名`，例如 `max_connections`。
3. 按需填写：
   - `默认参数值`
   - `是否支持修改`
   - `有效参数值`
   - `参数描述`
4. PgSQL SQL 配置区域会自动隐藏。
5. 保存。

MySQL 模板记录只负责补充展示信息和控制是否允许修改，不负责决定 MySQL 参数列表的来源。

### 添加 PgSQL 参数展示 SQL

进入 `/admin/sql/paramtemplate/add/`：

1. `数据库类型` 选择 `pgsql`。
2. `参数名` 标签会在页面上切换为 `配置名称`，填写这条 SQL 配置的名称，例如 `pg_settings参数展示`。
3. 页面会隐藏 MySQL 不需要的字段：
   - `默认参数值`
   - `是否支持修改`
   - `有效参数值`
   - `参数描述`
4. 页面会显示 `PostgreSQL参数展示SQL` 配置区域。
5. 填写 SQL，要求是单条 `SELECT`。
6. SQL 至少返回以下列：
   - `variable_name`
   - `runtime_value`
7. SQL 可选返回以下列：
   - `default_value`
   - `valid_values`
   - `description`
8. 按需填写：
   - `PostgreSQL查询数据库`，为空时使用实例配置的默认库。
   - `PostgreSQL SQL超时毫秒`，默认 3000。
   - `启用PostgreSQL参数展示SQL`。
9. 保存。

示例 SQL：

```sql
SELECT
  name AS variable_name,
  setting AS runtime_value,
  COALESCE(boot_val, reset_val, '') AS default_value,
  CASE
    WHEN enumvals IS NOT NULL THEN array_to_string(enumvals, '|')
    WHEN min_val IS NOT NULL OR max_val IS NOT NULL THEN concat('[', COALESCE(min_val, ''), '-', COALESCE(max_val, ''), ']')
    ELSE ''
  END AS valid_values,
  COALESCE(short_desc, '') AS description
FROM pg_settings
ORDER BY name;
```

## 展示逻辑

### MySQL 展示逻辑

代码入口：`sql/instance.py` 的 `param_list()`。

MySQL 流程：

1. 前端 `/instanceparam/` 选择 MySQL 实例后，请求 `/param/list/`。
2. 后端读取 `ParamTemplate` 中 `db_type=实例类型` 且参数名匹配搜索条件的模板。
3. 后端通过实例 engine 执行固定逻辑获取运行参数。
4. 对 MySQL 来说，engine 内部使用类似 `SHOW GLOBAL VARIABLES` 的方式拿当前实例参数列表。
5. 每个运行参数按 `variable_name` 和模板匹配。
6. 命中模板后补充：
   - `default_value`
   - `valid_values`
   - `description`
   - `editable`
7. 页面按“可编辑/不可编辑”筛选展示。
8. 可编辑参数提交修改时，后端执行 `SET GLOBAL variable_name=value`，并写入 `ParamHistory`。

结论：MySQL 参数列表来源不是后台模板 SQL，而是实例当前运行参数；后台模板只是补充说明和控制是否能修改。

### PgSQL 展示逻辑

代码入口：

- `sql/instance.py`：`param_list()` 分支判断 `ins.db_type == "pgsql"`
- `sql/utils/pgsql_params.py`：`query_pgsql_params_for_instance()`

PgSQL 流程：

1. 前端 `/instanceparam/` 选择 PgSQL 实例后，请求 `/param/list/`。
2. 后端进入 `query_pgsql_params_for_instance()`。
3. 如果页面选择“可编辑”筛选，PgSQL 直接返回空列表，因为当前不支持在线修改 PgSQL 参数。
4. 后端查询 `ParamTemplate`：

```python
ParamTemplate.objects.filter(
    db_type="pgsql",
    param_query_enabled=True,
).exclude(param_query_sql="").order_by("id")
```

5. 如果存在启用的 PgSQL SQL 模板，则按 `id` 顺序逐条执行。
6. 如果没有任何 PgSQL SQL 模板，则使用内置 `DEFAULT_PGSQL_PARAM_SQL` 查询 `pg_settings`。
7. 每条 SQL 都会先经过 `validate_metric_sql()` 校验，只允许单条 SELECT。
8. 每条 SQL 在当前选择的 PgSQL 实例上执行。
9. 每条 SQL 的返回结果都会转换成统一结构：
   - `variable_name`
   - `runtime_value`
   - `default_value`
   - `valid_values`
   - `description`
   - `editable=False`
10. 多条 SQL 的结果直接合并，不按参数名去重。

也就是说，如果第一条 SQL 返回 300 行，第二条 SQL 返回 100 行，页面最终应展示 400 行。

## Admin 页面切换逻辑

后台页面：`/admin/sql/paramtemplate/add/` 和 `/admin/sql/paramtemplate/<id>/change/`。

相关文件：

- `sql/admin.py`
- `common/static/js/admin_paramtemplate.js`

`ParamTemplateAdmin` 使用 `Media` 引入静态 JS：

```python
class Media:
    js = ("js/admin_paramtemplate.js",)
```

JS 根据 `id_db_type` 的值切换页面字段：

- `db_type=pgsql`：
  - 显示 PgSQL SQL 配置 fieldset。
  - 隐藏 `default_value`、`editable`、`valid_values`、`description`。
  - 把 `variable_name` 的 label 从 `参数名` 改成 `配置名称`。
- 其他数据库类型：
  - 隐藏 PgSQL SQL 配置 fieldset。
  - 显示 MySQL 原有参数模板字段。
  - 把 label 恢复为 `参数名`。

注意：字段隐藏只影响页面展示，不改变数据库字段结构。

## 数据结构

模型：`sql/models.py` 的 `ParamTemplate`。

本次在 `param_template` 表中增加了 PgSQL SQL 配置字段：

- `param_query_sql`：PostgreSQL 参数展示 SQL。
- `param_query_db_name`：执行 SQL 的数据库名，空表示使用实例默认库。
- `param_query_enabled`：是否启用这条 PgSQL SQL 配置。
- `param_query_timeout_ms`：SQL 超时时间，单位毫秒。

保留字段：

- `db_type`
- `variable_name`
- `default_value`
- `editable`
- `valid_values`
- `description`

约定：

- MySQL 使用 `variable_name/default_value/editable/valid_values/description`。
- PgSQL 使用 `variable_name` 作为配置名称，使用 `param_query_sql` 作为展示 SQL。
- PgSQL 的参数描述来自 SQL 返回的 `description` 列，不需要在模板表单里填写 `description` 字段。

当前仍保留 `PgSQLParamQuery` 模型和旧表，主要用于兼容已有数据和避免破坏历史结构；但 admin 页面已不再注册它。

## 初始化 SQL

相关文件：`src/init_sql/v1.14.0_pgsql_metrics.sql`。

该文件会：

1. 给 `param_template` 补充 PgSQL SQL 配置字段。
2. 插入默认的 `pg_settings参数展示` 模板。

注意：不要在已有开发库上重复执行包含 `DROP TABLE` 的初始化 SQL。执行结构变更前先备份开发库。

## 本地开发库迁移

当前开发库已经做过以下迁移：

1. 备份 `archery` 库。
2. `ALTER TABLE param_template` 增加 PgSQL SQL 配置字段。
3. 将旧 `pgsql_param_query` 中已有配置迁入 `param_template`。

迁移后的验证结果：

- `param_template` 中已有 2 条 `db_type=pgsql` 且带 SQL 的模板。
- `test-8` 实例验证到 2 条 PgSQL SQL。
- 合并返回参数行数为 716。

## 验证方式

### Python 语法检查

```bash
python -m py_compile sql/models.py sql/admin.py sql/utils/pgsql_params.py sql/instance.py
```

### Django 系统检查

```bash
DEBUG=true SECRET_KEY=dev-debug-secret-dev-debug-secret-123456 DATABASE_URL=mysql://root:QzLmNpRw%21%40%23S@127.0.0.1:23309/archery CACHE_URL=redis://127.0.0.1:6379/0 .venv/bin/python manage.py check
```

### 静态文件检查

```bash
DEBUG=true SECRET_KEY=dev-debug-secret-dev-debug-secret-123456 DATABASE_URL=mysql://root:QzLmNpRw%21%40%23S@127.0.0.1:23309/archery CACHE_URL=redis://127.0.0.1:6379/0 .venv/bin/python manage.py findstatic js/admin_paramtemplate.js --verbosity 2
```

### 重启 debug 服务

当前 debug 服务使用 `--noreload`，修改 Python、admin、模板、静态 JS 后都需要重启：

```bash
/home/opc/node/restart_archery_debug.sh
```

访问地址：

```bash
http://127.0.0.1:9123/login/
```

测试账号：

- 用户名：`zkiss`
- 密码：`Aa9213..99!`

### 页面验证

1. 登录 Archery。
2. 打开 `/admin/sql/paramtemplate/add/`。
3. `数据库类型` 选择 `mysql`：确认 PgSQL SQL 配置区隐藏，MySQL 参数字段显示。
4. `数据库类型` 选择 `pgsql`：确认 PgSQL SQL 配置区显示，MySQL 不需要字段隐藏。
5. 打开 `/instanceparam/`。
6. 选择 PgSQL 实例，例如 `test-8`。
7. 确认参数列表可以展示 PgSQL SQL 返回的参数。

## 重要代码位置

- `sql/models.py`
  - `ParamTemplate`：PgSQL SQL 配置字段定义。
  - `PgSQLParamQuery`：旧模型保留，admin 不再暴露。
- `sql/admin.py`
  - `ParamTemplateAdmin`：列表字段、fieldsets、静态 JS 引入。
- `common/static/js/admin_paramtemplate.js`
  - 根据数据库类型切换 admin 表单显示。
- `sql/instance.py`
  - `param_list()`：判断 PgSQL 后走 PgSQL 参数查询分支。
- `sql/utils/pgsql_params.py`
  - `configured_pgsql_param_queries()`：读取所有启用的 PgSQL SQL 模板。
  - `query_pgsql_params_for_instance()`：执行 SQL 并合并展示结果。
- `sql/templates/param.html`
  - `/instanceparam/` 前端实例选择和 PgSQL 参数展示相关逻辑。
- `src/init_sql/v1.14.0_pgsql_metrics.sql`
  - 新环境初始化字段和默认 PgSQL 参数展示 SQL。

## 接手开发注意点

- PgSQL 当前只支持展示参数，不支持在线修改参数。
- PgSQL 多 SQL 结果当前不去重，这是按需求实现的；如果后续需要去重，需要明确按什么字段和优先级去重。
- PgSQL SQL 必须返回 `variable_name` 和 `runtime_value`，否则对应行无法正确展示。
- PgSQL 参数描述应由 SQL 返回的 `description` 列提供，不在 admin 表单的 `参数描述` 字段里维护。
- admin 表单字段隐藏是前端 JS 控制，后端模型字段仍存在。
- 旧 `/admin/sql/pgsqlparamquery/` 已不再注册，如需兼容跳转，需要额外加 redirect URL。
- 修改静态 JS 后必须重启 debug 服务，并确认浏览器没有缓存旧 JS。
- 开发库结构变更前必须先备份 MySQL，避免再次丢失实例、权限、用户等元数据。
