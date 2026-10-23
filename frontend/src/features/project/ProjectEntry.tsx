import { useState } from "react";

import { ThemeToggle } from "@/components/ThemeToggle";
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

/** Linha ondulada vinho: assinatura visual, só na entrada. */
function Onda() {
  return (
    <svg
      aria-hidden
      className="assinatura-onda block h-12 w-full text-primary"
      viewBox="0 0 1440 48"
      preserveAspectRatio="none"
      fill="none"
    >
      <path
        d="M0 30 C 240 6, 520 8, 760 24 S 1220 46, 1440 14"
        stroke="currentColor"
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
        pathLength={1}
      />
      <path
        d="M0 40 C 300 30, 640 18, 980 26 S 1300 36, 1440 30"
        stroke="currentColor"
        strokeOpacity="0.35"
        strokeWidth="1"
        vectorEffect="non-scaling-stroke"
        pathLength={1}
      />
    </svg>
  );
}

const PASSOS = [
  { titulo: "Envie IFC e IDS", texto: "Uma linha por disciplina: arquitetura e estrutura, cada uma com a própria revisão." },
  { titulo: "Confirme o vínculo", texto: "O nome do arquivo nunca decide qual IDS vale para qual IFC. A confirmação é sua." },
  { titulo: "Revise as lacunas", texto: "Lista, 3D e detalhe andam juntos pela identidade do elemento, não pelo GlobalId." },
];

export function ProjectEntry({ api, project, onProjectChange, onOpenReview }: Props) {
  const [nome, setNome] = useState("");
  const [erro, setErro] = useState("");
  const podeAbrir = !!project?.models.some((m) => m.ifc);

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-8">
          <span className="font-serif text-xl">IFC Quality Copilot</span>
          <ThemeToggle />
        </div>
      </header>

      <main className="flex-1">
        <section className="mx-auto grid max-w-6xl items-end gap-x-16 gap-y-6 px-8 pt-16 pb-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <h1 className="font-serif text-5xl leading-[1.04] tracking-tight text-balance lg:text-6xl xl:text-7xl">
            Qualidade semântica de modelos IFC, com o engenheiro no <em className="text-primary">controle</em>.
          </h1>
          <div className="grid max-w-[52ch] gap-3 pb-2 text-base leading-relaxed text-muted-foreground">
            <p>
              A revisão lê o IFC, aplica os requisitos do IDS e aponta as lacunas de cada elemento. O IFC enviado
              nunca é alterado.
            </p>
            <p>Projeto com dois pares IFC/IDS: arquitetura e estrutura.</p>
          </div>
        </section>

        <Onda />

        <section className="mx-auto max-w-6xl px-8 py-10">
          {!project ? (
            <Card className="max-w-2xl">
              <CardHeader>
                <CardTitle className="font-serif text-3xl font-normal">Novo projeto</CardTitle>
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
                <CardTitle className="font-serif text-3xl font-normal">{project.name}</CardTitle>
                <CardDescription className="max-w-[80ch]">
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
        </section>
      </main>

      <section aria-label="Como funciona" className="bg-band text-band-foreground">
        <ol className="mx-auto grid max-w-6xl gap-10 px-8 py-12 md:grid-cols-3">
          {PASSOS.map((passo, i) => (
            <li key={passo.titulo} className="grid grid-cols-[auto_1fr] gap-x-4">
              <span className="font-serif text-5xl leading-none text-band-accent" aria-hidden>
                {i + 1}
              </span>
              <div className="grid gap-1">
                <h2 className="font-serif text-2xl">{passo.titulo}</h2>
                <p className="text-sm leading-relaxed text-band-muted">{passo.texto}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
