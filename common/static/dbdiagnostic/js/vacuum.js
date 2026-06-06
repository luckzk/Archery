let vacuumListColumns = [
    {
        title: 'Schema',
        field: 'schema_name',
        sortable: true
    }, {
        title: '表名',
        field: 'table_name',
        sortable: true
    }, {
        title: 'Owner',
        field: 'owner_name',
        sortable: true
    }, {
        title: '风险等级',
        field: 'risk_level',
        sortable: true
    }, {
        title: 'Live Tuples',
        field: 'n_live_tup',
        sortable: true
    }, {
        title: 'Dead Tuples',
        field: 'n_dead_tup',
        sortable: true
    }, {
        title: 'Dead Tuple比例(%)',
        field: 'dead_tuple_ratio',
        sortable: true
    }, {
        title: 'XID年龄',
        field: 'relfrozenxid_age',
        sortable: true
    }, {
        title: '总空间',
        field: 'total_size',
        sortable: true
    }, {
        title: '总空间(bytes)',
        field: 'total_size_bytes',
        sortable: true,
        visible: false
    }, {
        title: '最近Vacuum',
        field: 'last_vacuum',
        sortable: true,
        visible: false
    }, {
        title: '最近Autovacuum',
        field: 'last_autovacuum',
        sortable: true
    }, {
        title: '最近Analyze',
        field: 'last_analyze',
        sortable: true,
        visible: false
    }, {
        title: '最近Autoanalyze',
        field: 'last_autoanalyze',
        sortable: true
    }, {
        title: 'Vacuum次数',
        field: 'vacuum_count',
        sortable: true,
        visible: false
    }, {
        title: 'Autovacuum次数',
        field: 'autovacuum_count',
        sortable: true
    }, {
        title: 'Analyze次数',
        field: 'analyze_count',
        sortable: true,
        visible: false
    }, {
        title: 'Autoanalyze次数',
        field: 'autoanalyze_count',
        sortable: true,
        visible: false
    }
]

var pgsqlVacuumFilterInstance = "";

function refresh_vacuum_toolbar() {
    if (current_instance_db_type() === 'pgsql') {
        $("#pgsql-vacuum-toolbar").show();
        if (sessionStorage.getItem('diagnostic_active_li_id') === 'vacuum_tab') {
            load_pgsql_vacuum_filters(false);
        }
    } else {
        $("#pgsql-vacuum-toolbar").hide();
        $("#pgsql_vacuum_db").empty().selectpicker('render').selectpicker('refresh');
        $("#pgsql_vacuum_schema").empty().selectpicker('render').selectpicker('refresh');
        pgsqlVacuumFilterInstance = "";
    }
}

function fill_pgsql_vacuum_select(selector, values, selectedValue) {
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

function load_pgsql_vacuum_filters(force) {
    var instanceName = $("#instance_name").val();
    if (!instanceName || current_instance_db_type() !== 'pgsql') {
        return;
    }
    if (!force && pgsqlVacuumFilterInstance === instanceName) {
        return;
    }
    $.ajax({
        type: "get",
        url: "/db_diagnostic/pgsql_tablespace_filters/",
        dataType: "json",
        data: {
            instance_name: instanceName,
            db_name: $("#pgsql_vacuum_db").val()
        },
        success: function (data) {
            if (data.status === 0) {
                var result = data.data || {};
                var selectedDb = $("#pgsql_vacuum_db").val() || result.selected_db || "";
                fill_pgsql_vacuum_select("#pgsql_vacuum_db", result.databases, selectedDb);
                fill_pgsql_vacuum_select("#pgsql_vacuum_schema", result.schemas, $("#pgsql_vacuum_schema").val());
                pgsqlVacuumFilterInstance = instanceName;
            } else {
                alert(data.msg);
            }
        }
    })
}

function get_pgsql_vacuum_list() {
    $("#command-div").hide();
    $("#process-toolbar").hide();
    refresh_vacuum_toolbar();
    if ($("#instance_name").val()) {
        $('#vacuum-list').bootstrapTable('destroy').bootstrapTable({
            escape: true,
            method: 'post',
            contentType: "application/x-www-form-urlencoded",
            url: "/db_diagnostic/pgsql_vacuum/",
            striped: true,
            cache: false,
            pagination: true,
            sortable: true,
            sortName: 'relfrozenxid_age',
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
            uniqueId: "table_name",
            showToggle: true,
            showExport: true,
            exportDataType: "all",
            cardView: false,
            detailView: false,
            locale: 'zh-CN',
            toolbar: "#toolbar",
            queryParamsType: 'limit',
            queryParams: function (params) {
                return {
                    offset: params.offset,
                    limit: params.limit,
                    instance_name: $("#instance_name").val(),
                    db_name: $("#pgsql_vacuum_db").val(),
                    schema_name: $("#pgsql_vacuum_schema").val()
                }
            },
            columns: vacuumListColumns,
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
    $("#pgsql_vacuum_search").click(function () {
        get_pgsql_vacuum_list();
    });

    $("#pgsql_vacuum_reset").click(function () {
        $("#pgsql_vacuum_db").selectpicker('val', "");
        $("#pgsql_vacuum_schema").selectpicker('val', "");
        pgsqlVacuumFilterInstance = "";
        load_pgsql_vacuum_filters(true);
        get_pgsql_vacuum_list();
    });

    $("#pgsql_vacuum_db").change(function () {
        $("#pgsql_vacuum_schema").selectpicker('val', "");
        pgsqlVacuumFilterInstance = "";
        load_pgsql_vacuum_filters(true);
    });
});
