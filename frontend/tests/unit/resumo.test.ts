import { describe, expect, it } from "vitest";

import { montarLinhas, resumirRevisao, type ModeloRevisao } from "@/features/review/reviewData";

import { ARQ, EST, fakeApi, J01, J02, LAJE_ARQ, LAJE_EST, PORTA, PROXY } from "../fixtures";

async function modelos(): Promise<ModeloRevisao[]> {
  const api = fakeApi();
  const gaps = async (m: string) => (await api.listGaps("p1", m)).items;
  return [
    { binding: ARQ, elementos: [LAJE_ARQ, J01, J02, PORTA, PROXY], lacunas: await gaps("m-arq") },
    { binding: EST, elementos: [LAJE_EST], lacunas: await gaps("m-est") },
  ];
}

describe("faixa de resumo da revisão", () => {
  it("soma elementos, lacunas, ambíguas e sem geometria dos dois arquivos", async () => {
    const m = await modelos();
    expect(resumirRevisao(m, montarLinhas(m))).toEqual({ elementos: 6, lacunas: 2, ambiguas: 1, semGeometria: 1 });
  });

  it("sem modelo analisado, lacunas e ambíguas ficam indefinidas, não zero", async () => {
    const m = (await modelos()).map((x) => ({ ...x, lacunas: null }));
    expect(resumirRevisao(m, montarLinhas(m))).toMatchObject({ elementos: 6, lacunas: null, ambiguas: null });
  });
});
