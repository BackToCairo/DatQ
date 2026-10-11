import axios from 'axios'
import { message } from 'antd'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
})

// Request interceptor: attach token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor: handle errors
// 请求时可传 { silent: true } 跳过全局错误提示（用于可降级的请求）
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    if (!error.config?.silent) {
      const msg = error.response?.data?.detail?.message || error.message || '请求失败'
      message.error(msg)
    }
    return Promise.reject(error)
  }
)

// Auth
export const authApi = {
  login: (data: { username: string; password: string }) => api.post('/auth/login', data),
  register: (data: { username: string; email: string; password: string }) => api.post('/auth/register', data),
  me: () => api.get('/auth/me'),
  refresh: (refreshToken: string) => api.post('/auth/refresh', { refresh_token: refreshToken }),
}

// Datasource
export const datasourceApi = {
  list: () => api.get('/datasources'),
  create: (data: any) => api.post('/datasources', data),
  get: (id: string) => api.get(`/datasources/${id}`),
  update: (id: string, data: any) => api.put(`/datasources/${id}`, data),
  delete: (id: string) => api.delete(`/datasources/${id}`),
  testConnection: (id: string) => api.post(`/datasources/${id}/test-connection`),
  tables: (id: string) => api.get(`/datasources/${id}/tables`),
  columns: (id: string, tableName: string) => api.get(`/datasources/${id}/tables/${tableName}/columns`),
  uploadSchema: (id: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post(`/datasources/${id}/upload-schema`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  syncSchema: (id: string) => api.post(`/datasources/${id}/sync-schema`),
}

// Conversation
export const conversationApi = {
  list: () => api.get('/conversations'),
  create: (data?: { title?: string }) => api.post('/conversations', data || {}),
  get: (id: string) => api.get(`/conversations/${id}`),
  delete: (id: string) => api.delete(`/conversations/${id}`),
}

// Query
export const queryApi = {
  ask: (data: { question: string; conversation_id?: string; datasource_id?: string }) =>
    api.post('/query/ask', data),
  execute: (data: { sql: string; datasource_id: string }) => api.post('/query/execute', data),
  feedback: (id: string, feedback: string) => api.post(`/query/${id}/feedback`, { feedback }),
  exportCsv: async (id: string, filename: string) => {
    const res = await api.get(`/query/${id}/export`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([res as any]))
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    window.URL.revokeObjectURL(url)
  },
}

// Knowledge
export const knowledgeApi = {
  listDocs: (datasourceId?: string) => {
    const params = datasourceId ? `?datasource_id=${datasourceId}` : ''
    return api.get(`/knowledge/docs${params}`)
  },
  createDoc: (data: { title: string; doc_type: string; content: string; datasource_id?: string }) =>
    api.post('/knowledge/docs', data),
  uploadDoc: (file: File, title?: string, docType?: string, datasourceId?: string) => {
    const formData = new FormData()
    formData.append('file', file)
    if (title) formData.append('title', title)
    if (docType) formData.append('doc_type', docType)
    if (datasourceId) formData.append('datasource_id', datasourceId)
    return api.post('/knowledge/docs/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  deleteDoc: (id: string) => api.delete(`/knowledge/docs/${id}`),
  listSqlExamples: (datasourceId?: string) => {
    const params = datasourceId ? `?datasource_id=${datasourceId}` : ''
    return api.get(`/knowledge/sql-examples${params}`)
  },
  createSqlExample: (data: any) => api.post('/knowledge/sql-examples', data),
  updateSqlExample: (id: string, data: any) => api.put(`/knowledge/sql-examples/${id}`, data),
  deleteSqlExample: (id: string) => api.delete(`/knowledge/sql-examples/${id}`),
  retrieveTest: (data: { query: string; top_k?: number }) => api.post('/knowledge/retrieve-test', data),
}

// Admin(系统管理: 用户/角色/审计日志/统计)
export const adminApi = {
  listUsers: (params?: { page?: number; page_size?: number; search?: string }) =>
    api.get('/admin/users', { params }),
  createUser: (data: { username: string; email: string; password: string; display_name?: string; phone?: string }) =>
    api.post('/admin/users', data),
  updateUser: (id: string, data: { display_name?: string; phone?: string; email?: string }) =>
    api.put(`/admin/users/${id}`, data),
  updateUserStatus: (id: string, status: 'active' | 'disabled') =>
    api.patch(`/admin/users/${id}/status`, null, { params: { status } }),
  assignRoles: (id: string, roleIds: string[]) =>
    api.put(`/admin/users/${id}/roles`, { role_ids: roleIds }),
  listRoles: () => api.get('/admin/roles'),
  createRole: (data: { name: string; display_name: string; description?: string }) =>
    api.post('/admin/roles', data),
  listQueryLogs: (params?: { page?: number; page_size?: number; status?: string }) =>
    api.get('/admin/logs/queries', { params }),
  listOperationLogs: (params?: { page?: number; page_size?: number; action?: string }) =>
    api.get('/admin/logs/operations', { params }),
  queryTrend: (days = 14) =>
    api.get('/admin/stats/query-trend', { params: { days }, silent: true } as any),
  datasourceDistribution: () =>
    api.get('/admin/stats/datasource-distribution', { silent: true } as any),
}

// Semantic(语义层: 模型/指标/维度)
export const semanticApi = {
  listModels: (datasourceId?: string) =>
    api.get('/semantic/models', { params: datasourceId ? { datasource_id: datasourceId } : {} }),
  createModel: (data: { name: string; display_name: string; description?: string; datasource_id?: string; base_table?: string }) =>
    api.post('/semantic/models', data),
  getModel: (id: string) => api.get(`/semantic/models/${id}`),
  updateModel: (id: string, data: any) => api.put(`/semantic/models/${id}`, data),
  deleteModel: (id: string) => api.delete(`/semantic/models/${id}`),
  createMetric: (modelId: string, data: any) => api.post(`/semantic/models/${modelId}/metrics`, data),
  updateMetric: (modelId: string, metricId: string, data: any) =>
    api.put(`/semantic/models/${modelId}/metrics/${metricId}`, data),
  deleteMetric: (modelId: string, metricId: string) =>
    api.delete(`/semantic/models/${modelId}/metrics/${metricId}`),
  createDimension: (modelId: string, data: any) => api.post(`/semantic/models/${modelId}/dimensions`, data),
  updateDimension: (modelId: string, dimId: string, data: any) =>
    api.put(`/semantic/models/${modelId}/dimensions/${dimId}`, data),
  deleteDimension: (modelId: string, dimId: string) =>
    api.delete(`/semantic/models/${modelId}/dimensions/${dimId}`),
}

// Dashboard
export const dashboardApi = {
  list: () => api.get('/dashboards'),
  create: (data: { name: string; description?: string; is_public?: boolean }) =>
    api.post('/dashboards', data),
  get: (id: string) => api.get(`/dashboards/${id}`),
  update: (id: string, data: any) => api.put(`/dashboards/${id}`, data),
  delete: (id: string) => api.delete(`/dashboards/${id}`),
  addWidget: (dashboardId: string, data: any) => api.post(`/dashboards/${dashboardId}/widgets`, data),
  updateWidget: (widgetId: string, data: any) => api.put(`/dashboards/widgets/${widgetId}`, data),
  deleteWidget: (widgetId: string) => api.delete(`/dashboards/widgets/${widgetId}`),
  systemOverview: () => api.get('/dashboards/system/overview'),
}

export default api
