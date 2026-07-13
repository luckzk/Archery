# Replica Identity

`REPLICA IDENTITY` 决定逻辑复制中 UPDATE 和 DELETE 如何定位目标库中的行。迁移控制台需要清晰展示每张表当前的复制标识模式，以及 `USING INDEX` 模式下使用的索引。

## 模式说明

| 模式 | 含义 | 风险 |
| --- | --- | --- |
| `DEFAULT` | 使用主键作为复制标识 | 无主键表无法正确支持 UPDATE / DELETE |
| `USING INDEX` | 使用指定唯一索引作为复制标识 | 索引必须满足逻辑复制要求 |
| `FULL` | 使用整行旧值定位 | WAL 体积可能明显增大 |
| `NOTHING` | 不记录旧行标识 | UPDATE / DELETE 无法复制 |

## 扫描 SQL

可通过 `pg_class.relreplident` 获取模式：

```sql
SELECT
  n.nspname AS schema_name,
  c.relname AS table_name,
  CASE c.relreplident
    WHEN 'd' THEN 'DEFAULT'
    WHEN 'n' THEN 'NOTHING'
    WHEN 'f' THEN 'FULL'
    WHEN 'i' THEN 'USING INDEX'
  END AS replica_identity
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema');
```

## 获取 USING INDEX 对应索引

```sql
SELECT
  ns.nspname AS schema_name,
  tbl.relname AS table_name,
  idx.relname AS replica_identity_index
FROM pg_index i
JOIN pg_class idx ON idx.oid = i.indexrelid
JOIN pg_class tbl ON tbl.oid = i.indrelid
JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
WHERE i.indisreplident = true;
```

## 获取主键对应索引

有主键的表在 `REPLICA IDENTITY DEFAULT` 下会使用主键定位 UPDATE / DELETE。若需要显式设置成 `USING INDEX`，可以展示主键索引名称给用户确认。

```sql
SELECT
  ns.nspname AS schema_name,
  tbl.relname AS table_name,
  idx.relname AS primary_key_index,
  array_agg(att.attname ORDER BY key.ord) AS primary_key_columns
FROM pg_index i
JOIN pg_class idx ON idx.oid = i.indexrelid
JOIN pg_class tbl ON tbl.oid = i.indrelid
JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
JOIN unnest(i.indkey) WITH ORDINALITY AS key(attnum, ord) ON true
JOIN pg_attribute att ON att.attrelid = i.indrelid AND att.attnum = key.attnum
WHERE i.indisprimary = true
GROUP BY ns.nspname, tbl.relname, idx.relname;
```

## 获取可用唯一索引

可作为 `REPLICA IDENTITY USING INDEX` 的索引需要满足：唯一索引、非 partial、非 deferrable、非表达式索引，并且索引字段都为 `NOT NULL`。

```sql
SELECT
  ns.nspname AS schema_name,
  tbl.relname AS table_name,
  idx.relname AS index_name,
  array_agg(att.attname ORDER BY key.ord) AS columns
FROM pg_index i
JOIN pg_class idx ON idx.oid = i.indexrelid
JOIN pg_class tbl ON tbl.oid = i.indrelid
JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
JOIN unnest(i.indkey) WITH ORDINALITY AS key(attnum, ord) ON true
JOIN pg_attribute att ON att.attrelid = i.indrelid AND att.attnum = key.attnum
WHERE i.indisunique = true
  AND i.indisvalid = true
  AND i.indimmediate = true
  AND i.indpred IS NULL
  AND i.indexprs IS NULL
GROUP BY ns.nspname, tbl.relname, idx.relname
HAVING bool_and(att.attnotnull);
```

## 风险判断

控制台建议标记以下风险：

- 表为 `DEFAULT`，但没有主键。
- 表为 `NOTHING`。
- 表为 `FULL`，且表数据量较大。
- 表存在 UPDATE / DELETE 业务，但没有稳定的唯一标识。
- `USING INDEX` 对应索引字段允许空值。

## 修复建议

不同场景的建议：

- 有主键：保持 `DEFAULT`。
- 无主键但有合适唯一索引：设置 `USING INDEX`。
- 无主键也无合适索引：建议补充主键或唯一索引。
- 临时迁移且 UPDATE / DELETE 较少：可谨慎使用 `FULL`。

设置示例：

```sql
ALTER TABLE public.orders REPLICA IDENTITY USING INDEX orders_pkey;
ALTER TABLE public.orders REPLICA IDENTITY USING INDEX orders_unique_idx;
ALTER TABLE public.orders REPLICA IDENTITY FULL;
```

MVP 阶段可以先展示和告警，不强制提供自动修复。
