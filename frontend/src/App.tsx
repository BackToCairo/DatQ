import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, Watermark } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import MainLayout from './components/Layout/MainLayout'
import Login from './pages/Login'
import Chat from './pages/Chat'
import DataSource from './pages/DataSource'
import Knowledge from './pages/Knowledge'
import Dashboard from './pages/Dashboard'
import Semantic from './pages/Semantic'
import Admin from './pages/Admin'

const App: React.FC = () => {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<MainLayout />}>
            <Route index element={<Navigate to="/chat" replace />} />
            <Route path="chat" element={<Chat />} />
            <Route path="chat/:conversationId" element={<Chat />} />
            <Route path="datasource" element={<DataSource />} />
            <Route path="semantic" element={<Semantic />} />
            <Route path="knowledge" element={<Knowledge />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="admin" element={<Admin />} />
          </Route>
        </Routes>
      </BrowserRouter>
      {/* 独立的视口水印覆盖页面和弹窗，不参与布局，也不拦截交互。 */}
      <Watermark
        content="王宇个人项目"
        rotate={-24}
        gap={[160, 140]}
        font={{
          color: 'rgba(241, 245, 249, 0.07)',
          fontSize: 16,
          fontFamily: '"Microsoft YaHei", "PingFang SC", sans-serif',
        }}
        zIndex={2000}
        inherit={false}
        style={{ position: 'fixed', inset: 0, zIndex: 2000, pointerEvents: 'none' }}
      />
    </ConfigProvider>
  )
}

export default App
