import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, message, Typography } from 'antd'
import { UserOutlined, LockOutlined, ThunderboltOutlined, DatabaseOutlined, BarChartOutlined } from '@ant-design/icons'
import { authApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'

const { Title, Text } = Typography

const Login: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { login } = useAuthStore()

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const res: any = await authApi.login(values)
      if (res.code === 0) {
        const { access_token, user } = res.data
        login(user, access_token)
        message.success('登录成功')
        navigate('/chat')
      } else {
        message.error(res.message || '登录失败')
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail?.message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      height: '100vh',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      background: 'var(--gradient-bg)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Background decorations */}
      <div style={{
        position: 'absolute', width: 500, height: 500, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(99,102,241,0.1) 0%, transparent 70%)',
        top: '-10%', right: '-5%', animation: 'float 6s ease-in-out infinite',
      }} />
      <div style={{
        position: 'absolute', width: 400, height: 400, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(6,182,212,0.08) 0%, transparent 70%)',
        bottom: '-10%', left: '-5%', animation: 'float 8s ease-in-out infinite',
      }} />

      <div style={{ display: 'flex', gap: 60, alignItems: 'center', zIndex: 1 }}>
        {/* Left side - Branding */}
        <div style={{ maxWidth: 400, textAlign: 'left' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
            <div className="glow-btn" style={{
              width: 48, height: 48, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 24, cursor: 'default',
            }}>
              <ThunderboltOutlined />
            </div>
            <Title level={2} style={{ margin: 0, color: 'var(--text-primary)' }}>智能问数</Title>
          </div>
          <Text style={{ color: 'var(--text-secondary)', fontSize: 16, lineHeight: 1.8, display: 'block', marginBottom: 32 }}>
            自然语言查询，智能数据分析
            <br />
            让数据触手可及
          </Text>
          <div style={{ display: 'flex', gap: 24 }}>
            {[
              { icon: <ThunderboltOutlined />, text: '秒级响应' },
              { icon: <DatabaseOutlined />, text: '多源接入' },
              { icon: <BarChartOutlined />, text: '智能图表' },
            ].map((item, i) => (
              <div key={i} style={{ textAlign: 'center' }}>
                <div style={{
                  width: 44, height: 44, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)',
                  marginBottom: 8, fontSize: 18, color: 'var(--primary-light)',
                }}>
                  {item.icon}
                </div>
                <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>{item.text}</Text>
              </div>
            ))}
          </div>
        </div>

        {/* Right side - Login Form */}
        <div className="glass-card animate-fadeInUp" style={{ width: 400, padding: '40px 36px', borderRadius: 20 }}>
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <Title level={3} style={{ margin: 0, color: 'var(--text-primary)' }}>欢迎回来</Title>
            <Text style={{ color: 'var(--text-muted)', fontSize: 14, marginTop: 8, display: 'block' }}>
              登录以继续使用智能问数平台
            </Text>
          </div>
          <Form onFinish={onFinish} size="large">
            <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input
                prefix={<UserOutlined style={{ color: 'var(--text-muted)' }} />}
                placeholder="用户名"
                style={{ borderRadius: 12, height: 46 }}
              />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password
                prefix={<LockOutlined style={{ color: 'var(--text-muted)' }} />}
                placeholder="密码"
                style={{ borderRadius: 12, height: 46 }}
              />
            </Form.Item>
            <Form.Item style={{ marginBottom: 16 }}>
              <Button type="primary" htmlType="submit" loading={loading} block
                className="glow-btn"
                style={{ height: 46, borderRadius: 12, fontSize: 15, fontWeight: 600 }}>
                登 录
              </Button>
            </Form.Item>
          </Form>
          <div style={{ textAlign: 'center' }}>
            <Text style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              还没有账号？请联系管理员开通
            </Text>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Login
