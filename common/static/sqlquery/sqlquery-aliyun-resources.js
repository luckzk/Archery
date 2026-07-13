// Split from sqlquery-aliyun.js. Loaded by sqlquery.html.
function currentAliyunResourceParams(extra) {
    return Object.assign({
        instance_name: $('#instance_name').val(),
        db_name: $('#db_name').val(),
        schema_name: $('#schema_name').val()
    }, extra || {});
}

function normalizeAliyunResourceRow(row) {
    if ($.isArray(row)) {
        return row;
    }
    if (row && typeof row === 'object') {
        return Object.keys(row).map(function (key) {
            return row[key];
        });
    }
    return [row];
}

function flattenAliyunGroupedRows(rows) {
    if ($.isArray(rows)) {
        return rows;
    }
    if (rows && typeof rows === 'object') {
        return Object.keys(rows).sort().reduce(function (result, key) {
            var groupRows = rows[key];
            if ($.isArray(groupRows)) {
                return result.concat(groupRows);
            }
            return result;
        }, []);
    }
    return [];
}

function renderAliyunTreeMessage(list, className, text) {
    list.empty().append(
        $('<li/>', {class: className}).append(
            $('<div/>', {class: 'aliyun-tree-row'}).append(
                $('<span/>', {class: 'aliyun-tree-toggle'}),
                $('<i/>', {class: 'fa fa-info-circle'}),
                $('<span/>', {class: 'aliyun-tree-label', text: text})
            )
        )
    );
    syncAliyunResourceHelper();
}

function ensureAliyunResourceShell() {
    var panel = $('.aliyun-resource-panel');
    if (!panel.length) {
        return;
    }
    var header = panel.children('.aliyun-resource-header');
    if (header.length) {
        var tabs = header.children('.aliyun-resource-tabs');
        if (tabs.length) {
            tabs.insertBefore(header);
        }
        header.remove();
    }
    $('.aliyun-resource-search').each(function () {
        if (!$(this).children('.fa-search').length) {
            $('<i/>', {class: 'fa fa-search', 'aria-hidden': 'true'}).prependTo(this);
        }
    });
    $('#aliyun-resource-table > .text-muted')
        .addClass('aliyun-resource-helper');
    syncAliyunResourceHelper();
}

function syncAliyunResourceHelper() {
    var helper = $('#aliyun-resource-table > .aliyun-resource-helper');
    if (!helper.length) {
        return;
    }
    var list = $('#aliyun-table-object-list');
    var hasTable = list.children('.aliyun-table-node').length > 0;
    var hasVisibleTable = list.children('.aliyun-table-node:visible').length > 0;
    var hasState = list.children('.aliyun-tree-empty, .aliyun-tree-error, .aliyun-tree-loading').length > 0;
    var hasKeyword = $.trim($('#aliyun-table-tree-search').val() || '') !== '';
    helper.toggleClass('is-visible', !hasTable || hasState || (hasKeyword && !hasVisibleTable));
}

function setAliyunResourceRefreshState(buttonSelector, loading) {
    var button = $(buttonSelector);
    if (!button.length) {
        return;
    }
    button.toggleClass('is-loading', !!loading)
        .attr('aria-busy', loading ? 'true' : 'false')
        .prop('disabled', !!loading)
        .css('pointer-events', loading ? 'none' : '');
}

function aliyunRefreshToken(forceRefresh) {
    return forceRefresh ? Date.now() : undefined;
}

function aliyunTableGroupConfig(type) {
    return {
        overview: {
            label: '概要',
            apiResourceType: 'overview',
            icon: 'fa fa-info-circle',
            insertable: false
        },
        column: {
            label: '列',
            apiResourceType: 'column_detail',
            icon: 'fa fa-list-ul',
            insertable: true
        },
        index: {
            label: '索引',
            apiResourceType: 'index',
            icon: 'fa fa-key',
            insertable: true
        },
        constraint: {
            label: '约束',
            apiResourceType: 'constraint',
            icon: 'fa fa-shield',
            insertable: true
        },
        partition: {
            label: '分区',
            apiResourceType: 'partition',
            icon: 'fa fa-sitemap',
            insertable: true
        }
    }[type] || {
        label: type,
        apiResourceType: type,
        icon: 'fa fa-list-ul',
        insertable: false
    };
}

