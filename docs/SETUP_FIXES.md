# Correções de setup e itens em aberto

Registro da branch `fix/setup`. Só tocou `Makefile`, `.env.example`,
`run_mcp_claude.bat` e este arquivo. Nada em `src/`, `data/`, `windows/`, prompts ou testes.

## 1. O que foi corrigido

| # | Arquivo | Correção |
|---|---------|----------|
| 1 | `Makefile:4` | `make install` rodava `pip install -e ".[dev]"`, mas o `pyproject.toml` não declara o extra `dev`; pytest/ruff/mypy estão em `[dependency-groups]` (`pyproject.toml:27-32`), que o pip 24.x não lê. Agora `uv sync` (gerenciador do projeto: `uv.lock`, `windows/install.ps1:843`), que instala o grupo `dev` por padrão. |
| 2 | `.env.example:24-26` | `GROUNDING_MODE=none` fazia `Settings()` falhar: `src/config.py:18-22` não define `extra=`, então vale o padrão `forbid` do pydantic-settings. Reproduzido isoladamente: `Extra inputs are not permitted [type=extra_forbidden]`. A variável não é lida em `src/`, `scripts/`, `windows/` nem `tests/`; docs só registram a remoção (`docs/baseline-verificado-2026-06-26.md:10`). Trocada por comentário. |
| 3 | `run_mcp_claude.bat:2` | `cd /d` apontava para `C:\Users\Keller_\...`; agora `cd /d "%~dp0"` (raiz do repo, onde o .bat está). CRLF preservado (`eol=crlf` no `.gitattributes`). |

### Variáveis de `Settings` que faltam no `.env.example` (não adicionadas — aguardam aprovação)

`MAX_CONCURRENT_LLM_CALLS` (`config.py:70`), `OLLAMA_KEEP_ALIVE` (`config.py:57`),
`SUGGESTION_CACHE_ENABLED` (`config.py:65`), `SUGGESTION_CACHE_PATH` (`config.py:66`).
As demais variáveis do exemplo existem em `Settings`.

Observação: `IDS_XSD_PATH` no `.env.example:36` não tem efeito prático — o campo
`ids_xsd_path` (`config.py:82`) não é lido em lugar nenhum; `ids_parser.py:9,275` usa a
constante `IDS_XSD_PATH` de `config.py:12`.

## 2. Como validar na sua máquina

1. **Makefile:** `make -n install` deve imprimir `uv sync`. Depois `make install` e
   `uv run ruff --version && uv run pytest --version` (devem existir). *(`make` não está no
   PATH do shell em que estas mudanças foram feitas.)*
2. **.env.example:** `copy .env.example .env`, depois
   `uv run python -c "from src.config import get_settings; print(get_settings().ollama_model)"`.
   Deve imprimir `qwen3.5:9b` sem `ValidationError`. (Antes da correção falhava com
   `extra_forbidden` em `grounding_mode`.) Apague o `.env` de teste depois.
3. **run_mcp_claude.bat:** de outra pasta (ex.: `cd %USERPROFILE%`), execute o .bat pelo
   caminho completo; o servidor MCP deve subir a partir da raiz do repo. Confirme CRLF:
   `git ls-files --eol run_mcp_claude.bat` mostra `w/crlf`.

## 3. Itens apenas reportados (sem alteração de código)

### a. `_revert_correction` não tem chamador em produção

