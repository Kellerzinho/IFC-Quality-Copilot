import type { ElementRef } from "./types";

/**
 * Forma textual estável da identidade de um elemento: modelo + revisão IFC + express_id.
 * Igual a ElementRef.key no Python. O GlobalId nunca participa.
 */
export function elementKey(ref: ElementRef): string {
  return `${ref.model_id}:${ref.ifc_revision_id}:${ref.express_id}`;
}

/** Compara duas referências pela identidade completa. */
export function sameElement(a: ElementRef | null | undefined, b: ElementRef | null | undefined): boolean {
  return !!a && !!b && elementKey(a) === elementKey(b);
}

export const DISCIPLINE_LABEL = { architecture: "Arquitetura", structure: "Estrutura" } as const;
export const DISCIPLINE_SHORT = { architecture: "ARQ", structure: "EST" } as const;
