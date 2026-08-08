# Ground Truth Canônico para Prédio e Casa — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar um único `ground_truth.yaml` validado para cada IFC (`predio_v1.ifc` e `casa_v1.ifc`), preservando a base humana do prédio, abstendo-se quando a evidência é insuficiente e mantendo compatibilidade com o avaliador atual.

**Architecture:** O diagnóstico IFC existente continua sendo a fonte das chaves naturais. Um módulo pequeno e independente valida o documento YAML completo, inclusive a seção documental `skipped`, antes de qualquer benchmark. Um script determinístico audita a base do prédio e constrói a casa a partir de evidência do IFC, sem LLM e sem interpretação normativa no computador de benchmark. O `Evaluator` permanece inalterado.

**Tech Stack:** Python 3.11+, Pydantic 2, PyYAML, IfcOpenShell, pytest, pipeline de diagnóstico existente.

## Global Constraints

- O contrato de runtime continua sendo exatamente um YAML por IFC: `metadata`, `items` e `skipped`.
- Todo item pontuável tem `verified: true`, valor não nulo e chave natural completa.
- Incerteza nunca vira rótulo negativo; vira entrada em `skipped` com motivo.
- `check_property` é copiado literalmente da issue, inclusive a diferença entre `LoadBearing` e `IsLoadBearing`.
- A LLM avaliada não participa da construção do GT.
- O GT atual do prédio é a base autoral. Itens com alerta explícito de conferência são abstidos; os demais permanecem como intenção de projeto ratificada, não como laudo de desempenho.
- `AcousticRating`, `SolarHeatGainCoefficient`, relações quebradas e propriedades fora do escopo inicial ficam em `skipped`.
- Não incluir cópias não autorizadas de normas ABNT. Registrar versão, URL oficial e limitação de uso no metadata/documentação.
- O hash final do próprio YAML não entra no arquivo para evitar referência circular; ele é registrado no Git e, depois, nos resultados.
- Commits devem adicionar apenas caminhos desta tarefa; resultados históricos e demais arquivos sujos do usuário não podem ser alterados.

---

## Task 1: Validador estrito do documento de ground truth

**Files:**

- Create: `src/experiment/ground_truth_validation.py`
- Test: `tests/experiment/test_ground_truth_validation.py`

- [ ] **Step 1: Escrever os testes que falham para invariantes locais**

Criar fixtures YAML pequenas e os testes `test_rejects_unverified_item`,
`test_rejects_null_expected_value`, `test_rejects_duplicate_natural_key`,
`test_rejects_duplicate_issue_id`, `test_rejects_item_and_skip_overlap`,
`test_rejects_declared_count_mismatch` e `test_accepts_valid_document`. Cada teste
inválido altera exatamente um campo de um documento-base válido e compara a
mensagem de erro com o nome da invariante violada.

O teste válido deve provar que `GroundTruth.from_yaml(path)` continua carregando o mesmo arquivo e que `skipped` não entra em `GroundTruth.items`.

- [ ] **Step 2: Rodar o teste e confirmar a falha esperada**

Run: `python -m pytest tests/experiment/test_ground_truth_validation.py -q`

Expected: FAIL por ausência de `src.experiment.ground_truth_validation`.

- [ ] **Step 3: Implementar o contrato mínimo**

Implementar o alias `NaturalKey = tuple[str, str, str]`, a exceção
`GroundTruthValidationError(ValueError)`, o modelo
`GroundTruthValidationReport(path: Path, total_items: int, total_skipped: int,
item_keys: set[NaturalKey], skipped_keys: set[NaturalKey])` e estas assinaturas:

- `natural_key_from_mapping(entry: Mapping[str, Any]) -> NaturalKey`;
- `load_ground_truth_document(path: str | Path) -> dict[str, Any]`;
- `validate_ground_truth_document(path: str | Path) -> GroundTruthValidationReport`.

`validate_ground_truth_document` agrega todos os problemas encontrados e levanta uma única `GroundTruthValidationError` com mensagens ordenadas. Validar tipos de raiz/listas, chaves completas, `issue_id`, `expected_value`, `verified`, unicidade, sobreposição e contagens do metadata.

