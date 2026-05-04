# IFC Quality Copilot — Contexto Completo do Projeto

> Documento gerado para uso como contexto em pesquisas e sessões com LLMs.
> Descreve arquitetura, decisões de design, estado atual e pontos de extensão.

---

## 1. Visão Geral

**IFC Quality Copilot** é uma ferramenta de diagnóstico e correção assistida de modelos BIM/IFC voltada para engenheiros. O sistema combina análise determinística (heurísticas e regras) com geração de sugestões via LLM local (Ollama), e aplica correções **somente após aprovação explícita do usuário**.

### Problema que resolve

Modelos IFC exportados de ferramentas CAD frequentemente contêm:
- Espaços com nomes genéricos (`Room 1`, `Space`) sem classificação funcional
- Property Sets (Psets) obrigatórios ausentes ou vazios (ex: `ThermalTransmittance`)
- Relações estruturais quebradas (`IfcRelFillsElement` faltando em portas/janelas)
- Elementos sem classificação de sistema construtivo

Esses problemas bloqueiam simulações energéticas, verificação normativa (NBR 15575) e uso do modelo para orçamentação/manutenção.

### Princípio central

> **Nunca modificar o IFC sem `aprovado_pelo_usuario == True`.**

Toda escrita passa por uma validação explícita do engenheiro na UI ou via flag MCP.

---

## 2. Stack Tecnológica

| Componente | Tecnologia | Versão |
|---|---|---|
| Linguagem | Python | 3.11+ |
| Leitura/escrita IFC | IfcOpenShell | 0.8+ |
| Interface web | Streamlit | 1.38+ |
| LLM local | Ollama | qualquer |
| Modelo LLM padrão | `qwen3.5:9b` | — |
| Protocolo IA | MCP (Model Context Protocol) | SDK Python |
| Modelos de dados | Pydantic v2 | 2.0+ |
| Testes | Pytest | — |
| Logging | Loguru | — |
| Gráficos | Plotly | — |
| HTTP client | httpx | — |

---

## 3. Arquitetura Geral

### Fluxo principal (UI Streamlit)

```
Upload IFC
    │
    ▼
QualityPipeline
    │
    ├── IFCAnalyzer.analyze()           # diagnóstico rápido (síncrono)
    │       ├── diagnose_spaces()
    │       ├── diagnose_psets()
    │       ├── diagnose_relations()
    │       └── diagnose_systems()
    │
    ├── RuleEngine.process()            # heurísticas imediatas (síncrono)
    │       ├── resolved  → IssueStore (status: heuristic_ready)
    │       └── unresolved → IssueStore (status: queued)
    │
    ├── SuggestionWorker.start()        # thread daemon em background
    │       └── SuggestionGenerator.generate() via Ollama
    │               └── IssueStore.mark_ready()
    │
    └── UI Streamlit (polling a cada 2s via @st.fragment)
            └── render_issue_card() por issue pronta
                    ├── Aceitar  → pipeline.apply_correction()
                    ├── Editar   → pipeline.apply_correction()
                    └── Pular    → pipeline.skip_issue()
```

### Fluxo alternativo (MCP Server)

```
LLM externo (Claude, Cursor, etc.)
    │
    ▼
MCP Server (stdio)
    ├── Tools de leitura (diagnosticar_espacos, diagnosticar_psets, etc.)
    └── Tools de escrita (renomear_espaco, preencher_pset, etc.)
            └── IFCWriter + AuditLogger
```

---

## 4. Estrutura de Diretórios

