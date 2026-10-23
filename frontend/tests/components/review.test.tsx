import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "@/app/App";

import {
  EST,
  fakeApi,
  fakeViewer,
  GAP_PORTA_SCRIPT,
  J01,
  J02,
  LAJE_ARQ,
  LAJE_EST,
  NOME_SCRIPT,
  PROJECT,
  SPEC_SCRIPT,
  VALOR_SCRIPT,
  type FakeViewer,
} from "../fixtures";

async function abrirRevisao(viewer: FakeViewer, api = fakeApi()) {
  render(<App api={api} createViewer={() => viewer} initialProject={PROJECT} initialView="revisao" />);
  const lista = await screen.findByRole("list", { name: "Lista de elementos" });
  return { lista, api };
}

function botaoDaLinha(lista: HTMLElement, nome: string): HTMLElement {
  return within(lista).getByText(nome).closest("button")!;
}

describe("seleção sincronizada pela ElementRef", () => {
  it("selecionar na lista chama destacar e enquadrar com a chave certa", async () => {
    const viewer = fakeViewer();
    const { lista } = await abrirRevisao(viewer);
    await waitFor(() => expect(viewer.mocks.montar).toHaveBeenCalled());

    await userEvent.click(botaoDaLinha(lista, "Piso acabado"));

    await waitFor(() => expect(viewer.mocks.destacar).toHaveBeenCalledWith(LAJE_ARQ.ref));
    expect(viewer.mocks.enquadrar).toHaveBeenCalledWith(LAJE_ARQ.ref);
    expect(viewer.mocks.destacar).not.toHaveBeenCalledWith(LAJE_EST.ref);
    expect(screen.getByTestId("detalhe-chave")).toHaveTextContent(`m-arq:${LAJE_ARQ.ref.ifc_revision_id}:123`);
  });

  it("GlobalId e express_id iguais em dois arquivos não se confundem (lista → 3D e 3D → lista)", async () => {
    const viewer = fakeViewer();
    const { lista } = await abrirRevisao(viewer);
    await waitFor(() => expect(viewer.mocks.montar).toHaveBeenCalled());

    await userEvent.click(botaoDaLinha(lista, "Laje estrutural"));
    await waitFor(() => expect(viewer.mocks.destacar).toHaveBeenLastCalledWith(LAJE_EST.ref));
    expect(screen.getByTestId("detalhe-arquivo")).toHaveTextContent(`Estrutura · ${EST.ifc!.display_name}`);

    act(() => viewer.clicar(LAJE_ARQ.ref));
    await waitFor(() => expect(screen.getByTestId("detalhe-arquivo")).toHaveTextContent("Arquitetura · arq.ifc"));
    expect(botaoDaLinha(lista, "Piso acabado")).toHaveAttribute("aria-current", "true");
    expect(botaoDaLinha(lista, "Laje estrutural")).not.toHaveAttribute("aria-current");
  });

  it("GlobalId repetido no mesmo arquivo: cada janela é selecionada pelo próprio express_id", async () => {
    const viewer = fakeViewer();
    const { lista } = await abrirRevisao(viewer);
    await waitFor(() => expect(viewer.mocks.montar).toHaveBeenCalled());

    await userEvent.click(botaoDaLinha(lista, "J-02 Janela quarto"));
    await waitFor(() => expect(viewer.mocks.destacar).toHaveBeenLastCalledWith(J02.ref));
    expect(viewer.mocks.destacar).not.toHaveBeenCalledWith(J01.ref);
    expect(screen.getByTestId("detalhe-express")).toHaveTextContent("163");
    expect(screen.getByText(/repetido neste arquivo/)).toBeInTheDocument();
    expect(screen.getByText("ambígua")).toBeInTheDocument();
  });

  it("clique 3D sem identidade comprovada não seleciona nada", async () => {
    const viewer = fakeViewer();
    await abrirRevisao(viewer);
    await waitFor(() => expect(viewer.mocks.montar).toHaveBeenCalled());
    act(() => viewer.clicar(null, "nao_comprovado"));
    expect(await screen.findByText(/sem identidade comprovada/)).toBeInTheDocument();
    expect(screen.queryByTestId("detalhe-chave")).not.toBeInTheDocument();
  });
});

describe("falha do viewer", () => {
  it("falha ao montar o 3D não derruba a lista nem o painel", async () => {
    const viewer = fakeViewer({ montar: async () => Promise.reject(new Error("WebGL indisponível")) });
    const { lista } = await abrirRevisao(viewer);

    expect(await screen.findByText("Visualização 3D indisponível")).toBeInTheDocument();
    expect(screen.getByText(/WebGL indisponível/)).toBeInTheDocument();

    await userEvent.click(botaoDaLinha(lista, "Laje estrutural"));
    expect(screen.getByTestId("detalhe-arquivo")).toHaveTextContent("Estrutura");
    expect(viewer.mocks.destacar).not.toHaveBeenCalled();
    expect(viewer.mocks.carregarModelo).not.toHaveBeenCalled();
  });

  it("falha 3D em um modelo mantém o outro e oferece tentar novamente", async () => {
    const viewer = fakeViewer({
      carregarModelo: async (m: { modelId: string }) => {
        if (m.modelId === "m-arq") throw new Error("conversão falhou");
      },
    });
    await abrirRevisao(viewer);
    expect(await screen.findByText(/Falha 3D neste modelo: conversão falhou/)).toBeInTheDocument();
    expect(viewer.mocks.carregarModelo).toHaveBeenCalledTimes(2);
    await userEvent.click(screen.getByRole("button", { name: /Tentar novamente/ }));
    await waitFor(() => expect(viewer.mocks.carregarModelo).toHaveBeenCalledTimes(3));
  });
});

