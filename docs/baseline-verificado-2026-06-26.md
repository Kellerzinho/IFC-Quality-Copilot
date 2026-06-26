# Baseline Verificado — pré-Fase 0 (IFC Quality Copilot)

**Data:** 2026-06-26
**Método:** suíte de testes rodada inline (`python -m pytest`) + workflow read-only de 19 agentes
(6 caracterizando o delta não-commitado por área + 13 re-verificando os achados **F1–F15** de
`docs/revisao-critica-2026-06-09.md` contra o código atual).
**Objetivo:** estabelecer o estado real do código **antes** de executar a Fase 0 do
`docs/plano-orquestracao-2026-06-25.md`. Nada foi editado nesta auditoria.

---

## 0. Headline (leia isto primeiro)

1. **Não existe baseline commitado funcional.** O toplevel git é `C:/Users/Keller_` (repo home
   acidental). O último commit do projeto é `a37d665 "1.0"` (**2026-05-03**). Esse commit **não
   importa** em runtime: `pipeline.py` importa `suggestion_cache.py` e `issue_deduplicator.py`,
   que são **arquivos não-rastreados** (não existiam no commit). O único estado que funciona é a
   **working tree atual**, inteiramente não-commitada.
2. **A working tree atual é saudável:** `python -m pytest` → **671 passed, 0 failed (7.5s, exit 0)**,
   coleta limpa (sem import quebrado).
3. **O delta real é maior que os "9k de `git diff`":** 27 arquivos modificados **+ 16 arquivos
   novos não-rastreados** (10 em `src/`, 6 testes). O `git diff --stat` não enxerga os `??`.
4. **Consequência prática:** o primeiro passo seguro antes da Fase 0 é **criar um commit de
   baseline correto** (incluindo os 16 untracked), com pathspec cuidadoso por causa do toplevel
   na home. Sem isso, não há rede de segurança e um `git commit -am` ingênuo quebraria os imports.

---

## 1. Baseline de testes / lint

| Verificação | Resultado |
|---|---|
| `python -m pytest` (working tree atual) | **671 passed, 0 failed — exit 0 (7.5s)** |
| `pytest --collect-only` | 671 coletados, exit 0 — **sem import quebrado** pelo delta |
| `make lint` (`ruff` + `mypy`) | **Não executável** — sem `.venv`; `ruff`/`mypy` ausentes (nem módulo nem binário); `make` fora do PATH |

**Pendência de baseline:** habilitar lint com `pip install -e ".[dev]"` (declara dev-deps);
hoje `make lint` falha por ferramenta ausente, não por erro de código.

---

## 2. Estado de versionamento (o delta não-commitado real)

**Toplevel:** `C:/Users/Keller_` — qualquer `git add` precisa de pathspec restrito ao subdir do
projeto; **nunca `git add -A`** (varreria lixo da home).

**27 arquivos modificados (`M`):** `src/config.py`, `src/models.py`, `src/pipeline.py`,
todo `src/suggestion_engine/*` (6), `src/ifc_analyzer/{analyzer,pset_diagnostics}.py`,
`src/translator/rule_generator.py`, `src/ui/*` (4), `src/mcp_server/server.py`,
`src/profiles/registry.py`, `src/validation/post_validator.py`, `src/writer/ifc_writer.py`,
7 testes; + `CLAUDE.md`, `Makefile`, `pyproject.toml`, `.claude/settings.local.json`,
`data/cache/bsdd_cache.json`.

**16 arquivos novos não-rastreados (`??`) — um baseline PRECISA incluí-los:**

| Arquivo novo | Papel | Crítico? |
|---|---|---|
| `src/suggestion_engine/suggestion_cache.py` | cache SQLite + `compute_signature` | **sim — alvo do F4** |
| `src/suggestion_engine/issue_deduplicator.py` | `build_reuse_map`, fingerprint | **sim — pipeline importa** |
| `src/suggestion_engine/grounding.py` | `GroundedIssueContext`, `prepare_llm_grounding` | **sim — alvo de F1/F13/F5** |
| `src/ifc_analyzer/universal_extractor.py` | extrator universal p/ IDS arbitrário | sim |
| `src/translator/pset_resolver.py` | `resolve_property()` | sim |
| `src/mcp_server/http_server.py` | transporte HTTP do MCP | médio |
| `src/mcp_server/tools_pipeline.py` | tools de pipeline do MCP | médio |
| `src/profiles/{acoustic,fire_safety,structural}/__init__.py` | 3 perfis novos | médio |
| `tests/test_grounding.py`, `test_issue_deduplicator.py`, `test_issue_store_states.py`, `test_mcp_pipeline.py`, `test_suggestion_cache.py`, `test_suggestion_cache_integration.py` | testes dos módulos novos | sim (cobertura) |

