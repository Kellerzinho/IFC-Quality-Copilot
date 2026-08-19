# Ablação-bSDD — resultado e mecanismos (2026-08-19)

Rodada de 2026-08-18 (18h57–23h56 UTC) na **RTX 4070 12 GB** externa, release
`ifcqc-2026-08-18-801636831646`, run `54c4f307…`, zip
`dist/RESULTADO_IFCQC_20260818T185722Z_54c4f307….zip`. **20/20 estágios
validados, 0 inválidos, fila 4,44 h** (prevista 4h22 pela telemetria do par).
Identidade de execução única `95c7a5c3e520…`, `grounding_bsdd: false`.

Baseline: perna 4070 do par unificado v7.7 (2026-08-13, identidade
`5cab7c70…`), conforme §3 de `condicao-ablacao-bsdd-2026-08-18.md`. Comparação
pareada por `issue_id`, unidade primária = classe de equivalência (303 por
modelo), McNemar exato bicaudal; itens (4.983) como leitura ponderada
secundária — mesma régua do par e da escala-4070.

**Resultado em uma linha: o grounding bSDD, como o bSDD o entrega hoje para o
dicionário IFC 4.3, não compra acurácia — custa.** Remover o bloco melhora o
pool dos 10 modelos em +2,34 pp por classe (p=0,00022) e conserta o estrato
`relation_broken` (+50 pp), cujo colapso no par era **defeito de instrumento
induzido pelo próprio bloco bSDD**, não incapacidade dos modelos.

## 1. Validade — §6 e §7 da condição, tudo cumprido

- **Identidades**: única por braço e distintas entre braços (`5cab7c70…` on,
  `95c7a5c3…` off); `RunMetadata.grounding_bsdd` = ausente/None no on (artefato
  anterior ao campo) e `false` nos 20 estágios do off.
- **Invariantes idênticos nos 40 estágios**: prompt `751ec1679d46…` (v7.7),
  GT prédio `040c871f…` (4720/202) e casa `e72b344f…` (263/101), IFC/IDS shas,
  `num_ctx fixed 4096`, `num_predict 768`, seed 42, temp 0,1, top_p 0,9,
  repeat 1,1, réplica 1, cache off, reuso on, **Ollama 0.32.5 pinado nos
  dois**. GT do repo hoje == GT pinado nas duas rodadas.
- **Mesma máquina de fato**: RTX 4070 12 GB, driver 591.86 nas duas rodadas.
- **Tratamento é o que se diz**: `grounding_sources = ['bsdd']` +
  `bsdd_source_status: live` em **49.830/49.830** issues do braço on; `[]` +
  `None` em **49.830/49.830** do off. `has_official_candidates` False em 100%
  nos dois (a flag rastreia a propriedade pedida — ver §5 para a exceção que
  importa). `bsdd_cache_sha256` idêntico entre braços (`6d16d344…`).
- **População**: lock do par `c37c0a6f…`, 10/10 digests conferidos no
  `ollama-models.json` **e** no `model_digest` de cada estágio; digests
  idênticos entre braços (mesmos blobs físicos).
- **Comparador**: 0 divergências entre veredito armazenado e recomputado nos
  99.660 vereditos dos dois braços. Representantes idênticos entre braços nos
  10 modelos.
- **Roteamento inalterado (§4.5)**: verificação sem GPU já cobria o prédio
  (202/202 template base idêntico); refeita hoje para a casa com o mesmo
  espião: **101/101 prompts mudados, delta confinado ao bloco `BSDD_CONTEXT` +
  instrução de grounding do system** — nenhum estímulo trocou de família de
  template em nenhum dataset.

## 2. Resultado principal

Pool dos 10 modelos, pareado por classe (delta = off − on):

| nível | n | só on | só off | Δ | p (McNemar exato) |
|---|---|---|---|---|---|
| **classes top-1** | 3.030 | 145 | 216 | **+2,34 pp** | **0,00022** |
| classes top-1 **sem** `relation_broken` | 2.990 | 145 | 196 | +1,71 pp | 0,0067 |
| classes top-3 | 3.030 | — | — | +1,49 pp | 0,0076 |
| itens top-1 | 49.830 | — | — | +2,66 pp | <1e-6 |

Replica nos dois datasets: casa +2,57 pp (p=0,046), prédio +2,23 pp
(p=0,0019). **H1 confirmada em módulo (|Δ| < 5 pp) — mas com o sinal
invertido em relação à leitura ingênua**: o resultado não é "o bSDD ajuda
pouco", é "o bSDD atrapalha um pouco, de forma estatisticamente sólida", e o
efeito não desaparece quando se retira a armadilha da relação (§5).

