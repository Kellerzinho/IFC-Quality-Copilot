# Design: Ground truth com cobertura integral por equivalência

**Data:** 2026-08-09

**Status:** aprovado em conversa; aguardando revisão do documento

**Escopo:** `predio_v1.ifc`, `casa_v1.ifc`, avaliador experimental e release Windows

## Objetivo

Transformar os dois ground truths canônicos em referências pontuáveis para todos
os diagnósticos produzidos pelos IFCs congelados. Cada diagnóstico deve receber um
`expected_value` concreto, mesmo quando o valor precisar representar a alternativa
técnica mais provável. O resultado deve permanecer reproduzível, compatível com
`reuse_equivalent` e auditável para uso no artigo.

Cobertura final obrigatória:

- prédio: 4.720 `items` e zero `skipped`;
- casa: 263 `items` e zero `skipped`;
- total: 4.983/4.983 diagnósticos pontuáveis.

## Decisões de projeto

### Uma decisão por classe equivalente

A unidade primária de decisão será a classe usada pelo comportamento
`reuse_equivalent`. Uma classe reúne diagnósticos que compartilham contexto técnico
suficiente para reutilizar a mesma sugestão. O valor é decidido uma vez e propagado
para todas as ocorrências da classe.

Uma classe deve ser subdividida quando um atributo relevante do elemento alterar o
valor correto, por exemplo material, espessura, função, posição, tipo IFC, uso do
ambiente ou condição estrutural.

O gerador não poderá agrupar elementos apenas porque compartilham
`issue_type/check_property`. Ele deverá usar a mesma identidade semântica do reuso
real, complementada pelos discriminadores técnicos necessários.

### Um único YAML canônico por dataset

Os artefatos finais continuam sendo:

- `data/evaluation/predio/ground_truth.yaml`;
- `data/evaluation/casa/ground_truth.yaml`.

Todos os diagnósticos ficarão em `items`. O YAML manterá explicitamente
`skipped: []`, com contagem canônica igual a zero.

Cada item preservará os campos atuais e acrescentará:

```yaml
equivalence_id: eq-...
confidence: high  # high | medium | low
source_kind: ifc_literal  # enumeração definida abaixo
legacy_reference: true
```

`notes` continuará obrigatório e registrará fonte, cálculo ou hipótese. Os campos
existentes permanecem obrigatórios:

```yaml
element_guid: ...
issue_type: ...
check_property: ...
issue_id: ...
expected_value: ...
accepted_alternatives: []
verified: true
notes: ...
```

`verified: true` significa que o valor foi congelado como referência oficial do
experimento. Não significa certeza normativa. A certeza técnica é expressa por
`confidence` e `source_kind`.

`legacy_reference` será `true` exatamente para os 1.666 itens pontuáveis antes
desta migração e `false` para os novos itens. Esse campo define o subconjunto da
métrica histórica sem depender de posição, hash antigo ou lista externa.

`equivalence_id` será determinístico: prefixo `eq-` seguido dos primeiros 16
caracteres do SHA-256 do payload canônico de equivalência. O payload terá chaves
ordenadas e incluirá os discriminadores usados pela sugestão reutilizável. Colisões
de ID com payloads diferentes serão erro fatal.

## Política de atribuição de valores

O valor de cada classe seguirá a primeira fonte aplicável desta hierarquia:

1. valor literal ou alias semântico presente no IFC;
2. valor já ratificado no ground truth anterior;
3. doador ratificado da mesma classe equivalente;
4. cálculo técnico reproduzível com entradas documentadas;
5. regra normativa aplicável e identificada;
6. regra autoral/typológica explícita;
7. valor técnico mais provável, com hipóteses congeladas.

Valores produzidos pelos dez modelos avaliados podem ser usados como candidatos de
análise, mas não podem ser aceitos automaticamente por votação. O ground truth não
deve ser uma reprodução circular das respostas dos modelos que ele mede.

`source_kind` terá os seguintes valores:

- `ifc_literal`;
- `ifc_alias`;
- `existing_gt`;
- `equivalent_donor`;
- `calculation`;
- `normative_rule`;
- `typology`;
- `probable`.

Confiança:

- `high`: literal/alias IFC, relação diretamente observável ou doador exato;
- `medium`: cálculo reproduzível, regra técnica delimitada ou tipologia forte;
- `low`: valor mais provável dependente de hipóteses explícitas.

Nenhum item poderá usar `null`, `unknown`, `not_applicable`, `review_required` ou
outro sentinela no lugar de um valor concreto.

## Regras por família diagnóstica

### `IsLoadBearing`

Usar primeiro aliases IFC, especialmente `LoadBearing`. O levantamento inicial
identificou 685 diagnósticos com `LoadBearing = false`; esses valores são de alta
confiança.

### `Category` e `system_unclassified`

Expandir os vocabulários canônicos e reutilizar as decisões autorais existentes.
Material, função, tipo IFC e uso devem participar da classe equivalente. Classes
genéricas como “alvenaria” podem receber o tipo mais provável, com confiança baixa,
mas não podem variar entre ocorrências equivalentes.

### `relation_broken`

O valor será a relação IFC concreta esperada. Exemplos já identificados incluem
`IfcRelSpaceBoundary` e `IfcRelFillsElement`.

### `ThermalTransmittance`

Calcular pelas camadas quando composição, espessura e constantes estiverem
disponíveis. Na ausência de dados completos, usar tabela tipológica congelada por
material, espessura, tipo do elemento e contexto construtivo. O valor será numérico
e compatível com a normalização/tolerância térmica atual.

