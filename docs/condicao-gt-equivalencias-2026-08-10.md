# Condição — equivalência de decisão em fogo e acústico (2026-08-10)

> **Declaração metodológica, primeiro parágrafo de propósito.** Esta emenda
> **aumenta** a acurácia medida em dois estratos, e foi decidida **depois** de ver
> que o gemma2 zerava o acústico (0/18) e caía a 0,425 no fogo. Registro a ordem
> dos fatos como ela foi: a medição expôs dois defeitos de instrumento, não uma
> fraqueza de modelo, e a emenda corrige os defeitos. O critério é declarado,
> recalculável sobre coletas já gravadas, e vale igualmente para os 10 modelos.
> Ao reportar: os estratos `FireRating` e `AcousticRating` **não são comparáveis**
> com nenhuma coleta anterior a esta data.

Prompt: `v7.4` → `v7.5`. Ground truth: novos pins (§5). Suíte e verificação de
não-deriva ao final.

## 1. O princípio

O comparador (`src/experiment/evaluator.py`) trata classe de fogo e rótulo
acústico como **texto**, de propósito: `_as_scalar_number` documenta que tratar
"REI 60" como número fazia `EI 60`, `R 60` e `REI 60` casarem entre si e o
estrato virava medida de minutos. Esse rigor fica.

O que faltava era o outro lado: **onde duas respostas representam a mesma decisão
técnica, isso tem de estar declarado no ground truth**, item a item, em
`accepted_alternatives` — dado auditável, nunca regra embutida no comparador.

E a regra que governa a largura da equivalência:

> **A severidade da equivalência acompanha a confiança da referência.**

Onde o GT é hipótese congelada (`low`/`probable`), ele não tem autoridade para
discriminar o que não sabe — o TRRF depende de altura e ocupação, que o IFC não
carrega. Onde a referência foi verificada pelo autor (`high`), vale exatamente o
escopo que ele ratificou.

## 2. Fogo — o que estava errado

Medido com gemma2:9b sob v7.4, 40 estímulos de `FireRating` do prédio: **0,425**.
O padrão dos 23 erros denuncia o instrumento, não o modelo:

| ocorrências | GT esperava | modelo respondeu | leitura |
|---|---|---|---|
| 9 | `REI 60` | `EI 60` | **a emenda ratificada em 2026-08-04 aceitava isso** e foi removida |
| 9 | `EI 60` | `EI 30` | duração, sobre uma referência que é hipótese |
| 5 | `REI 60` | `EI 30` | itens de drywall que a revisão autoral tinha como `EI 30` |

A emenda de 2026-08-02, **ratificada por Felipe Keller em 2026-08-04**
(`data/evaluation/predio/REVISAO_GT.md`, "Emendas pós-aprovação"), declarava: em
vedação cujo IFC diz `LoadBearing = false`, `EI` de duração ≥ à exigida é
alternativa aceita ao `REI` da compartimentação — *"um modelo que responde EI
está seguindo a evidência dada pelo arquivo e não deve ser penalizado"*. O
protocolo de cobertura integral de 2026-08-08 tratou a emenda como pendente
(`ground_truth_audit._PENDING_EI_ALTERNATIVES`) e a apagou: o GT congelado passou
a ter **zero** itens aceitando EI.

**O que o v7.5 faz:**

- **Restaura a emenda nos 167 itens legados** de vedação não portante com `REI 60`:
  voltam a aceitar `REI 90/120` e `EI 60/90/120`. Escopo idêntico ao ratificado
  (`load_bearing_alias is False`). Nenhum `expected_value` mudou.
- **Estende a mesma regra declarada aos itens que o protocolo integral criou**
  (`low`/`probable`): aceitam a família estanqueidade+isolamento em duração
  normalizada — `EI/REI × {30, 60, 90, 120}` —, mais `P-CF` onde o esperado é EI
  (porta e janela corta-fogo também são especificadas assim). Justificativa: uma
  referência que é hipótese não pode reprovar uma duração plausível.
- **Não toca os 352 pilares** (`R 60`, `high`, alternativas `REI 60`/`R 90`): o
  critério ali é estrutural e foi verificado.

O que a emenda **não** faz: não conserta a inversão de valor esperado nos 222
itens de drywall (a revisão autoral os tinha em `EI 30`; o protocolo gravou
`REI 60`). O `expected_value` segue divergindo do registro autoral. Fica como
pendência declarada.

