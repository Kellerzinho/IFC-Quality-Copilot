# Revisão Crítica — IFC Quality Copilot

**Data:** 2026-06-09
**Autor:** Sessão de revisão (Claude, eng. sênior + apoio de pesquisa)
**Escopo:** código-fonte em `src/`, `tests/`, documentação (`CLAUDE.md`, `PROJECT_CONTEXT.md`, `fase3.md`) e alinhamento com o eixo de pesquisa (grounding openBIM, alvo A ERA BIM / ENTAC-SBTIC).
**Método:** todos os achados abaixo foram confirmados por leitura direta do código antes de afirmados. Onde a suspeita original estava errada, isso está dito explicitamente.

> **Atualização (2026-06-26):** este é um registro datado. A decisão experimental posterior **abandonou a ablação de grounding** — os modos `none`/`ids_only` e o conceito `grounding_mode` foram **removidos do projeto**; o sistema sempre faz grounding IDS+bSDD. Onde os achados abaixo (F1, F4, F13) tratam `grounding_mode` como algo a tornar "funcional", leia como **resolvido por remoção**. Os números F1–F15 são preservados como referência histórica.

---

## 1. Pontos fortes (o que está bem-feito)

**Arquitetura de governança coerente com a tese.** O princípio "o LLM apenas sugere; só correções aprovadas são escritas" está de fato implementado, não só declarado: `apply_correction()` é o único caminho de escrita, exige `decision`, registra `AuditEntry` com proveniência (grounding_sources, bsdd_uri, ids_requirement_id, prompt_hash, post_validation) e dispara o gate do `PostValidator`. A cadeia issue → evidência → sugestão → decisão → escrita → validação descrita no `fase3.md` existe no código.

**Defesa em profundidade contra alucinação.** O parsing da resposta do LLM é defensivo em múltiplas camadas (`parse_llm_response`: parse direto → reparo de JSON truncado → regex → linha a linha; remoção de blocos `<think>` de modelos com raciocínio), `bsdd_uri` inventado pelo LLM é zerado em `_validate_suggestions`, e `_validate_against_bsdd` rebaixa confiança de valores fora do vocabulário. Isso é exatamente o "sandbox semântico" que o artigo promete.

**Grounding compacto bem desenhado.** `GroundedIssueContext` + `build_compact_prompt` é uma solução elegante: payload pequeno, candidatos oficiais como vocabulário fechado, contrato de saída com `review_required` e abstenção. A separação entre caminho compacto (com grounding) e templates legados é razoável.

**Telemetria já presente.** `SuggestionMetrics` captura tempos por fase (grounding, cache, LLM, parse, validação), tokens e status final — boa parte da instrumentação da Fase B (benchmark) já existe.

**Cache com assinatura rica.** A assinatura de cache inclui fingerprints de contexto por tipo de issue (camadas de material, espessura bucketed, elementos contidos), evitando reuso indevido entre elementos distintos — um problema sutil que o projeto já antecipou.

**Suíte de testes substancial.** 49 arquivos, ~635 funções de teste (717 com parametrização), com mocks para Ollama e bSDD conforme a convenção. O `Evaluator` em `tests/evaluation/` é um motor de avaliação real, com top-1/top-3, P/R/F1 e readiness antes/depois.

**Deduplicação e reuso.** `IssueDeduplicator` + `reuse_map` reduz chamadas LLM para issues equivalentes, com critério `is_safe_to_reuse` — relevante para custo e para consistência de respostas.

---

## 2. Achados confirmados (com severidade e impacto)

Legenda de impacto: **[A]** = impacto no artigo/pesquisa; **[P]** = impacto no produto.

### F1 — `grounding_mode` é parâmetro fantasma no pipeline ✅ CONFIRMADO

`src/pipeline.py:81-83`:

```python
if grounding_mode != "ids_bsdd":
    logger.info("Grounding '{}' ignorado: bSDD e IDS+bSDD sao obrigatorios.", grounding_mode)
self.grounding_mode = "ids_bsdd"
```

