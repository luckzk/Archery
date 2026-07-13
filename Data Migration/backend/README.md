# PostgreSQL Migration API

后端 MVP 使用 FastAPI + psycopg + SQLite。

## 安装

后端依赖必须安装在 `backend/.venv` 虚拟环境中，避免污染本机 Python 环境。

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 启动

```bash
scripts/start-api.sh
```

## API 文档

启动后访问：

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/health

## 代理连接 PostgreSQL

实例连接支持通过 HTTP CONNECT 或 SOCKS 代理访问 PostgreSQL：

- `proxy_type`: `http`、`socks4`、`socks5`
- `proxy_host`: 代理地址
- `proxy_port`: 代理端口
- `proxy_username`: 代理用户名，可选
- `proxy_password`: 代理密码，可选

如果不需要代理，以上字段不传即可。

示例：

```json
{
  "host": "10.0.0.10",
  "port": 5432,
  "database": "app",
  "username": "postgres",
  "password": "postgres",
  "sslmode": "prefer",
  "proxy_type": "socks5",
  "proxy_host": "127.0.0.1",
  "proxy_port": 1080
}
```
