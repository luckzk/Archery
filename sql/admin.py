# -*- coding: UTF-8 -*-
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.http import JsonResponse
from django.urls import path

# Register your models here.
from django.forms import PasswordInput

from .models import (
    Users,
    Instance,
    SqlWorkflow,
    SqlWorkflowContent,
    QueryLog,
    SqlQueryKnowledge,
    SqlQueryFavorite,
    SqlQueryPreference,
    DataMaskingColumns,
    DataMaskingRules,
    AliyunRdsConfig,
    CloudAccessKey,
    ResourceGroup,
    QueryPrivilegesApply,
    QueryPrivileges,
    InstanceAccount,
    InstanceDatabase,
    ArchiveConfig,
    WorkflowAudit,
    WorkflowLog,
    ParamTemplate,
    ParamHistory,
    InstanceTag,
    Tunnel,
    AuditEntry,
    TwoFactorAuthConfig,
    PgSQLMetricDefinition,
    DBDiagnosticSQLTemplate,
    PgSQLMigrationTask,
    PgSQLMigrationTaskLog,
    PgSQLMigrationSequenceResult,
    PgSQLMigrationDataCheckResult,
)

from sql.form import TunnelForm, InstanceForm
from sql.engines import get_engine


# 用户管理
@admin.register(Users)
class UsersAdmin(UserAdmin):
    list_display = (
        "id",
        "username",
        "display",
        "email",
        "is_superuser",
        "is_staff",
        "is_active",
    )
    search_fields = ("id", "username", "display", "email")
    list_display_links = (
        "id",
        "username",
    )
    ordering = ("id",)
    # 编辑页显示内容
    fieldsets = (
        ("认证信息", {"fields": ("username", "password")}),
        (
            "个人信息",
            {
                "fields": (
                    "display",
                    "email",
                    "ding_user_id",
                    "wx_user_id",
                    "feishu_open_id",
                )
            },
        ),
        (
            "权限信息",
            {
                "fields": (
                    "is_superuser",
                    "is_active",
                    "is_staff",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("资源组", {"fields": ("resource_group",)}),
        ("其他信息", {"fields": ("date_joined", "failed_login_count")}),
    )
    # 添加页显示内容
    add_fieldsets = (
        ("认证信息", {"fields": ("username", "password1", "password2")}),
        (
            "个人信息",
            {
                "fields": (
                    "display",
                    "email",
                    "ding_user_id",
                    "wx_user_id",
                    "feishu_open_id",
                )
            },
        ),
        (
            "权限信息",
            {
                "fields": (
                    "is_superuser",
                    "is_active",
                    "is_staff",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("资源组", {"fields": ("resource_group",)}),
    )
    filter_horizontal = ("groups", "user_permissions", "resource_group")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups", "resource_group")


# PostgreSQL实时指标定义
@admin.register(PgSQLMetricDefinition)
class PgSQLMetricDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "metric_key",
        "metric_name",
        "enabled",
        "db_name",
        "value_column",
        "timeout_ms",
        "update_time",
    )
    list_display_links = ("id", "metric_key")
    search_fields = ("metric_key", "metric_name", "description", "sql")
    list_filter = ("enabled", "instances")
    filter_horizontal = ("instances",)
    fieldsets = (
        (
            "基础信息",
            {"fields": ("metric_key", "metric_name", "description", "enabled")},
        ),
        (
            "SQL约定",
            {
                "fields": ("sql", "db_name", "value_column", "timeout_ms", "instances"),
                "description": "输入：页面选择 PostgreSQL 实例，系统在该实例上执行单条 SELECT；采集数据库为空时使用实例默认库。输出：建议返回 value 列作为指标值，也可以通过取值字段指定其他列。",
            },
        ),
    )


# DB诊断会话管理自定义SQL
@admin.register(DBDiagnosticSQLTemplate)
class DBDiagnosticSQLTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "db_type",
        "diagnostic_type",
        "template_name",
        "enabled",
        "db_name",
        "timeout_ms",
        "update_time",
    )
    list_display_links = ("id", "template_name")
    search_fields = ("template_name", "description", "sql")
    list_filter = ("db_type", "diagnostic_type", "enabled")
    fieldsets = (
        (
            "基础信息",
            {
                "fields": (
                    "db_type",
                    "diagnostic_type",
                    "template_name",
                    "description",
                    "enabled",
                ),
                "description": "当前用于 /dbdiagnostic/ 会话管理页面，支持 PgSQL 进程状态、PgSQL事务信息、PgSQL Top表空间、PgSQL锁信息、PgSQL发布订阅、PgSQL复制状态、PgSQL复制Slot、PgSQL Vacuum风险、PgSQL Progress进度、PgSQL等待事件聚合、PgSQL索引诊断和 PgSQL插件展示。",
            },
        ),
        (
            "SQL",
            {
                "fields": ("sql", "db_name", "timeout_ms"),
                "description": "只允许单条 SELECT。PgSQL进程状态 SQL 可包含 $state_not_idle$ 占位符，页面选择 Not Idle 时会替换为状态过滤条件。",
            },
        ),
        (
            "输出字段约定",
            {
                "fields": (),
                "description": "PgSQL进程状态字段需匹配 pgsqlDiagnosticInfo.fieldsProcesslist；PgSQL事务信息字段需返回 pid、datname、usename、state、xact_start、query；PgSQL Top表空间字段需返回 schema_name、table_name、total_size_bytes、total_size；PgSQL锁信息字段需匹配 dbdiagnostic.html 中 pgsql 锁信息列，如 waiting_pid、blocking_pid、blocking_chain、waiting_query、blocking_query；PgSQL发布订阅字段需返回 object_type、object_name、enabled、owner_name、database_name；PgSQL复制状态字段需返回 pid、usename、application_name、client_addr、state、sync_state；PgSQL复制Slot字段需返回 slot_name、slot_type、active、restart_lsn；PgSQL Vacuum风险字段需返回 schema_name、table_name、n_live_tup、n_dead_tup、dead_tuple_ratio、relfrozenxid_age；PgSQL Progress进度字段需返回 progress_type、pid、database_name、relation_name、phase、progress_percent、blocks_done、blocks_total、query；PgSQL等待事件聚合字段需返回 state、wait_event_type、wait_event、session_count、max_wait_seconds、max_query_seconds；PgSQL索引诊断字段需返回 diagnostic_type、schema_name、table_name、index_name、index_size、idx_scan、seq_scan、is_valid、is_unique、reason；PgSQL插件展示字段需返回 extension_name、installed、default_version、installed_version。",
            },
        ),
    )


# 用户2fa管理
@admin.register(TwoFactorAuthConfig)
class TwoFactorAuthConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "auth_type", "phone", "secret_key", "user_id")


# 资源组管理
@admin.register(ResourceGroup)
class ResourceGroupAdmin(admin.ModelAdmin):
    list_display = (
        "group_id",
        "group_name",
        "ding_webhook",
        "feishu_webhook",
        "qywx_webhook",
        "is_deleted",
    )
    exclude = (
        "group_parent_id",
        "group_sort",
        "group_level",
    )


# 实例标签配置
@admin.register(InstanceTag)
class InstanceTagAdmin(admin.ModelAdmin):
    list_display = ("id", "tag_code", "tag_name", "active", "create_time")
    list_display_links = (
        "id",
        "tag_code",
    )
    fieldsets = (
        (
            None,
            {
                "fields": ("tag_code", "tag_name", "active"),
            },
        ),
    )

    # 不支持修改标签代码
    def get_readonly_fields(self, request, obj=None):
        return ("tag_code",) if obj else ()


# 实例管理
@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
    form = InstanceForm
    change_form_template = "admin/sql/instance/change_form.html"
    list_display = (
        "id",
        "instance_name",
        "db_type",
        "type",
        "host",
        "port",
        "user",
        "create_time",
    )
    search_fields = ["instance_name", "host", "port", "user"]
    list_filter = ("db_type", "type", "instance_tag")

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == "password":
            kwargs["widget"] = PasswordInput(render_value=True)
        return super(InstanceAdmin, self).formfield_for_dbfield(db_field, **kwargs)

    # 阿里云实例关系配置
    class AliRdsConfigInline(admin.TabularInline):
        model = AliyunRdsConfig

    # 实例资源组关联配置
    filter_horizontal = (
        "resource_group",
        "instance_tag",
    )

    inlines = [AliRdsConfigInline]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "test-pgsql-connection/",
                self.admin_site.admin_view(self.test_pgsql_connection),
                name="sql_instance_test_pgsql_connection",
            ),
        ]
        return custom_urls + urls

    def test_pgsql_connection(self, request):
        if request.method != "POST":
            return JsonResponse({"status": 1, "msg": "仅支持POST请求"})

        if request.POST.get("db_type") != "pgsql":
            return JsonResponse({"status": 1, "msg": "当前仅支持测试PgSQL实例连接"})

        instance = Instance(
            instance_name=request.POST.get("instance_name") or "admin-pgsql-test",
            type=request.POST.get("type") or "master",
            db_type="pgsql",
            mode=request.POST.get("mode") or "",
            host=request.POST.get("host") or "",
            port=request.POST.get("port") or 0,
            user=request.POST.get("user") or "",
            password=request.POST.get("password") or "",
            db_name=request.POST.get("db_name") or "",
            charset=request.POST.get("charset") or "",
            is_ssl=request.POST.get("is_ssl") == "on",
            verify_ssl=request.POST.get("verify_ssl") == "on",
        )

        tunnel_id = request.POST.get("tunnel")
        if tunnel_id:
            instance.tunnel_id = tunnel_id

        cursor = None
        try:
            engine = get_engine(instance=instance)
            conn = engine.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
        except Exception as e:
            return JsonResponse({"status": 1, "msg": f"无法连接实例：\n{str(e)}"})
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if "engine" in locals() and getattr(engine, "conn", None):
                try:
                    engine.conn.close()
                except Exception:
                    pass

        return JsonResponse({"status": 0, "msg": "连接测试成功"})


# SSH隧道
@admin.register(Tunnel)
class TunnelAdmin(admin.ModelAdmin):
    list_display = ("id", "tunnel_name", "host", "port", "create_time")
    list_display_links = (
        "id",
        "tunnel_name",
    )
    search_fields = ("id", "tunnel_name")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "tunnel_name",
                    "host",
                    "port",
                    "user",
                    "password",
                    "pkey_path",
                    "pkey_password",
                    "pkey",
                ),
            },
        ),
    )
    ordering = ("id",)
    # 添加页显示内容
    add_fieldsets = (
        ("隧道信息", {"fields": ("tunnel_name", "host", "port")}),
        (
            "连接信息",
            {"fields": ("user", "password", "pkey_path", "pkey_password", "pkey")},
        ),
    )
    form = TunnelForm

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name in ["password", "pkey_password"]:
            kwargs["widget"] = PasswordInput(render_value=True)
        return super(TunnelAdmin, self).formfield_for_dbfield(db_field, **kwargs)

    # 不支持修改标签代码
    def get_readonly_fields(self, request, obj=None):
        return ("id",) if obj else ()