O parâmetro é aceito na assinatura, descartado silenciosamente (log INFO) e sobrescrito. O `ExperimentRunner` ainda itera `["none", "ids_only", "ids_bsdd"]` passando o modo — acreditando que controla a condição experimental — e o pipeline ignora. Resultado: qualquer "ablação" rodada hoje produziria três execuções idênticas rotuladas como condições diferentes. Isso seria um erro grave de validade interna se publicado.

**Contexto da nova direção:** segundo o autor, a ablação das 3 condições deixou de ser o experimento central — `ids_bsdd` passa a ser o padrão fixo e o experimento central vira o benchmark de modelos × 3 tarefas. O hardcode, portanto, coincide acidentalmente com a decisão científica nova, mas continua sendo um defeito: (a) a assinatura mente sobre o comportamento; (b) o runner está desalinhado e perigoso (geraria dados falsos); (c) `fase3.md` e a nota do artigo no Obsidian ainda descrevem a ablação como pendente — há três fontes de verdade divergentes.

**Recomendação:** decidir e tornar explícito. Se `ids_bsdd` é o padrão científico fixo: remover o parâmetro da assinatura (ou tipá-lo `Literal["ids_bsdd"]`), reescrever o runner para o benchmark de modelos, e atualizar `fase3.md` + nota do artigo. Manter código morto de ablação no runner é o pior dos mundos.

- **Severidade: ALTA [A]** (runner geraria dados experimentais inválidos) / **média [P]** (API enganosa).

### F2 — `src/experiment/` são stubs que não produzem as métricas do paper ✅ CONFIRMADO

`runner.py` (33 linhas): só instancia o pipeline e chama `diagnose()` — não gera sugestões, não compara com ground truth, não aplica correções, não coleta telemetria. `metrics.py` (27 linhas): conta `issue.status` (`accepted`/`edited`/`rejected`), que **nunca é setado** num run automático (só `apply_correction`/`skip_issue` setam status, e ambos exigem decisão) — logo `acceptance_rate` retorna sempre 0.0.

Nenhuma métrica prometida no artigo (top-1/3, P/R/F1, conformidade IDS pós-correção, estabilidade de JSON, latência, recursos) sai desses módulos. O motor real (`Evaluator`, em `tests/evaluation/`) não é usado pelo runner — e está em `tests/`, fora do pacote distribuível.

**Recomendação:** reescrever `src/experiment/` como harness de benchmark de verdade (ver plano consolidado, Fase 0.5 e Fase B), promovendo o `Evaluator` para `src/experiment/` ou importando-o formalmente.

- **Severidade: CRÍTICA [A]** (sem isso não há resultados para o artigo) / **baixa [P]**.

### F3 — IDs aleatórios quebram reprodutibilidade ✅ CONFIRMADO (e pior do que o suspeitado)

`src/models.py:98`: `Issue.id = uuid4()[:8]`. O `GroundTruth` do `Evaluator` é chaveado por `issue_id` (`corrections: dict[str, Any]`, lookup em `_compute_accuracy`). Consequência direta: um ground truth construído numa execução **não casa com nenhuma issue** da execução seguinte. Reprodutibilidade quebrada na raiz.

**Agravante encontrado:** `OperationalRule.id` (models.py:561) também é `uuid4()[:8]`. Esse `rule_id` entra: (a) no `IDSContext.requirement_id`; (b) na **assinatura de cache** (`compute_signature(..., requirement_id=...)`); (c) no `AuditEntry.ids_requirement_id`. Ou seja: a cada execução, as mesmas regras IDS ganham IDs novos → o cache de sugestões **nunca acerta entre execuções** para issues vindas de IDS (assinatura muda), e a auditoria não permite correlacionar requisito entre sessões.

**Recomendação:** IDs determinísticos por conteúdo:
- `Issue.id = sha1(element_guid + issue_type + check_pset + check_property)[:12]`
- `OperationalRule.id = sha1(source_spec + filter_entity + check_pset + check_property + check_type + expected_value)[:12]`

Além disso, o ground truth deve ser chaveado pela **chave natural** `(element_guid, issue_type, check_property)` — robusto mesmo se o algoritmo de ID mudar.

- **Severidade: CRÍTICA [A]** (GT não casa; cache inútil entre runs; variância artificial nos números) / **média [P]** (cache desperdiçado, auditoria menos correlacionável).