- [ ] **Step 4: Rodar testes focados e regressão do loader**

Run: `python -m pytest tests/experiment/test_ground_truth_validation.py tests/evaluation/test_evaluator_v2.py -q`

Expected: PASS.

- [ ] **Step 5: Commit atômico**

```powershell
git add -- src/experiment/ground_truth_validation.py tests/experiment/test_ground_truth_validation.py
git commit -m "feat: validar ground truth canonico"
```

## Task 2: Casamento com o diagnóstico e hashes congelados

**Files:**

- Modify: `src/experiment/ground_truth_validation.py`
- Modify: `tests/experiment/test_ground_truth_validation.py`

- [ ] **Step 1: Acrescentar testes que falham para evidência externa**

Usar issues sintéticas e arquivos temporários nos testes
`test_rejects_item_without_matching_diagnostic_issue`,
`test_rejects_ifc_hash_mismatch`, `test_rejects_ids_hash_mismatch` e
`test_accepts_matching_issues_and_hashes`. O caso válido calcula os hashes dos
arquivos temporários com `hashlib.sha256(path.read_bytes()).hexdigest()` e os
grava no metadata antes da validação.

- [ ] **Step 2: Confirmar que os testes novos falham**

Run: `python -m pytest tests/experiment/test_ground_truth_validation.py -q`

Expected: FAIL por argumentos/funções ainda inexistentes.

- [ ] **Step 3: Estender a API sem mudar o loader existente**

Adicionar as assinaturas `sha256_file(path: str | Path) -> str` e
`validate_ground_truth_against_issues(path: str | Path, issues: Sequence[Issue],
*, ifc_path: str | Path, ids_path: str | Path) ->
GroundTruthValidationReport`.

A função primeiro chama a validação estrutural, depois compara `input_ifc_sha256` e `ids_sha256` em minúsculas e exige que cada entrada de `items` e `skipped` case com `(element_guid, issue_type, check_property)` do diagnóstico.

- [ ] **Step 4: Rodar todos os testes focados**

Run: `python -m pytest tests/experiment/test_ground_truth_validation.py tests/evaluation/test_evaluator_v2.py -q`

Expected: PASS.

- [ ] **Step 5: Commit atômico**

```powershell
git add -- src/experiment/ground_truth_validation.py tests/experiment/test_ground_truth_validation.py
git commit -m "feat: conferir hashes e issues do ground truth"
```

## Task 3: Política determinística de auditoria

**Files:**

- Create: `src/experiment/ground_truth_audit.py`
- Create: `tests/experiment/test_ground_truth_audit.py`

- [ ] **Step 1: Escrever testes de decisão que falham**

Cobrir as regras sem abrir IFC real com os testes
`test_predio_preserves_verified_legacy_item`,
`test_predio_skips_legacy_item_marked_conferir`,
`test_predio_clears_legacy_alternatives`,
`test_casa_propagates_authored_thermal_value_by_exact_type`,
`test_casa_does_not_infer_fire_rating_from_minimum_requirement`,
`test_casa_does_not_infer_load_bearing_from_ifc_class`,
`test_casa_maps_only_closed_space_categories`,
`test_casa_classifies_only_unambiguous_material_system` e
`test_out_of_scope_property_is_skipped`.

- [ ] **Step 2: Confirmar falha inicial**

Run: `python -m pytest tests/experiment/test_ground_truth_audit.py -q`

Expected: FAIL por ausência do módulo.

- [ ] **Step 3: Implementar modelos e funções puras**

Implementar o modelo `AuditDecision` com `expected_value: Any | None = None`,
`accepted_alternatives: list[Any] = Field(default_factory=list)`, `notes: str |
None = None` e `skip_reason: str | None = None`. Implementar as assinaturas
`audit_legacy_item(issue: Issue, legacy: GroundTruthItem) -> AuditDecision` e
`derive_casa_decision(issue: Issue, *, element_type_name: str,
element_long_name: str | None, authored_thermal_by_type: Mapping[str, float],
material_names: Sequence[str]) -> AuditDecision`.

Regras exatas:

