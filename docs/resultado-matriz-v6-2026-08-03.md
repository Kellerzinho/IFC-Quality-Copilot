# Matriz v6 — resultado e atribuição por estrato (2026-08-03)

Run: `src/experiment/results/2026-08-02-benchmark-v6/`, commit `977b188`,
matriz top-10 × 2 datasets × 1 réplica, `--reuse-equivalent`, seed 42 / temp 0,1,
cache off. **20/20 estágios, 8,1 h, zero falhas.** Instrumento: prompt v6, GT com
a emenda EI/REI, `predio_v1_masked.ifc` regenerado.

Comparação **apples-to-apples**: o run v5 (2026-07-28) foi re-scorado sob a emenda
antes de comparar. Sem isso, o ganho da mudança de critério viraria crédito
indevido do prompt.

## 1. Matriz final

| modelo | prédio v5 | prédio v6 | Δ | mascarado v5 | mascarado v6 | Δ |
|---|---|---|---|---|---|---|
| gemma2:9b | 0,8016 | **0,7341** | −6,8 | 0,5854 | **0,5122** | −7,3 |
| qwen3.5:4b | 0,8390 | **0,6736** | −16,5 | 0,2561 | **0,3780** | +12,2 |
| qwen2.5:7b-instruct | 0,6430 | **0,6575** | +1,5 | 0,1951 | **0,1829** | −1,2 |
| llama3.1:8b | 0,7145 | **0,6473** | −6,7 | 0,4146 | **0,4756** | +6,1 |
| qwen3.5:9b | 0,5868 | **0,5805** | −0,6 | 0,3780 | **0,4024** | +2,4 |
| granite4:tiny-h | 0,3881 | **0,4246** | +3,7 | 0,4512 | **0,4024** | −4,9 |
| lfm2.5:8b | 0,3225 | **0,3386** | +1,6 | 0,2195 | **0,1098** | −11,0 |
| phi4-mini | 0,3386 | **0,2101** | −12,8 | 0,0976 | **0,1220** | +2,4 |
| falcon3:7b | 0,4018 | **0,1658** | −23,6 | 0,1098 | **0,0976** | −1,2 |
| mistral:7b | 0,1009 | **0,1170** | +1,6 | 0,3902 | **0,4268** | +3,7 |
| **média do efeito v6** | | | **−5,9** | | | **+0,1** |

Ranking v6 no prédio: gemma2:9b (0,7341) · qwen3.5:4b (0,6736) ·
qwen2.5:7b (0,6575) · llama3.1:8b (0,6473) · qwen3.5:9b (0,5805) · granite4
(0,4246) · lfm2.5 (0,3386) · phi4-mini (0,2101) · falcon3 (0,1658) · mistral
(0,1170). O qwen3.5:4b **perdeu a liderança** que tinha sob o v5 re-scorado.

## 2. O achado principal: evidência ajuda, procedimento atrapalha

O v6 mudou três coisas no mesmo commit. Separadas por estrato, elas têm sinais
opostos e magnitudes muito diferentes:

| estrato | o que o v6 mudou | efeito médio |
|---|---|---|
| **Category** | `IfcSpace.LongName` passou a chegar ao prompt (**evidência**) | **+31,2 pp** |
| FireRating | PROCEDIMENTO TRRF → letra → 3 hipóteses (**instrução**) | **−12,5 pp** |
| ThermalTransmittance | memória de cálculo obrigatória (**instrução**) | **−8,4 pp** |
| LoadBearing | nada | 0,0 |
| system_unclassified | nada | 0,0 |

> **Contexto que é evidência do arquivo melhora muito; contexto que é instrução
> de procedimento piora.** Em Category, 9 dos 10 modelos melhoraram, vários acima
> de +30 pp (falcon3 e lfm2.5 +50,6; qwen2.5 +48,1; mistral +37,7). Nos dois
> estratos onde o v6 acrescentou procedimento, a média é negativa e as piores
> quedas atingem justamente os modelos que iam bem.

Isso responde de forma quantificada à pergunta "vale investir em melhorar o
contexto": vale, quando o que falta é **evidência que o arquivo já tem e o
extrator não estava entregando**. Não vale — custa — quando é **instrução sobre
como raciocinar**.

## 3. Validação de determinismo (subproduto forte)

`LoadBearing` e `system_unclassified` deram **exatamente 0,0 de variação nos 10
modelos**, porque seus templates não mudaram no v6. São dois runs independentes,
separados por 5 dias e por 14 commits, em código reimportado — e as respostas
são idênticas até o quarto decimal, para todos os modelos. É evidência direta de
que o harness é determinístico (seed 42 / temp 0,1) e de que a comparação v5×v6
é controlada: o que mudou, mudou pelas causas declaradas.

