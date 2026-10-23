// Copia WASM do web-ifc e worker do Fragments para public/viewer/ (servidos na
// mesma origem). Evita autoSetWasm/getWorker da That Open, que buscam no unpkg.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(join(root, "package.json"));
const out = join(root, "public", "viewer");
mkdirSync(out, { recursive: true });

const webIfcDir = dirname(require.resolve("web-ifc/web-ifc.wasm"));
copyFileSync(join(webIfcDir, "web-ifc.wasm"), join(out, "web-ifc.wasm"));
copyFileSync(require.resolve("@thatopen/fragments/worker"), join(out, "fragments-worker.mjs"));
console.log("ativos do viewer copiados para public/viewer/");
