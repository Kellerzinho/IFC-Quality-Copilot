// Lista à esquerda: elementos dos dois arquivos, busca, filtro por arquivo e "só com lacuna".
import { AlertTriangle, Copy, EyeOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { DISCIPLINE_SHORT } from "@/shared/elementKey";
import { cn } from "@/lib/utils";

import { totalLacunas, type LinhaElemento } from "../review/reviewData";
import type { ModeloRevisao } from "../review/reviewData";

export const LIMITE_LISTA = 400;

export interface FiltrosLista {
  busca: string;
  /** "todos" ou model_id. */
  arquivo: string;
  soComLacuna: boolean;
}

export function filtrarLinhas(linhas: LinhaElemento[], filtros: FiltrosLista): LinhaElemento[] {
  const termo = filtros.busca.trim().toLocaleLowerCase("pt-BR");
  return linhas.filter((linha) => {
    if (filtros.arquivo !== "todos" && linha.binding.model_id !== filtros.arquivo) return false;
    if (filtros.soComLacuna && totalLacunas(linha.lacunas) === 0) return false;
    if (!termo) return true;
    const r = linha.record;
    const alvo = [r.name ?? "", r.global_id ?? "", r.ifc_class, String(r.ref.express_id)].join(" ").toLocaleLowerCase("pt-BR");
    return alvo.includes(termo);
  });
}

interface Props {
  modelos: ModeloRevisao[];
  linhas: LinhaElemento[];
  filtros: FiltrosLista;
  onFiltros: (f: FiltrosLista) => void;
  selecionada: string | null;
  onSelecionar: (linha: LinhaElemento) => void;
}

export function DiagnosticList({ modelos, linhas, filtros, onFiltros, selecionada, onSelecionar }: Props) {
  const filtradas = filtrarLinhas(linhas, filtros);
  const visiveis = filtradas.slice(0, LIMITE_LISTA);

  return (
    <section aria-label="Elementos e lacunas" className="flex h-full min-h-0 flex-col">
      <div className="grid gap-2 border-b p-3">
        <Input
          type="search"
          aria-label="Buscar elemento"
          placeholder="Buscar nome, GlobalId, classe ou id"
          value={filtros.busca}
          onChange={(e) => onFiltros({ ...filtros, busca: e.target.value })}
        />
        <div className="flex items-center gap-2">
          <select
            aria-label="Filtrar por arquivo"
            className="h-8 flex-1 rounded-md border bg-background px-2 text-sm"
            value={filtros.arquivo}
            onChange={(e) => onFiltros({ ...filtros, arquivo: e.target.value })}
          >
            <option value="todos">Todos os arquivos</option>
            {modelos.map((m) => (
              <option key={m.binding.model_id} value={m.binding.model_id}>
                {DISCIPLINE_SHORT[m.binding.discipline]} · {m.binding.ifc?.display_name ?? "sem IFC"}
              </option>
            ))}
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Switch
            checked={filtros.soComLacuna}
            onCheckedChange={(v) => onFiltros({ ...filtros, soComLacuna: v })}
            aria-label="Só com lacuna"
          />
          Só com lacuna (lista e 3D)
        </label>
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {filtradas.length} de {linhas.length} elementos
          {filtradas.length > LIMITE_LISTA ? ` · exibindo os primeiros ${LIMITE_LISTA}; refine a busca` : ""}
        </p>
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto p-1" aria-label="Lista de elementos">
        {visiveis.length === 0 && (
          <li className="p-4 text-center text-sm text-muted-foreground">Nenhum resultado corresponde aos filtros.</li>
        )}
        {visiveis.map((linha) => {
          const r = linha.record;
          const n = totalLacunas(linha.lacunas);
          const ativa = linha.chave === selecionada;
          return (
            <li key={linha.chave}>
              <button
                type="button"
                data-chave={linha.chave}
                aria-current={ativa ? "true" : undefined}
                onClick={() => onSelecionar(linha)}
                className={cn(
                  "grid w-full gap-0.5 rounded-md border border-transparent px-2 py-1.5 text-left text-sm hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none",
                  ativa && "border-accent bg-accent-soft hover:bg-accent-soft",
                )}
              >
                <span className="flex items-center gap-1.5">
                  <Badge variant="outline">
                    {DISCIPLINE_SHORT[linha.binding.discipline]}
                  </Badge>
                  <span className="truncate font-medium">{r.name ?? "(sem nome)"}</span>
                  {n > 0 && (
                    <Badge variant="warning" className="ml-auto">
                      <AlertTriangle aria-hidden /> {n} lacuna{n > 1 ? "s" : ""}
                    </Badge>
                  )}
                </span>
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  {r.ifc_class} · <span className="font-mono">#{r.ref.express_id}</span>
                  {r.global_id_state === "duplicated_in_file" && (
                    <span className="inline-flex items-center gap-0.5 text-destructive" title="GlobalId repetido neste arquivo">
                      <Copy className="size-3" aria-hidden /> GUID repetido
                    </span>
                  )}
                  {!r.has_geometry && (
                    <span className="inline-flex items-center gap-0.5">
                      <EyeOff className="size-3" aria-hidden /> sem geometria
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
