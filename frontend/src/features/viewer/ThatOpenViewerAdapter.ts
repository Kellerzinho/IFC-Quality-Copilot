// PROVISÓRIO — escolha definitiva na M4-03 (comparação de viewers ainda não feita).
//
// Adaptador That Open (@thatopen/components 3.4.9 + @thatopen/fragments 3.4.8 +
// web-ifc 0.0.77, fixado: o build de navegador da 0.0.78 quebra StreamMeshes). Decisões desta fatia:
// - Ativos locais: WASM em /viewer/web-ifc.wasm e worker do Fragments em
//   /viewer/fragments-worker.mjs (scripts/copy-viewer-assets.mjs). Nunca usa
//   autoSetWasm nem FragmentsManager.getWorker(), que buscam no unpkg.
// - Coordenadas: COORDINATE_TO_ORIGIN = false na conversão e autoCoordinate = false
//   no carregamento. Os dois modelos ficam nas coordenadas do próprio IFC, sem
//   deslocamento por modelo nem "base" do primeiro carregado; a ordem A→B / B→A
//   não altera a posição relativa. Risco conhecido: coordenadas muito grandes
//   (georreferenciadas) podem perder precisão visual — não há origem comum aqui.
// - Identidade: mapa explícito e verificado (idMap.ts); clique sem vínculo
//   comprovado não seleciona.
import * as OBC from "@thatopen/components";
import * as FRAGS from "@thatopen/fragments";
import * as THREE from "three";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";

import { elementKey } from "@/shared/elementKey";
import type { ElementRef } from "@/shared/types";

import { coletarFatos, construirMapa, resumoMapa, type MapaIdentidade } from "./idMap";
import { aplicarRaioX, arestasDoItem, corContorno, type MemoriaRaioX } from "./realce";
import type { EstadoModelo, ModeloParaCarregar, ViewerAdapter } from "./ViewerPort";

export const VIEWER_ASSETS = {
  wasmPath: "/viewer/",
  fragmentsWorker: "/viewer/fragments-worker.mjs",
} as const;

const COR_DESTAQUE = new THREE.Color("#f59e0b");
const OPACIDADE_RAIO_X = 0.15;
/** Espessura do contorno do destaque, em px de tela. */
const ESPESSURA_CONTORNO = 3;

type Mundo = OBC.SimpleWorld<OBC.SimpleScene, OBC.SimpleCamera, OBC.SimpleRenderer>;

interface ModeloCarregado {
  model: FRAGS.FragmentsModel;
  mapa: MapaIdentidade;
  visivel: boolean;
  raioX: boolean;
}

/** Converte IFC → Fragments num worker dedicado (não bloqueia a UI). */
class ConversorIfc {
  private worker: Worker | null = null;
  private proximo = 0;
  private pendentes = new Map<number, { resolve: (b: Uint8Array) => void; reject: (e: Error) => void }>();

  converter(bytes: Uint8Array): Promise<Uint8Array> {
    if (!this.worker) {
      this.worker = new Worker(new URL("./ifcConversion.worker.ts", import.meta.url), { type: "module" });
      this.worker.onmessage = (ev: MessageEvent<{ id: number; ok: boolean; bytes?: Uint8Array; mensagem?: string }>) => {
        const pendente = this.pendentes.get(ev.data.id);
        if (!pendente) return;
        this.pendentes.delete(ev.data.id);
        if (ev.data.ok && ev.data.bytes) pendente.resolve(ev.data.bytes);
        else pendente.reject(new Error(ev.data.mensagem ?? "falha na conversão IFC"));
      };
      this.worker.onerror = (ev) => {
        for (const p of this.pendentes.values()) p.reject(new Error(ev.message || "falha no worker de conversão"));
        this.pendentes.clear();
      };
    }
    const id = this.proximo++;
    return new Promise((resolve, reject) => {
      this.pendentes.set(id, { resolve, reject });
      const copia = bytes.slice();
      this.worker!.postMessage({ id, bytes: copia, wasmPath: VIEWER_ASSETS.wasmPath }, [copia.buffer]);
    });
  }

  encerrar(): void {
    this.worker?.terminate();
    this.worker = null;
    for (const p of this.pendentes.values()) p.reject(new Error("viewer encerrado"));
    this.pendentes.clear();
  }
}

