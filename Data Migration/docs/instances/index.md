# 实例管理

实例管理用于保存源库和目标库连接信息，并为序列设置、数据检查和元数据扫描提供连接能力。

## 实例字段

建议保存以下字段：

| 字段 | 说明 |
| --- | --- |
| `name` | 实例名称 |
| `role` | `source` 或 `target` |
| `host` | 数据库地址 |
| `port` | 数据库端口 |
| `database` | 数据库名 |
| `username` | 用户名 |
| `password_encrypted` | 加密后的密码 |
| `ssl_mode` | SSL 模式 |
| `proxy_type` | 代理类型：`http`、`socks4`、`socks5` |
| `proxy_host` | 代理地址 |
| `proxy_port` | 代理端口 |
| `proxy_username` | 代理用户名 |
| `proxy_password_encrypted` | 加密后的代理密码 |
| `description` | 备注 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

## 连接测试

连接测试需要验证：

- 网络可达
- 用户名和密码正确
- 数据库存在
- 当前用户可以读取系统 catalog
- 当前用户可以访问目标 schema
- 如果配置代理，需要验证代理能连通 PostgreSQL 目标地址

建议连接成功后读取以下信息：

```sql
SELECT
  version(),
  current_database(),
  current_user,
  inet_server_addr(),
  inet_server_port();
```

## 安全要求

密码不能明文保存。推荐使用：

- 应用级密钥加密
- KMS
- Vault

开发阶段可以先使用应用级密钥加密，但要保证：

- 密钥不提交到代码仓库
- 连接串不写入日志
- 操作日志中脱敏展示账号和地址

MVP 当前本地实现使用 SQLite 保存实例配置，密码字段仅用于开发验证。正式版本必须补充加密存储。

## 代理连接

实例可以选择通过代理连接 PostgreSQL，支持：

- HTTP CONNECT
- SOCKS4
- SOCKS5

不配置代理时，后端会直接连接 PostgreSQL。配置代理时，后端会创建临时本地 TCP 转发端口，再通过代理访问真实数据库地址。

## 权限建议

用于扫描和检查的用户至少需要：

- 连接数据库权限
- 读取 `pg_catalog`
- 读取目标业务 schema
- 对目标库 sequence 执行 `setval` 的权限

如果后续要创建 publication / subscription，还需要额外的复制和建对象权限。
