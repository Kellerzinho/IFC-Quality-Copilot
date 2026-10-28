// Abrir projeto existente pela lista "Projetos recentes" (API real, armazenamento temporário).
import { expect, test } from "@playwright/test";

test("projeto criado aparece nos recentes e reabre com as duas linhas", async ({ page }) => {
  const nome = `E2E reabrir ${Date.now()}`;
  await page.goto("/");
  await expect(page.getByText("Projetos recentes", { exact: true })).toBeVisible();
  await page.getByLabel("Nome do projeto").fill(nome);
  await page.getByRole("button", { name: "Criar projeto" }).click();
  await expect(page.getByTestId("linha-architecture")).toBeVisible();

  await page.getByRole("button", { name: "Outro projeto" }).click();
  const recentes = page.getByRole("list", { name: "Projetos recentes" });
  await expect(recentes.getByRole("listitem").first()).toContainText(nome);
  await recentes.getByRole("button", { name: `Abrir ${nome}` }).click();

  await expect(page.getByText(nome)).toBeVisible();
  await expect(page.getByTestId("linha-architecture")).toBeVisible();
  await expect(page.getByTestId("linha-structure")).toBeVisible();
});
