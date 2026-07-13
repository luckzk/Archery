# 生产运行方式记录

> 记录日期：2026-07-01。当前项目仍处于开发阶段，本文件只记录从源码中确认的 Archery 生产运行形态，作为后续正式部署、容器化改造和运维固化的参考。当前本机 debug 启动方式不等同于生产运行方式。

## 源码依据

- `src/docker/Dockerfile`：生产镜像构建入口。
- `src/docker/startup.sh`：容器启动脚本。
- `src/docker/nginx.conf`：容器内 Nginx 反向代理配置。
- `src/docker/supervisord.conf`：Django-Q `qcluster` 进程管理配置。
- `src/docker-compose/docker-compose.yml`：Docker Compose 部署示例。
- `src/docker-compose/.env`：Compose 示例环境变量。
- `archery/settings.py`：数据库、缓存、Django-Q 等运行配置。
- `src/charts/`：Kubernetes Helm 历史部署模板，源码说明中已标注不建议继续作为最新部署依据。

## 进程拓扑

源码里的生产入口不是 Django `runserver`，而是：

```text
User / LB
  -> Nginx :9123
    -> Gunicorn 127.0.0.1:8888
      -> Django WSGI

Django / Django-Q
  -> Redis default cache
  -> Redis broker for qcluster
  -> MySQL metadata database
```

其中 `archery/settings.py` 里的 `Q_CLUSTER` 使用 `"django_redis": "default"`，所以 Redis 同时承担缓存和 Django-Q broker。

## 容器启动流程

`src/docker/startup.sh` 的启动顺序如下：

1. 进入 `/opt/archery`。
2. 激活 `/opt/venv4archery`。
3. 根据 `NGINX_PORT` 修正 Nginx 转发端口。
4. 启动 Nginx。
5. 执行 `python3 manage.py collectstatic -v0 --noinput`。
6. 通过 `supervisord -c /etc/supervisord.conf` 启动 Django-Q `qcluster`。
7. 启动 Gunicorn：

```bash
gunicorn -w 4 -b 127.0.0.1:8888 --timeout 600 archery.wsgi:application
```

容器内 Nginx 监听 `9123`，静态文件目录为 `/opt/archery/static`，动态请求反代到 `127.0.0.1:8888`。

## Docker Compose 形态

源码自带 `src/docker-compose/docker-compose.yml` 包含以下服务：

- `redis`：`redis:5`，配置密码，使用 `expose: 6379`，只给 Compose 内部服务访问。
- `mysql`：`mysql:5.7`，挂载 `./mysql/my.cnf` 和 `./mysql/datadir`。
- `goinception`：SQL 审核依赖服务。
- `archery`：镜像示例为 `hhyo/archery:v1.14.0`，对外暴露 `9123`，挂载 `local_settings.py`、`soar.yaml`、`downloads`、`logs`、`keys` 等目录。

示例环境变量来自 `src/docker-compose/.env`：

```env
DEBUG=false
DATABASE_URL=mysql://root:123456@mysql:3306/archery
CACHE_URL=redis://redis:6379/0?PASSWORD=123456
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:9123
Q_CLUISTER_WORKERS=4
Q_CLUISTER_TIMEOUT=60
Q_CLUISTER_SYNC=false
```

生产环境必须设置非空且稳定的 `SECRET_KEY`，并明确配置 `ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS`。

## Redis 生产要求

源码的 Compose 示例给 Redis 设置了密码且不映射宿主机端口，这是正确方向。但示例没有显式挂载 Redis 数据目录；Helm 历史模板里 Redis 默认 `persistence.enabled: false`。考虑到 Archery 的 Django-Q broker 使用 Redis，生产环境不应把 Redis 仅当作可丢弃缓存处理。

生产建议：

- Redis 不公网暴露，只允许 Archery 内网访问。
- Redis 必须设置密码或使用云厂商/托管 Redis 的访问控制。
- 开启持久化，推荐 AOF `appendfsync everysec`，并保留 RDB 快照。
- 保留 `stop-writes-on-bgsave-error yes`，持久化失败时应修复磁盘、权限或存储问题，而不是关闭写保护绕过。
- 对 Redis 数据目录做监控、备份或快照策略。

## MySQL 生产要求

Archery 的元数据数据库通过 `DATABASE_URL` 配置。Compose 示例已经将 MySQL 数据目录挂载到 `./mysql/datadir`。

生产建议：

- MySQL 数据目录必须持久化。
- `archery` 库需要定期备份。
- 升级或导入 `src/init_sql/*.sql` 前先备份。
- 不建议长期使用 root 账号运行应用连接，生产应创建权限收敛的应用账号。

## 开发运行与生产运行区别

当前开发阶段可以继续使用本机 debug 方式验证功能，但需要保持边界清晰：

- 开发验证可以使用 Django `runserver`。
- 生产入口应使用 `Nginx + Gunicorn + qcluster`。
- 生产不应使用 `DEBUG=true`。
- 生产不应依赖临时 `systemd-run` 进程。
- 生产 Redis/MySQL 需要持久化、密码和网络隔离。

后续如果要把当前环境切到接近生产的运行方式，建议优先整理为 Compose 或 systemd 管理的固定服务：`nginx`、`gunicorn`、`qcluster`、`redis`、`mysql`，并把所有密钥和连接串放到受控的环境变量或 secret 管理中。
