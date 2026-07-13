from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .instances import get_instance_or_404
from .postgres import execute_sql, payload_from_instance
from .schemas import SqlExecuteRequest, SqlExecuteResponse

router = APIRouter(prefix="/api/sql", tags=["sql"])


@router.post("/execute", response_model=SqlExecuteResponse)
def execute(payload: SqlExecuteRequest) -> SqlExecuteResponse:
    instance = get_instance_or_404(payload.instance_id)
    connection_payload = payload_from_instance(instance)
    try:
        result = execute_sql(
            connection_payload,
            payload.sql,
            readonly=payload.readonly,
            max_rows=payload.max_rows,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SqlExecuteResponse(**result)
