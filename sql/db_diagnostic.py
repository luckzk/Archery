import logging
import traceback
import MySQLdb

# import simplejson as json
import json
from django.contrib.auth.decorators import permission_required

from django.http import HttpResponse

from sql.engines import get_engine
from common.utils.extend_json_encoder import ExtendJSONEncoder, ExtendJSONEncoderBytes
from sql.utils.resource_group import user_instances
from .models import Instance

logger = logging.getLogger("default")


# 问题诊断--进程列表
@permission_required("sql.process_view", raise_exception=True)
def process(request):
    instance_name = request.POST.get("instance_name")
    command_type = request.POST.get("command_type")
    request_kwargs = {
        key: value for key, value in request.POST.items() if key != "command_type"
    }

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    query_result = None
    # processlist方法已提升为父类方法，简化此处的逻辑。进程添加新数据库支持时，改前端即可。
    query_result = query_engine.processlist(command_type=command_type, **request_kwargs)
    if query_result:
        if not query_result.error:
            processlist = query_result.to_dict()
            result = {"status": 0, "msg": "ok", "rows": processlist}
        else:
            result = {"status": 1, "msg": query_result.error}

    # 返回查询结果
    # ExtendJSONEncoderBytes 使用json模块，bigint_as_string只支持simplejson
    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoderBytes), content_type="application/json"
    )


# 问题诊断--通过线程id构建请求 这里只是用于确定将要kill的线程id还在运行
@permission_required("sql.process_kill", raise_exception=True)
def create_kill_session(request):
    instance_name = request.POST.get("instance_name")
    thread_ids = request.POST.get("ThreadIDs")

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    result = {"status": 0, "msg": "ok", "data": []}
    query_engine = get_engine(instance=instance)
    try:
        result["data"] = query_engine.get_kill_command(json.loads(thread_ids))
    except AttributeError:
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库通过进程id构建请求".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")
    # 返回查询结果
    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--终止会话 这里是实际执行kill的操作
@permission_required("sql.process_kill", raise_exception=True)
def kill_session(request):
    instance_name = request.POST.get("instance_name")
    thread_ids = request.POST.get("ThreadIDs")
    result = {"status": 0, "msg": "ok", "data": []}

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    engine = get_engine(instance=instance)
    r = None
    if instance.db_type in ["mysql", "doris", "clickhouse"]:
        r = engine.kill(json.loads(thread_ids))
    elif instance.db_type == "mongo":
        r = engine.kill_op(json.loads(thread_ids))
    elif instance.db_type == "oracle":
        r = engine.kill_session(json.loads(thread_ids))
    elif instance.db_type == "tdengine":
        r = engine.kill_query(json.loads(thread_ids))
    elif instance.db_type == "pgsql":
        r = engine.kill(json.loads(thread_ids))
    else:
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库终止会话".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    if r and r.error:
        result = {"status": 1, "msg": r.error, "data": []}
    # 返回查询结果
    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--取消正在执行的查询
@permission_required("sql.process_kill", raise_exception=True)
def cancel_session(request):
    instance_name = request.POST.get("instance_name")
    thread_ids = request.POST.get("ThreadIDs")
    result = {"status": 0, "msg": "ok", "data": []}

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    if instance.db_type != "pgsql":
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库取消查询".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    engine = get_engine(instance=instance)
    r = engine.cancel_backend(json.loads(thread_ids))

    if r and r.error:
        result = {"status": 1, "msg": r.error, "data": []}
    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--表空间信息
@permission_required("sql.tablespace_view", raise_exception=True)
def tablespace(request):
    instance_name = request.POST.get("instance_name")
    offset = int(request.POST.get("offset", 0))
    limit = int(request.POST.get("limit", 14))
    db_name = request.POST.get("db_name", "")
    schema_name = request.POST.get("schema_name", "")
    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    try:
        if instance.db_type == "pgsql":
            query_result = query_engine.tablespace(
                offset, limit, db_name=db_name, schema_name=schema_name
            )
        else:
            query_result = query_engine.tablespace(offset, limit)
    except AttributeError:
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库的表空间信息查询".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    if query_result:
        if not query_result.error:
            table_space = query_result.to_dict()
            if instance.db_type == "pgsql":
                r = query_engine.tablespace_count(
                    db_name=db_name, schema_name=schema_name
                )
            else:
                r = query_engine.tablespace_count()
            if r.error:
                result = {"status": 1, "msg": r.error}
                return HttpResponse(json.dumps(result), content_type="application/json")
            total = r.rows[0][0]
            result = {"status": 0, "msg": "ok", "rows": table_space, "total": total}
        else:
            result = {"status": 1, "msg": query_result.error}
    # 返回查询结果
    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--PgSQL Top表空间过滤项
