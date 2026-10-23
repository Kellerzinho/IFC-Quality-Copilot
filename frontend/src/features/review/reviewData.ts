// Dados da revisão já carregados da API, indexados pela identidade composta.
import { elementKey } from "@/shared/elementKey";
import type { ElementRecord, Gap, ModelPairBinding } from "@/shared/types";

export interface ModeloRevisao {
  binding: ModelPairBinding;
  elementos: ElementRecord[];
  /** null = modelo ainda não analisado (vínculo não confirmado). */
  lacunas: Gap[] | null;
  erro?: string;
}

export interface LacunasDoElemento {
  /** Lacunas atribuídas a este ElementRef. */
  resolvidas: Gap[];
  /** Lacunas ambíguas em que este elemento é um dos candidatos (nenhum foi escolhido). */
  ambiguas: Gap[];
}

export interface LinhaElemento {
  chave: string;
  record: ElementRecord;
  binding: ModelPairBinding;
  lacunas: LacunasDoElemento;
}

const VAZIO: LacunasDoElemento = { resolvidas: [], ambiguas: [] };

export function indexarLacunas(modelos: ModeloRevisao[]): Map<string, LacunasDoElemento> {
  const indice = new Map<string, LacunasDoElemento>();
  const obter = (chave: string) => {
    let item = indice.get(chave);
    if (!item) {
      item = { resolvidas: [], ambiguas: [] };
      indice.set(chave, item);
    }
    return item;
  };
  for (const modelo of modelos) {
    for (const gap of modelo.lacunas ?? []) {
      if (gap.element) obter(elementKey(gap.element)).resolvidas.push(gap);
      for (const candidato of gap.candidates ?? []) obter(elementKey(candidato)).ambiguas.push(gap);
    }
  }
  return indice;
}

export function montarLinhas(modelos: ModeloRevisao[]): LinhaElemento[] {
  const indice = indexarLacunas(modelos);
  return modelos.flatMap((modelo) =>
    modelo.elementos.map((record) => {
      const chave = elementKey(record.ref);
      return { chave, record, binding: modelo.binding, lacunas: indice.get(chave) ?? VAZIO };
    }),
  );
}

export function totalLacunas(l: LacunasDoElemento): number {
  return l.resolvidas.length + l.ambiguas.length;
}

export interface ResumoRevisao {
  elementos: number;
  /** null = nenhum modelo analisado (sem vínculo confirmado). */
  lacunas: number | null;
  ambiguas: number | null;
  semGeometria: number;
}

/** Números da faixa de resumo, somando os modelos carregados. */
export function resumirRevisao(modelos: ModeloRevisao[], linhas: LinhaElemento[]): ResumoRevisao {
  const analisados = modelos.filter((m) => m.lacunas !== null);
  const gaps = analisados.flatMap((m) => m.lacunas ?? []);
  return {
    elementos: linhas.length,
    lacunas: analisados.length ? gaps.length : null,
    ambiguas: analisados.length ? gaps.filter((g) => g.resolution === "ambiguous").length : null,
    semGeometria: linhas.filter((l) => !l.record.has_geometry).length,
  };
}
