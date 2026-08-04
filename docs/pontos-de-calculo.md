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

## Ver também

- `docs/condicao-v7-2026-08-04.md` — a condição que moveu a aritmética para o código
- `docs/achado-aritmetica-termica-2026-08-02.md` — a medição que motivou
- `docs/dividas-tecnicas.md` — F15 (denominador do readiness)
