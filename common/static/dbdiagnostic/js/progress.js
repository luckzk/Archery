let progressListTableInfos = [
    [
        'pgsql',
        [{
            title: '类型',
            field: 'progress_type',
            sortable: true
        }, {
            title: 'PID',
            field: 'pid',
            sortable: true
        }, {
            title: '数据库',
            field: 'database_name',
            sortable: true
        }, {
            title: '对象',
            field: 'relation_name',
            sortable: true
        }, {
            title: '阶段',
            field: 'phase',
            sortable: true
        }, {
            title: '进度(%)',
            field: 'progress_percent',
            sortable: true
        }, {
            title: '已处理块',
            field: 'blocks_done',
            sortable: true
        }, {
            title: '总块',
            field: 'blocks_total',
            sortable: true
        }, {
            title: '用户',
            field: 'usename',
            sortable: true
        }, {
            title: '应用',
            field: 'application_name',
            sortable: true
        }, {
            title: '客户端',
            field: 'client_addr',
            sortable: true
        }, {
            title: '已运行(s)',
            field: 'elapsed_time_seconds',
            sortable: true
        }, {
            title: '等待类型',
            field: 'wait_event_type',
            sortable: true,
            visible: false
        }, {
            title: '等待事件',
            field: 'wait_event',
            sortable: true,
            visible: false
        }, {
            title: '命令',
            field: 'command',
            sortable: true,
            visible: false
        }, {
            title: 'Heap已扫描块',
            field: 'heap_blks_scanned',
            sortable: true,
            visible: false
        }, {
            title: 'Heap总块',
            field: 'heap_blks_total',
            sortable: true,
            visible: false
        }, {
            title: '索引Vacuum次数',
            field: 'index_vacuum_count',
            sortable: true,
            visible: false
        }, {
            title: 'Dead Tuple上限',
            field: 'max_dead_tuples',
            sortable: true,
            visible: false
        }, {
            title: 'Dead Tuple数量',
            field: 'num_dead_tuples',
            sortable: true,
            visible: false
        }, {
            title: 'Tuple已处理',
            field: 'tuples_done',
            sortable: true,
            visible: false
        }, {
            title: 'Tuple总数',
            field: 'tuples_total',
            sortable: true,
            visible: false
        }, {
            title: 'SQL',
            field: 'query',
            sortable: true,
            visible: false
        }],
        function (index, row) {
            var html = [];
            html.push('<h5>SQL</h5><pre>' + (row.query || '') + '</pre>');
            html.push('<h5>进度</h5><span>blocks=' + (row.blocks_done || 0) + '/' + (row.blocks_total || 0) + ', tuples=' + (row.tuples_done || '') + '/' + (row.tuples_total || '') + '</span>');
            html.push('<h5>等待</h5><span>' + (row.wait_event_type || '') + ' ' + (row.wait_event || '') + '</span>');
            return html.join('');
        }
    ]
]

function get_pgsql_progress_list() {
    $("#command-div").hide();
    $("#process-toolbar").hide();
    if ($("#instance_name").val()) {
        $('#progress-list').bootstrapTable('destroy').bootstrapTable({
            escape: true,
            method: 'post',
            contentType: "application/x-www-form-urlencoded",
            url: "/db_diagnostic/pgsql_progress/",
            striped: true,
            cache: false,
            pagination: true,
            sortable: true,
            sortName: 'elapsed_time_seconds',
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
            uniqueId: "pid",
            showToggle: true,
            showExport: true,
            exportDataType: "all",
            cardView: false,
            detailView: true,
            detailFormatter: progressListDetailFormatCallback,
            locale: 'zh-CN',
            toolbar: "#toolbar",
            queryParamsType: 'limit',
            queryParams: function (params) {
                return {
                    instance_name: $("#instance_name").val()
                }
            },
            columns: progressListColumns,
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
