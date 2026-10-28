// Checklist 3D da M4 (PR #5) automatizado: antes era teste manual.
// Usa o corpus sintético (scripts/m4_gerar_corpus_sintetico.py) e o gancho
// window.__m4 = { adapter, linhas }, exposto só em dev (ReviewWorkspace.tsx).
// Screenshots: M4_SCREENS (padrão: pasta de resultados do Playwright).
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/** Gancho de dev exposto pelo ReviewWorkspace (só os membros usados aqui). */
type Ref = { model_id: string; ifc_revision_id: string; express_id: number };
interface CarregadoE2E {
  model: { getItemsByVisibility: (v: boolean) => Promise<number[]> };
  mapa: { refPorLocal: Map<number, Ref>; localPorChave: Map<string, number> };
}
declare global {
  interface Window {
    __m4: {
      adapter: {
        destacado: Ref | null;
        contorno: unknown;
        modelos: Map<string, CarregadoE2E>;
        destacar: (r: Ref | null) => Promise<void>;
        enquadrar: (r: Ref) => Promise<void>;
        centroNaTela: (r: Ref) => Promise<{ x: number; y: number } | null>;
        raioXAtivo: (modelId: string) => boolean;
      };
      linhas: { binding: { discipline: string; model_id: string }; record: { ref: Ref } }[];
    };
  }
}

const CORPUS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../tests/fixtures/m4/generated");
const LINHAS = [
  { disciplina: "architecture", rotulo: "Arquitetura", base: "arquitetura" },
  { disciplina: "structure", rotulo: "Estrutura", base: "estrutura" },
] as const;

/** Estatística de pixels do viewer, decodificando o PNG no próprio navegador. */
interface Pixels {
  total: number;
  /** Pixels com contraste ≥ 3:1 sobre o fundo amostrado no canto do viewer. */
  contrastantes: number;
  /** Maior contraste encontrado contra o fundo. */
  maxContraste: number;
  fundo: [number, number, number];
}

async function screenshotViewer(page: Page, nome?: string): Promise<Buffer> {
  const viewer = page.getByTestId("viewer-container");
  const dir = process.env.M4_SCREENS ?? test.info().outputDir;
  return viewer.screenshot(nome ? { path: path.join(dir, nome) } : {});
}

async function pixels(page: Page, png: Buffer): Promise<Pixels> {
  return page.evaluate(async (b64) => {
    const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob());
    const cv = new OffscreenCanvas(bmp.width, bmp.height);
    const ctx = cv.getContext("2d")!;
    ctx.drawImage(bmp, 0, 0);
    const { data } = ctx.getImageData(0, 0, bmp.width, bmp.height);
    const lum = (r: number, g: number, b: number) => {
      const c = (v: number) => ((v /= 255) <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
      return 0.2126 * c(r) + 0.7152 * c(g) + 0.0722 * c(b);
    };
    const fundo: [number, number, number] = [data[4 * (bmp.width * 5 + bmp.width - 6)], data[4 * (bmp.width * 5 + bmp.width - 6) + 1], data[4 * (bmp.width * 5 + bmp.width - 6) + 2]];
    const lf = lum(...fundo);
    let contrastantes = 0;
    let maxContraste = 1;
    for (let i = 0; i < data.length; i += 4) {
      const l = lum(data[i], data[i + 1], data[i + 2]);
      const k = (Math.max(l, lf) + 0.05) / (Math.min(l, lf) + 0.05);
      if (k >= 3) contrastantes++;
      if (k > maxContraste) maxContraste = k;
    }
    return { total: data.length / 4, contrastantes, maxContraste, fundo };
  }, png.toString("base64"));
}

