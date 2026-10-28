import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "@/app/App";
import { ApiFailure } from "@/shared/api";
import type { ProjectList } from "@/shared/types";

import { ARQ, EST, fakeApi, fakeViewer, PROJECT } from "../fixtures";

const LISTA: ProjectList = {
  schema_version: "m4-plataforma-base/1",
  total: 2,
  items: [
    {
      project_id: "p2",
      name: "Obra <b>nova</b>",
      created_at: "2026-10-28T12:00:00Z",
      updated_at: "2026-10-28T15:30:00Z",
      models: [{ ...ARQ, project_id: "p2", ifc: null, ids: null, confirmed: false, confirmed_ifc_revision_id: null, confirmed_ids_revision_id: null }],
    },
    { project_id: "p1", name: "Projeto teste", created_at: "2026-10-27T09:00:00Z", updated_at: "2026-10-27T10:00:00Z", models: [ARQ, EST] },
  ],
};

function apiComLista(lista: ProjectList = LISTA) {
  const api = fakeApi();
  vi.mocked(api.listProjects).mockResolvedValue(lista);
  return api;
}

describe("projetos recentes na entrada", () => {
  it("lista os projetos na ordem do servidor, com modelos e revisões", async () => {
    render(<App api={apiComLista()} createViewer={() => fakeViewer()} />);
    const itens = within(await screen.findByRole("list", { name: "Projetos recentes" })).getAllByRole("listitem");
    expect(itens).toHaveLength(2);
    expect(itens[0]).toHaveTextContent("Obra <b>nova</b>");
    expect(itens[0]).toHaveTextContent("sem IFC");
    expect(itens[1]).toHaveTextContent("arq.ifc");
    expect(itens[1]).toHaveTextContent("aaaaaaaa");
    expect(itens[1]).toHaveTextContent("confirmado");
    expect(within(itens[1]).getByText(/Alterado em/).querySelector("time")).toHaveAttribute("dateTime", "2026-10-27T10:00:00Z");
  });

  it("nome com marcação aparece como texto", async () => {
    render(<App api={apiComLista()} createViewer={() => fakeViewer()} />);
    expect(await screen.findByText("Obra <b>nova</b>")).toBeInTheDocument();
    expect(document.querySelector("b")).toBeNull();
  });

  it("abrir busca o projeto pelo id e mostra as linhas dele", async () => {
    const api = apiComLista();
    render(<App api={api} createViewer={() => fakeViewer()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Projeto teste" }));
    expect(api.getProject).toHaveBeenCalledWith("p1");
    expect(await screen.findByTestId("linha-architecture")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abrir revisão" })).toBeEnabled();
  });

  it("mantém o novo projeto disponível", async () => {
    const api = apiComLista();
    render(<App api={api} createViewer={() => fakeViewer()} />);
    await screen.findByRole("list", { name: "Projetos recentes" });
    await userEvent.type(screen.getByLabelText("Nome do projeto"), "Outra obra");
    await userEvent.click(screen.getByRole("button", { name: "Criar projeto" }));
    expect(api.createProject).toHaveBeenCalledWith("Outra obra");
  });

  it("sem projetos salvos, avisa e oferece criar", async () => {
    render(<App api={fakeApi()} createViewer={() => fakeViewer()} />);
    expect(await screen.findByText(/Nenhum projeto salvo ainda/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Criar projeto" })).toBeInTheDocument();
  });

  it("falha na listagem não bloqueia o novo projeto e permite tentar de novo", async () => {
    const api = fakeApi();
    vi.mocked(api.listProjects).mockRejectedValueOnce(new ApiFailure(403, "origem_recusada", "Origem não permitida para a API local."));
    vi.mocked(api.listProjects).mockResolvedValueOnce(LISTA);
    render(<App api={api} createViewer={() => fakeViewer()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Origem não permitida");
    expect(screen.getByRole("button", { name: "Criar projeto" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Tentar novamente/ }));
    expect(await screen.findByText("Projeto teste")).toBeInTheDocument();
  });

  it("falha ao abrir mostra o erro e continua na lista", async () => {
    const api = apiComLista();
    vi.mocked(api.getProject).mockRejectedValueOnce(new ApiFailure(404, "projeto_inexistente", "Projeto não encontrado."));
    render(<App api={api} createViewer={() => fakeViewer()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Projeto teste" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Projeto não encontrado.");
    expect(screen.getByRole("list", { name: "Projetos recentes" })).toBeInTheDocument();
  });

  it("'Outro projeto' volta para a escolha", async () => {
    render(<App api={apiComLista()} createViewer={() => fakeViewer()} initialProject={PROJECT} />);
    await userEvent.click(screen.getByRole("button", { name: "Outro projeto" }));
    expect(await screen.findByRole("list", { name: "Projetos recentes" })).toBeInTheDocument();
  });
});