```
ifc-quality-copilot/
├── src/
│   ├── models.py                    # todos os modelos Pydantic (fonte da verdade)
│   ├── pipeline.py                  # QualityPipeline — orquestração central
│   ├── config.py                    # Settings via pydantic-settings + .env
│   │
│   ├── ifc_analyzer/
│   │   ├── analyzer.py              # IFCAnalyzer — orquestrador dos diagnósticos
│   │   ├── space_diagnostics.py     # diagnose_spaces()
│   │   ├── pset_diagnostics.py      # diagnose_psets()
│   │   ├── relation_diagnostics.py  # diagnose_relations()
│   │   ├── system_diagnostics.py    # diagnose_systems()
│   │   └── extractors.py            # QuantityExtractor, ThermalExtractor, etc.
│   │
│   ├── translator/
│   │   ├── ids_parser.py            # XML IDS → list[IDSSpecification]
│   │   └── rule_generator.py        # IDSSpecification → OperationalRule + apply_rules()
│   │
│   ├── rule_engine/
│   │   ├── engine.py                # RuleEngine.process()
│   │   ├── packs.py                 # RulePackRegistry + RulePack por perfil
│   │   └── heuristics/
│   │       ├── space_heuristics.py
│   │       ├── wall_heuristics.py
│   │       ├── relation_heuristics.py
│   │       └── system_heuristics.py
│   │
│   ├── suggestion_engine/
│   │   ├── ollama_client.py         # OllamaClient — HTTP para /api/generate
│   │   ├── prompt_templates.py      # build_prompt() + parse_llm_response()
│   │   ├── prompt_router.py         # PromptRouter — seleciona template por perfil
│   │   ├── few_shot_examples.py     # exemplos few-shot por issue_type
│   │   ├── suggestion.py            # SuggestionGenerator
│   │   ├── issue_store.py           # IssueStore — fila thread-safe de sugestões
│   │   └── worker.py                # SuggestionWorker — thread daemon background
│   │
│   ├── writer/
│   │   └── ifc_writer.py            # IFCWriter — escrita segura no IFC
│   │
│   ├── audit/
│   │   └── logger.py                # AuditLogger — CSV + JSONL de correções
│   │
│   ├── mcp_server/
│   │   ├── server.py                # servidor MCP (stdio)
│   │   ├── registry.py              # ToolRegistry — filtragem por perfil
│   │   ├── tools_read.py            # tools de diagnóstico (sem escrita)
│   │   └── tools_write.py           # tools de escrita (requerem aprovação)
│   │
│   ├── profiles/
│   │   └── registry.py              # create_default_registry() com perfis pré-definidos
│   │
│   └── ui/
│       ├── app.py                   # entrypoint Streamlit
│       ├── styles.py                # CUSTOM_CSS global (inclui CSS dos cards)
│       └── components/
│           ├── issue_card.py        # render_issue_card()
│           ├── sidebar.py           # render_sidebar() — upload, config, export
│           ├── dashboard.py         # render_dashboard()
│           ├── filters.py           # render_filters()
│           └── progress_bar.py      # render_progress()
│
├── tests/
│   ├── conftest.py                  # fixtures compartilhadas + cache_clear autouse
│   ├── test_models.py
│   ├── test_analyzer.py
│   ├── test_rule_engine.py
│   ├── test_translator.py
│   ├── test_writer.py
│   ├── test_pipeline.py
│   └── test_suggestion.py
│
├── data/
│   ├── ids_templates/               # arquivos IDS de referência por perfil
│   ├── prompts/                     # templates de prompt versionados
│   └── heuristics/                  # tabelas NBR 15575
│
└── docs/
    ├── architecture.md
    ├── api.md
    └── mcp_tools.md
```

---

## 5. Modelos de Dados (`src/models.py`)

Todos os dados estruturados usam **Pydantic v2 BaseModel**. Enums simples usam `Literal` em vez de `Enum`.

### `Issue`
Representa um problema de qualidade detectado.

```python
class Issue(BaseModel):
    id: str                    # UUID[:16] — identificador interno
    element_guid: str          # GlobalId IFC (22 chars)
    element_class: str         # ex: "IfcWall", "IfcSpace"
    element_name: str | None
    issue_type: Literal[
        "space_unnamed",       # IfcSpace com nome genérico
        "pset_missing",        # propriedade obrigatória ausente
        "relation_broken",     # IfcRelFillsElement faltando
        "system_unclassified", # sem classificação de sistema construtivo
        "quantity_missing",    # BaseQuantities ausentes
        "classification_missing",
        "material_unmapped",
        "asset_unidentified",
        "thermal_incomplete",
    ]
    severity: Literal["high", "medium", "low"]
    description: str
    context: dict[str, Any]    # dados extras (pset_name, check_property, etc.)
    status: Literal["pending", "accepted", "edited", "rejected", "skipped"]
    created_at: datetime
    resolved_at: datetime | None
    resolution_value: Any
```