# SQL工单内容
class SqlWorkflowContentInline(admin.TabularInline):
    model = SqlWorkflowContent


# SQL工单
@admin.register(SqlWorkflow)
class SqlWorkflowAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "workflow_name",
        "group_name",
        "instance",
        "engineer_display",
        "create_time",
        "status",
        "is_backup",
    )
    search_fields = [
        "id",
        "workflow_name",
        "engineer_display",
        "sqlworkflowcontent__sql_content",
    ]
    list_filter = (
        "group_name",
        "instance__instance_name",
        "status",
        "syntax_type",
    )
    list_display_links = (
        "id",
        "workflow_name",
    )
    inlines = [SqlWorkflowContentInline]


# SQL查询日志
@admin.register(QueryLog)
class QueryLogAdmin(admin.ModelAdmin):
    list_display = (
        "instance_name",
        "db_name",
        "sqllog",
        "effect_row",
        "cost_time",
        "user_display",
        "create_time",
    )
    search_fields = ["sqllog", "user_display"]
    list_filter = (
        "instance_name",
        "db_name",
        "user_display",
        "priv_check",
        "hit_rule",
        "masking",
    )


@admin.register(SqlQueryKnowledge)
class SqlQueryKnowledgeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "scene",
        "engines",
        "username",
        "instance_name",
        "db_name",
        "sys_time",
    )
    search_fields = ("name", "scene", "sql", "username", "user_display")
    list_filter = ("username", "scene", "engines")
    readonly_fields = ("create_time", "sys_time")


