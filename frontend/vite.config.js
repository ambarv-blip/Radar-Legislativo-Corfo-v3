import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // El navegador nunca llama directamente al backend: todas las peticiones a /api
    // las recibe este mismo dev server y las reenvía server-side (sin CORS) a FastAPI.
    // Esto evita depender de que el puerto público de Codespaces reenvíe correctamente
    // las peticiones cross-origin entre dos hostnames *.app.github.dev distintos.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
})
