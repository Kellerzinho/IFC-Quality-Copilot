# Estudo do benchmark — estado do instrumento e o que falta (2026-08-05)

Auditoria feita a pedido do autor, com três perguntas: (1) o código está pronto
para escalar — novos modelos e outros hardwares? (2) o que já foi coletado e não
está sendo usado? (3) que dados novos deixariam o artigo mais forte?

Base: leitura de `src/experiment/` completo, `ollama_client.py`,
`scripts/run_benchmark.py`, `models.lock.json`, e os resultados das matrizes v6
(`2026-08-02-benchmark-v6`) e v7.2 (`2026-08-04-benchmark`).

---

## 1. O que já está no nível de artigo — e deve ser dito como força

O instrumento acumulou, em dois meses, um conjunto de propriedades que a maioria
dos benchmarks de LLM publicados **não tem**:

| propriedade | onde está |
|---|---|
| Metadados de reprodutibilidade por run: seed, temperatura, top_p, hashes de IFC/IDS/GT/cache bSDD, `prompt_version`, commit **capturado no import** (não no fim do run — bug real corrigido em 28/07) | `RunMetadata`, `runner.py` |
| Fila retomável por estágio, instância única, parada graciosa, descarga de VRAM entre modelos | `run_benchmark.py` |
| Resultado por issue em JSONL, com proveniência de grounding, marca de recomputação térmica e razão de falha | `per_issue.py` |
| Unidade amostral correta (estímulo, via `reused_from`) e teste pareado McNemar | `breakdown_estratos.py` |
| Controle de determinismo embutido: `space_unnamed` — 820 issues × 10 modelos, **zero diferenças** entre v6 e v7.2 | resultado v7.2 §5 |
| Varredura de vazamento de gabarito como prática por mudança de prompt + suíte `test_prompt_nao_vaza_gabarito` | smokes v7–v7.2 |
| IFC original nunca tocado (cópia descartável + verificação de invariante por hash no `finally`) | `runner.py` |
| Reuso de equivalentes (95,7% menos chamadas) com efeito nas métricas declarado | `run_single` docstring |
| Retry de transporte completo: timeout, conexão e agora 5xx (com o custo de uma primária perdida documentado: 262 cópias) | `ollama_client.py`, commit `b062210` |

Conclusão de altitude: **o instrumento não é o gargalo do artigo.** As lacunas
abaixo são reais, mas são incrementos sobre uma base sólida — nenhuma invalida o
que já foi medido.

---

## 2. Lacunas antes de escalar — em ordem de prioridade

### P0 — `model_digest` não é gravado no run (novos modelos)

`RunMetadata.model_digest` existe e está **sempre `None`** — conferido nos runs
v6 e v7.2. O `models.lock.json` tem os digests, mas nada garante que o modelo
que **rodou** é o que está no lock: um `ollama pull` no meio do experimento troca
o binário silenciosamente, e tags como `:latest` (`phi4-mini:latest`!) tornam
isso provável, não hipotético.

**Correção:** no início de cada estágio, consultar `ollama show`/`/api/show` e
gravar o digest real no metadata. Opcionalmente, **recusar o estágio** se o
digest divergir do lock — transforma o lock de referência citável em guarda
ativa. Custo: ~1 chamada HTTP por estágio.

### P0 — nenhum metadado de hardware no run (outros hardwares)

`RunMetadata` não registra GPU, VRAM, RAM, driver, CPU nem OS. Hoje é implícito
("a máquina do experimento"); no momento em que o mesmo benchmark rodar em duas
máquinas, **os JSONs ficam indistinguíveis** e a comparação inter-hardware fica
impossível de reconstruir a posteriori.

**Correção:** bloco `hardware` no metadata, coletado no início da fila:
`nvidia-smi --query-gpu=name,memory.total,driver_version` + `platform` +
RAM total. E, por estágio, o dado que a docstring do `_fit_num_ctx` mostra ser
o que decide o desempenho nesta classe de máquina: **fração do modelo na GPU**
(`/api/ps` → `size_vram / size`). Sem isso, latência entre máquinas mistura
"modelo mais lento" com "modelo transbordando para a CPU" — que é exatamente a
variável que o estudo multi-hardware quer separar.

### P1 — `num_ctx` gravado é o teto, não o usado

O metadata grava `num_ctx: 8192` (o teto da configuração), mas `_fit_num_ctx`
dimensiona a janela **por prompt** (2048 na maioria). Para reprodutibilidade
inter-hardware isso importa: a janela efetiva muda a pegada de VRAM, que muda o
offload, que muda a latência. **Correção:** registrar a distribuição de
`num_ctx` efetivos por run (ou ao menos min/máx/moda) na telemetria.

