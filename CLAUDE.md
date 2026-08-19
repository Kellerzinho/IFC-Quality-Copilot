# CLAUDE.md — IFC Quality Copilot

## Sobre o Projeto

**IFC Quality Copilot** é um fluxo com supervisão humana para enriquecimento semântico
de modelos IFC, combinando padrões openBIM (IFC, IDS, bSDD), LLM local (via Ollama)
e rastreabilidade das alterações. O objetivo é melhorar a qualidade semântica de modelos
IFC — nomenclaturas genéricas, propriedades ausentes, classificações incompletas e relações
semânticas frágeis — **sem comprometer o controle técnico** sobre os arquivos: o LLM apenas
sugere, e somente correções aprovadas pelo engenheiro são escritas no IFC.

**Palavras-chave:** LLM local; openBIM; IFC; IDS; bSDD.

### Fluxo conceitual (pipeline)

1. **Inspeção programática (IfcOpenShell)** — leitura do modelo e extração de entidades,
   propriedades, classificações e quantidades.
2. **Leitura de perfis IDS** — identificação dos requisitos computáveis aplicáveis
   (entidades, psets, propriedades, classificações e restrições de valor).
3. **Etapa determinística** — detecção de lacunas informacionais e criação dos campos
   exigidos pelo IDS (conjuntos de propriedades, propriedades e marcadores de revisão),
   sem participação do LLM.
4. **Construção de contexto com bSDD** — consulta ao bSDD para recuperar termos e
   definições oficiais e organizar um contexto técnico (grounding) para o LLM.
5. **Sugestão controlada (LLM local via Ollama)** — geração de sugestões estruturadas
   de preenchimento, classificação, renomeação ou correção semântica.
6. **Revisão humana** — aceitação, edição ou rejeição de cada sugestão.
7. **Escrita controlada + pós-validação** — aplicação apenas das correções aprovadas e
   verificação do resultado.
8. **Consolidação e exportação** — exportação do IFC atualizado com registros de auditoria,
   relatórios e artefatos de rastreabilidade (incluindo BCF).

A contribuição central **não é a automação integral**, mas a estruturação de um fluxo
verificável e auditável de enriquecimento semântico com humano no circuito.

## Stack Tecnológica

- **Python 3.11+** — linguagem principal
- **IfcOpenShell 0.8+** — leitura e escrita de arquivos IFC
- **IDS** — `data/ids_schema/ids.xsd` para validação; parser próprio em `src/translator`
- **bSDD** — cliente HTTP + cache para termos/classificações oficiais
- **Ollama** — execução local de LLMs (ex.: Llama 3 8B, Qwen 2.5 7B)
- **MCP Python SDK** — Model Context Protocol server (stdio e HTTP)
- **BCF** — exportação de issues/alterações para colaboração
- **Streamlit 1.38+** — interface web
- **Pydantic v2** — modelos de dados e validação
- **Pytest** — testes
- **Loguru** — logging
- **Plotly** — gráficos na interface

## Estrutura do Projeto

