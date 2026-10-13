import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // Served at aibharatiya.com/linkedin/ (and the same path on its own deployment).
  base: '/linkedin/',
  plugins: [react()],
  server: {
    port: 11001,
    proxy: {
      '/api/linkedin': 'http://localhost:11000',
    }
  }
})
