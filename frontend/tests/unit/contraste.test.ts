// @vitest-environment node
// Contraste WCAG 2.1 dos pares de cor do tema, lido direto de src/index.css:
// texto ≥ 4,5:1 (AA) e bordas/foco ≥ 3:1 (1.4.11), nos temas claro e escuro.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const css = readFileSync(fileURLToPath(new URL("../../src/index.css", import.meta.url)), "utf8");

function tokens(seletor: string): Record<string, string> {
  const bloco = css.match(new RegExp(`(?:^|\\n)${seletor.replace(".", "\\.")}\\s*\\{([^}]*)\\}`));
  if (!bloco) throw new Error(`bloco ${seletor} ausente`);
  return Object.fromEntries([...bloco[1].matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
}

function luminancia(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contraste(a: string, b: string): number {
  const [l1, l2] = [luminancia(a), luminancia(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

// [frente, fundo, onde aparece]
const TEXTO: [string, string, string][] = [
  ["ink", "bg", "texto corrido"],
  ["ink", "surface", "painéis e cards"],
  ["ink", "sunken", "selos neutros"],
  ["muted", "bg", "texto secundário"],
  ["muted", "surface", "texto secundário em painel"],
  ["muted", "sunken", "botão desativado"],
  ["primary-ink", "primary", "botão primário"],
  ["accent", "bg", "link"],
  ["accent", "surface", "link de envio"],
  ["ink", "accent-soft", "item selecionado"],
  ["accent", "accent-soft", "texto de destaque no selecionado"],
  ["band-ink", "band", "título na faixa"],
  ["band-muted", "band", "rótulos e eyebrow na faixa"],
  ["gold", "band", "números do resumo"],
  ["gold-text", "surface", "texto ouro"],
  ["gold-text", "gold-soft", "selo de lacuna e aviso"],
  ["gold-text", "sunken", "números dos passos"],
  ["danger", "bg", "erro"],
  ["danger", "surface", "erro em painel"],
  ["danger", "danger-soft", "selo GUID repetido / ambígua"],
];

const NAO_TEXTO: [string, string, string][] = [
  ["accent", "bg", "anel de foco"],
  ["accent", "surface", "anel de foco em painel, borda do selecionado"],
  ["muted", "surface", "borda de campo"],
  ["muted", "bg", "borda de campo"],
];

describe.each([":root", ".dark"])("contraste do tema %s", (seletor) => {
  const t = tokens(seletor);

  it.each(TEXTO)("texto %s sobre %s (%s) ≥ 4,5:1", (frente, fundo) => {
    expect(contraste(t[frente], t[fundo])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(NAO_TEXTO)("%s sobre %s (%s) ≥ 3:1", (frente, fundo) => {
    expect(contraste(t[frente], t[fundo])).toBeGreaterThanOrEqual(3);
  });
});
