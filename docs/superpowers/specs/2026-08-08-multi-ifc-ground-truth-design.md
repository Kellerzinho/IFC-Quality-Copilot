# Design — Ground truth canônico para prédio e casa

**Data:** 2026-08-08

**Status:** aprovado em conversa; aguardando revisão desta especificação

**Escopo:** ground truth dos datasets `predio_v1.ifc` e `casa_v1.ifc`

## 1. Objetivo

Produzir uma referência simples e defensável para o benchmark do IFC Quality
Copilot:

- um único `ground_truth.yaml` canônico para o prédio;
- um único `ground_truth.yaml` canônico para a casa;
- somente valores considerados corretos na seção `items`;
- toda informação insuficiente registrada em `skipped`, sem virar rótulo positivo;
- compatibilidade com o `GroundTruth.from_yaml()` e o `Evaluator` existentes;
- nenhuma alteração nos prompts ou no pipeline de geração de sugestões.

O GT atual do prédio será o ponto de partida, não uma verdade presumida. Ele será
auditado e corrigido no próprio caminho. A versão anterior continuará recuperável
pelo histórico Git, pelo hash registrado e pelos resultados experimentais já
produzidos.

## 2. Critérios de sucesso

O trabalho estará concluído quando:

1. `predio_v1.ifc` e `casa_v1.ifc` tiverem, cada um, um YAML carregável pelo
   código atual;
2. todo item em `items` estiver com `verified: true`, chave natural completa,
   valor, unidade implícita ou explícita e justificativa rastreável;
3. itens sem evidência suficiente estiverem em `skipped` com o motivo;
4. não existirem chaves naturais ou `issue_id` duplicados;
5. os hashes dos IFCs, do IDS e, no prédio, do GT anterior estiverem registrados
   no metadata; o hash final do próprio YAML estará no commit e nos resultados
   do benchmark, evitando uma referência circular;
6. duas execuções determinísticas do diagnóstico produzirem o mesmo conjunto de
   chaves naturais;
7. o GT legado do prédio permanecer recuperável e seus resultados históricos não
   forem reescritos;
8. um smoke test do runner carregar e avaliar ambos os datasets sem mudanças no
   contrato do `Evaluator`.

## 3. Decisões aprovadas

### 3.1 Um YAML por IFC

Estrutura canônica:

```text
data/evaluation/
├── predio/
│   ├── predio_v1.ifc
│   └── ground_truth.yaml
└── casa/
    ├── casa_v1.ifc
    └── ground_truth.yaml
```

O benchmark novo terá dois datasets originais: `predio` e `casa`. O
`predio_v1_masked.ifc` e seu GT de nomes permanecem disponíveis como artefatos
históricos/experimentais, mas não fazem parte da execução padrão de dois IFCs.

### 3.2 Continuidade do prédio

O arquivo atual `data/evaluation/predio/ground_truth.yaml`, cujo SHA-256 antes da
auditoria é
`D08D2C7466A71C0CDE467A959ED2AEBFD4857D1DA64944E4504F8F97D4EDD6F6`, será
editado a partir de sua base atual. O metadata novo registrará esse hash em
`previous_gt_sha256` e explicará as mudanças de escopo ou valor.

Não haverá um segundo GT selecionável em runtime. Comparações históricas usarão
os resultados já existentes ou a versão do arquivo no commit anterior.

### 3.3 Localidade comum

Os dois projetos serão tratados como situados em **Deodoro, município do Rio de
Janeiro/RJ**. Para contexto técnico térmico, a classificação pública do
LabEEE/UFSC para o município é **ZB 4A**. Essa fonte pública declara não possuir
valor normativo; portanto, o YAML deve distinguir contexto técnico de afirmação
formal de conformidade.

Para incêndio, aplicam-se o COSCIP e as Notas Técnicas vigentes do CBMERJ. A
localidade não prova, sozinha, ocupação, altura normativa, área total construída,
compartimentação, existência de sprinklers ou desempenho de um sistema.

### 3.4 Verdade descritiva não é requisito normativo

O valor esperado do benchmark descreve o que o elemento possui ou o que o
projetista declara como intenção. Um requisito mínimo não será copiado para
`expected_value` como se comprovasse o desempenho real.

Exemplos:

- `fire_required = 60 min` não prova `fire_provided = REI 60`;
- a norma fornecer um método de U não comprova a composição de uma janela;
- uma parede de concreto não é automaticamente portante;
- o nome do ambiente não substitui uma classificação de ocupação de incêndio.

