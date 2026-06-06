// get_replication_list函数表格的格式化信息
// 0.数据库类型； 1.字段映射，2.详细信息的处理函数
let replicationListTableInfos = [
    [
        'pgsql',
        [{
            title: 'PID',
            field: 'pid',
            sortable: true
        }, {
            title: '复制用户',
            field: 'usename',
            sortable: true
        }, {
            title: '应用名称',
            field: 'application_name',
            sortable: true
        }, {
            title: '客户端地址',
            field: 'client_addr',
            sortable: true
        }, {
            title: '状态',
            field: 'state',
            sortable: true
        }, {
            title: '同步状态',
            field: 'sync_state',
            sortable: true
        }, {
            title: '已发送LSN',
            field: 'sent_lsn',
            sortable: true
        }, {
            title: '已写入LSN',
            field: 'write_lsn',
            sortable: true
        }, {
            title: '已刷盘LSN',
            field: 'flush_lsn',
            sortable: true
        }, {
            title: '已回放LSN',
            field: 'replay_lsn',
            sortable: true
        }, {
            title: '回放延迟(bytes)',
            field: 'replay_lag_bytes',
            sortable: true
        }, {
            title: '刷盘延迟(bytes)',
            field: 'flush_lag_bytes',
            sortable: true,
            visible: false
        }, {
            title: '写入延迟(bytes)',
            field: 'write_lag_bytes',
            sortable: true,
            visible: false
        }, {
            title: '写入延迟',
            field: 'write_lag',
            sortable: true,
            visible: false
        }, {
            title: '刷盘延迟',
            field: 'flush_lag',
            sortable: true,
            visible: false
        }, {
            title: '回放延迟',
            field: 'replay_lag',
            sortable: true
        }, {
            title: '同步优先级',
            field: 'sync_priority',
            sortable: true,
            visible: false
        }, {
            title: '后端启动时间',
            field: 'backend_start',
            sortable: true
        }, {
            title: '回复时间',
            field: 'reply_time',
            sortable: true
        }, {
            title: '客户端主机名',
            field: 'client_hostname',
            sortable: true,
            visible: false
        }, {
            title: '客户端端口',
            field: 'client_port',
            sortable: true,
            visible: false
        }, {
            title: 'Backend XMIN',
            field: 'backend_xmin',
            sortable: true,
            visible: false
        }],
        function (index, row) {
            var html = [];
            html.push('<h5>LSN</h5><span>sent=' + (row.sent_lsn || '') + ', write=' + (row.write_lsn || '') + ', flush=' + (row.flush_lsn || '') + ', replay=' + (row.replay_lsn || '') + '</span>');
            html.push('<h5>延迟</h5><span>write=' + (row.write_lag || '') + ', flush=' + (row.flush_lag || '') + ', replay=' + (row.replay_lag || '') + '</span>');
            return html.join('');
        }
    ]
]

let replicationSlotsListTableInfos = [
    [
        'pgsql',
        [{
            title: 'Slot名称',
            field: 'slot_name',
            sortable: true
        }, {
            title: '类型',
            field: 'slot_type',
            sortable: true
        }, {
            title: '插件',
            field: 'plugin',
            sortable: true
        }, {
            title: '数据库',
            field: 'database_name',
            sortable: true
        }, {
            title: '活跃',
            field: 'active',
            sortable: true
        }, {
            title: '活跃PID',
            field: 'active_pid',
            sortable: true
        }, {
            title: 'restart LSN',
            field: 'restart_lsn',
            sortable: true
        }, {
            title: 'confirmed flush LSN',
            field: 'confirmed_flush_lsn',
            sortable: true
        }, {
            title: '保留WAL',
            field: 'retained_wal_size',
            sortable: true
        }, {
            title: '保留WAL(bytes)',
            field: 'retained_wal_bytes',
            sortable: true,
            visible: false
        }, {
            title: 'WAL状态',
            field: 'wal_status',
            sortable: true
        }, {
            title: '安全WAL大小',
            field: 'safe_wal_size',
            sortable: true,
            visible: false
        }, {
            title: '临时',
            field: 'temporary',
            sortable: true,
            visible: false
        }, {
            title: 'XMIN',
            field: 'xmin',
            sortable: true,
            visible: false
        }, {
            title: 'Catalog XMIN',
            field: 'catalog_xmin',
            sortable: true,
            visible: false
        }],
        function (index, row) {
            var html = [];
            html.push('<h5>LSN</h5><span>restart=' + (row.restart_lsn || '') + ', confirmed_flush=' + (row.confirmed_flush_lsn || '') + '</span>');
            html.push('<h5>WAL保留</h5><span>' + (row.retained_wal_size || '') + ' (' + (row.retained_wal_bytes || '') + ' bytes)</span>');
            return html.join('');
        }
    ]
]

function get_pgsql_replication_list() {
    $("#command-div").hide();
    $("#process-toolbar").hide();
    if ($("#instance_name").val()) {
        $('#replication-list').bootstrapTable('destroy').bootstrapTable({
            escape: true,
            method: 'post',
            contentType: "application/x-www-form-urlencoded",
            url: "/db_diagnostic/pgsql_replication/",
            striped: true,
            cache: false,
            pagination: true,
            sortable: true,
            sortName: 'application_name',
            sortOrder: "asc",
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
            detailFormatter: replicationListDetailFormatCallback,
            locale: 'zh-CN',
            toolbar: "#toolbar",
            queryParamsType: 'limit',
            queryParams: function (params) {
                return {
                    instance_name: $("#instance_name").val()
                }
            },
            columns: replicationListColumns,
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

function get_pgsql_replication_slots_list() {
    $("#command-div").hide();
    $("#process-toolbar").hide();
    if ($("#instance_name").val()) {
        $('#replication-slots-list').bootstrapTable('destroy').bootstrapTable({
            escape: true,
            method: 'post',
            contentType: "application/x-www-form-urlencoded",
            url: "/db_diagnostic/pgsql_replication_slots/",
            striped: true,
            cache: false,
            pagination: true,
            sortable: true,
            sortName: 'retained_wal_bytes',
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
            uniqueId: "slot_name",
            showToggle: true,
            showExport: true,
            exportDataType: "all",
            cardView: false,
            detailView: true,
            detailFormatter: replicationSlotsListDetailFormatCallback,
            locale: 'zh-CN',
            toolbar: "#toolbar",
            queryParamsType: 'limit',
            queryParams: function (params) {
                return {
                    instance_name: $("#instance_name").val()
                }
            },
            columns: replicationSlotsListColumns,
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
