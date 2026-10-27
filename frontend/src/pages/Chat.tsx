import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Input, Button, Table, Tag, Space, Typography, Empty, Tooltip, Select, Divider, Dropdown } from 'antd'
import {
  SendOutlined, PlusOutlined, MessageOutlined, DeleteOutlined,
  BarChartOutlined, TableOutlined, CodeOutlined, CopyOutlined,
  LikeOutlined, DislikeOutlined, ThunderboltOutlined, DownOutlined,
  RobotOutlined, UserOutlined, ClockCircleOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { conversationApi, queryApi, datasourceApi } from '../services/api'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const { Text, Paragraph } = Typography
const { TextArea } = Input

interface ChartConfig {
  type: 'line' | 'bar' | 'pie' | 'table'
  xField?: string
  yField?: string
  angleField?: string
  colorField?: string
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sql?: string
  data?: any[]
  columns?: any[]
  chart?: ChartConfig
  loading?: boolean
  executionTime?: number
  rowCount?: number
  queryId?: string
  error?: string
}

const Chat: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [conversations, setConversations] = useState<any[]>([])
  const [currentConvId, setCurrentConvId] = useState<string | null>(null)
  const [datasources, setDatasources] = useState<any[]>([])
  const [selectedDsId, setSelectedDsId] = useState<string | undefined>()
  const [sqlExpanded, setSqlExpanded] = useState<Record<string, boolean>>({})
  const [viewMode, setViewMode] = useState<Record<string, 'chart' | 'table'>>({})
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<any>(null)

  useEffect(() => {
    loadConversations()
    loadDatasources()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadConversations = async () => {
    try {
      const res: any = await conversationApi.list()
      if (res.code === 0) setConversations(res.data || [])
    } catch (e) { /* ignore */ }
  }

  const loadDatasources = async () => {
    try {
      const res: any = await datasourceApi.list()
      if (res.code === 0) setDatasources(res.data || [])
    } catch (e) { /* ignore */ }
  }

  const handleSend = async () => {
    if (!inputValue.trim() || loading) return
    const question = inputValue.trim()
    setInputValue('')

    const userMsgId = Date.now().toString()
    setMessages((prev: Message[]) => [...prev, { id: userMsgId, role: 'user', content: question }])
    setLoading(true)

    const loadingId = (Date.now() + 1).toString()
    setMessages((prev: Message[]) => [...prev, { id: loadingId, role: 'assistant', content: '', loading: true }])

    try {
      const res: any = await queryApi.ask({
        question,
        conversation_id: currentConvId || undefined,
        datasource_id: selectedDsId || undefined,
      })

      if (res.code === 0) {
        const d = res.data
        if (!currentConvId && d.conversation_id) {
          setCurrentConvId(d.conversation_id)
          loadConversations()
        }
        setMessages((prev: Message[]) => prev.map((m: Message) =>
          m.id === loadingId ? {
            ...m,
            content: d.answer || '查询完成',
            sql: d.sql,
            data: d.data,
            columns: d.columns,
            chart: d.chart,
            loading: false,
            executionTime: d.execution_time,
            rowCount: d.row_count,
            queryId: d.query_id,
            error: d.error,
          } : m
        ))
      }
    } catch (err: any) {
      setMessages((prev: Message[]) => prev.map((m: Message) =>
        m.id === loadingId ? {
          ...m,
          content: '查询遇到问题，请稍后重试。',
          loading: false,
          error: err?.response?.data?.detail?.message || '网络错误',
        } : m
      ))
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const handleNewChat = () => {
    setMessages([])
    setCurrentConvId(null)
    setInputValue('')
  }

  const handleCopySql = (sql: string) => {
    navigator.clipboard.writeText(sql)
  }

  const handleFeedback = async (queryId: string, feedback: 'good' | 'bad') => {
    try {
      await queryApi.feedback(queryId, feedback)
    } catch (e) { /* ignore */ }
  }

  const getChartOption = (chart: ChartConfig, data: any[]): any => {
    if (!chart || chart.type === 'table' || !data?.length) return null

    if (chart.type === 'line') {
      return {
        tooltip: { trigger: 'axis' },
        grid: { left: 40, right: 20, top: 20, bottom: 30 },
        xAxis: { type: 'category', data: data.map(d => d[chart.xField || '']), axisLabel: { color: '#94a3b8', fontSize: 11 } },
        yAxis: { type: 'value', axisLabel: { color: '#94a3b8', fontSize: 11 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
        series: [{ type: 'line', data: data.map(d => d[chart.yField || '']), smooth: true, areaStyle: { opacity: 0.15 }, lineStyle: { width: 2 }, itemStyle: { color: '#818cf8' } }],
      }
    }
    if (chart.type === 'bar') {
      return {
        tooltip: { trigger: 'axis' },
        grid: { left: 40, right: 20, top: 20, bottom: 30 },
        xAxis: { type: 'category', data: data.map(d => d[chart.xField || '']), axisLabel: { color: '#94a3b8', fontSize: 11 } },
        yAxis: { type: 'value', axisLabel: { color: '#94a3b8', fontSize: 11 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
        series: [{ type: 'bar', data: data.map(d => d[chart.yField || '']), barMaxWidth: 40, itemStyle: { color: '#818cf8', borderRadius: [4, 4, 0, 0] } }],
      }
    }
    if (chart.type === 'pie') {
      return {
        tooltip: { trigger: 'item' },
        series: [{
          type: 'pie', radius: ['40%', '70%'], center: ['50%', '50%'],
          data: data.map(d => ({ name: d[chart.colorField || ''], value: d[chart.angleField || ''] })),
          label: { color: '#94a3b8', fontSize: 11 },
          itemStyle: { borderColor: '#1a1a3e', borderWidth: 2 },
        }],
      }
    }
    return null
  }

  const suggestedQuestions = [
    { icon: '📊', text: '上个月各区域销售额排名' },
    { icon: '📈', text: '近30天GMV趋势变化' },
    { icon: '🏆', text: '各产品线TOP10商品' },
    { icon: '🔍', text: '本季度各品类营收占比' },
  ]

  return (
    <div style={{ display: 'flex', gap: 16, height: '100%' }}>
      {/* Conversation sidebar */}
      <div className="glass-card" style={{ width: 260, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '16px 12px 8px' }}>
          <Button className="glow-btn" icon={<PlusOutlined />} block onClick={handleNewChat}
            style={{ height: 40, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            新建对话
          </Button>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: '4px 8px 8px' }}>
          {conversations.map(conv => (
            <div key={conv.id}
              className="animate-fadeInUp"
              style={{
                padding: '10px 14px', cursor: 'pointer', borderRadius: 10, marginBottom: 4,
                background: currentConvId === conv.id ? 'rgba(99,102,241,0.15)' : 'transparent',
                border: currentConvId === conv.id ? '1px solid rgba(99,102,241,0.3)' : '1px solid transparent',
                transition: 'all 0.2s',
              }}
              onClick={() => setCurrentConvId(conv.id)}
              onMouseEnter={e => { if (currentConvId !== conv.id) (e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.03)' }}
              onMouseLeave={e => { if (currentConvId !== conv.id) (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <MessageOutlined style={{ color: 'var(--primary-light)', fontSize: 14 }} />
                <Text style={{ color: 'var(--text-primary)', fontSize: 13, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {conv.title || '未命名对话'}
                </Text>
              </div>
              <div style={{ marginTop: 4, paddingLeft: 22 }}>
                <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                  {dayjs(conv.last_active_at).fromNow()} · {conv.message_count}条消息
                </Text>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className="glass-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--border-glass)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <RobotOutlined style={{ fontSize: 20, color: 'var(--primary-light)' }} />
            <Text style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: 15 }}>智能问数</Text>
          </div>
          <Select
            placeholder="选择数据源"
            allowClear
            style={{ width: 200 }}
            value={selectedDsId}
            onChange={setSelectedDsId}
            options={datasources.map(ds => ({ value: ds.id, label: ds.name }))}
            suffixIcon={<DownOutlined style={{ color: 'var(--text-muted)' }} />}
          />
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflow: 'auto', padding: '20px' }}>
          {messages.length === 0 ? (
            <div style={{ textAlign: 'center', paddingTop: 60 }}>
              <div style={{ marginBottom: 32 }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>🤖</div>
                <Text style={{ color: 'var(--text-primary)', fontSize: 20, fontWeight: 600, display: 'block' }}>
                  你好，我是智能问数助手
                </Text>
                <Text style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 8, display: 'block' }}>
                  输入自然语言问题，我来帮你查询和分析数据
                </Text>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, maxWidth: 500, margin: '0 auto' }}>
                {suggestedQuestions.map((q, i) => (
                  <div key={i}
                    className="glass-card animate-fadeInUp"
                    style={{ padding: '14px 18px', cursor: 'pointer', textAlign: 'left', transition: 'all 0.2s', animationDelay: `${i * 0.1}s` }}
                    onClick={() => setInputValue(q.text)}
                    onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(99,102,241,0.4)'}
                    onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-glass)'}
                  >
                    <span style={{ fontSize: 20, marginRight: 8 }}>{q.icon}</span>
                    <Text style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{q.text}</Text>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div>
              {messages.map((msg, idx) => (
                <div key={msg.id} className={`animate-fadeInUp ${msg.role === 'user' ? '' : ''}`}
                  style={{ marginBottom: 20, display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start', animationDelay: '0.05s' }}>
                  
                  {/* Avatar */}
                  <div style={{
                    width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: msg.role === 'user' ? 'rgba(99,102,241,0.2)' : 'rgba(6,182,212,0.2)',
                    marginRight: msg.role === 'user' ? 0 : 12,
                    marginLeft: msg.role === 'user' ? 12 : 0,
                    order: msg.role === 'user' ? 1 : 0,
                  }}>
                    {msg.role === 'user' ? <UserOutlined style={{ color: 'var(--primary-light)' }} /> : <RobotOutlined style={{ color: 'var(--accent)' }} />}
                  </div>

                  {/* Bubble */}
                  <div style={{
                    maxWidth: '75%',
                    padding: '14px 18px',
                    borderRadius: 16,
                    background: msg.role === 'user' ? 'rgba(99,102,241,0.15)' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${msg.role === 'user' ? 'rgba(99,102,241,0.3)' : 'var(--border-glass)'}`,
                    backdropFilter: 'blur(10px)',
                  }}>
                    {msg.loading ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div className="typing-dots">
                          <span></span><span></span><span></span>
                        </div>
                        <Text style={{ color: 'var(--text-muted)', fontSize: 13 }}>正在分析中...</Text>
                      </div>
                    ) : (
                      <>
                        {/* Answer text */}
                        <Paragraph style={{ color: 'var(--text-primary)', fontSize: 14, lineHeight: 1.7, margin: 0, whiteSpace: 'pre-wrap' }}>
                          {msg.content}
                        </Paragraph>

                        {/* Error */}
                        {msg.error && (
                          <Tag color="error" style={{ marginTop: 8, borderRadius: 6 }}>{msg.error}</Tag>
                        )}

                        {/* SQL Block */}
                        {msg.sql && (
                          <div style={{ marginTop: 12, borderRadius: 10, overflow: 'hidden', border: '1px solid var(--border-glass)' }}>
                            <div style={{
                              padding: '8px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                              background: 'rgba(99,102,241,0.08)', borderBottom: '1px solid var(--border-glass)',
                            }}>
                              <Space size={6}>
                                <CodeOutlined style={{ color: 'var(--primary-light)', fontSize: 13 }} />
                                <Text style={{ color: 'var(--primary-light)', fontSize: 12, fontWeight: 600 }}>SQL</Text>
                              </Space>
                              <Space size={4}>
                                <Tooltip title="复制SQL">
                                  <Button type="text" size="small" icon={<CopyOutlined style={{ color: 'var(--text-muted)' }} />}
                                    onClick={() => handleCopySql(msg.sql!)} style={{ background: 'transparent', border: 'none' }} />
                                </Tooltip>
                              </Space>
                            </div>
                            <pre style={{
                              margin: 0, padding: '12px 14px', fontSize: 12, fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                              color: 'var(--text-secondary)', overflow: 'auto', maxHeight: sqlExpanded[msg.id] ? 'none' : 120,
                              background: 'rgba(0,0,0,0.2)',
                            }}>
                              {msg.sql}
                            </pre>
                          </div>
                        )}

                        {/* Data visualization */}
                        {msg.data && msg.data.length > 0 && (
                          <div style={{ marginTop: 12 }}>
                            {/* View toggle */}
                            <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
                              {msg.chart && msg.chart.type !== 'table' && (
                                <Button size="small" type={viewMode[msg.id] !== 'table' ? 'primary' : 'default'}
                                  icon={<BarChartOutlined />}
                                  onClick={() => setViewMode(prev => ({ ...prev, [msg.id]: 'chart' }))}
                                  style={{ borderRadius: 6, fontSize: 12 }}>
                                  图表
                                </Button>
                              )}
                              <Button size="small" type={viewMode[msg.id] === 'table' ? 'primary' : 'default'}
                                icon={<TableOutlined />}
                                onClick={() => setViewMode(prev => ({ ...prev, [msg.id]: 'table' }))}
                                style={{ borderRadius: 6, fontSize: 12 }}>
                                表格
                              </Button>
                            </div>

                            {/* Chart */}
                            {(viewMode[msg.id] !== 'table') && msg.chart && msg.chart.type !== 'table' && getChartOption(msg.chart, msg.data) && (
                              <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid var(--border-glass)', background: 'rgba(0,0,0,0.15)' }}>
                                <ReactECharts option={getChartOption(msg.chart, msg.data)!} style={{ height: 280 }} />
                              </div>
                            )}

                            {/* Table */}
                            {(viewMode[msg.id] === 'table' || !msg.chart || msg.chart.type === 'table') && (
                              <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid var(--border-glass)' }}>
                                <Table
                                  size="small"
                                  dataSource={msg.data}
                                  columns={msg.columns?.map((c: any) => ({
                                    title: c.name,
                                    dataIndex: c.name,
                                    key: c.name,
                                    ellipsis: true,
                                    width: 150,
                                  })) || Object.keys(msg.data[0] || {}).map(k => ({ title: k, dataIndex: k, key: k, ellipsis: true, width: 150 }))}
                                  pagination={msg.data.length > 10 ? { pageSize: 10, size: 'small' } : false}
                                  scroll={{ x: 'max-content', y: 300 }}
                                  style={{ fontSize: 12 }}
                                />
                              </div>
                            )}
                          </div>
                        )}

                        {/* Meta info & feedback */}
                        <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <Space size={12}>
                            {msg.executionTime !== undefined && (
                              <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                                <ClockCircleOutlined style={{ marginRight: 4 }} />
                                {msg.executionTime}ms
                              </Text>
                            )}
                            {msg.rowCount !== undefined && (
                              <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                                {msg.rowCount} 行结果
                              </Text>
                            )}
                          </Space>
                          {msg.queryId && (
                            <Space size={4}>
                              <Tooltip title="有帮助">
                                <Button type="text" size="small" icon={<LikeOutlined style={{ color: 'var(--text-muted)', fontSize: 13 }} />}
                                  onClick={() => handleFeedback(msg.queryId!, 'good')}
                                  style={{ background: 'transparent', border: 'none' }} />
                              </Tooltip>
                              <Tooltip title="需要改进">
                                <Button type="text" size="small" icon={<DislikeOutlined style={{ color: 'var(--text-muted)', fontSize: 13 }} />}
                                  onClick={() => handleFeedback(msg.queryId!, 'bad')}
                                  style={{ background: 'transparent', border: 'none' }} />
                              </Tooltip>
                            </Space>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div style={{ padding: '16px 20px', borderTop: '1px solid var(--border-glass)' }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
            <TextArea
              ref={inputRef}
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              onPressEnter={e => { if (!e.shiftKey) { e.preventDefault(); handleSend() } }}
              placeholder="输入您的问题... (Shift+Enter 换行)"
              autoSize={{ minRows: 1, maxRows: 4 }}
              disabled={loading}
              style={{ borderRadius: 12, resize: 'none', fontSize: 14, lineHeight: 1.6 }}
            />
            <Button
              className="glow-btn"
              icon={<SendOutlined />}
              onClick={handleSend}
              loading={loading}
              style={{ height: 44, width: 44, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
            />
          </div>
          <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {suggestedQuestions.slice(0, 3).map((q, i) => (
              <Tag key={i} style={{
                cursor: 'pointer', borderRadius: 8, padding: '2px 10px', fontSize: 12,
                background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-glass)', color: 'var(--text-muted)',
              }}
                onClick={() => setInputValue(q.text)}>
                {q.icon} {q.text}
              </Tag>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export default Chat
