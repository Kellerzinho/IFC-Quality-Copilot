import { useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { Api } from "@/shared/api";
import type { Project } from "@/shared/types";

import { ModelPairTable } from "./ModelPairTable";

interface Props {
  api: Api;
  project: Project | null;
  onProjectChange: (project: Project) => void;
  onOpenReview: () => void;
}

export function ProjectEntry({ api, project, onProjectChange, onOpenReview }: Props) {
  const [nome, setNome] = useState("");
  const [erro, setErro] = useState("");
  const podeAbrir = !!project?.models.some((m) => m.ifc);

  return (
    <main className="mx-auto grid max-w-5xl gap-4 p-6">
      <header>
        <h1 className="text-xl font-semibold">IFC Quality Copilot — revisão</h1>
        <p className="text-sm text-muted-foreground">Projeto com dois pares IFC/IDS: arquitetura e estrutura.</p>
      </header>

      {!project ? (
        <Card>
          <CardHeader>
            <CardTitle>Novo projeto</CardTitle>
            <CardDescription>Os arquivos ficam no armazenamento local da API (127.0.0.1).</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="flex gap-2"
              onSubmit={async (e) => {
                e.preventDefault();
                setErro("");
                try {
                  onProjectChange(await api.createProject(nome.trim()));
                } catch (falha) {
                  setErro(falha instanceof Error ? falha.message : String(falha));
                }
              }}
            >
              <Input
                aria-label="Nome do projeto"
                placeholder="Nome do projeto"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
              />
              <Button type="submit" disabled={!nome.trim()}>
                Criar projeto
              </Button>
            </form>
            {erro && <p role="alert" className="mt-2 text-sm text-destructive">{erro}</p>}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>{project.name}</CardTitle>
            <CardDescription>
              Envie IFC e IDS em cada linha e confirme o vínculo. Arquivos com nomes parecidos não são associados
              automaticamente; a confirmação vale para as revisões (SHA-256) exibidas.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <ModelPairTable project={project} api={api} onProjectChange={onProjectChange} />
            <Alert variant="warning">
              <AlertTitle>Lacunas exigem vínculo confirmado</AlertTitle>
              <AlertDescription>
                Uma linha só com IFC pode ser navegada (lista e 3D), mas aparece como “Modelo ainda não analisado”.
              </AlertDescription>
            </Alert>
            <div>
              <Button onClick={onOpenReview} disabled={!podeAbrir}>
                Abrir revisão
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </main>
  );
}
