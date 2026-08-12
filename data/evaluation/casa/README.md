# Ground truth — casa

Referência experimental integral do dataset `casa`, congelada em 2026-08-09.
O arquivo atribui um valor concreto a cada diagnóstico para permitir um benchmark
reproduzível. Ele não é laudo, certificado, aprovação ou declaração de
conformidade.

## Identificação e integridade

| Campo | Valor |
| --- | --- |
| Protocolo | `full-coverage-equivalent-v1` |
| Localidade | Deodoro, Rio de Janeiro/RJ |
| Tipologia | Residencial unifamiliar |
| Contexto bioclimático | ZB 4A, fonte técnica pública LabEEE/UFSC; sem valor de declaração formal |
| Data do freeze | 2026-08-09; emendado em 2026-08-10 e 2026-08-12 |
| `conformity_claim` | `false` |
| `ground_truth.yaml` | SHA-256 `e72b344f5b1bd30ac73a02db77868322fae1458e3d4d050f2ccd667f66f6138b` |
| `casa_v1.ifc` | SHA-256 `3b84789c7396449f2c8a3d2f4a66468d81e59f8351ebd4b71fad161fa06112f2`; entrada local não versionada pelo Git |
| IDS | SHA-256 `f698f2c020d79140bb314f077f8de680f492fd7ba42867e4000a4cead5d20905` |
| Cobertura | 263 diagnósticos; 263 itens; zero `skipped`; 101 classes de equivalência |
| Base preservada | 12 itens, protegidos por `data/evaluation/legacy-reference.lock.json` |
| Confiança | 52 `high`; 132 `medium`; 79 `low` |

Cadeia de hashes do artefato congelado (pino em
`scripts/build_ground_truths.py::EXPECTED_GROUND_TRUTH_SHA256`):

| Emenda | SHA-256 | O que mudou |
| --- | --- | --- |
| Freeze de 2026-08-09 | `60f87a079d2a…1a6f8cfee5` | protocolo `full-coverage-equivalent-v1` |
| 2026-08-10 (equivalências) | `c98fdd5ec056…58bb2d1d` | só `accepted_alternatives` de fogo e acústica |
| 2026-08-12 (emenda editorial) | `e72b344f5b1b…f66f6138b` | drywall aceita `EI 30`; telha de fibrocimento volta a U=4,6 |

## Como interpretar os valores

- `high`: valor literal/alias do IFC ou valor já presente na base autoral.
- `medium`: cálculo reproduzível ou decisão tipológica determinística.
- `low`: hipótese autoral congelada para que o benchmark tenha uma referência
  completa. Toda nota desse nível começa com `Hipótese congelada:`.

Os itens de uma mesma `equivalence_id` compartilham valor, alternativas, fonte e
confiança. Para o artigo, a métrica principal recomendada é
`accuracy_equivalence`, acompanhada por resultados por confiança e pela fatia
`legacy_reference`.

## Limites científicos e normativos

Valores `low` são referências autorais experimentais, não requisitos normativos
nem desempenho certificado. A tipologia de incêndio e a ZB 4A são contexto de
análise; o IFC isolado não prova composição, ensaio, execução, rota de fuga,
proteção instalada ou aprovação pelo CBMERJ.

As fontes públicas e os limites de uso estão em
[`references/normative/public/sources.yaml`](../../../references/normative/public/sources.yaml).
O repositório não redistribui textos licenciados da ABNT.
