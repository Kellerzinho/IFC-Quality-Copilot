# Análise comparativa — rodada v7.5 (RTX 4070) × rodada v7.6 (RTX 4060) — 2026-08-13

Estudo minucioso das duas coletas completas existentes, feito para decidir o
fechamento do instrumento **v7.7** (`docs/condicao-v7-7-2026-08-13.md`) e o
protocolo do par unificado de rodadas (4070 + 4060, mesma release). A conclusão
antecipada: **as duas rodadas não são diretamente comparáveis** — quatro
dimensões mudaram juntas — mas a análise por estrato, por modelo e por classe de
equivalência separa o que é robusto do que é confundido, e localizou três
defeitos de instrumento que o v7.7 corrige.

## 1. As duas condições

| dimensão | rodada v7.5 | rodada v7.6 |
|---|---|---|
| data | 2026-08-10 | 2026-08-12/13 |
| GPU | RTX 4070 (externa) | RTX 4060 Laptop 8 GB (local) |
| Ollama | 0.32.5 (pinado, release) | **0.32.9** (instalação local)* |
| prompt | v7.5 | v7.6 |
| janela de contexto | adaptativa 2048/4096 | fixa 4096 |
| normalização run-side | preenchia classe REI ausente | exige classe declarada |
| gabarito | pré-emenda | emendado 12/08 |
| execução | release oficial `…eb835f2ab43d` | repo-direct, identidade da release `…523b937cc657` |
| réplica/cache/seed | 1 / off / 42 | 1 / off / 42 |

\* A release v7.6 não coube no disco local (exige 55 GiB livres; havia 15).

**Método de comparação:** todos os números abaixo re-pontuam as DUAS coletas com
o comparador e o gabarito vigentes (mesmo critério dos dois lados, via a mesma
rotina de `scripts/rescore_results.py`). Isso isola o efeito de comparador — o
rescore da coleta v7.5 reproduziu exatamente os deltas declarados em
`docs/condicao-v7-6-2026-08-12.md` (+4,70 pp mistral e qwen2.5; +0,76
casa/granite4). O que NÃO é isolável retroativamente: (a) prompt v7.5→v7.6,
(b) Ollama 0.32.5→0.32.9, (c) GPU — mudaram juntos. E uma assimetria
irrecuperável: os `top_values` da coleta v7.5 foram gravados **depois** da
normalização da época, que preenchia REI ausente — parte dos acertos de fogo do
v7.5 carrega classe presumida que não se pode remover do dado gravado.

O diff byte a byte do código empacotado (project.zip da release v7.5 × árvore
atual) confere com o declarado no doc do v7.6: nenhuma mudança não-declarada
entre as rodadas.

## 2. Agregado por modelo (comparador atual nos dois lados)

| modelo | v7.5 top-1 | v7.6 top-1 | Δ pp | v7.5 top-3 | v7.6 top-3 |
|---|---|---|---|---|---|
| gemma2:9b | 0,8005 | **0,8637** | +6,32 | 0,8991 | 0,9131 |
| qwen3.5:4b | 0,7672 | 0,8437 | +7,65 | 0,8704 | 0,9179 |
| qwen3.5:9b | 0,7752 | 0,7991 | +2,39 | **0,9558** | 0,9314 |
| granite4:tiny-h | 0,7036 | 0,7797 | +7,61 | 0,8085 | 0,9061 |
| llama3.1:8b | 0,7576 | 0,7038 | −5,38 | 0,8832 | 0,9251 |
| falcon3:7b | 0,6428 | 0,6301 | −1,26 | 0,8896 | **0,9587** |
| qwen2.5:7b-instruct | 0,5511 | 0,6069 | +5,58 | 0,8810 | 0,9532 |
| mistral:7b | 0,6544 | 0,5653 | −8,91 | 0,7225 | 0,7764 |
| phi4-mini | 0,6542 | 0,5649 | −8,93 | 0,8094 | 0,7961 |
| lfm2.5:8b | 0,6374 | 0,4064 | **−23,10** | 0,7253 | 0,7066 |

Média dos deltas: −1,8 pp, com dispersão de −23 a +7,7 — o agregado não conta a
história; os estratos contam.

## 3. Por estrato — o que é robusto e o que é confundido