export class ThatOpenViewerAdapter implements ViewerAdapter {
  private components: OBC.Components | null = null;
  private world: Mundo | null = null;
  private fragments: OBC.FragmentsManager | null = null;
  private container: HTMLElement | null = null;
  private readonly modelos = new Map<string, ModeloCarregado>();
  private readonly conversor = new ConversorIfc();
  private readonly ouvintesSelecao = new Set<Parameters<ViewerAdapter["onSelecionar"]>[0]>();
  private readonly ouvintesEstado = new Set<(e: EstadoModelo) => void>();
  private destacado: ElementRef | null = null;
  private isolamento: Set<string> | null = null;
  private cancelados = new Set<string>();
  private removerClique: (() => void) | null = null;
  /** Raio-X pedido por modelo — vale também para modelo que ainda está carregando. */
  private readonly raioXPedido = new Map<string, boolean>();
  private readonly memoriaRaioX: MemoriaRaioX = new WeakMap();
  private contorno: LineSegments2 | null = null;
  /** Cada destacar() invalida contornos ainda em construção de chamadas anteriores. */
  private seqDestaque = 0;

  async montar(container: HTMLElement): Promise<void> {
    this.container = container;
    const components = new OBC.Components();
    const world = components.get(OBC.Worlds).create<OBC.SimpleScene, OBC.SimpleCamera, OBC.SimpleRenderer>();
    world.scene = new OBC.SimpleScene(components);
    world.scene.setup();
    world.scene.three.background = new THREE.Color("#f5f5f5");
    world.renderer = new OBC.SimpleRenderer(components, container);
    world.camera = new OBC.SimpleCamera(components);
    components.init();

    const fragments = components.get(OBC.FragmentsManager);
    fragments.init(VIEWER_ASSETS.fragmentsWorker);
    fragments.core.settings.autoCoordinate = false;
    world.camera.controls.addEventListener("rest", () => void this.atualizarCena());

    this.components = components;
    this.world = world;
    this.fragments = fragments;
    this.removerClique = this.instalarClique(world.renderer.three.domElement);
  }

  private instalarClique(dom: HTMLCanvasElement): () => void {
    let inicio: { x: number; y: number } | null = null;
    const down = (ev: PointerEvent) => {
      inicio = { x: ev.clientX, y: ev.clientY };
    };
    const up = (ev: PointerEvent) => {
      if (!inicio || Math.hypot(ev.clientX - inicio.x, ev.clientY - inicio.y) > 4) return; // arrasto de câmera
      inicio = null;
      void this.resolverClique(ev.clientX, ev.clientY);
    };
    dom.addEventListener("pointerdown", down);
    dom.addEventListener("pointerup", up);
    return () => {
      dom.removeEventListener("pointerdown", down);
      dom.removeEventListener("pointerup", up);
    };
  }

  /** Clique em coordenadas de tela → ElementRef verificada (ou null). */
  async resolverClique(clientX: number, clientY: number): Promise<ElementRef | null> {
    if (!this.fragments || !this.world) return null;
    const resultado = await this.fragments.raycast({
      camera: this.world.camera.three,
      mouse: new THREE.Vector2(clientX, clientY),
      dom: this.world.renderer!.three.domElement,
    });
    if (!resultado) {
      this.emitirSelecao(null, "vazio");
      return null;
    }
    const carregado = this.modelos.get(resultado.fragments.modelId);
    const ref = carregado?.mapa.refPorLocal.get(resultado.localId) ?? null;
    this.emitirSelecao(ref, ref ? undefined : "nao_comprovado");
    return ref;
  }

  private emitirSelecao(ref: ElementRef | null, motivo?: "vazio" | "nao_comprovado"): void {
    for (const cb of this.ouvintesSelecao) cb(ref, motivo);
  }

  private emitirEstado(estado: EstadoModelo): void {
    for (const cb of this.ouvintesEstado) cb(estado);
  }