@admin.register(SqlQueryFavorite)
class SqlQueryFavoriteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "alias",
        "username",
        "instance_name",
        "db_name",
        "source_query_log_id",
        "sys_time",
    )
    search_fields = (
        "alias",
        "sql",
        "username",
        "user_display",
        "instance_name",
        "db_name",
    )
    list_filter = ("username", "instance_name", "db_name")
    readonly_fields = ("create_time", "sys_time")


@admin.register(SqlQueryPreference)
class SqlQueryPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "username",
        "theme",
        "resource_tab",
        "mysql_tab",
        "sys_time",
    )
    search_fields = ("username", "user_display")
    list_filter = ("theme", "resource_tab", "mysql_tab")
    readonly_fields = ("create_time", "sys_time")


# 查询权限列表
@admin.register(QueryPrivileges)
class QueryPrivilegesAdmin(admin.ModelAdmin):
    list_display = (
        "privilege_id",
        "user_display",
        "instance",
        "db_name",
        "table_name",
        "valid_date",
        "limit_num",
        "create_time",
    )
    search_fields = ["user_display", "instance__instance_name"]
    list_filter = (
        "user_display",
        "instance",
        "db_name",
        "table_name",
    )


# 查询权限申请记录
@admin.register(QueryPrivilegesApply)
class QueryPrivilegesApplyAdmin(admin.ModelAdmin):
    list_display = (
        "apply_id",
        "user_display",
        "group_name",
        "instance",
        "valid_date",
        "limit_num",
        "create_time",
    )
    search_fields = ["user_display", "instance__instance_name", "db_list", "table_list"]
    list_filter = ("user_display", "group_name", "instance")


