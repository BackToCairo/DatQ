import React, { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Modal, Form, Input, Select,
  InputNumber, Drawer, Tabs, Popconfirm, message, Empty,
} from 'antd'
import {
  PlusOutlined, AppstoreOutlined, EditOutlined, DeleteOutlined,
  BarChartOutlined, BorderOuterOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { semanticApi, datasourceApi } from '../services/api'

const { Text } = Typography

const METRIC_TYPES = ['float', 'int', 'string']
const DIM_TYPES = ['string', 'number', 'date', 'time']

/** 语义层: 语义模型 / 指标 / 维度管理 */
const Semantic: React.FC = () => {
  const [models, setModels] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [datasources, setDatasources] = useState<any[]>([])

  // 模型弹窗
  const [modelModal, setModelModal] = useState(false)
  const [editingModel, setEditingModel] = useState<any>(null)
  const [modelForm] = Form.useForm()

  // 模型详情抽屉(指标/维度)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [currentModel, setCurrentModel] = useState<any>(null)
  const [detail, setDetail] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // 指标弹窗
  const [metricModal, setMetricModal] = useState(false)
  const [editingMetric, setEditingMetric] = useState<any>(null)
  const [metricForm] = Form.useForm()

  // 维度弹窗
  const [dimModal, setDimModal] = useState(false)
  const [editingDim, setEditingDim] = useState<any>(null)
  const [dimForm] = Form.useForm()

  useEffect(() => { loadModels(); loadDatasources() }, [])

  const loadModels = async () => {
    setLoading(true)
    try {
      const res: any = await semanticApi.listModels()
      if (res.code === 0) setModels(res.data || [])
    } catch (e) { /* interceptor 已提示 */ }
    setLoading(false)
  }

  const loadDatasources = async () => {
    try {
      const res: any = await datasourceApi.list()
      if (res.code === 0) setDatasources(res.data || [])
    } catch (e) { /* ignore */ }
  }

  const openDetail = async (model: any) => {
    setCurrentModel(model)
    setDrawerOpen(true)
    setDetailLoading(true)
    try {
      const res: any = await semanticApi.getModel(model.id)
      if (res.code === 0) setDetail(res.data)
    } catch (e) { /* ignore */ }
    setDetailLoading(false)
  }

  // ========== 模型 CRUD ==========
  const openModelModal = (model?: any) => {
    setEditingModel(model || null)
    if (model) {
      modelForm.setFieldsValue(model)
    } else {
      modelForm.resetFields()
    }
    setModelModal(true)
  }

  const handleModelSubmit = async (values: any) => {
    try {
      if (editingModel) {
        await semanticApi.updateModel(editingModel.id, values)
        message.success('模型已更新')
      } else {
        await semanticApi.createModel(values)
        message.success('模型已创建')
      }
      setModelModal(false)
      loadModels()
    } catch (e) { /* ignore */ }
  }

  const handleModelDelete = async (id: string) => {
    try {
      await semanticApi.deleteModel(id)
      message.success('已删除')
      if (currentModel?.id === id) setDrawerOpen(false)
      loadModels()
    } catch (e) { /* ignore */ }
  }

  // ========== 指标 CRUD ==========
  const openMetricModal = (metric?: any) => {
    setEditingMetric(metric || null)
    if (metric) {
      metricForm.setFieldsValue({
        ...metric,
        dimensions: metric.dimensions || [],
        synonyms: metric.synonyms || [],
        tags: metric.tags || [],
      })
    } else {
      metricForm.resetFields()
    }
    setMetricModal(true)
  }

  const reloadDetail = async () => {
    if (!currentModel) return
    const res: any = await semanticApi.getModel(currentModel.id)
    if (res.code === 0) setDetail(res.data)
  }

  const handleMetricSubmit = async (values: any) => {
    try {
      if (editingMetric) {
        await semanticApi.updateMetric(currentModel.id, editingMetric.id, values)
        message.success('指标已更新')
      } else {
        await semanticApi.createMetric(currentModel.id, values)
        message.success('指标已创建')
      }
      setMetricModal(false)
      reloadDetail()
      loadModels()
    } catch (e) { /* ignore */ }
  }

  const handleMetricDelete = async (metricId: string) => {
    try {
      await semanticApi.deleteMetric(currentModel.id, metricId)
      message.success('已删除')
      reloadDetail()
      loadModels()
    } catch (e) { /* ignore */ }
  }

  // ========== 维度 CRUD ==========
  const openDimModal = (dim?: any) => {
    setEditingDim(dim || null)
    if (dim) {
      dimForm.setFieldsValue({ ...dim, synonyms: dim.synonyms || [] })
    } else {
      dimForm.resetFields()
    }
    setDimModal(true)
  }

  const handleDimSubmit = async (values: any) => {
    try {
      if (editingDim) {
        await semanticApi.updateDimension(currentModel.id, editingDim.id, values)
        message.success('维度已更新')
      } else {
        await semanticApi.createDimension(currentModel.id, values)
        message.success('维度已创建')
      }
      setDimModal(false)
      reloadDetail()
      loadModels()
    } catch (e) { /* ignore */ }
  }

  const handleDimDelete = async (dimId: string) => {
    try {
      await semanticApi.deleteDimension(currentModel.id, dimId)
      message.success('已删除')
      reloadDetail()
      loadModels()
    } catch (e) { /* ignore */ }
  }

  // ========== 表格列 ==========
  const modelColumns = [
    {
      title: '模型', key: 'name',
      render: (_: any, r: any) => (
        <Space>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(99,102,241,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <AppstoreOutlined style={{ color: 'var(--primary-light)', fontSize: 14 }} />
          </div>
          <div>
            <Text style={{ color: 'var(--text-primary)', display: 'block', fontSize: 13 }}>{r.display_name}</Text>
            <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>{r.name}</Text>
          </div>
        </Space>
      ),
    },
    {
      title: '主表', dataIndex: 'base_table', key: 'base_table',
      render: (t: string) => <Text code style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{t || '-'}</Text>,
    },
    {
      title: '数据源', key: 'ds',
      render: (_: any, r: any) => {
        const ds = datasources.find((d: any) => d.id === r.datasource_id)
        return <Tag style={{ borderRadius: 6, fontSize: 11 }}>{ds ? ds.name : '-'}</Tag>
      },
    },
    {
      title: '指标/维度', key: 'counts', width: 110,
      render: (_: any, r: any) => (
        <Space size={4}>
          <Tag color="blue" style={{ borderRadius: 6, fontSize: 11 }}>{r.metric_count} 指标</Tag>
          <Tag color="cyan" style={{ borderRadius: 6, fontSize: 11 }}>{r.dimension_count} 维度</Tag>
        </Space>
      ),
    },
    {
      title: '描述', dataIndex: 'description', key: 'description', ellipsis: true,
      render: (d: string) => <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{d || '-'}</Text>,
    },
    {
      title: '操作', key: 'action', width: 200,
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<BorderOuterOutlined />} onClick={() => openDetail(r)}>管理</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openModelModal(r)} />
          <Popconfirm title="删除模型将级联删除其指标与维度, 确认?" onConfirm={() => handleModelDelete(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const metricColumns = [
    { title: '指标', key: 'name', render: (_: any, r: any) => (
      <div><Text style={{ color: 'var(--text-primary)', fontSize: 13 }}>{r.display_name}</Text>
        <Text style={{ color: 'var(--text-muted)', fontSize: 11, display: 'block' }}>{r.name}</Text></div>
    )},
    { title: '表达式', dataIndex: 'expression', key: 'expression', render: (e: string) => (
      <Text code style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{e}</Text>
    )},
    { title: '类型', dataIndex: 'data_type', key: 'data_type', width: 70,
      render: (t: string) => <Tag style={{ borderRadius: 6, fontSize: 11 }}>{t}</Tag> },
    { title: '相关维度', dataIndex: 'dimensions', key: 'dimensions',
      render: (d: string[]) => (d || []).map(x => <Tag key={x} color="cyan" style={{ borderRadius: 6, fontSize: 11 }}>{x}</Tag>) },
    { title: '操作', key: 'action', width: 90, render: (_: any, r: any) => (
      <Space>
        <Button size="small" icon={<EditOutlined />} onClick={() => openMetricModal(r)} />
        <Popconfirm title="确认删除该指标?" onConfirm={() => handleMetricDelete(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      </Space>
    )},
  ]

  const dimColumns = [
    { title: '维度', key: 'name', render: (_: any, r: any) => (
      <div><Text style={{ color: 'var(--text-primary)', fontSize: 13 }}>{r.display_name}</Text>
        <Text style={{ color: 'var(--text-muted)', fontSize: 11, display: 'block' }}>{r.name}</Text></div>
    )},
    { title: '字段', dataIndex: 'column_name', key: 'column_name',
      render: (c: string) => <Text code style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{c}</Text> },
    { title: '类型', dataIndex: 'data_type', key: 'data_type', width: 80,
      render: (t: string) => <Tag style={{ borderRadius: 6, fontSize: 11 }}>{t}</Tag> },
    { title: '层级', dataIndex: 'hierarchy_level', key: 'hierarchy_level', width: 60,
      render: (l: any) => <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{l ?? '-'}</Text> },
    { title: '同义词', dataIndex: 'synonyms', key: 'synonyms',
      render: (s: string[]) => (s || []).map(x => <Tag key={x} style={{ borderRadius: 6, fontSize: 11 }}>{x}</Tag>) },
    { title: '操作', key: 'action', width: 90, render: (_: any, r: any) => (
      <Space>
        <Button size="small" icon={<EditOutlined />} onClick={() => openDimModal(r)} />
        <Popconfirm title="确认删除该维度?" onConfirm={() => handleDimDelete(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      </Space>
    )},
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card
        title={<Space><AppstoreOutlined /><span>语义层 - 语义模型</span></Space>}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadModels} />
            <Button className="glow-btn" icon={<PlusOutlined />} onClick={() => openModelModal()}>
              新建模型
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={models} columns={modelColumns} rowKey="id"
          loading={loading} pagination={false}
          locale={{ emptyText: <Empty description="暂无语义模型, 点击右上角创建" /> }}
        />
      </Card>

      {/* 新建/编辑模型 */}
      <Modal
        title={editingModel ? '编辑语义模型' : '新建语义模型'}
        open={modelModal} onCancel={() => setModelModal(false)}
        onOk={() => modelForm.submit()} destroyOnClose
      >
        <Form form={modelForm} layout="vertical" onFinish={handleModelSubmit} style={{ marginTop: 12 }}>
          <Form.Item name="name" label="模型名称(英文标识)" rules={[{ required: true }]}>
            <Input placeholder="例如: sales_analysis" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}>
            <Input placeholder="例如: 销售分析模型" />
          </Form.Item>
          <Form.Item name="datasource_id" label="数据源">
            <Select
              allowClear placeholder="选择数据源"
              options={datasources.map((d: any) => ({ value: d.id, label: `${d.name} (${d.db_type})` }))}
            />
          </Form.Item>
          <Form.Item name="base_table" label="主表">
            <Input placeholder="例如: demo_sales_orders" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="模型业务描述(可选)" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 模型详情: 指标/维度管理 */}
      <Drawer
        title={currentModel ? `管理: ${currentModel.display_name}` : ''}
        open={drawerOpen} onClose={() => setDrawerOpen(false)} width={860}
      >
        {detail ? (
          <Tabs
            defaultActiveKey="metrics"
            items={[
              {
                key: 'metrics',
                label: <span><BarChartOutlined /> 指标 ({detail.metrics?.length || 0})</span>,
                children: (
                  <div>
                    <div style={{ marginBottom: 12 }}>
                      <Button type="primary" icon={<PlusOutlined />} onClick={() => openMetricModal()}>
                        新增指标
                      </Button>
                    </div>
                    <Table dataSource={detail.metrics || []} columns={metricColumns} rowKey="id" pagination={false} />
                  </div>
                ),
              },
              {
                key: 'dimensions',
                label: <span><BorderOuterOutlined /> 维度 ({detail.dimensions?.length || 0})</span>,
                children: (
                  <div>
                    <div style={{ marginBottom: 12 }}>
                      <Button type="primary" icon={<PlusOutlined />} onClick={() => openDimModal()}>
                        新增维度
                      </Button>
                    </div>
                    <Table dataSource={detail.dimensions || []} columns={dimColumns} rowKey="id" pagination={false} />
                  </div>
                ),
              },
            ]}
          />
        ) : (
          <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
            {detailLoading ? '加载中...' : '暂无数据'}
          </div>
        )}
      </Drawer>

      {/* 新增/编辑指标 */}
      <Modal
        title={editingMetric ? '编辑指标' : '新增指标'}
        open={metricModal} onCancel={() => setMetricModal(false)}
        onOk={() => metricForm.submit()} destroyOnClose
      >
        <Form form={metricForm} layout="vertical" onFinish={handleMetricSubmit} style={{ marginTop: 12 }}>
          <Form.Item name="name" label="指标名称(英文标识)" rules={[{ required: true }]}>
            <Input placeholder="例如: total_sales" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}>
            <Input placeholder="例如: 销售额" />
          </Form.Item>
          <Form.Item name="expression" label="聚合表达式" rules={[{ required: true }]}>
            <Input placeholder="例如: SUM(demo_sales_orders.amount)" />
          </Form.Item>
          <Form.Item name="data_type" label="数据类型" initialValue="float" rules={[{ required: true }]}>
            <Select options={METRIC_TYPES.map(t => ({ value: t, label: t }))} />
          </Form.Item>
          <Form.Item name="dimensions" label="相关维度">
            <Select mode="tags" placeholder="输入维度名称后回车, 例如: 区域" />
          </Form.Item>
          <Form.Item name="synonyms" label="同义词">
            <Select mode="tags" placeholder="例如: 销售金额、GMV" />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="业务标签(可选)" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新增/编辑维度 */}
      <Modal
        title={editingDim ? '编辑维度' : '新增维度'}
        open={dimModal} onCancel={() => setDimModal(false)}
        onOk={() => dimForm.submit()} destroyOnClose
      >
        <Form form={dimForm} layout="vertical" onFinish={handleDimSubmit} style={{ marginTop: 12 }}>
          <Form.Item name="name" label="维度名称(英文标识)" rules={[{ required: true }]}>
            <Input placeholder="例如: region" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}>
            <Input placeholder="例如: 区域" />
          </Form.Item>
          <Form.Item name="column_name" label="关联字段" rules={[{ required: true }]}>
            <Input placeholder="例如: demo_regions.name 或 order_date" />
          </Form.Item>
          <Form.Item name="data_type" label="数据类型" initialValue="string" rules={[{ required: true }]}>
            <Select options={DIM_TYPES.map(t => ({ value: t, label: t }))} />
          </Form.Item>
          <Form.Item name="hierarchy_level" label="层级(1-5)">
            <InputNumber min={1} max={5} style={{ width: '100%' }} placeholder="日期维度可设年/月/日层级" />
          </Form.Item>
          <Form.Item name="synonyms" label="同义词">
            <Select mode="tags" placeholder="例如: 地区、大区" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Semantic