function createAliyunTableGroup(type) {
    var config = aliyunTableGroupConfig(type);
    return $('<li/>', {class: 'aliyun-table-group', 'data-resource-group': type}).append(
        $('<div/>', {class: 'aliyun-tree-row'}).append(
            $('<span/>', {class: 'aliyun-tree-toggle', text: '+'}),
            $('<i/>', {class: config.icon}),
            $('<span/>', {class: 'aliyun-tree-label', text: config.label}),
            $('<span/>', {class: 'aliyun-tree-actions'}).append(
                $('<button/>', {
                    type: 'button',
                    class: 'aliyun-tree-action aliyun-table-group-refresh',
                    title: '刷新分组',
                    'aria-label': '刷新' + config.label
                }).append($('<i/>', {class: 'fa fa-refresh'}))
            )
        ),
        $('<ul/>', {class: 'aliyun-tree-children'})
    );
}

function aliyunTableGroupTypes() {
    if (currentDbTypeForDictionary() === 'pgsql') {
        return ['overview', 'column', 'index', 'constraint', 'partition'];
    }
    return ['column', 'index'];
}

function collectAliyunTablesFromSelect() {
    var tables = [];
    $('#table_name option').each(function () {
        var tableName = $(this).attr('value') || $(this).text();
        if (!tableName || tableName === 'is-empty' || $(this).prop('disabled')) {
            return;
        }
        tables.push(tableName);
    });
    return tables;
}

function syncAliyunTableSelectOptions(tableNames) {
    var tableSelect = $('#table_name');
    if (!tableSelect.length || !$.isArray(tableNames)) {
        return;
    }
    var currentValue = tableSelect.val();
    tableSelect.empty();
    tableNames.forEach(function (tableName) {
        tableSelect.append($('<option/>', {value: tableName, text: tableName}));
    });
    if (currentValue && tableNames.indexOf(currentValue) !== -1) {
        tableSelect.selectpicker('val', currentValue);
    }
    tableSelect.selectpicker('refresh');
}

function renderAliyunTableObjects(tableNames) {
    ensureAliyunResourceShell();
    var list = $('#aliyun-table-object-list');
    if (!list.length) {
        return;
    }
    list.empty();
    var count = 0;
    tableNames.forEach(function (tableName) {
        if (!tableName) {
            return;
        }
        var tableNode = $('<li/>', {class: 'aliyun-table-node', 'data-table-name': tableName}).append(
            $('<div/>', {class: 'aliyun-tree-row'}).append(
                $('<span/>', {class: 'aliyun-tree-toggle', text: '+'}),
                $('<i/>', {class: 'fa fa-table'}),
                $('<span/>', {class: 'aliyun-tree-label', text: tableName, title: tableName}),
                $('<span/>', {class: 'aliyun-tree-actions'}).append(
                    $('<button/>', {type: 'button', class: 'aliyun-tree-action aliyun-table-select-sql', title: '生成查询SQL', 'aria-label': '为表 ' + tableName + ' 生成查询SQL'}).append($('<i/>', {class: 'fa fa-play'})),
                    $('<button/>', {type: 'button', class: 'aliyun-tree-action aliyun-table-insert-name', title: '插入表名', 'aria-label': '插入表名 ' + tableName}).append($('<i/>', {class: 'fa fa-i-cursor'}))
                )
            ),
            $('<ul/>', {class: 'aliyun-tree-children'}).append(
                aliyunTableGroupTypes().map(function (type) {
                    return createAliyunTableGroup(type);
                })
            )
        );
        list.append(tableNode);
        count += 1;
        if (aliyunOpenTableNodes[tableName]) {
            tableNode.addClass('is-open');
            loadAliyunTableGroup(tableNode, 'column');
        }
    });
    if (!count) {
        renderAliyunTreeMessage(list, 'aliyun-tree-empty', '请选择库后刷新对象列表');
    }
    filterAliyunTableObjects();
    syncAliyunResourceHelper();
}

