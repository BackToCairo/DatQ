import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider } from 'antd'
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
    </ConfigProvider>
  )
}

export default App
