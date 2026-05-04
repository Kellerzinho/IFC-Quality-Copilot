# CLAUDE.md — IFC Quality Copilot

## Sobre o Projeto

Sistema interativo de diagnóstico e correção de qualidade de modelos BIM/IFC com validação humana. Combina LLMs (via Ollama local) com o Model Context Protocol (MCP) para sugerir correções semânticas em arquivos IFC, aplicando-as somente após aprovação explícita do engenheiro.

## Stack Tecnológica

- **Python 3.11+** — linguagem principal
- **IfcOpenShell 0.8+** — leitura e escrita de arquivos IFC
- **Streamlit 1.38+** — interface web
- **Ollama** — execução local de LLMs (Llama 3 8B, Qwen 2.5 7B)
- **MCP Python SDK** — Model Context Protocol server
- **Pydantic v2** — modelos de dados e validação
- **Pytest** — testes
- **Loguru** — logging
- **Plotly** — gráficos na interface

## Estrutura do Projeto

```
ifc-quality-copilot/
├── CLAUDE.md                    # este arquivo
├── pyproject.toml
├── Makefile
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── README.md
├── src/
│   ├── models.py                # todos os modelos Pydantic
│   ├── pipeline.py              # orquestração principal
│   ├── config.py                # configurações globais
│   ├── ifc_analyzer/
│   │   ├── __init__.py
│   │   ├── analyzer.py          # classe IFCAnalyzer (orquestrador)
│   │   ├── space_diagnostics.py
│   │   ├── pset_diagnostics.py
│   │   ├── relation_diagnostics.py
│   │   └── system_diagnostics.py
│   ├── translator/
│   │   ├── __init__.py
│   │   ├── ids_parser.py        # parse de arquivos IDS XML
│   │   └── rule_generator.py    # IDS → OperationalRule
│   ├── rule_engine/
│   │   ├── __init__.py
│   │   ├── engine.py            # classe RuleEngine
│   │   └── heuristics/
│   │       ├── __init__.py
│   │       ├── space_heuristics.py
│   │       └── wall_heuristics.py
│   ├── suggestion_engine/
│   │   ├── __init__.py
│   │   ├── ollama_client.py     # cliente HTTP para Ollama
│   │   ├── prompt_templates.py  # templates de prompt por issue_type
│   │   ├── few_shot_examples.py # exemplos para few-shot
│   │   └── suggestion.py        # classe SuggestionGenerator
│   ├── mcp_server/
│   │   ├── __init__.py
│   │   ├── server.py            # MCP server principal
│   │   ├── tools_read.py        # ferramentas de diagnóstico
│   │   └── tools_write.py       # ferramentas de escrita
│   ├── writer/
│   │   ├── __init__.py
│   │   └── ifc_writer.py        # classe IFCWriter
│   ├── audit/
│   │   ├── __init__.py
│   │   └── logger.py            # classe AuditLogger
│   └── ui/
│       ├── app.py               # aplicação Streamlit principal
│       ├── styles.py            # CSS customizado
│       └── components/
│           ├── __init__.py
│           ├── issue_card.py
│           ├── progress_bar.py
│           ├── suggestion_widget.py
│           ├── sidebar.py
│           ├── dashboard.py
│           └── usability_tracker.py
├── tests/
│   ├── conftest.py              # fixtures compartilhadas
│   ├── test_models.py
│   ├── test_analyzer.py
│   ├── test_rule_engine.py
│   ├── test_translator.py
│   ├── test_writer.py
│   ├── test_pipeline.py
│   ├── test_suggestion.py
│   ├── fixtures/                # modelos IFC de teste
│   └── evaluation/
│       ├── evaluation_framework.py
│       ├── benchmark.py
│       └── results/
├── data/
│   ├── ids_templates/           # arquivos IDS de referência
│   ├── prompts/                 # templates de prompt versionados
│   └── heuristics/              # tabelas de referência (NBR 15575)
├── scripts/
│   ├── paper_figures.py
│   └── create_degraded_models.py
└── docs/
    ├── architecture.md
    ├── api.md
    ├── mcp_tools.md
    ├── ids_guide.md
    ├── evaluation.md
    ├── contributing.md
    ├── usability_protocol.md
    └── prompts_log/             # registro de prompts usados
```

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
- **Classes:** PascalCase (`IFCAnalyzer`, `RuleEngine`)
- **Funções:** snake_case (`diagnose_spaces`)
- **Constantes:** UPPER_SNAKE_CASE (`DEFAULT_PSETS`)
- **Variáveis:** snake_case (`ifc_file`, `issue_list`)

### IFC / IfcOpenShell
- Sempre usar `ifcopenshell.open()` para abrir modelos
- GUIDs são strings de 22 caracteres (GlobalId do IFC)
- Ao buscar Psets, usar `ifcopenshell.util.element.get_psets(element)`
- Ao criar Psets, usar `ifcopenshell.api.pset.edit_pset()` quando disponível
- Nunca modificar o IFC sem que `aprovado_pelo_usuario == True`
- Sempre validar que o elemento existe antes de qualquer escrita

### Testes
- **Pytest** — sem unittest
- **Fixtures em `conftest.py`** — modelos IFC mínimos criados via `ifcopenshell.file()`
- **Nomes descritivos:** `test_space_with_generic_name_creates_issue`
- **Testes parametrizados** com `@pytest.mark.parametrize` quando testar variações
- **Mocks** para Ollama (nunca depender do servidor rodando em testes)
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

### Logging e Auditoria
- **loguru** com formato: `{time:YYYY-MM-DD HH:mm:ss} | {level} | {module}:{function}:{line} | {message}`
- **Audit trail** separado do log técnico — AuditLogger gera CSV/JSON
- **Nunca logar dados sensíveis** — GUIDs e valores técnicos são OK
- **Cada escrita no IFC = 1 entrada no AuditLogger**

## Referências Rápidas

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
make lint             # roda ruff + mypy
make run-ui           # inicia Streamlit (porta 8501)
make run-mcp          # inicia MCP server
make docker-up        # sobe tudo via docker-compose
```

## Contexto para o LLM (ao gerar código)

Ao pedir para o Claude Code gerar código neste projeto:
1. Leia este CLAUDE.md primeiro
2. Leia `src/models.py` para entender os modelos de dados
3. Leia o módulo que será modificado/criado
4. Siga as convenções acima
5. Sempre gere testes junto com o código
6. Docstrings em português, código em inglês (nomes de variáveis/funções)