function renderAliyunTableChildren(group, rows, type) {
    var children = group.children('.aliyun-tree-children');
    var config = aliyunTableGroupConfig(type);
    var label = config.label;
    children.empty();
    group.children('.aliyun-tree-row').find('> .aliyun-tree-label').text(label + '(' + rows.length + ')');
    if (!rows.length) {
        children.append(
            $('<li/>', {class: 'aliyun-tree-empty'}).append(
                $('<span/>', {class: 'aliyun-tree-label', text: '没有数据'})
            )
        );
        return;
    }
    rows.forEach(function (row) {
        var values = normalizeAliyunResourceRow(row);
        var name = values[0] || '';
        var meta = values[1] || '';
        var copyText = '';
        var title = '';
        if (type === 'overview') {
            name = values[0] || '';
            meta = [values[1], values[2], values[3], values[4], values[5]].filter(Boolean).join(' | ');
        } else if (type === 'index' && values.length > 2) {
            meta = values[1] || '';
            title = values[2] || '';
            copyText = title;
        } else if (type === 'constraint') {
            meta = values[1] || '';
            title = values[2] || '';
            copyText = title;
        } else if (type === 'partition') {
            name = values[1] || '';
            meta = [values[0], values[2]].filter(Boolean).join(' | ');
            title = meta;
        }
        if (type === 'index' && meta) {
            meta = '(' + meta + ')';
        }
        var rowAttrs = {
            class: 'aliyun-tree-row',
            title: title || (config.insertable ? '点击插入名称' : '')
        };
        if (config.insertable && name) {
            rowAttrs['data-resource-name'] = name;
            if (type === 'column') {
                rowAttrs['data-column-name'] = name;
            }
        }
        if (copyText) {
            rowAttrs['data-resource-detail'] = copyText;
        }
        var actions = $('<span/>', {class: 'aliyun-tree-actions'});
        if (copyText) {
            actions.append(
                $('<button/>', {
                    type: 'button',
                    class: 'aliyun-tree-action aliyun-resource-copy-detail',
                    title: '复制定义',
                    'aria-label': '复制' + name + '定义'
                }).append($('<i/>', {class: 'fa fa-copy'}))
            );
        }
        children.append(
            $('<li/>').append(
                $('<div/>', rowAttrs).append(
                    $('<span/>', {class: 'aliyun-tree-toggle'}),
                    $('<i/>', {class: config.icon}),
                    $('<span/>', {class: 'aliyun-tree-label', text: name, title: name}),
                    $('<span/>', {class: 'aliyun-tree-meta', text: meta, title: title || meta}),
                    actions
                )
            )
        );
    });
}

