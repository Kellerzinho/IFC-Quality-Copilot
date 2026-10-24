import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DetailPanel } from "@/features/detail/DetailPanel";
import { montarLinhas, type ModeloRevisao } from "@/features/review/reviewData";

import { ARQ, LAJE_ARQ, REV_ARQ } from "../fixtures";

const modelos: ModeloRevisao[] = [{ binding: ARQ, elementos: [LAJE_ARQ], lacunas: [] }];
const [linha] = montarLinhas(modelos);

afterEach(() => vi.unstubAllGlobals());

describe("painel de detalhe", () => {
  it("chave e revisão longas ficam inteiras no DOM e no title, truncadas só no visual", () => {
    render(<DetailPanel linha={linha} modelos={modelos} onIrPara={() => {}} />);
    const chave = screen.getByTestId("detalhe-chave");
    expect(chave).toHaveTextContent(`m-arq:${REV_ARQ}:123`);
    expect(chave).toHaveAttribute("title", linha.chave);
    expect(chave).toHaveClass("truncate");
    expect(screen.getByTitle(REV_ARQ)).toHaveTextContent(REV_ARQ);
  });

  it("copiar chave grava o valor completo na área de transferência", async () => {
    const writeText = vi.fn(async () => {});
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(<DetailPanel linha={linha} modelos={modelos} onIrPara={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Copiar chave" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(linha.chave));
    expect(await screen.findByRole("button", { name: "chave copiada" })).toBeInTheDocument();
  });
});
