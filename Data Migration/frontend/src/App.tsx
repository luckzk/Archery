import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EyeOutlined,
  FieldTimeOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined
} from '@ant-design/icons'
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  Layout,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useMemo, useState } from 'react'
import {
  api,
  DataCheckResult,
  InstancePayload,
  InstanceRecord,
  MigrationTask,
  SequenceResult,
  SqlExecutionResult,
  TableMetadata,
  TableRef,
  TaskLog
} from './api'

const { Content, Sider } = Layout
const { Paragraph: TextParagraph, Text, Title } = Typography

const statusColor: Record<string, string> = {
  draft: 'default',
  checking: 'processing',
  sequence_previewed: 'blue',
  sequence_applied: 'green',
  data_checked: 'cyan',
  failed: 'red',
  passed: 'green',
  warning: 'orange',
  succeeded: 'green',
  running: 'processing',
  applied: 'green',
  skipped: 'orange'
}

const identityTablePagination = {
  defaultPageSize: 20,
  pageSizeOptions: [10, 20, 50, 100, 500, 1000],
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 张表`
}

type ViewKey = 'instances' | 'tasks' | 'cutover' | 'sql'

function parseCsv(value?: string): string[] | undefined {
  const items = (value ?? '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
  return items.length ? items : undefined
}

function parseTables(value?: string): TableRef[] | undefined {
  const tables = (value ?? '')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const [schemaName, tableName] = item.split('.')
      return { schema_name: schemaName, table_name: tableName }
    })
    .filter((item) => item.schema_name && item.table_name)
  return tables.length ? tables : undefined
}

function formatTables(tables?: TableRef[]) {
  return tables?.map((table) => `${table.schema_name}.${table.table_name}`).join(', ') || '-'
}

function tableKey(table: TableRef | TableMetadata) {
  return `${table.schema_name}.${table.table_name}`
}

function tableIdentityRisk(table: TableMetadata) {
  if (table.replica_identity === 'NOTHING') {
    return { level: 'failed', label: 'NOTHING', message: 'UPDATE/DELETE 无法复制' }
  }
  if (table.replica_identity === 'DEFAULT' && (!table.primary_key_columns || table.primary_key_columns.length === 0)) {
    return { level: 'failed', label: '无主键', message: 'DEFAULT 需要主键定位行' }
  }
  if (table.replica_identity === 'FULL') {
    return { level: 'warning', label: 'FULL', message: 'WAL 体积可能增大' }
  }
  return { level: 'passed', label: '正常', message: '复制标识可用' }
}

function renderEligibleIdentityIndexes(indexes?: TableMetadata['eligible_replica_identity_indexes']) {
  if (!indexes?.length) return '-'
  return (
    <Space wrap size={[4, 4]}>
      {indexes.map((index) => (
        <Tag key={index.index_name} title={index.columns.join(', ')}>
          {index.index_name} ({index.columns.join(', ')})
        </Tag>
      ))}
    </Space>
  )
}

function App() {
  const { message } = AntApp.useApp()
  const [view, setView] = useState<ViewKey>('instances')
  const [instances, setInstances] = useState<InstanceRecord[]>([])
  const [tasks, setTasks] = useState<MigrationTask[]>([])
  const [selectedTaskId, setSelectedTaskId] = useState<number>()
  const [loading, setLoading] = useState(false)
  const [instanceModalOpen, setInstanceModalOpen] = useState(false)
  const [taskModalOpen, setTaskModalOpen] = useState(false)
  const [taskDrawerOpen, setTaskDrawerOpen] = useState(false)
  const [taskTableOptions, setTaskTableOptions] = useState<TableMetadata[]>([])
  const [taskTablesLoading, setTaskTablesLoading] = useState(false)
  const [instanceForm] = Form.useForm()
  const [taskForm] = Form.useForm()

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId),
    [selectedTaskId, tasks]
  )
  const pageTitle = view === 'instances'
    ? '实例管理'
    : view === 'tasks'
      ? '迁移准备'
      : view === 'cutover'
        ? '切换前检查'
        : 'SQL 编辑器'
  const pageSubtitle = view === 'instances'
    ? '管理源库、目标库和代理连接配置'
    : view === 'tasks'
      ? '为手动结构迁移和逻辑复制同步整理检查范围与前置风险'
      : view === 'cutover'
        ? '汇总序列、数据、Replica Identity 和操作日志风险'
        : '连接已保存实例，执行只读查询或经确认的写入语句'

  async function refreshAll() {
    setLoading(true)
    try {
      const [instanceItems, taskItems] = await Promise.all([api.listInstances(), api.listTasks()])
      setInstances(instanceItems)
      setTasks(taskItems)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '刷新失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshAll()
  }, [])

  async function createInstance(values: InstancePayload) {
    const payload = {
      ...values,
      port: Number(values.port),
      proxy_port: values.proxy_port ? Number(values.proxy_port) : undefined
    }
    try {
      await api.createInstance(payload)
      message.success('实例已保存')
      setInstanceModalOpen(false)
      instanceForm.resetFields()
      refreshAll()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败')
    }
  }

  async function testInstanceConnection() {
    try {
      const values = await instanceForm.validateFields()
      const result = await api.testConnection(values)
      if (result.ok) {
        Modal.success({
          title: '连接成功',
          content: (
            <Descriptions size="small" column={1}>
              {Object.entries(result.metadata ?? {}).map(([key, value]) => (
                <Descriptions.Item key={key} label={key}>
                  {String(value)}
                </Descriptions.Item>
              ))}
            </Descriptions>
          )
        })
      } else {
        Modal.error({ title: '连接失败', content: result.message })
      }
    } catch (error) {
      if (error instanceof Error) {
        message.error(error.message)
      }
    }
  }

  async function createTask(values: {
    name: string
    source_instance_id: number
    target_instance_id: number
    schemas?: string
    tables?: string
    table_keys?: string[]
    description?: string
  }) {
    try {
      if (values.source_instance_id === values.target_instance_id) {
        message.error('源库和目标库不能相同')
        return
      }
      const selectedTables = values.table_keys?.map((key) => {
        const [schemaName, tableName] = key.split('.')
        return { schema_name: schemaName, table_name: tableName }
      })
      const task = await api.createTask({
        name: values.name,
        source_instance_id: values.source_instance_id,
        target_instance_id: values.target_instance_id,
        schemas: parseCsv(values.schemas),
        tables: selectedTables?.length ? selectedTables : parseTables(values.tables),
        description: values.description
      })
      message.success('任务已创建')
      setTaskModalOpen(false)
      taskForm.resetFields()
      setSelectedTaskId(task.id)
      setTaskDrawerOpen(true)
      refreshAll()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建失败')
    }
  }

  async function scanTaskTables() {
    const sourceInstanceId = taskForm.getFieldValue('source_instance_id')
    const schemas = parseCsv(taskForm.getFieldValue('schemas'))
    if (!sourceInstanceId) {
      message.warning('请先选择源库')
      return
    }
    setTaskTablesLoading(true)
    try {
      const result = await api.getTables(sourceInstanceId, schemas)
      setTaskTableOptions(result.tables)
      message.success(`扫描到 ${result.tables.length} 张表`)
    } catch (error) {
      Modal.error({
        title: '扫描表失败',
        content: error instanceof Error ? error.message : '无法扫描源库表'
      })
    } finally {
      setTaskTablesLoading(false)
    }
  }

  const instanceColumns: ColumnsType<InstanceRecord> = [
    {
      title: '实例',
      dataIndex: 'name',
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.name}</Text>
          <Text type="secondary">{record.host}:{record.port}/{record.database}</Text>
        </Space>
      )
    },
    {
      title: '角色',
      dataIndex: 'role',
      width: 110,
      render: (role) => <Tag>{role}</Tag>
    },
    {
      title: '账号',
      dataIndex: 'username',
      width: 140
    },
    {
      title: '代理',
      width: 180,
      render: (_, record) =>
        record.proxy_type ? (
          <Tag color="blue">{record.proxy_type} {record.proxy_host}:{record.proxy_port}</Tag>
        ) : (
          <Text type="secondary">直连</Text>
        )
    },
    {
      title: '操作',
      width: 100,
      render: (_, record) => (
        <Popconfirm title="删除实例" description="确认删除这个实例？" onConfirm={async () => {
          await api.deleteInstance(record.id)
          message.success('实例已删除')
          refreshAll()
        }}>
          <Button icon={<DeleteOutlined />} size="small" />
        </Popconfirm>
      )
    }
  ]

  const taskColumns: ColumnsType<MigrationTask> = [
    {
      title: '任务',
      dataIndex: 'name',
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.name}</Text>
          <Text type="secondary">{formatTables(record.tables)}</Text>
        </Space>
      )
    },
    {
      title: '源库',
      dataIndex: 'source_instance_id',
      width: 160,
      render: (id) => instances.find((item) => item.id === id)?.name || id
    },
    {
      title: '目标库',
      dataIndex: 'target_instance_id',
      width: 160,
      render: (id) => instances.find((item) => item.id === id)?.name || id
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 150,
      render: (status) => <Tag color={statusColor[status]}>{status}</Tag>
    },
    {
      title: '操作',
      width: 170,
      render: (_, record) => (
        <Space>
          <Button
            icon={<EyeOutlined />}
            size="small"
            onClick={() => {
              setSelectedTaskId(record.id)
              setTaskDrawerOpen(true)
            }}
          >
            查看
          </Button>
          <Popconfirm title="删除任务" description="会同时清理日志和结果，确认删除？" onConfirm={async () => {
            await api.deleteTask(record.id)
            if (selectedTaskId === record.id) {
              setTaskDrawerOpen(false)
              setSelectedTaskId(undefined)
            }
            message.success('任务已删除')
            refreshAll()
          }}>
            <Button icon={<DeleteOutlined />} size="small" />
          </Popconfirm>
        </Space>
      )
    }
  ]

  return (
    <Layout className="app-shell">
      <Sider className="app-sider" width={248}>
        <div className="brand">
          <DatabaseOutlined className="brand-icon" />
          <div>
            <div className="brand-title">PG 手动迁移助手</div>
            <div className="brand-subtitle">Precheck & Sequence</div>
          </div>
        </div>
        <button className={view === 'instances' ? 'nav-item active' : 'nav-item'} onClick={() => setView('instances')}>
          <CloudServerOutlined /> 实例管理
        </button>
        <button className={view === 'tasks' ? 'nav-item active' : 'nav-item'} onClick={() => setView('tasks')}>
          <FieldTimeOutlined /> 迁移准备
        </button>
        <button className={view === 'cutover' ? 'nav-item active' : 'nav-item'} onClick={() => setView('cutover')}>
          <SafetyCertificateOutlined /> 切换前检查
        </button>
        <button className={view === 'sql' ? 'nav-item active' : 'nav-item'} onClick={() => setView('sql')}>
          <CodeOutlined /> SQL 编辑器
        </button>
      </Sider>
      <Layout>
        <Content className="app-content">
          <div className="page-header">
            <div>
              <Title level={2}>{pageTitle}</Title>
              <Text type="secondary">{pageSubtitle}</Text>
            </div>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={refreshAll} loading={loading}>刷新</Button>
              {view === 'instances' ? (
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setInstanceModalOpen(true)}>新增实例</Button>
              ) : view === 'tasks' ? (
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setTaskModalOpen(true)}>创建准备任务</Button>
              ) : null}
            </Space>
          </div>

          <Row gutter={16} className="stats-row">
            <Col span={8}><Card><Statistic title="实例" value={instances.length} prefix={<CloudServerOutlined />} /></Card></Col>
            <Col span={8}><Card><Statistic title="准备任务" value={tasks.length} prefix={<FieldTimeOutlined />} /></Card></Col>
            <Col span={8}><Card><Statistic title="异常任务" value={tasks.filter((task) => task.status === 'failed').length} prefix={<CheckCircleOutlined />} /></Card></Col>
          </Row>

          {view === 'instances' ? (
            <Table rowKey="id" columns={instanceColumns} dataSource={instances} loading={loading} pagination={{ pageSize: 8 }} />
          ) : view === 'tasks' ? (
            <Table rowKey="id" columns={taskColumns} dataSource={tasks} loading={loading} pagination={{ pageSize: 8 }} />
          ) : view === 'cutover' ? (
            <CutoverCheckPage tasks={tasks} instances={instances} />
          ) : (
            <SqlEditorPage instances={instances} />
          )}
        </Content>
      </Layout>

      <Modal
        title="新增 PostgreSQL 实例"
        open={instanceModalOpen}
        width={760}
        onCancel={() => setInstanceModalOpen(false)}
        footer={[
          <Button key="test" icon={<ApiOutlined />} onClick={testInstanceConnection}>测试连接</Button>,
          <Button key="cancel" onClick={() => setInstanceModalOpen(false)}>取消</Button>,
          <Button key="submit" type="primary" onClick={() => instanceForm.submit()}>保存</Button>
        ]}
      >
        <Form form={instanceForm} layout="vertical" onFinish={createInstance} initialValues={{ port: 5432, sslmode: 'prefer', role: 'source' }}>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="name" label="实例名称" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="role" label="角色" rules={[{ required: true }]}><Select options={[{ value: 'source', label: 'source' }, { value: 'target', label: 'target' }, { value: 'both', label: 'both' }]} /></Form.Item></Col>
            <Col span={12}><Form.Item name="host" label="Host" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="port" label="Port" rules={[{ required: true }]}><InputNumber min={1} max={65535} className="full" /></Form.Item></Col>
            <Col span={6}><Form.Item name="sslmode" label="SSL Mode"><Select options={['disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full'].map((value) => ({ value, label: value }))} /></Form.Item></Col>
            <Col span={12}><Form.Item name="database" label="Database" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="username" label="Username" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="password" label="Password" rules={[{ required: true }]}><Input.Password /></Form.Item></Col>
            <Col span={12}><Form.Item name="description" label="备注"><Input /></Form.Item></Col>
          </Row>
          <Divider orientation="left">代理连接</Divider>
          <Row gutter={16}>
            <Col span={8}><Form.Item name="proxy_type" label="代理类型"><Select allowClear options={[{ value: 'http', label: 'HTTP CONNECT' }, { value: 'socks4', label: 'SOCKS4' }, { value: 'socks5', label: 'SOCKS5' }]} /></Form.Item></Col>
            <Col span={10}><Form.Item name="proxy_host" label="代理 Host"><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="proxy_port" label="代理端口"><InputNumber min={1} max={65535} className="full" /></Form.Item></Col>
            <Col span={12}><Form.Item name="proxy_username" label="代理用户名"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="proxy_password" label="代理密码"><Input.Password /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title="创建迁移准备任务"
        open={taskModalOpen}
        width={720}
        onCancel={() => setTaskModalOpen(false)}
        onOk={() => taskForm.submit()}
      >
        <Form
          form={taskForm}
          layout="vertical"
          onFinish={createTask}
          onValuesChange={(changed) => {
            if ('source_instance_id' in changed || 'schemas' in changed) {
              setTaskTableOptions([])
              taskForm.setFieldValue('table_keys', undefined)
            }
          }}
        >
          <Form.Item name="name" label="准备任务名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="source_instance_id" label="源库" rules={[{ required: true }]}>
                <Select options={instances.map((item) => ({ value: item.id, label: item.name }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="target_instance_id" label="目标库" rules={[{ required: true }]}>
                <Select options={instances.map((item) => ({ value: item.id, label: item.name }))} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="schemas" label="Schema 范围"><Input placeholder="public, audit" /></Form.Item>
          <Space className="task-scan-row">
            <Button icon={<ReloadOutlined />} loading={taskTablesLoading} onClick={scanTaskTables}>扫描源库表</Button>
            <Text type="secondary">可先扫描选择检查表；无法连接时也可以手动填写。</Text>
          </Space>
          <Form.Item name="table_keys" label="选择数据检查表">
            <Select
              mode="multiple"
              showSearch
              placeholder="从源库扫描后选择"
              options={taskTableOptions.map((table) => ({
                value: `${table.schema_name}.${table.table_name}`,
                label: `${table.schema_name}.${table.table_name}`
              }))}
            />
          </Form.Item>
          <Form.Item name="tables" label="手动填写数据检查表"><Input.TextArea rows={4} placeholder={'public.users\npublic.orders'} /></Form.Item>
          <Form.Item name="description" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      <TaskDrawer
        open={taskDrawerOpen}
        task={selectedTask}
        instances={instances}
        onClose={() => setTaskDrawerOpen(false)}
        onRefresh={refreshAll}
      />
    </Layout>
  )
}

function TaskDrawer({ open, task, instances, onClose, onRefresh }: {
  open: boolean
  task?: MigrationTask
  instances: InstanceRecord[]
  onClose: () => void
  onRefresh: () => void
}) {
  const { message } = AntApp.useApp()
  const [logs, setLogs] = useState<TaskLog[]>([])
  const [checks, setChecks] = useState<DataCheckResult[]>([])
  const [tables, setTables] = useState<TableMetadata[]>([])
  const [checkTableKeys, setCheckTableKeys] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [identityBusyKey, setIdentityBusyKey] = useState<string>()
  const instanceName = (id: number) => instances.find((item) => item.id === id)?.name || `#${id}`
  const checkFailures = checks.filter((item) => item.status === 'failed').length
  const checkWarnings = checks.filter((item) => item.status === 'warning').length
  const replicaIdentityRisks = tables.filter((table) => (
    table.replica_identity === 'NOTHING' ||
    (table.replica_identity === 'DEFAULT' && (!table.primary_key_columns || table.primary_key_columns.length === 0))
  ))
  const readinessStatus = checkFailures || replicaIdentityRisks.length
    ? 'failed'
    : checkWarnings
      ? 'warning'
      : 'passed'

  async function refreshTaskData() {
    if (!task) return
    const [logData, checkData] = await Promise.all([
      api.getTaskLogs(task.id),
      api.getDataCheckResults(task.id)
    ])
    setLogs(logData.items)
    setChecks(checkData.items)
  }

  async function refreshTables() {
    if (!task) return
    const data = await api.getTables(task.source_instance_id, task.schemas)
    setTables(data.tables)
  }

  useEffect(() => {
    if (open && task) {
      refreshTaskData().catch((error) => message.error(error instanceof Error ? error.message : '加载任务失败'))
      refreshTables()
        .catch(() => setTables([]))
    }
  }, [open, task?.id])

  function confirmSetReplicaIdentity(table: TableMetadata, indexName: string) {
    if (!task) return
    Modal.confirm({
      title: '设置 Replica Identity',
      content: `确认将 ${table.schema_name}.${table.table_name} 设置为 USING INDEX ${indexName}？`,
      okText: '设置',
      cancelText: '取消',
      onOk: async () => {
        const busyKey = `${tableKey(table)}.${indexName}`
        setIdentityBusyKey(busyKey)
        try {
          await api.setTaskReplicaIdentityUsingIndex(task.id, {
            schema_name: table.schema_name,
            table_name: table.table_name,
            index_name: indexName
          })
          message.success('Replica Identity 已设置')
          await Promise.all([refreshTables(), refreshTaskData()])
          onRefresh()
        } catch (error) {
          message.error(error instanceof Error ? error.message : '设置失败')
        } finally {
          setIdentityBusyKey(undefined)
        }
      }
    })
  }

  async function runAction(action: 'check') {
    if (!task) return
    setBusy(true)
    try {
      if (action === 'check') {
        const selectedTables = checkTableKeys.map((key) => {
          const [schemaName, tableName] = key.split('.')
          return { schema_name: schemaName, table_name: tableName }
        })
        const result = await api.runTaskDataCheck(task.id, {
          tables: selectedTables.length ? selectedTables : undefined,
          exact_count: true,
          include_pk_range: true
        })
        setChecks(result)
        message.success('数据检查完成')
      }
      await refreshTaskData()
      onRefresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败')
      await refreshTaskData().catch(() => undefined)
    } finally {
      setBusy(false)
    }
  }

  const checkColumns: ColumnsType<DataCheckResult> = [
    { title: '表', render: (_, record) => `${record.schema_name}.${record.table_name}` },
    { title: '状态', dataIndex: 'status', render: (status) => <Tag color={statusColor[status]}>{status}</Tag> },
    { title: '检查项', render: (_, record) => record.checks.length }
  ]

  const logColumns: ColumnsType<TaskLog> = [
    { title: '操作', dataIndex: 'operation' },
    { title: '状态', dataIndex: 'status', render: (status) => <Tag color={statusColor[status]}>{status}</Tag> },
    { title: '消息', dataIndex: 'message' },
    { title: '开始时间', dataIndex: 'started_at' }
  ]

  const tableOptions = tables.map((table) => ({
    value: tableKey(table),
    label: tableKey(table)
  }))

  return (
    <Drawer title="准备详情" open={open} width="min(1180px, 96vw)" onClose={onClose}>
      {!task ? (
        <Alert type="info" message="请选择准备任务" />
      ) : (
        <Space direction="vertical" size={16} className="full">
          <Descriptions bordered size="small" column={3}>
            <Descriptions.Item label="准备任务">{task.name}</Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={statusColor[task.status]}>{task.status}</Tag></Descriptions.Item>
            <Descriptions.Item label="Schema">{task.schemas?.join(', ') || '-'}</Descriptions.Item>
            <Descriptions.Item label="源库">{instanceName(task.source_instance_id)}</Descriptions.Item>
            <Descriptions.Item label="目标库">{instanceName(task.target_instance_id)}</Descriptions.Item>
            <Descriptions.Item label="表">{formatTables(task.tables)}</Descriptions.Item>
          </Descriptions>

          <Alert
            type="info"
            showIcon
            message="当前阶段用于辅助手动迁移"
            description="这里主要做逻辑复制前检查：确认表的 Replica Identity、主键和检查表范围是否适合后续同步。数据同步完成后的序列预览与设置放在切换前检查页执行。"
          />

          <Card size="small" title="逻辑复制准备度">
            <Row gutter={16}>
              <Col span={8}>
                <Statistic
                  title="整体状态"
                  value={readinessStatus}
                  valueStyle={{ color: readinessStatus === 'passed' ? '#16a34a' : readinessStatus === 'warning' ? '#d97706' : '#dc2626' }}
                />
              </Col>
              <Col span={8}><Statistic title="检查失败" value={checkFailures} /></Col>
              <Col span={8}><Statistic title="Identity 风险" value={replicaIdentityRisks.length} /></Col>
            </Row>
            {replicaIdentityRisks.length > 0 ? (
              <Alert
                className="readiness-alert"
                type="warning"
                showIcon
                message="存在 Replica Identity 风险"
                description={replicaIdentityRisks.slice(0, 5).map((table) => `${table.schema_name}.${table.table_name} (${table.replica_identity})`).join(', ')}
              />
            ) : null}
          </Card>

          <Tabs
            items={[
              {
                key: 'checks',
                label: '数据检查',
                children: (
                  <Space direction="vertical" className="full" size={12}>
                    <Row gutter={12}>
                      <Col flex="auto">
                        <Select
                          mode="multiple"
                          allowClear
                          className="full"
                          placeholder="默认使用任务保存的表，也可以临时选择本次检查表"
                          value={checkTableKeys}
                          onChange={setCheckTableKeys}
                          options={tableOptions}
                        />
                      </Col>
                      <Col>
                        <Button type="primary" icon={<CheckCircleOutlined />} loading={busy} onClick={() => runAction('check')}>执行检查</Button>
                      </Col>
                    </Row>
                    <Text type="secondary">不选择时使用任务创建时保存的表；选择后仅检查本次选择的表。</Text>
                    <Table
                      rowKey={(record) => `${record.schema_name}.${record.table_name}`}
                      columns={checkColumns}
                      dataSource={checks}
                      size="small"
                      pagination={{ pageSize: 6 }}
                      expandable={{
                        expandedRowRender: (record) => (
                          <TextParagraph className="json-block">
                            <pre>{JSON.stringify(record.checks, null, 2)}</pre>
                          </TextParagraph>
                        )
                      }}
                    />
                  </Space>
                )
              },
              {
                key: 'metadata',
                label: '表元数据',
                children: (
                  <Table
                    rowKey={(record) => `${record.schema_name}.${record.table_name}`}
                    size="small"
                    dataSource={tables}
                    pagination={identityTablePagination}
                    columns={[
                      { title: '表', render: (_, record) => `${record.schema_name}.${record.table_name}` },
                      { title: '估算行数', dataIndex: 'estimated_rows' },
                      { title: 'Replica Identity', dataIndex: 'replica_identity', render: (value) => <Tag>{value}</Tag> },
                      { title: 'Identity Index', dataIndex: 'replica_identity_index', render: (value) => value || '-' },
                      { title: '主键索引', dataIndex: 'primary_key_index', render: (value) => value || '-' },
                      { title: '可用 Identity 索引', dataIndex: 'eligible_replica_identity_indexes', render: renderEligibleIdentityIndexes },
                      { title: '主键', dataIndex: 'primary_key_columns', render: (value?: string[]) => value?.join(', ') || '-' },
                      {
                        title: '设置 Identity',
                        width: 220,
                        render: (_, record) => (
                          <Select<string>
                            size="small"
                            className="identity-index-select"
                            placeholder="选择 USING INDEX"
                            disabled={!record.eligible_replica_identity_indexes?.length || Boolean(identityBusyKey)}
                            loading={Boolean(identityBusyKey?.startsWith(tableKey(record)))}
                            onSelect={(indexName) => confirmSetReplicaIdentity(record, indexName)}
                            options={(record.eligible_replica_identity_indexes ?? []).map((index) => ({
                              value: index.index_name,
                              label: `${index.index_name} (${index.columns.join(', ')})`
                            }))}
                          />
                        )
                      },
                      {
                        title: '风险',
                        render: (_, record) => {
                          const risk = tableIdentityRisk(record)
                          return <Tag color={statusColor[risk.level]}>{risk.label}</Tag>
                        }
                      },
                      {
                        title: '说明',
                        render: (_, record) => tableIdentityRisk(record).message
                      }
                    ]}
                  />
                )
              },
              {
                key: 'logs',
                label: '日志',
                children: <Table rowKey="id" columns={logColumns} dataSource={logs} size="small" pagination={{ pageSize: 8 }} />
              }
            ]}
          />
        </Space>
      )}
    </Drawer>
  )
}

