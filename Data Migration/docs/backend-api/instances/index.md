# 实例接口

实例接口用于测试、保存、查询和删除 PostgreSQL 连接配置。

## `POST /api/instances/test`

测试 PostgreSQL 连接，不保存实例。

请求：

```json
{
  "host": "127.0.0.1",
  "port": 5432,
  "database": "postgres",
  "username": "postgres",
  "password": "postgres",
  "sslmode": "prefer",
  "proxy_type": "socks5",
  "proxy_host": "127.0.0.1",
  "proxy_port": 1080,
  "proxy_username": null,
  "proxy_password": null
}
```

响应：

```json
{
  "ok": true,
  "message": "Connection succeeded",
  "metadata": {
    "version": "PostgreSQL ...",
    "database": "postgres",
    "username": "postgres",
    "server_addr": "127.0.0.1",
    "server_port": 5432
  }
}
```

## `POST /api/instances`

保存 PostgreSQL 实例。

请求：

```json
{
  "name": "源库",
  "role": "source",
  "host": "127.0.0.1",
  "port": 5432,
  "database": "app",
  "username": "postgres",
  "password": "postgres",
  "sslmode": "prefer",
  "proxy_type": "http",
  "proxy_host": "127.0.0.1",
  "proxy_port": 8001,
  "description": "本地开发源库"
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `name` | 实例显示名称 |
| `role` | `source`、`target` 或 `both` |
| `description` | 备注，可为空 |

响应会隐藏密码：

```json
{
  "id": 1,
  "name": "源库",
  "role": "source",
  "host": "127.0.0.1",
  "port": 5432,
  "database": "app",
  "username": "postgres",
  "sslmode": "prefer",
  "proxy_type": "http",
  "proxy_host": "127.0.0.1",
  "proxy_port": 8001,
  "proxy_username": null,
  "description": "本地开发源库",
  "created_at": "2026-06-03 16:30:00",
  "updated_at": "2026-06-03 16:30:00"
}
```

响应不会返回实例密码，也不会返回代理密码。

## `GET /api/instances`

获取实例列表。

## `GET /api/instances/{instance_id}`

获取单个实例。

路径参数：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `instance_id` | number | 实例 ID |

## `DELETE /api/instances/{instance_id}`

删除实例。

响应：

```json
{
  "ok": true
}
```

## curl 示例

保存实例：

```bash
curl -s http://127.0.0.1:8000/api/instances \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "source-local",
    "role": "source",
    "host": "127.0.0.1",
    "port": 5432,
    "database": "app",
    "username": "postgres",
    "password": "postgres",
    "sslmode": "prefer",
    "proxy_type": "socks5",
    "proxy_host": "127.0.0.1",
    "proxy_port": 1080
  }'
```
