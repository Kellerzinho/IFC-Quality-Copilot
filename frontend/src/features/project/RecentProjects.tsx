// Projetos já salvos no armazenamento local da API, do mais recente ao mais antigo.
// Abrir busca o projeto de novo pelo id (a lista é só um resumo).
import { FolderOpen, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Api } from "@/shared/api";
import { DISCIPLINE_SHORT } from "@/shared/elementKey";
import type { Project, ProjectSummary } from "@/shared/types";

interface Props {
  api: Api;
  onOpen: (project: Project) => void;
}

type Estado =
  | { tipo: "carregando" }
  | { tipo: "erro"; mensagem: string }
  | { tipo: "pronto"; itens: ProjectSummary[] };

const DATA = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

function ResumoModelos({ projeto }: { projeto: ProjectSummary }) {
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {projeto.models.map((m) => (
        <span key={m.model_id} className="inline-flex items-center gap-1">
          <Badge variant="outline" className="font-mono">
            {DISCIPLINE_SHORT[m.discipline]}
          </Badge>
          {m.ifc ? (
            <>
              <span className="max-w-48 truncate" title={m.ifc.display_name}>
                {m.ifc.display_name}
              </span>
              <span className="font-mono" title={m.ifc.revision_id}>
                {m.ifc.revision_id.slice(0, 8)}
              </span>
              {m.confirmed ? "· confirmado" : "· não confirmado"}
            </>
          ) : (
            "sem IFC"
          )}
        </span>
      ))}
    </span>
  );
}

export function RecentProjects({ api, onOpen }: Props) {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });
  const [abrindo, setAbrindo] = useState<string | null>(null);
  const [erroAbrir, setErroAbrir] = useState("");

  const carregar = useCallback(async () => {
    setEstado({ tipo: "carregando" });
    try {
      setEstado({ tipo: "pronto", itens: (await api.listProjects()).items });
    } catch (falha) {
      setEstado({ tipo: "erro", mensagem: falha instanceof Error ? falha.message : String(falha) });
    }
  }, [api]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function abrir(projectId: string) {
    setAbrindo(projectId);
    setErroAbrir("");
    try {
      onOpen(await api.getProject(projectId));
    } catch (falha) {
      setErroAbrir(falha instanceof Error ? falha.message : String(falha));
    } finally {
      setAbrindo(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-3xl tracking-wide uppercase">Projetos recentes</CardTitle>
        <CardDescription>Salvos neste computador, do mais recente ao mais antigo.</CardDescription>
      </CardHeader>
      <CardContent>
        {estado.tipo === "carregando" && <p className="text-sm text-muted-foreground">Carregando projetos…</p>}
        {estado.tipo === "erro" && (
          <div className="flex flex-wrap items-center gap-2">
            <p role="alert" className="text-sm text-destructive">
              Não foi possível listar os projetos: {estado.mensagem}
            </p>
            <Button size="sm" variant="outline" onClick={() => void carregar()}>
              <RotateCcw aria-hidden /> Tentar novamente
            </Button>
          </div>
        )}
        {estado.tipo === "pronto" && estado.itens.length === 0 && (
          <p className="text-sm text-muted-foreground">Nenhum projeto salvo ainda. Crie um abaixo.</p>
        )}
        {estado.tipo === "pronto" && estado.itens.length > 0 && (
          <ul className="grid gap-2" aria-label="Projetos recentes">
            {estado.itens.map((p) => (
              <li key={p.project_id} className="flex flex-wrap items-center gap-3 rounded-md border p-2">
                <div className="grid min-w-0 flex-1 gap-1">
                  <span className="font-medium break-all">{p.name}</span>
                  <span className="text-xs text-muted-foreground">
                    Alterado em <time dateTime={p.updated_at}>{DATA.format(new Date(p.updated_at))}</time>
                  </span>
                  <ResumoModelos projeto={p} />
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  aria-label={`Abrir ${p.name}`}
                  disabled={abrindo !== null}
                  onClick={() => void abrir(p.project_id)}
                >
                  <FolderOpen aria-hidden /> {abrindo === p.project_id ? "Abrindo…" : "Abrir"}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {erroAbrir && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {erroAbrir}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
