# 数据检查接口

数据检查接口用于对源库和目标库执行表级一致性检查。

## `POST /api/data-check/run`

对源库和目标库执行表级数据检查。

请求：

```json
{
  "source_instance_id": 1,
  "target_instance_id": 2,
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
| `source_instance_id` | number | 是 | 源库实例 ID |
| `target_instance_id` | number | 是 | 目标库实例 ID |
| `tables` | object[] | 是 | 要检查的表 |
| `tables[].schema_name` | string | 是 | schema 名 |
| `tables[].table_name` | string | 是 | 表名 |
| `exact_count` | boolean | 否 | 是否执行精确行数对比 |
| `include_pk_range` | boolean | 否 | 是否检查单列主键范围 |

响应：

```json
[
  {
    "schema_name": "public",
    "table_name": "users",
    "status": "passed",
    "checks": [
      {
        "type": "exact_count",
        "source_value": 1000,
        "target_value": 1000,
        "status": "passed"
      },
      {
        "type": "primary_key_range",
        "primary_key_column": "id",
        "source_value": {
          "min_value": 1,
          "max_value": 1000
        },
        "target_value": {
          "min_value": 1,
          "max_value": 1000
        },
        "status": "passed"
      }
    ]
  }
]
```

结果状态：

| 状态 | 说明 |
| --- | --- |
| `passed` | 检查通过 |
| `warning` | 检查可执行但存在限制，比如复合主键无法做范围检查 |
| `failed` | 检查失败或源目标结果不一致 |

## curl 示例

执行数据检查：

```bash
curl -s http://127.0.0.1:8000/api/data-check/run \
  -H 'Content-Type: application/json' \
  -d '{
    "source_instance_id": 1,
    "target_instance_id": 2,
    "tables": [
      { "schema_name": "public", "table_name": "users" }
    ],
    "exact_count": true,
    "include_pk_range": true
  }'
```
