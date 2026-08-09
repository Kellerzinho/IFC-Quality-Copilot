# Full-Coverage Ground Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar os 4.983 diagnósticos congelados de `predio_v1.ifc` e `casa_v1.ifc` pontuáveis, com um valor técnico concreto por ocorrência, metadados explícitos de confiança/proveniência, métrica principal por equivalência e uma nova release Windows de execução única.

**Architecture:** A identidade de equivalência será extraída da mesma assinatura estrutural usada pelo `reuse_equivalent`. Um resolvedor determinístico, sem LLM, aplicará a hierarquia IFC → legado → doador equivalente → cálculo → regra → tipologia → hipótese provável. O builder migrará os dois YAMLs para cobertura integral, preservará semanticamente os 1.666 rótulos existentes por meio de um lock agregado e falhará antes da escrita em qualquer conflito. O avaliador manterá as métricas antigas e acrescentará cortes por ocorrência, equivalência, confiança e legado. Os novos hashes entrarão na identidade de execução e na release Windows reconstruída.

**Tech Stack:** Python 3.12.13, Pydantic 2, PyYAML, IfcOpenShell, pytest, Ruff, mypy, `uv` 0.12.3, PowerShell 5.1/7 e o pipeline/runner existentes.

## Global Constraints

- Os artefatos finais continuam sendo exatamente `data/evaluation/predio/ground_truth.yaml` e `data/evaluation/casa/ground_truth.yaml`; ambos terão `skipped: []`.
- Cobertura obrigatória: prédio `4720/4720`, casa `263/263`, total `4983/4983`.
- Cada item canônico terá chave natural completa, `issue_id`, valor concreto, `equivalence_id`, `confidence`, `source_kind`, `legacy_reference`, `verified: true` e `notes` não vazias.
- `verified: true` significa “referência congelada do experimento”, não conformidade normativa.
- A LLM avaliada não participa da construção, escolha ou votação dos rótulos.
- O gerador não usa rede. Qualquer fonte normativa precisa estar identificada no catálogo público de proveniência; normas licenciadas não são copiadas para o repositório.
- Os 1.654 itens atuais do prédio e 12 da casa devem preservar chave natural, `issue_id`, `expected_value` e `accepted_alternatives` semanticamente. Eles terão `legacy_reference: true`; todos os demais terão `false`.
- Não são valores válidos: `null`, string vazia, `unknown`, `not_applicable`, `review_required`, `pending_review` ou sentinela equivalente.
- Itens `confidence: low` devem começar a explicação com `Hipótese congelada:` e identificar os sinais usados e os ausentes.
- Uma classe de equivalência não pode conter decisões divergentes. Se atributos técnicos alterarem o valor, eles devem participar da assinatura usada também pelo reuso real; nunca dividir a classe usando o próprio rótulo esperado.
- Todos os serializadores usam UTF-8, LF, chaves/itens em ordem estável e escrita atômica.
- O hash do próprio YAML não entra no YAML. Os SHA-256 finais ficam nos pins Python, identidade de execução, manifesto da release e recibo de benchmark.
- Não alterar resultados históricos. Resultados anteriores permanecem vinculados aos hashes antigos.
- Preservar mudanças alheias do usuário. Cada commit deve usar pathspec explícito e conter apenas arquivos da tarefa corrente.
- Comandos Python devem usar o runtime fixado. Nesta máquina:

```powershell
$benchmarkUv = 'C:\Users\Keller_\.cache\portable-benchmark-core\uv-0.12.3\bin\uv.exe'
& $benchmarkUv run --frozen --group dev python --version
```

Expected: Python `3.12.13`.

---

## Task 1: Unificar a identidade de equivalência e ampliar o schema do item

**Files:**

- Modify: `src/suggestion_engine/issue_deduplicator.py`
- Modify: `src/experiment/evaluator.py`
- Create: `src/experiment/ground_truth_policy.py`
- Modify: `tests/test_issue_deduplicator.py`
- Create: `tests/experiment/test_ground_truth_policy.py`
- Modify: `tests/evaluation/test_evaluator_v2.py`

**Interfaces:**

```python
# src/suggestion_engine/issue_deduplicator.py
def structural_fingerprint_payload(issue: Issue) -> dict[str, object]: ...
def equivalence_id_for_issue(issue: Issue) -> str: ...

# src/experiment/ground_truth_policy.py
POLICY_VERSION = "full-coverage-equivalent-v1"
Confidence = Literal["high", "medium", "low"]
SourceKind = Literal[
    "ifc_literal", "ifc_alias", "existing_gt", "equivalent_donor",
    "calculation", "normative_rule", "typology", "probable",
]

class GroundTruthDecision(BaseModel):
    expected_value: Any
    accepted_alternatives: list[Any] = Field(default_factory=list)
    confidence: Confidence
    source_kind: SourceKind
    notes: str
    legacy_reference: bool = False

# novos campos compatíveis no GroundTruthItem
equivalence_id: str | None = None
confidence: Confidence | None = None
source_kind: SourceKind | None = None
legacy_reference: bool = False
```

- [ ] **Step 1: Congelar em testes o comportamento atual do agrupamento**

Acrescentar testes que criem issues seguras e inseguras e capturem a partição atual de `IssueDeduplicator.group_issues`. Provar:

- issues seguras com os mesmos discriminadores recebem o mesmo ID;
- material, espessura, uso, exterioridade, tipo e relação esperada alteram o ID;
- issue insegura recebe uma classe exclusiva, mesmo se os demais campos coincidirem;
- a ordem das chaves de `context` não altera o ID;
- IDs seguem `^eq-[0-9a-f]{16}$`;
- dois payloads diferentes não podem ser registrados com o mesmo ID.

O teste de compatibilidade deve comparar os membros dos grupos, não o texto do hash antigo:

```python
before = _legacy_group_members(issues)
after = IssueDeduplicator().group_issues(issues)
assert sorted(map(sorted, before.values())) == sorted(map(sorted, after.values()))
```

