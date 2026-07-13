# -*- coding: UTF-8 -*-
import json
import traceback

from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render

from common.utils.extend_json_encoder import ExtendJSONEncoder
from sql.models import (
    Instance,
    PgSQLMigrationDataCheckResult,
    PgSQLMigrationSequenceResult,
    PgSQLMigrationTask,
    PgSQLMigrationTaskLog,
)
from sql.tool_plugins import tool_plugin_enabled_required
from sql.utils.pgsql_migration import (
    apply_sequence_values,
    build_sequence_preview,
    create_task_log,
    finish_task_log,
    json_dumps,
    json_loads,
    list_tables,
    parse_csv,
    parse_tables,
    run_feature_checks,
    run_table_checks,
    save_data_check_results,
    save_sequence_results,
    set_replica_identity_using_index,
    task_schemas,
    task_tables,
    task_to_dict,
)
from sql.utils.resource_group import user_instances

PGSQL_MIGRATION_PLUGIN_CODE = "pgsql_migration"


def _json_response(payload):
    return HttpResponse(
        json.dumps(payload, cls=ExtendJSONEncoder), content_type="application/json"
    )


def _can_manage_tasks(user):
    return user.is_superuser or user.has_perm("sql.pgsql_migration_mgt")


def _can_delete_task(user, task):
    return _can_manage_tasks(user) or task.user_name == user.username


def _task_for_user(request, task_id):
    task = get_object_or_404(PgSQLMigrationTask, id=task_id)
    if _can_manage_tasks(request.user):
        return task
    visible_ids = set(
        user_instances(request.user, db_type=["pgsql"]).values_list("id", flat=True)
    )
    if (
        task.source_instance_id in visible_ids
        and task.target_instance_id in visible_ids
    ):
        return task
    raise PermissionDenied("无权限访问该迁移任务")


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def page(request):
    instances = user_instances(request.user, db_type=["pgsql"]).order_by(
        "instance_name"
    )
    return render(request, "pgsql_migration.html", {"instances": instances})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def task_detail(request, task_id):
    task = _task_for_user(request, task_id)
    return render(request, "pgsql_migration_detail.html", {"task": task})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def task_list(request):
    limit = int(request.GET.get("limit", 20))
    offset = int(request.GET.get("offset", 0))
    search = request.GET.get("search", "")
    tasks = PgSQLMigrationTask.objects.select_related(
        "source_instance", "target_instance"
    )
    if not _can_manage_tasks(request.user):
        visible_ids = list(
            user_instances(request.user, db_type=["pgsql"]).values_list(
                "id", flat=True
            )
        )
        tasks = tasks.filter(
            source_instance_id__in=visible_ids, target_instance_id__in=visible_ids
        )
    if search:
        tasks = tasks.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )
    total = tasks.count()
    rows = []
    for task in tasks.order_by("-id")[offset : offset + limit]:
        row = task_to_dict(task)
        row["can_delete"] = _can_delete_task(request.user, task)
        rows.append(row)
    return _json_response({"total": total, "rows": rows})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def instance_tables(request):
    try:
        instance_id = int(request.GET.get("instance_id"))
        schemas = parse_csv(request.GET.get("schemas", ""))
        instance = user_instances(request.user, db_type=["pgsql"]).get(id=instance_id)
        rows = list_tables(instance, schemas)
        return _json_response({"status": 0, "msg": "ok", "rows": rows})
    except Instance.DoesNotExist:
        return JsonResponse({"status": 1, "msg": "你所在组未关联该 PostgreSQL 实例"})
    except Exception as exc:
        return JsonResponse({"status": 1, "msg": str(exc)})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def create_task(request):
    try:
        name = request.POST.get("name", "").strip()
        source_instance_id = int(request.POST.get("source_instance_id"))
        target_instance_id = int(request.POST.get("target_instance_id"))
        if source_instance_id == target_instance_id:
            return JsonResponse({"status": 1, "msg": "源库和目标库不能相同"})
        if not name:
            return JsonResponse({"status": 1, "msg": "任务名称不能为空"})
        instances = user_instances(request.user, db_type=["pgsql"])
        source = instances.get(id=source_instance_id)
        target = instances.get(id=target_instance_id)
        schemas = parse_csv(request.POST.get("schemas", ""))
        tables = parse_tables(request.POST.get("tables", ""))
        task = PgSQLMigrationTask.objects.create(
            name=name,
            source_instance=source,
            target_instance=target,
            schemas_json=json_dumps(schemas) if schemas else "",
            tables_json=json_dumps(tables) if tables else "",
            description=request.POST.get("description", ""),
            user_name=request.user.username,
            user_display=getattr(request.user, "display", "") or request.user.username,
        )
        create_task_log(task, "task.create", "succeeded", "迁移准备任务已创建")
        return JsonResponse({"status": 0, "msg": "ok", "data": task_to_dict(task)})
    except Instance.DoesNotExist:
        return JsonResponse({"status": 1, "msg": "你所在组未关联该 PostgreSQL 实例"})
    except Exception as exc:
        return JsonResponse({"status": 1, "msg": str(exc)})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def delete_task(request):
    try:
        task = _task_for_user(request, int(request.POST.get("task_id")))
        if not _can_delete_task(request.user, task):
            return JsonResponse(
                {"status": 1, "msg": "只有任务创建人或迁移管理权限用户可以删除任务"}
            )
        task.delete()
        return JsonResponse({"status": 0, "msg": "ok"})
    except Exception as exc:
        return JsonResponse({"status": 1, "msg": str(exc) or "删除任务失败"})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def scan_tables(request):
    try:
        task = _task_for_user(request, int(request.POST.get("task_id")))
        schemas = parse_csv(request.POST.get("schemas", "")) or task_schemas(task)
        rows = list_tables(task.source_instance, schemas)
        return _json_response({"status": 0, "msg": "ok", "rows": rows})
    except Exception as exc:
        return JsonResponse({"status": 1, "msg": str(exc)})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def preview_sequences(request):
    try:
        task = _task_for_user(request, int(request.POST.get("task_id")))
        step = int(request.POST.get("step", 10000))
        skip_if_target_greater = (
            request.POST.get("skip_if_target_greater", "true") == "true"
        )
        schemas = parse_csv(request.POST.get("schemas", "")) or task_schemas(task)
        log = create_task_log(
            task, "sequence.preview", "running", "开始预览目标库序列设置"
        )
        task.status = "checking"
        task.save(update_fields=["status", "update_time"])
        items = build_sequence_preview(
            task.source_instance,
            task.target_instance,
            step,
            schemas,
            skip_if_target_greater,
        )
        save_sequence_results(task, "preview", items)
        task.status = "sequence_previewed"
        task.save(update_fields=["status", "update_time"])
        finish_task_log(log, "succeeded", "序列预览完成", {"count": len(items)})
        return _json_response({"status": 0, "msg": "ok", "rows": items})
    except Exception as exc:
        if "task" in locals():
            task.status = "failed"
            task.save(update_fields=["status", "update_time"])
        if "log" in locals():
            finish_task_log(log, "failed", str(exc), traceback.format_exc())
        return JsonResponse({"status": 1, "msg": str(exc)})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.pgsql_migration_execute", raise_exception=True)
