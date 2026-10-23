import { Focus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { DISCIPLINE_LABEL } from "@/shared/elementKey";

import type { ModeloRevisao } from "../review/reviewData";

export interface EstadoExibicao {
  /** model_id → visível. */
  visivel: Record<string, boolean>;
  raioXArquitetura: boolean;
}

interface Props {
  modelos: ModeloRevisao[];
  exibicao: EstadoExibicao;
  onExibicao: (e: EstadoExibicao) => void;
  soComLacuna: boolean;
  onSoComLacuna: (v: boolean) => void;
  podeEnquadrar: boolean;
  onEnquadrar: () => void;
  desabilitado: boolean;
}

export function DisplayControls({
  modelos,
  exibicao,
  onExibicao,
  soComLacuna,
  onSoComLacuna,
  podeEnquadrar,
  onEnquadrar,
  desabilitado,
}: Props) {
  const temArquitetura = modelos.some((m) => m.binding.discipline === "architecture");
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b px-3 py-2 text-sm" aria-label="Controles 3D">
      {modelos.map((m) => (
        <label key={m.binding.model_id} className="flex items-center gap-2">
          <Switch
            aria-label={`Mostrar ${DISCIPLINE_LABEL[m.binding.discipline]}`}
            disabled={desabilitado}
            checked={exibicao.visivel[m.binding.model_id] ?? true}
            onCheckedChange={(v) => onExibicao({ ...exibicao, visivel: { ...exibicao.visivel, [m.binding.model_id]: v } })}
          />
          {DISCIPLINE_LABEL[m.binding.discipline]}
        </label>
      ))}
      {temArquitetura && (
        <label className="flex items-center gap-2">
          <Switch
            aria-label="Arquitetura transparente (raio-X)"
            disabled={desabilitado}
            checked={exibicao.raioXArquitetura}
            onCheckedChange={(v) => onExibicao({ ...exibicao, raioXArquitetura: v })}
          />
          Raio-X arquitetura
        </label>
      )}
      <label className="flex items-center gap-2">
        <Switch aria-label="Só com lacuna no 3D" checked={soComLacuna} onCheckedChange={onSoComLacuna} />
        Só com lacuna
      </label>
      <Button size="sm" variant="outline" disabled={desabilitado || !podeEnquadrar} onClick={onEnquadrar}>
        <Focus aria-hidden /> Enquadrar selecionado
      </Button>
    </div>
  );
}
