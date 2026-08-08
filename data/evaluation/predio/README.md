# Ground truth — prédio

Referência de proveniência do dataset `predio`, congelada em 2026-08-08 para o
benchmark. Este arquivo substitui descrições históricas de GT e não é um laudo,
certificado, aprovação ou declaração de conformidade.

## Identificação do conjunto

| Campo | Valor |
| --- | --- |
| Protocolo | `evidence-audited-v1` |
| Localidade declarada | Deodoro, Rio de Janeiro/RJ |
| Tipologia declarada | Residencial multifamiliar |
| Classificação de incêndio | A-2, premissa autoral para análise; não classificação oficial |
| Contexto bioclimático | ZB 4A, conforme fonte técnica pública LabEEE/UFSC para Rio de Janeiro/RJ |
| Status da ZB 4A | contexto técnico, sem valor de declaração formal de conformidade |
| Data de verificação | 2026-08-08 |
| `conformity_claim` | `false` |

## Artefatos congelados

| Artefato | SHA-256 | Contagem / observação |
| --- | --- | --- |
| `ground_truth.yaml` | `2594d7efee7c29b662e7b9253cb5fe06867a046192f12b62d1acdf00d0199800` | 4.720 issues diagnósticos; 1.654 itens; 3.066 abstenções (`skipped`) |
| `predio_v1.ifc` | `a71c8be30d82760218f5b3f3a1c476b49e3f30e608b0065916b9d5206a1a6dd0` | entrada IFC do GT canônico; não versionada pelo Git |
| `ground_truth_spaces.yaml` | `f1451e983f7a6a869c908051a7c527f394cae670e07fc3da2a4432682c065ac8` | 82 nomes de espaços curados |
| `predio_v1_masked.ifc` | `750315bbfe9379937f3d45b94170c8e45c0a1280ff4237d48839caa29e6ecec6` | variante mascarada para `space_unnamed`; não versionada pelo Git |
| IDS de entrada | `f698f2c020d79140bb314f077f8de680f492fd7ba42867e4000a4cead5d20905` | `data/ids_templates/residencial_nbr15575.ids` |

O hash legado do GT anterior é
`7d1b1dc8b4756e5a48cd28925d3dceb53a83ab401c31ae0fcf80914ddf85bccb` e está
registrado em `metadata.previous_gt_sha256` apenas para rastreabilidade. O GT
canônico é o arquivo e hash apresentados na primeira linha da tabela.

## Escopo e limites de inferência

Os valores em `ground_truth.yaml` são evidência modelada e/ou intenção de
projeto revisada pelo autor para fins de benchmark. Não transformam um requisito
normativo em desempenho fornecido por um elemento: um limite normativo pode
justificar análise, cálculo ou abstinência, mas nunca é copiado como
`expected_value` sem evidência específica do elemento.

A tipologia A-2 é uma premissa autoral. As medidas de segurança contra incêndio
dependem, entre outros dados, de área, altura, número de pavimentos, população,
sistemas de proteção (inclusive sprinklers) e escopo declarado do IFC. A ausência
de um objeto no modelo não prova sua ausência física. Por isso, o conjunto não
infere rota de fuga válida, aprovação, laudo ou certificado do CBMERJ a partir do
IFC.

O contexto ZB 4A não prova desempenho térmico. A presença de
`ThermalTransmittance` indica disponibilidade de dado no modelo; isoladamente,
não comprova composição, ensaio, execução ou atendimento a requisito. Quando a
evidência não é suficiente, o caso permanece em `skipped`.

Não usar referências históricas a zona bioclimática 3, à IT-11 de outra
jurisdição, ou a edições imprecisas como base deste dataset. As fontes oficiais e
as edições consultadas estão em
[`references/normative/public/sources.yaml`](../../../references/normative/public/sources.yaml).
As normas ABNT são apontadas somente por seus catálogos oficiais; o repositório
não redistribui seus textos.