**Veredito do delta por área (todas coerentes e com 671 testes verdes):**

| Área | Risco p/ baseline | Toca alvos da Fase 0? | Observação |
|---|---|---|---|
| `suggestion_engine` (6 arq.) | baixo | não (direto) | telemetria + cache + dedup + prompt compacto + 9 estados no IssueStore |
| `pipeline+models+config` | **alto** | **sim** | depende de untracked; SuggestionMetrics e campos de determinismo **já existem** |
| `analyzer+translator+writer+validation` | baixo | não | `analyze_from_ids()`, psets p/ Beam/Column/Roof/Stair/CurtainWall |
| `ui+mcp+profiles` | baixo | não | UI progressiva refatorada; **filtros/busca removidos** (decisão de UX — registrar no artigo) |
| `tests` | médio | **sim** | adaptados a `generate()→(text, metrics)`; `test_suggestion.py` tem BOM UTF-8 — validar parse |
| `meta+docs+cache` | baixo | não | `CLAUDE.md` reescrito; `pyproject` +starlette/uvicorn; cache bSDD +7.5k |

---

## 3. Re-auditoria F1–F15 (contra o código atual)

11 dos 13 **persistem e são relevantes à Fase 0**; F5 está **parcialmente endereçado**;
F7 é **não-issue** (o achado original era incorreto — o seed existe).

| # | Status | Local atual (verificado) | Fase 0? |
|---|---|---|---|
| **F1+F13** | `holds` | `pipeline.py:81-83` (overwrite) **+ `worker.py:54` (bug DUPLICADO)**; `grounding.py:58-135` (sem `grounding_mode`); `suggestion.py:122` | **sim** |
| **F2** | `holds` | `experiment/runner.py:12-33` + `metrics.py:9-27` (stubs); Evaluator ainda em `tests/evaluation/evaluation_framework.py:94` | **sim** |
| **F3** | `holds` | `models.py:98` (`Issue.id`) e `models.py:561` (`OperationalRule.id`) — `uuid4()[:8]` | **sim** |
| **F4** | `holds` | `suggestion_cache.py:27-60` (`compute_signature` sem `grounding_mode`) + `:132-139`; `pipeline.py:114` (`invalidate_by_model` apaga cache de outros modelos) | **sim** |
| **F5** | `partially_addressed` | compacto `prompt_templates.py:37-80` já injeta tipo/unidade/candidatos/abstenção; **falta contexto rico do elemento** em `GroundedIssueContext` (`grounding.py:16-44`); template legado `:166-178` ainda fraco e roteado em `:579/604` | **sim** |
| **F6** | `holds` | `models.py:116,147-151` (status só sai de `pending` via `resolve()`); sem revisor simulado | **sim** |
| **F7** | `holds` (seed existe) | `config.py:34` (`ollama_seed=42`) + `ollama_client.py:48-49` | **não** — achado original incorreto, nada a fazer |
| **F8** | `holds` | `models.py:267-276/307-317` (BSDDContext), `:329-341/381-399` (IDSContext); `ValidationResult :402-434` é dualidade de outra natureza | sim (limpeza) |
| **F9** | `holds` | `PROJECT_CONTEXT.md:114,161,332` (rule_engine inexistente); `CLAUDE.md:257-261` lista 4 issue types vs 9 em `models.py:102-112` | sim (docs) |
| **F10+F11** | `holds` | `evaluation_framework.py:292,297` (`str()==str()`), `:302-306` (precision = top-1/issues-com-sugestão) | **sim** |
| **F12** | `holds` | `models.py:183-201` — faltam `attempts`, `failure_reason`, `json_repaired` | **sim** |
| **F14** | `holds` | `tests/fixtures/` vazio; `*.ifc` em `.gitignore:14`; sem GT materializado; o IFC do prédio existe local mas é ignorado | **sim** |
| **F15** | `holds` | `pipeline.py:534` (`compute_readiness`), `:551` (`total_checks = ids_rules_count + total_issues`); dupla contagem parcial via `:213` | sim |

