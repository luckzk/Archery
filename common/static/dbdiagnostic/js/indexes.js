let indexesListColumns = [
    {
        title: '诊断类型',
        field: 'diagnostic_type',
        sortable: true
    }, {
        title: 'Schema',
        field: 'schema_name',
        sortable: true
    }, {
        title: '表名',
        field: 'table_name',
        sortable: true
    }, {
        title: '索引名',
        field: 'index_name',
        sortable: true
    }, {
        title: '索引大小',
        field: 'index_size',
        sortable: true
    }, {
        title: '索引大小(bytes)',
        field: 'index_size_bytes',
        sortable: true,
        visible: false
    }, {
        title: '表大小',
        field: 'table_size',
        sortable: true
    }, {
        title: '表大小(bytes)',
        field: 'table_size_bytes',
        sortable: true,
        visible: false
    }, {
        title: '索引扫描',
        field: 'idx_scan',
        sortable: true
    }, {
        title: '顺序扫描',
        field: 'seq_scan',
        sortable: true
    }, {
        title: 'Live Tuples',
        field: 'n_live_tup',
        sortable: true,
        visible: false
    }, {
        title: '有效',
        field: 'is_valid',
        sortable: true
    }, {
        title: 'Ready',
        field: 'is_ready',
        sortable: true,
        visible: false
    }, {
        title: '唯一',
        field: 'is_unique',
        sortable: true
    }, {
        title: '主键',
        field: 'is_primary',
        sortable: true
    }, {
        title: '原因',
        field: 'reason',
        sortable: true
    }, {
        title: '索引定义',
        field: 'index_def',
        sortable: true,
        visible: false
    }
]

var pgsqlIndexesFilterInstance = "";

function refresh_indexes_toolbar() {
    if (current_instance_db_type() === 'pgsql') {
        $("#pgsql-indexes-toolbar").show();
        if (sessionStorage.getItem('diagnostic_active_li_id') === 'indexes_tab') {
            load_pgsql_indexes_filters(false);
        }
    } else {
        $("#pgsql-indexes-toolbar").hide();
        $("#pgsql_indexes_db").empty().selectpicker('render').selectpicker('refresh');
        $("#pgsql_indexes_schema").empty().selectpicker('render').selectpicker('refresh');
        pgsqlIndexesFilterInstance = "";
    }
}

function fill_pgsql_indexes_select(selector, values, selectedValue) {
    var select = $(selector);
    select.empty();
    select.append("<option value=\"\">全部</option>");
    (values || []).forEach(function (value) {
        select.append("<option value=\"" + value + "\">" + value + "</option>");
    });
    select.selectpicker('render');
    select.selectpicker('refresh');
    select.selectpicker('val', selectedValue || "");
}

function load_pgsql_indexes_filters(force) {
    var instanceName = $("#instance_name").val();
    if (!instanceName || current_instance_db_type() !== 'pgsql') {
        return;
    }
    if (!force && pgsqlIndexesFilterInstance === instanceName) {
        return;
    }
    $.ajax({
        type: "get",
        url: "/db_diagnostic/pgsql_tablespace_filters/",
        dataType: "json",
        data: {
            instance_name: instanceName,
            db_name: $("#pgsql_indexes_db").val()
        },
        success: function (data) {
            if (data.status === 0) {
                var result = data.data || {};
                var selectedDb = $("#pgsql_indexes_db").val() || result.selected_db || "";
                fill_pgsql_indexes_select("#pgsql_indexes_db", result.databases, selectedDb);
                fill_pgsql_indexes_select("#pgsql_indexes_schema", result.schemas, $("#pgsql_indexes_schema").val());
                pgsqlIndexesFilterInstance = instanceName;
            } else {
                alert(data.msg);
            }
        }
    })
}

function get_pgsql_indexes_list() {
    $("#command-div").hide();
    $("#process-toolbar").hide();
    refresh_indexes_toolbar();
    if ($("#instance_name").val()) {
        $('#indexes-list').bootstrapTable('destroy').bootstrapTable({
            escape: true,
            method: 'post',
            contentType: "application/x-www-form-urlencoded",
            url: "/db_diagnostic/pgsql_indexes/",
            striped: true,
            cache: false,
            pagination: true,
            sortable: true,
            sortName: 'index_size_bytes',
            sortOrder: "desc",
            sidePagination: "server",
            pageNumber: 1,
            pageSize: 30,
            pageList: [20, 30, 50, 100, 500],
            search: true,
            strictSearch: false,
            showColumns: true,
            showRefresh: true,
            minimumCountColumns: 2,
            clickToSelect: true,
            uniqueId: "index_name",
            showToggle: true,
            showExport: true,
            exportDataType: "all",
            cardView: false,
            detailView: true,
            detailFormatter: function (index, row) {
                return '<h5>索引定义</h5><pre>' + (row.index_def || '') + '</pre>';
            },
            locale: 'zh-CN',
            toolbar: "#pgsql-indexes-toolbar",
            queryParamsType: 'limit',
            queryParams: function (params) {
                return {
                    offset: params.offset,
                    limit: params.limit,
                    instance_name: $("#instance_name").val(),
                    db_name: $("#pgsql_indexes_db").val(),
                    schema_name: $("#pgsql_indexes_schema").val()
                }
            },
            columns: indexesListColumns,
            onLoadSuccess: function (data) {
                if (data.status !== 0) {
                    alert("数据加载失败！" + data.msg);
                }
            },
            onLoadError: onLoadErrorCallback,
            onSearch: function (e) {
                queryParams(e)
            },
            responseHandler: function (res) {
                return res;
            }
        });
    }
}

$(function () {
    $("#pgsql_indexes_search").click(function () {
        get_pgsql_indexes_list();
    });

    $("#pgsql_indexes_reset").click(function () {
        $("#pgsql_indexes_db").selectpicker('val', "");
        $("#pgsql_indexes_schema").selectpicker('val', "");
        pgsqlIndexesFilterInstance = "";
        load_pgsql_indexes_filters(true);
        get_pgsql_indexes_list();
    });

    $("#pgsql_indexes_db").change(function () {
        $("#pgsql_indexes_schema").selectpicker('val', "");
        pgsqlIndexesFilterInstance = "";
        load_pgsql_indexes_filters(true);
    });
});
