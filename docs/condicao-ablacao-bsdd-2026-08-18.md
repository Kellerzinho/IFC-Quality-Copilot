# Condição ablação-bSDD — quanto o bSDD compra, com tudo o mais constante (2026-08-18)

Primeira condição a medir **grounding** em vez de **modelo**. Todas as rodadas
anteriores (v7.5 a v7.7, escala-4070) variaram a população de LLMs com o
instrumento fixo; esta fixa a população e varia **uma parte do instrumento**: o
bloco de contexto bSDD injetado no prompt.

A pergunta: **o grounding bSDD, tal como o bSDD entrega hoje para o dicionário
IFC 4.3, muda a qualidade das sugestões?** E, se muda, em quais estratos e em
que direção.

A ablação de grounding foi projetada em jun/26 e **removida** (commit `c767e46`,
2026-06-27) porque era código morto: produzia três execuções idênticas rotuladas
como condições diferentes — `docs/revisao-critica-2026-06-09.md:44-48` chamou
isso de "erro grave de validade interna se publicado". Esta condição a reabre
pela primeira vez com instrumento congelado, telemetria por issue e verificação
de que o tratamento é o que se diz que é.

**Isto não é um v7.8.** O arquivo `prompt_templates.py` não é tocado —
`PROMPT_VERSION` e `prompt_sha256` permanecem os do v7.7. O que muda é se o
pipeline **consulta** o bSDD. Como a identidade de execução não tem hoje nenhum
campo de grounding (§5), a rodada só ganha identidade própria com o campo novo
declarado em §5 — sem ele, ela é indistinguível da baseline e seria **pulada**
pelo runner.

## 1. Por que este desenho é limpo aqui (medido, não presumido)

O risco clássico desta ablação é **confundir tratamento com roteamento**:
`_should_use_compact` (`src/suggestion_engine/suggestion.py:351-352`) retorna
`False` quando `is_grounded` vira falso, e `is_grounded` é
`bool(grounding_sources)` (`src/suggestion_engine/grounding.py:64-66`).
Desligar o bSDD zeraria `grounding_sources` e poderia trocar a família de
prompt — medindo duas coisas ao mesmo tempo.

Três medições feitas em 2026-08-18 sobre os artefatos da rodada escala-4070
mostram que, **neste conjunto de estímulos**, isso não acontece:

1. **Cobertura de bSDD é total e o IDS não participa do grounding por issue.**
   Nos 4.983 itens (303 representantes), `grounding_sources` é `['bsdd']` em
   **100%** e `bsdd_source_status` é `live` em **100%**. Nenhum item tem
   `'ids'`: as issues vêm do diagnóstico programático, não de regras IDS
   (`issues_from_ids: 0` contra `ids_rules: 5` nos `run_0.json`). Consequência
   de desenho: **a única ablação possível hoje é a do bSDD** — o IDS já está
   efetivamente ausente do prompt por issue, e isso é em si um achado a
   declarar no artigo.
2. **Todo estrato medido tem template rico.** Os dez estratos do experimento
   (`AcousticRating`, `Category`, `FireRating`, `HasNonSkidSurface`,
   `IsLoadBearing`, `LoadBearing`, `SolarHeatGainCoefficient`,
   `ThermalTransmittance`, `relation_broken`, `system_unclassified`) são todos
   cobertos por `has_rich_template` (`prompt_templates.py:1144-1155` +
   `_specialized_pset_template_key:1095-1121`). Não há `space_unnamed` na
   população.
3. **O `PromptRouter` está desligado no benchmark.** Não há nenhuma referência
   a `prompt_router` em `src/experiment/runner.py`, logo
   `self.prompt_router is None`.

Com (2) e (3), os dois braços chamam **a mesma função com o mesmo template**:

| | caminho | chamada |
|---|---|---|
| baseline (bSDD on) | `suggestion.py:172` → `use_compact and has_rich_template` | `build_prompt(issue, …, bsdd_context=<ctx>, ids_context=None)` |
| ablação (bSDD off) | `suggestion.py:197` → `else` (router é None) | `build_prompt(issue, …, bsdd_context=None, ids_context=None)` |