### P1 — o gate de viabilidade é hardcoded para um modelo

`GATED_MODELS = {"qwen3:14b"}`. Numa máquina mais fraca, outros modelos vão
precisar de gate; numa mais forte, nenhum precisa. **Correção:** sondar todo
modelo antes do primeiro estágio (a sondagem custa segundos, o estágio custa
uma hora) e gravar o resultado. O `scripts/fit_modelos.py` já mede fit de VRAM
com o prompt real — promovê-lo a etapa formal de pré-qualificação por máquina:
o fit vira artefato citável (`fit-<hostname>.json`) e o critério de inclusão
de modelo numa máquina fica objetivo e documentado.

### P2 — assimetrias menores do harness

- `ExperimentRunner.run()` (multi-réplica, CLI) não expõe `reuse_equivalent`
  nem `check_properties` — só `run_single` tem. Hoje inofensivo porque a fila
  chama `run_single` direto, mas é armadilha para quem usar a CLI.
- `timestamp` registra só a data (`2026-08-04`), não ISO-8601 com hora — o
  campo até documenta a intenção de ISO. Runs do mesmo dia em máquinas
  diferentes colidem.
- As duas falhas restantes de resposta vazia esgotam 3 tentativas com o mesmo
  prompt e temperatura ~0. Retry idêntico contra saída determinística tende a
  falhar identicamente. Não mexer agora (é comportamento medido do modelo),
  mas registrar: se a taxa subir em modelos novos, a mitigação honesta é
  documentar a falha como resultado, não maquiar com temperatura.

---

## 3. Dados já coletados e ainda não reportados

O harness coleta **três eixos inteiros** que nenhum doc de resultado usou ainda.
Estão nos JSONs de todas as matrizes, a custo zero:

### 3.1 Revisor simulado (eficiência operacional) — v7.2, `predio`

| modelo | aceito | editado | rejeitado | review | conformidade IDS pós-correção |
|---|---:|---:|---:|---:|---:|
| gemma2:9b | 0,820 | 0,178 | 0,003 | 0,000 | **0,913** |
| qwen3.5:9b | 0,746 | 0,251 | 0,000 | 0,003 | 0,913 |
| qwen3.5:4b | 0,638 | 0,174 | 0,175 | 0,013 | 0,893 |
| qwen2.5:7b-instruct | 0,588 | 0,340 | 0,007 | 0,066 | 0,906 |
| lfm2.5:8b | 0,563 | 0,152 | 0,100 | 0,185 | 0,756 |
| granite4:tiny-h | 0,557 | 0,201 | 0,228 | 0,014 | 0,885 |
| falcon3:7b | 0,546 | 0,347 | 0,101 | 0,007 | 0,796 |
| llama3.1:8b | 0,541 | 0,284 | 0,095 | 0,080 | 0,789 |
| mistral:7b | 0,542 | 0,102 | 0,140 | 0,216 | 0,729 |
| phi4-mini:latest | 0,443 | 0,280 | 0,025 | 0,253 | 0,759 |

Este é o eixo que conecta o benchmark à tese do projeto (humano no circuito):
"aceito" ≈ zero esforço do revisor, "editado" ≈ esforço de escolha, "rejeitado/
review" ≈ esforço pleno. A leitura `qwen2.5` (34% de edição — o revisor acha a
resposta certa no top-3, mas precisa procurá-la) contra `mistral` (21,6% de
review — o revisor fica sem apoio nenhum) quantifica **cargas de revisão
qualitativamente diferentes**, e isso hoje não aparece em lugar nenhum do
artigo. Rotular sempre como *revisor simulado* (deriva do GT, não de humanos).

### 3.2 Calibração da confiança declarada — um achado pronto

`confidence_top1` está em todo JSONL. Fração de respostas com confiança "alta"
no v7.2: gemma2 **100%**, qwen2.5 **100%**, granite4 **100%**, falcon3 99%,
phi4-mini 91%, llama3.1 92%, qwen3.5:9b 92%, lfm2.5 81%, qwen3.5:4b 72%,
mistral **14%**.