| estrato | n/modelo | v7.5 | v7.6 | Δ pp | modelos ↑ | ↓ |
|---|---|---|---|---|---|---|
| AcousticRating | 899 | 0,6266 | 0,8575 | **+23,09** | 8 | 1 |
| LoadBearing (laje) | 29 | 0,5862 | 0,6552 | +6,90 | 1 | 0 |
| ThermalTransmittance | 644 | 0,4200 | 0,4419 | +2,19 | 5 | 3 |
| SHGC | 134 | 0,1754 | 0,1828 | +0,75 | 3 | 2 |
| Category | 95 | 0,7326 | 0,7368 | +0,42 | 3 | 5 |
| relation_broken | 4 | 0,0000 | 0,0000 | 0,00 | 0 | 0 |
| IsLoadBearing | 685 | 0,9439 | 0,8728 | −7,11 | 2 | 2 |
| FireRating | 1543 | 0,7782 | 0,7043 | −7,38 | 2 | 5 |
| system_unclassified | 940 | 0,7085 | 0,5485 | **−16,00** | 2 | 5 |
| HasNonSkidSurface | 10 | 0,3000 | 0,1000 | −20,00 | 1 | 3 |

### 3.1 Acústica: a única mudança do v7.6 com efeito grande, consistente e na direção prevista

+23,09 pp, subindo em 8 de 10 modelos (única queda: lfm2.5, −7,7). As duas
linhas tipológicas novas (porta, drywall simples) removeram a inatingibilidade
dos 214 itens de porta exatamente como o doc do v7.6 previu. **Achado robusto ao
confundidor**: direção consistente entre modelos e mecanismo estrutural (o menor
valor ofertado antes ficava acima do teto da banda aceita).

### 3.2 relation_broken: 0,00 nas DUAS rodadas — o template novo nunca chegou ao fio

Causa raiz encontrada e provada: `relation_broken` não estava em
`_RICH_TEMPLATE_ISSUE_TYPES`. Com o bSDD resolvendo a classe do elemento
(`is_grounded=True`), `SuggestionGenerator.generate` roteava a issue para
`build_compact_prompt` — o template `relation_missing` do v7.6, com o
vocabulário fechado de subtipos de `IfcRelationship`, existia no dicionário e
aparecia em `_select_template`, mas o fio carregava um prompt de metadados sem
pergunta e sem vocabulário. As respostas gravadas confirmam: nomes de elemento
("porta multiplas_growarq:…"), classes inventadas ("IfcDoorVariant") e prosa —
nenhum dos 10 modelos emitiu um único `IfcRel*` em 40 estímulos por rodada.

Corolário: o diagnóstico do doc v7.6 §2 ("os templates pediam 3 ações em
prosa") descrevia templates que **também não estavam no fio** — o defeito das
duas rodadas sempre foi o roteamento. A mesma regressão de 2026-07-27
(rich→compacto), num terceiro issue_type. Corrigido no v7.7 com teste de fio
(`tests/test_condicao_v7_7.py`).

### 3.3 system_unclassified e IsLoadBearing: o roteiro reintroduzido cobrou o preço medido na matriz v6

As duas regressões grandes tocam exatamente os dois templates que receberam, no
v7.6, **evidência nova acompanhada de parágrafo de roteiro**:

- `system_unclassified` −16,0 pp. "Alvenaria estrutural em bloco cerâmico"
  saltou de 953 → 2145 itens no pool de modelos — o parágrafo "VEDAÇÃO OU
  ESTRUTURAL", que ensinava a regra pórtico→vedação, menciona "estrutural" três
  vezes, e os modelos-eco reagiram ao vocabulário, não ao dado (phi4 −68,7 pp;
  mistral −43,0; lfm2.5 −23,7; granite4 −18,7; llama3.1 −17,8 — contra gemma2 e
  qwen2.5 estáveis e qwen3.5:4b +10,3). Apareceu ainda o eco cru do estímulo
  como rótulo ("Gesso Acartonado 10 (1.5cm)", 222 itens — a grafia "1.5cm" é o
  formato novo de camada do v7.6, prova de eco).
- `IsLoadBearing` −7,11 pp, com True subindo de 334 → 858 itens (GT
  majoritariamente False). Heterogêneo ao extremo: mistral −62,6, falcon3
  −39,0, **gemma2 +28,0** (foi a 1,000). O parágrafo "PAREDE EM EDIFICAÇÃO COM
  PÓRTICO" + a diretiva "Decida pelo inventário acima" ajudaram quem raciocina
  e cegaram quem ecoa — o padrão −12,5 pp de procedimento da matriz v6.

Decisão v7.7: **a evidência fica** (`{structural_inventory}`,
`{load_bearing}`); **o roteiro sai**. Ler o inventário é a tarefa que o estrato
mede.

### 3.4 HasNonSkidSurface: a diretiva elegeu o eixo errado para um gabarito de convenção

Os 5 itens (peso 10/modelo) são **escadas** com GT=True. No v7.5, 3 modelos
acertavam True; no v7.6, com o template novo mandando "decidir pelo acabamento
declarado" (concreto → liso → False), **9 de 10 responderam False** (granite4
foi o único a ir para True; gemma2, qwen3.5:4b e qwen3.5:9b desceram de True
para False). O estrato mede concordância com a convenção do gabarito (situação
normativa da NBR 9050 ⇒ True em degrau/rampa), como o SHGC mede concordância
com convenção — mas a diretiva do template pesava só o eixo do acabamento.
Decisão v7.7: a diretiva sai; ficam os dois blocos de conhecimento (escopo
normativo + tipologia de acabamento liso) e a decisão de pesá-los fica com o
modelo. n=5: peso mínimo no agregado, princípio igual ao dos estratos grandes.

