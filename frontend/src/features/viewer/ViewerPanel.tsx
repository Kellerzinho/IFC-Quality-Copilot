// Centro: cena 3D. Falha aqui nunca derruba lista/painel (D4-13/D4-23).
import { AlertTriangle, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { Api } from "@/shared/api";
import { DISCIPLINE_LABEL } from "@/shared/elementKey";

import type { ModeloRevisao } from "../review/reviewData";
import type { EstadoModelo, ViewerAdapter } from "./ViewerPort";

export type SituacaoViewer = { tipo: "montando" } | { tipo: "pronto" } | { tipo: "falhou"; mensagem: string };

interface Props {
  adapter: ViewerAdapter;
  api: Api;
  projectId: string;
  modelos: ModeloRevisao[];
  onSituacao: (s: SituacaoViewer) => void;
}

const ROTULO_ETAPA: Record<EstadoModelo["etapa"], string> = {
  convertendo: "convertendo IFC",
  carregando: "carregando na cena",
  pronto: "pronto",
  falhou: "falhou",
  descarregado: "descarregado",
};

export function ViewerPanel({ adapter, api, projectId, modelos, onSituacao }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const [situacao, setSituacao] = useState<SituacaoViewer>({ tipo: "montando" });
  const [estados, setEstados] = useState<Record<string, EstadoModelo>>({});
  const iniciados = useRef(new Set<string>());

  const atualizar = useCallback(
    (s: SituacaoViewer) => {
      setSituacao(s);
      onSituacao(s);
    },
    [onSituacao],
  );

  useEffect(() => {
    const remover = adapter.onEstado((e) => setEstados((prev) => ({ ...prev, [e.modelId]: e })));
    let ativo = true;
    adapter
      .montar(container.current!)
      .then(() => ativo && atualizar({ tipo: "pronto" }))
      .catch((erro: unknown) =>
        atualizar({ tipo: "falhou", mensagem: erro instanceof Error ? erro.message : String(erro) }),
      );
    return () => {
      ativo = false;
      remover();
      void adapter.destruir().catch(() => undefined);
    };
  }, [adapter, atualizar]);

  const carregar = useCallback(
    async (modelo: ModeloRevisao) => {
      const id = modelo.binding.model_id;
      try {
        const { bytes, revision } = await api.fetchIfc(projectId, id);
        if (revision !== modelo.binding.ifc?.revision_id) throw new Error("A revisão servida difere da revisão da linha.");
        await adapter.carregarModelo({ modelId: id, revisionId: revision, bytes, elementos: modelo.elementos });
      } catch (erro) {
        setEstados((prev) => ({
          ...prev,
          [id]: {
            modelId: id,
            etapa: "falhou",
            decorridoMs: prev[id]?.decorridoMs ?? 0,
            mensagem: erro instanceof Error ? erro.message : String(erro),
          },
        }));
      }
    },
    [adapter, api, projectId],
  );

  useEffect(() => {
    if (situacao.tipo !== "pronto") return;
    void (async () => {
      for (const modelo of modelos) {
        if (!modelo.binding.ifc || iniciados.current.has(modelo.binding.model_id)) continue;
        iniciados.current.add(modelo.binding.model_id);
        await carregar(modelo);
      }
    })();
  }, [situacao, modelos, carregar]);

  return (
    <section aria-label="Visualização 3D" className="relative flex h-full min-h-0 flex-col">
      {situacao.tipo === "falhou" && (
        <Alert variant="warning" className="m-3 w-auto">
          <AlertTriangle aria-hidden />
          <AlertTitle>Visualização 3D indisponível</AlertTitle>
          <AlertDescription>
            <p>A lista e o painel continuam funcionando. Detalhe técnico: {situacao.mensagem}</p>
          </AlertDescription>
        </Alert>
      )}
      <div ref={container} className="relative min-h-0 flex-1" data-testid="viewer-container" />
      <ul className="grid gap-1 border-t p-2 text-xs" aria-label="Estado dos modelos 3D">
        {modelos
          .filter((m) => m.binding.ifc)
          .map((m) => {
            const e = estados[m.binding.model_id];
            return (
              <li key={m.binding.model_id} className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{DISCIPLINE_LABEL[m.binding.discipline]}:</span>
                <span data-testid={`estado-3d-${m.binding.discipline}`}>
                  {e ? (
                    <>
                      {ROTULO_ETAPA[e.etapa]} (<span className="font-mono">{(e.decorridoMs / 1000).toFixed(1)} s</span>)
                    </>
                  ) : (
                    "aguardando"
                  )}
                </span>
                {e?.mapa && (
                  <span className="text-muted-foreground">
                    · identidade verificada {e.mapa.verificados}, sem geometria no viewer {e.mapa.semGeometria}
                    {e.mapa.divergentes ? `, divergentes ${e.mapa.divergentes} (clique desabilitado)` : ""}
                  </span>
                )}
                {e?.etapa === "falhou" && (
                  <>
                    <span role="alert" className="text-destructive">
                      Falha 3D neste modelo: {e.mensagem}
                    </span>
                    <Button size="sm" variant="outline" onClick={() => void carregar(m)}>
                      <RotateCcw aria-hidden /> Tentar novamente
                    </Button>
                  </>
                )}
              </li>
            );
          })}
      </ul>
    </section>
  );
}
