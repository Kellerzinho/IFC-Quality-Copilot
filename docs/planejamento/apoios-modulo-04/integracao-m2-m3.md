# Integração M4 ↔ M2/M3 — estudo de contratos (rascunho para discussão)

> **Estado:** estudo de leitura, 28/10/2026. Nenhum adaptador foi implementado.
> **Base M4:** `feat/m4-plataforma-base` (PR #5), contratos em `src/review_api/schemas.py`
> (`schema_version = "m4-plataforma-base/1"`, `Gap`/`Suggestion` com
> `schema_status = "provisorio_aguardando_M2_M3"`).
> **Base M2/M3 (Felipe):** `origin/codex/m1-domain-catalog` @ `6965639`, lida sem checkout
> (`git show`). Arquivos lidos: `src/validation/{diagnostic_models,ids_engine,analysis_service,catalog_analysis,analysis_identity}.py`,
> `src/suggestion_engine/{catalog_contracts,catalog_context,catalog_evidence}.py`,
> `src/ifc_analyzer/{identity,observations}.py`, `src/operations/{contracts,project_models,project_service,database}.py`,
> `src/artifacts/storage.py` (cabeçalho). Planos: M2, M3 §5–§7, M4 §4–§5.
>
> Este documento descreve o que está no código das duas branches nesta data. Onde o código
> do Felipe e o plano divergem, a divergência está marcada; não é uma decisão.

## 1. Resumo

1. **Os modelos do Felipe já são os contratos que o plano M4 pede** (`ElementRef`,
   `RequirementResult`, `DiagnosticSnapshot`, `FieldRef`, `FieldAlternative`,
   `FieldEnrichmentResult`, `ModelPairBinding`). Os nossos `Gap` e `Suggestion` são
   provisórios e devem virar **projeções de leitura** desses contratos, não um terceiro modelo.
2. **Identidade:** a nossa `ElementRef` (modelo + revisão SHA-256 + express_id) e a dele
   (fonte + revisão inteira + SHA-256 + express_id) não são intercambiáveis. A dele distingue
   "mesmos bytes enviados duas vezes" (duas revisões); a nossa não. Os ids também têm formatos
   diferentes (hex sem hífen × UUID canônico).
3. **Armazenamento concorre.** `src/operations` (SQLite `operations.sqlite3` com WAL, CAS,
   comandos/recibos/eventos) e `src/artifacts` (`s/<papel>/<sha256>`) cobrem o que a
   `review_api` faz em memória/`blobs/` e o `m4_projects.sqlite3` provisório do Bloco 2
   (abrir projeto existente). A proposta (§5) é a `review_api` virar fachada sobre o
   `ProjectService`, com o nosso armazenamento aposentado.
4. **Lacunas reais:** sem `real/decimal` no `TypedValue` dele; unidade fixa em
   `not_applicable` nas alternativas; sem listagem de projetos; sem rota HTTP; par só existe
   com IFC **e** IDS (a nossa "linha só com IFC" para navegar não tem equivalente).

## 2. Tabela campo a campo

### 2.1 Elemento

| Nosso (`review_api.schemas.ElementRef` / `ElementRecord`) | Felipe (`ifc_analyzer.identity.ElementRef`) | Situação |
|---|---|---|
| `model_id: str` (uuid4 **hex sem hífen**) | — (o modelo vem pela fonte) | **Conflito.** Ele identifica a fonte, não o modelo; `model_id` fica em `SourceArtifactRef` |
| — | `source_id: CanonicalUUID` (8-4-4-4-12) | **Falta** no nosso |
| `ifc_revision_id: Sha256Hex` | `revision: PositiveInt` + `sha256: Sha256Hex` | **Conflito.** Nossa revisão *é* o hash; a dele é número + hash |
| `express_id: int > 0` | `express_id: PositiveInt` | Bate |
| `ElementRecord.ifc_class` | `ifc_class` (padrão `^Ifc…`) | Bate (ele traz na própria ref) |
| `ElementRecord.global_id` | `global_id: str \| None` | Bate |
| `global_id_state: unique \| duplicated_in_file \| missing` | `guid_state: valid \| missing \| invalid \| duplicate` | **Mapeável com perda:** `unique→valid`, `duplicated_in_file→duplicate`, `missing→missing`; o nosso não distingue `invalid` (GUID fora da sintaxe vira `unique`) |
| `ElementRecord.name` | — (vem por observação) | Falta no dele; a lista da UI precisa do nome |
| `ElementRecord.has_geometry` | — | Falta no dele; é dado de visualização (M4), não de M2 — continua nosso |
| chave `model:rev:express` (`elementKey`) | `key() = (source_id, revision, sha256, express_id)` | **Conflito de chave** (§3) |

### 2.2 Fonte e par

| Nosso | Felipe (`operations`) | Situação |
|---|---|---|
| `SourceArtifactRef.role` | `role` | Bate |
| `revision_id` (= SHA-256) | `source_id` + `revision` + `sha256` | Conflito (como acima) |
| `size_bytes`, `display_name` | `size_bytes`, `display_name` (recusa `\/:*?"<>\|`) | Bate; ele valida o nome — o nosso aceita qualquer texto |
| `ifc_schema` | `declared_schema` | Bate (nome diferente) |
| — | `project_id`, `model_id`, `storage_key = s/<papel>/<sha>` | Falta no nosso (interno dele) |
| `ModelPairBinding` (linha) existe vazia desde a criação do projeto | `ModelRecord` + `ModelPairBinding` só com IFC **e** IDS | **Conflito de ciclo de vida** (§4) |
| `discipline: architecture \| structure` | `discipline: NonEmptyText` livre | Nosso é mais restrito; o dele aceita o nosso |
| `confirmed: bool` + `confirmed_*_revision_id` | `pair_revision`, `active`, `confirmed_by_actor_context_id` | Dele é mais rico: confirmação é ato de ator, com revisão do par |
| `Project(project_id, name, models)` | `ProjectRecord(project_id, name, pair_set_revision, active_pair_refs ≤ 2, created_by…, created_at_utc)` + `ProjectState` | Dele cobre o nosso; o nosso não tem ator nem revisão do conjunto |

### 2.3 Lacuna (`Gap` provisório) × diagnóstico M2

O nosso `Gap` é **uma linha não conforme** vista pela UI. O equivalente dele é
`RequirementResult` com `state = non_compliant` (e as demais linhas), mais `ExpectedField`,
`EvidenceObservation` e `SearchReport` do mesmo `DiagnosticSnapshot`.

| Nosso `Gap` | Felipe | Situação |
|---|---|---|
| `gap_id: str` (do adaptador legado) | `(analysis_id, requirement.key(), element.key())` | Derivável; ele não tem id próprio de linha |
| `origin: legacy_ifc_analyzer \| …` | `snapshot.identity` (verificador, condição `m1-e3-evidence-v1`) | Dele é rastreável ao runtime; o nosso só diz "legado" |
| `resolution: resolved \| ambiguous` | `state` (5 estados) + `reason` | **Falta no nosso:** `not_applicable`, `not_verified`, `error` e `compliant`. "Ambígua" (GUID repetido) não é estado formal dele: com `ElementRef` por express_id não há ambiguidade de alvo — a ambiguidade só existia porque o legado devolve GlobalId |
| `element: ElementRef \| None` | `element: ElementRef \| None` (None = linha de escopo) | Bate na forma; **semântica diferente**: nosso None = alvo ambíguo; dele None = linha da especificação |
| `candidates: list[ElementRef]` | — | Some com o motor M2 (não há GlobalId como chave) |
| `ifc_class`, `element_name`, `global_id` | `element.ifc_class`, `element.global_id`; nome via observação | Bate (nome falta) |
| `requirement.property_set / property_name` | `ExpectedField.set_name / field_name: IDSValue` | Bate; dele pode ser restrição (padrão/enum), não só texto |
| `requirement.check`, `expected_value`, `unit` | `ExpectedField.value: IDSValue`, `data_type`, `cardinality` (+ origem) | Dele é mais rico; o nosso `check` é texto do legado |
| `requirement.specification: str` | `RequirementRef` (hash do IDS + índices) + `SpecificationResult.name` | Dele é localizador estável; o nosso é só o nome |
| `current_value: ObservedValue(state, kind, value)` | `EvidenceObservation(state, raw_value, typed_value, ifc_type, unit_state, unit, origem occurrence/type)` | Bate em espírito; o dele traz portador, origem (tipo × ocorrência) e unidade |
| `provisional_marker` ("A definir", "0", "FALSE") | — | **Falta no dele.** É observação nossa; precisa decidir se vira regra M2, M3 ou fica na UI |
| — | `capability_cell`, `backend_passed`, `annotation` (catálogo) | Falta no nosso; a UI deve mostrar "não verificado por capacidade" |
| `GapList.limitations` | `CoverageSummary`, `TechnicalProblem` | Dele é mais completo (denominador desconhecido = `None`, não zero) |

### 2.4 Sugestão provisória × enriquecimento M3

| Nosso `Suggestion` | Felipe (`catalog_contracts`) | Situação |
|---|---|---|
| `outcome: proposed \| abstained` | `FieldEnrichmentResult.status: proposed \| abstained \| unsupported \| failed \| not_requested` | **Falta no nosso:** `unsupported`, `failed` (técnica ≠ abstenção) e `not_requested` |
| `field: FieldRef(element, property_set, property_name)` | `FieldRef(analysis_id, snapshot_id, element, requirement, target_set_name, target_field_name, binding_id, concept_id)` | Dele amarra à análise e ao requisito — necessário para descartar resposta de outra análise (M4 `AnalysisViewRef`) |
| `alternatives[].alternative_id` | — (posição na tupla; hash do resultado) | Falta no dele: a UI precisa de id estável para `ReviewCommand` |
| `value: ProposedValue(kind boolean\|integer\|real\|string, value, unit)` | `value: TypedValue` (`string \| boolean \| integer`), `unit_state = "not_applicable"` fixo | **Conflito:** sem real/decimal e sem unidade no dele (o plano M2/M3 prevê decimal, enum, data, referência, coleção) |
| `method: str` | `method: exact_recovery \| code_standardization` | Bate (dele fechado) |
| `evidence: list[str] ≥ 1` | `evidence_refs: tuple[Sha256Hex] ≥ 1` (ids de observação) | Bate na regra; dele é referência resolvível, nosso é texto |
| `justification: str` | `transformation: str \| None` | Parcial |
| `limitations` | `FieldEnrichmentResult.limitations` | Bate (nível diferente) |
| `reason` (abstenção, texto livre) | `reason: M3Reason` (≈ 40 motivos fechados) + `reasons` | Dele é fechado; a UI precisa de rótulo PT por motivo |
| — | `candidate_validation`, `target_binding_id`, `target_scope = occurrence`, `would_modify_type = False`, `affected_elements` (exatamente 1), `requires_human_review = True` | Falta no nosso; são as garantias que a prévia M4/M5 precisa mostrar |
| — | `EvidenceAssessment` (status, conflitos, cobertura, ação requerida) | Falta no nosso; base do painel de evidência |

## 3. Conflitos de identidade

**C1 — o que é "revisão".** Para nós, revisão = SHA-256 dos bytes (`register_source` devolve a
mesma revisão para o mesmo arquivo, com outro nome). Para o Felipe, revisão é um contador por
fonte, e o hash é atributo: os mesmos bytes enviados de novo são outra revisão
(`SourceArtifactRef` doc). Consequência: uma `ElementRef` nossa não determina a dele (falta
`source_id` e `revision`); a dele determina a nossa se soubermos o `model_id` da fonte.

**C2 — modelo × fonte.** Nossa chave começa no `model_id` (linha do projeto). A dele começa no
`source_id`. O `model_id` está no `SourceArtifactRef`, então a tradução dele → nosso é direta
via `ProjectState.sources`.

**C3 — formato dos ids.** `uuid4().hex` (32 hex) não passa no `CanonicalUUID` dele (exige
hífens, minúsculo). Qualquer id gerado pela `review_api` atual é recusado pelos contratos dele.

**C4 — chave na UI.** `elementKey = model:rev:express` está em toda a UI (lista, mapa do viewer,
seleção, isolamento, testes, e2e). Trocar o formato da chave é mudança ampla, mas mecânica,
desde que a chave continue sendo *texto opaco* para a UI.

**C5 — ambiguidade.** Nossa lacuna "ambígua" vem do legado (que aponta GlobalId). Com o motor
M2 do Felipe, cada linha já sai por `ElementRef`; o caso J-01/J-02 deixa de produzir lacuna
ambígua e passa a produzir duas linhas, uma por janela. O teste T4-04 e o checklist e2e
"J-01/J-02 ambíguas" precisarão ser reescritos para a nova semântica (o GUID repetido continua
visível como `guid_state = duplicate`).

**Proposta de identidade:** a UI passa a usar como chave `source_id:revision:express_id`
(o hash entra para conferência, não para a chave), recebida pronta do servidor como
`element_key`. O mapa do viewer continua amarrando chave ↔ localId verificado por classe e
GlobalId, sem mudança de regra. O `model_id` vira atributo de agrupamento (disciplina/linha).

## 4. Armazenamento: `src/operations` × `review_api`

| Aspecto | `review_api` (PR #5) | `src/operations` + `src/artifacts` (Felipe) |
|---|---|---|
| Projetos | memória + `m4_projects.sqlite3` provisório (Bloco 2) | `operations.sqlite3`, tabela `projects` com heads/CAS |
| Fontes | `blobs/<sha>.<role>` sem fsync | `s/<papel>/<sha256>`, fsync, sem sobrescrever, recusa link/junction |
| Pares | linha criada vazia; upload invalida confirmação | par só com IFC+IDS; revisão de par; ≤ 2 ativos |
| Ator | nenhum | `actor_context_id` em todo comando; recibo com `ActorSnapshot` |
| Idempotência | nenhuma | `command_id` + hash do payload; recibo `applied`/`noop` |
| Análise | adaptador legado síncrono, cache em memória | run durável `queued → running → completed/failed`, lock de arquivo, snapshot imutável |
| Listagem de projetos | `GET /api/v1/projects` (Bloco 2) | **não existe** (só `load_project_state(id)`) |
| HTTP | FastAPI em 127.0.0.1, Host/Origin em allowlist | nenhum |

**Concorrem**, sim: dois bancos SQLite e dois layouts de blobs para os mesmos objetos. Manter
os dois criaria duas verdades sobre "qual IFC é a revisão atual".

**Proposta de unificação:**

1. O `ProjectService` (+ `OperationalStore`, `LocalArtifactStore`) é a **autoridade**. A
   `review_api` vira fachada HTTP: valida acesso local, traduz pedido → `OperationalCommand`,
   devolve projeções de leitura para a UI.
2. A raiz de dados é a mesma (`%LOCALAPPDATA%/IFC-Quality-Copilot/...`), com `purpose`
   `operational` em produção e `synthetic_test` em teste/e2e.
3. O `m4_projects.sqlite3` e o `ArtifactStore` da `review_api` são aposentados; não há
   migração de dados (a M4 ainda não tem dados reais), só um aviso no log se encontrar o
   arquivo antigo.
4. Falta no `ProjectService`: **listar projetos** (para "Projetos recentes") e o conceito de
   **linha sem par** (IFC enviado, IDS ainda não). Ou a UI aceita que só existe navegação
   depois do par, ou o serviço expõe "modelo com fonte, sem par".

## 5. Plano do adaptador em etapas

| Etapa | O que | Saída verificável | Risco |
|---|---|---|---|
| A0 | Acordar perguntas da §7 com o Felipe | respostas registradas aqui | — |
| A1 | Projeções de leitura em Python: `ElementView`, `RequirementRowView`, `FieldEnrichmentView` montadas a partir de `DiagnosticSnapshot`/`EnrichmentRun`, com `element_key` pronto | testes com snapshot sintético (corpus M4) | `DiagnosticSnapshot` exige `VerifierIdentity` real: construir em teste pode exigir runtime completo |
| A2 | `review_api` lê de `ProjectService` (projeto, fontes, pares) atrás de flag; escrita ainda no armazenamento atual | contratos OpenAPI sem quebra; e2e verde nos dois modos | duas fontes de verdade durante a transição |
| A3 | Upload/confirmação viram comandos (`register_source_revision`, `register_pair`) com `actor_context_id` local | recibo exibido na UI; idempotência por `command_id` | ator local: quem é o "humano" no MVP? (M6) |
| A4 | Análise: rota enfileira `queue_initial_analysis`; UI consome eventos/estado do run; adaptador legado sai | diagnóstico com 5 estados na lista; `not_verified` visível | tempo de análise no corpus real; UI precisa de estado "em análise" |
| A5 | Enriquecimento M3 na UI: `FieldEnrichmentResult` → painel de detalhe com alternativas e motivos | `Suggestion` provisório removido do OpenAPI | `TypedValue` sem decimal/unidade bloqueia U, fck, cobrimento |
| A6 | Remover `m4_projects.sqlite3`, `ArtifactStore`, `legacy_adapter.py`, `Gap` provisório | `schema_version` M4 novo; tipos TS regenerados | testes e2e e Vitest com fixtures novas |

Riscos transversais: (R1) a branch dele tem ~220 arquivos e 90 mil linhas; integrar exige que
ela entre na `main` antes (não depender de branch não mesclada). (R2) Ids canônicos com hífen
mudam todas as fixtures de frontend. (R3) Semântica de "ambígua" muda (C5); o checklist
precisa ser reescrito, não só adaptado. (R4) O lock de arquivo do coordenador e o servidor
HTTP precisam conviver no mesmo processo ou em processos separados — decisão M6.

### Esboço de tipos (TS, só ilustrativo — não implementado)

```ts
// Projeção de leitura que a review_api serviria depois da A1. Chave opaca do servidor.
// type ElementKey = string;                       // "source_id:revision:express_id"
// interface ElementView {
//   element_key: ElementKey;
//   model_id: string;                             // linha/disciplina, para agrupar
//   source: { source_id: string; revision: number; sha256: string };
//   express_id: number;
//   ifc_class: string;
//   global_id: string | null;
//   guid_state: "valid" | "missing" | "invalid" | "duplicate";
//   name: string | null;                          // observação de Name, se lida
//   has_geometry: boolean;                        // M4 (viewer), não M2
// }
// type FormalState = "compliant" | "non_compliant" | "not_applicable" | "not_verified" | "error";
// interface RequirementRowView {
//   analysis_id: string; snapshot_id: string;
//   requirement_key: string;                      // RequirementRef.key()
//   element_key: ElementKey | null;               // null = linha de escopo
//   state: FormalState; reason: string | null;
//   expected: { set_name: string | null; field_name: string | null; data_type: string | null; value: string | null };
//   observed: { state: string; value: string | boolean | number | null; unit: string | null } | null;
//   capability_cell: string;
// }
// interface FieldEnrichmentView {
//   field: { analysis_id: string; element_key: ElementKey; requirement_key: string };
//   status: "proposed" | "abstained" | "unsupported" | "failed" | "not_requested";
//   reason: string | null;                        // M3Reason → rótulo PT na UI
//   alternatives: { alternative_key: string; value: { tag: "string" | "boolean" | "integer"; value: string | boolean | number };
//                   method: "exact_recovery" | "code_standardization"; evidence_refs: string[] }[];
// }
```

## 6. O que não muda

- Viewer: mapa explícito chave ↔ localId verificado por classe e GlobalId (só o texto da chave muda).
- Regras de acesso local (Host/Origin), CSP e ativos locais.
- "O IFC só é alterado após aprovação humana explícita": as garantias de `FieldAlternative`
  (`requires_human_review = True`, `affected_elements` = 1) reforçam a regra.

## 7. Perguntas para o Felipe

1. **Revisão:** os mesmos bytes enviados de novo devem ser outra revisão (como está) mesmo
   quando o usuário só reenvia o arquivo? A M4 hoje deduplica por hash. Qual comportamento a UI
   deve mostrar?
2. **Linha sem par:** existe ou pode existir "modelo com IFC registrado e sem IDS" no
   `ProjectService`, para navegar na lista/3D antes do vínculo? Ou a navegação só começa no par?
3. **Listagem:** topa um `list_projects()` (id, nome, datas, pares ativos) no `ProjectService`,
   para substituir o `GET /projects` provisório da M4?
4. **TypedValue:** quando entram `decimal` e unidade (`unit_state = known`)? Sem isso, U, fck e
   cobrimento não chegam à revisão.
5. **Nome do elemento:** o `DiagnosticSnapshot` pode trazer `Name` (e talvez `Description`) por
   elemento, ou a M4 lê à parte? A lista depende disso.
6. **Marcadores provisórios** ("A definir", "0", "FALSE"): são `present` para M2 e assunto do M3,
   ou deveriam virar regra M2? Hoje são observação do adaptador M4.
7. **Ator local:** qual `actor_context_id` a UI usa no MVP (um por instalação? por sessão?), e
   quem cria — `review_api` ou `operations.actor_context`?
8. **Processo:** o `AnalysisCoordinator` (lock de arquivo) roda dentro do processo da API ou num
   worker separado? Isso define se a UI acompanha por eventos ou por polling.
9. **Id de alternativa:** a UI precisa referenciar uma alternativa exata num `ReviewCommand`.
   Usamos `canonical_sha256(alternativa)` ou você prefere um id explícito no contrato?
10. **Ordem de merge:** sua branch entra na `main` antes da integração (para a PR #5 não depender
    de branch aberta)? Há previsão?
