// Falha se src/shared/contracts.ts não corresponder a openapi.json.
// O par openapi.json × API Python é conferido por tests/review_api/test_openapi_sync.py.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const tmp = mkdtempSync(join(tmpdir(), "m4-contracts-"));
const generated = join(tmp, "contracts.ts");
const cli = join(root, "node_modules", "openapi-typescript", "bin", "cli.js");

try {
  execFileSync(process.execPath, [cli, join(root, "openapi.json"), "-o", generated], {
    stdio: "pipe",
  });
  const normalize = (text) => text.replace(/\r\n/g, "\n");
  const expected = normalize(readFileSync(generated, "utf8"));
  const current = normalize(readFileSync(join(root, "src", "shared", "contracts.ts"), "utf8"));
  if (expected !== current) {
    console.error("contracts.ts desatualizado: rode `npm run gen:api` em frontend/.");
    process.exit(1);
  }
  console.log("contracts.ts em dia com openapi.json.");
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
