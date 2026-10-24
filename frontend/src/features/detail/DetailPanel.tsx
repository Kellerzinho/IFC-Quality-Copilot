// Painel direito: identidade completa do selecionado e suas lacunas PROVISÓRIAS.
import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DISCIPLINE_LABEL } from "@/shared/elementKey";
import type { ElementRef, Gap, ObservedValue } from "@/shared/types";

import type { LinhaElemento, ModeloRevisao } from "../review/reviewData";

function formatarValor(v: ObservedValue | null | undefined): string {
  if (!v) return "não lido (alvo ambíguo)";
  switch (v.state) {
    case "pset_absent":
      return "Pset ausente";
    case "property_absent":
      return "propriedade ausente";
    case "null":
      return "nulo";
    case "empty":
      return "texto vazio";
    default:
      if (typeof v.value === "boolean") return v.value ? "TRUE" : "FALSE";
      if (typeof v.value === "string") return `“${v.value}”`;
      return String(v.value);
  }
}

function Campo({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-2 text-sm">
      <dt className="text-muted-foreground">{rotulo}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

/** Valor longo (hash, chave) truncado com reticências; texto completo no title e no DOM. */
function ValorCopiavel({ valor, rotulo, testId }: { valor: string; rotulo: string; testId?: string }) {
  const [copiado, setCopiado] = useState(false);
  return (
    <span className="flex min-w-0 items-center gap-1">
      <span className="min-w-0 truncate font-mono text-xs" title={valor} data-testid={testId}>
        {valor}
      </span>
      <Button
        size="icon"
        variant="ghost"
        className="size-6 shrink-0"
        aria-label={copiado ? `${rotulo} copiada` : `Copiar ${rotulo}`}
        title={copiado ? "Copiado" : `Copiar ${rotulo}`}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(valor);
            setCopiado(true);
            setTimeout(() => setCopiado(false), 1500);
          } catch {
            setCopiado(false);
          }
        }}
      >
        {copiado ? <Check aria-hidden className="size-3.5" /> : <Copy aria-hidden className="size-3.5" />}
      </Button>
    </span>
  );
}

function CartaoLacuna({
  gap,
  ambigua,
  onIrPara,
}: {
  gap: Gap;
  ambigua: boolean;
  onIrPara: (ref: ElementRef) => void;
}) {
  const req = gap.requirement;
  return (
    <li className="grid gap-1 rounded-md border p-2 text-sm" data-testid="lacuna">
      <div className="flex flex-wrap items-center gap-1">
        <span className="font-medium">
          {req.property_set ? `${req.property_set}.` : ""}
          {req.property_name}
        </span>
        <Badge variant="outline">{gap.origin === "legacy_ifc_analyzer" ? "legado" : "observação do adaptador M4"}</Badge>
        {ambigua && <Badge variant="destructive">ambígua</Badge>}
      </div>
      <p className="text-xs text-muted-foreground">
        Regra: {req.specification} · checagem {req.check}
        {req.expected_value ? ` = ${req.expected_value}` : ""}
      </p>
      <p>Atual no IFC: {formatarValor(gap.current_value)}</p>
      {gap.provisional_marker && (
        <p className="text-xs">
          <Badge variant="warning">provisório</Badge> marcador “{gap.provisional_marker.marker}” — não é valor confirmado
        </p>
      )}
      {ambigua && (
        <div className="grid gap-1 text-xs">
          <p>
            O legado apontou o GlobalId {gap.global_id}, repetido em {gap.candidates?.length} entidades deste arquivo.
            Nenhuma foi escolhida.
          </p>
          <div className="flex flex-wrap gap-1">
            {gap.candidates?.map((c) => (
              <Button key={c.express_id} size="sm" variant="outline" onClick={() => onIrPara(c)}>
                Ver #{c.express_id}
              </Button>
            ))}
          </div>
        </div>
      )}
    </li>
  );
}

interface Props {
  linha: LinhaElemento | null;
  modelos: ModeloRevisao[];
  onIrPara: (ref: ElementRef) => void;
}

export function DetailPanel({ linha, modelos, onIrPara }: Props) {
  if (!linha) {
    return (
      <section aria-label="Detalhe" className="p-4 text-sm text-muted-foreground">
        Selecione um elemento na lista ou no 3D.
      </section>
    );
  }
  const { record, binding, lacunas } = linha;
  const modelo = modelos.find((m) => m.binding.model_id === binding.model_id);
  const total = lacunas.resolvidas.length + lacunas.ambiguas.length;

  return (
    <section aria-label="Detalhe" className="grid content-start gap-4 overflow-y-auto p-4">
      <header className="grid gap-1">
        <h2 className="font-display text-2xl leading-tight break-words" data-testid="detalhe-nome">
          {record.name ?? "(sem nome)"}
        </h2>
        <p className="text-sm text-muted-foreground" data-testid="detalhe-arquivo">
          {DISCIPLINE_LABEL[binding.discipline]} · {binding.ifc?.display_name}
        </p>
      </header>

      <dl className="grid gap-1">
        <Campo rotulo="Classe IFC">{record.ifc_class}</Campo>
        <Campo rotulo="express_id">
          <span className="font-mono" data-testid="detalhe-express">
            {record.ref.express_id}
          </span>
        </Campo>
        <Campo rotulo="Revisão IFC">
          <ValorCopiavel valor={record.ref.ifc_revision_id} rotulo="revisão IFC" />
        </Campo>
        <Campo rotulo="GlobalId">
          <span className="font-mono">{record.global_id ?? "ausente"}</span> <span className="text-xs text-muted-foreground">(atributo, não identidade)</span>
          {record.global_id_state === "duplicated_in_file" && (
            <Badge variant="destructive" className="ml-1">
              repetido neste arquivo
            </Badge>
          )}
        </Campo>
        <Campo rotulo="Geometria">{record.has_geometry ? "sim" : "Elemento sem geometria disponível"}</Campo>
        <Campo rotulo="Chave">
          <ValorCopiavel valor={linha.chave} rotulo="chave" testId="detalhe-chave" />
        </Campo>
      </dl>

      <div className="grid gap-2">
        <h3 className="text-sm font-semibold">Lacunas</h3>
        <p className="text-xs text-muted-foreground">PROVISÓRIO — formato aguardando M2/M3.</p>
        {modelo?.lacunas === null ? (
          <p className="text-sm">Modelo ainda não analisado (vínculo IFC/IDS não confirmado).</p>
        ) : total === 0 ? (
          <p className="text-sm">Nenhuma lacuna reportada para este elemento.</p>
        ) : (
          <ul className="grid gap-2">
            {lacunas.resolvidas.map((g) => (
              <CartaoLacuna key={g.gap_id} gap={g} ambigua={false} onIrPara={onIrPara} />
            ))}
            {lacunas.ambiguas.map((g) => (
              <CartaoLacuna key={g.gap_id} gap={g} ambigua onIrPara={onIrPara} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
