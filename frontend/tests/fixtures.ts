// Dados de teste no formato dos contratos gerados. Espelham o corpus sintético:
// laje com o MESMO GlobalId e o MESMO express_id nos dois arquivos, janelas com
// GlobalId repetido dentro do arquivo de arquitetura e porta com nome contendo script.
import { vi } from "vitest";

import type { EstadoModelo, ViewerAdapter } from "@/features/viewer/ViewerPort";
import type { Api } from "@/shared/api";
import type { ElementRecord, ElementRef, Gap, ModelPairBinding, Project } from "@/shared/types";

export const REV_ARQ = "a".repeat(64);
export const REV_EST = "e".repeat(64);
export const REV_IDS = "d".repeat(64);
export const GUID_LAJE = "2RegXo54vIjhQd_lnMjBAL";
export const GUID_JANELA = "3fAuhsW35I6Bb9_iLskGo8";
export const NOME_SCRIPT = "Porta <script>alert(1)</script>";

function binding(modelId: string, discipline: "architecture" | "structure", rev: string, nome: string): ModelPairBinding {
  return {
    project_id: "p1",
    model_id: modelId,
    discipline,
    ifc: { role: "ifc", revision_id: rev, size_bytes: 2048, display_name: nome, ifc_schema: "IFC4" },
    ids: { role: "ids", revision_id: REV_IDS, size_bytes: 512, display_name: `${discipline}.ids`, ifc_schema: null },
    confirmed: true,
    confirmed_ifc_revision_id: rev,
    confirmed_ids_revision_id: REV_IDS,
  };
}

export const ARQ = binding("m-arq", "architecture", REV_ARQ, "arq.ifc");
export const EST = binding("m-est", "structure", REV_EST, "est.ifc");

export const PROJECT: Project = { schema_version: "m4-plataforma-base/1", project_id: "p1", name: "Projeto teste", models: [ARQ, EST] };

export function ref(modelId: string, rev: string, expressId: number): ElementRef {
  return { model_id: modelId, ifc_revision_id: rev, express_id: expressId };
}

function el(r: ElementRef, ifcClass: string, name: string, guid: string, state: ElementRecord["global_id_state"] = "unique", geo = true): ElementRecord {
  return { ref: r, ifc_class: ifcClass, name, global_id: guid, global_id_state: state, has_geometry: geo };
}

export const LAJE_ARQ = el(ref("m-arq", REV_ARQ, 123), "IfcSlab", "Piso acabado", GUID_LAJE);
export const J01 = el(ref("m-arq", REV_ARQ, 143), "IfcWindow", "J-01 Janela sala", GUID_JANELA, "duplicated_in_file");
export const J02 = el(ref("m-arq", REV_ARQ, 163), "IfcWindow", "J-02 Janela quarto", GUID_JANELA, "duplicated_in_file");
export const PORTA = el(ref("m-arq", REV_ARQ, 183), "IfcDoor", NOME_SCRIPT, "2G3k6AWu1PmheWnEPCH$GS");
export const PROXY = el(ref("m-arq", REV_ARQ, 194), "IfcBuildingElementProxy", "PX-01 Proxy sem geometria", "1T2ZITQTjGgxkvpoEVczV5", "unique", false);
export const LAJE_EST = el(ref("m-est", REV_EST, 123), "IfcSlab", "Laje estrutural", GUID_LAJE);

const GAP_JANELA: Gap = {
  schema_status: "provisorio_aguardando_M2_M3",
  gap_id: "g-janela",
  origin: "legacy_ifc_analyzer",
  resolution: "ambiguous",
  element: null,
  candidates: [J01.ref, J02.ref],
  global_id: GUID_JANELA,
  ifc_class: "IfcWindow",
  element_name: "J-01 Janela sala",
  requirement: { property_set: "Pset_WindowCommon", property_name: "Reference", check: "equals", expected_value: "IMPOSSIVEL", unit: null, specification: "impossível" },
  current_value: null,
  provisional_marker: null,
};

const GAP_LAJE_EST: Gap = {
  schema_status: "provisorio_aguardando_M2_M3",
  gap_id: "g-laje-est",
  origin: "m4_adapter_marker",
  resolution: "resolved",
  element: LAJE_EST.ref,
  candidates: [],
  global_id: GUID_LAJE,
  ifc_class: "IfcSlab",
  element_name: "Laje estrutural",
  requirement: { property_set: "Pset_SlabCommon", property_name: "LoadBearing", check: "is_boolean", expected_value: null, unit: null, specification: "Lajes" },
  current_value: { state: "present", kind: "boolean", value: false },
  provisional_marker: { observed_by: "m4_adapter", marker: "FALSE", classification: "provisorio", note: "nota" },
};

