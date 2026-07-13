# 后端接口

本章节记录 PostgreSQL 迁移控制台后端 API。接口按业务域拆分，每一章只描述一类接口。

当前后端 MVP 位于 `backend/` 目录，使用 FastAPI + psycopg + SQLite。

## 接口分组

| 分组 | 说明 |
| --- | --- |
| [接口总览](/backend-api/overview/) | 启动方式、通用字段、代理连接说明 |
| [实例接口](/backend-api/instances/) | PostgreSQL 实例连接测试、保存、查询、删除 |
| [任务接口](/backend-api/tasks/) | 迁移准备任务创建、状态、日志、结果查询和任务化操作 |
| [元数据接口](/backend-api/metadata/) | 表、主键、`REPLICA IDENTITY` 扫描 |
| [序列接口](/backend-api/sequences/) | 源库序列扫描、目标库设置预览、一键设置 |
| [数据检查接口](/backend-api/data-check/) | 行数检查、主键范围检查 |

## 基础地址

开发环境默认地址：

```text
http://127.0.0.1:8000
```

交互式 OpenAPI 文档：

```text
http://127.0.0.1:8000/docs
```

健康检查：

```http
GET /health
```
