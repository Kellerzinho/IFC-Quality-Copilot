# Análise profunda do benchmark 2026-07-28 (run limpo, commit 2e03386)

Estudo por modelo × estrato **no nível de estímulo** (a unidade de inferência),
com auditoria do fluxo IFC → prompt (dump com cliente espião, sem GPU) e do que
o bSDD realmente injeta. Dados: `src/experiment/results/2026-07-28-benchmark-limpo/`
(20/20 estágios, `run_0_issues.jsonl` por estágio). Scripts da análise: sessão
de 2026-07-28 (`analyze_benchmark.py`, `detalha_estratos.py`, `dump_prompts.py`).

## 1. Top-1 por estímulo (não por issue)

**Prédio** (Category n=77 · Fire n=6 · LoadBearing n=2 · Thermal n=19 · system n=11):

| modelo | Category | Fire | LoadB | Thermal | system |
|---|---|---|---|---|---|
| gemma2:9b | 0,61 | 0,50 | 1,00 | 0,58 | **1,00** |
| qwen3.5:4b | 0,58 | **0,67** | 1,00 | 0,53 | 0,91 |
| qwen3.5:9b | 0,48 | 0,17 | 1,00 | 0,53 | **1,00** |
| llama3.1:8b | 0,48 | 0,33 | 1,00 | 0,42 | 0,82 |
| granite4:tiny-h | 0,48 | 0,17 | 0,50 | **0,00** | 0,82 |
| mistral:7b | 0,52 | **0,00** | 1,00 | 0,10 | 0,09 |
| qwen2.5:7b | 0,38 | 0,33 | 1,00 | 0,47 | 0,91 |
| falcon3:7b | 0,30 | 0,17 | 0,50 | 0,47 | 0,09 |
| phi4-mini | 0,22 | 0,17 | 0,50 | **0,00** | 0,18 |
| lfm2.5:8b | 0,22 | 0,33 | 0,50 | 0,26 | 0,27 |

**Masked** (space_unnamed, n=79): gemma2 0,57/0,67 (top1/top3) · granite4
0,43/0,63 · llama3.1 0,43/0,62 · mistral 0,41/0,60 · qwen3.5:9b 0,35/0,48 ·
qwen3.5:4b 0,23/0,29 · lfm2.5 0,23/0,38 · qwen2.5 0,20/0,48 · falcon3
0,11/0,44 · phi4-mini 0,10/0,17.

Estabilidade de JSON **não é problema** (≥ 92% de first-try válido em todos,
0-2 falhas/202): o defeito está no **valor** dentro do JSON, não no formato do
JSON. 115 estímulos comparáveis no prédio: 24 todos erram, 3 todos acertam,
88 discriminam modelos. No masked: 28/79 todos erram, 0 todos acertam.

## 2. Auditoria IFC → prompt: o que chega e o que não chega

Verificado com dump dos 202+79 prompts primários reais (bate 1:1 com os
`samples` do run).

**Chega correto:** paredes, lajes e esquadrias térmicas recebem camadas com
espessuras em metros corretas (ex.: laje 15 cm = porcelanato 2 + regularização
3 + concreto 10; o cálculo NBR 15220-2 com esses dados dá exatamente o valor de
referência). A pendência antiga de "espessura 140 m" não se manifesta nesses
estratos. LoadBearing, PredefinedType e IsExternal chegam.