// T4-53: texto do IDS e valor lido do IFC com marcação; fora do fakeApi padrão
// para não mudar a contagem de lacunas dos demais testes.
export const SPEC_SCRIPT = "Portas <script>alert(2)</script>";
export const VALOR_SCRIPT = "<script>alert(3)</script>";

export const GAP_PORTA_SCRIPT: Gap = {
  schema_status: "provisorio_aguardando_M2_M3",
  gap_id: "g-porta-script",
  origin: "legacy_ifc_analyzer",
  resolution: "resolved",
  element: PORTA.ref,
  candidates: [],
  global_id: PORTA.global_id,
  ifc_class: "IfcDoor",
  element_name: NOME_SCRIPT,
  requirement: { property_set: "Pset_DoorCommon", property_name: "Reference", check: "equals", expected_value: "P-01", unit: null, specification: SPEC_SCRIPT },
  current_value: { state: "present", kind: "string", value: VALOR_SCRIPT },
  provisional_marker: null,
};

export function fakeApi(): Api & { [k: string]: ReturnType<typeof vi.fn> } {
  const elementos: Record<string, ElementRecord[]> = { "m-arq": [LAJE_ARQ, J01, J02, PORTA, PROXY], "m-est": [LAJE_EST] };
  const lacunas: Record<string, Gap[]> = { "m-arq": [GAP_JANELA], "m-est": [GAP_LAJE_EST] };
  const revisoes: Record<string, string> = { "m-arq": REV_ARQ, "m-est": REV_EST };
  return {
    createProject: vi.fn(async () => PROJECT),
    getProject: vi.fn(async () => PROJECT),
    uploadSource: vi.fn(async () => ARQ),
    confirm: vi.fn(async () => ARQ),
    listElements: vi.fn(async (_p: string, m: string) => ({
      schema_version: "m4-plataforma-base/1" as const,
      model_id: m,
      ifc_revision_id: revisoes[m],
      total: elementos[m].length,
      items: elementos[m],
    })),
    listGaps: vi.fn(async (_p: string, m: string) => ({
      schema_status: "provisorio_aguardando_M2_M3" as const,
      schema_version: "m4-plataforma-base/1" as const,
      model_id: m,
      ifc_revision_id: revisoes[m],
      ids_revision_id: REV_IDS,
      source: "legado",
      total: lacunas[m].length,
      items: lacunas[m],
      limitations: [],
    })),
    fetchIfc: vi.fn(async (_p: string, m: string) => ({ bytes: new Uint8Array([1, 2, 3]), revision: revisoes[m] })),
  } as unknown as Api & { [k: string]: ReturnType<typeof vi.fn> };
}

export interface FakeViewer extends ViewerAdapter {
  clicar(r: ElementRef | null, motivo?: "vazio" | "nao_comprovado"): void;
  mocks: Record<keyof ViewerAdapter, ReturnType<typeof vi.fn>>;
}

export function fakeViewer(overrides: Partial<Record<keyof ViewerAdapter, (...args: never[]) => unknown>> = {}): FakeViewer {
  const selecao = new Set<(r: ElementRef | null, m?: "vazio" | "nao_comprovado") => void>();
  const estado = new Set<(e: EstadoModelo) => void>();
  const ok = () => vi.fn(async () => undefined);
  const mocks = {
    montar: ok(),
    carregarModelo: ok(),
    descarregar: ok(),
    destacar: ok(),
    isolar: ok(),
    mostrarDisciplina: ok(),
    transparencia: ok(),
    enquadrar: ok(),
    destruir: ok(),
    onSelecionar: vi.fn((cb: (r: ElementRef | null) => void) => {
      selecao.add(cb);
      return () => selecao.delete(cb);
    }),
    onEstado: vi.fn((cb: (e: EstadoModelo) => void) => {
      estado.add(cb);
      return () => estado.delete(cb);
    }),
  } as Record<keyof ViewerAdapter, ReturnType<typeof vi.fn>>;
  for (const [nome, impl] of Object.entries(overrides)) mocks[nome as keyof ViewerAdapter] = vi.fn(impl as never);
  return {
    ...(mocks as unknown as ViewerAdapter),
    mocks,
    clicar: (r, motivo) => selecao.forEach((cb) => cb(r, motivo)),
  };
}
