from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .db import get_connection, row_to_dict
from .postgres import test_postgres_connection
from .schemas import ConnectionTestResult, InstanceCreate, InstanceOut, PostgresConnection

router = APIRouter(prefix="/api/instances", tags=["instances"])


def redact_instance(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "role": row["role"],
        "host": row["host"],
        "port": row["port"],
        "database": row["database_name"],
        "username": row["username"],
        "sslmode": row["sslmode"],
        "proxy_type": row["proxy_type"],
        "proxy_host": row["proxy_host"],
        "proxy_port": row["proxy_port"],
        "proxy_username": row["proxy_username"],
        "description": row["description"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_instance_or_404(instance_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM postgres_instances WHERE id = ?",
            (instance_id,),
        ).fetchone()
    data = row_to_dict(row)
    if data is None:
        raise HTTPException(status_code=404, detail="PostgreSQL instance not found")
    return data


@router.post("/test", response_model=ConnectionTestResult)
def test_connection(payload: PostgresConnection) -> ConnectionTestResult:
    return test_postgres_connection(payload)


@router.post("", response_model=InstanceOut)
def create_instance(payload: InstanceCreate) -> InstanceOut:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO postgres_instances (
                name, role, host, port, database_name, username, password, sslmode,
                proxy_type, proxy_host, proxy_port, proxy_username, proxy_password, description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.role.value,
                payload.host,
                payload.port,
                payload.database,
                payload.username,
                payload.password,
                payload.sslmode,
                payload.proxy_type.value if payload.proxy_type else None,
                payload.proxy_host,
                payload.proxy_port,
                payload.proxy_username,
                payload.proxy_password,
                payload.description,
            ),
        )
        row = conn.execute(
            "SELECT * FROM postgres_instances WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return InstanceOut(**redact_instance(dict(row)))


@router.get("", response_model=list[InstanceOut])
def list_instances() -> list[InstanceOut]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM postgres_instances ORDER BY id DESC",
        ).fetchall()
    return [InstanceOut(**redact_instance(dict(row))) for row in rows]


@router.get("/{instance_id}", response_model=InstanceOut)
def get_instance(instance_id: int) -> InstanceOut:
    return InstanceOut(**redact_instance(get_instance_or_404(instance_id)))


@router.delete("/{instance_id}")
def delete_instance(instance_id: int) -> dict[str, bool]:
    get_instance_or_404(instance_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM postgres_instances WHERE id = ?", (instance_id,))
    return {"ok": True}
