// Split from sqlquery-aliyun.js. Loaded by sqlquery.html.
function normalizeKnowledgeEngines(engines) {
    if ($.isArray(engines)) {
        return engines.length ? engines : ['通用'];
    }
    if (engines) {
        return String(engines).split(',').map(function (engine) {
            return $.trim(engine);
        }).filter(Boolean);
    }
    return ['通用'];
}

function knowledgeEngineLabel(engines) {
    return normalizeKnowledgeEngines(engines).join(',');
}

function renderAliyunKnowledgeItem(item) {
    var engines = knowledgeEngineLabel(item.engines);
    return '' +
        '<tr class="aliyun-knowledge-row aliyun-knowledge-custom-row" data-knowledge-id="' + escapeHtml(item.id) + '"' +
        ' data-engines="' + escapeHtml(engines) + '"' +
        ' data-name="' + escapeHtml(item.name) + '"' +
        ' data-scene="' + escapeHtml(item.scene || '自定义') + '"' +
        ' data-sql="' + escapeHtml(item.sql) + '">' +
        '<td title="' + escapeHtml(item.name) + '">' + escapeHtml(item.name) + '</td>' +
        '<td class="sql-text" title="' + escapeHtml(item.sql) + '">' + escapeHtml(item.sql) + '</td>' +
        '<td>' + escapeHtml(engines) + '</td>' +
        '<td>' + escapeHtml(item.scene || '自定义') + '</td>' +
        '<td>' +
        '<button type="button" class="btn btn-xs btn-default aliyun-knowledge-fill" aria-label="填充知识库SQL ' + escapeHtml(item.name) + '">填充</button> ' +
        '<button type="button" class="btn btn-xs btn-default aliyun-knowledge-edit" aria-label="编辑知识库SQL ' + escapeHtml(item.name) + '">编辑</button> ' +
        '<button type="button" class="btn btn-xs btn-default aliyun-knowledge-copy" aria-label="复制知识库SQL ' + escapeHtml(item.name) + '">复制</button> ' +
        '<button type="button" class="btn btn-xs btn-default aliyun-knowledge-delete" aria-label="删除知识库SQL ' + escapeHtml(item.name) + '">删除</button>' +
        '</td>' +
        '</tr>';
}

function renderAliyunCustomKnowledgeRows() {
    $('.aliyun-knowledge-custom-row').remove();
    var emptyRow = $('.aliyun-knowledge-empty');
    aliyunKnowledgeRows.forEach(function (item) {
        emptyRow.before(renderAliyunKnowledgeItem(item));
    });
}

function showAliyunKnowledgeAlert(message) {
    $('#aliyun-knowledge-alert').text(message || '').toggle(Boolean(message));
}

function syncAliyunKnowledgeSceneOptions(scenes) {
    var sceneFilter = $('#aliyun-knowledge-scene-filter');
    var currentValue = sceneFilter.val() || '';
    aliyunKnowledgeFilterSyncing = true;
    sceneFilter.find('option:not([value=""])').remove();
    (scenes || []).forEach(function (scene) {
        $('<option/>', {value: scene, text: scene}).appendTo(sceneFilter);
    });
    sceneFilter.selectpicker('val', currentValue);
    sceneFilter.selectpicker('refresh');
    aliyunKnowledgeFilterSyncing = false;
}

function refreshAliyunKnowledgeRows() {
    return $.ajax({
        type: 'get',
        url: '/query/knowledge/',
        dataType: 'json',
        data: {
            search: $('#aliyun-knowledge-search-input').val() || '',
            engine: $('#aliyun-knowledge-engine-filter').val() || '',
            scene: $('#aliyun-knowledge-scene-filter').val() || ''
        },
        success: function (data) {
            if (data.status !== 0) {
                showAliyunKnowledgeAlert(data.msg);
                return;
            }
            aliyunKnowledgeRows = data.data || [];
            syncAliyunKnowledgeSceneOptions(data.scenes || []);
            renderAliyunCustomKnowledgeRows();
            syncAliyunKnowledgeRows();
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            showAliyunKnowledgeAlert(errorThrown);
        }
    });
}

function syncAliyunKnowledgeRows() {
    var engine = $('#instance_name :selected').parent().attr('label');
    var keyword = $.trim($('#aliyun-knowledge-search-input').val() || '').toLowerCase();
    var visibleCount = 0;
    $('.aliyun-knowledge-row').each(function () {
        var engines = String($(this).data('engines') || '').split(',');
        var rowText = $(this).text().toLowerCase();
        var sqlText = String($(this).data('sql') || '').toLowerCase();
        var matchesEngine = !engine || engines.indexOf(engine) !== -1 || engines.indexOf('通用') !== -1;
        var matchesKeyword = !keyword || rowText.indexOf(keyword) !== -1 || sqlText.indexOf(keyword) !== -1;
        var visible = matchesEngine && matchesKeyword;
        $(this).toggle(visible);
        if (visible) {
            visibleCount += 1;
        }
    });
    $('.aliyun-knowledge-empty').toggle(visibleCount === 0);
}

