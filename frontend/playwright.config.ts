// E2E do checklist 3D da M4 (Playwright). Fora da suíte padrão: `npm run e2e`.
// Sobe (ou reaproveita) a API em 127.0.0.1:8765 com armazenamento temporário e o
// dev server em 127.0.0.1:5173. O Chromium headless usa WebGL por SwiftShader;
// HEADED=1 abre a janela (útil se a GPU de software não estiver disponível).
import os from "node:os";
import path from "node:path";

import { defineConfig } from "@playwright/test";

const DADOS_E2E = path.join(os.tmpdir(), "ifc-qc-m4-e2e");

export default defineConfig({
  testDir: "e2e",
  testMatch: "**/*.spec.ts",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  outputDir: path.join(os.tmpdir(), "ifc-qc-m4-e2e-resultados"),
  use: {
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1600, height: 900 },
    headless: process.env.HEADED !== "1",
    launchOptions: { args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] },
  },
  webServer: [
    {
      command: `uv run --directory .. python -m src.review_api --port 8765 --data-dir "${DADOS_E2E}"`,
      url: "http://127.0.0.1:8765/api/v1/health",
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
