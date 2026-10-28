// Entrada do projeto: uma linha por disciplina, IFC + IDS enviados e confirmados
// explicitamente por linha. Nome de arquivo nunca decide o vínculo (D4-09).
import { CheckCircle2, FileUp } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Api } from "@/shared/api";
import { DISCIPLINE_LABEL } from "@/shared/elementKey";
import type { ModelPairBinding, Project, SourceArtifactRef } from "@/shared/types";

interface Props {
  project: Project;
  api: Api;
  onProjectChange: (project: Project) => void;
}

function Fonte({ fonte }: { fonte: SourceArtifactRef | null | undefined }) {
  if (!fonte) return <span className="text-muted-foreground">não enviado</span>;
  return (
    <div className="grid">
      <span className="font-medium break-all">{fonte.display_name}</span>
      <span className="font-mono text-xs text-muted-foreground" title={fonte.revision_id}>
        rev {fonte.revision_id.slice(0, 12)} · {(fonte.size_bytes / 1024).toFixed(0)} KiB
        {fonte.ifc_schema ? ` · ${fonte.ifc_schema}` : ""}
      </span>
    </div>
  );
}

function EnvioArquivo({
  label,
  accept,
  disabled,
  onFile,
}: {
  label: string;
  accept: string;
  disabled: boolean;
  onFile: (file: File) => void;
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-1 text-xs font-medium text-accent underline-offset-2 hover:underline has-[:focus-visible]:rounded-sm has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background">
      <FileUp className="size-3.5" aria-hidden />
      {label}
      <input
        type="file"
        accept={accept}
        className="sr-only"
        disabled={disabled}
        aria-label={label}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) onFile(file);
        }}
      />
    </label>
  );
}

export function ModelPairTable({ project, api, onProjectChange }: Props) {
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [erro, setErro] = useState<Record<string, string>>({});

  async function executar(binding: ModelPairBinding, acao: () => Promise<unknown>) {
    setOcupado(binding.model_id);
    setErro((e) => ({ ...e, [binding.model_id]: "" }));
    try {
      await acao();
      onProjectChange(await api.getProject(project.project_id));
    } catch (falha) {
      setErro((e) => ({ ...e, [binding.model_id]: falha instanceof Error ? falha.message : String(falha) }));
    } finally {
      setOcupado(null);
    }
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Disciplina</TableHead>
          <TableHead>IFC</TableHead>
          <TableHead>IDS</TableHead>
          <TableHead>Vínculo</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {project.models.map((binding) => {
          const ocupada = ocupado === binding.model_id;
          const podeConfirmar = !!binding.ifc && !!binding.ids && !binding.confirmed;
          return (
            <TableRow key={binding.model_id} data-testid={`linha-${binding.discipline}`}>
              <TableCell className="font-medium">{DISCIPLINE_LABEL[binding.discipline]}</TableCell>
              <TableCell className="max-w-72 align-top">
                <Fonte fonte={binding.ifc} />
                <EnvioArquivo
                  label={`Enviar IFC (${DISCIPLINE_LABEL[binding.discipline]})`}
                  accept=".ifc"
                  disabled={ocupada}
                  onFile={(f) => executar(binding, () => api.uploadSource(project.project_id, binding.model_id, "ifc", f, f.name))}
                />
              </TableCell>
              <TableCell className="max-w-72 align-top">
                <Fonte fonte={binding.ids} />
                <EnvioArquivo
                  label={`Enviar IDS (${DISCIPLINE_LABEL[binding.discipline]})`}
                  accept=".ids,.xml"
                  disabled={ocupada}
                  onFile={(f) => executar(binding, () => api.uploadSource(project.project_id, binding.model_id, "ids", f, f.name))}
                />
              </TableCell>
              <TableCell className="align-top">
                {binding.confirmed ? (
                  <Badge variant="secondary">
                    <CheckCircle2 aria-hidden /> Confirmado nas revisões acima
                  </Badge>
                ) : (
                  <Button
                    size="sm"
                    disabled={!podeConfirmar || ocupada}
                    onClick={() =>
                      executar(binding, () =>
                        api.confirm(project.project_id, binding.model_id, binding.ifc!.revision_id, binding.ids!.revision_id),
                      )
                    }
                  >
                    Confirmar: este IFC + este IDS = {DISCIPLINE_LABEL[binding.discipline]}
                  </Button>
                )}
                {ocupada && <p className="mt-1 text-xs text-muted-foreground">Processando…</p>}
                {erro[binding.model_id] && (
                  <p role="alert" className="mt-1 text-xs text-destructive">
                    {erro[binding.model_id]}
                  </p>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
