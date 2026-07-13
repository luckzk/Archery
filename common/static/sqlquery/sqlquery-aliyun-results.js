// Split from sqlquery-aliyun.js. Loaded by sqlquery.html.
function restoreAliyunResultPanes() {
    var tabContent = document.getElementById('tab-content');
    if (!tabContent) {
        return;
    }
    $('#aliyun-result-panes > [id^="sqlquery_result"]').each(function () {
        $(this).removeClass('aliyun-workbench-pane aliyun-result-pane active in');
        tabContent.appendChild(this);
    });
    $('#aliyun-result-tabs').empty();
}

function isAliyunSqlqueryTheme() {
    return $('#sqlquery-theme-root').hasClass('is-aliyun');
}

function ensureAliyunWorkbenchShell() {
    var workbenchTabs = $('.aliyun-workbench-tabs');
    var mysqlTab = $('[data-aliyun-workbench-tab="mysql"]');
    if (mysqlTab.length) {
        mysqlTab.text('SQL资产');
    }
    if (workbenchTabs.length && mysqlTab.length && !$('[data-aliyun-workbench-tab="results"]').length) {
        $('<button/>', {
            type: 'button',
            class: 'aliyun-workbench-tab aliyun-result-home-tab',
            'data-aliyun-workbench-tab': 'results',
            role: 'tab',
            'aria-selected': 'false',
            text: '执行结果'
        }).insertAfter(mysqlTab);
    }
    if (!$('#aliyun-workbench-results-empty').length && $('#aliyun-result-panes').length) {
        $('<div/>', {
            id: 'aliyun-workbench-results-empty',
            class: 'aliyun-workbench-pane aliyun-result-empty-pane'
        }).append(
            $('<div/>', {class: 'aliyun-result-empty-state'}).append(
                $('<strong/>', {text: '暂无执行结果'}),
                $('<span/>', {text: '执行 SQL 后，结果会在这里以独立标签展示。'})
            )
        ).insertBefore('#aliyun-result-panes');
    }
    $('#aliyun-knowledge-modal')
        .addClass('aliyun-console-modal')
        .find('.modal-title')
        .removeClass('text-danger');
    $('#aliyun-knowledge-save')
        .removeClass('btn-danger')
        .addClass('btn-primary');
    $('#aliyun-knowledge-modal .modal-footer .btn-info[data-dismiss="modal"]')
        .addClass('aliyun-modal-cancel');
}

function showAliyunWorkbenchPane(target) {
    ensureAliyunWorkbenchShell();
    $('.aliyun-workbench-tab').removeClass('active');
    $('.aliyun-workbench-pane').removeClass('active');
    if (target === 'mysql') {
        $('[data-aliyun-workbench-tab="mysql"]').addClass('active');
        $('#aliyun-workbench-mysql').addClass('active');
        syncAliyunTabsA11y();
        return;
    }
    if (target === 'results') {
        $('[data-aliyun-workbench-tab="results"]').addClass('active');
        var firstResultTab = $('#aliyun-result-tabs [data-aliyun-result-tab]').first();
        if (firstResultTab.length) {
            showAliyunWorkbenchPane(firstResultTab.data('aliyun-result-tab'));
        } else {
            $('#aliyun-workbench-results-empty').addClass('active');
            syncAliyunTabsA11y();
        }
        return;
    }
    $('[data-aliyun-workbench-tab="results"]').addClass('active');
    $('[data-aliyun-result-tab="' + target + '"]').addClass('active');
    $('#' + target).addClass('active');
    syncAliyunTabsA11y();
}

function showAliyunMysqlPane(target, options) {
    options = options || {};
    target = ['knowledge', 'favorite', 'history'].indexOf(target) !== -1 ? target : 'knowledge';
    showAliyunWorkbenchPane('mysql');
    $('.aliyun-mysql-tab').removeClass('active');
    $('[data-aliyun-mysql-tab="' + target + '"]').addClass('active');
    $('.aliyun-mysql-pane').removeClass('active');
    $('#aliyun-mysql-' + target).addClass('active');
    if (options.persist) {
        saveSqlqueryPreference({mysql_tab: target});
    } else {
        updateSqlqueryPreferenceAttrs({mysql_tab: target});
    }
    if (target === 'history') {
        $("#filter-star").selectpicker('val', '');
        $("#filter-alias").selectpicker('val', '');
        get_querylog();
    }
}

