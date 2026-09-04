import path from "path"
import react from '@vitejs/plugin-react'
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      input: {
        // Static marketing landing page, served at "/".
        landing: path.resolve(import.meta.dirname, "index.html"),
        // React SPA (dashboard), served at "/app/".
        app: path.resolve(import.meta.dirname, "app/index.html"),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.js",
  },
})