function loadAliyunTableGroup(tableNode, resourceType, options) {
    options = options || {};
    var group = tableNode.find('[data-resource-group="' + resourceType + '"]');
    var config = aliyunTableGroupConfig(resourceType);
    var apiResourceType = config.apiResourceType;
    if (group.data('loaded') && !options.forceRefresh) {
        group.toggleClass('is-open');
        return;
    }
    group.removeData('loaded');
    group.addClass('is-open');
    group.children('.aliyun-tree-children').html('<li class="aliyun-tree-loading"><div class="aliyun-tree-row"><span class="aliyun-tree-label">加载中...</span></div></li>');
    if (resourceType === 'column') {
        $.ajax({
            type: 'post',
            url: '/instance/describetable/',
            dataType: 'json',
            data: currentAliyunResourceParams({
                tb_name: tableNode.data('table-name'),
                _refresh: aliyunRefreshToken(options.forceRefresh)
            }),
            success: function (data) {
                if (data.status !== 0) {
                    group.children('.aliyun-tree-children').html(
                        '<li class="aliyun-tree-error"><div class="aliyun-tree-row"><span class="aliyun-tree-label">' + escapeHtml(data.msg) + '</span></div></li>'
                    );
                    return;
                }
                renderAliyunTableChildren(group, (data.data && data.data.rows) || [], resourceType);
                group.data('loaded', true);
            },
            error: function (XMLHttpRequest, textStatus, errorThrown) {
                group.children('.aliyun-tree-children').html(
                    '<li class="aliyun-tree-error"><div class="aliyun-tree-row"><span class="aliyun-tree-label">' + escapeHtml(errorThrown) + '</span></div></li>'
                );
            },
            complete: function () {
                if (typeof options.complete === 'function') {
                    options.complete();
                }
            }
        });
        return;
    }
    $.ajax({
        type: 'get',
        url: '/instance/instance_resource/',
        dataType: 'json',
        data: currentAliyunResourceParams({
            tb_name: tableNode.data('table-name'),
            resource_type: apiResourceType,
            _refresh: aliyunRefreshToken(options.forceRefresh)
        }),
        success: function (data) {
            if (data.status !== 0) {
                group.children('.aliyun-tree-children').html(
                    '<li class="aliyun-tree-error"><div class="aliyun-tree-row"><span class="aliyun-tree-label">' + escapeHtml(data.msg) + '</span></div></li>'
                );
                return;
            }
            renderAliyunTableChildren(group, data.data || [], resourceType);
            group.data('loaded', true);
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            group.children('.aliyun-tree-children').html(
                '<li class="aliyun-tree-error"><div class="aliyun-tree-row"><span class="aliyun-tree-label">' + escapeHtml(errorThrown) + '</span></div></li>'
            );
        },
        complete: function () {
            if (typeof options.complete === 'function') {
                options.complete();
            }
        }
    });
}

function syncAliyunTableObjects(options) {
    ensureAliyunResourceShell();
    options = options || {};
    var list = $('#aliyun-table-object-list');
    if (!list.length) {
        return;
    }
    if (!$('#instance_name').val() || !$('#db_name').val()) {
        renderAliyunTableObjects(collectAliyunTablesFromSelect());
        return;
    }
    setAliyunResourceRefreshState('#aliyun-resource-refresh', true);
    list.html('<li class="aliyun-tree-loading"><div class="aliyun-tree-row"><span class="aliyun-tree-label">加载中...</span></div></li>');
    syncAliyunResourceHelper();
    $.ajax({
        type: 'get',
        url: '/instance/instance_resource/',
        dataType: 'json',
        data: currentAliyunResourceParams({
            resource_type: 'table',
            _refresh: aliyunRefreshToken(options.forceRefresh)
        }),
        success: function (data) {
            if (data.status !== 0) {
                renderAliyunTableObjects(collectAliyunTablesFromSelect());
                showAliyunNotice(data.msg || '表列表刷新失败，已使用当前缓存', 'error');
                return;
            }
            var tableNames = (data.data || []).map(function (row) {
                return $.isArray(row) ? row[0] : row;
            }).filter(Boolean);
            syncAliyunTableSelectOptions(tableNames);
            renderAliyunTableObjects(tableNames);
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            renderAliyunTableObjects(collectAliyunTablesFromSelect());
            showAliyunNotice(errorThrown || '表列表刷新失败，已使用当前缓存', 'error');
        },
        complete: function () {
            setAliyunResourceRefreshState('#aliyun-resource-refresh', false);
            syncAliyunResourceHelper();
        }
    });
}

function filterAliyunTableObjects() {
    var keyword = $('#aliyun-table-tree-search').val().toLowerCase();
    $('#aliyun-table-object-list > .aliyun-table-node').each(function () {
        var tableName = String($(this).data('table-name') || '').toLowerCase();
        $(this).toggle(!keyword || tableName.indexOf(keyword) !== -1);
    });
    syncAliyunResourceHelper();
}

