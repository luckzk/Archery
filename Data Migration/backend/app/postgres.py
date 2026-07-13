from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
import sqlparse
from psycopg import sql
from psycopg.rows import dict_row
from sqlparse.sql import TokenList
from sqlparse.tokens import Keyword, Whitespace, Newline, Comment

from .proxy_tunnel import proxy_tunnel
from .schemas import ConnectionTestResult, PostgresConnection


READONLY_SQL_PREFIXES = ("select", "with", "show", "explain", "values", "table")
LIMITABLE_SQL_PREFIXES = ("select", "with", "values", "table")
ROW_LIMIT_KEYWORDS = {"limit", "fetch"}
SQL_EDITOR_STATEMENT_TIMEOUT_MS = 60_000


def normalize_sql(statement: str) -> str:
    return statement.strip().rstrip(";").strip()


def is_single_statement(statement: str) -> bool:
    return len(sqlparse.split(statement)) == 1


def parsed_statement(statement: str):
    statements = sqlparse.parse(statement)
    if not statements:
        raise ValueError("SQL cannot be parsed")
    return statements[0]


def statement_type(statement: str) -> str:
    return parsed_statement(statement).get_type().lower()


def is_readonly_statement(statement: str) -> bool:
    parsed_type = statement_type(statement)
    if parsed_type in READONLY_SQL_PREFIXES:
        return True
    return parsed_type == "unknown" and statement.lstrip().lower().startswith(("show", "explain", "values", "table"))


def is_limitable_statement(statement: str) -> bool:
    parsed_type = statement_type(statement)
    if parsed_type in LIMITABLE_SQL_PREFIXES:
        return True
    return parsed_type == "unknown" and statement.lstrip().lower().startswith(("values", "table"))


def meaningful_top_level_tokens(token_list: TokenList):
    return [
        token
        for token in token_list.tokens
        if not token.is_whitespace
        and token.ttype not in (Whitespace, Newline)
        and not token.ttype in Comment
    ]


def has_top_level_row_limit(statement: str) -> bool:
    for token in meaningful_top_level_tokens(parsed_statement(statement)):
        token_value = token.value.lower()
        if token.ttype in Keyword and token_value.split()[0] in ROW_LIMIT_KEYWORDS:
            return True
    return False


def limit_query(statement: str, max_rows: int) -> sql.Composed:
    if not is_limitable_statement(statement) or has_top_level_row_limit(statement):
        return sql.SQL(statement)
    return sql.SQL("{query} LIMIT {limit}").format(
        query=sql.SQL(statement),
        limit=sql.Literal(max_rows + 1),
    )


def payload_from_instance(instance: dict[str, Any]) -> PostgresConnection:
    return PostgresConnection(
        host=instance["host"],
        port=instance["port"],
        database=instance["database_name"],
        username=instance["username"],
        password=instance["password"],
        sslmode=instance["sslmode"],
        proxy_type=instance.get("proxy_type"),
        proxy_host=instance.get("proxy_host"),
        proxy_port=instance.get("proxy_port"),
        proxy_username=instance.get("proxy_username"),
        proxy_password=instance.get("proxy_password"),
    )


def open_psycopg_connection(payload: PostgresConnection, host: str, port: int):
    return psycopg.connect(
        host=host,
        port=port,
        dbname=payload.database,
        user=payload.username,
        password=payload.password,
        sslmode=payload.sslmode,
        row_factory=dict_row,
        connect_timeout=10,
    )


@contextmanager
def connect(payload: PostgresConnection) -> Iterator[psycopg.Connection]:
    proxy_values = [payload.proxy_type, payload.proxy_host, payload.proxy_port]
    use_proxy = all(proxy_values)
    if any(proxy_values) and not use_proxy:
        raise ValueError("proxy_type, proxy_host and proxy_port must be provided together")

    if not use_proxy:
        with open_psycopg_connection(payload, payload.host, payload.port) as conn:
            yield conn
        return

    with proxy_tunnel(
        target_host=payload.host,
        target_port=payload.port,
        proxy_type=payload.proxy_type.value,
        proxy_host=payload.proxy_host,
        proxy_port=payload.proxy_port,
        proxy_username=payload.proxy_username,
        proxy_password=payload.proxy_password,
    ) as (local_host, local_port):
        with open_psycopg_connection(payload, local_host, local_port) as conn:
            yield conn