**Não chegava (corrigido em v6):**
- **`IfcSpace.LongName` não entrava no prompt de Category.** O prédio tem o
  uso declarado em LongName ("Hall de Circulação", "Sacada", "Medidores de
  Luz"); o prompt mostrava só `Name` numérico ("40", "64"). O maior estrato da
  matriz (77/115 estímulos) foi medido com a evidência principal amputada — as
  confusões universais (CIRCULATION→TECHNICAL_AREA em 6 estímulos que todos
  erram; BALCONY→KITCHEN) são consequência disso, não ignorância dos modelos.
  Corrigido: `long_name` no contexto + linha "Uso declarado" no template.
- **`IfcRoof` chegava sem material, sem camadas e sem espessura** (o Revit
  agrega o material nas partes via `IfcRelAggregates`). Sem camadas, os modelos
  devolviam λ como U (0,95 = λ do fibrocimento, emitido por 4 modelos) ou um U
  de telhado isolado. Corrigido: `read_material_layers` herda das partes.

**Morto no dataset (não é bug de código; reportar como característica):**
- Adjacências: "nenhum" em **161/161** prompts de espaço/Category — o modelo
  não tem IfcRelSpaceBoundary utilizável.
- No masked: Pavimento `None` em 79/79, `Fronteira com exterior: False` em
  79/79 (inclusive sacadas — o sinal não existe no arquivo), pé-direito
  uniforme 4,0 m (sem poder discriminativo).
- Armadilha de conteúdo: "Vaso Manu 25" (vaso de PLANTA) era lido pela tabela
  de interpretação como vaso sanitário → banheiro. Tratado no template v6.

## 3. "Estão seguindo o bSDD?" — o que o bSDD realmente injeta

Para **todas** as combinações do experimento, o bSDD entrega apenas a
**resolução de classe** (`IfcWall` + URI 4.3) e, para FireRating, a ficha da
propriedade com `tipo: String` e valores **"livre"**. `official_candidates` e
`allowed_values` = **vazios em 100% dos estratos**. Ou seja: hoje não existe
vocabulário de valores vindo do bSDD para nenhuma tarefa do benchmark; os
vocabulários fechados que os modelos seguem (ou ignoram) vêm dos **templates**
(lista de Category, rótulos de sistema, formato de FireRating). Aderência
medida a esses vocabulários:

- Respeitam a lista mas erram o item (erro semântico, não de formato): gemma2,
  qwen3.5:4b, qwen2.5, llama3.1, granite4 — quase 100% das respostas de
  Category/sistema dentro do vocabulário.
- Ignoram o vocabulário: **mistral** inventa classes IFC como sistema
  (`IfcBeam`, `IfcSlabPrecast` — 8/8 lajes); **lfm2.5** e **phi4-mini** ecoam o
  nome do objeto do modelo ("Piso:laje de concreto usinado + piso genérico");
  **qwen3.5:9b** devolve números do contexto como Category (8×: área "6.3",
  nomes "50"/"115").
- Caso gemma2: 19 dos 47 erros de Category eram **grafia** ("LIVING ROOM" com
  espaço, `_BEDROOM_`, "Bedroom") — o run mediu o prompt anterior ao commit
  2e03386; a exigência "copiado caractere por caractere" já cobre parte disso.

**Bug latente encontrado (não afeta os estratos do benchmark):**
`prepare_llm_grounding` e `_validate_against_bsdd` comparam `check_property`
("FireRating") com o nome humano do bSDD ("Fire Rating") por igualdade exata —
nunca casam, então `expected_datatype`/`allowed_values` não fluem para o
caminho grounded genérico e o downgrade por tipo nunca dispara. Vale corrigir
quando o caminho `pset_missing` genérico entrar no experimento.

## 4. Perfil de dificuldade por modelo (o achado a dimensionar no artigo)

**Decisão de desenho (2026-07-28): o prompt é UM instrumento uniforme.** Um
protótipo de direcionamento por família de modelo chegou a ser implementado e
foi **removido por decisão do autor**: a evidência e o direcionamento genérico
vão nos templates, iguais para todos, e se um modelo não chega à resposta com o
direcionamento correto, isso é exatamente o que o experimento mede. Prompt
calibrado por modelo quebraria a comparabilidade (cada LLM medida por um
instrumento diferente) e mascararia as diferenças que o artigo quer dimensionar.
Os perfis abaixo são, portanto, resultado — não defeito a compensar.

Taxonomia dos mecanismos de erro observados (com o prompt idêntico):
**colapso de moda** (responder o ambiente mais frequente, ignorando a
evidência), **eco de contexto** (copiar um dado do prompt como resposta),
**indisciplina de valor** (JSON válido com valor fora do formato/vocabulário),
**ancoragem no limite normativo** (responder o critério de aprovação em vez de
calcular) e **hiperespecificidade** (qualificação técnica no lugar do termo de
planta).

- **gemma2:9b** — melhor geral; único forte nos 2 datasets. Fraquezas: grafia
  do token de Category (19/47 erros eram formato: "LIVING ROOM", `_BEDROOM_`),
  térmico de laje ancorado em ~1,85-2,0 (limite normativo do piso, apesar da
  ATENÇÃO) e minutos trocados no fogo.
- **qwen3.5:4b** — melhor no fogo (4/6); térmico bom em parede/janela, ancora
  em 2,0 nas lajes. No masked despenca (0,23; top3 0,29 — o certo nem está no
  top-3): nomes hiperespecíficos ("Área Técnica de Esgoto", "Ambiente Técnico
  (Sifonagem)") no lugar do termo de planta.
- **qwen3.5:9b** — sistema 1,00; masked com o mesmo vício de nome técnico
  ("Área Técnica …" em 15+ estímulos). Fogo colapsa em escada EI 60/90/120
  (0,17 por estímulo, 0,007 por issue: erra exatamente os estímulos grandes) e
  Category ecoa números do contexto (área, nome numérico).
- **qwen2.5:7b-instruct** — obediente a vocabulário; fogo em escada EI fixa;
  masked devolve a classe de função da INFERÊNCIA como nome final ("Passagem
  Vertical") e tem 22 acertos presos no top-3 (problema de ordenação). Térmico
  emite 1,23456789/1,894… (placeholder e limite normativo).
- **llama3.1:8b** — sólido em sistema (0,82)/LoadBearing; fogo com EI em tudo
  (até E em escada); térmico bimodal (janelas certas, 10 estímulos em
  subestimativa >50%); Category com coringas LIVING_ROOM/TECHNICAL_AREA.
- **granite4:tiny-h** — surpresa do masked (0,43, 3º) e rápido (p50 3,8 s).
  Térmico: **0/19 com padrão único** — 10 estímulos entre 10-20% abaixo do
  cálculo (soma resistências a mais); fogo em escada R 30/60/90.
- **mistral:7b** — masked ok (0,41); resto colapsa: fogo **0/6 com classes de
  uma letra** (E 60, R 30 — não cumprem requisito de compartimentação), sistema
  com classes IFC inventadas, térmico caótico (237, 568 = eco de números).
  Top-3 do prédio é 0,54: o conhecimento existe, o top-1 é indisciplina.
- **falcon3:7b** — janelas térmicas 8/8, e no masked a patologia mais clara da
  matriz: top-1 fixo "Sala de Estar" (43×) com o acerto no top-3 (26×) —
  ordena por prior, não por evidência. Category colapsa em OFFICE/KITCHEN;
  térmico emite absurdos (1296449).
- **phi4-mini** — mais rápido (p50 3,5 s), pior qualidade. No masked nomeia o
  ambiente com a linha de CONTEXTO ("Residencial Multifamiliar - Zona
  Bioclimática 3", 48×) — não entende o escopo da tarefa. Fogo R 90 fixo;
  térmico 0/19 em subestimativa profunda; sistema ecoa nome do objeto.
- **lfm2.5:8b** — colapso de moda extremo: Category → BEDROOM (46/77!),
  masked → "Sala de Estar" (38×); sistema ecoa nomes do objeto.

## 5. O que NÃO é fraqueza de modelo (decisões de GT/experimento)

1. **Fogo, 2 estímulos "todos erram" = 429/1020 issues (42% do estrato):** o
   IFC entrega `LoadBearing: False` nessas paredes e o GT pede classe de
   parede portante-e-compartimentadora (ambiguidade já documentada: critério
   estrito vs prática de compartimentação). Os modelos que respondem EI estão
   **seguindo a evidência dada e o critério do template**. Não é corrigível por
   prompt sem vazar gabarito — é decisão de GT (aceitar EI como alternativa, ou
   documentar o critério da prática como regra do experimento).
2. **Térmico de lajes (5 estímulos GT 3,2):** o prompt contém tudo e o cálculo
   correto dá o GT; os modelos respondem o limite normativo (~2,0). A memória
   de cálculo obrigatória (v6) ataca isso, mas o padrão "responder o limite" é
   um achado de comportamento a reportar no artigo.
3. **Telhados e Category:** eram lacunas de evidência (seção 2) — já corrigidas;
   os números de 2026-07-28 nesses estratos medem o pipeline velho.
4. **GT herda erro do modelo:** "Casa de Hidrômeros" (typo no LongName do
   arquivo) está como expected no GT de nomeação.

## 6. Mudanças aplicadas (prompt v6) e como re-medir

- `material_reader.py`: herança de material via `IfcRelAggregates` (telhados).
- `pset_diagnostics.py`: `long_name` no contexto de Category.
- `prompt_templates.py` (v6): linha LongName + "evidência primária" no
  Category; PROCEDIMENTO (TRRF → letra → 3 hipóteses distintas) no fogo;
  VERIFICAÇÃO OBRIGATÓRIA (memória de cálculo numérica + ordem de grandeza) no
  térmico de parede e laje; no space: pia decidida pelo conjunto, vaso
  sanitário ≠ vaso de planta, equipamento de combate a incêndio → circulação,
  série homogênea → nomear pelo conteúdo, dezenas de assentos → uso coletivo.
  Tudo **genérico e idêntico para todos os modelos** — o direcionamento por
  família de modelo foi prototipado e removido (ver seção 4).
- Guardrail: suíte inteira verde; `test_prompt_nao_vaza_gabarito` passa sobre
  os templates novos. (Durante o protótipo descartado, a mesma varredura pegou
  um vazamento acidental — a palavra "Entrada", alternativa aceita no GT — o
  que confirma o valor de rodá-la sobre qualquer texto novo de prompt.)

**Nota metodológica (importante para o artigo):** os complementos de template
foram escritos DEPOIS de olhar os erros — exatamente a condição da lição dos
13,6 pp. As defesas: (a) conteúdo restrito a evidência do arquivo, processo e
procedimento normativo, jamais valor, faixa ou nome do GT; (b) guardrail
automatizado sobre os templates; (c) prompt idêntico para todos os modelos;
(d) v5 e v6 ficam distinguíveis pelo `prompt_version` no metadata — reportar
como condições separadas, e o ganho de v6 deve ser lido como correção de
evidência + engenharia de prompt genérica informada por análise de erro, não
como capacidade nova de modelo. Para validar barato antes de refazer a matriz:
`scripts/mede_estrato.py` num estrato por vez (~5 min), começando por Category
(maior efeito esperado: LongName) e térmico de laje.
