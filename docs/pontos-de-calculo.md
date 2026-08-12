# Pontos de cálculo do projeto (referência)

Onde há **aritmética** no IFC Quality Copilot, **quem executa** cada conta e com
**que constantes**. Escrito em 2026-08-04, junto da condição v7, porque o achado
do colapso térmico mostrou que a pergunta "quem faz a conta" tinha respostas
diferentes em lugares diferentes do sistema.

**Princípio adotado:** o LLM declara a **estrutura** (quais camadas, qual λ, qual
resistência superficial); o **código executa a aritmética**. Onde essa separação
ainda não vale, está marcado abaixo.

## 1. Mapa: quem calcula o quê

| grandeza | quem monta os termos | quem faz a conta | onde |
|---|---|---|---|
| **U (transmitância)** — parede, laje, cobertura | LLM (`memoria_calculo`) | **código** | `src/suggestion_engine/thermal_recompute.py` |
| **U** — esquadria (janela/porta) | LLM | **LLM** (valor de referência, não há soma) | template `pset_missing_u_value_window` |
| **FireRating** (classe + minutos) | LLM | — (não é cálculo: é tabela + função do elemento) | template `pset_missing_fire` |
| **erro relativo** por issue | — | código | `src/experiment/per_issue.py::_relative_error_pct` |
| **top-1/top-3, MAPE, faixas** | — | código | `src/experiment/per_issue.py::aggregate_by_stratum` |
| **McNemar exato** (teste pareado) | — | código | `src/experiment/per_issue.py::mcnemar_exact` |
| **readiness score** | — | código ⚠️ **denominador aproximado** | `src/pipeline.py::compute_readiness` (dívida F15) |

## 2. Fórmula e constantes do térmico (NBR 15220-2)

```
U = 1 / R_total
R_total = Rsi + Σ(espessura / λ) + Rse
```

### Resistências superficiais declaradas nos prompts

| situação | Rsi | Rse | template |
|---|---|---|---|
| parede, fluxo horizontal | 0,13 | 0,04 | `pset_missing_thermal` |
| laje de piso, fluxo descendente | 0,17 | 0,04 | `pset_missing_u_value_slab` |
| cobertura, fluxo ascendente | 0,10 | 0,04 | `pset_missing_u_value_slab` |

### Condutividade térmica λ [W/(m·K)]

As duas tabelas são **complementares** (materiais de parede × materiais de laje),
não conflitantes: nos quatro materiais que aparecem nas duas — concreto 1,75;
argamassa 1,15; madeira 0,15; aço/metal 55 — os valores **coincidem**.

| template | λ declarados |
|---|---|
| parede | concreto 1,75 · argamassa/reboco 1,15 · bloco cerâmico 0,90 · gesso acartonado 0,35 · madeira 0,15 · vidro 1,00 · aço/metal 55 |
| laje/cobertura | concreto 1,75 · argamassa/regularização 1,15 · cerâmica/porcelanato 1,05 · fibrocimento 0,95 · madeira 0,15 · EPS 0,04 · lã de vidro 0,045 · aço/metal 55 |

### Câmara de ar não ventilada — **constante divergente entre templates**

| onde | R |
|---|---|
| parede (montante metálico / drywall) | **0,17** m²K/W |
| laje nervurada ou vazio entre perfis | **0,16** m²K/W |
| ground truth do prédio (drywall) | **0,17** m²K/W |

Ambos os valores são defensáveis pela NBR 15220-2 (dependem de espessura e
direção do fluxo), e o GT usa 0,17 no único estímulo que decide. Fica **anotado
como divergência conhecida**: se um dia as constantes virarem fonte única em
código, resolver explicitamente em vez de silenciosamente.

**Regra semântica que sobrevive nos dois:** metal **não isola** (λ = 55); a
camada central de "Metal" num drywall é o montante, e o vão entre montantes é
que vale como câmara de ar. Dividir a espessura do metal por um λ baixo produz
resistência inexistente — patologia observada no benchmark.

### Precisão da espessura entregue ao modelo (v7.6, 2026-08-12)