def test_postgres_connection(payload: PostgresConnection) -> ConnectionTestResult:
    try:
        with connect(payload) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      version() AS version,
                      current_database() AS database,
                      current_user AS username,
                      inet_server_addr()::text AS server_addr,
                      inet_server_port() AS server_port
                    """
                )
                metadata = cur.fetchone()
        return ConnectionTestResult(ok=True, message="Connection succeeded", metadata=metadata)
    except Exception as exc:
        return ConnectionTestResult(ok=False, message=str(exc), metadata=None)


def execute_sql(
    payload: PostgresConnection,
    statement: str,
    readonly: bool = True,
    max_rows: int = 200,
) -> dict[str, Any]:
    normalized = normalize_sql(statement)
    if not normalized:
        raise ValueError("SQL cannot be empty")
    if not is_single_statement(normalized):
        raise ValueError("Only one SQL statement can be executed at a time")
    if readonly and not is_readonly_statement(normalized):
        raise ValueError("Readonly mode only allows SELECT, WITH, SHOW, EXPLAIN, VALUES or TABLE statements")

    with connect(payload) as conn:
        with conn.cursor() as cur:
            if readonly:
                cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                sql.SQL("SET LOCAL statement_timeout = {}").format(
                    sql.Literal(SQL_EDITOR_STATEMENT_TIMEOUT_MS)
                )
            )

            query = limit_query(normalized, max_rows) if readonly else sql.SQL(normalized)
            cur.execute(query)
            executed_sql = query.as_string(conn)
            if cur.description:
                columns = [column.name for column in cur.description]
                rows = [dict(row) for row in cur.fetchmany(max_rows + 1)]
                truncated = len(rows) > max_rows
                visible_rows = rows[:max_rows]
                return {
                    "columns": columns,
                    "rows": visible_rows,
                    "row_count": len(visible_rows),
                    "status": cur.statusmessage,
                    "readonly": readonly,
                    "executed_sql": executed_sql,
                    "truncated": truncated,
                }
            if readonly:
                conn.rollback()
            else:
                conn.commit()
            return {
                "columns": [],
                "rows": [],
                "row_count": cur.rowcount if cur.rowcount >= 0 else 0,
                "status": cur.statusmessage,
                "readonly": readonly,
                "executed_sql": executed_sql,
                "truncated": False,
            }


def list_tables(payload: PostgresConnection, schemas: list[str] | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    schema_filter = ""
    if schemas:
        schema_filter = "AND n.nspname = ANY(%s)"
        params.append(schemas)

    with connect(payload) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
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
                  WHERE i.indrelid = c.oid
                    AND i.indisreplident = true
                  LIMIT 1
                ) ri ON true
                LEFT JOIN LATERAL (
                  SELECT
                    idx.relname AS primary_key_index,
                    array_agg(a.attname ORDER BY k.ord) AS primary_key_columns
                  FROM pg_index i
                  JOIN pg_class idx ON idx.oid = i.indexrelid
                  JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
                  JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                  WHERE i.indrelid = c.oid
                    AND i.indisprimary = true
                  GROUP BY idx.relname
                ) pk ON true
                LEFT JOIN LATERAL (
                  SELECT jsonb_agg(
                    jsonb_build_object(
                      'index_name', eligible_index.index_name,
                      'columns', eligible_index.columns
                    )
                    ORDER BY eligible_index.index_name
                  ) AS eligible_replica_identity_indexes
                  FROM (
                    SELECT
                      idx.relname AS index_name,
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
                """,
                params,
            )
            return list(cur.fetchall())


