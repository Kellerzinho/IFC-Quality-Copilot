# Ground truth — prédio

Referência experimental integral do dataset `predio`, congelada em 2026-08-09.
O arquivo atribui um valor concreto a cada diagnóstico para permitir um benchmark
reproduzível. Ele não é laudo, certificado, aprovação ou declaração de
conformidade.

## Identificação e integridade

| Campo | Valor |
| --- | --- |
| Protocolo | `full-coverage-equivalent-v1` |
| Localidade | Deodoro, Rio de Janeiro/RJ |
| Tipologia | Residencial multifamiliar |
| Contexto bioclimático | ZB 4A, fonte técnica pública LabEEE/UFSC; sem valor de declaração formal |
| Data do freeze | 2026-08-09 |
| `conformity_claim` | `false` |
| `ground_truth.yaml` | SHA-256 `f92057437c8b5f6a7c098e818f6936e01c868afd82500b14d3844a1e10940c9d` |
| `predio_v1.ifc` | SHA-256 `a71c8be30d82760218f5b3f3a1c476b49e3f30e608b0065916b9d5206a1a6dd0`; entrada local não versionada pelo Git |
| IDS | SHA-256 `f698f2c020d79140bb314f077f8de680f492fd7ba42867e4000a4cead5d20905` |
| Cobertura | 4.720 diagnósticos; 4.720 itens; zero `skipped`; 202 classes de equivalência |
| Base preservada | 1.654 itens, protegidos por `data/evaluation/legacy-reference.lock.json` |
| Confiança | 2.307 `high`; 1.365 `medium`; 1.048 `low` |

O hash do GT histórico anterior,
`7d1b1dc8b4756e5a48cd28925d3dceb53a83ab401c31ae0fcf80914ddf85bccb`,
permanece em `metadata.previous_gt_sha256` apenas para rastreabilidade.

## Como interpretar os valores

- `high`: valor literal/alias do IFC ou valor já presente na base autoral.
- `medium`: cálculo reproduzível ou decisão tipológica determinística.
- `low`: hipótese autoral congelada para que o benchmark tenha uma referência
  completa. Toda nota desse nível começa com `Hipótese congelada:`.

Os itens de uma mesma `equivalence_id` compartilham valor, alternativas, fonte e
confiança. Para o artigo, a métrica principal recomendada é
`accuracy_equivalence`, acompanhada por resultados por confiança e pela fatia
`legacy_reference`, para que milhares de repetições estruturais não dominem a
análise.

## Limites científicos e normativos

Valores `low` são referências autorais experimentais, não requisitos normativos
nem desempenho certificado. A tipologia de incêndio e a ZB 4A são contexto de
análise; o IFC isolado não prova composição, ensaio, execução, rota de fuga,
proteção instalada ou aprovação pelo CBMERJ.

As fontes públicas e os limites de uso estão em
[`references/normative/public/sources.yaml`](../../../references/normative/public/sources.yaml).
O repositório não redistribui textos licenciados da ABNT.