---

## 4. Refinamentos que a auditoria acrescentou ao plano de 25/06

1. **F1 tem um segundo local:** o overwrite de `grounding_mode` está **também em `worker.py:54`**,
   não só em `pipeline.py:83`. A Fase 0.1 precisa corrigir **os dois**.
2. **O alvo do F4 (`compute_signature`) está num arquivo não-rastreado** (`suggestion_cache.py`),
   e o `grounding.py` (F1/F13/F5) também. A Fase 0 vai editar arquivos que ainda **não estão
   no git** — mais um motivo para o commit de baseline primeiro.
3. **A Fase 0 está parcialmente em movimento:** `SuggestionMetrics` (F12) **já existe** —
   só faltam 3 campos; os campos de determinismo do `config.py` já estão lá; `invalidate_by_model`
   (problema do F4) já está cabeado. O delta é andaime do experimento, não a correção em si.
4. **F5 mudou de "fraco" para "parcial":** o caminho compacto melhorou; o que falta é
   **enriquecer `GroundedIssueContext`** com material/espessura/PredefinedType/IsExternal.
5. **UI perdeu filtros/busca** (decisão de UX deliberada) — relevante registrar no artigo:
   não há filtragem por tipo durante a avaliação.

---

## 5. Sequência recomendada (ajustada à realidade)

**Passo 0 (NOVO, pré-requisito) — Commit de baseline correto.**
Working tree passa 671 testes mas está 100% não-commitada e sem rede de segurança. Antes de
tocar em qualquer coisa:
- `git add` **com pathspec restrito ao subdir do projeto** (toplevel é a home!), incluindo os
  16 untracked + 27 modificados + `pyproject.toml`/`Makefile` (necessários para os módulos novos).
- Conferir com `git add --dry-run` antes de commitar; **nunca `git add -A`**.
- Avaliar `.gitignore` para `data/cache/bsdd_cache.json` e `.claude/settings.local.json`
  (cache e settings locais — decidir se entram ou viram ignore).
- Commit rotulado honestamente como *"snapshot funcional (Fase 0 parcialmente iniciada)"*,
  **não** como "pré-Fase 0 limpo".

**Gate independente — confirmar o desenho híbrido com o Maj. Otranto** (Risco #1 do plano),
antes de investir na Fase 0.

**Depois, Fase 0 incremental (TDD + commit atômico por item), ordem sugerida:**
1. **0.2 / F3** — IDs determinísticos (`Issue.id`, `OperationalRule.id`). Destrava cache e GT.
2. **0.1 / F1+F13** — `grounding_mode` funcional nos 3 modos; remover overwrite em
   `pipeline.py:83` **e `worker.py:54`**; gatear grounding em `prepare_llm_grounding`.
3. **0.4 / F4** — `grounding_mode` na assinatura do `compute_signature`; remover
   `invalidate_by_model` do `__init__`.
4. **0.3 / F10+F11** — promover Evaluator p/ `src/experiment/`; comparação normalizada; métricas definidas.
5. **0.5 / F2+F6+F12** — reescrever `src/experiment/` como harness real; revisor simulado; campos `attempts`/`failure_reason`/`json_repaired` no `SuggestionMetrics`.
6. **0.6 / F9+F15** — saneamento de docs + denominador do readiness.

Cada item fecha com `make test` verde (e `make lint`, uma vez instaladas as dev-deps).

---

## 6. Artefatos desta auditoria

- Script do workflow: `…/workflows/scripts/baseline-verificado-fase0-wf_9eef2047-65e.js`
- Resultado bruto (JSON, 19 agentes): salvo no diretório de tasks da sessão.
- Este relatório consolida tudo; é o ponto de partida verificado para a Fase 0.