**Método central:** `issue.resolve(value, decision)` — atualiza status, timestamp e valor.

### `SuggestionSet`
Conjunto de sugestões para uma issue.

```python
class SuggestionSet(BaseModel):
    issue_id: str
    suggestions: list[Suggestion]    # 2-3 opções ordenadas por confiança
    allow_custom: bool = True        # permite valor digitado pelo usuário
    error: str | None                # mensagem se geração falhou
```

### `Suggestion`

```python
class Suggestion(BaseModel):
    label: str           # ex: "Lavabo Suíte" ou "2.48 W/(m².K)"
    value: Any           # valor a escrever no IFC
    justification: str   # raciocínio em português
    confidence: Literal["alta", "media", "baixa"]
    normative_ref: str | None    # ex: "NBR 15575-4 Tab. C.2"
    source: Literal["heuristic", "llm"]
```

### `OperationalRule`
Regra verificável gerada a partir de um IDS XML.

```python
class OperationalRule(BaseModel):
    id: str
    source_spec: str              # nome da IDSSpecification origem
    filter_entity: str            # ex: "IfcWall"
    check_pset: str               # ex: "Pset_WallCommon"
    check_property: str           # ex: "ThermalTransmittance"
    check_type: Literal["exists", "is_numeric", "is_boolean", "equals", "not_empty"]
    issue_type: str
    severity: Literal["high", "medium", "low"]
    suggestion_strategy: Literal["lookup_table", "llm_inference", ...]
    write_action: Literal["preencher_pset", "renomear_espaco", ...]
```

### `ReadinessProfile`
Define um perfil de uso downstream do IFC (ex: simulação energética, orçamento).

```python
class ReadinessProfile(BaseModel):
    id: str
    name: str
    ids_filename: str | None        # arquivo IDS associado em data/ids_templates/
    required_extractors: list[str]  # ["thermal", "quantities", "classifications"]
    issue_types: list[str]          # tipos de issue relevantes para este perfil
    blocking_severities: list[str]  # default: ["high"]
```

### `AuditEntry`
Registro imutável de cada correção aplicada.

```python
class AuditEntry(BaseModel):
    element_guid: str
    action: str           # "renomear_espaco", "preencher_pset", etc.
    field: str
    old_value: Any
    new_value: Any
    decision: Literal["accepted", "edited", "rejected"]
    confidence: str
    source: Literal["heuristic", "llm"]
    user: str
    timestamp: datetime
```

---

## 6. Módulo de Diagnóstico (`src/ifc_analyzer/`)

### `IFCAnalyzer`
Orquestra os quatro módulos de diagnóstico. Abre o IFC uma única vez via `ifcopenshell.open()` e passa o mesmo objeto `ifc_file` para todos os módulos.

**Método central:** `analyze()` → `DiagnosticReport`

Suporta enriquecimento de contexto por perfil: se um `ReadinessProfile` é passado, os extratores listados em `required_extractors` são chamados para cada issue, adicionando dados como `thermal_transmittance`, `total_thickness_m`, `has_insulation` ao `issue.context`.

### Extratores (lazy init)
- `ThermalExtractor` — `is_external`, `thermal_transmittance`, `estimated_u_range`, layers de material
- `QuantityExtractor` — `width`, `height`, `length`, `volume`, `net_floor_area`
- `ClassificationExtractor` — `has_classification`, `classification_code`
- `AssetExtractor` — `manufacturer`, `asset_type`, `model_reference`

### Diagnósticos

| Módulo | O que detecta |
|---|---|
| `space_diagnostics` | IfcSpace com LongName genérico ou vazio |
| `pset_diagnostics` | Psets obrigatórios ausentes (ThermalTransmittance, IsExternal, FireRating, etc.) |
| `relation_diagnostics` | IfcDoor/Window sem IfcRelFillsElement |
| `system_diagnostics` | IfcWall/IfcSlab sem IfcClassification de sistema construtivo |

