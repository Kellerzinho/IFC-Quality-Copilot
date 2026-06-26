# Plano de Orquestração — Fase Experimental (IFC Quality Copilot)

**Data:** 2026-06-25
**Autor da sessão:** Felipe + Claude (orquestração)
**Base:** `docs/plano-consolidado-2026-06-09.md` + `docs/revisao-critica-2026-06-09.md` (achados F1–F15) + abstract do artigo *A ERA BIM* (`Resumo IFC-Quality-Copilot corrigido.pdf`) + **auditoria de estado em 25/06** + **decisões do Felipe (25/06)** + **hardware real da máquina**.
**Alvo de publicação:** 9º Congresso Internacional **A ERA BIM** (resumo em `Artigo/`); ENTAC/SBTIC 2027 para o artigo completo. Orientador: Maj. Rafael Otranto.

> Este documento **substitui o sequenciamento** do plano de 09/06 onde houver conflito, porque incorpora três decisões novas (abaixo) e o estado real do código em 25/06. O plano de 09/06 continua válido como detalhamento dos achados F1–F15.

---

## Decisões fixadas nesta sessão (25/06)

1. **Desenho experimental = HÍBRIDO** *(confirmar com Maj. Otranto)*:
   - **B1 — Ablação de grounding em 1 modelo fixo:** `none` × `ids_only` × `ids_bsdd`, nas 3 tarefas. Valida a **hipótese central** do `fase3.md` (grounding melhora conformidade/aceitação).
   - **B2 — Benchmark de famílias de LLM** sob `ids_bsdd` fixo, nas 3 tarefas. Responde "qual modelo local é viável aqui".
   - **Consequência forte vs. plano de 09/06:** `grounding_mode` **NÃO é removido** — ele precisa ficar **funcional e correto** (os 3 modos têm de gerar prompts/saídas realmente distintos). Isso muda a Fase 0.1.

2. **Modelo de estudo = prédio de autoria do Felipe** (projeto de engenharia, com lacunas reais), **não a CASA**.
   - Entrada de teste = versão "como exportada" (com lacunas).
   - Ground truth = versão **enriquecida corretamente** pelo Felipe (**GT-by-diff**).
   - **Complemento recomendado:** 1 IFC externo completo via *masking* controlado (proveniência independente + massa estatística).
   - **Guardrail anti-circularidade:** a LLM avaliada **nunca** define o GT; só as partes determinísticas (IDS/bSDD) + expertise + norma.

3. **Tarefas do experimento (3):** preenchimento de Pset · nomeação de espaços · classificação de sistemas.

**Regra inviolável:** o IFC só é alterado após aprovação humana explícita (`aprovado_pelo_usuario == True`). O "revisor simulado" das fases experimentais opera sobre **cópias descartáveis**, e isso é declarado no artigo.

---

## 1. Hardware real e o papel do `llmfit`

| Recurso | Valor medido (25/06) |
|---|---|
| GPU | **RTX 4060 Laptop, 8 GB VRAM** (~6.3 GB livres em idle) |
| RAM | **16 GB** (restrição relevante — mais apertada que o plano assumia) |
| CPU | i7-13650HX (14 cores / 20 threads) |
| Ollama já instalado | `qwen3.5:9b` (default do projeto), `qwen3:14b`, `batiai/qwen3.5-9b:q4`, `llama3:8b`, `gemma-4-12B` (custom) |

**Alvo prático:** modelos **7–9B em Q4 (~5–7 GB)** cabem na VRAM e são rápidos; um **14B** (ex.: `qwen3:14b`) entra como *teto de qualidade mais lento* (offload p/ CPU/RAM).

**`llmfit`** (instalado via scoop em `…\scoop\shims\llmfit.exe`) entra como ferramenta de **seleção de modelos e viabilidade**:
- `llmfit system --json` → especificação detectada (fonte da seção de hardware do paper).
- `llmfit fit --json` / `recommend --json` → quais modelos cabem e quão bem (gera a **matriz candidata**).
- `llmfit plan` → VRAM por modelo + contexto (dimensiona `num_ctx`).
- `llmfit bench` → **tokens/s reais** contra o Ollama em execução (parte da métrica de eficiência).

