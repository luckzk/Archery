# 技术栈

第一阶段建议使用成熟、实现成本低的技术栈。重点是稳定管理 PostgreSQL 连接、执行 SQL、调度后台任务和展示检查结果。

## 后端

推荐：

- Python
- FastAPI
- psycopg 3
- SQLite 存储 MVP 元数据
- 后续再引入 SQLAlchemy 和 Alembic

原因：

- Python 数据库生态成熟。
- FastAPI 适合快速构建控制台 API。
- `psycopg 3` 对 PostgreSQL 支持完整。
- 后续如果要消费逻辑复制，也可以继续扩展。
- MVP 阶段直接使用 SQLite 保存实例配置，减少启动成本。

## 任务系统

推荐：

- Celery + Redis

适合异步执行：

- 元数据扫描
- 序列采集
- 批量 `setval`
- 大表 `count(*)`
- 抽样校验
- 报告生成

## 元数据数据库

推荐使用 PostgreSQL 保存系统自身数据：

- 实例信息
- 迁移准备任务
- 表扫描结果
- 序列扫描结果
- 数据检查结果
- 操作日志

## 前端

推荐：

- React
- TypeScript
- Vite
- Ant Design 或 MUI

这是一个运维控制台，界面应该偏清晰、密集、可扫描。表格、步骤条、筛选器、状态标签和操作日志会很多，Ant Design 或 MUI 都比较适合。

## 实时状态

推荐：

- Server-Sent Events
- 或 WebSocket

用于展示：

- 后台任务进度
- 当前检查表
- 执行日志
- 错误信息

## 部署

MVP 可以使用 Docker Compose：

- API 服务
- Worker 服务
- Redis
- PostgreSQL 元数据库
- 前端静态资源

后续再考虑 Kubernetes。

## 不建议第一阶段做的技术选择

第一阶段不建议：

- 自研 WAL apply
- 引入复杂流处理框架
- 引入分布式任务编排
- 做跨数据库转换引擎

先把 PostgreSQL 原生能力周边的控制、检查和校准做好，会更快产生价值。
