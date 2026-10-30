import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // expose on LAN so the app can be opened on a phone
    host: true,
    // Same-origin calls to the FastAPI backend (also from a phone on the LAN, where 127.0.0.1 is the phone).
    // Production serves the built app from FastAPI, so the same relative paths work there.
    proxy: Object.fromEntries(
      ['/auth', '/briefing', '/documents', '/segments', '/health'].map((path) => [
        path,
        { target: process.env.BACKEND_URL ?? 'http://127.0.0.1:8000', changeOrigin: true },
      ]),
    ),
  },
})
