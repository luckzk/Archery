# 元数据接口

元数据接口用于扫描表、估算行数、主键字段和 `REPLICA IDENTITY`。

## `POST /api/metadata/tables`

扫描表、估算行数、主键字段和 `REPLICA IDENTITY`。

请求：

```json
{
  "instance_id": 1,
  "schemas": ["public"]
}
```

参数：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `instance_id` | number | 是 | 已保存的实例 ID |
| `schemas` | string[] | 否 | 限定扫描 schema，不传则扫描所有业务 schema |

响应：

```json
{
  "tables": [
    {
      "schema_name": "public",
      "table_name": "users",
      "estimated_rows": 12000,
      "replica_identity": "DEFAULT",
      "replica_identity_index": null,
      "primary_key_index": "users_pkey",
      "primary_key_columns": ["id"],
      "eligible_replica_identity_indexes": [
        {
          "index_name": "users_pkey",
          "columns": ["id"]
        }
      ]
    }
  ]
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `estimated_rows` | PostgreSQL 统计信息中的估算行数，不等同于精确 `count(*)` |
| `replica_identity` | 表当前复制标识模式 |
| `replica_identity_index` | `USING INDEX` 模式下使用的索引 |
| `primary_key_index` | 主键对应的索引名称，可用于显式设置 `REPLICA IDENTITY USING INDEX` |
| `primary_key_columns` | 主键字段数组，复合主键会返回多个字段 |
| `eligible_replica_identity_indexes` | 满足 `REPLICA IDENTITY USING INDEX` 条件的唯一索引列表 |
