from __future__ import annotations

import json
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException

from .db import get_connection, row_to_dict
from .instances import get_instance_or_404
from .postgres import (
    apply_sequence_values,
    build_sequence_preview,
    count_rows,
    get_primary_key_columns,
    payload_from_instance,
    primary_key_range,
    set_replica_identity_using_index,
)
from .schemas import (
    CheckStatus,
    MigrationTaskCreate,
    MigrationTaskOut,
    TableCheckResult,
    TableRef,
    TaskDataCheckRequest,
    TaskReplicaIdentityUsingIndexRequest,
    TaskSequenceApplyRequest,
    TaskSequencePreviewRequest,
    TaskStatus,
)

router = APIRouter(prefix="/api/tasks", tags=["migration-tasks"])


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def json_loads(value: Optional[str], default: Any = None) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


def table_refs_to_json(tables: Optional[List[TableRef]]) -> Optional[str]:
    if tables is None:
        return None
    return json_dumps([table.model_dump() for table in tables])


def row_to_task(row: dict[str, Any]) -> MigrationTaskOut:
    tables = json_loads(row["tables_json"], None)
    return MigrationTaskOut(
        id=row["id"],
        name=row["name"],
        source_instance_id=row["source_instance_id"],
        target_instance_id=row["target_instance_id"],
        schemas=json_loads(row["schemas_json"], None),
        tables=[TableRef(**item) for item in tables] if tables is not None else None,
        status=row["status"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_task_or_404(task_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM migration_tasks WHERE id = ?", (task_id,)).fetchone()
    data = row_to_dict(row)
    if data is None:
        raise HTTPException(status_code=404, detail="Migration task not found")
    return data


def update_task_status(task_id: int, status: TaskStatus) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE migration_tasks SET status = ? WHERE id = ?", (status.value, task_id))


def create_log(task_id: int, operation: str, status: str, message: str, details: Any = None) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO task_logs (task_id, operation, status, message, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, operation, status, message, json_dumps(details) if details is not None else None),
        )
        return int(cursor.lastrowid)


def finish_log(log_id: int, status: str, message: str, details: Any = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE task_logs
            SET status = ?, message = ?, details_json = ?, finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, message, json_dumps(details) if details is not None else None, log_id),
        )


def task_payloads(task: dict[str, Any]):
    source = payload_from_instance(get_instance_or_404(task["source_instance_id"]))
    target = payload_from_instance(get_instance_or_404(task["target_instance_id"]))
    return source, target


def save_sequence_results(task_id: int, operation: str, items: list[dict[str, Any]]) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM sequence_results WHERE task_id = ? AND operation = ?",
            (task_id, operation),
        )
        conn.executemany(
            """
            INSERT INTO sequence_results (
                task_id, operation, sequence_schema, sequence_name, table_schema, table_name,
                column_name, source_last_value, target_current_value, target_value,
                should_apply, reason, setval_sql, status, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    task_id,
                    operation,
                    item.get("sequence_schema"),
                    item.get("sequence_name"),
                    item.get("table_schema"),
                    item.get("table_name"),
                    item.get("column_name"),
                    item.get("last_value"),
                    item.get("target_current_value"),
                    item.get("target_value"),
                    1 if item.get("should_apply") else 0,
                    item.get("reason"),
                    item.get("setval_sql"),
                    item.get("status"),
                    item.get("error"),
                )
                for item in items
            ],
        )


def save_data_check_results(task_id: int, items: list[TableCheckResult]) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM data_check_results WHERE task_id = ?", (task_id,))
        conn.executemany(
            """
            INSERT INTO data_check_results (task_id, schema_name, table_name, status, checks_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    task_id,
                    item.schema_name,
                    item.table_name,
                    item.status.value,
                    json_dumps(item.checks),
                )
                for item in items
            ],
        )