### F4 — Assinatura de cache não inclui `grounding_mode` ✅ CONFIRMADO (relevância reduzida pela nova direção; problema novo encontrado para a Fase B)

`SuggestionGenerator._compute_signature` deriva a assinatura do **conteúdo** do grounding (candidatos, constraints, expected_value...), mas não do **modo**. Dois modos que produzam payloads de grounding iguais (ex.: `none` vs `ids_only` numa issue sem IDS) colidem na mesma assinatura, com prompts potencialmente diferentes (`build_prompt` injeta `GROUNDING_MODE: {mode}` no texto). Com a ablação fora do escopo, o risco prático cai — mas se qualquer comparação entre modos voltar, é contaminação silenciosa de condições.

**Problema novo, mais relevante para a Fase B (benchmark de modelos):** `QualityPipeline.__init__` chama `suggestion_cache.invalidate_by_model(self._ollama_client.model)` — que **apaga as entradas de todos os outros modelos**. Num benchmark que alterna 4+ modelos, cada troca de modelo destrói o cache do anterior: re-execuções e réplicas ficam caras e a reprodutibilidade via cache se perde.

**Recomendação:** (a) incluir `grounding_mode` na assinatura (campo barato, elimina a classe de bug); (b) na Fase B, trocar `invalidate_by_model` por convivência multi-modelo (a assinatura já inclui `model_version`; a invalidação global por modelo é desnecessária e nociva ao benchmark).

- **Severidade: média [A]** (alta se houver comparação entre modos; a invalidação por modelo é **alta [A]** para a Fase B) / **baixa [P]**.

### F5 — `pset_missing_generic` é fraco ✅ CONFIRMADO (com nuance importante)

O template (`prompt_templates.py:166-178`) fornece apenas classe, nome, pset alvo e nome da propriedade — sem tipo de dado, sem unidade, sem valores permitidos, sem material/espessura/PredefinedType, sem instrução de abstenção. Pede "3 valores possíveis... considere o contexto construtivo brasileiro" — um convite à alucinação tipada errada.

**Nuance:** quando a issue tem grounding (IDS ou bSDD), `_should_use_compact` desvia para `build_compact_prompt`, que **já injeta** candidatos oficiais, tipo de dado e unidade. O template fraco é atingido quando: (a) não há grounding resolvido (bSDD offline/vazio e issue sem IDS); (b) o caminho legado via `PromptRouter` é usado. Mas mesmo o prompt compacto carece de **contexto rico do elemento** (material, espessura, PredefinedType, IsExternal) para propriedades genéricas — os fingerprints existem na assinatura de cache, mas não entram no prompt compacto.

**Recomendação:** é o alvo da Fase A — template `pset_missing_generic_grounded` + enriquecimento do caminho compacto. Ver plano consolidado.

- **Severidade: ALTA [A]** (a tarefa "preenchimento de Pset" é 1 das 3 tarefas do experimento; medir com prompt fraco subestima a abordagem) / **média [P]**.

### F6 — Métricas de aceitação/edição/rejeição sem decisão humana nem proxy ✅ CONFIRMADO

Num run automático, nenhuma issue muda de `pending`. O artigo promete taxas de aceitação/edição/rejeição e tempo de revisão; hoje não há nem coleta sistemática de decisões humanas (a UI registra na auditoria, mas não há protocolo de estudo), nem proxy automático definido.

**Recomendação (lacuna metodológica, decisão a registrar no plano):** definir um **revisor simulado** documentado: comparação normalizada da sugestão com o ground truth → top-1 casa = "accepted"; alguma do top-3 casa = "edited" (custo de edição ≈ escolher outra opção); nenhuma casa = "rejected"; `review_required=True` = "review". Reportar no paper como proxy, com validação por amostra de decisões humanas reais (Felipe + se possível um segundo avaliador, com concordância inter-avaliador). Sem isso, essas métricas devem sair do artigo.

- **Severidade: ALTA [A]** / **n/a [P]**.

### F7 — "Sem seed fixo" ❌ INCORRETO (havia suspeita, mas o código tem seed)

