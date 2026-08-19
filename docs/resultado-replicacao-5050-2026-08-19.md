# Replicação RTX 5050 — terceira perna do par v7.7 (2026-08-19)

Rodada de 2026-08-18/19 na **RTX 5050 Laptop 8 GB (Blackwell)** — a replicação
pré-declarada como extensão nº 1 do par unificado. Release
`ifcqc-2026-08-18-801636831646` (a mesma da ablação, rodada no **braço padrão,
bSDD ligado**), run `96f42b02…`, zip
`dist/RESULTADO_IFCQC_20260818T190222Z_96f42b02….zip`. **20/20 estágios
validados, 0 inválidos.** Instalação + download do armazém ~4,8 h; estágios de
18/08 23:50 UTC a 19/08 15:17 UTC com **uma única pausa de 9,36 h entre prédio
e casa** (máquina suspensa; 00:27→09:48 BRT) — **soma dos estágios 6,07 h**.

Máquina: Avell ION A70, Core Ultra 7 155H (22 threads), 32 GB DDR5-5600,
RTX 5050 Laptop 8.151 MiB (compute 12.0), **driver 573.22**, Windows 11 Pro,
plano "Alto desempenho", NVMe Lexar NM790. Ollama 0.32.5 pinado, Python 3.12.13.

Identidade de execução `941104fa…` — difere do par (`5cab7c70…`) apenas porque
o schema ganhou `grounding_bsdd: true` e `release_id`/`source_commit`/`project_sha`
são os da release nova; **todos os campos científicos são idênticos ao par**.
Baselines: pernas 4070 (13/08, `…20260813T164437Z…`) e 4060 (14-15/08,
`…20260814T174140Z…`). Régua idêntica às análises anteriores (reproduz gemma2
0,8216/0,8250, mistral classe 0,7063/0,6865, qwen3.5:9b t3 0,9430/0,9382 e os
flips 17/483/610 do par).

**Resultado em uma linha: o instrumento replica em uma terceira GPU de outra
arquitetura — pool de classes dentro de 0,9 pp e McNemar agregado n.s. nos três
pares de máquinas — e o eixo de estabilidade ganha n=3: gemma2 flippa 1–2
classes por par enquanto lfm2.5 flippa 42–44 e cai para 0,391 em itens.**

## 1. Validade

- **Condição**: `grounding_bsdd: true` em `input-hashes.json` e nos 20
  `run_0.json`; `grounding_sources=['bsdd']` + `bsdd_source_status: live` em
  49.830/49.830 issues; `bsdd_cache_sha256` idêntico às três máquinas
  (`6d16d344…`). É a condição do par v7.7-on, não a da ablação.
- **Invariantes idênticos ao par**: prompt v7.7 `751ec1679d46…`, GT prédio
  `040c871f…` (4720/202) e casa `e72b344f…` (263/101), IFC/IDS shas, lock
  `c37c0a6f…` com 10/10 digests conferidos no `ollama-models.json`,
  `num_ctx fixed 4096`, `num_predict 768`, seed 42, temp 0,1, top_p 0,9,
  repeat 1,1, réplica 1, cache off, reuso on.
- **Estímulos equivalentes por construção**: partições de classe idênticas
  (303/modelo, 0 classes não homogêneas), conjuntos de `issue_id` idênticos,
  e `num_ctx_effective` com exatamente a mesma distribuição das pernas do par
  (49.810 × 4096 + **20 × 8192** — os mesmos 2 estímulos fills × 10 modelos).
- **Comparador**: 0 divergências em 99.660 vereditos recomputados (GT do repo
  == GT pinado na rodada).
- **Estabilidade de coleta**: 0 falhas terminais; retries 11 (par: 11/10);
  pior `json_valid_first_try` 0,683 (falcon; par: 0,673).

## 2. Pódio por métrica nas três GPUs

Pooled prédio+casa; item n=4.983, classe n=303. Ordem: 4070 / 4060 / 5050.

