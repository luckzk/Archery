# -*- coding: UTF-8 -*-
import datetime
import logging
import re
import time
import traceback

import simplejson as json
from django.contrib.auth.decorators import permission_required
from django.db import connection, close_old_connections
from django.db.models import Q
from django.http import HttpResponse
from common.config import SysConfig
from common.utils.extend_json_encoder import ExtendJSONEncoder, ExtendJSONEncoderFTime
from common.utils.openai import OpenaiClient, check_openai_config
from common.utils.timer import FuncTimer
from sql.query_privileges import query_priv_check
from sql.utils.resource_group import user_instances
from sql.utils.sqlquery_favorite import (
    SQLQUERY_KNOWLEDGE_ALIAS,
    favorite_by_source_query_log_id,
    favorite_rows_for_user,
    migrate_legacy_favorites,
)
from sql.utils.sqlquery_knowledge import SQLQUERY_KNOWLEDGE_ENGINES
from sql.utils.sqlquery_preference import (
    get_sqlquery_preference,
    update_sqlquery_preference,
)
from sql.utils.tasks import add_kill_conn_schedule, del_schedule
from .models import QueryLog, Instance, SqlQueryKnowledge, SqlQueryFavorite
from sql.engines import get_engine
from sql.services.querylog_service import list_query_logs, update_favorite
from sql.services.sqlquery_service import execute_sql_query

logger = logging.getLogger("default")


def _normalize_knowledge_engines(engine_values):
    if not isinstance(engine_values, (list, tuple)):
        engine_values = [engine_values]

    valid_engines = set(SQLQUERY_KNOWLEDGE_ENGINES)
    engines = []
    for value in engine_values:
        for engine in str(value or "").split(","):
            engine = engine.strip()
            if engine in valid_engines and engine not in engines:
                engines.append(engine)
    return engines or ["通用"]


def _knowledge_item_from_log(query_log):
    try:
        payload = json.loads(query_log.sqllog)
    except (TypeError, ValueError):
        payload = {}

    sql = payload.get("sql") or query_log.sqllog
    return {
        "id": query_log.id,
        "name": payload.get("name") or "未命名",
        "scene": payload.get("scene") or "自定义",
        "engines": _normalize_knowledge_engines(payload.get("engines", [])),
        "sql": sql,
        "create_time": query_log.create_time,
        "sys_time": query_log.sys_time,
    }


def _knowledge_item_from_model(knowledge):
    return {
        "id": knowledge.id,
        "name": knowledge.name,
        "scene": knowledge.scene or "自定义",
        "engines": _normalize_knowledge_engines(knowledge.engines),
        "sql": knowledge.sql,
        "instance_name": knowledge.instance_name,
        "db_name": knowledge.db_name,
        "create_time": knowledge.create_time,
        "sys_time": knowledge.sys_time,
    }


def _migrate_legacy_knowledge(user):
    legacy_logs = QueryLog.objects.filter(
        username=user.username, alias=SQLQUERY_KNOWLEDGE_ALIAS
    )
    for legacy_log in legacy_logs:
        legacy_item = _knowledge_item_from_log(legacy_log)
        if SqlQueryKnowledge.objects.filter(
            username=user.username,
            name=legacy_item["name"],
            sql=legacy_item["sql"],
        ).exists():
            continue
        SqlQueryKnowledge.objects.create(
            username=user.username,
            user_display=user.display,
            name=legacy_item["name"][:64],
            scene=legacy_item["scene"][:64],
            engines=",".join(legacy_item["engines"]),
            sql=legacy_item["sql"],
            instance_name=legacy_log.instance_name,
            db_name=legacy_log.db_name,
        )


