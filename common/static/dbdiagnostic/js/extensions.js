let extensionsListColumns = [
    {
        title: '插件名',
        field: 'extension_name',
        sortable: true
    }, {
        title: '已安装',
        field: 'installed',
        sortable: true
    }, {
        title: '默认版本',
        field: 'default_version',
        sortable: true
    }, {
        title: '安装版本',
        field: 'installed_version',
        sortable: true
    }, {
        title: '安装版本明细',
        field: 'installed_version_detail',
        sortable: true,
        visible: false
    }, {
        title: 'Schema',
        field: 'schema_name',
        sortable: true
    }, {
        title: '可迁移',
        field: 'relocatable',
        sortable: true,
        visible: false
    }, {
        title: '说明',
        field: 'description',
        sortable: true
    }, {
        title: '配置OIDs',
        field: 'config_oids',
        sortable: true,
        visible: false
    }, {
        title: '条件',
        field: 'conditions',
        sortable: true,
        visible: false
    }
]

var pgsqlExtensionsFilterInstance = "";

function refresh_extensions_toolbar() {
    if (current_instance_db_type() === 'pgsql') {
        $("#pgsql-extensions-toolbar").show();
        if (sessionStorage.getItem('diagnostic_active_li_id') === 'extensions_tab') {
            load_pgsql_extensions_filters(false);
        }
    } else {
        $("#pgsql-extensions-toolbar").hide();
        $("#pgsql_extensions_db").empty().selectpicker('render').selectpicker('refresh');
        pgsqlExtensionsFilterInstance = "";
    }
}

function fill_pgsql_extensions_select(selector, values, selectedValue) {
    var select = $(selector);
    select.empty();
    select.append("<option value=\"\">默认</option>");
    (values || []).forEach(function (value) {
        select.append("<option value=\"" + value + "\">" + value + "</option>");
    });
    select.selectpicker('render');
    select.selectpicker('refresh');
    select.selectpicker('val', selectedValue || "");
}

function load_pgsql_extensions_filters(force) {
    var instanceName = $("#instance_name").val();
    if (!instanceName || current_instance_db_type() !== 'pgsql') {
        return;
    }
    if (!force && pgsqlExtensionsFilterInstance === instanceName) {
        return;
    }
    $.ajax({
        type: "get",
        url: "/db_diagnostic/pgsql_tablespace_filters/",
        dataType: "json",
        data: {
            instance_name: instanceName,
            db_name: $("#pgsql_extensions_db").val()
        },
        success: function (data) {
            if (data.status === 0) {
                var result = data.data || {};
                var selectedDb = $("#pgsql_extensions_db").val() || result.selected_db || "";
                fill_pgsql_extensions_select("#pgsql_extensions_db", result.databases, selectedDb);
                pgsqlExtensionsFilterInstance = instanceName;
            } else {
                alert(data.msg);
            }
        }
    })
}

function get_pgsql_extensions_list() {
    $("#command-div").hide();
    $("#process-toolbar").hide();
    refresh_extensions_toolbar();
    if ($("#instance_name").val()) {
        $('#extensions-list').bootstrapTable('destroy').bootstrapTable({
            escape: true,
            method: 'post',
            contentType: "application/x-www-form-urlencoded",
            url: "/db_diagnostic/pgsql_extensions/",
            striped: true,
            cache: false,
            pagination: true,
            sortable: true,
            sortName: 'installed',
            sortOrder: "desc",
            sidePagination: "client",
            pageNumber: 1,
            pageSize: 50,
            pageList: [20, 50, 100, 500],
            search: true,
            strictSearch: false,
            showColumns: true,
            showRefresh: true,
            minimumCountColumns: 2,
            clickToSelect: true,
            uniqueId: "extension_name",
            showToggle: true,
            showExport: true,
            exportDataType: "all",
            cardView: false,
            detailView: false,
            locale: 'zh-CN',
            toolbar: "#pgsql-extensions-toolbar",
            queryParamsType: 'limit',
            queryParams: function (params) {
                return {
                    instance_name: $("#instance_name").val(),
                    db_name: $("#pgsql_extensions_db").val()
                }
            },
            columns: extensionsListColumns,
            onLoadSuccess: function (data) {
                if (data.status !== 0) {
                    alert("数据加载失败！" + data.msg);
                }
            },
            onLoadError: onLoadErrorCallback,
            onSearch: function (e) {
                queryParams(e)
            }
        });
    }
}

$(function () {
    $("#pgsql_extensions_search").click(function () {
        get_pgsql_extensions_list();
    });

    $("#pgsql_extensions_reset").click(function () {
        $("#pgsql_extensions_db").selectpicker('val', "");
        pgsqlExtensionsFilterInstance = "";
        load_pgsql_extensions_filters(true);
        get_pgsql_extensions_list();
    });

    $("#pgsql_extensions_db").change(function () {
        get_pgsql_extensions_list();
    });
});