def run_table_checks(source, target, tables: List[TableRef], exact_count: bool, include_pk_range: bool) -> List[TableCheckResult]:
    results: List[TableCheckResult] = []

    for table in tables:
        checks = []
        status = CheckStatus.passed

        if exact_count:
            try:
                source_count = count_rows(source, table.schema_name, table.table_name)
                target_count = count_rows(target, table.schema_name, table.table_name)
                count_status = "passed" if source_count == target_count else "failed"
                if count_status == "failed":
                    status = CheckStatus.failed
                checks.append(
                    {
                        "type": "exact_count",
                        "source_value": source_count,
                        "target_value": target_count,
                        "status": count_status,
                    }
                )
            except Exception as exc:
                status = CheckStatus.failed
                checks.append({"type": "exact_count", "status": "failed", "message": str(exc)})

        if include_pk_range:
            try:
                pk_columns = get_primary_key_columns(source, table.schema_name, table.table_name)
                if len(pk_columns) != 1:
                    checks.append(
                        {
                            "type": "primary_key_range",
                            "status": "warning",
                            "message": "primary key range check requires exactly one primary key column",
                            "primary_key_columns": pk_columns,
                        }
                    )
                    if status != CheckStatus.failed:
                        status = CheckStatus.warning
                else:
                    pk = pk_columns[0]
                    source_range = primary_key_range(source, table.schema_name, table.table_name, pk)
                    target_range = primary_key_range(target, table.schema_name, table.table_name, pk)
                    range_status = "passed" if source_range == target_range else "failed"
                    if range_status == "failed":
                        status = CheckStatus.failed
                    checks.append(
                        {
                            "type": "primary_key_range",
                            "primary_key_column": pk,
                            "source_value": source_range,
                            "target_value": target_range,
                            "status": range_status,
                        }
                    )
            except Exception as exc:
                status = CheckStatus.failed
                checks.append({"type": "primary_key_range", "status": "failed", "message": str(exc)})

        results.append(
            TableCheckResult(
                schema_name=table.schema_name,
                table_name=table.table_name,
                status=status,
                checks=checks,
            )
        )

    return results


