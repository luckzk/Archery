# AGENTS.md

## 全局约定

- 始终使用简体中文交流。
- 不回滚用户已有未提交改动，除非用户明确要求。
- 代码保持原始语言；Shell 命令保持英文。

## 当前集成方向

- `PgSQL迁移助手` 继续集成到 Archery 主体，不再以 `Data Migration/` 独立原型作为主方向。
- 在 Archery 主体内作为 `工具插件` 接入，入口位于左侧 `工具插件` 菜单。
- 工具插件注册表位于 `sql/tool_plugins.py`。
- 部署级启停开关为 `ENABLED_TOOL_PLUGINS`，默认启用：

```env
ENABLED_TOOL_PLUGINS=archive,pgsql_migration,my2sql,schemasync
```

## PgSQL迁移助手状态

- 已接入 Archery 主体路由和页面：
  - `sql/pgsql_migration.py`
  - `sql/templates/pgsql_migration.html`
  - `sql/templates/pgsql_migration_detail.html`
  - `sql/utils/pgsql_migration.py`
- 已通过工具插件注册表控制菜单展示。
- 已通过 `tool_plugin_enabled_required("pgsql_migration")` 控制直达 URL/API 访问。
- 权限仍使用 Archery 权限体系：
  - `menu_pgsql_migration`
  - `pgsql_migration_mgt`
  - `pgsql_migration_execute`

## SQLQuery Aliyun 主题状态

- `/sqlquery/` 保持 Archery 原版页面不动，通过页面内主题切换进入 Aliyun 风格。
- Aliyun 主题前端主文件：
  - `sql/templates/sqlquery.html`
  - `common/static/sqlquery/sqlquery-aliyun.css`
  - `common/static/sqlquery/sqlquery-aliyun-core.js`
  - `common/static/sqlquery/sqlquery-aliyun-favorites.js`
  - `common/static/sqlquery/sqlquery-aliyun-results.js`
  - `common/static/sqlquery/sqlquery-aliyun-knowledge.js`
  - `common/static/sqlquery/sqlquery-aliyun-resources.js`
  - `common/static/sqlquery/sqlquery-aliyun-init.js`
  - `common/static/sqlquery/sqlquery-aliyun.js` 仅保留拆分说明占位。
- Aliyun 主题已实现的主要交互：
  - 顶部选择实例、库、模式。
  - 右侧展示表和可编程对象；选择库/模式后刷新对象树。
  - 表资源栏刷新会直接请求 `/instance/instance_resource/` 获取当前库/模式的表，并同步原始 `#table_name` 选择框；失败时回退当前 select 缓存并用页面内提示。
  - 表资源栏和可编程对象资源栏均支持搜索；刷新时按钮进入不可点击的 loading 状态，并带 `_refresh` 参数绕过前端缓存。
  - 表节点可下钻概要、列、索引、约束、分区；列可插入编辑器，表可生成查询 SQL；索引和约束支持复制定义。
  - 表下分组支持单独刷新，刷新中按钮不可点击。
  - 可编程对象支持 view、materialized view、sequence、function、procedure、trigger 的列表展示、名称插入、点击查看定义；PgSQL 详情查询已补 `pg_views`、`pg_proc`、`pg_trigger` 等。
  - 可编程对象定义面板支持复制定义和刷新定义；函数/过程详情使用 `pg_proc.oid` 精确定位重载对象。
  - 每次执行 SQL 都新开执行结果 tab，结果 tab 支持关闭、搜索、列设置入口、复制 SQL/列名/单元格/行，并显示返回行数、执行耗时、脱敏耗时。
  - PgSQL 执行计划支持 `EXPLAIN (FORMAT JSON, COSTS, VERBOSE)` 的结构化树/表视图；可手动勾选 `ANALYZE`，执行前使用页面内确认，结果展示 actual time/rows、Buffers/WAL、Planning/Execution time。
  - PgSQL 锁诊断在结果表上方展示阻塞链摘要，等待超过 30 秒高亮，并支持复制 `pg_cancel_backend` / `pg_terminate_backend` SQL。
  - “我的 SQL”下含知识库、收藏、执行历史；执行历史只展示历史记录，不嵌入执行结果。
