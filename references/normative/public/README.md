# Registro público de fontes normativas

Este diretório contém somente metadados e links oficiais usados para delimitar a
análise dos ground truths de `predio` e `casa`. O catálogo completo está em
[`sources.yaml`](sources.yaml), com data de consulta, edição, emissor, status e
uso declarado de cada fonte.

## Política de redistribuição

Todas as entradas têm `redistribution: link-only`. Em especial, normas ABNT são
protegidas e aparecem apenas como links para o catálogo oficial: não foram
baixadas, copiadas ou incluídas neste repositório. Este diretório não contém PDFs;
links para PDFs institucionais públicos do CBMERJ e LabEEE/UFSC permanecem apenas
referências externas, sem redistribuição local.

## Limite de uso

As fontes delimitam aplicabilidade, contexto técnico, cálculo reproduzível ou
razão de abstinência. Elas não comprovam que um elemento IFC forneça o desempenho
exigido e não fazem dos ground truths um laudo, certificado, aprovação ou
declaração de conformidade. A classificação A-1/A-2 é uma premissa autoral; a
ausência de objeto no IFC não prova ausência física.

## Tratamento das citações legadas do `predio`

As notas herdadas foram mantidas como trilha de curadoria, mas sua redação não
permite completar silenciosamente referências incompletas:

- `NBR 14432:2001` identifica uma edição exata, agora ligada ao registro oficial
  correspondente. O catálogo público confirma a edição, não o conteúdo atribuído
  à Tabela A.1 nem o desempenho de um elemento IFC.
- `NBR 15220-2` não traz ano. O registro vigente de 2022, corrigido em 2023, serve
  somente para localizar a família normativa: não demonstra se a curadoria usou
  essa edição ou a edição anterior, nem valida retroativamente os valores de
  cálculo anotados.
- `NBR 15200` também não traz ano. O registro vigente de 2024, corrigido em 2024,
  não autoriza atribuir essa edição à nota legada ou concluir que os pilares
  modelados forneçam a resistência indicada.
- `IT-08 CBPMESP` não traz ano e pertence ao Estado de São Paulo. Com a
  reclassificação das 262 entradas prováveis de paredes como `skipped`, ela fica
  preservada apenas como contexto histórico não fluminense e não é doadora de
  rótulos pontuados para Deodoro/Rio de Janeiro. A delimitação territorial de
  incêndio permanece apoiada no COSCIP e nas fontes oficiais do CBMERJ.

Quando a edição não está na evidência original, o catálogo registra a ambiguidade
em vez de inferi-la. Nenhum desses links transforma uma decisão autoral em
verificação normativa, ensaio de desempenho ou declaração de conformidade.