| modelo | item top-1 | classe top-1 | item top-3 | classe top-3 |
|---|---|---|---|---|
| falcon3:7b | 0,696 / 0,680 / 0,679 | 0,637 / 0,624 / 0,617 | 0,910 / 0,900 / 0,900 | 0,825 / 0,815 / 0,815 |
| **gemma2:9b** | **0,8216 / 0,8250 / 0,8232** | 0,663 / 0,667 / 0,663 | 0,930 / 0,914 / 0,928 | 0,868 / 0,865 / **0,878** |
| granite4:tiny-h | 0,774 / 0,735 / 0,755 | 0,657 / 0,667 / 0,667 | 0,906 / 0,804 / 0,819 | 0,838 / 0,838 / 0,828 |
| lfm2.5:8b | 0,540 / 0,479 / **0,391** | 0,485 / 0,426 / 0,426 | 0,718 / 0,774 / 0,782 | 0,700 / 0,706 / 0,690 |
| llama3.1:8b | 0,748 / 0,737 / 0,758 | 0,627 / 0,630 / 0,627 | 0,929 / 0,925 / 0,913 | 0,832 / 0,838 / 0,809 |
| mistral:7b | 0,703 / 0,657 / 0,626 | 0,706 / 0,687 / 0,670 | 0,819 / 0,810 / **0,934** | 0,805 / 0,799 / 0,795 |
| phi4-mini | 0,648 / 0,661 / 0,667 | 0,422 / 0,452 / 0,449 | 0,858 / 0,893 / 0,824 | 0,693 / 0,706 / 0,703 |
| qwen2.5:7b-instruct | 0,552 / 0,544 / 0,520 | 0,525 / 0,515 / 0,518 | 0,865 / 0,863 / 0,849 | 0,845 / 0,855 / 0,855 |
| qwen3.5:4b | 0,723 / 0,793 / 0,761 | 0,627 / 0,621 / 0,657 | 0,872 / 0,918 / 0,841 | 0,786 / 0,792 / 0,809 |
| qwen3.5:9b | 0,787 / 0,764 / 0,780 | 0,703 / 0,680 / 0,687 | 0,943 / 0,938 / 0,928 | 0,868 / 0,852 / 0,848 |
| **pool (10 modelos)** | 0,699 / 0,688 / 0,676 | **0,605 / 0,597 / 0,598** | 0,875 / 0,874 / 0,872 | **0,806 / 0,807 / 0,803** |

- **Item top-1: gemma2 lidera nas três GPUs, com amplitude de 0,34 pp** — o
  resultado central do par sai intacto da terceira réplica.
- **Classe top-1: mistral × qwen3.5:9b é empate estatístico**. A liderança
  pontual alterna (mistral por 1 classe na 4070 e 2 na 4060; qwen3.5:9b por 5
  na 5050) — diferenças de 1–5 classes contra um ruído cross-GPU de 26–35
  classes/par para esses modelos. qwen3.5:9b é top-2 nas três.
- **Item top-3: o "salto" do mistral na 5050 (0,819→0,934) é peso de item, não
  capacidade** — ver §4. No nível de classe o top-3 dele fica parado (0,795).
- Pool de classes: as três máquinas concordam dentro de **0,9 pp** (top-1) e
  **0,4 pp** (top-3). O pool de itens abre 2,3 pp, quase todo por lfm2.5
  (−15 pp sozinho ≈ −1,5 pp de pool) e pilares do mistral.

## 3. Ruído cross-GPU com n=3: simétrico no agregado, propriedade do modelo

Flips top-1 por par de máquinas (item | classe; McNemar exato de classe):

| par | flips item (10 modelos) | flips classe | McNemar agregado classe |
|---|---|---|---|
| 4070×4060 | 2.982 | 220/3.030 | 123×97, p=0,092 |
| 5050×4070 | 3.285 | 244/3.030 | 111×133, p=0,179 |
| 5050×4060 | 3.091 | 212/3.030 | 108×104, p=0,837 |

Nenhum par tem assimetria significativa no agregado de classe: **trocar de GPU
(inclusive de arquitetura, Ada→Blackwell) desloca ~7% das classes de forma
simétrica** — mesma leitura do piso de ruído usado na ablação.

Por modelo, a hierarquia de estabilidade replica:

- **gemma2**: 17/26/9 flips de item; **1/2/1 de classe**. As classes que
  flipam: SHGC de 17 itens (0,65↔0,87 — a 5050 concorda com a 4060 e acerta) e
  FireRating de 9 itens (EI 30 × REI 60, perde na 5050). Distribuição de fogo
  quase idêntica nas três (EI 30: 41/41/42).
