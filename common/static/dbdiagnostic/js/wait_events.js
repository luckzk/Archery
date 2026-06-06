let waitEventsListTableInfos = [
    [
        'pgsql',
        [{
            title: '状态',
            field: 'state',
            sortable: true
        }, {
            title: '等待类型',
            field: 'wait_event_type',
            sortable: true
        }, {
            title: '等待事件',
            field: 'wait_event',
            sortable: true
        }, {
            title: '会话数',
            field: 'session_count',
            sortable: true
        }, {
            title: '最大等待(s)',
            field: 'max_wait_seconds',
            sortable: true
        }, {
            title: '最大查询(s)',
            field: 'max_query_seconds',
            sortable: true
        }, {
            title: 'Active数',
            field: 'active_count',
            sortable: true
        }, {
            title: 'Idle in Trx数',
            field: 'idle_in_transaction_count',
            sortable: true
        }, {
            title: '最早查询开始',
            field: 'oldest_query_start',
            sortable: true,
            visible: false
        }, {
            title: '最早状态变更',
            field: 'oldest_state_change',
            sortable: true,
            visible: false
        }, {
            title: '数据库',
            field: 'database_names',
            sortable: true
        }, {
            title: '用户',
            field: 'user_names',
            sortable: true
        }, {
            title: '应用',
            field: 'application_names',
            sortable: true,
            visible: false
        }]
    ]
]

function get_pgsql_wait_events_list() {
    $("#command-div").hide();
    $("#process-toolbar").hide();
    if ($("#instance_name").val()) {
        $('#wait-events-list').bootstrapTable('destroy').bootstrapTable({
            escape: true,
            method: 'post',
            contentType: "application/x-www-form-urlencoded",
            url: "/db_diagnostic/pgsql_wait_events/",
            striped: true,
            cache: false,
            pagination: true,
            sortable: true,
            sortName: 'session_count',
            sortOrder: "desc",
            sidePagination: "client",
            pageNumber: 1,
            pageSize: 30,
            pageList: [20, 30, 50, 100],
            search: true,
            strictSearch: false,
            showColumns: true,
            showRefresh: true,
            minimumCountColumns: 2,
            clickToSelect: true,
            uniqueId: "wait_event",
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
                    instance_name: $("#instance_name").val()
                }
            },
            columns: waitEventsListColumns,
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