## 4. Os dois colapsos a 0,000 em fogo

`falcon3:7b` e `phi4-mini` foram de 0,602 e 0,345 a **0,000**. Causa idêntica e
verificada nas primárias: **ambos perderam o estímulo do pilar**, que sozinho
vale 352 das 1020 issues do estrato (34,5%).

- **phi4-mini**: pilar (GT `R 60`, alternativa aceita `R 90`) respondia `R 90` no
  v5 — acerto legítimo pela regra de alternativas. No v6 respondeu `R 120`, fora
  da lista. Perdeu 352 issues numa única troca de duração.
- **falcon3**: perdeu os dois acertos que tinha. No pilar, saiu de `R 90` para
  **`EI 60`** — trocou o critério estrutural pelo de compartimentação, o que é
  claramente indefensável para um pilar. Na parede de alvenaria (262 issues),
  saiu de `EI 60` (aceito pela emenda) para `R 60`.

Ou seja, a instrução "TRRF → letra → hipóteses" fez os modelos fracos
**raciocinarem sobre a letra e inverterem a atribuição** — falcon3 chegou a
espelhar o erro, pondo `R` em vedação e `EI` em pilar. O v6 não os deixou apenas
mais errados na métrica: moveu-os de respostas defensáveis para indefensáveis.

Reforço da lição de unidade amostral: um estímulo (o pilar) responde por um terço
do estrato de fogo, e dois modelos inteiros colapsam por causa dele.

## 5. Leitura para o artigo

A leitura mais forte e mais honesta **não** é "v6 é melhor" nem "v6 é pior" — é
a assimetria medida entre os dois tipos de contexto, com a conclusão de que
**as duas mudanças precisavam ter sido medidas separadamente**, e só a
estratificação permitiu separá-las depois do fato. Isso é contribuição
metodológica, não desculpa.

Consequência prática já apontada em
`docs/achado-aritmetica-termica-2026-08-02.md`: a instrução de calcular deveria
ser substituída por uma **camada determinística que executa a conta** a partir
da estrutura que o LLM propõe. E a instrução de procedimento normativo (TRRF),
pelo que se vê aqui, provavelmente deveria sair — ou virar uma condição própria,
medida isolada, e não empacotada com correções de extração.

**Decisão em aberto (do autor):** reportar v5 e v6 como duas condições e discutir
a assimetria, ou montar um v7 que mantém a evidência (LongName, material do
telhado) e devolve os blocos de procedimento ao estado do v5. A segunda opção
custa outra rodada de ~8 h — e escolhê-la *depois* de ver estes números é o
mesmo movimento que custou os 13,6 pp da lição de ajuste ao gabarito. Se for
feita, tem de ser declarada como tal.

> **RESOLVIDA em 2026-08-04: as duas.** O v7 foi construído (mantendo a
> evidência, removendo o PROCEDIMENTO do fogo e trocando a cobrança de
> aritmética do térmico por memória estruturada + recomputação determinística) e
> está **declarado como escolhido depois de ver estes números** em
> `docs/condicao-v7-2026-08-04.md`. O relato passa a ser de **três condições de
> instrumento** (v5, v6, v7) mais a emenda de critério EI/REI — e a assimetria
> evidência × procedimento medida aqui continua sendo o achado; o v7 é a
> consequência de engenharia dela. Delta do v7 medido sem GPU: 59 dos 202
> estímulos mudam, só nos dois estratos-alvo. A rodada de coleta segue pendente.

## 6. Limites

- 1 réplica por estágio; a dispersão entre réplicas não foi medida neste run.
- n de inferência = 202 estímulos no prédio e 79 no mascarado, não 4720/82 issues.
  Sem poder para ranquear 10 modelos; a matriz compara perfis.
- Um prédio, um IDS, um autor. Validade externa é a fraqueza conhecida.
- ~~A emenda EI/REI ainda aguarda ratificação formal do autor~~ — **ratificada em
  2026-08-04** (`REVISAO_GT.md`, seção Emendas; escopo conferido: 429 itens de
  vedação não portante, hash `D08D2C74`).

## Método

`scratchpad/matriz_v5_v6.py` — re-scora o v5 sob a emenda, compara por estrato e
imprime a matriz. Fontes: `2026-07-28-benchmark-limpo/` (v5) e
`2026-08-02-benchmark-v6/` (v6), ambos com `run_0_issues.jsonl` por modelo.