@permission_required("sql.query_submit", raise_exception=True)
def query(request):
    """
    获取SQL查询结果
    :param request:
    :return:
    """
    instance_name = request.POST.get("instance_name")
    sql_content = request.POST.get("sql_content")
    db_name = request.POST.get("db_name")
    tb_name = request.POST.get("tb_name")
    limit_num = int(request.POST.get("limit_num", 0))
    schema_name = request.POST.get("schema_name", None)
    user = request.user

    result = {"status": 0, "msg": "ok", "data": {}}
    try:
        instance = user_instances(request.user).get(instance_name=instance_name)
    except Instance.DoesNotExist:
        result["status"] = 1
        result["msg"] = "你所在组未关联该实例"
        return HttpResponse(json.dumps(result), content_type="application/json")

    # 服务器端参数验证
    if None in [sql_content, db_name, instance_name, limit_num]:
        result["status"] = 1
        result["msg"] = "页面提交参数可能为空"
        return HttpResponse(json.dumps(result), content_type="application/json")

    try:
        config = SysConfig()
        # 查询前的检查，禁用语句检查，语句切分
        query_engine = get_engine(instance=instance)
        query_check_info = query_engine.query_check(db_name=db_name, sql=sql_content)
        if query_check_info.get("bad_query"):
            # 引擎内部判断为 bad_query
            result["status"] = 1
            result["msg"] = query_check_info.get("msg")
            return HttpResponse(json.dumps(result), content_type="application/json")
        if query_check_info.get("has_star") and config.get("disable_star") is True:
            # 引擎内部判断为有 * 且禁止 * 选项打开
            result["status"] = 1
            result["msg"] = query_check_info.get("msg")
            return HttpResponse(json.dumps(result), content_type="application/json")
        sql_content = query_check_info["filtered_sql"]

        # 查询权限校验，并且获取limit_num
        priv_check_info = query_priv_check(
            user, instance, db_name, sql_content, limit_num, schema_name=schema_name
        )
        if priv_check_info["status"] == 0:
            limit_num = priv_check_info["data"]["limit_num"]
            priv_check = priv_check_info["data"]["priv_check"]
        else:
            result["status"] = priv_check_info["status"]
            result["msg"] = priv_check_info["msg"]
            return HttpResponse(json.dumps(result), content_type="application/json")
        # explain的limit_num设置为0
        limit_num = 0 if re.match(r"^explain", sql_content.lower()) else limit_num

        # 对查询sql增加limit限制或者改写语句
        sql_content = query_engine.filter_sql(sql=sql_content, limit_num=limit_num)

        # 先获取查询连接，用于后面查询复用连接以及终止会话
        query_engine.get_connection(db_name=db_name)
        thread_id = query_engine.thread_id
        max_execution_time = int(config.get("max_execution_time", 60))
        # 执行查询语句，并增加一个定时终止语句的schedule，timeout=max_execution_time
        if thread_id:
            schedule_name = f"query-{time.time()}"
            run_date = datetime.datetime.now() + datetime.timedelta(
                seconds=max_execution_time
            )
            add_kill_conn_schedule(schedule_name, run_date, instance.id, thread_id)
        with FuncTimer() as t:
            # 获取主从延迟信息
            seconds_behind_master = query_engine.seconds_behind_master
            query_result = query_engine.query(
                db_name,
                sql_content,
                limit_num,
                schema_name=schema_name,
                tb_name=tb_name,
                max_execution_time=max_execution_time * 1000,
            )
        query_result.query_time = t.cost
        # 返回查询结果后删除schedule
        if thread_id:
            del_schedule(schedule_name)

        # 查询异常
        if query_result.error:
            result["status"] = 1
            result["msg"] = query_result.error
        # 数据脱敏，仅对查询无错误的结果集进行脱敏，并且按照query_check配置是否返回
        elif config.get("data_masking"):
            try:
                with FuncTimer() as t:
                    masking_result = query_engine.query_masking(
                        db_name, sql_content, query_result
                    )
                masking_result.mask_time = t.cost
                # 脱敏出错
                if masking_result.error:
                    # 开启query_check，直接返回异常，禁止执行
                    if config.get("query_check"):
                        result["status"] = 1
                        result["msg"] = f"数据脱敏异常：{masking_result.error}"
                    # 关闭query_check，忽略错误信息，返回未脱敏数据，权限校验标记为跳过
                    else:
                        logger.warning(
                            f"数据脱敏异常，按照配置放行，查询语句：{sql_content}，错误信息：{masking_result.error}"
                        )
                        query_result.error = None
                        result["data"] = query_result.__dict__
                # 正常脱敏
                else:
                    result["data"] = masking_result.__dict__
            except Exception as msg:
                logger.error(traceback.format_exc())
                # 抛出未定义异常，并且开启query_check，直接返回异常，禁止执行
                if config.get("query_check"):
                    result["status"] = 1
                    result["msg"] = f"数据脱敏异常，请联系管理员，错误信息：{msg}"
                # 关闭query_check，忽略错误信息，返回未脱敏数据，权限校验标记为跳过
                else:
                    logger.warning(
                        f"数据脱敏异常，按照配置放行，查询语句：{sql_content}，错误信息：{msg}"
                    )
                    query_result.error = None
                    result["data"] = query_result.__dict__
        # 无需脱敏的语句
        else:
            result["data"] = query_result.__dict__

        # 仅将成功的查询语句记录存入数据库
        if not query_result.error:
            result["data"]["seconds_behind_master"] = seconds_behind_master
            if int(limit_num) == 0:
                limit_num = int(query_result.affected_rows)
            else:
                limit_num = min(int(limit_num), int(query_result.affected_rows))
            # 防止查询超时
            if connection.connection and not connection.is_usable():
                close_old_connections()
        else:
            limit_num = 0
        query_log = QueryLog(
            username=user.username,
            user_display=user.display,
            db_name=db_name,
            instance_name=instance.instance_name,
            sqllog=sql_content,
            effect_row=limit_num,
            cost_time=query_result.query_time,
            priv_check=priv_check,
            hit_rule=query_result.mask_rule_hit,
            masking=query_result.is_masked,
        )
        query_log.save()
    except Exception as e:
        logger.error(
            f"查询异常报错，查询语句：{sql_content}\n，错误信息：{traceback.format_exc()}"
        )
        result["status"] = 1
        result["msg"] = f"查询异常报错，错误信息：{e}"
        return HttpResponse(json.dumps(result), content_type="application/json")
    # 返回查询结果
    try:
        return HttpResponse(
            json.dumps(
                result,
                use_decimal=False,
                cls=ExtendJSONEncoderFTime,
                bigint_as_string=True,
            ),
            content_type="application/json",
        )
    # 虽然能正常返回，但是依然会乱码
    except UnicodeDecodeError:
        return HttpResponse(
            json.dumps(result, default=str, bigint_as_string=True, encoding="latin1"),
            content_type="application/json",
        )


