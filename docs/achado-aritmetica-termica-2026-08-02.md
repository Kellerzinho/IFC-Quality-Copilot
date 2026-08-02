# O colapso térmico do v6 é aritmético, não semântico (2026-08-02)

Medido no estrato `pset_missing` do prédio com `gemma2:9b`, prompt v6
(`estrato-v6-pset-gemma2`, 131 chamadas, 0 falhas), comparado ao mesmo modelo
sob prompt v5 no run limpo de 2026-07-28. Único diff nos templates térmicos
entre as duas condições (`git diff 2e03386 92c8fe7`): o bloco **VERIFICAÇÃO
OBRIGATÓRIA** — "a justificativa da 1ª opção traz a memória de cálculo numérica
no formato `R_total = Rsi + (e1/λ1) + ... + Rse`, e o campo valor é exatamente
`1/R_total`". A faixa "parede de vedação típica fica entre 1,5 e 3,5" **já
existia no v5**.

| | v5 | v6 |
|---|---|---|
| top-1 | 0,6241 | **0,2190** |
| top-3 | 0,6241 | **0,6241** |
| MAPE | 34,3% | 33,4% |

Top-3 e MAPE praticamente idênticos com o top-1 caindo 40 pp: o conhecimento
não mudou: mudou **qual candidato vai para o 1º lugar**.

## 1. Os 40 pontos são UMA chamada de LLM

Dos 19 estímulos térmicos, **18 mantiveram o mesmo veredito**. A queda inteira
está num único estímulo — a parede de drywall, que carrega **222 das 548
issues (40,5% do estrato)**:

| estímulo | issues | v5 top-1 | erro | v6 top-1 | erro |
|---|---|---|---|---|---|
| **IfcWall drywall (GT 2,35)** | **222** | **2,50** | **6,4% ✓** | **3,50** | **48,9% ✗** |
| 10 esquadrias/panos de vidro (GT 5,7) | 120 | 5,50 | 3,5% ✓ | 5,50 | 3,5% ✓ |
| 6 lajes + 2 telhados | 206 | — | ✗ | — | ✗ |

O `2,50` do v5 continua no top-3 do v6, rebaixado para 2ª posição — é por isso
que o top-3 não se move um décimo. Caso de manual da lição "a unidade de
inferência é o estímulo, nunca a issue": aqui um estímulo vale 40 pp.

## 2. No estímulo decisivo, a memória de cálculo NÃO foi produzida

A resposta do v6 para a parede (log do run, DEBUG):

> `{"valor": 3.5, "justificativa": "Parede de drywall/steel frame com espessura
> total de 0,1 m e ausência de camada isolante. Considerando a norma NBR 15220-2
> e o montante metálico como câmara de ar não ventilada (R ≈ 0,17 m²K/W), o
> valor U resultante é alto.", "confianca": "alta"}`

Nenhuma conta. A instrução obrigatória produziu a **retórica** do cálculo
("considerando… o valor resultante é alto") sem o cálculo — e o valor escolhido,
`3,5`, é exatamente o **teto da faixa que o nosso próprio prompt enuncia**. Como
essa faixa já estava no v5 e o modelo não ancorou nela então, o que empurrou a
âncora foi a cobrança de cálculo. É a patologia "ancoragem no limite" já
catalogada, agora sobre um número que nós escrevemos.

Lição operacional: **enunciar faixa típica no prompt é oferecer uma âncora**.
Sob pressão de justificar, o modelo prefere o número saliente do enunciado a uma
conta que não sabe fechar.

## 3. Onde a memória FOI produzida, o erro é puramente aritmético

4 dos 9 estímulos de template por camadas produziram memória parseável. Nos
**4, a soma está errada** — e em todos o valor devolvido é fielmente
`1/(a soma que o próprio modelo escreveu)`. Ou seja: **obedece ao contrato,
monta os termos certos, e erra a adição.**