O termo `Σ(espessura/λ)` vale o que vale a espessura que chega ao prompt.
`_format_thickness_cm` (`src/suggestion_engine/prompt_templates.py`) arredondava
para centímetro inteiro: a chapa de gesso de **1,5 cm** era renderizada como
**"2cm"**. O modelo que declarasse fielmente o que leu calculava **U = 2,20
contra 2,35 do gabarito — 6,4 % de erro embutido pelo próprio estímulo**, dentro
da banda de tolerância de 10 % (§4). O erro cabia na banda e por isso nunca
apareceu como falha, mas consumia dois terços dela antes de o modelo decidir
qualquer coisa; e o estímulo se contradizia, com camadas de 2+7+2 cm num pacote
declarado de 10 cm. Desde a condição v7.6 a espessura preserva o milímetro
(`1.5cm`) — ver `docs/condicao-v7-6-2026-08-12.md` §5.

## 3. Guardas numéricas (onde o código recusa agir)

`src/suggestion_engine/thermal_recompute.py`:

| guarda | valor | por quê |
|---|---|---|
| `_R_TOTAL_MIN` / `_R_TOTAL_MAX` | 0,05 – 10,0 m²K/W | fora disso a memória foi parseada errado |
| `_U_MIN` / `_U_MAX` | 0,1 – 20,0 W/(m²·K) | idem, pelo lado do resultado |
| `_CONSISTENCY_TOLERANCE` | **1 %** | separa "arredondou" de "somou errado" — é aritmética, não estimativa |
| mínimo de termos | 2 | um termo só não é memória de cálculo |

`src/suggestion_engine/plausibility.py` (rebaixa, **nunca descarta**):

| propriedade | faixa | recorte por classe |
|---|---|---|
| ThermalTransmittance | 0,2 – 7,0 | envidraçado (IfcWindow/IfcCurtainWall/IfcPlate): **0,8 – 7,0** |
| SolarHeatGainCoefficient | 0,05 – 1,0 | — |
| VisibleTransmittance | 0,05 – 1,0 | — |

## 4. Bandas de equivalência na avaliação (`src/experiment/evaluator.py`)

| propriedade | banda | por quê |
|---|---|---|
| padrão (numérico) | **2 %** | igualdade de valor tabelado |
| ThermalTransmittance | **10 %** | o próprio GT é **derivado por cálculo**, não medido: exigir 2 % de concordância com uma estimativa reprovava a mesma parede |

Nada fica escondido pela banda: `error_pct` é gravado por issue e o breakdown
reporta MAPE e as faixas ±10 % / ±20 %, então o top-1 sob qualquer banda é
recalculável sem repetir a coleta.

## 5. O que a recomputação determinística conserta — e o que não conserta

**Conserta:** a soma. Nas memórias reais do run v6, o modelo montava os termos
certos e errava a adição; refazer a soma reproduz o GT.

**Não conserta:** a **atribuição de λ**. No estímulo da laje de 20 cm o modelo
trocou os λ (usou 1,75 para o piso cerâmico e 1,05 para o concreto); a soma
refeita dá 2,56 contra GT 2,93 — 12,6 % de erro, ainda **fora** da banda de
10 %. Erro semântico continua sendo erro semântico.

| estímulo | soma dita | soma real | LLM | recomputado | GT | dentro de 10 %? |
|---|---|---|---|---|---|---|
| laje 15 cm (107) | 0,468 | 0,3123 | 2,14 | **3,20** | 3,2 | ✅ |
| laje 15 cm (31) | 0,386 | 0,3123 | 2,59 | **3,20** | 3,2 | ✅ |
| laje usinada (53) | 0,386 | 0,3017 | 2,59 | **3,31** | 3,2 | ✅ (3,6 %) |
| laje 20 cm (4) | 0,6986 | 0,3904 | 1,43 | **2,56** | 2,93 | ❌ (λ trocado) |

É por isso que `thermal_recomputed` é gravado por issue: separa **"o modelo
acertou"** de **"o modelo montou os termos e o código somou"** — e a linha de
cima mostra que a distinção não é retórica.

## 6. Cálculo que NÃO é confiável hoje

`compute_readiness` usa `total_checks = regras IDS aplicadas + total de issues`,
que mistura duas contagens e **não é uma fração de conformidade**. Registrado
como dívida **F15** (`docs/dividas-tecnicas.md`) com condição de resgate: se o
readiness score for citado no artigo ou usado em decisão de engenharia, corrigir
o denominador para checks efetivamente avaliados, com teste de regressão. **Não
é métrica do artigo** — as métricas são top-k, conformidade IDS pós-correção,
estabilidade, eficiência e proxy de revisão.

## 7. Derivações do ground truth