@permission_required("sql.menu_sqlquery", raise_exception=True)
def pgsql_blocking_chain(request):
    """SQLQuery 获取 PostgreSQL 锁等待/阻塞链"""
    instance_name = request.POST.get("instance_name")
    db_name = request.POST.get("db_name")
    result = {"status": 0, "msg": "ok", "data": {}}

    if not instance_name or not db_name:
        result["status"] = 1
        result["msg"] = "页面提交参数可能为空"
        return HttpResponse(json.dumps(result), content_type="application/json")

    try:
        instance = user_instances(request.user, db_type=["pgsql"]).get(
            instance_name=instance_name
        )
    except Instance.DoesNotExist:
        result["status"] = 1
        result["msg"] = "你所在组未关联该PgSQL实例"
        return HttpResponse(json.dumps(result), content_type="application/json")

    try:
        query_engine = get_engine(instance=instance)
        db_name = query_engine.escape_string(db_name)
        query_result = query_engine.get_blocking_chain(db_name=db_name)
        if query_result.error:
            result["status"] = 1
            result["msg"] = query_result.error
        else:
            query_result.query_time = "-"
            query_result.mask_time = "-"
            query_result.full_sql = "PgSQL 锁等待 / 阻塞链诊断"
            result["data"] = query_result.__dict__
    except Exception as msg:
        logger.error(traceback.format_exc())
        result["status"] = 1
        result["msg"] = str(msg)

    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder, bigint_as_string=True),
        content_type="application/json",
    )


@permission_required("sql.menu_sqlquery", raise_exception=True)
def querylog(request):
    return _querylog(request)


@permission_required("sql.audit_user", raise_exception=True)
def querylog_audit(request):
    return _querylog(request)


