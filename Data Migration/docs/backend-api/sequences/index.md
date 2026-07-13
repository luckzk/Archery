# 序列接口

序列接口用于扫描源库序列、预览目标库序列设置值，并执行一键设置。

## `POST /api/sequences/scan`

扫描源库序列。可选同时扫描目标库序列。

请求：

```json
{
  "source_instance_id": 1,
  "target_instance_id": 2,
  "schemas": ["public"]
}
```

参数：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `source_instance_id` | number | 是 | 源库实例 ID |
| `target_instance_id` | number | 否 | 目标库实例 ID |
| `schemas` | string[] | 否 | 限定 schema |

响应：

```json
{
  "source": [
    {
      "sequence_schema": "public",
      "sequence_name": "users_id_seq",
      "last_value": 95000,
      "increment_by": 1,
      "cycle": false,
      "cache_size": 1,
      "table_schema": "public",
      "table_name": "users",
      "column_name": "id"
    }
  ],
  "target": []
}
```

## `POST /api/sequences/preview`

预览目标库序列设置值，不执行写入。

请求：

```json
{
  "source_instance_id": 1,
  "target_instance_id": 2,
  "step": 10000,
  "schemas": ["public"],
  "skip_if_target_greater": true
}
```

参数：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `source_instance_id` | number | 是 | 源库实例 ID |
| `target_instance_id` | number | 是 | 目标库实例 ID |
| `step` | number | 否 | 在源库当前值基础上增加的步进值，默认 `10000` |
| `schemas` | string[] | 否 | 限定 schema |
| `skip_if_target_greater` | boolean | 否 | 如果目标库当前值更大，是否跳过，默认 `true` |

响应：

```json
{
  "items": [
    {
      "sequence_schema": "public",
      "sequence_name": "users_id_seq",
      "last_value": 95000,
      "target_current_value": 100,
      "target_value": 105000,
      "should_apply": true,
      "reason": "ready",
      "setval_sql": "SELECT setval('public.users_id_seq', 105000, true);"
    }
  ]
}
```

## `POST /api/sequences/apply`

执行目标库序列设置。

请求参数与 `/api/sequences/preview` 相同。

响应：

```json
{
  "items": [
    {
      "sequence_schema": "public",
      "sequence_name": "users_id_seq",
      "target_value": 105000,
      "should_apply": true,
      "reason": "ready",
      "status": "applied"
    }
  ]
}
```

状态说明：

| 状态 | 说明 |
| --- | --- |
| `applied` | 已执行 `setval` |
| `skipped` | 因目标序列缺失、目标值更大等原因跳过 |
| `failed` | 执行失败，响应中会包含 `error` |

## curl 示例

预览序列设置：

```bash
curl -s http://127.0.0.1:8000/api/sequences/preview \
  -H 'Content-Type: application/json' \
  -d '{
    "source_instance_id": 1,
    "target_instance_id": 2,
    "step": 10000,
    "schemas": ["public"],
    "skip_if_target_greater": true
  }'
```