# 脱敏字段页面定义
@admin.register(DataMaskingColumns)
class DataMaskingColumnsAdmin(admin.ModelAdmin):
    list_display = (
        "column_id",
        "rule_type",
        "active",
        "instance",
        "table_schema",
        "table_name",
        "column_name",
        "column_comment",
        "create_time",
    )
    search_fields = ["table_name", "column_name"]
    list_filter = ("rule_type", "active", "instance__instance_name")


# 脱敏规则页面定义
@admin.register(DataMaskingRules)
class DataMaskingRulesAdmin(admin.ModelAdmin):
    list_display = (
        "rule_type",
        "rule_regex",
        "hide_group",
        "rule_desc",
        "sys_time",
    )


# 工作流审批列表
@admin.register(WorkflowAudit)
class WorkflowAuditAdmin(admin.ModelAdmin):
    list_display = (
        "workflow_title",
        "group_name",
        "workflow_type",
        "current_status",
        "create_user_display",
        "create_time",
    )
    search_fields = ["workflow_title", "create_user_display"]
    list_filter = (
        "create_user_display",
        "group_name",
        "workflow_type",
        "current_status",
    )


# 工作流日志表
@admin.register(WorkflowLog)
class WorkflowLogAdmin(admin.ModelAdmin):
    list_display = (
        "operation_type_desc",
        "operation_info",
        "operator_display",
        "operation_time",
    )
    list_filter = ("operation_type_desc", "operator_display")


# 实例数据库列表
@admin.register(InstanceDatabase)
class InstanceDatabaseAdmin(admin.ModelAdmin):
    list_display = ("db_name", "owner_display", "instance", "remark")
    search_fields = ("db_name",)
    list_filter = ("instance", "owner_display")
    list_display_links = ("db_name",)

    # 仅支持修改备注
    def get_readonly_fields(self, request, obj=None):
        return ("instance", "owner", "owner_display") if obj else ()


# 实例用户列表
@admin.register(InstanceAccount)
class InstanceAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "host", "password", "instance", "remark")
    search_fields = ("user", "host")
    list_filter = ("instance", "host")
    list_display_links = ("user",)

    # 仅支持修改备注
    def get_readonly_fields(self, request, obj=None):
        return (
            (
                "user",
                "host",
                "instance",
            )
            if obj
            else ()
        )