Ou seja: modelos com top-1 de 0,44 a 0,82 declaram "alta" quase sempre — **a
autoconfiança declarada não discrimina acerto** (com exceção interessante do
mistral, que é o menos confiante e não é o pior). Para um fluxo com humano no
circuito isso é um resultado central: **a confiança do LLM não serve como
critério de triagem de revisão**, e a alternativa (priorizar por severidade e
por estrato) é justamente o que o pipeline faz. Um gráfico de calibração
(confiança × acerto, por modelo) conta essa história inteira.

### 3.3 Telemetria fina de tempo

`SuggestionMetrics` separa `ollama_load_ms`, `prompt_eval_ms`, `eval_ms`,
`parse_ms`, `grounding_ms` por issue. Dá para derivar **tokens/s de geração**
por modelo (output_tokens ÷ eval_ms) — a métrica de eficiência que viaja entre
hardwares melhor que latência absoluta, porque isola a geração do load e do
prompt processing. Hoje só p50/p95 de latência total são reportados.

---

## 4. Coletas novas que fortaleceriam o artigo

Em ordem de custo-benefício:

1. **Réplicas 2 e 3 da matriz v7.2** (~25 h de GPU, zero código). Sem variância,
   as três quedas de top-1 do v7.2 não se distinguem de ruído e um revisor vai
   apontar isso. É a pendência mais barata com maior efeito na solidez.

2. **IC por bootstrap sobre estímulos** (barato: só análise). Reamostrar os
   estímulos com reposição e reportar IC 95% para top-1/top-3 por modelo. Com
   n=202 estímulos os ICs são honestos; nos estratos pequenos (fogo n=6) eles
   ficam largos — o que é exatamente o que se quer mostrar. Complementa o
   McNemar pareado que já existe.

3. **Ablação de grounding bSDD** (o harness já está pronto: `grounding_sources`
   e `bsdd_source_status` por issue existem desde f927425). Rodar a matriz — ou
   só 3 modelos representativos — com bSDD desligado responde "quanto o
   grounding paga?" com o mesmo instrumento. Era o plano da fase experimental
   (jun/26) e nenhuma condição mediu isso isoladamente ainda.

4. **Matriz multi-hardware** (depende dos P0 da §2). O desenho que mais rende
   por hora de máquina: 2–3 modelos âncora (gemma2:9b, qwen3.5:4b, granite4)
   × 3 máquinas (fraca/atual/forte), 1 réplica, mesmos hashes. Duas perguntas
   respondíveis: (a) **a qualidade é invariante ao hardware?** — deveria ser,
   com seed fixo; o controle `space_unnamed` verifica isso de graça, e uma
   divergência seria um achado por si só (determinismo de GPU não é garantido
   entre arquiteturas); (b) **como latência e viabilidade escalam com
   VRAM/offload?** — a curva que transforma "rodou na minha máquina" em
   recomendação de dimensionamento reprodutível.

5. **Consumo de energia por sugestão** (médio: um amostrador de
   `nvidia-smi --query-gpu=power.draw` durante a fila). J/sugestão por modelo
   junta com o eixo de viabilidade computacional e diferencia o artigo — quase
   nenhum benchmark local reporta isso. Na matriz multi-hardware, vira
   J/sugestão × classe de máquina.

6. **Validação humana em amostra** (caro, mas é o que mais eleva o artigo).
   O revisor simulado é um proxy declarado; um estudo pequeno e honesto —
   1 revisor real, ~50 issues estratificadas, medindo decisão e **tempo por
   decisão** — calibra o proxy (concordância humano × simulado) e entrega o
   "tempo médio de revisão" que a seção de métricas do CLAUDE.md promete e
   nenhum dado atual cobre.

7. **Novos modelos** (quando entrarem): o processo correto já existe em embrião
   — `fit_modelos.py` → smoke estratificado → `lock_models.py`. Formalizar como
   critério de inclusão documentado (fit 100% GPU na máquina de referência +
   JSON estável no smoke) e **congelar a matriz por hardware**. Com o P0 do
   digest resolvido, modelo novo = lock novo datado, sem risco de contaminar
   os resultados antigos.

---

## 5. Síntese

- **O código não é o gargalo.** As duas lacunas que precisam fechar **antes**
  de escalar são de registro, não de lógica: digest real do modelo e metadados
  de hardware por run. Ambas são pequenas.
- **Há três eixos de dados prontos e não usados** — revisor simulado,
  calibração de confiança e telemetria fina — que rendem seções de artigo sem
  nenhuma hora de GPU nova.
- **A sequência que eu recomendo:** réplicas 2–3 (já) → digest + hardware no
  metadata → ablação bSDD → matriz multi-hardware → energia → validação humana.
  Cada passo é independente e publicável por si.