function closeAliyunResultPane(resultId) {
    var wasActive = $('#' + resultId).hasClass('active');
    var tabNumber = resultId.replace('sqlquery_result', '');
    $('[data-aliyun-result-tab="' + resultId + '"]').remove();
    $('#' + resultId).remove();
    $('#execute_result_tab' + tabNumber).remove();

    if (wasActive) {
        var lastResultTab = $('#aliyun-result-tabs [data-aliyun-result-tab]').last();
        if (lastResultTab.length) {
            showAliyunWorkbenchPane(lastResultTab.data('aliyun-result-tab'));
        } else {
            showAliyunWorkbenchPane('results');
        }
    }
}

function closeAllAliyunResultPanes() {
    $('#aliyun-result-tabs [data-aliyun-result-tab]').each(function () {
        closeAliyunResultPane($(this).data('aliyun-result-tab'));
    });
    showAliyunWorkbenchPane('results');
}

function copyActiveAliyunResultSql() {
    var activePane = $('#aliyun-result-panes .aliyun-result-pane.active');
    if (!activePane.length) {
        showAliyunNotice('当前没有激活的执行结果', 'error');
        return;
    }
    var tabNumber = activePane.attr('id').replace('sqlquery_result', '');
    var cacheSql = $('#execute_result_tab' + tabNumber + ' input').attr('sql_cache') || activePane.find('p:first').text();
    copyTextToClipboard(cacheSql, '已复制SQL');
}

function getActiveAliyunResultPane() {
    return $('#aliyun-result-panes .aliyun-result-pane.active');
}

function getActiveAliyunResultTable(pane) {
    pane = pane && pane.length ? pane : getActiveAliyunResultPane();
    return pane.find('table[id^="query_result"]').first();
}

function searchActiveAliyunResult(input) {
    var table = getActiveAliyunResultTable($(input).closest('.aliyun-result-pane'));
    if (table.length && table.data('bootstrap.table')) {
        table.bootstrapTable('resetSearch', $(input).val());
    }
}

function buildAliyunResultExportName(tabNumber) {
    var now = new Date();
    var pad = function (value) {
        return String(value).padStart(2, '0');
    };
    return 'sqlquery_result_' + tabNumber + '_' +
        now.getFullYear() +
        pad(now.getMonth() + 1) +
        pad(now.getDate()) + '_' +
        pad(now.getHours()) +
        pad(now.getMinutes()) +
        pad(now.getSeconds());
}

function getAliyunResultExportName(tabNumber) {
    var pane = $('#sqlquery_result' + tabNumber);
    var inputValue = $.trim(pane.find('.aliyun-result-export-name-input').val() || '');
    return inputValue || pane.data('export-name') || buildAliyunResultExportName(tabNumber);
}

function getAliyunResultColumns(table) {
    if (!table.length || !table.data('bootstrap.table')) {
        return [];
    }
    return (table.bootstrapTable('getOptions').columns || [[]])[0] || [];
}

function openActiveAliyunColumnSettings(button) {
    var pane = $(button).closest('.aliyun-result-pane');
    var table = getActiveAliyunResultTable(pane);
    var columns = getAliyunResultColumns(table).filter(function (column) {
        return column && column.field !== undefined && column.title !== undefined;
    });
    if (!columns.length) {
        showAliyunNotice('当前结果没有列设置', 'error');
        return;
    }
    var panel = pane.find('.aliyun-column-settings-panel');
    if (panel.length) {
        panel.toggleClass('is-open');
        return;
    }
    panel = $('<div/>', {class: 'aliyun-column-settings-panel is-open'}).append(
        $('<div/>', {class: 'aliyun-column-settings-head'}).append(
            $('<strong/>', {text: '列设置'}),
            $('<button/>', {type: 'button', class: 'aliyun-column-settings-close', text: '×'})
        ),
        $('<div/>', {class: 'aliyun-column-settings-list'})
    );
    columns.forEach(function (column) {
        $('<label/>', {class: 'aliyun-column-settings-item'}).append(
            $('<input/>', {
                type: 'checkbox',
                checked: column.visible !== false,
                'data-field': column.field
            }),
            $('<span/>', {text: column.title})
        ).appendTo(panel.find('.aliyun-column-settings-list'));
    });
    pane.children('.aliyun-result-summary').after(panel);
}