/** Fração de pixels que mudaram entre duas capturas do viewer. */
async function diferenca(page: Page, a: Buffer, b: Buffer): Promise<number> {
  return page.evaluate(
    async ([x, y]) => {
      const ler = async (b64: string) => {
        const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob());
        const cv = new OffscreenCanvas(bmp.width, bmp.height);
        const ctx = cv.getContext("2d")!;
        ctx.drawImage(bmp, 0, 0);
        return ctx.getImageData(0, 0, bmp.width, bmp.height).data;
      };
      const [da, db] = [await ler(x), await ler(y)];
      let mudou = 0;
      for (let i = 0; i < da.length; i += 4) {
        if (Math.abs(da[i] - db[i]) + Math.abs(da[i + 1] - db[i + 1]) + Math.abs(da[i + 2] - db[i + 2]) > 24) mudou++;
      }
      return mudou / (da.length / 4);
    },
    [a.toString("base64"), b.toString("base64")],
  );
}

function linha(page: Page, express: number) {
  return page.locator("button[data-chave]", { hasText: new RegExp(`· #${express}(\\D|$)`) });
}

/** Chave do elemento destacado no adaptador (null se nada destacado). */
async function destacado(page: Page): Promise<{ model_id: string; express_id: number } | null> {
  return page.evaluate(() => {
    const a = window.__m4.adapter;
    return a.destacado ? { model_id: a.destacado.model_id, express_id: a.destacado.express_id } : null;
  });
}

async function temContorno(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const a = window.__m4.adapter;
    return a.contorno !== null;
  });
}

async function esperarCena(page: Page): Promise<void> {
  // Duas voltas de animação: o renderer do That Open desenha no frame seguinte.
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForTimeout(400);
}

test.describe.configure({ mode: "serial" });

