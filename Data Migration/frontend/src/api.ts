export type InstanceRole = 'source' | 'target' | 'both'
export type ProxyType = 'http' | 'socks4' | 'socks5'
export type TaskStatus =
  | 'draft'
  | 'checking'
  | 'sequence_previewed'
  | 'sequence_applied'
  | 'data_checked'
  | 'failed'

export interface InstancePayload {
  name: string
  role: InstanceRole
  host: string
  port: number
  database: string
  username: string
  password: string
  sslmode: string
  proxy_type?: ProxyType
  proxy_host?: string
  proxy_port?: number
  proxy_username?: string
  proxy_password?: string
  description?: string
}

export interface InstanceRecord extends Omit<InstancePayload, 'password' | 'proxy_password'> {
  id: number
  created_at: string
  updated_at: string
}

export interface TableRef {
  schema_name: string
  table_name: string
}

export interface MigrationTask {
  id: number
  name: string
  source_instance_id: number
  target_instance_id: number
  schemas?: string[]
  tables?: TableRef[]
  status: TaskStatus
  description?: string
  created_at: string
  updated_at: string
}

export interface TaskLog {
  id: number
  task_id: number
  operation: string
  status: string
  message?: string
  details_json?: string
  started_at: string
  finished_at?: string
}

export interface SequenceResult {
  id?: number
  task_id?: number
  operation?: string
  sequence_schema: string
  sequence_name: string
  table_schema?: string
  table_name?: string
  column_name?: string
  last_value?: number
  source_last_value?: number
  target_current_value?: number
  target_value?: number
  should_apply?: boolean | number
  reason?: string
  setval_sql?: string
  status?: string
  error?: string
  created_at?: string
}

export interface DataCheckResult {
  id?: number
  task_id?: number
  schema_name: string
  table_name: string
  status: 'passed' | 'warning' | 'failed'
  checks: Array<Record<string, unknown>>
  created_at?: string
}

export interface TableMetadata {
  schema_name: string
  table_name: string
  estimated_rows: number
  replica_identity: string
  replica_identity_index?: string
  primary_key_index?: string
  primary_key_columns?: string[]
  eligible_replica_identity_indexes?: Array<{
    index_name: string
    columns: string[]
  }>
}

export interface SqlExecutionResult {
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  status: string
  readonly: boolean
  executed_sql: string
  truncated: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {})
    }
  })

  if (!response.ok) {
    const text = await response.text()
    let errorMessage = text
    try {
      const payload = JSON.parse(text)
      errorMessage = payload.detail || payload.message || text
    } catch {
      errorMessage = text
    }
    throw new Error(errorMessage || `Request failed: ${response.status}`)
  }

  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ ok: boolean }>('/health'),
  listInstances: () => request<InstanceRecord[]>('/api/instances'),
  createInstance: (payload: InstancePayload) =>
    request<InstanceRecord>('/api/instances', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  deleteInstance: (id: number) =>
    request<{ ok: boolean }>(`/api/instances/${id}`, { method: 'DELETE' }),
  testConnection: (payload: InstancePayload) =>
    request<{ ok: boolean; message: string; metadata?: Record<string, unknown> }>('/api/instances/test', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  listTasks: () => request<MigrationTask[]>('/api/tasks'),
  deleteTask: (id: number) =>
    request<{ ok: boolean }>(`/api/tasks/${id}`, { method: 'DELETE' }),
  createTask: (payload: {
    name: string
    source_instance_id: number
    target_instance_id: number
    schemas?: string[]
    tables?: TableRef[]
    description?: string
  }) =>
    request<MigrationTask>('/api/tasks', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  getTaskLogs: (taskId: number) => request<{ items: TaskLog[] }>(`/api/tasks/${taskId}/logs`),
  previewTaskSequences: (taskId: number, payload: { step: number; schemas?: string[]; skip_if_target_greater: boolean }) =>
    request<{ items: SequenceResult[] }>(`/api/tasks/${taskId}/sequences/preview`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  applyTaskSequences: (taskId: number, payload: { step: number; schemas?: string[]; skip_if_target_greater: boolean }) =>
    request<{ items: SequenceResult[] }>(`/api/tasks/${taskId}/sequences/apply`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  getSequenceResults: (taskId: number) => request<{ items: SequenceResult[] }>(`/api/tasks/${taskId}/sequence-results`),
  runTaskDataCheck: (taskId: number, payload: { tables?: TableRef[]; exact_count: boolean; include_pk_range: boolean }) =>
    request<DataCheckResult[]>(`/api/tasks/${taskId}/data-check/run`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  getDataCheckResults: (taskId: number) =>
    request<{ items: DataCheckResult[] }>(`/api/tasks/${taskId}/data-check-results`),
  setTaskReplicaIdentityUsingIndex: (taskId: number, payload: { schema_name: string; table_name: string; index_name: string }) =>
    request<{ ok: boolean; schema_name: string; table_name: string; index_name: string; sql: string }>(
      `/api/tasks/${taskId}/replica-identity/using-index`,
      {
        method: 'POST',
        body: JSON.stringify(payload)
      }
    ),
  getTables: (instanceId: number, schemas?: string[]) =>
    request<{ tables: TableMetadata[] }>('/api/metadata/tables', {
      method: 'POST',
      body: JSON.stringify({ instance_id: instanceId, schemas })
    }),
  executeSql: (payload: { instance_id: number; sql: string; readonly: boolean; max_rows: number }) =>
    request<SqlExecutionResult>('/api/sql/execute', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
}
