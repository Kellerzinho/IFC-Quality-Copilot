# Modelo de estudo — Prédio (Fase C.1: entrada congelada)

Dataset primário do experimento (protocolo **GT-by-diff**, ver
`docs/plano-orquestracao-2026-06-25.md` §5). A entrada é a versão "como
exportada" do prédio, **com lacunas reais** — é ela que o pipeline deve
enriquecer. O arquivo IFC não é versionado no git (`*.ifc` no `.gitignore`);
este README é a referência canônica com hash de integridade.

## Identificação do arquivo congelado

| Campo | Valor |
|---|---|
| Arquivo | `data/evaluation/predio/predio_v1.ifc` |
| Nome original | `24405 - KELLER - PREDIO.ifc` |
| SHA256 | `A71C8BE30D82760218F5B3F3A1C476B49E3F30E608B0065916B9D5206A1A6DD0` |
| Tamanho | 186,64 MB |
| Schema | IFC4 |
| MVD / View | ReferenceView_V1.2 (ExchangeRequirement: Architecture) |
| Ferramenta de exportação | Autodesk Revit 26.2.0.20 (PTB) — IFC 26.2.0.20 (ODA SDAI 25.12) |
| Data de exportação | 2026-06-25T19:02:46-03:00 |
| Congelado em | 2026-07-02 |
| Autoria | Felipe Keller (projeto próprio) |

**Integridade:** antes de qualquer run do experimento, conferir
`Get-FileHash predio_v1.ifc -Algorithm SHA256` contra o valor acima.

## Perfil IDS aplicado

- `data/ids_templates/residencial_nbr15575.ids`
- SHA256 do IDS registrado por run nos metadados do experimento (`RunMetadata`).

## Protocolo GT-by-diff (próximos passos)

1. ✅ **C.1** — entrada congelada (este README).
2. ✅ **C.2 passo 1** — `diagnose()` executado; CSV de trabalho com chave natural
   em `issues_v1.csv` (distribuição abaixo).
3. ⬜ **C.2 passo 2** — Felipe enriquece o prédio corretamente no Revit
   (guiado pelo CSV, pela NBR 15575 e pelo vocabulário bSDD — **nunca** pela
   LLM avaliada; guardrail anti-circularidade C.0) → exporta `predio_gt.ifc`.
4. ⬜ **C.2 passo 3** — `python -m src.experiment.gt_extractor --ifc predio_v1.ifc
   --ids ... --gt-ifc predio_gt.ifc --output ground_truth.yaml`.
5. ⬜ **C.2 passo 4** — revisão humana do YAML item a item (`verified: true`,
   `accepted_alternatives` onde houver múltiplos valores corretos).
6. ⬜ **C.2 passo 5** — congelar `ground_truth.yaml` (hash + data + revisor).

## Conteúdo do modelo (contagem de entidades)

| Entidade | Quantidade |
|---|---|
| IfcSpace | 82 |
| IfcWall | 651 |
| IfcSlab | 236 |
| IfcDoor | 203 |
| IfcWindow | 130 |
| IfcColumn | 352 |
| IfcBeam | 0 |

## Distribuição de issues (v1, diagnose de 2026-07-02, IDS residencial_nbr15575)

**Total: 2792 issues** (diagnose em ~11 s). CSV de trabalho com chave natural
`(element_guid, issue_type, check_property)` em `issues_v1.csv`.

### Por tarefa do experimento (meta C.4: ≥ 30 por tarefa)

| Tarefa | Issues | Situação |
|---|---|---|
| Preenchimento de Pset (`pset_missing`) | 1904 | ✅ meta atingida |
| Classificação de sistemas (`system_unclassified`) | 887 | ✅ meta atingida |
| Nomeação de espaços (`space_unnamed`) | **0** | ⚠️ **sem cobertura — ver alerta** |
| Fora do experimento (`relation_broken`) | 1 | — |

### Por severidade

| Severidade | Issues |
|---|---|
| high | 1600 |
| medium | 1191 |
| low | 1 |

### `pset_missing` por propriedade

| Propriedade | Issues |
|---|---|
| FireRating | 1216 |
| ThermalTransmittance | 577 |
| Category (Pset_SpaceCommon) | 82 |
| LoadBearing | 29 |

## ⚠️ Alerta de cobertura: nomeação de espaços

Os 82 IfcSpaces do prédio **já têm nomes funcionais** (nenhum nome genérico
detectado), então a tarefa de nomeação de espaços tem **0 issues** neste
modelo. Decisão necessária (risco nº 3 do plano de orquestração):

1. **Masking no próprio prédio** (recomendado): derivar `predio_v1_masked.ifc`
   removendo/zerando os nomes dos espaços; o GT dessa tarefa vira os nomes
   originais do Felipe (curados, com `accepted_alternatives`). Requer o
   `mask_extractor.py` (Fase C.3, ainda não implementado).
2. **Modelo externo complementar** com masking (também planejado em C.3) —
   resolve ao mesmo tempo a crítica de proveniência única.

As outras duas tarefas têm massa estatística de sobra (1904 e 887 ≥ 30).

## Nota operacional para o enriquecimento no Revit (C.2 passo 2)

- `FireRating` (1216) e `ThermalTransmittance` (577) concentram-se em paredes,
  portas e lajes — no Revit, preencher **por tipo** (não por instância) reduz o
  esforço em ordens de magnitude e é a prática correta de modelagem.
- O CSV `issues_v1.csv` (separador `;`, UTF-8 BOM — abre direto no Excel) lista
  cada elemento com GUID, pavimento e propriedade faltante, na ordem do
  diagnóstico.