Por modelo (classes top-1; p de McNemar exato; Bonferroni×10 = 0,005):

| modelo | on | off | só on / só off | Δ pp | p |
|---|---|---|---|---|---|
| gemma2:9b | 0,6634 | 0,7360 | **0 / 22** | **+7,26** | **4,8e-7** |
| qwen3.5:4b | 0,6271 | 0,6832 | 11 / 28 | +5,61 | 0,0095 |
| lfm2.5:8b | 0,4851 | 0,5314 | 24 / 38 | +4,62 | 0,098 |
| phi4-mini | 0,4224 | 0,4521 | 20 / 29 | +2,97 | 0,25 |
| qwen2.5:7b | 0,5248 | 0,5545 | 15 / 24 | +2,97 | 0,20 |
| qwen3.5:9b | 0,7030 | 0,7162 | 16 / 20 | +1,32 | 0,62 |
| llama3.1:8b | 0,6271 | 0,6370 | 6 / 9 | +0,99 | 0,61 |
| granite4:tiny-h | 0,6568 | 0,6601 | 17 / 18 | +0,33 | 1,0 |
| falcon3:7b | 0,6370 | 0,6370 | 9 / 9 | 0,00 | 1,0 |
| mistral:7b | 0,7063 | 0,6799 | 27 / 19 | −2,64 | 0,30 |

Só o gemma2 sobrevive a Bonferroni — e de forma extraordinária: **22 classes
ganhas, zero perdidas**. O único modelo com saldo negativo em classes é o
mistral (n.s.), que ao mesmo tempo dá o maior salto em **itens**: +14,91 pp
(0,7032 → 0,8523), porque os ganhos caem em classes gigantes — o pilar de
fogo de 352 itens (`R 30` → `REI 60`, dentro da banda) e duas classes de
`IsLoadBearing` com 262 e 167 itens (`True` → `False`, gabarito False) — e as
27 perdas somam 103 itens. Em itens: mistral +14,91, qwen3.5:4b +8,81,
qwen2.5 +3,71, qwen3.5:9b +1,40, gemma2 +1,34, llama +1,15; negativos
falcon −0,30, granite −0,56, lfm −0,78, phi4-mini −3,09 (perde duas classes
térmicas de 222 e 107 itens para chutes redondos "2.0").

Máximos por métrica (contrafactual; **o instrumento oficial segue o v7.7 com
bSDD**): item mistral 0,8523 (on: gemma2 0,8216) · classe gemma2 0,7360 (on:
mistral 0,7063) · top-3 item llama3.1 0,9695 (on: qwen3.5:9b 0,9430). **As
três métricas têm máximo maior no braço sem bSDD.** No top-3 por classe, o
ganho significativo é do qwen2.5 (+4,95 pp, p=0,0041).

## 3. Hipóteses pré-registradas (§4 da condição) × observado

| # | hipótese | veredito |
|---|---|---|
| 1 | efeito agregado pequeno, \|Δ\| < 5 pp | **confirmada** (+2,34 pp) — e direcional contra o bSDD |
| 2 | `system_unclassified` com maior chance de efeito **positivo** do bSDD | **refutada**: +1,67 pp a favor do off (n.s., p=0,40) |
| 3 | fogo/acústica/térmica mudam pouco | **refutada para fogo**: +4,93 pp off (p=0,0051); acústica +2,50 n.s.; térmica +0,60 n.s. |
| 4 | menores mais sensíveis à remoção da âncora | **refutada na forma**: o maior efeito é do gemma2:9b, o líder; e o sinal é o oposto do previsto (remoção **ajuda**) |
| 5 | sem mudança de roteamento (condição de validade) | **cumprida** (202/202 prédio + 101/101 casa) |

Pool por estrato (classes top-1; só on / só off; itens quando divergem):

| estrato | n cls | on | off | b/c | Δ pp | p |
|---|---|---|---|---|---|---|
| relation_broken | 40 | 0,375 | 0,875 | 0/20 | **+50,0** | **2e-6** |
| FireRating | 690 | 0,6551 | 0,7043 | 53/87 | **+4,93** | **0,0051** |
| IsLoadBearing | 80 | 0,875 | 0,925 | 1/5 | +5,00 | 0,22 (itens +8,95, p<1e-6) |
| HasNonSkidSurface | 10 | 0,10 | 0,30 | 0/2 | +20,0 | 0,50 |
| SolarHeatGainCoefficient | 120 | 0,1667 | 0,2083 | 2/7 | +4,17 | 0,18 |
| AcousticRating | 320 | 0,6656 | 0,6906 | 9/17 | +2,50 | 0,17 |
| system_unclassified | 300 | 0,5533 | 0,5700 | 9/14 | +1,67 | 0,40 |
| ThermalTransmittance | 500 | 0,3540 | 0,3600 | 35/38 | +0,60 | 0,82 (itens **−3,26**, p<1e-6) |
| LoadBearing | 20 | 0,75 | 0,75 | 1/1 | 0,00 | 1,0 |
| Category | 950 | 0,7421 | 0,7316 | 35/25 | **−1,05** | 0,245 |

