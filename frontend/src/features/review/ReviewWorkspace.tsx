// Tela de revisão em três painéis — layout "Modelo em foco" do protótipo M4, no tema
// LEPV em avaliação (a escolha visual do plano M4 §13.4 segue pendente).
// Seleção sincronizada sempre pela ElementRef (modelo + revisão + express_id).
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ThemeToggle } from "@/components/ThemeToggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { cn } from "@/lib/utils";
import type { Api } from "@/shared/api";
import { DISCIPLINE_SHORT, elementKey } from "@/shared/elementKey";
import type { ElementRef, Project } from "@/shared/types";

import { DetailPanel } from "../detail/DetailPanel";
import { DiagnosticList, type FiltrosLista } from "../diagnostic/DiagnosticList";
import { DisplayControls, type EstadoExibicao } from "../viewer/DisplayControls";
import { ViewerPanel, type SituacaoViewer } from "../viewer/ViewerPanel";
import type { ViewerAdapter } from "../viewer/ViewerPort";
import {
  montarLinhas,
  resumirRevisao,
  rotuloContagem,
  totalLacunas,
  type LinhaElemento,
  type ModeloRevisao,
} from "./reviewData";

interface Props {
  api: Api;
  project: Project;
  createViewer: () => ViewerAdapter;
  onVoltar: () => void;
}

/** Número grande da faixa de resumo; null aparece como travessão, não como zero. */
function Numero({
  singular,
  plural,
  valor,
  testId,
  semValor,
}: {
  singular: string;
  plural: string;
  valor: number | null;
  testId: string;
  semValor?: string;
}) {
  return (
    <div className="grid min-w-16 gap-0.5">
      <dt className="order-2 text-xs text-band-muted" data-testid={`${testId}-rotulo`}>
        {rotuloContagem(valor, singular, plural)}
      </dt>
      <dd
        className="order-1 font-display text-4xl leading-none text-gold tabular-nums"
        data-testid={testId}
        title={valor === null ? semValor : undefined}
      >
        {valor ?? "—"}
      </dd>
    </div>
  );
}

async function carregarModelos(api: Api, project: Project): Promise<ModeloRevisao[]> {
  const comIfc = project.models.filter((b) => b.ifc);
  return Promise.all(
    comIfc.map(async (binding): Promise<ModeloRevisao> => {
      try {
        const elementos = (await api.listElements(project.project_id, binding.model_id)).items;
        const lacunas = binding.confirmed ? (await api.listGaps(project.project_id, binding.model_id)).items : null;
        return { binding, elementos, lacunas };
      } catch (erro) {
        return { binding, elementos: [], lacunas: null, erro: erro instanceof Error ? erro.message : String(erro) };
      }
    }),
  );
}