### `FireRating`

Combinar função do elemento, uso, posição, sistema, função estrutural e regras de
incêndio aplicáveis. Quando os dados forem incompletos, escolher a classe técnica
mais provável e registrar as hipóteses. Valores devem usar a forma canônica, por
exemplo `REI 60`.

### `AcousticRating`

Usar tipologia, material, espessura e desempenho usual documentado do sistema. A
forma canônica para os elementos presentes nestes dois datasets será
`Rw <inteiro> dB`. Alternativas textuais equivalentes poderão ser listadas em
`accepted_alternatives`, mas todas deverão representar o mesmo índice e valor.

### `SolarHeatGainCoefficient`

Inferir pelo produto/tipo de vidro. Quando houver apenas a indicação genérica de
vidro, usar `0.87`, referência tipológica congelada para vidro incolor comum, e
marcar a decisão como `typology` ou `probable`. Valores permanecerão no intervalo
fechado `[0, 1]`.

### `HasNonSkidSurface`

Inferir o booleano pela função, localização e material da superfície, usando regras
determinísticas e registrando a hipótese. Áreas externas, molhadas, escadas,
patamares e circulações com acabamento apropriado receberão `true`; ambientes secos
sem indicação de acabamento antiderrapante receberão `false`.

## Geração e migração

O construtor canônico será ampliado, sem depender de LLM em tempo de geração:

```text
diagnóstico congelado
  -> classe reuse_equivalent
  -> procura de doador
  -> cálculo/regra/tipologia
  -> decisão concreta
  -> propagação para ocorrências
  -> validação integral
  -> escrita atômica do YAML
```

Os 1.666 itens atualmente pontuados devem permanecer semanticamente idênticos:
mesma chave natural, `issue_id`, `expected_value` e alternativas. Novos metadados de
equivalência/confiança podem ser acrescentados sem alterar sua resposta ratificada.

As decisões novas serão congeladas no próprio YAML. O gerador deve ser capaz de
revalidar o snapshot pinado e comprovar que todas as ocorrências da mesma classe
continuam coerentes.

## Validação e falha fechada

A construção falhará antes de escrever quando ocorrer qualquer condição abaixo:

- diagnóstico sem item correspondente;
- item sem valor concreto;
- classe equivalente sem decisão;
- valores, confiança ou fonte divergentes dentro da mesma classe;
- valor incompatível com a normalização real da propriedade;
- item `low` sem hipótese explícita em `notes`;
- alteração de um valor legado ratificado;
- chave natural ou `issue_id` duplicado;
- hash IFC/IDS divergente;
- cobertura diferente de 4.720/263;
- geração não determinística.

Arquivos serão escritos atomicamente e com LF, mantendo pins SHA-256 externos.

## Pontuação

O avaliador continuará calculando top-1, top-3, recall, precisão e tolerâncias atuais,
mas passará a expor quatro visões:

1. `accuracy_all`: micro média sobre as 4.983 ocorrências;
2. `accuracy_equivalence`: macro média, uma contribuição por `equivalence_id`;
3. `accuracy_by_confidence`: métricas separadas em `high`, `medium` e `low`;
4. `accuracy_legacy`: subconjunto dos itens ratificados antes desta migração.

`accuracy_equivalence` será a métrica principal recomendada para o artigo, pois evita
que uma classe repetida centenas de vezes domine o resultado. `accuracy_all` será a
medida operacional de cobertura completa.

O formato de resultados deverá registrar a versão da política, os hashes dos dois
YAMLs e as contagens por confiança.

## Compatibilidade e release Windows

A migração altera os hashes dos ground truths e, portanto, a identidade de execução.
Após congelar os novos YAMLs será obrigatório:

- atualizar pins no construtor/runner;
- atualizar testes de identidade e retomada;
- reconstruir `project.zip` e `release-manifest.json`;
- reconstruir a pasta Windows final;
- executar `ValidateOnly` e `PlanOnly` novamente;
- comprovar que os dois GTs novos estão dentro do payload;
- manter a matriz oficial de 10 modelos x 2 datasets x 1 réplica.

Resultados antigos permanecem vinculados aos hashes anteriores e não podem ser
misturados com os resultados da política integral.

## Testes de aceitação

O trabalho só estará completo quando todos os seguintes testes passarem:

- prédio: 4.720 itens, zero skipped;
- casa: 263 itens, zero skipped;
- cobertura: 4.983/4.983;
- partição exata por chave natural e `issue_id`;
- valores legados semanticamente inalterados;
- coerência total dentro de cada equivalência;
- validação de `confidence/source_kind/notes`;
- oracle construído dos dois YAMLs obtém 100%;
- respostas propositalmente erradas reduzem as métricas;
- métricas por confiança, equivalência e legado;
- regeneração byte-determinística;
- `build_ground_truths --dataset all --check` sem drift;
- smoke integrado do runner com os dois YAMLs;
- release Windows reconstruída, `ValidateOnly` e `PlanOnly` com código zero.

## Limites e transparência científica

Cobertura integral não transforma valores prováveis em fatos normativos. O artigo e
os relatórios deverão informar:

- quantos itens são `high`, `medium` e `low`;
- quais famílias concentram hipóteses tipológicas;
- que a métrica principal por equivalência reduz o efeito de repetição;
- que os resultados anteriores usavam o subconjunto legado;
- que valores `low` são referências autorais congeladas para comparação experimental.

Não fazem parte deste escopo a comprovação formal de conformidade normativa, ensaios
de materiais, simulação térmica/acústica completa ou substituição de projeto técnico
por inferência automatizada.