def _querylog(request):
    """
    获取sql查询记录
    :param request:
    :return:
    """
    # 获取用户信息
    user = request.user

    limit = int(request.GET.get("limit", 0))
    offset = int(request.GET.get("offset", 0))
    limit = offset + limit
    limit = limit if limit else None
    star = True if request.GET.get("star") == "true" else False
    query_log_id = request.GET.get("query_log_id")
    search = request.GET.get("search", "")
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    source_favorites = favorite_by_source_query_log_id(user)

    # 组合筛选项
    filter_dict = dict()
    # 是否收藏
    if star:
        filter_dict["id__in"] = list(source_favorites.keys())
    # 语句别名
    if query_log_id:
        filter_dict["id"] = query_log_id

    # 管理员、审计员查看全部数据,普通用户查看自己的数据
    if not (user.is_superuser or user.has_perm("sql.audit_user")):
        filter_dict["username"] = user.username

    if start_date and end_date:
        end_date = datetime.datetime.strptime(
            end_date, "%Y-%m-%d"
        ) + datetime.timedelta(days=1)
        filter_dict["create_time__range"] = (start_date, end_date)

    # 过滤组合筛选项
    sql_log = QueryLog.objects.filter(**filter_dict).exclude(
        alias=SQLQUERY_KNOWLEDGE_ALIAS
    )

    # 过滤搜索信息
    sql_log = sql_log.filter(
        Q(sqllog__icontains=search)
        | Q(user_display__icontains=search)
        | Q(alias__icontains=search)
    )

    sql_log_count = sql_log.count()
    sql_log_list = sql_log.order_by("-id")[offset:limit].values(
        "id",
        "instance_name",
        "db_name",
        "sqllog",
        "effect_row",
        "cost_time",
        "user_display",
        "favorite",
        "alias",
        "create_time",
    )
    # QuerySet 序列化
    rows = []
    for row in sql_log_list:
        favorite = source_favorites.get(row["id"])
        row["favorite"] = bool(favorite)
        if favorite:
            row["favorite_id"] = favorite.id
            row["alias"] = favorite.alias
        rows.append(row)
    result = {"total": sql_log_count, "rows": rows}
    # 返回查询结果
    return HttpResponse(
        json.dumps(result, cls=ExtendJSONEncoder, bigint_as_string=True),
        content_type="application/json",
    )


@permission_required("sql.menu_sqlquery", raise_exception=True)
def favorite(request):
    """
    收藏查询记录，并且设置别名
    :param request:
    :return:
    """
    user = request.user

    if request.method == "GET":
        search = request.GET.get("search", "")
        rows = favorite_rows_for_user(user, search=search)
        return HttpResponse(
            json.dumps(
                {"status": 0, "msg": "ok", "data": rows},
                cls=ExtendJSONEncoder,
                bigint_as_string=True,
            ),
            content_type="application/json",
        )

    query_log_id = request.POST.get("query_log_id")
    favorite_id = request.POST.get("favorite_id")
    star = True if request.POST.get("star") == "true" else False
    alias = (request.POST.get("alias") or "").strip()
    sql_content = (request.POST.get("sql_content") or "").strip()

    if favorite_id:
        try:
            favorite_row = SqlQueryFavorite.objects.get(
                id=favorite_id, username=user.username
            )
        except SqlQueryFavorite.DoesNotExist:
            return HttpResponse(
                json.dumps({"status": 1, "msg": "收藏记录不存在"}),
                content_type="application/json",
            )
        if not star:
            favorite_row.delete()
        else:
            if not sql_content:
                return HttpResponse(
                    json.dumps({"status": 1, "msg": "SQL内容不能为空"}),
                    content_type="application/json",
                )
            favorite_row.alias = alias[:64]
            favorite_row.sql = sql_content
            favorite_row.instance_name = request.POST.get("instance_name") or ""
            favorite_row.db_name = request.POST.get("db_name") or ""
            favorite_row.save()
    elif query_log_id:
        try:
            query_log_filter = {"id": query_log_id}
            if not (user.is_superuser or user.has_perm("sql.audit_user")):
                query_log_filter["username"] = user.username
            query_log = QueryLog.objects.exclude(alias=SQLQUERY_KNOWLEDGE_ALIAS).get(
                **query_log_filter
            )
        except QueryLog.DoesNotExist:
            return HttpResponse(
                json.dumps({"status": 1, "msg": "收藏记录不存在"}),
                content_type="application/json",
            )
        if not star:
            SqlQueryFavorite.objects.filter(
                username=user.username, source_query_log_id=query_log.id
            ).delete()
        else:
            favorite_row, _ = SqlQueryFavorite.objects.get_or_create(
                username=user.username,
                source_query_log_id=query_log.id,
                defaults={
                    "user_display": user.display,
                    "alias": alias[:64],
                    "sql": sql_content or query_log.sqllog,
                    "instance_name": query_log.instance_name,
                    "db_name": query_log.db_name,
                },
            )
            favorite_row.alias = alias[:64]
            favorite_row.sql = sql_content or query_log.sqllog
            favorite_row.instance_name = query_log.instance_name
            favorite_row.db_name = query_log.db_name
            favorite_row.save()
    else:
        if not star:
            return HttpResponse(
                json.dumps({"status": 1, "msg": "收藏记录不存在"}),
                content_type="application/json",
            )
        if not sql_content:
            return HttpResponse(
                json.dumps({"status": 1, "msg": "SQL内容不能为空"}),
                content_type="application/json",
            )
        SqlQueryFavorite.objects.create(
            username=user.username,
            user_display=user.display,
            db_name=request.POST.get("db_name") or "",
            instance_name=request.POST.get("instance_name") or "",
            sql=sql_content,
            alias=alias[:64],
        )
    # 返回查询结果
    return HttpResponse(json.dumps(result), content_type="application/json")


