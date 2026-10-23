// Varre frontend/dist e falha se o build depender de qualquer recurso externo em
// tempo de execução: CDN, Google Fonts, fontes/ícones/CSS remotos, WASM ou worker
// fora da origem. Rode após `npm run build` (ou use `npm run verify:local`).
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
if (!existsSync(dist)) {
  console.error("dist/ não existe: rode `npm run build` antes.");
  process.exit(1);
}

function listar(dir) {
  return readdirSync(dir).flatMap((nome) => {
    const caminho = join(dir, nome);
    return statSync(caminho).isDirectory() ? listar(caminho) : [caminho];
  });
}

const arquivos = listar(dist);
const falhas = [];
const falhar = (arquivo, motivo) => falhas.push(`${relative(dist, arquivo)}: ${motivo}`);

// Hosts proibidos em QUALQUER arquivo do build (inclui JS).
const CDN = /(fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com|use\.fontawesome\.com|kit\.fontawesome\.com|ajax\.googleapis\.com|esm\.sh|skypack\.dev|cdn\.tailwindcss\.com)/;

// Strings conhecidas da That Open que contêm unpkg mas NÃO executam neste app:
// IfcLoader.autoSetWasm (desligado: não usamos IfcLoader) e
// FragmentsModels.getWorker (não chamado: worker local em /viewer/).
const UNPKG_TOLERADOS = [
  "https://unpkg.com/@thatopen/components@",
  "https://unpkg.com/web-ifc@",
  "https://unpkg.com/@thatopen/fragments@",
];

for (const arquivo of arquivos) {
  const ext = extname(arquivo);
  if ([".wasm", ".png", ".jpg", ".ico", ".woff", ".woff2", ".map"].includes(ext)) continue;
  const texto = readFileSync(arquivo, "utf8");

  const cdn = texto.match(CDN);
  if (cdn) falhar(arquivo, `referência a CDN/fonte externa (${cdn[0]})`);

  for (const m of texto.matchAll(/https:\/\/unpkg\.com\/[^"'`\s)]*/g)) {
    if (!UNPKG_TOLERADOS.some((p) => m[0].startsWith(p))) falhar(arquivo, `unpkg não tolerado (${m[0]})`);
  }

  if (ext === ".html") {
    for (const m of texto.matchAll(/<(?:script|link|img|iframe|source)\b[^>]*\b(?:src|href)\s*=\s*["']([^"']+)["']/gi)) {
      if (/^(https?:)?\/\//i.test(m[1])) falhar(arquivo, `ativo externo no HTML (${m[1]})`);
    }
    if (!/http-equiv="Content-Security-Policy"/.test(texto)) falhar(arquivo, "CSP ausente no HTML do build");
  }

  if (ext === ".css") {
    if (/@import\s+(url\()?\s*["']?(https?:)?\/\//i.test(texto)) falhar(arquivo, "@import de CSS externo");
    for (const m of texto.matchAll(/url\(\s*["']?((?:https?:)?\/\/[^"')]+)/gi)) falhar(arquivo, `url() externa (${m[1]})`);
    // Fontes do tema (@fontsource) vêm empacotadas: todo src de @font-face precisa ser
    // um arquivo deste build, servido pela própria origem.
    for (const bloco of texto.matchAll(/@font-face\s*\{[^}]*\}/gi)) {
      for (const m of bloco[0].matchAll(/url\(\s*["']?([^"')]+)/gi)) {
        const alvo = m[1].split(/[?#]/)[0];
        if (/^(?:[a-z]+:)?\/\//i.test(alvo) || /^data:/i.test(alvo)) continue; // externa já acusada acima; data: é local
        const local = alvo.startsWith("/") ? join(dist, alvo) : join(dirname(arquivo), alvo);
        if (!existsSync(local)) falhar(arquivo, `@font-face aponta para arquivo ausente no build (${m[1]})`);
      }
    }
  }
}

// O viewer exige estes ativos servidos pela própria origem.
for (const necessario of ["viewer/web-ifc.wasm", "viewer/fragments-worker.mjs"]) {
  if (!existsSync(join(dist, necessario))) falhas.push(`${necessario}: ausente no build`);
}

// Worker do Fragments não pode importar nada de fora.
const worker = join(dist, "viewer", "fragments-worker.mjs");
if (existsSync(worker) && /\bimport\s*(?:[^"';]*from\s*)?["'](?:https?:)?\/\//.test(readFileSync(worker, "utf8"))) {
  falhas.push("viewer/fragments-worker.mjs: import remoto");
}

if (falhas.length) {
  console.error("Dependências externas em tempo de execução encontradas:\n- " + falhas.join("\n- "));
  process.exit(1);
}
console.log(`dist/ verificado: ${arquivos.length} arquivos, nenhum recurso externo em tempo de execução.`);