O delta é exatamente **o bloco `BSDD_CONTEXT:`** no user prompt
(`_inject_grounding`, `prompt_templates.py:1541-1543`) e **a instrução de
grounding** no system prompt (`:1544-1546`, condicionada a
`ids_context is not None or bsdd_context is not None`). Os dois compõem o
tratamento porque são o que desaparece quando não se tem bSDD — é o
contrafactual realista, não uma amputação artificial.

## 2. O que o bSDD realmente entrega (e por que o efeito pode ser pequeno)

`has_official_candidates` é **False em 100%** dos 4.983 itens. Ou seja: o bSDD
**não** está fornecendo vocabulário fechado (`allowed_values` nulo nas
propriedades do experimento, como `docs/revisao-bsdd-2026-08-04.md` já
registrou). O que ele entrega é **classe oficial + URI canônica**, mais tipo de
dado/unidade quando a propriedade existe no dicionário.

A causa é estrutural, não uma lacuna pontual: o único dicionário consultado é
`{"IFC": ".../ifc/4.3"}`, que espelha o **schema** IFC, e o schema tipa
`FireRating` e `AcousticRating` como `IfcLabel` — texto livre. Medido no cache
em 2026-08-18: **0 de 233** propriedades de `IfcWall` têm `allowed_values`. A
própria resposta do bSDD declara o motivo ("in IFC this property takes
'IfcLabel' as value. Such objects are not included in bSDD for simplicity
reason"), e essa nota é filtrada como boilerplate antes de entrar no prompt
(`_is_boilerplate`, `src/models.py:333`). Com `allowed_values` nulo, o bloco
do prompt imprime literalmente `livre` (`src/models.py:411`). Enumerações
existem no bSDD apenas em dicionários que as definem (classificações
nacionais, de fabricante); não há dicionário publicado que enumere classes de
resistência ao fogo pela NBR 14432. *(Emenda de 2026-08-18, mesmo dia, antes
de qualquer execução: censo ao vivo do catálogo confirmou — 426 dicionários,
11 pt-BR, nenhum ABNT/normativo e nenhum com valores de desempenho; o
mecanismo `allowedValues` funciona no próprio dicionário IFC onde o schema
define PEnum, p.ex. `Status`. Fatos e método em
`docs/auditoria-bsdd-ids-2026-08-18.md`.)*

**Onde então está o vocabulário normativo?** Nos templates — mas de forma
heterogênea, o que importa para o desenho da extensão (§8). Medido template a
template em 2026-08-18: `pset_missing_fire` **não traz lista alguma**, só a
norma e a gramática das letras (R / E / I / REI / EI) a partir da qual o
modelo compõe o rótulo; `pset_missing_space_category` traz menu fechado
explícito (tokens do próprio schema IFC); `system_unclassified` traz uma lista
de sistemas "comuns" (tipologia de literatura); `pset_missing_acoustic` traz
tabela tipológica; `pset_missing_thermal` traz constantes (Rsi 0,13 / Rse
0,04), tabela de λ e banda de plausibilidade. Dizer que "o vocabulário fechado
vem dos templates" é correto para Category e impreciso para o maior estrato do
experimento, que é o de fogo.

Portanto a hipótese honesta é de **efeito modesto**, e um resultado nulo é
publicável e útil: diria à comunidade openBIM que o bSDD, no estado atual do
dicionário IFC 4.3, contribui pouco além da âncora de classe quando o prompt já
carrega a norma. Declarar isso **antes** de medir é o que impede a leitura
oportunista do resultado depois.

Há precedente de efeito **negativo** por via indireta: o comentário em
`prompt_templates.py:1135-1141` registra que o bSDD, ao resolver a classe do
elemento e tornar `is_grounded=True`, roteava `relation_broken` para o prompt
compacto e zerou aquele estrato em 20/20 estágios nas rodadas v7.5 e v7.6. Com
o v7.7 isso foi corrigido, mas o episódio é o motivo de a verificação da §1 ser
obrigatória e não opcional.

## 3. Desenho: um braço novo, baseline já medida

Como na escala-4070, **o lado de referência não é re-rodado**. A perna do par
unificado v7.7 já é o braço "com bSDD": mesma máquina, mesma release, mesmos
estímulos, mesmos modelos. Esta condição roda apenas o braço **sem bSDD** e
compara **item a item, pareado por `issue_id`**.

- **População:** os 10 modelos do lock do par v7.7 (`5cab7c70…`), que rodam em
  8 GB. Razão: permite executar em qualquer uma das duas máquinas e mantém a
  baseline pareada disponível nas duas.
- **Máquina:** preferencialmente a **RTX 4070** (baseline = perna de 13/08,
  `RESULTADO_IFCQC_20260813T164437Z…`). Fallback declarado: **RTX 4060**
  (baseline = perna de 14-15/08, `…20260814T174140Z…`). A máquina escolhida
  **define** a baseline e deve ser declarada no fechamento; misturar pernas é
  proibido, porque o par mediu deslocamento de mediana 2,3 pp e até 7,1 pp só
  por trocar de GPU.
- **Datasets:** os dois (`casa` 263/101 e `predio` 4720/202), sem mudança.
- **Réplica:** 1, como em toda rodada oficial.
- **Custo:** 4,35 h na 4070 (soma medida dos estágios do par); ~7,4 h na 4060
  em regime overnight.

Unidade de análise: **classe de equivalência** (303 gerações independentes por
modelo), com McNemar exato bicaudal sobre os representantes; os itens (4.983)
entram como leitura secundária ponderada, exatamente como no par e na escala.

## 4. Hipóteses declaradas antes da medição

1. **Efeito agregado pequeno** (|Δ| < 5 pp por classe no pool dos 10 modelos),
   pelo argumento da §2.
2. **`system_unclassified` é o estrato com maior chance de efeito positivo**: é
   o único onde `_scoped_bsdd_context` (`prompt_templates.py:1568`) poda
   ativamente classes `Ifc*` para montar o bloco, ou seja, onde o conteúdo
   bSDD é mais específico da tarefa.
3. **`FireRating`, `AcousticRating` e `ThermalTransmittance` mudam pouco**: o
   valor vem da norma carregada no template, não do dicionário.
4. **Efeito heterogêneo entre modelos**, com os menores mais sensíveis à
   remoção da âncora de classe.
5. **Sem mudança de roteamento** — verificável sem GPU (§6) e condição de
   validade da rodada: se o roteamento mudar, a rodada é descartada.

## 5. Implementação e identidade (o ponto que não pode ser esquecido)

Kill-switch mínimo: `QualityPipeline` já tolera ausência de bSDD —
`_issue_bsdd_context` (`src/pipeline.py:894-895`) retorna `None` quando
`self.bsdd_builder is None`. Basta um parâmetro `use_bsdd: bool = True` em
`QualityPipeline.__init__` que suprima a instanciação em `pipeline.py:121-122`,
propagado por `ExperimentRunner.run_single` (`src/experiment/runner.py:308-326`)
e pelo argparse de `scripts/run_benchmark.py` (`:1194`, chamada em `:1306`).
Ordem de grandeza: ~25 linhas.

**A parte obrigatória e não óbvia:** `ExecutionIdentity`
(`src/experiment/execution_identity.py:119-145`) não tem campo de grounding, e
`prompt_sha256` é o SHA do **arquivo** `prompt_templates.py` — que esta condição
não toca. Sem um campo novo, a rodada de ablação produz
`execution_identity_sha256` **idêntico** ao da baseline, e
`_stage_expectation`/`_stage_done` (`scripts/run_benchmark.py:429-493`) tratam
os estágios como já concluídos e os **pulam**. Acrescentar
`grounding_bsdd: bool` exige tocar:

- `execution_identity.py`: dataclass, `_require_exact_keys` (`:170-201`, que
  exige igualdade exata do conjunto de chaves), `_parse_execution_identity`
  (`:202-306`);
- `scripts/windows_benchmark.py::build_execution_identity` (`:301-430`);
- fixtures `tests/test_run_benchmark.py:33-70` e
  `tests/experiment/test_execution_identity.py`;
- regenerar `execution-identity.json` e reconstruir a release.

Invariantes oficiais que **permanecem** e seguem validadas
(`run_benchmark.py:312-329`): `replica_count == 1`, `cache_enabled == False`,
`reuse_equivalent == True`, `prompt_version == PROMPT_VERSION`.

Ferramenta de análise: **nada a construir**. `IssueOutcome` já exporta
`grounding_sources`, `bsdd_source_status`, `bsdd_class_uri` e
`has_official_candidates` por issue (`src/experiment/per_issue.py:78-84`), e
`paired_comparison` no mesmo módulo faz o teste pareado por estímulo.

## 6. Verificação obrigatória antes de gastar GPU

O delta de prompt é mensurável **sem GPU**, em ~2 min, com as ferramentas que
já existem — e é o que separa esta condição da tentativa abandonada de jun/26:

```bash
# 1. Despejar os prompts dos dois bracos e diferenciar
python scripts/dump_prompts_spy.py --out /tmp/prompts_on.jsonl
python scripts/dump_prompts_spy.py --no-bsdd --out /tmp/prompts_off.jsonl
python scripts/diff_prompts.py /tmp/prompts_on.jsonl /tmp/prompts_off.jsonl
```

O script `scripts/verifica_ablacao_bsdd.py` (novo) implementa os critérios e
sai com código ≠ 0 se algum falhar.

Critérios de aceitação, **todos obrigatórios**:

1. Os dois braços produzem prompts **diferentes** em 100% dos estímulos (se
   algum for idêntico, o kill-switch não funcionou — foi exatamente o defeito
   de jun/26).
2. O **template base é o mesmo** nos dois braços para todos os estímulos: a
   diferença se limita ao bloco `BSDD_CONTEXT:` e à instrução de grounding no
   system prompt. Qualquer estímulo cuja família de template mude **invalida**
   a rodada (§4.5).
3. `grounding_sources` fica vazio no braço off e `['bsdd']` no braço on, em
   100% dos estímulos.
4. `prompt_sha256` **não muda** (o arquivo não foi tocado);
   `execution_identity_sha256` **muda** (campo novo).
5. Ground truth sem deriva: `python scripts/build_ground_truths.py --dataset all --check`.

## 7. O que pode invalidar a rodada

- **Roteamento mudou** em algum estímulo (§6.2) — descartar e redesenhar.
- **bSDD indisponível na baseline**: a comparação exige `bsdd_source_status:
  live` no braço on. Se a rodada de referência tivesse `offline`, os braços
  seriam parcialmente iguais. Medido: 100% `live` no par e na escala.
- **Mistura de máquinas** entre braço e baseline (§3).
- **Deriva do cache bSDD**: `bsdd_cache_sha256` é registrado no metadata; se
  divergir da baseline, declarar. O braço off não consulta o bSDD, então o
  cache não participa dele — a checagem vale para confirmar que a baseline
  usada é a que se diz.

## 8. Extensão prevista: ablação da camada normativa dos templates

Declarada aqui como extensão, **não executada** nesta condição. Origem: se o
bSDD entrega apenas âncora de classe e tipo (§2), então o conhecimento
normativo que sustenta o desempenho está nos templates — e medir só o bSDD
deixaria a parte grande sem medição. As duas ablações são complementares e
formam, com o masking já medido, a decomposição de onde vem o desempenho do
sistema:

| camada removida | o que isola | estado |
|---|---|---|
| evidência do arquivo IFC | quanto vale ler o modelo | **medido** (masking, matriz v6: +31,2 pp) |
| contexto bSDD | quanto vale o openBIM padrão | esta condição (§1-§7) |
| camada normativa dos templates | quanto vale o conhecimento que nós injetamos | **esta extensão** |

### 8.1 Taxonomia das camadas do prompt

O template não é um bloco monolítico. Para ablação, sete camadas distintas:

1. **Evidência do arquivo** — `material_layers`, `thickness_m`, `load_bearing`,
   `is_external`, `area_m2`, adjacências.
2. **Referência normativa** — o nome da norma (NBR 14432, 15220-2, 15575-4/5).
3. **Critério semântico** — a gramática (R/E/I/REI/EI; vedação × estrutural).
4. **Constantes e tabelas** — λ, Rsi/Rse, R da câmara de ar, tabela acústica.
5. **Vocabulário fechado** — tokens de `Category`, lista de sistemas comuns.
6. **Guardas de plausibilidade** — p.ex. "parede típica entre 1,5 e 3,5 W/(m²·K)".
7. **Contrato de formato** — JSON, memória estruturada, tokens em maiúsculas.

**O braço remove 2–6 e preserva 1 e 7.** Preservar o formato é condição de
validade: sem ele, mede-se quebra de parsing, não falta de conhecimento — o
mesmo confounding que a §1 evita no roteamento.

### 8.2 Ablacionabilidade por estrato (não é uniforme)

- **`FireRating` (1.543 itens) — o caso mais limpo.** Remove-se a norma e a
  gramática das letras; o formato do rótulo não é ditado pelo template hoje, e
  o comparador aceita a banda de equivalência do GT. Mede se o modelo conhece
  a NBR 14432.
- **`ThermalTransmittance` (644) — limpo e informativo.** `thermal_recompute.py`
  usa o λ, o Rsi e o Rse **declarados pelo modelo** (`:170`, `:199`), não
  constantes próprias — remover a tabela do prompt mede diretamente se o
  modelo sabe as condutividades, e o código segue refazendo a soma. A guarda
  de plausibilidade (camada 6) deve ser um sub-braço separado: a memória do
  projeto registra que faixa no prompt vira âncora.
- **`AcousticRating` (899) — limpo, e o mais sensível a circularidade.** A
  tabela tipológica do template e o gabarito tipológico saem da mesma fonte
  autoral; esta é a ablação que melhor testa essa circularidade.
- **`system_unclassified` (940) — atenção ao formato.** Sem a lista de sistemas
  comuns, a resposta vira texto livre e o casamento por string normalizada
  pode falhar por forma, não por conteúdo. Exige verificação prévia do
  comparador ou tratamento como resultado parcial declarado.
- **`Category` (95) — excluir do braço principal.** O menu é simultaneamente
  vocabulário (camada 5) e contrato de formato (camada 7): sem os tokens, o
  modelo responde "Quarto" e o comparador não casa. Removê-lo mede protocolo,
  não conhecimento. Se medido, que seja em braço próprio e declarado como tal.

### 8.3 Diferenças de contrato em relação à ablação de bSDD

- **Identidade: automática.** A extensão **toca** `prompt_templates.py`, logo
  `prompt_sha256` muda e a rodada ganha identidade própria sem precisar do
  campo `grounding_bsdd` da §5. Em compensação, o contrato do projeto exige
  bumpar a versão: usar um identificador de **variante**, não um sucessor
  (sugestão: `v7.7-abl-norma`), deixando explícito que **v7.7 permanece o
  instrumento oficial** e que esta variante não entra na linha principal.
- **Custo maior de autoria.** Não é uma flag: é um segundo conjunto de
  templates, mantido em paralelo e byte a byte justificado. O risco de
  introduzir diferenças acidentais (espaçamento, ordem de campos) é real, e é
  o que `scripts/diff_prompts.py` existe para pegar.
- **Mesma verificação prévia sem GPU** da §6, com um critério adicional: o
  diff entre baseline e braço deve tocar **apenas** as camadas 2-6, em todos
  os estímulos.
- **Mesma baseline e mesma máquina** da §3.

### 8.4 Ordem recomendada

Executar a ablação de bSDD (§1-§7) **primeiro**: é mais barata, tem desenho
mais limpo e sua verificação prévia valida o protocolo de ablação que esta
extensão reutiliza. Só depois autorar a variante de templates.

## 8-bis. Fase 1 executada — implementação e verificação (2026-08-18)

Implementado no mesmo dia da redação, **antes** de qualquer rodada. O que
existe agora:

- **Kill-switch**: `QualityPipeline(..., use_bsdd=False)` não instancia
  `BSDDClient` nem `BSDDContextBuilder` (`src/pipeline.py:71-140`);
  `_issue_bsdd_context` já devolvia `None` sem builder.
- **Propagação**: `ExperimentRunner.run_single/run(..., use_bsdd=...)`, com
  guarda que **recusa** divergência entre o braço e
  `execution_identity.grounding_bsdd`; CLI de pesquisa e oficial ganharam
  `--no-bsdd`; `RunMetadata.grounding_bsdd` registra o braço no artefato.
- **Identidade**: campo `grounding_bsdd: bool = True` em `ExecutionIdentity`,
  obrigatório e tipado no snapshot (`_parse_execution_identity`), construído
  por `windows_benchmark.build_execution_identity` e conferido contra a flag
  antes do primeiro estágio. Vetor dourado do hash canônico recalculado
  (`13f5dc1718b8…`; anteriores registrados no teste).
- **Operação**: `install.ps1 -NoBsdd` e o lançador de duplo clique
  **`EXECUTAR_ABLACAO_SEM_BSDD.cmd`**, documentado no LEIA-ME.
- **Testes**: `tests/test_ablacao_bsdd.py` (14 casos) trava identidade,
  snapshot, kill-switch no `__init__` real e coerência nas duas pontas.
  Suíte completa: **1606 passando**, 2 skips de smoke Windows.

**População restaurada ao lock do par v7.7** (`c37c0a6f04c4…`, 10 modelos que
rodam em 8 GB, soma 45.852.962.404), conforme §3. O lock da escala-4070
(`a5e25d13…`) permanece recuperável em `b655a54` e reautorável por
`scripts/lock_from_registry.py`; rodar a ablação sobre a população de 12 GB é
possível, mas exige emenda datada aqui e usaria a escala-4070 como baseline.

**Release `ifcqc-2026-08-18-7ecdd1d0aff3`** — prompt `751ec1679d46…`
(byte-idêntico ao das rodadas anteriores) e lock do par.

### Resultado da verificação sem GPU (§6), executada

Dumps de 202 estímulos por braço (`dump_prompts_spy.py`, dataset predio):

1. **prompts diferentes: 202/202** — o kill-switch chega a todo estímulo.
2. **template base idêntico: 202/202** — removido o bloco `BSDD_CONTEXT` e
   normalizada a instrução de grounding do system prompt, os prompts coincidem
   byte a byte em todos os dez estratos. **O confounding de roteamento temido
   na §1 não se materializou: está medido, não presumido.**
3. **identidade distingue os braços**: confirmado.
4. **`prompt_sha256` inalterado**: `751ec1679d46…`, igual ao da baseline.

O que sai do prompt no braço off, agregado: `BSDD_CONTEXT:` e
`bSDD source_status: live` (186 estímulos — os 16 restantes são
`system_unclassified`, cujo bloco já vinha podado por `_scoped_bsdd_context`),
as definições oficiais de classe, as linhas de propriedade (todas com valores
`livre`, coerente com a §2) e a instrução de grounding no system prompt.

**Pendente:** apenas a execução — extrair a release no disco escolhido e dar
duplo clique em `EXECUTAR_ABLACAO_SEM_BSDD.cmd` (4h22 na 4070 pela telemetria
do par; ~7,4 h na 4060). O braço com bSDD **não** é re-rodado.

## 9. Estado na publicação

Condição redigida em 2026-08-18 **antes** de qualquer implementação, e
implementada no mesmo dia (§8-bis) **antes** de qualquer medição com LLM. O
instrumento não mudou: `PROMPT_VERSION` segue `v7.7` e `prompt_sha256`
permanece `751ec1679d46…`. Nenhuma rodada de ablação foi executada até aqui —
o que existe é a instrumentação, a release e a verificação sem GPU aprovada.
A extensão da §8 permanece apenas **declarada**: não existe variante de
templates.

As medições que fundamentam §1, §2 e §8 foram feitas sobre artefatos já
publicados (rodada escala-4070, `RESULTADO_IFCQC_20260817T131446Z…`), sobre o
cache `data/cache/bsdd_cache.json` e por leitura direta do código no commit
vigente — não constituem resultado desta condição.

O resultado oficial do eixo principal (par unificado v7.7) e o do eixo de
escala (escala-4070) permanecem inalterados; esta condição adiciona o eixo de
grounding sem tocar em nenhum dos dois.