function toggleAliyunTableNode(tableNode) {
    if (!tableNode.length) {
        return;
    }
    $('#aliyun-table-object-list .is-active').removeClass('is-active');
    tableNode.addClass('is-active');
    $('#table_name').selectpicker('val', tableNode.data('table-name'));
    $('#table_name').selectpicker('refresh');
    tableNode.toggleClass('is-open');
    aliyunOpenTableNodes[tableNode.data('table-name')] = tableNode.hasClass('is-open');
    if (tableNode.hasClass('is-open')) {
        var columnGroup = tableNode.find('[data-resource-group="column"]');
        if (!columnGroup.data('loaded')) {
            loadAliyunTableGroup(tableNode, 'column');
        }
    }
}

function currentDbTypeForDictionary() {
    var engine = $('#instance_name :selected').parent().attr('label');
    return engine ? engine.toLowerCase() : '';
}

function programObjectConfig(type) {
    return {
        view: {
            type: 'view',
            url: '/data_dictionary/view_list/',
            detailUrl: '/data_dictionary/view_info/',
            detailParam: 'view_name',
            icon: 'fa fa-eye',
            empty: '没有视图',
            insertSuffix: ''
        },
        materialized_view: {
            type: 'materialized_view',
            url: '/data_dictionary/materialized_view_list/',
            detailUrl: '/data_dictionary/materialized_view_info/',
            detailParam: 'matview_name',
            icon: 'fa fa-database',
            empty: '没有物化视图',
            insertSuffix: '',
            dbTypes: ['pgsql']
        },
        sequence: {
            type: 'sequence',
            url: '/data_dictionary/sequence_list/',
            detailUrl: '/data_dictionary/sequence_info/',
            detailParam: 'sequence_name',
            icon: 'fa fa-sort-numeric-asc',
            empty: '没有序列',
            insertSuffix: '',
            dbTypes: ['pgsql']
        },
        function: {
            type: 'function',
            url: '/data_dictionary/function_list/',
            detailUrl: '/data_dictionary/function_info/',
            detailParam: 'func_name',
            icon: 'fa fa-code',
            empty: '没有函数',
            insertSuffix: '()',
            objectIdIndex: 2,
            rawNameIndex: 3,
            argumentsIndex: 4
        },
        procedure: {
            type: 'procedure',
            url: '/data_dictionary/procedure_list/',
            detailUrl: '/data_dictionary/procedure_info/',
            detailParam: 'proc_name',
            icon: 'fa fa-cogs',
            empty: '没有存储过程',
            insertSuffix: '()',
            objectIdIndex: 2,
            rawNameIndex: 3,
            argumentsIndex: 4
        },
        trigger: {
            type: 'trigger',
            url: '/data_dictionary/trigger_list/',
            detailUrl: '/data_dictionary/trigger_info/',
            detailParam: 'trigger_name',
            icon: 'fa fa-bolt',
            empty: '没有触发器',
            insertSuffix: ''
        }
    }[type];
}

function isAliyunProgramObjectSupported(config) {
    var dbType = currentDbTypeForDictionary();
    if (!config || !config.dbTypes || !config.dbTypes.length) {
        return true;
    }
    return config.dbTypes.indexOf(dbType) !== -1;
}

function formatAliyunProgramDefinitionValue(value) {
    if (value === null || value === undefined) {
        return '';
    }
    if ($.isArray(value)) {
        if (value.length === 1) {
            return formatAliyunProgramDefinitionValue(value[0]);
        }
        return value.map(formatAliyunProgramDefinitionValue).filter(Boolean).join('\n');
    }
    if (typeof value === 'object') {
        if (value.create_sql) {
            return formatAliyunProgramDefinitionValue(value.create_sql);
        }
        if (value.view_definition) {
            return formatAliyunProgramDefinitionValue(value.view_definition);
        }
        if (value.rows) {
            return formatAliyunProgramDefinitionValue(value.rows);
        }
        return JSON.stringify(value, null, 2);
    }
    return String(value);
}

