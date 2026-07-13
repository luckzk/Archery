# 接口总览

## 启动方式

第一次安装后端依赖：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
HTTP_PROXY=http://127.0.0.1:8001 HTTPS_PROXY=http://127.0.0.1:8001 pip install -r requirements.txt
```

后端依赖只安装在 `backend/.venv` 虚拟环境中，不安装到本机全局 Python。

启动 API：

```bash
cd backend
scripts/start-api.sh
```

启动后访问：

- `GET http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## 存储说明

实例连接信息保存在：

```text
backend/.data/app.db
```

当前是开发版 MVP，密码会保存在本地 SQLite 中。后续正式版本需要改成加密保存，推荐使用应用密钥、KMS 或 Vault。

## 健康检查

### `GET /health`

检查后端服务是否启动。

响应：

```json
{
  "ok": true
}
```

## PostgreSQL 连接字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `host` | string | 是 | PostgreSQL 地址 |
| `port` | number | 是 | 端口，默认 `5432` |
| `database` | string | 是 | 数据库名 |
| `username` | string | 是 | 用户名 |
| `password` | string | 是 | 密码 |
| `sslmode` | string | 否 | SSL 模式，默认 `prefer` |

## 代理字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `proxy_type` | string | 否 | 代理类型：`http`、`socks4`、`socks5` |
| `proxy_host` | string | 否 | 代理地址 |
| `proxy_port` | number | 否 | 代理端口 |
| `proxy_username` | string | 否 | 代理用户名 |
| `proxy_password` | string | 否 | 代理密码 |

如果不需要代理，代理字段全部不传即可。如果配置代理，`proxy_type`、`proxy_host`、`proxy_port` 必须一起提供。

::: tip 代理实现说明
`psycopg/libpq` 不直接支持 HTTP 或 SOCKS 代理参数。后端会在执行数据库操作时创建一个临时本地 TCP 转发端口，由该端口通过 HTTP CONNECT 或 SOCKS 代理连接真实 PostgreSQL，然后 psycopg 连接这个临时本地端口。
:::

::: warning SSL 注意事项
如果通过代理连接，并且 PostgreSQL 使用 `sslmode=verify-full`，证书主机名校验可能因为 psycopg 实际连接的是本地临时端口而失败。MVP 建议代理场景先使用 `prefer`、`require` 或后续补充更完整的证书配置能力。
:::

## 实例角色

| 值 | 说明 |
| --- | --- |
| `source` | 源库 |
| `target` | 目标库 |
| `both` | 既可作为源库也可作为目标库 |
