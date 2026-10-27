import React, { useState, useEffect } from 'react'
import {
  Card, Table, Button, Modal, Form, Input, Tag, Space, message, Switch,
  Popconfirm, Upload, Drawer, Typography, Tooltip, Empty, Spin, Tabs, Alert,
  AutoComplete, Collapse, InputNumber, Radio, Divider,
} from 'antd'
import {
  PlusOutlined, ApiOutlined, SyncOutlined, DeleteOutlined, EditOutlined,
  UploadOutlined, DatabaseOutlined, TableOutlined, ColumnWidthOutlined,
  ReloadOutlined, SearchOutlined, EyeOutlined, KeyOutlined, LeftOutlined,
  CloudUploadOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { datasourceApi } from '../services/api'
import type { DatasourceType, DatasourcePayload } from '../services/api'

const { Text, Title } = Typography

const FALLBACK_ACCENT = '#6366f1'

// 品牌图片沿用 SQLBot 的本地资源，随前端构建分发，不依赖外部图床。
const DATABASE_LOGOS = new Set([
  'mysql', 'postgresql', 'clickhouse', 'sqlserver', 'oracle',
  'doris', 'starrocks', 'redshift', 'kingbase', 'dm',
])

const DatabaseLogo: React.FC<{ dbType: string; label?: string; size?: number }> = ({ dbType, label, size = 32 }) => {
  const type = dbType === 'dameng' ? 'dm' : dbType
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [type])
  return (
    <span style={{
      width: size, height: size, flexShrink: 0, display: 'inline-flex',
      alignItems: 'center', justifyContent: 'center', padding: 4, boxSizing: 'border-box',
      borderRadius: 8, background: '#f8fafc', overflow: 'hidden', verticalAlign: 'middle',
    }}>
      {DATABASE_LOGOS.has(type) && !failed ? (
        <img src={`${import.meta.env.BASE_URL}database-logos/${type}.png`}
          alt={`${label || type} Logo`} onError={() => setFailed(true)}
          style={{ width: '100%', height: '100%', objectFit: 'contain', transform: type === 'kingbase' ? 'scale(1.45)' : undefined }} />
      ) : <DatabaseOutlined style={{ color: FALLBACK_ACCENT, fontSize: size * 0.6 }} />}
    </span>
  )
}

/** 类型清单尚未加载完成时的兜底描述，避免编辑弹窗字段缺失 */
const fallbackType = (dbType: string): DatasourceType => ({
  db_type: dbType,
  label: dbType === 'dm' ? '达梦' : (dbType || '').toUpperCase(),
  default_port: dbType === 'dm' ? 5236 : 0,
  driver: dbType === 'dm' ? 'dmPython' : '',
  default_schema: '',
  supports_schema: true,
  supports_database: dbType !== 'dm',
  supports_ssl: dbType !== 'dm',
  supports_connect_mode: false,
  supports_low_version: false,
  driver_package: '',
  accent: FALLBACK_ACCENT,
})

const fmtTime = (v?: string) => (v ? dayjs(v).format('MM-DD HH:mm') : '-')

const statusTag = (s: string) => (
  <Tag color={s === 'active' ? 'success' : s === 'error' ? 'error' : 'default'} style={{ borderRadius: 6 }}>
    {s === 'active' ? '正常' : s === 'error' ? '异常' : '未连接'}
  </Tag>
)

interface ProbeResult {
  success: boolean
  message: string
  version?: string
  latency_ms?: number
  server?: string
}

