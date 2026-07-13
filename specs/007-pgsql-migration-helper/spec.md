# PgSQL 手动迁移助手功能说明

## 背景

`/pgsql_migration/` 用于 PostgreSQL 人工迁移前后的检查和切换辅助。它来自外部原型的功能分析，但正式实现已经合入 Archery 自身的 Django 模型、视图、模板和工具函数，不依赖外部原型目录。

该功能不是自动迁移引擎，不负责复制数据、创建发布订阅或执行长时间数据搬迁。它聚焦在迁移切换前后最容易遗漏的准备项：表与复制标识检查、序列值预览和设置、数据量与主键范围核对。

## 入口与权限

页面入口：

```text
/pgsql_migration/
/pgsql_migration/tasks/<task_id>/
```

菜单位置：工具插件 -> PgSQL迁移助手。任务列表页用于创建和查看任务，点击“操作”进入独立任务操作页。

权限：

| Codename | 含义 |
| --- | --- |
| `menu_pgsql_migration` | 查看菜单和页面，创建本人可见实例范围内的迁移准备任务 |
| `pgsql_migration_mgt` | 管理全部迁移准备任务 |
| `pgsql_migration_execute` | 执行目标库序列设置和源库 REPLICA IDENTITY 设置 |

普通用户只能操作自己资源组可见的 PgSQL 实例。任务删除限制为任务创建人、超级用户或具备 `pgsql_migration_mgt` 的用户。

## 数据模型

新增 Archery 元数据库表：

| 表 | 用途 |
| --- | --- |
| `pgsql_migration_task` | 迁移准备任务，保存源实例、目标实例、schema/table 范围和状态 |
| `pgsql_migration_task_log` | 操作日志，记录扫描、预览、执行和错误详情 |
| `pgsql_migration_sequence_result` | 序列预览和设置结果 |
| `pgsql_migration_data_check_result` | 数据检查结果 |

项目历史上不提交 `sql/migrations/`，表结构和权限初始化维护在 `src/init_sql/v1.14.0_pgsql_metrics.sql`。

## 功能范围

### 表与复制标识扫描

扫描源库普通表和分区表，展示：

- 估算行数
- 当前 `REPLICA IDENTITY`
- 当前复制标识索引
- 主键索引和主键字段
- 可作为 `REPLICA IDENTITY USING INDEX` 的唯一非空索引

具备 `pgsql_migration_execute` 权限的用户可以选择合格唯一索引并执行：

```sql
ALTER TABLE "schema"."table" REPLICA IDENTITY USING INDEX "index_name"
```

### 序列预览和设置

序列预览会扫描源库和目标库同名序列，计算目标建议值：

```text
source last_value + step
```

默认 `step` 为 `10000`。如果目标序列当前值已经更大，默认跳过，避免回退目标序列。

具备 `pgsql_migration_execute` 权限的用户可以在目标库执行 `setval`。执行前会重新生成预览结果，并只应用 `should_apply=true` 的序列。

### 数据检查

数据检查支持按任务保存的表范围，或手工输入 `schema.table` 列表执行：

- 精确行数对比：源库和目标库分别执行 `count(*)`
- 单字段主键范围对比：对单列主键执行 `min(pk), max(pk)`

复合主键或无主键表会把主键范围检查标记为 warning，不阻断行数检查。

## 使用建议

1. 在实例管理中确认源库和目标库都配置为 `pgsql`，并加入操作者可见的资源组。
2. 创建迁移准备任务，填写源库、目标库、可选 schema；可以加载源库和目标库表后勾选表，也可以手工填写 `schema.table` 表范围。
3. 先执行表扫描，处理缺失或不合适的 `REPLICA IDENTITY`。
4. 执行序列预览，确认目标建议值；切换前再执行设置序列。
5. 迁移完成后执行数据检查，保留任务日志和结果作为切换记录。

## 风险边界

- `count(*)` 会对大表产生明显负载，应在维护窗口或低峰期使用。
- `ALTER TABLE ... REPLICA IDENTITY USING INDEX` 是源库写操作，必须由具备执行权限的用户显式触发。
- 序列设置只处理源库和目标库同名序列，不自动创建缺失序列。
- 该助手不替代迁移方案本身；数据同步、校验抽样、回滚方案仍需按业务迁移流程设计。
