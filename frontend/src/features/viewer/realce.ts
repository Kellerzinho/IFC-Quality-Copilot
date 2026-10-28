// Realce visual do viewer: raio-X por modelo e contorno do elemento destacado.
// Funções puras sobre objetos three, testáveis sem WebGL (tests/unit/realce.test.ts).
//
// Por que o raio-X não usa model.setOpacity() do Fragments 3.4.8: o highlight é
// desenhado como um grupo EXTRA da geometria por cima do grupo base
// ([0,∞,mat0] da visibilidade + [0,∞,mat1] do highlight, ver mesh-manager.mjs
// updateStatus). O grupo base opaco continua sendo desenhado; o transparente só
// mistura a cor sobre ele e a parede fica opaca. Diagnóstico com window.__m4 em
// 2026-10-28. A transparência vai, então, no material base do próprio modelo.
import * as THREE from "three";

/** Material base de uma malha do Fragments: índice 0 (grupo da visibilidade). */
function materialBase(mesh: THREE.Mesh): THREE.Material | null {
  const m = mesh.material;
  return (Array.isArray(m) ? m[0] : m) ?? null;
}

interface EstadoMaterial {
  opacity: number;
  transparent: boolean;
  depthWrite: boolean;
}

export type MemoriaRaioX = WeakMap<THREE.Material, EstadoMaterial>;

/**
 * Aplica (ou desfaz) transparência no material base de todas as malhas de `raiz`.
 * O estado original fica em `memoria` e é restaurado ao desligar. Materiais de
 * highlight (índices ≥ 1) não são tocados: o elemento destacado continua opaco.
 * Idempotente: pode ser reaplicado depois de cada atualização de tiles.
 * Retorna quantos materiais estão no estado pedido.
 */
export function aplicarRaioX(raiz: THREE.Object3D, ativa: boolean, opacidade: number, memoria: MemoriaRaioX): number {
  const vistos = new Set<THREE.Material>();
  raiz.traverse((o) => {
    if (!(o as THREE.Mesh).isMesh) return;
    const base = materialBase(o as THREE.Mesh);
    if (base) vistos.add(base);
  });
  for (const material of vistos) {
    const original = memoria.get(material);
    if (ativa) {
      if (!original) {
        memoria.set(material, {
          opacity: material.opacity,
          transparent: material.transparent,
          depthWrite: material.depthWrite,
        });
      }
      material.opacity = opacidade;
      material.transparent = true;
      material.depthWrite = false; // o que está atrás (estrutura) continua visível
    } else if (original) {
      material.opacity = original.opacity;
      material.transparent = original.transparent;
      material.depthWrite = original.depthWrite;
      memoria.delete(material);
    }
    material.needsUpdate = true;
  }
  return vistos.size;
}

/** Luminância relativa WCAG 2.x de uma cor sRGB. */
export function luminancia(cor: THREE.Color): number {
  const canal = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const srgb = cor.getRGB({ r: 0, g: 0, b: 0 }, THREE.SRGBColorSpace);
  return 0.2126 * canal(srgb.r) + 0.7152 * canal(srgb.g) + 0.0722 * canal(srgb.b);
}

/** Razão de contraste WCAG entre duas cores (1 a 21). */
export function razaoContraste(a: THREE.ColorRepresentation, b: THREE.ColorRepresentation): number {
  const la = luminancia(new THREE.Color(a));
  const lb = luminancia(new THREE.Color(b));
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Candidatas ao contorno do destaque: escura para fundo claro, clara para fundo escuro. */
export const CORES_CONTORNO = ["#111827", "#f9fafb"] as const;

/** Contraste mínimo do contorno sobre o fundo do viewer (WCAG 1.4.11, objeto gráfico). */
export const CONTRASTE_MINIMO_CONTORNO = 3;

/** Cor do contorno com maior contraste sobre o fundo atual do viewer. */
export function corContorno(fundo: THREE.ColorRepresentation): THREE.Color {
  const [melhor] = [...CORES_CONTORNO].sort((x, y) => razaoContraste(y, fundo) - razaoContraste(x, fundo));
  return new THREE.Color(melhor);
}

/** Malha de um item como o Fragments a devolve em getItemsGeometry(). */
export interface MalhaItem {
  transform: THREE.Matrix4;
  positions?: ArrayLike<number>;
  indices?: ArrayLike<number>;
}

/**
 * Arestas (ângulo ≥ `limiarGraus`) das malhas de um item, já no espaço do modelo,
 * como pares de pontos para LineSegments. Malha sem posições é ignorada.
 */
export function arestasDoItem(malhas: MalhaItem[], limiarGraus = 20): Float32Array {
  const partes: Float32Array[] = [];
  for (const malha of malhas) {
    if (!malha.positions || malha.positions.length < 9) continue;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(Float32Array.from(malha.positions), 3));
    if (malha.indices && malha.indices.length) geo.setIndex(Array.from(malha.indices));
    geo.applyMatrix4(malha.transform);
    const arestas = new THREE.EdgesGeometry(geo, limiarGraus);
    partes.push(arestas.getAttribute("position").array as Float32Array);
    geo.dispose();
    arestas.dispose();
  }
  const total = partes.reduce((n, p) => n + p.length, 0);
  const saida = new Float32Array(total);
  let pos = 0;
  for (const p of partes) {
    saida.set(p, pos);
    pos += p.length;
  }
  return saida;
}
