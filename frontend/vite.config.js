import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',       // Vercel expects dist/ for Vite
    sourcemap: false,     // smaller bundle in production
  },
  server: {
    port: 5173,           // local dev port
  },
})