function toggleAliyunResultColumn(input) {
    var pane = $(input).closest('.aliyun-result-pane');
    var table = getActiveAliyunResultTable(pane);
    var field = $(input).data('field');
    if (!table.length || !table.data('bootstrap.table')) {
        return;
    }
    if ($(input).is(':checked')) {
        table.bootstrapTable('showColumn', field);
    } else {
        table.bootstrapTable('hideColumn', field);
    }
}

function copyActiveAliyunColumnNames(button) {
    var pane = $(button).closest('.aliyun-result-pane');
    var names = [];
    pane.find('.fixed-table-header th:visible .th-inner').each(function () {
        var text = $.trim($(this).clone().children().remove().end().text());
        if (text && text !== '+') {
            names.push(text);
        }
    });
    copyTextToClipboard(names.join('\t'), '已复制列名');
}

function copyActiveAliyunCell(button) {
    var pane = $(button).closest('.aliyun-result-pane');
    var cell = pane.find('.aliyun-result-cell-active').first();
    if (!cell.length) {
        showAliyunNotice('请先点击一个结果单元格', 'error');
        return;
    }
    copyTextToClipboard($.trim(cell.text()), '已复制单元格');
}

function copyActiveAliyunRow(button) {
    var pane = $(button).closest('.aliyun-result-pane');
    var cell = pane.find('.aliyun-result-cell-active').first();
    var row = cell.length ? cell.closest('tr') : pane.find('.fixed-table-body tbody tr:visible').first();
    var values = [];
    row.children('td:visible').each(function () {
        if (!$(this).hasClass('detail')) {
            values.push($.trim($(this).text()));
        }
    });
    copyTextToClipboard(values.join('\t'), '已复制行');
}

function parseAliyunPgExplainJson(result, cacheSql) {
    if (!result || !result.rows || !result.rows.length || !cacheSql) {
        return null;
    }
    if (currentDbTypeForDictionary() !== 'pgsql' || !/^\s*explain\b/i.test(cacheSql) || !/format\s+json/i.test(cacheSql)) {
        return null;
    }
    var firstCell = $.isArray(result.rows[0]) ? result.rows[0][0] : result.rows[0];
    if (!firstCell) {
        return null;
    }
    try {
        var payload = typeof firstCell === 'string' ? JSON.parse(firstCell) : firstCell;
        if ($.isArray(payload) && payload.length && payload[0].Plan) {
            return payload[0];
        }
        if (payload && payload.Plan) {
            return payload;
        }
    } catch (e) {
        return null;
    }
    return null;
}

function flattenAliyunPgPlan(plan, depth, rows) {
    if (!plan) {
        return rows;
    }
    rows.push({
        depth: depth,
        nodeType: plan['Node Type'] || '',
        relation: plan['Relation Name'] || plan['Alias'] || '',
        startupCost: plan['Startup Cost'],
        totalCost: plan['Total Cost'],
        planRows: plan['Plan Rows'],
        planWidth: plan['Plan Width'],
        actualStartupTime: plan['Actual Startup Time'],
        actualTotalTime: plan['Actual Total Time'],
        actualRows: plan['Actual Rows'],
        actualLoops: plan['Actual Loops'],
        indexCond: plan['Index Cond'] || '',
        filter: plan.Filter || '',
        joinFilter: plan['Join Filter'] || '',
        sharedHitBlocks: plan['Shared Hit Blocks'],
        sharedReadBlocks: plan['Shared Read Blocks'],
        walRecords: plan['WAL Records'],
        strategy: plan.Strategy || plan['Join Type'] || ''
    });
    (plan.Plans || []).forEach(function (child) {
        flattenAliyunPgPlan(child, depth + 1, rows);
    });
    return rows;
}

