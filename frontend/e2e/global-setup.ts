// Gera o corpus sintético M4 se ainda não existir (arquivos ignorados pelo git).
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const AQUI = path.dirname(fileURLToPath(import.meta.url));

export const CORPUS = path.resolve(AQUI, "../../tests/fixtures/m4/generated");

export default function globalSetup(): void {
  const faltando = ["arquitetura", "estrutura"].some(
    (b) => !existsSync(path.join(CORPUS, `m4_sintetico_${b}.ifc`)) || !existsSync(path.join(CORPUS, `m4_sintetico_${b}.ids`)),
  );
  if (!faltando) return;
  execFileSync("uv", ["run", "python", "scripts/m4_gerar_corpus_sintetico.py"], {
    cwd: path.resolve(AQUI, "../.."),
    stdio: "inherit",
  });
}
