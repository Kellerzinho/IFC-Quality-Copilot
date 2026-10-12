# Módulo 1 — Domínio e catálogo semântico

**Plano de implementação proposto — 9 de outubro de 2026.**
**Estado:** documentação para revisão; nenhuma tarefa funcional deste plano foi executada.
**Coordenação de domínio e pesquisa:** Felipe. Curador nominal e liderança de implementação: a definir.
**Base:** [consolidação preservada](CONSOLIDACAO-2026-10-09.md), [decisões confirmadas](README.md#decisoes-posteriores-de-0910) e [sete frentes](mapa-sete-frentes.md).

**Nova integração bibliográfica — 10/10/2026:** [fundamentação e matriz referência → decisão/risco → tarefa/critério](#m1-bibliografia), baseada na [síntese dos 29 artigos](../pesquisa/sintese-bibliografica-daiane-29-artigos.md). Adendo documental aos três planos; decisões, IDs e escopo permanecem. Novos refinamentos estão marcados como propostas.

**Navegação:** [Escopo](#m1-escopo) · [Inventário](#m1-inventario) · [Modelo de dados](#m1-modelo) · [Curadoria](#m1-curadoria) · [Daiane](#m1-daiane) · [Interfaces](#m1-interfaces) · [Pacotes](#m1-pacotes) · [Percursos](#m1-percursos) · [Tarefas](#m1-tarefas) · [Testes](#m1-testes) · [Entregas](#m1-entregas) · [Esforço](#m1-esforco) · [Riscos](#m1-riscos) · [Aceite](#m1-aceite) · [Fontes](#m1-fontes) · [Bibliografia integrada](#m1-bibliografia).

<a id="m1-escopo"></a>

## 1. Objetivo, arquitetura e limites de aprovação

**Objetivo:** disponibilizar um catálogo de domínio local, versionado, curado e consultável pela plataforma, que descreva o significado de propriedades, sua aplicabilidade, suas representações IFC e a evidência admissível para propor valores. O primeiro perfil cobre arquitetura e estrutura da dissertação de Daiane, incluindo `EB_Orçamento`. O catálogo deverá permitir novos cadastros e a futura incorporação do dicionário brasileiro de Juliana.

**Arquitetura proposta:** uma biblioteca de domínio dentro da aplicação Python existente, com leitura de pacotes imutáveis, serviço de curadoria e adaptadores de compatibilidade. Separar o estado de edição do pacote publicado e separar ambos dos valores observados em cada IFC. As sete frentes não exigem sete serviços.

**Base tecnológica observada:** Python, Pydantic, IfcOpenShell e módulos existentes de bSDD, semântica, perfis e fundação. **Escolha técnica proposta para esta implementação:** Pydantic para modelos/validações, JSON UTF-8 para intercâmbio e pacotes publicados, SQLite da biblioteca padrão para rascunhos/eventos de curadoria e armazenamento interno aprovado pela frente 6. Essa escolha precisa passar pela revisão técnica; não aprova implantação multiusuário, troca de stack visual ou instalação de dependências nesta etapa.

**Especificação funcional confirmada:** D01–D19 do índice de planejamento, com os seguintes limites:

- O operador fornece IDS pronto; sua validação suportada independe de cadastro no catálogo.
- Operador solicita cadastro/mapeamento; curador aprova e publica; LLM somente sugere.
- Definição, aplicabilidade e evidência são separadas. Reutilizar um conceito exige mesmo significado.
- O projeto fixa uma versão do catálogo; a atualização é explícita, com diff, reprocessamento e preservação do histórico.
- Cada análise identifica as versões exatas de IFC, IDS e catálogo. Mudanças geram nova análise.
- A plataforma oferecerá tabela editável com detalhe e ações de adicionar/duplicar linha como direção de curadoria; layout detalhado e stack permanecem abertos. Duplicar cria rascunho e exige revisão de identidade, não publica um novo conceito.
- Cadastro sem código seleciona operações já suportadas. Uma extração ou cálculo novo exige implementação e fica sem enriquecimento até então.
- Os resultados do módulo 2 distinguem conforme, não conforme, não aplicável, não verificado e erro. Lista vazia de elementos não aprova automaticamente: interpretar cardinalidade/exigência do IDS e mostrar a ausência.
- A visualização principal será por elemento, com alternativa por requisito, mostrando esperado, encontrado e origem.
- A primeira entrega do módulo 2 fará análise individual. Visualização federada de vários IFCs é extra posterior, integrada à frente 4, com arquivos e saídas separados e proveniência preservada.
- IFC2X3, IFC4 e IFC4.3 são metas de suporte aprovadas; cada capacidade depende de teste, caso real e fixtures. Isso não amplia o domínio para infraestrutura nem comprova suporte instalado.
- Validar e exportar diagnóstico independe de enriquecimento/LLM. O resultado completo fica rastreável na plataforma e em relatório exportável; BCF da frente 5 consome o mesmo diagnóstico, com formatos/limites/timing a ensaiar.
- A execução do produto permanece local ou na infraestrutura interna do IME, incluindo dados, índices, logs, backups e ativos.

Os nomes de classes, estruturas, caminhos novos, assinaturas, estratégias de armazenamento, estimativas e políticas adicionais descritos adiante são **propostas implementáveis**, não decisões já confirmadas por Felipe nem capacidades existentes.

### 1.1 Dentro da primeira entrega do módulo

1. Inventariar e reconciliar o piso Daiane A.1–A.10 e B, com cobertura por entrada e divergências rastreáveis.
2. Cadastrar conceitos, unidades, valores permitidos, representações IFC, aplicabilidade, aliases e políticas de evidência.
3. Consultar um pacote local fixado, distinguindo resolução exata, ambiguidade, ausência e operação indisponível.
4. Solicitar, revisar, aprovar, publicar, importar, comparar e fixar versões do catálogo.
5. Adaptar consumidores existentes por uma fronteira explícita e verificável, sem substituir silenciosamente a condição experimental histórica.
6. Entregar contrato de curadoria à frente 4 e de evidência à frente 3; integrar uma fatia mínima de interface em trabalho conjunto.
7. Medir cobertura, ambiguidades, procedência, estabilidade de IDs e execução sem rede.

### 1.2 Fora desta entrega

Autoria/exportação de IDS pela UI é extensão futura das frentes 1, 2 e 4. Orçamento operacional SINAPI, composições, preços e atualização de custos ficam para depois. Não prometer preenchimento automático de toda propriedade, conformidade de todo schema IFC, inferência de fatos ausentes ou substituição do projetista. Não implementar aqui um novo validador IDS completo, writer IFC, viewer 3D, servidor institucional ou estudo humano.

Memoriais e especificações externas dependem da decisão do orientador e de um fluxo de evidência ainda a definir. O modelo de fontes pode reservar referências a documentos; ingestão, OCR, busca e inferência sobre esses documentos não entram automaticamente no escopo.

### 1.3 Casos de uso e comportamento observável

| Caso | Ação | Resultado esperado |
|---|---|---|
| UC01 — Consultar significado | Operador seleciona uma propriedade no resultado | Vê definição, fonte, versão, bindings aplicáveis, unidades e limitações; definição não é apresentada como valor do elemento |
| UC02 — Reutilizar conceito | Curador adiciona uso de um conceito existente em outra classe | Novo vínculo de aplicabilidade/binding, mantendo o ID do conceito quando significado, grandeza e qualificação coincidirem |
| UC03 — Solicitar cadastro | Operador informa campo desconhecido em um IDS | Solicitação ligada ao IDS/req.; a análise dos requisitos suportados continua; não surge equivalência automática |
| UC04 — Cadastrar com operação existente | Curador seleciona leitura exata de propriedade e evidência admissível | Novo rascunho validável; publicação depende de revisão e compatibilidade, sem código enviado pelo usuário |
| UC05 — Solicitar nova operação | Cadastro exige cálculo ainda inexistente | Capacidade explicitamente indisponível, tarefa de engenharia e abstenção de enriquecimento |
| UC06 — Resolver conflito | Duas fontes ou aliases levam a candidatos diferentes | Candidatos e razões preservados; nenhuma escolha silenciosa pelo primeiro resultado |
| UC07 — Publicar versão | Curador aprova um conjunto de alterações verificadas | Pacote imutável, manifesto e recibo de publicação; projetos existentes mantêm o pacote fixado |
| UC08 — Atualizar projeto | Operador autorizado examina diff entre pacotes | Nova análise após atualização explícita; análises e aprovações anteriores permanecem consultáveis |
| UC09 — Migrar para Juliana | Curador importa snapshot do dicionário futuro | Mapeamentos revisados e relatório de perdas/conflitos; nenhuma reescrita de IDs históricos |
| UC10 — Operar desconectado | Consulta, curadoria e análise sem acesso público | Funciona com ativos internos; pacote ausente/corrompido produz limitação explícita, sem fallback de API |

<a id="m1-inventario"></a>

## 2. Inventário real e estratégia de aproveitamento

A leitura dos arquivos fundamenta a distinção entre implementação atual e trabalho proposto. Uma forma de protocolo compatível não comprova localidade, aprovação semântica ou cobertura funcional.

| Caminho existente | O que já oferece | Uso previsto / lacuna |
|---|---|---|
| [src/foundation/contracts.py](../../src/foundation/contracts.py) | Protocolos `SemanticCatalog`, `GroundingContextBuilder`, `ModelInspector`, `RequirementSource` | Preservar fronteiras existentes e introduzir contrato rico de catálogo por adaptação; faltam versão, bindings, aplicabilidade, curadoria e proveniência detalhada |
| [src/bsdd/models.py](../../src/bsdd/models.py) | `BSDDClassData`, `BSDDPropertyData`, origem/status/aliases | DTOs úteis na compatibilidade; unidade única e enumeração de strings não representam o domínio inteiro |
| [src/bsdd/client.py](../../src/bsdd/client.py) | Resolução/busca via HTTP, metadados, wrappers antigos e cache | Reaproveitar conhecimento do formato, não instanciar cliente público no provedor local; consulta ausente hoje pode ir à API |
| [src/bsdd/cache.py](../../src/bsdd/cache.py) | Cache JSON por namespace/chave | Não é repositório de publicação: erro de leitura vira cache vazio, escrita direta não é protocolo de publicação atômica |
| [src/bsdd/context_builder.py](../../src/bsdd/context_builder.py) | Monta contexto para issues e IDS | Depende também de métodos legados; normalizações e origem precisam de adaptação explícita |
| [src/semantic_registry/registry.py](../../src/semantic_registry/registry.py), [resolver.py](../../src/semantic_registry/resolver.py), [source_policy.py](../../src/semantic_registry/source_policy.py) | Registro/resolução e classificação de fontes | Usar como camada legada isolada; URI construída por nome e domínio reconhecido não provam existência/aprovação |
| [src/semantic/property_match.py](../../src/semantic/property_match.py) | Normalização textual e comparação flexível | Pode gerar candidatos, nunca decidir sozinho equivalência semântica ou conformidade IDS |
| [src/translator/pset_resolver.py](../../src/translator/pset_resolver.py) | Busca exata, aliases e busca em outros Psets; informa localização e coincidência exata | Separar recuperação de evidência e validação do caminho exigido no IDS; revisão funcional pertence também à frente 2 |
| [src/profiles/registry.py](../../src/profiles/registry.py) | Perfis de prontidão e criação de perfil a partir de IDS | Preservar como consumidor/adaptador de entrada; perfil de prontidão não é catálogo nem editor IDS |
| [src/ifc_analyzer/universal_extractor.py](../../src/ifc_analyzer/universal_extractor.py), [material_reader.py](../../src/ifc_analyzer/material_reader.py), [model_evidence.py](../../src/ifc_analyzer/model_evidence.py) | Extração e evidências de elementos | Alimentar observações tipadas com caminho, schema, unidade e ocorrência/tipo; verificar cada capacidade |
| [src/ifc_analyzer/extractors/quantity_extractor.py](../../src/ifc_analyzer/extractors/quantity_extractor.py) | Quantidades, incluindo aproximações | Distinguir Qto declarado, cálculo geométrico e estimativa por bounding box; não tratar como métodos equivalentes |
| [src/suggestion_engine/](../../src/suggestion_engine/) | Grounding, regras, sugestões, cache, normalização e revisão por issue | Consumir receitas aprovadas e evidência; incorporar identidade do pacote/receita na nova condição |
| [src/foundation/locality.py](../../src/foundation/locality.py), [adapters.py](../../src/foundation/adapters.py), [review.py](../../src/foundation/review.py) | Base de localidade, adaptação e revisão | Coordenar com frente 6; não supor política já aplicada a todos os caminhos |
| [src/experiment/](../../src/experiment/) | Identidade experimental, locks, bundles e políticas históricas | Referência de rastreabilidade; preservar casos e resultados históricos, sem generalização silenciosa |
| [src/ui/](../../src/ui/), [src/pipeline.py](../../src/pipeline.py), [src/models.py](../../src/models.py) | Interface e orquestração existentes | Pontos de integração futuros; esta documentação não os modifica |
| [data/ids_templates/](../../data/ids_templates/), [data/ids_schema/ids.xsd](../../data/ids_schema/ids.xsd) | Templates e arquivo XSD atual | Não confundir templates com cobertura Daiane; XSD observado é placeholder e não certifica validação completa |

### 2.1 Lacuna concreta entre SemanticCatalog e BSDDContextBuilder

O contrato atual declara exatamente:

```python
search_classes_text(query: str, domain: str = "IFC") -> list[BSDDClassData]
get_class_metadata(class_uri: str) -> BSDDClassData
resolve_property(property_uri: str) -> BSDDPropertyData
```

O builder recebe um `BSDDClient` concreto e também chama:

```python
search_class(query, domain)       # lista de dicts: name, uri, domain, description
get_class_properties(class_uri)  # lista de BSDDProperty
get_property_values(property_uri)  # lista de strings
```

Portanto, implementar apenas os três métodos do protocolo **não basta** para substituí-lo no builder. Além disso, o builder usa canonicalização do registro padrão, normalizações de nomes e correspondências textuais, e pode apresentar origem como `live` após consulta bem-sucedida mesmo quando a origem precisa ser diferenciada. Exceções podem virar contexto vazio/offline. São lacunas distintas: forma, significado, procedência e tratamento de erro.

**Solução proposta:** `LocalSemanticCatalogAdapter` preserva a forma dos três métodos; `LegacyBSDDContextAdapter` expõe os três wrappers adicionais sobre a mesma leitura fixada. O novo caminho de grounding consome um resultado rico de resolução, sem fabricar URI oficial e sem reduzir erro de pacote a “nenhuma propriedade”. A injeção do provedor no builder será explícita, com testes dos seis métodos e dos dados realmente consumidos.

A projeção para DTO legado é potencialmente redutora. Retornar somente dados representáveis, com aviso estruturado no novo caminho; não concatenar unidades distintas nem transformar um conjunto tipado em equivalências inventadas. Caso o DTO antigo não comporte a advertência, recusar aquela projeção para enriquecimento e exigir o contrato rico.

Não alterar silenciosamente o comportamento usado em `v7.8`. Os adaptadores serão testados isoladamente e a integração operacional será identificada como nova condição quando mudar contexto, fonte, comparação ou decisão. Preservar os três pinos de `PROMPT_VERSION` e a reprodução histórica.

### 2.2 Cuidados específicos com resolução e aliases

O resolver atual pode construir URI IFC a partir de um nome sintaticamente aceito. Isso não comprova que uma propriedade exista naquele dicionário/schema. `resolve_pset` aceita padrões `Pset_`/`Qto_`, insuficientes para representar `EB_Orçamento`. A origem classificada por prefixo de URL não é aprovação por especialista nem licença de reutilização.

A busca flexível atual inclui associações como `fck`/`fcd` e `Rw`/`DnTw`. Este plano não as valida como sinônimos: qualificações de resistência e índices acústicos podem ter significados diferentes. Registrar qualquer revisão como trabalho conjunto com a frente 2; não transportar a tabela legada inteira para aliases aprovados.

Uma propriedade encontrada em outro Pset pode ser evidência para proposta de correção. Isso não torna satisfeita uma exigência de caminho exato do IDS. O resultado deverá manter ambos: caminho exigido e caminho observado.

### 2.3 Estrutura nova proposta

Todos os caminhos nesta tabela são **a criar em implementação futura**; não são links para arquivos já existentes.

| Área | Caminhos propostos | Responsabilidade |
|---|---|---|
| Modelo e contratos | `src/domain_catalog/models.py`, `contracts.py`, `errors.py` | Entidades, invariantes e resultados tipados |
| Leitura e busca | `reader.py`, `resolver.py`, `applicability.py` | Pacote fixado, candidatos, resolução e aplicabilidade de catálogo |
| Curadoria | `curation.py`, `draft_store.py`, `audit.py` | Solicitações, revisões, controle de concorrência e decisões |
| Publicação | `package.py`, `publication.py`, `migration.py` | Validação, hashes, importação, diff, fixação e rollback |
| Integração | `adapters.py`, `operations.py` | Compatibilidade e registro declarativo de operações suportadas |
| Fontes | `importers/daiane.py`, `importers/bsdd.py` | Importação por fonte, sem busca pública em runtime |
| Dados versionáveis | `data/catalogs/schemas/`, `data/catalogs/fixtures/` | Schema e pequenas fixtures sintéticas/reutilizáveis permitidas |
| Estado operacional | diretório interno configurado pela frente 6 | Rascunhos, pacotes, fontes autorizadas e auditoria; localização institucional ainda a definir |
| Testes | `tests/domain_catalog/` | Unidade, contratos, integração, publicação, regressão e isolamento |
| Documentação de domínio | `docs/catalogo/` | Dicionário, matriz de cobertura, decisões de reconciliação e operação |

O diretório operacional não deve ser inferido como `data/cache` nem entrar no Git por conveniência. O local final, retenção e permissões dependem da frente 6; testes usam diretórios temporários próprios.

<a id="m1-modelo"></a>

## 3. Modelo de dados proposto

### 3.1 Separação dos objetos e das identidades

| Entidade | Campos mínimos | Invariantes |
|---|---|---|
| `CatalogIdentity` | ID lógico, namespace, nome, mantenedor, idioma, descrição | Namespace local explicitamente provisório; não se apresentar como dicionário oficial |
| `CatalogRelease` | ID lógico, versão, versão do formato, hash do manifesto, data UTC, autor de publicação, release anterior | Conteúdo publicado imutável; versão reutilizada com bytes distintos é rejeitada |
| `SourceArtifact` | ID, título, autor, edição/data, tipo, localização, hash quando arquivo adquirido, licença/estado de permissão | URL identifica origem, hash identifica arquivo adquirido; não inventar hash de documento não armazenado |
| `SourceAssertion` | ID, fonte, página/quadro/linha ou caminho XML, conteúdo transcrito, tipo original, contexto | Registro da fonte não é sobrescrito pela reconciliação; correção cria nova revisão e vínculo |
| `ConceptDefinition` | ID estável, código local, rótulos por idioma, definição, qualificadores, tipo lógico, dimensão, referências | Mesmo nome não implica mesmo conceito; tipo e dimensão compatíveis |
| `AllowedValueSet` | ID, tipo, códigos estáveis, rótulos, fonte, ordem opcional, escopo | Código é distinto de rótulo; sem conversão silenciosa entre string, número e booleano |
| `UnitDefinition` | ID, símbolo, dimensão, referência, conversão aprovada quando houver | Unidade ausente não é adimensional; conversão exige grandeza compatível |
| `IFCBinding` | ID, conceito, schema/release, entidade, faceta, portador, nome/caminho, escopo ocorrência/tipo | Nome exato e caixa/acentos preservados; schema precisa ser explicitamente suportado |
| `ApplicabilityRule` | ID, predicado declarativo, classes/predefined types, condições e referências | Usar operadores permitidos; condição desconhecida resulta indeterminada, não falsa |
| `EvidencePolicy` | ID, fontes admissíveis, operação, pré-condições, precedência, conflito, abstenção | Expectativa do IDS não é evidência de valor; operação não pode executar código cadastrado |
| `AliasMapping` | termo, idioma, namespace, escopo, conceito/binding candidato, tipo da relação, aprovação | Colisão/ambiguidade explícita; alias não torna todas as fontes semanticamente equivalentes |
| `ProfileMembership` | perfil, conceito/binding, aplicabilidade, source assertions, status de cobertura | Associação ao perfil não cria requisito obrigatório no IDS |
| `ReconciliationDecision` | divergência, assertivas de origem, proposta, justificativa, evidência, ator, revisão | Original e reconciliado recuperáveis; decisão pendente não vira dado aprovado |
| `ChangeRequest` | requerente, motivação, origem IFC/IDS, patch proposto, base revision, estado | Pedido não modifica release; guardar apenas dados necessários e autorizados |
| `CurationEvent` | ID, UTC, ator/papel, ação, IDs/versões, estado antes/depois, motivo | Registro durável, ordenação/revisão verificável; logs técnicos separados |
| `ProjectCatalogPin` | projeto, catalog ID, versão, hash, revisão do pin, autor/motivo | Resolver por identidade exata; nunca “latest” durante uma análise |
| `AnalysisIdentity` | análise, hashes/revisões IFC e IDS, pin do catálogo, capacidades/condição | Mudança em qualquer entrada cria nova análise, preservando a anterior |

O catálogo descreve conceitos reutilizáveis. Valores de elementos ficam em `EvidenceObservation`, produzidos pela frente 2/3 e ligados a uma análise, não em uma coluna “valor atual” do conceito global.

**Proposta de ID:** UUID estável representado por URN para entidades locais; namespace do mantenedor separado, código legível separado e versão do pacote separada do ID lógico. IDs de exemplos não são URIs oficiais. Vínculos externos guardam URI exata, versão e tipo de relação. Renomear rótulo não troca ID; alterar o significado exige novo conceito ou mudança incompatível explicitamente revisada.

Uma ocorrência da fonte terá identidade própria, mesmo quando várias ocorrências se reconciliem em um conceito. Assim, deduplicar um conceito não apaga a cobertura das dez especificações.

### 3.2 Tipos, dimensões, unidades e restrições

Usar tipos lógicos explícitos: booleano, inteiro, decimal, string, código enumerado, data/hora e referência. Tipo lógico não substitui tipo IFC: guardar separadamente, por exemplo, string/`IfcLabel`, decimal/`IfcLengthMeasure`, e a estrutura necessária ao portador IFC. Precisão, escala e tolerância só entram quando justificadas; nenhuma tolerância universal será presumida.

Representar dimensão física separada da unidade. Comprimento, área, volume, massa, tensão e grandezas adimensionais são distintas. Não converter espessura em área por coincidência textual. Conversões de unidades devem usar operações aprovadas, rastrear valor/unidade originais e tratar offset quando aplicável. Unidade do projeto, unidade explícita na propriedade e unidade esperada no requisito precisam ser distinguíveis.

Enumerações armazenam código, rótulo, tipo e fonte. Um conjunto global pode ser restringido em um binding/perfil; não estender o conjunto global por uma restrição local. `Usos_Forma` é descrito na fonte como texto/`IfcLabel` com valores numericamente escritos: manter a representação original e só adotar inteiro mediante reconciliação explícita e análise da escrita IFC/IDS.

Ausência, nulo, string vazia, zero, falso, valor não suportado e valor conflitante têm estados distintos. Valores iniciais como `0`, `FALSE` ou “A definir” de ferramentas de estruturação não comprovam informação válida. Uma restrição de valor esperado — por exemplo, classe de resistência indicada para um perfil — não autoriza preenchê-la como fato do elemento.

### 3.3 Bindings e aplicabilidade

`IFCBinding` deverá representar:

- atributo IFC, com caminho e contexto de entidade/tipo;
- propriedade em conjunto, com nome exato do conjunto e da propriedade;
- quantidade em conjunto de quantidades, com tipo e método quando disponível;
- material e seus caminhos/associações;
- classificação, sistema/edição/código e papel;
- referência documental, quando o suporte correspondente existir.

`Pset_` e `Qto_` não são sinônimos; `EB_Orçamento` é um conjunto personalizado. `Area_Forma` aparece na fonte associada a `IfcQuantityArea` dentro desse conjunto: registrar a assertiva fiel e decidir explicitamente o portador reconciliado. Não produzir uma estrutura IFC incoerente para imitar a tabela.

Aplicabilidade do catálogo orienta uso/receita; aplicabilidade do IDS continua controlada pelo arquivo fornecido e pelo validador. Comparar ambas e expor divergência, sem reescrever o IDS. Regras podem considerar classe, predefined type, schema, material, sistema construtivo e condições aprovadas. Se faltar evidência para distinguir alvenaria e drywall, o estado é indeterminado; nome ou aparência não bastam.

Uma regra precisa informar o tratamento de subclasses, classe de tipo e herança. Suporte em IFC4 não comprova disponibilidade em IFC2X3 ou IFC4.3. Cada binding declara a matriz efetivamente verificada, incluindo restrições de cardinalidade ou portador relevantes.

### 3.4 Evidência e receitas de enriquecimento

Separar o que é admissível do que foi encontrado. A política cadastral refere operações; a observação contém valor, unidade, origem IFC, elemento, ocorrência/tipo, método, precisão quando conhecida, instante e identidade da análise.

| Operação proposta | Insumos / saída | Condições e limites |
|---|---|---|
| Leitura exata | Binding aprovado → valor tipado e caminho observado | Registrar fonte ocorrência/tipo; ausência não vira default |
| Recuperação por mapeamento | Alias/mapeamento aprovado + escopo → candidato de evidência | Não satisfaz automaticamente caminho exato IDS; conflito exige revisão |
| Padronização | Valor original + tabela/conversão aprovada → proposta normalizada | Preservar original e transformação; códigos sem regra permanecem pendentes |
| Cálculo | Entradas verificadas + operação implementada/versionada → valor/método | Unidades e pré-condições conferidas; geometria aproximada é identificada |
| Interpretação contextual | Evidências autorizadas + regra/contexto → proposta e justificativa | Frente 3 define limites; não promover associação estatística a fato |
| Solicitação humana | Campo sem evidência suficiente → pendência orientada | Indicar exatamente o dado necessário |
| Abstenção | Conflito, falta de suporte ou evidência → motivo estruturado | Nunca preencher com valor esperado só para passar |

Nenhuma fórmula Python, SQL, expressão arbitrária ou caminho de executável enviado em cadastro será executado. O registro de operações conterá ID/versionamento, insumos, tipos, schemas, precondições, implementação referenciada e testes. Cadastro novo com operação desconhecida fica `unsupported_operation` e não produz proposta de valor.

### 3.5 Exemplo JSON ilustrativo

O exemplo é **sintético, parcial e não publicável**. Os UUIDs são ilustrativos; o texto não afirma uma equivalência oficial nem fornece um pacote pronto. A tarefa M1-03 transformará este desenho em schema validado; o pacote real exigirá fontes e aprovação completas.

```json
{
  "format_version": "1",
  "catalog_id": "urn:uuid:159d0293-1096-4b5c-b0ae-f5bf766f7a43",
  "namespace": "ifc-quality-copilot.local.provisional",
  "release": {"version": "0.1.0", "state": "draft", "manifest_sha256": null},
  "concept": {
    "id": "urn:uuid:5d4c0c8f-92a4-4a92-95a4-38497e33c9dc",
    "code": "DEMO_FORMWORK_AREA",
    "labels": {"pt-BR": "Área de forma — exemplo"},
    "definition": "Área de contato com forma segundo método explicitamente definido.",
    "logical_type": "decimal",
    "dimension": "area",
    "unit_code": "m2",
    "source_assertion_ids": [],
    "lifecycle": "draft"
  },
  "binding": {
    "id": "urn:uuid:40a5a201-d6b6-4ef6-b134-b83038247e20",
    "concept_id": "urn:uuid:5d4c0c8f-92a4-4a92-95a4-38497e33c9dc",
    "ifc_schema": "IFC4",
    "entity": "IfcColumn",
    "facet": "property",
    "set_name": "EB_Orçamento",
    "field_name": "Area_Forma",
    "scope": "occurrence",
    "carrier_status": "pending_reconciliation",
    "source_original_type": "IfcQuantityArea",
    "write_enabled": false
  },
  "evidence_policy": {
    "operation_id": "formwork_area_from_geometry",
    "operation_version": null,
    "capability": "unsupported",
    "on_missing_or_conflict": "abstain"
  }
}
```

Esse exemplo demonstra por que cadastro, compatibilidade de portador e implementação de operação são eixos separados. Um leitor pode mostrar a pendência, mas o publicador deve impedir que esse binding seja ativado para escrita/enriquecimento enquanto faltarem reconciliação, fontes e capacidade.

<a id="m1-curadoria"></a>

## 4. Curadoria, deduplicação e publicação

### 4.1 Fluxo de trabalho proposto

1. **Solicitação:** operador descreve finalidade, origem e campo; serviço registra ator, UTC e vínculo à análise/requisito, sem copiar IFC inteiro para o catálogo.
2. **Triagem:** localizar conceito/binding existente por ID, URI verificada, código e busca textual. Mostrar candidatos e escopo; não selecionar automaticamente por maior score.
3. **Rascunho:** adicionar ou duplicar linha; duplicação gera ID de rascunho e obriga revisar ID de conceito, fonte, aplicabilidade e operações. Campos derivados não são livremente editáveis.
4. **Validação automática:** schema, referências, unidade/dimensão, enumeração, ciclos, aliases, suporte de operação, compatibilidade declarada e completude de fonte.
5. **Revisão de domínio:** comparar original e proposta lado a lado; explicar equivalência, diferenças, impacto e lacunas. LLM pode fornecer uma proposta identificada, nunca o ato de aprovação.
6. **Aprovação:** curador aprova uma revisão exata e um conjunto de mudanças; qualquer edição posterior invalida a aprovação desse conteúdo.
7. **Pré-publicação:** construir candidato isolado, executar verificações, calcular diff e verificar que todas as referências ativas são publicáveis.
8. **Publicação:** somente autoridade de curador confirmada pelo serviço; gravação durável e recibo identificam pacote/hash/ator. UI não é a única barreira.
9. **Adoção:** projeto permanece no pin anterior até atualização explícita; adotar versão cria nova identidade de análise.
10. **Correção posterior:** versão publicada não é editada. Emitir nova versão, deprecação ou aviso de problema, preservando histórico e trilha.

O operador pode acumular o papel de curador se a governança o autorizar; exigir duas pessoas distintas é decisão institucional ainda aberta, não requisito já confirmado. Implementar os papéis e a autorização de publicação é obrigatório; a atribuição nominal depende da frente 6.

### 4.2 Estados distintos

| Eixo | Estados propostos | Uso |
|---|---|---|
| Solicitação | aberta, em triagem, em revisão, aprovada, rejeitada, cancelada | Acompanhamento de demanda |
| Registro cadastral | rascunho, revisado, aprovado, depreciado | Prontidão de conteúdo |
| Pacote | candidato, publicado, substituído, com aviso/quarentena | Disponibilidade/versionamento; detalhes de quarentena a revisar |
| Resolução | exata, mapeamento aprovado, ambígua, não mapeada, não suportada, erro de pacote | Resultado semântico, independente da conformidade |
| Evidência | suficiente, ausente, conflitante, insuficiente, indisponível | Base de uma proposta |
| Validação IDS | conforme, não conforme, não aplicável, não verificado, erro | Vocabulário confirmado no módulo 2 |

Não reduzir essas máquinas de estado a um campo `status` genérico. Uma propriedade pode estar cadastrada e sem evidência; um requisito não mapeado pode ser conforme pelo IDS; um pacote válido não garante conformidade do IFC.

### 4.3 Deduplicação e aliases

A chave de comparação semântica inclui definição, grandeza, qualificadores e método quando parte do significado. Classe, portador e schema pertencem ao uso/binding. Reutilizar um conceito em várias classes é preferível quando significado coincide; não fundir resistência característica e resistência de cálculo ou área bruta e líquida.

Aliases têm finalidade explícita: busca textual, tradução de rótulo, grafia histórica, correspondência de representação ou equivalência aprovada. Busca textual pode ignorar acentos para localizar candidatos, mas nunca modifica os nomes de gravação. Um alias global que capture campos incompatíveis deve ser recusado ou restringido a namespace/Pset/classe/schema.

Deduplicação cria vínculo entre registros de origem e conceito canônico local, mantendo IDs históricos como referências/deprecações quando necessário. Não apagar uma origem para fazer a contagem “fechar”. Se houver dúvida, publicar apenas a parte resolvida e manter a divergência visível no relatório de cobertura.

### 4.4 Original versus reconciliado

Manter três camadas: artefato de fonte, assertivas fielmente extraídas e modelo reconciliado aprovado. Toda transformação deve apontar para as assertivas envolvidas, justificativa, evidência, responsável e revisão. Transcrição corrigida e interpretação corrigida são eventos diferentes.

Um erro de grafia pode originar alias de busca depois da revisão; isso não autoriza corrigir o XML IDS do operador. Divergências entre apêndices A/B ou entre 2025/2026 exigem decisão por contexto, nunca uma tabela global de substituição silenciosa.


<a id="m1-daiane"></a>

## 5. Cobertura Daiane e reconciliação das fontes

### 5.1 Fontes e o que foi efetivamente verificado

A dissertação de **Daiane Castro Dias**, *Gestão da informação em modelos BIM para orçamentação de obras públicas com uso do Information Delivery Specification*, IME, 2025, foi consultada pelo texto extraído do PDF via conector. A referência usa **paginação impressa**, não índice de imagem do leitor. O PDF não foi incorporado ao repositório nesta etapa.

O texto descreve a planilha de requisitos e sua organização nas pp. 86–94; a elaboração/auditoria do IDS nas pp. 95–98; e o fluxo de estruturação de informações com IDScribe nas pp. 99–105. Os quadros A.1–A.10 estão nas pp. 161–170, e o relatório do Apêndice B nas pp. 171–185. [Dissertação de Daiane, PDF no Drive](https://drive.google.com/file/d/1TNRFxlXW9osGvrkNavm9t2A-qbQpbNcu/view).

A fonte relata a elaboração com usBIM.IDSeditor 2.3.8.0 e auditoria com IDS Audit Tool 1.0.84; o caso de `PartitioningType` exigiu verificação/ajuste após a exportação. Isso fundamenta a conferência dos arquivos, não a reprodução automática de correções. O IDScribe descrito lê IDS e estrutura informações no IFC; não confundir criação de campos/valores provisórios com autoria ou aprovação de requisitos. Esses números são da experiência relatada na dissertação, não versões aprovadas para este projeto. [Dissertação, pp. 95–105](https://drive.google.com/file/d/1TNRFxlXW9osGvrkNavm9t2A-qbQpbNcu/view).

O relatório B é identificado como **IDS_Mestrado**, versão 1, data **22/08/2025**, com dez especificações. O relatório não substitui o XML original. A planilha editável e o XML original dessas dez especificações continuam pendentes. Buscar com Juliana é encaminhamento confirmado; nenhum contato foi realizado nesta tarefa. A demanda foi relatada na tarefa Todoist `6hj2RxM24fr9fqw9`, sem prazo confirmado.

O pacote público de 2026 é outra fonte. O registro Zenodo foi consultado e lista `IDS_Cost.ids`, relatório, modelo arquitetônico, README e add-on. A análise XML recebida no handoff anterior relata seis especificações arquitetônicas, IFC4, 133 requisitos, `Cost_Prop` e data XML 08/01/2026. **Esses números não foram recontados nesta tarefa**; o acesso web direto ao XML/relatório não permitiu uma nova inspeção. Portanto, registrar a procedência do levantamento antes de usá-lo como fixture. [Registro Zenodo 19150057](https://zenodo.org/records/19150057).

Não substituir a base de 2025 pela de 2026, nem renomear `EB_Orçamento` para `Cost_Prop`. A licença CC-BY-4.0 do registro foi relatada na pesquisa anterior; o README consultado menciona uso acadêmico/de pesquisa. Verificar alcance por arquivo antes de redistribuir dados/código, sem inferir uma licença única para todos os componentes. Isso não impede modelar o catálogo ou registrar referências. [README do pacote IDScribe](https://zenodo.org/records/19150057/files/README_IDSCRIBE.txt?download=1).

### 5.2 Matriz mínima de cobertura

O piso é a união rastreável de A.1–A.10 e B. Contar requisitos por especificação e conceitos únicos separadamente. Não contar cópias de arquivo ou repetição de conceito como ampliação de domínio.

**Baseline recebido, ainda sujeito a reconferência:** 195 entradas semânticas, excluindo facetas de classe, sendo 137 propriedades/Qto, 29 atributos, 19 classificações e 10 materiais; 88 caminhos Pset/Qto propostos; 34 pontos de reconciliação. São números do levantamento anterior, não uma certificação produzida agora.

| Quadro / página impressa | Família e recorte da fonte | Entradas relatadas | Cobertura exigida na implementação |
|---|---|---:|---|
| A.1 / 161 | `IfcWindow` | 23 | Atributos, Psets/Qto, materiais, classificação e informações contextuais; conferir posição/tipo e dimensões |
| A.2 / 162 | `IfcDoor` | 29 | Mesmas categorias pertinentes; qualificar densidade, dimensões, operação e requisitos do conjunto personalizado |
| A.3 / 163 | `IfcWall` | 25 | Diferenciar sistemas construtivos e condições de aplicabilidade; não transferir exigência de alvenaria para drywall sem critério |
| A.4 / 164 | `IfcCovering` / `CEILING` | 21 | Binding por predefined type e suporte de schema; quantidades, material e contexto |
| A.5 / 165 | `IfcCovering` / `FLOORING` | 18 | Separar piso/revestimento de laje estrutural; manter método e unidade das quantidades |
| A.6 / 166 | `IfcCovering` / `CLADDING` | 23 | Diferenciar contexto de revestimento; conferir Pset de status e condições por sistema |
| A.7 / 167 | `IfcSlab` / `FLOOR` | 17 | Concreto, forma, Qto e `EB_Orçamento`; método da área de forma e representação de usos |
| A.8 / 168 | `IfcColumn` | 15 | Estrutura/concreto/forma, Qto e condições do perfil; valor esperado não é evidência do objeto |
| A.9 / 169 | `IfcBeam` | 16 | Estrutura/concreto/forma e Qto; preservar condições específicas e diferenças em relação a pilares |
| A.10 / 170 | `IfcReinforcingBar` | 8 | Material, dimensões/massa e condições da armadura; reconciliar nomes e diferenças A/B |
| B / 171–185 | E01–E10 de `IDS_Mestrado` | Não somar como novo corpus | Mapear cada faceta/restrição do relatório ao quadro e às assertivas; registrar entradas somente em A, somente em B e divergentes |

Fonte da matriz de famílias/páginas: [Dissertação, Apêndices A e B](https://drive.google.com/file/d/1TNRFxlXW9osGvrkNavm9t2A-qbQpbNcu/view). A soma das dez contagens relatadas é 195; a reconferência deve preservar o denominador original e explicar qualquer alteração, sem ajustar linhas artificialmente para reproduzir a soma.

As exigências geométricas e documentais dos quadros também entram no inventário de cobertura. Quando não forem representáveis por faceta/operação suportada, registrar `documental`, `geométrica` ou `não operacionalizada`, com motivo. A contagem de 195 não autoriza apagá-las nem prometer que todas são verificáveis por IDS.

### 5.3 Registro de cobertura por entrada

Propor uma linha por assertiva de fonte, com os campos:

`source_entry_id`, fonte/hash quando disponível, página/quadro/linha, especificação B, faceta, classe/predefined type, conjunto, campo, tipo original, unidade original, valores/restrições, aplicabilidade original, conceito local, binding, decisão de reconciliação, operação/capacidade, testes e estado de publicação.

IDs de origem podem usar `DAI2025-A07-RNNN` para posição estável na transcrição e `DAI2025-B-E07-RNNN` para o relatório. A numeração será gerada após a conferência; ela não inventa linhas ainda não transcritas. Guardar também localização textual para sobreviver a uma correção da ordenação.

**Estados de cobertura propostos:** fonte registrada; transcrição conferida; pendente de reconciliação; cadastro aprovado; validação suportada; enriquecimento suportado; sem suporte operacional; excluída justificadamente. Uma linha pode ter cadastro aprovado e enriquecimento indisponível. Métricas devem reportar os eixos separadamente.

**Aceite da cobertura:** todas as dez famílias e todas as categorias da fonte têm destino rastreável. Nenhuma pendência desaparece por deduplicação. A afirmação “piso integral operacionalizado” só será permitida após cobertura operacional/testada de todas as entradas dentro do escopo acordado; antes disso, publicar percentual e lista de pendências, não um rótulo de completude.

<a id="m1-duas-camadas"></a>

#### 5.3.1 Decisão confirmada — duas camadas e uma base canônica

**Confirmado por Felipe em voz em 10/10/2026:** representar o Apêndice A em duas camadas vinculadas: **tabela fiel à fonte**, uma linha por requisito, com classe, propriedade, Pset, tipo, unidade ou valores permitidos e página de origem, mantendo divergências sem normalização silenciosa; e **catálogo operacional separado**, que acrescenta significado, locais de evidência no IFC, operações autorizadas e encaminhamento BCF. Os campos de rastreabilidade da seção 5.3 continuam aplicáveis. O artefato original permanece como proveniência conforme a seção 4.4; as duas camadas de representação não eliminam sua preservação.

**CSV inicial para revisão humana e JSON para consumo pelo software devem derivar da mesma base canônica**, como projeções identificadas da mesma revisão, sem duas cópias mantidas independentemente. Ajustes da revisão retornam à base sob o fluxo de curadoria e geram novas exportações; não sobrescrevem silenciosamente a transcrição fiel. O formato físico dessa base continua a ser detalhado na implementação futura.

A [integração com as receitas de contexto do M3](modulo-03-contexto-enriquecimento.md#m3-interface-camadas) deve preservar o vínculo entre requisito, registro/página de fonte, versão do catálogo e versão da receita/operação. Esta confirmação especifica a representação e a rastreabilidade; não implementa transcrição, exportadores ou receitas nem aprova o M3. Registro recebido das falas `01a12801-05a6-77ad-aa68-e67be837b822` e `01a12801-c0a1-773c-a486-8e4a2722f9c1`.

### 5.4 Tratamento dos 34 pontos relatados

O levantamento recebido informa **34 divergências**, mas o inventário individual completo não está disponível neste handoff. Não criar 34 descrições fictícias nem afirmar que todas foram confirmadas. Abrir uma tarefa de recuperação/reconferência do inventário; registrar `reported_count = 34`, fonte do relato e `verified_count` derivado das entradas efetivamente conferidas.

O ledger proposto terá ID, fontes comparadas, transcrições curtas pertinentes, categoria, impacto, candidatos de resolução, evidência adicional, estado, responsável, decisão e casos de teste. `DAI-DIV-NNN` será atribuído a um achado real. Se a reconferência encontrar quantidade diferente, publicar tabela de correspondência com o levantamento anterior e explicação do denominador.

Exemplos para triagem, **não lista completa das 34**:

| Tema conhecido | Estado da evidência nesta etapa | Tratamento planejado |
|---|---|---|
| `Weight` / `Weigth` | Variante de grafia localizada no texto da dissertação | Relacionar ocorrências exatas, confirmar caminho/schema e decidir alias de busca; não reescrever IDS do operador |
| `Height` / `Heigth` | Relatado no levantamento anterior; localização ainda a reconferir | Conferir fonte/página/faceta antes de aprovar correção |
| Pset de status em revestimento referindo conjunto de porta | Relatado anteriormente; decisão cadastral pendente | Comparar A/B, classe e schema; manter a assertiva original e registrar binding reconciliado aprovado |
| `Densidade_Porta` | Sentido, grandeza/unidade/tipo precisam ser reconciliados | Não presumir densidade física apenas pelo nome; exigir definição e fonte |
| `Usos_Forma` | Texto/`IfcLabel` e valores escritos como números observados em A.7/A.8 | Preservar código textual; qualquer mudança de tipo requer revisão de consumidores |
| `Area_Forma` | Indicação de `IfcQuantityArea` associada a `EB_Orçamento` observada | Resolver portador e método; nenhuma escrita habilitada enquanto inconsistente |
| Armaduras em A/B | Diferenças relatadas no levantamento anterior | Conferir cada faceta e restrição, sem escolher apêndice por conveniência |
| Alvenaria/drywall | Aplicabilidade requer qualificação por sistema | Separar regras e evidências; abster-se quando sistema não puder ser identificado |

Fonte para exemplos observados: [Dissertação, Apêndices A/B](https://drive.google.com/file/d/1TNRFxlXW9osGvrkNavm9t2A-qbQpbNcu/view). Os exemplos relatados como pendentes conservam esse estado até a conferência. Recuperar XML/planilha pode resolver a transcrição, mas não substitui julgamento sobre significado e validade IFC.

<a id="m1-interfaces"></a>

## 6. Contratos e dependências entre frentes

### 6.1 Interfaces de leitura propostas

Contratos abaixo são desenho para implementação, não APIs existentes. Usar DTOs tipados e versionados; nomes podem ser ajustados na revisão sem mudar os invariantes.

```python
open_catalog(ref: CatalogReleaseRef) -> CatalogReader
CatalogReader.describe() -> CatalogManifest
CatalogReader.search(query: CatalogQuery) -> CandidatePage
CatalogReader.get_concept(concept_id: str) -> ConceptDefinition
CatalogReader.resolve_binding(request: BindingRequest) -> ResolutionResult
CatalogReader.list_bindings(query: BindingQuery) -> BindingPage
CatalogReader.get_evidence_policy(policy_id: str) -> EvidencePolicy
CatalogReader.get_capability(operation_id: str) -> OperationCapability
```

`CatalogReleaseRef` inclui ID, versão e hash esperado. O reader é somente leitura e permanece fixado durante a análise. Abrir falha por pacote ausente, inválido ou versão de formato incompatível; falha não é uma busca sem resultados.

`BindingRequest` inclui schema, faceta, classe/predefined type quando conhecidos, caminho requerido/observado, escopo ocorrência/tipo e identidade do requisito. Campos desconhecidos permanecem desconhecidos. `ResolutionResult` retorna status, candidatos, correspondência aprovada quando única, motivos, fonte/versão, limitações e IDs das decisões. Ordenação estável de candidatos não implica escolha.

`CatalogQuery` deve suportar paginação, busca textual, classe, faceta, perfil, fonte e estado; rascunhos só aparecem a quem tem acesso de curadoria. Uma busca de uso operacional usa release publicado, sem mistura com edição aberta.

### 6.2 Interfaces de curadoria e versão propostas

```python
request_change(request: ChangeRequestInput, actor: Actor) -> ChangeRequest
edit_draft(draft_id: str, base_revision: int, patch: DraftPatch, actor: Actor) -> Draft
validate_draft(draft_id: str, revision: int) -> ValidationReport
review_draft(draft_id: str, revision: int, decision: ReviewInput, actor: Actor) -> Review
prepare_release(draft_ids: list[str], actor: Actor) -> ReleaseCandidate
publish(candidate_id: str, candidate_hash: str, actor: Actor) -> PublicationReceipt
diff_catalogs(before: CatalogReleaseRef, after: CatalogReleaseRef) -> CatalogDiff
plan_project_update(project_id: str, target: CatalogReleaseRef) -> UpdateImpact
apply_project_update(plan_id: str, expected_pin_revision: int, actor: Actor) -> ProjectCatalogPin
```

Toda mutação é transacional e usa revisão esperada para impedir sobrescrita concorrente. Publicação recebe hash do candidato aprovado e chave idempotente no envelope de comando; repetir a mesma operação não gera duas versões. Mudança em dados após revisão exige novo candidato. Importação de fonte somente cria staging/rascunhos; não chama publicação automaticamente.

### 6.3 Contrato com a frente 2 — leitura e validação IFC/IDS

**Confirmado por Felipe às 14:06:** módulo 2 será somente leitura/verificação, sem criar propriedades nem alterar valores IFC. Propostas de enriquecimento e escrita após revisão humana pertencem a etapas posteriores. Às 14:15 foi confirmada análise individual na primeira entrega. Carregar/exibir vários IFCs como conjunto federado é extra posterior do módulo 2, integrado visualmente à frente 4; manter arquivos originais e saídas IFC separados. Não estabelecer um IFC por projeto como restrição definitiva.

A identidade deve admitir projeto com vários modelos e distinguir arquivo/revisão/elemento, pois GlobalId isolado pode colidir entre arquivos. O extra federado precisará tratar alinhamento espacial, proveniência das observações/decisões e encaminhamento de cada saída ao arquivo correto. Não fundir os arquivos. A cardinalidade/associação de IDSs nesse extra e o projeto detalhado do viewer continuam abertos; nenhum viewer é implementado neste plano.

Às 14:17 Felipe confirmou IFC4.3 como meta ao lado de IFC2X3/IFC4. A matriz deve testar leitura, validação, visualização e escrita separadamente, com caso de arquitetura/estrutura e fixtures IFC4.3. Fixar release exato pelos ensaios; documentação de uma biblioteca não prova suporte da instalação atual. O domínio não se expande para infraestrutura por adotar esse schema.

| Meta de schema confirmada | Leitura IFC | Validação IDS | Visualização | Escrita posterior |
|---|---|---|---|---|
| IFC2X3 | Conferir caso/fixtures e capacidades | Ensaiar facetas e limitações | Ensaiar separadamente na frente 4 | Ensaiar por operação na frente 5 |
| IFC4 | Conferir caso/fixtures e capacidades | Ensaiar facetas e limitações | Ensaiar separadamente na frente 4 | Ensaiar por operação na frente 5 |
| IFC4.3 | Obter caso arquitetura/estrutura e fixtures | Fixar release e ensaiar capacidades | Não presumir suporte a partir do parser | Não presumir suporte a partir da leitura |

Esta é uma matriz de trabalho, sem células de suporte certificado nesta tarefa.
A release IDS 1.0 registra a enumeração `IFC4X3_ADD2`; isso orienta a identificação
do schema e não substitui testes da instalação e de cada capacidade.
[Releases oficiais do IDS](https://github.com/buildingSMART/IDS/releases).

**Confirmado às 14:18:** validar e exportar diagnóstico deve funcionar sem
enriquecimento/LLM. Manter resultado completo rastreável na plataforma e relatório
exportável; a frente 5 usa o mesmo diagnóstico para BCF. Formatos, limites e
timing serão definidos por ensaios, sem fechar escolhas arbitrárias neste plano.
A falha/ausência do catálogo ou LLM não deve impedir um diagnóstico IDS que seja
independentemente suportado, respeitados os bloqueios de arquivo já confirmados.

Entradas para o catálogo: schema, entidade/tipo, faceta/caminho, identificação do requisito, versões e observações necessárias. Saídas: significado, candidatos, mapeamento, aplicabilidade do catálogo, unidade esperada do conceito e fonte. **O IDS fornecido continua sendo a autoridade do requisito formal.**

O módulo 2 devolve resultados com `analysis_id`, identificação do elemento e requisito, esperado, encontrado, origem, status, motivo e limitações. Os cinco estados confirmados não são intercambiáveis:

| Estado confirmado | Uso contratual a detalhar/testar na frente 2 |
|---|---|
| Conforme | Requisito suportado foi avaliado e satisfeito segundo o IDS |
| Não conforme | Requisito suportado foi avaliado e violado |
| Não aplicável | Aplicabilidade/exigência não exige aquela avaliação, com razão rastreável |
| Não verificado | Avaliação não realizada ou recurso não suportado; jamais aprovado |
| Erro | Falha técnica impede resultado confiável para o escopo afetado |

A ausência de elementos aplicáveis deve constar expressamente e ser interpretada pela cardinalidade/exigência do IDS. Não atribuir conforme pelo simples fato de a lista de resultados estar vazia. O caso pode envolver a especificação como um todo, portanto a visão por requisito não deve desaparecer quando não há elemento.

Separar categoria de problema técnico, falha IDS e alerta complementar conforme D12. Um alerta de catálogo não cria não conformidade IDS; um erro de pacote não altera silenciosamente o conteúdo do requisito. Quando possível, a validação independente continua com limitação de enriquecimento registrada; arquivos sem interpretação confiável bloqueiam o escopo afetado.

### 6.4 Contrato com a frente 3 — contexto e enriquecimento

Responsável principal: Nonato. Receber pacote fixado, binding resolvido, política de evidência, capacidades e observações vinculadas à análise. Retornar proposta ou abstenção com método/receita/versionamento, valores tipados, fontes e conflitos. Um valor permitido do IDS ou um exemplo da fonte não constitui observação do IFC.

Incluir no cache da nova condição: identidade IFC/IDS/catálogo, binding, política/receita, versão da operação, versão de contexto/condição, modelo e parâmetros quando houver LLM. Uma chave apenas por texto da issue pode reutilizar resultado indevido após migração.

O módulo 1 não implementa todas as operações do módulo 3. Ele fornece contratos e catálogo de capacidades. Até implementação/teste de uma operação, a UI mostra sua indisponibilidade; não há fallback para inferência livre.

### 6.5 Contrato com a frente 4 — curadoria e revisão

Nonato tem participação parcial; liderança restante e recorte ainda abertos. A tela usa serviços de consulta/curadoria, não escreve diretamente no JSON publicado ou no banco. A tabela deve permitir filtrar fonte, classe, perfil e estado, adicionar/duplicar linha, abrir detalhes e mostrar validações por campo.

Detalhes essenciais: original e reconciliado, conceito versus binding, unidade/tipo, aplicabilidade, aliases, operação/capacidade, histórico e impacto. Ações de publicar dependem de papel/revisão exata. Salvar rascunho não publica e não altera IFC/IDS. Erro de concorrência deve preservar o trabalho do usuário e exigir conciliação explícita.

Na análise, mostrar estado IDS, estado de mapeamento e estado de evidência separadamente. Navegação principal por elemento e alternativa por requisito, com esperado/encontrado/origem. Aprovação de cadastro não equivale à aprovação de valor para um elemento; a revisão por campo e o alcance em tipo pertencem ao fluxo de enriquecimento/escrita.

### 6.6 Contrato com a frente 6 — infraestrutura e governança

Responsável principal: Nonato. Definir diretório interno, autorização de papéis, backup/restauração, atomicidade suportada pelo ambiente e limites de volume. SQLite local é proposta adequada a processo único; um servidor multiusuário requer ensaio de concorrência e estratégia institucional, não simples compartilhamento de arquivo em rede.

Runtime do reader não usa HTTP público, DNS externo, CDN, telemetria ou download implícito. URLs de fonte são metadados. Uma operação de importação administrativa futura poderá usar um artefato previamente adquirido por canal autorizado; a consulta de catálogo em uma análise não inicia aquisição.

A frente 6 provê identidade autenticada ou contexto local de ator definido pela governança. Não confiar em papel enviado livremente pelo navegador. Retenção e acesso aos dados de projetos não são derivados da licença do catálogo.

### 6.7 Contrato com a frente 7 — avaliação científica

Felipe coordena; Nonato participa parcialmente. Registrar versão/hash do catálogo, cobertura por perfil, estado de mapeamento, fontes e decisões usadas, além de identidade de IFC/IDS, operações e condição experimental.

Medir separadamente: cobertura de transcrição, cobertura de cadastro aprovado, resolução exata/aprovada, ambiguidades, validação suportada, enriquecimento suportado, abstenção correta, propostas sem suporte e esforço de curadoria. Denominadores devem indicar se contam assertivas, conceitos, bindings, requisitos ou elementos.

Mudança de catálogo ou contexto pode alterar o instrumento mesmo sem mudar `PROMPT_VERSION v7.8`. Planejar nova condição/registro para a integração; não recalcular ou reinterpretar resultados históricos silenciosamente. Comparar apenas condições explicitamente documentadas e usar gabarito especializado independente. Casa/prédio são casos iniciais, não todo o corpus.

<a id="m1-pacotes"></a>

## 7. Pacotes locais, integridade, atualização e rollback

### 7.1 Formato de publicação proposto

Um release conterá manifesto, conceitos, bindings, aplicabilidade, unidades, enumerações, políticas de evidência, aliases, referências de fontes, decisões publicadas e relatório de cobertura/limitações. Rascunhos e dados pessoais desnecessários ficam fora. Fontes binárias só entram quando a distribuição for autorizada; uma referência verificável pode permanecer externa ao pacote.

O manifesto declara catalog ID, versão semântica interna, versão do formato, release anterior, UTC, mantenedor, perfis, schemas verificados, capacidades mínimas, licença/termos por componente e lista de arquivos com tamanho/hash. Versão do formato e versão de conteúdo têm funções diferentes.

**Hash proposto:** cada arquivo de dados tem SHA-256 de seus bytes; o manifesto canônico contém esses hashes e metadados. O hash de identidade do release é o SHA-256 dos bytes do manifesto, guardado no pin/recibo, fora do próprio manifesto. Evitar autorreferência de hash. Serialização canônica deve ser definida e testada: UTF-8, chaves ordenadas, separadores definidos, terminação LF e ausência de números não finitos/chaves duplicadas. Não normalizar nomes IFC/acentos para calcular identidade.

O hash detecta diferença de conteúdo; não prova autoria confiável. Aprovação/ator/recibo e canal interno de distribuição compõem a confiança. Assinatura criptográfica de pacotes é decisão futura da frente 6, sem promessa de implementação nesta entrega.

### 7.2 Publicação que falha com segurança

1. Validar rascunhos e aprovação exata; resolver todas as dependências ativas.
2. Gerar candidato em diretório de staging interno separado do release ativo.
3. Reabrir o candidato, validar schema/referências/hashes e rodar testes de pacote.
4. Persistir artefatos de forma durável e promover o diretório/publicação de maneira atômica compatível com o filesystem aprovado.
5. Persistir recibo e estado transacional; só então disponibilizar o release para novos pins.
6. Se houver interrupção, o pacote anterior continua íntegro. Staging incompleto não é release utilizável.
7. Na retomada, reconciliar staging/recibo por ID e hash, sem publicar automaticamente conteúdo não aprovado.

Validar referências de arquivos, tamanho, número de entradas e profundidade. Rejeitar caminhos absolutos, travessia de diretório, links que saiam do pacote, arquivos inesperados e formatos desconhecidos. Se for adotado ZIP de transporte, testar extração confinada e limites de descompressão antes de habilitá-lo; uma pasta de release é suficiente para a primeira fatia.

Pacote inválido, assinatura exigida ausente, hash divergente ou formato incompatível bloqueiam sua ativação. Não transformar falha em catálogo vazio nem consultar a API pública. A validação IDS que for independente pode continuar com limitação técnica explícita; isso não autoriza enriquecimento sem fonte confiável.

### 7.3 Diff e fixação por projeto

Comparar pelo ID estável e informar: adição, retirada/deprecação, alteração de definição/tipo/unidade/enumeração, binding/schema, aplicabilidade, alias, operação, fonte e decisão. Mudança somente de rótulo também fica rastreada, embora seu impacto seja diferente de uma mudança de significado.

O plano de atualização identifica requisitos/mapeamentos afetados, caches/propostas potencialmente inválidos e versões de operação necessárias. A atualização do pin exige confirmação explícita no fluxo do produto e revisão esperada do pin. Esta exigência é parte da funcionalidade futura confirmada por D08; não é pedido de permissão para editar este documento.

Mudança gera nova análise com entradas exatas e ligação à análise anterior. Aprovações antigas permanecem no histórico e não são automaticamente transportadas. O alcance do reprocessamento seletivo pode ser otimizado depois; a primeira implementação pode reprocessar integralmente o escopo suportado, sem prometer performance ainda não medida.

### 7.4 Rollback e migração para o dicionário de Juliana

Rollback seleciona um release anterior íntegro e gera novo evento/pin e nova análise. Não apagar a análise da atualização malsucedida nem modificar releases. Backup deve restaurar pacote, pin, eventos e referências consistentes; testar restauração antes de tratar backup como capacidade entregue.

Ao receber o dicionário de Juliana, importar em staging com identidade/versão/fonte preservadas; comparar conceitos e bindings com a base local; revisar relações equivalentes, próximas e incompatíveis; gerar tabela de mapeamento e relatório de perdas. URI externa é referência de origem, não autorização para substituir um conceito por similaridade nominal.

A documentação oficial bSDD distingue propriedades e suas associações a classes, incluindo uso de `PropertyCode` ou `PropertyUri`, metadados de versão e restrições de valores/unidades. O modelo local deve preservar esses dados de importação e validar diferenças de formato; não assumir que todo release local seja diretamente publicável no bSDD. [Modelo JSON de importação bSDD](https://github.com/buildingSMART/bSDD/blob/master/Documentation/bSDD%20JSON%20import%20model.md).

Códigos e nomes de apresentação têm funções distintas, e a representação IFC depende do contexto de classe/conjunto/schema. Esses pontos orientam o adaptador, sem conferir equivalência automática entre versões. [Documentação bSDD–IFC](https://github.com/buildingSMART/bSDD/blob/master/Documentation/bSDD-IFC%20documentation.md).

Enquanto um mapeamento estiver pendente, o projeto pode permanecer no release local anterior. A nova fonte não revoga retroativamente decisões históricas; correções e avisos devem ser rastreados. Política operacional para releases conhecidos como incorretos — aviso, restrição a novas análises ou quarentena — precisa de decisão explícita, mantendo acesso de auditoria ao conteúdo antigo.

<a id="m1-percursos"></a>

## 8. Percursos completos de uso

### 8.1 Propriedade reutilizável em outra classe

Um curador pretende usar um conceito de área de forma em pilares e vigas. Primeiro compara definição, método de medição, unidade e qualificadores. Se o significado coincidir, preserva o ID do conceito e cria outro binding/aplicabilidade. Se método ou significado diferirem, cria conceito distinto e relação explicativa.

Registra as assertivas A.8/A.9, reconcilia portador IFC e verifica operação disponível. A interface mostra que o conceito é compartilhado e os usos são diferentes. Publica após revisão e testes; projeto adota explicitamente. Nenhum elemento recebe valor apenas porque o conceito passou a ser aplicável.

### 8.2 Nova operação de cálculo

O operador solicita `Area_Forma` calculada da geometria, mas o registro de operações não contém um método validado. O catálogo admite rascunho/solicitação e marca enriquecimento indisponível. A validação de requisito suportado continua; a proposta não usa área de bounding box como substituição tácita.

Engenharia na frente 3 define método, entradas, unidades, limitações e testes geométricos; o curador revisa a relação entre método e significado. Depois de implementar/versionar a operação e validar exemplos de referência, um novo release habilita a receita. Adoção pelo projeto gera nova análise; aprovação humana precede qualquer escrita posterior.

### 8.3 IDS com propriedade desconhecida

Um IDS fornecido exige um caminho de propriedade não cadastrado. O módulo 2 lê e valida a faceta se suportada, sem alterar o IFC. O resultado mostra esperado/encontrado/origem e status IDS. O catálogo retorna não mapeada; a UI permite solicitação com referência ao requisito.

Se o campo existe e satisfaz o IDS, pode ser conforme mesmo sem cadastro semântico. Se falta, pode ser não conforme; o sistema não preenche usando outro campo de nome parecido. Se a faceta não é suportada, não verificado. Ausência de elementos segue cardinalidade/exigência do IDS e permanece visível por requisito.

### 8.4 Atualização/migração de pacote

Projeto P usa release local R1. R2 corrige um binding, deprecia um alias e acrescenta URI revisada de Juliana. O diff identifica todos esses impactos e as análises ligadas a R1 permanecem recuperáveis.

Após atualização explícita, criar análise A2 com as mesmas entradas IFC/IDS identificadas e R2. Reprocessar o escopo definido e comparar com A1; propostas/decisões não são copiadas por conveniência. Se R2 for recusado operacionalmente, selecionar R1 cria evento e análise posteriores; o histórico A1/A2 continua intacto.

### 8.5 Fonte divergente e pacote indisponível

A transcrição de um campo diverge entre A e B. O curador registra ambas, mantém binding pendente e publica apenas o conteúdo aprovado, com cobertura parcial explícita. O LLM pode ajudar a organizar candidatos, mas não aprova a divergência.

Se o pacote fixado não puder ser aberto depois de uma falha de disco, o reader informa erro de pacote. Não busca bSDD público e não assume um pacote mais recente. A aplicação decide, conforme contrato da frente 2, se a verificação IDS independente pode continuar; o enriquecimento dependente fica indisponível.


<a id="m1-tarefas"></a>

## 9. Plano de execução por tarefas

As tarefas são futuras. Cada uma deve resultar em mudança pequena e revisável, com evidência do comportamento e das limitações. Testes são escritos para contratos e riscos reais, não para espelhar campos triviais. Começar pelo teste que demonstra o comportamento ausente quando houver implementação funcional; não executar comandos desta seção nesta etapa documental.

Caminhos sob `src/domain_catalog/`, `tests/domain_catalog/`, `docs/catalogo/` e `data/catalogs/` são propostos. Arquivos existentes citados como “adaptar” só poderão mudar na implementação autorizada, preservando invariantes experimentais.

<a id="m1-t01"></a>

### M1-01 — Fixar baseline de implementação e matriz de compatibilidade

**Dependências:** plano revisado e autorização para iniciar implementação. **Responsável proposto:** implementador com Felipe; frente 7 revisa identidade experimental.

**Arquivos:** criar `docs/catalogo/baseline-e-compatibilidade.md`; inspecionar `src/foundation/contracts.py`, `src/bsdd/context_builder.py`, `src/bsdd/client.py`, `src/config.py`, `src/experiment/` e pinos de prompt.

**Passos:**

1. Registrar commit, estado de trabalho, versões instaladas, caminhos do fluxo atual e testes pertinentes; não confundir suíte relatada com executada.
2. Mapear chamadas do builder e formatos realmente lidos, incluindo wrappers legados, canonicalizadores e tratamento de erros.
3. Enumerar schemas/facetas/portadores suportados por evidência de código e teste; marcar suporte parcial/desconhecido.
4. Identificar condição histórica a preservar e estratégia de integração isolada da nova fonte de contexto.

**Teste/aceite:** relatório reproduzível com três métodos do protocolo e três wrappers, matriz sem células “suportado” por inferência e casos históricos escolhidos. Nenhum baseline/GT/prompt é atualizado para fazer teste passar. Bloqueio real de ambiente é registrado com comando e saída, sem chamar isso de validação bem-sucedida.

<a id="m1-t02"></a>

### M1-02 — Registrar fontes e reconstruir o inventário auditável

**Dependências:** M1-01. **Responsável proposto:** Felipe/curador, com apoio de implementação.

**Arquivos:** criar `docs/catalogo/fontes.md`, `docs/catalogo/cobertura-daiane.csv`, `docs/catalogo/divergencias-daiane.csv` e `src/domain_catalog/importers/daiane.py`; binários de fonte ficam em armazenamento autorizado, não automaticamente no Git.

**Passos:**

1. Registrar identidade/edição/páginas/termos das fontes; obter hash apenas dos arquivos efetivamente adquiridos.
2. Transcrever todas as assertivas A.1–A.10 e B com IDs e categoria; registrar exigências geométricas/documentais fora da contagem semântica.
3. Recuperar o inventário dos 34 pontos, conferir achados e registrar contagem reportada versus verificada.
4. Recontar 195 entradas/88 caminhos e explicar diferenças; separar fonte 2026 sem substituir a base 2025.
5. Incorporar XML/planilha originais quando obtidos, por comparação, conservando a reconstrução anterior e suas correções.

**Teste/aceite:** cada linha aponta para origem e tem estado; as dez famílias aparecem; somas por categoria/família fecham segundo denominador declarado; diferenças não são apagadas. Um revisor consegue localizar amostra de cada família e de cada categoria na fonte. XML/planilha ausentes são pendência explícita; não bloqueiam estruturação pelos apêndices, mas impedem afirmar equivalência integral ao arquivo original.

<a id="m1-t03"></a>

### M1-03 — Implementar entidades e schema de catálogo

**Dependências:** M1-01 e amostra conferida de M1-02. **Arquivos:** criar `models.py`, `errors.py`, `data/catalogs/schemas/catalog-v1.json`, `tests/domain_catalog/test_models.py`.

**Passos:**

1. Implementar entidades da seção 3 com IDs estáveis, referências e estados separados.
2. Definir serialização, tipos lógicos/IFC, dimensões/unidades e valores enumerados.
3. Validar referências internas, identificadores duplicados, tipo de código enumerado, schema declarado e campos obrigatórios por estado.
4. Gerar schema de intercâmbio compatível com o modelo e documentar migração de formato.

**Testes:** enum `"1"` não vira inteiro; zero/falso não viram ausente; área não aceita unidade de comprimento; ID duplicado e referência órfã falham; alteração só de rótulo preserva ID; exemplo parcial de rascunho não passa como release.

**Aceite:** modelos validam fixtures válidas e rejeitam incompatibilidades com mensagens por campo. Tipo/estado não são inferidos do nome. Nenhuma nova dependência é adotada sem necessidade demonstrada.

<a id="m1-t04"></a>

### M1-04 — Reconciliar o perfil Daiane com cobertura integral de inventário

**Dependências:** M1-02 e M1-03. **Arquivos:** `docs/catalogo/cobertura-daiane.csv`, `divergencias-daiane.csv`, `data/catalogs/fixtures/daiane-reviewed/` e `tests/domain_catalog/test_daiane_coverage.py`.

**Passos:**

1. Agrupar assertivas por conceito candidato, comparando definição e qualificadores.
2. Criar bindings por schema/faceta/portador e regras por classe/predefined type/contexto.
3. Resolver com justificativa os casos confirmados; manter os demais pendentes, sem alterar a fonte.
4. Classificar cada entrada em cadastro, validação e enriquecimento suportados/pendentes.
5. Fazer revisão cruzada das dez famílias com especialista, incluindo `EB_Orçamento`, atributos, materiais, classificações e Qto.

**Testes:** toda assertiva tem destino ou pendência motivada; referência A/B não se perde após deduplicação; nomes acentuados são preservados; `Cost_Prop` não aparece como substituição silenciosa; binding incoerente de `Area_Forma` não ativa escrita.

**Aceite:** relatório por família/categoria com denominadores e divergências abertas. Entrega pode conter pendências documentadas, mas não recebe rótulo de perfil completamente operacional até atender todas as capacidades acordadas.

<a id="m1-t05"></a>

### M1-05 — Implementar aplicabilidade, aliases e registro de capacidades

**Dependências:** M1-03; decisões de domínio de M1-04 alimentam fixtures. **Arquivos:** criar `applicability.py`, `resolver.py`, `operations.py`, `tests/domain_catalog/test_resolution.py`, `test_applicability.py`, `test_capabilities.py`.

**Passos:**

1. Implementar operadores declarativos e lógica de aplicável/não aplicável/indeterminado no contexto cadastral.
2. Implementar resolução por ID/URI verificada/caminho e aliases aprovados com escopo.
3. Produzir candidatos estáveis, motivo e estado quando houver ambiguidade.
4. Registrar capacidades reais com operação/versionamento/insumos/precondições; operação ausente não é executada.
5. Tratar colisões, aliases cíclicos e resultados múltiplos sem escolher o primeiro.

**Testes:** mesmo nome em Psets diferentes não une conceitos; alias fora do escopo não resolve; ausência do sistema construtivo é indeterminada; classe/predefined type incompatível não aplica; operação desconhecida abstém; string semelhante não fabrica URI oficial.

**Aceite:** consulta retorna resolução justificada ou estado explícito. Regras não usam `eval`, import dinâmico de cadastro ou acesso à rede.

<a id="m1-t06"></a>

### M1-06 — Construir reader de pacote local fixado

**Dependências:** M1-03 e M1-05. **Arquivos:** criar `contracts.py`, `reader.py`, `package.py`, `tests/domain_catalog/test_reader.py`, `test_locality.py`.

**Passos:**

1. Implementar abertura por catalog ID/versão/hash com verificação do manifesto.
2. Construir índices internos de busca e referências a partir do pacote validado.
3. Implementar consulta/paginação com ordenação determinística e leitura sem mutação.
4. Diferenciar não encontrado, ambiguidade, formato incompatível e pacote corrompido.
5. Provar que operações do reader não instanciam o cliente HTTP legado.

**Testes:** pacote válido funciona com rede bloqueada por fixture; tentativa de chamada HTTP/socket faz teste falhar; hash incorreto e versão inesperada bloqueiam abertura; pacote ausente não abre “latest”; consultas não alteram bytes do release.

**Aceite:** reader cumpre os contratos ricos e mantém o mesmo release durante toda uma análise. Não há fallback de rede, cache legado ou catálogo vazio em erro.

<a id="m1-t07"></a>

### M1-07 — Adaptar contratos legados e grounding sem regressão silenciosa

**Dependências:** M1-06. **Arquivos:** criar `src/domain_catalog/adapters.py`, `tests/domain_catalog/test_legacy_adapters.py`; adaptar, quando autorizado, `src/bsdd/context_builder.py` e ponto de injeção; rever `tests/foundation/test_contracts.py`.

**Passos:**

1. Implementar projeção dos três métodos de `SemanticCatalog` e wrappers exigidos pelo builder.
2. Preservar formatos consumidos e registrar perdas de representação; recusar enriquecimento quando a projeção não for segura.
3. Introduzir origem local/versionada e erro estruturado no novo caminho; não rotular snapshot como `live`.
4. Isolar canonicalização e matching legados para não converter URNs locais em URIs oficiais.
5. Integrar sob condição explícita, mantendo reprodução histórica sem alterar pinos `v7.8`.

**Testes:** contrato estrutural e execução real de builder com provider falso/local; cobertura dos seis métodos; nome personalizado acentuado; propriedade ambígua; enum tipado não representável; erro de pacote; contexto não vazio quando fonte é válida.

**Aceite:** regressões pertinentes passam e qualquer diferença no novo contexto é documentada como nova condição. Um teste apenas de `isinstance(..., SemanticCatalog)` é insuficiente.

<a id="m1-t08"></a>

### M1-08 — Implementar serviço de curadoria e trilha durável

**Dependências:** M1-03; identidade/papéis acordados com frente 6. **Arquivos:** criar `curation.py`, `draft_store.py`, `audit.py`, `tests/domain_catalog/test_curation.py`, `test_curation_concurrency.py`.

**Passos:**

1. Persistir solicitações, revisões de rascunho, eventos e decisões em transações.
2. Implementar adicionar/duplicar com regras de identidade e histórico.
3. Exigir revisão esperada ao editar e hash/revisão exata ao aprovar.
4. Autorizar aprovação/publicação conforme papel fornecido pelo contexto confiável.
5. Registrar rejeição/cancelamento/motivo e impedir promoção automática de sugestões LLM.

**Testes:** operador sem papel não publica; editar após aprovação invalida aquela aprovação; duas edições concorrentes não se sobrescrevem; comando idempotente não duplica eventos; falha transacional preserva estado anterior; duplicar binding não duplica conceito involuntariamente.

**Aceite:** reiniciar aplicação recupera solicitações e decisões; dados de autor/revisão têm origem confiável; cada ação relevante tem evento. Política de pessoas distintas só é aplicada se acordada.

<a id="m1-t09"></a>

### M1-09 — Implementar publicação e importação de pacote com integridade

**Dependências:** M1-06 e M1-08. **Arquivos:** criar `publication.py`, completar `package.py`, criar `tests/domain_catalog/test_publication.py`, `test_package_security.py`.

**Passos:**

1. Gerar manifesto canônico e hash externo do manifesto, com dependências fechadas.
2. Criar candidato separado e reabri-lo para validação.
3. Promover de forma durável/atômica no ambiente definido, com recibo idempotente.
4. Rejeitar colisão de versão com conteúdo diferente, arquivos extras indevidos e referências fora do pacote.
5. Implementar recuperação de publicação interrompida sem ativar candidato não aprovado.

**Testes:** falha antes/depois de gravação de candidato; falha durante promoção/recibo; hash/tamanho divergente; path traversal; referência órfã; arquivo de operação executável disfarçado; versão de formato desconhecida; chave JSON duplicada e número não finito.

**Aceite:** após qualquer falha simulada há release anterior íntegro ou candidato não ativo identificável; nunca release ativo parcial. Nenhuma falha inicia download público.

<a id="m1-t10"></a>

### M1-10 — Preparar importador de snapshot bSDD e migração de fontes

**Dependências:** M1-03, M1-04 e M1-09. **Arquivos:** criar `importers/bsdd.py`, `tests/domain_catalog/test_bsdd_import.py`, `docs/catalogo/importacao-bsdd.md`.

**Passos:**

1. Definir subconjunto de formato bSDD suportado a partir da documentação oficial e fixtures permitidas.
2. Preservar dicionário/versão/URI/código/rótulo, bindings de classe, unidades, valores e fonte.
3. Produzir relatório de campos não representados, ambiguidades e referências externas ausentes.
4. Importar somente como staging/rascunho; revisar relações com conceitos locais.
5. Definir procedimento repetível para receber o futuro snapshot de Juliana sem depender de API em runtime.

**Testes:** propriedade local por código versus referência externa por URI; restrição por classe não sobrescreve definição global; códigos e rótulos distintos; referência externa ausente fica pendente; reimportação idêntica não duplica conceitos; incompatibilidade de tipo/unidade impede equivalência automática.

**Aceite:** importador não promete cobertura de campos não implementados, conserva proveniência e produz diff revisável. Dicionário de Juliana não é considerado disponível antes de recebê-lo.

<a id="m1-t11"></a>

### M1-11 — Implementar diff, pin de projeto e atualização rastreável

**Dependências:** M1-09; contrato de identidade com frentes 2/6/7. **Arquivos:** criar `migration.py`, `tests/domain_catalog/test_project_pin.py`, `test_migration.py`; adaptar armazenamento de identidade do projeto a definir pela frente 6.

**Passos:**

1. Comparar releases por IDs, separando alterações cosméticas, semânticas e operacionais.
2. Persistir pin exato e revisão de pin; proibir seleção implícita de última versão na análise.
3. Gerar plano de impacto e aplicar atualização explicitamente confirmada.
4. Gerar nova análise e invalidar propostas/cache conforme entradas e políticas afetadas.
5. Implementar seleção de release anterior sem apagar análises/eventos.

**Testes:** mudar unidade/binding/alias aponta impacto correto; atualização concorrente falha sem sobrescrever; pacote ausente não altera pin; A1 continua idêntica após A2; rollback gera evento/identidade posterior; versão igual/hash diferente é rejeitada.

**Aceite:** reconstruir qualquer análise com referências exatas, quando seus artefatos retidos estiverem disponíveis. Histórico não depende do estado atual de um rascunho.

<a id="m1-t12"></a>

### M1-12 — Integrar resultado semântico ao leitor/validador da frente 2

**Dependências:** M1-06, M1-11 e contrato de resultados acordado na frente 2. **Arquivos:** criar `tests/domain_catalog/test_ids_boundary.py`; adaptar fronteiras em `src/translator/`, `src/validation/`, `src/foundation/` conforme plano específico da frente 2.

**Passos:**

1. Associar resultado IDS e resolução semântica por identidade de requisito/elemento/análise.
2. Preservar validação de faceta suportada mesmo sem cadastro.
3. Distinguir caminho exigido e evidência encontrada por alias/outro Pset.
4. Expor esperado/encontrado/origem e os cinco estados confirmados, com casos sem elementos aplicáveis.
5. Verificar que leitura/validação não criam Psets, propriedades ou valores no IFC.

**Testes:** propriedade desconhecida presente/ausente; faceta não suportada; arquivo ilegível; requisito sem elemento aplicável com cardinalidades diferentes; alias só fornece candidato; bytes/estrutura do IFC original permanecem inalterados após leitura/verificação.

**Aceite:** integração não confunde alerta complementar com conformidade e não muta o modelo. Cobertura/cardinalidade dos requisitos seguem suporte IDS verificado; a primeira entrega analisa individualmente e preserva possibilidade de federação posterior com saídas separadas.

<a id="m1-t13"></a>

### M1-13 — Integrar políticas de evidência à frente 3

**Dependências:** M1-05, M1-07 e M1-12; coordenação de Nonato. **Arquivos:** criar `tests/domain_catalog/test_grounding_boundary.py`; adaptar pontos acordados em `src/suggestion_engine/grounding.py`, `deterministic.py`, `suggestion_cache.py` sob nova condição.

**Passos:**

1. Passar observação tipada e política/capacidade ao mecanismo de propostas.
2. Aplicar abstenção por falta/conflito/ausência de operação.
3. Registrar método, fonte, unidades e impacto em ocorrência/tipo.
4. Incluir pacote/política/operação/condição na identidade de cache.
5. Demonstrar recuperação exata e uma padronização apoiada em regra, antes de inferências mais amplas.

**Testes:** valor esperado não usado como evidência; estimativa não se apresenta como medição; conflito entre ocorrência/tipo permanece explícito; troca de catálogo não reutiliza proposta indevida; operação ausente não chama LLM livremente.

**Aceite:** cada proposta é sustentada por evidências identificáveis ou há abstenção justificada; nenhuma escrita IFC é feita pelo catálogo. Avaliação histórica continua reproduzível.

<a id="m1-t14"></a>

### M1-14 — Entregar a fatia de interface de catálogo com a frente 4

**Dependências:** M1-08, M1-09, M1-11 e direção visual refinada com frente 4. **Arquivos:** nova página/componente em `src/ui/` a definir após revisão da estrutura; criar testes de serviço/UI adequados e roteiro `docs/catalogo/aceite-curadoria.md`.

**Passos:**

1. Mostrar tabela com filtros, estado e detalhes de original/reconciliado/fonte.
2. Permitir adicionar/duplicar rascunho e apresentar erros por campo.
3. Expor solicitação, revisão, diff e publicação conforme papel.
4. Mostrar pacote fixado e impacto da atualização no projeto.
5. Demonstrar a separação de conformidade, mapeamento e evidência nas visões por elemento/requisito.

**Testes:** fluxo operador → solicitação → curador → aprovação → publicação; concorrência e retomada; operação indisponível visível; botão não substitui autorização de serviço; acessibilidade de foco/teclado e clareza de mensagens em aceite humano.

**Aceite:** usuário consegue cadastrar um uso com operação existente sem editar JSON/código e entende o que permanece pendente. Não incluir editor IDS, viewer completo ou nova stack por conveniência.

<a id="m1-t15"></a>

### M1-15 — Instrumentar avaliação e regressão da condição

**Dependências:** M1-04, M1-07, M1-12 e M1-13; frente 7. **Arquivos:** criar `docs/catalogo/protocolo-avaliacao.md`, testes novos em `tests/domain_catalog/`; adaptar infraestrutura experimental apenas em tarefa própria autorizada.

**Passos:**

1. Definir denominadores e indicadores cadastrais/operacionais separados.
2. Selecionar amostras por família/faceta, com exemplos negativos, ambíguos e sem evidência.
3. Registrar nova condição de catálogo/contexto e relação com `v7.8`, sem substituir histórico.
4. Fazer revisão especializada independente da própria geração de mapeamentos.
5. Medir esforço de curadoria e recurso de consulta com hardware/corpus identificados.

**Testes:** mesmas entradas/pacote produzem mesma resolução determinística; alteração semântica muda identidade da condição; duplicatas não aumentam corpus; denominador excluído é explicitado; falso mapeamento e abstenção têm contagens próprias.

**Aceite:** relatório permite reproduzir a medição e distinguir cobertura, correção e eficiência. Não afirmar melhoria científica apenas porque testes unitários passam.

<a id="m1-t16"></a>

### M1-16 — Ensaiar atualização, interrupção, backup e rollback

**Dependências:** M1-09, M1-11 e armazenamento/backup acordados com frente 6. **Arquivos:** `tests/domain_catalog/test_recovery.py`, `docs/catalogo/operacao-e-recuperacao.md`.

**Passos:**

1. Publicar R1, criar análise A1, publicar R2 com mudanças controladas e atualizar.
2. Simular interrupções em edição, publicação e alteração de pin.
3. Restaurar backup em ambiente isolado e conferir hashes/referências/eventos.
4. Executar rollback explícito e verificar acesso ao histórico.
5. Registrar procedimentos de recuperação e limites operacionais observados.

**Testes/aceite:** perda de processo não deixa pin para pacote incompleto; restauração abre as análises esperadas; R1/R2 não têm bytes alterados; não são perdidos eventos confirmados dentro da garantia transacional definida. Garantias de durabilidade devem corresponder ao ambiente testado, não a uma suposição sobre disco/rede.

<a id="m1-t17"></a>

### M1-17 — Revisar isolamento, segurança e licença do pacote

**Dependências:** M1-09, M1-10, M1-14 e M1-16. **Responsabilidade conjunta:** implementação, curadoria e frente 6.

**Arquivos:** `tests/domain_catalog/test_package_security.py`, `test_locality.py`, `docs/catalogo/fontes.md` e checklist de release.

**Passos:**

1. Ensaiar pacote malformado, caminhos indevidos, volume excessivo e texto de fonte que pareça instrução.
2. Verificar autorização no serviço e impossibilidade de executar expressões cadastrais.
3. Verificar que logs/relatórios não copiam dados de projeto desnecessários e que fontes respeitam o escopo de distribuição.
4. Ensaiar runtime com acesso público bloqueado, incluindo assets da fatia de UI.
5. Revisar estados de erro e mensagens para que falhas não se convertam em aprovação.

**Aceite:** entrada de catálogo é tratada como dado; nenhum texto de fonte controla ferramentas/papéis; pacote inválido não ativa nem causa fallback externo. Termos incertos são registrados por componente e resolvidos antes de distribuir aquele componente.

<a id="m1-t18"></a>

### M1-18 — Consolidar entrega e abrir PR revisável

**Dependências:** tarefas da fatia proposta concluídas; para conclusão integral, M1-01–M1-17 com critérios pertinentes atendidos.

**Arquivos:** documentação de operação, cobertura, release notes e testes alterados na implementação futura; atualização deste plano com estado real.

**Passos:**

1. Reexecutar apenas verificações requeridas pela mudança e resolver falhas reais.
2. Conferir diff, dados de teste, identidades de fontes, caminhos e conteúdo do pacote.
3. Demonstrar os percursos da seção 8 e publicar relatório de limitações.
4. Preparar PR com problema, comportamento entregue, testes, impacto científico e pendências.
5. Solicitar revisão de domínio e técnica conforme áreas afetadas; merge somente após processo acordado.

**Aceite:** PR não anuncia cobertura/resultado que não foi verificado; destino do PR é confirmado antes da criação; não há alterações incidentais em dados/GT/configuração. Nenhum commit, PR ou merge é feito pela elaboração deste plano.

### 9.1 Dependências e caminho crítico

- M1-01 → M1-02/M1-03 → M1-04/M1-05 → M1-06 forma a base de domínio e leitura.
- M1-06 → M1-07 sustenta adaptação; M1-03 → M1-08 → M1-09 sustenta curadoria/publicação.
- M1-09 → M1-10/M1-11; M1-11 + frente 2 → M1-12; M1-12 + frente 3 → M1-13.
- M1-08/M1-09/M1-11 + frente 4 → M1-14.
- M1-04/M1-07/M1-12/M1-13 → M1-15; M1-09/M1-11 + frente 6 → M1-16.
- M1-10/M1-14/M1-16 → M1-17; revisão e critérios da fatia → M1-18.

A transcrição/conferência pode avançar junto ao schema após uma amostra real, sem esperar o XML original. Resolver semântica, revisar operações e disponibilizar frentes 2/4/6 são dependências que podem dominar o calendário. Trabalho simultâneo nesta proposta não é autorização para executar agentes ou modificar o repositório agora.

<a id="m1-testes"></a>

## 10. Estratégia de testes e evidências de aceite

### 10.1 Matriz de verificação

| Nível | Verificação de maior valor | Evidência esperada |
|---|---|---|
| Unidade | Tipos, unidades/dimensões, enumerações, identidade, referências, aplicabilidade, aliases, capacidades | Casos positivos e negativos com motivo preciso; ausência diferente de zero/falso |
| Contrato | Seis métodos consumidos pelo legado; contratos ricos; estado IDS separado de mapeamento | Fixtures versionadas e teste executando consumidores reais relevantes |
| Integração | IDS desconhecido, pacote fixado, observações/grounding, curadoria e pin | Fluxos completos sem rede e sem mutação pelo módulo 2 |
| Regressão | Comportamentos históricos pertinentes e condição nova explícita | Relatório de diferenças esperadas, pinos/GT/resultados preservados |
| Publicação | Aprovação exata, hash, versão única, dependências, atomicidade e idempotência | Candidato reaberto e falhas simuladas sem release parcial |
| Segurança | Papel de curador, path traversal, payload excessivo, instruções embutidas, operações arbitrárias | Rejeição antes da ativação, sem execução de código ou fallback |
| Recuperação | Interrupção, restore e rollback | Artefatos/históricos recuperáveis e hashes consistentes |
| Domínio | A.1–A.10/B, divergências e aplicação por schema | Matriz por entrada e revisão especializada |
| Interface | Cadastro/duplicação/revisão, estados, foco e retomada | Roteiro de aceite com observação humana; testes de serviço não substituem usabilidade |
| Desempenho | Abrir pacote, buscar/paginar, resolver lote, memória | Medição em hardware/corpus conhecidos; meta definida depois da linha de base |

Metas de latência e tamanho máximo do pacote precisam ser definidas com hardware e volume esperados. Antes disso, medir e registrar; não inventar um SLA. Limites de segurança de leitura/importação devem ter valores configurados e testados na implementação, mesmo que ajustados após medição.

### 10.2 Regressões existentes a selecionar

Arquivos existentes úteis para a primeira seleção: `tests/test_bsdd_client.py`, `tests/test_bsdd_context_builder.py`, `tests/test_bsdd.py`, `tests/test_canonical_uris.py`, `tests/test_semantic_registry.py`, `tests/test_property_match.py`, `tests/test_profiles.py`, `tests/test_ablacao_bsdd.py`, `tests/test_bsdd_block_por_tarefa.py`, `tests/test_suggestion_bsdd_validation.py`, `tests/test_prompt_contract_unificado.py` e `tests/foundation/test_contracts.py`.

A seleção deve conferir marcadores e dependências antes de rodar. Testes que dependam de rede/Ollama devem ser separados dos contratos locais; não instalar, chamar serviço ou baixar artefato implicitamente. Testes Windows de pinos/empacotamento, incluindo `tests/windows/test_install_contract.py`, tornam-se pertinentes se essa superfície for alterada.

**Comandos exemplificativos para a etapa futura**, depois de criar os testes e validar o ambiente:

```powershell
python -m pytest tests/domain_catalog/test_models.py tests/domain_catalog/test_resolution.py
python -m pytest tests/domain_catalog/test_reader.py tests/domain_catalog/test_legacy_adapters.py
python -m pytest tests/domain_catalog/test_publication.py tests/domain_catalog/test_recovery.py
python -m pytest tests/foundation/test_contracts.py tests/test_prompt_contract_unificado.py
```

Não há resultado presumido desses comandos. A suíte de 1.700 testes anteriormente relatada por outro assistente não foi executada nem certificada nesta elaboração. Esta tarefa verifica documentação, não comportamento funcional futuro.

### 10.3 Fixtures e independência da avaliação

Criar fixtures pequenas de IFC/IDS/pacote para cada risco: zero/falso, unidade incompatível, propriedade de tipo e de ocorrência conflitantes, alias em conjunto errado, classe sem elementos, operação não suportada e pacote inválido. Preservar os arquivos reais casa/prédio e seus históricos.

Fixtures sintéticas verificam contrato; não demonstram validade de todo o domínio. Para avaliação científica, usar exemplos revisados por especialista, independentes da geração de mapeamentos. Separar dados usados para desenhar aliases dos usados para medir erro. Registrar quais entradas da matriz têm somente teste sintético e quais têm evidência em modelo real.

<a id="m1-entregas"></a>

## 11. Entregas graduais, branches e revisão

A branch de integração indicada é `feat/semantic-foundation`. Os nomes abaixo são **propostas de branches futuras**; não foram criados. Destino final de PR ainda precisa ser definido. Não há autorização de merge automático nem de alteração da condição histórica.

| Entrega | Tarefas predominantes | Demonstração vertical | Branch proposta / revisão |
|---|---|---|---|
| E1 — Consulta local mínima | M1-01–03, amostra M1-04, M1-05–06 | Um conceito, dois usos e uma consulta local fixada com ausência/ambiguidade explícitas | `feat/catalog-local-reader`; revisão técnica + Felipe |
| E2 — Curadoria e release | M1-08–09, parte M1-14/M1-16 | Solicitação → rascunho → curador → pacote publicado → reabertura sem rede | `feat/catalog-curation-release`; curador + frente 6 |
| E3 — Integração rastreável | M1-07, M1-11–13 | IDS desconhecido valida quando suportado; mapeamento separado; nova análise ao mudar pacote | `feat/catalog-analysis-integration`; frentes 2/3/7 |
| E4 — Perfil completo de inventário | M1-04, M1-10, M1-15 | Todas as famílias/entradas com destino, capacidade e pendência explícita; importação de snapshot em staging | `feat/catalog-daiane-profile`; revisão especializada |
| E5 — Operação e aceite | M1-14, M1-16–18 | Curadoria pela plataforma, atualização/rollback/restauração e relatório de cobertura real | `feat/catalog-operational-acceptance`; frentes 4/6/7 |

E1 deve atravessar leitura/schema/resolução com um exemplo revisado; não é um pacote de classes vazias. E2 entrega autoridade/publicação antes de permitir uso operacional de conteúdo editado. E4 não oculta divergências para anunciar completude. Cada PR descreve o comportamento efetivamente entregue e suas limitações, com uma evidência verificável por critério de aceite.

Branches podem ser reorganizadas para reduzir conflitos, mantendo PRs delimitados. Não criar uma branch por arquivo nem misturar correções B01–B10 não necessárias à fatia. Quando uma correção do backlog for dependência real, referenciá-la e planejar PR específico com sua validação.

<a id="m1-esforco"></a>

## 12. Sequência e cronograma condicionado à capacidade

Não há carga semanal, prazo acadêmico ou disponibilidade de revisores confirmados. Portanto, este documento define ordem e faixas de esforço para planejamento, **não datas de entrega**. Estimativas abaixo são hipótese inicial, a recalibrar após E1; incluem desenvolvimento, testes e revisão técnica usual, mas não espera externa por fontes, decisão institucional ou mudanças de escopo.

| Onda | Escopo | Engenharia estimada | Curadoria/revisão de domínio estimada | Condição de saída |
|---|---|---:|---:|---|
| O0 | Baseline, fontes e amostra, M1-01–02 | 12–24 h | 12–24 h | Inventário rastreável e amostra conferida |
| O1 | Modelo, resolução e reader, M1-03/05/06 | 40–64 h | 8–16 h | E1 demonstrável sem rede |
| O2 | Curadoria/publicação, M1-08–09 | 40–64 h | 8–16 h | Aprovação e release recuperáveis |
| O3 | Adaptação/pin/interfaces, M1-07/11–13 | 48–80 h | 8–16 h | Nova análise e contratos integrados |
| O4 | Perfil e importação, M1-04/10 | 24–40 h | 24–48 h | Dez famílias com cobertura e pendências |
| O5 | Interface/avaliação, M1-14–15 | 32–56 h | 8–16 h | Fluxo de curadoria e métricas observáveis |
| O6 | Recuperação/isolamento/entrega, M1-16–18 | 24–40 h | 4–8 h | Aceites e PRs revisáveis |

**Total indicativo:** 220–368 horas de engenharia e 72–144 horas de curadoria/revisão de domínio. As horas de pessoas diferentes não se somam como duração de calendário. Há sobreposição possível entre transcrição/curadoria e implementação depois de estabilizar schema e contratos.

Após confirmar capacidades semanais `Ce` e `Cc`, o piso teórico de calendário é o maior entre `He/Ce` e `Hc/Cc`; dependências, disponibilidade das outras frentes e espera por aprovação/fontes aumentam esse piso. Por exemplo, capacidades de 20 h/semana de engenharia e 8 h/semana de curadoria implicariam pisos de 11–18,4 e 9–18 semanas respectivamente, **antes** das restrições de sequência. É ilustração matemática, não previsão acordada.

Se o prazo acadêmico não comportar o módulo integral, negociar uma fatia demonstrável E1–E3 com cobertura explicitamente parcial e manter a matriz completa como dívida visível. Não retirar arquitetura/estrutura do piso de pesquisa nem renomear cobertura parcial como conclusão integral sem nova decisão.

<a id="m1-riscos"></a>

## 13. Riscos, decisões abertas e pontos de revisão

| Risco / decisão | Consequência | Tratamento e responsável proposto |
|---|---|---|
| XML original e planilha indisponíveis | Reconstrução pode diferir do instrumento original | M1-02 registra lacuna; Felipe encaminha obtenção com Juliana; comparação posterior preserva histórico |
| Lista completa das 34 divergências ausente | Falsa sensação de reconciliação completa | Recuperar/recontar ledger; nunca inventar itens para fechar número |
| Operação inferida a partir de cadastro | Propostas sem evidência ou método válido | Registro de capacidades, abstenção e tarefa de engenharia; frentes 1/3 |
| Aliases legados semanticamente amplos | Falsas correspondências e falsas aprovações | Escopo/revisão de aliases e separação do validador; frentes 1/2 |
| Diferença entre schemas/portadores | Campo inválido ou interpretação errada | Matriz por binding, teste de schema e ausência de suporte explícita |
| DTO legado perde tipo/proveniência | Grounding enganoso | Adaptador restrito e contrato rico; M1-07 |
| Publicação/pin sem atomicidade | Projeto aponta para pacote parcial | Falhas simuladas e recibos idempotentes; frente 6 |
| Curadoria insuficiente para dez famílias | Acúmulo de rascunhos ou atraso | Definir curador, tempo semanal e revisão especializada; Felipe |
| SQLite usado como servidor compartilhado sem ensaio | Conflito/perda de escrita | Começar com topologia verificada; decidir implantação multiusuário na frente 6 |
| Mudança de contexto atribuída à v7.8 | Comparação científica inválida | Nova identidade/condição, histórico preservado; frente 7 |
| Permissões/licenças pouco claras por arquivo | Distribuição inadequada de fonte/código | Conferir termos por componente e separar referência de redistribuição |
| Qualidade de OCR/transcrição | Nomes/tipos incorretos | Conferência visual/arquivo original na implementação e dupla revisão das divergências |
| Atualização global implícita | Análises anteriores perdem significado | Pin/hash e atualização explícita com nova análise |
| Cadastro expõe dados de modelo desnecessários | Acesso indevido a informação de projeto | Minimização de solicitações/logs e governança da frente 6 |

**Decisões ainda necessárias antes das respectivas implementações:**

1. Pessoa(s) com papel de curador, critérios de aprovação especializada e política de separação de funções.
2. Namespace institucional definitivo, mantenedor e formato da primeira versão pública/interna.
3. Capacidades, facetas, portadores e releases exatos a testar nas metas aprovadas IFC2X3/IFC4/IFC4.3, junto à versão IDS, coordenados com frente 2.
4. Desenho do extra federado posterior: associação de IDSs, alinhamento espacial, identidade por arquivo/revisão/elemento e integração visual; análise individual inicial e saídas por IFC já estão confirmadas.
5. Topologia local versus servidor interno, diretório operacional, autenticação, concorrência, retenção e política de releases problemáticos.
6. Contrato final de identidade do projeto/análise e persistência compartilhada, sem enfraquecer D08/D14.
7. Layout detalhado da curadoria, liderança restante da frente 4 e testes de usabilidade.
8. Regras científicas de nova condição, critérios de gabarito, hardware e metas de desempenho.
9. Horas semanais, prazo acadêmico, disponibilidade de revisão e destino dos PRs.
10. Escopo de memoriais/especificações externas e requisitos de licença/distribuição.
11. Recebimento/versão/licença do dicionário de Juliana e estratégia exata de mapeamento.
12. Política de cópia IFC parcial e escrita/revalidação nas frentes posteriores; módulo 2 permanece sem mutação. Diagnóstico/exportação independente de enriquecimento foi confirmado; formatos, limites e timing permanecem a ensaiar.

Esses pontos não impedem produzir schema, reader, fixtures e inventário em uma fatia inicial autorizada. Impedem afirmar escolhas ou capacidades correspondentes como fechadas. Quando uma decisão for confirmada, registrá-la no índice e refletir os impactos neste plano.

<a id="m1-aceite"></a>

## 14. Prontidão e definição de conclusão

### 14.1 Para iniciar a primeira fatia

- [ ] Plano revisado quanto ao escopo e responsáveis; autorização de implementação distinta da aprovação documental.
- [ ] Baseline e isolamento de alterações do usuário conferidos; destino do trabalho Git acordado.
- [ ] Amostra de fonte conferida e fixtures permitidas identificadas.
- [ ] Critérios de IDs, schema e contrato rico revisados, com diferenças do legado explícitas.
- [ ] Estratégia de preservação da condição v7.8 e testes de regressão selecionada.
- [ ] Curador/revisor de domínio disponível para a amostra inicial.

### 14.2 Para publicar um primeiro release de uso

- [ ] Conteúdo aprovado em revisão exata e fontes/limitações identificadas.
- [ ] Nenhum binding ativo com unidade/tipo/portador incoerente ou referência órfã.
- [ ] Alias ambíguo não resolve automaticamente; operação ausente não enriquece.
- [ ] Pacote reaberto com hashes válidos; publicação interrompida não ativa parcial.
- [ ] Papel de curador verificado no serviço e trilha durável.
- [ ] Reader sem dependência pública e sem fallback de rede.
- [ ] Cobertura parcial/completa descrita com denominadores e pendências reais.
- [ ] Projeto fixa versão/hash; atualização é explícita e gera nova análise.
- [ ] Backup/restauração/rollback ensaiados no ambiente definido.
- [ ] Termos de distribuição verificados para os componentes incluídos.

### 14.3 Para concluir o módulo no piso acordado

- [ ] Todas as entradas A.1–A.10 e B têm transcrição, destino, reconciliação/pendência e capacidade rastreáveis.
- [ ] Contagens relatadas foram conferidas, inclusive inventário das divergências; diferenças documentadas.
- [ ] Caminhos de validação e enriquecimento suportados têm testes e evidência adequada por família/faceta.
- [ ] Curadoria acessível pela plataforma: adicionar/duplicar, revisar, aprovar, publicar e consultar histórico.
- [ ] Contratos com frentes 2/3/4/6/7 integrados e demonstrados nos percursos da seção 8.
- [ ] Módulo 2 continua somente leitura/verificação; estados e ausência de elementos estão explícitos.
- [ ] Resultados históricos e originais IFC/IDS permanecem preservados; mudanças geram identidades novas.
- [ ] Avaliação distingue cobertura, correção, abstenção e esforço, sem confundir teste sintético com validação científica.
- [ ] Riscos residuais e pendências externas aparecem no relatório final; nenhum “não verificado” é anunciado como aprovado.

<a id="m1-fontes"></a>

## 15. Referências e evidência desta elaboração

| Fonte | Uso e limite |
|---|---|
| [Consolidação de 09/10](CONSOLIDACAO-2026-10-09.md) | Registro congelado de decisões/inventário; números de cobertura e divergências são baseline relatado |
| [Decisões posteriores](README.md#decisoes-posteriores-de-0910) | Confirmações posteriores, incluindo visão por requisito, identidade da análise, cinco estados e leitura sem mutação |
| [Arquitetura base](../arquitetura/base-do-projeto.md) | Fronteiras da aplicação e capacidades observadas |
| [Dissertação de Daiane, 2025](https://drive.google.com/file/d/1TNRFxlXW9osGvrkNavm9t2A-qbQpbNcu/view) | Texto consultado via conector; pp. 86–94 requisitos, 95–98 IDS, 99–105 IDScribe, 161–170 A.1–A.10, 171–185 B; PDF não incorporado |
| [Zenodo 19150057](https://zenodo.org/records/19150057) | Registro público de 2026; não equivale ao instrumento de dez especificações de 2025 |
| [IDS_Cost.ids, link do registro](https://zenodo.org/records/19150057/files/IDS_Cost.ids?download=1) | XML analisado na pesquisa anterior; sem nova inspeção direta bem-sucedida nesta tarefa |
| [README IDScribe](https://zenodo.org/records/19150057/files/README_IDSCRIBE.txt?download=1) | Termos informados pelo pacote e contexto de uso; alcance por componente a conferir |
| [Modelo de importação bSDD](https://github.com/buildingSMART/bSDD/blob/master/Documentation/bSDD%20JSON%20import%20model.md) | Fonte oficial para estudar compatibilidade de importação; não é modelo pronto do catálogo local |
| [Documentação bSDD–IFC](https://github.com/buildingSMART/bSDD/blob/master/Documentation/bSDD-IFC%20documentation.md) | Distinção de códigos/rótulos e representações IFC por contexto |
| [Releases oficiais IDS](https://github.com/buildingSMART/IDS/releases) | Enumeração IFC4X3_ADD2 na release 1.0; não comprova suporte da aplicação atual |
| [Condição v7.8](../condicao-v7-8-2026-08-19.md) | Instrumento histórico a preservar; integração futura exige condição explícita se alterar contexto/decisão |

**Verificação desta entrega documental:** conferir leitura posterior do arquivo, links locais/âncoras, coerência das decisões, JSON ilustrativo, dependências das tarefas e escopo de alterações. Verificações funcionais acima são propostas futuras. Não se executam testes do produto, alterações de configuração, publicação de catálogo, contato externo, staging, commit, push ou merge ao elaborar este plano.

**Dados ainda necessários:** XML original das dez especificações, planilha editável, inventário individual das 34 divergências, curador/revisores disponíveis, capacidade semanal/prazo, infraestrutura e decisões abertas da seção 13. Essas lacunas estão incorporadas ao plano, sem substituir fontes ou inventar resultados.

<a id="m1-bibliografia"></a>

## 16. Integração bibliográfica de 10/10/2026 — domínio e catálogo

Esta é a **nova atualização documental autorizada em 10/10**, posterior à elaboração deste plano. A [síntese curada dos 29 artigos](../pesquisa/sintese-bibliografica-daiane-29-artigos.md) conserva IDs, referências originais, correções, páginas, nível de acesso e limites. A seleção abaixo reúne **14 estudos pertinentes ao M1**; não implica que todos sustentem todos os módulos. Nenhuma tarefa foi executada ou decisão aprovada por esta incorporação.

O conjunto fundamenta três separações já previstas: conceito versus representação IFC; curadoria de um significado versus exigência de um IDS fornecido; e definição de um campo versus evidência admissível para seu valor real. Os casos de orçamento ajudam a definir uso, origem e critério de medição; os dicionários mostram trabalho de especialistas e intercâmbio sem provar preenchimento verdadeiro. Os casos HBIM/BEM e de infraestrutura fornecem princípios de organização, sem ampliar o perfil inicial de arquitetura/estrutura ou antecipar SINAPI operacional.

**Como ler a matriz:** “base existente” remete a tarefa e critério já planejados, ainda não executados. Todo trecho marcado **Proposta** é refinamento de avaliação para revisão, sem nova aprovação de escopo. As páginas/seções e o alcance da evidência estão nas fichas vinculadas. O M1 não possui IDs individuais de casos: a referência é à tarefa e à [matriz de testes da seção 10](#m1-testes), sem inventar testes preexistentes.

| Referência | Decisão ou risco fundamentado | Tarefa existente | Critério de avaliação e efeito no desenvolvimento |
|---|---|---|---|
| [Q34-01 — Mancila](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-01) | Quantidade extraída depende do uso e critério de medição; códigos não substituem interpretação orçamentária | [M1-02](#m1-t02), [M1-13](#m1-t13) | Base existente: inventário com fonte e política de evidência. **Proposta:** registrar finalidade/fase e uma situação em que quantidade bruta não representa serviço; recusar equivalência sem critério documentado. |
| [Q34-02 — Moura 2024a](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-02) | Classificação, propriedade e quantidade são representações distintas; concordância com o exportador não é GT independente | [M1-03](#m1-t03), [M1-05](#m1-t05), [M1-15](#m1-t15) | Base existente: bindings e avaliação independente. **Proposta:** uma classe com classificações/quantidades em portadores diferentes; registrar origem e impedir que nome semelhante ou concordância circular prove correção. |
| [Q34-05 — Moura 2024c](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-05) | Requisitos por uso e associação IFC–SINAPI são antecedentes; cadastro não prova qualidade da assistência | [M1-04](#m1-t04), [M1-12](#m1-t12), [M1-15](#m1-t15) | Base existente: reconciliar Daiane sem substituir `EB_Orçamento`, separar mapeamento/conformidade. **Proposta:** relatar cobertura cadastral e erro semântico separadamente; não reivindicar novidade apenas por vincular IFC a custos. |
| [Q34-11 — Andrade](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-11) | Fonte → interpretação → requisito de modelagem → regra → teste exige rastreabilidade humana | [M1-02](#m1-t02), [M1-08](#m1-t08), [M1-15](#m1-t15) | Base existente: fonte, revisão/publicação e GT independente. **Proposta:** vincular cada binding amostrado à interpretação e a um erro deliberado; percentual de itens cobertos não será apresentado como acurácia. Não criar catálogo legal. |
| [Q310-01 — de Marco](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-01) | Normalização de requisitos ajuda ao mapeamento, mas mockup/questionário e dicionário futuro não comprovam enriquecimento | [M1-03](#m1-t03), [M1-13](#m1-t13), [M1-14](#m1-t14) | Base existente: separar definição, aplicabilidade e evidência. **Proposta:** exibir um conceito conhecido e campo vazio sem sugerir valor; criação de campo, URI ou enum permitido não conta como recuperação de informação. |
| [Q310-04 — Tomczak/circularidade](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-04) | Referência externa ou domínio de valores não prova que o produto real tenha aquela propriedade | [M1-06](#m1-t06), [M1-10](#m1-t10), [M1-13](#m1-t13) | Base existente: snapshot fixado, proveniência e limites de grounding. **Proposta:** uma URI válida sem vínculo comprovado ao produto deve continuar sem valor admissível; preservar ano editorial 2024 separado de 2022a em Daiane. |
| [Q310-07 — Bigai](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-07) | Aplicabilidade depende de uso, tipo/ocorrência e exportação; exclusão pode esconder falta de informação | [M1-05](#m1-t05), [M1-12](#m1-t12) | Base existente: aplicabilidade explícita e desconhecido ≠ não conforme. **Proposta:** contrastar parâmetro ausente no tipo, na ocorrência e objeto excluído; documentar o destino da evidência. Link correto `w78-2024-85`. |
| [Q310-08 — Garlet 2024](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-08) | Dicionário multilíngue organiza conceitos; os valores continuam dependentes de quem conhece o objeto | [M1-03](#m1-t03), [M1-05](#m1-t05), [M1-10](#m1-t10) | Base existente: separar URI, rótulo, alias, unidade e binding. **Proposta:** round-trip de termos com traduções iguais e sentidos distintos; não colapsar conceitos pela coincidência lexical nem presumir operação offline demonstrada no artigo. |
| [Q310-10 — Argasiński](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-10) | Classificação de domínio não é classe IFC; mapeamento parcial exige especialista | [M1-05](#m1-t05), [M1-08](#m1-t08), [M1-10](#m1-t10) | Base existente: alias revisado, autoridade do curador e identidade de fonte. **Proposta:** candidato lexical incorreto deve permanecer proposta, sem publicação automática; manter código/nome/URI/versão. O link `-63` pertence a este estudo. |
| [Q310-12 — Scandurra 2024](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-12) | Mesmo termo pode mudar de sentido por material ou componente; segmentação foi humana | [M1-05](#m1-t05), [M1-13](#m1-t13) | Base existente: alias condicionado e evidência admissível. **Proposta:** negativo com palavra igual em componente/material diferente deve rejeitar equivalência; não importar patologias do patrimônio para o perfil inicial. |
| [Q310-14 — Mellenthin Filardo](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-14) | Atualização de requisitos pode produzir conflitos; usuário precisa decidir sobre versões | [M1-08](#m1-t08), [M1-11](#m1-t11), [M1-14](#m1-t14) | Base existente: diff, pin, decisão registrada e ausência de atualização silenciosa. **Proposta:** mudança de tipo/unidade/valor predefinido gera conflito revisável e nova análise; aprovação cadastral não aprova valor no IFC. Questionário não mede retrabalho evitado. |
| [Q310-15 — Scandurra/di Luggo](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-15) | Estrutura JSON e persistência IFC são verificáveis; correção física/semântica é outra pergunta | [M1-03](#m1-t03), [M1-09](#m1-t09), [M1-15](#m1-t15) | Base existente: validação de pacote, tipos e proveniência. **Proposta:** pacote estruturalmente válido com associação semanticamente incorreta deve falhar na revisão de domínio; relatar integridade e correção em medidas distintas. |
| [Q310-17 — Tomczak/revisão](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-17) | Dicionário, IDS e métodos de entrega cobrem responsabilidades distintas | [M1-12](#m1-t12), [M1-13](#m1-t13), [M1-15](#m1-t15) | Base existente: requisito desconhecido pode ser validado; conceito conhecido não garante valor. **Proposta:** testar ambas as direções dessa independência e medir separadamente mapeamento, conformidade e evidência suficiente. |
| [Q310-18 — Trani](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-18) | Uso, fase e responsável ajudam a definir dados; incoerência de tipo/unidade pode sobreviver em fichas | [M1-02](#m1-t02), [M1-03](#m1-t03), [M1-08](#m1-t08) | Base existente: schema e revisão de domínio. **Proposta:** campo dimensional com tipo booleano deve ser sinalizado ao curador, sem correção presumida; responsabilidade pela informação não cria obrigatoriedade IDS. Infraestrutura permanece fora do recorte inicial. |

**Reserva de escopo:** [Q310-13 — Owerko](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-13) sustenta somente uma pista bibliográfica para [autoria IDS futura, D06](README.md#extensao-futura--autoria-ids). Há apenas resumo/metadados; obter o integral é **proposta de pesquisa**, sem criar tarefa de autoria nesta entrega ou atribuir geração por LLM ao estudo.

**Consequência para avaliação:** os estudos apoiam a necessidade de curadoria e proveniência, sem validar o catálogo local ou o nosso LLM. A pesquisa de [M1-15](#m1-t15) continua necessária: fonte independente, denominadores explícitos, erros de mapping/alias, cobertura por família e esforço de revisão. Os 29 artigos não substituem XML/planilha originais de Daiane, reconciliação das contagens históricas ou designação de curador. Novos exemplos da matriz são propostas de casos, não dados ou resultados já obtidos.


[Voltar ao planejamento](README.md) · [Índice documental](../README.md) · [Mapa das sete frentes](mapa-sete-frentes.md).