function formatAliyunProgramDefinition(data) {
    var payload = data && data.data !== undefined ? data.data : data;
    var definition = '';
    if (payload && typeof payload === 'object') {
        definition = formatAliyunProgramDefinitionValue(payload.create_sql);
        if (!definition) {
            definition = formatAliyunProgramDefinitionValue(payload.view_definition);
        }
        if (!definition && payload.meta_data && payload.meta_data.rows) {
            definition = formatAliyunProgramDefinitionValue(payload.meta_data.rows);
        }
        if (!definition && payload.rows) {
            definition = formatAliyunProgramDefinitionValue(payload.rows);
        }
    }
    if (!definition) {
        definition = formatAliyunProgramDefinitionValue(payload);
    }
    return $.trim(definition || '');
}

function renderProgramObjectChildren(group, rows, config) {
    var children = group.children('.aliyun-tree-children');
    children.empty();
    if (!rows.length) {
        children.append(
            $('<li/>', {class: 'aliyun-tree-empty'}).append(
                $('<div/>', {class: 'aliyun-tree-row'}).append(
                    $('<span/>', {class: 'aliyun-tree-label', text: config.empty})
                )
            )
        );
        return;
    }
    rows.forEach(function (row) {
        var values = normalizeAliyunResourceRow(row);
        var name = values[0] || '';
        var meta = values[1] || '';
        var objectId = config.objectIdIndex !== undefined ? values[config.objectIdIndex] || '' : '';
        var rawName = config.rawNameIndex !== undefined ? values[config.rawNameIndex] || name : name;
        var identityArguments = config.argumentsIndex !== undefined ? values[config.argumentsIndex] || '' : '';
        children.append(
            $('<li/>', {
                class: 'aliyun-program-object',
                'data-program-object-name': name,
                'data-program-object-type': config.type,
                'data-program-object-id': objectId,
                'data-program-object-raw-name': rawName,
                'data-program-object-arguments': identityArguments
            }).append(
                $('<div/>', {
                    class: 'aliyun-tree-row aliyun-program-object-row',
                    title: '点击查看定义'
                }).append(
                    $('<span/>', {class: 'aliyun-tree-toggle'}),
                    $('<i/>', {class: config.icon}),
                    $('<span/>', {class: 'aliyun-tree-label', text: name, title: name}),
                    $('<span/>', {class: 'aliyun-tree-meta', text: meta}),
                    $('<span/>', {class: 'aliyun-tree-actions'}).append(
                        $('<button/>', {
	                            type: 'button',
	                            class: 'aliyun-tree-action aliyun-program-show-definition',
	                            title: '查看定义',
	                            'aria-label': '查看' + name + '定义'
	                        }).append($('<i/>', {class: 'fa fa-file-code-o'})),
	                        $('<button/>', {
	                            type: 'button',
	                            class: 'aliyun-tree-action aliyun-program-insert-name',
	                            title: '插入名称',
	                            'aria-label': '插入对象名称 ' + name
	                        }).append($('<i/>', {class: 'fa fa-i-cursor'}))
                    )
                ),
                $('<div/>', {class: 'aliyun-program-definition'}).append(
                    $('<div/>', {class: 'aliyun-program-definition-tools'}).append(
                        $('<button/>', {
	                            type: 'button',
	                            class: 'aliyun-tree-action aliyun-program-copy-definition',
	                            title: '复制定义',
	                            'aria-label': '复制定义'
	                        }).append($('<i/>', {class: 'fa fa-copy'})),
	                        $('<button/>', {
	                            type: 'button',
	                            class: 'aliyun-tree-action aliyun-program-refresh-definition',
	                            title: '刷新定义',
	                            'aria-label': '刷新定义'
	                        }).append($('<i/>', {class: 'fa fa-refresh'}))
                    ),
                    $('<pre/>', {class: 'aliyun-program-definition-code'})
                )
            )
        );
    });
}

