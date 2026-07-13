# -*- coding: UTF-8 -*-
import argparse
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def login(page, base_url, username, password):
    page.goto(f"{base_url}/login/", wait_until="domcontentloaded")
    username_input = page.locator(
        "input[name='username'], #username, input[type='text']"
    ).first
    password_input = page.locator(
        "input[name='password'], #password, input[type='password']"
    ).first
    username_input.fill(username)
    password_input.fill(password)
    page.locator(
        "button[type='submit'], input[type='submit'], button:has-text('登录')"
    ).first.click()
    page.wait_for_load_state("networkidle")


def assert_visible(page, selector, label):
    locator = page.locator(selector).first
    locator.wait_for(state="visible", timeout=8000)
    print(f"ok - {label}")
    return locator


def run_smoke(base_url, username, password, headless):
    dialogs = []
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1440, "height": 920})
        page = context.new_page()
        page.on("dialog", lambda dialog: dialogs.append(dialog.message))
        page.on("pageerror", lambda error: errors.append(str(error)))

        login(page, base_url, username, password)
        page.goto(f"{base_url}/sqlquery/", wait_until="networkidle")

        page.locator("button[data-sqlquery-theme='aliyun']").click()
        assert_visible(page, "#sqlquery-theme-root.is-aliyun", "Aliyun主题生效")
        assert_visible(page, "#aliyun-instance-slot #instance_name", "实例选择移动到顶部")
        page.locator("[data-aliyun-resource-tab='table']").click()
        assert_visible(page, "#aliyun-resource-table.active", "右侧表资源栏可见")
        assert_visible(page, "#aliyun-workbench-mysql.active", "我的SQL面板可见")
        local_theme = page.evaluate("() => window.localStorage.getItem('sqlquery_theme')")
        if local_theme is not None:
            raise AssertionError("主题仍写入 localStorage")
        print("ok - 主题不写浏览器本地缓存")

        page.locator("[data-aliyun-mysql-tab='favorite']").click()
        assert_visible(page, "#aliyun-mysql-favorite.active", "收藏面板可见")
        page.evaluate("() => { editor.setValue('select 1 as smoke_id;'); editor.clearSelection(); }")
        page.locator("#aliyun-favorite-add").click()
        assert_visible(page, "#favorite.in, #favorite[style*='display: block']", "收藏弹窗可见")
        assert_visible(page, "#favorite_sql_content", "收藏SQL可编辑")
        page.locator("#favorite .btn-info").click()

        page.locator("[data-aliyun-mysql-tab='knowledge']").click()
        page.locator("#aliyun-knowledge-add").click()
        assert_visible(
            page,
            "#aliyun-knowledge-modal.in, #aliyun-knowledge-modal[style*='display: block']",
            "知识库弹窗可见",
        )
        assert_visible(page, "#aliyun-knowledge-engines", "知识库引擎选择可见")
        engine_count = page.locator("#aliyun-knowledge-engines option").count()
        if engine_count < 6:
            raise AssertionError("知识库引擎选项过少，可能未从后端渲染")
        if page.locator("#aliyun-knowledge-engines option[value='PgSQL']").count() != 1:
            raise AssertionError("知识库引擎缺少 PgSQL")
        print("ok - 知识库引擎选项已渲染")
        page.locator("#aliyun-knowledge-modal .btn-info").click()
        page.locator("#aliyun-knowledge-modal.in").wait_for(state="detached", timeout=8000)

        page.evaluate(
            """
            () => {
              $('#instance_name').append('<option value="smoke_instance">smoke_instance</option>').val('smoke_instance');
              $('#db_name').append('<option value="smoke_db">smoke_db</option>').val('smoke_db');
              const previousAjax = $.ajax;
              window.__smokeTableAjax = previousAjax;
              $.ajax = function (options) {
                if (options.url === '/instance/instance_resource/' && options.data && options.data.resource_type === 'table') {
                  window.__smokeTableForceRefresh = !!options.data._refresh;
                  setTimeout(() => {
                    options.success({status: 0, data: ['smoke_table', 'archive_table']});
                    if (options.complete) { options.complete(); }
                  }, 80);
                  return {abort: function () {}};
                }
                return previousAjax.apply($, arguments);
              };
              syncAliyunTableObjects();
            }
            """
        )
        assert_visible(
            page,
            "#aliyun-table-object-list .aliyun-table-node[data-table-name='smoke_table']",
            "表资源栏可直接刷新",
        )
        if page.locator("#table_name option[value='smoke_table']").count() != 1:
            raise AssertionError("表资源刷新后未同步原表选择框")
        print("ok - 表资源刷新同步选择框")
        page.locator("#aliyun-resource-refresh").click()
        page.locator("#aliyun-resource-refresh.is-loading").wait_for(timeout=8000)
        if page.locator("#aliyun-resource-refresh").evaluate("el => getComputedStyle(el).pointerEvents") != "none":
            raise AssertionError("表资源刷新时按钮未禁用")
        page.wait_for_function("() => !document.querySelector('#aliyun-resource-refresh').classList.contains('is-loading')")
        if page.evaluate("() => window.__smokeTableForceRefresh !== true"):
            raise AssertionError("表资源刷新未发送强制刷新标记")
        print("ok - 表资源刷新时按钮不可点击")
        page.locator("#aliyun-table-tree-search").fill("archive")
        assert_visible(
            page,
            "#aliyun-table-object-list .aliyun-table-node[data-table-name='archive_table']",
            "表资源搜索可用",
        )
        hidden_smoke_table = page.locator(
            "#aliyun-table-object-list .aliyun-table-node[data-table-name='smoke_table']"
        ).is_hidden()
        if not hidden_smoke_table:
            raise AssertionError("表资源搜索未隐藏不匹配项")
        print("ok - 表资源搜索能过滤")
        page.evaluate(
            """
            () => {
              const tableNode = document.querySelector('#aliyun-table-object-list .aliyun-table-node[data-table-name="archive_table"]');
              tableNode.classList.add('is-open');
              const indexGroup = tableNode.querySelector('[data-resource-group="index"]');
              indexGroup.classList.add('is-open');
              renderAliyunTableChildren(
                $(indexGroup),
                [['idx_archive_id', 'id', 'CREATE INDEX idx_archive_id ON archive_table (id)']],
                'index'
              );
            }
            """
        )
        index_row = page.locator(
            ".aliyun-table-node[data-table-name='archive_table'] "
            "[data-resource-group='index'] [data-resource-detail]"
        )
        index_row.hover()
        index_row.locator(".aliyun-resource-copy-detail").click()
        assert_visible(page, "#aliyun-page-notice", "索引定义复制提示可见")
        page.evaluate("() => { if (window.__smokeTableAjax) { $.ajax = window.__smokeTableAjax; } }")

        page.locator("[data-aliyun-resource-tab='program']").click()
        assert_visible(page, "#aliyun-resource-program.active", "可编程对象资源栏可见")
        page.wait_for_timeout(300)
        preference = page.evaluate(
            """
            async () => {
              const response = await fetch('/query/preference/');
              return await response.json();
            }
            """
        )
        if preference.get("status") != 0:
            raise AssertionError("界面偏好读取失败")
        preference_data = preference.get("data") or {}
        if preference_data.get("theme") != "aliyun":
            raise AssertionError("主题偏好未落库")
        if preference_data.get("resource_tab") != "program":
            raise AssertionError("资源页签偏好未落库")
        if preference_data.get("mysql_tab") != "knowledge":
            raise AssertionError("我的SQL页签偏好未落库")
        print("ok - 界面偏好已落库")
        page.evaluate(
            """
            () => {
              const list = document.querySelector('#aliyun-program-object-list .aliyun-program-group[data-program-type="function"] > .aliyun-tree-children');
              list.innerHTML = '';
              list.parentElement.classList.add('is-open');
              const item = document.createElement('li');
              item.className = 'aliyun-program-object';
              item.dataset.programObjectName = 'smoke_fn(integer, text)';
              item.dataset.programObjectType = 'function';
              item.dataset.programObjectId = '42';
              item.dataset.programObjectRawName = 'smoke_fn';
              item.dataset.programObjectArguments = 'integer, text';
              item.innerHTML = `
                <div class="aliyun-tree-row aliyun-program-object-row">
                  <span class="aliyun-tree-toggle"></span>
                  <i class="fa fa-code"></i>
                  <span class="aliyun-tree-label">smoke_fn(integer, text)</span>
                  <span class="aliyun-tree-actions">
                    <button type="button" class="aliyun-tree-action aliyun-program-show-definition"><i class="fa fa-file-code-o"></i></button>
                    <button type="button" class="aliyun-tree-action aliyun-program-insert-name"><i class="fa fa-i-cursor"></i></button>
                  </span>
                </div>
                <div class="aliyun-program-definition">
                  <div class="aliyun-program-definition-tools">
                    <button type="button" class="aliyun-tree-action aliyun-program-copy-definition"><i class="fa fa-copy"></i></button>
                    <button type="button" class="aliyun-tree-action aliyun-program-refresh-definition"><i class="fa fa-refresh"></i></button>
                  </div>
                  <pre class="aliyun-program-definition-code"></pre>
                </div>
              `;
              list.appendChild(item);
              const previousAjax = $.ajax;
              window.__smokePreviousAjax = previousAjax;
              window.__smokeFunctionObjectIdUsed = false;
              window.__smokeFunctionDefinitionRequests = 0;
              $.ajax = function (options) {
                if (options.url === '/data_dictionary/function_info/') {
                  if (!options.data || options.data.func_name !== 'smoke_fn' || String(options.data.object_id) !== '42') {
                    throw new Error('函数定义请求未使用 pg_proc oid');
                  }
                  window.__smokeFunctionObjectIdUsed = true;
                  window.__smokeFunctionDefinitionRequests += 1;
                  setTimeout(() => options.success({
                    status: 0,
                    data: {create_sql: [['CREATE FUNCTION smoke_fn(integer, text) RETURNS integer AS $$ SELECT 1 $$ LANGUAGE sql;']]}
                  }), 0);
                  return {abort: function () {}};
                }
                return previousAjax.apply($, arguments);
              };
            }
            """
        )
        page.locator("#aliyun-program-tree-search").fill("smoke")
        assert_visible(
            page,
            ".aliyun-program-object[data-program-object-id='42']",
            "可编程对象搜索可匹配",
        )
        page.locator("#aliyun-program-tree-search").fill("missing")
        if not page.locator(".aliyun-program-object[data-program-object-id='42']").is_hidden():
            raise AssertionError("可编程对象搜索未隐藏不匹配项")
        print("ok - 可编程对象搜索能过滤")
        page.locator("#aliyun-program-tree-search").fill("")
        page.evaluate("() => { editor.setValue(''); editor.clearSelection(); }")
        program_object = page.locator(".aliyun-program-object[data-program-object-id='42']")
        program_object.locator(".aliyun-program-object-row").hover()
        program_object.locator(".aliyun-program-insert-name").click()
        inserted_program_name = page.evaluate("() => editor.getValue()")
        if "smoke_fn(integer, text)" not in inserted_program_name:
            raise AssertionError("可编程对象名称未插入编辑器")
        print("ok - 可编程对象名称可插入")
        program_object.locator(".aliyun-program-object-row").hover()
        program_object.locator(".aliyun-program-show-definition").click()
        assert_visible(
            page,
            ".aliyun-program-object[data-program-object-id='42'] .aliyun-program-definition.is-open",
            "可编程对象定义面板可见",
        )
        page.locator(
            ".aliyun-program-object[data-program-object-id='42'] .aliyun-program-definition-code"
        ).wait_for(timeout=8000)
        definition_text = page.locator(
            ".aliyun-program-object[data-program-object-id='42'] .aliyun-program-definition-code"
        ).inner_text()
        if "CREATE FUNCTION smoke_fn" not in definition_text:
            raise AssertionError("可编程对象定义未展示")
        if page.evaluate("() => window.__smokeFunctionObjectIdUsed !== true"):
            raise AssertionError("可编程对象定义未带 object_id")
        print("ok - 可编程对象定义可展示")
        program_object.locator(".aliyun-program-copy-definition").click()
        assert_visible(page, "#aliyun-page-notice", "可编程对象定义复制提示可见")
        program_object.locator(".aliyun-program-refresh-definition").click()
        page.wait_for_function("() => window.__smokeFunctionDefinitionRequests >= 2")
        print("ok - 可编程对象定义可复制和刷新")
        page.evaluate("() => { if (window.__smokePreviousAjax) { $.ajax = window.__smokePreviousAjax; } }")

        page.evaluate(
            """
            () => {
              const tab = document.createElement('li');
              tab.id = 'execute_result_tab999';
              const input = document.createElement('input');
              input.setAttribute('sql_cache', 'select 1 as id, "name" as name');
              tab.appendChild(input);
              document.querySelector('#nav-tabs').appendChild(tab);

              const pane = document.createElement('div');
              pane.id = 'sqlquery_result999';
              pane.innerHTML = '<table id="query_result999"></table>';
              document.querySelector('#tab-content').appendChild(pane);
              $('#query_result999').bootstrapTable({
                data: [[1, 'alice']],
                columns: [
                  {field: 0, title: 'id', visible: true},
                  {field: 1, title: 'name', visible: true}
                ],
                showColumns: true,
                search: true
              });
              syncAliyunResultPane(
                {rows: [[1, 'alice']], query_time: 0.01, mask_time: 0},
                999,
                true
              );
            }
            """
        )
        assert_visible(page, "[data-aliyun-result-tab='sqlquery_result999']", "执行结果tab已创建")
        assert_visible(page, "#sqlquery_result999 .aliyun-result-search-input", "结果内搜索可见")
        assert_visible(page, "#sqlquery_result999 .aliyun-result-export-name-input", "导出名输入可见")

        page.locator("#sqlquery_result999 .aliyun-result-columns").click()
        assert_visible(page, "#sqlquery_result999 .aliyun-column-settings-panel.is-open", "列设置面板可见")
        page.locator("#sqlquery_result999 .aliyun-column-settings-item input").nth(1).uncheck()
        hidden = page.evaluate(
            "() => $('#query_result999').bootstrapTable('getOptions').columns[0][1].visible === false"
        )
        if not hidden:
            raise AssertionError("列隐藏状态未生效")
        print("ok - 列显示状态可切换")

        page.evaluate(
            """
            () => {
              const tab = document.createElement('li');
              tab.id = 'execute_result_tab998';
              const input = document.createElement('input');
              input.setAttribute('sql_cache', 'PgSQL 锁等待 / 阻塞链诊断');
              tab.appendChild(input);
              document.querySelector('#nav-tabs').appendChild(tab);

              const pane = document.createElement('div');
              pane.id = 'sqlquery_result998';
              pane.innerHTML = '<table id="query_result998"></table>';
              document.querySelector('#tab-content').appendChild(pane);
              const result = {
                full_sql: 'PgSQL 锁等待 / 阻塞链诊断',
                column_list: [
                  'waiting_pid', 'blocking_pid', 'waiting_user', 'blocking_user',
                  'waiting_duration', 'wait_event_type', 'wait_event', 'lock_type',
                  'relation_name', 'waiting_state', 'blocking_state',
                  'waiting_query', 'blocking_query', 'cancel_sql', 'terminate_sql'
                ],
                rows: [[
                  101, 202, 'app', 'admin', '00:00:35', 'Lock', 'transactionid',
                  'relation', 'public.orders', 'active', 'active',
                  'update orders set status = 1', 'select * from orders',
                  'SELECT pg_cancel_backend(202);', 'SELECT pg_terminate_backend(202);'
                ]],
                query_time: '-',
                mask_time: '-'
              };
              renderAliyunResultTable(result, 998);
              syncAliyunResultPane(result, 998, true);
            }
            """
        )
        assert_visible(page, "#sqlquery_result998 .aliyun-pg-lock-chain", "锁诊断阻塞链摘要可见")
        assert_visible(page, "#sqlquery_result998 .aliyun-pg-lock-item.is-long-wait", "长等待阻塞高亮可见")
        page.locator("#sqlquery_result998 .aliyun-copy-lock-sql").first.click()
        assert_visible(page, "#aliyun-page-notice", "锁操作SQL复制提示可见")

        if dialogs:
            raise AssertionError("检测到浏览器原生弹窗: " + "; ".join(dialogs))
        if errors:
            raise AssertionError("检测到页面脚本错误: " + "; ".join(errors))

        context.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser(description="SQLQuery Aliyun UI smoke test")
    parser.add_argument("--base-url", default="http://127.0.0.1:9123")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    try:
        run_smoke(args.base_url.rstrip("/"), args.username, args.password, not args.headed)
    except (AssertionError, PlaywrightTimeoutError) as exc:
        print(f"failed - {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