- prédio: preservar o valor esperado verificado e ratificado; mover para `skipped` se `notes` contiver, sem diferenciar caixa/acentos, `CONFERIR`, `SEM ESPECIFICAÇÃO`, `PROVÁVEL` ou `USUAL`; limpar todas as `accepted_alternatives`, pois a nova referência tem um único valor esperado por issue; anexar uma única vez a nota de que o valor mantido representa intenção autoral e não laudo;
- casa/ThermalTransmittance: aceitar somente valor positivo já declarado em outra instância do mesmo tipo exato; nenhuma constante genérica de vidro/telha;
- casa/FireRating e `LoadBearing`/`IsLoadBearing`: `skipped` por falta de declaração de desempenho/intencionalidade;
- casa/Category: vocabulário fechado `BATHROOM`, `BEDROOM`, `WC`, `CIRCULATION`, `LIVING_ROOM`, `KITCHEN`, `TECHNICAL_AREA`, `BALCONY`, `SERVICE_AREA`, `STORAGE`, mapeado somente por nome inequívoco;
- casa/system_unclassified: normalizar nomes sem caixa/acentos e aceitar somente uma família inequívoca: `concreto` → `Concreto armado moldado in loco`; `bloco cerâmico` → `Alvenaria de vedação em bloco cerâmico`; `bloco de concreto` → `Alvenaria em bloco de concreto`; `drywall` ou `gesso acartonado` → `Drywall / Steel frame`; `madeira` → `Sistema em madeira`; `vidro` → `Sistema envidraçado`. Mais de uma família, ausência de família ou nomes genéricos ficam em `skipped`;
- demais propriedades/tipos: `skipped` com razão `fora do escopo evidence-audited-v1`.

- [ ] **Step 4: Rodar os testes**

Run: `python -m pytest tests/experiment/test_ground_truth_audit.py -q`

Expected: PASS.

- [ ] **Step 5: Commit atômico**

```powershell
git add -- src/experiment/ground_truth_audit.py tests/experiment/test_ground_truth_audit.py
git commit -m "feat: auditar rotulos de ground truth sem llm"
```

## Task 4: Construtor canônico dos dois datasets

**Files:**

- Create: `scripts/build_ground_truths.py`
- Create: `tests/experiment/test_build_ground_truths.py`
- Preserve as historical utility: `scripts/build_predio_gt.py`

- [ ] **Step 1: Criar testes que falham para a orquestração**

Testar com dublês pequenos em `test_dataset_registry_has_predio_and_casa_only`,
`test_build_preserves_literal_check_property`,
`test_build_partitions_every_issue_into_item_or_skip`,
`test_build_orders_output_deterministically` e
`test_build_refuses_to_overwrite_without_valid_output`.

- [ ] **Step 2: Confirmar falha inicial**

Run: `python -m pytest tests/experiment/test_build_ground_truths.py -q`

Expected: FAIL por ausência do script.

- [ ] **Step 3: Implementar CLI e escrita atômica**

Contrato: `DatasetSpec` é um `@dataclass(frozen=True)` com `key: str`,
`ifc_path: Path`, `ground_truth_path: Path` e `building_context: dict[str, str]`.
`DATASETS` contém exatamente:

- `predio`: `data/evaluation/predio/predio_v1.ifc`,
  `data/evaluation/predio/ground_truth.yaml`, contexto
  `{"building_type": "Residencial multifamiliar", "bioclimatic_zone": "4A"}`;
- `casa`: `data/evaluation/casa/casa_v1.ifc`,
  `data/evaluation/casa/ground_truth.yaml`, contexto
  `{"building_type": "Residencial unifamiliar", "bioclimatic_zone": "4A"}`.

Implementar `build_dataset(spec: DatasetSpec, *, legacy_gt_path: Path | None =
None) -> tuple[GTExtractionResult, list[Issue]]`,
`write_canonical_ground_truth(result: GTExtractionResult, issues: Sequence[Issue],
spec: DatasetSpec) -> Path` e `main(argv: list[str] | None = None) -> int`.

