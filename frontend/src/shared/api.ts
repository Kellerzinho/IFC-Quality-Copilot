// Cliente da API local de revisão. Caminhos e corpos tipados pelo OpenAPI gerado.
import type { paths } from "./contracts";
import type { ApiError, ElementList, GapList, ModelPairBinding, Project } from "./types";

const BASE = "/api/v1";

/** Erro devolvido pela API (ApiError) ou falha de transporte. */
export class ApiFailure extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function parse<T>(resp: Response): Promise<T> {
  if (resp.ok) return (await resp.json()) as T;
  let body: Partial<ApiError> = {};
  try {
    body = (await resp.json()) as ApiError;
  } catch {
    // corpo não-JSON: mantém mensagem genérica
  }
  throw new ApiFailure(resp.status, body.code ?? "erro_http", body.message ?? `Falha HTTP ${resp.status}`);
}

type ProjectPath = keyof paths & `/api/v1/projects${string}`;
const _typed: ProjectPath = "/api/v1/projects"; // garante que o prefixo existe no contrato
void _typed;

function modelBase(projectId: string, modelId: string): string {
  return `${BASE}/projects/${encodeURIComponent(projectId)}/models/${encodeURIComponent(modelId)}`;
}

export const api = {
  async createProject(name: string): Promise<Project> {
    const resp = await fetch(`${BASE}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    return parse<Project>(resp);
  },

  async getProject(projectId: string): Promise<Project> {
    return parse<Project>(await fetch(`${BASE}/projects/${encodeURIComponent(projectId)}`));
  },

  async uploadSource(
    projectId: string,
    modelId: string,
    role: "ifc" | "ids",
    file: Blob,
    filename: string,
  ): Promise<ModelPairBinding> {
    const url = `${modelBase(projectId, modelId)}/${role}?filename=${encodeURIComponent(filename)}`;
    const resp = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    });
    return parse<ModelPairBinding>(resp);
  },

  async confirm(projectId: string, modelId: string, ifcRevision: string, idsRevision: string): Promise<ModelPairBinding> {
    const resp = await fetch(`${modelBase(projectId, modelId)}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ifc_revision_id: ifcRevision, ids_revision_id: idsRevision }),
    });
    return parse<ModelPairBinding>(resp);
  },

  async listElements(projectId: string, modelId: string): Promise<ElementList> {
    return parse<ElementList>(await fetch(`${modelBase(projectId, modelId)}/elements`));
  },

  async listGaps(projectId: string, modelId: string): Promise<GapList> {
    return parse<GapList>(await fetch(`${modelBase(projectId, modelId)}/gaps`));
  },

  /** Bytes do IFC para o viewer, com a revisão declarada pelo servidor. */
  async fetchIfc(projectId: string, modelId: string): Promise<{ bytes: Uint8Array; revision: string }> {
    const resp = await fetch(`${modelBase(projectId, modelId)}/ifc-file`);
    if (!resp.ok) await parse<never>(resp);
    return { bytes: new Uint8Array(await resp.arrayBuffer()), revision: resp.headers.get("X-Ifc-Revision") ?? "" };
  },
};

export type Api = typeof api;
