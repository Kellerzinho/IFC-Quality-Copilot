// Porta neutra do viewer 3D (M4 §8.1). A UI conversa só com esta interface;
// a biblioteca concreta fica atrás de um adaptador trocável (escolha na M4-03).
import type { ElementRecord, ElementRef } from "@/shared/types";

export interface ModeloParaCarregar {
  /** model_id da linha do projeto (identidade lógica do arquivo). */
  modelId: string;
  /** SHA-256 do IFC: a cena pertence a esta revisão. */
  revisionId: string;
  bytes: Uint8Array;
  /** Elementos que a API conhece nesta revisão; base do mapa de identidade. */
  elementos: ElementRecord[];
}

export type EtapaCarga = "convertendo" | "carregando" | "pronto" | "falhou" | "descarregado";

export interface EstadoModelo {
  modelId: string;
  etapa: EtapaCarga;
  /** ms desde o início da carga deste modelo. */
  decorridoMs: number;
  mensagem?: string;
  /** Contagem do mapa visual: verificados, sem geometria no viewer, divergentes. */
  mapa?: { verificados: number; semGeometria: number; divergentes: number };
}

export interface ViewerAdapter {
  montar(container: HTMLElement): Promise<void>;
  carregarModelo(modelo: ModeloParaCarregar): Promise<void>;
  descarregar(modelId: string): Promise<void>;
  /** Destaca um elemento (null limpa o destaque). */
  destacar(ref: ElementRef | null): Promise<void>;
  /** Mostra apenas estes elementos (null restaura todos). */
  isolar(refs: ElementRef[] | null): Promise<void>;
  mostrarDisciplina(modelId: string, visivel: boolean): Promise<void>;
  /** Aplica (ou retira) transparência a um modelo inteiro ("raio-X"). */
  transparencia(modelId: string, ativa: boolean): Promise<void>;
  enquadrar(ref: ElementRef): Promise<void>;
  /** Clique no 3D → ElementRef verificada, ou null (vazio / identidade não comprovada). */
  onSelecionar(callback: (ref: ElementRef | null, motivo?: "vazio" | "nao_comprovado") => void): () => void;
  onEstado(callback: (estado: EstadoModelo) => void): () => void;
  destruir(): Promise<void>;
}