/** 左侧表清单 + 右侧字段详情，用于「线上表结构」与「已同步元数据」两种浏览模式 */
const SchemaBrowser: React.FC<{
  tables: { table_name: string; table_comment?: string }[]
  loading: boolean
  search: string
  onSearch: (v: string) => void
  selected: string | null
  onSelect: (name: string) => void
  columns: any[]
  columnsLoading: boolean
  emptyHint: string
  selectedActions?: React.ReactNode
  onRefresh?: () => void
}> = ({ tables, loading, search, onSearch, selected, onSelect, columns, columnsLoading, emptyHint, selectedActions, onRefresh }) => {
  const filtered = tables.filter(t => !search || t.table_name.toLowerCase().includes(search.toLowerCase()))

  const columnTableColumns = [
    {
      title: '字段名', dataIndex: 'column_name', key: 'column_name',
      render: (name: string, record: any) => (
        <Space size={6}>
          {!!record.is_primary_key && <KeyOutlined style={{ color: '#f59e0b', fontSize: 12 }} />}
          <Text style={{ color: 'var(--text-primary)', fontFamily: 'monospace', fontSize: 13 }}>{name}</Text>
        </Space>
      ),
    },
    {
      title: '类型', dataIndex: 'column_type', key: 'column_type',
      render: (t: string) => <Tag style={{ borderRadius: 4, fontFamily: 'monospace', fontSize: 11 }}>{t}</Tag>,
    },
    {
      title: '注释', dataIndex: 'column_comment', key: 'column_comment',
      render: (c: string) => <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{c || '-'}</Text>,
    },
    {
      title: '可空', dataIndex: 'is_nullable', key: 'is_nullable', width: 64,
      render: (v: any) => <Tag color={v ? 'default' : 'warning'} style={{ fontSize: 11 }}>{v ? 'Y' : 'N'}</Tag>,
    },
    {
      title: '主键', dataIndex: 'is_primary_key', key: 'is_primary_key', width: 64,
      render: (v: any) => <Tag color={v ? 'gold' : 'default'} style={{ fontSize: 11 }}>{v ? 'PK' : '-'}</Tag>,
    },
  ]

  return (
    <div style={{ display: 'flex', gap: 16, height: '100%' }}>
      <div style={{ width: 250, flexShrink: 0, borderRight: '1px solid var(--border-glass)', paddingRight: 16, display: 'flex', flexDirection: 'column' }}>
        <Space.Compact style={{ width: '100%', marginBottom: 10 }}>
          <Input
            placeholder="搜索表名..."
            prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
            value={search}
            onChange={e => onSearch(e.target.value)}
            allowClear
          />
          {onRefresh && <Button icon={<ReloadOutlined />} onClick={onRefresh} />}
        </Space.Compact>
        <div style={{ flex: 1, overflow: 'auto' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
          ) : filtered.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32 }}>
              <Empty description="暂无表" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              <Text style={{ color: 'var(--text-muted)', fontSize: 12, display: 'block', marginTop: 8 }}>{emptyHint}</Text>
            </div>
          ) : (
            <>
              <Text style={{ color: 'var(--text-muted)', fontSize: 11, marginBottom: 8, display: 'block' }}>
                共 {filtered.length} 张表
              </Text>
              {filtered.map(t => (
                <div
                  key={t.table_name}
                  onClick={() => onSelect(t.table_name)}
                  style={{
                    padding: '8px 10px', cursor: 'pointer', borderRadius: 8, marginBottom: 2,
                    background: selected === t.table_name ? 'rgba(99,102,241,0.15)' : 'transparent',
                    border: selected === t.table_name ? '1px solid rgba(99,102,241,0.3)' : '1px solid transparent',
                    transition: 'all 0.15s',
                  }}
                >
                  <Space size={6}>
                    <TableOutlined style={{ color: 'var(--primary-light)', fontSize: 13 }} />
                    <Text style={{ color: 'var(--text-primary)', fontSize: 13, fontFamily: 'monospace' }}>{t.table_name}</Text>
                  </Space>
                  {t.table_comment && (
                    <div style={{ paddingLeft: 20, marginTop: 2 }}>
                      <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>{t.table_comment}</Text>
                    </div>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        {selected ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, gap: 8 }}>
              <Title level={5} style={{ color: 'var(--text-primary)', margin: 0 }}>
                <TableOutlined style={{ marginRight: 8, color: 'var(--primary-light)' }} />
                {selected}
              </Title>
              <Space size={6}>{selectedActions}</Space>
            </div>
            {columnsLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : columns.length === 0 ? (
              <Empty description="暂无字段信息" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Table
                dataSource={columns}
                columns={columnTableColumns}
                rowKey={(r: any) => r.id || r.column_name}
                size="small"
                pagination={false}
                scroll={{ y: 'calc(100vh - 300px)' }}
              />
            )}
          </>
        ) : (
          <div style={{ textAlign: 'center', paddingTop: 100 }}>
            <ColumnWidthOutlined style={{ fontSize: 48, color: 'var(--text-muted)', marginBottom: 16 }} />
            <div><Text style={{ color: 'var(--text-muted)' }}>选择左侧表查看字段详情</Text></div>
          </div>
        )}
      </div>
    </div>
  )
}

const DataSource: React.FC = () => {
  // ===== 列表 =====
  const [datasources, setDatasources] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [types, setTypes] = useState<DatasourceType[]>([])
  const [typesLoading, setTypesLoading] = useState(false)

  // ===== 新建/编辑弹窗 =====
  const [modalOpen, setModalOpen] = useState(false)
  const [step, setStep] = useState<'type' | 'form'>('type')
  const [selectedType, setSelectedType] = useState<DatasourceType | null>(null)
  const [editing, setEditing] = useState<any>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()
  const [schemaOptions, setSchemaOptions] = useState<string[]>([])
  const [schemaLoading, setSchemaLoading] = useState(false)
  const [probeLoading, setProbeLoading] = useState(false)
  const [probeResult, setProbeResult] = useState<ProbeResult | null>(null)

  // ===== 表结构抽屉 =====
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerDs, setDrawerDs] = useState<any>(null)

  const [liveTables, setLiveTables] = useState<any[]>([])
  const [liveTablesLoading, setLiveTablesLoading] = useState(false)
  const [liveSearch, setLiveSearch] = useState('')
  const [liveSelected, setLiveSelected] = useState<string | null>(null)
  const [liveColumns, setLiveColumns] = useState<any[]>([])
  const [liveColumnsLoading, setLiveColumnsLoading] = useState(false)

  const [metaTables, setMetaTables] = useState<any[]>([])
  const [metaTablesLoading, setMetaTablesLoading] = useState(false)
  const [metaSearch, setMetaSearch] = useState('')
  const [metaSelected, setMetaSelected] = useState<string | null>(null)
  const [metaColumns, setMetaColumns] = useState<any[]>([])
  const [metaColumnsLoading, setMetaColumnsLoading] = useState(false)

  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewTable, setPreviewTable] = useState('')
  const [previewData, setPreviewData] = useState<{ columns: any[]; data: any[]; row_count?: number }>({ columns: [], data: [] })

  useEffect(() => {
    loadData()
    loadTypes()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const res: any = await datasourceApi.list()
      if (res.code === 0) setDatasources(res.data || [])
    } catch (e) { /* handled by interceptor */ }
    setLoading(false)
  }

  const loadTypes = async () => {
    setTypesLoading(true)
    try {
      const res: any = await datasourceApi.types()
      if (res.code === 0) setTypes(res.data || [])
    } catch (e) { /* handled by interceptor */ }
    setTypesLoading(false)
  }

  const typeOf = (dbType?: string): DatasourceType | undefined =>
    types.find(t => t.db_type === dbType)

  const accentOf = (dbType: string) => typeOf(dbType)?.accent || FALLBACK_ACCENT
  const labelOf = (dbType: string) => typeOf(dbType)?.label || dbType?.toUpperCase() || '-'

  // ===== 弹窗逻辑 =====

  const resetModal = () => {
    setEditing(null)
    setSelectedType(null)
    setStep('type')
    setProbeResult(null)
    setSchemaOptions([])
    form.resetFields()
  }

  const openCreate = () => {
    resetModal()
    form.setFieldsValue({ timeout: 30, pool_size: 5, pool_timeout: 30, connect_mode: 'service_name', ssl: false, low_version: false })
    setModalOpen(true)
  }

  const openEdit = (record: any) => {
    resetModal()
    setEditing(record)
    setSelectedType(typeOf(record.db_type) || fallbackType(record.db_type))
    setStep('form')
    setSchemaOptions(record.db_schema ? [record.db_schema] : [])
    form.setFieldsValue({
      name: record.name,
      description: record.description,
      host: record.host,
      port: record.port,
      username: record.username,
      password: '',
      database_name: record.database_name,
      db_schema: record.db_schema,
      connect_mode: record.connect_mode || 'service_name',
      ssl: !!record.ssl,
      extra_jdbc: record.extra_jdbc,
      low_version: !!record.low_version,
      timeout: record.timeout ?? 30,
      pool_size: record.pool_size ?? 5,
      pool_timeout: record.pool_timeout ?? 30,
    })
    setModalOpen(true)
  }

  const selectType = (t: DatasourceType) => {
    setSelectedType(t)
    setStep('form')
    setProbeResult(null)
    setSchemaOptions(t.default_schema ? [t.default_schema] : [])
    form.setFieldsValue({
      port: t.default_port,
      db_schema: t.default_schema || undefined,
      connect_mode: 'service_name',
    })
  }

  const buildPayload = (): DatasourcePayload | null => {
    if (!selectedType) return null
    const values = form.getFieldsValue()
    const payload: DatasourcePayload = {
      name: values.name || '',
      db_type: selectedType.db_type,
      host: values.host,
      port: Number(values.port) || selectedType.default_port,
      database_name: selectedType.supports_database ? values.database_name || '' : '',
      username: values.username || '',
      // 传 null 而非 undefined，保证编辑时清空字段能落库
      description: values.description || null,
      timeout: values.timeout ?? 30,
      pool_size: values.pool_size ?? 5,
      pool_timeout: values.pool_timeout ?? 30,
      extra_jdbc: values.extra_jdbc || null,
    }
    if (editing) payload.ds_id = editing.id
    if (values.password) payload.password = values.password
    if (selectedType.supports_schema) payload.db_schema = values.db_schema || null
    if (selectedType.supports_connect_mode) payload.connect_mode = values.connect_mode || 'service_name'
    if (selectedType.supports_ssl) payload.ssl = !!values.ssl
    if (selectedType.supports_low_version) payload.low_version = !!values.low_version
    return payload
  }

  const handleSave = async () => {
    const payload = buildPayload()
    if (!payload) return
    setSaving(true)
    try {
      if (editing) {
        const { ds_id, ...rest } = payload
        await datasourceApi.update(editing.id, rest)
        message.success('更新成功')
      } else {
        const { ds_id, ...rest } = payload
        await datasourceApi.create(rest as DatasourcePayload)
        message.success('创建成功')
      }
      setModalOpen(false)
      resetModal()
      loadData()
    } catch (e) { /* handled by interceptor */ }
    setSaving(false)
  }

  const handleProbe = async () => {
    const payload = buildPayload()
    if (!payload) return
    try {
      await form.validateFields(selectedType?.db_type === 'dm' ? ['host', 'port', 'username'] : ['host', 'port'])
    } catch {
      return
    }
    setProbeLoading(true)
    setProbeResult(null)
    try {
      const res: any = await datasourceApi.probe(payload)
      if (res.code === 0 && res.data) {
        setProbeResult({ success: true, ...res.data })
        message.success(res.message || '连接成功')
      } else {
        setProbeResult({ success: false, message: res.message || '连接失败' })
      }
    } catch (e: any) {
      setProbeResult({ success: false, message: e?.response?.data?.detail?.message || e?.message || '连接失败' })
    }
    setProbeLoading(false)
  }

  const handleFetchSchemas = async () => {
    const payload = buildPayload()
    if (!payload) return
    try {
      await form.validateFields(selectedType?.db_type === 'dm' ? ['host', 'port', 'username'] : ['host', 'port'])
    } catch {
      return
    }
    setSchemaLoading(true)
    try {
      const res: any = await datasourceApi.probeSchemas(payload)
      if (res.code === 0) {
        const list: string[] = res.data || []
        setSchemaOptions(list)
        message.success(list.length ? `获取到 ${list.length} 个 Schema` : '未获取到 Schema')
      } else {
        message.error(res.message || '获取 Schema 失败')
      }
    } catch (e) { /* handled by interceptor */ }
    setSchemaLoading(false)
  }

  // ===== 列表操作 =====

  const handleTest = async (id: string) => {
    try {
      const res: any = await datasourceApi.testConnection(id)
      if (res.code === 0) {
        const info = res.data || {}
        message.success(`${info.message || '连接成功'}${info.version ? ` · ${info.version}` : ''}`)
        loadData()
      } else {
        message.error(res.message || '连接失败')
        loadData()
      }
    } catch (e) { /* handled by interceptor */ }
  }

  const handleDelete = async (id: string) => {
    try {
      await datasourceApi.delete(id)
      message.success('删除成功')
      loadData()
    } catch (e) { /* handled by interceptor */ }
  }

  const handleSyncAll = async (dsId: string) => {
    try {
      const res: any = await datasourceApi.syncSchema(dsId)
      if (res.code === 0) {
        message.success(res.message || '同步完成')
        await loadData()
        if (drawerDs?.id === dsId) {
          loadMetaTables(dsId)
          loadLiveTables(dsId)
        }
      }
    } catch (e) { /* handled by interceptor */ }
  }

  const handleSyncTable = async (tableName: string) => {
    if (!drawerDs) return
    try {
      const res: any = await datasourceApi.syncSchema(drawerDs.id, [tableName])
      if (res.code === 0) {
        message.success(`表 ${tableName} 同步完成`)
        loadMetaTables(drawerDs.id)
        loadData()
      }
    } catch (e) { /* handled by interceptor */ }
  }

  // ===== 抽屉逻辑 =====

  const openDrawer = (ds: any) => {
    setDrawerDs(ds)
    setDrawerOpen(true)
    setLiveTables([]); setLiveSelected(null); setLiveColumns([]); setLiveSearch('')
    setMetaTables([]); setMetaSelected(null); setMetaColumns([]); setMetaSearch('')
    loadLiveTables(ds.id)
    loadMetaTables(ds.id)
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
    setDrawerDs(null)
  }

  const loadLiveTables = async (dsId: string) => {
    setLiveTablesLoading(true)
    try {
      const res: any = await datasourceApi.liveTables(dsId)
      if (res.code === 0) setLiveTables(res.data || [])
    } catch (e) { /* handled by interceptor */ }
    setLiveTablesLoading(false)
  }

  const loadLiveColumns = async (dsId: string, tableName: string) => {
    setLiveSelected(tableName)
    setLiveColumns([])
    setLiveColumnsLoading(true)
    try {
      const res: any = await datasourceApi.liveColumns(dsId, tableName)
      if (res.code === 0) setLiveColumns(res.data || [])
    } catch (e) { /* handled by interceptor */ }
    setLiveColumnsLoading(false)
  }

  const loadMetaTables = async (dsId: string) => {
    setMetaTablesLoading(true)
    try {
      const res: any = await datasourceApi.tables(dsId)
      if (res.code === 0) setMetaTables(res.data || [])
    } catch (e) { /* handled by interceptor */ }
    setMetaTablesLoading(false)
  }

  const loadMetaColumns = async (dsId: string, tableName: string) => {
    setMetaSelected(tableName)
    setMetaColumns([])
    setMetaColumnsLoading(true)
    try {
      const res: any = await datasourceApi.columns(dsId, tableName)
      if (res.code === 0) setMetaColumns(res.data || [])
    } catch (e) { /* handled by interceptor */ }
    setMetaColumnsLoading(false)
  }

  const openPreview = async (tableName: string) => {
    if (!drawerDs) return
    setPreviewTable(tableName)
    setPreviewOpen(true)
    setPreviewData({ columns: [], data: [] })
    setPreviewLoading(true)
    try {
      const res: any = await datasourceApi.preview(drawerDs.id, tableName, 50)
      if (res.code === 0) setPreviewData(res.data || { columns: [], data: [] })
    } catch (e) { /* handled by interceptor */ }
    setPreviewLoading(false)
  }

  const handleUploadSchema = async (dsId: string, file: File) => {
    try {
      const res: any = await datasourceApi.uploadSchema(dsId, file)
      if (res.code === 0) {
        message.success(res.message || `成功导入 ${res.data?.imported_tables} 张表`)
        loadMetaTables(dsId)
      }
    } catch (e) { /* handled by interceptor */ }
    return false
  }

  // ===== 渲染 =====

  const tableColumns = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (name: string, record: any) => (
        <div>
          <Space size={6}>
            <DatabaseLogo dbType={record.db_type} label={labelOf(record.db_type)} size={28} />
            <Text style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{name}</Text>
          </Space>
          {record.description && (
            <div style={{ paddingLeft: 34 }}>
              <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>{record.description}</Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: '类型', dataIndex: 'db_type', key: 'db_type', width: 130,
      render: (t: string) => (
        <Tag color={accentOf(t)} style={{ borderRadius: 6, color: '#fff', border: 'none' }}>{labelOf(t)}</Tag>
      ),
    },
    {
      title: '连接地址', key: 'address', width: 220,
      render: (_: any, record: any) => (
        <div>
          <Text style={{ color: 'var(--text-secondary)', fontFamily: 'monospace', fontSize: 12 }}>
            {record.host}:{record.port}
          </Text>
          <div>
            <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>
              {record.database_name || '-'}
              {record.db_schema ? ` / ${record.db_schema}` : ''}
            </Text>
          </div>
        </div>
      ),
    },
    {
      title: '表数量', dataIndex: 'table_count', key: 'table_count', width: 90,
      render: (c: number) => <Text style={{ color: 'var(--text-secondary)' }}>{c ?? 0}</Text>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string) => statusTag(s),
    },
    {
      title: '最近同步', dataIndex: 'last_sync_at', key: 'last_sync_at', width: 120,
      render: (v: string) => <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{fmtTime(v)}</Text>,
    },
    {
      title: '操作', key: 'action', width: 300, fixed: 'right' as const,
      render: (_: any, record: any) => (
        <Space size={4}>
          <Tooltip title="测试连接"><Button size="small" icon={<ApiOutlined />} onClick={() => handleTest(record.id)} /></Tooltip>
          <Tooltip title="浏览表结构"><Button size="small" icon={<TableOutlined />} onClick={() => openDrawer(record)} /></Tooltip>
          <Tooltip title="编辑"><Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} /></Tooltip>
          <Tooltip title="同步表结构"><Button size="small" icon={<SyncOutlined />} onClick={() => handleSyncAll(record.id)} /></Tooltip>
          <Popconfirm title="确认删除?" description="将同时清理已同步的元数据与向量索引" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const isDm = selectedType?.db_type === 'dm'
  const supportsSchema = !!selectedType?.supports_schema
  const supportsDatabase = !!selectedType?.supports_database
  const supportsSsl = !!selectedType?.supports_ssl
  const supportsConnectMode = !!selectedType?.supports_connect_mode
  const supportsLowVersion = !!selectedType?.supports_low_version
  const dbNameLabel = selectedType?.db_type === 'oracle' ? '服务名 / SID' : '数据库名'

  const previewColumns = (previewData.columns || []).map((c: any) => ({
    title: (
      <Space size={4}>
        <span>{c.name}</span>
        <Text style={{ color: 'var(--text-muted)', fontSize: 10 }}>{c.type}</Text>
      </Space>
    ),
    dataIndex: c.name,
    key: c.name,
    ellipsis: true,
    render: (v: any) => (v === null || v === undefined
      ? <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>NULL</Text>
      : <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{String(v)}</span>),
  }))

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card
        title={<Space><DatabaseOutlined /><span>数据源管理</span></Space>}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
            <Button className="glow-btn" icon={<PlusOutlined />} onClick={openCreate}>新增数据源</Button>
          </Space>
        }
      >
        <Table
          dataSource={datasources}
          columns={tableColumns}
          loading={loading}
          rowKey="id"
          pagination={false}
          scroll={{ x: 1150 }}
        />
      </Card>

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editing ? `编辑数据源 - ${editing.name}` : step === 'type' ? '选择数据源类型' : '新增数据源'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); resetModal() }}
        onOk={() => (step === 'type' ? null : form.submit())}
        okText={editing ? '保存' : '创建'}
        okButtonProps={{ loading: saving, disabled: step === 'type' }}
        footer={step === 'type'
          ? <Button onClick={() => { setModalOpen(false); resetModal() }}>取消</Button>
          : undefined}
        width={step === 'type' ? 620 : 720}
        forceRender
        destroyOnClose={false}
      >
        <div style={{ display: step === 'type' ? 'block' : 'none', marginTop: 12 }}>
          {typesLoading ? (
            <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
          ) : types.length === 0 ? (
            <Empty description="未获取到支持的数据源类型">
              <Button onClick={loadTypes}>重新获取</Button>
            </Empty>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
              {types.map(t => (
                <div
                  key={t.db_type}
                  onClick={() => selectType(t)}
                  style={{
                    cursor: 'pointer', borderRadius: 10, padding: '14px 12px',
                    background: 'rgba(255,255,255,0.02)',
                    border: '1px solid var(--border-glass)',
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLDivElement).style.borderColor = t.accent
                    ;(e.currentTarget as HTMLDivElement).style.background = `${t.accent}14`
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-glass)'
                    ;(e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.02)'
                  }}
                >
                  <Space size={10}>
                    <DatabaseLogo dbType={t.db_type} label={t.label} size={40} />
                    <Text style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{t.label}</Text>
                  </Space>
                  <div style={{ marginTop: 6 }}>
                    <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>默认端口 {t.default_port}</Text>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ display: step === 'form' ? 'block' : 'none' }}>
          <Form form={form} onFinish={handleSave} layout="vertical" style={{ marginTop: 12 }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '8px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.03)',
              marginBottom: 16, border: '1px solid var(--border-glass)',
            }}>
              <Space size={8}>
                <DatabaseLogo dbType={selectedType?.db_type || ''} label={selectedType?.label} />
                <Text style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{selectedType?.label}</Text>
                <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{selectedType?.driver}</Text>
                {selectedType?.driver_package && (
                  <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>驱动: {selectedType.driver_package}</Text>
                )}
              </Space>
              {!editing && (
                <Button type="link" size="small" icon={<LeftOutlined />} onClick={() => { setStep('type'); setProbeResult(null) }}>
                  更换类型
                </Button>
              )}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Form.Item name="name" label="数据源名称" rules={[{ required: true, message: '请输入数据源名称' }]}>
                <Input placeholder="例如：生产库-MySQL" />
              </Form.Item>
              <Form.Item name="description" label="描述">
                <Input placeholder="用途说明(可选)" />
              </Form.Item>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
              <Form.Item name="host" label="主机地址" rules={[{ required: true, message: '请输入主机地址' }]}>
                <Input placeholder="192.168.1.100" />
              </Form.Item>
              <Form.Item name="port" label="端口" rules={[{ required: true, message: '请输入端口' }]}>
                <InputNumber style={{ width: '100%' }} min={1} max={65535} placeholder={String(selectedType?.default_port || 3306)} />
              </Form.Item>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Form.Item name="username" label="用户名" rules={isDm ? [{ required: true, whitespace: true, message: '请输入达梦数据库账号' }] : []}>
                <Input placeholder="数据库账号" autoComplete="off" />
              </Form.Item>
              <Form.Item name="password" label="密码" extra={editing ? '留空表示不修改已保存的密码' : undefined}>
                <Input.Password placeholder={editing ? '••••••••' : '数据库密码'} autoComplete="new-password" />
              </Form.Item>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: supportsDatabase && supportsSchema ? '1fr 1fr' : '1fr', gap: 12 }}>
              {supportsDatabase && (
                <Form.Item name="database_name" label={dbNameLabel}>
                  <Input placeholder={selectedType?.db_type === 'oracle' ? 'ORCL' : 'my_database'} />
                </Form.Item>
              )}
              {supportsSchema && (
                <Form.Item label={`Schema / ${selectedType?.db_type === 'oracle' ? '用户' : '模式'}`} required={isDm} style={{ marginBottom: 24 }}
                  extra={isDm ? '达梦按模式读取表结构。可点击「获取」选择，也可输入准确模式名；请保留原始大小写。' : undefined}>
                  <Space.Compact style={{ width: '100%' }}>
                    <Form.Item name="db_schema" noStyle rules={isDm ? [{ required: true, whitespace: true, message: '请输入或选择达梦 Schema / 模式' }] : []}>
                      <AutoComplete
                        style={{ width: '100%' }}
                        options={schemaOptions.map(s => ({ value: s }))}
                        placeholder={isDm ? '选择或输入模式名，例如 SYSDBA' : selectedType?.default_schema || 'public'}
                        filterOption={(input, option) => String(option?.value || '').toLowerCase().includes(input.toLowerCase())}
                      />
                    </Form.Item>
                    <Button onClick={handleFetchSchemas} loading={schemaLoading}>获取</Button>
                  </Space.Compact>
                </Form.Item>
              )}
            </div>

            {(supportsSsl || supportsConnectMode || supportsLowVersion) && (
              <div style={{ display: 'flex', gap: 32, alignItems: 'center', marginBottom: 8 }}>
                {supportsSsl && (
                  <Form.Item name="ssl" label="SSL 加密" valuePropName="checked" style={{ marginBottom: 8 }}>
                    <Switch checkedChildren="开" unCheckedChildren="关" />
                  </Form.Item>
                )}
                {supportsLowVersion && (
                  <Form.Item name="low_version" label="低版本兼容" valuePropName="checked" style={{ marginBottom: 8 }}
                    tooltip="SQL Server 2008 及更早版本使用 TDS 7.0 协议">
                    <Switch checkedChildren="开" unCheckedChildren="关" />
                  </Form.Item>
                )}
                {supportsConnectMode && (
                  <Form.Item name="connect_mode" label="Oracle 连接方式" style={{ marginBottom: 8 }}>
                    <Radio.Group size="small">
                      <Radio.Button value="service_name">Service Name</Radio.Button>
                      <Radio.Button value="sid">SID</Radio.Button>
                    </Radio.Group>
                  </Form.Item>
                )}
              </div>
            )}

            <Collapse
              ghost
              size="small"
              items={[{
                key: 'advanced',
                label: <Text style={{ color: 'var(--text-secondary)', fontSize: 13 }}>高级配置</Text>,
                children: (
                  <>
                    <Form.Item name="extra_jdbc" label="附加连接参数"
                      extra={isDm ? '可选 dmPython 驱动参数，格式 k1=v1&k2=v2；一般留空。账号、地址及超时请使用上方配置。' : 'k1=v1&k2=v2，会拼接到连接串'}>
                      <Input placeholder={isDm ? '留空使用达梦驱动默认配置' : selectedType?.db_type === 'clickhouse' ? 'socket_timeout=60' : 'charset=utf8mb4'} />
                    </Form.Item>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                      <Form.Item name="timeout" label="连接超时(秒)">
                        <InputNumber style={{ width: '100%' }} min={1} max={600} />
                      </Form.Item>
                      <Form.Item name="pool_size" label="连接池大小">
                        <InputNumber style={{ width: '100%' }} min={1} max={50} />
                      </Form.Item>
                      <Form.Item name="pool_timeout" label="取连接超时(秒)">
                        <InputNumber style={{ width: '100%' }} min={1} max={300} />
                      </Form.Item>
                    </div>
                  </>
                ),
              }]}
            />

            {probeResult && (
              <Alert
                style={{ marginBottom: 8 }}
                type={probeResult.success ? 'success' : 'error'}
                showIcon
                message={probeResult.success ? probeResult.message : '连接失败'}
                description={probeResult.success
                  ? <Text style={{ fontSize: 12 }}>
                      版本: {probeResult.version || '-'} · 耗时 {probeResult.latency_ms ?? 0}ms · {probeResult.server}
                    </Text>
                  : <Text style={{ fontSize: 12 }}>{probeResult.message}</Text>}
              />
            )}

            <Divider style={{ margin: '12px 0' }} />
            <Space>
              <Button icon={<ApiOutlined />} loading={probeLoading} onClick={handleProbe}>测试连接</Button>
              <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                仅使用当前表单参数探测，不会保存；编辑态留空密码将复用已保存密码。
              </Text>
            </Space>
          </Form>
        </div>
      </Modal>

      {/* 表结构抽屉 */}
      <Drawer
        title={
          <Space>
            <DatabaseOutlined style={{ color: 'var(--primary-light)' }} />
            <span>{drawerDs?.name}</span>
            {drawerDs && (
              <Tag color={accentOf(drawerDs.db_type)} style={{ borderRadius: 6, color: '#fff', border: 'none' }}>
                {labelOf(drawerDs.db_type)}
              </Tag>
            )}
            {drawerDs && <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{drawerDs.host}:{drawerDs.port}</Text>}
          </Space>
        }
        open={drawerOpen}
        onClose={closeDrawer}
        width={960}
        extra={
          <Space>
            <Upload accept=".sql,.ddl,.csv" showUploadList={false}
              beforeUpload={(file) => { if (drawerDs) handleUploadSchema(drawerDs.id, file as File); return false }}>
              <Button icon={<UploadOutlined />} size="small">上传表结构</Button>
            </Upload>
            <Button icon={<SyncOutlined />} size="small" onClick={() => drawerDs && handleSyncAll(drawerDs.id)}>
              同步全部
            </Button>
          </Space>
        }
      >
        <Tabs
          defaultActiveKey="live"
          items={[
            {
              key: 'live',
              label: <Space size={6}><ApiOutlined />线上表结构</Space>,
              children: (
                <div style={{ height: 'calc(100vh - 200px)' }}>
                  <SchemaBrowser
                    tables={liveTables}
                    loading={liveTablesLoading}
                    search={liveSearch}
                    onSearch={setLiveSearch}
                    selected={liveSelected}
                    onSelect={(name) => drawerDs && loadLiveColumns(drawerDs.id, name)}
                    columns={liveColumns}
                    columnsLoading={liveColumnsLoading}
                    emptyHint="读取数据源实时表清单失败时请检查连接配置"
                    onRefresh={() => drawerDs && loadLiveTables(drawerDs.id)}
                    selectedActions={liveSelected && (
                      <>
                        <Button size="small" icon={<EyeOutlined />} onClick={() => openPreview(liveSelected)}>预览数据</Button>
                        <Button size="small" icon={<CloudUploadOutlined />} onClick={() => handleSyncTable(liveSelected)}>同步此表</Button>
                      </>
                    )}
                  />
                </div>
              ),
            },
            {
              key: 'meta',
              label: <Space size={6}><DatabaseOutlined />已同步元数据 ({metaTables.length})</Space>,
              children: (
                <div style={{ height: 'calc(100vh - 200px)' }}>
                  <SchemaBrowser
                    tables={metaTables}
                    loading={metaTablesLoading}
                    search={metaSearch}
                    onSearch={setMetaSearch}
                    selected={metaSelected}
                    onSelect={(name) => drawerDs && loadMetaColumns(drawerDs.id, name)}
                    columns={metaColumns}
                    columnsLoading={metaColumnsLoading}
                    emptyHint="请点击「同步全部」从数据库拉取，或上传 DDL/CSV 文件"
                    onRefresh={() => drawerDs && loadMetaTables(drawerDs.id)}
                  />
                </div>
              ),
            },
          ]}
        />
      </Drawer>

      {/* 表数据预览 */}
      <Modal
        title={<Space><EyeOutlined /><span>{previewTable}</span>
          <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>最多 50 行</Text></Space>}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={<Button onClick={() => setPreviewOpen(false)}>关闭</Button>}
        width={960}
        zIndex={1100}
      >
        {previewLoading ? (
          <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
        ) : previewData.data?.length ? (
          <>
            <div style={{ marginBottom: 8 }}>
              <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                共 {previewData.row_count ?? previewData.data.length} 行 · {previewColumns.length} 列
              </Text>
            </div>
            <Table
              dataSource={previewData.data.map((row: any, i: number) => ({ ...row, __key: i }))}
              columns={previewColumns}
              rowKey="__key"
              size="small"
              pagination={false}
              scroll={{ x: 'max-content', y: 420 }}
            />
          </>
        ) : (
          <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Modal>
    </div>
  )
}

export default DataSource