  async carregarModelo(modelo: ModeloParaCarregar): Promise<void> {
    if (!this.fragments || !this.world) throw new Error("viewer não montado");
    const inicio = performance.now();
    const decorrido = () => Math.round(performance.now() - inicio);
    this.cancelados.delete(modelo.modelId);
    if (this.modelos.has(modelo.modelId)) await this.descarregar(modelo.modelId);
    try {
      this.emitirEstado({ modelId: modelo.modelId, etapa: "convertendo", decorridoMs: 0 });
      const fragBytes = await this.conversor.converter(modelo.bytes);
      if (this.cancelados.has(modelo.modelId)) return; // removido durante a carga: não ressuscitar
      this.emitirEstado({ modelId: modelo.modelId, etapa: "carregando", decorridoMs: decorrido() });
      const model = await this.fragments.core.load(fragBytes, { modelId: modelo.modelId });
      if (this.cancelados.has(modelo.modelId)) {
        await this.fragments.core.disposeModel(modelo.modelId);
        return;
      }
      model.useCamera(this.world.camera.three);
      this.world.scene.three.add(model.object);
      const mapa = construirMapa(modelo.modelId, modelo.elementos, await coletarFatos(model));
      this.modelos.set(modelo.modelId, {
        model,
        mapa,
        visivel: true,
        raioX: this.raioXPedido.get(modelo.modelId) ?? false,
      });
      await this.atualizarCena();
      if (this.modelos.size === 1) await this.enquadrarTudo();
      await this.aplicarVisibilidade();
      await new Promise<void>((r) => requestAnimationFrame(() => r()));
      this.emitirEstado({ modelId: modelo.modelId, etapa: "pronto", decorridoMs: decorrido(), mapa: resumoMapa(mapa) });
    } catch (erro) {
      const mensagem = erro instanceof Error ? erro.message : String(erro);
      this.emitirEstado({ modelId: modelo.modelId, etapa: "falhou", decorridoMs: decorrido(), mensagem });
      throw erro;
    }
  }

  private async enquadrarTudo(): Promise<void> {
    if (!this.world) return;
    const caixa = new THREE.Box3();
    for (const { model } of this.modelos.values()) caixa.union(model.box);
    if (caixa.isEmpty()) return;
    await this.world.camera.controls.fitToSphere(caixa.getBoundingSphere(new THREE.Sphere()), false);
  }

  async descarregar(modelId: string): Promise<void> {
    this.cancelados.add(modelId);
    const carregado = this.modelos.get(modelId);
    if (!carregado || !this.fragments) return;
    this.modelos.delete(modelId);
    await this.fragments.core.disposeModel(modelId);
    this.emitirEstado({ modelId, etapa: "descarregado", decorridoMs: 0 });
  }

  private localDe(ref: ElementRef): { carregado: ModeloCarregado; localId: number } | null {
    const carregado = this.modelos.get(ref.model_id);
    const localId = carregado?.mapa.localPorChave.get(elementKey(ref));
    return carregado && localId !== undefined ? { carregado, localId } : null;
  }

  /** Atualiza os tiles do Fragments e reaplica o raio-X nos materiais recém-criados. */
  private async atualizarCena(): Promise<void> {
    await this.fragments?.core.update(true);
    for (const carregado of this.modelos.values()) {
      aplicarRaioX(carregado.model.object, carregado.raioX, OPACIDADE_RAIO_X, this.memoriaRaioX);
    }
  }

  async destacar(ref: ElementRef | null): Promise<void> {
    if (this.destacado) {
      const anterior = this.localDe(this.destacado);
      if (anterior) await anterior.carregado.model.resetHighlight([anterior.localId]);
    }
    this.removerContorno();
    const seq = ++this.seqDestaque;
    this.destacado = ref;
    const alvo = ref ? this.localDe(ref) : null;
    if (alvo) {
      await alvo.carregado.model.highlight([alvo.localId], {
        color: COR_DESTAQUE,
        renderedFaces: FRAGS.RenderedFaces.TWO,
        opacity: 1,
        transparent: false,
      });
      await this.criarContorno(alvo.carregado.model, alvo.localId, seq);
    }
    await this.atualizarCena();
  }

  /**
   * Contorno escuro (ou claro, conforme o fundo) sobre as arestas do elemento.
   * A cor de destaque sozinha tem contraste ~1,9:1 sobre o fundo claro; o contorno
   * passa de 3:1 nos dois temas (realce.ts). depthTest desligado: o contorno
   * aparece mesmo quando o elemento está atrás de outro (laje EST sob o piso ARQ).
   */
  private async criarContorno(model: FRAGS.FragmentsModel, localId: number, seq: number): Promise<void> {
    if (!this.world) return;
    const [malhas = []] = await model.getItemsGeometry([localId]);
    const pontos = arestasDoItem(malhas);
    if (!pontos.length || seq !== this.seqDestaque) return;
    const geometria = new LineSegmentsGeometry().setPositions(pontos);
    const fundo = this.world.scene.three.background;
    const material = new LineMaterial({
      color: corContorno(fundo instanceof THREE.Color ? fundo : "#f5f5f5"),
      linewidth: ESPESSURA_CONTORNO,
      depthTest: false,
      transparent: true,
    });
    const tela = this.world.renderer!.three.domElement;
    material.resolution.set(tela.clientWidth || 1, tela.clientHeight || 1);
    const linhas = new LineSegments2(geometria, material);
    linhas.applyMatrix4(model.object.matrixWorld);
    linhas.renderOrder = 10;
    linhas.name = "m4-contorno-destaque";
    this.world.scene.three.add(linhas);
    this.contorno = linhas;
  }

