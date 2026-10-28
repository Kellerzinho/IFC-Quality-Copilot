// Tema claro/escuro: classe .dark no <html>. Sem escolha salva, segue o sistema.
// A preferência fica só neste navegador (localStorage), como conveniência.
import { useCallback, useSyncExternalStore } from "react";

export type Tema = "claro" | "escuro";

const CHAVE = "iqc-tema";
const ouvintes = new Set<() => void>();

function temaSalvo(): Tema | null {
  try {
    const v = localStorage.getItem(CHAVE);
    return v === "claro" || v === "escuro" ? v : null;
  } catch {
    return null;
  }
}

function temaDoSistema(): Tema {
  return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches ? "escuro" : "claro";
}

export function temaAtual(): Tema {
  return document.documentElement.classList.contains("dark") ? "escuro" : "claro";
}

export function aplicarTema(tema: Tema): void {
  document.documentElement.classList.toggle("dark", tema === "escuro");
  ouvintes.forEach((ouvir) => ouvir());
}

/** Aplica o tema salvo (ou o do sistema) antes do primeiro render. */
export function iniciarTema(): void {
  aplicarTema(temaSalvo() ?? temaDoSistema());
}

export function definirTema(tema: Tema): void {
  try {
    localStorage.setItem(CHAVE, tema);
  } catch {
    // Sem armazenamento: o tema vale só para esta aba.
  }
  aplicarTema(tema);
}

function assinar(ouvir: () => void) {
  ouvintes.add(ouvir);
  return () => {
    ouvintes.delete(ouvir);
  };
}

export function useTema(): [Tema, () => void] {
  const tema = useSyncExternalStore(assinar, temaAtual, () => "claro" as Tema);
  const alternar = useCallback(() => definirTema(temaAtual() === "escuro" ? "claro" : "escuro"), []);
  return [tema, alternar];
}
