import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/pipeline': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/upload_answer': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/analyze': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/audio_proxy': { target: 'http://127.0.0.1:8080', changeOrigin: true }
    }
  }
})