`Category` é o **único** estrato onde o bSDD aparece a favor — e não é
significativo. É também o estrato onde o bloco chega a dizer, textualmente,
"Propriedade pedida: ausente do dicionário IFC 4.3 […] Não há vocabulário
oficial a seguir aqui" — o benefício, se existe, é a âncora da definição de
`IfcSpace`. A térmica tem sinais opostos por nível: classes estáveis, itens
−3,26 pp porque phi4-mini troca duas classes grandes por chutes redondos e o
qwen3.5:4b passa a abster na classe de 107 itens (`3.2023` → vazio).

## 4. Piso de ruído: o efeito excede a instabilidade própria de cada modelo?

O par v7.7 dá, de graça, o piso de ruído por modelo: discordância em classes
entre as duas pernas do braço **on** (4070×4060, só a GPU muda) contra a
discordância da ablação (mesma 4070, só o bloco muda):

| modelo | cross-GPU b+c (b,c) | ablação b+c (só on, só off) | leitura |
|---|---|---|---|
| gemma2:9b | 1 (0,1) | 22 (0,22) | 22× o piso, 100% direcional — **efeito real** |
| llama3.1:8b | 7 (3,4) | 15 (6,9) | 2× o piso, assimetria fraca |
| falcon3:7b | 16 (10,6) | 18 (9,9) | dentro do piso |
| qwen3.5:4b | 22 (12,10) | 39 (11,28) | 1,8× o piso, assimétrico |
| qwen2.5:7b | 23 (13,10) | 39 (15,24) | 1,7× o piso, assimétrico |
| granite4 | 23 (10,13) | 35 (17,18) | simétrico — ruído |
| mistral:7b | 26 (16,10) | 46 (27,19) | 1,8× o piso, simétrico em classes (o sinal está nos itens) |
| qwen3.5:9b | 27 (17,10) | 36 (16,20) | ~piso |
| phi4-mini | 31 (11,20) | 49 (20,29) | 1,6× o piso |
| lfm2.5:8b | 44 (31,13) | 62 (24,38) | o próprio ruído domina — não interpretar |

A discordância cross-GPU é aproximadamente simétrica (ruído); a da ablação é
assimétrica na direção do off — exatamente a assinatura que o McNemar
pareado captura. Para lfm2.5 e granite, qualquer leitura individual é
indevida; o pool e o gemma2 carregam o resultado.

## 5. Mecanismo 1 — o bloco sem escopo: truncamento que engole a tarefa

