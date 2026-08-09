# Definição das métricas de avaliação (Fase 0.3 / F10+F11)

**Data da revisão integral:** 2026-08-09
**Implementação:** `src/experiment/evaluator.py` (`Evaluator`, `EvaluationMetrics`).

Este documento formaliza como o experimento mede a qualidade das sugestões do LLM
contra o *ground truth* (GT). Ele responde aos achados **F10** (comparação frágil por
string exata) e **F11** ("precision" mal definida) da revisão crítica de 09/06.

---

## 1. Casamento sugestão × ground truth (F10)

A igualdade **não** é `str(x) == str(y)`. Uma sugestão "casa" o GT quando
`values_match(issue, candidate, expected)` é verdadeiro, o que aplica a **mesma
normalização** que o pipeline usa antes de escrever no IFC
(`normalize_value_for_issue`, em `src/suggestion_engine/normalization.py`) aos dois
lados e então compara por tipo:

| Tipo de valor | Regra de comparação |
|---|---|
| Numérico (ex.: `ThermalTransmittance`) | tolerância **relativa** (default **2%**): `|c − e| ≤ tol · |e|` |
| Booleano (ex.: `IsExternal`) | igualdade após coerção de `"true"/"sim"/"1"` → `True`, `"false"/"nao"/"0"` → `False` |
| Texto (espaços, sistemas, classificação) | igualdade por chave normalizada (sem acento, *casefold*, espaços colapsados) |

Cada item de GT pode declarar `accepted_alternatives`: a sugestão casa se for igual ao
`expected_value` **ou** a qualquer alternativa aceita. Isso é essencial em **nomeação de
espaços**, onde múltiplos rótulos são corretos (ex.: "Lavabo" ≡ "WC Social").

A tolerância é parametrizável: `Evaluator(float_tolerance=0.02)`.

---

## 2. Identificação da issue: chave natural (F10)

O GT é casado às issues pela **chave natural** `(element_guid, issue_type,
check_property)`, não por `Issue.id`. Combinada com os IDs determinísticos da Fase 0.2,
isso garante que **o mesmo GT casa as mesmas issues entre execuções distintas** do
`diagnose()`. Há *fallback* por `issue_id` para compatibilidade com GTs legados.

O GT é versionável em **YAML** (`GroundTruth.from_yaml`), validado por Pydantic:

```yaml
metadata:
  source: predio_v1
  verified_by: Felipe
  date: 2026-06-28
items:
  - element_guid: 3xY9...            # GlobalId IFC (22 chars)
    issue_type: pset_missing
    check_property: ThermalTransmittance
    expected_value: 2.5
    accepted_alternatives: []
    verified: true
  - element_guid: 1aB2...
    issue_type: space_unnamed
    expected_value: Lavabo
    accepted_alternatives: [WC Social]
    verified: true
```

---

## 3. Métricas (F11)

Seja **G** o conjunto de issues avaliadas que têm entrada no GT (após o filtro de
perfil), **S ⊆ G** as que receberam ao menos uma sugestão, e **GT** o total de itens do
ground truth. "Casa GT" usa a comparação normalizada da seção 1.

| Métrica | Definição | Interpretação |
|---|---|---|
| `accuracy_top1` | \|{i ∈ G : top-1 casa}\| / \|G\| | acerto da 1ª sugestão |
| `accuracy_top3` | \|{i ∈ G : alguma das top-3 casa}\| / \|G\| | acerto entre as 3 melhores |
| `precision` | \|{i ∈ S : top-1 casa}\| / \|S\| | acurácia top-1 **condicionada à geração** |
| `recall` | \|{i ∈ G : top-1 casa}\| / \|GT\| | **cobertura** sobre todo o GT |
| `f1` | média harmônica de `precision` e `recall` | — |

### 3.1 Cortes científicos do protocolo integral

O protocolo `full-coverage-equivalent-v1` publica quatro visões simultâneas:

| Campo | Unidade de análise | Definição |
|---|---|---|
| `accuracy_all` | ocorrência | microacurácia sobre cada diagnóstico; reproduz `accuracy_top1/top3` |
| `accuracy_equivalence` | classe estrutural | calcula top-k dentro de cada `equivalence_id` e tira a média simples das classes |
| `accuracy_by_confidence` | ocorrência | microacurácia separada em `high`, `medium` e `low` |
| `accuracy_legacy` | ocorrência preservada | microacurácia somente onde `legacy_reference=true` |