```
ifc-quality-copilot/
├── CLAUDE.md                    # este arquivo
├── PROJECT_CONTEXT.md           # contexto adicional do projeto
├── fase3.md                     # notas da fase atual
├── pyproject.toml
├── Makefile
├── run_mcp_claude.bat
├── src/
│   ├── models.py                # todos os modelos Pydantic
│   ├── pipeline.py              # orquestração principal do fluxo
│   ├── config.py                # configurações globais
│   ├── ifc_analyzer/            # diagnóstico e extração do IFC
│   │   ├── analyzer.py          # classe IFCAnalyzer (orquestrador)
│   │   ├── space_diagnostics.py
│   │   ├── pset_diagnostics.py
│   │   ├── relation_diagnostics.py
│   │   ├── system_diagnostics.py
│   │   ├── universal_extractor.py
│   │   └── extractors/          # extratores especializados
│   │       ├── asset_extractor.py
│   │       ├── classification_extractor.py
│   │       ├── quantity_extractor.py
│   │       └── thermal_extractor.py
│   ├── translator/              # IDS → regras operacionais
│   │   ├── ids_parser.py        # parse de arquivos IDS XML
│   │   ├── rule_generator.py    # IDS → OperationalRule
│   │   └── pset_resolver.py     # resolução de psets/propriedades
│   ├── bsdd/                    # integração buildingSMART Data Dictionary
│   │   ├── client.py            # cliente HTTP do bSDD
│   │   ├── cache.py             # cache local de respostas
│   │   ├── context_builder.py   # contexto técnico (grounding) para o LLM
│   │   └── models.py
│   ├── semantic/               # URIs canônicas e semântica compartilhada
│   │   ├── canonical_uris.py
│   │   └── property_match.py    # matcher único de nomes IFC × bSDD
│   ├── semantic_registry/      # resolução e política de fontes
│   │   ├── registry.py
│   │   ├── resolver.py
│   │   └── source_policy.py
│   ├── suggestion_engine/       # geração de sugestões via LLM
│   │   ├── ollama_client.py     # cliente HTTP para Ollama
│   │   ├── prompt_templates.py  # templates de prompt por issue_type
│   │   ├── prompt_router.py     # seleção de prompt/estratégia
│   │   ├── grounding.py         # injeção de contexto bSDD/IDS
│   │   ├── normalization.py     # normalização das respostas do LLM
│   │   ├── issue_store.py       # persistência/estado das issues
│   │   ├── issue_deduplicator.py
│   │   ├── suggestion_cache.py  # cache de sugestões (SQLite)
│   │   ├── thermal_recompute.py # refaz a soma de U (o LLM declara os termos)
│   │   ├── worker.py            # processamento assíncrono/em lote
│   │   └── suggestion.py        # classe SuggestionGenerator
│   ├── validation/
│   │   └── post_validator.py    # pós-validação após a escrita
│   ├── writer/
│   │   └── ifc_writer.py        # classe IFCWriter
│   ├── bcf/
│   │   └── exporter.py          # exportação BCF
│   ├── profiles/               # perfis de readiness por caso de uso
│   │   ├── registry.py
│   │   ├── base_ifc/ acoustic/ budget/ compliance/ energy/
│   │   ├── fire_safety/ fm/ hvac/ structural/ ids/
│   ├── ifc_registry/
│   │   └── registry.py          # registro de entidades/tipos IFC
│   ├── experiment/             # avaliação experimental
│   │   ├── runner.py            # execução dos experimentos
│   │   └── metrics.py           # métricas (top-k, P/R/F1, taxas, tempo)
│   ├── mcp_server/
│   │   ├── server.py            # MCP server (stdio)
│   │   ├── http_server.py       # MCP server (HTTP)
│   │   ├── registry.py          # registro de tools
│   │   ├── tools_read.py        # ferramentas de diagnóstico
│   │   ├── tools_write.py       # ferramentas de escrita
│   │   └── tools_pipeline.py    # ferramentas de orquestração do pipeline
│   ├── audit/
│   │   └── logger.py            # classe AuditLogger
│   └── ui/
│       ├── app.py               # aplicação Streamlit principal
│       ├── styles.py            # CSS customizado
│       └── components/
│           ├── issue_card.py
│           ├── progress_bar.py
│           ├── sidebar.py
│           ├── dashboard.py
│           └── filters.py
├── tests/                       # ~45 arquivos de teste (pytest)
│   ├── conftest.py              # fixtures compartilhadas
│   ├── fixtures/                # modelos IFC de teste
│   └── evaluation/              # framework e benchmark de avaliação
├── data/
│   ├── ids_schema/ids.xsd       # schema XSD do IDS
│   ├── ids_templates/           # perfis IDS de referência (.ids)
│   └── cache/                   # cache bSDD e de sugestões
├── scripts/
│   └── test_bsdd_live.py        # teste de integração ao vivo do bSDD
├── docs/                        # documentação, planos e specs
└── Artigo/                      # artigo IME, resumo ERA BIM 2026, PIBIC
```

