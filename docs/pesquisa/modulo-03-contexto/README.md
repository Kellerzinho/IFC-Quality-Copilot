# M3 — Base documental, receitas e cobertura do Apêndice A

Revisão documental `2026-10-12-r2` (12/10/2026). Apoio ao [planejamento M3](../../planejamento/modulo-03-contexto-enriquecimento.md). **Planejamento concluído e verificado, sem pendência de aprovação de Felipe; implementação não concluída.** O planejamento descreve trabalho futuro; **não há receita executável, inferência ou teste funcional realizado nesta entrega**.

## Arquivos e base única

- [Matriz canônica JSON](matriz-canonica.json): fonte recebida integral em `source_matrix_original`, páginas extraídas em `family_context`, representação de fonte em `records.source_layer` e planejamento em `records.operational_layer`. Não importar diretamente como catálogo publicado.
- [CSV para revisão](matriz-revisao.csv): projeção dos 313 registros da mesma revisão; campos estruturados conservam JSON para não perder fontes, alternativas e critérios. Importar como texto/UTF-8; não editar como segunda base independente.
- [Fichas individuais](fichas-apendice-a.md): projeção legível de todos os registros, com âncoras, caminhos, limites, tarefas e cenários verificáveis.
- [Baseline e estudos existentes](baseline.md): achados da auditoria local anterior, resultados brutos existentes, condições e limites; não reexecutados.
- [Verificação documental](verificacao-documental.json): resultados por check, conteúdo individual das 313 fichas, contagens, JSON/CSV, fontes, páginas, links, revisão Astra xhigh, hashes e preservação. Inclui a distinção dos novos arquivos M4 autorizados em tarefa separada.

Uma alteração futura parte da base canônica, incrementa sua revisão, documenta a razão e regenera as projeções. IDs A1-001…A10-009 da pesquisa foram mantidos. `REC3-*` é identificador de receita planejada, não de operação implementada. Os antigos `F01`…`F24` citados nas fichas são referências da pesquisa: o arquivo `fixtures_contexto_daiane2025.json` **não integra o ZIP recebido**. Não são testes disponíveis; os novos `TR3-*` especificam critérios futuros, sem fingir execução.

## Fontes efetivamente acessadas e limitações