# 实例参数配置表
@admin.register(ParamTemplate)
class ParamTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "variable_name",
        "db_type",
        "pgsql_query_status",
        "default_value",
        "editable",
        "valid_values",
    )
    search_fields = ("variable_name", "description", "param_query_sql")
    list_filter = ("db_type", "editable", "param_query_enabled")
    list_display_links = ("variable_name",)
    def pgsql_query_status(self, obj):
        if obj.db_type != "pgsql" or not obj.param_query_sql:
            return "-"
        return "启用" if obj.param_query_enabled else "禁用"

    pgsql_query_status.short_description = "PgSQL SQL状态"

    fieldsets = (
        (
            "基础信息",
            {
                "fields": (
                    "db_type",
                    "variable_name",
                    "default_value",
                    "editable",
                    "valid_values",
                    "description",
                ),
                "description": "MySQL 使用具体参数名匹配实例运行参数；PostgreSQL 的参数名可作为配置名称。",
                "classes": ("paramtemplate-base-fields",),
            },
        ),
        (
            "PostgreSQL参数展示SQL",
            {
                "fields": (
                    "param_query_enabled",
                    "param_query_sql",
                    "param_query_db_name",
                    "param_query_timeout_ms",
                ),
                "description": "仅数据库类型选择 PgSQL 时使用，保留原 PostgreSQL 参数展示SQL配置方式。可配置多条启用 SQL，/instanceparam/ 会全部执行并合并显示。",
                "classes": ("paramtemplate-pgsql-query-fields",),
            },
        ),
    )

    class Media:
        js = ("js/admin_paramtemplate.js",)


# 实例参数修改历史
@admin.register(ParamHistory)
class ParamHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "variable_name",
        "instance",
        "old_var",
        "new_var",
        "user_display",
        "create_time",
    )
    search_fields = ("variable_name",)
    list_filter = ("instance", "user_display")


# 归档配置
@admin.register(ArchiveConfig)
class ArchiveConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "src_instance",
        "src_db_name",
        "src_table_name",
        "dest_instance",
        "dest_db_name",
        "dest_table_name",
        "mode",
        "no_delete",
        "status",
        "state",
        "user_display",
        "create_time",
        "resource_group",
    )
    search_fields = ("title", "src_table_name")
    list_display_links = ("id", "title")
    list_filter = ("src_instance", "src_db_name", "mode", "no_delete", "state")
    # 编辑页显示内容
    fields = (
        "title",
        "resource_group",
        "src_instance",
        "src_db_name",
        "src_table_name",
        "dest_instance",
        "dest_db_name",
        "dest_table_name",
        "mode",
        "condition",
        "sleep",
        "no_delete",
        "state",
        "user_name",
        "user_display",
    )


# 云服务认证信息配置
@admin.register(CloudAccessKey)
class CloudAccessKeyAdmin(admin.ModelAdmin):
    list_display = ("type", "key_id", "key_secret", "remark")


# 登录审计日志
@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = (
        "user_id",
        "user_name",
        "user_display",
        "action",
        "extra_info",
        "action_time",
    )
    list_filter = ("user_id", "user_name", "user_display", "action", "extra_info")


@admin.register(PgSQLMigrationTask)
class PgSQLMigrationTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "source_instance",
        "target_instance",
        "status",
        "user_display",
        "create_time",
        "update_time",
    )
    search_fields = ("name", "description", "user_name", "user_display")
    list_filter = ("status", "source_instance", "target_instance")


@admin.register(PgSQLMigrationTaskLog)
class PgSQLMigrationTaskLogAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "operation", "status", "start_time", "finish_time")
    search_fields = ("task__name", "operation", "message", "details_json")
    list_filter = ("operation", "status")


@admin.register(PgSQLMigrationSequenceResult)
class PgSQLMigrationSequenceResultAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "task",
        "operation",
        "sequence_schema",
        "sequence_name",
        "target_value",
        "should_apply",
        "status",
        "create_time",
    )
    search_fields = ("task__name", "sequence_schema", "sequence_name", "table_name")
    list_filter = ("operation", "status", "should_apply")


@admin.register(PgSQLMigrationDataCheckResult)
class PgSQLMigrationDataCheckResultAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "schema_name", "table_name", "status", "create_time")
    search_fields = ("task__name", "schema_name", "table_name", "checks_json")
    list_filter = ("status",)