`src/config.py:34`: `ollama_seed: int | None = Field(default=42, ...)`, e `OllamaClient.generate` envia `options["seed"]` quando não-nulo. Portanto **há seed fixo (42) por padrão**, com `temperature=0.1`, `top_p=0.9`, `repeat_penalty=1.1`.

Ressalvas legítimas que permanecem para o paper:
- Seed no Ollama garante determinismo **apenas** para mesmo modelo (digest), mesma versão do Ollama, mesmo hardware/backend e mesmos parâmetros — isso precisa ser registrado nos metadados do experimento (hoje o export de métricas não grava seed, temperatura, num_ctx, versão do Ollama nem digest do modelo).
- O retry corretivo (`_build_retry_prompt`) muda o prompt entre tentativas — execuções podem divergir se a 1ª tentativa falha de modo não-determinístico (ex.: timeout).
- Recomendação para o artigo: fixar digests (`ollama pull` com tag exata), registrar metadados completos por run e rodar **n≥3 réplicas** reportando variância, em vez de assumir determinismo perfeito.

- **Severidade: baixa [A]** (afirmação original corrigida; resta trabalho de registro de metadados).

### F8 — Camadas de compatibilidade em `models.py` ✅ CONFIRMADO (é dualidade de nomes, não duplicação de classes)

Não há classes duplicadas; há **dupla nomenclatura mantida viva** via `AliasChoices` + propriedades-espelho: `IDSContext` (`spec_name`/`specification_name`, `expected_pset`/`check_pset`, `expected_unit`/`unit`, `requirement_description`/`requirement_text`...), `BSDDContext` (`related_properties`/`properties`, `classification_suggestions`/`classes`, `domain_name`/`domain`...), `ValidationResult` (errors/schema_errors/ids_errors com pós-processamento de consistência). Cada campo tem dois nomes válidos em todo o codebase — custo permanente de manutenção e fonte de confusão para colaboradores e para o LLM que gera código.

**Recomendação:** escolher a nomenclatura canônica (sugestão: a que os módulos novos usam — `check_pset`, `properties`, `classes`), migrar consumidores em um PR mecânico e remover aliases. Baixo risco com a suíte de testes atual. Prioridade abaixo das correções experimentais.

- **Severidade: baixa [A]** / **média [P]**.

### F9 — Deriva de documentação ✅ CONFIRMADO

`PROJECT_CONTEXT.md` referencia `src/rule_engine/` em 3 lugares (linhas 114, 161, seção 8 inteira na linha 332) — módulo descontinuado segundo o próprio `CLAUDE.md`. `docs/2026-04-17-estado-atual-projeto.md` também o cita como módulo ativo. Outras derivas menores: `CLAUDE.md` lista 4 issue types em "Referências Rápidas", mas `models.py` define 9; `fase3.md` descreve o experimento antigo (ablação) que a nova direção substituiu.

**Recomendação:** atualizar `PROJECT_CONTEXT.md` (remover rule_engine, refletir translator/), revisar `fase3.md` para o desenho experimental novo, completar a lista de issue types no `CLAUDE.md`.

- **Severidade: baixa [A]** / **média [P]** (documentos são consumidos por LLMs como contexto — deriva induz código errado).

---

## 3. Achados adicionais (não listados na suspeita original)

### F10 — Comparação do Evaluator com ground truth é frágil — **ALTA [A]**

`_compute_accuracy` compara `str(suggestion.value) == str(expected)` exato. Para `ThermalTransmittance`, `"2.5"` ≠ `"2.50"` ≠ `2.5` formatado de outro jeito; para booleanos, `"True"` ≠ `"true"` ≠ `"sim"`; para texto, sensível a caixa/acentos. Os números do paper ficariam artificialmente baixos e enviesados contra modelos que formatam diferente. Já existe `normalize_value_for_issue` no projeto — a comparação deve normalizar ambos os lados (com tolerância numérica relativa para floats).

### F11 — Definição de "precision" no Evaluator não é precision — **média [A]**

`precision = top1_hits / nº de issues com ≥1 sugestão` — isso é acurácia top-1 condicionada à geração, não precisão sobre sugestões. Para o paper, definir formalmente cada métrica (e alinhar com o que a literatura de enriquecimento semântico reporta) antes de gerar números, ou os revisores vão apontar.