@router.post("", response_model=MigrationTaskOut)
def create_task(payload: MigrationTaskCreate) -> MigrationTaskOut:
    get_instance_or_404(payload.source_instance_id)
    get_instance_or_404(payload.target_instance_id)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO migration_tasks (
                name, source_instance_id, target_instance_id, schemas_json, tables_json, description
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.source_instance_id,
                payload.target_instance_id,
                json_dumps(payload.schemas) if payload.schemas is not None else None,
                table_refs_to_json(payload.tables),
                payload.description,
            ),
        )
        row = conn.execute("SELECT * FROM migration_tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()

    task = row_to_task(dict(row))
    create_log(task.id, "task.create", "succeeded", "Migration task created")
    return task


@router.get("", response_model=list[MigrationTaskOut])
def list_tasks() -> list[MigrationTaskOut]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM migration_tasks ORDER BY id DESC").fetchall()
    return [row_to_task(dict(row)) for row in rows]


@router.get("/{task_id}", response_model=MigrationTaskOut)
def get_task(task_id: int) -> MigrationTaskOut:
    return row_to_task(get_task_or_404(task_id))


@router.post("/{task_id}/replica-identity/using-index")
def set_task_replica_identity_using_index(task_id: int, payload: TaskReplicaIdentityUsingIndexRequest) -> dict[str, Any]:
    task = get_task_or_404(task_id)
    source, _ = task_payloads(task)
    log_id = create_log(
        task_id,
        "replica_identity.using_index",
        "running",
        f"Setting {payload.schema_name}.{payload.table_name} replica identity to {payload.index_name}",
        payload.model_dump(),
    )
    try:
        result = set_replica_identity_using_index(
            source,
            payload.schema_name,
            payload.table_name,
            payload.index_name,
        )
        finish_log(log_id, "succeeded", "Replica identity updated", result)
        return {"ok": True, **result}
    except Exception as exc:
        finish_log(log_id, "failed", str(exc), payload.model_dump())
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{task_id}")
def delete_task(task_id: int) -> dict[str, bool]:
    get_task_or_404(task_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM task_logs WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM sequence_results WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM data_check_results WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM migration_tasks WHERE id = ?", (task_id,))
    return {"ok": True}


@router.get("/{task_id}/logs")
def get_task_logs(task_id: int) -> dict[str, Any]:
    get_task_or_404(task_id)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM task_logs WHERE task_id = ? ORDER BY id DESC",
            (task_id,),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.get("/{task_id}/sequence-results")
def get_sequence_results(task_id: int) -> dict[str, Any]:
    get_task_or_404(task_id)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sequence_results WHERE task_id = ? ORDER BY id DESC",
            (task_id,),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.get("/{task_id}/data-check-results")
def get_data_check_results(task_id: int) -> dict[str, Any]:
    get_task_or_404(task_id)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM data_check_results WHERE task_id = ? ORDER BY id DESC",
            (task_id,),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["checks"] = json_loads(item.pop("checks_json"), [])
        items.append(item)
    return {"items": items}


@router.post("/{task_id}/sequences/preview")
def preview_task_sequences(task_id: int, payload: TaskSequencePreviewRequest) -> dict[str, Any]:
    task = get_task_or_404(task_id)
    schemas = payload.schemas if payload.schemas is not None else json_loads(task["schemas_json"], None)
    log_id = create_log(task_id, "sequence.preview", "running", "Previewing sequence values")
    update_task_status(task_id, TaskStatus.checking)

    try:
        source, target = task_payloads(task)
        items = build_sequence_preview(
            source,
            target,
            payload.step,
            schemas,
            payload.skip_if_target_greater,
        )
        save_sequence_results(task_id, "preview", items)
        update_task_status(task_id, TaskStatus.sequence_previewed)
        finish_log(log_id, "succeeded", "Sequence preview completed", {"count": len(items)})
        return {"items": items}
    except Exception as exc:
        update_task_status(task_id, TaskStatus.failed)
        finish_log(log_id, "failed", str(exc))
        raise


@router.post("/{task_id}/sequences/apply")
def apply_task_sequences(task_id: int, payload: TaskSequenceApplyRequest) -> dict[str, Any]:
    task = get_task_or_404(task_id)
    schemas = payload.schemas if payload.schemas is not None else json_loads(task["schemas_json"], None)
    log_id = create_log(task_id, "sequence.apply", "running", "Applying sequence values")
    update_task_status(task_id, TaskStatus.checking)

    try:
        source, target = task_payloads(task)
        preview = build_sequence_preview(
            source,
            target,
            payload.step,
            schemas,
            payload.skip_if_target_greater,
        )
        items = apply_sequence_values(target, preview)
        save_sequence_results(task_id, "apply", items)
        update_task_status(task_id, TaskStatus.sequence_applied)
        finish_log(log_id, "succeeded", "Sequence apply completed", {"count": len(items)})
        return {"items": items}
    except Exception as exc:
        update_task_status(task_id, TaskStatus.failed)
        finish_log(log_id, "failed", str(exc))
        raise


@router.post("/{task_id}/data-check/run", response_model=list[TableCheckResult])
def run_task_data_check(task_id: int, payload: TaskDataCheckRequest) -> list[TableCheckResult]:
    task = get_task_or_404(task_id)
    task_tables = json_loads(task["tables_json"], None)
    tables = payload.tables or ([TableRef(**item) for item in task_tables] if task_tables else None)
    if not tables:
        raise HTTPException(status_code=400, detail="No tables were provided for data check")

    log_id = create_log(task_id, "data_check.run", "running", "Running data check")
    update_task_status(task_id, TaskStatus.checking)

    try:
        source, target = task_payloads(task)
        items = run_table_checks(
            source,
            target,
            tables,
            payload.exact_count,
            payload.include_pk_range,
        )
        save_data_check_results(task_id, items)
        update_task_status(task_id, TaskStatus.data_checked)
        failed_count = sum(1 for item in items if item.status == CheckStatus.failed)
        finish_log(
            log_id,
            "succeeded" if failed_count == 0 else "warning",
            "Data check completed",
            {"count": len(items), "failed_count": failed_count},
        )
        return items
    except Exception as exc:
        update_task_status(task_id, TaskStatus.failed)
        finish_log(log_id, "failed", str(exc))
        raise
