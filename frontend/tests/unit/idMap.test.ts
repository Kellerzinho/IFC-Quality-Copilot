import { describe, expect, it, vi } from "vitest";

import { coletarFatos, construirMapa, resumoMapa, type FatoViewer } from "@/features/viewer/idMap";
import { elementKey } from "@/shared/elementKey";

import { GUID_JANELA, GUID_LAJE, J01, J02, LAJE_ARQ, LAJE_EST, PROXY } from "../fixtures";

function fatos(...lista: FatoViewer[]): Map<number, FatoViewer> {
  return new Map(lista.map((f) => [f.localId, f]));
}

describe("mapa explícito id do viewer ↔ ElementRef (T4-05)", () => {
  it("vincula só quando classe e GlobalId conferem", () => {
    const mapa = construirMapa(
      "m-arq",
      [LAJE_ARQ, J01, J02],
      fatos(
        { localId: 123, categoria: "IFCSLAB", guid: GUID_LAJE },
        { localId: 143, categoria: "IFCWINDOW", guid: GUID_JANELA },
        { localId: 163, categoria: "IFCWINDOW", guid: GUID_JANELA },
      ),
    );
    expect(mapa.refPorLocal.get(143)).toEqual(J01.ref);
    expect(mapa.refPorLocal.get(163)).toEqual(J02.ref);
    expect(mapa.localPorChave.get(elementKey(LAJE_ARQ.ref))).toBe(123);
    expect(resumoMapa(mapa)).toEqual({ verificados: 3, semGeometria: 0, divergentes: 0 });
  });

  it("classe ou GlobalId divergente não vincula (clique desabilitado)", () => {
    const mapa = construirMapa(
      "m-arq",
      [LAJE_ARQ, J01],
      fatos({ localId: 123, categoria: "IFCWALL", guid: GUID_LAJE }, { localId: 143, categoria: "IFCWINDOW", guid: "outro" }),
    );
    expect(mapa.refPorLocal.size).toBe(0);
    expect(mapa.situacao.get(elementKey(LAJE_ARQ.ref))).toBe("divergente");
    expect(mapa.situacao.get(elementKey(J01.ref))).toBe("divergente");
  });

  it("elemento sem geometria no viewer fica fora do mapa, sem sumir da lista", () => {
    const mapa = construirMapa("m-arq", [PROXY], fatos());
    expect(mapa.situacao.get(elementKey(PROXY.ref))).toBe("sem_geometria");
    expect(mapa.refPorLocal.size).toBe(0);
  });

  it("mesmo express_id em outro modelo nunca entra neste mapa", () => {
    const mapa = construirMapa("m-arq", [LAJE_EST], fatos({ localId: 123, categoria: "IFCSLAB", guid: GUID_LAJE }));
    expect(mapa.refPorLocal.size).toBe(0);
    expect(mapa.situacao.get(elementKey(LAJE_EST.ref))).toBe("divergente");
  });
});

describe("fatos do viewer (Fragments)", () => {
  it("usa os ids de getItemsIdsWithGeometry como localIds, sem retraduzir", async () => {
    const model = {
      getItemsIdsWithGeometry: vi.fn(async () => [183, 123, 143]),
      getGuidsByLocalIds: vi.fn(async (ids: number[]) => ids.map((id) => `g${id}`)),
      getItemsOfCategories: vi.fn(async () => ({ IFCDOOR: [183], IFCSLAB: [123], IFCWINDOW: [143] })),
      getLocalIdsFromItemIds: vi.fn(),
    };
    const fatos = await coletarFatos(model);
    expect([...fatos.keys()]).toEqual([183, 123, 143]);
    expect(fatos.get(143)).toEqual({ localId: 143, categoria: "IFCWINDOW", guid: "g143" });
    expect(model.getLocalIdsFromItemIds).not.toHaveBeenCalled();
  });
});