O PDF integral local `Downloads/2025 - Dissertação Daiane.pdf` tem **217 páginas**, 11.380.259 bytes e SHA-256 `82ead7b5f06fd06247f9f057727bab071ab1c08de4fe42412bebeb9e0c06877a`. Foi aberto; as dez páginas do Apêndice A, impressas **161–170 / PDF 162–171**, foram extraídas e conferidas visualmente. Não se afirma releitura das 217 páginas. Também foram lidos os trechos impressos 90–91, 100, 124–125 e 131 e trechos pertinentes de B nas páginas 175, 181, 183 e 185. [Fonte fornecida da dissertação](https://drive.google.com/file/d/1TNRFxlXW9osGvrkNavm9t2A-qbQpbNcu/view).

O ZIP local `Downloads/IFC-Quality-Copilot-Pesquisa-Contexto-M3-2026-10-09.zip` tem 336.721 bytes, nove membros e SHA-256 `e4bab30f48eaf6f57b79aaf514c7306489f89e834dfa000dc72637ebdbd75ca7`. Os membros foram validados e lidos em pasta temporária, sem sobrescrever originais. Os três hashes MD/JSON/CSV coincidem com a auditoria interna; os 203 registros CSV correspondem ao JSON nos campos comuns. O JSON de origem foi incorporado integralmente na base canônica, evitando criar outra transcrição concorrente. As recomendações antigas contidas nele, especialmente catálogo offline e revisão do rascunho, são **históricas**; a política atual está no M3 e em `current_policy`.

A síntese `sintese-para-felipe.md`, Library `libfile_030b0f9c3b60819182f3de320e3ed7a5`, foi resolvida por `prepare_materialize`. O helper oficial de materialização falhou ao aplicar `os.setxattr`, indisponível no runtime Windows; o destino final não existe. **Conteúdo não lido nem usado como evidência.** Não foi criado download alternativo sem metadados. Sua incorporação posterior, como referência de domínio/metodologia e não gabarito automático, é tarefa documental de desenvolvimento; não impede concluir este planejamento com o PDF, a pesquisa local e a [bibliografia já incorporada](../sintese-bibliografica-daiane-29-artigos.md).

XML IDS original de 2025 e planilha editável continuam ausentes. Nenhum foi reconstruído como se fosse original. Conferir o PDF permite planejar cobertura, mas não provar equivalência de cardinalidade, regex, facetas ou binding ao XML. O pacote público de 2026/Cost_Prop/seis famílias não substitui esta fonte.

## Denominadores auditados

| Base de contagem | Total | Interpretação |
|---|---:|---|
| Registros alfanuméricos da representação recebida | 203 | 10 classes, 28 atributos/condições, 10 materiais, 19 grupos de classificação, 82 propriedades customizadas, 36 propriedades padrão e 18 quantidades |
| Propriedades/quantidades por família | 136 | 82 + 36 + 18; não são propriedades únicas |
| Identificadores lexicais de propriedades/quantidades | 72 | `target_identifier_literal`, sem rótulo traduzido explicativo; homônimos podem ter significados distintos |
| Pares literais conjunto + identificador | 85 | Ainda não são conceitos/bindings únicos por schema/papel |
| Grupos de classificação / pares código-nome contidos | 19 / 58 | Alternativas dentro de um domínio, não 58 exigências simultâneas |
| Registros sem desdobrar condição USERDEFINED A1-007 | 202 | A1-007 desdobra a mesma célula de A1-006; A2-006 mantém a condição agrupada. IDs e convenção recebida preservados |
| Metadados de entrega | 50 | Cinco por família: objeto, requerente, fornecedor, fase, propósito |
| Requisitos geométricos | 50 | Cinco por família; não convertidos em propriedades EB_Orçamento |
| Requisito documental | 10 | Um por família, “Não requerido”; não autoriza ingestão de memorial |
| Total de registros planejados com rastreabilidade | 313 | 203 + 50 + 50 + 10, em denominadores separados |
| Cenários de aceite especificados | 1.328 | Seis por registro alfanumérico e um por auxiliar; não são testes executados, amostras independentes ou contagem do corpus |

| Família | Alfanuméricos | EB_Orçamento | Pset padrão | Qto | Propriedade/quantidade | Auxiliares |
|---|---:|---:|---:|---:|---:|---:|
| [A1 — Janela](fichas-apendice-a.md#a1) | 24 | 7 | 7 | 0 | 14 | 11 |
| [A2 — Porta](fichas-apendice-a.md#a2) | 28 | 10 | 9 | 0 | 19 | 11 |
| [A3 — Parede](fichas-apendice-a.md#a3) | 26 | 13 | 2 | 5 | 20 | 11 |
| [A4 — Forro](fichas-apendice-a.md#a4) | 22 | 12 | 1 | 3 | 16 | 11 |
| [A5 — Piso](fichas-apendice-a.md#a5) | 19 | 7 | 3 | 3 | 13 | 11 |
| [A6 — Revestimento de parede](fichas-apendice-a.md#a6) | 24 | 13 | 2 | 3 | 18 | 11 |
| [A7 — Laje](fichas-apendice-a.md#a7) | 18 | 7 | 4 | 1 | 12 | 11 |
| [A8 — Pilar](fichas-apendice-a.md#a8) | 16 | 5 | 4 | 1 | 10 | 11 |
| [A9 — Viga](fichas-apendice-a.md#a9) | 17 | 6 | 4 | 1 | 11 | 11 |
| [A10 — Armadura](fichas-apendice-a.md#a10) | 9 | 2 | 0 | 1 | 3 | 11 |
| **Total** | **203** | **82** | **36** | **18** | **136** | **110** |

Contar `target_literal` completo, incluindo rótulos traduzidos como “É externa (IsExternal)”, produz **79 textos / 90 pares conjunto-rótulo**. A contagem 72/85 usa o identificador explicitado nesses rótulos; a diferença não demonstra conceitos adicionais.

Os 195/88/34 registrados anteriormente são mantidos como contagens históricas de outra representação. Sem a base linha a linha que originou esses totais, não é possível atribuir cada diferença a uma inclusão ou erro. Não se inventa reconciliação aritmética. Publicar agora os denominadores auditados não altera os artefatos históricos.

Chamadas LLM dependem dos elementos selecionados, campos aplicáveis, evidência, regras suficientes, roteamento, agrupamento, orçamento e retries. **136 entradas não implicam 136 chamadas**. Uma IfcReinforcingBar pode representar um grupo, e cada receita pode servir muitos elementos. Campos inaplicáveis, determinísticos, sem evidência ou com erro não exigem geração.

## Camada fiel e camada operacional

`source_matrix_original` mantém o objeto recebido com todas as observações e divergências. `source_layer` conserva conteúdo dos quadros por registro e identifica quando datatype/unidade não consta na célula. Termos como “IFC4: IfcLabel” acrescentados pela pesquisa a atributos não foram apresentados como texto da tabela. Unidades por convenção do nome e esclarecimentos de B são indicados como interpretação reportada, não unidade explícita do IFC real. A transcrição normaliza layout/quebras, não constitui fac-símile; os textos integrais extraídos das dez páginas permitem confronto.

`operational_layer` especifica significado, papel, aplicabilidade da receita, caminhos candidatos, canais, transformações, rotas, conflitos, tarefas e critérios. Aplicabilidade semântica da receita não modifica a seleção formal M2. Se o IDS exigir característica de um componente inexistente/inadequado — dobradiça de porta de correr, material de isolamento em parede sem isolante, entre outros — apresentar **requisito a revisar**, sem modificar a fonte para passar.

<a id="divergencias"></a>

| Divergência preservada | Consequência operacional |
|---|---|
| A4 informa Pset_DoorCommon.Status para IfcCovering | Ler o literal; Pset_CoveringCommon é candidato de reconciliação. Não corrigir silenciosamente o IDS |
| A3 escreve Heigth | Height pode ser candidato de leitura por mapping curado; não equivale à presença do alvo literal |
| Densidade_Porta: categoria IfcLabel em A, IfcReal/massa por área em B | Significados/contratos distintos; não converter quatro classes usando apenas dois intervalos de B |
| GlassLayers e GlassThickness1 têm tipos diferentes em A versus template/B | Preservar ambos; validar destino segundo perfil escolhido, sem coerção automática |
| Area_Forma usa entidade IfcQuantityArea dentro de EB_Orçamento em A | Definir portador válido em binding operacional; quantidade e medida de propriedade não são intercambiáveis |
| Usos_Forma: Label em A, Integer em B; usos versus reaproveitamentos | Tipo e convenção precisam de decisão curatorial antes da publicação |
| Retirado/Recolocado compartilham código nos quadros A4–A6 | Manter dois pares fonte; não escolher nome pelo código sem resolver ambiguidade |
| Aplicacao_Argamassa_Massa e Tipo_Emassamento têm descrições divergentes em B | Não confundir preparo/aplicação nem emassamento/lixamento; requisito a revisar |
| Weight em A e Weigth no relatório B | Alias apenas candidato; XML ausente não foi corrigido nem inspecionado |
| USERDEFINED em A1/A2 e UserDefinedType de B | Destinos textuais dependem do schema; não criar atributo inexistente |

As demais divergências são conservadas em cada ficha. A6 tem `3E.14.02.04.00.00.00` no cabeçalho e na classificação; uma suspeita inicial de diferença foi descartada após confronto com a página. Não houve correção indevida desse código.

## Receitas configuráveis e canais de leitura

As 72 entradas de `property_policy_templates` são **modelos de redação da política por nome**, não catálogo de 72 conceitos universais. Cada uma se instancia por família, fonte, papel, schema e requisito nos 203 registros. `Tipo_Revestimento`, `Tipo_Argamassa`, `Tipo_Chapisco`, `Tamanho_Placa` e `Tipo_Escora` exigem diferenças por família. As fichas explicitam essas diferenças e os domínios literais; a publicação futura deve separá-las em conceitos/bindings quando necessário.

Fluxo de busca: alvo literal → tipo/ocorrência separados → aliases publicados → componentes/relações permitidos → seleção textual local. O inventário pode ser mais amplo que o pacote LLM, mas seu manifesto registra canais consultados, omissões e erros. Um coletor genérico não substitui uma receita de domínio. Os pseudocaminhos da pesquisa preservados no JSON não são queries prontas nem prova de suporte em todos os schemas.

<a id="canal-p"></a>

### Canal P

Ocorrência E → IfcRelDefinesByProperties (RelatedObjects contém E) → RelatingPropertyDefinition. Para IfcPropertySet, conferir Name e HasProperties; ler SingleValue.NominalValue, EnumeratedValue.EnumerationValues selecionados, ListValue.ListValues, BoundedValue, TableValue e ReferenceValue conforme capacidade. Não usar valores permitidos da enumeração como selecionados. ComplexProperty conserva hierarquia. Conjunto predefinido especializado usa leitor de seus atributos, não presume HasProperties.

<a id="canal-t"></a>

### Canal T

Ocorrência E → IfcRelDefinesByType (RelatedObjects contém E) → RelatingType; atributos do tipo e HasPropertySets separados dos da ocorrência. Validar cardinalidade e schema; registrar regra efetiva por categoria. Não aplicar override de Pset indistintamente a PredefinedType/OperationType/PartitioningType.

<a id="canal-q"></a>

### Canal Q

E → IfcRelDefinesByProperties → IfcElementQuantity(Name do conjunto) → Quantities(Name, entidade de quantidade, valor apropriado, Unit, MethodOfMeasurement no conjunto). Conservar quantidade complexa, conjunto e método. Tipo pode fornecer contexto, mas não substituir medida específica da ocorrência sem contrato.

<a id="canal-m"></a>

### Canal M

E e seu tipo, separadamente → IfcRelAssociatesMaterial.RelatingMaterial. Inspecionar IfcMaterial; MaterialLayerSet/Usage.ForLayerSet.MaterialLayers; MaterialConstituentSet.MaterialConstituents; MaterialProfileSet/Usage.ForProfileSet.MaterialProfiles; listas legadas quando suportadas. Registrar Name/Category/papel, Material.Name, propriedades de material, espessura/perfil/fração e fonte de cada associação. Fração não é espessura; nome de conjunto não é material do componente.

<a id="canal-c"></a>

### Canal C

E/tipo → IfcRelAssociatesClassification.RelatingClassification → IfcClassificationReference (Identification em IFC4; ItemReference em IFC2X3 quando suportado), Name, Location e cadeia ReferencedSource até sistema/edição. Conservar múltiplas associações e os pares código/nome sem corrigir a fonte por suposição.

<a id="canal-d"></a>

### Canal D

E → IfcRelAggregates/IfcRelNests com RelatingObject=E → RelatedObjects; também percorrer direção inversa quando a receita exige o pai. Conservar ID/tipo da relação, extremos, parte, papel e ordem quando definida. Contenção espacial ou proximidade não substitui todo/parte.

<a id="canal-h"></a>

### Canal H

Esquadria E → IfcRelFillsElement com RelatedBuildingElement=E → RelatingOpeningElement; abertura → IfcRelVoidsElement com RelatedOpeningElement=abertura → RelatingBuildingElement. Do hospedeiro só consultar partes/conexões autorizadas com papel comprovado. Ausência da cadeia não prova inexistência física.

<a id="canal-s"></a>

### Canal S

Revestimento E → IfcRelCoversBldgElements/IfcRelCoversSpaces quando existentes no schema: RelatedCoverings contém E → RelatingBuildingElement/RelatingSpace (IfcRelCoversSpaces usa RelatedSpace em IFC2X3 e RelatingSpace desde IFC4; adaptar ao release). Alternativamente inspecionar relações de composição e IfcRelSpaceBoundary com RelatedBuildingElement=E ou hospedeiro, registrando RelatingSpace e InternalOrExternalBoundary. IfcRelContainedInSpatialStructure com RelatedElements contém E → RelatingStructure localiza; um pavimento não equivale a espaço ou hospedeiro.

<a id="canal-x"></a>

### Canal X

Name, Description, ObjectType e Psets autorais de E, tipo e componentes autorizados. Busca local lexical/aliases primeiro, com trecho exato, idioma, negação, ID do portador e papel. Resultado semelhante é candidato de descoberta, não mapping publicado. Não abrir URLs ou documentos referidos pelo texto.

<a id="canal-j"></a>

### Canal J

IfcRelAssignsToProcess/IfcRelAssignsToResource ou grupo/parte explicitamente relacionado: conferir RelatedObjects contém o alvo, RelatingProcess/RelatingResource, papel, etapa e descrição. Presença do recurso no projeto não prova uso no elemento. Capacidade e semântica precisam de ensaio por schema.

<a id="canal-g"></a>

### Canal G

Representation/ObjectPlacement do alvo e partes autorizadas; representação mapeada do tipo com transformação da ocorrência, unidades efetivas e abertura/recortes. Cálculo somente por operação publicada e domínio geométrico testado; bounding box não vira área líquida, volume bruto ou área de fôrma por conveniência.

<a id="canal-a"></a>

### Canal A

Atribuição explícita no mesmo arquivo: IfcRelAssignsToGroup, RelatedObjects contém E, → RelatingGroup; ou IfcRelAssignsToProduct, RelatedObjects contém E, → RelatingProduct (produto/tipo conforme schema). Registrar subtipo, relação, extremos, Name/Description, papel declarado e revisão. Grupo não é decomposição nem prova de função; atribuição a produto não prova hospedeiro físico. Exigir declaração/mapping específico do papel, sem inferir FireExit, LoadBearing ou distribuição de armadura pela simples associação. Não usar este canal como contenção espacial; não atravessar arquivos da federação. Context/View pode ligar representações, sem significar hospedagem. IfcStructuralAnalysisModel agrupa itens analíticos; se houver relação intermediária até objeto físico, conservar a cadeia completa e testar cada papel.

As relações de atribuição foram conferidas em [IfcRelAssignsToGroup](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifckernel/lexical/ifcrelassignstogroup.htm) e [IfcRelAssignsToProduct](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifckernel/lexical/ifcrelassignstoproduct.htm). Elas localizam atribuições; a exigência de prova do papel é política operacional do Copilot. A diferença RelatedSpace/RelatingSpace está no histórico de [IfcRelCoversSpaces](https://standards.buildingsmart.org/IFC/DEV/IFC4_3/HTML/lexical/IfcRelCoversSpaces.html); a presença da entidade na documentação não certifica suporte do backend.

<a id="canal-k"></a>

### Canal K

Conexões explícitas no mesmo arquivo: IfcRelConnectsElements e subtipos suportados, lendo RelatingElement e RelatedElement em ambas as direções quando E é um dos extremos. Conservar ID/subtipo da relação, extremos, Name/Description, ConnectionGeometry quando disponível e papel da ligação. ConnectedTo/ConnectedFrom são entradas de navegação dependentes do schema. Conexão não é decomposição, não determina material/função da junta e não nasce de proximidade visual; ligação de topo exige papel e componente comprovados. Não atravessar arquivos da federação.

## Organização individual do contexto

Cada registro contém `context_organization`: alvo e papel próprios, bloco de requisito separado do observado, navegação, agrupamento das fontes admissíveis, negativo específico, elegibilidade LLM e manifesto de cobertura. Os canais declarados delimitam o percurso operacional; pseudocaminhos e limites recebidos da pesquisa permanecem históricos quando divergirem da política atual, sem ativação implícita.

O MVP M4 reúne dois pares IFC–IDS na mesma sessão e prioriza federação visual. Contexto M3, identidade, diagnóstico e exportação permanecem por arquivo; **nenhuma evidência atravessa arquivos no MVP**. Uma fila LLM serial atende à sessão, inclusive retries. Manual fundamentado registra origem própria, sem atribuí-la ao extrator.

## Transformações, revisão e avaliação

Converter unidade exige fonte, grandeza, papel e unidade conhecidos. Código mantém bruto, normalizado, operação e versão; o valor de destino respeita o tipo contratado. Uma grandeza igual não torna largura de vão e de marco equivalentes. Quantidades declaradas, calculadas e aproximadas são separadas. Nenhuma receita autoriza LLM a calcular geometria, distribuir massa de hospedeiro, inventar constante física ou decidir método de execução não registrado.

Regras podem recuperar ou normalizar o dado; alocação de EAP por contrato é `assigned_by_rule`, não fato recuperado. LLM só interpreta evidência existente. M4 também aceita entrada manual fundamentada, inclusive quando a evidência não está no IFC: registrar origem humana/documental declarada e não atribuí-la retroativamente ao extrator. O código confere tipo, unidade, binding quando existente (ou alvo literal tipado sem mapping), restrições IDS e resolubilidade das fontes antes de habilitar aprovação. Fundamentação externa permanece distinta da evidência disponível no experimento R/R+L.

Conflitos exibem valores e fontes; o responsável decide com justificativa. Proposta, aprovação, aplicação em cópia e resolução revalidada têm estados distintos. Campo desconhecido pelo catálogo permanece verificável por M2 se o requisito é suportado; M3 retorna ausência de mapping, permite manual/curadoria e não deixa LLM publicar correspondência sozinha.

`TR3-<registro>-R/L/C/A/I/E` especifica regra, interpretação com evidência, conflito, ausência, requisito inadequado e erro. Cada registro aponta tarefas M3 e casos CT3 preservados. Os auxiliares têm cenário documental `-D`. A matriz não multiplica automaticamente esses cenários por todos os schemas: cada capacidade exige fixture válida e caso real pertinente; uma combinação não suportada permanece explicitamente assim.

Separar no desenvolvimento: (1) recuperação de fontes, papéis e unidades contra referência independente; (2) interpretação LLM sobre pacote congelado; (3) ponta a ponta e revisão humana. Um ganho do extrator não será atribuído à LLM. As métricas, controles de vazamento e condições R versus R+L do [M3 §14](../../planejamento/modulo-03-contexto-enriquecimento.md#m3-avaliacao) permanecem obrigatórios. A [bibliografia dos 29 artigos](../sintese-bibliografica-daiane-29-artigos.md) orienta limites e métodos, sem validar antecipadamente a combinação local.

## Referências técnicas pontuais conferidas

Os caminhos de janela e a separação de abertura/corpo foram conferidos na [definição IFC4 de IfcWindow](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifcsharedbldgelements/lexical/ifcwindow.htm). Camadas/tratamentos e espessura da primeira camada interior constam no [Pset_DoorWindowGlazingType](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifcsharedbldgelements/pset/pset_doorwindowglazingtype.htm). Quantidades de revestimento distinguem área bruta/líquida e espessura em [Qto_CoveringBaseQuantities](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifcsharedbldgelements/qset/qto_coveringbasequantities.htm).

A possibilidade de barra/grupo e o escopo do peso foram conferidos em [IfcReinforcingBar](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifcstructuralelementsdomain/lexical/ifcreinforcingbar.htm) e [Qto_ReinforcingElementBaseQuantities](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifcstructuralelementsdomain/qset/qto_reinforcingelementbasequantities.htm). A [documentação oficial da API bSDD](https://github.com/buildingSMART/bSDD/blob/master/Documentation/bSDD%20API.md) é referência de interface; nossa política de não enviar conteúdo de projeto é requisito próprio, não garantia decorrente da existência da API. Demais URLs da pesquisa são preservadas como referências recebidas, sem alegar nova auditoria de todas elas.
