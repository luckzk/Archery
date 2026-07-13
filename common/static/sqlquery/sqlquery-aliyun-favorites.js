// Split from sqlquery-aliyun.js. Loaded by sqlquery.html.
function formatFavoriteTime(value) {
    return value || '';
}

function favoriteAliasLabel(alias) {
    return alias || '未命名';
}

function syncFavoriteSelectOptions(favorites) {
    var filterAlias = $('#filter-alias');
    var quickFavorites = $('#favorites');
    filterAlias.find('option:not([value=""])').remove();
    quickFavorites.empty();
    favorites.forEach(function (favorite) {
        var label = favoriteAliasLabel(favorite.alias);
        if (favorite.source_query_log_id) {
            $('<option/>', {
                value: favorite.source_query_log_id,
                text: label
            }).appendTo(filterAlias);
        }
        $('<option/>', {
            value: favorite.id,
            text: label,
            'data-source-query-log-id': favorite.source_query_log_id || '',
            'data-sql': favorite.sqllog || '',
            'data-instance-name': favorite.instance_name || '',
            'data-db-name': favorite.db_name || ''
        }).appendTo(quickFavorites);
    });
    if ($.fn.selectpicker) {
        filterAlias.selectpicker('render').selectpicker('refresh');
        quickFavorites.selectpicker('render').selectpicker('refresh');
    }
}

function renderFavoriteRow(favorite) {
    var alias = favoriteAliasLabel(favorite.alias);
    var sql = favorite.sqllog || '';
    return '' +
        '<tr class="aliyun-favorite-row" data-favorite-id="' + escapeHtml(favorite.id) + '"' +
        ' data-source-query-log-id="' + escapeHtml(favorite.source_query_log_id || '') + '"' +
        ' data-instance-name="' + escapeHtml(favorite.instance_name || '') + '"' +
        ' data-db-name="' + escapeHtml(favorite.db_name || '') + '">' +
        '<td class="aliyun-favorite-alias" title="' + escapeHtml(alias) + '">' + escapeHtml(alias) + '</td>' +
        '<td class="sql-text" title="' + escapeHtml(sql) + '">' + escapeHtml(sql) + '</td>' +
        '<td>' + escapeHtml(formatFavoriteTime(favorite.create_time)) + '</td>' +
        '<td>' + escapeHtml(formatFavoriteTime(favorite.sys_time || favorite.create_time)) + '</td>' +
        '<td>' +
        '<button type="button" class="btn btn-xs btn-default aliyun-favorite-fill" aria-label="回填收藏SQL ' + escapeHtml(alias) + '">回填</button> ' +
        '<button type="button" class="btn btn-xs btn-default aliyun-favorite-edit" aria-label="编辑收藏SQL ' + escapeHtml(alias) + '">编辑</button> ' +
        '<button type="button" class="btn btn-xs btn-default aliyun-favorite-delete" aria-label="删除收藏SQL ' + escapeHtml(alias) + '">删除</button>' +
        '</td>' +
        '<td class="aliyun-favorite-sql-source">' + escapeHtml(sql) + '</td>' +
        '</tr>';
}

function renderFavoriteTable(favorites) {
    var tbody = $('#aliyun-favorite-table tbody');
    tbody.empty();
    if (!favorites.length) {
        tbody.append('<tr class="aliyun-favorite-empty"><td class="aliyun-empty-row" colspan="5">没有数据</td></tr>');
        return;
    }
    favorites.forEach(function (favorite) {
        tbody.append(renderFavoriteRow(favorite));
    });
}

function sortFavoriteRows(field) {
    if (aliyunFavoriteSort.field === field) {
        aliyunFavoriteSort.direction = aliyunFavoriteSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        aliyunFavoriteSort.field = field;
        aliyunFavoriteSort.direction = 'asc';
    }
    var direction = aliyunFavoriteSort.direction === 'asc' ? 1 : -1;
    aliyunFavoriteRows.sort(function (left, right) {
        var leftValue = left[field] || '';
        var rightValue = right[field] || '';
        return String(leftValue).localeCompare(String(rightValue), 'zh-CN') * direction;
    });
    renderFavoriteTable(aliyunFavoriteRows);
}

