import React, { useState, useEffect } from 'react'
import {
  Card, Table, Button, Modal, Form, Input, Select, Tag, Space, message,
  Popconfirm, Upload, Drawer, Tree, Typography, Divider, Tooltip, Empty, Spin, Tabs,
} from 'antd'
import {
  PlusOutlined, ApiOutlined, SyncOutlined, DeleteOutlined, EditOutlined,
  UploadOutlined, DatabaseOutlined, TableOutlined, ColumnWidthOutlined,
  FileTextOutlined, CloudUploadOutlined, FolderOutlined, KeyOutlined,
  ReloadOutlined, SearchOutlined,
} from '@ant-design/icons'
import { datasourceApi } from '../services/api'

const { Text, Title } = Typography

const dbTypes = [
  { value: 'mysql', label: 'MySQL' },
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'clickhouse', label: 'ClickHouse' },
  { value: 'sqlserver', label: 'SQL Server' },
  { value: 'oracle', label: 'Oracle' },
]

const dbTypeColors: Record<string, string> = {
  mysql: '#4479A1', postgresql: '#336791', clickhouse: '#FFCC00',
  sqlserver: '#CC2132', oracle: '#F80000',
}

const DataSource: React.FC = () => {
  const [datasources, setDatasources] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()

  // Table structure drawer
  const [drawerVisible, setDrawerVisible] = useState(false)
  const [selectedDs, setSelectedDs] = useState<any>(null)
  const [tables, setTables] = useState<any[]>([])
  const [tablesLoading, setTablesLoading] = useState(false)
  const [selectedTable, setSelectedTable] = useState<string | null>(null)
  const [columns, setColumns] = useState<any[]>([])
  const [columnsLoading, setColumnsLoading] = useState(false)
  const [searchText, setSearchText] = useState('')

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const res: any = await datasourceApi.list()
      if (res.code === 0) setDatasources(res.data || [])
    } catch (e) { /* ignore */ }
    setLoading(false)
  }

  const handleCreate = async (values: any) => {
    try {
      await datasourceApi.create(values)
      message.success('创建成功')
      setModalVisible(false)
      form.resetFields()
      loadData()
    } catch (e: any) { /* handled by interceptor */ }
  }

  const handleTest = async (id: string) => {
    try {
      const res: any = await datasourceApi.testConnection(id)
      message.success(res.data?.message || '连接成功')
    } catch (e) { /* handled by interceptor */ }
  }

  const handleDelete = async (id: string) => {
    try {
      await datasourceApi.delete(id)
      message.success('删除成功')
      loadData()
    } catch (e) { /* handled by interceptor */ }
  }

  const handleBrowseTables = async (ds: any) => {
    setSelectedDs(ds)
    setDrawerVisible(true)
    setTablesLoading(true)
    try {
      const res: any = await datasourceApi.tables(ds.id)
      if (res.code === 0) setTables(res.data || [])
    } catch (e) { /* ignore */ }
    setTablesLoading(false)
  }

  const handleTableClick = async (tableName: string) => {
    if (!selectedDs) return
    setSelectedTable(tableName)
    setColumnsLoading(true)
    try {
      const res: any = await datasourceApi.columns(selectedDs.id, tableName)
      if (res.code === 0) setColumns(res.data || [])
    } catch (e) { /* ignore */ }
    setColumnsLoading(false)
  }

  const handleUploadSchema = async (dsId: string, file: File) => {
    try {
      const res: any = await datasourceApi.uploadSchema(dsId, file)
      if (res.code === 0) {
        message.success(res.message || `成功导入 ${res.data?.imported_tables} 张表`)
        // Refresh tables list
        const tablesRes: any = await datasourceApi.tables(dsId)
        if (tablesRes.code === 0) setTables(tablesRes.data || [])
      }
    } catch (e) { /* handled by interceptor */ }
    return false // prevent auto upload
  }

  const handleSyncSchema = async (dsId: string) => {
    try {
      const res: any = await datasourceApi.syncSchema(dsId)
      if (res.code === 0) {
        message.success(res.message || '同步完成')
        const tablesRes: any = await datasourceApi.tables(dsId)
        if (tablesRes.code === 0) setTables(tablesRes.data || [])
      }
    } catch (e) { /* handled by interceptor */ }
  }

  const filteredTables = tables.filter(t =>
    !searchText || t.table_name.toLowerCase().includes(searchText.toLowerCase())
  )

  const tableColumns = [
    { title: '名称', dataIndex: 'name', key: 'name',
      render: (name: string, record: any) => (
        <Space>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: dbTypeColors[record.db_type] || '#6366f1' }} />
          <Text style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{name}</Text>
        </Space>
      )
    },
    { title: '类型', dataIndex: 'db_type', key: 'db_type',
      render: (t: string) => <Tag color={dbTypeColors[t] || 'blue'} style={{ borderRadius: 6 }}>{t.toUpperCase()}</Tag>
    },
    { title: '主机', dataIndex: 'host', key: 'host', render: (h: string) => <Text style={{ color: 'var(--text-secondary)' }}>{h}</Text> },
    { title: '端口', dataIndex: 'port', key: 'port', render: (p: number) => <Text style={{ color: 'var(--text-secondary)' }}>{p}</Text> },
    { title: '数据库', dataIndex: 'database_name', key: 'database_name', render: (d: string) => <Text style={{ color: 'var(--text-secondary)' }}>{d}</Text> },
    { title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={s === 'active' ? 'success' : s === 'error' ? 'error' : 'default'} style={{ borderRadius: 6 }}>{s === 'active' ? '正常' : s === 'error' ? '异常' : '未连接'}</Tag>
    },
    {
      title: '操作', key: 'action', width: 320,
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<ApiOutlined />} onClick={() => handleTest(record.id)}>测试</Button>
          <Button size="small" icon={<TableOutlined />} onClick={() => handleBrowseTables(record)}>浏览</Button>
          <Button size="small" icon={<SyncOutlined />} loading={false} onClick={() => handleSyncSchema(record.id)}>同步</Button>
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    },
  ]

  const columnTableColumns = [
    { title: '字段名', dataIndex: 'column_name', key: 'column_name',
      render: (name: string, record: any) => (
        <Space>
          {record.is_primary_key && <KeyOutlined style={{ color: '#f59e0b', fontSize: 12 }} />}
          <Text style={{ color: 'var(--text-primary)', fontFamily: 'monospace', fontSize: 13 }}>{name}</Text>
        </Space>
      )
    },
    { title: '类型', dataIndex: 'column_type', key: 'column_type',
      render: (t: string) => <Tag style={{ borderRadius: 4, fontFamily: 'monospace', fontSize: 11 }}>{t}</Tag>
    },
    { title: '注释', dataIndex: 'column_comment', key: 'column_comment',
      render: (c: string) => <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{c || '-'}</Text>
    },
    { title: '可空', dataIndex: 'is_nullable', key: 'is_nullable', width: 60,
      render: (v: any) => <Tag color={v ? 'default' : 'warning'} style={{ fontSize: 11 }}>{v ? 'Y' : 'N'}</Tag>
    },
    { title: '主键', dataIndex: 'is_primary_key', key: 'is_primary_key', width: 60,
      render: (v: any) => <Tag color={v ? 'gold' : 'default'} style={{ fontSize: 11 }}>{v ? 'PK' : '-'}</Tag>
    },
  ]

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card
        title={<Space><DatabaseOutlined /><span>数据源管理</span></Space>}
        extra={
          <Button className="glow-btn" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
            新增数据源
          </Button>
        }
      >
        <Table dataSource={datasources} columns={tableColumns} loading={loading} rowKey="id"
          pagination={false} />
      </Card>

      {/* Create Modal */}
      <Modal title="新增数据源" open={modalVisible} onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()} destroyOnClose width={520}>
        <Form form={form} onFinish={handleCreate} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input placeholder="例如：生产库-MySQL" /></Form.Item>
          <Form.Item name="db_type" label="数据库类型" rules={[{ required: true }]}>
            <Select options={dbTypes} placeholder="选择数据库类型" />
          </Form.Item>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
            <Form.Item name="host" label="主机地址" rules={[{ required: true }]}><Input placeholder="192.168.1.100" /></Form.Item>
            <Form.Item name="port" label="端口" rules={[{ required: true }]}><Input type="number" placeholder="3306" /></Form.Item>
          </div>
          <Form.Item name="database_name" label="数据库名" rules={[{ required: true }]}><Input placeholder="my_database" /></Form.Item>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Form.Item name="username" label="用户名" rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="password" label="密码" rules={[{ required: true }]}><Input.Password /></Form.Item>
          </div>
        </Form>
      </Modal>

      {/* Table Structure Drawer */}
      <Drawer
        title={
          <Space>
            <DatabaseOutlined style={{ color: 'var(--primary-light)' }} />
            <span>{selectedDs?.name} - 表结构</span>
          </Space>
        }
        open={drawerVisible}
        onClose={() => { setDrawerVisible(false); setSelectedDs(null); setTables([]); setColumns([]); setSelectedTable(null) }}
        width={720}
        extra={
          <Space>
            <Upload accept=".sql,.ddl,.csv" showUploadList={false}
              beforeUpload={(file) => { handleUploadSchema(selectedDs?.id, file); return false }}>
              <Button icon={<UploadOutlined />} size="small">上传表结构</Button>
            </Upload>
            <Button icon={<ReloadOutlined />} size="small" onClick={() => selectedDs && handleSyncSchema(selectedDs.id)}>
              同步
            </Button>
          </Space>
        }
      >
        <div style={{ display: 'flex', gap: 16, height: '100%' }}>
          {/* Table list */}
          <div style={{ width: 220, borderRight: '1px solid var(--border-glass)', paddingRight: 16 }}>
            <Input
              placeholder="搜索表名..."
              prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              style={{ marginBottom: 12, borderRadius: 8 }}
              allowClear
            />
            {tablesLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : filteredTables.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <Empty description="暂无表结构" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                <Text style={{ color: 'var(--text-muted)', fontSize: 12, display: 'block', marginTop: 8 }}>
                  请上传DDL/CSV文件或同步数据源
                </Text>
              </div>
            ) : (
              <div>
                <Text style={{ color: 'var(--text-muted)', fontSize: 11, marginBottom: 8, display: 'block' }}>
                  共 {filteredTables.length} 张表
                </Text>
                {filteredTables.map(t => (
                  <div key={t.id}
                    onClick={() => handleTableClick(t.table_name)}
                    style={{
                      padding: '8px 12px', cursor: 'pointer', borderRadius: 8, marginBottom: 2,
                      background: selectedTable === t.table_name ? 'rgba(99,102,241,0.15)' : 'transparent',
                      border: selectedTable === t.table_name ? '1px solid rgba(99,102,241,0.3)' : '1px solid transparent',
                      transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => { if (selectedTable !== t.table_name) (e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.03)' }}
                    onMouseLeave={e => { if (selectedTable !== t.table_name) (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
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
              </div>
            )}
          </div>

          {/* Column details */}
          <div style={{ flex: 1 }}>
            {selectedTable ? (
              <>
                <div style={{ marginBottom: 12 }}>
                  <Title level={5} style={{ color: 'var(--text-primary)', margin: 0 }}>
                    <TableOutlined style={{ marginRight: 8, color: 'var(--primary-light)' }} />
                    {selectedTable}
                  </Title>
                </div>
                {columnsLoading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : (
                  <Table
                    dataSource={columns}
                    columns={columnTableColumns}
                    rowKey="id"
                    size="small"
                    pagination={false}
                    scroll={{ y: 400 }}
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
      </Drawer>
    </div>
  )
}

export default DataSource