> **Correção de 2026-08-12.** O parágrafo acima afirmava que "com a família
> aceita, o modelo que responde `EI 30` deixa de ser penalizado". **Isso era
> falso no artefato congelado**: `_fire_alternatives(ratified=False)` restringe
> as durações a `>= 60`, então a lista real dos itens `REI 60`/`low` era
> `[EI 60, EI 90, EI 120, REI 90, REI 120]` — sem `EI 30`. A resposta mais
> aderente ao estímulo (o template ensina `EI` para drywall e autoriza 30 min)
> continuou contada como erro nas 222 issues durante todo o benchmark v7.5.
> Corrigido pela emenda de 2026-08-12 (`docs/emenda-gt-2026-08-12.md`), que
> acrescenta `EI 30` ao conjunto aceito **apenas** em vedação leve declarada no
> arquivo — o piso de 60 min continua valendo em toda vedação pesada.

## 3. Acústico — o que estava errado

Medido: **0,000** em 18/18 estímulos. O modelo respondeu `D` em todos. Não é erro
de decisão: o template **ensinava** essa forma — *"Alvenaria 14cm: 'D' ou '35 dB'"*
— e o schema do ground truth (`ACOUSTIC_RATING_PATTERN = ^Rw \d{2} dB$`) só
pontua `Rw NN dB`. Pior: mesmo em dB o prompt sugeria 35/42/50 e o GT esperava
40/25, sob banda de 2%. Contrato incompatível nas duas dimensões.

É o mesmo defeito do vazamento solar corrigido no v7.4, **invertido**: lá o prompt
entregava a resposta e inflava; aqui o prompt pedia uma forma que o GT não sabia
ler e zerava.

**O que o v7.5 faz — corrige os dois lados:**

- **Prompt:** o template acústico passa a exigir `Rw NN dB` no campo `valor`, com
  a tabela de referências expressa em Rw e a classe D/M/S marcada
  explicitamente como *raciocínio, não resposta*.
- **Ground truth:** banda de equivalência de **±5 dB**, materializada como
  `accepted_alternatives` na notação canônica. Motivo idêntico ao da banda de 10%
  do térmico, já declarada em `docs/pontos-de-calculo.md`: a referência é uma
  constante tipológica por classe de elemento — a própria nota do item diz "não
  representa ensaio do sistema construído" — e o passo entre classes de
  desempenho é ~5 dB. Exigir 2% de uma referência tipológica mede notação, não
  decisão.

A banda preserva a discriminação que importa: parede (40 dB) e porta (25 dB)
continuam sem sobreposição, então um modelo que não distingue os dois elementos
segue errando.

## 4. O que continua estrito

- `EI` **não** casa com `REI` por acidente numérico — só quando declarado.
- Nenhuma equivalência foi adicionada a `Category`, `system_unclassified`,
  `ThermalTransmittance`, `SolarHeatGainCoefficient`, `LoadBearing`,
  `IsLoadBearing`, `HasNonSkidSurface` ou `relation_broken`.
- Nenhum `expected_value`, `confidence` ou `source_kind` mudou em nenhum item dos
  dois datasets. A emenda é **só** sobre o conjunto de respostas aceitas.

## 5. Pins e cadeia de hashes

| artefato | antes | depois |
|---|---|---|
| `predio/ground_truth.yaml` | `f92057437c8b…10940c9d` | `853ff6040254…78dc58b` |
| `casa/ground_truth.yaml` | `60f87a079d2a…1a6f8cfee5` | `c98fdd5ec056…58bb2d1d` |
| `legacy-reference.lock.json` (prédio, hash semântico) | `f1aac68fec38…463f4552` | `4efc089aae14…8b8f85fa7c` |
| `PROMPT_VERSION` | `v7.4` | `v7.5` |

O lock legado mudou **porque a emenda ratificada volta a itens legados** — é uma
alteração deliberada do subconjunto histórico, declarada no próprio arquivo
(campo `amendment`). A contagem permanece 1654/12; só as alternativas mudaram.
`python scripts/build_ground_truths.py --check`: sem drift nos dois datasets.

## 6. Comparabilidade

- **`FireRating` e `AcousticRating`: quebrados** contra qualquer coleta anterior a
  2026-08-10 — inclusive a matriz v6 e o v7.2. Não compare, não agregue.
- **Demais estratos: intactos.** O diff de prompt do v7.5 toca apenas o template
  acústico; nenhum outro estímulo mudou (verificável com
  `scripts/dump_prompts_spy.py` + `scripts/diff_prompts.py`).
- A ponte `accuracy_legacy` continua compartilhando a **população** da base
  histórica, e agora também difere dela no **critério de fogo** — mais um motivo
  para não citá-la como réplica de v6/v7.2.

## Ver também

- `data/evaluation/predio/REVISAO_GT.md` — a emenda ratificada em 2026-08-04
- `docs/condicao-v7-4-2026-08-10.md` — o vazamento solar e a frase da laje
- `docs/pontos-de-calculo.md` §8 — constantes do resolvedor e bandas de equivalência