function renderAliyunPgPlanNode(plan) {
    var children = plan.Plans || [];
    var meta = [
        plan['Relation Name'] ? 'relation: ' + plan['Relation Name'] : '',
        plan['Index Name'] ? 'index: ' + plan['Index Name'] : '',
        plan['Startup Cost'] !== undefined ? 'cost: ' + plan['Startup Cost'] + '..' + plan['Total Cost'] : '',
        plan['Plan Rows'] !== undefined ? 'rows: ' + plan['Plan Rows'] : '',
        plan['Actual Total Time'] !== undefined ? 'actual: ' + plan['Actual Total Time'] + 'ms' : '',
        plan['Actual Rows'] !== undefined ? 'actual rows: ' + plan['Actual Rows'] : ''
    ].filter(Boolean).join(' | ');
    var node = $('<li/>', {class: 'aliyun-plan-node'}).append(
        $('<div/>', {class: 'aliyun-plan-node-line'}).append(
            $('<span/>', {class: 'aliyun-plan-node-type', text: plan['Node Type'] || 'Plan'}),
            $('<span/>', {class: 'aliyun-plan-node-meta', text: meta})
        )
    );
    var details = [
        plan['Index Cond'] ? ['Index Cond', plan['Index Cond']] : null,
        plan.Filter ? ['Filter', plan.Filter] : null,
        plan['Join Filter'] ? ['Join Filter', plan['Join Filter']] : null,
        plan['Hash Cond'] ? ['Hash Cond', plan['Hash Cond']] : null,
        plan['Recheck Cond'] ? ['Recheck Cond', plan['Recheck Cond']] : null
    ].filter(Boolean);
    if (details.length) {
        var detailList = $('<ul/>', {class: 'aliyun-plan-node-details'});
        details.forEach(function (item) {
            detailList.append(
                $('<li/>').append(
                    $('<strong/>', {text: item[0] + ': '}),
                    $('<span/>', {text: item[1]})
                )
            );
        });
        node.append(detailList);
    }
    if (children.length) {
        var childList = $('<ul/>', {class: 'aliyun-plan-tree'});
        children.forEach(function (child) {
            childList.append(renderAliyunPgPlanNode(child));
        });
        node.append(childList);
    }
    return node;
}