function SqlEditorPage({ instances }: {
  instances: InstanceRecord[]
}) {
  const { message } = AntApp.useApp()
  const [instanceId, setInstanceId] = useState<number>()
  const [sqlText, setSqlText] = useState('SELECT current_database(), current_user, now();')
  const [readonly, setReadonly] = useState(true)
  const [maxRows, setMaxRows] = useState(200)
  const [result, setResult] = useState<SqlExecutionResult>()
  const [executing, setExecuting] = useState(false)

  const resultColumns: ColumnsType<Record<string, unknown>> = (result?.columns ?? []).map((column) => ({
    title: column,
    dataIndex: column,
    ellipsis: true,
    render: (value) => value === null || value === undefined ? <Text type="secondary">NULL</Text> : String(value)
  }))

  async function executeSql() {
    if (!instanceId) {
      message.warning('请先选择实例')
      return
    }
    if (!sqlText.trim()) {
      message.warning('请输入 SQL')
      return
    }
    setExecuting(true)
    try {
      const data = await api.executeSql({
        instance_id: instanceId,
        sql: sqlText,
        readonly,
        max_rows: maxRows
      })
      setResult(data)
      message.success(data.columns.length ? `查询返回 ${data.row_count} 行` : data.status)
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'SQL 执行失败')
    } finally {
      setExecuting(false)
    }
  }

  return (
    <Space direction="vertical" size={16} className="full">
      <Card>
        <Row gutter={12} align="middle">
          <Col xs={24} lg={10}>
            <Select
              className="full"
              placeholder="选择要连接的 PostgreSQL 实例"
              value={instanceId}
              onChange={setInstanceId}
              options={instances.map((item) => ({
                value: item.id,
                label: `${item.name} (${item.host}:${item.port}/${item.database})`
              }))}
            />
          </Col>
          <Col xs={12} lg={5}>
            <Space>
              <Switch checked={readonly} onChange={setReadonly} />
              <Text>只读模式</Text>
            </Space>
          </Col>
          <Col xs={12} lg={4}>
            <Space direction="vertical" size={0} className="full">
              <Text type="secondary">最大行数</Text>
              <InputNumber min={1} max={1000} value={maxRows} onChange={(value) => setMaxRows(Number(value ?? 200))} className="full" />
            </Space>
          </Col>
          <Col xs={24} lg={5}>
            <Button type="primary" icon={<PlayCircleOutlined />} loading={executing} onClick={executeSql} className="full">
              执行 SQL
            </Button>
          </Col>
        </Row>
      </Card>

      <Card title="编辑器">
        <Input.TextArea
          className="sql-editor"
          value={sqlText}
          onChange={(event) => setSqlText(event.target.value)}
          autoSize={{ minRows: 10, maxRows: 18 }}
          spellCheck={false}
        />
      </Card>

      {readonly ? (
        <Alert
          type="info"
          showIcon
          message="只读模式会启用 READ ONLY，限制为单条查询类语句，并对查询结果在数据库侧应用最大行数。"
        />
      ) : (
        <Alert
          type="warning"
          showIcon
          message="写入模式会提交成功执行的语句，请确认目标实例和 SQL 内容。"
        />
      )}

      <Card
        title="执行结果"
        extra={result ? (
          <Space>
            <Tag>{result.status}</Tag>
            {result.truncated ? <Tag color="orange">已截断</Tag> : null}
          </Space>
        ) : null}
      >
        {result ? (
          result.columns.length ? (
            <Space direction="vertical" className="full" size={12}>
              <TextParagraph className="json-block">
                <pre>{result.executed_sql}</pre>
              </TextParagraph>
              <Table
                rowKey={(_, index) => String(index)}
                columns={resultColumns}
                dataSource={result.rows}
                size="small"
                scroll={{ x: true }}
                pagination={{ pageSize: 20, showSizeChanger: true }}
              />
            </Space>
          ) : (
            <Space direction="vertical" className="full" size={12}>
              <Descriptions size="small" bordered column={3}>
                <Descriptions.Item label="状态">{result.status}</Descriptions.Item>
                <Descriptions.Item label="影响行数">{result.row_count}</Descriptions.Item>
                <Descriptions.Item label="模式">{result.readonly ? '只读' : '写入'}</Descriptions.Item>
              </Descriptions>
              <TextParagraph className="json-block">
                <pre>{result.executed_sql}</pre>
              </TextParagraph>
            </Space>
          )
        ) : (
          <Alert type="info" message="执行 SQL 后将在这里显示结果" />
        )}
      </Card>
    </Space>
  )
}

