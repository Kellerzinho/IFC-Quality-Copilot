import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  aplicarRaioX,
  arestasDoItem,
  CONTRASTE_MINIMO_CONTORNO,
  corContorno,
  razaoContraste,
  type MemoriaRaioX,
} from "@/features/viewer/realce";

/** Malha como o Fragments 3.4.8 deixa um tile com highlight: base [0] + highlight [1]. */
function malhaComHighlight() {
  const base = new THREE.MeshLambertMaterial({ color: "#cccccc" });
  const highlight = new THREE.MeshLambertMaterial({ color: "#f59e0b" });
  const geo = new THREE.BoxGeometry(1, 1, 1);
  geo.clearGroups();
  geo.addGroup(0, Infinity, 0);
  geo.addGroup(0, Infinity, 1);
  const mesh = new THREE.Mesh(geo, [base, highlight]);
  const raiz = new THREE.Group();
  raiz.add(mesh);
  return { raiz, base, highlight };
}

describe("aplicarRaioX", () => {
  it("deixa o material base transparente e sem escrita de profundidade", () => {
    const { raiz, base } = malhaComHighlight();
    aplicarRaioX(raiz, true, 0.15, new WeakMap());
    expect(base.transparent).toBe(true);
    expect(base.opacity).toBe(0.15);
    expect(base.depthWrite).toBe(false);
  });

  // Regressão do defeito de 2026-10-28: o setOpacity do Fragments só mexia no
  // grupo de highlight, e o grupo base opaco continuava cobrindo a parede.
  it("não depende do highlight: o material do grupo base é o que muda", () => {
    const { raiz, base, highlight } = malhaComHighlight();
    aplicarRaioX(raiz, true, 0.15, new WeakMap());
    expect(base.opacity).toBeLessThan(1);
    expect(highlight.opacity).toBe(1);
    expect(highlight.transparent).toBe(false);
  });

  it("restaura o estado original ao desligar", () => {
    const { raiz, base } = malhaComHighlight();
    base.opacity = 0.9;
    base.transparent = true;
    const memoria: MemoriaRaioX = new WeakMap();
    aplicarRaioX(raiz, true, 0.15, memoria);
    aplicarRaioX(raiz, false, 0.15, memoria);
    expect(base.opacity).toBe(0.9);
    expect(base.transparent).toBe(true);
    expect(base.depthWrite).toBe(true);
  });

  it("é idempotente: reaplicar não perde o original", () => {
    const { raiz, base } = malhaComHighlight();
    const memoria: MemoriaRaioX = new WeakMap();
    aplicarRaioX(raiz, true, 0.15, memoria);
    aplicarRaioX(raiz, true, 0.15, memoria);
    aplicarRaioX(raiz, false, 0.15, memoria);
    expect(base.opacity).toBe(1);
    expect(base.transparent).toBe(false);
  });

  it("desligar sem ter ligado não altera nada", () => {
    const { raiz, base } = malhaComHighlight();
    aplicarRaioX(raiz, false, 0.15, new WeakMap());
    expect(base.opacity).toBe(1);
    expect(base.transparent).toBe(false);
  });

  it("aceita malha com material único (sem grupos de highlight)", () => {
    const material = new THREE.MeshLambertMaterial();
    const raiz = new THREE.Group().add(new THREE.Mesh(new THREE.BoxGeometry(), material));
    expect(aplicarRaioX(raiz, true, 0.2, new WeakMap())).toBe(1);
    expect(material.opacity).toBe(0.2);
  });
});

describe("contraste do contorno do destaque", () => {
  it("calcula a razão WCAG nos extremos", () => {
    expect(razaoContraste("#000000", "#ffffff")).toBeCloseTo(21, 1);
    expect(razaoContraste("#777777", "#777777")).toBeCloseTo(1, 5);
  });

  it("a cor de destaque sozinha não chega a 3:1 sobre o fundo claro (motivo do contorno)", () => {
    expect(razaoContraste("#f59e0b", "#f5f5f5")).toBeLessThan(CONTRASTE_MINIMO_CONTORNO);
  });

  // Fundos do viewer: base (#f5f5f5) e os tokens dos temas em avaliação
  // (Oliva-Turquesa --viewer e LEPV --viewer-bg, claro e escuro).
  it.each(["#f5f5f5", "#ebece6", "#efece6", "#1b1b18", "#1a1816"])(
    "contorno sobre %s tem contraste ≥ 3:1",
    (fundo) => {
      expect(razaoContraste(corContorno(fundo), fundo)).toBeGreaterThanOrEqual(CONTRASTE_MINIMO_CONTORNO);
    },
  );

  it("fundo claro recebe contorno escuro; fundo escuro, contorno claro", () => {
    expect(corContorno("#f5f5f5").getHexString()).toBe("111827");
    expect(corContorno("#1b1b18").getHexString()).toBe("f9fafb");
  });
});

describe("arestasDoItem", () => {
  it("devolve as 12 arestas de um cubo, já transformadas", () => {
    const cubo = new THREE.BoxGeometry(1, 1, 1);
    const transform = new THREE.Matrix4().makeTranslation(10, 0, 0);
    const pontos = arestasDoItem([
      { transform, positions: cubo.getAttribute("position").array, indices: cubo.getIndex()!.array },
    ]);
    expect(pontos.length).toBe(12 * 2 * 3);
    const xs = pontos.filter((_, i) => i % 3 === 0);
    expect(Math.min(...xs)).toBeCloseTo(9.5);
    expect(Math.max(...xs)).toBeCloseTo(10.5);
  });

  it("ignora malha sem posições", () => {
    expect(arestasDoItem([{ transform: new THREE.Matrix4() }]).length).toBe(0);
  });
});