@permission_required("sql.tablespace_view", raise_exception=True)
def pgsql_tablespace_filters(request):
    instance_name = request.GET.get("instance_name")
    db_name = request.GET.get("db_name", "")

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": {}}
        return HttpResponse(json.dumps(result), content_type="application/json")

    if instance.db_type != "pgsql":
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库的PgSQL表空间过滤项".format(instance.db_type),
            "data": {},
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    result = {"status": 0, "msg": "ok", "data": {"databases": [], "schemas": []}}
    try:
        database_result = query_engine.get_all_databases()
        if database_result.error:
            result = {"status": 1, "msg": database_result.error, "data": {}}
        else:
            result["data"]["databases"] = database_result.rows
            selected_db = db_name or query_engine.db_name or "postgres"
            schema_result = query_engine.get_all_schemas(db_name=selected_db)
            if schema_result.error:
                result = {"status": 1, "msg": schema_result.error, "data": result["data"]}
            else:
                result["data"]["selected_db"] = selected_db
                result["data"]["schemas"] = schema_result.rows
    finally:
        query_engine.close()

    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--锁等待
@permission_required("sql.trxandlocks_view", raise_exception=True)
def trxandlocks(request):
    instance_name = request.POST.get("instance_name")

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    if instance.db_type == "mysql":
        query_result = query_engine.trxandlocks()
    elif instance.db_type == "pgsql":
        query_result = query_engine.trxandlocks()
    elif instance.db_type == "oracle":
        query_result = query_engine.lock_info()
    else:
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库的锁等待查询".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    if not query_result.error:
        trxandlocks = query_result.to_dict()
        result = {"status": 0, "msg": "ok", "rows": trxandlocks}
    else:
        result = {"status": 1, "msg": query_result.error}

    # 返回查询结果
    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--PgSQL发布订阅
@permission_required("sql.trxandlocks_view", raise_exception=True)
def pubsub(request):
    instance_name = request.POST.get("instance_name")

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    if instance.db_type != "pgsql":
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库的发布订阅查询".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    query_result = query_engine.pubsub()

    if not query_result.error:
        pubsub = query_result.to_dict()
        result = {"status": 0, "msg": "ok", "rows": pubsub}
    else:
        result = {"status": 1, "msg": query_result.error}

    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--PgSQL复制状态
@permission_required("sql.trxandlocks_view", raise_exception=True)
def pgsql_replication(request):
    instance_name = request.POST.get("instance_name")

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    if instance.db_type != "pgsql":
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库的复制状态查询".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    query_result = query_engine.replication_status()

    if not query_result.error:
        rows = query_result.to_dict()
        result = {"status": 0, "msg": "ok", "rows": rows}
    else:
        result = {"status": 1, "msg": query_result.error}

    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--PgSQL复制Slot
@permission_required("sql.trxandlocks_view", raise_exception=True)
def pgsql_replication_slots(request):
    instance_name = request.POST.get("instance_name")

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    if instance.db_type != "pgsql":
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库的复制Slot查询".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    query_result = query_engine.replication_slots()

    if not query_result.error:
        rows = query_result.to_dict()
        result = {"status": 0, "msg": "ok", "rows": rows}
    else:
        result = {"status": 1, "msg": query_result.error}

    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--PgSQL Vacuum风险
