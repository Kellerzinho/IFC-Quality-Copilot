# Plano Consolidado de Desenvolvimento — IFC Quality Copilot

**Data:** 2026-06-09
**Base:** `docs/revisao-critica-2026-06-09.md` (achados F1–F15) + alinhamento com o segundo cérebro (nota-raiz do projeto, nota do artigo, decisão de eixo de pesquisa).
**Alvo de publicação:** 9º Congresso Internacional **A ERA BIM** (resumo já estruturado em `Artigo/`), com ENTAC/SBTIC 2027 como destino posterior do artigo completo. Orientador: Maj. Rafael Otranto.
**Decisão científica vigente (confirmar com orientador e registrar):** o experimento central **não é mais a ablação de 3 condições de grounding** — `ids_bsdd` é o padrão fixo do sistema. O experimento central passa a ser o **benchmark de famílias de LLMs locais** sob o mesmo arcabouço de grounding, em **3 tarefas** (preenchimento de Pset, nomeação de espaços, classificação de sistemas).

**Regra inviolável em todas as fases:** o IFC só é alterado após aprovação humana explícita (`aprovado_pelo_usuario == True`). Nenhuma tarefa abaixo propõe escrita automática sem revisão; o "revisor simulado" da Fase 0 opera sobre **cópias** do modelo, em ambiente de experimento, e isso será declarado no artigo.

---

## Visão geral do sequenciamento

```
Fase 0 — Fundação experimental (correções de base)        [bloqueia tudo]
   │
   ├──► Fase A — Feature: pset_missing_generic_grounded    [bloqueia B]
   │
   ├──► Fase C — Ground truth da CASA                      [paralela à A; bloqueia B]
   │
   └──────────► Fase B — Benchmark de LLMs locais          [depende de 0 + A + C]
                    │
                    └──► Fase D — Documentação, consolidação e redação
Extensão futura (fora de escopo): descoberta de propriedades via bSDD (opção 1)
```

---

## Fase 0 — Fundação experimental

Objetivo: tornar o sistema **mensurável e reprodutível**. Sem a Fase 0, qualquer número gerado nas fases A/B é inválido ou irrepetível.

### 0.1 Fixar `ids_bsdd` como padrão explícito e eliminar o parâmetro fantasma (F1)

- Remover o parâmetro `grounding_mode` da assinatura de `QualityPipeline.__init__` **ou** tipá-lo como `Literal["ids_bsdd"]` com docstring explicando a decisão científica (preferência: remover; menos superfície).
- Manter `grounding_mode` no `AuditEntry` e nos exports (proveniência continua registrando o modo).
- Remover do `ExperimentRunner` a iteração por modos (será reescrito em 0.5).
- Atualizar `fase3.md` com o novo desenho experimental (ou criar `docs/fase4-benchmark.md` e marcar `fase3.md` como histórico).

**Critérios de aceitação:** nenhum caminho do código aceita modo ≠ `ids_bsdd`; `grep -rn "ids_only\|\"none\"" src/` retorna apenas usos de proveniência/serialização documentados; testes que exercitavam modos alternativos ajustados; `make test` verde.

**Dependências:** nenhuma.

### 0.2 IDs determinísticos (F3)

- `Issue.id`: default passa a ser derivado — `sha1(f"{element_guid}|{issue_type}|{check_pset}|{check_property}")[:12]`. Como `context` é populado após a construção em alguns fluxos, implementar via factory/validator que recalcula quando os campos-chave existem, com fallback documentado para issues sem `check_property` (usar string vazia — a chave natural `(guid, type, "")` ainda é estável).
- `OperationalRule.id`: `sha1(f"{source_spec}|{filter_entity}|{check_pset}|{check_property}|{check_type}|{expected_value}")[:12]`.
- Garantir unicidade na prática: teste que roda `diagnose()` duas vezes no mesmo modelo e exige conjuntos de IDs idênticos; teste de colisão (duas issues distintas → IDs distintos).

**Critérios de aceitação:** duas execuções de `diagnose()` sobre o mesmo IFC produzem exatamente os mesmos `Issue.id` e `OperationalRule.id`; cache de sugestões passa a acertar entre execuções para issues IDS (teste de integração com cache em tmp_path); `make test` verde.

**Dependências:** nenhuma. **Bloqueia:** 0.3, 0.5, Fase C.

### 0.3 Ground truth por chave natural + comparação normalizada (F3, F10, F11)