@permission_required("sql.menu_sqlquery", raise_exception=True)
def knowledge(request):
    """
    当前账号的 SQL 查询知识库。
    :param request:
    :return:
    """
    user = request.user

    if request.method == "GET":
        _migrate_legacy_knowledge(user)
        search = request.GET.get("search", "")
        engine = request.GET.get("engine", "")
        scene = request.GET.get("scene", "")
        knowledge_rows = SqlQueryKnowledge.objects.filter(
            username=user.username,
        )
        if engine:
            knowledge_rows = knowledge_rows.filter(
                Q(engines__icontains=engine) | Q(engines__icontains="通用")
            )
        if scene:
            knowledge_rows = knowledge_rows.filter(scene=scene)
        if search:
            knowledge_rows = knowledge_rows.filter(
                Q(name__icontains=search)
                | Q(scene__icontains=search)
                | Q(engines__icontains=search)
                | Q(sql__icontains=search)
            )
        rows = [
            _knowledge_item_from_model(row)
            for row in knowledge_rows.order_by("-sys_time", "-id")
        ]
        scenes = list(
            SqlQueryKnowledge.objects.filter(username=user.username)
            .exclude(scene="")
            .order_by("scene")
            .values_list("scene", flat=True)
            .distinct()
        )
        return HttpResponse(
            json.dumps(
                {"status": 0, "msg": "ok", "data": rows, "scenes": scenes},
                cls=ExtendJSONEncoder,
                bigint_as_string=True,
            ),
            content_type="application/json",
        )

    action = request.POST.get("action", "add")
    if action == "delete":
        knowledge_id = request.POST.get("id")
        if not knowledge_id or not str(knowledge_id).isdigit():
            return HttpResponse(
                json.dumps({"status": 1, "msg": "知识库记录不存在"}),
                content_type="application/json",
            )
        deleted_count, _ = SqlQueryKnowledge.objects.filter(
            id=knowledge_id, username=user.username
        ).delete()
        if not deleted_count:
            return HttpResponse(
                json.dumps({"status": 1, "msg": "知识库记录不存在"}),
                content_type="application/json",
            )
        return HttpResponse(
            json.dumps({"status": 0, "msg": "ok"}), content_type="application/json"
        )

    source_knowledge = None
    if action in ("edit", "copy"):
        knowledge_id = request.POST.get("id")
        try:
            source_knowledge = SqlQueryKnowledge.objects.get(
                id=knowledge_id, username=user.username
            )
        except SqlQueryKnowledge.DoesNotExist:
            return HttpResponse(
                json.dumps({"status": 1, "msg": "知识库记录不存在"}),
                content_type="application/json",
            )

    name = (request.POST.get("name") or "").strip()
    scene = (request.POST.get("scene") or "自定义").strip() or "自定义"
    engines = _normalize_knowledge_engines(request.POST.getlist("engines[]"))
    sql_content = (request.POST.get("sql") or "").strip()
    if not name:
        return HttpResponse(
            json.dumps({"status": 1, "msg": "请输入名称"}),
            content_type="application/json",
        )
    if not sql_content:
        return HttpResponse(
            json.dumps({"status": 1, "msg": "请输入SQL"}),
            content_type="application/json",
        )

    if action == "edit" and source_knowledge:
        source_knowledge.name = name[:64]
        source_knowledge.scene = scene[:64]
        source_knowledge.engines = ",".join(engines)
        source_knowledge.sql = sql_content
        source_knowledge.instance_name = request.POST.get("instance_name") or ""
        source_knowledge.db_name = request.POST.get("db_name") or ""
        source_knowledge.save()
        knowledge_row = source_knowledge
    else:
        if action == "copy" and source_knowledge and not name.endswith(" 副本"):
            name = f"{name} 副本"
        knowledge_row = SqlQueryKnowledge.objects.create(
            username=user.username,
            user_display=user.display,
            name=name[:64],
            scene=scene[:64],
            engines=",".join(engines),
            sql=sql_content,
            instance_name=request.POST.get("instance_name") or "",
            db_name=request.POST.get("db_name") or "",
        )
    return HttpResponse(
        json.dumps(
            {
                "status": 0,
                "msg": "ok",
                "data": _knowledge_item_from_model(knowledge_row),
            },
            cls=ExtendJSONEncoder,
            bigint_as_string=True,
        ),
        content_type="application/json",
    )


