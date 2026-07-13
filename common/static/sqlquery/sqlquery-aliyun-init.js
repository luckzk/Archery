// Split from sqlquery-aliyun.js. Loaded by sqlquery.html.
function applySqlqueryTheme(theme, options) {
    options = options || {};
    rememberSqlqueryThemeSlots();
    var root = document.getElementById('sqlquery-theme-root');
    var normalizedTheme = theme === 'aliyun' ? 'aliyun' : 'archery';

    if (normalizedTheme === 'aliyun') {
        root.classList.add('is-aliyun');
        moveNodeToSlot(sqlqueryThemeSlots.instance, 'aliyun-instance-slot');
        moveNodeToSlot(sqlqueryThemeSlots.db, 'aliyun-db-slot');
        moveNodeToSlot(sqlqueryThemeSlots.schema, 'aliyun-schema-slot');
        moveNodeToSlot(sqlqueryThemeSlots.actions, 'aliyun-query-actions-slot');
        moveNodeToSlot(sqlqueryThemeSlots.aiGenerateDesc, 'aliyun-ai-slot');
        moveNodeToSlot(sqlqueryThemeSlots.aiGenerateButton, 'aliyun-ai-slot');
        moveNodeToSlot(sqlqueryThemeSlots.aiHelpButton, 'aliyun-ai-slot');
        moveNodeToSlot(sqlqueryThemeSlots.exportButton, 'aliyun-toolbar-extra');
        moveNodeToSlot(sqlqueryThemeSlots.editor, 'aliyun-editor-slot');
        moveNodeToSlot(sqlqueryThemeSlots.locator, 'aliyun-table-locator-slot');
        moveNodeToSlot(sqlqueryThemeSlots.table, 'aliyun-table-select-slot');
        moveNodeToSlot(sqlqueryThemeSlots.limit, 'aliyun-limit-slot');
        moveNodeToSlot(sqlqueryThemeSlots.queryLogToolbar, 'aliyun-mysql-history');
        moveNodeToSlot(sqlqueryThemeSlots.queryLogPane, 'aliyun-mysql-history');
        ensureAliyunWorkbenchShell();
        ensureAliyunResourceShell();
        setAliyunButtonLabels();
        syncAliyunEngineTag();
        syncAliyunSchemaGroup();
        syncAliyunPgTools();
        syncAliyunKnowledgeRows();
        syncAliyunTableObjects();
    } else {
        root.classList.remove('is-aliyun');
        restoreAliyunResultPanes();
        restoreNodeToOriginal('queryLogToolbar', sqlqueryThemeSlots.queryLogToolbar);
        restoreNodeToOriginal('queryLogPane', sqlqueryThemeSlots.queryLogPane);
        restoreNodeToOriginal('exportButton', sqlqueryThemeSlots.exportButton);
        restoreNodeToOriginal('aiGenerateDesc', sqlqueryThemeSlots.aiGenerateDesc);
        restoreNodeToOriginal('aiGenerateButton', sqlqueryThemeSlots.aiGenerateButton);
        restoreNodeToOriginal('aiHelpButton', sqlqueryThemeSlots.aiHelpButton);
        restoreNodeToOriginal('editor', sqlqueryThemeSlots.editor);
        restoreNodeToOriginal('locator', sqlqueryThemeSlots.locator);
        restoreNodeToOriginal('instance', sqlqueryThemeSlots.instance);
        restoreNodeToOriginal('db', sqlqueryThemeSlots.db);
        restoreNodeToOriginal('schema', sqlqueryThemeSlots.schema);
        restoreNodeToOriginal('table', sqlqueryThemeSlots.table);
        restoreNodeToOriginal('limit', sqlqueryThemeSlots.limit);
        restoreNodeToOriginal('actions', sqlqueryThemeSlots.actions);
        restoreButtonLabels();
    }

    $('button[data-sqlquery-theme]').removeClass('btn-primary').addClass('btn-default');
    $('button[data-sqlquery-theme="' + normalizedTheme + '"]').removeClass('btn-default').addClass('btn-primary');
    if (options.persist) {
        saveSqlqueryPreference({theme: normalizedTheme});
    } else {
        updateSqlqueryPreferenceAttrs({theme: normalizedTheme});
    }
    refreshSqlquerySelectpickers();
    resizeSqlqueryEditor();
}