Deduplicação por `(element_guid, issue_type)` antes de retornar.

---

## 7. Translator IDS (`src/translator/`)

Converte arquivos IDS XML (BuildingSMART) em regras operacionais.

```
IDS XML → parse_ids() → list[IDSSpecification]
                      → generate_rules() → list[OperationalRule]
                                         → apply_rules(ifc_file) → list[Issue]
```

- `ids_parser.py` — parseia XML via `lxml`, extrai `applicability` (filtros de entidade) e `requirements` (checks de Pset/propriedade)
- `rule_generator.py` — transforma specs em `OperationalRule` e as aplica ao modelo IFC, gerando issues adicionais com deduplicação por `(guid, issue_type, check_property)`

O pipeline integra IDS ao diagnóstico base e mescla issues sem duplicatas.

---

## 8. Rule Engine (`src/rule_engine/`)

### `RuleEngine.process(issues)`
Separa issues em dois grupos:
- **resolved**: resolvidas por heurística → `SuggestionSet` pronto de forma determinística
- **unresolved**: precisam do LLM

### Heurísticas disponíveis
- `space_heuristics` — classifica espaços por área + equipamentos sanitários adjacentes (banheiro, lavabo, cozinha, etc.)
- `wall_heuristics` — sugere `ThermalTransmittance` com base em espessura e material
- `relation_heuristics` — detecta portas próximas a aberturas existentes
- `system_heuristics` — classifica sistema por material da parede/laje

### RulePackRegistry
Permite registrar `RulePack` específicos por perfil. Se um perfil tem um pack, ele é aplicado primeiro. Se o pack não resolver, cai nas heurísticas genéricas.

### Configuração
Heurísticas podem ser habilitadas/desabilitadas via `Settings.enable_heuristics` (default: `False`).

---

## 9. Suggestion Engine (`src/suggestion_engine/`)

### Arquitetura de geração progressiva

O sistema usa uma arquitetura produtor-consumidor com thread-safety:

```
Main Thread              Worker Thread (daemon)
    │                          │
    ├─ IssueStore.add_issues() │
    │   status: "queued"       │
    │                          ├─ get_next_queued()
    │                          ├─ mark_processing()
    │                          ├─ SuggestionGenerator.generate()
    │                          │       └─ OllamaClient.generate()
    │                          └─ mark_ready() / mark_failed()
    │
    └─ UI polling a cada 2s
        └─ get_all_with_status()
```

### `IssueStore`
Estrutura thread-safe com `threading.Lock()`. Estados possíveis: `queued → processing → ready | heuristic_ready | failed`.

Métodos chave:
- `add_issues(issues, priority_issue_types)` — ordena por prioridade e severidade
- `get_issue(id)` — acesso seguro com lock
- `get_next_queued()` — respeita ordem de prioridade
- `get_all_with_status()` — leitura para a UI

### `SuggestionWorker`
Thread daemon que consome a fila do `IssueStore`. Usa `Event.wait(timeout=0.5)` no lugar de `time.sleep` para responder rapidamente ao sinal de parada.

### `OllamaClient`
- POST para `/api/generate` com retry (até 2x) em `TimeoutException`, `ConnectError`, `HTTPStatusError`
- Parâmetros: `temperature`, `num_ctx`, `num_predict`, `repeat_penalty`, `top_p` via `Settings`
- `think: bool` via `Settings.ollama_think` (compatível com modelos Qwen3 que suportam reasoning)
- `list_models()` retorna `[]` graciosamente se Ollama offline

### `SuggestionGenerator`
Gera `SuggestionSet` para uma issue. Suporta dois modos:
- **modo direto** (`build_prompt` + `parse_llm_response`) — sem perfil
- **modo roteado** (via `PromptRouter`) — seleciona template por perfil/tipo de issue

Valida e limpa sugestões: remove labels vazios, duplicatas, limita a 3.

### `PromptRouter`
Seleciona o template de prompt correto baseado em `(issue_type, profile)`. Os templates ficam em `prompt_templates.py` (6 variantes por papel: engenheiro estrutural, arquiteto, etc.).