CLI: `python scripts/build_ground_truths.py --dataset predio|casa|all`. O default é `all`. Para o prédio, carregar o YAML atual em memória antes de gerar. Se ele já tiver protocolo `evidence-audited-v1`, reutilizar seus itens sem repetir o sufixo de auditoria; `previous_gt_sha256` permanece o hash congelado da base de 2026-07-02. Escrever primeiro em arquivo temporário no mesmo diretório, validar documento/hashes/issues, e somente então usar `Path.replace()` no caminho canônico. Se validar falhar, preservar o YAML anterior.

Metadata obrigatório:

```yaml
protocol: evidence-audited-v1
source_dataset: predio|casa
locality: Deodoro, Rio de Janeiro/RJ
building_type: Residencial multifamiliar|Residencial unifamiliar
bioclimatic_context: ZB 4A
bioclimatic_context_status: public technical source; not a formal conformity declaration
input_ifc_sha256: hash SHA-256 calculado do IFC canônico
ids_sha256: f698f2c020d79140bb314f077f8de680f492fd7ba42867e4000a4cead5d20905
previous_gt_sha256: d08d2c7466a71c0cde467a959ed2aebfd4857d1da64944e4504f8f97d4edd6f6 # só prédio
verified_by: Felipe Keller (autor do projeto)
verified_at: '2026-08-08'
total_diagnostic_issues: inteiro igual a len(report.issues)
total_items: inteiro igual a len(items)
total_skipped: inteiro igual a len(skipped)
```

O script deve exigir `len(items) + len(skipped) == len(report.issues)` e não deve usar relógio no ordenamento/conteúdo, exceto `verified_at` congelado acima, para que duas execuções sejam byte a byte iguais.

- [ ] **Step 4: Rodar testes de orquestração**

Run: `python -m pytest tests/experiment/test_build_ground_truths.py -q`

Expected: PASS.

- [ ] **Step 5: Commit atômico**

```powershell
git add -- scripts/build_ground_truths.py tests/experiment/test_build_ground_truths.py
git commit -m "feat: construir ground truth de predio e casa"
```

## Task 5: Congelar o dataset da casa e regenerar os YAMLs

**Files:**

- Create locally (large input, distribution artifact): `data/evaluation/casa/casa_v1.ifc`
- Create: `data/evaluation/casa/ground_truth.yaml`
- Modify: `data/evaluation/predio/ground_truth.yaml`
- Create: `tests/experiment/test_ground_truth_datasets.py`

- [ ] **Step 1: Preparar o IFC canônico da casa sem alterar o original**

Copiar `casa_v1.ifc` para `data/evaluation/casa/casa_v1.ifc`, confirmar tamanho `98.786.386` bytes e SHA-256 `3B84789C7396449F2C8A3D2F4A66468D81E59F8351EBD4B71FAD161FA06112F2`. Confirmar também o prédio com SHA-256 `A71C8BE30D82760218F5B3F3A1C476B49E3F30E608B0065916B9D5206A1A6DD0`.

- [ ] **Step 2: Escrever o teste de integração real antes da geração**

Teste parametrizado `predio/casa` deve:

1. diagnosticar o IFC com o contexto do dataset;
2. chamar `validate_ground_truth_against_issues`;
3. carregar com `GroundTruth.from_yaml`;
4. afirmar `all(item.verified for item in gt.items)`;
5. afirmar cobertura exclusiva: toda issue está exatamente em `items` ou `skipped`;
6. afirmar que nenhum item da casa tem `AcousticRating` ou `SolarHeatGainCoefficient`;
7. afirmar que o prédio registra `previous_gt_sha256` igual a `d08d2c7466a71c0cde467a959ed2aebfd4857d1da64944e4504f8f97d4edd6f6`.

- [ ] **Step 3: Confirmar que o teste falha pela ausência do GT da casa**

Run: `python -m pytest tests/experiment/test_ground_truth_datasets.py -q`

Expected: FAIL porque `data/evaluation/casa/ground_truth.yaml` ainda não existe.

- [ ] **Step 4: Gerar os dois YAMLs canônicos**

Run: `python scripts/build_ground_truths.py --dataset all`