function showAliyunResourcePane(target, options) {
    options = options || {};
    target = target === 'program' ? 'program' : 'table';
    ensureAliyunResourceShell();
    $('.aliyun-resource-tab').removeClass('active');
    $('[data-aliyun-resource-tab="' + target + '"]').addClass('active');
    $('.aliyun-resource-pane').removeClass('active');
    $('#aliyun-resource-' + target).addClass('active');
    syncAliyunTabsA11y();
    if (options.persist) {
        saveSqlqueryPreference({resource_tab: target});
    } else {
        updateSqlqueryPreferenceAttrs({resource_tab: target});
    }
}

$(function () {
    $('button[data-sqlquery-theme]').on('click', function () {
        applySqlqueryTheme($(this).data('sqlquery-theme'), {persist: true});
    });

    $('.aliyun-resource-panel').on('click', '[data-aliyun-resource-tab]', function () {
        showAliyunResourcePane($(this).data('aliyun-resource-tab'), {persist: true});
    });

    $('#aliyun-resource-refresh').on('click', function () {
        syncAliyunTableObjects({forceRefresh: true});
    });

    $('#aliyun-table-tree-search').on('input', function () {
        filterAliyunTableObjects();
    });

    $('#aliyun-program-resource-refresh').on('click', function () {
        refreshAliyunProgramObjects();
    });

    $('#aliyun-program-tree-search').on('input', function () {
        filterAliyunProgramObjects();
    });

    $('#aliyun-pg-locks').on('click', function () {
        loadAliyunPgBlockingChain();
    });

    $('#aliyun-table-object-list').on('click', '> .aliyun-table-node > .aliyun-tree-row', function (event) {
        event.stopPropagation();
        if ($(event.target).closest('.aliyun-tree-action').length) {
            return;
        }
        toggleAliyunTableNode($(this).closest('.aliyun-table-node'));
    });

    $('#aliyun-table-object-list').on('click', '.aliyun-table-select-sql', function (event) {
        event.stopPropagation();
        generateSelectSqlFromTableNode($(this).closest('.aliyun-table-node'));
    });

    $('#aliyun-table-object-list').on('click', '.aliyun-table-insert-name', function (event) {
        event.stopPropagation();
        insertTextIntoEditor(qualifiedTableName($(this).closest('.aliyun-table-node').data('table-name')));
    });

    $('#aliyun-table-object-list').on('click', '.aliyun-table-group > .aliyun-tree-row', function (event) {
        event.stopPropagation();
        if ($(event.target).closest('.aliyun-tree-action').length) {
            return;
        }
        var group = $(this).closest('.aliyun-table-group');
        loadAliyunTableGroup(group.closest('.aliyun-table-node'), group.data('resource-group'));
    });

    $('#aliyun-table-object-list').on('click', '.aliyun-table-group-refresh', function (event) {
        event.stopPropagation();
        var button = $(this);
        var group = button.closest('.aliyun-table-group');
        button.prop('disabled', true).addClass('is-loading');
        loadAliyunTableGroup(group.closest('.aliyun-table-node'), group.data('resource-group'), {
            forceRefresh: true,
            complete: function () {
                button.prop('disabled', false).removeClass('is-loading');
            }
        });
    });

    $('#aliyun-table-object-list').on('click', '.aliyun-resource-copy-detail', function (event) {
        event.stopPropagation();
        copyTextToClipboard($(this).closest('.aliyun-tree-row').data('resource-detail'), '已复制定义');
    });

    $('#aliyun-table-object-list').on('click', '[data-resource-name]', function (event) {
        event.stopPropagation();
        if ($(event.target).closest('.aliyun-tree-action').length) {
            return;
        }
        insertTextIntoEditor(quoteSqlIdentifier($(this).data('resource-name')));
    });

    $('#aliyun-program-object-list').on('click', '> .aliyun-program-group > .aliyun-tree-row', function (event) {
        event.stopPropagation();
        if ($(event.target).closest('.aliyun-tree-action').length) {
            return;
        }
        loadAliyunProgramGroup($(this).closest('.aliyun-program-group'));
    });

    $('#aliyun-program-object-list').on('click', '.aliyun-program-object-row', function (event) {
        event.stopPropagation();
        if ($(event.target).closest('.aliyun-tree-action').length) {
            return;
        }
        loadAliyunProgramObjectDefinition($(this).closest('.aliyun-program-object'));
    });

    $('#aliyun-program-object-list').on('click', '.aliyun-program-show-definition', function (event) {
        event.stopPropagation();
        loadAliyunProgramObjectDefinition($(this).closest('.aliyun-program-object'));
    });

    $('#aliyun-program-object-list').on('click', '.aliyun-program-copy-definition', function (event) {
        event.stopPropagation();
        copyAliyunProgramDefinition($(this).closest('.aliyun-program-object'));
    });

    $('#aliyun-program-object-list').on('click', '.aliyun-program-refresh-definition', function (event) {
        event.stopPropagation();
        var button = $(this);
        button.prop('disabled', true).addClass('is-loading');
        loadAliyunProgramObjectDefinition($(this).closest('.aliyun-program-object'), {
            forceRefresh: true,
            complete: function () {
                button.prop('disabled', false).removeClass('is-loading');
            }
        });
    });

    $('#aliyun-program-object-list').on('click', '.aliyun-program-insert-name', function (event) {
        event.stopPropagation();
        insertAliyunProgramObjectName($(this).closest('.aliyun-program-object'));
    });

    $('#aliyun-result-panes').on('click', '.aliyun-copy-lock-sql', function (event) {
        event.stopPropagation();
        copyTextToClipboard($(this).data('lock-sql'), '已复制锁操作SQL');
    });

    $('#instance_name, #db_name, #schema_name').on('changed.bs.select change', function () {
        aliyunOpenTableNodes = {};
        if ($('#sqlquery-theme-root').hasClass('is-aliyun')) {
            setTimeout(syncAliyunTableObjects, 80);
        }
        syncAliyunPgTools();
        resetAliyunProgramObjects();
    });

    $('[data-aliyun-mysql-tab]').on('click', function () {
        var target = $(this).data('aliyun-mysql-tab');
        showAliyunMysqlPane(target, {persist: true});
        syncAliyunTabsA11y();
    });

    $('.aliyun-workbench-tabs').on('click', '[data-aliyun-workbench-tab="mysql"]', function () {
        showAliyunWorkbenchPane('mysql');
        syncAliyunTabsA11y();
    });

    $('.aliyun-workbench-tabs').on('click', '[data-aliyun-workbench-tab="results"]', function () {
        showAliyunWorkbenchPane('results');
        syncAliyunTabsA11y();
    });

    $('#aliyun-result-tabs').on('click', '[data-aliyun-result-tab]', function () {
        showAliyunWorkbenchPane($(this).data('aliyun-result-tab'));
        syncAliyunTabsA11y();
    });

    $('#aliyun-result-tabs').on('click', '.aliyun-result-tab-close', function (event) {
        event.stopPropagation();
        closeAliyunResultPane($(this).closest('[data-aliyun-result-tab]').data('aliyun-result-tab'));
    });

    $('#aliyun-result-panes').on('click', '.aliyun-copy-result-sql', function (event) {
        event.stopPropagation();
        copyActiveAliyunResultSql();
        $(this).closest('.dropdown').removeClass('open');
    });

    $('#aliyun-result-panes').on('input', '.aliyun-result-search-input', function () {
        searchActiveAliyunResult(this);
    });

    $('#aliyun-result-panes').on('click', '.aliyun-result-columns', function () {
        openActiveAliyunColumnSettings(this);
    });

    $('#aliyun-result-panes').on('click', '.aliyun-column-settings-close', function () {
        $(this).closest('.aliyun-column-settings-panel').removeClass('is-open');
    });

    $('#aliyun-result-panes').on('change', '.aliyun-column-settings-item input', function () {
        toggleAliyunResultColumn(this);
    });

    $('#aliyun-result-panes').on('input', '.aliyun-result-export-name-input', function () {
        $(this).closest('.aliyun-result-pane').data('export-name', $.trim($(this).val()));
    });

    $('#aliyun-result-panes').on('click', '.aliyun-copy-result-columns', function (event) {
        event.stopPropagation();
        copyActiveAliyunColumnNames(this);
        $(this).closest('.dropdown').removeClass('open');
    });

    $('#aliyun-result-panes').on('click', '.aliyun-copy-result-cell', function (event) {
        event.stopPropagation();
        copyActiveAliyunCell(this);
        $(this).closest('.dropdown').removeClass('open');
    });

    $('#aliyun-result-panes').on('click', '.aliyun-copy-result-row', function (event) {
        event.stopPropagation();
        copyActiveAliyunRow(this);
        $(this).closest('.dropdown').removeClass('open');
    });

    $('#aliyun-result-panes').on('click', '.fixed-table-body td', function () {
        $(this).closest('.aliyun-result-pane').find('.aliyun-result-cell-active').removeClass('aliyun-result-cell-active');
        $(this).addClass('aliyun-result-cell-active');
    });

    $('#aliyun-result-panes').on('click', '.aliyun-close-all-results', function (event) {
        event.stopPropagation();
        $(this).closest('.dropdown').removeClass('open');
        closeAllAliyunResultPanes();
    });

    $('.aliyun-knowledge-table').on('dblclick', '.aliyun-knowledge-row .sql-text', function () {
        fillEditorFromKnowledge($(this).closest('.aliyun-knowledge-row'));
    });

    $('.aliyun-knowledge-table').on('click', '.aliyun-knowledge-fill', function (event) {
        event.stopPropagation();
        fillEditorFromKnowledge($(this).closest('.aliyun-knowledge-row'));
    });

    $('.aliyun-knowledge-table').on('click', '.aliyun-knowledge-edit', function (event) {
        event.stopPropagation();
        openAliyunKnowledgeModalForItem($(this).closest('.aliyun-knowledge-row'), 'edit');
    });

    $('.aliyun-knowledge-table').on('click', '.aliyun-knowledge-copy', function (event) {
        event.stopPropagation();
        openAliyunKnowledgeModalForItem($(this).closest('.aliyun-knowledge-row'), 'copy');
    });

    $('.aliyun-knowledge-table').on('click', '.aliyun-knowledge-delete', function (event) {
        event.stopPropagation();
        deleteAliyunKnowledge($(this).closest('.aliyun-knowledge-row'));
    });

    $('#aliyun-knowledge-add').on('click', function () {
        openAliyunKnowledgeModal();
    });

    $('#aliyun-knowledge-save').on('click', function () {
        saveAliyunKnowledgeFromModal();
    });

    $('#aliyun-knowledge-search-input').on('input', function () {
        clearTimeout(aliyunKnowledgeSearchTimer);
        aliyunKnowledgeSearchTimer = setTimeout(function () {
            refreshAliyunKnowledgeRows();
        }, 250);
    });

    $('#aliyun-knowledge-engine-filter, #aliyun-knowledge-scene-filter').on('changed.bs.select change', function () {
        if (aliyunKnowledgeFilterSyncing) {
            return;
        }
        refreshAliyunKnowledgeRows();
    });

    $('#aliyun-favorite-table').on('dblclick', '.aliyun-favorite-row .sql-text', function () {
        fillEditorFromFavorite($(this).closest('.aliyun-favorite-row'));
    });

    $('#aliyun-favorite-table').on('click', '.aliyun-favorite-fill', function (event) {
        event.stopPropagation();
        fillEditorFromFavorite($(this).closest('.aliyun-favorite-row'));
    });

    $('#aliyun-favorite-table').on('click', '.aliyun-favorite-edit', function (event) {
        event.stopPropagation();
        editFavoriteAlias($(this).closest('.aliyun-favorite-row'));
    });

    $('#aliyun-favorite-table').on('click', '.aliyun-favorite-delete', function (event) {
        event.stopPropagation();
        deleteFavorite($(this).closest('.aliyun-favorite-row'));
    });

    $('#aliyun-favorite-table').on('click', '[data-favorite-sort]', function () {
        sortFavoriteRows($(this).data('favorite-sort'));
    });

    $('#aliyun-favorite-search-input').on('input', function () {
        var keyword = $(this).val();
        clearTimeout(aliyunFavoriteSearchTimer);
        aliyunFavoriteSearchTimer = setTimeout(function () {
            refreshAliyunFavorites(keyword);
        }, 250);
    });

    $('#aliyun-favorite-add').on('click', function () {
        addCurrentSqlToFavorite();
    });

    $('#favorite').on('hidden.bs.modal', function () {
        resetFavoriteModalTitle();
    });

    refreshAliyunKnowledgeRows();
    refreshAliyunFavorites();
    var preference = getSqlqueryPreference();
    applySqlqueryTheme(preference.theme, {persist: false});
    showAliyunResourcePane(preference.resource_tab, {persist: false});
    showAliyunMysqlPane(preference.mysql_tab, {persist: false});
    syncAliyunTabsA11y();
});