@permission_required("sql.menu_sqlquery", raise_exception=True)
def preference(request):
    """SQL查询页账号级界面偏好"""
    user = request.user
    if request.method == "GET":
        return HttpResponse(
            json.dumps(
                {
                    "status": 0,
                    "msg": "ok",
                    "data": get_sqlquery_preference(user),
                },
                cls=ExtendJSONEncoder,
                bigint_as_string=True,
            ),
            content_type="application/json",
        )

    if request.method == "POST":
        preference_data = update_sqlquery_preference(user, request.POST)
        return HttpResponse(
            json.dumps(
                {"status": 0, "msg": "ok", "data": preference_data},
                cls=ExtendJSONEncoder,
                bigint_as_string=True,
            ),
            content_type="application/json",
        )

    return HttpResponse(
        json.dumps({"status": 1, "msg": "不支持的请求方法"}),
        content_type="application/json",
    )


def kill_query_conn(instance_id, thread_id):
    """终止查询会话，用于schedule调用"""
    instance = Instance.objects.get(pk=instance_id)
    query_engine = get_engine(instance)
    query_engine.kill_connection(thread_id)


@permission_required("sql.menu_sqlquery", raise_exception=True)
def generate_sql(request):
    """
    利用AI生成查询SQL, 传入数据基本结构和查询描述
    :param request:
    :return:
    """
    query_desc = request.POST.get("query_desc")
    db_type = request.POST.get("db_type")
    if not query_desc or not db_type:
        return HttpResponse(
            json.dumps({"status": 1, "msg": "query_desc or db_type不存在", "data": []}),
            content_type="application/json",
        )

    instance_name = request.POST.get("instance_name")
    try:
        instance = Instance.objects.get(instance_name=instance_name)
    except Instance.DoesNotExist:
        return HttpResponse(
            json.dumps({"status": 1, "msg": "实例不存在", "data": []}),
            content_type="application/json",
        )
    db_name = request.POST.get("db_name")
    schema_name = request.POST.get("schema_name")
    # 获取多表名列表
    tb_name_list = request.POST.getlist("tb_name_list[]") or request.POST.getlist(
        "tb_name_list"
    )

    result = {"status": 0, "msg": "ok", "data": ""}
    try:
        query_engine = get_engine(instance=instance)
        # 循环获取表列表的表结构
        table_structures = []
        for tb_name in tb_name_list:
            query_result = query_engine.describe_table(
                db_name, tb_name, schema_name=schema_name
            )
            # 有些不存在表结构, 例如 redis
            if len(query_result.rows) != 0:
                table_structures.append(query_result.rows[0][-1])
        # 拼接所有表结构
        table_structure_str = "\n\n".join(table_structures)
        openai_client = OpenaiClient()
        result["data"] = openai_client.generate_sql_by_openai(
            db_type, table_structure_str, query_desc
        )
    except Exception as msg:
        result["status"] = 1
        result["msg"] = str(msg)
    return HttpResponse(json.dumps(result), content_type="application/json")


def check_openai(request):
    """
    校验openai配置是否存在
    :param request:
    :return:
    """
    config_validate = check_openai_config()
    if not config_validate:
        return HttpResponse(
            json.dumps(
                {
                    "status": 1,
                    "msg": "openai 缺少配置, 必需配置[openai_base_url, openai_api_key, default_chat_model]",
                    "data": False,
                }
            ),
            content_type="application/json",
        )

    return HttpResponse(
        json.dumps({"status": 0, "msg": "ok", "data": True}),
        content_type="application/json",
    )