**Reprodutibilidade (importante p/ o artigo):** fixar **tags e digests oficiais/citáveis** em `src/experiment/results/models.lock.json`. Evitar fine-tunes *custom* (`gemma-4-12B fable5`) e tags incomuns (`qwen3.5`) como modelos do paper; usar versões oficiais com digest fixado via `ollama pull modelo:tag`.

---

## 2. Sequência

```
Fase 0 — Fundação experimental (correções de base)         [bloqueia tudo]
   │
   ├──► Fase A — Feature: pset_missing_generic_grounded     [bloqueia B]
   │
   ├──► Fase C — Modelo de estudo + Ground Truth (prédio)   [paralela à A; bloqueia B]
   │
   └──────────► Fase B — Experimento (B1 ablação + B2 benchmark)
                    │
                    └──► Fase D — Consolidação e redação
```

Estimativa: Fase 0 ≈ 1–2 sprints · A ≈ 1 sprint · C depende do retrabalho no Revit · B ≈ 1 sprint de engenharia + tempo de máquina. **~4–6 semanas em ritmo de IC.**

---

## 3. Fase 0 — Fundação experimental (atualizada ao estado real de 25/06)

> **Estado auditado:** quase nada da Fase 0 foi feito desde 09/06. Os arquivos `src/experiment/` continuam stubs de abril. As correções abaixo são pré-requisito de qualquer número do artigo.

### 0.1 `grounding_mode` FUNCIONAL (mudança vs. 09/06 — NÃO remover)
- Tipar `grounding_mode: Literal["none", "ids_only", "ids_bsdd"]` em `QualityPipeline.__init__`. Default `"ids_bsdd"`.
- **Fazer os 3 modos diferirem de verdade:**
  - `none` → prompt só com contexto IFC bruto (sem IDS, sem bSDD).
  - `ids_only` → injeta requisito IDS, **sem** vocabulário bSDD.
  - `ids_bsdd` → injeta IDS + candidatos/valores oficiais do bSDD.
- Corrigir **F13** (vazamento de IDS no modo `none`): `prepare_llm_grounding`/`generate_batch` só usam `ids_context`/`bsdd_context` conforme o modo.
- Remover do código atual o overwrite silencioso (`src/pipeline.py:81-83`). Manter `grounding_mode` no `AuditEntry` e nos exports.
- **Critérios:** os 3 modos produzem prompts mensuravelmente distintos (teste compara o texto do prompt por modo); nenhuma fonte de grounding vaza para `none`; `make test` verde.

### 0.2 IDs determinísticos (F3 — CRÍTICO)
- `Issue.id` (hoje `uuid4()[:8]` em `src/models.py:98`) → `sha1(f"{element_guid}|{issue_type}|{check_pset}|{check_property}")[:12]`, via factory/validator que recalcula quando os campos-chave existem (fallback: `check_property=""`).
- `OperationalRule.id` (hoje `uuid4()[:8]` em `src/models.py:561`) → `sha1(source_spec|filter_entity|check_pset|check_property|check_type|expected_value)[:12]`.
- **Critérios:** duas execuções de `diagnose()` no mesmo IFC produzem **IDs idênticos**; cache de sugestões passa a acertar entre execuções para issues IDS; teste de colisão.

### 0.3 Ground truth por chave natural + comparação normalizada + promover o Evaluator (F3, F10, F11)
- Promover o motor de avaliação de `tests/evaluation/evaluation_framework.py` → **`src/experiment/evaluator.py`** (produção não fica em `tests/`).
- `GroundTruth` v2: chave **`(element_guid, issue_type, check_property)`** (mantém compat por `issue_id` para testes legados); loader de arquivo versionável (**YAML**) com validação Pydantic; campo `accepted_alternatives: list` por item.
- Comparação **normalizada** no Evaluator: usar `normalize_value_for_issue` (`src/suggestion_engine/normalization.py:124`) nos dois lados; floats com tolerância relativa (default 2%); booleanos/strings com casefold/strip. Substitui o `str(x)==str(y)` atual.
- Formalizar definições de métricas (docstring + seção no relatório): top-1/top-3 sobre issues com GT; precisão/revocação/F1 com definição defensável (ou substituir por top-k + conformidade IDS — decisão a registrar).
- **Critérios:** GT de arquivo casa com issues entre execuções distintas; teste parametrizado de `2.5` vs `"2,50"` vs `"2.50 W/m²K"`, `True` vs `"true"` vs `"sim"`; documento de métricas existe.