function renderAliyunPgExplainPlan(panel, result, cacheSql) {
    panel.children('.aliyun-pg-explain').remove();
    var explain = parseAliyunPgExplainJson(result, cacheSql);
    if (!explain || !explain.Plan) {
        return;
    }
    var hasAnalyze = explain.Plan['Actual Total Time'] !== undefined || explain['Execution Time'] !== undefined;
    var rows = flattenAliyunPgPlan(explain.Plan, 0, []);
    var table = $('<table/>', {class: 'table table-condensed aliyun-plan-table'}).append(
        $('<thead/>').append(
            $('<tr/>').append(
                $('<th/>', {text: '节点'}),
                $('<th/>', {text: '对象'}),
                $('<th/>', {text: '成本'}),
                $('<th/>', {text: '估算行数'}),
                $('<th/>', {text: '实际耗时'}),
                $('<th/>', {text: '实际行数'}),
                $('<th/>', {text: 'Buffers/WAL'}),
                $('<th/>', {text: '条件'})
            )
        ),
        $('<tbody/>')
    );
    rows.forEach(function (row) {
        table.find('tbody').append(
            $('<tr/>').append(
                $('<td/>', {text: Array(row.depth + 1).join('  ') + row.nodeType}),
                $('<td/>', {text: row.relation || row.strategy}),
                $('<td/>', {text: row.startupCost !== undefined ? row.startupCost + '..' + row.totalCost : ''}),
                $('<td/>', {text: row.planRows !== undefined ? row.planRows : ''}),
                $('<td/>', {text: row.actualTotalTime !== undefined ? row.actualStartupTime + '..' + row.actualTotalTime + ' ms' : ''}),
                $('<td/>', {text: row.actualRows !== undefined ? row.actualRows + ' x ' + row.actualLoops : ''}),
                $('<td/>', {text: [
                    row.sharedHitBlocks !== undefined ? 'hit ' + row.sharedHitBlocks : '',
                    row.sharedReadBlocks !== undefined ? 'read ' + row.sharedReadBlocks : '',
                    row.walRecords !== undefined ? 'wal ' + row.walRecords : ''
                ].filter(Boolean).join(' | ')}),
                $('<td/>', {text: [row.indexCond, row.filter, row.joinFilter].filter(Boolean).join(' | ')})
            )
        );
    });
    var explainPanel = $('<div/>', {class: 'aliyun-pg-explain'}).append(
        $('<div/>', {class: 'aliyun-pg-explain-head'}).append(
            $('<strong/>', {text: 'PgSQL 执行计划'}),
            $('<span/>', {text: hasAnalyze ? 'FORMAT JSON / ANALYZE 已执行' : 'FORMAT JSON / 未启用 ANALYZE'}),
            explain['Planning Time'] !== undefined ? $('<span/>', {text: 'Planning: ' + explain['Planning Time'] + ' ms'}) : '',
            explain['Execution Time'] !== undefined ? $('<span/>', {text: 'Execution: ' + explain['Execution Time'] + ' ms'}) : ''
        ),
        $('<div/>', {class: 'aliyun-pg-explain-body'}).append(
            $('<div/>', {class: 'aliyun-pg-explain-tree'}).append(
                $('<ul/>', {class: 'aliyun-plan-tree'}).append(renderAliyunPgPlanNode(explain.Plan))
            ),
            $('<div/>', {class: 'aliyun-pg-explain-table'}).append(table)
        )
    );
    panel.children('.aliyun-result-summary').after(explainPanel);
}

function getAliyunResultColumnIndex(result, columnName) {
    return (result.column_list || []).indexOf(columnName);
}

function getAliyunResultValue(row, result, columnName) {
    if (!row) {
        return '';
    }
    if ($.isArray(row)) {
        var index = getAliyunResultColumnIndex(result, columnName);
        return index === -1 ? '' : row[index];
    }
    return row[columnName] === undefined || row[columnName] === null ? '' : row[columnName];
}

function parseAliyunPgWaitSeconds(duration) {
    var text = String(duration || '');
    var dayMatch = text.match(/(\d+)\s+days?/);
    var timeMatch = text.match(/(\d{1,2}):(\d{2}):(\d{2})/);
    if (!timeMatch) {
        return 0;
    }
    return (dayMatch ? parseInt(dayMatch[1], 10) * 86400 : 0) +
        parseInt(timeMatch[1], 10) * 3600 +
        parseInt(timeMatch[2], 10) * 60 +
        parseInt(timeMatch[3], 10);
}

function isAliyunPgBlockingResult(result) {
    var columns = result && result.column_list ? result.column_list : [];
    return columns.indexOf('waiting_pid') !== -1 && columns.indexOf('blocking_pid') !== -1;
}