- **lfm2.5**: 483/898/1.167 flips de item (até **23%** dos itens); item top-1
  0,540→0,479→**0,391**. Na 5050 perde três pilares de 222 itens
  (IsLoadBearing True em vez de False, AcousticRating, e o drywall do
  system — ecoa o nome do elemento no lugar do rótulo). Fogo: **5ª rodada, 5ª
  composição** (REI30-heavy de novo, mas com membros diferentes). Único
  modelo com McNemar de classe significativo contra a 4070 (44 flips,
  p=0,0096) — perda direcional, não só ruído.
- **qwen3.5:4b**: o salto de +7 pp da 4060 não replica (5050 fica no meio,
  0,761); na 5050 o pilar térmico de 222 itens vira **abstenção** — 231 itens
  abstidos, todos ThermalTransmittance (4 classes). Abstenção do pool:
  87 (4070) / 19 (4060) / 247 (5050) — o botão volátil é dele.
- **mistral**: erro silencioso (errado & confiança alta) sobe de 13,1% para
  **25,1%** na 5050 — perde os pilares de top-1 sem baixar a confiança.
- **llama3.1**: único ganho unidirecional na 5050 (54×4 vs 4070; 108×5 vs
  4060) — um pilar térmico de 53 itens entra na tolerância (3,31 vs 4,09 para
  esperado 3,2).

## 4. O salto de top-3 do mistral: aula de peso de item

Na 5050, duas classes-pilar entram no top-3 do mistral:

- **R 60 (pilar de 352 itens, FireRating)**: 4070 respondia
  `[R 30, REI 90, REI 120]` (zero); 5050 responde `[REI 30, REI 60, EI 30]` —
  REI 60 em 2ª posição, aceito pela banda.
- **Térmica de 222 itens (esperado 2,35)**: 4070 `[1,5; 1,67; 1,83]`; 5050
  `[1,5; 1,78; 2,37]` — 2,37 dentro da tolerância.

574 itens em duas decisões: item top-3 +11,5 pp; classe top-3 −1,0 pp. O
comprimento das listas não muda (2,67→2,71 valores/resposta) — é conteúdo de
pilar, não formato. **É o argumento mais limpo até agora para a classe de
equivalência como unidade primária de leitura.**

## 5. Estratos: tudo replica, incluindo o defeito

Acurácia de classe, pool dos 10 modelos (4070/4060/5050):

- `relation_broken`: **fills 0/20 nas três máquinas** — terceira replicação do
  colapso induzido pelo bloco bSDD sem escopo (42,5 KB truncando a tarefa,
  diagnosticado na ablação); boundary/contained 15/17/16 de 20.
- FireRating 0,655/0,630/0,639; Category 0,742/0,735/0,745; acústica
  0,666/0,675/0,666; térmica 0,354/0,334/0,340; system 0,553/0,563/0,540;
  SHGC 0,167/0,167/0,150 (convenção, como no par); HasNonSkidSurface 0,10 nas
  três (o mesmo único modelo acerta).

## 6. Hardware: a 5050 é ~1,5× a 4060 — e ainda ~1,5× atrás da 4070

Latência p50 por chamada (s), mesmos estímulos:

| modelo | 4070 12 GB | 4060 8 GB | 5050 8 GB | 5050 vs 4060 |
|---|---|---|---|---|
| granite4:tiny-h | 1,72 | 3,93 | 2,71 | 1,45× |
| lfm2.5:8b | 1,46 | 3,87 | 2,00 | 1,93× |
| phi4-mini | 1,84 | 4,91 | 2,63 | 1,87× |
| llama3.1:8b | 2,59 | 5,89 | 3,74 | 1,58× |
| qwen3.5:4b | 2,52 | 6,64 | 3,78 | 1,76× |
| falcon3:7b | 2,71 | 5,99 | 4,09 | 1,46× |
| qwen2.5:7b | 3,41 | 7,26 | 4,82 | 1,51× |
| mistral:7b | 3,59 | 7,29 | 5,53 | 1,32× |
| **gemma2:9b** (transborda) | 3,16 | 8,38 | 6,61 | 1,27× |
| **qwen3.5:9b** (transborda) | 3,85 | 8,90 | 6,70 | 1,33× |

