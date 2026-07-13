from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .instances import get_instance_or_404
from .postgres import (
    apply_sequence_values,
    build_sequence_preview,
    count_rows,
    get_primary_key_columns,
    list_tables,
    payload_from_instance,
    primary_key_range,
    scan_sequences,
)
from .schemas import (
    CheckStatus,
    DataCheckRequest,
    SequenceApplyRequest,
    SequencePreviewRequest,
    SequenceScanRequest,
    TableCheckResult,
    TablesRequest,
)

router = APIRouter(prefix="/api", tags=["tasks"])


def instance_payload(instance_id: int):
    return payload_from_instance(get_instance_or_404(instance_id))


@router.post("/metadata/tables")
def get_tables(payload: TablesRequest) -> dict:
    pg = instance_payload(payload.instance_id)
    return {"tables": list_tables(pg, payload.schemas)}


@router.post("/sequences/scan")
def scan_sequence_values(payload: SequenceScanRequest) -> dict:
    source = instance_payload(payload.source_instance_id)
    result = {"source": scan_sequences(source, payload.schemas)}
    if payload.target_instance_id is not None:
        target = instance_payload(payload.target_instance_id)
        result["target"] = scan_sequences(target, payload.schemas)
    return result


@router.post("/sequences/preview")
def preview_sequence_values(payload: SequencePreviewRequest) -> dict:
    source = instance_payload(payload.source_instance_id)
    target = instance_payload(payload.target_instance_id)
    preview = build_sequence_preview(
        source,
        target,
        payload.step,
        payload.schemas,
        payload.skip_if_target_greater,
    )
    return {"items": preview}


@router.post("/sequences/apply")
def apply_sequences(payload: SequenceApplyRequest) -> dict:
    source = instance_payload(payload.source_instance_id)
    target = instance_payload(payload.target_instance_id)
    preview = build_sequence_preview(
        source,
        target,
        payload.step,
        payload.schemas,
        payload.skip_if_target_greater,
    )
    return {"items": apply_sequence_values(target, preview)}


@router.post("/data-check/run", response_model=list[TableCheckResult])
def run_data_check(payload: DataCheckRequest) -> list[TableCheckResult]:
    source = instance_payload(payload.source_instance_id)
    target = instance_payload(payload.target_instance_id)
    results: list[TableCheckResult] = []

    for table in payload.tables:
        checks = []
        status = CheckStatus.passed

        if payload.exact_count:
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

        if payload.include_pk_range:
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
