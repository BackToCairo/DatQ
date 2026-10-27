import React, { useState, useEffect } from 'react'
import {
  Card, Tabs, Table, Empty, Tag, Button, Space, Typography, Row, Col,
  Modal, Form, Input, Select, message, Popconfirm, Tooltip, Badge, Alert, Spin,
} from 'antd'
import {
  PlusOutlined, TeamOutlined, FileSearchOutlined, HistoryOutlined,
  DashboardOutlined, SettingOutlined, EditOutlined, DeleteOutlined,
  CheckCircleOutlined, CloseCircleOutlined, UserOutlined, ReloadOutlined,
  UserSwitchOutlined, StopOutlined, PlayCircleOutlined, ApiOutlined,
} from '@ant-design/icons'
import { dashboardApi, adminApi } from '../services/api'
import type { LlmSettings, LlmSettingsPayload, LlmProbeResult } from '../services/api'

const { Text, Title } = Typography

const Admin: React.FC = () => {
  const [activeTab, setActiveTab] = useState('overview')

  // 系统概览
  const [overview, setOverview] = useState<any>(null)
  const [overviewLoading, setOverviewLoading] = useState(false)

  // 用户管理
  const [users, setUsers] = useState<any[]>([])
  const [userTotal, setUserTotal] = useState(0)
  const [userPage, setUserPage] = useState(1)
  const [userSearch, setUserSearch] = useState('')
  const [usersLoading, setUsersLoading] = useState(false)
  const [roles, setRoles] = useState<any[]>([])

  // 用户弹窗
  const [userModal, setUserModal] = useState(false)
  const [editingUser, setEditingUser] = useState<any>(null)
  const [userForm] = Form.useForm()
  const [roleModal, setRoleModal] = useState(false)
  const [roleUser, setRoleUser] = useState<any>(null)
  const [roleForm] = Form.useForm()

  // 审计日志
  const [queryLogs, setQueryLogs] = useState<any[]>([])
  const [queryLogTotal, setQueryLogTotal] = useState(0)
  const [queryLogPage, setQueryLogPage] = useState(1)
  const [queryLogStatus, setQueryLogStatus] = useState<string | undefined>()
  const [queryLogsLoading, setQueryLogsLoading] = useState(false)

  const [opLogs, setOpLogs] = useState<any[]>([])
  const [opLogTotal, setOpLogTotal] = useState(0)
  const [opLogPage, setOpLogPage] = useState(1)
  const [opLogsLoading, setOpLogsLoading] = useState(false)

  // 大模型设置：仅在当前表单内暂存新密钥，不写入浏览器存储。
  const [llmForm] = Form.useForm<LlmSettingsPayload>()
  const [llmSettings, setLlmSettings] = useState<LlmSettings | null>(null)
  const [llmLoading, setLlmLoading] = useState(false)
  const [llmSaving, setLlmSaving] = useState(false)
  const [llmTesting, setLlmTesting] = useState(false)
  const [llmProbe, setLlmProbe] = useState<LlmProbeResult | null>(null)
  const llmBusy = llmLoading || llmSaving || llmTesting

  useEffect(() => { loadOverview() }, [])
  useEffect(() => {
    if (activeTab === 'users') { loadUsers(1); loadRoles() }
    if (activeTab === 'query-logs') loadQueryLogs(1)
    if (activeTab === 'op-logs') loadOpLogs(1)
    if (activeTab === 'settings') loadLlmSettings()
    else { llmForm.setFieldValue('api_key', ''); setLlmProbe(null) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab])

  const loadOverview = async () => {
    setOverviewLoading(true)
    try {
      const res: any = await dashboardApi.systemOverview()
      if (res.code === 0) setOverview(res.data)
    } catch (e) { /* ignore */ }
    setOverviewLoading(false)
  }

  // ========== 大模型配置 ==========
  const applyLlmSettings = (data: LlmSettings) => {
    setLlmSettings(data)
    llmForm.setFieldsValue({ base_url: data.base_url || '', model: data.model, api_key: '' })
  }

  const loadLlmSettings = async () => {
    setLlmLoading(true)
    setLlmProbe(null)
    try {
      const res = await adminApi.getLlmSettings()
      if (res.code === 0) applyLlmSettings(res.data)
      else message.error(res.message || '读取配置失败')
    } catch { /* 全局拦截器处理 HTTP 错误 */ }
    finally { setLlmLoading(false) }
  }

  const handleLlmSave = async (values: LlmSettingsPayload) => {
    setLlmSaving(true)
    setLlmProbe(null)
    try {
      const res = await adminApi.saveLlmSettings(values)
      if (res.code === 0) {
        applyLlmSettings(res.data)
        message.success(res.message || '配置已保存')
      } else message.error(res.message || '保存失败')
    } catch { /* 全局拦截器处理 HTTP 错误 */ }
    finally { setLlmSaving(false) }
  }

  const handleLlmTest = async () => {
    let values: LlmSettingsPayload
    try { values = await llmForm.validateFields() } catch { return }
    setLlmTesting(true)
    setLlmProbe(null)
    try {
      const res = await adminApi.testLlmSettings(values)
      const success = res.code === 0 && res.data?.success === true
      setLlmProbe({ success, message: res.data?.message || res.message || '测试失败', latency_ms: res.data?.latency_ms || 0 })
      if (success) message.success('连接成功，配置尚未保存')
    } catch { /* 全局拦截器处理 HTTP 错误，不输出含密钥的请求对象 */ }
    finally { setLlmTesting(false) }
  }

  const handleClearLlmKey = async () => {
    // 清除仅针对已保存配置，不将未保存的地址、模型或密钥一并提交。
    if (!llmSettings) return
    await handleLlmSave({ base_url: llmSettings.base_url, model: llmSettings.model, clear_api_key: true })
  }

  // ========== 用户管理 ==========
  const loadUsers = async (page: number, search: string = userSearch) => {
    setUsersLoading(true)
    try {
      const res: any = await adminApi.listUsers({ page, page_size: 10, search: search || undefined })
      if (res.code === 0) {
        setUsers(res.data.items || [])
        setUserTotal(res.data.total || 0)
        setUserPage(page)
      }
    } catch (e) { /* ignore */ }
    setUsersLoading(false)
  }

  const loadRoles = async () => {
    try {
      const res: any = await adminApi.listRoles()
      if (res.code === 0) setRoles(res.data || [])
    } catch (e) { /* ignore */ }
  }

  const openUserModal = (user?: any) => {
    setEditingUser(user || null)
    if (user) {
      userForm.setFieldsValue({ username: user.username, email: user.email, display_name: user.display_name, phone: user.phone })
    } else {
      userForm.resetFields()
    }
    setUserModal(true)
  }

  const handleUserSubmit = async (values: any) => {
    try {
      if (editingUser) {
        await adminApi.updateUser(editingUser.id, {
          display_name: values.display_name, phone: values.phone, email: values.email,
        })
        message.success('用户已更新')
      } else {
        await adminApi.createUser(values)
        message.success('用户已创建')
      }
      setUserModal(false)
      loadUsers(userPage)
    } catch (e) { /* ignore */ }
  }

  const handleToggleStatus = async (user: any) => {
    const next = user.status === 'active' ? 'disabled' : 'active'
    try {
      await adminApi.updateUserStatus(user.id, next)
      message.success(next === 'active' ? '已启用' : '已禁用')
      loadUsers(userPage)
    } catch (e) { /* ignore */ }
  }

  const openRoleModal = (user: any) => {
    setRoleUser(user)
    roleForm.setFieldsValue({ role_ids: (user.roles || []).map((r: any) => r.id) })
    setRoleModal(true)
  }

  const handleAssignRoles = async (values: any) => {
    try {
      await adminApi.assignRoles(roleUser.id, values.role_ids || [])
      message.success('角色已更新')
      setRoleModal(false)
      loadUsers(userPage)
    } catch (e) { /* ignore */ }
  }

  // ========== 审计日志 ==========
  const loadQueryLogs = async (page: number) => {
    setQueryLogsLoading(true)
    try {
      const res: any = await adminApi.listQueryLogs({ page, page_size: 10, status: queryLogStatus })
      if (res.code === 0) {
        setQueryLogs(res.data.items || [])
        setQueryLogTotal(res.data.total || 0)
        setQueryLogPage(page)
      }
    } catch (e) { /* ignore */ }
    setQueryLogsLoading(false)
  }

  const loadOpLogs = async (page: number) => {
    setOpLogsLoading(true)
    try {
      const res: any = await adminApi.listOperationLogs({ page, page_size: 10 })
      if (res.code === 0) {
        setOpLogs(res.data.items || [])
        setOpLogTotal(res.data.total || 0)
        setOpLogPage(page)
      }
    } catch (e) { /* ignore */ }
    setOpLogsLoading(false)
  }

  // ========== 列定义 ==========
  const userColumns = [
    {
      title: '用户', dataIndex: 'username', key: 'username',
      render: (name: string, record: any) => (
        <Space>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(99,102,241,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <UserOutlined style={{ color: 'var(--primary-light)', fontSize: 14 }} />
          </div>
          <div>
            <Text style={{ color: 'var(--text-primary)', display: 'block', fontSize: 13 }}>{record.display_name || name}</Text>
            <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>@{name}</Text>
          </div>
        </Space>
      )
    },
    { title: '邮箱', dataIndex: 'email', key: 'email', render: (e: string) => <Text style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{e}</Text> },
    {
      title: '角色', dataIndex: 'roles', key: 'roles',
      render: (roles: any[]) => (roles || []).map(r => (
        <Tag key={r.id} color="blue" style={{ borderRadius: 6, fontSize: 11 }}>{r.display_name || r.name}</Tag>
      ))
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => (
        <Tag color={s === 'active' ? 'success' : 'error'} style={{ borderRadius: 6 }}>
          {s === 'active' ? '正常' : '禁用'}
        </Tag>
      )
    },
    {
      title: '注册时间', dataIndex: 'created_at', key: 'created_at',
      render: (t: string) => <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{t ? new Date(t).toLocaleDateString() : '-'}</Text>
    },
    {
      title: '操作', key: 'action', width: 200,
      render: (_: any, record: any) => (
        <Space>
          <Tooltip title="编辑"><Button size="small" icon={<EditOutlined />} onClick={() => openUserModal(record)} /></Tooltip>
          <Tooltip title="分配角色"><Button size="small" icon={<UserSwitchOutlined />} onClick={() => openRoleModal(record)} /></Tooltip>
          {record.status === 'active' ? (
            <Popconfirm title="确认禁用该用户?">
              <Button size="small" danger icon={<StopOutlined />} onClick={() => handleToggleStatus(record)} />
            </Popconfirm>
          ) : (
            <Popconfirm title="确认启用该用户?">
              <Button size="small" icon={<PlayCircleOutlined />} onClick={() => handleToggleStatus(record)} />
            </Popconfirm>
          )}
        </Space>
      )
    },
  ]

  const queryLogColumns = [
    {
      title: '问题', dataIndex: 'question', key: 'question', width: 220,
      render: (q: string) => <Text style={{ color: 'var(--text-primary)', fontSize: 13 }}>{q}</Text>
    },
    {
      title: 'SQL', dataIndex: 'sql', key: 'sql',
      render: (sql: string) => (
        <Tooltip title={sql} placement="topLeft">
          <Text style={{ color: 'var(--text-secondary)', fontFamily: 'monospace', fontSize: 11 }} ellipsis={{ symbol: '...' }}>{sql || '-'}</Text>
        </Tooltip>
      )
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string) => (
        <Tag icon={s === 'success' ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
          color={s === 'success' ? 'success' : 'error'} style={{ borderRadius: 6 }}>
          {s === 'success' ? '成功' : '失败'}
        </Tag>
      )
    },
    {
      title: '耗时', dataIndex: 'execution_time', key: 'execution_time', width: 90,
      render: (t: any) => <Text style={{ color: (t || 0) > 2000 ? 'var(--warning)' : 'var(--text-muted)', fontSize: 12 }}>{t != null ? `${t}ms` : '-'}</Text>
    },
    {
      title: '行数', dataIndex: 'row_count', key: 'row_count', width: 60,
      render: (c: any) => <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{c ?? '-'}</Text>
    },
    {
      title: '时间', dataIndex: 'created_at', key: 'created_at', width: 150,
      render: (t: string) => <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>{t ? new Date(t).toLocaleString() : '-'}</Text>
    },
  ]

  const opLogColumns = [
    { title: '用户', dataIndex: 'username', key: 'username', width: 120,
      render: (u: string) => <Text style={{ color: 'var(--text-primary)', fontSize: 13 }}>@{u || '-'}</Text> },
    { title: '动作', dataIndex: 'action', key: 'action', width: 110,
      render: (a: string) => <Tag color="geekblue" style={{ borderRadius: 6, fontSize: 11 }}>{a}</Tag> },
    { title: '资源类型', dataIndex: 'resource_type', key: 'resource_type', width: 100,
      render: (r: string) => <Text style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{r || '-'}</Text> },
    { title: '资源ID', dataIndex: 'resource_id', key: 'resource_id', width: 180, ellipsis: true,
      render: (r: string) => <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>{r || '-'}</Text> },
    { title: '详情', dataIndex: 'detail', key: 'detail', ellipsis: true,
      render: (d: any) => (
        <Tooltip title={d ? JSON.stringify(d) : ''}>
          <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{d ? JSON.stringify(d) : '-'}</Text>
        </Tooltip>
      ) },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 150,
      render: (t: string) => <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>{t ? new Date(t).toLocaleString() : '-'}</Text> },
  ]

  const tabItems = [
    {
      key: 'overview',
      label: <span><DashboardOutlined /> 系统概览</span>,
      children: overview ? (
        <div>
          <Row gutter={[16, 16]}>
            {[
              { label: '总用户数', value: overview.total_users, color: '#818cf8' },
              { label: '数据源总数', value: overview.total_datasources, color: '#06b6d4' },
              { label: '在线数据源', value: overview.active_datasources, color: '#10b981' },
              { label: '总对话数', value: overview.total_conversations, color: '#f59e0b' },
              { label: '今日查询', value: overview.total_queries_today, color: '#ef4444' },
            ].map((item, i) => (
              <Col xs={12} md={8} lg={4} key={i}>
                <div className="glass-card" style={{ padding: '16px 20px', textAlign: 'center' }}>
                  <div style={{ fontSize: 28, fontWeight: 700, color: item.color }}>{item.value}</div>
                  <Text style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4, display: 'block' }}>{item.label}</Text>
                </div>
              </Col>
            ))}
          </Row>
          <div className="glass-card" style={{ padding: 24, marginTop: 16 }}>
            <Title level={5} style={{ color: 'var(--text-primary)' }}>系统信息</Title>
            <Row gutter={[24, 12]}>
              {[
                ['系统版本', 'v1.0.0'],
                ['运行环境', 'Development'],
                ['数据库', 'PostgreSQL 16'],
                ['向量库', 'ChromaDB (内嵌)'],
                ['LLM', 'OpenAI 兼容 (未配置Key时降级)'],
                ['SQL校验', 'sqlglot'],
              ].map(([label, value], i) => (
                <Col xs={12} md={8} key={i}>
                  <Space>
                    <Text style={{ color: 'var(--text-muted)', fontSize: 13 }}>{label}:</Text>
                    <Tag style={{ borderRadius: 6 }}>{value}</Tag>
                  </Space>
                </Col>
              ))}
            </Row>
          </div>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
          {overviewLoading ? '加载中...' : '加载系统信息失败'}
        </div>
      ),
    },
    {
      key: 'users',
      label: <span><TeamOutlined /> 用户管理</span>,
      children: (
        <div>
          <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
            <Space>
              <Input.Search
                placeholder="搜索用户名/邮箱/昵称"
                allowClear style={{ width: 280 }}
                onSearch={(v) => { setUserSearch(v); loadUsers(1, v) }}
              />
              <Select
                placeholder="分配角色视图" allowClear style={{ width: 140 }} disabled
              />
            </Space>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => loadUsers(userPage)} />
              <Button className="glow-btn" icon={<PlusOutlined />} onClick={() => openUserModal()}>新增用户</Button>
            </Space>
          </div>
          <Table
            dataSource={users} columns={userColumns} rowKey="id" loading={usersLoading}
            pagination={{
              current: userPage, pageSize: 10, total: userTotal,
              onChange: (p) => loadUsers(p), showTotal: (t) => `共 ${t} 个用户`,
            }}
          />
        </div>
      ),
    },
    {
      key: 'query-logs',
      label: <span><FileSearchOutlined /> 查询日志</span>,
      children: (
        <div>
          <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
            <Select
              placeholder="按状态筛选" allowClear style={{ width: 140 }}
              value={queryLogStatus}
              onChange={(v) => { setQueryLogStatus(v); setTimeout(() => loadQueryLogs(1), 0) }}
              options={[
                { value: 'success', label: '成功' },
                { value: 'failed', label: '失败' },
                { value: 'pending', label: '执行中' },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadQueryLogs(queryLogPage)} />
          </div>
          <Table
            dataSource={queryLogs} columns={queryLogColumns} rowKey="id" loading={queryLogsLoading}
            pagination={{
              current: queryLogPage, pageSize: 10, total: queryLogTotal,
              onChange: (p) => loadQueryLogs(p), showTotal: (t) => `共 ${t} 条`,
            }}
          />
        </div>
      ),
    },
    {
      key: 'op-logs',
      label: <span><HistoryOutlined /> 操作日志</span>,
      children: (
        <div>
          <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
            <Button icon={<ReloadOutlined />} onClick={() => loadOpLogs(opLogPage)} />
          </div>
          <Table
            dataSource={opLogs} columns={opLogColumns} rowKey="id" loading={opLogsLoading}
            pagination={{
              current: opLogPage, pageSize: 10, total: opLogTotal,
              onChange: (p) => loadOpLogs(p), showTotal: (t) => `共 ${t} 条`,
            }}
          />
        </div>
      ),
    },
    {
      key: 'settings',
      label: <span><SettingOutlined /> 系统设置</span>,
      forceRender: true,
      children: (
        <div>
          <div className="glass-card" style={{ padding: 24, marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <Title level={5} style={{ color: 'var(--text-primary)', margin: 0 }}>LLM 配置</Title>
              <Button icon={<ReloadOutlined />} disabled={llmBusy} onClick={loadLlmSettings}>读取已保存配置</Button>
            </div>
            <Space wrap style={{ marginBottom: 16 }}>
              <Tag color="blue">OpenAI 兼容</Tag>
              {llmSettings && <>
                <Tag color={llmSettings.has_api_key && llmSettings.key_readable ? 'green' : 'orange'}>
                  {!llmSettings.key_readable ? '密钥无法解密' : llmSettings.has_api_key ? '已配置密钥（不代表连接已验证）' : '未配置密钥，问数使用知识库降级'}
                </Tag>
                <Tag>{llmSettings.source === 'database' ? '管理员配置' : '环境变量配置'}</Tag>
                {llmSettings.updated_at && <Text type="secondary" style={{ fontSize: 12 }}>
                  更新于 {new Date(llmSettings.updated_at + 'Z').toLocaleString()}
                </Text>}
              </>}
            </Space>
            {llmSettings?.configuration_error && <Alert type="error" showIcon message={llmSettings.configuration_error} style={{ marginBottom: 16 }} />}
            <Spin spinning={llmLoading}>
              <Form form={llmForm} layout="vertical" onFinish={handleLlmSave}
                onValuesChange={() => setLlmProbe(null)} disabled={llmBusy || !llmSettings}>
                <Form.Item name="base_url" label="API 地址"
                  extra="填写 OpenAI 兼容 API 的基础地址，通常包含 /v1；留空使用 https://api.openai.com/v1。"
                  rules={[{ max: 2048, message: '地址最多 2048 个字符' }, { validator: (_, value) => {
                    if (!value?.trim()) return Promise.resolve()
                    try {
                      const url = new URL(value.trim())
                      if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password
                        || value.includes('?') || value.includes('#') || /[\s\\]/.test(value.trim())) throw new Error()
                      return Promise.resolve()
                    } catch { return Promise.reject(new Error('请输入 HTTP/HTTPS 地址，不能包含账号密码、查询参数或片段')) }
                  } }]}>
                  <Input placeholder="https://api.example.com/v1" autoComplete="off" maxLength={2048} />
                </Form.Item>
                <Row gutter={24}>
                  <Col xs={24} md={12}>
                    <Form.Item name="model" label="模型名称" rules={[{ required: true, whitespace: true, message: '请输入模型名称' }, { max: 128, message: '模型名最多 128 个字符' }]}>
                      <Input placeholder="例如 gpt-4o、deepseek-chat" maxLength={128} autoComplete="off" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="api_key" label="API Key" extra={llmSettings?.has_api_key ? '留空保留当前密钥，填写新密钥可替换；已保存密钥不会回传。' : '请输入供应商提供的 API Key；密钥加密保存，不写入浏览器存储。'}>
                      <Input.Password placeholder={llmSettings?.has_api_key ? '已配置（留空不修改）' : '输入 API Key'} autoComplete="new-password" maxLength={4096} />
                    </Form.Item>
                  </Col>
                </Row>
                {llmProbe && <Alert type={llmProbe.success ? 'success' : 'error'} showIcon
                  message={llmProbe.message} description={`耗时 ${llmProbe.latency_ms}ms。测试不会保存配置。`} style={{ marginBottom: 16 }} />}
                <Space wrap>
                  <Button icon={<ApiOutlined />} loading={llmTesting} onClick={handleLlmTest}>测试连接</Button>
                  <Button type="primary" htmlType="submit" loading={llmSaving}>保存配置</Button>
                  <Popconfirm title="确认清除全系统 API Key？"
                    description="清除后不会回退环境变量密钥；未保存的表单内容会被舍弃。"
                    onConfirm={handleClearLlmKey} disabled={llmBusy || !llmSettings?.has_api_key}>
                    <Button danger disabled={llmBusy || !llmSettings?.has_api_key}>清除 API Key</Button>
                  </Popconfirm>
                </Space>
              </Form>
            </Spin>
            <Text type="secondary" style={{ display: 'block', marginTop: 16, fontSize: 12 }}>
              管理员统一配置供全系统聊天和问数使用，保存后无需重启。测试会发起一次少量 tokens 的请求，可能产生费用。
              本配置不修改 Embedding 模型或现有知识库索引。
            </Text>
          </div>
          <div className="glass-card" style={{ padding: 24 }}>
            <Title level={5} style={{ color: 'var(--text-primary)' }}>安全策略</Title>
            <Row gutter={[24, 12]}>
              {[
                ['SQL安全校验', '已启用 (sqlglot)'],
                ['只读查询', '仅允许SELECT'],
                ['查询行数限制', '1000行'],
                ['查询超时', '30秒'],
                ['频率限制', '10次/分钟'],
                ['行/列权限', '支持 (按角色)'],
              ].map(([label, value], i) => (
                <Col xs={12} md={8} key={i}>
                  <Space>
                    <Text style={{ color: 'var(--text-muted)', fontSize: 13 }}>{label}:</Text>
                    <Tag color="green" style={{ borderRadius: 6 }}>{value}</Tag>
                  </Space>
                </Col>
              ))}
            </Row>
          </div>
        </div>
      ),
    },
  ]

  return (
    <Card title={<Space><SettingOutlined /><span>系统管理</span></Space>}>
      <Tabs items={tabItems} activeKey={activeTab} onChange={setActiveTab} />

      {/* 新增/编辑用户 */}
      <Modal
        title={editingUser ? '编辑用户' : '新增用户'}
        open={userModal} onCancel={() => setUserModal(false)}
        onOk={() => userForm.submit()} destroyOnClose
      >
        <Form form={userForm} layout="vertical" onFinish={handleUserSubmit} style={{ marginTop: 12 }}>
          <Form.Item name="username" label="用户名" rules={[{ required: !editingUser }]}>
            <Input disabled={!!editingUser} placeholder="登录用户名" />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ required: !editingUser, type: 'email' }]}>
            <Input placeholder="user@example.com" />
          </Form.Item>
          {!editingUser && (
            <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 6, message: '密码至少6位' }]}>
              <Input.Password placeholder="至少6位" />
            </Form.Item>
          )}
          <Form.Item name="display_name" label="显示名称">
            <Input placeholder="昵称(可选)" />
          </Form.Item>
          <Form.Item name="phone" label="手机号">
            <Input placeholder="手机号(可选)" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 分配角色 */}
      <Modal
        title={`分配角色: ${roleUser?.display_name || roleUser?.username || ''}`}
        open={roleModal} onCancel={() => setRoleModal(false)}
        onOk={() => roleForm.submit()} destroyOnClose
      >
        <Form form={roleForm} layout="vertical" onFinish={handleAssignRoles} style={{ marginTop: 12 }}>
          <Form.Item name="role_ids" label="角色(可多选)">
            <Select
              mode="multiple" placeholder="选择角色"
              options={roles.map(r => ({ value: r.id, label: r.display_name || r.name }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}

export default Admin