### 3.5 FireRating: −7,38 pp que são, na prática, um modelo só

Decomposição por modelo: lfm2.5 **−54,6 pp** e qwen3.5:4b −13,9; os outros oito
ficam em ±3,4. O template de fogo não mudou no v7.6 (só formato de evidência e
bloco bSDD). O lfm2.5 declara classe normalmente nas duas rodadas (100% dos
valores finais com classe) — o que mudou foi a distribuição inteira das
durações no prédio: REI 60×815 + REI 120×530 (v7.5) → REI 30×585 + REI 90×371 +
REI 120×391 (v7.6). Deslocamento em bloco sob perturbação mínima de estímulo +
runtime novo — instabilidade do modelo, não defeito de contrato. Nota: parte
dos acertos de fogo v7.5 (todas as famílias) pode carregar classe REI presumida
pela normalização da época (108 respostas de duração pura medidas no log da
rodada), gravada nos `top_values` — assimetria declarada, irrecuperável.

### 3.6 Térmico, Category, SHGC: dentro do ruído estrutural do desenho

Térmico +2,19 agregado esconde qwen3.5:9b −51,1 e llama3.1 −16,9 contra
granite4 +36,8 e phi4 +33,5. Com `reuse-equivalent`, **uma chamada decide uma
classe de equivalência inteira** (a maior classe de parede tem 262 itens =
5,5% do prédio): flip de um representante move o estrato do modelo em dezenas
de pp. A contagem de flips entre rodadas (representantes com veredito trocado)
ficou entre 11 e 79 por modelo (de 303), movendo 300–1700 itens-peso — réplicas
na MESMA máquina/runtime são bit-idênticas (medido em 2026-08-05), então esses
flips são efeito determinístico da mudança conjunta (prompt+runtime+GPU), não
amostragem. Consequência metodológica: comparação entre condições exige
mesma-máquina-mesmo-runtime, e o n efetivo do experimento é o número de classes
(202+101), não o de itens (4.720+263).

### 3.7 lfm2.5:8b: colapso concentrado, causa não separável nesta comparação

−23,1 pp agregados, quase inteiramente em prédio (fogo −54,6, sistema −23,7 —
este último a 0,0096 com respostas-eco). Hipóteses não separáveis aqui:
sensibilidade do lfm2moe ao runtime 0.32.9 × sensibilidade à perturbação de
estímulo do v7.6. O par unificado (ambas as máquinas em 0.32.5 pinado) decide.

## 4. Decisões tomadas

1. **Instrumento v7.7** (`docs/condicao-v7-7-2026-08-13.md`): roteamento do
   relation_broken corrigido com teste de fio; roteiro removido dos três
   templates (evidência mantida); aliases de comparador que presumiam a função
   da parede removidos. Diff de espião: 192/202 estímulos idênticos ao v7.6,
   10 mudados, todos nas cirurgias declaradas.
2. **As rodadas v7.5 e v7.6 viram pilotos.** O resultado oficial passa a ser o
   par unificado: mesma release v7.7, Ollama 0.32.5 pinado, 4070 (tarde) e
   4060 (noite) — que mede o eixo de hardware com instrumento fixo, além do
   resultado principal por modelo.
3. **O que o par unificado NÃO medirá:** o efeito isolado do prompt v7.6→v7.7
   (nesta máquina, o runtime muda junto de 0.32.9→0.32.5 entre as rodadas de
   12/08 e 13/08). Aceito: o objeto do artigo é a comparação entre LLMs sob o
   instrumento fechado, não a arqueologia dos pilotos.

## 5. Reprodução

```bash
# re-pontuar as coletas com o comparador vigente
python scripts/rescore_results.py <coleta>/ --ground-truth-root data/evaluation

# delta do instrumento sem GPU
python scripts/dump_prompts_spy.py /tmp/v77.json
python scripts/diff_prompts.py /tmp/v76.json /tmp/v77.json

# guardas
pytest tests/test_condicao_v7_7.py tests/test_condicao_v7_6.py \
       tests/test_prompt_nao_vaza_ground_truth.py -q
```

Coletas usadas: `dist/RESULTADO_IFCQC_20260810T183938Z_…7ed7c7.zip` (v7.5,
4070) e `src/experiment/results/2026-08-12-benchmark-4060/` (v7.6, 4060,
20/20 estágios, 6,94 h, 0 falhas).