### Parsing da resposta LLM
`parse_llm_response()` extrai JSON do texto gerado, com:
- remoção de tags `<think>...</think>` (Qwen3 reasoning)
- tentativa de reparo de JSON truncado
- fallback para array vazio se parsing falhar completamente

---

## 10. IFC Writer (`src/writer/ifc_writer.py`)

Executa correções no objeto `ifcopenshell.file` em memória. Nunca persiste em disco sozinho — isso é responsabilidade do pipeline via `writer.salvar(path)`.

### Operações disponíveis

| Método | O que faz |
|---|---|
| `renomear_espaco(guid, novo_long_name)` | Atualiza `LongName` de `IfcSpace` |
| `preencher_pset(guid, pset_name, properties)` | Cria/atualiza Property Set com mapeamento automático de tipos Python → IFC |
| `criar_relacao_fills(door_guid, wall_guid)` | Cria `IfcRelFillsElement` (com `IfcOpeningElement` se necessário) |
| `classificar_sistema(element_guid, sistema)` | Adiciona/atualiza `IfcClassificationReference` |
| `preencher_base_quantities(guid, qto_name, quantities)` | Cria/atualiza `IfcElementQuantity` |
| `mapear_classificacao(guid, sistema, codigo, descricao)` | Associa código orçamentário (SINAPI, Omniclass, etc.) |
| `associar_zona_termica(space_guid, zone_name, zone_type)` | Vincula `IfcSpace` a `IfcZone` |
| `salvar(output_path)` | Persiste o IFC em disco |

Todos os métodos retornam `(sucesso: bool, valor_anterior: Any)` para rastreabilidade.

---

## 11. Pipeline Central (`src/pipeline.py`)

### `QualityPipeline`
Objeto principal que une todos os módulos. Criado uma vez por sessão Streamlit.

```python
pipeline = QualityPipeline(ifc_path, building_context, ids_path, profile)
report = pipeline.diagnose_and_start_suggestions()
# worker já está rodando em background
# UI faz polling via pipeline.get_available_issues()

# Quando usuário clica Aplicar:
pipeline.apply_correction(issue_id, value, decision, user="engineer")

# Exportar:
pipeline.export(output_dir)
```

### Métodos chave

| Método | Descrição |
|---|---|
| `diagnose_and_start_suggestions()` | Diagnóstico + heurísticas + inicia worker. Retorna rápido. |
| `get_available_issues()` | Lista de `(issue, suggestion_set, status)` para a UI |
| `get_suggestions_progress()` | Dict com contagens por status (para barra de progresso) |
| `apply_correction(issue_id, value, decision, user)` | Escreve no IFC + registra na auditoria |
| `skip_issue(issue_id, user)` | Marca como pulada sem escrever |
| `compute_readiness()` | Calcula `ReadinessScore` para o perfil ativo |
| `export(output_dir)` | IFC corrigido + CSV + JSONL + métricas |

### Integração IDS
Se `ids_path` é fornecido, `_integrate_ids()` parseia o arquivo, gera regras e mescla issues adicionais ao relatório com deduplicação por `(guid, issue_type, check_property)`.

---

## 12. MCP Server (`src/mcp_server/`)

Servidor MCP via stdio, compatível com qualquer cliente MCP (Claude Desktop, Cursor, etc.).

### Session State
```python
_session = {
    "analyzer": IFCAnalyzer | None,
    "writer": IFCWriter | None,
    "audit_logger": AuditLogger,
    "profile_id": str | None,
    "tool_registry": ToolRegistry | None,
}
```

### Tools de Leitura (não requerem aprovação)
- `carregar_modelo` — abre IFC e inicializa session
- `resumo_modelo` — estatísticas do modelo carregado
- `diagnosticar_espacos/psets/relacoes/sistemas` — roda diagnóstico específico
- `verificar_readiness` — calcula score para perfil
- `listar_tools_disponiveis` — lista tools filtradas pelo perfil ativo