def apply_sequences(request):
    try:
        task = _task_for_user(request, int(request.POST.get("task_id")))
        step = int(request.POST.get("step", 10000))
        skip_if_target_greater = (
            request.POST.get("skip_if_target_greater", "true") == "true"
        )
        schemas = parse_csv(request.POST.get("schemas", "")) or task_schemas(task)
        log = create_task_log(task, "sequence.apply", "running", "开始设置目标库序列")
        task.status = "checking"
        task.save(update_fields=["status", "update_time"])
        preview = build_sequence_preview(
            task.source_instance,
            task.target_instance,
            step,
            schemas,
            skip_if_target_greater,
        )
        items = apply_sequence_values(task.target_instance, preview)
        save_sequence_results(task, "apply", items)
        task.status = "sequence_applied"
        task.save(update_fields=["status", "update_time"])
        finish_task_log(log, "succeeded", "目标库序列设置完成", {"count": len(items)})
        return _json_response({"status": 0, "msg": "ok", "rows": items})
    except Exception as exc:
        if "task" in locals():
            task.status = "failed"
            task.save(update_fields=["status", "update_time"])
        if "log" in locals():
            finish_task_log(log, "failed", str(exc), traceback.format_exc())
        return JsonResponse({"status": 1, "msg": str(exc)})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def sequence_results(request):
    try:
        task = _task_for_user(request, int(request.GET.get("task_id")))
        rows = list(
            PgSQLMigrationSequenceResult.objects.filter(task=task)
            .order_by("-id")
            .values()
        )
        return _json_response({"status": 0, "msg": "ok", "rows": rows})
    except Exception as exc:
        return JsonResponse({"status": 1, "msg": str(exc)})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def run_data_check(request):
    try:
        task = _task_for_user(request, int(request.POST.get("task_id")))
        exact_count = request.POST.get("exact_count", "true") == "true"
        include_pk_range = request.POST.get("include_pk_range", "true") == "true"
        tables = parse_tables(request.POST.get("tables", "")) or task_tables(task)
        if not tables:
            return JsonResponse(
                {"status": 1, "msg": "请先指定检查表，格式为 schema.table"}
            )
        log = create_task_log(task, "data_check.run", "running", "开始执行数据检查")
        task.status = "checking"
        task.save(update_fields=["status", "update_time"])
        items = run_table_checks(
            task.source_instance,
            task.target_instance,
            tables,
            exact_count,
            include_pk_range,
        )
        save_data_check_results(task, items)
        task.status = "data_checked"
        task.save(update_fields=["status", "update_time"])
        failed_count = len([item for item in items if item["status"] == "failed"])
        finish_task_log(
            log,
            "succeeded" if failed_count == 0 else "warning",
            "数据检查完成",
            {"count": len(items), "failed_count": failed_count},
        )
        return _json_response({"status": 0, "msg": "ok", "rows": items})
    except Exception as exc:
        if "task" in locals():
            task.status = "failed"
            task.save(update_fields=["status", "update_time"])
        if "log" in locals():
            finish_task_log(log, "failed", str(exc), traceback.format_exc())
        return JsonResponse({"status": 1, "msg": str(exc)})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def data_check_results(request):
    try:
        task = _task_for_user(request, int(request.GET.get("task_id")))
        rows = []
        for row in PgSQLMigrationDataCheckResult.objects.filter(task=task).order_by(
            "-id"
        ):
            rows.append(
                {
                    "id": row.id,
                    "task_id": row.task_id,
                    "schema_name": row.schema_name,
                    "table_name": row.table_name,
                    "status": row.status,
                    "checks": json_loads(row.checks_json, []),
                    "create_time": row.create_time,
                }
            )
        return _json_response({"status": 0, "msg": "ok", "rows": rows})
    except Exception as exc:
        return JsonResponse({"status": 1, "msg": str(exc)})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def run_feature_check(request):
    try:
        task = _task_for_user(request, int(request.POST.get("task_id")))
        schemas = parse_csv(request.POST.get("schemas", "")) or task_schemas(task)
        log = create_task_log(task, "feature.check", "running", "开始执行特性差异检查")
        task.status = "checking"
        task.save(update_fields=["status", "update_time"])
        rows = run_feature_checks(task.source_instance, task.target_instance, schemas)
        issue_count = len([row for row in rows if row.get("status") != "passed"])
        finish_task_log(
            log,
            "succeeded" if issue_count == 0 else "warning",
            "特性差异检查完成",
            {"count": len(rows), "issue_count": issue_count, "rows": rows},
        )
        return _json_response({"status": 0, "msg": "ok", "rows": rows})
    except Exception as exc:
        if "task" in locals():
            task.status = "failed"
            task.save(update_fields=["status", "update_time"])
        if "log" in locals():
            finish_task_log(log, "failed", str(exc), traceback.format_exc())
        return JsonResponse({"status": 1, "msg": str(exc)})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def feature_check_results(request):
    try:
        task = _task_for_user(request, int(request.GET.get("task_id")))
        log = (
            PgSQLMigrationTaskLog.objects.filter(task=task, operation="feature.check")
            .order_by("-id")
            .first()
        )
        if not log:
            return _json_response({"status": 0, "msg": "ok", "rows": []})
        details = json_loads(log.details_json, {})
        return _json_response({
            "status": 0,
            "msg": "ok",
            "rows": details.get("rows", []),
            "summary": {
                "log_id": log.id,
                "status": log.status,
                "message": log.message,
                "count": details.get("count", 0),
                "issue_count": details.get("issue_count", 0),
                "finish_time": log.finish_time,
            },
        })
    except Exception as exc:
        return JsonResponse({"status": 1, "msg": str(exc)})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.pgsql_migration_execute", raise_exception=True)
