import { afterEach, describe, expect, it } from "vitest";

import { definirTema, iniciarTema, temaAtual } from "@/shared/theme";

afterEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

describe("tema claro/escuro", () => {
  it("definirTema aplica a classe .dark e lembra a escolha", () => {
    definirTema("escuro");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(temaAtual()).toBe("escuro");
    document.documentElement.classList.remove("dark");
    iniciarTema();
    expect(temaAtual()).toBe("escuro");
  });

  it("sem escolha salva e sem matchMedia, começa claro", () => {
    iniciarTema();
    expect(temaAtual()).toBe("claro");
  });
});
