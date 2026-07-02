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

## Protocolo do ground truth (rota adotada: norm-derived-draft)

Em vez do retrabalho completo no Revit (GT-by-diff puro), o GT candidato foi
**derivado deterministicamente, sem LLM** (guardrail C.0 preservado), por
`scripts/build_predio_gt.py`, a partir de: propagação por tipo (valores já
preenchidos pelo projetista no modelo), cálculo NBR 15220-2, TRRF NBR 14432
(Tab. A.1: A-2, P3 → 60 min) e mapeamentos fechados. A revisão humana item a
item continua obrigatória — é ela que transforma o rascunho em padrão-ouro.

1. ✅ **C.1** — entrada congelada (este README).
2. ✅ **C.2 passo 1** — `diagnose()` executado; CSV de trabalho com chave natural
   em `issues_v1.csv` (distribuição abaixo).
3. ✅ **C.2 passo 3 (rota norm-derived)** — `ground_truth.yaml` gerado com 2546
   itens (`verified: false`) + 246 abstenções documentadas; regras e memórias
   de cálculo em `scripts/build_predio_gt.py` e resumo em `REVISAO_GT.md`.
4. ✅ **C.2 passo 4** — revisão humana concluída em 2026-07-02: Felipe Keller
   revisou o `REVISAO_GT.md` (itens agrupados) e aprovou integralmente;
   todos os 2546 itens com `verified: true`.
5. ✅ **C.2 passo 5** — `ground_truth.yaml` **congelado**:

   | Campo | Valor |
   |---|---|
   | SHA256 | `3924D611219A00A05BF2643EB19D43300DC9EBDF391DB72B0E5AFF3E5F366BA3` |
   | Itens | 2546 (1674 `pset_missing` + 872 `system_unclassified`), 100% verified |
   | Abstenções | 246 (documentadas no próprio YAML, seção `skipped`) |
   | Revisor | Felipe Keller (autor do projeto) |
   | Data | 2026-07-02 |

   Qualquer alteração posterior exige nova revisão e novo hash.
   Pendência externa: comunicar a rota norm-derived ao orientador e declarar
   o método na seção de materiais do artigo.

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

## Variante mascarada: tarefa de nomeação de espaços (Fase C.3)

Gerada por `python -m src.experiment.mask_extractor` em 2026-07-02, resolve o
alerta de cobertura abaixo:

| Campo | Valor |
|---|---|
| Arquivo | `predio_v1_masked.ifc` (não versionado; `*.ifc` no `.gitignore`) |
| SHA256 | `D867AA3D97884815A02953B4CE636D12DA0901E67539BCDDCE28089F531F2277` |
| Derivação | `predio_v1.ifc` com `LongName` dos 82 IfcSpaces removidos (o `Name` numérico do Revit é preservado e dispara `space_unnamed`) |
| GT | `ground_truth_spaces.yaml` — 82 itens, nomes originais do autor, **100% verified** |
| Curadoria | concluída em 2026-07-02 (delegada pelo autor): sinônimos conservadores em `accepted_alternatives` para todos os 82 itens (ex.: "Lavatório Social" ≈ "Lavabo Social"/"WC Social"; "Quarto N" ≈ "Dormitório N"; "Sacada" ≈ "Varanda") |
| SHA256 (congelado) | `F1451E983F7A6A869C908051A7C527F394CAE670E07FC3DA2A4432682C065AC8` |

Verificado: `diagnose` no modelo mascarado gera exatamente 82 issues
`space_unnamed`, casando com o GT pela chave natural.

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