### 0.4 Higiene do cache para multi-modelo (F4)
- Incluir `grounding_mode` na `compute_signature` (`src/suggestion_engine/suggestion_cache.py`).
- **Remover a chamada `invalidate_by_model` do `__init__` do pipeline** (`src/pipeline.py:114`) — ela apaga o cache dos outros modelos e inviabiliza o benchmark multi-modelo. Invalidação vira operação explícita (`make clean-cache`).
- Bypass de cache no modo experimento (réplicas de variância precisam de chamadas reais — flag por run; `suggestion_cache_enabled` já existe em `config.py`).
- **Critérios:** alternar modelos não apaga entradas de outros; assinatura muda quando `grounding_mode` muda; harness roda com e sem cache.

### 0.5 Reescrever `src/experiment/` como harness real (F2, F6, F12)
- `runner.py`: dado `(ifc_path, ids_path, ground_truth_path, model_name, grounding_mode | lista de modos, n_réplicas, cache on/off)` → `diagnose()` → gera sugestões (batch, grounding conforme modo) → avalia vs GT (Evaluator) → aplica **revisor simulado** → exporta JSON versionável.
- **Revisor simulado (proxy de decisão humana, F6):** top-1 casa GT (normalizado) → `accepted`; algo do top-3 casa → `edited`; nada casa → `rejected`; `review_required` sem match → `review`. **Sem escrever no IFC original** — conformidade IDS pós-correção medida aplicando as correções aceitas numa **cópia descartável** + `PostValidator`, rotulado como simulação.
- Instrumentar estabilidade (**F12**): adicionar a `SuggestionMetrics` (`src/models.py:183`) os campos `attempts: int`, `failure_reason: Literal["json_invalid","schema_invalid","empty","timeout","other"] | None`, `json_repaired: bool`.
- Metadados por run (F7): modelo + digest, versão do Ollama, seed, temperature, top_p, num_ctx, num_predict, hash SHA256 do IFC, hash do IDS, versão do prompt (`PROMPT_VERSION`), commit do repo, `grounding_mode`.
- `metrics.py`: `ExperimentResult` Pydantic agregando Evaluator + proxy + telemetria.
- **Critérios:** `python -m src.experiment.runner --help` funcional; run com Ollama **mockado** gera JSON com todas as métricas; teste de **hash do IFC antes/depois** prova que o revisor simulado não toca o arquivo original.

### 0.6 Correções menores
- F13 (já coberto em 0.1).
- F15 (denominador de `compute_readiness`) — só se readiness for citado no paper; senão, registrar como dívida.
- `Suggestion.source` e `AuditEntry.source` (hoje `Literal["llm"]`) → `Literal["llm", "deterministic"]` (pré-requisito da Fase A.3).

---

## 4. Fase A — Feature: `pset_missing` grounded (completar os ~20–30% restantes)

> **Estado auditado:** o caminho compacto (`build_compact_prompt` + `GroundedIssueContext` + roteamento `_should_use_compact`) já está **vivo**. Falta o template dedicado, o contexto rico do elemento e o prefill determinístico. `PROMPT_VERSION` ainda `v2`.

- **A.1** Template `pset_missing_generic_grounded` em `prompt_templates.py`: injeta vocabulário fechado bSDD (`allowed_values`, `data_type`, `unit`) + **contexto rico do elemento** (camadas de material, espessura total, `PredefinedType`, `IsExternal`, pavimento) + requisito IDS + contrato JSON com `review_required`. **Enriquecer `GroundedIssueContext`** (`src/suggestion_engine/grounding.py`) com `material_layers`, `thickness_m`, `predefined_type`, `is_external` (hoje ausentes). Bump `PROMPT_VERSION` → `v3`.
- **A.2** Roteamento: `pset_missing` sem template especializado **com** grounding → caminho grounded; **sem** grounding → template genérico endurecido com instrução de abstenção (`review_required=true`).
- **A.3** Pré-preenchimento determinístico (`source="deterministic"`) para booleanos deriváveis (`IsExternal` via análise de fronteira; `LoadBearing` quando inequívoco) — apresentado como sugestão, **sempre com aprovação humana**, nunca escrita automática. Lista fechada e conservadora, revisada com o orientador.
- **A.4** Testes (junto com o código): mocks de bSDD em 3 cenários (com `allowed_values` / só `data_type+unit` / vazio); sugestão fora do vocabulário rebaixada/descartada; prefill determinístico não chama Ollama; roteamento grounded vs fallback. Cobertura ≥ 80% nos módulos tocados.
- **Critérios:** 3 cenários end-to-end com mocks; nenhuma escrita sem aprovação; demo manual na UI com bSDD vivo.