- `GroundTruth` v2: chave `(element_guid, issue_type, check_property)` (mantendo compat com chave por `issue_id` para testes legados), com loader de arquivo versionável (YAML ou CSV) e validação Pydantic.
- Comparação normalizada no `Evaluator`: usar `normalize_value_for_issue` em ambos os lados; floats com tolerância relativa configurável (default 2%); booleanos e strings casefold/strip.
- Corrigir definições de métricas e documentá-las formalmente (docstring + seção no relatório do experimento): acurácia top-1/top-3 sobre issues com GT; precision/recall/F1 com definição defensável (ou removê-las em favor de top-k + conformidade IDS, decisão a registrar).
- Promover o motor de avaliação de `tests/evaluation/` para `src/experiment/evaluator.py` (o pacote `tests/` não deve conter código de produção).

**Critérios de aceitação:** GT carregado de arquivo casa com issues entre execuções distintas; teste parametrizado cobrindo `2.5` vs `"2,50"` vs `"2.50 W/m²K"`, `True` vs `"true"` vs `"sim"`; documento de definição de métricas existe; `make test` verde.

**Dependências:** 0.2.

### 0.4 Higiene do cache para o benchmark (F4)

- Incluir `grounding_mode` na assinatura (`compute_signature`) — barato e elimina a classe de bug.
- Remover/condicionar `invalidate_by_model` no `__init__` do pipeline: o cache passa a conviver com múltiplos modelos (a assinatura já inclui `model_version`); a invalidação vira operação explícita (`make clean-cache` ou flag).
- Adicionar política de bypass de cache para o modo experimento (réplicas de variância precisam de chamadas reais — flag `cache_enabled=False` por run, já suportada via settings; expor no harness).

**Critérios de aceitação:** alternar modelos no pipeline não apaga entradas de outros modelos (teste); assinatura muda quando `grounding_mode` muda (teste); harness consegue rodar com e sem cache.

**Dependências:** nenhuma (paralela a 0.2/0.3).

### 0.5 Reescrever `src/experiment/` como harness real (F2, F6, F12)

- `runner.py` novo: dado `(ifc_path, ids_path, ground_truth_path, model_name, n_réplicas, cache on/off)` → roda diagnose → gera sugestões (batch, com grounding ids_bsdd) → avalia contra GT (Evaluator) → aplica **revisor simulado** → exporta resultados JSON versionáveis.
- **Revisor simulado (proxy de decisão humana, F6):** top-1 casa com GT (comparação normalizada) → `accepted`; alguma do top-3 casa → `edited`; nenhuma casa → `rejected`; `review_required=True` sem match → `review`. Implementado **sem escrever no IFC** (decisões registradas em memória/relatório). Conformidade IDS pós-correção é medida aplicando as correções aceitas numa **cópia descartável** do modelo e rodando o `PostValidator` — claramente rotulado como simulação experimental, não fluxo de produção.
- Instrumentar estabilidade de saída (F12): `SuggestionMetrics.attempts: int`, `failure_reason: Literal["json_invalid","schema_invalid","empty","timeout","other"] | None`, flag `json_repaired: bool`.
- Registro de metadados por run (F7): modelo + digest, versão do Ollama, seed, temperature, top_p, num_ctx, num_predict, hash SHA256 do IFC, hash do IDS, versão do prompt, commit do repo.
- `metrics.py` novo: agrega Evaluator + proxy + telemetria em um `ExperimentResult` Pydantic serializável.

**Critérios de aceitação:** `python -m src.experiment.runner --help` funcional; run completo com Ollama mockado produz JSON com todas as métricas do paper; metadados completos presentes; testes com mocks (nunca Ollama/bSDD vivos); o caminho do revisor simulado comprovadamente não toca o arquivo IFC original (teste de hash antes/depois).

**Dependências:** 0.1, 0.2, 0.3, 0.4. **Bloqueia:** Fase B.

### 0.6 Correções menores de fundação

- F13: em `prepare_llm_grounding`/`generate_batch`, condicionar uso de `ids_context`/`bsdd_context` ao modo (defesa em profundidade, mesmo com modo fixo).
- F15: corrigir denominador de `compute_readiness` (total_checks = checks avaliados de fato) — apenas se readiness for citado no artigo; senão, registrar como dívida.

**Critérios de aceitação:** testes específicos; `make lint` e `make test` verdes.

---

## Fase A — Feature: sugestões de valor grounded para `pset_missing` genérico

**Escopo aprovado: somente a opção 2** (reforçar sugestões de valor para propriedades que o IDS aponta como ausentes). A opção 1 (descoberta de propriedades além do IDS) está documentada como extensão futura no fim deste plano e **não será implementada agora**.