- **Mediana: 5050 ≈ 1,49× mais rápida que a 4060** (faixa 1,27–1,93×) e
  ≈ 1,50× mais lenta que a 4070. Em tokens/s a mediana é +51% sobre a 4060
  (phi4 +111%, lfm +95%, granite +71%).
- **O ganho geracional aparece nos residentes e encolhe nos transbordados**:
  gemma2 +27–33% apenas — quando o modelo vaza para RAM, o gargalo migra para
  PCIe/CPU e a GDDR7 não paga.
- **O transbordo persiste em Blackwell 8 GB**: gemma2 frac 0,781 e qwen3.5:9b
  0,856 (4060: 0,797 e 0,878; a 5050 tem até menos VRAM útil, 8.151 vs 8.188
  MiB). **A conclusão de viabilidade do par não muda com a geração: os dois
  líderes seguem não-residentes em 8 GB**; a recomendação de compromisso
  (qwen3.5:9b) e o plano B residente (llama3.1) ficam de pé.
- Fila efetiva (soma dos estágios): **6,07 h** vs 4,35 h (4070) e 18,91 h
  (4060 em uso diurno; overnight limpo ~7,4 h). Como sempre: comparar
  latência/chamada, não fila absoluta.
- Confounders declarados: driver 573.22 (mais antigo que os 591.x das outras
  duas), 32 GB de RAM (vs 16 GB da 4060 — ajuda o transbordo), CPU/plataforma
  diferentes. GPU+driver+máquina mudam juntos — é réplica de ambiente, como
  no desenho do par.

## 7. O que muda no artigo

1. **C1–C5 ganham terceira réplica** em GPU de outra arquitetura: pódio de
   item intacto (gemma2, amplitude 0,34 pp), pool de classes dentro de 0,9 pp,
   McNemar agregado n.s. nos três pares.
2. **Redação da liderança de classe**: tratar mistral × qwen3.5:9b como empate
   dentro do ruído cross-GPU (a ordem pontual alterna com a GPU); não há
   mudança de conclusão, há honestidade a mais.
3. **Eixo de estabilidade vira resultado com n=3 GPUs / 3 pares / 2
   arquiteturas**: gemma2 0,2–0,5% de flips de item × lfm2.5 10–23% — a
   estabilidade é propriedade do modelo, não do par de máquinas usado.
4. **Nova evidência para a classe como unidade primária**: +11,5 pp de top-3
   de item do mistral vindos de 2 decisões (574 itens) sem movimento no top-3
   de classe.
5. **fills 0/20 na terceira máquina** — fecha o círculo com a ablação: o
   defeito é do tratamento (bloco bSDD sem escopo), replicável em qualquer
   GPU.
6. **Primeira medição Blackwell do instrumento**: geração nova de 8 GB compra
   ~1,5× de velocidade sobre Ada 8 GB, mas não muda nenhuma conclusão de
   acurácia nem de viabilidade (transbordo persiste).
7. **Nenhum número oficial muda**: o oficial segue o par v7.7 (4070+4060); a
   5050 entra como replicação, citada como extensão.

## 8. Limitações declaradas

- A release é a da ablação (`801636831646`), não a do par (`da0f471b44a9`):
  mesma condição **por hashes** (prompt, GTs, lock, cache bSDD, parâmetros) e
  mesma distribuição de `num_ctx_effective`, mas não é o mesmo binário.
- Réplica de ambiente, não experimento controlado de hardware: GPU, driver,
  CPU, RAM e máquina mudam juntos (idêntico ao desenho do par).
- A fila teve pausa de 9,36 h entre datasets (suspensão da máquina): usar soma
  de estágios ou latência por chamada, nunca o span de 15,45 h.
- A comparação de fila absoluta com a 4060 herda a inflação conhecida da perna
  4060 (uso diurno + Defender).

## 9. Artefatos desta análise

- Scripts e JSON no scratchpad da sessão `18105fc3`: `analise_5050.py`
  (métricas, flips, McNemar, estratos, telemetria, recomputação do
  comparador), `dig_5050.py` (mecanismos: fills, pilares, abstenções, fila),
  `pools.py`, `analise_5050.json`.
- Zips: rodada em `dist/RESULTADO_IFCQC_20260818T190222Z_96f42b02….zip`;
  baselines nas duas pernas do par (13/08 e 14/08).
