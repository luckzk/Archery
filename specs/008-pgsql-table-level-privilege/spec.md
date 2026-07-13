# PgSQL 表级查询权限功能说明

## 背景

Archery 的在线查询权限校验，对 PostgreSQL 实例原本只支持到**库（database）级**：`query_priv_check`（`sql/query_privileges.py`）对 `pgsql/redis/mssql` 仅调用 `_db_priv`，一旦用户拿到某库权限，就能查询该库下所有 schema、所有表。表级校验（`_tb_priv`）此前只在 MySQL 分支被调用，因为 MySQL 依赖 GoInception 解析 SQL 提取表引用，而 GoInception 不支持 PostgreSQL 语法。

本功能把 PostgreSQL 的查询鉴权颗粒度扩展到**表级（`schema.table`）**，可按用户/权限组精确授权到单张表。限制仅作用于**经 Archery 的查询链路**（应用层），不涉及数据库原生 GRANT。

## 入口与权限

- 申请入口：查询权限申请页 `/query/applylist/`（模板 `sql/templates/queryapplylist.html`）。
- 审批入口：查询权限审核 `/query/privaudit/`。
- 用户权限管理（回收）：`/query/userprivileges/`。

权限级别（`priv_type`）：

| 值 | 含义 | pgsql 支持 |
| --- | --- | --- |
| 1 | DATABASE（整库） | ✅ 原有 |
| 2 | TABLE（`schema.table`） | ✅ 本次新增 |

pgsql 实例在申请页可选择 DATABASE 或 TABLE；选择 TABLE 时新增 schema 选择器，按 库 → schema → 表 三级联动选表。

## 数据模型

复用既有权限表，不新增表、不改变字段语义：

| 表 | 存储约定 |
| --- | --- |
| `query_privileges` | 表级权限：`db_name=<database>`、`table_name="schema.table"`、`priv_type=2`；库级权限：`db_name=<database>`、`table_name=""`、`priv_type=1` |
| `query_privileges_apply` | 申请记录，priv_type=2 时 `db_list=<database>`、`table_list="schema.table1,schema.table2"` |

说明：`QueryPrivileges.table_name` 以 `schema.table` 形式存储，字段长度对齐迁移中的 128。审批通过回调 `_query_apply_audit_call_back` 的入库逻辑无需改动——只要申请提交的 `table_list` 每项为 `schema.table`，即可正确落库。

## 功能范围

### 表引用解析

新增 `PgSQLEngine.get_table_ref(sql, db_name, schema_name)`（`sql/engines/pgsql.py`），基于 `sqlglot`（PostgreSQL 方言）解析 SQL：

- 遍历 AST 的 `Table` 节点，得到 `schema`（`table.db`）与 `table`（`table.name`）。
- 不带 schema 的表引用用传入的 `schema_name` 补全，缺省 `public`。
- 排除 CTE（`WITH` 子句）定义的临时表名。
- 跳过 `pg_catalog`、`information_schema` 等系统 schema。
- 返回结构与 GoInception 对齐：`[{"schema": ..., "name": ...}]`。

### 鉴权逻辑

`query_priv_check` 新增 pgsql 分支（新增 `schema_name` 形参，由 `sql/query.py` 传入）：

1. `explain`/`show` 语句跳过校验。
2. 若拥有整库权限 `_db_priv(db_name)` → 放行（向后兼容库级授权）。
3. 否则解析 SQL 得到涉及的 `schema.table`，逐个 `_tb_priv(db_name, "schema.table")` 校验；任一张表无权限即拒绝（`status=2`）。
4. 解析不出表（如 `select 1`）时按无库权限处理，拒绝（安全默认）。
5. 全部通过后取各表 limit 的最小值作为结果集行数上限。

### 申请前端

`queryapplylist.html`：

- pgsql 实例开放 TABLE 权限级别选项。
- TABLE 级新增 schema 选择器（`resource_type=schema` 拉取，接口 `sql/instance.py` 已支持）。
- 选定 schema 后按 `schema_name` 拉表；表下拉项的 value 自动拼为 `schema.table`，随 `table_list` 提交。
- MySQL 路径保持不变。

## 边界与非目标

- 仅解析**直接表引用**。查询视图时，视图底层引用的未授权表追不到 → 可能放过（如需堵死需升级到列级血缘分析）。
- 跨 schema 的**显式**引用（`SELECT * FROM other_schema.t`）能正确拦截。
- 只约束经 Archery 的查询；不管理数据库原生账号权限。若要物理隔离（防直连），需另行叠加 PostgreSQL 原生 role + GRANT。
- 授权为「授予制」：默认无权限，需申请→审批授予；不是「默认全开再禁用」。

## 依赖

- 新增 Python 依赖：`sqlglot`（纯 Python，无 C 依赖）。

## 测试

- `sql/engines/tests.py`（`TestPgSQL`）：`get_table_ref` 的 schema 补全、CTE 排除、系统 schema 跳过。
- `sql/test_query_privileges.py`：pgsql 库级放行、表级放行、表级拒绝、跨 schema 绕过拦截。
