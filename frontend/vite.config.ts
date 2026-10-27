import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        // 容器内运行时可通过 VITE_PROXY_TARGET 指向后端服务
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8004',
        changeOrigin: true,
      },
    },
  },
})
