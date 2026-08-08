# Ground truth — casa

Referência de proveniência do dataset `casa`, congelada em 2026-08-08 para o
benchmark. O conjunto é uma referência anotada para avaliação, não um laudo,
certificado, aprovação ou declaração de conformidade.

## Identificação e integridade

| Campo | Valor |
| --- | --- |
| Protocolo | `evidence-audited-v1` |
| Localidade declarada | Deodoro, Rio de Janeiro/RJ |
| Tipologia declarada | Residencial unifamiliar |
| Classificação de incêndio | A-1, premissa autoral para análise; não classificação oficial |
| Contexto bioclimático | ZB 4A, conforme fonte técnica pública LabEEE/UFSC para Rio de Janeiro/RJ |
| Status da ZB 4A | contexto técnico, sem valor de declaração formal de conformidade |
| Data de verificação | 2026-08-08 |
| `conformity_claim` | `false` |
| `ground_truth.yaml` | SHA-256 `5903db9a3e3904f16a82df38b10d09f13769e7d88f3b61f52730a27dc8627c59` |
| `casa_v1.ifc` | SHA-256 `3b84789c7396449f2c8a3d2f4a66468d81e59f8351ebd4b71fad161fa06112f2`; não versionado pelo Git |
| IDS de entrada | SHA-256 `f698f2c020d79140bb314f077f8de680f492fd7ba42867e4000a4cead5d20905` (`data/ids_templates/residencial_nbr15575.ids`) |
| Contagens | 263 issues diagnósticos; 12 itens; 251 abstenções (`skipped`) |

## Escopo e limites de inferência

Os valores esperados são evidência modelada e/ou intenção de projeto submetida à
auditoria determinística aprovada pelo autor. Não são desempenho certificado. Um
valor ou limite normativo pode ser fonte da análise, de um cálculo reproduzível ou
da razão de abstinência; não deve ser usado como `expected_value` fornecido pelo
elemento sem evidência específica desse elemento.

A-1 é premissa autoral. A ausência de extintor, sinalização ou objeto de saída de
emergência no IFC não recebe violação automática e não prova ausência física. O
IFC tampouco basta para inferir ocupação, população, rota de fuga, proteção
instalada, aprovação, laudo ou certificado do CBMERJ.

ZB 4A é apenas contexto técnico da localidade declarada; não prova desempenho
térmico. Em particular, `ThermalTransmittance` presente no IFC não substitui
composição, ensaio ou evidência de execução. A falta dessas evidências justifica
`skipped`, não uma conclusão de conformidade ou não conformidade.

As fontes oficiais, edições consultadas e sua política de redistribuição estão em
[`references/normative/public/sources.yaml`](../../../references/normative/public/sources.yaml).
As normas ABNT aparecem somente como links de catálogo oficial; nenhum texto de
norma paga é distribuído neste repositório.