> Nota: o antigo módulo `rule_engine/` foi descontinuado; a geração de regras a partir
> do IDS vive em `src/translator/rule_generator.py`.

## Convenções de Código

### Geral
- **Docstrings em português** — toda função pública tem docstring explicando o que faz
- **Type hints obrigatórios** — toda função tem anotação de tipos
- **Sem `print()`** — usar `loguru.logger` para tudo
- **Sem `Any` desnecessário** — tipar o mais específico possível
- **Imports organizados** — stdlib, terceiros, locais (separados por linha em branco)

### Modelos de Dados
- **Pydantic v2 BaseModel** para tudo que é dados estruturados
- **Literal** para enums simples (não usar Enum do Python)
- **Valores default** sempre que fizer sentido
- **Validadores** com `@field_validator` quando necessário
- **Método `.to_dict()`** para serialização customizada quando Pydantic não basta

### Padrões de Nomenclatura
- **Arquivos:** snake_case (`space_diagnostics.py`)
- **Classes:** PascalCase (`IFCAnalyzer`, `SuggestionGenerator`)
- **Funções:** snake_case (`diagnose_spaces`)
- **Constantes:** UPPER_SNAKE_CASE (`DEFAULT_PSETS`)
- **Variáveis:** snake_case (`ifc_file`, `issue_list`)

### IFC / IfcOpenShell
- Sempre usar `ifcopenshell.open()` para abrir modelos
- GUIDs são strings de 22 caracteres (GlobalId do IFC)
- Ao buscar Psets, usar `ifcopenshell.util.element.get_psets(element)`
- Ao criar Psets, usar `ifcopenshell.api.pset.edit_pset()` quando disponível
- **Nunca modificar o IFC sem que `aprovado_pelo_usuario == True`**
- Sempre validar que o elemento existe antes de qualquer escrita
- Toda escrita deve ser passível de pós-validação (`src/validation/post_validator.py`)

### IDS
- IDS é a fonte dos **requisitos computáveis**; o parser está em `src/translator/ids_parser.py`
- Validar arquivos IDS contra `data/ids_schema/ids.xsd`
- A criação determinística de campos exigidos pelo IDS ocorre **antes** de acionar o LLM
- Perfis IDS de referência ficam em `data/ids_templates/`

### bSDD
- bSDD fornece **termos e definições oficiais** para grounding do LLM (nunca confiar no
  LLM para terminologia sem contexto)
- Escopo medido (2026-08-04): no dicionário IFC 4.3, o grounding efetivo é **classe
  oficial + URI canônica** (+ tipo de dado quando a propriedade existe no dicionário);
  `allowed_values` é nulo nas propriedades do experimento — o vocabulário fechado vem
  dos **templates** (ver `docs/revisao-bsdd-2026-08-04.md`)
- Nomes de propriedade: o bSDD usa forma humana ("Fire Rating"), IFC/IDS usam PascalCase —
  **sempre** comparar via `src/semantic/property_match.py`, nunca literalmente
- Acesso via `src/bsdd/client.py`, sempre com cache (`src/bsdd/cache.py`)
- O contexto técnico é montado em `src/bsdd/context_builder.py`
- Em testes, **nunca** depender da API bSDD ao vivo (usar mocks/fixtures);
  testes ao vivo só via `scripts/test_bsdd_live.py`

### Sugestões (LLM)
- **`PROMPT_VERSION` vigente: `v7.8`** (fonte única em `prompt_templates.py`),
  declarado em `docs/condicao-v7-8-2026-08-19.md`. **O instrumento das rodadas
  publicadas é o `v7.7`** (par unificado, escala-4070, ablação-bSDD) — o v7.8
  corrige empacotamento de grounding e ainda não foi executado
