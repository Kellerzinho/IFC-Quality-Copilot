# Revisão do uso do bSDD — 2026-08-04

Pedido do autor: "corrigir o uso do bSDD". Revisão medida contra o cache
versionado do experimento (`data/cache/bsdd_cache.json`) e o código em
`fase0-experimental`. Commits desta revisão: `8b3faea` (matcher), `f927425`
(proveniência), `667d818` (poda), `ffc6a23` (style). Suíte: **976 verdes**.
Nenhum benchmark foi executado — a medição fica com o autor.

## 1. O que o bSDD efetivamente entrega (medido, não inferido)

Censo das 53 consultas registradas no cache versionado do run:

| tipo de consulta | n | resolvem |
|---|---|---|
| classe nua (`IfcWall`, `IfcSpace`, ...) | 10 | **10/10** |
| compostas (`IfcWall FireRating`, `IfcSpace OmniClass Table 13`, `{classe} classification`, nomes de família Revit) | 43 | **0/43** |

O endpoint de busca procura **classes**; o fallback de classe nua carregava
100% do grounding e as compostas eram custo HTTP puro.

Nas propriedades do experimento, o dicionário IFC 4.3 devolve **tipo de dado**
(FireRating=String, LoadBearing=Boolean, ThermalTransmittance=Real) mas
**`allowed_values` e `unit` nulos** — verificado nas entradas `property_uri`
do cache. Isso **não é bug**: o dicionário não enumera valores para elas.

**Formulação correta para o artigo:** o grounding bSDD entrega a **classe
oficial com URI canônica** e, quando a propriedade existe no dicionário, o
**tipo de dado e a URI canônica da propriedade**. Todo vocabulário fechado
que os modelos veem (classes de fogo, faixas térmicas, rótulos de ambiente)
vem dos **templates de prompt**, não do bSDD. O dossiê foi anotado.

## 2. Quatro comparações de nome eram no-ops silenciosos (corrigidos)

O client entrega `name` humano (`"Fire Rating"`); IFC/IDS usam PascalCase
(`"FireRating"`). Quatro consumidores comparavam literalmente e **nunca
casavam**:

| consumidor | efeito do no-op |
|---|---|
| `grounding.prepare_llm_grounding` | tipo/unidade do bSDD nunca chegavam ao prompt nem à assinatura de cache |
| `SuggestionGenerator._validate_against_bsdd` | a validação pós-LLM contra vocabulário **nunca executou em nenhum run** |
| `normalization.resolve_bsdd_uri` | sugestão aplicada sem URI canônica da propriedade |
| `QualityPipeline._default_bsdd_uri` | auditoria apontava a URI da **classe** em vez da propriedade |

Causa raiz única: `get_class_properties` descartava o `code` PascalCase na
conversão legada. Os testes antigos usavam PascalCase **dos dois lados** e
mascaravam tudo — os testes de regressão novos usam o nome humano, como o
client real produz. Matcher único em `src/semantic/property_match.py` (mesma
regra já validada de `_filter_properties`, incluindo o prefixo booleano
`Is*`), consumido pelos quatro pontos.

Importante para a integridade dos números: como o defeito era **no-op** (e
não falso positivo), **nenhum run anterior foi contaminado** — nada foi
rebaixado indevidamente; a camada simplesmente não existia na prática.

## 3. Delta do instrumento: prompts byte-idênticos (medido com espião)

`scripts/dump_prompts_spy.py` (harness real, LLM substituído por espião, sem
GPU) antes e depois do fix, no prédio completo: **202/202 estímulos com
system e user byte-idênticos** (`scripts/diff_prompts.py`).

Por que nada mudou no texto: os estratos de pset caem nos **templates ricos**
(que injetam o bloco bSDD via `format_bsdd_context`, caminho que sempre esteve
correto); nenhum estímulo do prédio cai no template genérico grounded (único
que renderiza `tipo_dado`/`unidade` do `GroundedIssueContext`); e Category
não existe no dicionário. Além disso, `_validate_against_bsdd` roda **depois**
da ordenação por confiança e não há re-sort — o rebaixamento muda o rótulo de
confiança, não a ordem.

**Consequência: o v6.1 é, por construção, neutro em `match_top1`/`match_top3`
no prédio.** Efeitos possíveis: `confidence_top1` menor onde houver tipo
incompatível e o marcador na `justification`. `PROMPT_VERSION` avançou para
`v6.1` mesmo assim — assina o cache de sugestões (payloads podem diferir) e a
capacidade de `tipo_dado` vale para datasets que caiam no template genérico.

Guardrail de vazamento: não há texto novo de prompt (202/202 idênticos), logo
nada a varrer; a suíte de não-vazamento (`test_prompt_nao_vaza_gabarito.py`)
segue verde.

**Decisão de medição (do autor):** re-rodar benchmark sob v6.1 é **opcional**
— serviria só para confirmar a neutralidade prevista acima. A decisão de
medição que importa continua sendo a de `docs/resultado-matriz-v6-2026-08-03.md`
(reportar v5+v6 vs. montar v7).

## 4. Poda das consultas mortas

`_build_search_queries` emite agora **só a classe nua** (1 chamada por issue;
eram até 4). O `BSDDContext` resultante é idêntico — todas as consultas
removidas retornavam zero. Se um dia OmniClass/Uniclass entrarem, a consulta
certa é pelo `dictionary_uri` próprio, não texto composto contra o IFC 4.3.

## 5. Proveniência de grounding no JSONL por issue

`run_0_issues.jsonl` tinha 20 campos e nenhum sobre grounding — impossível
provar pelos artefatos o que o bSDD entregou em cada issue. Novos campos em
`SuggestionMetrics` e `IssueOutcome`: `grounding_sources`,
`bsdd_source_status`, `bsdd_class_uri`, `has_official_candidates`. Issues
reusadas herdam da primária (mesmo estímulo). JSONLs antigos seguem parseando
(defaults; verificado contra as 2546 linhas do run v6).

Nota: a ablação de grounding foi abandonada em jun/26 (dossiê §"artigo");
estes campos não a reabrem — tornam o grounding **auditável**, que é claim
central do fluxo.

## 6. O que NÃO foi tocado (decisões do autor, pendentes)

- Blocos de **procedimento TRRF** e **memória de cálculo** no prompt — intactos.
- **Camada determinística de recomputação térmica** — não implementada
  (condição v7 declarada, `docs/achado-aritmetica-termica-2026-08-02.md`).
- **Decisão v5+v6 vs v7** (`docs/resultado-matriz-v6-2026-08-03.md`, §5).
- **Ratificação da emenda EI/REI** (`data/evaluation/predio/REVISAO_GT.md`).
- Dívidas F15/F8 (`docs/dividas-tecnicas.md`) — condições de resgate não atendidas.

## Método

Espião + diff: `scripts/dump_prompts_spy.py` e `scripts/diff_prompts.py`
(persistidos; a versão de julho viveu só no scratchpad e se perdeu). Censo:
leitura direta de `data/cache/bsdd_cache.json` (chaves `class_search` e
`property_uri`). RED-GREEN: todos os fixes nasceram de teste falhando com o
nome humano do bSDD. Lint: ruff/mypy limpos nos arquivos tocados (o repo tem
baseline de avisos ruff pré-existente, fora do escopo).
