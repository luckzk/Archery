from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class InstanceRole(str, Enum):
    source = "source"
    target = "target"
    both = "both"


class ProxyType(str, Enum):
    http = "http"
    socks4 = "socks4"
    socks5 = "socks5"


class PostgresConnection(BaseModel):
    host: str
    port: int = Field(default=5432, ge=1, le=65535)
    database: str
    username: str
    password: str
    sslmode: str = "prefer"
    proxy_type: Optional[ProxyType] = None
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = Field(default=None, ge=1, le=65535)
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None


class InstanceCreate(PostgresConnection):
    name: str
    role: InstanceRole
    description: Optional[str] = None


class InstanceOut(BaseModel):
    id: int
    name: str
    role: InstanceRole
    host: str
    port: int
    database: str
    username: str
    sslmode: str
    proxy_type: Optional[ProxyType] = None
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    proxy_username: Optional[str] = None
    description: Optional[str] = None
    created_at: str
    updated_at: str


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str
    metadata: Optional[Dict[str, Any]] = None


class SequenceScanRequest(BaseModel):
    source_instance_id: int
    target_instance_id: Optional[int] = None
    schemas: Optional[List[str]] = None


class SequencePreviewRequest(BaseModel):
    source_instance_id: int
    target_instance_id: int
    step: int = Field(default=10000, ge=0)
    schemas: Optional[List[str]] = None
    skip_if_target_greater: bool = True


class SequenceApplyRequest(SequencePreviewRequest):
    pass


class TableRef(BaseModel):
    schema_name: str
    table_name: str


class DataCheckRequest(BaseModel):
    source_instance_id: int
    target_instance_id: int
    tables: List[TableRef]
    exact_count: bool = True
    include_pk_range: bool = True


class CheckStatus(str, Enum):
    passed = "passed"
    warning = "warning"
    failed = "failed"


class TaskStatus(str, Enum):
    draft = "draft"
    checking = "checking"
    sequence_previewed = "sequence_previewed"
    sequence_applied = "sequence_applied"
    data_checked = "data_checked"
    failed = "failed"


class TableCheckResult(BaseModel):
    schema_name: str
    table_name: str
    status: CheckStatus
    checks: List[Dict[str, Any]]


class TablesRequest(BaseModel):
    instance_id: int
    schemas: Optional[List[str]] = None


class SqlExecuteRequest(BaseModel):
    instance_id: int
    sql: str = Field(min_length=1, max_length=20000)
    readonly: bool = True
    max_rows: int = Field(default=200, ge=1, le=1000)


class SqlExecuteResponse(BaseModel):
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int
    status: str
    readonly: bool
    executed_sql: str
    truncated: bool = False


class MigrationTaskCreate(BaseModel):
    name: str
    source_instance_id: int
    target_instance_id: int
    schemas: Optional[List[str]] = None
    tables: Optional[List[TableRef]] = None
    description: Optional[str] = None


class MigrationTaskOut(BaseModel):
    id: int
    name: str
    source_instance_id: int
    target_instance_id: int
    schemas: Optional[List[str]] = None
    tables: Optional[List[TableRef]] = None
    status: TaskStatus
    description: Optional[str] = None
    created_at: str
    updated_at: str


class TaskSequencePreviewRequest(BaseModel):
    step: int = Field(default=10000, ge=0)
    schemas: Optional[List[str]] = None
    skip_if_target_greater: bool = True


class TaskSequenceApplyRequest(TaskSequencePreviewRequest):
    pass


class TaskDataCheckRequest(BaseModel):
    tables: Optional[List[TableRef]] = None
    exact_count: bool = True
    include_pk_range: bool = True


class TaskReplicaIdentityUsingIndexRequest(BaseModel):
    schema_name: str
    table_name: str
    index_name: str


ReplicaIdentityMode = Literal["DEFAULT", "NOTHING", "FULL", "USING INDEX"]
