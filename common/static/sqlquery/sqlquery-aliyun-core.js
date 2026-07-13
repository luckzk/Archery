// Split from sqlquery-aliyun.js. Loaded by sqlquery.html.
const sqlqueryThemeSlots = {
    instance: null,
    db: null,
    schema: null,
    table: null,
    limit: null,
    locator: null,
    actions: null,
    editor: null,
    queryLogToolbar: null,
    queryLogPane: null,
    resultsPanel: null,
    aiGenerateDesc: null,
    aiGenerateButton: null,
    aiHelpButton: null,
    exportButton: null,
    originalMarkers: {},
    originalButtonLabels: {},
};
var aliyunFavoriteSearchTimer = null;
var aliyunFavoriteRows = [];
var aliyunFavoriteSort = {
    field: '',
    direction: 'asc'
};
var aliyunKnowledgeRows = [];
var aliyunKnowledgeSearchTimer = null;
var aliyunOpenTableNodes = {};
var aliyunKnowledgeFilterSyncing = false;
var sqlqueryPreferenceSaveTimer = null;
var aliyunConfirmLastFocus = null;

function normalizeSqlqueryPreferenceChoice(value, choices, defaultValue) {
    return choices.indexOf(value) !== -1 ? value : defaultValue;
}

function getSqlqueryPreference() {
    var root = $('#sqlquery-theme-root');
    return {
        theme: normalizeSqlqueryPreferenceChoice(root.attr('data-sqlquery-theme'), ['archery', 'aliyun'], 'archery'),
        resource_tab: normalizeSqlqueryPreferenceChoice(root.attr('data-sqlquery-resource-tab'), ['table', 'program'], 'table'),
        mysql_tab: normalizeSqlqueryPreferenceChoice(root.attr('data-sqlquery-mysql-tab'), ['knowledge', 'favorite', 'history'], 'knowledge')
    };
}

function updateSqlqueryPreferenceAttrs(preference) {
    var root = $('#sqlquery-theme-root');
    if (preference.theme) {
        root.attr('data-sqlquery-theme', preference.theme);
    }
    if (preference.resource_tab) {
        root.attr('data-sqlquery-resource-tab', preference.resource_tab);
    }
    if (preference.mysql_tab) {
        root.attr('data-sqlquery-mysql-tab', preference.mysql_tab);
    }
}

function saveSqlqueryPreference(changes) {
    var currentPreference = getSqlqueryPreference();
    var preference = Object.assign(getSqlqueryPreference(), changes || {});
    preference.theme = normalizeSqlqueryPreferenceChoice(preference.theme, ['archery', 'aliyun'], 'archery');
    preference.resource_tab = normalizeSqlqueryPreferenceChoice(preference.resource_tab, ['table', 'program'], 'table');
    preference.mysql_tab = normalizeSqlqueryPreferenceChoice(preference.mysql_tab, ['knowledge', 'favorite', 'history'], 'knowledge');
    if (
        currentPreference.theme === preference.theme &&
        currentPreference.resource_tab === preference.resource_tab &&
        currentPreference.mysql_tab === preference.mysql_tab
    ) {
        return;
    }
    updateSqlqueryPreferenceAttrs(preference);
    clearTimeout(sqlqueryPreferenceSaveTimer);
    sqlqueryPreferenceSaveTimer = setTimeout(function () {
        postSqlqueryPreference(preference);
    }, 120);
}

function postSqlqueryPreference(preference) {
    $.ajax({
        type: 'post',
        url: '/query/preference/',
        dataType: 'json',
        data: preference,
        success: function (data) {
            if (data.status !== 0) {
                showAliyunNotice(data.msg || '界面偏好保存失败', 'error');
                return;
            }
            updateSqlqueryPreferenceAttrs(data.data || preference);
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            showAliyunNotice(errorThrown || '界面偏好保存失败', 'error');
        }
    });
}

function rememberOriginalPosition(name, node) {
    if (!node || sqlqueryThemeSlots.originalMarkers[name]) {
        return;
    }
    var marker = document.createComment('sqlquery-original-' + name);
    node.parentNode.insertBefore(marker, node);
    sqlqueryThemeSlots.originalMarkers[name] = marker;
}