O GT do prédio traz a memória de cálculo de cada estímulo térmico em
`data/evaluation/predio/REVISAO_GT.md` (coluna de notas) — por exemplo:

> `Rsi 0,17 + piso 0,02/1,05 + regularização 0,03/1,15 + concreto 0,10/1,75 + Rse 0,04 = 0,312 → U = 3,20`

Conferidas em 2026-08-04, refazendo cada soma: **as três derivações que decidem
o estrato fecham** — laje 15 cm (0,3123 → 3,20), laje 20 cm (0,3408 → 2,93) e
drywall (0,4257 → 2,35), todas dentro de 1 % do que a nota declara. Isso importa
porque o GT térmico é **derivado**, não medido — e é o que justifica a banda de
10 % (§4).

## 8. Constantes do resolvedor do ground truth integral (2026-08-09)

`src/experiment/ground_truth_value_policy.py` atribui um valor a **cada** issue
dos dois modelos quando o protocolo passou a exigir cobertura integral. Até
2026-08-10 essas constantes viviam só no código; ficam registradas aqui porque
este documento é o ponto único de constantes do projeto.

**Como o valor é decidido** (`source_kind` gravado em cada item do GT):

| `source_kind` | o que é | confiança |
|---|---|---|
| `existing_gt` | rótulo legado ratificado, preservado byte a byte | `high` |
| `ifc_literal` / `ifc_alias` | lido do próprio arquivo (alias de propriedade) | `high` |
| `calculation` | somado pelo código a partir das camadas, com memória na nota | `medium` |
| `typology` | constante tipológica das tabelas abaixo | `medium` |
| `probable` | hipótese congelada, nota obrigatória com prefixo "Hipótese congelada:" | `low` |

Distribuição medida nos artefatos congelados: **prédio** 1654 `existing_gt`,
1365 `typology`, 1048 `probable`, 652 `ifc_alias`, 1 `ifc_literal`, **0
`calculation`**; **casa** 125 `typology`, 79 `probable`, 37 `ifc_alias`, 12
`existing_gt`, 7 `calculation`, 3 `ifc_literal`.

**Tabelas tipológicas** (usadas quando não há camadas suficientes para somar):

| constante | valores |
|---|---|
| `THERMAL_FALLBACK` U [W/(m²·K)] | parede 2,48 · laje 3,20 · cobertura 2,00 · porta 3,00 · janela e fachada-cortina 5,70 |
| `_THERMAL_FALLBACK_BY_MATERIAL` U [W/(m²·K)] | `IfcRoof` + camada de **fibrocimento** → **4,60**, prevalecendo sobre os 2,00 da classe |
| `ACOUSTIC_FALLBACK_DB` Rw [dB] | parede 40 · laje 45 · cobertura 40 · porta 25 · janela 30 |
| `FIRE_FALLBACK` | porta e janela `EI 60`; demais elementos `REI 60` |
| `SHGC_GENERIC_CLEAR_GLASS` | 0,87 (vidro incolor comum) |