function renderAliyunPgBlockingChain(panel, result) {
    panel.children('.aliyun-pg-lock-chain').remove();
    if (!isAliyunPgBlockingResult(result)) {
        return;
    }
    var rows = (result.rows || []).filter(function (row) {
        return !!getAliyunResultValue(row, result, 'waiting_pid') && !!getAliyunResultValue(row, result, 'blocking_pid');
    });
    var chainPanel = $('<div/>', {class: 'aliyun-pg-lock-chain'}).append(
        $('<div/>', {class: 'aliyun-pg-lock-chain-head'}).append(
            $('<strong/>', {text: 'PgSQL 阻塞链'}),
            $('<span/>', {text: rows.length ? rows.length + ' 条等待关系' : '当前没有锁等待'})
        ),
        $('<div/>', {class: 'aliyun-pg-lock-chain-body'})
    );
    var body = chainPanel.find('.aliyun-pg-lock-chain-body');
    if (!rows.length) {
        body.append(
            $('<div/>', {class: 'aliyun-pg-lock-empty', text: '当前没有锁等待'})
        );
        panel.children('.aliyun-result-summary').after(chainPanel);
        return;
    }
    rows.forEach(function (row) {
        var waitingPid = getAliyunResultValue(row, result, 'waiting_pid');
        var blockingPid = getAliyunResultValue(row, result, 'blocking_pid');
        var duration = getAliyunResultValue(row, result, 'waiting_duration');
        var waitingUser = getAliyunResultValue(row, result, 'waiting_user');
        var blockingUser = getAliyunResultValue(row, result, 'blocking_user');
        var relationName = getAliyunResultValue(row, result, 'relation_name');
        var lockType = getAliyunResultValue(row, result, 'lock_type');
        var waitEvent = [getAliyunResultValue(row, result, 'wait_event_type'), getAliyunResultValue(row, result, 'wait_event')].filter(Boolean).join(' / ');
        var waitingQuery = getAliyunResultValue(row, result, 'waiting_query');
        var blockingQuery = getAliyunResultValue(row, result, 'blocking_query');
        var cancelSql = getAliyunResultValue(row, result, 'cancel_sql');
        var terminateSql = getAliyunResultValue(row, result, 'terminate_sql');
        var item = $('<div/>', {
            class: 'aliyun-pg-lock-item' + (parseAliyunPgWaitSeconds(duration) >= 30 ? ' is-long-wait' : '')
        }).append(
            $('<div/>', {class: 'aliyun-pg-lock-flow'}).append(
                $('<span/>', {class: 'aliyun-pg-lock-pid waiting', text: '等待 ' + waitingPid}),
                $('<i/>', {class: 'fa fa-long-arrow-right'}),
                $('<span/>', {class: 'aliyun-pg-lock-pid blocking', text: '阻塞 ' + blockingPid}),
                $('<span/>', {class: 'aliyun-pg-lock-duration', text: duration || '-'})
            ),
            $('<div/>', {class: 'aliyun-pg-lock-meta'}).append(
                $('<span/>', {text: '对象：' + (relationName || '-')}),
                $('<span/>', {text: '锁：' + (lockType || '-')}),
                $('<span/>', {text: '等待事件：' + (waitEvent || '-')}),
                $('<span/>', {text: '用户：' + (waitingUser || '-') + ' / ' + (blockingUser || '-')})
            ),
            $('<div/>', {class: 'aliyun-pg-lock-actions'}).append(
                $('<button/>', {
                    type: 'button',
                    class: 'btn btn-xs btn-default aliyun-copy-lock-sql',
                    'data-lock-sql': cancelSql,
                    text: '复制取消SQL'
                }),
                $('<button/>', {
                    type: 'button',
                    class: 'btn btn-xs btn-default aliyun-copy-lock-sql',
                    'data-lock-sql': terminateSql,
                    text: '复制终止SQL'
                })
            ),
            $('<div/>', {class: 'aliyun-pg-lock-sql'}).append(
                $('<div/>').append(
                    $('<label/>', {text: '等待 SQL'}),
                    $('<pre/>', {text: waitingQuery || '-'})
                ),
                $('<div/>').append(
                    $('<label/>', {text: '阻塞 SQL'}),
                    $('<pre/>', {text: blockingQuery || '-'})
                )
            )
        );
        body.append(item);
    });
    panel.children('.aliyun-result-summary').after(chainPanel);
}