### F12 — Estabilidade de saída estruturada está só parcialmente instrumentada — **média [A]**

Existem tempos e `final_status`, mas `SuggestionMetrics` não registra **nº de tentativas** (retries), motivo da falha (JSON inválido vs schema vs vazio) nem se houve reparo de JSON truncado. A Fase B promete "taxa de JSON válido, nº de retries, taxa de rejeição no parsing" — falta um campo `attempts: int` e um `failure_reason` enumerado (mudança pequena).

### F13 — Vazamento de IDS no modo "none" (latente) — **baixa [A]**

`generate_batch` repassa `ids_context` por issue e `prepare_llm_grounding` o utiliza **independente do `grounding_mode`** — se um dia a condição "none" voltar, o grounding IDS vazaria para o prompt compacto. Hoje é código morto (modo é sempre `ids_bsdd`), mas é uma armadilha para quem reativar a comparação.

### F14 — Não há modelo IFC de referência versionado nem GT no repositório — **ALTA [A]**

`tests/fixtures/` está vazio (fixtures são criadas em memória no conftest — correto para testes unitários) e `tests/evaluation/results/` está vazio. Não existe nenhum arquivo `.ifc` de estudo versionado/referenciado nem ground truth materializado. O benchmark precisa de: modelo congelado (hash registrado), GT versionado com chave natural, e protocolo de criação do GT. A CASA do projeto de arquitetura do autor é a candidata natural (ver plano, Fase C).

### F15 — `compute_readiness` mistura denominadores — **baixa [A][P]**

`total_checks = self._ids_rules_count + self.report.total_issues` soma regras (potenciais checks) com issues (falhas detectadas) — um denominador conceitualmente inconsistente que distorce o score percentual de readiness. Não bloqueia o experimento (readiness não é métrica central), mas vale corrigir se readiness for citado no paper.

---

## 4. Tabela-resumo

| # | Achado | Confirmação | Severidade artigo | Severidade produto |
|---|--------|-------------|-------------------|--------------------|
| F1 | grounding_mode fantasma + runner desalinhado | ✅ | **Alta** | Média |
| F2 | experiment/ stubs sem métricas reais | ✅ | **Crítica** | Baixa |
| F3 | Issue.id e OperationalRule.id aleatórios | ✅ (pior) | **Crítica** | Média |
| F4 | Cache sem grounding_mode + invalidação por modelo nociva ao benchmark | ✅ (+novo) | Média / **Alta (B)** | Baixa |
| F5 | pset_missing_generic fraco | ✅ (nuance) | **Alta** | Média |
| F6 | Aceitação/edição/rejeição sem decisão nem proxy | ✅ | **Alta** | n/a |
| F7 | "Sem seed" | ❌ incorreto (seed=42 existe) | Baixa | n/a |
| F8 | Dualidade de nomes em models.py | ✅ | Baixa | Média |
| F9 | Deriva de docs (rule_engine etc.) | ✅ | Baixa | Média |
| F10 | Comparação GT frágil (string exata) | novo | **Alta** | n/a |
| F11 | "Precision" mal definida | novo | Média | n/a |
| F12 | Retries/falhas de parsing não instrumentados | novo | Média | Baixa |
| F13 | Vazamento de IDS em modo none (latente) | novo | Baixa | Baixa |
| F14 | Sem IFC de referência nem GT versionados | novo | **Alta** | n/a |
| F15 | Denominador do readiness inconsistente | novo | Baixa | Baixa |

## 5. Síntese

O produto está maduro: governança, escrita defensiva, auditoria e parsing são de qualidade acima da média para um protótipo de pesquisa. O que está imaturo é exatamente a **camada experimental** — runner/metrics stubs, IDs não-determinísticos, GT inexistente, comparação frágil e proxy de decisão indefinido. Em outras palavras: o sistema está pronto para ser usado, mas ainda não está pronto para ser **medido**. O plano consolidado (`docs/plano-consolidado-2026-06-09.md`) ordena as correções para fechar essa lacuna antes da Fase A (feature) e da Fase B (benchmark).