**Referência por material dentro da classe (emenda de 2026-08-12).**
`THERMAL_FALLBACK["IfcRoof"] = 2,00` segue valendo como **caso geral** da classe:
descreve laje de cobertura. `_THERMAL_FALLBACK_BY_MATERIAL` abre uma exceção
nominal quando o arquivo declara uma construção de comportamento térmico
distinto — hoje só uma entrada, `IfcRoof` + `fibrocimento` → **4,60**. O valor é
o da revisão autoral (`data/evaluation/predio/REVISAO_GT.md:39`: *"telha de
fibrocimento sem forro: U≈4,6 W/(m²·K) (NBR 15575-5 / LabEEE, valor consagrado
para cobertura leve sem forro)"*), que o protocolo de cobertura integral havia
descartado. Telha fina, sem forro e sem câmara de ar isola muito pouco: os 2,00
erravam **−56 % contra a revisão do autor** e no sentido oposto ao da física do
elemento. **Alcance medido: 5 itens no prédio + 2 na casa** — a casa não tem base
autoral própria e recebe o mesmo número pela mesma construção. Decisão declarada
em `docs/emenda-gt-2026-08-12.md` §2.

**Pendência declarada — a mesma telha com duas referências.** O prédio tem **9
itens de `ThermalTransmittance` cujas camadas são apenas "CRO5 - Telha
Fibrocimento Ondulada", mas cuja classe IFC é `IfcSlab`**; por isso recebem o
fallback de laje, **3,20**, e não os 4,60. É a mesma construção física dos 5
itens de `IfcRoof` que a emenda corrigiu. Não foram tocados: a revisão autoral
registra exatamente **5** itens térmicos para essa construção, e estender a
emenda aos 9 seria decisão editorial nova, não restauração de registro
existente. Fica anotado como inconsistência interna conhecida, para decisão numa
próxima revisão. **Nenhum dos dois números é "o resultado"**: os dois saem como
`typology` (`medium`), e o artigo reporta as fatias de confiança.

**Status de proveniência — leia antes de citar qualquer um destes números.**
São hipóteses tipológicas adotadas pelo protocolo, **não** valores atribuíveis a
uma edição normativa: `references/normative/public/sources.yaml` registra
explicitamente que os metadados públicos consultados não permitem atribuir
condutividades, resistências superficiais ou resultados à edição vigente da
NBR 15220-2. Por isso todo item resolvido por tabela sai como `typology`
(`medium`) ou `probable` (`low`), nunca como `high`, e a leitura correta do
estrato é "concordância com convenção autoral congelada", não conformidade
normativa. O U de parede 2,48 permanece **sem citação de fonte** e coincide com
uma resposta de modelo medida em 2026-07-27 (`src/experiment/evaluator.py`);
enquanto essa coincidência não for resolvida, não use os 6 itens que dependem
dele como evidência de acerto normativo.

**λ do resolvedor** — espelha as duas tabelas complementares de §2:

| família do elemento | λ [W/(m·K)] |
|---|---|
| parede (padrão) | concreto 1,75 · argamassa e revestimento cimentício 1,15 · cerâmica 0,90 (bloco) · gesso 0,35 · madeira 0,15 · vidro 1,00 · EPS 0,04 |
| laje e cobertura (`IfcSlab`, `IfcSlabStandardCase`, `IfcRoof`) | idem, **exceto cerâmica 1,05** (piso cerâmico/porcelanato) |

Corrigido em 2026-08-10: o resolvedor achatava as duas tabelas numa só e usava
0,90 para cerâmica em qualquer família, divergindo deste documento e dos
próprios templates de prompt, que já declaravam 1,05 para laje. A correção foi
verificada com `python scripts/build_ground_truths.py --check`: **sem drift** nos
dois GTs congelados — nenhum item resolvido por cálculo usa cerâmica hoje, então
a mudança é inerte no que está congelado e vale para rebuilds futuros.

**Lacuna conhecida:** os tokens `porcelanato` e `fibrocimento` **não** estão na
tabela. Uma camada chamada só "porcelanato" ou só "Telha Fibrocimento Ondulada"
faz `_lambda_for` devolver `None`, o cálculo inteiro é abandonado e o item cai
para a constante tipológica — falha fechada, sem erro silencioso, mas é parte da
explicação de o prédio ter **zero** itens `calculation`. Incluir os tokens
mudaria rótulos do GT e por isso exige rebuild declarado, não correção em
silêncio.

No caso da telha isso tem consequência direta: **o cálculo por camadas jamais
reproduz 4,60 nem 2,00** — o item sempre cai no fallback, e é por isso que a
emenda acima teve de agir sobre a constante, não sobre o λ. Note a divergência
entre as duas tabelas: o template de laje/cobertura (§2) **declara** fibrocimento
0,95 ao modelo, enquanto o resolvedor do GT não conhece o token. O modelo pode
somar essa camada; o gabarito, não.

**Circularidade a declarar no artigo:** `SHGC_GENERIC_CLEAR_GLASS` (0,87) é o
mesmo número que o template `pset_missing_solar` entrega ao modelo na tabela de
referências, e o IFC não declara o vidro em nenhum dos estímulos (o campo traz
`None` ou o caixilho de alumínio). Esse estrato mede **concordância com a
convenção adotada**, não derivação — reporte-o assim.

## Ver também

- `docs/condicao-v7-2026-08-04.md` — a condição que moveu a aritmética para o código
- `docs/condicao-v7-6-2026-08-12.md` — fechamento do instrumento (§5: espessura com milímetro)
- `docs/emenda-gt-2026-08-12.md` — a emenda que restaurou os 4,6 da telha de fibrocimento
- `docs/achado-aritmetica-termica-2026-08-02.md` — a medição que motivou
- `docs/dividas-tecnicas.md` — F15 (denominador do readiness)
- `references/normative/public/sources.yaml` — o que as citações normativas provam e o que não provam