function rememberSqlqueryThemeSlots() {
    if (sqlqueryThemeSlots.instance) {
        return;
    }
    sqlqueryThemeSlots.instance = document.getElementById('div-instance_name');
    sqlqueryThemeSlots.db = document.getElementById('div-db_name');
    sqlqueryThemeSlots.schema = document.getElementById('div-schema_name');
    sqlqueryThemeSlots.table = document.getElementById('div-table_name');
    sqlqueryThemeSlots.limit = document.getElementById('div-limit_num');
    sqlqueryThemeSlots.locator = document.getElementById('div-table-locator');
    sqlqueryThemeSlots.actions = document.getElementById('div-query-actions');
    sqlqueryThemeSlots.editor = document.getElementById('sql_content_editor');
    sqlqueryThemeSlots.queryLogToolbar = document.getElementById('query-log-toolbar');
    sqlqueryThemeSlots.queryLogPane = document.getElementById('sql_log_result');
    sqlqueryThemeSlots.resultsPanel = document.querySelector('.sqlquery-original-view > .row.clearfix > .col-md-12.column');
    sqlqueryThemeSlots.aiGenerateDesc = document.getElementById('generateDesc');
    sqlqueryThemeSlots.aiGenerateButton = document.getElementById('btn-generatesql');
    sqlqueryThemeSlots.aiHelpButton = document.getElementById('btn-openaiTooltip');
    sqlqueryThemeSlots.exportButton = document.getElementById('div-exportsubmit');
    ['btn-sqlquery', 'btn-format', 'btn-explain', 'btn-generatesql'].forEach(function (id) {
        var button = document.getElementById(id);
        if (button) {
            sqlqueryThemeSlots.originalButtonLabels[id] = button.value || button.textContent;
        }
    });

    Object.keys(sqlqueryThemeSlots).forEach(function (name) {
        if (name !== 'originalMarkers' && name !== 'originalButtonLabels') {
            rememberOriginalPosition(name, sqlqueryThemeSlots[name]);
        }
    });
}

function moveNodeToSlot(node, slotId) {
    var slot = document.getElementById(slotId);
    if (node && slot) {
        slot.appendChild(node);
    }
}

function restoreNodeToOriginal(name, node) {
    var marker = sqlqueryThemeSlots.originalMarkers[name];
    if (node && marker && marker.parentNode) {
        marker.parentNode.insertBefore(node, marker.nextSibling);
    }
}

function resizeSqlqueryEditor() {
    if (typeof editor !== 'undefined' && editor && typeof editor.resize === 'function') {
        setTimeout(function () {
            editor.resize(true);
        }, 60);
    }
}

function refreshSqlquerySelectpickers() {
    if ($.fn.selectpicker) {
        setTimeout(function () {
            $('.selectpicker').selectpicker('refresh');
        }, 40);
    }
}

function escapeHtml(value) {
    return $('<div/>').text(value === null || value === undefined ? '' : value).html()
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function setInputButtonLabel(id, label) {
    var button = document.getElementById(id);
    if (button) {
        if ('value' in button) {
            button.value = label;
        } else {
            button.textContent = label;
        }
    }
}

function setAliyunButtonLabels() {
    setInputButtonLabel('btn-sqlquery', '执行(F8)');
    setInputButtonLabel('btn-format', '格式化(F10)');
    setInputButtonLabel('btn-explain', '执行计划(F9)');
    setInputButtonLabel('btn-generatesql', 'Copilot');
}

function restoreButtonLabels() {
    Object.keys(sqlqueryThemeSlots.originalButtonLabels).forEach(function (id) {
        setInputButtonLabel(id, sqlqueryThemeSlots.originalButtonLabels[id]);
    });
}

function showAliyunNotice(message, type) {
    var notice = $('#aliyun-page-notice');
    if (!notice.length) {
        notice = $('<div/>', {
            id: 'aliyun-page-notice',
            class: 'aliyun-page-notice',
            role: type === 'error' ? 'alert' : 'status',
            'aria-live': type === 'error' ? 'assertive' : 'polite'
        }).appendTo('body');
    }
    notice.attr({
        role: type === 'error' ? 'alert' : 'status',
        'aria-live': type === 'error' ? 'assertive' : 'polite'
    });
    notice.removeClass('is-error is-success')
        .addClass(type === 'error' ? 'is-error' : 'is-success')
        .text(message || '')
        .stop(true, true)
        .fadeIn(120)
        .delay(1600)
        .fadeOut(180);
}

function showAliyunConfirm(message, onConfirm) {
    var confirmBox = $('#aliyun-confirm');
    if (!confirmBox.length) {
        if (typeof onConfirm === 'function') {
            onConfirm();
        }
        return;
    }
    aliyunConfirmLastFocus = document.activeElement;
    confirmBox.find('.aliyun-confirm-message').text(message || '');
    confirmBox.show();
    confirmBox.find('.aliyun-confirm-ok').focus();
    confirmBox.off('keydown.aliyunConfirm').on('keydown.aliyunConfirm', function (event) {
        if (event.key === 'Escape') {
            confirmBox.hide();
            confirmBox.off('keydown.aliyunConfirm');
            if (aliyunConfirmLastFocus && aliyunConfirmLastFocus.focus) {
                aliyunConfirmLastFocus.focus();
            }
        }
    });
    confirmBox.find('.aliyun-confirm-cancel').off('click').on('click', function () {
        confirmBox.hide();
        confirmBox.off('keydown.aliyunConfirm');
        if (aliyunConfirmLastFocus && aliyunConfirmLastFocus.focus) {
            aliyunConfirmLastFocus.focus();
        }
    });
    confirmBox.find('.aliyun-confirm-ok').off('click').on('click', function () {
        confirmBox.hide();
        confirmBox.off('keydown.aliyunConfirm');
        if (typeof onConfirm === 'function') {
            onConfirm();
        }
    });
}

function copyTextToClipboard(text, successMessage) {
    if (!text) {
        showAliyunNotice('没有可复制的内容', 'error');
        return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
            showAliyunNotice(successMessage || '已复制');
        }, function () {
            showAliyunNotice('复制失败', 'error');
        });
        return;
    }
    var textArea = $('<textarea/>').val(text).appendTo('body');
    textArea[0].select();
    document.execCommand('copy');
    textArea.remove();
    showAliyunNotice(successMessage || '已复制');
}