function renderAliyunResultTable(result, tabNumber, options) {
    options = options || {};
    result = result || {};
    var rows = result.rows || [];
    var columns = [];
    (result.column_list || []).forEach(function (column, index) {
        columns.push({
            field: index,
            title: column,
            sortable: true,
            cellStyle: function () {
                return {css: {}};
            },
            formatter: function (value) {
                if (value instanceof Array || value instanceof Object) {
                    return JSON.stringify(value);
                }
                return value;
            }
        });
    });
    if (!columns.length) {
        columns = [{
            field: 'message',
            title: '信息'
        }];
        rows = [{message: options.emptyMessage || '没有数据'}];
    } else if (!rows.length && options.emptyMessage) {
        rows = [columns.map(function (column, index) {
            return index === 0 ? options.emptyMessage : '';
        })];
    }
    $('#query_result' + tabNumber).bootstrapTable('destroy').bootstrapTable({
        escape: true,
        data: rows,
        columns: columns,
        undefinedText: '(null)',
        showColumns: true,
        clickToSelect: true,
        striped: true,
        pagination: true,
        pageSize: 30,
        pageList: [30, 50, 100, 500, 1000],
        search: true,
        strictSearch: false,
        locale: 'zh-CN'
    });
}

function openAliyunResultTab(title, cacheSql) {
    tab_add(title);
    var tabNumber = sessionStorage.getItem('tab_num');
    $('#execute_result_tab' + tabNumber + ' input').attr('sql_cache', cacheSql || title || '');
    return tabNumber;
}

function loadAliyunPgBlockingChain() {
    if (currentDbTypeForDictionary() !== 'pgsql') {
        showAliyunNotice('锁诊断仅支持 PgSQL 实例', 'error');
        return;
    }
    if (!$('#instance_name').val() || !$('#db_name').val()) {
        showAliyunNotice('请先选择实例和库', 'error');
        return;
    }
    var tabNumber = openAliyunResultTab('锁诊断', 'PgSQL 锁等待 / 阻塞链诊断');
    var loadingResult = {
        full_sql: 'PgSQL 锁等待 / 阻塞链诊断',
        column_list: ['message'],
        rows: [['加载中...']],
        query_time: '-',
        mask_time: '-'
    };
    renderAliyunResultTable(loadingResult, tabNumber);
    syncAliyunResultPane(loadingResult, tabNumber, true);
    $.ajax({
        type: 'post',
        url: '/query/pgsql_blocking_chain/',
        dataType: 'json',
        data: {
            instance_name: $('#instance_name').val(),
            db_name: $('#db_name').val()
        },
        success: function (data) {
            if (data.status !== 0) {
                var errorResult = {
                    full_sql: 'PgSQL 锁等待 / 阻塞链诊断',
                    column_list: ['error'],
                    rows: [[data.msg || '加载失败']],
                    query_time: '-',
                    mask_time: '-'
                };
                renderAliyunResultTable(errorResult, tabNumber);
                syncAliyunResultPane(errorResult, tabNumber, true);
                showAliyunNotice(data.msg || '锁诊断加载失败', 'error');
                return;
            }
            var result = data.data || {};
            renderAliyunResultTable(result, tabNumber, {emptyMessage: '当前没有锁等待'});
            syncAliyunResultPane(result, tabNumber, true);
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            var errorResult = {
                full_sql: 'PgSQL 锁等待 / 阻塞链诊断',
                column_list: ['error'],
                rows: [[errorThrown || '加载失败']],
                query_time: '-',
                mask_time: '-'
            };
            renderAliyunResultTable(errorResult, tabNumber);
            syncAliyunResultPane(errorResult, tabNumber, true);
            showAliyunNotice(errorThrown || '锁诊断加载失败', 'error');
        }
    });
}