/** Texto literal no DOM: escapado no HTML serializado e sem nenhum <script> criado. */
function esperarInerte(alvo: HTMLElement, texto: string): void {
  expect(alvo.textContent).toContain(texto);
  expect(alvo.innerHTML).toContain("&lt;script&gt;");
  expect(alvo.querySelector("script")).toBeNull();
  expect(document.querySelector("script")).toBeNull();
}

function apiComLacunaDaPorta(): ReturnType<typeof fakeApi> {
  const api = fakeApi();
  const original = api.listGaps;
  api.listGaps = vi.fn(async (p: string, m: string) => {
    const lista = await original(p, m);
    return m === "m-arq" ? { ...lista, total: lista.total + 1, items: [...lista.items, GAP_PORTA_SCRIPT] } : lista;
  });
  return api;
}

describe("conteúdo do IFC é dado inerte (T4-53)", () => {
  it("nome com <script> aparece como texto e não cria elemento script", async () => {
    const viewer = fakeViewer();
    const { lista } = await abrirRevisao(viewer);
    expect(within(lista).getByText(NOME_SCRIPT)).toBeInTheDocument();
    esperarInerte(lista, NOME_SCRIPT);
  });

  it("painel de detalhe: nome, especificação do IDS e valor atual com <script> são texto", async () => {
    const viewer = fakeViewer();
    const { lista } = await abrirRevisao(viewer, apiComLacunaDaPorta());

    await userEvent.click(botaoDaLinha(lista, NOME_SCRIPT));

    const nome = await screen.findByTestId("detalhe-nome");
    expect(nome).toHaveTextContent(NOME_SCRIPT);
    esperarInerte(nome, NOME_SCRIPT);

    const lacuna = screen.getByTestId("lacuna");
    expect(lacuna).toHaveTextContent(`Regra: ${SPEC_SCRIPT}`);
    expect(lacuna).toHaveTextContent(`Atual no IFC: “${VALOR_SCRIPT}”`);
    esperarInerte(lacuna, SPEC_SCRIPT);
    esperarInerte(lacuna, VALOR_SCRIPT);
  });

  it("aviso do viewer no ReviewWorkspace mostra a mensagem de erro com <script> como texto", async () => {
    const erro = "<script>alert(4)</script>";
    const viewer = fakeViewer({ destacar: async () => Promise.reject(new Error(erro)) });
    const { lista } = await abrirRevisao(viewer);
    await waitFor(() => expect(viewer.mocks.montar).toHaveBeenCalled());

    await userEvent.click(botaoDaLinha(lista, "Piso acabado"));

    const aviso = await screen.findByRole("status");
    expect(aviso).toHaveTextContent(`3D: ${erro}`);
    esperarInerte(aviso, erro);
  });

  it("falha ao montar o viewer com <script> na mensagem aparece como detalhe técnico literal", async () => {
    const erro = "WebGL <script>alert(5)</script>";
    const viewer = fakeViewer({ montar: async () => Promise.reject(new Error(erro)) });
    await abrirRevisao(viewer);

    const detalhe = await screen.findByText(/Detalhe técnico:/);
    expect(detalhe).toHaveTextContent(`Detalhe técnico: ${erro}`);
    esperarInerte(detalhe, erro);
  });
});

describe("filtros e controles", () => {
  it("'só com lacuna' filtra a lista e isola no 3D somente elementos com lacuna", async () => {
    const viewer = fakeViewer();
    const { lista } = await abrirRevisao(viewer);
    await waitFor(() => expect(viewer.mocks.isolar).toHaveBeenCalledWith(null));

    await userEvent.click(screen.getByRole("switch", { name: "Só com lacuna" }));
    expect(within(lista).queryByText("Piso acabado")).not.toBeInTheDocument();
    expect(within(lista).getByText("J-01 Janela sala")).toBeInTheDocument();
    await waitFor(() => expect(viewer.mocks.isolar).toHaveBeenLastCalledWith([J01.ref, J02.ref, LAJE_EST.ref]));
  });

  it("desligar estrutura e ligar raio-X chamam o adaptador por model_id", async () => {
    const viewer = fakeViewer();
    await abrirRevisao(viewer);
    await waitFor(() => expect(viewer.mocks.montar).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("switch", { name: "Mostrar Estrutura" }));
    await waitFor(() => expect(viewer.mocks.mostrarDisciplina).toHaveBeenCalledWith("m-est", false));
    await userEvent.click(screen.getByRole("switch", { name: "Arquitetura transparente (raio-X)" }));
    await waitFor(() => expect(viewer.mocks.transparencia).toHaveBeenCalledWith("m-arq", true));
  });

  it("busca por GlobalId mostra as duas lajes, cada uma com seu arquivo", async () => {
    const viewer = fakeViewer();
    const { lista } = await abrirRevisao(viewer);
    // fireEvent: no jsdom todo retângulo mede 0 e o react-resizable-panels trata o
    // pointerdown como "sobre o separador" (preventDefault), impedindo o foco do
    // userEvent. A digitação real é conferida no navegador (ensaio manual).
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar elemento" }), { target: { value: "2RegXo54" } });
    expect(within(lista).getByText("Piso acabado")).toBeInTheDocument();
    expect(within(lista).getByText("Laje estrutural")).toBeInTheDocument();
    expect(within(lista).getAllByRole("button")).toHaveLength(2);
  });
});
