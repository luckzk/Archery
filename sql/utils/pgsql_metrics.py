# -*- coding: UTF-8 -*-
import json
import logging
import time
from decimal import Decimal

import sqlparse
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

from sql.engines import get_engine
from sql.models import PgSQLMetricDefinition

logger = logging.getLogger("default")

SENSITIVE_WORDS = ("password", "passwd", "secret", "token", "host=", "user=")

BUILTIN_PGSQL_METRICS = [
    {
        "metric_key": "pgsql_lock_waiting_count",
        "metric_name": "锁等待数量",
        "description": "当前处于锁等待状态的会话数量。",
        "sql": "SELECT count(*) AS value FROM pg_stat_activity WHERE wait_event_type = 'Lock';",
        "value_column": "value",
        "timeout_ms": 3000,
    },
    {
        "metric_key": "pgsql_deadlocks_total",
        "metric_name": "死锁累计次数",
        "description": "当前数据库 pg_stat_database.deadlocks 累计值。",
        "sql": "SELECT sum(deadlocks) AS value FROM pg_stat_database;",
        "value_column": "value",
        "timeout_ms": 3000,
    },
    {
        "metric_key": "pgsql_connections_active",
        "metric_name": "活跃连接数",
        "description": "当前 active 状态连接数。",
        "sql": "SELECT count(*) AS value FROM pg_stat_activity WHERE state = 'active';",
        "value_column": "value",
        "timeout_ms": 3000,
    },
    {
        "metric_key": "pgsql_connections_total",
        "metric_name": "总连接数",
        "description": "当前 pg_stat_activity 连接总数。",
        "sql": "SELECT count(*) AS value FROM pg_stat_activity;",
        "value_column": "value",
        "timeout_ms": 3000,
    },
    {
        "metric_key": "pgsql_long_transaction_count",
        "metric_name": "长事务数量",
        "description": "事务持续超过 10 分钟的会话数量。",
        "sql": "SELECT count(*) AS value FROM pg_stat_activity WHERE xact_start IS NOT NULL AND now() - xact_start > interval '10 minutes';",
        "value_column": "value",
        "timeout_ms": 3000,
    },
    {
        "metric_key": "pgsql_idle_in_transaction_count",
        "metric_name": "idle in transaction 数量",
        "description": "当前 idle in transaction 状态会话数量。",
        "sql": "SELECT count(*) AS value FROM pg_stat_activity WHERE state = 'idle in transaction';",
        "value_column": "value",
        "timeout_ms": 3000,
    },
    {
        "metric_key": "pgsql_replication_lag_bytes_max",
        "metric_name": "复制 WAL 延迟最大字节数",
        "description": "基于 pg_stat_replication 计算的最大 WAL 发送延迟。",
        "sql": "SELECT COALESCE(max(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)), 0) AS value FROM pg_stat_replication;",
        "value_column": "value",
        "timeout_ms": 3000,
    },
    {
        "metric_key": "pgsql_replication_client_count",
        "metric_name": "复制客户端数量",
        "description": "当前 pg_stat_replication 复制客户端数量。",
        "sql": "SELECT count(*) AS value FROM pg_stat_replication;",
        "value_column": "value",
        "timeout_ms": 3000,
    },
    {
        "metric_key": "pgsql_subscription_disabled_count",
        "metric_name": "禁用订阅数量",
        "description": "当前禁用的逻辑订阅数量。",
        "sql": "SELECT count(*) AS value FROM pg_subscription WHERE NOT subenabled;",
        "value_column": "value",
        "timeout_ms": 3000,
    },
]


def sanitize_error(error):
    message = str(error or "")
    for word in SENSITIVE_WORDS:
        if word.lower() in message.lower():
            return "查询失败，错误信息包含敏感内容，已隐藏"
    return message[:1000]


def validate_metric_sql(sql):
    raw_sql = (sql or "").strip()
    if not raw_sql:
        return False, "SQL不能为空", ""

    formatted_sql = sqlparse.format(raw_sql, strip_comments=True).strip()
    statements = [statement.strip() for statement in sqlparse.split(formatted_sql) if statement.strip()]
    if len(statements) != 1:
        return False, "只允许单条SELECT语句", ""

    statement = sqlparse.parse(statements[0])[0]
    if statement.get_type() != "SELECT":
        return False, "只允许SELECT查询", ""

    return True, "", statements[0].rstrip(";")


def json_safe(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False))


def result_rows_to_dicts(result_set):
    columns = result_set.column_list or []
    rows = result_set.rows or []
    return [dict(zip(columns, row)) for row in rows]


def pick_metric_value(metric, rows):
    if not rows:
        return ""

    first_row = rows[0]
    if metric.value_column and metric.value_column in first_row:
        value = first_row.get(metric.value_column)
    else:
        value = next(iter(first_row.values()), "")

    if isinstance(value, Decimal):
        return str(value)
    if value is None:
        return ""
    return str(value)


def metric_applies_to_instance(metric, instance):
    selected_instances = metric.instances.filter(db_type="pgsql")
    return not selected_instances.exists() or selected_instances.filter(pk=instance.pk).exists()


def query_metric_for_instance(metric, instance):
    started = time.monotonic()
    ok, message, safe_sql = validate_metric_sql(metric.sql)
    if not ok:
        return {
            "metric_key": metric.metric_key,
            "metric_name": metric.metric_name,
            "description": metric.description,
            "status": "failed",
            "value": "",
            "value_json": {},
            "row_count": 0,
            "error": message,
            "elapsed_ms": 0,
        }

    try:
        engine = get_engine(instance=instance)
        result_set = engine.query(
            db_name=metric.db_name or instance.db_name or None,
            sql=safe_sql,
            max_execution_time=metric.timeout_ms,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if result_set.error:
            return {
                "metric_key": metric.metric_key,
                "metric_name": metric.metric_name,
                "description": metric.description,
                "status": "failed",
                "value": "",
                "value_json": {},
                "row_count": 0,
                "error": sanitize_error(result_set.error),
                "elapsed_ms": elapsed_ms,
            }

        rows = json_safe(result_rows_to_dicts(result_set))
        value = pick_metric_value(metric, rows)
        return {
            "metric_key": metric.metric_key,
            "metric_name": metric.metric_name,
            "description": metric.description,
            "status": "success",
            "value": value,
            "value_json": {"columns": result_set.column_list, "rows": rows},
            "row_count": len(rows),
            "error": "",
            "elapsed_ms": elapsed_ms,
        }
    except Exception as e:
        logger.warning(f"PostgreSQL指标实时查询失败 metric={metric.metric_key} instance={instance.id}: {e}")
        return {
            "metric_key": metric.metric_key,
            "metric_name": metric.metric_name,
            "description": metric.description,
            "status": "failed",
            "value": "",
            "value_json": {},
            "row_count": 0,
            "error": sanitize_error(e),
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }


def query_pgsql_metrics_for_instance(instance):
    metrics = PgSQLMetricDefinition.objects.filter(enabled=True).order_by("id")
    rows = []
    for metric in metrics:
        if metric_applies_to_instance(metric, instance):
            rows.append(query_metric_for_instance(metric, instance))
    return rows


@transaction.atomic
def seed_builtin_pgsql_metrics():
    created = 0
    updated = 0
    for metric in BUILTIN_PGSQL_METRICS:
        defaults = dict(metric)
        metric_key = defaults.pop("metric_key")
        _, is_created = PgSQLMetricDefinition.objects.update_or_create(
            metric_key=metric_key,
            defaults=defaults,
        )
        if is_created:
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated}