- Definição: `src/pipeline.py:947-970` (docstring: "Reverte a correção quando o gate
  pós-validação falha").
- Chamadores: `grep -rn _revert_correction src tests` retorna só a definição e o teste
  `tests/test_pipeline.py:523-540`, que a chama diretamente. Nenhum código de `src/` a usa.
- Onde só avisa: `src/pipeline.py:418-425` — após `_write_correction`, se
  `validation_result.status == "fail"` há apenas `logger.warning(...)`; a entrada de
  auditoria é gravada (`pipeline.py:433-448`) com `post_validation="fail"` e a escrita
  permanece no IFC.
- Proposta (não implementada): flag `POST_VALIDATION_GATE: Literal["warn", "revert"] = "warn"`
  em `Settings` (default `warn` preserva o comportamento medido). Em `pipeline.py:~419`, se
  `== "revert"` e `status == "fail"`, chamar `self._revert_correction(issue, old_value)`,
  re-rodar `_validate_after_write` e registrar no `AuditEntry` `decision="rejected"` (ou um
  campo `reverted=True`) com `old_value`/`new_value` invertidos, mantendo 1 entrada por
  escrita. Pontos de atenção: `_revert_correction` não cobre todos os `issue_type` (ex.:
  se `old_value is None` em `pset_missing` ela não remove a propriedade criada), então a
  reversão precisa de testes antes de virar padrão; e um `fail` por regra IDS preexistente
  (não causada pela escrita) reverteria correções boas. Decisão do Felipe/orientador.

### b. Schema check desligado no pipeline

- `src/pipeline.py:141-145` e `:221-225` constroem `PostValidator(...,
  run_schema_on_element_validation=False)`. O padrão da classe é `True`
  (`src/validation/post_validator.py:21`); com `False`, `validate_element` pula
  `_run_schema_check` (`post_validator.py:45-48`), que usa `ifcopenshell.validate`.
- Por quê: **não encontrei justificativa nos docs** (`grep` em `docs/`, `src/`, `tests/`).
  Hipótese não confirmada: `ifcopenshell.validate` percorre o modelo inteiro a cada
  elemento (custo). Os testes de `post_validator` mockam `_run_schema_check`
  (`tests/test_post_validator.py:47,61,80`), então o caminho real não é exercitado.
- Impacto: a "pós-validação" do pipeline cobre IDS + checagens semânticas, não o schema IFC.

### c. `ids.xsd` é placeholder

- `data/ids_schema/ids.xsd:2-5`: "Placeholder do schema IDS 1.0. Substituir pelo XSD oficial"
  (2.241 bytes).
- Uso: `src/translator/ids_parser.py:275-276` valida todo `.ids` contra ele
  (`validate_ids_against_xsd`, `:228-254`); se o arquivo não existe, só avisa (`:278-281`).
- Impacto: a validação de IDS de entrada é frouxa/diferente da oficial — IDS inválido pelo
  XSD oficial pode passar, e um IDS válido que use construções fora do placeholder pode ser
  rejeitado. CLAUDE.md afirma que IDS é validado contra o XSD; isso só vale com o oficial.

### d. Servidor MCP: HTTP aberto e sessão global

- `src/mcp_server/http_server.py:81` — host padrão `0.0.0.0` (escuta em todas as interfaces).
- `:21-34` — autenticação Bearer **opcional**: sem `IFC_COPILOT_MCP_TOKEN`/`MCP_BEARER_TOKEN`,
  `_is_authorized` retorna `True` e qualquer cliente da rede chama as tools (inclusive as de
  escrita em `tools_write.py`).
- `:62-64` — CORS com `allow_origins=["*"]`.
- `src/mcp_server/server.py:53-60` — `_session` é um dicionário global do processo
  (analyzer, writer, pipeline); todos os clientes HTTP compartilham o mesmo IFC e pipeline,
  e `handle_iniciar_pipeline` (`tools_pipeline.py:126-137`) fecha o pipeline do cliente anterior.
- Risco: com HTTP exposto e sem token, terceiros leem/alteram o IFC carregado e se
  interferem mutuamente. O transporte stdio não tem esse problema.

## 4. Pré-requisitos não validados nesta máquina

- `make` e `uv`: ausentes do PATH do shell usado (`make -n install` não pôde ser executado).
- `ifcopenshell`, `pydantic_settings` e demais dependências: não instaladas no Python global
  (3.13); o pytest completo **não** foi executado. A reprodução do item 2 usou apenas
  `pydantic-settings` instalado em pasta temporária.
- `ollama` (e o modelo `qwen3.5:9b`): não verificado.
- Python do projeto exige `>=3.11` (`pyproject.toml:8`); o `python` global é 3.13.
