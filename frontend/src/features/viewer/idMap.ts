// Mapa EXPLÍCITO id interno do viewer ↔ ElementRef (M4 §8.1, T4-05).
//
// Hipótese do importador da That Open: localId = express_id. Ela NÃO é presumida:
// cada vínculo só vale se o item do viewer tiver a mesma classe IFC e o mesmo
// GlobalId que a API declara para aquele ElementRef. Divergência ou ausência
// tira o elemento do mapa; clique nele não seleciona nada.
import { elementKey } from "@/shared/elementKey";
import type { ElementRecord, ElementRef } from "@/shared/types";

/** O que o viewer informa sobre um item que possui geometria. */
export interface FatoViewer {
  localId: number;
  categoria: string | null;
  guid: string | null;
}

export type SituacaoVinculo = "verificado" | "sem_geometria" | "divergente";

/** Subconjunto do FragmentsModel usado para levantar os fatos. */
export interface FonteFatos {
  getItemsIdsWithGeometry(): Promise<number[]>;
  getGuidsByLocalIds(localIds: number[]): Promise<(string | null)[]>;
  getItemsOfCategories(categories: RegExp[]): Promise<Record<string, number[]>>;
}

/**
 * Classe e GlobalId de cada item COM geometria. Apesar do nome,
 * getItemsIdsWithGeometry() já devolve localIds (Fragments 3.4.8); passá-los
 * por getLocalIdsFromItemIds() embaralha os ids.
 */
export async function coletarFatos(model: FonteFatos): Promise<Map<number, FatoViewer>> {
  const localIds = await model.getItemsIdsWithGeometry();
  const guids = await model.getGuidsByLocalIds(localIds);
  const porCategoria = await model.getItemsOfCategories([/.*/]);
  const categoria = new Map<number, string>();
  for (const [cat, ids] of Object.entries(porCategoria)) for (const id of ids) categoria.set(id, cat);
  const fatos = new Map<number, FatoViewer>();
  localIds.forEach((localId, i) => {
    fatos.set(localId, { localId, categoria: categoria.get(localId) ?? null, guid: guids[i] ?? null });
  });
  return fatos;
}

export interface MapaIdentidade {
  modelId: string;
  /** chave do ElementRef → localId no viewer (só verificados). */
  localPorChave: Map<string, number>;
  /** localId → ElementRef (só verificados). */
  refPorLocal: Map<number, ElementRef>;
  situacao: Map<string, SituacaoVinculo>;
}

function normalizarClasse(valor: string): string {
  return valor.trim().toUpperCase();
}

export function construirMapa(
  modelId: string,
  elementos: ElementRecord[],
  fatos: Map<number, FatoViewer>,
): MapaIdentidade {
  const mapa: MapaIdentidade = {
    modelId,
    localPorChave: new Map(),
    refPorLocal: new Map(),
    situacao: new Map(),
  };
  for (const elemento of elementos) {
    const ref = elemento.ref;
    const chave = elementKey(ref);
    if (ref.model_id !== modelId) {
      mapa.situacao.set(chave, "divergente");
      continue;
    }
    const fato = fatos.get(ref.express_id);
    if (!fato) {
      mapa.situacao.set(chave, "sem_geometria");
      continue;
    }
    const classeOk = fato.categoria !== null && normalizarClasse(fato.categoria) === normalizarClasse(elemento.ifc_class);
    const guidOk = elemento.global_id == null || fato.guid === elemento.global_id;
    if (!classeOk || !guidOk || mapa.refPorLocal.has(fato.localId)) {
      mapa.situacao.set(chave, "divergente");
      continue;
    }
    mapa.localPorChave.set(chave, fato.localId);
    mapa.refPorLocal.set(fato.localId, ref);
    mapa.situacao.set(chave, "verificado");
  }
  return mapa;
}

export function resumoMapa(mapa: MapaIdentidade): { verificados: number; semGeometria: number; divergentes: number } {
  let verificados = 0;
  let semGeometria = 0;
  let divergentes = 0;
  for (const s of mapa.situacao.values()) {
    if (s === "verificado") verificados += 1;
    else if (s === "sem_geometria") semGeometria += 1;
    else divergentes += 1;
  }
  return { verificados, semGeometria, divergentes };
}
