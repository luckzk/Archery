# SQL 编辑器与 Archery 查询流程分析

本文档用于分析 [hhyo/Archery](https://github.com/hhyo/Archery) 的查询执行流程，并对比当前项目的 SQL 编辑器实现，整理后续可优化方向。

## 分析范围

Archery 是一个 SQL 审核查询平台。它的 README 功能矩阵显示 PgSQL 支持“查询”和“执行”，但不支持审核、备份、数据字典、慢日志、会话管理、账号管理、参数管理和数据归档。README 的依赖清单中也明确列出 PostgreSQL connector、`sqlparse`、SQL 美化、表格组件、任务系统等查询平台常用依赖。

本次重点参考 Archery 的查询入口 `sql/query.py`，以及通用引擎接口和 MySQL 引擎中的查询实现细节。PgSQL 引擎文件在仓库中存在，但当前主要结论来自 Archery 的通用查询链路，因为查询入口会统一调用数据库引擎的 `query_check`、`filter_sql` 和 `query` 方法。

## Archery 查询主流程

Archery 的查询入口是 `sql/query.py` 中的 `query(request)`。整体流程如下：

<div class="archery-flow">
  <div class="flow-node">接收请求参数<br><span>instance_name / db_name / sql_content / limit_num</span></div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">按用户资源组获取实例</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">参数完整性校验</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">get_engine(instance)</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">query_engine.query_check(db_name, sql)</div>
  <div class="flow-branch">
    <div class="flow-node danger">bad_query<br><span>返回错误</span></div>
    <div class="flow-node">检查通过<br><span>继续处理</span></div>
  </div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">可选禁止 SELECT *</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">query_priv_check<br><span>权限与 limit_num 修正</span></div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">EXPLAIN 查询不应用 limit</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node highlight">query_engine.filter_sql(sql, limit_num)<br><span>生成最终执行 SQL</span></div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">query_engine.get_connection(db_name)</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">记录 thread_id</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">按 max_execution_time 创建 kill schedule</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node highlight">query_engine.query(...)</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">删除 kill schedule</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">可选数据脱敏</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">记录 QueryLog</div>
  <div class="flow-arrow">↓</div>
  <div class="flow-node">返回 JSON 结果</div>
</div>

关键点：

- **先检查，后执行**：`query_check` 负责去注释、语句切分、语法类型判断和部分安全检查。
- **先权限，后改写**：`query_priv_check` 会根据用户和实例权限修正最终 `limit_num`。
- **改写后的 SQL 才执行**：`filter_sql(sql, limit_num)` 是查询限制落到数据库侧的关键步骤。
- **执行前拿连接和线程 ID**：先调用 `get_connection`，再获取 `thread_id`，用于后续超时终止。
- **超时不是只靠客户端等待**：Archery 会创建一个定时任务，到点调用 `kill_query_conn` 终止数据库连接。
- **结果后处理独立**：查询结果可以再进入数据脱敏流程，并写入查询日志。

## Archery 引擎接口设计

Archery 的通用引擎接口定义了一组统一方法：

- `get_connection(db_name)`
- `query_check(db_name, sql)`
- `filter_sql(sql, limit_num)`
- `query(db_name, sql, limit_num, ...)`
- `query_masking(db_name, sql, resultset)`
- `kill_connection(thread_id)`
- 数据库、表、字段、索引、视图、函数等元数据方法

这种设计把查询功能拆成三个阶段：

1. **检查阶段**：判断 SQL 是否能执行，返回 `filtered_sql`。
2. **改写阶段**：对 SQL 做 limit、hint、方言特定处理。
3. **执行阶段**：负责连接、游标、fetch、异常和结果封装。

这个分层对多数据库很有价值。即使当前项目只做 PostgreSQL，也值得保留类似边界，避免 SQL 编辑器逻辑全部堆在连接工具函数里。

## Archery 查询细节

## Archery 前端实现方式

Archery 的前端不是独立 SPA，也不是 Vite/React 这类现代前后端分离工程。它更接近传统 Django 后台系统：

- **Django 模板渲染页面**：页面主体由 Django view 返回 HTML template。
- **静态资源集中维护**：公共 CSS、JS、图片、第三方库放在 `common/static/` 一类目录下。
- **模板集中维护**：公共布局、导航、基础模板放在 `common/templates/`，业务模块再有自己的模板目录。
- **页面交互靠 jQuery/Bootstrap 插件**：查询页、工单页、表格页通常通过页面级 JavaScript 发 AJAX 请求。
- **SQL 编辑器用 Ace**：Archery release 记录中有 `upgrade ace.js==1.15.0`。
- **结果表格用 bootstrap-table**：Archery release 记录中有 `bootstrap-table` 从 `v1.18.3` 升到 `v1.22.4` 的变更。

可以把它理解为：

```text
Django urls.py
  -> views.py
    -> render(template.html)
      -> template 引入 common/static 下的 CSS/JS
        -> 页面 JS 通过 AJAX 调后端接口
          -> 后端执行 query / workflow / metadata 等逻辑
```

### 如果要改 Archery 前端

修改 Archery 前端时，推荐按页面链路反查：

1. **先找 URL 路由**
   - 从 `urls.py` 或模块内 `urls.py` 找到页面入口。
   - 查询相关页面通常在 `sql/` 模块下。

2. **再找 view**
   - 进入对应 `views.py`。
   - 看 view 返回哪个 template，或者返回哪些 AJAX JSON 接口。

3. **再改 template**
   - 修改 HTML 结构、按钮、表单、弹窗、表格容器。
   - 公共布局、顶部导航、侧边栏一般在 `common/templates/`。
   - 业务页面模板一般在对应 app 的 `templates/` 目录。

4. **再改页面 JS**
   - 找 template 引入了哪些 JS。
   - 查询页通常会有 Ace editor 初始化、bootstrap-table 初始化、AJAX submit、结果渲染、格式化、导出等代码。

5. **如果改第三方库**
   - Ace、bootstrap-table、select 组件、日期组件等多数是静态文件方式引入。
   - 需要更新 `common/static/` 下对应资源，并检查 template 里的引用路径。

6. **部署时处理静态文件**
   - 开发环境通常直接由 Django 读取 static。
   - 生产环境需要 `collectstatic` 或重新构建镜像，让 Nginx/静态服务拿到新文件。

### 修改 Archery 查询页的常见入口

如果目标是改“在线查询”页面，通常要关注：

- 页面模板：实例选择、数据库选择、SQL 编辑器、执行按钮、结果区域。
- 页面 JS：Ace 初始化、执行按钮事件、limit_num 参数、查询接口调用、结果表格刷新。
- 后端查询入口：`sql/query.py` 的 `query(request)`。
- 数据库引擎：`sql/engines/*` 中的 `query_check`、`filter_sql`、`query`。

Archery 的前端改动和后端查询逻辑经常是配套的。例如要加“实际执行 SQL 展示”，不仅要改页面结果区域，还要让后端 JSON 返回 `filtered_sql` 或 `executed_sql`。

### 对当前项目的启发

当前项目是 Vite + React + TypeScript + Ant Design，不建议照搬 Archery 的 Django template + jQuery 模式。更合适的做法是只借鉴它的产品和流程：

- SQL 编辑器组件化。
- 查询参数、limit、只读模式、执行状态集中管理。
- 结果表格支持截断提示、耗时、导出。
- 后端返回实际执行 SQL。
- 查询历史和执行日志持久化。
- 支持取消执行。

当前项目前端修改入口更简单：

- `frontend/src/App.tsx`：页面、组件、状态、表格、按钮。
- `frontend/src/api.ts`：后端 API 类型和请求函数。
- `frontend/src/styles.css`：页面样式。

因此，如果要继续增强当前项目的 SQL 编辑器，应该在 React 里新增 `SqlEditorPage` 子组件文件，而不是引入 jQuery 插件式写法。

### SQL 检查

MySQL 引擎中的 `query_check` 展示了一个典型模式：

- 使用 `sqlparse.format(sql, strip_comments=True)` 去掉注释。
- 使用 `sqlparse.split(sql)[0]` 获取第一条有效 SQL。
- 只允许 `select`、`show`、`explain` 这类查询语法。
- 标记 `SELECT *`，供系统配置决定是否禁用。
- 对 `select` 先执行 `explain` 检查语法。
- 对敏感系统表做额外阻断。

当前项目已经引入 `sqlparse`，但还没有形成独立的 `query_check` 返回结构，也没有配置项控制 `SELECT *`、敏感对象、EXPLAIN 预检查。

### Limit 处理

Archery 的关键思路不是只在客户端 `fetchmany(limit)`，而是在 `filter_sql(sql, limit_num)` 阶段把限制写进最终 SQL。随后 `query` 执行的是改写后的 SQL。

需要注意：数据库侧 `LIMIT` 不等于所有场景都会快速返回。对大排序、聚合、`count(*)`、窗口函数或不合适的执行计划，PostgreSQL 仍可能需要大量扫描或计算。因此 limit 应和 `statement_timeout`、可取消查询、执行计划预览一起使用。

### 超时与取消

Archery 执行前拿到连接标识，并创建定时 kill 任务。查询完成后删除 schedule。这个设计比单纯设置 HTTP 超时更可靠，因为真正释放的是数据库端正在执行的会话。

当前项目使用 PostgreSQL `SET LOCAL statement_timeout`，这是一个好的起点，但还缺少用户可见的“取消执行”能力，以及查询请求和数据库后端 PID 的关联。

### 结果、日志与审计

Archery 查询成功后会写入 QueryLog，记录用户、库名、实例、SQL、影响行数、耗时、权限检查、命中规则和脱敏状态。

当前项目 SQL 编辑器会返回 `executed_sql`，但没有持久化查询历史、耗时、错误、用户或实例上下文。

## 当前项目实现概览

当前项目新增的 SQL 编辑器主要由以下部分组成：

- `backend/app/sql_editor.py`：提供 `/api/sql/execute` 接口。
- `backend/app/postgres.py`：负责 SQL 解析、只读判断、limit 改写、连接和执行。
- `backend/app/schemas.py`：定义 `SqlExecuteRequest` 和 `SqlExecuteResponse`。
- `frontend/src/App.tsx`：提供 SQL 编辑器页面、实例选择、只读开关、最大行数、结果表格和实际执行 SQL 展示。

当前已有能力：

- 使用已保存 PostgreSQL 实例连接。
- 默认只读模式。
- 使用 `sqlparse.split()` 限制单语句。
- 使用 `sqlparse.parse(...).get_type()` 判断语句类型。
- 只读模式允许 `SELECT`、`WITH`、`SHOW`、`EXPLAIN`、`VALUES`、`TABLE`。
- 对可限制查询追加顶层 `LIMIT max_rows + 1`。
- 使用 `SET TRANSACTION READ ONLY` 和 `SET LOCAL statement_timeout`。
- 返回 `executed_sql`，便于确认最终执行 SQL。

## 当前项目与 Archery 对比

| 维度 | Archery | 当前项目 | 优化建议 |
| --- | --- | --- | --- |
| 查询入口 | 查询 API 统一调度检查、权限、改写、执行、日志 | `/api/sql/execute` 直接调用 `execute_sql` | 拆成 `query_check`、`filter_sql`、`query` 服务层 |
| SQL 解析 | 使用 `sqlparse` 去注释、切分和类型判断 | 已使用 `sqlparse`，但结构较轻 | 增加统一 `QueryCheckResult` |
| limit | 通过 `filter_sql` 改写 SQL | 已追加顶层 `LIMIT max_rows + 1` | 对已有大 LIMIT 做下调，保留 offset/fetch 语义 |
| 权限 | `query_priv_check` 控制用户可查范围和 limit | 暂无用户级 SQL 权限 | 增加实例级只读/写入权限和最大行数上限 |
| 超时 | 定时 kill 数据库连接 | `statement_timeout` | 增加取消按钮和后端 PID/任务 ID |
| 结果处理 | 支持脱敏、日志、耗时 | 只返回结果和实际 SQL | 增加 QueryLog、耗时、错误历史 |
| 审计 | 持久化查询记录 | 暂无 | 增加 SQL 执行日志表 |
| 前端 | Ace 编辑器、格式化、结果表格 | Ant Design TextArea | 可升级 Monaco/Ace、历史、格式化 |
| 多数据库 | 引擎抽象 | PostgreSQL 专用 | 保持 PostgreSQL 专用即可，但保留阶段边界 |

## 建议优化路线

### P0：查询安全与可控性

1. 抽出 `SqlQueryService`：
   - `query_check(sql) -> QueryCheckResult`
   - `filter_sql(sql, max_rows) -> FilteredSql`
   - `query(payload, filtered_sql) -> SqlExecutionResult`

2. 完善 SQL 检查：
   - 使用 `sqlparse.format(sql, strip_comments=True)` 去注释。
   - 拒绝空语句和多语句。
   - 明确只读语句白名单。
   - 对写入模式保留更严格确认。

3. 改进 limit 规则：
   - 无顶层 limit 时追加 `LIMIT max_rows + 1`。
   - 已有顶层 limit 且大于 `max_rows + 1` 时下调。
   - 对 `EXPLAIN`、`SHOW` 不追加 limit。
   - 对 `FETCH FIRST n ROWS ONLY` 做识别，必要时下调。

4. 增加取消能力：
   - 执行前获取 `pg_backend_pid()`。
   - 前端展示“取消执行”按钮。
   - 后端提供 `/api/sql/{query_id}/cancel`，调用 `pg_cancel_backend(pid)` 或 `conn.cancel()`。

### P1：日志、历史与诊断

1. 新增 `sql_query_logs` 表：
   - 实例 ID、SQL 原文、实际执行 SQL、只读模式、最大行数、状态、错误、耗时、返回行数、开始/结束时间。

2. 前端增加查询历史：
   - 最近执行记录。
   - 点击恢复 SQL。
   - 展示耗时、行数、状态。

3. 增加执行计划预览：
   - 对 `SELECT/WITH` 支持 `EXPLAIN (FORMAT JSON)`。
   - 用于执行前判断是否可能全表扫描或大排序。

### P2：编辑体验和结果能力

1. 使用 Monaco 或 Ace：
   - SQL 高亮。
   - 快捷键执行。
   - 格式化 SQL。

2. 结果表格增强：
   - 大字段折叠。
   - NULL 和二进制值显示优化。
   - CSV 导出。

3. 查询模板：
   - 当前库、当前用户、表结构、序列、复制状态等常用 SQL。

### P3：平台化能力

1. 实例级 SQL 权限：
   - 是否允许写入。
   - 最大返回行数。
   - statement timeout。
   - 禁止访问的 schema/table。

2. 数据脱敏：
   - 针对邮箱、手机号、密钥字段做展示脱敏。

3. 后台异步查询：
   - 长查询转后台任务。
   - 前端轮询或 SSE 展示状态。
   - 支持结果分页或下载。

## 推荐近期落地方案

当前项目是 PostgreSQL 手动迁移助手，不需要完整复制 Archery 的多数据库平台。但 SQL 编辑器已经进入“会直接触碰数据库”的能力范围，建议按以下顺序优化：

1. **先做查询服务分层和日志**：让 SQL 检查、改写、执行、记录有清晰边界。
2. **再做取消执行**：解决“执行中一直转”的真实痛点。
3. **随后做 limit 下调和 EXPLAIN 预检查**：减少误执行大查询。
4. **最后增强前端编辑器体验**：Monaco/Ace、历史、格式化、导出。

这样既吸收 Archery 的成熟流程，又不会把当前 MVP 拖成一个完整 SQL 审核平台。

## 参考链接

- [Archery GitHub 仓库](https://github.com/hhyo/Archery)
- [Archery README](https://raw.githubusercontent.com/hhyo/Archery/master/README.md)
- [Archery 查询入口 sql/query.py](https://raw.githubusercontent.com/hhyo/Archery/master/sql/query.py)
- [Archery 通用引擎接口 sql/engines/__init__.py](https://github.com/hhyo/Archery/blob/master/sql/engines/__init__.py)
- [Archery MySQL 引擎 sql/engines/mysql.py](https://github.com/hhyo/Archery/blob/master/sql/engines/mysql.py)
- [Archery Releases](https://github.com/hhyo/Archery/releases)

<style>
.archery-flow {
  align-items: center;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 20px 0 28px;
}

.flow-node {
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-border);
  border-radius: 8px;
  color: var(--vp-c-text-1);
  font-weight: 600;
  line-height: 1.45;
  max-width: 520px;
  padding: 12px 16px;
  text-align: center;
  width: min(100%, 520px);
}

.flow-node span {
  color: var(--vp-c-text-2);
  font-size: 13px;
  font-weight: 400;
}

.flow-node.highlight {
  border-color: var(--vp-c-brand-1);
  box-shadow: 0 0 0 1px var(--vp-c-brand-soft);
}

.flow-node.danger {
  border-color: var(--vp-c-danger-1);
}

.flow-arrow {
  color: var(--vp-c-text-3);
  font-size: 20px;
  line-height: 1;
}

.flow-branch {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  max-width: 720px;
  width: 100%;
}

.flow-branch .flow-node {
  max-width: none;
  width: 100%;
}

@media (max-width: 640px) {
  .flow-branch {
    grid-template-columns: 1fr;
  }
}
</style>