@permission_required("sql.tablespace_view", raise_exception=True)
def pgsql_vacuum(request):
    instance_name = request.POST.get("instance_name")
    offset = int(request.POST.get("offset", 0))
    limit = int(request.POST.get("limit", 30))
    db_name = request.POST.get("db_name", "")
    schema_name = request.POST.get("schema_name", "")

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    if instance.db_type != "pgsql":
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库的Vacuum风险查询".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    query_result = query_engine.vacuum_risk(
        offset=offset, row_count=limit, db_name=db_name, schema_name=schema_name
    )

    if query_result and not query_result.error:
        rows = query_result.to_dict()
        count_result = query_engine.vacuum_risk_count(
            db_name=db_name, schema_name=schema_name
        )
        if count_result.error:
            result = {"status": 1, "msg": count_result.error}
        else:
            result = {
                "status": 0,
                "msg": "ok",
                "rows": rows,
                "total": count_result.rows[0][0],
            }
    elif query_result:
        result = {"status": 1, "msg": query_result.error}
    else:
        result = {"status": 1, "msg": "Vacuum风险查询无返回结果"}

    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--PgSQL Progress进度
@permission_required("sql.trxandlocks_view", raise_exception=True)
def pgsql_progress(request):
    instance_name = request.POST.get("instance_name")

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    if instance.db_type != "pgsql":
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库的Progress进度查询".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    query_result = query_engine.progress_status()

    if query_result and not query_result.error:
        rows = query_result.to_dict()
        result = {"status": 0, "msg": "ok", "rows": rows}
    elif query_result:
        result = {"status": 1, "msg": query_result.error}
    else:
        result = {"status": 1, "msg": "Progress进度查询无返回结果"}

    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--PgSQL等待事件聚合
@permission_required("sql.trxandlocks_view", raise_exception=True)
def pgsql_wait_events(request):
    instance_name = request.POST.get("instance_name")

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    if instance.db_type != "pgsql":
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库的等待事件聚合查询".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    query_result = query_engine.wait_event_summary()

    if query_result and not query_result.error:
        rows = query_result.to_dict()
        result = {"status": 0, "msg": "ok", "rows": rows}
    elif query_result:
        result = {"status": 1, "msg": query_result.error}
    else:
        result = {"status": 1, "msg": "等待事件聚合查询无返回结果"}

    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--PgSQL索引诊断
@permission_required("sql.tablespace_view", raise_exception=True)
def pgsql_indexes(request):
    instance_name = request.POST.get("instance_name")
    offset = int(request.POST.get("offset", 0))
    limit = int(request.POST.get("limit", 30))
    db_name = request.POST.get("db_name", "")
    schema_name = request.POST.get("schema_name", "")

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    if instance.db_type != "pgsql":
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库的索引诊断查询".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    query_result = query_engine.index_diagnostic(
        offset=offset, row_count=limit, db_name=db_name, schema_name=schema_name
    )

    if query_result and not query_result.error:
        rows = query_result.to_dict()
        count_result = query_engine.index_diagnostic_count(
            db_name=db_name, schema_name=schema_name
        )
        if count_result.error:
            result = {"status": 1, "msg": count_result.error}
        else:
            result = {
                "status": 0,
                "msg": "ok",
                "rows": rows,
                "total": count_result.rows[0][0],
            }
    elif query_result:
        result = {"status": 1, "msg": query_result.error}
    else:
        result = {"status": 1, "msg": "索引诊断查询无返回结果"}

    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )


# 问题诊断--长事务
@permission_required("sql.trx_view", raise_exception=True)
def innodb_trx(request):
    instance_name = request.POST.get("instance_name")

    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result = {"status": 1, "msg": "你所在组未关联该实例", "data": []}
        return HttpResponse(json.dumps(result), content_type="application/json")

    query_engine = get_engine(instance=instance)
    try:
        query_result = query_engine.get_long_transaction()
    except AttributeError:
        result = {
            "status": 1,
            "msg": "暂时不支持{}类型数据库的长事务查询".format(instance.db_type),
            "data": [],
        }
        return HttpResponse(json.dumps(result), content_type="application/json")

    if not query_result.error:
        trx = query_result.to_dict()
        result = {"status": 0, "msg": "ok", "rows": trx}
    else:
        result = {"status": 1, "msg": query_result.error}

    # 返回查询结果
    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder),
        content_type="application/json",
    )