- [ ] **Step 2: Escrever testes RED para o schema e a decisão**

Cobrir `GroundTruthDecision` com:

- valor nulo/sentinela rejeitado;
- `notes` vazia rejeitada;
- `low` sem prefixo `Hipótese congelada:` rejeitado;
- enums desconhecidos rejeitados;
- alternativa igual ao valor principal ou duplicada após normalização rejeitada;
- construção legada `GroundTruth(corrections={...})` ainda aceita campos novos ausentes;
- YAML canônico com os quatro campos novos carrega sem perder tipos.

Run:

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/test_issue_deduplicator.py tests/experiment/test_ground_truth_policy.py tests/evaluation/test_evaluator_v2.py -q
```

Expected: FAIL porque as novas funções, o modelo e os campos ainda não existem.

- [ ] **Step 3: Extrair o payload estrutural sem mudar a semântica do reuso**

Refatorar o corpo atual de `compute_structural_signature` para produzir uma lista ordenada de componentes e expô-la em um payload canônico:

```python
def structural_fingerprint_payload(issue: Issue) -> dict[str, object]:
    safe = is_safe_to_reuse(issue)
    return {
        "schema": "reuse-equivalent-v1",
        "safe_to_reuse": safe,
        "components": _structural_components(issue),
        "unique_issue_id": None if safe else issue.id,
    }