function loadAliyunProgramGroup(group, options) {
    ensureAliyunResourceShell();
    options = options || {};
    var type = group.data('program-type');
    var config = programObjectConfig(type);
    if (!config) {
        return;
    }
    if (!isAliyunProgramObjectSupported(config)) {
        group.hide().removeClass('is-open').removeData('loaded');
        group.children('.aliyun-tree-children').empty();
        return;
    }
    group.show();
    if (group.data('loaded') && !options.forceRefresh) {
        group.toggleClass('is-open');
        return;
    }
    group.removeData('loaded');
    group.addClass('is-open');
    group.children('.aliyun-tree-children').html('<li class="aliyun-tree-loading"><div class="aliyun-tree-row"><span class="aliyun-tree-label">加载中...</span></div></li>');
    $.ajax({
        type: 'get',
        url: config.url,
        dataType: 'json',
        data: {
            instance_name: $('#instance_name').val(),
            db_name: $('#db_name').val(),
            schema_name: $('#schema_name').val(),
            db_type: currentDbTypeForDictionary(),
            _refresh: aliyunRefreshToken(options.forceRefresh)
        },
        success: function (data) {
            if (data.status !== 0) {
                group.children('.aliyun-tree-children').html(
                    '<li class="aliyun-tree-error"><div class="aliyun-tree-row"><span class="aliyun-tree-label">' + escapeHtml(data.msg) + '</span></div></li>'
                );
                return;
            }
            renderProgramObjectChildren(group, flattenAliyunGroupedRows(data.data), config);
            group.data('loaded', true);
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            group.children('.aliyun-tree-children').html(
                '<li class="aliyun-tree-error"><div class="aliyun-tree-row"><span class="aliyun-tree-label">' + escapeHtml(errorThrown) + '</span></div></li>'
            );
        },
        complete: function () {
            if (typeof options.complete === 'function') {
                options.complete();
            }
        }
    });
}

function refreshAliyunProgramObjects() {
    ensureAliyunResourceShell();
    var hasOpenGroup = false;
    setAliyunResourceRefreshState('#aliyun-program-resource-refresh', true);
    var pendingRequests = 0;
    var finishRefresh = function () {
        pendingRequests -= 1;
        if (pendingRequests <= 0) {
            setAliyunResourceRefreshState('#aliyun-program-resource-refresh', false);
        }
    };
    $('.aliyun-program-group').removeData('loaded').each(function () {
        var group = $(this);
        var config = programObjectConfig(group.data('program-type'));
        if (!isAliyunProgramObjectSupported(config)) {
            group.hide().removeClass('is-open');
            group.children('.aliyun-tree-children').empty();
            return;
        }
        group.show();
        if (group.hasClass('is-open')) {
            hasOpenGroup = true;
            group.removeClass('is-open');
            pendingRequests += 1;
            loadAliyunProgramGroup(group, {forceRefresh: true, complete: finishRefresh});
        }
    });
    if (!hasOpenGroup) {
        $('.aliyun-program-group').each(function () {
            var group = $(this);
            var config = programObjectConfig(group.data('program-type'));
            if (!isAliyunProgramObjectSupported(config)) {
                return;
            }
            pendingRequests += 1;
            loadAliyunProgramGroup(group, {forceRefresh: true, complete: finishRefresh});
        });
    }
    if (!pendingRequests) {
        setAliyunResourceRefreshState('#aliyun-program-resource-refresh', false);
    }
}

