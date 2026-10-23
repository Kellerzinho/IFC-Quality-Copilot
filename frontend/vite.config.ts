/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// CSP do build: só a própria origem; WASM do web-ifc exige 'wasm-unsafe-eval'.
// Em dev não se aplica porque o plugin React injeta um script inline.
const CSP =
  "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; " +
  "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; " +
  "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'";

function contentSecurityPolicy(): Plugin {
  return {
    name: "m4-csp",
    apply: "build",
    transformIndexHtml: () => [
      { tag: "meta", attrs: { "http-equiv": "Content-Security-Policy", content: CSP }, injectTo: "head-prepend" },
    ],
  };
}

const API = "http://127.0.0.1:8765";

// Dev e preview só em 127.0.0.1. O proxy mantém a mesma origem para /api;
// a API aceita a Origin http://127.0.0.1:5173 explicitamente (local_access.py).
export default defineConfig({
  plugins: [react(), tailwindcss(), contentSecurityPolicy()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: API, changeOrigin: false } },
  },
  // Sem proxy no preview: a API só aceita a Origin do dev server (5173).
  preview: { host: "127.0.0.1", port: 4173, strictPort: true },
  worker: { format: "es" },
  build: { target: "es2022", chunkSizeWarningLimit: 4096 },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    css: false,
  },
});
