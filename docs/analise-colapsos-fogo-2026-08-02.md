# Colapsos de FireRating — investigação fechada (2026-08-02)

Origem: `docs/analise-benchmark-2026-07-28.md` deixou dois colapsos em aberto no
estrato de fogo do run limpo (commit `2e03386`). Investigados aqui a partir do
`run_0_issues.jsonl` gravado (sem GPU), com as 6 primárias de FireRating por
modelo (`--reuse-equivalent` colapsa as 1020 issues em 6 estímulos).

## 1. qwen3.5:9b — hipótese "formato" REFUTADA

Suspeitava-se de formato (top-1 0,007 com top-3 0,570). O dump das primárias
mostra JSON limpo em todas (1 tentativa, zero falhas, confiança alta). O
mecanismo real é **atribuição errada do conjunto de critérios por papel do
elemento**:

| Elemento | Esperado | Top-3 do modelo | Leitura |
|---|---|---|---|
| Parede alvenaria interna | REI 60 | EI 60, EI 90 | EI correto p/ não portante (emenda) |
| Parede alvenaria externa | REI 60 | EI 90, EI 60, EI 30 | idem |
| Drywall | EI 30 | EI 60, EI 90, EI 30 | critério certo, duração superestimada |
| Porta corta-fogo | EI 30 | EI 60, EI 90, EI 120 | aceito (porta 60 é plausível) |
| Pilar | R 60 | REI 90, REI 60, REI 30 | REI onde basta R; REI 60 (aceito) só no top-2 |
| Escada | REI 60 | EI 60, EI 90 | omite o R de elemento estrutural |

Duas componentes separáveis:
- **Critério de avaliação** (resolvido pela emenda EI/REI de 2026-08-02): as
  duas paredes não portantes respondidas com EI eram evidência seguida, não
  erro. Re-score: fogo 0,007 → 0,427; global 0,4183 → 0,5868.
- **Erro real remanescente** (patologia reportável): omite R em elemento
  estrutural (escada), usa REI em pilar (onde a prática pede R — acerta REI 60
  apenas no top-2) e superestima duração do drywall. É "indisciplina de
  conjunto de critérios", não formato.

## 2. mistral:7b — patologia confirmada, nenhum artefato

5 das 6 primárias respondem **classe de uma letra** (`E 60`, `R 30`…), e as
atribuições se invertem: `R 60` no drywall **não portante** e `E 60` na porta
corta-fogo. Só o pilar tem o critério certo (R), com duração errada no top-1.
A emenda EI/REI corretamente **não** o beneficia (0,1009 inalterado): `E 60`
não cumpre nem REI nem EI. Classificação: indisciplina de vocabulário
normativo — achado de modelo, sem correção de instrumento cabível.

## 3. A regra implícita da curadoria do GT (explicitar no método do artigo)

O padrão de `accepted_alternatives` aprovado em 2026-07-02 segue uma regra
consistente, ainda não declarada em texto:

> Aceita-se um valor quando (a) **cumpre o requisito aplicável** ao elemento e
> (b) é **plausível como desempenho real** do componente.

| Grupo | Esperado | Aceita | Rejeita (e por quê) |
|---|---|---|---|
| Alvenaria (não portante) | REI 60 | REI 90/120; EI 60/90/120 (emenda) | E 60 (sem I) |
| Pilar | R 60 | REI 60, R 90 | REI 90 (rotular pilar REI já é impróprio; 90 agrava) |
| Drywall ST 15 | EI 30 | REI 30 | EI 60+ (chapa simples não entrega 60 min) |
| Porta corta-fogo | EI 30 | EI 60+ (P-CF 60 existe e cumpre) | — |

Recomendação: declarar a regra na seção de materiais/método e citar os dois
lados que ela decide (porta aceita duração superior; drywall não).

## 4. Nota sobre o qwen3.5:4b

Sob a emenda, fecha o estrato de fogo em **6/6 estímulos** — o único da matriz.
Perfil "segue a evidência do arquivo" (LoadBearing=false → EI) premiado pelo
critério corrigido, coerente com sua liderança pós-emenda no prédio (0,8390).

## Método

`scratchpad/colapsos.py` (sessão 2026-08-02): lê `run_0_issues.jsonl` das
pastas `2026-07-28-benchmark-limpo/predio/{qwen3.5_9b,mistral_7b,qwen3.5_4b}`
e imprime as primárias de FireRating com top-3, flags, tentativas e reusos.
Re-score da emenda em `scratchpad/rescore_ei.py` (tabela completa em
`data/evaluation/predio/REVISAO_GT.md`, seção Emendas).