### A.1 Template `pset_missing_generic_grounded`

Novo template em `prompt_templates.py` que injeta:

- **Vocabulário fechado do bSDD:** `allowed_values` da propriedade alvo (quando existirem), `data_type`, `unit` — com instrução explícita "escolha APENAS entre os valores permitidos".
- **Contexto rico do elemento:** classe IFC, `PredefinedType`, material (camadas + espessuras), espessura total, `IsExternal`, psets existentes, pavimento — os mesmos sinais que hoje só entram na assinatura de cache passam a entrar no prompt.
- **Requisito IDS:** pset.propriedade, check_type, valor/unidade esperados, severidade (via `IDSContext.as_prompt_block`).
- **Contrato de saída:** JSON com `suggested_value` tipado conforme `data_type`, `justification` ≤ 120 chars, `confidence`, `review_required`.

Comportamento por cenário:

| Cenário | Comportamento |
|---|---|
| bSDD traz allowed_values | vocabulário fechado; sugestão fora do vocabulário é descartada/rebaixada (já existe `_validate_against_bsdd`) |
| bSDD traz só data_type/unit | valor **tipado** + justificativa técnica; `review_required=true` se confiança ≠ alta |
| bSDD vazio/offline | template exige justificativa + `review_required=true` por padrão (abstenção preferível a chute) |

### A.2 Roteamento e integração

- `_select_template` / `_should_use_compact`: issues `pset_missing` sem template especializado (térmico, fogo, acústico...) e **com** grounding → caminho grounded novo; **sem** grounding → template genérico atual endurecido com instrução de abstenção (`review_required`).
- Enriquecer `GroundedIssueContext` com os campos de contexto do elemento (material, espessura, predefined_type, is_external) e propagá-los ao `build_compact_prompt` — beneficia também os templates especializados.
- `PROMPT_VERSION` bump (`v2` → `v3`) — invalida cache corretamente.

### A.3 Pré-preenchimento determinístico para casos triviais

- Para propriedades booleanas deriváveis do modelo (ex.: `IsExternal` quando o analyzer já computou `is_on_exterior`/`is_external` no contexto da issue): gerar **sugestão determinística** pré-computada (sem LLM), apresentada ao engenheiro como qualquer outra sugestão — **sempre com aprovação humana**, nunca escrita automática.
- Requer estender `Suggestion.source` de `Literal["llm"]` para `Literal["llm", "deterministic"]` (e `AuditEntry.source` idem) — mudança de modelo documentada; o `AuditEntry` já registra a origem, preservando a distinção na proveniência do artigo.
- Lista inicial de casos triviais: `IsExternal` (paredes/lajes com análise de fronteira), `LoadBearing` quando `ObjectType`/classe estrutural é inequívoco — lista fechada, conservadora, revisada com o orientador.

### A.4 Testes (junto com o código, conforme CLAUDE.md)

- Mocks de bSDD com allowed_values, só data_type, e vazio (3 cenários da tabela).
- Teste de que sugestão fora do vocabulário é rebaixada/descartada.
- Teste do pré-preenchimento determinístico (não chama Ollama; `source="deterministic"`).
- Teste de roteamento (`_select_template` grounded vs fallback).
- Cobertura ≥ 80% nos módulos tocados.

**Critérios de aceitação da Fase A:** os 3 cenários da tabela funcionam end-to-end com mocks; nenhuma escrita sem aprovação; `make test`/`make lint` verdes; demonstração manual na UI com um modelo real e bSDD vivo (fora de testes).

**Dependências:** Fase 0 (0.1–0.4). **Bloqueia:** Fase B (o benchmark mede a tarefa de Pset com o arcabouço novo).

---

## Fase C — Ground truth do modelo CASA (paralela à Fase A)

Objetivo: dataset de avaliação congelado e reprodutível usando o IFC da **CASA** (projeto de arquitetura "24405 - KELLER - CASA" do autor).

### C.1 Congelar o modelo de estudo

- Escolher a versão "como exportada" da CASA (a versão com lacunas reais — é ela que o pipeline deve enriquecer) e versioná-la em `data/evaluation/casa/casa_v1.ifc` (ou referência externa + hash, se o arquivo for grande/confidencial).
- Registrar SHA256, ferramenta/versão de exportação e data no `data/evaluation/casa/README.md`.

### C.2 Protocolo de criação do ground truth (recomendado: GT por diff de modelo enriquecido)

Em vez de preencher planilha manualmente do zero, o protocolo aproveita o fluxo natural do Felipe no Revit:

1. **Rodar `diagnose()`** (com IDs determinísticos da Fase 0.2) na CASA v1 + IDS escolhido (`residencial_nbr15575.ids` é o candidato natural) → exportar lista de issues com chave natural `(guid, issue_type, check_property)` para um CSV de trabalho.
2. **Felipe produz a CASA "completa"** no Revit: preenche corretamente as propriedades apontadas, nomeia espaços, classifica sistemas — a versão de referência de especialista. Exporta `casa_gt.ifc`.
3. **Script extrator de GT** (novo, `src/experiment/gt_extractor.py`): para cada issue da CASA v1, busca no `casa_gt.ifc` (por GlobalId) o valor correto da propriedade/nome/classificação → gera `ground_truth.yaml` automaticamente, com flag `verified: false`.
4. **Revisão humana do GT:** Felipe revisa o YAML (vira `verified: true` item a item) — esse passo é o "padrão-ouro de especialista" citável no artigo. Itens ambíguos ganham `accepted_alternatives: [...]` (lista de valores igualmente corretos — importante para nomeação de espaços, onde "Lavabo" e "Banheiro de serviço" podem ambos valer).
5. Congelar `ground_truth.yaml` com hash + data + revisor no cabeçalho.

Alternativa (se preferir não retrabalhar a CASA no Revit): preencher o YAML manualmente a partir do CSV do passo 1. Mais trabalhoso e menos auditável — o protocolo por diff é o recomendado.

### C.3 Cobertura e estatística mínima

- Meta: GT cobrindo as **3 tarefas** com tamanho suficiente por célula da análise (regra prática: ≥ 30 issues por tarefa; se a CASA não atingir em alguma tarefa, complementar com um segundo modelo aberto — ex.: um sample IFC público — para generalização e para rebater a crítica de modelo único).
- Registrar no README a distribuição de issues por tarefa e severidade.

**Critérios de aceitação:** `ground_truth.yaml` versionado, 100% `verified`, casando com `diagnose()` em duas execuções independentes; extractor com testes (fixtures IFC mínimas em memória); documento de protocolo citável no artigo.

**Dependências:** 0.2, 0.3. **Bloqueia:** Fase B.

---

## Fase B — Benchmark de LLMs locais (experimento do artigo)

Objetivo: rodar o **mesmo arcabouço** (grounding `ids_bsdd` + feature da Fase A) sobre 4 famílias de modelos e produzir as tabelas/gráficos do paper.

### B.1 Matriz experimental

| Dimensão | Valores |
|---|---|
| Famílias de modelos | **Qwen 2.5/3 (7–14B)** · **Llama 3.1/3.2 (8B)** · **Mistral 7B / Mixtral** · **Gemma 2 9B / Phi-3** (1 representante por família no mínimo; 2 onde a VRAM da RTX 4060 8GB permitir — quantizações Q4 documentadas) |
| Tarefas | preenchimento de Pset · nomeação de espaços · classificação de sistemas |
| Réplicas | n = 3 por (modelo × tarefa), cache desligado, seed fixo |
| Dataset | CASA v1 + GT da Fase C (+ modelo complementar, se adotado) |

Digests exatos fixados via `ollama pull modelo:tag` e registrados em `src/experiment/results/models.lock.json` (nome, tag, digest, tamanho, quantização). Atenção à restrição de hardware: Mixtral 8x7B não cabe em 8GB de VRAM — usar Mistral 7B e documentar; validar cada modelo com smoke test antes do run completo.

### B.2 Métricas por modelo (todas já viabilizadas pelas Fases 0/A)

- **Qualidade:** acurácia top-1/top-3, F1 (definição formalizada em 0.3), **conformidade IDS pós-correção** (PostValidator sobre cópia com correções aceitas pelo revisor simulado), por tarefa e agregado.
- **Estabilidade de saída estruturada:** taxa de JSON válido na 1ª tentativa, nº médio de retries, taxa de reparo de truncamento, taxa de rejeição no parsing/validação (campos novos de 0.5).
- **Eficiência:** latência por sugestão (p50/p95), tokens/s (eval_count/eval_duration), tempo de load do modelo.
- **Recursos:** VRAM/RAM por amostragem externa — script `scripts/sample_resources.py` (loop `nvidia-smi --query-gpu=memory.used --format=csv -l 1` + psutil), correlacionado por timestamp com os runs. Medição externa ao processo, como o plano original pede.
- **Proxy de revisão:** taxas accepted/edited/rejected/review do revisor simulado (rotuladas como proxy no paper) + sessão de validação com decisões humanas reais numa amostra (≥ 50 issues) para reportar concordância proxy-vs-humano.

