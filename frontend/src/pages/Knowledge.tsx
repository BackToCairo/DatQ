import React, { useState, useEffect } from 'react'
import {
  Card, Tabs, Table, Button, Tag, Empty, Modal, Form, Input, Select,
  Upload, message, Popconfirm, Space, Typography, Tooltip,
} from 'antd'
import {
  UploadOutlined, PlusOutlined, DeleteOutlined, FileTextOutlined,
  CodeOutlined, SearchOutlined, BookOutlined, EditOutlined,
  CheckCircleOutlined, ExperimentOutlined,
} from '@ant-design/icons'
import { knowledgeApi } from '../services/api'

const { Text, Paragraph, Title } = Typography
const { TextArea } = Input

const Knowledge: React.FC = () => {
  const [activeTab, setActiveTab] = useState('docs')

  // Document state
  const [docs, setDocs] = useState<any[]>([])
  const [docsLoading, setDocsLoading] = useState(false)
  const [docModalVisible, setDocModalVisible] = useState(false)
  const [docForm] = Form.useForm()

  // SQL Example state
  const [sqlExamples, setSqlExamples] = useState<any[]>([])
  const [sqlLoading, setSqlLoading] = useState(false)
  const [sqlModalVisible, setSqlModalVisible] = useState(false)
  const [sqlForm] = Form.useForm()

  // Retrieve test state
  const [testQuery, setTestQuery] = useState('')
  const [testResults, setTestResults] = useState<any[]>([])
  const [testLoading, setTestLoading] = useState(false)

  useEffect(() => { loadDocs(); loadSqlExamples() }, [])

  const loadDocs = async () => {
    setDocsLoading(true)
    try {
      const res: any = await knowledgeApi.listDocs()
      if (res.code === 0) setDocs(res.data || [])
    } catch (e) { /* ignore */ }
    setDocsLoading(false)
  }

  const loadSqlExamples = async () => {
    setSqlLoading(true)
    try {
      const res: any = await knowledgeApi.listSqlExamples()
      if (res.code === 0) setSqlExamples(res.data || [])
    } catch (e) { /* ignore */ }
    setSqlLoading(false)
  }

  const handleCreateDoc = async (values: any) => {
    try {
      await knowledgeApi.createDoc(values)
      message.success('创建成功')
      setDocModalVisible(false)
      docForm.resetFields()
      loadDocs()
    } catch (e) { /* ignore */ }
  }

  const handleUploadDoc = async (file: File) => {
    try {
      await knowledgeApi.uploadDoc(file, file.name, 'file')
      message.success('上传成功')
      loadDocs()
    } catch (e) { /* ignore */ }
    return false
  }

  const handleDeleteDoc = async (id: string) => {
    try {
      await knowledgeApi.deleteDoc(id)
      message.success('删除成功')
      loadDocs()
    } catch (e) { /* ignore */ }
  }

  const handleCreateSqlExample = async (values: any) => {
    try {
      await knowledgeApi.createSqlExample(values)
      message.success('创建成功')
      setSqlModalVisible(false)
      sqlForm.resetFields()
      loadSqlExamples()
    } catch (e) { /* ignore */ }
  }

  const handleDeleteSqlExample = async (id: string) => {
    try {
      await knowledgeApi.deleteSqlExample(id)
      message.success('删除成功')
      loadSqlExamples()
    } catch (e) { /* ignore */ }
  }

  const handleRetrieveTest = async () => {
    if (!testQuery.trim()) return
    setTestLoading(true)
    try {
      const res: any = await knowledgeApi.retrieveTest({ query: testQuery, top_k: 5 })
      if (res.code === 0) setTestResults(res.data?.results || [])
    } catch (e) { /* ignore */ }
    setTestLoading(false)
  }

  const docColumns = [
    {
      title: '标题', dataIndex: 'title', key: 'title',
      render: (t: string) => (
        <Space><FileTextOutlined style={{ color: 'var(--primary-light)' }} /><Text style={{ color: 'var(--text-primary)' }}>{t}</Text></Space>
      )
    },
    {
      title: '类型', dataIndex: 'doc_type', key: 'doc_type',
      render: (t: string) => <Tag color={t === 'file' ? 'blue' : 'green'} style={{ borderRadius: 6 }}>{t === 'file' ? '文件' : '文本'}</Tag>
    },
    {
      title: '分块数', dataIndex: 'chunk_count', key: 'chunk_count',
      render: (c: number) => <Text style={{ color: 'var(--text-secondary)' }}>{c}</Text>
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => (
        <Tag color={s === 'active' ? 'success' : s === 'processing' ? 'processing' : 'default'} style={{ borderRadius: 6 }}>
          {s === 'active' ? '就绪' : s === 'processing' ? '处理中' : '异常'}
        </Tag>
      )
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at',
      render: (t: string) => <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{new Date(t).toLocaleString()}</Text>
    },
    {
      title: '操作', key: 'action', width: 80,
      render: (_: any, record: any) => (
        <Popconfirm title="确认删除?" onConfirm={() => handleDeleteDoc(record.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      )
    },
  ]

  const sqlColumns = [
    {
      title: '问题', dataIndex: 'question', key: 'question', width: 200,
      render: (q: string) => <Text style={{ color: 'var(--text-primary)' }}>{q}</Text>
    },
    {
      title: 'SQL', dataIndex: 'sql_content', key: 'sql_content',
      render: (sql: string) => (
        <Tooltip title={sql}>
          <Text style={{ color: 'var(--text-secondary)', fontFamily: 'monospace', fontSize: 12 }} ellipsis>
            {sql}
          </Text>
        </Tooltip>
      )
    },
    {
      title: '描述', dataIndex: 'description', key: 'description', width: 150,
      render: (d: string) => <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{d || '-'}</Text>
    },
    {
      title: '使用次数', dataIndex: 'use_count', key: 'use_count', width: 90,
      render: (c: number) => <Tag style={{ borderRadius: 6 }}>{c}</Tag>
    },
    {
      title: '操作', key: 'action', width: 80,
      render: (_: any, record: any) => (
        <Popconfirm title="确认删除?" onConfirm={() => handleDeleteSqlExample(record.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      )
    },
  ]

  const tabItems = [
    {
      key: 'docs',
      label: <span><FileTextOutlined /> 文档管理</span>,
      children: (
        <div>
          <div style={{ marginBottom: 16, display: 'flex', gap: 12 }}>
            <Upload accept=".txt,.md,.pdf,.doc,.docx" showUploadList={false} beforeUpload={handleUploadDoc}>
              <Button icon={<UploadOutlined />} className="glow-btn">上传文档</Button>
            </Upload>
            <Button icon={<PlusOutlined />} onClick={() => setDocModalVisible(true)}>新建文档</Button>
          </div>
          <Table dataSource={docs} columns={docColumns} loading={docsLoading} rowKey="id"
            locale={{ emptyText: <Empty description="暂无知识文档，请上传业务文档以增强问数准确率" /> }} />
        </div>
      ),
    },
    {
      key: 'sql',
      label: <span><CodeOutlined /> SQL示例</span>,
      children: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <Button icon={<PlusOutlined />} className="glow-btn" onClick={() => setSqlModalVisible(true)}>
              新增示例
            </Button>
          </div>
          <Table dataSource={sqlExamples} columns={sqlColumns} loading={sqlLoading} rowKey="id"
            locale={{ emptyText: <Empty description="暂无SQL示例，添加问答对可提升查询准确率" /> }} />
        </div>
      ),
    },
    {
      key: 'test',
      label: <span><ExperimentOutlined /> 检索测试</span>,
      children: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 12 }}>
              <Input
                value={testQuery}
                onChange={e => setTestQuery(e.target.value)}
                onPressEnter={handleRetrieveTest}
                placeholder="输入问题测试知识检索效果..."
                prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
                style={{ borderRadius: 10 }}
              />
              <Button className="glow-btn" onClick={handleRetrieveTest} loading={testLoading}>
                测试检索
              </Button>
            </div>
          </div>
          {testResults.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {testResults.map((r, i) => (
                <div key={i} className="glass-card" style={{ padding: '14px 18px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <Tag color={r.type === 'sql_example' ? 'blue' : 'green'} style={{ borderRadius: 6 }}>
                      {r.type === 'sql_example' ? 'SQL示例' : '文档'}
                    </Tag>
                    <Tag color="purple" style={{ borderRadius: 6 }}>相似度: {(r.score * 100).toFixed(1)}%</Tag>
                  </div>
                  {r.question && <Text style={{ color: 'var(--text-primary)', fontSize: 13, display: 'block', marginBottom: 6 }}>Q: {r.question}</Text>}
                  <pre style={{
                    margin: 0, padding: '8px 12px', fontSize: 12, fontFamily: 'monospace',
                    color: 'var(--text-secondary)', background: 'rgba(0,0,0,0.2)', borderRadius: 6, overflow: 'auto',
                  }}>
                    {r.content}
                  </pre>
                </div>
              ))}
            </div>
          ) : (
            <Empty description="输入问题后点击测试检索" />
          )}
        </div>
      ),
    },
  ]

  return (
    <Card title={<Space><BookOutlined /><span>知识库管理</span></Space>}>
      <Tabs items={tabItems} activeKey={activeTab} onChange={setActiveTab} />

      {/* Create Doc Modal */}
      <Modal title="新建知识文档" open={docModalVisible} onCancel={() => setDocModalVisible(false)}
        onOk={() => docForm.submit()} destroyOnClose>
        <Form form={docForm} onFinish={handleCreateDoc} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input placeholder="文档标题" /></Form.Item>
          <Form.Item name="doc_type" label="类型" rules={[{ required: true }]}>
            <Select options={[{ value: 'text', label: '文本' }, { value: 'schema', label: 'Schema说明' }, { value: 'business', label: '业务规则' }]} />
          </Form.Item>
          <Form.Item name="content" label="内容" rules={[{ required: true }]}>
            <TextArea rows={8} placeholder="输入文档内容..." />
          </Form.Item>
        </Form>
      </Modal>

      {/* Create SQL Example Modal */}
      <Modal title="新增SQL示例" open={sqlModalVisible} onCancel={() => setSqlModalVisible(false)}
        onOk={() => sqlForm.submit()} destroyOnClose width={600}>
        <Form form={sqlForm} onFinish={handleCreateSqlExample} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="question" label="问题" rules={[{ required: true }]}><Input placeholder="例如：上个月各区域销售额是多少？" /></Form.Item>
          <Form.Item name="sql_content" label="SQL" rules={[{ required: true }]}>
            <TextArea rows={4} placeholder="SELECT region, SUM(amount) FROM sales GROUP BY region" style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item name="description" label="描述"><Input placeholder="示例说明（可选）" /></Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}

export default Knowledge