def equivalence_id_for_issue(issue: Issue) -> str:
    encoded = json.dumps(
        structural_fingerprint_payload(issue),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"eq-{hashlib.sha256(encoded).hexdigest()[:16]}"
```

`IssueDeduplicator.group_issues` deve indexar por `equivalence_id_for_issue(issue)`. Manter `compute_structural_signature` e `signature_for` como wrappers compatíveis, documentando que novos consumidores devem usar o ID prefixado.

- [ ] **Step 4: Implementar o contrato de política e os campos compatíveis**

Criar `GroundTruthDecision` com validação Pydantic estrita. Adicionar os novos campos opcionais ao modelo de runtime para manter leitura de fixtures/artefatos legados; a obrigatoriedade canônica ficará no validador da Task 3.

Incluir helper de colisão:

```python
def assert_equivalence_ids_unique(
    pairs: Iterable[tuple[str, Mapping[str, object]]],
) -> None:
    """Falha quando o mesmo eq-id representa payloads canônicos diferentes."""
```

- [ ] **Step 5: Rodar regressão focada e estática**

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/test_issue_deduplicator.py tests/experiment/test_ground_truth_policy.py tests/evaluation/test_evaluator_v2.py -q
& $benchmarkUv run --frozen --group dev ruff check src/suggestion_engine/issue_deduplicator.py src/experiment/evaluator.py src/experiment/ground_truth_policy.py tests/test_issue_deduplicator.py tests/experiment/test_ground_truth_policy.py tests/evaluation/test_evaluator_v2.py
& $benchmarkUv run --frozen --group dev mypy src/suggestion_engine/issue_deduplicator.py src/experiment/ground_truth_policy.py --follow-imports=skip
```

Expected: PASS.

- [ ] **Step 6: Commit atômico**

```powershell
git add -- src/suggestion_engine/issue_deduplicator.py src/experiment/evaluator.py src/experiment/ground_truth_policy.py tests/test_issue_deduplicator.py tests/experiment/test_ground_truth_policy.py tests/evaluation/test_evaluator_v2.py
git commit -m "feat(gt): unificar identidade de equivalencia"
```

---

## Task 2: Implementar o resolvedor técnico determinístico de cobertura integral

**Files:**

- Create: `src/experiment/ground_truth_value_policy.py`
- Create: `tests/experiment/test_ground_truth_value_policy.py`
- Modify: `src/experiment/ground_truth_audit.py`
- Modify: `tests/experiment/test_ground_truth_audit.py`

**Interfaces:**

```python
class LayerEvidence(BaseModel):
    material: str
    thickness_m: float | None = None

class ElementEvidence(BaseModel):
    element_class: str
    element_type_name: str = ""
    element_long_name: str = ""
    material_name: str = ""
    layers: tuple[LayerEvidence, ...] = ()
    total_thickness_m: float | None = None
    is_external: bool | None = None
    load_bearing_alias: bool | None = None
    expected_relation: str | None = None

def resolve_ground_truth_decision(
    issue: Issue,
    evidence: ElementEvidence,
    *,
    prior_item: GroundTruthItem | None,
    equivalent_donor: GroundTruthItem | None,
    building_context: Mapping[str, str],
) -> GroundTruthDecision: ...
```

**Política congelada de fallback:**

```python
THERMAL_FALLBACK = {
    "IfcWall": 2.48,
    "IfcWallStandardCase": 2.48,
    "IfcSlab": 3.20,
    "IfcRoof": 2.00,
    "IfcDoor": 3.00,
    "IfcWindow": 5.70,
    "IfcCurtainWall": 5.70,
}
ACOUSTIC_FALLBACK_DB = {
    "IfcWall": 40,
    "IfcWallStandardCase": 40,
    "IfcSlab": 45,
    "IfcRoof": 40,
    "IfcDoor": 25,
    "IfcWindow": 30,
}
FIRE_FALLBACK = {"IfcDoor": "EI 60", "IfcWindow": "EI 60"}
FIRE_FALLBACK_DEFAULT = "REI 60"
SHGC_GENERIC_CLEAR_GLASS = 0.87
```

Os números de fallback são referências autorais congeladas para comparação, não limites normativos. A nota de cada decisão deve deixar isso explícito.

- [ ] **Step 1: Escrever a matriz RED de fontes e precedência**

Criar testes parametrizados que provem a ordem exata:

1. alias/literal IFC vence legado apenas quando a propriedade representa o mesmo conceito e o legado não é marcado como referência imutável;
2. item `legacy_reference` válido é copiado semanticamente e marcado `existing_gt/high`;
3. doador da mesma equivalência produz `equivalent_donor/high`;
4. cálculo completo produz `calculation/medium`;
5. regra/tipologia produz `normative_rule|typology/medium`;
6. fallback produz `probable/low` com hipótese explícita.

Para preservar os 1.666 rótulos aprovados, o ramo `prior_item` com `legacy_reference=True` deve ser avaliado antes de qualquer regra nova.

- [ ] **Step 2: Escrever testes RED por família**

Cobrir pelo menos:

- `LoadBearing`/`IsLoadBearing`: alias booleano, elementos estruturais, parede/laje sem indicação estrutural;
- `Category`: aliases de `LongName` e fallback `TECHNICAL_AREA` apenas para espaço sem pista;
- `system_unclassified`: vocabulário por classe/material e fallbacks `Alvenaria de vedação em bloco cerâmico` para parede e `Laje maciça de concreto armado` para laje;
- `relation_broken`: `expected_relation`, `IfcRelFillsElement` para porta/janela e `IfcRelSpaceBoundary` para espaço;
- `ThermalTransmittance`: cálculo e cada fallback de classe;
- `FireRating`: `EI 60` para porta/janela, `REI 60` para os demais elementos atuais;
- `AcousticRating`: string exata `Rw <inteiro> dB` por classe;
- `SolarHeatGainCoefficient`: `0.87` e limite `[0, 1]`;
- `HasNonSkidSurface`: `true` para escada/patamar/área molhada/externa com pista e `false` para ambiente seco sem pista.

Casos desconhecidos fora das famílias presentes devem falhar com `UnsupportedGroundTruthFamily`; não inventar um sentinela.

Run:

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/experiment/test_ground_truth_value_policy.py tests/experiment/test_ground_truth_audit.py -q
```

Expected: FAIL por módulo/API ausente.

- [ ] **Step 3: Implementar normalização de evidência e regras literais**

Implementar alias booleano sem coerção insegura de strings. Normalizar texto apenas para decisão, mantendo o valor canônico final. `Category` e sistemas devem aceitar somente os vocabulários exportados por `ground_truth_validation.py`.

Para relações:

```python
if evidence.expected_relation:
    return _decision(evidence.expected_relation, "high", "ifc_literal", ...)
if issue.element_class in {"IfcDoor", "IfcWindow"}:
    return _decision("IfcRelFillsElement", "medium", "typology", ...)
if issue.element_class == "IfcSpace":
    return _decision("IfcRelSpaceBoundary", "medium", "typology", ...)
raise UnsupportedGroundTruthFamily(...)
```

- [ ] **Step 4: Implementar cálculo térmico reprodutível**

Usar apenas camadas com espessura positiva e condutividade catalogada. Catálogo inicial congelado em W/(m·K): concreto `1.75`, argamassa/revestimento cimentício `1.15`, cerâmica `0.90`, gesso `0.35`, EPS `0.04`, madeira `0.15`, vidro `1.00`. Resistências superficiais:

- parede/fluxo horizontal: `Rsi=0.13`, `Rse=0.04`;
- cobertura/fluxo ascendente: `Rsi=0.10`, `Rse=0.04`;
- piso/fluxo descendente: `Rsi=0.17`, `Rse=0.04`.

Fórmula:

```python
r_total = rsi + sum(layer.thickness_m / lambda_value for layer in layers) + rse
u_value = round(1.0 / r_total, 2)
```

Se alguma camada não tiver espessura/λ confiável, não calcular parcialmente: aplicar o fallback por classe como `typology/medium` quando houver material/tipo forte, ou `probable/low` quando só houver a classe IFC.

- [ ] **Step 5: Substituir a abstração de abstenção no auditor**

Manter `AuditDecision` temporariamente como adaptador de compatibilidade, mas retirar `skip_reason` do caminho canônico novo. Adicionar:

```python
def audit_or_resolve_item(...) -> GroundTruthDecision:
    """Preserva item congelado válido ou delega ao resolvedor integral."""
```

Testes antigos de abstinência histórica podem permanecer para leitura do snapshot anterior, mas nenhum builder novo chamará `_skip` para uma issue dos dois datasets congelados.

- [ ] **Step 6: Rodar testes, lint e tipos**

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/experiment/test_ground_truth_value_policy.py tests/experiment/test_ground_truth_audit.py -q
& $benchmarkUv run --frozen --group dev ruff check src/experiment/ground_truth_value_policy.py src/experiment/ground_truth_audit.py tests/experiment/test_ground_truth_value_policy.py tests/experiment/test_ground_truth_audit.py
& $benchmarkUv run --frozen --group dev mypy src/experiment/ground_truth_value_policy.py src/experiment/ground_truth_audit.py --follow-imports=skip
```

Expected: PASS.

- [ ] **Step 7: Commit atômico**

```powershell
git add -- src/experiment/ground_truth_value_policy.py src/experiment/ground_truth_audit.py tests/experiment/test_ground_truth_value_policy.py tests/experiment/test_ground_truth_audit.py
git commit -m "feat(gt): resolver todos os valores tecnicos"
```

---

## Task 3: Tornar builder e validador integrais, com lock dos rótulos legados

**Files:**

- Create: `data/evaluation/legacy-reference.lock.json`
- Modify: `scripts/build_ground_truths.py`
- Modify: `src/experiment/ground_truth_validation.py`
- Modify: `src/experiment/gt_extractor.py`
- Modify: `tests/experiment/test_build_ground_truths.py`
- Modify: `tests/experiment/test_ground_truth_validation.py`
- Modify: `tests/experiment/test_ground_truth_datasets.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class LegacyReferenceLock:
    dataset: str
    count: int
    semantic_sha256: str

def canonical_legacy_items_sha256(items: Sequence[GroundTruthItem]) -> str: ...

def build_full_coverage_dataset(
    spec: DatasetSpec,
    *,
    source_ground_truth_path: Path | None = None,
) -> tuple[GroundTruth, list[Issue]]: ...
```

- [ ] **Step 1: Congelar o subconjunto legado antes de alterar os YAMLs**

Criar um teste/utilitário que leia os YAMLs atuais e calcule SHA-256 sobre JSON canônico dos campos:

```python
{
    "element_guid": item.element_guid,
    "issue_type": item.issue_type,
    "check_property": item.check_property,
    "issue_id": item.issue_id,
    "expected_value": item.expected_value,
    "accepted_alternatives": item.accepted_alternatives,
}
```

Ordenar pela chave natural e serializar com `sort_keys=True`, separadores compactos e UTF-8. Gravar `legacy-reference.lock.json` com schema `1`, contagens `1654`/`12` e os dois hashes calculados. O lock não armazena respostas nem duplica o GT; ele impede drift sem depender do Git no computador novo.

- [ ] **Step 2: Escrever testes RED do contrato integral**

Adicionar testes para:

- `skipped` não vazio é rejeitado no protocolo novo;
- qualquer item sem os quatro metadados novos é rejeitado;
- `equivalence_id`, `confidence` e `source_kind` inválidos são rejeitados;
- classe equivalente com `expected_value`, alternativas, fonte ou confiança divergentes é rejeitada;
- `low` sem hipótese é rejeitado;
- `legacy_reference` seleciona exatamente os itens cujo hash/count bate no lock;
- prédio diferente de 4.720 ou casa diferente de 263 é rejeitado;
- metadata sem `policy_version`, `confidence_counts`, `equivalence_class_count` é rejeitada;
- dois builds em memória produzem bytes idênticos;
- falha de validação não altera o YAML existente.

Run:

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/experiment/test_build_ground_truths.py tests/experiment/test_ground_truth_validation.py tests/experiment/test_ground_truth_datasets.py -q
```

Expected: FAIL nos contratos novos.

- [ ] **Step 3: Generalizar a leitura da fonte congelada para os dois datasets**

Substituir `_read_predio_source` por `_read_frozen_source`. O primeiro build integral usa os YAMLs antigos pinados. Rebuilds posteriores usam o YAML canônico integral pinado. Para cada issue:

1. recuperar item anterior pela chave natural;
2. recuperar skip anterior somente como indicação de que uma nova decisão é necessária;
3. extrair `ElementEvidence` do IFC;
4. calcular `equivalence_id` pela API da Task 1;
5. preservar item legado ou resolver uma decisão nova;
6. propagar a decisão por classe somente depois de provar coerência de evidência.

O mapa de doadores deve ser construído exclusivamente de itens válidos da mesma classe:

```python
donor_by_equivalence: dict[str, GroundTruthItem] = {}
for item in legacy_items:
    eq_id = item_equivalence[item.natural_key]
    previous = donor_by_equivalence.setdefault(eq_id, item)
    assert_semantically_equal(previous, item)
```

Se itens legados de uma classe divergirem, abortar e melhorar os discriminadores da Task 1 com evidência IFC; não usar o valor legado na assinatura.

Ao ler o protocolo antigo `evidence-audited-v1`, marcar todos os itens da seção
`items` como legados antes da resolução. Ao ler o novo protocolo, preservar o
booleano já congelado. A decisão técnica é de classe: valor, alternativas,
`confidence`, `source_kind` e nota de evidência da classe são copiados para todos
os membros; apenas `legacy_reference`, chave natural e `issue_id` permanecem por
ocorrência.

- [ ] **Step 4: Produzir somente `items` e `skipped: []`**

Trocar a partição item/skip por cobertura exata:

```python
def _require_exact_coverage(ground_truth: GroundTruth, issues: Sequence[Issue]) -> None:
    diagnostic_keys = {_issue_key(issue) for issue in issues}
    item_keys = {item.natural_key for item in ground_truth.items}
    if len(ground_truth.items) != len(issues) or item_keys != diagnostic_keys:
        raise ValueError("items nao cobrem exatamente todas as issues")
```

`canonical_ground_truth_bytes` sempre emite `"skipped": []`. Atualizar `GTExtractionResult` apenas se necessário para manter API legada; o caminho novo deve expor `GroundTruth` integral e não aceitar `SkippedIssue`.

- [ ] **Step 5: Ampliar metadata canônico**

Emitir, em ordem estável:

```yaml
protocol: full-coverage-equivalent-v1
policy_version: full-coverage-equivalent-v1
total_diagnostic_issues: 4720
total_items: 4720
total_skipped: 0
equivalence_class_count: <inteiro>
confidence_counts:
  high: <inteiro>
  medium: <inteiro>
  low: <inteiro>
legacy_reference_count: 1654
```

Na casa, `total_diagnostic_issues/total_items=263` e `legacy_reference_count=12`. `verified_at` passa a `2026-08-09`.

- [ ] **Step 6: Implementar validação fail-closed**

No protocolo integral, `validate_ground_truth_against_issues` deve validar:

- cobertura exata e contagens fixas por dataset;
- valores por propriedade com o normalizador real;
- conjunto de classes equivalentes e ausência de colisões;
- coerência de valor/alternativas/confiança/fonte dentro da classe;
- hash semântico do subconjunto legado;
- somatório de `confidence_counts` igual a `total_items`;
- `legacy_reference_count` e `equivalence_class_count` reais;
- IDs e chaves únicos;
- IFC/IDS pinados.

- [ ] **Step 7: Rodar regressões focadas**

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/experiment/test_build_ground_truths.py tests/experiment/test_ground_truth_validation.py tests/experiment/test_ground_truth_datasets.py tests/experiment/test_ground_truth_audit.py tests/experiment/test_ground_truth_value_policy.py -q
& $benchmarkUv run --frozen --group dev ruff check scripts/build_ground_truths.py src/experiment/ground_truth_validation.py src/experiment/gt_extractor.py tests/experiment/test_build_ground_truths.py tests/experiment/test_ground_truth_validation.py tests/experiment/test_ground_truth_datasets.py
& $benchmarkUv run --frozen --group dev mypy scripts/build_ground_truths.py src/experiment/ground_truth_validation.py --follow-imports=skip
```

Expected: PASS com fixtures sintéticas; os YAMLs reais ainda não foram sobrescritos.

- [ ] **Step 8: Commit atômico**

```powershell
git add -- data/evaluation/legacy-reference.lock.json scripts/build_ground_truths.py src/experiment/ground_truth_validation.py src/experiment/gt_extractor.py tests/experiment/test_build_ground_truths.py tests/experiment/test_ground_truth_validation.py tests/experiment/test_ground_truth_datasets.py
git commit -m "feat(gt): exigir cobertura integral deterministica"
```

---

## Task 4: Gerar, auditar e congelar os 4.983 rótulos reais

**Files:**

- Modify: `data/evaluation/predio/ground_truth.yaml`
- Modify: `data/evaluation/casa/ground_truth.yaml`
- Modify: `data/evaluation/predio/README.md`
- Modify: `data/evaluation/casa/README.md`
- Modify: `scripts/build_ground_truths.py`
- Modify: `references/normative/public/sources.yaml` only if a new normative source is actually used
- Modify: `references/normative/public/README.md` only if `sources.yaml` changes
- Create: `tests/experiment/test_full_coverage_ground_truth.py`

- [ ] **Step 1: Rodar a geração real em modo de candidato**

Adicionar ao script `--output-dir <dir>` para materializar os dois candidatos fora dos caminhos canônicos. Executar:

```powershell
$candidateRoot = Join-Path $env:TEMP 'ifcqc-full-coverage-candidate'
& $benchmarkUv run --frozen --group dev python scripts/build_ground_truths.py --dataset all --output-dir $candidateRoot
```

Expected: dois YAMLs, sem modificar `data/evaluation/**/ground_truth.yaml`.

- [ ] **Step 2: Auditar mecanicamente cada candidato**

O novo teste real deve diagnosticar os IFCs e provar:

```python
assert len(predio.items) == 4720
assert len(casa.items) == 263
assert predio_document["skipped"] == []
assert casa_document["skipped"] == []
assert sum(predio.metadata["confidence_counts"].values()) == 4720
assert sum(casa.metadata["confidence_counts"].values()) == 263
assert sum(item.legacy_reference for item in predio.items) == 1654
assert sum(item.legacy_reference for item in casa.items) == 12
```

Também agrupar por família e exigir domínio:

- booleanos reais para `LoadBearing`, `IsLoadBearing`, `HasNonSkidSurface`;
- `0 < U <= 8` para `ThermalTransmittance`;
- `0 <= SHGC <= 1`;
- regex `^(R|E|I|RE|EI|REI|P-CF) [0-9]{2,3}$` para fogo;
- regex `^Rw [0-9]{2} dB$` para acústica;
- vocabulários canônicos para Category/sistemas;
- nomes `IfcRel*` conhecidos para relações.

- [ ] **Step 3: Provar preservação e coerência de equivalência**

Calcular o hash semântico dos itens `legacy_reference: true` e comparar com `legacy-reference.lock.json`. Para cada `equivalence_id`, comparar o JSON canônico de:

```python
(expected_value, accepted_alternatives, confidence, source_kind)
```

Expected: exatamente um valor por classe. Separadamente, provar que todas as notas `low` começam por `Hipótese congelada:`.

- [ ] **Step 4: Revisar a distribuição científica antes do freeze**

Imprimir e salvar somente no log do teste as tabelas por dataset/família/confiança/fonte, sem criar um terceiro artefato de runtime. Confirmar que:

- todos os 685 aliases `LoadBearing=false` encontrados no levantamento continuam `false/high/ifc_alias`;
- SHGC genérico usa `0.87` com nota tipológica/provável;
- nenhum valor provável cita norma como se fosse requisito;
- fontes `normative_rule` referenciam um `source_id` presente em `references/normative/public/sources.yaml`;
- o catálogo não contém PDF de norma licenciada.

Se nenhuma decisão usar regra normativa nova, não alterar `sources.yaml`.

- [ ] **Step 5: Substituir atomicamente os YAMLs e calcular pins**

Após os testes do candidato passarem, executar a escrita canônica:

```powershell
& $benchmarkUv run --frozen --group dev python scripts/build_ground_truths.py --dataset all
Get-FileHash data/evaluation/predio/ground_truth.yaml -Algorithm SHA256
Get-FileHash data/evaluation/casa/ground_truth.yaml -Algorithm SHA256
```

Inserir os dois SHA-256 lowercase obtidos em `EXPECTED_GROUND_TRUTH_SHA256`. Não antecipar nem preencher hashes fictícios no plano.

- [ ] **Step 6: Provar determinismo e ausência de drift**

```powershell
& $benchmarkUv run --frozen --group dev python scripts/build_ground_truths.py --dataset all --check
& $benchmarkUv run --frozen --group dev pytest tests/experiment/test_full_coverage_ground_truth.py tests/experiment/test_ground_truth_datasets.py tests/experiment/test_build_ground_truths.py -q
```

Expected: `predio 4720 sem drift`, `casa 263 sem drift`, testes PASS.

- [ ] **Step 7: Atualizar os READMEs dos datasets**

Documentar protocolo, hashes, contagens, significado de confiança, regra de valores prováveis, preservação de 1.666 legados e recomendação de `accuracy_equivalence` para o artigo. Deixar explícito que valores `low` são referências autorais experimentais.

- [ ] **Step 8: Rodar lint, diff e commit atômico**

```powershell
& $benchmarkUv run --frozen --group dev ruff check scripts/build_ground_truths.py tests/experiment/test_full_coverage_ground_truth.py
git diff --check -- data/evaluation scripts/build_ground_truths.py tests/experiment/test_full_coverage_ground_truth.py references/normative/public
git add -- data/evaluation/predio/ground_truth.yaml data/evaluation/casa/ground_truth.yaml data/evaluation/predio/README.md data/evaluation/casa/README.md scripts/build_ground_truths.py tests/experiment/test_full_coverage_ground_truth.py
git add -- references/normative/public/sources.yaml references/normative/public/README.md  # somente se alterados
git commit -m "data(gt): congelar cobertura integral dos dois ifcs"
```

---

## Task 5: Acrescentar métricas por equivalência, confiança e legado

**Files:**

- Modify: `src/experiment/evaluator.py`
- Modify: `src/experiment/report.py`
- Modify: `tests/evaluation/test_evaluator_v2.py`
- Modify: `tests/evaluation/test_evaluation_framework.py`
- Modify: `tests/experiment/test_report.py`

**Interfaces:**

```python
class AccuracySlice(BaseModel):
    top1: float = 0.0
    top3: float = 0.0
    total: int = 0
    top1_hits: int = 0
    top3_hits: int = 0

class EvaluationMetrics(BaseModel):
    # campos atuais permanecem
    accuracy_all: AccuracySlice = Field(default_factory=AccuracySlice)
    accuracy_equivalence: AccuracySlice = Field(default_factory=AccuracySlice)
    accuracy_by_confidence: dict[str, AccuracySlice] = Field(default_factory=dict)
    accuracy_legacy: AccuracySlice = Field(default_factory=AccuracySlice)
```

Definições:

- `accuracy_all`: micro sobre ocorrências; deve reproduzir `accuracy_top1/accuracy_top3`.
- `accuracy_equivalence`: para cada classe, calcular hits/ocorrências da classe; o `top1/top3` final é a média simples das acurácias das classes. `total` é número de classes.
- `accuracy_by_confidence`: micro separado em `high`, `medium`, `low`.
- `accuracy_legacy`: micro somente onde `legacy_reference=true`.

- [ ] **Step 1: Escrever testes RED com distribuição desbalanceada**

Criar um caso com uma equivalência de 100 ocorrências e outra de 1. A primeira acerta tudo e a segunda erra. Provar:

```python
assert metrics.accuracy_all.top1 == pytest.approx(100 / 101)
assert metrics.accuracy_equivalence.top1 == pytest.approx(0.5)
assert metrics.accuracy_equivalence.total == 2
```

Adicionar casos de acerto parcial dentro de uma classe, top-3, ausência de sugestão, buckets vazios, confiança e legado. Um oracle montado diretamente dos dois YAMLs deve obter `1.0` em todas as visões não vazias; uma mutação de valor deve reduzir as métricas correspondentes.

Run:

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/evaluation/test_evaluator_v2.py tests/evaluation/test_evaluation_framework.py tests/experiment/test_report.py -q
```

Expected: FAIL por campos/algoritmos ausentes.

- [ ] **Step 2: Implementar uma única coleta de observações**

Evitar quatro loops com regras diferentes. Criar registro interno:

```python
@dataclass(frozen=True)
class _AccuracyObservation:
    equivalence_id: str
    confidence: str
    legacy_reference: bool
    top1_hit: bool
    top3_hit: bool
    has_suggestion: bool
```

`_compute_accuracy` produz as observações uma vez, preserva precision/recall/f1 atuais e deriva os quatro cortes. Arredondar somente ao materializar `EvaluationMetrics`, nunca antes das médias.

- [ ] **Step 3: Atualizar exportação e relatório**

Manter colunas antigas e acrescentar:

- `accuracy_equivalence_top1`, `accuracy_equivalence_top3`;
- `accuracy_high_top1`, `accuracy_medium_top1`, `accuracy_low_top1`;
- `accuracy_legacy_top1`;
- contagens de ocorrência e equivalência.

O ranking padrão de `report.py` deve usar `accuracy_equivalence_top1_mean`; se um resultado legado não tiver o campo, cair explicitamente para `accuracy_top1_mean` e marcar `metric_basis="legacy_occurrence"`.

- [ ] **Step 4: Rodar testes e estática**

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/evaluation/test_evaluator_v2.py tests/evaluation/test_evaluation_framework.py tests/experiment/test_report.py -q
& $benchmarkUv run --frozen --group dev ruff check src/experiment/evaluator.py src/experiment/report.py tests/evaluation/test_evaluator_v2.py tests/evaluation/test_evaluation_framework.py tests/experiment/test_report.py
& $benchmarkUv run --frozen --group dev mypy src/experiment/evaluator.py src/experiment/report.py --follow-imports=skip
```

Expected: PASS.

- [ ] **Step 5: Commit atômico**

```powershell
git add -- src/experiment/evaluator.py src/experiment/report.py tests/evaluation/test_evaluator_v2.py tests/evaluation/test_evaluation_framework.py tests/experiment/test_report.py
git commit -m "feat(eval): medir acuracia por equivalencia e confianca"
```

---

## Task 6: Propagar política e contagens pela identidade, resultados e retomada

**Files:**

- Modify: `src/experiment/execution_identity.py`
- Modify: `src/experiment/metrics.py`
- Modify: `src/experiment/runner.py`
- Modify: `scripts/run_benchmark.py`
- Modify: `scripts/windows_benchmark.py`
- Modify: `tests/experiment/test_execution_identity.py`
- Modify: `tests/experiment/test_runner_harness.py`
- Modify: `tests/test_run_benchmark.py`
- Modify: `tests/windows/test_windows_benchmark.py`
- Modify: `tests/experiment/test_ground_truth_runner_smoke.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class DatasetIdentity:
    key: str
    ifc_sha256: str
    ground_truth_sha256: str
    ids_sha256: str
    building_context: Sequence[tuple[str, str]]
    ground_truth_policy_version: str
    ground_truth_items: int
    equivalence_classes: int
    confidence_counts: Sequence[tuple[str, int]]

class RunMetadata(BaseModel):
    ground_truth_policy_version: str = ""
    ground_truth_items: int = 0
    ground_truth_equivalence_classes: int = 0
    ground_truth_confidence_counts: dict[str, int] = Field(default_factory=dict)
```

- [ ] **Step 1: Escrever testes RED de identidade e resume**

Provar que mudar qualquer um destes campos muda `canonical_identity_sha256` e invalida `_stage_done`:

- hash do GT;
- versão da política;
- contagem de itens;
- contagem de equivalências;
- distribuição de confiança.

Rejeitar identidade com datasets fora de `predio,casa`, buckets fora de `high,medium,low`, somatório divergente ou política diferente de `full-coverage-equivalent-v1` no modo oficial.

Run:

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/experiment/test_execution_identity.py tests/experiment/test_runner_harness.py tests/test_run_benchmark.py tests/windows/test_windows_benchmark.py -q
```

Expected: FAIL por schema/forwarding ausente.

- [ ] **Step 2: Carregar metadata do YAML ao construir a identidade**

Em `windows_benchmark.py`, após validar o SHA do GT, carregar apenas `metadata` e exigir chaves/tipos exatos. Converter mapas em tuplas ordenadas antes de construir `DatasetIdentity`:

```python
confidence_counts=tuple(
    (name, int(metadata["confidence_counts"][name]))
    for name in ("high", "medium", "low")
)
```

O runner local deve usar o mesmo helper para não haver duas políticas de parsing.

- [ ] **Step 3: Propagar para RunMetadata e StageExpectation**

Adicionar os campos explícitos ao `run_N.json`. `StageExpectation` deve projetá-los e `_stage_done` deve exigir igualdade literal além da identidade aninhada. O JSONL por issue não precisa duplicar os metadados do dataset.

- [ ] **Step 4: Atualizar o smoke integrado dos dois GTs**

O smoke deve usar os YAMLs reais, doubles apenas para Ollama/hardware, e provar:

- prédio e casa carregam todos os itens;
- `evaluation.accuracy_all` e `accuracy_equivalence` são serializadas;
- `RunMetadata` contém a política, contagens e SHA correto;
- um resultado antigo sem esses campos não é considerado retomável pela matriz oficial;
- os 20 pares agregados/JSONL continuam íntegros.

- [ ] **Step 5: Rodar regressões focadas e estática**

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/experiment/test_execution_identity.py tests/experiment/test_runner_harness.py tests/test_run_benchmark.py tests/windows/test_windows_benchmark.py tests/experiment/test_ground_truth_runner_smoke.py -q
& $benchmarkUv run --frozen --group dev ruff check src/experiment/execution_identity.py src/experiment/metrics.py src/experiment/runner.py scripts/run_benchmark.py scripts/windows_benchmark.py tests/experiment/test_execution_identity.py tests/experiment/test_runner_harness.py tests/test_run_benchmark.py tests/windows/test_windows_benchmark.py tests/experiment/test_ground_truth_runner_smoke.py
& $benchmarkUv run --frozen --group dev mypy src/experiment/execution_identity.py src/experiment/metrics.py scripts/run_benchmark.py scripts/windows_benchmark.py --follow-imports=skip
```

Expected: PASS.

- [ ] **Step 6: Commit atômico**

```powershell
git add -- src/experiment/execution_identity.py src/experiment/metrics.py src/experiment/runner.py scripts/run_benchmark.py scripts/windows_benchmark.py tests/experiment/test_execution_identity.py tests/experiment/test_runner_harness.py tests/test_run_benchmark.py tests/windows/test_windows_benchmark.py tests/experiment/test_ground_truth_runner_smoke.py
git commit -m "feat(run): identificar politica integral do ground truth"
```

---

## Task 7: Regressão integrada do núcleo antes da release

**Files:**

- Modify: `tests/experiment/test_portable_benchmark_core.py`
- Modify: `tests/experiment/test_full_coverage_ground_truth.py`
- Modify: `docs/metricas-avaliacao.md`

- [ ] **Step 1: Acrescentar aceite integrado RED/GREEN**

No smoke portátil, manter reais:

- loader dos GTs;
- identidade canônica;
- equivalência;
- avaliador;
- export agregado/JSONL;
- `_stage_done` e `_invalid_matrix_stages`;
- scanner/manifesto/ZIP de evidências.

Isolar somente rede/Ollama/hardware, como no smoke existente. Provar matriz `10 × 2 × 1`, 20 JSON + 20 JSONL, e o oracle dos dois GTs com 100% nas métricas integral/equivalência/legado e nos buckets não vazios.

- [ ] **Step 2: Rodar o conjunto focado completo**

```powershell
& $benchmarkUv lock --check
& $benchmarkUv run --frozen --group dev pytest tests/test_issue_deduplicator.py tests/evaluation tests/experiment/test_ground_truth_policy.py tests/experiment/test_ground_truth_value_policy.py tests/experiment/test_ground_truth_audit.py tests/experiment/test_ground_truth_validation.py tests/experiment/test_build_ground_truths.py tests/experiment/test_ground_truth_datasets.py tests/experiment/test_full_coverage_ground_truth.py tests/experiment/test_execution_identity.py tests/experiment/test_runner_harness.py tests/test_run_benchmark.py tests/experiment/test_ground_truth_runner_smoke.py tests/experiment/test_portable_benchmark_core.py tests/windows/test_windows_benchmark.py -q
```

Expected: PASS sem downloads, sem Ollama e sem benchmark real.

- [ ] **Step 3: Rodar estática escopada e suíte global com saída preservada**

```powershell
& $benchmarkUv run --frozen --group dev ruff check src scripts tests
& $benchmarkUv run --frozen --group dev mypy src/experiment scripts/build_ground_truths.py scripts/run_benchmark.py scripts/windows_benchmark.py --follow-imports=skip
& $benchmarkUv run --frozen --group dev pytest -ra --tb=short
```

Não declarar suíte global PASS se ela expirar. Registrar o último teste concluído e confiar no conjunto focado apenas para o aceite escopado.

- [ ] **Step 4: Documentar as métricas científicas**

Em `docs/metricas-avaliacao.md`, definir formalmente:

- micro por ocorrência;
- macro por equivalência;
- cortes por confiança;
- subconjunto legado;
- interpretação de valores `low`;
- impossibilidade de comparar diretamente resultados com hashes de GT diferentes.

- [ ] **Step 5: Commit atômico**

```powershell
git add -- tests/experiment/test_portable_benchmark_core.py tests/experiment/test_full_coverage_ground_truth.py docs/metricas-avaliacao.md
git commit -m "test: verificar ground truth integral ponta a ponta"
```

---

## Task 8: Reconstruir e validar a pasta Windows final

**Files:**

- Modify: `scripts/build_windows_release.py`
- Modify: `tests/windows/test_release_builder.py`
- Modify: `tests/windows/test_windows_release_smoke.py`
- Modify: `windows/LEIA-ME.txt`
- Generated, not committed: `dist/IFCQC-Benchmark-Windows-x64-<release-id>/`

- [ ] **Step 1: Escrever testes RED da árvore/payload**

Atualizar o contrato para exigir no `project.zip`:

- `src/experiment/ground_truth_policy.py`;
- `src/experiment/ground_truth_value_policy.py`;
- `data/evaluation/legacy-reference.lock.json`;
- os dois YAMLs integrais com os hashes finais;
- o builder/validador/avaliador atualizados.

O smoke deve abrir `project.zip`, re-hashear todos os membros do manifesto e validar que cada GT tem contagem integral e `skipped: []`.

Run:

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/windows/test_release_builder.py tests/windows/test_windows_release_smoke.py -q
```

Expected: FAIL até allowlist/manifesto/documentação serem atualizados.

- [ ] **Step 2: Atualizar builder e guia simples**

Alterar `RELEASE_DATE` para `2026-08-09`. Adicionar
`data/evaluation/legacy-reference.lock.json` a `PROJECT_PATTERNS` e
`REQUIRED_PROJECT_FILES`; os módulos Python novos já são cobertos por
`src/**/*.py`, mas os testes devem exigir seus nomes na árvore interna. Atualizar
`LEIA-ME.txt` para manter a experiência:

1. copiar a pasta inteira para o computador Windows 10/11 x64;
2. dar duplo clique em `EXECUTAR_BENCHMARK.cmd`;
3. aguardar instalação/download dos modelos e 20 etapas;
4. recuperar o ZIP final indicado na tela.

Explicar no guia que os dois IFCs e GTs já estão no payload, que nenhum Python/Git/Ollama prévio é obrigatório e que resultados carregam hardware, llmfit, métricas integrais e sugestões de modelos adicionais.

- [ ] **Step 3: Construir uma nova release real**

Usar uma pasta de saída nova; nunca sobrescrever a release anterior:

```powershell
& $benchmarkUv run --frozen --group dev python scripts/build_windows_release.py --root . --output dist
$release = Get-ChildItem dist -Directory |
    Where-Object Name -Like 'IFCQC-Benchmark-Windows-x64-*' |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
```

Registrar caminho, tamanho, `release_id`, SHA-256 do `release-manifest.json`, `project.zip` e dos dois GTs.

- [ ] **Step 4: Executar caminho feliz offline seguro**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$($release.FullName)\install.ps1" -PackageRoot $release.FullName -ValidateOnly
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$($release.FullName)\install.ps1" -PackageRoot $release.FullName -PlanOnly
```

Expected: ambos retornam `0`; `ValidateOnly` informa `PAYLOAD_OK`; `PlanOnly` mostra Python `3.12.13`, AppRoot por usuário e nenhum download/benchmark é iniciado.

- [ ] **Step 5: Rodar aceite da release e verificar ausência de drift**

```powershell
& $benchmarkUv run --frozen --group dev pytest tests/windows/test_release_builder.py tests/windows/test_windows_release_smoke.py tests/windows/test_install_contract.py tests/windows/test_windows_benchmark.py -q
& $benchmarkUv run --frozen --group dev ruff check scripts/build_windows_release.py tests/windows
git diff --check -- scripts/build_windows_release.py tests/windows windows/LEIA-ME.txt
```

Expected: PASS. O teste opt-in de download real/20 modelos permanece documentado como aceite de máquina limpa, não é executado automaticamente nesta estação.

- [ ] **Step 6: Commit atômico e entrega**

```powershell
git add -- scripts/build_windows_release.py tests/windows/test_release_builder.py tests/windows/test_windows_release_smoke.py windows/LEIA-ME.txt
git commit -m "build: publicar benchmark Windows com gt integral"
```

Entregar ao usuário:

- link para a nova pasta em `dist`;
- instrução de duplo clique;
- hashes principais;
- contagens `4720 + 263`;
- distribuição `high/medium/low`;
- lista curta de pendências não bloqueantes: aceite em Windows limpo, downloads reais de ~48 GB, benchmark completo de 20 etapas, sensores térmicos/energia e refinamento futuro dos rótulos `low` por especialista.

## Acceptance Gate Final

O trabalho só pode ser declarado concluído quando todas as condições forem verdadeiras:

- [ ] prédio possui 4.720 itens e zero skips;
- [ ] casa possui 263 itens e zero skips;
- [ ] todos os 4.983 valores passam o normalizador da propriedade;
- [ ] os 1.666 valores legados batem o lock semântico;
- [ ] todas as classes equivalentes são internamente coerentes;
- [ ] contagens por confiança fecham o total e todo `low` documenta hipótese;
- [ ] oracle obtém 100% e mutações propositais reduzem métricas;
- [ ] métricas integral, equivalência, confiança e legado aparecem no resultado;
- [ ] hashes/política fazem parte da identidade e impedem retomada antiga;
- [ ] `build_ground_truths.py --dataset all --check` retorna zero;
- [ ] conjunto focado do núcleo e testes Windows passam;
- [ ] release nova passa `ValidateOnly` e `PlanOnly`;
- [ ] `project.zip` contém os dois GTs integrais e o lock legado;
- [ ] guia final exige apenas copiar a pasta e executar `EXECUTAR_BENCHMARK.cmd`.