Formalmente, para classes de equivalência `E` e ocorrências `G_e` de cada
classe, a principal métrica do artigo é:

`accuracy_equivalence_top1 = (1 / |E|) · Σ_e (acertos_top1(G_e) / |G_e|)`.

Assim, uma parede repetida 651 vezes não vale 651 vezes mais que uma classe rara.
`accuracy_all` continua sendo reportada para mostrar o comportamento por elemento,
mas não deve ser usada sozinha para ranquear modelos neste dataset.

Confiança tem significado de proveniência, não probabilidade estatística:

- `high`: literal/alias IFC ou base autoral preservada;
- `medium`: cálculo reproduzível ou regra tipológica determinística;
- `low`: hipótese autoral congelada para completar a referência experimental.

Um valor `low` não é requisito normativo, conformidade ou desempenho certificado.
Resultados com `ground_truth_sha256` ou `ground_truth_policy_version` diferentes
não são diretamente comparáveis. Uma tabela conjunta deve estratificar esses
runs ou recalculá-los contra exatamente o mesmo GT congelado.

### Nota honesta sobre "precision" (F11)

Cada issue produz uma **lista ranqueada** de sugestões, não um conjunto de predições
positivas independentes; logo, *precision/recall* no sentido clássico de recuperação de
informação não se aplicam diretamente. Adotamos definições **defensáveis e explícitas**:

- **`precision`** mede a acurácia top-1 **apenas quando o sistema não se abstém** (issues
  com `review_required` sem sugestão ficam de fora). É a "acurácia condicionada à
  tentativa".
- **`recall`** mede a acurácia top-1 **sobre todo o GT**, contando abstenções e issues
  filtradas como erro — ou seja, a cobertura efetiva.

No artigo, as métricas **principais** reportadas são **top-1 / top-3** e a
**conformidade IDS pós-correção** (PostValidator sobre cópia descartável, Fase 0.5).
`precision/recall/f1` entram como métricas secundárias, sempre com a definição acima.

---

## 4. Readiness (contexto, não métrica de qualidade do LLM)

`readiness_before/after/improvement` medem o efeito de **aplicar todas as correções do
GT** sobre o score de prontidão de um perfil (`ReadinessScore`). É um indicador de
impacto do enriquecimento, independente de qual modelo gerou as sugestões — não deve ser
confundido com a qualidade das sugestões do LLM.

---

## Adendo (2026-07-02): métricas sob amostragem (`--max-issues`)

O runner passou a suportar amostragem estratificada determinística
(`--max-issues N --sample-seed S`). Sob amostragem, as métricas devem ser
interpretadas assim:

- **Válidas por construção:** `accuracy_top1`, `accuracy_top3` e `precision`
  são computadas **sobre as issues amostradas com GT** — continuam bem
  definidas e comparáveis entre modelos (mesma seed ⇒ mesma amostra).
- **Distorcidas — não reportar:** `recall` e `f1` usam |GT| **completo** no
  denominador (2546 itens no prédio); num run amostrado de 24 issues o recall
  fica artificialmente ~0 (observado no smoke de 2026-07-02: recall 0,0031).
  Em runs amostrados, reportar apenas top-1/top-3/precision + estabilidade +
  eficiência, ou recomputar recall contra o subconjunto de GT da amostra.
- A amostra usada fica registrada em `issue_counts.sampled_from` e
  `issue_counts.sample_seed` de cada `run_*.json` (auditável).

Para os números finais do artigo, preferir runs com a amostra fixa acordada
com o orientador (mesma seed em todos os modelos) ou runs completos.

---

## Adendo (2026-08-09): benchmark oficial com reuso equivalente

O benchmark portátil oficial usa `reuse_equivalent=true` e cache persistente
desligado. Issues estruturalmente equivalentes recebem uma chamada de LLM e as
demais reutilizam o resultado da primária. Essa condição faz parte de
`ExecutionIdentity`; mudar a flag invalida a retomada.

O desenho reduz custo e torna o tempo executável em hardware local, sem esconder a
estrutura do dataset:

- `accuracy_all` ainda mede todas as 4.983 ocorrências;
- `accuracy_equivalence` impede que classes muito repetidas dominem o ranking;
- o JSONL preserva um desfecho por issue;
- latência mede estímulos efetivamente enviados, e deve ser interpretada junto da
  contagem de equivalências e de `reuse_equivalent`.

Resultados históricos gerados por instância continuam úteis como análise de
sensibilidade, mas não devem ser misturados ao ranking oficial sem marcar a diferença
de identidade experimental.
