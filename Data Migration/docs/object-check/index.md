# 数据库对象检查

数据库对象检查用于对比源库和目标库中除表数据之外的对象差异。它不放入当前 MVP 主线，建议作为数据检查稳定后的增强能力。

优先关注：

- 触发器
- 函数和过程
- 视图和物化视图
- 索引
- 约束
- 扩展
- schema 和权限

## 目标

对象检查需要回答：

1. 源库对象在目标库是否存在？
2. 对象定义是否一致？
3. 对象启用状态是否一致？
4. 对象差异是否会影响切换后的写入和查询？

## 检查范围

| 对象 | 优先级 | 说明 |
| --- | --- | --- |
| 触发器 | 高 | 切换后写入行为可能受影响 |
| 函数 / 过程 | 高 | 触发器、默认值、业务 SQL 可能依赖 |
| 视图 | 中 | 查询兼容性检查 |
| 物化视图 | 中 | 需要检查定义和刷新策略 |
| 索引 | 高 | 影响查询性能和唯一性约束 |
| 约束 | 高 | 主键、唯一约束、外键、check 约束 |
| 扩展 | 高 | 函数、类型、索引方法可能依赖扩展 |
| 权限 | 中 | 应用账号切换后是否可读写 |

## 触发器检查

触发器需要比较：

- schema
- table
- trigger name
- enabled 状态
- 触发时机：`BEFORE` / `AFTER` / `INSTEAD OF`
- 触发事件：`INSERT` / `UPDATE` / `DELETE` / `TRUNCATE`
- 调用函数
- 触发器定义

建议使用：

```sql
SELECT
  n.nspname AS schema_name,
  c.relname AS table_name,
  t.tgname AS trigger_name,
  t.tgenabled AS enabled,
  pg_get_triggerdef(t.oid, true) AS trigger_definition
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, t.tgname;
```

风险判断：

- 源库存在触发器，目标库不存在：`failed`
- 定义不同：`failed`
- 启用状态不同：`warning` 或 `failed`
- 触发器依赖函数缺失：`failed`

## 函数和过程检查

函数需要比较：

- schema
- name
- 参数签名
- 返回类型
- language
- volatility
- security definer
- 函数定义

建议使用：

```sql
SELECT
  n.nspname AS schema_name,
  p.proname AS function_name,
  pg_get_function_identity_arguments(p.oid) AS identity_arguments,
  pg_get_function_result(p.oid) AS result_type,
  l.lanname AS language,
  p.provolatile AS volatility,
  p.prosecdef AS security_definer,
  pg_get_functiondef(p.oid) AS function_definition
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_language l ON l.oid = p.prolang
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.proname, identity_arguments;
```

比较时建议使用 `(schema_name, function_name, identity_arguments)` 作为唯一键。

## 视图检查

视图需要比较：

- schema
- view name
- view definition
- 是否 security barrier
- 是否 security invoker

建议使用：

```sql
SELECT
  n.nspname AS schema_name,
  c.relname AS view_name,
  pg_get_viewdef(c.oid, true) AS view_definition
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('v', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;
```

物化视图还需要检查是否需要在切换前刷新。

## 索引检查

索引需要比较：

- schema
- table
- index name
- unique
- primary
- valid
- ready
- index definition

建议使用：

```sql
SELECT
  n.nspname AS schema_name,
  t.relname AS table_name,
  i.relname AS index_name,
  ix.indisunique AS is_unique,
  ix.indisprimary AS is_primary,
  ix.indisvalid AS is_valid,
  ix.indisready AS is_ready,
  pg_get_indexdef(i.oid) AS index_definition
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, t.relname, i.relname;
```

风险判断：

- 唯一索引缺失：`failed`
- 普通索引缺失：`warning`
- 索引定义不同：`warning` 或 `failed`
- 索引 invalid：`failed`

## 约束检查

约束需要比较：

- 主键
- 唯一约束
- 外键
- check 约束
- exclusion 约束

建议使用：

```sql
SELECT
  n.nspname AS schema_name,
  c.relname AS table_name,
  con.conname AS constraint_name,
  con.contype AS constraint_type,
  pg_get_constraintdef(con.oid, true) AS constraint_definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, con.conname;
```

## 扩展检查

扩展需要比较：

- extension name
- version
- schema

建议使用：

```sql
SELECT
  e.extname AS extension_name,
  e.extversion AS extension_version,
  n.nspname AS schema_name
FROM pg_extension e
JOIN pg_namespace n ON n.oid = e.extnamespace
ORDER BY e.extname;
```

如果源库使用 `uuid-ossp`、`pgcrypto`、`postgis`、`citext` 等扩展，目标库缺失会直接影响函数、类型、索引和业务 SQL。

## 比较策略

建议将对象检查设计成三层：

1. **存在性检查**：源库有，目标库是否也有。
2. **定义 hash 检查**：规范化定义后计算 hash。
3. **风险分级**：根据对象类型和差异类型给出 `passed` / `warning` / `failed`。

结果模型可以复用任务体系：

| 字段 | 说明 |
| --- | --- |
| `task_id` | 迁移准备任务 ID |
| `object_type` | `trigger` / `function` / `view` / `index` / `constraint` / `extension` |
| `schema_name` | schema |
| `object_name` | 对象名 |
| `parent_name` | 表名或父对象 |
| `source_definition_hash` | 源库定义 hash |
| `target_definition_hash` | 目标库定义 hash |
| `status` | `passed` / `warning` / `failed` |
| `message` | 差异说明 |

## 实施建议

第一版对象检查可以只做：

1. 触发器存在性和定义对比。
2. 函数签名和定义对比。
3. 扩展存在性和版本对比。
4. 索引和约束存在性对比。

不要一开始自动修复对象差异。先展示差异和风险，让用户决定是否用 `pg_dump --schema-only`、手工 SQL 或后续自动修复能力处理。
