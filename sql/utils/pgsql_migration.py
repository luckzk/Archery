# -*- coding: UTF-8 -*-
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.utils import timezone
from psycopg2 import sql

from common.utils.extend_json_encoder import ExtendJSONEncoder
from sql.engines import get_engine
from sql.models import (
    Instance,
    PgSQLMigrationDataCheckResult,
    PgSQLMigrationSequenceResult,
    PgSQLMigrationTask,
    PgSQLMigrationTaskLog,
)

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.$-]+$")


def quote_pg_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def quote_pg_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def format_pg_qualified_identifier(schema_name: str, object_name: str) -> str:
    return f"{quote_pg_identifier(schema_name)}.{quote_pg_identifier(object_name)}"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, cls=ExtendJSONEncoder)


def json_loads(value: str, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


def parse_csv(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def parse_tables(value: str) -> List[Dict[str, str]]:
    tables = []
    for raw_item in parse_csv(value):
        if "." not in raw_item:
            raise ValueError("表范围格式应为 schema.table，多个表用逗号分隔")
        schema_name, table_name = raw_item.split(".", 1)
        validate_identifier(schema_name, "Schema名称")
        validate_identifier(table_name, "表名")
        tables.append({"schema_name": schema_name, "table_name": table_name})
    return tables


def validate_identifier(value: str, label: str = "标识符") -> None:
    if not value or not IDENTIFIER_PATTERN.match(value):
        raise ValueError(f"{label}只允许字母、数字、下划线、点、美元符号和短横线")


def task_schemas(task: PgSQLMigrationTask) -> Optional[List[str]]:
    return json_loads(task.schemas_json, None)


def task_tables(task: PgSQLMigrationTask) -> Optional[List[Dict[str, str]]]:
    return json_loads(task.tables_json, None)


def task_to_dict(task: PgSQLMigrationTask) -> Dict[str, Any]:
    return {
        "id": task.id,
        "name": task.name,
        "source_instance_id": task.source_instance_id,
        "source_instance_name": task.source_instance.instance_name,
        "target_instance_id": task.target_instance_id,
        "target_instance_name": task.target_instance.instance_name,
        "schemas": task_schemas(task),
        "tables": task_tables(task),
        "status": task.status,
        "description": task.description,
        "user_display": task.user_display,
        "create_time": task.create_time,
        "update_time": task.update_time,
    }


def create_task_log(task: PgSQLMigrationTask, operation: str, status: str, message: str, details: Any = None) -> PgSQLMigrationTaskLog:
    return PgSQLMigrationTaskLog.objects.create(
        task=task,
        operation=operation,
        status=status,
        message=message,
        details_json=json_dumps(details) if details is not None else "",
    )


def finish_task_log(log: PgSQLMigrationTaskLog, status: str, message: str, details: Any = None) -> None:
    log.status = status
    log.message = message
    log.details_json = json_dumps(details) if details is not None else log.details_json
    log.finish_time = timezone.now()
    log.save(update_fields=["status", "message", "details_json", "finish_time"])


def get_pgsql_engine(instance: Instance, db_name: Optional[str] = None):
    if instance.db_type != "pgsql":
        raise ValueError("仅支持 PostgreSQL 实例")
    engine = get_engine(instance=instance)
    if db_name:
        engine.db_name = db_name
    return engine


def fetchall_dict(engine, query: Any, params: Optional[Iterable[Any]] = None, db_name: Optional[str] = None, readonly: bool = True) -> List[Dict[str, Any]]:
    conn = None
    cursor = None
    try:
        conn = engine.get_connection(db_name=db_name)
        conn.autocommit = False
        cursor = conn.cursor()
        if readonly:
            cursor.execute("SET transaction ISOLATION LEVEL READ COMMITTED READ ONLY;")
        else:
            cursor.execute("SET transaction ISOLATION LEVEL READ COMMITTED READ WRITE;")
        cursor.execute(query, params)
        fields = [field[0] for field in cursor.description] if cursor.description else []
        rows = [dict(zip(fields, row)) for row in cursor.fetchall()]
        conn.commit()
        return rows
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        engine.close()


def execute_statement(engine, statement: Any, params: Optional[Iterable[Any]] = None, db_name: Optional[str] = None) -> Dict[str, Any]:
    conn = None
    cursor = None
    try:
        conn = engine.get_connection(db_name=db_name)
        conn.autocommit = False
        cursor = conn.cursor()
        cursor.execute("SET transaction ISOLATION LEVEL READ COMMITTED READ WRITE;")
        cursor.execute(statement, params)
        fields = [field[0] for field in cursor.description] if cursor.description else []
        rows = [dict(zip(fields, row)) for row in cursor.fetchall()] if fields else []
        conn.commit()
        return {"columns": fields, "rows": rows, "rowcount": cursor.rowcount}
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        engine.close()


def list_tables(instance: Instance, schemas: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    for schema_name in schemas or []:
        validate_identifier(schema_name, "Schema名称")
    params: List[Any] = []
    schema_filter = ""
    if schemas:
        schema_filter = "AND n.nspname = ANY(%s)"
        params.append(schemas)
    engine = get_pgsql_engine(instance)
    query = f"""
        SELECT
          n.nspname AS schema_name,
          c.relname AS table_name,
          c.reltuples::bigint AS estimated_rows,
          CASE c.relreplident
            WHEN 'd' THEN 'DEFAULT'
            WHEN 'n' THEN 'NOTHING'
            WHEN 'f' THEN 'FULL'
            WHEN 'i' THEN 'USING INDEX'
          END AS replica_identity,
          ri.index_name AS replica_identity_index,
          pk.primary_key_index,
          pk.primary_key_columns,
          eligible.eligible_replica_identity_indexes
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN LATERAL (
          SELECT idx.relname AS index_name
          FROM pg_index i
          JOIN pg_class idx ON idx.oid = i.indexrelid
          WHERE i.indrelid = c.oid AND i.indisreplident = true
          LIMIT 1
        ) ri ON true
        LEFT JOIN LATERAL (
          SELECT idx.relname AS primary_key_index,
                 array_agg(a.attname ORDER BY k.ord) AS primary_key_columns
          FROM pg_index i
          JOIN pg_class idx ON idx.oid = i.indexrelid
          JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
          JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
          WHERE i.indrelid = c.oid AND i.indisprimary = true
          GROUP BY idx.relname
        ) pk ON true
        LEFT JOIN LATERAL (
          SELECT jsonb_agg(
            jsonb_build_object('index_name', eligible_index.index_name, 'columns', eligible_index.columns)
            ORDER BY eligible_index.index_name
          ) AS eligible_replica_identity_indexes
          FROM (
            SELECT idx.relname AS index_name,
                   array_agg(a.attname ORDER BY k.ord) AS columns
            FROM pg_index i
            JOIN pg_class idx ON idx.oid = i.indexrelid
            JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
            WHERE i.indrelid = c.oid
              AND i.indisunique = true
              AND i.indisvalid = true
              AND i.indimmediate = true
              AND i.indpred IS NULL
              AND i.indexprs IS NULL
            GROUP BY idx.relname
            HAVING bool_and(a.attnotnull)
          ) eligible_index
        ) eligible ON true
        WHERE c.relkind IN ('r', 'p')
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {schema_filter}
        ORDER BY n.nspname, c.relname
    """
    return fetchall_dict(engine, query, params)


def scan_sequences(instance: Instance, schemas: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    for schema_name in schemas or []:
        validate_identifier(schema_name, "Schema名称")
    params: List[Any] = []
    schema_filter = ""
    if schemas:
        schema_filter = "AND ps.schemaname = ANY(%s)"
        params.append(schemas)
    engine = get_pgsql_engine(instance)
    query = f"""
        SELECT
          ps.schemaname AS sequence_schema,
          ps.sequencename AS sequence_name,
          ps.last_value,
          ps.increment_by,
          ps.cycle,
          ps.cache_size,
          tbl_ns.nspname AS table_schema,
          tbl.relname AS table_name,
          col.attname AS column_name
        FROM pg_sequences ps
        JOIN pg_namespace seq_ns ON seq_ns.nspname = ps.schemaname
        JOIN pg_class seq ON seq.relnamespace = seq_ns.oid
          AND seq.relname = ps.sequencename
          AND seq.relkind = 'S'
        LEFT JOIN pg_depend dep ON dep.objid = seq.oid AND dep.deptype IN ('a', 'i')
        LEFT JOIN pg_class tbl ON tbl.oid = dep.refobjid
        LEFT JOIN pg_namespace tbl_ns ON tbl_ns.oid = tbl.relnamespace
        LEFT JOIN pg_attribute col ON col.attrelid = tbl.oid AND col.attnum = dep.refobjsubid
        WHERE ps.schemaname NOT IN ('pg_catalog', 'information_schema')
          {schema_filter}
        ORDER BY ps.schemaname, ps.sequencename
    """
    return fetchall_dict(engine, query, params)


def sequence_key(row: Dict[str, Any]) -> Tuple[str, str]:
    return row["sequence_schema"], row["sequence_name"]


def build_sequence_preview(source_instance: Instance, target_instance: Instance, step: int, schemas: Optional[List[str]], skip_if_target_greater: bool) -> List[Dict[str, Any]]:
    source_sequences = scan_sequences(source_instance, schemas)
    target_sequences = {sequence_key(row): row for row in scan_sequences(target_instance, schemas)}
    preview = []
    for source in source_sequences:
        key = sequence_key(source)
        target = target_sequences.get(key)
        source_last_value = source.get("last_value")
        target_current_value = target.get("last_value") if target else None
        desired_value = None if source_last_value is None else int(source_last_value) + int(step)
        should_apply = target is not None and desired_value is not None
        reason = "ready"
        if target is None:
            should_apply = False
            reason = "target sequence not found"
        elif desired_value is None:
            should_apply = False
            reason = "source last_value is null"
        elif skip_if_target_greater and target_current_value is not None and int(target_current_value) > desired_value:
            should_apply = False
            reason = "target value is already greater"
        qualified_name = format_pg_qualified_identifier(source["sequence_schema"], source["sequence_name"])
        preview.append({
            **source,
            "target_current_value": target_current_value,
            "target_value": desired_value,
            "should_apply": should_apply,
            "reason": reason,
            "setval_sql": f"SELECT setval({quote_pg_string_literal(qualified_name)}, {desired_value}, true);" if desired_value is not None else "",
        })
    return preview


def _schema_filter_sql(alias: str, schemas: Optional[List[str]], params: List[Any]) -> str:
    if not schemas:
        return ""
    params.append(schemas)
    return f"AND {alias} = ANY(%s)"


def _map_rows(rows: List[Dict[str, Any]], key_fields: Iterable[str]) -> Dict[Tuple[Any, ...], Dict[str, Any]]:
    keys = list(key_fields)
    return {tuple(row.get(field) for field in keys): row for row in rows}


def _compare_feature_rows(feature_type: str, source_rows: List[Dict[str, Any]], target_rows: List[Dict[str, Any]], key_fields: Iterable[str], compare_fields: Iterable[str]) -> List[Dict[str, Any]]:
    source_map = _map_rows(source_rows, key_fields)
    target_map = _map_rows(target_rows, key_fields)
    results = []
    for key in sorted(set(source_map.keys()) | set(target_map.keys())):
        source = source_map.get(key)
        target = target_map.get(key)
        status = "passed"
        message = "一致"
        if source and not target:
            status = "missing_target"
            message = "目标缺失"
        elif target and not source:
            status = "extra_target"
            message = "目标多出"
        else:
            diffs = [
                field
                for field in compare_fields
                if source.get(field) != target.get(field)
            ]
            if diffs:
                status = "different"
                message = "字段不一致: " + ",".join(diffs)
        results.append({
            "feature_type": feature_type,
            "object_key": ".".join([str(part) for part in key if part not in (None, "")]),
            "status": status,
            "message": message,
            "source": source,
            "target": target,
        })
    return results


def scan_feature_inventory(instance: Instance, schemas: Optional[List[str]] = None) -> Dict[str, List[Dict[str, Any]]]:
    for schema_name in schemas or []:
        validate_identifier(schema_name, "Schema名称")
    engine = get_pgsql_engine(instance)
    inventory: Dict[str, List[Dict[str, Any]]] = {}
    inventory["extension"] = fetchall_dict(engine, """
        SELECT extname AS name, extversion AS version
        FROM pg_extension
        ORDER BY extname
    """)
    inventory["collation"] = fetchall_dict(engine, """
        SELECT n.nspname AS schema_name, c.collname AS name,
               c.collprovider AS provider, c.collcollate AS collate, c.collctype AS ctype
        FROM pg_collation c
        JOIN pg_namespace n ON n.oid = c.collnamespace
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY n.nspname, c.collname
    """)
    inventory["role"] = fetchall_dict(engine, """
        SELECT rolname AS name, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolcanlogin
        FROM pg_roles
        WHERE rolname NOT LIKE 'pg_%'
        ORDER BY rolname
    """)

    params: List[Any] = []
    schema_filter = _schema_filter_sql("n.nspname", schemas, params)
    inventory["owner"] = fetchall_dict(engine, f"""
        SELECT n.nspname AS schema_name, c.relname AS object_name,
               c.relkind::text AS object_type, pg_get_userbyid(c.relowner) AS owner
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relkind IN ('r', 'p', 'm', 'S', 'v')
          {schema_filter}
        ORDER BY n.nspname, c.relname
    """, params)

    params = []
    schema_filter = _schema_filter_sql("seq_ns.nspname", schemas, params)
    inventory["sequence_ownership"] = fetchall_dict(engine, f"""
        SELECT seq_ns.nspname AS sequence_schema, seq.relname AS sequence_name,
               tbl_ns.nspname AS table_schema, tbl.relname AS table_name, col.attname AS column_name
        FROM pg_class seq
        JOIN pg_namespace seq_ns ON seq_ns.oid = seq.relnamespace
        LEFT JOIN pg_depend dep ON dep.objid = seq.oid AND dep.deptype IN ('a', 'i')
        LEFT JOIN pg_class tbl ON tbl.oid = dep.refobjid
        LEFT JOIN pg_namespace tbl_ns ON tbl_ns.oid = tbl.relnamespace
        LEFT JOIN pg_attribute col ON col.attrelid = tbl.oid AND col.attnum = dep.refobjsubid
        WHERE seq.relkind = 'S'
          AND seq_ns.nspname NOT IN ('pg_catalog', 'information_schema')
          {schema_filter}
        ORDER BY seq_ns.nspname, seq.relname
    """, params)

    params = []
    schema_filter = _schema_filter_sql("n.nspname", schemas, params)
    inventory["identity_generated"] = fetchall_dict(engine, f"""
        SELECT n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
               a.attidentity AS identity_type, a.attgenerated AS generated_type,
               pg_get_expr(def.adbin, def.adrelid) AS default_expr
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef def ON def.adrelid = a.attrelid AND def.adnum = a.attnum
        WHERE a.attnum > 0
          AND NOT a.attisdropped
          AND c.relkind IN ('r', 'p')
          AND (a.attidentity <> '' OR a.attgenerated <> '')
          {schema_filter}
        ORDER BY n.nspname, c.relname, a.attname
    """, params)

    params = []
    schema_filter = _schema_filter_sql("n.nspname", schemas, params)
    inventory["partition"] = fetchall_dict(engine, f"""
        SELECT n.nspname AS schema_name, c.relname AS table_name,
               parent_ns.nspname AS parent_schema, parent.relname AS parent_table,
               pg_get_expr(c.relpartbound, c.oid) AS partition_bound
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_inherits inh ON inh.inhrelid = c.oid
        LEFT JOIN pg_class parent ON parent.oid = inh.inhparent
        LEFT JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
        WHERE c.relkind IN ('r', 'p')
          AND (c.relispartition OR c.relkind = 'p')
          {schema_filter}
        ORDER BY n.nspname, c.relname
    """, params)

    params = []
    schema_filter = _schema_filter_sql("schemaname", schemas, params)
    inventory["materialized_view"] = fetchall_dict(engine, f"""
        SELECT schemaname AS schema_name, matviewname AS object_name,
               matviewowner AS owner, ispopulated, definition
        FROM pg_matviews
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
          {schema_filter}
        ORDER BY schemaname, matviewname
    """, params)

    params = []
    schema_filter = _schema_filter_sql("n.nspname", schemas, params)
    inventory["routine"] = fetchall_dict(engine, f"""
        SELECT n.nspname AS schema_name, p.proname AS routine_name,
               p.prokind::text AS routine_type,
               pg_get_function_identity_arguments(p.oid) AS identity_arguments,
               pg_get_function_result(p.oid) AS result_type,
               l.lanname AS language,
               pg_get_userbyid(p.proowner) AS owner
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_language l ON l.oid = p.prolang
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND p.prokind IN ('f', 'p')
          {schema_filter}
        ORDER BY n.nspname, p.proname, pg_get_function_identity_arguments(p.oid)
    """, params)

    params = []
    schema_filter = _schema_filter_sql("n.nspname", schemas, params)
    inventory["trigger"] = fetchall_dict(engine, f"""
        SELECT n.nspname AS schema_name, c.relname AS table_name,
               t.tgname AS trigger_name, pg_get_triggerdef(t.oid, true) AS definition
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE NOT t.tgisinternal
          {schema_filter}
        ORDER BY n.nspname, c.relname, t.tgname
    """, params)
    return inventory


def run_feature_checks(source_instance: Instance, target_instance: Instance, schemas: Optional[List[str]]) -> List[Dict[str, Any]]:
    source = scan_feature_inventory(source_instance, schemas)
    target = scan_feature_inventory(target_instance, schemas)
    checks: List[Dict[str, Any]] = []
    checks.extend(_compare_feature_rows("extension", source["extension"], target["extension"], ["name"], ["version"]))
    checks.extend(_compare_feature_rows("collation", source["collation"], target["collation"], ["schema_name", "name"], ["provider", "collate", "ctype"]))
    checks.extend(_compare_feature_rows("role", source["role"], target["role"], ["name"], ["rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolcanlogin"]))
    checks.extend(_compare_feature_rows("owner", source["owner"], target["owner"], ["schema_name", "object_name", "object_type"], ["owner"]))
    checks.extend(_compare_feature_rows("sequence_ownership", source["sequence_ownership"], target["sequence_ownership"], ["sequence_schema", "sequence_name"], ["table_schema", "table_name", "column_name"]))
    checks.extend(_compare_feature_rows("identity_generated", source["identity_generated"], target["identity_generated"], ["schema_name", "table_name", "column_name"], ["identity_type", "generated_type", "default_expr"]))
    checks.extend(_compare_feature_rows("partition", source["partition"], target["partition"], ["schema_name", "table_name"], ["parent_schema", "parent_table", "partition_bound"]))
    checks.extend(_compare_feature_rows("materialized_view", source["materialized_view"], target["materialized_view"], ["schema_name", "object_name"], ["owner", "ispopulated", "definition"]))
    checks.extend(_compare_feature_rows("routine", source["routine"], target["routine"], ["schema_name", "routine_name", "routine_type", "identity_arguments"], ["result_type", "language", "owner"]))
    checks.extend(_compare_feature_rows("trigger", source["trigger"], target["trigger"], ["schema_name", "table_name", "trigger_name"], ["definition"]))
    return checks


def save_sequence_results(task: PgSQLMigrationTask, operation: str, items: List[Dict[str, Any]]) -> None:
    PgSQLMigrationSequenceResult.objects.filter(task=task, operation=operation).delete()
    objects = []
    for item in items:
        objects.append(PgSQLMigrationSequenceResult(
            task=task,
            operation=operation,
            sequence_schema=item.get("sequence_schema") or "",
            sequence_name=item.get("sequence_name") or "",
            table_schema=item.get("table_schema") or "",
            table_name=item.get("table_name") or "",
            column_name=item.get("column_name") or "",
            source_last_value=item.get("last_value") or item.get("source_last_value"),
            target_current_value=item.get("target_current_value"),
            target_value=item.get("target_value"),
            should_apply=bool(item.get("should_apply")),
            reason=item.get("reason") or "",
            setval_sql=item.get("setval_sql") or "",
            status=item.get("status") or "",
            error=item.get("error") or "",
        ))
    PgSQLMigrationSequenceResult.objects.bulk_create(objects)


def apply_sequence_values(target_instance: Instance, preview: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    engine = get_pgsql_engine(target_instance)
    results = []
    for item in preview:
        if not item.get("should_apply"):
            results.append({**item, "status": "skipped"})
            continue
        try:
            qualified_name = format_pg_qualified_identifier(item["sequence_schema"], item["sequence_name"])
            execute_statement(engine, "SELECT setval(%s::regclass, %s, true)", [qualified_name, item["target_value"]])
            results.append({**item, "status": "applied"})
        except Exception as exc:
            results.append({**item, "status": "failed", "error": str(exc)})
    return results


def get_primary_key_columns(instance: Instance, schema_name: str, table_name: str) -> List[str]:
    validate_identifier(schema_name, "Schema名称")
    validate_identifier(table_name, "表名")
    engine = get_pgsql_engine(instance)
    rows = fetchall_dict(engine, """
        SELECT array_agg(a.attname ORDER BY k.ord) AS columns
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_index i ON i.indrelid = c.oid AND i.indisprimary = true
        JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
        WHERE n.nspname = %s AND c.relname = %s
    """, [schema_name, table_name])
    return rows[0].get("columns") or [] if rows else []


def count_rows(instance: Instance, schema_name: str, table_name: str) -> int:
    validate_identifier(schema_name, "Schema名称")
    validate_identifier(table_name, "表名")
    engine = get_pgsql_engine(instance)
    query = sql.SQL("SELECT count(*) AS row_count FROM {}.{}").format(sql.Identifier(schema_name), sql.Identifier(table_name))
    rows = fetchall_dict(engine, query)
    return int(rows[0]["row_count"])


def primary_key_range(instance: Instance, schema_name: str, table_name: str, pk_column: str) -> Dict[str, Any]:
    validate_identifier(schema_name, "Schema名称")
    validate_identifier(table_name, "表名")
    validate_identifier(pk_column, "主键字段")
    engine = get_pgsql_engine(instance)
    query = sql.SQL("SELECT min({pk}) AS min_value, max({pk}) AS max_value FROM {schema}.{table}").format(
        pk=sql.Identifier(pk_column),
        schema=sql.Identifier(schema_name),
        table=sql.Identifier(table_name),
    )
    rows = fetchall_dict(engine, query)
    return rows[0] if rows else {"min_value": None, "max_value": None}


def run_table_checks(source_instance: Instance, target_instance: Instance, tables: List[Dict[str, str]], exact_count: bool, include_pk_range: bool) -> List[Dict[str, Any]]:
    results = []
    for table in tables:
        schema_name = table["schema_name"]
        table_name = table["table_name"]
        checks = []
        status = "passed"
        if exact_count:
            try:
                source_count = count_rows(source_instance, schema_name, table_name)
                target_count = count_rows(target_instance, schema_name, table_name)
                count_status = "passed" if source_count == target_count else "failed"
                if count_status == "failed":
                    status = "failed"
                checks.append({"type": "exact_count", "source_value": source_count, "target_value": target_count, "status": count_status})
            except Exception as exc:
                status = "failed"
                checks.append({"type": "exact_count", "status": "failed", "message": str(exc)})
        if include_pk_range:
            try:
                pk_columns = get_primary_key_columns(source_instance, schema_name, table_name)
                if len(pk_columns) != 1:
                    checks.append({"type": "primary_key_range", "status": "warning", "message": "primary key range check requires exactly one primary key column", "primary_key_columns": pk_columns})
                    if status != "failed":
                        status = "warning"
                else:
                    pk = pk_columns[0]
                    source_range = primary_key_range(source_instance, schema_name, table_name, pk)
                    target_range = primary_key_range(target_instance, schema_name, table_name, pk)
                    range_status = "passed" if source_range == target_range else "failed"
                    if range_status == "failed":
                        status = "failed"
                    checks.append({"type": "primary_key_range", "primary_key_column": pk, "source_value": source_range, "target_value": target_range, "status": range_status})
            except Exception as exc:
                status = "failed"
                checks.append({"type": "primary_key_range", "status": "failed", "message": str(exc)})
        results.append({"schema_name": schema_name, "table_name": table_name, "status": status, "checks": checks})
    return results


def save_data_check_results(task: PgSQLMigrationTask, items: List[Dict[str, Any]]) -> None:
    PgSQLMigrationDataCheckResult.objects.filter(task=task).delete()
    PgSQLMigrationDataCheckResult.objects.bulk_create([
        PgSQLMigrationDataCheckResult(
            task=task,
            schema_name=item["schema_name"],
            table_name=item["table_name"],
            status=item["status"],
            checks_json=json_dumps(item.get("checks", [])),
        )
        for item in items
    ])


def set_replica_identity_using_index(instance: Instance, schema_name: str, table_name: str, index_name: str) -> Dict[str, Any]:
    validate_identifier(schema_name, "Schema名称")
    validate_identifier(table_name, "表名")
    validate_identifier(index_name, "索引名")
    engine = get_pgsql_engine(instance)
    rows = fetchall_dict(engine, """
        SELECT idx.relname AS index_name,
               array_agg(a.attname ORDER BY k.ord) AS columns
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_index i ON i.indrelid = c.oid
        JOIN pg_class idx ON idx.oid = i.indexrelid
        JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
        WHERE n.nspname = %s
          AND c.relname = %s
          AND idx.relname = %s
          AND i.indisunique = true
          AND i.indisvalid = true
          AND i.indimmediate = true
          AND i.indpred IS NULL
          AND i.indexprs IS NULL
        GROUP BY idx.relname
        HAVING bool_and(a.attnotnull)
    """, [schema_name, table_name, index_name])
    if not rows:
        raise ValueError("索引不满足 REPLICA IDENTITY USING INDEX 条件")
    statement = sql.SQL("ALTER TABLE {} REPLICA IDENTITY USING INDEX {}").format(
        sql.Identifier(schema_name, table_name),
        sql.Identifier(index_name),
    )
    execute_statement(engine, statement)
    return {
        "schema_name": schema_name,
        "table_name": table_name,
        "index_name": index_name,
        "columns": rows[0].get("columns") or [],
        "sql": f"ALTER TABLE {format_pg_qualified_identifier(schema_name, table_name)} REPLICA IDENTITY USING INDEX {quote_pg_identifier(index_name)}",
    }