  private removerContorno(): void {
    if (!this.contorno) return;
    this.contorno.removeFromParent();
    this.contorno.geometry.dispose();
    this.contorno.material.dispose();
    this.contorno = null;
  }

  async isolar(refs: ElementRef[] | null): Promise<void> {
    this.isolamento = refs ? new Set(refs.map(elementKey)) : null;
    await this.aplicarVisibilidade();
  }

  async mostrarDisciplina(modelId: string, visivel: boolean): Promise<void> {
    const carregado = this.modelos.get(modelId);
    if (carregado) carregado.visivel = visivel;
    await this.aplicarVisibilidade();
  }

  async transparencia(modelId: string, ativa: boolean): Promise<void> {
    this.raioXPedido.set(modelId, ativa);
    const carregado = this.modelos.get(modelId);
    if (!carregado) return; // aplicado quando a carga terminar
    carregado.raioX = ativa;
    await this.atualizarCena();
  }

  /** Estado do raio-X por modelo (apoio a teste e2e; não altera a cena). */
  raioXAtivo(modelId: string): boolean {
    return this.modelos.get(modelId)?.raioX ?? false;
  }

  /** Visibilidade = disciplina ligada ∩ isolamento (quando houver). */
  private async aplicarVisibilidade(): Promise<void> {
    for (const carregado of this.modelos.values()) {
      const { model, mapa } = carregado;
      if (!carregado.visivel) {
        await model.setVisible(undefined, false);
        continue;
      }
      if (!this.isolamento) {
        await model.setVisible(undefined, true);
        continue;
      }
      await model.setVisible(undefined, false);
      const ids = [...this.isolamento].map((k) => mapa.localPorChave.get(k)).filter((v): v is number => v !== undefined);
      if (ids.length) await model.setVisible(ids, true);
    }
    await this.atualizarCena();
  }

  async enquadrar(ref: ElementRef): Promise<void> {
    const alvo = this.localDe(ref);
    if (!alvo || !this.world) return;
    const caixa = await alvo.carregado.model.getMergedBox([alvo.localId]);
    if (caixa.isEmpty()) return;
    const esfera = caixa.getBoundingSphere(new THREE.Sphere());
    esfera.radius = Math.max(esfera.radius * 2.5, 1);
    await this.world.camera.controls.fitToSphere(esfera, true);
    await this.atualizarCena();
  }

  /** Centro projetado na tela (px do cliente) — apoio ao ensaio manual de cliques. */
  async centroNaTela(ref: ElementRef): Promise<{ x: number; y: number } | null> {
    const alvo = this.localDe(ref);
    if (!alvo || !this.world || !this.container) return null;
    const caixa = await alvo.carregado.model.getMergedBox([alvo.localId]);
    const centro = caixa.getCenter(new THREE.Vector3()).project(this.world.camera.three);
    const rect = this.world.renderer!.three.domElement.getBoundingClientRect();
    return { x: rect.left + ((centro.x + 1) / 2) * rect.width, y: rect.top + ((1 - centro.y) / 2) * rect.height };
  }

  onSelecionar(callback: Parameters<ViewerAdapter["onSelecionar"]>[0]): () => void {
    this.ouvintesSelecao.add(callback);
    return () => this.ouvintesSelecao.delete(callback);
  }

  onEstado(callback: (e: EstadoModelo) => void): () => void {
    this.ouvintesEstado.add(callback);
    return () => this.ouvintesEstado.delete(callback);
  }

  async destruir(): Promise<void> {
    this.removerClique?.();
    this.removerContorno();
    this.conversor.encerrar();
    for (const id of [...this.modelos.keys()]) await this.descarregar(id);
    this.components?.dispose();
    this.components = null;
    this.world = null;
    this.fragments = null;
  }
}