### Tools de Escrita (requerem `aprovado_pelo_usuario: true`)
- `renomear_espaco`, `preencher_pset`, `criar_relacao_fills`
- `classificar_sistema`, `preencher_base_quantities`
- `mapear_classificacao`, `associar_zona_termica`
- `registrar_log` — adiciona entrada manual no audit trail

### `ToolRegistry`
Filtra tools disponíveis por perfil ativo. Se perfil define `issue_types`, só expõe tools relevantes àquele perfil.

---

## 13. Interface Streamlit (`src/ui/`)

### Modo Progressivo vs. Legado

**Modo progressivo** (default quando `pipeline.issue_store is not None`):
- Usa `@st.fragment(run_every="2s")` para polling automático
- Exibe cards de placeholder (processing/queued) enquanto LLM processa
- Cards completos aparecem à medida que sugestões ficam prontas

**Modo legado** (quando `issues_suggestions` foi gerado de forma síncrona):
- Exibe todas as issues de uma vez após geração completa

### Exportação (lazy)
Bytes de exportação são gerados **sob demanda** ao clicar em Download, não a cada ação. A sidebar (`sidebar.py`) usa cache em `session_state` e regenera apenas quando o cache está vazio. Após cada `apply_correction` ou `skip_issue`, o cache é apenas invalidado.

### `render_issue_card()`
Comportamento por status:
- `heuristic_ready` / `ready` — card completo com radio de opções + botões Aplicar/Pular/Revisão posterior
- `processing` — card cinza com spinner
- `queued` — card cinza com posição na fila
- `failed` — card vermelho com botão "Tentar novamente"
- `accepted` / `edited` — card colapsado verde (sem interação)

CSS global injetado uma única vez via `CUSTOM_CSS` em `styles.py`.

### Aceite em Lote
Botão "Aceitar todas top-1 confiança alta" aplica automaticamente sugestões com `confidence == "alta"` para todas as issues prontas. Disponível apenas quando `is_all_done() == True`.

---

## 14. Auditoria (`src/audit/logger.py`)

### `AuditLogger`
Mantém lista de `AuditEntry` em memória. Exporta para:
- CSV via `export_csv(path)`
- JSONL via `export_json(path)`

Cada escrita no IFC gera exatamente uma `AuditEntry` com `old_value`, `new_value`, `decision`, `confidence`, `source`, `user` e `timestamp`.

---

## 15. Configurações (`src/config.py`)

```python
class Settings(BaseSettings):
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    enable_heuristics: bool = False
    ollama_temperature: float = 0.1
    ollama_num_ctx: int = 8192
    ollama_num_predict: int = 2048
    ollama_think: bool = False       # thinking mode para modelos compatíveis
    log_level: str = "DEBUG"
    ifc_upload_dir: str = "./uploads"
```

Carregadas via `pydantic-settings` de `.env` ou variáveis de ambiente. Cacheadas com `@lru_cache(maxsize=1)`. Em testes, `get_settings.cache_clear()` é chamado automaticamente via fixture `autouse`.

---

## 16. Testes (`tests/`)

### Fixtures principais (`conftest.py`)
- `simple_ifc_file` — IFC2X3 mínimo com hierarquia projeto/site/building/storey
- `ifc_with_spaces` — 4 espaços com características distintas (genérico, funcional, sem LongName)
- `ifc_with_walls` — 3 paredes com variações de Pset e material
- `ifc_with_doors` — 2 portas: uma com IfcRelFillsElement, outra sem
- `complete_test_model` — modelo completo para testes de integração
- `simple_ifc_file_ifc4` — base IFC4 para `IfcSanitaryTerminal`
- `ifc_with_sanitary_space` — espaço com WC e lavatório
- `ifc_with_boundary_adjacency` — espaços adjacentes via IfcRelSpaceBoundary

Todos os modelos IFC são criados em memória via `ifcopenshell.api` (sem arquivos em disco).

### Estratégia
- Mocks para Ollama (nunca depende do servidor rodando)
- Testes unitários por módulo + testes de integração em `test_pipeline.py`
- `clear_settings_cache` fixture `autouse` garante isolamento de configuração

---

