# 任务接口

任务接口用于把一次手动迁移准备过程组织成可追踪的准备任务。前端展示会称为“迁移准备任务”，接口路径仍保留 `/api/tasks`，方便后续继续扩展为自动创建发布、订阅和自动迁移。

当前任务接口仍是同步执行：请求发起后会立即执行序列预览、序列设置或数据检查，并把结果写入 SQLite。它不会自动创建 publication / subscription，也不会自动迁移数据。后续可以把执行部分替换为后台 worker，而接口形态保持不变。

## 任务状态

| 状态 | 说明 |
| --- | --- |
| `draft` | 已创建，尚未执行检查 |
| `checking` | 正在执行序列或数据检查 |
| `sequence_previewed` | 已完成序列设置预览 |
| `sequence_applied` | 已执行目标库序列设置 |
| `data_checked` | 已完成数据检查 |
| `failed` | 任务执行失败 |

## `POST /api/tasks`

创建迁移准备任务。

请求：

```json
{
  "name": "用户库迁移",
  "source_instance_id": 1,
  "target_instance_id": 2,
  "schemas": ["public"],
  "tables": [
    {
      "schema_name": "public",
      "table_name": "users"
    }
  ],
  "description": "先验证序列和数据检查"
}
```

参数：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `name` | string | 是 | 准备任务名称 |
| `source_instance_id` | number | 是 | 源库实例 ID |
| `target_instance_id` | number | 是 | 目标库实例 ID |
| `schemas` | string[] | 否 | 默认操作范围 |
| `tables` | object[] | 否 | 默认数据检查表 |
| `description` | string | 否 | 备注 |

响应：

```json
{
  "id": 1,
  "name": "用户库迁移",
  "source_instance_id": 1,
  "target_instance_id": 2,
  "schemas": ["public"],
  "tables": [
    {
      "schema_name": "public",
      "table_name": "users"
    }
  ],
  "status": "draft",
  "description": "先验证序列和数据检查",
  "created_at": "2026-06-03 16:30:00",
  "updated_at": "2026-06-03 16:30:00"
}
```

## `GET /api/tasks`

获取迁移准备任务列表。

## `GET /api/tasks/{task_id}`

获取单个迁移准备任务。

路径参数：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | number | 任务 ID |

## `DELETE /api/tasks/{task_id}`

删除迁移准备任务，并清理该任务下的日志、序列结果和数据检查结果。

响应：

```json
{
  "ok": true
}
```

## `GET /api/tasks/{task_id}/logs`

获取任务操作日志。

响应：

```json
{
  "items": [
    {
      "id": 1,
      "task_id": 1,
      "operation": "task.create",
      "status": "succeeded",
      "message": "Migration task created",
      "details_json": null,
      "started_at": "2026-06-03 16:30:00",
      "finished_at": null
    }
  ]
}
```

## `POST /api/tasks/{task_id}/replica-identity/using-index`

在源库上设置指定表的 `REPLICA IDENTITY USING INDEX`。接口会再次校验索引是否满足 replica identity 条件，成功或失败都会写入任务日志。

请求：

```json
{
  "schema_name": "public",
  "table_name": "orders",
  "index_name": "orders_order_no_uidx"
}
```

参数：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_name` | string | 是 | 表所在 schema |
| `table_name` | string | 是 | 表名 |
| `index_name` | string | 是 | 从 `eligible_replica_identity_indexes` 中选择的索引名 |

响应：

```json
{
  "ok": true,
  "schema_name": "public",
  "table_name": "orders",
  "index_name": "orders_order_no_uidx",
  "columns": ["order_no"],
  "sql": "ALTER TABLE \"public\".\"orders\" REPLICA IDENTITY USING INDEX \"orders_order_no_uidx\""
}
```

## `POST /api/tasks/{task_id}/sequences/preview`

基于任务源库和目标库，预览目标库序列设置值，并持久化到 `sequence_results`。

请求：

```json
{
  "step": 10000,
  "schemas": ["public"],
  "skip_if_target_greater": true
}
```

参数：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `step` | number | 否 | 源库当前值基础上的步进值，默认 `10000` |
| `schemas` | string[] | 否 | 本次限定 schema，不传则使用任务的 `schemas` |
| `skip_if_target_greater` | boolean | 否 | 目标库当前值更大时是否跳过 |

响应结构与 [序列接口的预览响应](/backend-api/sequences/#post-api-sequences-preview) 一致。

## `POST /api/tasks/{task_id}/sequences/apply`

基于任务源库和目标库，执行目标库序列设置，并持久化执行结果。

请求参数与 `/api/tasks/{task_id}/sequences/preview` 相同。

执行结果可通过 `/api/tasks/{task_id}/sequence-results` 查询。

## `GET /api/tasks/{task_id}/sequence-results`

查询任务的序列预览或设置结果。

响应：

```json
{
  "items": [
    {
      "id": 1,
      "task_id": 1,
      "operation": "preview",
      "sequence_schema": "public",
      "sequence_name": "users_id_seq",
      "source_last_value": 95000,
      "target_current_value": 100,
      "target_value": 105000,
      "should_apply": 1,
      "reason": "ready",
      "setval_sql": "SELECT setval('public.users_id_seq', 105000, true);",
      "status": null,
      "error": null,
      "created_at": "2026-06-03 16:30:00"
    }
  ]
}
```

## `POST /api/tasks/{task_id}/data-check/run`

基于任务源库和目标库执行数据检查，并持久化检查结果。

请求：

```json
{
  "tables": [
    {
      "schema_name": "public",
      "table_name": "users"
    }
  ],
  "exact_count": true,
  "include_pk_range": true
}
```

参数：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tables` | object[] | 否 | 本次检查表，不传则使用任务创建时保存的 `tables` |
| `exact_count` | boolean | 否 | 是否执行精确行数对比 |
| `include_pk_range` | boolean | 否 | 是否检查单列主键范围 |

响应结构与 [数据检查接口响应](/backend-api/data-check/#post-api-data-check-run) 一致。

## `GET /api/tasks/{task_id}/data-check-results`

查询任务的数据检查结果。

响应：

```json
{
  "items": [
    {
      "id": 1,
      "task_id": 1,
      "schema_name": "public",
      "table_name": "users",
      "status": "passed",
      "created_at": "2026-06-03 16:30:00",
      "checks": [
        {
          "type": "exact_count",
          "source_value": 1000,
          "target_value": 1000,
          "status": "passed"
        }
      ]
    }
  ]
}
```

## curl 示例

创建准备任务：

```bash
curl -s http://127.0.0.1:8000/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "用户库迁移",
    "source_instance_id": 1,
    "target_instance_id": 2,
    "schemas": ["public"],
    "tables": [
      { "schema_name": "public", "table_name": "users" }
    ]
  }'
```

预览任务序列：

```bash
curl -s http://127.0.0.1:8000/api/tasks/1/sequences/preview \
  -H 'Content-Type: application/json' \
  -d '{
    "step": 10000,
    "skip_if_target_greater": true
  }'
```

查询任务日志：

```bash
curl -s http://127.0.0.1:8000/api/tasks/1/logs
```
