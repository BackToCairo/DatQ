import React, { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Avatar, Dropdown, Button, Tooltip, Badge } from 'antd'
import {
  MessageOutlined,
  DatabaseOutlined,
  BookOutlined,
  DashboardOutlined,
  AppstoreOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ThunderboltOutlined,
  BellOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '../../stores/authStore'

const { Header, Sider, Content } = Layout

const menuItems = [
  { key: '/chat', icon: <MessageOutlined />, label: '智能问数' },
  { key: '/dashboard', icon: <DashboardOutlined />, label: '数据看板' },
  { key: '/datasource', icon: <DatabaseOutlined />, label: '数据源管理' },
  { key: '/semantic', icon: <AppstoreOutlined />, label: '语义层' },
  { key: '/knowledge', icon: <BookOutlined />, label: '知识库' },
  { key: '/admin', icon: <SettingOutlined />, label: '系统管理' },
]

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()

  const handleMenuClick = (e: { key: string }) => {
    navigate(e.key)
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const userMenuItems = [
    { key: 'profile', icon: <UserOutlined />, label: '个人设置' },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
  ]

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        theme="light"
        width={220}
        style={{
          borderRight: '1px solid var(--border-glass)',
          background: 'rgba(15,15,35,0.8)',
          backdropFilter: 'blur(20px)',
        }}
      >
        <div style={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          padding: collapsed ? 0 : '0 20px',
          borderBottom: '1px solid var(--border-glass)',
          gap: 10,
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: 10,
            background: 'var(--gradient-primary)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <ThunderboltOutlined style={{ color: '#fff', fontSize: 16 }} />
          </div>
          {!collapsed && (
            <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
              智能问数
            </span>
          )}
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{ borderRight: 0, marginTop: 8, background: 'transparent' }}
        />
      </Sider>
      <Layout>
        <Header style={{
          background: 'rgba(15,15,35,0.6)',
          backdropFilter: 'blur(20px)',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid var(--border-glass)',
          height: 56,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Button
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
              type="text"
              style={{ color: 'var(--text-secondary)' }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Tooltip title="通知">
              <Badge count={0} size="small">
                <Button type="text" icon={<BellOutlined style={{ color: 'var(--text-muted)', fontSize: 16 }} />} />
              </Badge>
            </Tooltip>
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10, padding: '4px 8px', borderRadius: 10, transition: 'all 0.2s' }}
                onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.05)'}
                onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.background = 'transparent'}
              >
                <Avatar icon={<UserOutlined />} style={{ background: 'var(--gradient-primary)' }} />
                <span style={{ color: 'var(--text-primary)', fontSize: 13 }}>
                  {user?.display_name || user?.username || '用户'}
                </span>
              </div>
            </Dropdown>
          </div>
        </Header>
        <Content style={{ background: 'transparent', overflow: 'auto' }}>
          <div style={{ padding: 20, height: '100%' }}>
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}

export default MainLayout
