import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        timeout: 600_000, // 10 min — SSE pipeline streams can run long
      },
      '/health': 'http://localhost:8001',
    },
  },
})