function CutoverCheckPage({ tasks, instances }: {
  tasks: MigrationTask[]
  instances: InstanceRecord[]
}) {
  const { message } = AntApp.useApp()
  const [taskId, setTaskId] = useState<number>()
  const [loading, setLoading] = useState(false)
  const [logs, setLogs] = useState<TaskLog[]>([])
  const [sequences, setSequences] = useState<SequenceResult[]>([])
  const [checks, setChecks] = useState<DataCheckResult[]>([])
  const [tables, setTables] = useState<TableMetadata[]>([])
  const [step, setStep] = useState(10000)
  const [skipGreater, setSkipGreater] = useState(true)
  const [sequenceBusy, setSequenceBusy] = useState(false)
  const [identityBusyKey, setIdentityBusyKey] = useState<string>()

  const task = tasks.find((item) => item.id === taskId)
  const instanceName = (id?: number) => instances.find((item) => item.id === id)?.name || (id ? `#${id}` : '-')
  const sequenceFailures = sequences.filter((item) => item.status === 'failed' || item.error).length
  const sequenceSkipped = sequences.filter((item) => item.status === 'skipped').length
  const sequencePending = sequences.filter((item) => item.should_apply === true || item.should_apply === 1).length
  const checkFailures = checks.filter((item) => item.status === 'failed').length
  const checkWarnings = checks.filter((item) => item.status === 'warning').length
  const identityRisks = tables
    .map((table) => ({ table, risk: tableIdentityRisk(table) }))
    .filter((item) => item.risk.level !== 'passed')
  const failedLogs = logs.filter((item) => item.status === 'failed')
  const hasSequenceResults = sequences.length > 0
  const hasCheckResults = checks.length > 0
  const hasMetadata = tables.length > 0

  const blockers = [
    ...(!task ? [{ type: '准备任务', level: 'failed', message: '请选择一个迁移准备任务' }] : []),
    ...(task && !hasSequenceResults ? [{ type: '序列', level: 'warning', message: '还没有执行序列预览或设置' }] : []),
    ...(task && !hasCheckResults ? [{ type: '数据检查', level: 'warning', message: '还没有执行数据检查' }] : []),
    ...(task && !hasMetadata ? [{ type: '表元数据', level: 'warning', message: '还没有加载表元数据' }] : []),
    ...sequences
      .filter((item) => item.status === 'failed' || item.error)
      .map((item) => ({
        type: '序列',
        level: 'failed',
        message: `${item.sequence_schema}.${item.sequence_name}: ${item.error || item.reason || '设置失败'}`
      })),
    ...checks
      .filter((item) => item.status !== 'passed')
      .map((item) => ({
        type: '数据检查',
        level: item.status,
        message: `${item.schema_name}.${item.table_name}: ${item.status}`
      })),
    ...identityRisks.map(({ table, risk }) => ({
      type: 'Replica Identity',
      level: risk.level,
      message: `${table.schema_name}.${table.table_name}: ${risk.message}`
    })),
    ...failedLogs.map((item) => ({
      type: '任务日志',
      level: 'failed',
      message: `${item.operation}: ${item.message || '操作失败'}`
    }))
  ]

  const failedCount = blockers.filter((item) => item.level === 'failed').length
  const warningCount = blockers.filter((item) => item.level === 'warning').length
  const readiness = !task || failedCount > 0
    ? 'failed'
    : warningCount > 0
      ? 'warning'
      : 'passed'

  async function loadCutoverCheck(nextTaskId = taskId) {
    if (!nextTaskId) {
      message.warning('请先选择任务')
      return
    }
    const selected = tasks.find((item) => item.id === nextTaskId)
    if (!selected) return

    setLoading(true)
    try {
      const [logData, sequenceData, checkData, tableData] = await Promise.all([
        api.getTaskLogs(nextTaskId),
        api.getSequenceResults(nextTaskId),
        api.getDataCheckResults(nextTaskId),
        api.getTables(selected.source_instance_id, selected.schemas)
      ])
      setLogs(logData.items)
      setSequences(sequenceData.items)
      setChecks(checkData.items)
      setTables(tableData.tables)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载切换前检查失败')
    } finally {
      setLoading(false)
    }
  }

  async function runSequenceAction(action: 'preview' | 'apply') {
    if (!task) {
      message.warning('请先选择准备任务')
      return
    }
    setSequenceBusy(true)
    try {
      const result = action === 'preview'
        ? await api.previewTaskSequences(task.id, { step, skip_if_target_greater: skipGreater })
        : await api.applyTaskSequences(task.id, { step, skip_if_target_greater: skipGreater })
      setSequences(result.items)
      const [logData] = await Promise.all([
        api.getTaskLogs(task.id),
        loadCutoverCheck(task.id)
      ])
      setLogs(logData.items)
      message.success(action === 'preview' ? '序列预览完成' : '目标库序列设置完成')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '序列操作失败')
      await loadCutoverCheck(task.id).catch(() => undefined)
    } finally {
      setSequenceBusy(false)
    }
  }

  function confirmSetReplicaIdentity(table: TableMetadata, indexName: string) {
    if (!task) return
    Modal.confirm({
      title: '设置 Replica Identity',
      content: `确认将 ${table.schema_name}.${table.table_name} 设置为 USING INDEX ${indexName}？`,
      okText: '设置',
      cancelText: '取消',
      onOk: async () => {
        const busyKey = `${tableKey(table)}.${indexName}`
        setIdentityBusyKey(busyKey)
        try {
          await api.setTaskReplicaIdentityUsingIndex(task.id, {
            schema_name: table.schema_name,
            table_name: table.table_name,
            index_name: indexName
          })
          message.success('Replica Identity 已设置')
          await loadCutoverCheck(task.id)
        } catch (error) {
          message.error(error instanceof Error ? error.message : '设置失败')
        } finally {
          setIdentityBusyKey(undefined)
        }
      }
    })
  }

  const blockerColumns: ColumnsType<{ type: string; level: string; message: string }> = [
    { title: '类型', dataIndex: 'type', width: 160 },
    { title: '级别', dataIndex: 'level', width: 120, render: (level) => <Tag color={statusColor[level]}>{level}</Tag> },
    { title: '问题', dataIndex: 'message' }
  ]

  const tableColumns: ColumnsType<TableMetadata> = [
    { title: '表', render: (_, record) => tableKey(record) },
    { title: '估算行数', dataIndex: 'estimated_rows', width: 120 },
    { title: 'Replica Identity', dataIndex: 'replica_identity', width: 150, render: (value) => <Tag>{value}</Tag> },
    { title: 'Identity Index', dataIndex: 'replica_identity_index', width: 180, render: (value) => value || '-' },
    { title: '主键索引', dataIndex: 'primary_key_index', width: 180, render: (value) => value || '-' },
    { title: '可用 Identity 索引', dataIndex: 'eligible_replica_identity_indexes', width: 260, render: renderEligibleIdentityIndexes },
    { title: '主键', dataIndex: 'primary_key_columns', render: (value?: string[]) => value?.join(', ') || '-' },
    {
      title: '设置 Identity',
      width: 220,
      render: (_, record) => (
        <Select<string>
          size="small"
          className="identity-index-select"
          placeholder="选择 USING INDEX"
          disabled={!record.eligible_replica_identity_indexes?.length || Boolean(identityBusyKey)}
          loading={Boolean(identityBusyKey?.startsWith(tableKey(record)))}
          onSelect={(indexName) => confirmSetReplicaIdentity(record, indexName)}
          options={(record.eligible_replica_identity_indexes ?? []).map((index) => ({
            value: index.index_name,
            label: `${index.index_name} (${index.columns.join(', ')})`
          }))}
        />
      )
    },
    {
      title: '风险',
      width: 120,
      render: (_, record) => {
        const risk = tableIdentityRisk(record)
        return <Tag color={statusColor[risk.level]}>{risk.label}</Tag>
      }
    },
    { title: '说明', render: (_, record) => tableIdentityRisk(record).message }
  ]

  return (
    <Space direction="vertical" size={16} className="full">
      <Card>
        <Row gutter={12} align="middle">
          <Col flex="auto">
            <Select
              className="full"
              placeholder="选择迁移准备任务"
              value={taskId}
              onChange={(value) => {
                setTaskId(value)
                loadCutoverCheck(value)
              }}
              options={tasks.map((item) => ({
                value: item.id,
                label: `${item.name} (${instanceName(item.source_instance_id)} -> ${instanceName(item.target_instance_id)})`
              }))}
            />
          </Col>
          <Col>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => loadCutoverCheck()}>刷新检查</Button>
          </Col>
        </Row>
      </Card>

      {task ? (
        <Descriptions bordered size="small" column={4}>
          <Descriptions.Item label="准备任务">{task.name}</Descriptions.Item>
          <Descriptions.Item label="状态"><Tag color={statusColor[task.status]}>{task.status}</Tag></Descriptions.Item>
          <Descriptions.Item label="源库">{instanceName(task.source_instance_id)}</Descriptions.Item>
          <Descriptions.Item label="目标库">{instanceName(task.target_instance_id)}</Descriptions.Item>
          <Descriptions.Item label="Schema">{task.schemas?.join(', ') || '-'}</Descriptions.Item>
          <Descriptions.Item label="表" span={3}>{formatTables(task.tables)}</Descriptions.Item>
        </Descriptions>
      ) : (
        <Alert type="info" showIcon message="请选择一个迁移准备任务开始切换前检查" />
      )}

      <Card title="当前手动迁移流程">
        <div className="flow-grid">
          <div className="flow-step">
            <Text strong>1. 结构迁移</Text>
            <Text type="secondary">手动完成 schema、表、索引、约束等结构迁移。</Text>
          </div>
          <div className="flow-step">
            <Text strong>2. 逻辑复制前检查</Text>
            <Text type="secondary">先处理表与 Identity 风险，再创建发布和订阅。</Text>
          </div>
          <div className="flow-step">
            <Text strong>3. 数据同步</Text>
            <Text type="secondary">手动配置逻辑复制，等待业务数据追平。</Text>
          </div>
          <div className="flow-step">
            <Text strong>4. 切换前检查</Text>
            <Text type="secondary">聚合数据检查、序列预设值和操作日志风险。</Text>
          </div>
          <div className="flow-step">
            <Text strong>5. 序列处理</Text>
            <Text type="secondary">同步完成后预览并设置目标库序列。</Text>
          </div>
        </div>
      </Card>

      <Card title="检查结论">
        <Row gutter={16}>
          <Col span={6}>
            <Statistic
              title="切换建议"
              value={readiness === 'passed' ? '可切换' : readiness === 'warning' ? '需确认' : '不可切换'}
              valueStyle={{ color: readiness === 'passed' ? '#16a34a' : readiness === 'warning' ? '#d97706' : '#dc2626' }}
            />
          </Col>
          <Col span={6}><Statistic title="阻断项" value={failedCount} /></Col>
          <Col span={6}><Statistic title="警告项" value={warningCount} /></Col>
          <Col span={6}><Statistic title="已检查表" value={checks.length} /></Col>
        </Row>
        <Row gutter={16} className="cutover-metrics">
          <Col span={6}><Statistic title="序列待设置" value={sequencePending} /></Col>
          <Col span={6}><Statistic title="序列跳过" value={sequenceSkipped} /></Col>
          <Col span={6}><Statistic title="数据检查失败" value={checkFailures} /></Col>
          <Col span={6}><Statistic title="Identity 风险" value={identityRisks.length} /></Col>
        </Row>
      </Card>

      <Tabs
        items={[
          {
            key: 'blockers',
            label: '必处理事项',
            children: (
              <Table
                rowKey={(_, index) => String(index)}
                columns={blockerColumns}
                dataSource={blockers}
                loading={loading}
                pagination={{ pageSize: 8 }}
              />
            )
          },
          {
            key: 'tables',
            label: '表与 Identity',
            children: (
              <Table
                rowKey={(record) => tableKey(record)}
                columns={tableColumns}
                dataSource={tables}
                loading={loading}
                pagination={identityTablePagination}
              />
            )
          },
          {
            key: 'data',
            label: '数据检查',
            children: (
              <Table
                rowKey={(record) => tableKey(record)}
                loading={loading}
                dataSource={checks}
                pagination={{ pageSize: 8 }}
                columns={[
                  { title: '表', render: (_, record) => tableKey(record) },
                  { title: '状态', dataIndex: 'status', render: (status) => <Tag color={statusColor[status]}>{status}</Tag> },
                  { title: '检查项', render: (_, record) => record.checks.length }
                ]}
                expandable={{
                  expandedRowRender: (record) => (
                    <TextParagraph className="json-block">
                      <pre>{JSON.stringify(record.checks, null, 2)}</pre>
                    </TextParagraph>
                  )
                }}
              />
            )
          },
          {
            key: 'sequences',
            label: '序列',
            children: (
              <Space direction="vertical" className="full" size={12}>
                <Card size="small" title="序列设置">
                  <Row gutter={12} align="middle">
                    <Col xs={24} md={6}>
                      <Text type="secondary">步进值</Text>
                      <InputNumber min={0} value={step} onChange={(value) => setStep(Number(value ?? 0))} className="full" />
                    </Col>
                    <Col xs={24} md={8}>
                      <Text type="secondary">目标库当前值更大时</Text>
                      <Space className="full sequence-switch-row">
                        <Switch checked={skipGreater} onChange={setSkipGreater} />
                        <Text>跳过设置</Text>
                      </Space>
                    </Col>
                    <Col xs={24} md={10}>
                      <Space wrap>
                        <Button icon={<EyeOutlined />} loading={sequenceBusy} disabled={!task} onClick={() => runSequenceAction('preview')}>预览预设值</Button>
                        <Button type="primary" icon={<PlayCircleOutlined />} loading={sequenceBusy} disabled={!task} onClick={() => runSequenceAction('apply')}>一键设置目标库序列</Button>
                      </Space>
                    </Col>
                  </Row>
                </Card>
                <Table
                  rowKey={(record) => `${record.operation || 'result'}-${record.sequence_schema}.${record.sequence_name}`}
                  loading={loading || sequenceBusy}
                  dataSource={sequences}
                  pagination={{ pageSize: 8 }}
                  columns={[
                    { title: '序列', render: (_, record) => `${record.sequence_schema}.${record.sequence_name}` },
                    { title: '绑定字段', render: (_, record) => record.table_name ? `${record.table_schema}.${record.table_name}.${record.column_name}` : '-' },
                    { title: '源端当前值', render: (_, record) => record.source_last_value ?? record.last_value ?? '-' },
                    { title: '目标端当前值', dataIndex: 'target_current_value', render: (value) => value ?? '-' },
                    { title: '预设目标值', dataIndex: 'target_value', render: (value) => value ?? '-' },
                    { title: '状态', render: (_, record) => <Tag color={statusColor[record.status || record.reason || '']}>{record.status || record.reason || '-'}</Tag> },
                    { title: '错误', dataIndex: 'error', render: (value) => value || '-' }
                  ]}
                  expandable={{
                    expandedRowRender: (record) => (
                      <Space direction="vertical" className="full">
                        {record.setval_sql ? <Text code>{record.setval_sql}</Text> : null}
                        {record.error ? <Alert type="error" message={record.error} /> : null}
                      </Space>
                    ),
                    rowExpandable: (record) => Boolean(record.setval_sql || record.error)
                  }}
                />
              </Space>
            )
          },
          {
            key: 'logs',
            label: '日志',
            children: (
              <Table
                rowKey="id"
                loading={loading}
                dataSource={logs}
                pagination={{ pageSize: 8 }}
                columns={[
                  { title: '操作', dataIndex: 'operation' },
                  { title: '状态', dataIndex: 'status', render: (status) => <Tag color={statusColor[status]}>{status}</Tag> },
                  { title: '消息', dataIndex: 'message' },
                  { title: '开始时间', dataIndex: 'started_at' },
                  { title: '结束时间', dataIndex: 'finished_at', render: (value) => value || '-' }
                ]}
              />
            )
          }
        ]}
      />
    </Space>
  )
}

export default function RootApp() {
  return (
    <AntApp>
      <App />
    </AntApp>
  )
}
