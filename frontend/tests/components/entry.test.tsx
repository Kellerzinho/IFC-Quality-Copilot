import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { App } from "@/app/App";
import type { Project } from "@/shared/types";

import { fakeApi, fakeViewer, PROJECT, REV_ARQ, REV_IDS } from "../fixtures";

const SEM_CONFIRMACAO: Project = {
  ...PROJECT,
  models: PROJECT.models.map((m) => ({ ...m, confirmed: false, confirmed_ifc_revision_id: null, confirmed_ids_revision_id: null })),
};

describe("entrada do projeto", () => {
  it("mostra as linhas arquitetura e estrutura com revisões", () => {
    render(<App api={fakeApi()} createViewer={() => fakeViewer()} initialProject={SEM_CONFIRMACAO} />);
    expect(within(screen.getByTestId("linha-architecture")).getByText("Arquitetura")).toBeInTheDocument();
    expect(within(screen.getByTestId("linha-structure")).getByText("Estrutura")).toBeInTheDocument();
    expect(within(screen.getByTestId("linha-architecture")).getByText(/rev aaaaaaaaaaaa/)).toBeInTheDocument();
  });

  it("confirmação é explícita por linha e envia as revisões exibidas", async () => {
    const api = fakeApi();
    render(<App api={api} createViewer={() => fakeViewer()} initialProject={SEM_CONFIRMACAO} />);
    const linha = screen.getByTestId("linha-architecture");
    await userEvent.click(within(linha).getByRole("button", { name: /Confirmar/ }));
    expect(api.confirm).toHaveBeenCalledWith("p1", "m-arq", REV_ARQ, REV_IDS);
  });

  it("o upload vai para a linha escolhida, independentemente do nome do arquivo", async () => {
    const api = fakeApi();
    render(<App api={api} createViewer={() => fakeViewer()} initialProject={SEM_CONFIRMACAO} />);
    const arquivo = new File(["ISO-10303-21;"], "estrutura_parece.ifc");
    await userEvent.upload(screen.getByLabelText("Enviar IFC (Arquitetura)"), arquivo);
    expect(api.uploadSource).toHaveBeenCalledWith("p1", "m-arq", "ifc", arquivo, "estrutura_parece.ifc");
  });
});
