// get_pubsub_list函数表格的格式化信息
// 0.数据库类型； 1.字段映射，2.详细信息的处理函数
let pubsubListTableInfos = [
    [
        'pgsql',
        [{
            title: '类型',
            field: 'object_type',
            sortable: true,
            formatter: function (value, row, index) {
                if (value === 'publication') {
                    return '发布';
                }
                if (value === 'subscription') {
                    return '订阅';
                }
                return value;
            }
        }, {
            title: '名称',
            field: 'object_name',
            sortable: true
        }, {
            title: '启用',
            field: 'enabled',
            sortable: true
        }, {
            title: 'Owner',
            field: 'owner_name',
            sortable: true
        }, {
            title: '数据库',
            field: 'database_name',
            sortable: true
        }, {
            title: '发布名称',
            field: 'publication_names',
            sortable: true
        }, {
            title: '表',
            field: 'table_name',
            sortable: true
        }, {
            title: '操作',
            field: 'operations',
            sortable: true
        }, {
            title: '订阅PID',
            field: 'subscription_pid',
            sortable: true
        }, {
            title: 'Slot',
            field: 'slot_name',
            sortable: true
        }, {
            title: '同步提交',
            field: 'sync_commit',
            sortable: true,
            visible: false
        }, {
            title: '接收LSN',
            field: 'received_lsn',
            sortable: true,
            visible: false
        }, {
            title: '最新结束LSN',
            field: 'latest_end_lsn',
            sortable: true,
            visible: false
        }, {
            title: '延迟(秒)',
            field: 'lag_seconds',
            sortable: true
        }, {
            title: '发送时间',
            field: 'last_msg_send_time',
            sortable: true,
            visible: false
        }, {
            title: '接收时间',
            field: 'last_msg_receipt_time',
            sortable: true,
            visible: false
        }, {
            title: '最新结束时间',
            field: 'latest_end_time',
            sortable: true
        }, {
            title: '连接信息',
            field: 'conninfo',
            formatter: function (value, row, index) {
                return truncateText(value, 60);
            }
        }, {
            title: '完整连接信息',
            field: 'conninfo',
            visible: false
        }],
        function (index, row) {
            var html = [];
            if (row.conninfo) {
                html.push('<h5>连接信息</h5><span>' + row.conninfo + '</span>');
            }
            if (row.publication_names) {
                html.push('<h5>发布名称</h5><span>' + row.publication_names + '</span>');
            }
            return html.join('');
        }
    ]
]

// 问题诊断--发布订阅列表
function get_pubsub_list() {
    $("#command-div").hide();
    $("#process-toolbar").hide();
    if ($("#instance_name").val()) {
        $('#pubsub-list').bootstrapTable('destroy').bootstrapTable({
            escape: true,
            method: 'post',
            contentType: "application/x-www-form-urlencoded",
            url: "/db_diagnostic/pubsub/",
            striped: true,
            cache: false,
            pagination: true,
            sortable: true,
            sortName: 'object_name',
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
            uniqueId: "object_name",
            showToggle: true,
            showExport: true,
            exportDataType: "all",
            cardView: false,
            detailView: true,
            detailFormatter: pubsubListDetailFormatCallback,
            locale: 'zh-CN',
            toolbar: "#toolbar",
            queryParamsType: 'limit',
            queryParams: function (params) {
                return {
                    instance_name: $("#instance_name").val()
                }
            },
            columns: pubsubListColumns,
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