---

## 5. Fase C — Modelo de estudo + Ground Truth (decisão do Felipe)

**Estratégia recomendada:** **prédio do Felipe (primário, GT-by-diff) + 1 IFC externo completo (complemento, masking).**

| Abordagem | Papel | Força | Fraqueza |
|---|---|---|---|
| Prédio do Felipe (GT-by-diff) | **Primário** | realismo (lacunas autênticas) + autoria | GT definido pelo autor → risco de circularidade (mitigado pelo guardrail) |
| IFC externo completo (masking) | **Complemento** | proveniência independente + massa estatística | precisa de fonte boa; nomes exigem `accepted_alternatives` |

### C.0 Guardrail anti-circularidade (obrigatório, declarar no método)
O GT é definido por **expertise do Felipe + norma (NBR 15575) + partes determinísticas do sistema** (detecção IDS, vocabulário bSDD). A **LLM sob avaliação nunca gera valores do GT.** Sem isso, a avaliação é viciada.

### C.1 Congelar a entrada
- Exportar o prédio "como está" (com lacunas) → `data/evaluation/predio/predio_v1.ifc`.
- `data/evaluation/predio/README.md` com **SHA256**, ferramenta/versão de exportação, data, e descrição do prédio.

### C.2 Protocolo GT-by-diff (primário)
1. Rodar `diagnose()` (com IDs determinísticos da 0.2) em `predio_v1.ifc` + `data/ids_templates/residencial_nbr15575.ids` → exportar issues com chave natural `(guid, issue_type, check_property)` para CSV de trabalho.
2. Felipe enriquece o prédio **corretamente** no Revit (preenche propriedades, nomeia espaços, classifica sistemas) — guiado pela norma e pelas partes determinísticas, **não** pela LLM avaliada → exporta `predio_gt.ifc`.
3. Novo `src/experiment/gt_extractor.py`: para cada issue da v1, busca em `predio_gt.ifc` (por `GlobalId`) o valor correto → gera `data/evaluation/predio/ground_truth.yaml` (`verified: false`).
4. Felipe **revisa** o YAML item a item (`verified: true`), adicionando `accepted_alternatives: [...]` onde múltiplos valores são corretos (essencial em nomeação de espaços).
5. Congelar `ground_truth.yaml` com hash + data + revisor no cabeçalho.

### C.3 Complemento por masking (recomendado)
- Obter 1 IFC externo completo e bem-feito (ex.: amostra pública buildingSMART, ou um projeto cedido).
- Novo `src/experiment/mask_extractor.py`: grava os valores verdadeiros, depois **remove/zera** propriedades/nomes/classificações alvo → `predio_ext_masked.ifc` (entrada) + `ground_truth_ext.yaml` (valores originais, **curados**).
- Bom para Pset/classificação; nomes exigem `accepted_alternatives`. Itens cujo "original" seja arbitrário/errado são **excluídos** do GT.

### C.4 Cobertura e estatística
- Meta: **≥ 30 issues por tarefa** somando os modelos. Registrar no README a distribuição por tarefa e severidade.
- **Critérios:** `ground_truth.yaml` versionado, 100% `verified`, casando com `diagnose()` em duas execuções; `gt_extractor`/`mask_extractor` com testes (fixtures IFC em memória); protocolo citável no artigo.

---

## 6. Fase B — Experimento (B1 ablação + B2 benchmark)

### B.0 Travar a matriz de modelos com `llmfit` → `src/experiment/results/models.lock.json`
*(Resultado da análise `llmfit` desta sessão é anexado abaixo na seção "Matriz de modelos travada".)*
- Validar cada modelo com **smoke test** (1 issue de cada tarefa) antes do run completo.
- Registrar nome, tag, digest, tamanho, quantização.