def set_replica_identity(request):
    try:
        task = _task_for_user(request, int(request.POST.get("task_id")))
        schema_name = request.POST.get("schema_name", "")
        table_name = request.POST.get("table_name", "")
        index_name = request.POST.get("index_name", "")
        log = create_task_log(
            task,
            "replica_identity.using_index",
            "running",
            "开始设置 REPLICA IDENTITY",
        )
        result = set_replica_identity_using_index(
            task.source_instance, schema_name, table_name, index_name
        )
        finish_task_log(log, "succeeded", "REPLICA IDENTITY 已更新", result)
        return _json_response({"status": 0, "msg": "ok", "data": result})
    except Exception as exc:
        if "log" in locals():
            finish_task_log(log, "failed", str(exc), traceback.format_exc())
        return JsonResponse({"status": 1, "msg": str(exc)})


@tool_plugin_enabled_required(PGSQL_MIGRATION_PLUGIN_CODE)
@permission_required("sql.menu_pgsql_migration", raise_exception=True)
def logs(request):
    try:
        task = _task_for_user(request, int(request.GET.get("task_id")))
        rows = list(
            PgSQLMigrationTaskLog.objects.filter(task=task).order_by("-id").values()
        )
        return _json_response({"status": 0, "msg": "ok", "rows": rows})
    except Exception as exc:
        return JsonResponse({"status": 1, "msg": str(exc)})