def set_replica_identity_using_index(
    payload: PostgresConnection,
    schema_name: str,
    table_name: str,
    index_name: str,
) -> dict[str, Any]:
    with connect(payload) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  idx.relname AS index_name,
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
                """,
                (schema_name, table_name, index_name),
            )
            index = cur.fetchone()
            if index is None:
                raise ValueError("index is not eligible for REPLICA IDENTITY USING INDEX")

            statement = sql.SQL("ALTER TABLE {} REPLICA IDENTITY USING INDEX {}").format(
                sql.Identifier(schema_name, table_name),
                sql.Identifier(index_name),
            )
            cur.execute(statement)
            conn.commit()
            return {
                "schema_name": schema_name,
                "table_name": table_name,
                "index_name": index_name,
                "columns": index["columns"],
                "sql": statement.as_string(conn),
            }


def scan_sequences(payload: PostgresConnection, schemas: list[str] | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    schema_filter = ""
    if schemas:
        schema_filter = "AND ps.schemaname = ANY(%s)"
        params.append(schemas)

    with connect(payload) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
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
                LEFT JOIN pg_depend dep
                  ON dep.objid = seq.oid
                  AND dep.deptype IN ('a', 'i')
                LEFT JOIN pg_class tbl ON tbl.oid = dep.refobjid
                LEFT JOIN pg_namespace tbl_ns ON tbl_ns.oid = tbl.relnamespace
                LEFT JOIN pg_attribute col
                  ON col.attrelid = tbl.oid
                  AND col.attnum = dep.refobjsubid
                WHERE ps.schemaname NOT IN ('pg_catalog', 'information_schema')
                  {schema_filter}
                ORDER BY ps.schemaname, ps.sequencename
                """,
                params,
            )
            return list(cur.fetchall())


def sequence_key(row: dict[str, Any]) -> tuple[str, str]:
    return row["sequence_schema"], row["sequence_name"]


def build_sequence_preview(
    source_payload: PostgresConnection,
    target_payload: PostgresConnection,
    step: int,
    schemas: list[str] | None,
    skip_if_target_greater: bool,
) -> list[dict[str, Any]]:
    source_sequences = scan_sequences(source_payload, schemas)
    target_sequences = {sequence_key(row): row for row in scan_sequences(target_payload, schemas)}
    preview: list[dict[str, Any]] = []

    for source in source_sequences:
        key = sequence_key(source)
        target = target_sequences.get(key)
        source_last_value = source["last_value"]
        target_current_value = target["last_value"] if target else None
        desired_value = None if source_last_value is None else int(source_last_value) + step
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

        qualified_name = f"{source['sequence_schema']}.{source['sequence_name']}"
        preview.append(
            {
                **source,
                "target_current_value": target_current_value,
                "target_value": desired_value,
                "should_apply": should_apply,
                "reason": reason,
                "setval_sql": f"SELECT setval('{qualified_name}', {desired_value}, true);"
                if desired_value is not None
                else None,
            }
        )
    return preview


def apply_sequence_values(target_payload: PostgresConnection, preview: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with connect(target_payload) as conn:
        with conn.cursor() as cur:
            for item in preview:
                if not item["should_apply"]:
                    results.append({**item, "status": "skipped"})
                    continue
                try:
                    cur.execute(
                        sql.SQL("SELECT setval({sequence_name}, {target_value}, true)").format(
                            sequence_name=sql.Literal(
                                f"{item['sequence_schema']}.{item['sequence_name']}"
                            ),
                            target_value=sql.Literal(item["target_value"]),
                        )
                    )
                    results.append({**item, "status": "applied"})
                except Exception as exc:
                    conn.rollback()
                    results.append({**item, "status": "failed", "error": str(exc)})
                else:
                    conn.commit()
    return results


def get_primary_key_columns(payload: PostgresConnection, schema_name: str, table_name: str) -> list[str]:
    with connect(payload) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT array_agg(a.attname ORDER BY k.ord) AS columns
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_index i ON i.indrelid = c.oid AND i.indisprimary = true
                JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
                JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
                WHERE n.nspname = %s
                  AND c.relname = %s
                """,
                (schema_name, table_name),
            )
            row = cur.fetchone()
    return row["columns"] or [] if row else []


def count_rows(payload: PostgresConnection, schema_name: str, table_name: str) -> int:
    with connect(payload) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT count(*) AS row_count FROM {}.{}").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                )
            )
            return int(cur.fetchone()["row_count"])


def primary_key_range(
    payload: PostgresConnection,
    schema_name: str,
    table_name: str,
    pk_column: str,
) -> dict[str, Any]:
    with connect(payload) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT min({pk}) AS min_value, max({pk}) AS max_value FROM {schema}.{table}").format(
                    pk=sql.Identifier(pk_column),
                    schema=sql.Identifier(schema_name),
                    table=sql.Identifier(table_name),
                )
            )
            return dict(cur.fetchone())