- Estado do gabarito e do instrumento anterior em `docs/emenda-gt-2026-08-12.md`
  e `docs/condicao-v7-6-2026-08-12.md` — **leia antes de mexer em prompt, ground
  truth ou comparador**
- O LLM **apenas sugere**; a aplicação é sempre mediada por aprovação humana
- **Aritmética não é tarefa de LLM** (medido em 2026-08-02): onde houver conta,
  o LLM declara os termos e o código executa — ver `thermal_recompute.py` e
  `docs/condicao-v7-2026-08-04.md`
- **Mudança de prompt é mudança de instrumento:** bumpe `PROMPT_VERSION` nos
  **três** pinos — `prompt_templates.py`, `scripts/build_windows_release.py` (com
  `RELEASE_DATE`) e **`windows/install.ps1`** (esquecer este quebra 8 testes de
  contrato Windows) —, meça o delta com `scripts/dump_prompts_spy.py` +
  `diff_prompts.py` (sem GPU) e declare a condição num doc datado. Evidência do
  arquivo tende a ajudar; roteiro de como raciocinar tende a atrapalhar
  (+31,2 pp × −12,5 pp, matriz v6)
- **Grounding só ajuda se contiver a resposta** (medido em 2026-08-18): bloco sem
  escopo custou um estrato inteiro por truncamento, e "use apenas o vocabulário
  fornecido" sobre um bloco que imprime `livre` mede −2,34 pp. Ver
  `docs/resultado-ablacao-bsdd-2026-08-19.md`
- **Três naturezas legítimas de mudança de estímulo**, e nenhuma outra:
  evidência do arquivo IFC, vocabulário genérico (tipologia de literatura ou
  classe de schema) e formato. Colisão numérica entre prompt e gabarito precisa
  estar declarada em `tests/test_prompt_nao_vaza_ground_truth.py`
- **O comparador também é instrumento**: presumir a parte difícil da resposta
  (era o caso da classe de fogo a partir de uma duração solta) é vazamento tanto
  quanto entregá-la no prompt
- Sugestões devem ser **estruturadas** (parseáveis) e normalizadas em `normalization.py`
- Usar `grounding.py` para injetar contexto IDS/bSDD nos prompts
- Cachear sugestões (`suggestion_cache.py`) para reprodutibilidade e custo

### Testes
- **Pytest** — sem unittest
- **Fixtures em `conftest.py`** — modelos IFC mínimos criados via `ifcopenshell.file()`
- **Nomes descritivos:** `test_space_with_generic_name_creates_issue`
- **Testes parametrizados** com `@pytest.mark.parametrize` quando testar variações
- **Mocks** para Ollama e bSDD (nunca depender de serviços externos em testes)
- **Coverage mínimo:** 80% em módulos core

### Interface Streamlit
- **session_state** para todo estado persistente entre reruns
- **Componentes em funções** — cada componente é uma função em arquivo separado
- **CSS via `st.markdown(unsafe_allow_html=True)`** — mínimo necessário
- **Chaves únicas** em widgets (`key=f"radio_{issue.id}"`)
- **st.spinner** para operações longas
- **st.cache_data** para dados que não mudam (ex: parse do IFC)

### MCP Server
- **Descriptions em português** — o LLM precisa entender as tools
- **JSON Schema completo** — todo input e output documentado
- **Erro amigável** — nunca retornar stack trace, sempre mensagem legível
- **Idempotência** — chamar a mesma tool 2x com mesmos params = mesmo resultado
- Dois transportes: stdio (`server.py`) e HTTP (`http_server.py`); tools registradas em `registry.py`