| estímulo | termos escritos pelo modelo | soma dita | soma real | devolveu | recomputado | GT |
|---|---|---|---|---|---|---|
| laje 15cm (107 issues) | `0,17 + (0,02/1,05) + (0,03/1,15) + (0,10/1,75) + 0,04` | 0,4680 | **0,3123** | 2,14 | **3,20** | 3,2 |
| laje 15cm (31 issues) | idem | 0,3860 | **0,3123** | 2,59 | **3,20** | 3,2 |
| laje usinada (53 issues) | `0,17 + (0,02/1,15) + (0,03/1,75) + (0,10/1,75) + 0,04` | 0,3860 | 0,3017 | 2,05 | 3,31 | 3,2 |
| laje 20cm (4 issues) | `0,17 + (0,02/1,75) + (0,03/1,15) + (0,15/1,05) + 0,04` | 0,6986 | 0,3904 | 1,43 | 2,56 | 2,93 |

A primeira linha é o caso exemplar: os termos que o modelo escreveu são
**verbatim a derivação do próprio ground truth** (`REVISAO_GT.md`: "Rsi 0,17 +
piso 0,02/1,05 + regularização 0,03/1,15 + concreto 0,10/1,75 + Rse 0,04 =
0,312 → U = 3,20"). Ele identificou as camadas, recuperou os λ corretos, montou
o método certo — e então declarou que a soma dava 0,468. Refeita a soma:
**3,20, o GT, com 0,1% de erro.**

Se uma camada determinística reparsasse a memória (cujo formato o próprio prompt
já fixa) e refizesse a conta, **3 dos 4 cruzariam a banda de 10%** — 191 das 548
issues, ~35 pp do estrato térmico.

## 4. Consequência de arquitetura (não de prompt)

O achado aponta para uma divisão de trabalho que é a própria tese do pipeline:

> O LLM propõe a **estrutura** do cálculo (quais camadas, qual λ, qual método
> normativo); a camada determinística **executa a conta**.

Isso não é engenharia de prompt — é mover uma responsabilidade para onde ela é
verificável. Encaixa no enquadramento de governança openBIM: a sugestão passa a
carregar uma memória de cálculo auditável, e a aritmética deixa de ser um ato de
fé no modelo. Também dá um critério de rejeição objetivo: se `valor ≠ 1/R_total`
pelos termos declarados, a sugestão é inconsistente **consigo mesma** e pode ser
rebaixada ou recalculada antes de chegar ao engenheiro.

Benefício colateral já colhido aqui: **exigir memória estruturada tornou o erro
diagnosticável**. Sem ela, "2,14 contra GT 3,2" é só um erro; com ela, dá para
afirmar que o modelo sabia o método e não soube somar — distinção que o acerto
binário jamais mostraria.

## 5. Limites deste achado

- **n pequeno**: 4 memórias parseáveis, 1 modelo (gemma2:9b), 1 réplica. A
  generalização por família de modelo depende da matriz v6 completa.
- **Adesão parcial ao contrato**: só 4 de 9 estímulos elegíveis produziram
  memória parseável; uma estratégia de recomputação só age onde a memória
  existe, e no estímulo mais pesado (a parede, 222 issues) ela não existia.
- **Não implementar agora**: a matriz v6 está em execução e mede o instrumento
  como está. A recomputação determinística deve ser uma **condição declarada
  separada (v7)**, medida depois, para não repetir o ciclo de ajustar o
  instrumento olhando o resultado.
- O 5,5 das esquadrias (erro 3,5%) passa na banda de 10% mas não é cálculo — é
  valor de referência recuperado; o template de esquadria não pede memória.

## Método

`scratchpad/compara_termico2.py` (comparação estímulo a estímulo v5×v6 com a
banda de 10% e peso em issues) e `scratchpad/censo_termico.py` (censo dos 19
estímulos avaliados, ligando log → estímulo pelo valor do top-1 e recomputando
cada memória). Fontes: `2026-07-28-benchmark-limpo/predio/gemma2_9b/run_0_issues.jsonl`
(v5) e `estrato-v6-pset-gemma2/` + seu log DEBUG (v6).