export function ReviewWorkspace({ api, project, createViewer, onVoltar }: Props) {
  const adapter = useMemo(() => createViewer(), [createViewer]);
  const [modelos, setModelos] = useState<ModeloRevisao[] | null>(null);
  const [filtros, setFiltros] = useState<FiltrosLista>({ busca: "", arquivo: "todos", soComLacuna: false });
  const [selecionada, setSelecionada] = useState<string | null>(null);
  const [situacao, setSituacao] = useState<SituacaoViewer>({ tipo: "montando" });
  const [exibicao, setExibicao] = useState<EstadoExibicao>({ visivel: {}, raioXArquitetura: false });
  const [aviso, setAviso] = useState("");
  const viewerPronto = situacao.tipo === "pronto";
  const prontoRef = useRef(false);
  prontoRef.current = viewerPronto;

  useEffect(() => {
    let ativo = true;
    void carregarModelos(api, project).then((m) => ativo && setModelos(m));
    return () => {
      ativo = false;
    };
  }, [api, project]);

  const linhas = useMemo(() => (modelos ? montarLinhas(modelos) : []), [modelos]);
  const porChave = useMemo(() => new Map(linhas.map((l) => [l.chave, l])), [linhas]);
  const linhaSelecionada = selecionada ? porChave.get(selecionada) ?? null : null;
  const resumo = useMemo(() => (modelos ? resumirRevisao(modelos, linhas) : null), [modelos, linhas]);

  /** Chamada ao viewer que nunca derruba a lista/painel. */
  const noViewer = useCallback((acao: () => Promise<unknown>) => {
    if (!prontoRef.current) return;
    acao().catch((erro: unknown) => setAviso(`3D: ${erro instanceof Error ? erro.message : String(erro)}`));
  }, []);

  const selecionarPelaLista = useCallback(
    (ref: ElementRef) => {
      setSelecionada(elementKey(ref));
      setAviso("");
      noViewer(async () => {
        await adapter.destacar(ref);
        await adapter.enquadrar(ref);
      });
    },
    [adapter, noViewer],
  );

  useEffect(
    () =>
      adapter.onSelecionar((ref, motivo) => {
        if (!ref) {
          if (motivo === "nao_comprovado") setAviso("Clique sem identidade comprovada: nenhum elemento selecionado.");
          return;
        }
        setAviso("");
        setSelecionada(elementKey(ref));
        noViewer(() => adapter.destacar(ref));
      }),
    [adapter, noViewer],
  );

  useEffect(() => {
    if (!viewerPronto || !modelos) return;
    for (const m of modelos) noViewer(() => adapter.mostrarDisciplina(m.binding.model_id, exibicao.visivel[m.binding.model_id] ?? true));
    const arq = modelos.find((m) => m.binding.discipline === "architecture");
    if (arq) noViewer(() => adapter.transparencia(arq.binding.model_id, exibicao.raioXArquitetura));
  }, [adapter, exibicao, modelos, viewerPronto, noViewer]);

  useEffect(() => {
    if (!viewerPronto) return;
    const refs = filtros.soComLacuna
      ? linhas.filter((l) => totalLacunas(l.lacunas) > 0).map((l) => l.record.ref)
      : null;
    noViewer(() => adapter.isolar(refs));
  }, [adapter, filtros.soComLacuna, linhas, viewerPronto, noViewer]);

  useEffect(() => {
    if (import.meta.env.DEV) {
      (window as unknown as { __m4?: unknown }).__m4 = { adapter, linhas };
    }
  }, [adapter, linhas]);

  return (
    <div className="flex h-full flex-col">
      <header className="border-b-[3px] border-gold bg-band text-band-foreground">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <Button
            size="sm"
            variant="ghost"
            onClick={onVoltar}
            className="text-band-foreground hover:bg-band-foreground/10 hover:text-band-foreground"
          >
            <ArrowLeft aria-hidden /> Projeto
          </Button>
          <h1 className="min-w-0 truncate font-display text-3xl leading-none tracking-wide uppercase">{project.name}</h1>
          {resumo && (
            <dl className="ml-auto flex gap-x-8" aria-label="Resumo da revisão">
              <Numero singular="Elemento" plural="Elementos" valor={resumo.elementos} testId="resumo-elementos" />
              <Numero
                singular="Lacuna"
                plural="Lacunas"
                valor={resumo.lacunas}
                testId="resumo-lacunas"
                semValor="Nenhum modelo analisado"
              />
              <Numero
                singular="Ambígua"
                plural="Ambíguas"
                valor={resumo.ambiguas}
                testId="resumo-ambiguas"
                semValor="Nenhum modelo analisado"
              />
              <Numero singular="Sem geometria" plural="Sem geometria" valor={resumo.semGeometria} testId="resumo-sem-geometria" />
            </dl>
          )}
          <ThemeToggle
            className={cn("text-band-foreground hover:bg-band-foreground/10 hover:text-band-foreground", !resumo && "ml-auto")}
          />
        </div>
      </header>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b bg-card px-4 py-1.5" aria-label="Arquivos da revisão">
        {project.models
          .filter((m) => m.ifc)
          .map((m) => (
            <span key={m.model_id} className="flex items-center gap-1.5 text-xs">
              <Badge variant="outline">{DISCIPLINE_SHORT[m.discipline]}</Badge>
              <span className="max-w-48 truncate font-medium" title={m.ifc?.display_name}>
                {m.ifc?.display_name}
              </span>
              <span className="font-mono text-muted-foreground">{m.ifc?.revision_id.slice(0, 8)}</span>
              <span className="text-muted-foreground">· IDS {m.ids?.display_name ?? "—"}</span>
              {!m.confirmed && <Badge variant="warning">não analisado</Badge>}
            </span>
          ))}
        <Badge variant="secondary" className="ml-auto">
          Tema em avaliação
        </Badge>
      </div>

      {aviso && (
        <p role="status" className="border-b border-gold/60 bg-gold-soft px-4 py-1 text-sm">
          {aviso}
        </p>
      )}

      {!modelos ? (
        <p className="p-6 text-sm text-muted-foreground">Carregando elementos e lacunas…</p>
      ) : (
        <ResizablePanelGroup orientation="horizontal" className="min-h-0 flex-1">
          <ResizablePanel defaultSize="26" minSize="16" className="bg-card">
            <DiagnosticList
              modelos={modelos}
              linhas={linhas}
              filtros={filtros}
              onFiltros={setFiltros}
              selecionada={selecionada}
              onSelecionar={(l: LinhaElemento) => selecionarPelaLista(l.record.ref)}
            />
          </ResizablePanel>
          <ResizableHandle />
          <ResizablePanel defaultSize="48" minSize="25">
            <div className="flex h-full min-h-0 flex-col">
              <DisplayControls
                modelos={modelos}
                exibicao={exibicao}
                onExibicao={setExibicao}
                soComLacuna={filtros.soComLacuna}
                onSoComLacuna={(v) => setFiltros({ ...filtros, soComLacuna: v })}
                podeEnquadrar={!!linhaSelecionada}
                onEnquadrar={() => linhaSelecionada && noViewer(() => adapter.enquadrar(linhaSelecionada.record.ref))}
                desabilitado={!viewerPronto}
              />
              {modelos.some((m) => m.erro) && (
                <p role="alert" className="px-3 py-1 text-sm text-destructive">
                  {modelos
                    .filter((m) => m.erro)
                    .map((m) => `${DISCIPLINE_SHORT[m.binding.discipline]}: ${m.erro}`)
                    .join(" · ")}
                </p>
              )}
              <div className="min-h-0 flex-1">
                <ViewerPanel
                  adapter={adapter}
                  api={api}
                  projectId={project.project_id}
                  modelos={modelos}
                  onSituacao={setSituacao}
                />
              </div>
            </div>
          </ResizablePanel>
          <ResizableHandle />
          <ResizablePanel defaultSize="26" minSize="16" className="bg-card">
            <DetailPanel linha={linhaSelecionada} modelos={modelos} onIrPara={selecionarPelaLista} />
          </ResizablePanel>
        </ResizablePanelGroup>
      )}
    </div>
  );
}
