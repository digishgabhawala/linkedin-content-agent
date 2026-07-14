import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 11001,
    proxy: {
      '/api': 'http://localhost:11000',
      '/data': 'http://localhost:11000',
    }
  }
})