### B.3 Saídas

- `src/experiment/results/<data>/<modelo>/run_<n>.json` versionados no git (são pequenos).
- `src/experiment/report.py`: gera tabelas (pandas → markdown/LaTeX) e gráficos **Plotly** prontos para o paper (barras por tarefa, dispersão qualidade × latência, radar por modelo).
- Notebook ou script de reprodução de ponta a ponta documentado no README do experimento — a "contribuição metodológica reprodutível" prometida no fase3.

**Critérios de aceitação:** run completo de 1 modelo em < tempo viável (estimar no smoke test); resultados das 4 famílias versionados; tabelas e figuras geradas por script (nenhum número manual); replicabilidade demonstrada (re-run do mesmo modelo/seed reproduz métricas dentro da variância reportada); todos os metadados de B.1 presentes em cada JSON.

**Dependências:** Fases 0, A e C completas.

---

## Fase D — Consolidação e documentação

1. Atualizar `PROJECT_CONTEXT.md` (remover `rule_engine/`, refletir arquitetura real, seção do experimento novo) — F9.
2. Revisar `fase3.md` → registrar a mudança de desenho experimental (ablação → benchmark sob grounding fixo) com justificativa, ou criar `docs/fase4-benchmark.md`.
3. Consolidar dualidade de nomes em `models.py` (F8) — PR mecânico, baixo risco, depois que as fases experimentais estabilizarem.
4. Completar issue types no `CLAUDE.md`.
5. Relatório técnico versionado da release (item já listado nas "Próximas ações" da nota do projeto no Obsidian).

**Dependências:** nenhuma rígida; itens 1–2 idealmente logo após a Fase 0 (evita deriva durante o desenvolvimento).

---

## Extensão futura (fora do escopo de implementação): descoberta de propriedades via bSDD (opção 1)

**Ideia:** hoje o sistema só sugere valores para propriedades que o **IDS exige**. A extensão inverte a direção: dada a classe bSDD resolvida para a entidade (ex.: parede externa → classe IFC/bSDD correspondente), recuperar o **conjunto completo de propriedades** que o dicionário associa à classe e propor o preenchimento das relevantes que o modelo não tem — enriquecimento "além do contrato" do IDS.

**Esboço de design (para quando for priorizada):**

- Novo issue_type `pset_discoverable` (severidade `low`, nunca bloqueante) gerado por um `DiscoveryAnalyzer` opcional, desligado por padrão (flag de perfil), para não inflar o diagnóstico.
- Fonte: `BSDDClient.get_class_properties(class_uri)` (já existe infraestrutura de cliente + cache); filtro por relevância (propriedades com allowed_values ou unidade definida primeiro; cap de N por elemento).
- Reuso integral do arcabouço da Fase A: mesmas regras de vocabulário fechado, tipagem, `review_required` e aprovação humana.
- Riscos a resolver antes de implementar: explosão de issues (um IfcWall pode ter dezenas de propriedades candidatas); utilidade prática vs ruído para o engenheiro (curadoria por perfil de uso — energia, fogo, FM); ausência de GT (não há como medir acurácia sem referência — provavelmente avaliada por estudo de utilidade com usuários, não por top-k).
- Valor para a pesquisa: é a ponte natural para um segundo artigo (enriquecimento orientado a caso de uso/gestão de ativos — linha do orientador).

---

## Riscos e pontos de decisão para o Felipe

1. **Confirmar com o orientador** a substituição formal da ablação pelo benchmark de modelos (a nota do artigo no Obsidian ainda diz "rodar a ablação das 3 condições" — atualizada nesta sessão com ressalva). Sem ablação, a evidência de que o grounding ajuda fica indireta — se o orientador quiser manter uma comparação mínima com/sem grounding, a Fase 0.1 muda (manter o modo configurável em vez de removê-lo). **Esta é a decisão que mais afeta o plano — tomar antes de iniciar a Fase 0.**
2. **VRAM (RTX 4060 8GB):** modelos 14B quantizados Q4 ficam no limite; Mixtral não cabe. O lock de modelos deve ser validado com smoke test antes de prometer a matriz no artigo.
3. **Tamanho do GT da CASA:** se < 30 issues/tarefa, decidir cedo se complementa com segundo modelo (afeta a Fase C).
4. **Tempo:** Fase 0 ≈ 1–2 sprints; A ≈ 1 sprint; C depende do retrabalho no Revit (estimar); B ≈ 1 sprint de engenharia + tempo de máquina. Total: ~4–6 semanas em ritmo de IC.