function ensureAliyunTopbarShell() {
    var topbar = $('.aliyun-topbar');
    if (!topbar.length || topbar.children('.aliyun-env-tag').length) {
        return;
    }
    $('<span/>', {class: 'aliyun-env-tag', text: '生产'}).prependTo(topbar);
}

function syncAliyunEngineTag() {
    ensureAliyunTopbarShell();
    var engine = $('#instance_name :selected').parent().attr('label');
    var tag = $('#aliyun-engine-tag');
    if (engine) {
        tag
            .attr('data-engine', engine)
            .attr('title', engine + ' 数据库引擎')
            .attr('aria-label', engine + ' 数据库引擎')
            .addClass('has-engine')
            .text('')
            .show();
    } else {
        tag
            .removeAttr('data-engine title aria-label')
            .removeClass('has-engine')
            .text('')
            .hide();
    }
}

function syncAliyunSchemaGroup() {
    $('#aliyun-schema-group').toggleClass('has-schema', $('#div-schema_name').is(':visible'));
}

function syncAliyunPgTools() {
    var isPg = currentDbTypeForDictionary() === 'pgsql';
    $('#aliyun-pg-locks').toggle(isPg);
    $('#aliyun-pg-analyze-wrap').toggle(isPg);
}

function syncAliyunTabsA11y() {
    $('.aliyun-resource-tab').each(function () {
        $(this).attr('aria-selected', $(this).hasClass('active') ? 'true' : 'false');
    });
    $('.aliyun-workbench-tab').each(function () {
        $(this).attr('aria-selected', $(this).hasClass('active') ? 'true' : 'false');
    });
    $('.aliyun-mysql-tab').each(function () {
        $(this).attr('aria-selected', $(this).hasClass('active') ? 'true' : 'false');
    });
}

function fillEditorFromKnowledge(row) {
    var sql = $(row).data('sql') || $(row).find('.sql-text').text();
    if (sql) {
        editor.setValue(sql);
        editor.clearSelection();
        resizeSqlqueryEditor();
    }
}

function insertTextIntoEditor(text) {
    if (!text) {
        return;
    }
    editor.insert(text);
    editor.focus();
    resizeSqlqueryEditor();
}

function replaceEditorSql(sql) {
    if (!sql) {
        return;
    }
    editor.setValue(sql);
    editor.clearSelection();
    resizeSqlqueryEditor();
}

function quoteSqlIdentifier(name) {
    var engine = $('#instance_name :selected').parent().attr('label');
    if (!name) {
        return '';
    }
    if (engine === 'MySQL' || engine === 'Doris') {
        return '`' + String(name).replace(/`/g, '``') + '`';
    }
    if (engine === 'PgSQL' || engine === 'Oracle' || engine === 'MsSQL') {
        return '"' + String(name).replace(/"/g, '""') + '"';
    }
    return name;
}

function qualifiedTableName(tableName) {
    var schemaName = $('#schema_name').val();
    if (schemaName && $('#div-schema_name').is(':visible')) {
        return quoteSqlIdentifier(schemaName) + '.' + quoteSqlIdentifier(tableName);
    }
    return quoteSqlIdentifier(tableName);
}

function qualifiedProgramObjectName(objectName) {
    var schemaName = $('#schema_name').val();
    if (schemaName && $('#div-schema_name').is(':visible')) {
        return quoteSqlIdentifier(schemaName) + '.' + quoteSqlIdentifier(objectName);
    }
    return quoteSqlIdentifier(objectName);
}

function buildSelectSqlForTable(tableName) {
    var limitNum = $('#limit_num').val() || 100;
    var engine = $('#instance_name :selected').parent().attr('label');
    var sql = 'select * from ' + qualifiedTableName(tableName);
    if (engine === 'Oracle') {
        return sql + ' where rownum <= ' + limitNum + ';';
    }
    if (engine === 'MsSQL') {
        return 'select top ' + limitNum + ' * from ' + qualifiedTableName(tableName) + ';';
    }
    return sql + ' limit ' + limitNum + ';';
}

function generateSelectSqlFromTableNode(tableNode) {
    replaceEditorSql(buildSelectSqlForTable(tableNode.data('table-name')));
}

function getCurrentEditorSql() {
    var selectSqlContent = editor.session.getTextRange(editor.getSelectionRange());
    return $.trim(selectSqlContent || editor.getValue());
}
