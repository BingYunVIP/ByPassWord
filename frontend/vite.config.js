import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发/预览端口固定为 899（strictPort 防止被自动切换端口）
// /api 请求代理到本地 FastAPI（127.0.0.1:8000）；生产环境由 Nginx 反代
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 899,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  },
  preview: {
    host: true,
    port: 899,
    strictPort: true
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.js']
  }
})