Quando o requisito for relevante para justificar aplicabilidade ou cálculo, ele
será citado em `notes`. Se o desempenho real continuar desconhecido, a issue irá
para `skipped`.

### 3.5 Escopo de propriedades

O GT inicial cobre o conjunto comum e já estudado no projeto:

- `FireRating`;
- `ThermalTransmittance`;
- intenção portante, preservando em `check_property` exatamente o nome produzido
  pelo diagnóstico (`LoadBearing` ou `IsLoadBearing`);
- `Category` de espaço segundo o vocabulário fechado do projeto;
- `system_unclassified`.

`AcousticRating` e `SolarHeatGainCoefficient` encontrados na casa ficam fora
desta primeira entrega. Eles poderão ser adicionados posteriormente ao mesmo
YAML, sem mudar o formato, quando houver evidência suficiente.

## 4. Contrato do YAML

O formato permanece o já aceito por `src/experiment/evaluator.py`:

```yaml
metadata:
  protocol: evidence-audited-v1
  input_ifc_sha256: "..."
  ids_sha256: "..."
  previous_gt_sha256: "..."  # somente prédio
  verified_by: "valor específico do dataset; distingue revisão autoral do prédio de derivação determinística da casa"
  verified_at: "AAAA-MM-DD"
  locality: "Deodoro, Rio de Janeiro/RJ"
  total_items: 0
  total_skipped: 0
items:
  - element_guid: "..."
    issue_type: pset_missing
    check_property: ThermalTransmittance
    issue_id: "..."
    expected_value: 0.0
    accepted_alternatives: []
    verified: true
    notes: "Evidência e derivação sucintas."
skipped:
  - element_guid: "..."
    issue_type: pset_missing
    check_property: FireRating
    issue_id: "..."
    reason: "Desempenho real não comprovado."
```

Não serão adicionadas classes complexas, múltiplos perfis de GT ou seleção de
camadas no runner. O loader atual lê `metadata` e `items`; `skipped` é uma seção
documental e não participa da pontuação.

## 5. Política de inclusão por propriedade

### 5.1 `ThermalTransmittance`

Um item poderá entrar em `items` quando houver uma destas evidências:

- valor declarado por fonte técnica do projeto e confirmado pelo autor; ou
- cálculo reproduzível com composição, espessuras, condutividades/resistências,
  direção do fluxo e resistências superficiais explicitadas.

Hipóteses genéricas como “vidro simples = 5,7” ou “fibrocimento = 4,6” não serão
tratadas como corretas sem especificação do conjunto. Camadas incompletas,
materiais ambíguos ou propriedades térmicas não rastreáveis irão para `skipped`.

### 5.2 `FireRating`

Um item somente entrará quando o desempenho fornecido estiver declarado no
projeto, laudo, ensaio, memória técnica ou for atestado conscientemente pelo
autor como intenção de projeto. O COSCIP/CBMERJ pode justificar a exigência, mas
não comprova o desempenho fornecido.

As classes `R`, `E`, `I`, `REI`, `EI` e `P-CF` não serão consideradas
intercambiáveis sem justificativa explícita. Portas, escadas, paredes de
compartimentação e elementos estruturais serão tratados segundo suas funções.

### 5.3 `LoadBearing`

Não será inferido apenas por classe IFC, material, espessura ou posição. Entrará
quando houver declaração no modelo/projeto estrutural ou confirmação inequívoca
da intenção pelo autor. Ausência de evidência não equivale a `false`.

### 5.4 `Category`

Será usado o vocabulário fechado já adotado pelo projeto. O mapeamento poderá
partir do `LongName`, mas precisa de confirmação do autor. Casos sem rótulo
canônico inequívoco irão para `skipped`, em vez de ampliar o vocabulário durante
a construção do GT.

### 5.5 `system_unclassified`

O rótulo será incluído quando materiais/camadas e intenção construtiva forem
suficientes e confirmados. Nomes genéricos, como “alvenaria” sem tipo de bloco,
não autorizam um rótulo mais específico.

## 6. Fontes normativas e direitos de uso

Não serão incluídas cópias não autorizadas de normas ABNT. O trabalho poderá
consultar catálogo oficial e documentos institucionais públicos, registrando em
`notes` título, edição, órgão e URL necessários para reproduzir a decisão.

Fontes de contexto identificadas:

- Catálogo ABNT: <https://www.abntcatalogo.com.br/>;
- zoneamento LabEEE/UFSC: <https://labeee.ufsc.br/zoneamento/>;
- Notas Técnicas do CBMERJ: <https://www.cbmerj.rj.gov.br/notas-tecnicas/>;
- COSCIP compilado: Decreto Estadual nº 42/2018 com alterações;
- ABNT NBR 15220-3:2024 e ABNT TR 15220-3-1:2024 Versão Corrigida:2025;
- ABNT NBR 15575 partes 1, 4 e 5 nas formas consolidadas de 2025;
- CBMERJ NT 1-04:2019, NT 2-01:2020, NT 2-05:2023, NT 2-08:2019
  atualizada em 2025, NT 2-09:2025 quando aplicável, NT 2-18:2022 e
  NT 2-19:2025 atualizada em 2025;
- ABNT NBR 14432, NBR 9077, NBR 11742 e NBR 15965-6, quando aplicáveis.

A classificação de uso A-1/A-2 será premissa autoral explícita. Para A-1, não se
inferirá violação por ausência de extintor ou sinalização no IFC. Para A-2, área,
altura, pavimentos, população e sistemas de proteção ainda precisam ser
confirmados antes de transformar uma exigência do COSCIP em verificação. Ausência
de objeto no IFC não demonstra ausência física, e o GT não equivale a aprovação
ou certificado do CBMERJ.

Documentos públicos poderão ser baixados para pesquisa local apenas a partir da
fonte oficial. Redistribuição no pacote do benchmark dependerá de licença
expressa; na ausência dela, o metadata do YAML guardará somente URL, versão e
hash do arquivo consultado.

## 7. Fluxo de produção

1. Registrar hashes e metadados das entradas.
2. Executar o diagnóstico determinístico sem LLM.
3. Agrupar issues equivalentes para tornar a revisão viável.
4. Importar os valores atuais do prédio como candidatos, nunca como aprovação
   automática.
5. Gerar candidatos da casa somente a partir de evidência do IFC, cálculo
   reproduzível ou confirmação do autor.
6. Apresentar grupos e justificativas para revisão.
7. Expandir as decisões agrupadas para itens individuais com chave natural.
8. Mover incertezas para `skipped`.
9. Validar o YAML e congelar seu hash.

O LLM avaliado pelo benchmark não participa de nenhuma etapa de geração do GT.

## 8. Compatibilidade mínima com o código

O núcleo do `Evaluator` não precisa mudar. O trabalho de integração posterior se
limita a:

- garantir que a casa use o mesmo formato de YAML;
- cadastrar `casa` como dataset do runner de benchmark;
- fornecer contexto por dataset: residencial multifamiliar para o prédio,
  residencial unifamiliar para a casa, ambos em Deodoro/RJ;
- validar hashes e presença dos arquivos antes da fila;
- manter `--reuse-equivalent`;
- gerar relatórios separados para `predio` e `casa`.

Não haverá interpretação normativa no computador de benchmark. O novo hardware
receberá IFCs e GTs já congelados.

## 9. Validações e tratamento de erro

O congelamento deve falhar antes do benchmark se houver:

- hash de IFC/IDS divergente do metadata;
- chave natural ou `issue_id` duplicado;
- item com `verified: false` dentro de `items`;
- `expected_value` ausente;
- item que não case com uma issue do diagnóstico;
- contagem declarada diferente da contagem real;
- cálculo numérico sem entradas ou unidade rastreáveis.

Uma fonte normativa inacessível, material ambíguo ou falta de projeto técnico não
é erro de execução: a issue vai para `skipped` e o motivo é contabilizado.

## 10. Estratégia de testes

- teste de carga dos dois YAMLs com `GroundTruth.from_yaml()`;
- teste de unicidade das chaves naturais e `issue_id`;
- teste de casamento de cada item com uma issue real;
- teste de hashes e contagens do metadata;
- teste parametrizado das memórias de cálculo aceitas;
- teste de determinismo do diagnóstico em duas execuções;
- smoke test do runner com Ollama simulado para cada dataset;
- regressão garantindo que prompts, normalização e `reuse-equivalent` não foram
  alterados pela inclusão da casa;
- verificação de que o GT anterior do prédio permanece recuperável no Git.

## 11. Fora de escopo desta especificação

- instalador Windows e downloads de Ollama/modelos;
- telemetria completa de hardware e integração com `llmfit`;
- relatório `.zip` do benchmark;
- execução da matriz de modelos;
- inclusão de `AcousticRating` e SHGC;
- comprovação formal de conformidade legal dos projetos;
- revisão por segundo especialista.

Esses itens pertencem aos subprojetos seguintes. A ordem permanece: congelar os
GTs, adaptar o benchmark para dois IFCs e, por último, criar o instalador de um
clique.