test.describe("checklist 3D — corpus sintético M4", () => {
  let page: Page;
  const dialogos: string[] = [];
  let modeloPorDisciplina: Record<string, string> = {};

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    page.on("dialog", async (d) => {
      dialogos.push(d.message());
      await d.dismiss();
    });
    await page.goto("/");
    await page.getByLabel("Nome do projeto").fill(`E2E checklist ${Date.now()}`);
    await page.getByRole("button", { name: "Criar projeto" }).click();
    for (const l of LINHAS) {
      const tr = page.getByTestId(`linha-${l.disciplina}`);
      await page.getByLabel(`Enviar IFC (${l.rotulo})`).setInputFiles(path.join(CORPUS, `m4_sintetico_${l.base}.ifc`));
      await expect(tr.getByText(`m4_sintetico_${l.base}.ifc`)).toBeVisible();
      await page.getByLabel(`Enviar IDS (${l.rotulo})`).setInputFiles(path.join(CORPUS, `m4_sintetico_${l.base}.ids`));
      await expect(tr.getByText(`m4_sintetico_${l.base}.ids`)).toBeVisible();
      await tr.getByRole("button", { name: /Confirmar:/ }).click();
      await expect(tr.getByText("Confirmado")).toBeVisible();
    }
    await page.getByRole("button", { name: "Abrir revisão" }).click();
    for (const l of LINHAS) {
      await expect(page.getByTestId(`estado-3d-${l.disciplina}`)).toContainText("pronto", { timeout: 120_000 });
    }
    modeloPorDisciplina = await page.evaluate(() => {
      const linhas = window.__m4.linhas;
      return Object.fromEntries(linhas.map((l) => [l.binding.discipline, l.binding.model_id]));
    });
    await esperarCena(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("barra do 3D: ARQ 8 verificados / 1 sem geometria; EST 9 / 0", async () => {
    const barra = page.getByLabel("Estado dos modelos 3D");
    await expect(barra.locator("li").nth(0)).toContainText("identidade verificada 8, sem geometria no viewer 1");
    await expect(barra.locator("li").nth(1)).toContainText("identidade verificada 9, sem geometria no viewer 0");
    await expect(barra).not.toContainText("divergentes");
    await screenshotViewer(page, "01-inicial.png");
  });

  test("lista → 3D: destaque com contorno de contraste ≥ 3:1 e enquadramento", async () => {
    const antes = await pixels(page, await screenshotViewer(page));
    await linha(page, 66).click(); // W-02 Fachada leste
    await expect.poll(() => destacado(page)).toEqual({ model_id: modeloPorDisciplina.architecture, express_id: 66 });
    await expect.poll(() => temContorno(page)).toBe(true);
    await esperarCena(page);
    const depois = await pixels(page, await screenshotViewer(page, "02-lista-para-3d.png"));
    test.info().annotations.push({
      type: "contraste",
      description: `fundo rgb(${depois.fundo.join(",")}); máx. ${depois.maxContraste.toFixed(2)}:1; pixels ≥3:1 ${antes.contrastantes} → ${depois.contrastantes}`,
    });
    expect(depois.maxContraste).toBeGreaterThanOrEqual(3);
    expect(depois.contrastantes).toBeGreaterThan(antes.contrastantes + 200);
    await expect(page.getByTestId("detalhe-express")).toHaveText("66");
  });

  test("3D → lista: clique no centro de um elemento seleciona a linha e o painel", async () => {
    const ref = { model_id: modeloPorDisciplina.architecture, express_id: 88 }; // W-03 Fachada norte
    await page.evaluate(async (r) => {
      const m4 = window.__m4;
      const alvo = m4.linhas.find((l) => l.record.ref.model_id === r.model_id && l.record.ref.express_id === r.express_id)!;
      await m4.adapter.destacar(null);
      await m4.adapter.enquadrar(alvo.record.ref);
    }, ref);
    await page.waitForTimeout(1500); // fim da animação de câmera
    const centro = await page.evaluate(async (r) => {
      const m4 = window.__m4;
      const alvo = m4.linhas.find((l) => l.record.ref.model_id === r.model_id && l.record.ref.express_id === r.express_id)!;
      return m4.adapter.centroNaTela(alvo.record.ref);
    }, ref);
    expect(centro).not.toBeNull();
    await page.mouse.click(centro!.x, centro!.y);
    await expect(page.getByTestId("detalhe-express")).toHaveText("88");
    await expect(linha(page, 88)).toHaveAttribute("aria-current", "true");
    await expect.poll(() => destacado(page)).toEqual(ref);
    await screenshotViewer(page, "03-3d-para-lista.png");
  });

  test("lajes 2RegXo54: ARQ #123 e EST #187 não se confundem (arquitetura oculta)", async () => {
    await linha(page, 123).click();
    await expect.poll(() => destacado(page)).toEqual({ model_id: modeloPorDisciplina.architecture, express_id: 123 });
    await expect(page.getByTestId("detalhe-express")).toHaveText("123");
    await expect(page.getByTestId("detalhe-arquivo")).toContainText("Arquitetura");

    await page.getByLabel("Mostrar Arquitetura").click();
    await linha(page, 187).click();
    await expect.poll(() => destacado(page)).toEqual({ model_id: modeloPorDisciplina.structure, express_id: 187 });
    await expect.poll(() => temContorno(page)).toBe(true);
    await expect(page.getByTestId("detalhe-express")).toHaveText("187");
    await expect(page.getByTestId("detalhe-arquivo")).toContainText("Estrutura");
    await esperarCena(page);
    const px = await pixels(page, await screenshotViewer(page, "04-laje-est-arq-oculta.png"));
    expect(px.maxContraste).toBeGreaterThanOrEqual(3);
    await page.getByLabel("Mostrar Arquitetura").click();
  });

  test("J-01/J-02 com GUID repetido: cada uma pelo próprio express_id, lacuna ambígua", async () => {
    for (const [express, outro] of [
      [143, 163],
      [163, 143],
    ] as const) {
      await linha(page, express).click();
      await expect(page.getByTestId("detalhe-express")).toHaveText(String(express));
      await expect.poll(() => destacado(page)).toEqual({ model_id: modeloPorDisciplina.architecture, express_id: express });
      const lacuna = page.getByTestId("lacuna").filter({ hasText: "ambígua" });
      await expect(lacuna).toHaveCount(1);
      await expect(lacuna.getByRole("button", { name: `Ver #${outro}` })).toBeVisible();
    }
    await page.getByTestId("lacuna").filter({ hasText: "ambígua" }).getByRole("button", { name: "Ver #163" }).click();
    await expect(page.getByTestId("detalhe-express")).toHaveText("163");
    await screenshotViewer(page, "05-janelas-ambiguas.png");
  });

  test("só com lacuna: lista e 3D isolam os mesmos elementos", async () => {
    const contagem = page.locator("p[aria-live=polite]");
    await expect(contagem).toContainText("18 de 18");
    await page.getByRole("switch", { name: "Só com lacuna no 3D" }).click();
    await expect(contagem).not.toContainText("18 de 18");
    const naLista = await page.locator("button[data-chave]").evaluateAll((bs) => bs.map((b) => b.getAttribute("data-chave")!));
    expect(naLista.length).toBeGreaterThan(0);
    // No 3D, o esperado é a lista restrita aos elementos com identidade verificada no viewer.
    const no3d = () =>
      page.evaluate(async () => {
        const a = window.__m4.adapter;
        const visiveis: string[] = [];
        const mapeados: string[] = [];
        for (const c of a.modelos.values()) {
          mapeados.push(...c.mapa.localPorChave.keys());
          for (const id of await c.model.getItemsByVisibility(true)) {
            const r = c.mapa.refPorLocal.get(id);
            if (r) visiveis.push(`${r.model_id}:${r.ifc_revision_id}:${r.express_id}`);
          }
        }
        return { visiveis: visiveis.sort(), mapeados };
      });
    await expect
      .poll(async () => {
        const { visiveis, mapeados } = await no3d();
        return JSON.stringify(visiveis) === JSON.stringify(naLista.filter((k) => mapeados.includes(k)).sort());
      })
      .toBe(true);
    const { visiveis, mapeados } = await no3d();
    expect(visiveis).toEqual(naLista.filter((k) => mapeados.includes(k)).sort());
    expect(visiveis.length).toBeGreaterThan(0);
    await esperarCena(page);
    await screenshotViewer(page, "06-so-com-lacuna.png");
    await page.getByRole("switch", { name: "Só com lacuna no 3D" }).click();
    await expect(contagem).toContainText("18 de 18");
  });

  test("raio-X: paredes da arquitetura ficam transparentes e voltam ao desligar", async () => {
    await page.evaluate(() => window.__m4.adapter.destacar(null));
    await esperarCena(page);
    const opaco = await screenshotViewer(page, "07a-raiox-desligado.png");
    await page.getByLabel("Arquitetura transparente (raio-X)").click();
    await expect
      .poll(() => page.evaluate((id) => window.__m4.adapter.raioXAtivo(id), modeloPorDisciplina.architecture))
      .toBe(true);
    await esperarCena(page);
    const transparente = await screenshotViewer(page, "07b-raiox-ligado.png");
    const mudou = await diferenca(page, opaco, transparente);
    test.info().annotations.push({ type: "raio-x", description: `pixels alterados ao ligar: ${(mudou * 100).toFixed(1)}%` });
    expect(mudou).toBeGreaterThan(0.02);

    await page.getByLabel("Arquitetura transparente (raio-X)").click();
    await esperarCena(page);
    const deVolta = await screenshotViewer(page);
    expect(await diferenca(page, opaco, deVolta)).toBeLessThan(0.005);
  });

  test("porta com <script> aparece como texto e nada executa", async () => {
    const porta = linha(page, 183);
    await expect(porta).toContainText("Porta <script>alert(1)</script>");
    await porta.click();
    await expect(page.getByTestId("detalhe-nome")).toHaveText("Porta <script>alert(1)</script>");
    expect(await page.locator("script", { hasText: "alert(1)" }).count()).toBe(0);
    expect(dialogos).toEqual([]);
    await screenshotViewer(page, "08-porta-script.png");
  });
});