## 17. Perfis de Readiness (`src/profiles/`)

Perfis pré-definidos registrados em `create_default_registry()`. Exemplos:
- **Simulação Energética** — requer `ThermalTransmittance`, `IsExternal`, zonas térmicas
- **Orçamentação** — requer classificação SINAPI, BaseQuantities
- **Manutenção** — requer identificação de assets, fabricantes

Cada perfil define:
- `ids_filename` — arquivo IDS a carregar de `data/ids_templates/`
- `required_extractors` — quais extratores enriquecem o contexto das issues
- `issue_types` — filtro de quais tipos de issue são relevantes
- `blocking_severities` — severidades que bloqueiam o score de readiness

### `ReadinessScore`
Calculado como `(total_checks - issues_failed) / total_checks * 100`.
Status: `ready` (≥90% sem bloqueantes), `partially_ready` (≥50%), `not_ready` (<50%).

---

## 18. Decisões de Design Importantes

### Por que heurísticas antes do LLM?
Heurísticas são determinísticas, instantâneas e não custam tokens. Para issues simples (banheiro com WC → "Lavabo"), a regra geométrica/tipológica é mais confiável que o LLM e responde imediatamente na UI.

### Por que IssueStore + Worker ao invés de async?
Streamlit não é compatível com `asyncio` puro. O padrão produtor-consumidor com `threading.Thread(daemon=True)` permite background processing sem bloquear o event loop do Streamlit.

### Por que exportação lazy?
Serializar um IFC completo para bytes a cada clique de "Aplicar" causa latência perceptível (100ms–2s dependendo do tamanho do modelo). Os bytes só são necessários quando o usuário clica em "Download", então são gerados sob demanda e cacheados em `session_state`.

### Por que `Literal` em vez de `Enum`?
Pydantic v2 serializa `Literal` diretamente como string sem overhead de conversão. Facilita comparação direta com strings vindas do LLM ou do IFC.

### Por que MCP além da UI?
Permite que LLMs externos (Claude Desktop, Cursor, etc.) usem as mesmas ferramentas de diagnóstico e correção, com o mesmo controle de aprovação. O modelo IFC é carregado uma vez na sessão MCP e pode ser interrogado interativamente.

---

## 19. Convenções de Código

- **Docstrings em português** — toda função pública
- **Código em inglês** — variáveis, funções, classes
- **Sem `print()`** — apenas `loguru.logger`
- **Sem `Any` desnecessário** — tipar o mais específico possível
- **Sem `except Exception` genérico** — catches específicos na maioria dos módulos
- **Sem modificação do IFC sem aprovação** — lei do projeto

---

## 20. Estado Atual e Pontos de Extensão

### Implementado e funcional
- Pipeline completo: diagnóstico → heurísticas → LLM → UI → escrita → auditoria
- Modo progressivo com polling a cada 2s
- Integração IDS (BuildingSMART)
- MCP Server com 15+ tools
- 5+ perfis de readiness pré-definidos
- Extratores: thermal, quantities, classifications, assets
- Exportação lazy (IFC corrigido + CSV + JSONL + métricas)

### Áreas para extensão/melhoria
1. **Novos tipos de issue** — adicionar em `models.py` (Literal), criar módulo de diagnóstico, adicionar heurística e handler no writer
2. **Novo perfil de readiness** — criar `ReadinessProfile` em `profiles/registry.py` com IDS correspondente em `data/ids_templates/`
3. **Paralelização LLM** — o worker atual é single-threaded (Ollama é single-threaded); para múltiplas GPUs, escalar com múltiplos workers
4. **Persistência de sessão** — o estado atual é in-memory por sessão Streamlit; adicionar serialização de `IssueStore` para retomar sessões interrompidas
5. **Validação de saída do LLM** — adicionar JSON Schema para validar estrutura da resposta antes de `parse_llm_response()`
6. **Suporte a IFC4 completo** — alguns diagnósticos testados apenas em IFC2X3; expandir fixtures e validar em IFC4
7. **Novos extratores** — adicionar `FireRatingExtractor`, `AccessibilityExtractor` para perfis específicos