function refreshAliyunFavorites(search) {
    return $.ajax({
        type: 'get',
        url: '/query/favorite/',
        dataType: 'json',
        data: {
            search: search || ''
        },
        success: function (data) {
            if (data.status !== 0) {
                showAliyunNotice(data.msg, 'error');
                return;
            }
            var favorites = data.data || [];
            aliyunFavoriteRows = favorites;
            renderFavoriteTable(aliyunFavoriteRows);
            if (!search) {
                syncFavoriteSelectOptions(favorites);
            }
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            showAliyunNotice(errorThrown, 'error');
        }
    });
}

function refreshAliyunFavoriteOptions() {
    return $.ajax({
        type: 'get',
        url: '/query/favorite/',
        dataType: 'json',
        success: function (data) {
            if (data.status !== 0) {
                showAliyunNotice(data.msg, 'error');
                return;
            }
            syncFavoriteSelectOptions(data.data || []);
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            showAliyunNotice(errorThrown, 'error');
        }
    });
}

function refreshSqlLogTable() {
    var sqlLogTable = $('#sql-log');
    if (sqlLogTable.data('bootstrap.table')) {
        sqlLogTable.bootstrapTable('refresh');
    }
}

function refreshAliyunFavoriteState(refreshLog) {
    var search = $('#aliyun-favorite-search-input').val();
    refreshAliyunFavorites(search);
    if (search) {
        refreshAliyunFavoriteOptions();
    }
    if (refreshLog !== false) {
        refreshSqlLogTable();
    }
}

function postFavorite(data, afterSuccess) {
    return $.ajax({
        type: 'post',
        url: '/query/favorite/',
        dataType: 'json',
        data: data,
        success: function (response) {
            if (response.status !== 0) {
                showAliyunNotice(response.msg, 'error');
                return;
            }
            if (afterSuccess) {
                afterSuccess();
            }
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            showAliyunNotice(errorThrown, 'error');
        }
    });
}

function addCurrentSqlToFavorite() {
    var selectSqlContent = editor.session.getTextRange(editor.getSelectionRange());
    var sqlContent = $.trim(selectSqlContent || editor.getValue());
    if (!sqlContent) {
        showAliyunNotice('SQL内容不能为空！', 'error');
        return;
    }
    $('#query_log_id').val('');
    $('#favorite_id').val('');
    $('#favorite_sql_content').val(sqlContent);
    $('#alias').val('');
    $('#favorite').modal('show');
}

function editFavoriteAlias(row) {
    var favoriteId = $(row).data('favorite-id');
    var currentAlias = $(row).find('.aliyun-favorite-alias').text();
    var sqlContent = $(row).find('.aliyun-favorite-sql-source').text() || $(row).find('.sql-text').text();
    $('#favorite_id').val(favoriteId);
    $('#query_log_id').val('');
    $('#favorite_sql_content').val(sqlContent);
    $('#alias').val(currentAlias === '未命名' ? '' : currentAlias);
    $('#favorite-modal-alert').hide().text('');
    $('#favorite .modal-title').text('编辑收藏');
    $('#btn-star').text('保存');
    $('#favorite').modal('show');
}

function resetFavoriteModalTitle() {
    $('#favorite .modal-title').text('收藏语句');
    $('#btn-star').text('收藏');
}

function resetFavoriteDeleteState(row) {
    $(row).removeClass('is-confirming-delete');
    $(row).find('.aliyun-favorite-delete').text('删除');
}

function deleteFavorite(row) {
    var favoriteId = $(row).data('favorite-id');
    if (!$(row).hasClass('is-confirming-delete')) {
        $('.aliyun-favorite-row.is-confirming-delete').each(function () {
            resetFavoriteDeleteState(this);
        });
        $(row).addClass('is-confirming-delete');
        $(row).find('.aliyun-favorite-delete').text('确认删除');
        showAliyunNotice('再次点击确认删除该收藏');
        setTimeout(function () {
            resetFavoriteDeleteState(row);
        }, 3500);
        return;
    }
    resetFavoriteDeleteState(row);
    postFavorite({
        favorite_id: favoriteId,
        star: false,
        alias: ''
    }, function () {
        showAliyunNotice('已删除收藏');
        refreshAliyunFavoriteState();
    });
}

function fillEditorFromFavorite(row) {
    var sql = $(row).find('.aliyun-favorite-sql-source').text();
    if (sql) {
        editor.setValue(sql);
        editor.clearSelection();
        resizeSqlqueryEditor();
    }
}
