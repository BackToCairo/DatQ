import React, { useState, useEffect } from 'react'
import { Card, Row, Col, Statistic, Button, Modal, Form, Input, Empty, Space, Typography, Tag, Spin, message } from 'antd'
import {
  PlusOutlined, DashboardOutlined, DatabaseOutlined, MessageOutlined,
  TeamOutlined, ThunderboltOutlined, BarChartOutlined, LineChartOutlined,
  PieChartOutlined, TableOutlined, DeleteOutlined, EyeOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { dashboardApi, adminApi } from '../services/api'

const { Text, Title } = Typography

const Dashboard: React.FC = () => {
  const [dashboards, setDashboards] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [form] = Form.useForm()
  const [overview, setOverview] = useState<any>(null)
  const [overviewLoading, setOverviewLoading] = useState(false)
  const [trend, setTrend] = useState<any[] | null>(null)
  const [distribution, setDistribution] = useState<any[] | null>(null)

  useEffect(() => { loadDashboards(); loadOverview(); loadTrend(); loadDistribution() }, [])

  // 管理员统计(非管理员 403 时静默降级隐藏图表)
  const loadTrend = async () => {
    try {
      const res: any = await adminApi.queryTrend(14)
      if (res.code === 0) setTrend(res.data || [])
    } catch (e) { /* 非管理员无权限 */ }
  }

  const loadDistribution = async () => {
    try {
      const res: any = await adminApi.datasourceDistribution()
      if (res.code === 0) setDistribution(res.data || [])
    } catch (e) { /* 非管理员无权限 */ }
  }

  const loadDashboards = async () => {
    setLoading(true)
    try {
      const res: any = await dashboardApi.list()
      if (res.code === 0) setDashboards(res.data || [])
    } catch (e) { /* ignore */ }
    setLoading(false)
  }

  const loadOverview = async () => {
    setOverviewLoading(true)
    try {
      const res: any = await dashboardApi.systemOverview()
      if (res.code === 0) setOverview(res.data)
    } catch (e) { /* ignore */ }
    setOverviewLoading(false)
  }

  const handleCreate = async (values: any) => {
    try {
      await dashboardApi.create(values)
      message.success('创建成功')
      setCreateModalVisible(false)
      form.resetFields()
      loadDashboards()
    } catch (e) { /* ignore */ }
  }

  const handleDelete = async (id: string) => {
    try {
      await dashboardApi.delete(id)
      message.success('删除成功')
      loadDashboards()
    } catch (e) { /* ignore */ }
  }

  // 真实统计数据图表
  const DS_COLORS: Record<string, string> = {
    postgresql: '#336791', mysql: '#4479A1', clickhouse: '#FFCC00',
  }

  const getQueryTrendOption = () => ({
    tooltip: { trigger: 'axis' },
    legend: { data: ['总查询', '成功'], textStyle: { color: '#94a3b8', fontSize: 11 }, top: 0, right: 10 },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: {
      type: 'category',
      data: (trend || []).map((t: any) => String(t.date).slice(5)),
      axisLabel: { color: '#94a3b8', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
    },
    series: [
      {
        name: '总查询', type: 'line', smooth: true,
        data: (trend || []).map((t: any) => t.total),
        areaStyle: { opacity: 0.15 },
        lineStyle: { width: 2 },
        itemStyle: { color: '#818cf8' },
      },
      {
        name: '成功', type: 'line', smooth: true,
        data: (trend || []).map((t: any) => t.success),
        lineStyle: { width: 2 },
        itemStyle: { color: '#10b981' },
      },
    ],
  })

  const getDatasourceTypeOption = () => ({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 次 ({d}%)' },
    series: [{
      type: 'pie', radius: ['40%', '70%'], center: ['50%', '50%'],
      data: (distribution || []).map((d: any, i: number) => ({
        value: d.query_count,
        name: d.name,
        itemStyle: { color: DS_COLORS[d.db_type] || ['#818cf8', '#06b6d4', '#f59e0b', '#ef4444'][i % 4] },
      })),
      label: { color: '#94a3b8', fontSize: 11 },
      itemStyle: { borderColor: '#1a1a3e', borderWidth: 2 },
    }],
  })

  const statCards = overview ? [
    { title: '数据源', value: overview.total_datasources, icon: <DatabaseOutlined />, color: '#818cf8', sub: `${overview.active_datasources} 个在线` },
    { title: '总对话数', value: overview.total_conversations, icon: <MessageOutlined />, color: '#06b6d4', sub: '累计对话' },
    { title: '今日查询', value: overview.total_queries_today, icon: <ThunderboltOutlined />, color: '#10b981', sub: '今日活跃' },
    { title: '用户数', value: overview.total_users, icon: <TeamOutlined />, color: '#f59e0b', sub: '注册用户' },
  ] : []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* System Overview Stats */}
      {overviewLoading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : overview ? (
        <Row gutter={[16, 16]}>
          {statCards.map((item, i) => (
            <Col xs={12} sm={12} md={6} key={i}>
              <div className="glass-card animate-fadeInUp" style={{ padding: '20px 24px', animationDelay: `${i * 0.1}s` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <Text style={{ color: 'var(--text-muted)', fontSize: 13, display: 'block' }}>{item.title}</Text>
                    <div style={{ fontSize: 32, fontWeight: 700, color: item.color, marginTop: 4, lineHeight: 1.2 }}>
                      {item.value}
                    </div>
                    <Text style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 4, display: 'block' }}>{item.sub}</Text>
                  </div>
                  <div style={{
                    width: 44, height: 44, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: `${item.color}15`, fontSize: 20, color: item.color,
                  }}>
                    {item.icon}
                  </div>
                </div>
              </div>
            </Col>
          ))}
        </Row>
      ) : null}

      {/* Charts Row(需管理员权限, 无权限时隐藏) */}
      {trend !== null && (
        <Row gutter={[16, 16]}>
          <Col xs={24} md={16}>
            <div className="glass-card" style={{ padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <LineChartOutlined style={{ color: 'var(--primary-light)' }} />
                <Text style={{ color: 'var(--text-primary)', fontWeight: 600 }}>查询趋势（近 14 天）</Text>
              </div>
              {(trend || []).length === 0 ? (
                <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
                  暂无查询数据, 去智能问数页提第一个问题吧
                </div>
              ) : (
                <ReactECharts option={getQueryTrendOption()} style={{ height: 240 }} />
              )}
            </div>
          </Col>
          <Col xs={24} md={8}>
            <div className="glass-card" style={{ padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <PieChartOutlined style={{ color: 'var(--primary-light)' }} />
                <Text style={{ color: 'var(--text-primary)', fontWeight: 600 }}>数据源查询分布</Text>
              </div>
              <ReactECharts option={getDatasourceTypeOption()} style={{ height: 240 }} />
            </div>
          </Col>
        </Row>
      )}

      {/* Dashboard List */}
      <Card
        title={<Space><DashboardOutlined /><span>数据看板</span></Space>}
        extra={
          <Button className="glow-btn" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>
            新建看板
          </Button>
        }
      >
        {dashboards.length === 0 ? (
          <Empty description="暂无看板，点击右上方按钮创建第一个数据看板" />
        ) : (
          <Row gutter={[16, 16]}>
            {dashboards.map((ds: any) => (
              <Col xs={24} sm={12} md={8} key={ds.id}>
                <div className="glass-card" style={{ padding: 20, cursor: 'pointer', transition: 'all 0.2s' }}
                  onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(99,102,241,0.4)'}
                  onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-glass)'}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <Title level={5} style={{ color: 'var(--text-primary)', margin: 0 }}>{ds.name}</Title>
                      <Text style={{ color: 'var(--text-muted)', fontSize: 12, display: 'block', marginTop: 4 }}>
                        {ds.description || '暂无描述'}
                      </Text>
                    </div>
                    <Tag color={ds.is_public ? 'blue' : 'default'} style={{ borderRadius: 6 }}>
                      {ds.is_public ? '公开' : '私有'}
                    </Tag>
                  </div>
                  <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                    <Button size="small" icon={<EyeOutlined />}>查看</Button>
                    <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(ds.id)}>删除</Button>
                  </div>
                </div>
              </Col>
            ))}
          </Row>
        )}
      </Card>

      {/* Create Modal */}
      <Modal title="新建看板" open={createModalVisible} onCancel={() => setCreateModalVisible(false)}
        onOk={() => form.submit()} destroyOnClose>
        <Form form={form} onFinish={handleCreate} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="看板名称" rules={[{ required: true }]}><Input placeholder="例如：销售数据看板" /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={3} placeholder="看板描述（可选）" /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Dashboard