Expected: saída informa, para cada dataset, total de issues, itens, skips, SHA-256 de entrada e caminho final validado.

- [ ] **Step 5: Provar determinismo**

Calcular SHA-256 dos dois YAMLs, executar novamente o mesmo comando e confirmar hashes idênticos.

- [ ] **Step 6: Rodar testes reais**

Run: `python -m pytest tests/experiment/test_ground_truth_datasets.py -q`

Expected: PASS.

- [ ] **Step 7: Commit dos artefatos versionáveis**

```powershell
git add -- data/evaluation/predio/ground_truth.yaml data/evaluation/casa/ground_truth.yaml tests/experiment/test_ground_truth_datasets.py
git commit -m "data: congelar ground truth de predio e casa"
```

O IFC grande da casa permanece artefato local/distribuído conforme a política já usada para IFCs; não forçar `git add` se estiver ignorado.

## Task 6: Documentar proveniência e limitações

**Files:**

- Modify: `data/evaluation/predio/README.md`
- Create: `data/evaluation/casa/README.md`
- Create: `references/normative/public/README.md`
- Create: `references/normative/public/sources.yaml`

- [ ] **Step 1: Registrar a proveniência sem redistribuir material protegido**

Os READMEs devem registrar hashes finais dos YAMLs, hashes dos IFCs, data, protocolo, contagens, contexto Deodoro/Rio, ZB 4A e a distinção entre intenção autoral e laudo/conformidade.

`sources.yaml` deve conter título, versão/data, emissor, URL oficial, `redistribution: link-only` e observação para:

- ABNT NBR 15220-3:2024;
- ABNT TR 15220-3-1:2024 Versão Corrigida:2025;
- ABNT NBR 15575-1/-4/-5:2025;
- LabEEE/UFSC zoneamento e lista Sudeste;
- COSCIP Decreto Estadual 42/2018 compilado;
- CBMERJ NT 1-04, NT 2-08, NT 2-18 e NT 2-19:2025 com Portaria 1.317/2025.

- [ ] **Step 2: Validar YAML de fontes e ausência de PDFs ABNT**

Run:

```powershell
python -c "import yaml; yaml.safe_load(open('references/normative/public/sources.yaml', encoding='utf-8')); print('ok')"
Get-ChildItem -LiteralPath references/normative/public -Recurse -Filter *.pdf
```

Expected: `ok`; nenhum PDF ABNT presente.

- [ ] **Step 3: Commit atômico**

```powershell
git add -- data/evaluation/predio/README.md data/evaluation/casa/README.md references/normative/public/README.md references/normative/public/sources.yaml
git commit -m "docs: registrar proveniencia dos ground truths"
```

## Task 7: Verificação final deste subprojeto

**Files:**

- Verify only; no expected source changes.

- [ ] **Step 1: Executar testes focados**

Run:

```powershell
python -m pytest tests/experiment/test_ground_truth_validation.py tests/experiment/test_ground_truth_audit.py tests/experiment/test_build_ground_truths.py tests/experiment/test_ground_truth_datasets.py tests/test_gt_extractor.py tests/evaluation/test_evaluator_v2.py -q
```

Expected: PASS.

- [ ] **Step 2: Executar qualidade estática nos arquivos alterados**

Run:

```powershell
python -m ruff check src/experiment/ground_truth_validation.py src/experiment/ground_truth_audit.py scripts/build_ground_truths.py tests/experiment
python -m mypy src/experiment/ground_truth_validation.py src/experiment/ground_truth_audit.py
```

Expected: PASS; se `mypy` não estiver configurado no projeto, registrar explicitamente `not configured` e não ocultar o fato.

- [ ] **Step 3: Validar os dois artefatos contra diagnósticos reais**

Run: `python scripts/build_ground_truths.py --dataset all --check`

Expected: exit code 0, nenhum arquivo alterado, hashes de saída iguais aos congelados.

- [ ] **Step 4: Revisar diff e estado do repositório**

Run:

```powershell
git diff --check
git status --short -- src/experiment scripts data/evaluation references/normative/public tests docs/superpowers
```

Expected: nenhum whitespace error e somente mudanças intencionais/untracked do usuário preservados.