function syncAliyunResultPane(result, tabNumber, hasColumns) {
    if (!isAliyunSqlqueryTheme()) {
        return;
    }
    if ($('#aliyun-workbench-mysql').hasClass('active') && $('#aliyun-mysql-history').hasClass('active')) {
        get_querylog();
    }
    var resultId = 'sqlquery_result' + tabNumber;
    var panel = $('#' + resultId);
    if (panel.length) {
        var resultTabSelector = '[data-aliyun-result-tab="' + resultId + '"]';
        if (!$(resultTabSelector).length) {
            $('<button/>', {
                type: 'button',
                class: 'aliyun-workbench-tab aliyun-result-tab',
                'data-aliyun-result-tab': resultId,
                role: 'tab',
                'aria-selected': 'false',
                'aria-controls': resultId
            }).append(
                $('<span/>', {text: '执行结果' + tabNumber}),
                $('<span/>', {
                    class: 'aliyun-result-tab-close',
                    title: '关闭',
                    'aria-label': '关闭'
                })
            ).appendTo('#aliyun-result-tabs');
        }
        result = result || {};
        var queryTime = result.query_time !== undefined && result.query_time !== '' && result.query_time !== '-' ? result.query_time + ' sec' : '-';
        var maskTime = result.mask_time !== undefined && result.mask_time !== '' && result.mask_time !== '-' ? result.mask_time + ' sec' : '-';
        var rows = hasColumns && result.rows ? result.rows.length : '-';
        var cacheSql = $('#execute_result_tab' + tabNumber + ' input').attr('sql_cache') || panel.find('p:first').text();
        var exportName = panel.data('export-name') || buildAliyunResultExportName(tabNumber);
        var summarySql = cacheSql || '当前执行结果';
        panel.data('export-name', exportName);
        panel.children('.aliyun-result-summary').remove();
        panel.children('.aliyun-column-settings-panel').remove();
        panel.prepend(
            '<div class="aliyun-result-summary">' +
            '<div class="aliyun-result-summary-main">' +
            '<span class="aliyun-result-metric">返回行数 <strong>' + rows + '</strong></span>' +
            '<span class="aliyun-result-metric">执行耗时 <strong>' + queryTime + '</strong></span>' +
            '<span class="aliyun-result-metric">脱敏耗时 <strong>' + maskTime + '</strong></span>' +
            '</div>' +
            '<div class="aliyun-result-summary-tools">' +
            '<span class="aliyun-result-search"><i class="fa fa-search" aria-hidden="true"></i><input type="text" class="aliyun-result-search-input" placeholder="搜索当前结果" aria-label="搜索当前结果"></span>' +
            '<button type="button" class="btn btn-xs btn-default aliyun-result-columns" aria-label="打开列设置">列设置</button>' +
            '<div class="aliyun-result-more dropdown">' +
            '<button type="button" class="btn btn-xs btn-default dropdown-toggle aliyun-result-more-toggle" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">更多 <span class="caret"></span></button>' +
            '<ul class="dropdown-menu dropdown-menu-right aliyun-result-more-menu">' +
            '<li><button type="button" class="aliyun-result-menu-action aliyun-copy-result-sql" aria-label="复制当前结果SQL">复制SQL</button></li>' +
            '<li><button type="button" class="aliyun-result-menu-action aliyun-copy-result-columns" aria-label="复制当前结果列名">复制列名</button></li>' +
            '<li><button type="button" class="aliyun-result-menu-action aliyun-copy-result-cell" aria-label="复制已选单元格">复制单元格</button></li>' +
            '<li><button type="button" class="aliyun-result-menu-action aliyun-copy-result-row" aria-label="复制已选行">复制行</button></li>' +
            '<li role="separator" class="divider"></li>' +
            '<li><button type="button" class="aliyun-result-menu-action aliyun-close-all-results" aria-label="关闭全部执行结果">关闭全部结果</button></li>' +
            '</ul>' +
            '</div>' +
            '</div>' +
            '<div class="aliyun-result-summary-sql">' +
            '<span class="aliyun-result-sql-label">SQL</span>' +
            '<span class="aliyun-result-sql" title="' + escapeHtml(summarySql) + '">' + escapeHtml(summarySql) + '</span>' +
            '<span class="aliyun-result-export-name"><span>导出名</span><input type="text" class="aliyun-result-export-name-input" value="' + escapeHtml(exportName) + '"></span>' +
            '</div>' +
            '</div>'
        );
        renderAliyunPgBlockingChain(panel, result);
        renderAliyunPgExplainPlan(panel, result, cacheSql);
        panel.addClass('aliyun-workbench-pane aliyun-result-pane');
        $('#aliyun-result-panes').append(panel);
        showAliyunWorkbenchPane(resultId);
    }
}
