# PostgreSQL 优化任务清单

## 目标

围绕 PostgreSQL 在 Archery 中的真实日常可用性，补齐 SQLQuery 资源视图、执行计划、诊断和迁移助手能力。所有账号级偏好、知识库、收藏等持久状态必须落库，不使用浏览器缓存作为持久方案。

## Task 1: 函数/存储过程重载支持

- 状态：已完成
- 范围：
  - SQLQuery 右侧可编程对象中，PgSQL 函数/过程展示为 `name(args)`。
  - 详情查看使用 `pg_proc.oid` 或等价唯一标识精确定位，避免同名不同参数混淆。
  - 插入编辑器时使用带参数提示的名称。
- 验收：
  - 同名不同参数函数能分别展示和查看定义。
  - 旧 MySQL 视图/函数/过程/触发器接口不回退。
  - Playwright 冒烟覆盖一个带 `data-program-object-id` 的函数定义查看。

## Task 2: 右侧 PgSQL 对象资源类型扩展

- 状态：已完成
- 范围：
  - 增加 materialized view。
  - 增加 sequence。
  - 增加 index、constraint/foreign key 的对象入口或表下钻入口。
  - 识别 partition table / partition child。
- 验收：
  - 选择 PgSQL 库/模式后，右侧能看到新增对象分组。
  - 对象支持搜索、刷新、插入名称，能查看定义或关键元信息。

## Task 3: PgSQL 表下钻增强

- 状态：已完成
- 范围：
  - 表下钻除列、索引外，增加主键、外键、唯一约束、check 约束。
  - 展示表注释、列注释。
  - 展示分区信息，包括父表/子分区。
- 验收：
  - 表节点展开后能按分组查看新增信息。
  - 约束/索引信息可复制或插入关键对象名。
  - 查询失败时使用页面内提示，不使用浏览器原生弹窗。

## Task 4: PgSQL EXPLAIN JSON 计划视图

- 状态：已完成
- 范围：
  - SQLQuery 中对 PgSQL `EXPLAIN (FORMAT JSON, COSTS, VERBOSE)` 增加结构化视图。
  - 默认不使用 `ANALYZE`，避免真实执行慢 SQL。
  - Aliyun 主题中可手动勾选 `ANALYZE`，执行前用页面内确认提示，确认后使用 `EXPLAIN (FORMAT JSON, COSTS, VERBOSE, ANALYZE, BUFFERS, WAL)`。
  - 展示节点类型、成本、行数估计、过滤条件、索引条件等。
  - `ANALYZE` 结果展示 actual time/rows、Buffers/WAL、Planning Time、Execution Time。
- 验收：
  - PgSQL explain 结果能以树形/表格方式查看。
  - 原始结果仍可查看。
  - 非 PgSQL 引擎行为不受影响。

## Task 5: PgSQL 锁等待 / 阻塞链诊断

- 状态：已完成
- 范围：
  - 在 `/dbdiagnostic/` 或 SQLQuery 附近展示 PostgreSQL 阻塞链。
  - 展示 waiting pid、blocking pid、等待时长、lock type、relation、等待 SQL、阻塞 SQL。
  - 生成 `pg_cancel_backend` / `pg_terminate_backend` SQL。
  - SQLQuery Aliyun 主题中在结果表上方展示阻塞链摘要，等待超过 30 秒高亮，操作 SQL 可复制。
- 验收：
  - 没有阻塞时展示空状态。
  - 有阻塞时能看到链路和可复制处理 SQL。
  - 权限继续使用现有会话/锁相关权限。

## 后续补充优化状态

- 状态：已完成
- 范围：
  - 表资源和可编程对象资源刷新按钮增加刷新中不可点击状态。
  - 表资源刷新、表分组刷新、可编程对象列表刷新、定义刷新均支持 `_refresh` 强制刷新参数。
  - 表分组支持单独刷新。
  - 索引定义通过 PgSQL `pg_get_indexdef` 返回并支持复制。
  - 约束定义支持复制。
  - 可编程对象定义面板支持复制定义和刷新定义。
- 验收：
  - Playwright 冒烟覆盖刷新按钮不可点击、索引定义复制、可编程对象定义复制/刷新、锁诊断摘要和复制操作 SQL。

## Task 6: PgSQL 迁移助手特性检查增强

- 状态：已完成
- 范围：
  - extension 差异。
  - collation 差异。
  - role/owner/privilege 差异。
  - sequence ownership。
  - identity/generated column。
  - partition table。
  - materialized view。
  - function/procedure/trigger 依赖顺序。
- 验收：
  - 迁移任务详情中能看到新增检查结果。
  - 检查结果落库，不依赖浏览器缓存。
  - 对缺权限/缺系统视图的情况给出明确错误。

## 当前执行顺序

1. Task 1：先解决函数/过程重载，减少对象定义误判风险。
2. Task 2：扩展 materialized view 和 sequence，保持右侧资源栏可用性。
3. Task 3：扩展表下钻元信息。
4. Task 4：结构化 PgSQL explain。
5. Task 5：阻塞链诊断。
6. Task 6：迁移助手增强。

## 验证命令

```bash
python -m py_compile sql/engines/pgsql.py sql/data_dictionary.py sql/instance.py sql/query.py sql/views.py scripts/sqlquery_aliyun_smoke.py
node --check common/static/sqlquery/sqlquery-aliyun-core.js && node --check common/static/sqlquery/sqlquery-aliyun-resources.js && node --check common/static/sqlquery/sqlquery-aliyun-results.js && node --check common/static/sqlquery/sqlquery-aliyun-init.js
git diff --check
```

可用环境下继续运行：

```bash
DEBUG=true SECRET_KEY=dev-debug-secret-dev-debug-secret-123456 DATABASE_URL=mysql://root:QzLmNpRw%21%40%23S@127.0.0.1:23309/archery CACHE_URL=redis://127.0.0.1:6379/0 ENABLE_CAS=false .venv/bin/python manage.py check
DEBUG=true SECRET_KEY=dev-debug-secret-dev-debug-secret-123456 DATABASE_URL=mysql://root:QzLmNpRw%21%40%23S@127.0.0.1:23309/archery CACHE_URL=redis://127.0.0.1:6379/0 ENABLE_CAS=false .venv/bin/python manage.py runserver 127.0.0.1:9124 --insecure --noreload
.venv/bin/python scripts/sqlquery_aliyun_smoke.py --base-url http://127.0.0.1:9124 --username zkiss --password 'Aa9213..99!'
```
