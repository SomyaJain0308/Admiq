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
        // React SPA (dashboard), served at "/home/".
        home: path.resolve(import.meta.dirname, "home/index.html"),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.js",
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      exclude: [
        "node_modules/**",
        "src/test/**",
        "**/*.config.js",
        "src/main.jsx",
        // shadcn/ui primitives - generated/vendored, not app logic worth covering
        "src/components/ui/**",
      ],
    },
  },
})