- SQLQuery 界面偏好已落库，不使用浏览器本地缓存：
  - 模型：`sql.models.SqlQueryPreference`
  - 管理后台：`sql.admin.SqlQueryPreferenceAdmin`
  - 接口：`sql/query.py` 中 `/query/preference/`
  - 初始化 SQL：`src/init_sql/v1.14.0_pgsql_metrics.sql`
  - 保存账号级 `theme`、`resource_tab`、`mysql_tab`，页面初始化从数据库读取；不再使用 `localStorage.sqlquery_theme`。
- 知识库已从 localStorage 改为服务端账号级保存：
  - 模型：`sql.models.SqlQueryKnowledge`
  - 管理后台：`sql.admin.SqlQueryKnowledgeAdmin`
  - 接口：`sql/query.py` 中 `/query/knowledge/`
  - 初始化 SQL：`src/init_sql/v1.14.0_pgsql_metrics.sql`
  - 支持新增、编辑、复制、删除、搜索、引擎筛选、场景筛选；引擎支持多选。
- 收藏交互：
  - 新增、编辑、删除均使用页面内提示/弹窗，不使用浏览器 `alert`/`confirm`/`prompt`。
  - 编辑收藏可同时修改注释和 SQL；后端 `/query/favorite/` 会在编辑时同步更新关联 `query_log.sqllog`。
  - Aliyun 收藏列表直接展示 SQL，支持搜索、排序、回填。
- `/sqlquery/` 相关 UI 交互应优先使用页面内提示：
  - `showSqlqueryPageNotice`
  - `showAliyunNotice`
  - 避免新增浏览器原生弹窗。
- 元数据库结构变更仍遵循本项目约束：不新增 `sql/migrations/`，优先维护 `src/init_sql/*.sql`。
- 当前常用静态验证：
  - `node --check common/static/sqlquery/sqlquery-aliyun-core.js common/static/sqlquery/sqlquery-aliyun-favorites.js common/static/sqlquery/sqlquery-aliyun-results.js common/static/sqlquery/sqlquery-aliyun-knowledge.js common/static/sqlquery/sqlquery-aliyun-resources.js common/static/sqlquery/sqlquery-aliyun-init.js`
  - `python -m py_compile sql/query.py sql/models.py sql/admin.py sql/urls.py sql/views.py sql/utils/sqlquery_favorite.py sql/utils/sqlquery_knowledge.py sql/utils/sqlquery_preference.py scripts/sqlquery_aliyun_smoke.py`
  - `git diff --check`
  - 可用环境下运行 `scripts/sqlquery_aliyun_smoke.py`，覆盖主题、资源栏、知识库、收藏、结果 tab、偏好落库和无浏览器原生弹窗。
- 当前本地可用验证环境：
  - 元数据库：`DATABASE_URL=mysql://root:QzLmNpRw%21%40%23S@127.0.0.1:23309/archery`
  - Redis：`CACHE_URL=redis://127.0.0.1:6379/0`
  - 临时服务可用命令：

```bash
DEBUG=true SECRET_KEY=dev-debug-secret-dev-debug-secret-123456 DATABASE_URL=mysql://root:QzLmNpRw%21%40%23S@127.0.0.1:23309/archery CACHE_URL=redis://127.0.0.1:6379/0 ENABLE_CAS=false .venv/bin/python manage.py runserver 127.0.0.1:9124 --insecure --noreload
```

  - 冒烟命令：

```bash
.venv/bin/python scripts/sqlquery_aliyun_smoke.py --base-url http://127.0.0.1:9124 --username zkiss --password 'Aa9213..99!'
```

  - 注意：已有 `9123` 服务通常是 `--noreload`，修改 Python、模板或静态 JS/CSS 后要重启对应服务才会生效；本地验证可用 9124 临时服务，验证后停止。

## 相关约束

- 当前仓库历史上不提交 `sql/migrations/`；涉及元数据库结构变更时优先维护 `src/init_sql/*.sql`。
- `Data Migration/` 是早期 FastAPI + React + SQLite 原型，暂不作为主集成方向；除非用户明确要求，不要继续扩展该目录。
- 当前环境 `.git` 被只读挂载，无法执行 `git add` / `git commit`。
- 当前环境缺少 `django` 和 `pytest`，不能运行 `python manage.py check` 或 pytest；可运行 `python -m py_compile` 和 `git diff --check` 做静态校验。