### B.1 Ablação de grounding (1 modelo fixo)
| Dimensão | Valores |
|---|---|
| Modelo | **1 fixo** (escolhido pela análise llmfit — melhor equilíbrio qualidade/velocidade; ou o default `qwen3.5:9b`) |
| Modos | `none` × `ids_only` × `ids_bsdd` |
| Tarefas | Pset · nomeação de espaços · classificação de sistemas |
| Réplicas | n = 3, cache off, seed fixo |
- **Hipótese H1:** `ids_bsdd` ≥ +20 p.p. de conformidade vs. `none`; edição ≤ 25% (vs. ≥ 40% em `none`); zero regressões de schema.

### B.2 Benchmark de famílias (grounding fixo `ids_bsdd`)
| Dimensão | Valores |
|---|---|
| Modelos | matriz travada por llmfit (Qwen · Llama · Mistral · Gemma/Phi — 1+/família; quantização Q4 documentada) |
| Tarefas | as 3 |
| Réplicas | n = 3, cache off, seed fixo |

### B.3 Métricas (todas viabilizadas pelas Fases 0/A)
- **Qualidade:** top-1/top-3, F1 (def. de 0.3), **conformidade IDS pós-correção** (PostValidator sobre cópia), por tarefa e agregado.
- **Estabilidade da saída estruturada:** % JSON válido na 1ª tentativa, nº médio de retries, taxa de reparo de truncamento, taxa de rejeição no parsing/validação (campos de 0.5).
- **Eficiência:** latência por sugestão (p50/p95), tokens/s (`eval_count/eval_duration` e `llmfit bench`), tempo de load do modelo.
- **Recursos:** VRAM/RAM por amostragem externa — `scripts/sample_resources.py` (`nvidia-smi … -l 1` + psutil), correlacionado por timestamp.
- **Proxy de revisão:** accepted/edited/rejected/review do revisor simulado (rotulado como proxy) + sessão com decisões humanas reais numa amostra (≥ 50 issues) para concordância proxy-vs-humano.

### B.4 Saídas
- `src/experiment/results/<data>/<modelo>/run_<n>.json` (versionados — pequenos).
- `src/experiment/report.py`: tabelas (pandas → markdown/LaTeX) + gráficos **Plotly** (barras por tarefa, dispersão qualidade × latência, radar por modelo).
- Script/notebook de reprodução ponta a ponta documentado no README do experimento.
- **Critérios:** run de 1 modelo em tempo viável (estimado no smoke test); 4 famílias versionadas; tabelas/figuras geradas por script (nenhum número manual); re-run do mesmo modelo/seed reproduz métricas dentro da variância; metadados completos por JSON.

---

## 7. Fase D — Consolidação e documentação

1. Atualizar `PROJECT_CONTEXT.md` (remover `rule_engine/`, refletir `translator/`, seção do experimento novo) — F9.
2. Registrar em `fase3.md` a mudança de desenho (ablação → **híbrido ablação+benchmark**) com justificativa, ou criar `docs/fase4-benchmark.md`.
3. Consolidar dualidade de nomes em `models.py` (F8) — PR mecânico, depois das fases experimentais.
4. Completar a lista de issue types no `CLAUDE.md` (9, não 4).
5. Relatório técnico versionado da release.

---

## 8. Riscos e pontos de decisão

1. **Confirmar com o orientador** o desenho híbrido (ablação + benchmark). É a decisão que mais afeta o plano — **antes da Fase 0**.
2. **VRAM 8 GB / RAM 16 GB:** 14B é lento (offload); Mixtral não cabe. Matriz validada por `llmfit` + smoke test.
3. **GT do prédio:** circularidade (guardrail C.0) e tamanho (≥ 30/tarefa → daí o modelo externo).
4. **Modelos citáveis:** fixar tags/digests oficiais; evitar fine-tunes custom.

---

## 9. Verificação (como testar de ponta a ponta)

- `make test` / `make lint` verdes ao fim de cada fase.
- 0.2: duas execuções de `diagnose()` no mesmo IFC → conjuntos de `Issue.id`/`OperationalRule.id` idênticos (teste).
- 0.1: prompts dos 3 modos são distintos e `none` não contém IDS/bSDD (teste).
- 0.5: `python -m src.experiment.runner --help`; run com Ollama mockado → JSON com todas as métricas; **hash do IFC antes == depois** (revisor simulado não toca o original).
- Fase A: 3 cenários de bSDD (mock) end-to-end; prefill determinístico não chama Ollama.
- Fase C: `gt_extractor` sobre fixtures IFC em memória; `ground_truth.yaml` casa com `diagnose()` em 2 execuções.
- Fase B: smoke test por modelo; `report.py` gera tabelas/figuras a partir dos JSON; re-run reproduz dentro da variância.
- Demo manual na UI (`make run-ui`) com bSDD vivo, fora dos testes.