function openAliyunKnowledgeModal() {
    var engine = $('#instance_name :selected').parent().attr('label') || '通用';
    $('#aliyun-knowledge-modal .modal-title').text('添加知识库SQL');
    $('#aliyun-knowledge-id').val('');
    $('#aliyun-knowledge-action').val('add');
    showAliyunKnowledgeAlert('');
    $('#aliyun-knowledge-name').val('');
    $('#aliyun-knowledge-scene').val('自定义');
    var engineValues = engine ? [engine] : ['通用'];
    $('#aliyun-knowledge-engines').selectpicker('val', engineValues);
    $('#aliyun-knowledge-engines').selectpicker('refresh');
    $('#aliyun-knowledge-sql').val(getCurrentEditorSql());
    $('#aliyun-knowledge-modal').modal('show');
}

function getAliyunKnowledgeItemById(knowledgeId) {
    knowledgeId = String(knowledgeId || '');
    for (var i = 0; i < aliyunKnowledgeRows.length; i++) {
        if (String(aliyunKnowledgeRows[i].id) === knowledgeId) {
            return aliyunKnowledgeRows[i];
        }
    }
    return null;
}

function openAliyunKnowledgeModalForItem(row, action) {
    var knowledgeId = String($(row).data('knowledge-id') || '');
    var item = getAliyunKnowledgeItemById(knowledgeId);
    if (!item) {
        showAliyunKnowledgeAlert('知识库记录不存在');
        return;
    }
    var isCopy = action === 'copy';
    $('#aliyun-knowledge-modal .modal-title').text(isCopy ? '复制知识库SQL' : '编辑知识库SQL');
    $('#aliyun-knowledge-id').val(item.id);
    $('#aliyun-knowledge-action').val(action || 'edit');
    showAliyunKnowledgeAlert('');
    $('#aliyun-knowledge-name').val(isCopy ? item.name + ' 副本' : item.name);
    $('#aliyun-knowledge-scene').val(item.scene || '自定义');
    $('#aliyun-knowledge-engines').selectpicker('val', normalizeKnowledgeEngines(item.engines));
    $('#aliyun-knowledge-engines').selectpicker('refresh');
    $('#aliyun-knowledge-sql').val(item.sql || '');
    $('#aliyun-knowledge-modal').modal('show');
}

function saveAliyunKnowledgeFromModal() {
    var knowledgeId = $('#aliyun-knowledge-id').val();
    var action = $('#aliyun-knowledge-action').val() || 'add';
    var name = $.trim($('#aliyun-knowledge-name').val());
    var scene = $.trim($('#aliyun-knowledge-scene').val()) || '自定义';
    var engines = $('#aliyun-knowledge-engines').val() || [];
    var sql = $.trim($('#aliyun-knowledge-sql').val());
    if (!name) {
        showAliyunKnowledgeAlert('请输入名称');
        return;
    }
    if (!engines.length) {
        showAliyunKnowledgeAlert('请选择适用引擎');
        return;
    }
    if (!sql) {
        showAliyunKnowledgeAlert('请输入SQL');
        return;
    }
    showAliyunKnowledgeAlert('');
    $.ajax({
        type: 'post',
        url: '/query/knowledge/',
        dataType: 'json',
        data: {
            action: action,
            id: knowledgeId,
            name: name,
            scene: scene,
            'engines[]': engines,
            sql: sql,
            instance_name: $('#instance_name').val(),
            db_name: $('#db_name').val()
        },
        success: function (data) {
            if (data.status !== 0) {
                showAliyunKnowledgeAlert(data.msg);
                return;
            }
            $('#aliyun-knowledge-modal').modal('hide');
            refreshAliyunKnowledgeRows();
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            showAliyunKnowledgeAlert(errorThrown);
        }
    });
}

function deleteAliyunKnowledge(row) {
    var knowledgeId = String($(row).data('knowledge-id') || '');
    if (!knowledgeId) {
        return;
    }
    $.ajax({
        type: 'post',
        url: '/query/knowledge/',
        dataType: 'json',
        data: {
            action: 'delete',
            id: knowledgeId
        },
        success: function (data) {
            if (data.status !== 0) {
                showAliyunKnowledgeAlert(data.msg);
                return;
            }
            refreshAliyunKnowledgeRows();
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            showAliyunKnowledgeAlert(errorThrown);
        }
    });
}