O colapso de `IfcRelFillsElement` no par (0,00 em 20/20 estágios, "defeito
declarado, n=2 uniforme") **era o bloco bSDD**. Cadeia completa, medida:

1. `relation_broken` não tem `check_property` → o `context_builder` não tem
   propriedade para escopar → o bloco vira **o catálogo inteiro de
   propriedades do `IfcDoor` no IFC 4.3: 42,5 KB** (o bloco mediano da casa
   tem 434 chars; média 1.233; máx 42.473 — só as duas portas).
2. O prompt on dessas duas issues fica com **44,8 KB ≈ 20,7 mil tokens pela
   estimativa do cliente** (2,5 chars/token, margem 1,10, +768 de resposta).
   A guarda anti-truncamento sobe a janela — mas tem teto
   `max(fixa, ollama_num_ctx)` = **8192**. Os únicos 20 usos de 8192 em toda
   a rodada on são exatamente estes 2 estímulos × 10 modelos; no off,
   49.830/49.830 chamadas em 4096.
3. Com necessário ≫ teto, **o servidor trunca o início do prompt**. A tarefa
   e a evidência ocupam os chars 0–1.850; o corte cai por volta do char
   26.000, dentro do bloco. **O modelo nunca viu a pergunta** — viu o rabo de
   um catálogo de propriedades, o critério e as REGRAS DE SAIDA.
4. O que sobrou visível contém a única enumeração fechada que o bSDD entregou
   no experimento inteiro: `Process Item: BARREL, CGT, NOTKNOWN, OTHER,
   PASSENGER, TEU, TONNE, UNSET, VEHICLE` (URI `…/prop/ProcessItem` — IFC 4.3
   herdou propriedades de logística/infraestrutura) e `Operation Type: GRILL,
   LOUVER, SCREEN, OTHER, NOTKNOWN…`. E o system prompt do braço on instrui:
   *"Se houver contexto IDS ou bSDD, use apenas o vocabulário e os requisitos
   fornecidos."*
5. Resultado: os modelos **obedeceram**. gemma2 respondeu `BARREL, CGT,
   NOTKNOWN`; phi4-mini `TEU, TONNE, PASSENGER`; qwen3.5:9b `PASSENGER`;
   qwen3.5:4b `BARREL`; granite copiou o exemplo das regras ("Exemplo de Nome
   do Elemento"); falcon respondeu materiais; mistral, um nome de propriedade
   de amianto do catálogo. Não é alucinação: é instrução cumprida sobre um
   contexto que não continha a resposta.
6. **Sem o bloco, o prompt tem 2,5 KB e 8/10 modelos respondem
   `IfcRelFillsElement` em 1º** (fills: 0/20 on → 16/20 off; lfm2.5 erra os
   2, phi4-mini 1, qwen3.5:9b põe a resposta certa em 2º — top-3 acerta).

No space boundary (bloco de `IfcProject`, 5 KB, **sem truncamento**), o efeito
existe e é mais sutil: com o bloco, lfm2.5, llama3.1 e mistral põem
`IfcRelContainedInSpatialStructure` em 1º e `IfcRelSpaceBoundary` em 2º; sem
o bloco, invertem (boundary: 15/20 on → 19/20 off). Ancoragem semântica pela
definição oficial, não truncamento.

A ironia registrada: a §2 da condição previa efeito pequeno porque
`allowed_values` é nulo nas propriedades **medidas** — e é verdade. O único
lugar onde o bSDD entregou vocabulário fechado foi num estrato onde ele é
**distrator**, e o experimento é o flagrante de que grounding não-escopado
com instrução de obediência é pior do que nenhum grounding.

## 6. Mecanismo 2 — ancoragem conservadora onde o prompt cabe

Fora da relação, nada trunca (bloco mediano de 434 chars) — o efeito é de
conteúdo/instrução, menor e concentrado em fogo e função portante:

- **FireRating (+4,93 pp, p=0,0051)**: os 22 ganhos do gemma2 incluem **13
  classes de fogo com o mesmo padrão**: on responde `EI 30` (abaixo da banda
  aceita) e off responde `EI 60`/`REI 60` (dentro). O mesmo padrão aparece em
  qwen3.5:4b (`R 60`→`REI 60` no pilar de 107 itens; `REI 30`→`REI 60`) e
  phi4-mini (`EI 30`→`EI 60`, 107 itens). As perdas de fogo do mistral são o
  espelho (REI 90→REI 30 em classes pequenas). llama3.1 é imune: `REI 120`
  em 40/40 classes do prédio nos dois braços.
- **IsLoadBearing (itens +8,95 pp, p<1e-6)**: `True`→`False` (gabarito False)
  em classes de 262/167/17/8 itens para mistral, qwen3.5:4b e gemma2.
- Interpretação (marcada como hipótese, não como medição): a instrução "use
  apenas o vocabulário fornecido" sobre um bloco que **não traz valor de
  desempenho** encolhe a resposta para o literal/conservador — o rating
  mínimo que o template menciona, o `True` sugerido pela definição de parede.
  O que está **medido** é o padrão das respostas; a via causal exata exigiria
  sub-braços (p.ex. bloco sem instrução).

Efeitos colaterais mensuráveis do bloco sobre o comportamento declarativo:

- **Confiança**: sem bSDD, llama3.1 passa a declarar `alta` em 99,9% (era
  95,5%; as 223 issues térmicas com `baixa` desaparecem), falcon 86→92,5%,
  qwen3.5:4b 57→69%. O bloco funcionava como **sinal de cautela** para parte
  dos modelos.
- **Erro silencioso** (errado + confiança alta, % dos itens): melhora onde a
  acurácia sobe (mistral 13,1→6,4; gemma2 12,3→8,8; qwen3.5:4b 9,8→7,3) e
  **piora** em llama (20,7→24,0), falcon (25,6→30,4) e phi4 (31,7→33,4) — e o
  erro *sinalizado* despenca (llama 4,5%→0,02%). Para o fluxo com revisão
  humana, remover o bSDD deixa alguns modelos mais certos, porém **mais
  silenciosamente errados quando erram**.
- **Abstenção**: 87 → 152 itens (qwen3.5:4b 61→125, concentrada em térmica).

## 7. O que o bSDD custa em recursos: nada — e é isso que fecha o argumento

Fila 4,35 h (on) → 4,44 h (off); latência p50 por modelo variando de −4,7% a
+5,6% sem direção sistemática; tokens de saída estáveis. O bloco mediano é
pequeno demais para custar tempo — e grande demais nos dois estímulos errados.
O custo do bSDD não é computacional: é **os 2,34 pp de acurácia** e o estrato
quebrado. (E o benefício de latência de removê-lo também é nulo — ninguém
deve remover bSDD "para acelerar".)

## 8. O que muda no artigo

1. **Terceiro eixo fecha com resultado forte**: modelo (par v7.7), escala
   (escala-4070) e agora **grounding**. A decomposição das camadas do prompt
   fica: evidência do arquivo **+31,2 pp** (masking, matriz v6) · contexto
   bSDD **−2,34 pp** (esta rodada) · camada normativa dos templates — ainda
   não medida (extensão §8 da condição, agora com prioridade alta, porque é
   onde o conhecimento normativo realmente está).
2. **Achado publicável para a comunidade openBIM**, nos termos declarados
   antes da medição (§2 da condição): no estado atual do dicionário IFC 4.3
   (sem valores de desempenho, propriedades `IfcLabel` "livres", nenhum
   dicionário ABNT), injetar o contexto bSDD no prompt **não melhora** a
   sugestão semântica — e o modo de falha específico (bloco não-escopado →
   truncamento → resposta colhida do próprio bloco) é um alerta concreto de
   engenharia de grounding, não uma crítica ao bSDD em si. A auditoria de
   18/08 mostra o caminho para o bloco voltar a ter valor: dicionários com
   `allowedValues` de desempenho (precedente ACCA), que hoje não existem
   para as normas brasileiras.
3. **Correção de narrativa do par**: o 0,00 uniforme de `IfcRelFillsElement`
   deixa de ser "defeito declarado de contrato" e ganha causa medida — os
   modelos **sabem** a relação (8/10 acertam sem o bloco). O resultado
   oficial do par não muda; a nota de rodapé muda de "limitação do
   instrumento" para "efeito do tratamento bSDD, quantificado na ablação".
4. **A estabilidade cross-GPU vira régua de inferência** (§4): usar a
   discordância entre pernas do par como piso de ruído por modelo é um método
   que o artigo pode exibir — e que separa o efeito real (gemma2, 22× o
   piso, unidirecional) do não-interpretável (lfm2.5).
5. **Recomendações práticas** (seção de engenharia): escopar o bloco bSDD por
   `check_property` também na ausência de propriedade (ou suprimi-lo em
   `relation_broken`), impor teto de tamanho ao bloco, e não emitir a
   instrução "use apenas o vocabulário fornecido" quando o contexto não
   contém vocabulário da resposta. Nenhuma dessas mudanças entra no
   instrumento v7.7 — são trabalho futuro/apêndice.

## 9. Limitações declaradas

- 1 réplica por braço (padrão das rodadas oficiais); a baseline não foi
  re-rodada (desenho §3) — mesma máquina e driver, 5 dias de distância.
- Só o pool e o gemma2 sobrevivem a correção de multiplicidade; os deltas
  por modelo restantes são descritivos. Itens são pseudo-replicados por
  desenho (reuso por equivalência) — classes são a unidade inferencial.
- Estratos pequenos (HasNonSkidSurface n=1/modelo, LoadBearing n=2,
  relation n=4) têm p exato mas potência mínima fora do pool.
- O Mecanismo 2 (§6) é interpretação sobre padrões medidos; separar
  instrução × conteúdo do bloco exigiria sub-braços não pré-registrados.
- População = lock 8 GB do par. Generalizar à população de 12 GB
  (escala-4070) exigiria emenda e rodada própria, como previsto na condição.
- A direção exata do truncamento do servidor (descarte do início) é o
  comportamento padrão do llama.cpp e é **consistente** com as respostas
  observadas (tokens do meio/fim do bloco, exemplo das REGRAS copiado), mas
  não foi instrumentada por dentro do Ollama.

## 10. Artefatos desta análise

- `analise_ablacao.py` / `analise_ablacao.json` + `dig_ablacao.py`,
  `dig2_ablacao.py`, `dig3_ablacao.py`, `spy_casa.py`,
  `prompts_casa_{on,off}.json` — scratchpad da sessão `97373ca5`.
- Régua reproduzida da análise do par/escala (recompute integral do
  comparador; 0 mismatches).
- Piso de ruído: perna 4060 do par (`RESULTADO_IFCQC_20260814T174140Z…`),
  extraída só para a comparação da §4.