---

## Matriz de modelos travada (análise `llmfit` de 25/06)

**Sistema detectado (`llmfit system`):** RTX 4060 Laptop **8 GB VRAM** (CUDA), **16 GB RAM** (apenas ~1.8 GB livres no instante da varredura), i7-13650HX (20 threads). Contexto de estimativa fixado em **8192 tokens** (= `num_ctx` do projeto).

**Leitura dos resultados:** todos os candidatos viáveis são **7–8B em 4-bit**, `fit_level: Perfect`, ~59–71% de uso da VRAM, ~37–41 tok/s estimados. A base do `llmfit` é orientada a **vLLM / AWQ / GPTQ (HuggingFace)** (`ollama_name: null`) — para o pipeline **Ollama**, mapeie cada família para o **GGUF Q4_K_M equivalente** (tamanho e velocidade comparáveis). O aviso "Insufficient VRAM and system RAM / Need X GB" reflete a **RAM livre no instante** (1.8 GB), não a VRAM — os modelos **cabem** na VRAM.

**Matriz recomendada (tags Ollama oficiais/citáveis):**

| Família | Tag Ollama | Params | VRAM Q4 | tok/s (est. llmfit) | Papel no experimento |
|---|---|---|---|---|---|
| Qwen | `qwen2.5:7b-instruct` | 7.6B | ~4.7 GB | ~39 | **Principal + modelo da ablação (B1).** Score 90.2, quality 77, tool use, ctx 32k |
| Qwen (JSON) | `qwen2.5-coder:7b` | 7.6B | ~4.7 GB | ~39 | Opcional: especialista em saída estruturada (score 91.1, quality 83) |
| Llama | `llama3.1:8b` | 8.0B | ~5.5 GB | ~37 | Representante Llama (score 89.7, quality 80, tool use) |
| Mistral | `mistral:7b` (v0.3) | 7.2B | ~5.1 GB | ~41 (mais rápido) | Representante Mistral (score 89.2, quality 73) |
| Gemma | `gemma2:9b` | 9B | ~5.4–6.5 GB | ~30 (confirmar) | Representante Gemma (confirmar fit via `llmfit info`/smoke) |
| Phi | `phi3.5` | 3.8B | ~2.5 GB | rápido | Modelo pequeno (piso de tamanho/velocidade) |
| Teto (lento) | `qwen3:14b` *(já instalado)* | 14B | ~9.3 GB (offload→RAM) | lento | Teto de qualidade; reportar latência maior |

**Ablação (B1):** modelo fixo = `qwen2.5:7b-instruct` (oficial, forte, reprodutível). Alternativa: o default atual `qwen3.5:9b`. Decidir após smoke test.

**A baixar (`ollama pull`):** `qwen2.5:7b-instruct`, `llama3.1:8b`, `mistral:7b`, `gemma2:9b`, `phi3.5` (+ opcional `qwen2.5-coder:7b`). Já instalados: `qwen3:14b`, `llama3:8b` (atualizar p/ `llama3.1:8b`).

**Próximos comandos `llmfit` no experimento:**
- `llmfit info <modelo>` → confirmar fit exato de `gemma2:9b` e `phi3.5`.
- Após `ollama pull` + smoke test: `llmfit bench` → **tok/s reais** contra o Ollama em execução (métrica de eficiência da Fase B).
- Congelar nome + tag + digest + quant + tamanho em `src/experiment/results/models.lock.json`.

**Cuidados de reprodutibilidade:** fixar digests via `ollama pull modelo:tag`; **evitar** fine-tunes custom (`gemma-4-12B fable5`) e a tag incomum `qwen3.5` como modelos do paper; fechar Revit/Chrome antes dos runs (RAM livre estava em 1.8 GB) para o KV cache e o offload do 14B terem folga; usar `cache_enabled=False` nas réplicas de variância.