### Logging e Auditoria
- **loguru** com formato: `{time:YYYY-MM-DD HH:mm:ss} | {level} | {module}:{function}:{line} | {message}`
- **Audit trail** separado do log técnico — AuditLogger gera CSV/JSON
- **Nunca logar dados sensíveis** — GUIDs e valores técnicos são OK
- **Cada escrita no IFC = 1 entrada no AuditLogger**, garantindo rastreabilidade

## Avaliação Experimental

O experimento (`src/experiment/`) avalia a abordagem segundo qualidade semântica,
conformidade com IDS, eficiência operacional e viabilidade computacional. Métricas:

- **Qualidade das sugestões:** acurácia top-1 / top-3, precisão, revocação e F1 em
  relação a uma referência humana/de especialistas
- **Eficiência operacional:** taxas de aceitação, edição e rejeição; tempo médio de revisão
- **Viabilidade computacional:** comparação entre modelos locais (Ollama) quanto a
  desempenho, consumo de recursos e estabilidade das respostas estruturadas

Os modelos LLM e suas versões exatas devem ser **fixados e registrados** para garantir
reprodutibilidade dos resultados do artigo.

## Referências Rápidas

### Pontos de cálculo
Onde há aritmética, quem executa e com que constantes (λ, Rsi/Rse, câmara de ar,
bandas de equivalência, guardas de plausibilidade): **`docs/pontos-de-calculo.md`**.
Consultar antes de mexer em qualquer número normativo ou tolerância.

### Psets Mais Comuns (NBR 15575)
- `Pset_WallCommon`: ThermalTransmittance, IsExternal, FireRating, IsLoadBearing
- `Pset_DoorCommon`: FireRating, IsExternal
- `Pset_SlabCommon`: IsExternal, LoadBearing
- `Pset_SpaceCommon`: Category, GrossFloorArea
- `Pset_MaterialConcrete`: CompressiveStrength

### Issue Types
- `space_unnamed` — IfcSpace com nome genérico
- `pset_missing` — propriedade obrigatória ausente ou vazia
- `relation_broken` — IfcRelFillsElement ou IfcRelSpaceBoundary ausente
- `system_unclassified` — parede/laje sem classificação de sistema construtivo

### Severidades
- `high` — impede simulação ou verificação normativa (ThermalTransmittance, relações)
- `medium` — degrada qualidade mas não impede uso (classificação de sistemas)
- `low` — inconveniência (nomes genéricos de espaços)

## Comandos Úteis

```bash
make install          # instala dependências
make test             # roda pytest
make test-cov         # pytest com cobertura
make lint             # roda ruff + mypy
make format           # formata o código
make run-ui           # inicia Streamlit (porta 8501)
make run-mcp          # inicia MCP server (stdio)
make run-mcp-http     # inicia MCP server (HTTP)
make clean            # limpa artefatos temporários
```

## Contexto para o LLM (ao gerar código)

Ao pedir para gerar código neste projeto:
1. Leia este CLAUDE.md primeiro
2. Leia `src/models.py` para entender os modelos de dados
3. Leia o módulo que será modificado/criado
4. Siga as convenções acima
5. Sempre gere testes junto com o código
6. Docstrings em português, código em inglês (nomes de variáveis/funções)
7. Respeite o princípio fundamental: **o IFC só é alterado após aprovação humana explícita**

## Referências (artigo)

- Bloch, T. (2022). *Connecting research on semantic enrichment of BIM: Review of
  approaches, methods and possible applications.* Journal of Information Technology in
  Construction, 27, 416–440. https://doi.org/10.36680/j.itcon.2022.020
- buildingSMART International. *openBIM* / *Information Delivery Specification (IDS)*.
  https://www.buildingsmart.org/
- IfcOpenShell Contributors. *IfcOpenShell.* https://ifcopenshell.org/
- Solihin, W., & Eastman, C. (2015). *Classification of rules for automated BIM rule
  checking development.* Automation in Construction, 53, 69–82.
  https://doi.org/10.1016/j.autcon.2015.03.003
```