function filterAliyunProgramObjects() {
    var keyword = $('#aliyun-program-tree-search').val().toLowerCase();
    $('#aliyun-program-object-list .aliyun-program-object').each(function () {
        var objectName = String($(this).data('program-object-name') || '').toLowerCase();
        var rawName = String($(this).data('program-object-raw-name') || '').toLowerCase();
        $(this).toggle(!keyword || objectName.indexOf(keyword) !== -1 || rawName.indexOf(keyword) !== -1);
    });
    $('.aliyun-program-group').each(function () {
        var group = $(this);
        var config = programObjectConfig(group.data('program-type'));
        if (!isAliyunProgramObjectSupported(config)) {
            group.hide();
            return;
        }
        var hasVisibleObjects = group.find('.aliyun-program-object:visible').length > 0;
        var hasObjects = group.find('.aliyun-program-object').length > 0;
        group.toggle(!keyword || !hasObjects || hasVisibleObjects);
    });
}

function insertAliyunProgramObjectName(objectNode) {
    var type = objectNode.data('program-object-type');
    var config = programObjectConfig(type);
    var name = objectNode.data('program-object-name');
    var rawName = objectNode.data('program-object-raw-name') || name;
    var identityArguments = objectNode.data('program-object-arguments');
    if (!config || !name) {
        return;
    }
    if (config.type === 'function' || config.type === 'procedure') {
        insertTextIntoEditor(qualifiedProgramObjectName(rawName) + '(' + (identityArguments || '') + ')');
        return;
    }
    insertTextIntoEditor(qualifiedProgramObjectName(rawName) + config.insertSuffix);
}

function loadAliyunProgramObjectDefinition(objectNode, options) {
    options = options || {};
    var type = objectNode.data('program-object-type');
    var config = programObjectConfig(type);
    var name = objectNode.data('program-object-name');
    var rawName = objectNode.data('program-object-raw-name') || name;
    var objectId = objectNode.data('program-object-id');
    var definition = objectNode.children('.aliyun-program-definition');
    var code = definition.find('.aliyun-program-definition-code');
    if (!config || !name || !definition.length) {
        return;
    }
    if (objectNode.data('definition-loaded') && !options.forceRefresh) {
        definition.toggleClass('is-open');
        return;
    }
    objectNode.removeData('definition-loaded');
    definition.addClass('is-open is-loading');
    code.text('加载中...');
    var params = currentAliyunResourceParams({
        db_type: currentDbTypeForDictionary()
    });
    params[config.detailParam] = rawName;
    if (objectId) {
        params.object_id = objectId;
    }
    if (options.forceRefresh) {
        params._refresh = aliyunRefreshToken(true);
    }
    $.ajax({
        type: 'get',
        url: config.detailUrl,
        dataType: 'json',
        data: params,
        success: function (data) {
            definition.removeClass('is-loading');
            if (data.status !== 0) {
                code.text(data.msg || '加载失败');
                return;
            }
            var definitionText = formatAliyunProgramDefinition(data);
            code.text(definitionText || '没有可展示的定义');
            objectNode.data('definition-loaded', true);
            objectNode.data('definition-text', definitionText);
            if (typeof options.onLoaded === 'function') {
                options.onLoaded(definitionText);
            }
            filterAliyunProgramObjects();
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            definition.removeClass('is-loading');
            code.text(errorThrown || '加载失败');
        },
        complete: function () {
            if (typeof options.complete === 'function') {
                options.complete();
            }
        }
    });
}

function copyAliyunProgramDefinition(objectNode) {
    var definitionText = objectNode.data('definition-text');
    if (definitionText) {
        copyTextToClipboard(definitionText, '已复制定义');
        return;
    }
    loadAliyunProgramObjectDefinition(objectNode, {
        forceRefresh: true,
        onLoaded: function (text) {
            copyTextToClipboard(text, '已复制定义');
        }
    });
}

function resetAliyunProgramObjects() {
    ensureAliyunResourceShell();
    $('#aliyun-program-tree-search').val('');
    $('.aliyun-program-group').removeClass('is-open').removeData('loaded').each(function () {
        var group = $(this);
        var config = programObjectConfig(group.data('program-type'));
        group.toggle(isAliyunProgramObjectSupported(config));
        $(this).children('.aliyun-tree-children').empty();
    });
}
