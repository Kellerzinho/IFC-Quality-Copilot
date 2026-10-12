# Módulo 2 — Núcleo IFC/IDS

**Plano completo de implementação proposto — 9 de outubro de 2026.**
**Estado:** entrega documental; código, dados, dependências e verificadores não foram alterados.
**Objetivo:** ler um IFC e um IDS fornecidos, verificar capacidades e integridade, executar as avaliações suportadas e entregar diagnóstico completo, rastreável e exportável, sem modificar o IFC e sem depender de LLM.
**Arquitetura proposta:** serviço de análise somente leitura, com ingestão identificada, parser IDS seguro, representação de requisitos sem perda, adaptador de motor, leitores de evidência e armazenamento de resultados. Consumidores de interface, enriquecimento, exportação e avaliação usam o mesmo diagnóstico.
**Base tecnológica observada:** Python 3.11+, Pydantic v2, IfcOpenShell, lxml, pytest e módulos existentes de análise/tradução/validação. Versões efetivas e eventual inclusão de IfcTester serão fixadas por ensaio antes da implementação operacional; a consulta à documentação não certifica o ambiente.
**Especificação:** [decisões D01–D19](README.md#decisoes-posteriores-de-0910), [consolidação preservada](CONSOLIDACAO-2026-10-09.md), [plano do módulo 1](modulo-01-dominio-catalogo.md) e [mapa das sete frentes](mapa-sete-frentes.md).

Este plano define tarefas futuras e critérios verificáveis. Estruturas, assinaturas, formatos de relatório, estimativas e escolhas de implementação são propostas técnicas. As decisões de produto explicitamente confirmadas abaixo prevalecem sobre descrições históricas do pipeline. O plano 1 e a consolidação permanecem intactos.

**Nova integração bibliográfica — 10/10/2026:** [fundamentação e matriz referência → decisão/risco → tarefa/critério](#m2-bibliografia), baseada na [síntese dos 29 artigos](../pesquisa/sintese-bibliografica-daiane-29-artigos.md). Adendo documental aos três planos; decisões, IDs e escopo permanecem. Novos refinamentos estão marcados como propostas.

As declarações de preservação de outros planos e as verificações anteriores descrevem suas etapas históricas; esta nova autorização acrescenta bibliografia a M1, M2 e M3, sem alterar a consolidação.

**Navegação:** [Escopo](#m2-escopo) · [Inventário](#m2-inventario) · [Fluxo](#m2-fluxo) · [Identidade e dados](#m2-dados) · [Leitura IFC](#m2-leitura) · [Semântica IDS](#m2-ids) · [Compatibilidade](#m2-compatibilidade) · [Interfaces](#m2-interfaces) · [Operação segura](#m2-operacao) · [Diagnóstico](#m2-diagnostico) · [Percursos](#m2-percursos) · [Tarefas](#m2-tarefas) · [Testes](#m2-testes) · [Entregas e esforço](#m2-entregas) · [Riscos e aceite](#m2-aceite) · [Fontes](#m2-fontes) · [Bibliografia integrada](#m2-bibliografia).

<a id="m2-escopo"></a>

## 1. Escopo confirmado, atores e restrições globais

### 1.1 Decisões que vinculam todas as tarefas

1. Entrada inicial: **análise individual de um IFC e um IDS pronto**. Autoria de IDS está fora desta entrega.
2. Módulo 2 **somente lê e verifica**. Não cria Psets, propriedades, valores, relações ou classificações; não salva IFC alterado, nem em memória como “preparação”.
3. Checagens técnicas precedem avaliações de requisitos. Arquivos ilegíveis/inválidos bloqueiam quando impedem interpretação confiável.
4. Quando a interpretação é confiável, avaliar requisitos suportados e explicitar limitações. Não verificado jamais é aprovado.
5. Separar problemas técnicos, falhas de requisitos IDS e alertas complementares. Alertas fora do IDS não constituem conformidade formal.
6. Estados de avaliação: conforme, não conforme, não aplicável, não verificado e erro. Ausência de elementos aplicáveis é explícita e segue a exigência/cardinalidade da especificação.
7. Apresentação principal por elemento, alternativa por requisito; mostrar esperado, encontrado e origem.
8. Cada execução identifica versões/hashes de IFC, IDS, catálogo e verificador, incluindo opções e capacidades pertinentes. Mudanças geram nova análise, preservando histórico.
9. Cadastro semântico ausente não impede validar requisito suportado. O núcleo não inventa equivalência, alias ou valor para satisfazer o IDS.
10. IFC2X3, IFC4 e IFC4.3 são metas aprovadas. Leitura, validação, geometria/visualização e escrita futura têm suporte testado separadamente; fixar release exato, sem anunciar suporte universal.
11. IFC4.3 não amplia arquitetura/estrutura para infraestrutura. É necessário obter caso real IFC4.3 e fixtures adequadas.
12. Diagnóstico/exportação funcionam sem enriquecimento ou LLM. O resultado completo fica rastreável na plataforma; relatórios e BCF da frente 5 consomem o mesmo resultado.
13. Visualização federada de múltiplos IFCs é **extra posterior**, integrado à frente 4. Preservar arquivos, origem e saídas por IFC; não fundir fontes nem impor um IFC por projeto como restrição definitiva.
14. Operação, schemas, índices, logs e ativos são locais/internos ao IME, sem fallback público.
15. Preservar `PROMPT_VERSION v7.8`, seus pinos, GTs, comparadores, locks e resultados. Uma nova semântica de validação exige identidade/condição explícita, mesmo sem modificar prompt.
16. Esta etapa não instala pacotes, executa suíte funcional, altera configurações, faz staging/commit/push/merge ou inicia o módulo 3.

### 1.2 Atores e responsabilidades

| Ator/frente | Responsabilidade confirmada ou função no fluxo | Limite |
|---|---|---|
| Operador | Fornecer arquivos, iniciar/cancelar análise, examinar diagnóstico e solicitar exportação | Não precisa de LLM nem cadastro prévio de todas as propriedades |
| Felipe | Coordenação dos critérios BIM e da pesquisa | Liderança de implementação e disponibilidade semanal ainda não definidas |
| Implementador do núcleo | Executar tarefas e demonstrar contratos/testes | Pessoa a acordar; não presumir atribuição integral a Nonato |
| Curador do catálogo / frente 1 | Explicar conceitos e aprovar mapeamentos | Aprovação de catálogo não decide conformidade do requisito fornecido |
| Nonato / frente 3 | Responsável principal por contexto/enriquecimento | Consome evidências e resultados; não participa da decisão determinística obrigatória |
| Frente 4 | Navegação, acompanhamento e revisão; Nonato parcial | Stack/detalhes visuais e liderança restante em aberto |
| Frente 5 | Relatórios de saída, BCF e escrita IFC em etapas posteriores | Não duplicar motor de diagnóstico; nenhuma escrita pertence a este núcleo |
| Nonato / frente 6 | Responsável principal por infraestrutura/governança | Definir execução, isolamento, persistência, acesso e recursos |
| Frente 7 | Felipe coordena pesquisa; Nonato parcial | Gabarito independente, condição e métricas; testes técnicos não substituem avaliação científica |

### 1.3 Casos de uso iniciais

| Caso | Situação | Resultado observável |
|---|---|---|
| UC2-01 | IFC/IDS válidos e requisito suportado | Resultado por requisito/elemento, esperado/encontrado/origem e agregação explicada |
| UC2-02 | Propriedade desconhecida no catálogo | Validação IDS continua; mapeamento semântico fica ausente, sem preenchimento |
| UC2-03 | IDS com parte não suportada | Demais especificações/requisitos avaliáveis continuam; cobertura e limitações explícitas |
| UC2-04 | Arquivo ilegível ou interpretação inviável | Diagnóstico técnico com motivo; nenhuma aprovação formal |
| UC2-05 | Especificação sem elementos aplicáveis | Registro da especificação com contagem zero e interpretação da cardinalidade |
| UC2-06 | Valores conflitantes entre tipo/ocorrência ou portadores duplicados | Evidências separadas e regra de interpretação rastreável; sem escolher primeiro valor |
| UC2-07 | IFC sem representação geométrica | Validar informações independentes de geometria; capacidade geométrica marcada ausente/indisponível |
| UC2-08 | Cancelamento ou limite de recursos | Resultado parcial identificado, contagens consistentes e restante não verificado |
| UC2-09 | Repetição ou nova revisão de entrada | Nova execução identificável; histórico preservado e comparação sem reutilização indevida |
| UC2-10 | Exportar diagnóstico sem LLM disponível | Artefato derivado do mesmo resultado persistido, sem iniciar enriquecimento |

### 1.4 Fora do escopo inicial

Editor IDS, inferência/geração de sugestões, recuperação de fatos por LLM, criação determinística de propriedades, writer IFC, conserto automático de modelo, viewer federado, clash detection e orçamento SINAPI não integram esta entrega. A leitura pode identificar suas necessidades como pendências.

Geometria serve como capacidade de leitura/diagnóstico quando explicitamente solicitada e suportada. Uma falha geométrica não deve bloquear requisitos de propriedade independentes. Geração de geometria para viewer será integrada à frente 4; cálculo para enriquecimento pertence à frente 3 com método aprovado.

### 1.5 Foco de revisão transversal

Cinco condições de maior risco e seus testes responsáveis:

- Enumeração com várias alternativas ou restrições combinadas: nenhuma alternativa se perde; M2-04/M2-07.
- Aplicabilidade desconhecida e zero aplicáveis: não transformar população indefinida/vazia em aprovação; M2-08/M2-11.
- GlobalId duplicado, ausente ou inválido: manter elementos distintos e localização segura; M2-02/M2-05.
- Falha/ausência de XSD ou motor: estado técnico explícito, sem `pass` por falta de erros; M2-03/M2-06/M2-12.
- Interrupção/exportação de execução parcial: relatório mostra incompletude e não altera fontes; M2-13/M2-14/M2-17.

<a id="m2-inventario"></a>

## 2. Inventário verificado e fronteira de reaproveitamento

Leitura estática em 09/10/2026. Os comportamentos abaixo foram observados em código; não foram reproduzidos executando a aplicação nesta elaboração.

| Caminho existente | Implementação observada | Reaproveitar/adaptar |
|---|---|---|
| [src/ifc_analyzer/analyzer.py](../../src/ifc_analyzer/analyzer.py) | `IFCAnalyzer`, diagnósticos por perfil, `analyze_from_ids`, `get_element(guid)`, resumo | Reaproveitar leitura e leitores após teste; separar diagnóstico de enriquecimento automático de contexto |
| [src/ifc_analyzer/universal_extractor.py](../../src/ifc_analyzer/universal_extractor.py) | Reúne propriedades, material, quantidades e geometria | Adaptar para observações tipadas, origem e leitura sob demanda; evitar extrair tudo por falha |
| [src/ifc_analyzer/material_reader.py](../../src/ifc_analyzer/material_reader.py) | Leitura de material/camadas/constituintes e fallback de partes | Preservar conhecimento dos formatos; revisar associação por ordem/nome, unidade e escolha da primeira parte |
| [src/ifc_analyzer/extractors/quantity_extractor.py](../../src/ifc_analyzer/extractors/quantity_extractor.py) | Qto e fallback de bounding box | Separar quantidade declarada, cálculo e estimativa; nunca usar estimativa para fingir presença do Qto requerido |
| [src/ifc_analyzer/space_diagnostics.py](../../src/ifc_analyzer/space_diagnostics.py), [pset_diagnostics.py](../../src/ifc_analyzer/pset_diagnostics.py), [relation_diagnostics.py](../../src/ifc_analyzer/relation_diagnostics.py), [system_diagnostics.py](../../src/ifc_analyzer/system_diagnostics.py) | Diagnósticos complementares existentes | Consumir com categoria própria e ID/versionamento de regra; não misturar com avaliação formal IDS |
| [src/ifc_registry/registry.py](../../src/ifc_registry/registry.py) | Registro de entidades e apoio a normalização | Conferir schema real; não presumir que registro parcial representa todos os schemas |
| [src/translator/ids_parser.py](../../src/translator/ids_parser.py) | XML com lxml, representação reduzida, cache por caminho/mtime/tamanho | Novo parser sem perda e políticas explícitas; preservar adaptador para reprodução legada |
| [src/translator/rule_generator.py](../../src/translator/rule_generator.py) | Gera `OperationalRule`, aplica checks e retorna issues de falha | Não usar lista vazia de issues como prova de conformidade; migrar avaliação para resultados completos |
| [src/translator/pset_resolver.py](../../src/translator/pset_resolver.py) | Aliases e busca em Psets alternativos | Usar somente como busca de candidatos/evidência, sob política explícita; não corrigir caminho IDS |
| [data/ids_schema/ids.xsd](../../data/ids_schema/ids.xsd) | Declara “Placeholder”, usa estruturas permissivas | Substituição futura por bundle autêntico, versionado e local, com proveniência/licença |
| [src/validation/post_validator.py](../../src/validation/post_validator.py) | Verificação de schema, revalidação IDS e checks semânticos | Adaptar como consumidor do mesmo núcleo em revisão posterior, corrigindo estados permissivos |
| [src/models.py](../../src/models.py) | `IFCElement`, `IDSSpecification`, `OperationalRule`, `DiagnosticReport`, `ValidationResult` | Modelos atuais insuficientes para identidade/restrições/cobertura; criar DTOs próprios e projeções explícitas |
| [src/foundation/contracts.py](../../src/foundation/contracts.py), [adapters.py](../../src/foundation/adapters.py) | `ModelInspector`, `RequirementSource`, `IDSFileRequirementSource` | Preservar compatibilidade possível sem perder estado; contrato rico será adicional |
| [src/pipeline.py](../../src/pipeline.py) | Orquestra diagnóstico, sugestões, revisão e escrita; integra IDS com captura genérica de erro | Criar percurso diagnóstico independente e injetável; evitar construir clientes LLM/bSDD nesse percurso |
| [src/ui/](../../src/ui/), [src/mcp_server/](../../src/mcp_server/) | Apresentação/entrada existentes | Consumir serviço somente leitura, sem reutilizar sessão gravável como autoridade de diagnóstico |
| [src/bcf/exporter.py](../../src/bcf/exporter.py), [src/audit/logger.py](../../src/audit/logger.py) | Saídas/auditoria existentes | Adaptadores da frente 5; não comprovar compatibilidade BCF só pela forma atual |
| [src/experiment/execution_identity.py](../../src/experiment/execution_identity.py) e [src/experiment/](../../src/experiment/) | Identidade e experimentos históricos | Reutilizar princípios, preservando hipóteses/casos antigos; identidade operacional precisa generalizar sem reescrever históricos |

### 2.1 Perdas e riscos concretos do parser/tradutor

- `_simplevalue` retorna apenas a primeira enumeração; `_extract_constraint` inspeciona o primeiro filho de uma restrição e pode reduzir enumeração a igualdade.
- `IDSSpecification` contém nome, descrição, entidade/filtros e listas de dicionários; não conserva o conjunto completo de cardinalidades, versões, restrições e localização de origem.
- O parser diferencia quantidade por prefixo `Qto_`, representa atributo como propriedade com conjunto vazio e reduz `partOf` a convenção de relação. Essa representação interna não deve ser confundida com facetas oficiais.
- A aplicabilidade lida atualmente privilegia entidade, propriedades e materiais; recursos omitidos precisam virar inventário explícito, não ser descartados.
- Se o XSD não existe, o parser registra aviso e prossegue. XML é lido com `etree.parse` sem uma política de segurança explícita no ponto de chamada.
- O cache por caminho/mtime/tamanho não identifica integralmente conteúdo, versão do schema, parser ou opções.
- `_infer_check_type` infere por nome e simplifica limites numéricos; `is_numeric` exige valor positivo, o que não é uma exigência universal.
- `_evaluate_condition` e `_passes_check` têm retorno positivo no caso desconhecido. Relações são ignoradas nesse check e tratadas em outro diagnóstico, sem equivalência formal assegurada.
- `apply_rules` retorna apenas falhas e deduplica por GlobalId/conjunto/propriedade. Pode colapsar dois requisitos distintos sobre o mesmo campo e perde avaliações aprovadas/não executadas.
- Falha ao localizar entidade pode virar lista vazia e continuação; assim, ausência real e erro de interpretação não são distinguíveis pelo consumidor.

Esses achados fundamentam B01/B02/B07 e as tarefas M2-03/M2-04/M2-07/M2-08/M2-11. Corrigir schema sem corrigir representação e agregação não resolve o problema completo.

### 2.2 Pós-validação e integração atuais

`PostValidator._run_schema_check` devolve lista vazia de erros e aviso quando o validador está indisponível ou falha. `validate_element` calcula `pass` a partir da ausência de erros; `ValidationResult` tem booleanos inicialmente verdadeiros e lógica que força ambos a verdadeiro quando o status é `pass`. Logo, “não executado” pode desaparecer como categoria.

`_run_ids_revalidation` retorna vazio quando não há regras aplicáveis e captura algumas falhas de seleção como avisos. `_run_semantic_checks` incorpora critérios específicos, como formato de `FireRating`, ao resultado ligado a IDS; esses critérios precisam de categoria complementar e fonte própria.

No pipeline, `_integrate_ids` captura uma exceção genérica e continua com aviso. Instancia `PostValidator` com verificação de schema desativada por elemento nesse percurso. O novo contrato deve indicar o que efetivamente foi executado, a extensão verificada e o motivo de omissão. Não reclassificar automaticamente resultados antigos; adaptar a fronteira sob nova versão de verificador.

B03/B04/B05 permanecem ligados à escrita/revisão/BCF das frentes 4/5. Este plano entrega identidade e diagnóstico para resolvê-los depois; não amplia a entrega para corrigir todas as saídas.

### 2.3 Estratégia de motor e adaptação

**Proposta preferencial:** integrar um motor IDS especializado por `IdsEngine`, avaliando IfcTester versionado como primeiro candidato. Sua documentação oficial descreve leitura de IDS, validação IFC e relatórios, mas a página consultada é da documentação **0.9.0**, não comprova instalação ou compatibilidade com as dependências atuais. [IfcTester](https://docs.ifcopenshell.org/ifctester.html).

M2-06 executará um ensaio limitado para confirmar versão instalável no ambiente aprovado, licença, cobertura, resultados por requisito, cancelamento e ausência de mutação IFC. Se o candidato não cumprir uma capacidade, ela permanece não suportada até solução testada. Não trocar silenciosamente entre motores por resultado ou falha.

O tradutor atual permanece para reprodução histórica e projeções compatíveis. O novo fluxo não toma `OperationalRule` como representação normativa universal, porque ela também contém estratégias de sugestão e ações de escrita. Implementações próprias de facetas só entram por necessidade demonstrada e com os mesmos testes de conformidade; não começar reimplementando todo o padrão por conveniência.

A escolha final de backend é uma decisão técnica de M2-06, com relatório comparativo e efeito nas estimativas. O contrato e o corpus são estáveis perante essa escolha. Bibliotecas podem alterar seus objetos internos de resultado; cada execução terá instâncias próprias e nenhum objeto IFC gravável compartilhado com revisão/escrita.

### 2.4 Arquivos novos propostos

Todos os caminhos abaixo serão criados **somente na implementação futura**.

| Área | Caminhos propostos | Responsabilidade |
|---|---|---|
| Serviço e resultados | `src/validation/analysis_service.py`, `diagnostic_models.py`, `aggregation.py` | Orquestração, DTOs, estados e contagens |
| Fontes e identidade | `src/validation/source_gate.py`, `analysis_identity.py` | Ingestão local, hashes, manifesto de execução e imutabilidade |
| IDS seguro | `src/translator/ids_document.py`, `ids_constraints.py`, `ids_compiler.py` | Representação completa, restrições e plano de suporte |
| Bundle IDS | `src/validation/schema_bundle.py`, `data/ids_schema/releases/` | Schema oficial local, dependências, hash e licença |
| Motor | `src/validation/ids_engine.py`, `ifctester_adapter.py` | Contrato de avaliação e backend aprovado |
| Leitores IFC | `src/ifc_analyzer/identity.py`, `observations.py`, `units.py`, `geometry_evidence.py` | Identidade local e evidências sem alteração |
| Aplicabilidade e evidências de faceta | `src/validation/applicability.py`, `facet_evidence.py` | Planejar população e adaptar observações do motor sem duplicar sua semântica |
| Diagnóstico complementar | `src/validation/complementary.py` | Regras extras versionadas, isoladas do IDS |
| Persistência e exportação | `src/validation/diagnostic_store.py`, `diagnostic_export.py` | Resultado canônico, consulta e projeções |
| Ciclo de vida | `src/validation/analysis_worker.py` | Processo isolado, progresso, cancelamento e recursos |
| Testes e evidências | `tests/validation_core/`, `tests/fixtures/validation_core/`, `docs/nucleo-ifc-ids/` | Corpus, contratos, matrizes, operação e ensaios |

A divisão acompanha responsabilidades e limita tamanho dos arquivos; não exige serviço remoto novo. Evitar duplicar os contratos globais do módulo 1: `AnalysisIdentity`, referências de catálogo e observações devem ser alinhados antes de definir uma segunda estrutura equivalente.

<a id="m2-fluxo"></a>

## 3. Pipeline, estados de execução e algoritmo

### 3.1 Etapas propostas

| Etapa | Ação | Saída / falha |
|---|---|---|
| P0 — Solicitar | Receber referências locais/autorizadas a IFC e IDS, pin do catálogo quando aplicável, opções e ator | Pedido validado; recusar referência fora do escopo autorizado |
| P1 — Preservar e identificar | Ler bytes para armazenamento da análise sem sobrescrever a fonte, calcular hashes e verificar consistência da cópia | `SourceArtifactRef`; falha de leitura/alteração concorrente bloqueia fonte |
| P2 — Checar tecnicamente | Tipo/formato/schema declarado, parser IFC, XML seguro e XSD local | Relatório técnico independente da avaliação de requisitos |
| P3 — Interpretar IDS | Construir documento tipado com localização e todas as restrições/cardinalidades | Documento válido ou erro; nenhum recurso desconhecido desaparece |
| P4 — Planejar suporte | Cruzar schema IFC, versão IDS, facetas, operadores, portadores e backend | `EvaluationPlan` com cobertura e motivos de não suporte |
| P5 — Indexar modelo | Entidades/localizadores, classes/tipos, relações e unidades; leitura de evidência sob demanda | `ModelReadSession` e problemas locais identificados |
| P6 — Avaliar aplicabilidade | Determinar população por especificação; registrar ausência ou incerteza | `ApplicabilityResult`; incerteza não equivale a conjunto vazio |
| P7 — Avaliar requisitos | Executar requisitos suportados sobre população conhecida | `RequirementResult` para cada avaliação, inclusive satisfatória/omitida |
| P8 — Complementar | Executar regras extras explicitamente habilitadas e leituras geométricas requeridas | `ComplementaryFinding`, separado do IDS |
| P9 — Consolidar e persistir | Agregar sem aprovar indefinidos; gravar manifesto, resultados, cobertura e limites | Diagnóstico completo ou parcial com estado terminal |
| P10 — Consultar/exportar | Visões por elemento/requisito e artefatos derivados do mesmo diagnóstico | Relatório rastreável; nenhuma nova avaliação escondida na exportação |

O módulo 1 pode enriquecer descrições e informar resolução semântica depois de identificar o requisito. Sua indisponibilidade não deve bloquear P6/P7 quando a validação é independente. Nenhuma etapa inicial depende de Ollama ou busca bSDD.

### 3.2 Estados de execução diferentes dos estados de conformidade

`RunState` proposto: `queued`, `ingesting`, `checking_sources`, `planning`, `evaluating`, `finalizing`, `completed`, `completed_partial`, `blocked`, `cancelled`, `failed`.

`completed` significa que o escopo planejado foi executado; não significa que o modelo está conforme. `completed_partial` indica lacunas conhecidas e um subconjunto confiável. `blocked` aplica-se à impossibilidade técnica de interpretar as entradas; `failed` a uma falha de execução que interrompe o serviço. Cancelamento é evento do ciclo de vida, não sexto estado de avaliação: itens não avaliados ficam não verificados, com motivo.

Registrar transições com UTC e sequência monotônica de evento. O progresso informa etapa, unidades concluídas e denominador conhecido; não inventar percentual enquanto a população é desconhecida. Um worker encerrado não é considerado concluído só por ter produzido um arquivo parcial.

### 3.3 Bloqueio e continuidade parcial

| Condição | Conduta proposta conforme decisões confirmadas |
|---|---|
| IFC ilegível, XML malformado ou IDS sem interpretação estrutural confiável | Bloquear avaliação formal dependente; entregar diagnóstico técnico |
| XSD oficial requerido ausente/corrompido | Erro de infraestrutura/schema, sem declarar IDS válido; inspeção exploratória, se oferecida, fica explicitamente não verificada |
| Schema IFC reconhecido, mas recurso específico não suportado | Marcar escopo afetado; prosseguir no restante comprovadamente independente |
| Restrição de requisito não suportada | Não verificado para esse requisito; preservar avaliações de outros requisitos cuja aplicabilidade seja conhecida |
| Faceta de aplicabilidade não suportada | População daquela especificação indeterminada; não avaliar requisitos como conformes sobre um subconjunto adivinhado |
| Erro localizado em um elemento/valor, com contexto restante íntegro | Erro localizado, continuidade dos demais e agregação parcial |
| Falha geométrica | Isolar capacidade geométrica; continuar informações não dependentes dela |
| Catálogo ausente/corrompido ou LLM indisponível | Registrar limitação semântica; validar/exportar diagnóstico IDS independente |
| Cancelamento/limite | Preservar resultados concluídos com cobertura parcial; restante não verificado e motivo |
| Mesmo arquivo muda durante ingestão | Invalidar aquela ingestão e solicitar nova execução sobre fonte estável, sem misturar bytes |

Não “consertar” XML ou IFC em memória para habilitar validação formal. Reparos exploratórios seriam outro fluxo explicitamente autorizado, fora deste módulo.

### 3.4 Algoritmo de referência

O pseudocódigo define comportamento; não é implementação executável ou promessa de API já existente.

```text
criar run_id e manifesto provisório
ingerir fontes de maneira estável e identificar hashes
verificar IFC e IDS com políticas/bundle locais
se interpretação confiável for impossível:
    registrar problema técnico e finalizar como bloqueada
interpretar documento IDS completo e produzir plano de suporte
abrir sessão IFC somente leitura e indexar identidades
para cada especificação:
    verificar cancelamento e limites
    se aplicabilidade não puder ser determinada:
        registrar população indeterminada e requisitos não verificados
        continuar outra especificação independente
    determinar população e avaliar exigência de cardinalidade
    registrar explicitamente população vazia, quando ocorrer
    para cada requisito e elemento aplicável:
        se capacidade ausente: registrar não verificado
        senão: avaliar e guardar resultado + evidências + motivo
        se falha localizada: registrar erro, sem convertê-lo em aprovação
executar regras complementares habilitadas, com identidade própria
agregar resultados e cobertura por especificação, requisito e elemento
verificar integridade das fontes preservadas
persistir resultado terminal completo/parcial e hashes dos derivados
exportar consultando esse mesmo resultado
```

A ordem de processamento pode mudar para eficiência, mas não a semântica. Paginação de UI não pode limitar o conjunto validado; amostragem científica não pode ser apresentada como análise completa do arquivo.

<a id="m2-dados"></a>

## 4. Identidade, modelo de dados e proveniência

### 4.1 Hierarquia de identidades

- **Projeto:** contexto organizacional persistente, capaz de referenciar vários modelos ao longo do tempo.
- **Arquivo lógico/modelo:** identidade atribuída pelo projeto; nome de arquivo ou caminho não é identidade confiável.
- **Revisão de fonte:** bytes exatos, tamanho, SHA-256, papel IFC/IDS, schema declarado e referência de armazenamento interno.
- **Execução:** `run_id` único, entradas exatas, catálogo, verificador, opções/capacidades, horários e relação com execução anterior.
- **Elemento:** `ElementRef` composto por revisão do arquivo e localizador da entidade dentro dessa revisão; GlobalId é atributo de identificação adicional sujeito a validação.
- **Especificação/requisito:** ID local derivado do hash do IDS e caminho estrutural/posição, além do identificador declarado quando houver.
- **Avaliação:** identidade formada por execução, especificação, requisito e ElementRef, ou escopo de especificação para cardinalidade/zero aplicáveis.

`express_id`/STEP ID localiza uma entidade **naquela revisão**; não estabelece continuidade entre revisões. Dois IFCs podem conter mesmo GlobalId sem serem a mesma entidade operacional. Dentro de um arquivo, GlobalId duplicado precisa manter ambas as entidades e produzir problema técnico, sem sobrescrever índice. GlobalId ausente/inválido não autoriza gerar GUID novo para “reparar” a fonte.

Índice proposto: revisão → express ID → registro; índice auxiliar GlobalId → lista de ElementRefs. Consulta por GlobalId que retorne vários itens informa ambiguidade. Se identificadores numéricos também forem duplicados e o parser perder entidades, não inventar localizadores confiáveis: registrar limitação e bloquear o escopo cuja interpretação foi comprometida.

Continuar um elemento entre revisões exige correspondência rastreável da frente 5, com ambiguidade explícita. Mesmo GlobalId é candidato de correspondência, não autorização automática para reaproveitar aprovação, principalmente se valor, tipo, geometria ou requisito mudou.

### 4.2 Entidades propostas

| Entidade | Campos essenciais | Invariante |
|---|---|---|
| `SourceArtifactRef` | ID lógico, revisão, papel, hash, tamanho, nome de exibição, schema, localização interna | Fonte original preservada; caminho local privado não precisa aparecer em relatório compartilhável |
| `VerifierIdentity` | nome/versão/build, hash do artefato/código e lock de dependências, backend, versões Python/IfcOpenShell/lxml, bundle XSD/hash, opções e capability hash | Resultado reproduzível depende do conjunto efetivo, não só do nome do executável |
| `AnalysisIdentity` | projeto, run ID, referências IFC/IDS, pin/estado de catálogo, verificador, condição | Alinha o conceito do módulo 1; sem catálogo válido, registrar ausente/inválido explicitamente |
| `AnalysisRun` | identidade, estado, UTC início/fim, sequência, cobertura e vínculo anterior | Nova execução não sobrescreve resultados terminais antigos |
| `ElementRef` | revisão IFC, express ID, GlobalId opcional, estado do GUID, classe/schema | Chave não depende exclusivamente de GUID nem de nome |
| `ElementRecord` | ElementRef, nome, tipo, localização espacial e referências de relação | Dados de navegação não substituem evidência de requisito |
| `IDSLocation` | hash IDS, índice/caminho da especificação/faceta, linha XML quando disponível | Rótulos duplicados não colapsam requisitos |
| `SpecificationDefinition` | ID, nome/descrição, versões IFC declaradas, aplicabilidade completa, cardinalidade, requisitos | Preservar estrutura e valores originais, sem inferir obrigação pelo catálogo |
| `FacetDefinition` | tipo oficial, parâmetros/restrições tipados, cardinalidade, metadados URI/instruções, localização | Campo desconhecido deve ficar registrado como inválido/não suportado conforme schema |
| `Restriction` | tipo base e árvore de valores/enumerações/padrões/limites/composições | Não reduzir para string `equals:first`; preservar semântica e lexical original |
| `CapabilityRecord` | schema/release, versão IDS, faceta, operador, portador, estado, teste/evidência | Declarar suportado somente quando a combinação foi testada |
| `EvaluationPlan` | especificações, capacidades exigidas, escopos avaliáveis/bloqueados, motivos | Não excluir silenciosamente requisito para aumentar taxa de conformidade |
| `ApplicabilityResult` | especificação, população conhecida/indeterminada, contagem, referências, cardinalidade avaliada | Conjunto vazio conhecido é diferente de seleção que falhou |
| `EvidenceObservation` | ElementRef, caminho/portador, valor bruto/tipado, unidade, origem ocorrência/tipo/parte, método, referência | Compatível com o módulo 1; ausência e erro de leitura distintos |
| `RequirementResult` | IDs, estado, esperado estruturado, observações, motivo, motor/capacidade, mapeamento opcional | Estado deriva de avaliação suportada, nunca de ausência de issues |
| `TechnicalProblem` | código, etapa, escopo, gravidade operacional, efeito bloqueante, mensagem segura | Não confundir erro de infraestrutura com falha de requisito |
| `ComplementaryFinding` | regra/versionamento/fonte, ElementRef, observações, mensagem | Não entra no denominador de conformidade IDS |
| `SpecificationResult` | definição, ApplicabilityResult, resultado de cardinalidade, estado, referências de requisitos e limitações | Conserva resultado mesmo sem linha de elemento |
| `CoverageSummary` | complete, quantidades planejadas/avaliadas/não verificadas, populações indeterminadas e denominadores | Não mistura requisitos com pares elemento/requisito |
| `IntegrityRecord` | hashes antes/depois e método/resultado de verificação; instrumentação adicional nos ensaios | Booleano declarado não substitui evidência de ausência de mutação |
| `DiagnosticSnapshot` | manifesto, results, specifications, coverage, integrity, problemas técnicos, alertas, limitações e hash | Fonte canônica para plataforma, relatório e BCF |
| `ExportReceipt` | snapshot ID/hash, formato/versão, filtros, completude, arquivo/hash, UTC | Exportar não reavalia nem altera o diagnóstico |

`TypedValue` proposto é união discriminada: booleano, inteiro, decimal com representação controlada, string, enum/código, data/hora, referência ou coleção tipada. `ValueState` diferencia presente, ausente, nulo IFC, vazio, inválido, não suportado, erro e conflitante. Zero e falso permanecem valores, não sentinelas de desconhecido.

### 4.3 Original, normalizado e derivado

Guardar separadamente valor lexical/IFC original, valor tipado, transformação de unidade aplicada e valor comparado. Toda transformação tem operação/versionamento e justificativa. Nomes de propriedade/conjunto não são normalizados no arquivo nem substituídos por rótulo do catálogo.

Uma unidade convertida em memória para comparação é evidência derivada; não é alteração IFC. Quantidade calculada/estimada recebe método e origem distintos e não comprova que uma quantidade requerida exista no conjunto especificado. Representação geométrica derivada para visualização deve ter hash/opções, ElementRef e vínculo à fonte.

### 4.4 Exemplo JSON ilustrativo

Exemplo **sintético, parcial e não executado**. Hashes repetitivos, nomes e IDs demonstram a forma; não são evidência de análise real. Os campos finais serão validados por schema na tarefa M2-02. O requisito de existência é propositalmente simples e a ausência de catálogo não impede avaliá-lo.

```json
{
  "format_version": "1",
  "run_id": "run-demo-001",
  "run_state": "completed",
  "sources": {
    "ifc": {
      "model_id": "model-demo",
      "revision_id": "ifc-rev-demo",
      "sha256": "1111111111111111111111111111111111111111111111111111111111111111",
      "schema_identifier": "IFC4"
    },
    "ids": {
      "revision_id": "ids-rev-demo",
      "sha256": "2222222222222222222222222222222222222222222222222222222222222222",
      "version": "1.0"
    }
  },
  "catalog": {"state": "not_attached", "release_ref": null},
  "verifier": {
    "build_id": "illustrative-build",
    "build_sha256": "5555555555555555555555555555555555555555555555555555555555555555",
    "capability_manifest_sha256": "3333333333333333333333333333333333333333333333333333333333333333",
    "schema_bundle_sha256": "4444444444444444444444444444444444444444444444444444444444444444"
  },
  "result": {
    "specification_id": "spec-demo-001",
    "requirement_id": "req-demo-001",
    "element": {
      "ifc_revision_id": "ifc-rev-demo",
      "express_id": 42,
      "global_id": null,
      "global_id_state": "missing",
      "ifc_class": "IfcWall"
    },
    "state": "non_compliant",
    "reason_code": "required_property_absent",
    "expected": {
      "facet": "property",
      "property_set": "Demo_Set",
      "base_name": "Code",
      "cardinality": "required",
      "constraint": {"kind": "exists"}
    },
    "observations": [],
    "mapping_state": "unmapped"
  },
  "technical_problems": [
    {
      "code": "global_id_missing",
      "scope": "element",
      "blocking_for_this_requirement": false
    }
  ],
  "coverage": {
    "requirements_planned": 1,
    "requirements_evaluated": 1,
    "requirements_not_verified": 0
  },
  "ifc_mutated": false
}
```

O exemplo ilustra resultado de propriedade avaliável e problema de identidade coexistentes. O produto pode concluir a avaliação desse requisito e ainda informar problema técnico no arquivo. Isso não é certificado global de validade IFC, e `ifc_mutated: false` precisa de verificação de integridade, não de um booleano autodeclarado.


<a id="m2-leitura"></a>

## 5. Leitura IFC: origem, tipos, materiais, unidades e geometria

### 5.1 Abertura e verificações técnicas

Ler o cabeçalho sem presumir schema pelo nome do arquivo; comparar schema declarado e schema efetivamente aberto. Registrar produto/exportador e versão quando declarados como metadados, sem tratar esses campos como prova da integridade do modelo.

A leitura deve produzir três evidências distintas: integridade dos bytes, sucesso/limitações do parser e verificação de estrutura/schema. Abrir com IfcOpenShell não prova que toda a população seja válida. A documentação de `ifcopenshell.validate` informa limites para erros que antecedem o parsing, incluindo identificadores numéricos duplicados; as opções efetivas de validação devem constar do manifesto. [API de validação, documentação IfcOpenShell 0.9.0](https://docs.ifcopenshell.org/autoapi/ifcopenshell/validate/index.html).

Capturar mensagens do parser no contexto daquela execução e traduzir para problemas técnicos, sem despejar o log bruto na interface. Um arquivo parcialmente recuperado por uma biblioteca precisa de política explícita: só avaliar o subconjunto cuja interpretação e identidade forem confiáveis e marcar a incompletude. Se a perda comprometer população/cardinalidade, bloquear o resultado formal dessa especificação.

O serviço não deve passar objetos abertos à rotina de escrita da aplicação. A sessão de leitura expõe consultas/DTOs, fecha recursos ao terminar e não exporta o handle IFC ao cliente. Nenhuma chamada de `ifcopenshell.api` que crie/edite entidade é permitida no percurso de diagnóstico.

### 5.2 Ocorrência, tipo e conflitos

Guardar observações de ocorrência e de tipo separadamente antes de resolver o valor efetivo. Não depender apenas de um dicionário achatado de `get_psets` que elimine proveniência ou sobreponha propriedades de mesmo nome.

Cada observação identifica entidade portadora, relação, conjunto e propriedade/quantidade de origem, tipo IFC, unidade e caminho de acesso. A política de herança efetiva deve seguir a faceta/schema e ser testada com o backend fixado. Não adotar regra global “sempre ocorrência” ou “sempre tipo” para todas as facetas.

Casos obrigatórios: só no tipo; só na ocorrência; mesmo valor em ambos; valores divergentes; conjunto/propriedade duplicados; múltiplos tipos inválidos; propriedade vazia na ocorrência e valor no tipo. Se a regra do padrão/portador determina precedência, registrar o valor efetivo e a evidência da alternativa; se não puder decidir com confiança, emitir erro/não verificado no escopo pertinente e preservar conflito.

O módulo 2 informa alcance potencial em tipo para consumidores posteriores, mas não promove nenhum valor a todas as ocorrências. O fluxo de escrita decidirá esse impacto após revisão humana.

### 5.3 Materiais, camadas, perfis e constituintes

Representar a estrutura encontrada: material simples, lista, layer set/usage, profile set/usage, constituent set e associações via tipo/partes. Leitura de uma representação ainda não suportada é diferente de ausência de material.

O manual IDS consultado descreve verificação por nome/categoria e diferentes formas de associação; URI da faceta é metadado de referência, não exigência de igualdade de URI no IFC. Isso reforça a separação entre validação e catálogo. A regra exata deve ser fixada com o bundle e os testes da versão adotada. [Faceta material, documentação oficial em development](https://github.com/buildingSMART/IDS/blob/development/Documentation/UserManual/material-facet.md).

Para diagnóstico de evidência, conservar cada camada/constituinte com sua identidade, material, posição quando definida, espessura/unidade quando disponível e relações. Espessura de constituent set não deve ser presumida a partir da posição em outra lista. Correspondência com quantidades por nome/ordem, como no código atual, deve aparecer como método específico do exportador, com evidência/teste, ou permanecer ambígua.

O fallback atual que escolhe a primeira parte com material não caracteriza uma composição inteira. A nova leitura deve enumerar partes relevantes, distinguir materiais heterogêneos e não inferir que o todo tem a primeira composição encontrada. Traversal usa conjunto de visitados e limites de profundidade/nós; um ciclo não pode causar recursão ilimitada. O contador de profundidade deve atravessar chamadas de fallback, sem reiniciar a cada função pública.

Não somar espessuras ausentes como zero para afirmar espessura total conhecida. Total parcial precisa de estado próprio e identificação das parcelas desconhecidas. Largura de porta/janela não é espessura de camada. Esses cuidados pertencem à extração rastreável, não à inferência sobre a solução construtiva.

### 5.4 Unidades e quantidades

A leitura registra unidade explícita da propriedade/quantidade, unidade do projeto quando aplicável, dimensão e fator/offset de conversão utilizado. Se unidade não puder ser resolvida, manter indeterminação; não assumir metros porque um campo legado termina em `_m`.

Manter distinção entre valor numericamente escrito em string, valor IFC numérico e código enumerado que parece número. Booleano não é número, mesmo que a linguagem de programação permita essa conversão. Comparações numéricas não devem impor positividade por nome de propriedade nem tolerância fixa herdada sem fonte.

O manual de faceta property inclui propriedades e quantidades na mesma faceta IDS, embora o portador IFC seja distinto. Portanto, `quantity` pode ser uma categoria interna de evidência, mas não uma sétima faceta IDS inventada. Nome de conjunto, portador, tipo e unidade precisam ser conferidos, inclusive em conjuntos personalizados. [Faceta property, documentação oficial em development](https://github.com/buildingSMART/IDS/blob/development/Documentation/UserManual/property-facet.md).

Separar:

| Origem | Exemplo | Pode comprovar presença no caminho IDS? |
|---|---|---|
| Quantidade declarada | Campo de `IfcElementQuantity` no Qto requerido | Sim, quando faceta/tipo/unidade/restrição forem suportados e satisfeitos |
| Propriedade declarada | Valor em `IfcPropertySet` | Depende do requisito e portador efetivamente aceito; não trocar silenciosamente por Qto |
| Cálculo geométrico | Volume por método implementado/versionado | Não cria presença de Qto ausente; somente evidência derivada/alerta conforme política |
| Estimativa de bounding box | Produto das dimensões da caixa envolvente | Não equivale a volume líquido nem área descontando aberturas |
| Valor do catálogo/IDS | Restrição ou exemplo esperado | Não é valor observado no elemento |

Comparar valor declarado e calculado pode gerar alerta complementar. A divergência só é falha IDS se existir requisito formal correspondente e sua avaliação for suportada. Conservar método, tolerância/fonte, opções geométricas e estado de aproximação.

### 5.5 Relações, composição e navegação

Indexar relações com identidade própria e direção, distinguindo agregação, nesting, contenção espacial, atribuição a grupo e relações de abertura/preenchimento. Não transformar “tem alguma relação” em satisfação de `partOf`.

A faceta `partOf` tem entidade-alvo e parâmetro de relação, com navegação definida pelo padrão; o manual consultado descreve traversal de relações pertinentes. A implementação precisa de testes por relação e casos com múltiplos níveis, ciclos e relações inválidas. [Faceta partOf, documentação oficial em development](https://github.com/buildingSMART/IDS/blob/development/Documentation/UserManual/partof-facet.md).

Hierarquia para UI e conformidade da faceta são projeções distintas do mesmo grafo observado. Um elemento sem pavimento pode continuar avaliável para propriedade. Um componente de agregado não deve perder seu ElementRef porque a UI o mostra dentro de um conjunto.

### 5.6 Geometria e preparação para o extra federado

Declarar capacidades independentes: presença de representação, leitura de placement, tesselação, cálculo de grandeza e visualização. Sucesso em uma não certifica as demais. Sem geometria, conservar diagnóstico semântico e motivo da indisponibilidade visual.

Ativos derivados de visualização devem guardar revisão IFC, ElementRef, opções, unidade, transformação e hash. Não persistir “coordenadas ajustadas” no IFC original. O extra federado posterior precisa de política de alinhamento/georreferenciamento; origem local, deslocamento de visualização e sistema de referência não podem ser confundidos.

Na primeira entrega, modelar referências sem impor um único IFC ao projeto. O viewer federado, sua sincronização espacial e exportações múltiplas serão tarefas futuras; não entram no caminho crítico inicial.

<a id="m2-ids"></a>

## 6. IDS: schema autêntico, interpretação e avaliação

### 6.1 Três verificações diferentes

1. **XML bem formado e seguro:** bytes podem ser interpretados sem recuperação silenciosa, entidades externas ou acessos não autorizados.
2. **Conformidade estrutural IDS:** documento valida contra bundle XSD oficial fixado, com suas dependências locais.
3. **Semântica e capacidade operacional:** configurações de facetas/restrições são interpretáveis e suportadas pelo backend para aquele schema IFC.

Um documento pode passar no XSD e conter combinação semanticamente incoerente ou ainda não suportada pelo produto. Um motor pode ler algo fora do schema, mas isso não o torna IDS válido. O relatório identifica cada camada, versão e resultado.

### 6.2 Bundle offline do schema

Proposta inicial de alvo: **IDS 1.0**, com artefatos obtidos de uma release oficial e fixados por commit/hash. A página oficial registra `v1.0.0` como padrão final e a enumeração `IFC4X3_ADD2`. Isso não prova compatibilidade do parser ou do XSD hoje presente no projeto. [Releases buildingSMART IDS](https://github.com/buildingSMART/IDS/releases).

M2-03 deve adquirir por processo de desenvolvimento autorizado o XSD autêntico e todas as dependências, registrar URL/release/commit/hash/licença e empacotá-los localmente. A pesquisa desta tarefa consultou a release e os manuais; **não incorporou nem verificou os bytes do bundle oficial**. Tentativas de acesso direto aos caminhos de arquivos da tag não forneceram conteúdo verificável, portanto nenhum caminho remoto presumido é anunciado como artefato instalado.

Resolver imports/includes somente no conjunto aprovado. `xsi:schemaLocation` do documento é dado de identificação, não autorização para buscar URL. Se versão não for suportada, informar incompatibilidade; não validar contra um schema “parecido”. Se o bundle estiver ausente/corrompido, bloquear a declaração de validação formal, sem recorrer ao placeholder.

Separar validação XSD e auditoria semântica do IDS. Avaliar o IDS Audit Tool como referência/corpus ou etapa de auditoria adicional na implementação, com versão e licença verificadas; não prometer que a biblioteca já o executa. [Repositório oficial IDS Audit Tool](https://github.com/buildingSMART/IDS-Audit-tool).

### 6.3 Representação sem perda e compilação

Preservar, em objetos tipados e referências à fonte:

- informações, identificadores, nomes duplicados, instruções e versões IFC declaradas;
- todas as facetas da aplicabilidade e requisitos, com ordem/localização;
- `minOccurs`/`maxOccurs` da especificação e cardinalidade de cada requisito;
- entidades/predefined types, nomes, conjuntos, sistemas, valores, relações e `dataType`;
- `simpleValue`, todas as enumerações, padrões, limites inclusivos/exclusivos, comprimentos e demais restrições permitidas pelo bundle;
- namespaces/tipos das restrições, lexical original e forma normalizada para avaliação;
- URIs/metadados sem tratá-los como ações de rede ou campos IFC obrigatórios.

O parser não decide conformidade do modelo. O compilador transforma o documento em `EvaluationPlan`, listando capacidades necessárias e cada recurso não suportado. Elemento XML que não pertença ao padrão pode ser inválido no XSD; recurso válido mas não implementado é não suportado. Não confundir essas situações.

Não converter restrições em uma lista plana de comparações com semântica alterada. Enumerações e limites combinados precisam conservar sua composição conforme o schema e as regras adotadas. Expressões regulares XML Schema não são automaticamente expressões Python: usar mecanismo compatível ou declarar aquela forma não suportada, com teste que demonstre a diferença.

### 6.4 Facetas e cobertura do motor

O manual oficial distingue seis facetas e separa seleção da população de informação exigida. A tabela abaixo é um plano de cobertura, não alegação de suporte atual. [Especificações IDS, documentação oficial em development](https://github.com/buildingSMART/IDS/blob/development/Documentation/UserManual/specifications.md).

| Faceta | O que precisa ser conservado e testado | Risco de simplificação |
|---|---|---|
| entity | Classe, subclasses quando pertinentes, predefined type e tratamento de tipo/USERDEFINED | Normalizar caixa pelo schema, sem `capitalize` de nome desconhecido ou ignorar predefined type |
| attribute | Nome, valor, tipo, nulidade e restrições/cardinalidade permitidas | Não traduzir todo atributo para “texto não vazio” |
| property | Conjunto, baseName, dataType, valor, unidades, cardinalidade, portador/property ou quantity | Não substituir conjunto, aceitar qualquer alias ou reduzir enumeração |
| classification | Sistema e valor, cadeia/referência e representações por schema | Nome de material/classificação parecidos não são correspondência |
| material | Valor/nome/categoria e associações suportadas, inclusive estruturas compostas | Não escolher primeiro material e não exigir URI de catálogo como dado IFC |
| partOf | Entidade-alvo, predefined type pertinente, relação e traversal permitido | Não retornar verdadeiro porque relação é tratada por diagnóstico separado |

Portadores como propriedade simples, enumerada, lista, bounded/table ou quantidade precisam aparecer como subcapacidades. A falta de suporte de um portador não é ausência do valor. As formas reconhecidas pelo padrão e suas restrições serão fixadas no corpus versionado; não extrapolar o suporte do caso simples.

### 6.5 Aplicabilidade, cardinalidade e população vazia

Avaliar aplicabilidade antes dos requisitos, preservando todas as condições. Seleção com faceta desconhecida não é equivalente a ignorá-la. Se a população não puder ser determinada confiavelmente, marcar a especificação afetada como não verificada e continuar outras especificações independentes.

Distinguir cardinalidade da **população exigida pela especificação** e cardinalidade da **faceta de requisito**. Não implementar optional/prohibited como simples teste de valor presente. A ausência pode ser admitida ou exigida, e valor presente pode ainda violar uma restrição; regras exatas dependem da faceta e do bundle fixado.

Exemplos de aceite a verificar contra o corpus oficial da versão:

| Cenário | Resultado que o produto deve explicar |
|---|---|
| Especificação exige população mínima e nenhum objeto é aplicável | Falha de exigência da especificação, ainda que não exista linha de elemento |
| Especificação permite população vazia | Ausência explicitada; cardinalidade avaliada como satisfeita quando essa for a regra, sem inferir aprovação pela lista vazia |
| Especificação proíbe ocorrência da população e encontra objetos | Não conformidade de especificação com elementos/localização |
| Requisito required e valor ausente | Não conformidade quando a presença é efetivamente exigida |
| Requisito optional ausente | Resultado conforme a regra da faceta; distinguir ausência admitida de requisito não executado |
| Requisito optional presente e inválido | Não conformidade quando a restrição se aplica ao valor presente |
| Requisito prohibited com valor/associação proibidos | Não conformidade segundo a semântica da faceta |
| Aplicabilidade indisponível por erro | Erro/não verificado com população indeterminada; nunca zero aplicáveis presumido |

A apresentação pode usar “sem elementos aplicáveis” como rótulo adicional, mas deve conservar o resultado da checagem de cardinalidade e seu fundamento. Uma visão só por elemento não consegue expressar esse caso; a visão por requisito/especificação é obrigatória.

### 6.6 Resultado parcial e agregação

Guardar contagens por população, especificação, requisito e elemento. Não confundir número de requisitos, número de pares avaliados e número de falhas. Os denominadores devem informar exclusões, capacidades ausentes e população indeterminada.

**Proposta de agregação conservadora:**

- Uma avaliação suportada satisfatória gera conforme; violação demonstrada gera não conforme.
- Não aplicável exige razão de aplicabilidade/cardinalidade, não ausência de execução.
- Falta de capacidade ou interrupção antes da avaliação gera não verificado; exceção técnica que impede a avaliação gera erro.
- Uma especificação com falhas e itens não verificados mostra **falhas comprovadas e cobertura parcial**, sem substituir toda a informação por um único booleano.
- Um resultado global só anuncia conformidade integral quando todas as obrigações pertinentes, inclusive cardinalidade, foram avaliadas com suporte e satisfeitas; problemas técnicos que invalidem a interpretação impedem esse anúncio.
- Se não houver avaliação de elemento porque a população legitimamente é vazia, exibir esse fato e a checagem de cardinalidade. Não produzir selo verde genérico apenas por `issues == []`.
- Cancelamento, erro de motor ou schema indisponível impedem aprovação integral, mesmo com nenhum item não conforme registrado até então.

Preservar estado terminal da execução e conclusão formal separadamente. Preferir resumo de cobertura e estados a uma única nota. O readiness legado não representa denominador real de avaliações e não deve ser rotulado como conformidade IDS.

### 6.7 IDS oficial versus diagnóstico complementar

Regra proveniente do IDS tem localização exata no documento e resultado formal. Regras de nomenclatura, qualidade térmica, formato de resistência ao fogo, relações desejáveis ou coerência entre Qto e geometria entram como complementares quando não são exigidas pelo IDS fornecido.

Cada regra extra declara fonte, versão, objetivo, escopo, dados necessários, severidade e justificativa. Se o dado é insuficiente, a regra pode emitir “não avaliada”; não inventar violação normativa. Normas citadas historicamente devem ser verificadas antes de adotar limiares; nenhuma tolerância/número normativo é acrescentado nesta elaboração.

Quando o mesmo campo participa de várias especificações, conservar resultados separados. A UI pode agrupar apresentação, mas precisa permitir rastrear cada requisito e valor esperado. Deduplicação por GUID/Pset/propriedade não é identidade suficiente.

<a id="m2-compatibilidade"></a>

## 7. Matriz de schemas, versões e evidência de suporte

### 7.1 Evidência atual e metas

O cabeçalho de `casa_v1.ifc` foi relido e declara **IFC2X3**; `predio_v1.ifc` declara **IFC4**. Os hashes conferidos mostram que as cópias em `data/evaluation/casa/` e `data/evaluation/predio/` são idênticas aos respectivos arquivos da raiz. São os mesmos casos, não quatro modelos independentes.

Não foi fornecido/verificado um caso real IFC4.3 para o núcleo nesta etapa. A presença de um parser capaz de abrir parte do schema não demonstra cobertura de IDS, geometrias ou escrita.

| Meta confirmada | Caso real atual | Leitura | Validação formal | Geometria/visualização | Escrita posterior |
|---|---|---|---|---|---|
| IFC2X3 | Casa, cabeçalho verificado | Ensaiar parser/identidade/unidades | Ensaiar facetas/portadores/restrições | Ensaiar separadamente | Fora do núcleo; contrato com frente 5 |
| IFC4 | Prédio, cabeçalho verificado | Ensaiar parser/identidade/unidades | Ensaiar facetas/portadores/restrições | Ensaiar separadamente | Fora do núcleo; contrato com frente 5 |
| IFC4.3 | Caso arquitetura/estrutura pendente | Fixar release e obter fixtures | Fixar compatibilidade IDS/backend | Não presumir pelo sucesso da leitura | Ensaios futuros separados, sem ampliar domínio |

### 7.2 Manifesto de capacidades

Cada célula publicável será uma combinação: release IFC + versão IDS + versão backend/bundle + faceta + papel aplicabilidade/requisito + operador + portador + unidade/semântica pertinente. Estados propostos: planejada, reconhecida não suportada, suportada com limitações, testada, regressão conhecida.

Para anunciar suporte, registrar teste, fixture, resultado esperado independente, versão/fonte e limitações. Um teste de abertura não preenche toda a linha. Um ensaio sintético positivo não substitui os negativos, a cardinalidade e o caso real.

Matriz detalhada mínima:

- entidade/predefined type: valor único, restrição e versões/classes ausentes;
- atributo: string/booleano/número, nulo, opcional/proibido quando permitido;
- propriedade/Qto: ocorrência/tipo, unidade explícita/projeto, portador simples e formas não suportadas;
- material: simples, layers, profiles, constituents, associações herdadas e inconsistentes;
- classificação: sistema/código, múltiplas associações e diferenças de schema;
- partOf: relações suportadas, traversal, ciclos, ausência e erro;
- restrições: múltiplas enumerações, padrões, limites/comprimentos e combinações;
- população: vazia, proibida, obrigatória, parcial/indeterminada;
- execução: cancelamento, limite, erro de backend, ausência de schema e offline.

### 7.3 Versões e critérios de atualização

Fixar versões testadas do verificador, IfcOpenShell, backend IDS, lxml/libxml2 e bundle oficial. O requisito mínimo em `pyproject.toml` ou uma página de documentação recente não prova a combinação instalada. Não trocar versão para “ganhar suporte IFC4.3” sem corpus e revisão de regressões.

Uma atualização que altere resultado formal gera nova identidade de verificador/condição; reproduzir resultados antigos com o conjunto anterior quando retido. Mudanças de tolerância, interpretação de alias, datatype ou herança também alteram o instrumento, mesmo sem mudar o nome da biblioteca.

<a id="m2-interfaces"></a>

## 8. Contratos com módulos e consumidores

### 8.1 Serviço central proposto

Os nomes são propostas de API e os DTOs foram definidos na seção 4. Classes auxiliares: `AnalysisRequest` contém referências de entrada e opções; `AnalysisHandle` contém run ID; `DiagnosticQuery` contém filtros/paginação; `ResultPage` e `ElementPage` contêm itens e cursor; `ExportRequest` contém formato, filtros e destino autorizado; `CancelReceipt` confirma recebimento, não conclusão instantânea.

```python
class AnalysisService:
    def start(self, request: AnalysisRequest, actor: Actor) -> AnalysisHandle: ...
    def get_run(self, run_id: str) -> AnalysisRun: ...
    def cancel(self, run_id: str, actor: Actor) -> CancelReceipt: ...
    def get_diagnostic(self, run_id: str) -> DiagnosticSnapshot: ...
    def query_results(self, run_id: str, query: DiagnosticQuery) -> ResultPage: ...
    def query_elements(self, run_id: str, query: DiagnosticQuery) -> ElementPage: ...
    def export_diagnostic(self, run_id: str, request: ExportRequest) -> ExportReceipt: ...

class IdsEngine:
    def describe(self) -> VerifierIdentity: ...
    def plan(self, document: IDSDocument, model: ModelDescriptor) -> EvaluationPlan: ...
    def evaluate(
        self,
        session: ModelReadSession,
        plan: EvaluationPlan,
        sink: ResultSink,
        control: ExecutionControl,
    ) -> EngineRunSummary: ...
```

`IDSDocument` reúne definições e proveniência; `ModelDescriptor` identifica schema/capacidades da fonte; `ResultSink` persiste resultados/eventos com idempotência; `ExecutionControl` expõe cancelamento e orçamento de recursos; `EngineRunSummary` informa escopos concluídos/incompletos e motivos.

Não passar um `bool` como contrato total do motor. Falha de inicialização não é `False` de requisito e não é uma lista vazia. Adaptador que não consiga fornecer proveniência/cobertura suficiente precisa marcar limitação ou ser recusado para aquela capacidade.

### 8.2 Módulo 1 — catálogo

Consumir os contratos propostos do plano 1: `open_catalog(CatalogReleaseRef)`, `resolve_binding(BindingRequest)` e `ResolutionResult`, com reader fixado. Enviar schema, faceta, classe/predefined type conhecidos e caminhos originais. Não alterar parâmetros do IDS a partir do resultado semântico.

Conservar `mapping_state` separado de estado formal. Propriedade não cadastrada pode ser conforme; mapeamento aprovado pode coexistir com não conformidade por caminho/valor. Erro de pacote gera limitação semântica e não apaga diagnóstico independente.

Alinhar `AnalysisIdentity` e `EvidenceObservation` com o plano 1, acrescentando verificador e origem arquivo/revisão/elemento. Não modificar o plano 1 nesta elaboração: eventuais refinamentos de contrato entram como decisão técnica conjunta na implementação.

### 8.3 Módulo 3 — contexto/enriquecimento

Fornecer observações tipadas, resultado IDS, limitação, requisito e identidade da execução. Retorno de proposta/abstenção é responsabilidade da frente 3 e não altera o resultado já emitido pelo núcleo. O esperado no IDS não é evidência do valor real.

O consumidor solicita somente dados necessários, mantendo referência a fonte/escopo. Nenhum erro do enriquecimento muda conformidade IDS. A análise/exportação básica funciona com clientes LLM/bSDD não construídos ou deliberadamente indisponíveis.

### 8.4 Módulo 4 — interface

Consultar o mesmo snapshot por elemento ou requisito; filtros mudam apresentação, não reexecutam seletivamente o motor. Exibir categorias, cinco estados, contagens, cobertura, origem, esperado/encontrado e versão. Uma especificação sem elementos aparece na visão por requisito.

A interface informa capacidade pendente, bloqueio, cancelamento e resultado parcial. Ao cancelar, mostrar pedido recebido e depois estado terminal confirmado. Download filtrado indica filtros e total exportado; relatório completo não é limitado à página visível.

Visualização individual pode receber derivados identificados da sessão; viewer federado é extra posterior. Cliques precisam resolver ElementRef, sem selecionar o primeiro objeto com GlobalId igual.

### 8.5 Módulo 5 — relatório, BCF e revalidação após escrita

BCF e relatórios consomem `DiagnosticSnapshot` e referências; não recriam regras ou reduzem estado a pending/accepted. Identidade do projeto IFC e do componente são distintas. GUID ausente/duplicado requer tratamento explícito na exportação e não deve gerar referência BCF incorreta.

Após uma escrita humana autorizada fora do núcleo, a cópia IFC torna-se nova revisão de entrada. Revalidar com o **mesmo serviço/motor versionado**, relacionando diagnóstico anterior/posterior e mudanças. `PostValidator` será adaptador, não um segundo motor permissivo. A política de publicar IFC parcialmente conforme é decisão da frente 5; o núcleo fornece cobertura/falhas/regressões verificadas.

### 8.6 Módulo 6 — infraestrutura/governança

Receber identidade do ator, diretórios internos autorizados, isolamento de processo, capacidade de armazenamento e limites. Estado não deve depender de `session_state` ou variável global MCP para sobreviver a reinício.

Proposta de persistência inicial: SQLite transacional para manifesto/resultados e arquivos imutáveis internos para fontes/derivados, alinhada ao plano 1. Configuração multiusuário/servidor deve ser ensaiada; compartilhar um arquivo SQLite em rede não é garantia de operação institucional.

Fornecer eventos estruturados, métricas operacionais e erros seguros. Autorização é verificada no serviço para ler/exportar análises de um projeto; um run ID não funciona como credencial. Runtime não resolve schemas/URIs na internet.

### 8.7 Módulo 7 — pesquisa

Fornecer diagnóstico completo, identidade de fontes/verificador, capacidades, denominadores e tempos/memória. Separar erro de verificação, falha real de requisito e abstenção por falta de suporte. Comparações entre verificadores precisam controlar corpus e versão do IDS.

Novo núcleo pode corrigir falsos positivos/negativos históricos; isso requer condição de avaliação explícita, sem reescrever GT/resultados. Gabarito especializado independente deve incluir casos indeterminados e suporte parcial, não apenas valores preenchidos. Modelos reais iguais por hash não são amostras independentes.

<a id="m2-operacao"></a>

## 9. Parsing seguro, offline, cancelamento e recursos

### 9.1 Política XML explícita

Proposta de configuração do parser, a verificar na versão efetivamente fixada:

```python
parser = etree.XMLParser(
    resolve_entities=False,
    load_dtd=False,
    dtd_validation=False,
    no_network=True,
    recover=False,
    huge_tree=False,
)
```

A configuração é apenas parte da proteção. Rejeitar DTD/entidades declaradas no IDS de entrada, não executar XInclude e não aceitar acesso local por `file:` nem rede por URI do documento. Resolver imports do XSD somente por mapeamento fechado do bundle aprovado; `no_network` sozinho não cobre todos os acessos a arquivos locais.

Aplicar limites ao fluxo de bytes antes do parsing e ao tamanho/profundidade/número de nós conforme política de recursos. Não permitir que expansão de entidades, compressão implícita ou regex excessiva consuma recursos ilimitados. Mensagem do parser deve ser sanitizada para não copiar conteúdo sensível ou caminhos privados.

A documentação lxml 5.4 consultada descreve essas opções e ressalta que `recover` tenta recuperar XML e `huge_tree` desativa restrições. Os defaults dependem da versão; por isso o projeto deve configurá-los e testá-los explicitamente. [Parsing XML com lxml 5.4](https://lxml.de/5.4/parsing.html).

### 9.2 Arquivos e formatos

Primeira proposta de implementação: IFC STEP e IDS XML não compactados. Validar conteúdo/cabeçalho e parser, não só extensão/MIME informados. Não aceitar URL arbitrária como arquivo; aquisição remota pertence a outro fluxo autorizado.

IFCZIP/ZIP é extensão condicionada a necessidade e ensaio, não suporte inicial implícito. Se adotada, verificar número/tamanho expandido/razão de compressão, caminhos absolutos/travessia, links externos, arquivos inesperados e identidade do IFC selecionado. Nunca extrair livremente sobre diretório do projeto; preservar arquivo de transporte e hash dos membros autorizados.

Rejeitar arquivos especiais e referências que escapem do armazenamento permitido. Descrever claramente arquivo vazio, truncado, sem cabeçalho, schema desconhecido e conteúdo que não corresponde ao formato. A checagem deve ocorrer antes de criar trabalho caro de geometria.

### 9.3 Isolamento, cancelamento e memória

Proposta: executar análise em processo próprio, especialmente onde bibliotecas nativas de IFC/geometria não podem ser interrompidas de modo confiável. Coordenador permanece responsivo, observa recursos e persiste progresso; não compartilhar handle de modelo entre processo de diagnóstico e escrita.

Cancelamento cooperativo é verificado entre etapas/lotes. Se uma chamada nativa não retornar, o coordenador pode encerrar **somente o worker da execução**, conforme política de tempo acordada, e marcar diagnóstico parcial/cancelado. Não matar processos por nome genérico nem atingir sessões de outro projeto.

Os limites concretos de bytes, entidades, nós XML, tempo e memória são propostas a calibrar com hardware/corpus. Não há limiar numérico confirmado neste plano. Entretanto, antes de aceitar arquivos operacionais, a política precisa conter limites explícitos e testes que exercitem ultrapassagem; “sem número definido” não vira consumo ilimitado.

Paginar consulta e persistir resultados em lotes; evitar materializar todas as combinações elemento/requisito simultaneamente. Índices devem ser construídos uma vez por revisão; caches incluem identidade e capacidades. Processamento lazy não pode ocultar avaliações não realizadas. Geometria é solicitada separadamente para não tornar um diagnóstico de dados dependente de uma malha gigante.

### 9.4 Logs, conteúdo não confiável e derivados

Separar log técnico resumido, trilha de análise e diagnóstico detalhado com acesso por projeto. Por padrão, não gravar IFC/XML completos, caminhos pessoais, segredos, textos longos de propriedades ou payload de erros em logs gerais. Hashes e IDs opacos ajudam a localizar a análise; dados técnicos detalhados ficam no artefato autorizado.

Escapar texto de nomes/propriedades/instruções ao renderizar HTML/UI; uma fonte pode conter markup ou texto que pareça instrução ao sistema. Tratar tudo como dados. Relatórios CSV precisam de proteção contra fórmulas ao abrir em planilhas, preservando valor original no formato canônico e identificando a transformação de apresentação.

Escrever derivados em área da análise com nomes seguros e publicação atômica; nunca usar diretamente nome fornecido pelo usuário como caminho de sobrescrita. Exportação falha não altera snapshot nem fonte. Links/ativos de relatório devem ser locais; não inserir CDN ou fontes externas para que um relatório básico funcione.

<a id="m2-diagnostico"></a>

## 10. Diagnóstico completo e formatos de exportação propostos

### 10.1 Resultado canônico

O diagnóstico canônico precisa conter:

1. manifesto de execução e identidades de entrada/verificador/catálogo;
2. checagens técnicas e capacidade efetivamente executada;
3. documento IDS interpretado ou referências suficientes ao original preservado;
4. população/cardinalidade por especificação, incluindo zero/indeterminada;
5. avaliações de requisitos com estados, esperado, encontrado, origem e motivos;
6. alertas complementares em coleção separada;
7. agregações com denominadores, cobertura e filtros explicitados;
8. limitações/cancelamento/erros e integridade das fontes;
9. referências a derivados e relações com análises anteriores.

Não armazenar somente falhas: isso impede diferenciar aprovado, não avaliado e perdido. Para volumes grandes, persistir registros normalizados e índices e serializar sob demanda, sem replicar metadados de elemento em cada linha. A estrutura física e a retenção devem ser acordadas com frente 6.

### 10.2 Formatos iniciais a ensaiar

| Formato proposto | Finalidade | Critério de aceite |
|---|---|---|
| JSON versionado + manifesto | Intercâmbio completo e reprodutível | Tipos/estados/IDs preservados, schema validado e hash do artefato |
| CSV tabular de avaliações | Filtragem/revisão em planilha | Estado/origem/esperado/encontrado e IDs por linha; metadados e filtros acompanhando; proteção de fórmulas |
| HTML autocontido | Leitura humana e compartilhamento interno | Sem dependências públicas, texto escapado, totais/limitações visíveis e navegação por elemento/requisito |
| BCF | Colaboração sobre pendências | Frente 5 adapta o mesmo snapshot e testa versão/receptor/viewpoint; não implementar motor paralelo |

PDF/XLSX podem ser acrescentados quando houver necessidade confirmada e teste de fidelidade/volume. Esses formatos e sua ordem de implementação são propostas, não decisões de produto já fechadas. A primeira fatia pode entregar JSON completo e uma apresentação simples para tornar o resultado revisável, antes de todos os formatos.

Exportação de resultado parcial é permitida como diagnóstico **parcial**, com indicação inequívoca da execução, cobertura, motivo e itens não verificados. Exportar somente falhas é filtro opcional explícito; não chamar esse arquivo de resultado completo. IDs e versões acompanham todas as projeções.

### 10.3 Contagens e avaliação de integridade

Propor invariantes verificáveis: todo requisito planejado está avaliado, explicitamente não verificado ou associado a erro/escopo não aplicável; nenhuma avaliação aparece em duas categorias exclusivas; resultados de duas especificações sobre o mesmo campo permanecem distintos; contagens da plataforma e do exportador derivam das mesmas consultas.

Ao término, conferir hash das fontes preservadas e documentar método de verificação. Não reserializar o IFC para provar ausência de mutação: isso pode alterar representação/ordem. Testes de serviço devem também detectar chamadas de mutação em objetos/rotinas, porque manter bytes do arquivo original não prova que o modelo em memória não foi editado.

<a id="m2-percursos"></a>

## 11. Percursos representativos de ponta a ponta

### 11.1 IFC4, propriedade desconhecida e diagnóstico sem LLM

Operador fornece prédio IFC4 e IDS com propriedade personalizada não cadastrada. P1 identifica fontes; P2 valida estrutura; P4 confirma suporte da faceta. O motor observa valor exato no conjunto requerido, avalia restrição e registra conforme ou não conforme.

Catálogo retorna não mapeada e isso aparece como informação separada. Interface mostra esperado/encontrado/origem. Exportação consulta o snapshot com LLM desligado. Nenhuma propriedade é criada e o hash do IFC permanece igual.

### 11.2 Enumeração, requisito repetido e alias em conjunto errado

IDS contém dois requisitos distintos sobre um campo e uma enumeração com três alternativas. O parser conserva os três valores e IDs por localização. Um valor que corresponda à segunda alternativa não pode falhar por perda da primeira; duas especificações não podem ser fundidas.

O valor só existe em outro conjunto com nome semelhante. A validação do caminho formal permanece fiel ao IDS; o catálogo pode apontar candidato para revisão posterior. Relatório preserva falha e evidência alternativa, sem remapear a fonte.

### 11.3 População vazia e aplicabilidade não suportada

Duas especificações selecionam classes distintas. A primeira é inteiramente suportada e não encontra objetos: avaliar cardinalidade e mostrar contagem zero. A segunda contém filtro de aplicabilidade não suportado: população indeterminada, requisitos não verificados.

A UI por requisito mostra ambas. Resultado global não confunde as duas situações nem usa ausência de issues para aprovar. A primeira pode ter obrigação de presença violada; a segunda não pode produzir conclusão formal confiável.

### 11.4 Tipo/ocorrência, material composto e unidades

Uma parede possui propriedade no tipo, valor divergente na ocorrência, camadas com unidade do projeto e um Qto. Leitores conservam as origens; o motor usa regra de herança da faceta testada e registra qual valor comparou. Material heterogêneo de partes não é reduzido ao primeiro.

Normalização de unidade produz valor comparável e mantém original/método. Se uma associação de espessura for ambígua, não usar esse dado para completar o valor. Um alerta complementar pode sinalizar conflito sem alterar automaticamente o resultado de um requisito independente.

### 11.5 IFC4.3 sem geometria suportada

Caso IFC4.3 real/fixture passa na leitura de dados, mas uma representação geométrica não é suportada pelo ambiente ensaiado. Requisitos informacionais suportados continuam; visualização/cálculo recebem limitação própria. A matriz registra a combinação real, sem anunciar “IFC4.3 totalmente suportado”.

O domínio permanece arquitetura/estrutura. Nenhum teste com infraestrutura é exigido para fingir cobertura além da meta acordada.

### 11.6 Falha de schema, cancelamento e nova revisão

Sem bundle XSD confiável, a análise informa erro e não atesta validade do IDS. Em outra execução válida, usuário cancela após parte das avaliações: registrar resultados concluídos, restante não verificado e exportação parcial rotulada.

Ao reenviar IFC/IDS alterado ou mudar verificador/catálogo, criar nova análise. Histórico anterior permanece consultável; não retomar a execução parcial com entradas diferentes sob o mesmo run ID.


<a id="m2-tarefas"></a>

## 12. Tarefas de implementação, dependências e aceite

Cada tarefa abaixo entrega um comportamento revisável e seu ciclo de teste. Nenhuma foi executada nesta elaboração. Caminhos novos foram identificados na seção 2; testes e documentação específicos também são futuros. Trabalhar em fatias autorizadas, preservar mudanças locais e não usar este plano como autorização de commit/merge.

<a id="m2-t01"></a>

### M2-01 — Fixar baseline e corpus mínimo do núcleo

**Dependências:** revisão do plano e autorização para implementar. **Responsáveis propostos:** implementador + Felipe; frente 7 revisa condição.
**Arquivos:** criar `docs/nucleo-ifc-ids/baseline.md`, `tests/fixtures/validation_core/manifest.json`, `tests/validation_core/conftest.py`, `tests/validation_core/cases.py`.
**Interface produzida:** catálogo de casos com ID, fontes/hashes, esperado independente e capacidades exigidas; helper de teste `run_case(case_id: str) -> DiagnosticSnapshot` será ligado ao serviço conforme as tarefas seguintes.

- [ ] Registrar commit/estado local, versões efetivas, pinos e limites conhecidos, sem alterar dados históricos.
- [ ] Inventariar os testes existentes e identificar quais cobrem contrato versus reprodução de comportamento permissivo.
- [ ] Criar pequenas fixtures IFC/IDS válidas e inválidas para os cinco riscos da seção 1.5.
- [ ] Registrar casa/prédio como dois casos reais e suas cópias idênticas, sem ampliar denominador.
- [ ] Definir IDs estáveis para casos futuros IFC4.3 e pendência de obtenção do caso real.

**Testes/aceite:** manifesto rejeita ID duplicado, fonte ausente e esperado não definido; cópias com mesmo hash não contam como casos independentes. O corpus mínimo contém positivo, negativo, zero aplicáveis, não suportado e erro. Baseline observado é separado de suíte efetivamente executada.

<a id="m2-t02"></a>

### M2-02 — Criar contratos, identidades e ingestão imutável

**Dependências:** M2-01 e alinhamento de `AnalysisIdentity` com módulo 1.
**Arquivos:** criar `src/validation/diagnostic_models.py`, `analysis_identity.py`, `source_gate.py`, `tests/validation_core/test_identity.py`, `test_source_gate.py`.
**Consome:** referências de entrada de `AnalysisRequest`, ator e política interna da frente 6.
**Produz:** `SourceArtifactRef`, `AnalysisIdentity`, manifesto de execução e DTOs da seção 4.

- [ ] Escrever teste de arquivo alterado entre leitura/cópia e identidade por bytes, não só mtime/tamanho.
- [ ] Implementar ingestão estável com cópia interna autorizada e verificação de hash, sem sobrescrever fonte.
- [ ] Implementar IDs de execução, revisões e requisitos por localização; não usar nome de especificação como chave única.
- [ ] Registrar catálogo ausente/inválido explicitamente e verificador/opções/capacidades no manifesto.
- [ ] Testar repetição idêntica como nova execução rastreável e mudança de qualquer entrada como nova identidade de conteúdo.

**Aceite:** duas revisões de mesmo nome não se confundem; hashes repetidos podem compartilhar armazenamento, mas preservam referências lógicas e execuções. Fontes originais permanecem byte a byte iguais. IDs não contêm caminhos pessoais nem são usados como autorização de acesso.

<a id="m2-t03"></a>

### M2-03 — Substituir o placeholder por bundle IDS autêntico e parsing seguro

**Dependências:** M2-01/M2-02; aquisição autorizada dos artefatos oficiais.
**Arquivos:** criar `src/validation/schema_bundle.py`, `data/ids_schema/releases/` com manifesto/licenças, `tests/validation_core/test_schema_bundle.py`, `test_xml_security.py`; adaptar `src/translator/ids_parser.py` apenas na fronteira de novo fluxo.
**Consome:** bytes preservados IDS e referência de bundle.
**Produz:** resultado de XML/XSD com versão/hash, localização de erro e bloqueio explícito.

- [ ] Obter release oficial IDS 1.0 e dependências locais; registrar origem/commit/hash/licença sem presumir caminho remoto.
- [ ] Criar testes de IDS válido/inválido que o placeholder aceitava, XSD ausente/corrompido e versão não suportada.
- [ ] Implementar resolução fechada do bundle e parser com entidades/DTD/recovery/rede desativados conforme seção 9.
- [ ] Testar entidade externa HTTP e arquivo local, expansão de entidades, XInclude, schemaLocation remoto e XML profundo/truncado.
- [ ] Fazer ausência/falha de bundle bloquear declaração de validade, sem fallback permissivo.

**Aceite:** nenhuma leitura externa acontece nos testes adversariais; documento inválido não passa por existir XML bem formado. Bundle é verificável offline e licença/proveniência acompanham distribuição. O arquivo legado não é silenciosamente usado na condição nova; reprodução histórica mantém sua identificação própria.

<a id="m2-t04"></a>

### M2-04 — Interpretar IDS sem perder facetas, restrições ou cardinalidades

**Dependências:** M2-03.
**Arquivos:** criar `src/translator/ids_document.py`, `ids_constraints.py`, `ids_compiler.py`, `tests/validation_core/test_ids_document.py`, `test_constraints.py`; adaptar projeção legada de `ids_parser.py` quando necessário.
**Consome:** documento XML validado e identidade IDS.
**Produz:** `IDSDocument`, `SpecificationDefinition`, `FacetDefinition`, `Restriction` e localizações.

- [ ] Escrever casos com várias enumerações, valores false/zero, limites combinados, padrões e nomes duplicados de especificação.
- [ ] Implementar árvore tipada preservando lexical, tipo, metadados e localização de todas as facetas.
- [ ] Conservar cardinalidade de especificação e de requisito em campos distintos.
- [ ] Distinguir XML inválido e recurso válido não suportado; registrar ambos sem descartar nós.
- [ ] Testar projeção para `IDSSpecification` antigo somente quando representável; rejeitar perda silenciosa.

**Aceite:** segunda/terceira alternativa sobrevivem ao parsing; `partOf`, datatype e predefined type não viram convenções incompletas sem aviso. Cache, se usado, inclui hash IDS, bundle e parser; objetos mutáveis de resultado não são compartilhados entre execuções.

<a id="m2-t05"></a>

### M2-05 — Abrir IFC e indexar identidade, schema e população com confiança

**Dependências:** M2-02.
**Arquivos:** criar `src/ifc_analyzer/identity.py`, adaptar `src/ifc_analyzer/analyzer.py` por interface de leitura e criar `tests/validation_core/test_ifc_read_session.py`, `test_element_identity.py`.
**Consome:** revisão IFC preservada.
**Produz:** `ModelDescriptor`, `ModelReadSession`, `ElementRecord` e problemas técnicos.

- [ ] Escrever casos com GUID duplicado/nulo/inválido, nomes iguais e STEP IDs alterados entre revisões.
- [ ] Abrir com IfcOpenShell e registrar schema real, mensagens de parsing e limites da interpretação.
- [ ] Construir índice por revisão/express ID e índice auxiliar GlobalId → lista.
- [ ] Separar leitura confiável de arquivo parcialmente interpretado; não converter erro de classe em seleção vazia.
- [ ] Expor consultas sem handle de escrita e testar ausência de chamadas de criação/edição IFC.

**Aceite:** nenhum elemento é perdido por colisão de GlobalId; consulta ambígua não escolhe o primeiro. Falha estrutural que comprometa identidade/população bloqueia o escopo correspondente. Hash do original e estado dos objetos de fixture permanecem preservados.

<a id="m2-t06"></a>

### M2-06 — Ensaiar e fixar o backend IDS por capacidade

**Dependências:** M2-04/M2-05.
**Arquivos:** criar `src/validation/ids_engine.py`, `ifctester_adapter.py` se aprovado, `tests/validation_core/test_engine_contract.py`, `docs/nucleo-ifc-ids/decisao-motor.md`.
**Consome:** IDSDocument, sessão IFC e corpus.
**Produz:** `IdsEngine`, `VerifierIdentity`, manifesto inicial de capacidades e decisão técnica.

- [ ] Definir versão candidata de IfcTester compatível com o ambiente e verificar licença/dependências em etapa autorizada.
- [ ] Executar o mesmo corpus pequeno sobre candidato e comportamento legado, preservando esperados independentes.
- [ ] Verificar resultados por requisito, cardinalidade, origem, erros, unidade/herança e efeitos em memória.
- [ ] Implementar adaptador que exponha limitações em vez de alternar motores silenciosamente.
- [ ] Registrar capacidades aceitas, recusadas e trabalho adicional; revisar esforço antes de ampliar cobertura.

**Aceite:** escolha sustentada por testes e APIs reais da versão fixada; nenhum “suporte universal”. Se faltar uma capacidade necessária, registrar não suporte e tarefa específica, mantendo percurso parcial seguro. Instalar/atualizar dependências faz parte apenas da implementação autorizada, não deste documento.

<a id="m2-t07"></a>

### M2-07 — Avaliar restrições e facetas suportadas sem heurísticas indevidas

**Dependências:** M2-04/M2-06.
**Arquivos:** completar `ids_compiler.py`, `ids_constraints.py`, `ids_engine.py` e adaptador; criar `src/validation/facet_evidence.py`, `tests/validation_core/test_facets.py`, `test_restriction_evaluation.py`.
**Consome:** plano/definições e observações do backend.
**Produz:** RequirementResult com esperado completo, observações e estado/motivo.

- [ ] Adicionar casos parametrizados das seis facetas, separando aplicabilidade e requisito.
- [ ] Verificar enumerações, limites, tipos, strings/códigos numéricos, padrões e portadores.
- [ ] Remover do novo caminho inferências por nome, positividade universal e retorno verdadeiro para operador desconhecido.
- [ ] Preservar caminho formal; aliases/Psets alternativos só entram como evidência complementar de candidato.
- [ ] Registrar qualquer forma reconhecida sem suporte e testar que não vira conforme.

**Aceite:** um campo com valor válido apenas por segunda alternativa passa quando permitido; um limite violado falha; datatype/unidade incompatíveis não são corrigidos implicitamente. Relação não suportada não retorna verdadeiro por ser tratada em outro módulo.

<a id="m2-t08"></a>

### M2-08 — Implementar aplicabilidade e cardinalidade explícitas

**Dependências:** M2-04/M2-06/M2-07.
**Arquivos:** criar `src/validation/applicability.py`, `tests/validation_core/test_applicability.py`, `test_cardinality.py`.
**Consome:** especificação completa, capacidades e sessão IFC.
**Produz:** `ApplicabilityResult`, resultado de cardinalidade e escopos de avaliação.

- [ ] Criar fixtures com população obrigatória vazia, opcional vazia, proibida presente e filtros combinados.
- [ ] Implementar seleção conforme semântica do motor/bundle, conservando contagem e referências.
- [ ] Bloquear avaliação formal da especificação quando aplicabilidade não puder ser determinada.
- [ ] Testar required/optional/prohibited por faceta, inclusive valor presente inválido.
- [ ] Registrar cardinalidade como resultado de especificação, mesmo sem ElementRef.

**Aceite:** vazio conhecido e população indeterminada são distinguíveis na API e relatório. Nenhum teste considera ausência de issues como aprovação. Casos de outras especificações independentes continuam quando há suporte parcial.

<a id="m2-t09"></a>

### M2-09 — Preservar evidência de propriedades, tipo/ocorrência, unidades e Qto

**Dependências:** M2-05; alinhamento com M2-07 e contrato de observação do módulo 1.
**Arquivos:** criar `src/ifc_analyzer/observations.py`, `units.py`; adaptar `universal_extractor.py` e `extractors/quantity_extractor.py` por novo percurso; criar `tests/validation_core/test_observations.py`, `test_units_and_qto.py`.
**Consome:** ElementRef e consulta de faceta.
**Produz:** EvidenceObservation com origem e transformação, sem criação de propriedade.

- [ ] Escrever casos de ocorrência/tipo conflitantes, Pset duplicado e unidade explícita/projeto.
- [ ] Ler portadores separadamente antes de calcular valor efetivo e registrar a regra de herança utilizada.
- [ ] Implementar normalização dimensional rastreável; unidade desconhecida permanece desconhecida.
- [ ] Separar Qto declarado, cálculo e estimativa; não satisfazer presença formal usando bounding box.
- [ ] Testar zero/falso, string numérica, dimensão incompatível, quantidade líquida/bruta e geometria rotacionada.

**Aceite:** cada valor comparado aponta para portador e unidade original; dados conflitantes não são sobrescritos por merge de dicts. Campo legado com sufixo `_m` não prova conversão para metros.

<a id="m2-t10"></a>

### M2-10 — Ler materiais, composição, relações e geometria com limites

**Dependências:** M2-05/M2-09.
**Arquivos:** adaptar `src/ifc_analyzer/material_reader.py`; criar `geometry_evidence.py`, `tests/validation_core/test_material_provenance.py`, `test_relation_traversal.py`, `test_geometry_capabilities.py`.
**Consome:** sessão IFC, ElementRef, política de recursos.
**Produz:** observações de associações/composição e capacidades geométricas independentes.

- [ ] Criar casos de material simples, layers, profiles, constituents, tipo e partes heterogêneas.
- [ ] Preservar associações, ordem/identidade e unidades sem casar listas arbitrariamente.
- [ ] Tratar ciclo/profundidade/quantidade de nós com estado explícito; não reiniciar limite por fallback.
- [ ] Separar ausência de geometria, falha de representação e cálculo não suportado.
- [ ] Testar que erro geométrico não bloqueia propriedade independente e que parte inicial não representa o todo.

**Aceite:** nenhuma espessura ausente vira zero conhecido; largura de janela não é espessura. Traversal não entra em loop e não oculta interrupção de busca. Representação derivada conserva revisão/ElementRef e opções.

<a id="m2-t11"></a>

### M2-11 — Agregar e persistir diagnóstico completo

**Dependências:** M2-02/M2-07/M2-08; evidências de M2-09/M2-10 conforme capacidade.
**Arquivos:** criar `src/validation/aggregation.py`, `diagnostic_store.py`, `tests/validation_core/test_result_aggregation.py`, `test_diagnostic_store.py`.
**Consome:** ResultSink com resultados de requisito/cardinalidade/problemas.
**Produz:** DiagnosticSnapshot consultável com cobertura e estado terminal.

- [ ] Escrever testes com conformes, não conformes, não aplicáveis, não verificados e erros na mesma execução.
- [ ] Persistir resultados por identidade completa, preservando dois requisitos sobre o mesmo campo.
- [ ] Implementar agregação da seção 6.6 e denominadores por escopo.
- [ ] Gravar em transações/lotes idempotentes; não publicar snapshot completo antes de finalizar.
- [ ] Reabrir resultado após reinício e comparar contagens/IDs com os eventos persistidos.

**Aceite:** snapshot inclui sucessos e omissões; estado `completed` não implica conformidade. Falha parcial/cancelamento não produz resumo integralmente aprovado. Persistência não depende da sessão da UI.

<a id="m2-t12"></a>

### M2-12 — Integrar percurso diagnóstico e unificar revalidação

**Dependências:** M2-06/M2-11.
**Arquivos:** criar `src/validation/analysis_service.py`, `complementary.py`; adaptar fronteiras em `src/pipeline.py`, `src/validation/post_validator.py`, `src/foundation/adapters.py`; criar `tests/validation_core/test_analysis_service.py`, `test_post_validation_boundary.py`.
**Consome:** AnalysisRequest e serviços de leitura/motor/store.
**Produz:** AnalysisService e adaptador de revalidação com os mesmos resultados formais.

- [ ] Testar diagnóstico com construtores Ollama/bSDD configurados para falhar se forem chamados.
- [ ] Isolar leitura/validação da geração de sugestões e de todas as ações de escrita.
- [ ] Propagar erro de integração IDS ao resultado; não capturar e continuar como carregamento bem-sucedido.
- [ ] Separar checks complementares de IDS e preservar identidade/versionamento de cada regra.
- [ ] Adaptar pós-validação para schema indisponível/erro como não verificado/erro, sem booleanos aprovados por default.

**Aceite:** diagnóstico/exportação não exigem LLM, catálogo completo ou sugestões. Pós-validação consome o mesmo motor e não esconde falha técnica. Política de escrita/publicação IFC e correções B03–B05 permanecem fora desta tarefa.

<a id="m2-t13"></a>

### M2-13 — Implementar progresso, cancelamento e limites de execução

**Dependências:** M2-11/M2-12; topologia/política de recursos com frente 6.
**Arquivos:** criar `src/validation/analysis_worker.py`, `tests/validation_core/test_worker_lifecycle.py`, `test_resource_limits.py`.
**Consome:** AnalysisRequest, ExecutionControl e ResultSink.
**Produz:** execução isolada, eventos/progresso e estados terminais confiáveis.

- [ ] Testar cancelamento antes de parsing, entre lotes e durante operação nativa simulada.
- [ ] Implementar worker/coordenador com identidade por execução e sem compartilhamento de handle gravável.
- [ ] Persistir unidades concluídas e motivo do restante não verificado.
- [ ] Aplicar limites explícitos de bytes/tempo/memória/profundidade conforme política calibrada.
- [ ] Testar que encerramento afeta só o worker correspondente e que outro projeto permanece intacto.

**Aceite:** UI/coordenador permanecem responsivos; resultado parcial pode ser consultado/exportado como parcial; reinício não transforma processo morto em execução concluída. Não há consumo ilimitado por ausência de configuração.

<a id="m2-t14"></a>

### M2-14 — Exportar o mesmo diagnóstico com fidelidade

**Dependências:** M2-11/M2-12; formatos iniciais refinados com frentes 4/5.
**Arquivos:** criar `src/validation/diagnostic_export.py`, `tests/validation_core/test_diagnostic_export.py`, `docs/nucleo-ifc-ids/formato-diagnostico.md`.
**Consome:** DiagnosticSnapshot/Query e ExportRequest.
**Produz:** ExportReceipt, JSON versionado e projeções aprovadas.

- [ ] Definir schema JSON e manifesto que preservem identidades, estados, cobertura e origem.
- [ ] Testar relatório completo versus filtrado, incluindo zero aplicáveis e resultado parcial.
- [ ] Implementar exportadores sem reexecutar o motor; CSV/HTML somente após validar critérios da seção 10.
- [ ] Escapar HTML e proteger CSV contra fórmulas, conservando valor canônico.
- [ ] Testar falha de escrita/cancelamento de exportação sem corromper snapshot ou fonte.

**Aceite:** totais/IDs batem com a plataforma; relatório informa versão/verificador/limitações/filtros. Nenhum download público ou chamada LLM é necessário. BCF recebe contrato de dados, sem duplicação de motor nem promessa de receptor ainda não testado.

<a id="m2-t15"></a>

### M2-15 — Integrar catálogo e navegação por elemento/requisito

**Dependências:** M2-11/M2-12/M2-14; contratos M1-06/M1-11/M1-12 do plano 1.
**Arquivos:** adaptar consumidores em `src/ui/` e `src/foundation/` sem escolher nova stack; criar `tests/validation_core/test_catalog_boundary.py`, `test_diagnostic_queries.py` e roteiro de aceite da UI.
**Consome:** DiagnosticQuery, ElementRef e ResolutionResult do catálogo.
**Produz:** consultas/visões consistentes com versão de análise e mapeamento separado.

- [ ] Testar requisito suportado desconhecido no catálogo, com catálogo ausente e com pacote inválido.
- [ ] Expor esperado/encontrado/origem, cinco estados, categorias e cobertura.
- [ ] Implementar consulta por elemento e por requisito/especificação, mantendo casos sem elementos.
- [ ] Distinguir filtro/paginação de escopo avaliado/exportado.
- [ ] Verificar que seleção por GUID ambíguo exige ElementRef e que atualização de catálogo cria nova análise.

**Aceite:** usuário consegue explicar um resultado a partir de suas fontes; cadastro não muda requisito. Diagnóstico básico funciona sem catálogo/LLM. Viewer federado não é implementado nesta fatia.

<a id="m2-t16"></a>

### M2-16 — Publicar matriz de suporte e ensaiar schemas/corpus

**Dependências:** M2-07–M2-12 e capacidade de ambiente; caso IFC4.3 a obter.
**Arquivos:** criar `docs/nucleo-ifc-ids/matriz-suporte.md`, `tests/validation_core/test_schema_matrix.py`, `test_official_corpus.py`, `test_real_cases.py`.
**Consome:** casos, backend fixado e manifesto de capacidades.
**Produz:** matriz com evidência por combinação, limitações e condição experimental.

- [ ] Incorporar casos oficiais permitidos da versão fixada, preservando origem/licença/esperado.
- [ ] Rodar positivos/negativos por faceta/schema/restrição, incluindo vazio, erro e não suporte.
- [ ] Ensaiar casa/prédio sem alterar fontes e obter caso real de arquitetura/estrutura IFC4.3.
- [ ] Comparar resultados esperados com revisão especializada; investigar divergências de motor sem “votação” automática.
- [ ] Medir tempo/memória por etapa/hardware e registrar nova condição quando semântica mudar.

**Aceite:** nenhuma célula é anunciada suportada só por leitura; falta do caso IFC4.3 real é limitação explícita. Corpus duplicado não infla métricas. Testes de dados, geometria e escrita futura permanecem separados.

<a id="m2-t17"></a>

### M2-17 — Ensaiar isolamento, segurança, recuperação e ausência de mutação

**Dependências:** M2-03/M2-10/M2-13/M2-14/M2-15.
**Arquivos:** criar `tests/validation_core/test_security_boundary.py`, `test_recovery.py`, `test_read_only_invariant.py`, `docs/nucleo-ifc-ids/operacao.md`.
**Consome:** serviço completo e política de ambiente.
**Produz:** evidência de segurança/recuperação e limitações operacionais.

- [ ] Executar casos de XML hostil, arquivo malformado, limites e conteúdo de fonte com markup/instruções.
- [ ] Bloquear rede em teste e detectar qualquer tentativa, inclusive resolução de schemas/URIs e assets de relatório.
- [ ] Simular interrupção/transação incompleta e restauração em ambiente isolado.
- [ ] Conferir hashes das fontes e ausência de operações de mutação no grafo IFC de fixtures.
- [ ] Verificar isolamento por projeto e que logs gerais não vazam payload/caminhos privados.

**Aceite:** não há falso positivo de conformidade em falha, original alterado ou resultado acessível sem autorização. Recuperação mantém identidade, cobertura e eventos, sem renomear análise parcial como completa.

<a id="m2-t18"></a>

### M2-18 — Consolidar fatias, revisão e entrega operacional

**Dependências:** tarefas necessárias à fatia; conclusão integral exige critérios da seção 15.
**Arquivos:** documentação/matriz/release notes e testes da implementação futura; atualizar índices somente com estado real.
**Consome:** evidências de testes, cobertura, riscos e contratos.
**Produz:** PR revisável e demonstração da entrega autorizada.

- [ ] Executar checks pertinentes às mudanças e resolver falhas, sem atualizar esperados para encobrir regressão.
- [ ] Demonstrar os percursos da seção 11, inclusive diagnóstico sem LLM e cancelamento.
- [ ] Conferir integridade, licenças, condições científicas e pendências por schema/faceta.
- [ ] Preparar PR com problema/comportamento, validação, limitações e impacto nos consumidores.
- [ ] Definir destino do PR e obter revisões técnica/de domínio conforme processo acordado; nenhum merge automático.

**Aceite:** comportamento anunciado corresponde ao que foi testado, e o relatório é utilizável sem geração de sugestões. O módulo 3 continua com plano/implementação próprios; concluir o núcleo não autoriza expansão automática.

### 12.1 Ordem e dependências sem bloquear trabalho independente

Caminho inicial: M2-01 → M2-02 → M2-03/M2-05 → M2-04 → M2-06 → M2-07/M2-08 → M2-11 → M2-12 → M2-14.

M2-09/M2-10 aprofundam proveniência/capacidades e alimentam M2-11/M2-16. M2-13 depende de ciclo de vida/persistência; M2-15 integra consumidores depois do contrato estabilizado. M2-16/M2-17 fecham suporte e operação antes de M2-18.

Obtenção de caso IFC4.3, revisão de domínio e topologia institucional podem ocorrer em paralelo à implementação inicial por pessoas designadas; isso não autoriza agentes paralelos nem muda responsáveis confirmados. Não esperar o catálogo completo para provar validação de uma propriedade desconhecida.

<a id="m2-testes"></a>

## 13. Corpus e estratégia de verificação

### 13.1 Casos mínimos com esperado explícito

| ID proposto | Fixture | Resultado essencial |
|---|---|---|
| C01 | IFC/IDS válidos, propriedade exata satisfatória | Conforme com evidência e fontes identificadas |
| C02 | Propriedade obrigatória ausente | Não conforme; nenhuma propriedade criada |
| C03 | Propriedade desconhecida do catálogo, valor válido | Conforme IDS + unmapped semântico |
| C04 | Enumeração de três alternativas, valor na segunda | Conforme quando permitido; parser preserva as três |
| C05 | Valor fora da enumeração/limite | Não conforme com restrição completa |
| C06 | Optional ausente/presente inválido, por faceta permitida | Interpretação conforme bundle, não um único teste de existência |
| C07 | Prohibited com valor/associação presente | Falha segundo a faceta/versionamento |
| C08 | População obrigatória vazia | Resultado de cardinalidade não conforme sem elemento fictício |
| C09 | População vazia admitida | Ausência explícita e cardinalidade avaliada; nenhum selo derivado de lista vazia |
| C10 | Aplicabilidade válida mas não suportada | População indeterminada e requisitos não verificados |
| C11 | Um requisito não suportado, outro suportado | Resultado parcial com o segundo avaliado e cobertura correta |
| C12 | Mesmo campo em duas especificações | Duas avaliações e dois IDs; sem deduplicação indevida |
| C13 | Valor em Pset alternativo/alias | Caminho formal continua fiel; candidato de evidência separado |
| C14 | GUID duplicado/nulo/inválido | Entidades preservadas por localizador e problema técnico |
| C15 | Ocorrência/tipo com conflito | Proveniência de ambos e regra efetiva explícita |
| C16 | Unidades mm/m, explícita/projeto e incompatível | Conversão rastreável quando válida; incompatibilidade/ausência explicitada |
| C17 | Zero, falso, vazio, nulo e código `"1"` | Estados/tipos distintos, sem coerção indevida |
| C18 | Material layers/profiles/constituents e partes heterogêneas | Associações preservadas; primeiro material não representa o todo |
| C19 | Relações recursivas/ciclo/profundidade excedida | Resultado ou limitação rastreável, sem loop/retorno positivo default |
| C20 | Sem geometria ou representação não suportada | Dados independentes continuam; capacidade geométrica indisponível |
| C21 | Bounding box versus volume/área líquidos | Estimativa não satisfaz presença de Qto nem se passa por quantidade líquida |
| C22 | XML malformado, DTD/entidade externa, schemaLocation remoto | Bloqueio seguro sem leitura externa |
| C23 | Bundle ausente/corrompido e motor lança exceção | Erro/não verificado; nunca pass pela lista vazia |
| C24 | Cancelamento antes/durante avaliação | Parcial/cancelada com cobertura e restante não verificado |
| C25 | Fonte muda durante ingestão | Sem mistura de revisões; execução não usa bytes instáveis |
| C26 | Mesmo caminho/tamanho/mtime com conteúdo distinto | Hash invalida identidade/cache |
| C27 | Nova versão de verificador/catálogo | Nova análise e histórico anterior intacto |
| C28 | Exportação completa/filtrada/parcial com texto hostil | Identidade/contagens corretas e apresentação segura |
| C29 | Rede/LLM indisponíveis | Diagnóstico/exportação independentes funcionam ou mostram falha local real |
| C30 | Reinício, transação incompleta e restauração | Estado consistente e nenhuma promoção indevida a concluído |
| C31 | IFC4.3 real + fixtures de arquitetura/estrutura | Capacidades verificadas separadamente; limitações publicadas |
| C32 | Duas sessões/projetos | Sem mistura de fontes, resultados, cancelamento ou acesso |

Fixtures ruins não precisam simular todo um projeto. Cada uma isola um risco; modelos reais verificam integração e não substituem negativos. Casos sem esperado independente não entram como evidência de correção, embora sirvam para medir desempenho.

### 13.2 Exemplos de testes de contrato a implementar

Os trechos abaixo são **esboços de testes futuros**, apoiados no helper `run_case` definido em M2-01 e ligado ao serviço em M2-12. `DiagnosticSnapshot` deverá expor `results`, `specifications`, `coverage` e `integrity` como DTOs/visões tipadas correspondentes às seções 4/10. São exemplos de comportamento, não arquivos de teste criados nesta entrega.

```python
def test_second_enumeration_value_is_preserved_and_evaluated(run_case):
    snapshot = run_case("C04")
    result = snapshot.results[0]
    assert result.expected.constraint.allowed_values == ["A", "B", "C"]
    assert result.observations[0].typed_value.value == "B"
    assert result.state == "compliant"


def test_unsupported_applicability_is_not_an_empty_success(run_case):
    snapshot = run_case("C10")
    spec = snapshot.specifications[0]
    assert spec.applicability.population_state == "indeterminate"
    assert spec.applicability.count is None
    assert spec.state == "not_verified"
    assert snapshot.coverage.complete is False


def test_two_requirements_on_same_field_remain_distinct(run_case):
    snapshot = run_case("C12")
    assert len(snapshot.results) == 2
    assert len({item.requirement_id for item in snapshot.results}) == 2


def test_diagnosis_does_not_mutate_ifc(run_case):
    snapshot = run_case("C02")
    assert snapshot.results[0].state == "non_compliant"
    assert snapshot.integrity.source_sha256_before == snapshot.integrity.source_sha256_after
    assert snapshot.integrity.fixture_mutation_calls == []
```

O helper de teste pode instrumentar chamadas de mutação e o grafo da fixture. `fixture_mutation_calls` é evidência de ensaio, não campo obrigatório do relatório de produção nem prova suficiente isolada.

### 13.3 Testes existentes pertinentes

Reavaliar seleção após M2-01. Arquivos observados:

- `tests/test_translator.py`, `tests/test_ids_xsd.py`, `tests/test_ids_context.py`;
- `tests/test_analyzer.py`, `tests/test_extractors.py`, `tests/test_quantity_extractor.py`;
- `tests/test_material_constituent_set.py`, `tests/test_ifc_registry.py`;
- `tests/test_post_validator.py`, `tests/test_pipeline.py`, `tests/test_mcp_pipeline.py`;
- `tests/foundation/test_contracts.py`, `tests/experiment/test_execution_identity.py`;
- `tests/test_prompt_contract_unificado.py` e verificações de pinos quando interfaces experimentais forem afetadas.

Um teste legado que espera comportamento permissivo é evidência do comportamento antigo; não é justificativa para mantê-lo no novo núcleo. Preservar condição histórica e criar esperados novos com fundamento independente. Testes do enriquecimento/escrita só entram quando a adaptação toca essas fronteiras, sem expandir implementação.

### 13.4 Comandos futuros e critérios

Depois de criar testes e validar ambiente, executar conjuntos pertinentes, por exemplo:

```powershell
python -m pytest tests/validation_core/test_identity.py tests/validation_core/test_source_gate.py
python -m pytest tests/validation_core/test_schema_bundle.py tests/validation_core/test_xml_security.py
python -m pytest tests/validation_core/test_ids_document.py tests/validation_core/test_cardinality.py
python -m pytest tests/validation_core/test_result_aggregation.py tests/validation_core/test_analysis_service.py
python -m pytest tests/validation_core/test_read_only_invariant.py tests/validation_core/test_diagnostic_export.py
```

Esses comandos não foram executados nesta elaboração. Verificar marcadores e dependências antes de rodar suítes legadas; não chamar rede/Ollama implicitamente. A convenção do repositório pede cobertura mínima de 80% em core; esse número não substitui casos de falso positivo, cardinalidade e falha técnica. Medir cobertura de capacidade e qualidade dos resultados, além de cobertura de linhas.

Alegar conformidade IDS exige escopo/versão/capacidades e evidência. Passar XSD, abrir IFC ou passar testes próprios não é certificação externa da buildingSMART. Não usar esse termo no produto sem processo pertinente.

<a id="m2-entregas"></a>

## 14. Entregas, primeiro ciclo vertical e esforço

### 14.1 Primeiro ciclo vertical verificável

**Objetivo do primeiro ciclo:** receber uma fixture IFC e IDS oficiais/compatíveis com um requisito simples, preservar fontes, registrar identidade, verificar XML/XSD, avaliar presença/valor por backend aprovado e exportar diagnóstico JSON com estados e origem.

A fatia inclui os mínimos de M2-01–M2-08/M2-11/M2-12/M2-14, com cobertura estreita e explicitamente declarada. Deve demonstrar caso conforme, campo ausente, propriedade desconhecida no catálogo, população vazia e motor/schema indisponível. Usar serviço/teste de integração antes de UI completa; resultado deve ser revisável por pessoa.

Não entregar somente interfaces vazias, parser sem avaliação ou tela com dados simulados como se fossem diagnóstico real. A integração vertical estreita permite validar decisões de backend/identidade antes de investir em todas as facetas e schemas.

### 14.2 Fatias e branches propostas

Branch de integração indicada: `feat/semantic-foundation`. Nomes abaixo são propostas futuras; destino final dos PRs continua pendente. Nenhuma branch/PR foi criada nesta etapa.

| Entrega | Conteúdo | Evidência de conclusão | Branch proposta |
|---|---|---|---|
| E2-1 — Diagnóstico mínimo rastreável | Primeiro ciclo vertical | Fontes intactas, casos positivo/negativo/vazio/erro e JSON sem LLM | `feat/ifc-ids-readonly-core` |
| E2-2 — Semântica e proveniência | M2-07–M2-10 ampliados | Facetas/restrições, tipo/ocorrência, unidade/material/relações com casos negativos | `feat/ifc-ids-evidence-semantics` |
| E2-3 — Resultado completo e operação parcial | M2-11–M2-14 | Persistência, cancelamento, recuperação e exportação consistente | `feat/ifc-ids-diagnostic-lifecycle` |
| E2-4 — Plataforma e contratos | M2-15 e fronteiras com 1/4/5/7 | Visões por elemento/requisito, unmapped independente e BCF com contrato de entrada | `feat/ifc-ids-diagnostic-integration` |
| E2-5 — Compatibilidade e aceite | M2-16–M2-18 | Matriz real por capacidade, corpus, offline e limites operacionais | `feat/ifc-ids-compatibility-acceptance` |

Revisão técnica verifica contratos, parsing, identidade e falhas; Felipe/especialista verifica semântica BIM/IDS e esperados; frentes 6/7 revisam operação/condição quando afetadas. PR descreve capacidades efetivas e pendências, sem anunciar suporte universal a uma versão IFC.

### 14.3 Estimativa relativa com premissas

Não há prazo acadêmico, horas semanais, hardware ou disponibilidade de revisores confirmados. As faixas abaixo são **hipóteses de esforço**, não datas acordadas, e serão recalibradas após M2-06/E2-1. Incluem desenvolvimento/testes/revisão usuais; excluem espera externa por fontes/caso IFC4.3, aquisição institucional, mudança de escopo e viewer federado.

| Onda | Escopo | Engenharia | Revisão BIM/IDS |
|---|---|---:|---:|
| O0 | Baseline, corpus e contratos | 16–24 h | 8–12 h |
| O1 | Ingestão, identidade e XML/bundle | 24–40 h | 4–8 h |
| O2 | AST, backend e ciclo vertical | 48–80 h | 8–16 h |
| O3 | Facetas, cardinalidade e evidências IFC | 48–80 h | 12–24 h |
| O4 | Agregação, persistência e serviço | 40–64 h | 8–16 h |
| O5 | Cancelamento, exportação e interface | 32–56 h | 8–16 h |
| O6 | Matriz, corpus real e segurança/recuperação | 48–80 h | 16–32 h |
| O7 | Revisão final e entrega | 24–40 h | 4–8 h |

Total indicativo: **280–464 horas de engenharia e 68–132 horas de revisão BIM/IDS**. Trabalho compartilhado de identidade/persistência/integração com o módulo 1 deve ser contabilizado uma vez; não somar mecanicamente os dois planos. Implementar um motor IDS próprio amplo, se necessário após o ensaio, exige reestimativa específica e não está absorvido silenciosamente nessas faixas.

Com capacidades hipotéticas de 20 h/semana de engenharia e 8 h/semana de revisão, os pisos aritméticos seriam 14–23,2 e 8,5–16,5 semanas; dependências e espera podem aumentar o calendário. Não são previsão nem compromisso. Para planejar datas, confirmar capacidade, marco acadêmico, responsável e recorte da primeira entrega.

Se o prazo exigir redução, priorizar E2-1 com suporte estreito declarado, preservando diagnóstico independente, ausência de mutação e estados seguros. Não reduzir testes de falso positivo ou ocultar não suporte para cumprir calendário.

### 14.4 Extra federado e backlog futuro

Manter fora da prioridade inicial:

- visualização conjunta de IFCs por disciplina, alinhamento espacial e gestão de transformações;
- associação de vários IDSs a modelos/disciplinas e regras de seleção por escopo;
- comparação entre revisões com correspondência de elementos, além de IDs locais;
- formatos adicionais de relatório e receptores BCF;
- IFCZIP/formatos adicionais após necessidade e segurança ensaiadas;
- novas facetas/portadores/combinações fora do manifesto inicial;
- processamento distribuído/multiusuário institucional após decisão da frente 6;
- autoria IDS futura das frentes 1/2/4;
- enriquecimento e escrita posteriores, com revisão humana e revalidação.

O modelo de identidade deve permitir evolução sem fundir arquivos. Uma seleção visual federada precisa encaminhar cada decisão/saída ao arquivo de origem. Nada nesse backlog autoriza implementar o módulo 3 ou viewer neste turno.

<a id="m2-aceite"></a>

## 15. Riscos, decisões abertas e prontidão

### 15.1 Registro de riscos

| Risco | Impacto | Mitigação/tarefa |
|---|---|---|
| Placeholder aceito como schema oficial | Falsa validação de IDS | Bundle autêntico, hash e negativos; M2-03 |
| Perda de enumerações/cardinalidade | Falsos positivos/negativos | AST sem perda e corpus; M2-04/M2-07/M2-08 |
| Backend escolhido sem evidência | Cobertura/promessas indevidas | Ensaio versionado por capacidade; M2-06/M2-16 |
| Identidade só por GUID | Entidades/decisões colapsadas | ElementRef por revisão/localizador e índice multivalorado; M2-02/M2-05 |
| Aplicabilidade desconhecida tratada como vazia | Aprovação indevida | População indeterminada explícita; M2-08/M2-11 |
| Alias/Pset alternativo aceito formalmente | Requisito diferente do fornecido | Caminho formal preservado; M2-07/M2-15 |
| Herança/unidades achatadas | Comparação com valor/origem errados | Observações separadas e conversão rastreável; M2-09 |
| Primeiro material/parte usado como todo | Evidência enganosa | Composição e conflitos; M2-10 |
| Geometria aproximada usada como Qto | Falsa presença/quantidade | Origem/método separados; M2-09/M2-10 |
| Pós-validação permissiva | Falha técnica apresentada como aprovação | Mesmo motor e estados explícitos; M2-12 |
| Recursos nativos não interrompíveis | UI travada/consumo excessivo | Worker isolado, limites e cancelamento; M2-13 |
| Exportação recalcula ou filtra silenciosamente | Relatório diverge da plataforma | Snapshot canônico/filtros declarados; M2-14 |
| Fonte/relatório com conteúdo hostil | Acesso externo, execução ou vazamento | Parser fechado, escaping, isolamento/logs; M2-03/M2-17 |
| Caso IFC4.3 real ausente | Generalização indevida | Obter caso e manter limitação explícita; M2-16 |
| Mudança no verificador sem nova condição | Comparação científica inválida | Identidade/versionamento e histórico; M2-02/M2-16 |
| Duplicação de trabalho entre planos | Custo/contratos divergentes | Contratos comuns e revisão conjunta com módulo 1 |
| Falta de revisor/capacidade semanal | Atraso de semântica/aceite | Definir disponibilidade e recalibrar após E2-1 |

### 15.2 Decisões necessárias no momento pertinente

1. Responsável de implementação e revisor BIM/IDS; Nonato não foi designado principal da frente 2.
2. Versões exatas do backend, bibliotecas, bundle IDS e releases IFC após ensaios, incluindo IFC4.3.
3. Subconjunto inicial de capacidades que compõe E2-1 e sequência de expansão da matriz.
4. Local/topologia de execução, armazenamento, autenticação, retenção e limites calibrados com frente 6.
5. Formatos iniciais de relatório, política de exportação filtrada e requisitos de tamanho/desempenho.
6. Fornecedor/autorização e adequação do caso real IFC4.3 de arquitetura/estrutura.
7. Gabarito independente, tratamento de divergências entre motores e condição científica nova.
8. Destino dos PRs, disponibilidade semanal e prazo acadêmico.
9. Detalhes do extra federado, associação de vários IDSs e alinhamento espacial, em etapa posterior.
10. Política de publicação IFC parcial/revalidação de regressões da frente 5; não altera o caráter somente leitura do módulo 2.

Esses itens não reabrem decisões confirmadas. A implementação inicial pode avançar com fixtures e contrato estreito após autorização, mas não pode alegar resolvidas versões/capacidades ou implantação ainda não ensaiadas.

### 15.3 Pronto para iniciar a primeira fatia

- [ ] Escopo deste plano revisado e implementação autorizada separadamente.
- [ ] Baseline/local changes protegidos e destino de trabalho acordado.
- [ ] Corpus mínimo com esperados independentes e fonte/licença conhecida.
- [ ] Contrato de identidade alinhado ao módulo 1, sem perder origem de arquivo.
- [ ] Processo de aquisição/fixação do bundle oficial definido.
- [ ] Responsável técnico e revisor de domínio disponíveis.

### 15.4 Pronto para anunciar uma capacidade

- [ ] Combinação schema/release + IDS + backend + faceta/operador/portador identificada.
- [ ] Positivos, negativos, ausência, erro e cardinalidade pertinentes testados.
- [ ] Evidência de tipo/ocorrência/unidade/material preservada quando pertinente.
- [ ] Não suporte e limitação conhecidos publicados, com razão.
- [ ] Versões/hashes e condição reproduzíveis; nenhum “pass” por falha de execução.
- [ ] Caso real usado para generalização, além de fixtures sintéticas, quando o anúncio o exigir.

### 15.5 Pronto para concluir o módulo no escopo inicial

- [ ] Entrada individual IFC+IDS gera diagnóstico completo/rastreável sem LLM.
- [ ] Fontes e grafo IFC permanecem sem mutação; derivados são separados.
- [ ] XML/XSD autêntico/offline e interpretação IDS preservam facetas/restrições/cardinalidades.
- [ ] Estados/categorias, população vazia/indeterminada e cobertura parcial são inequívocos.
- [ ] Identidade suporta GUID duplicado/nulo e futuras fontes múltiplas sem colisão.
- [ ] Interfaces com 1/3/4/5/6/7 estão demonstradas; catálogo desconhecido não bloqueia requisito suportado.
- [ ] Visões por elemento/requisito e exportações usam o mesmo diagnóstico.
- [ ] Cancelamento, recursos, falhas e recuperação foram ensaiados.
- [ ] Matriz IFC2X3/IFC4/IFC4.3 informa exatamente o testado e as lacunas.
- [ ] Prompt v7.8, GTs, comparadores, dados/resultados e planos congelados preservados.
- [ ] Formatos, operação e riscos residuais documentados; nenhuma certificação externa presumida.
- [ ] Revisão técnica/de domínio concluída para a fatia e PR preparado conforme processo acordado.

<a id="m2-fontes"></a>

## 16. Fontes consultadas, limites e evidência desta entrega

| Fonte | Versão/contexto | Uso e limite |
|---|---|---|
| [Consolidação preservada](CONSOLIDACAO-2026-10-09.md) | 09/10/2026 | B01/B02/B07/B08 e dependências; leitura estática não é reprodução funcional |
| [Decisões posteriores](README.md#decisoes-posteriores-de-0910) | D01–D19 | Escopo confirmado, estados, identidade, schemas, extra federado e diagnóstico independente |
| [Plano do módulo 1](modulo-01-dominio-catalogo.md) | Plano concluído em 09/10 | Contratos de catálogo/observação/identidade preservados; documento não reescrito |
| [Condição v7.8](../condicao-v7-8-2026-08-19.md) | Instrumento histórico | Preservar pinos e condição; novo verificador não reinterpreta resultados silenciosamente |
| [Releases oficiais IDS](https://github.com/buildingSMART/IDS/releases) | Release v1.0.0 e IFC4X3_ADD2 | Alvo proposto do bundle; bytes do XSD oficial não foram incorporados nesta tarefa |
| [Manual de especificações IDS](https://github.com/buildingSMART/IDS/blob/development/Documentation/UserManual/specifications.md) | Branch development, consultada em 09/10/2026 | Estrutura/facetas; fixar documentação/corpus compatíveis com release antes de implementar |
| [Faceta property](https://github.com/buildingSMART/IDS/blob/development/Documentation/UserManual/property-facet.md) | Branch development | Propriedades/quantidades e parâmetros; não certifica todas as formas no backend |
| [Faceta material](https://github.com/buildingSMART/IDS/blob/development/Documentation/UserManual/material-facet.md) | Branch development | Associações e papel de metadados; testar versão/schema efetivos |
| [Faceta partOf](https://github.com/buildingSMART/IDS/blob/development/Documentation/UserManual/partof-facet.md) | Branch development | Relações/traversal; não substituir por heurística de “qualquer relação” |
| [IDS Audit Tool](https://github.com/buildingSMART/IDS-Audit-tool) | Repositório oficial consultado; versão de uso não fixada | Referência para auditoria/corpus; não executado nem instalado |
| [IfcTester](https://docs.ifcopenshell.org/ifctester.html) | Documentação consultada identifica 0.9.0 | Candidato de backend, não prova de versão instalada/compatibilidade |
| [IfcOpenShell validate](https://docs.ifcopenshell.org/autoapi/ifcopenshell/validate/index.html) | Documentação consultada identifica 0.9.0 | Limites da validação pós-parsing e opções; ensaiar a versão adotada |
| [lxml parsing](https://lxml.de/5.4/parsing.html) | Documentação 5.4 | Opções de parser; configurar explicitamente e verificar versão efetiva |

As páginas em development podem evoluir e não substituem uma release fixada. As citações sustentam o desenho e os riscos; não conferem certificação normativa ao produto. Licenças de schemas, ferramentas, corpus e modelos precisam ser verificadas por componente antes de redistribuição. Não deduzir direitos sobre IFC de projeto a partir da licença do software.

**Verificação desta entrega documental:** releitura do documento salvo, coerência de decisões/contratos, JSON ilustrativo, referências locais/âncoras, escopo de alterações e hashes protegidos. Nenhum teste funcional listado foi executado, nenhum arquivo IFC/IDS foi reparado, nenhum backend foi instalado e nenhum resultado científico foi recalculado.

**Lacunas explícitas:** caso real IFC4.3, versões efetivas e bundle oficial fixados por ensaio, responsável/revisor e disponibilidade, infraestrutura/limites, formatos finais e destino de PR. São insumos da implementação planejada, sem bloqueio para entregar este documento completo.

<a id="m2-bibliografia"></a>

## 17. Integração bibliográfica de 10/10/2026 — diagnóstico IFC/IDS

A [síntese curada dos 29 artigos](../pesquisa/sintese-bibliografica-daiane-29-artigos.md) fundamenta esta **nova atualização documental dos três planos**. Selecionam-se **16 estudos pertinentes ao M2**. As referências fornecem antecedentes, casos negativos e riscos; suporte por schema, release, faceta e cardinalidade continua dependendo dos ensaios planejados. Resultados em Solibri, ferramentas autorais ou extensões experimentais não certificam o backend do Copilot.

O principal efeito no desenvolvimento é tornar auditável o que foi verificado: população aplicável, requisito, dado observado, origem, capacidade disponível e resultado. Isso reforça D11/D12/D15/D19 e evita duas conclusões inválidas: tomar elemento fora da aplicabilidade como aprovado ou tomar conformidade do valor armazenado como comprovação física/geométrica. IDS fornecido, diagnóstico sem LLM e leitura sem mutação permanecem o escopo confirmado.

**Como ler a matriz:** tarefas e casos `C01–C32` são os já previstos na [seção 13](#m2-testes), não executados nesta etapa. “Base existente” indica critério já planejado; **Proposta** indica refinamento bibliográfico sujeito à revisão. A ficha vinculada contém páginas, acesso e limites de cada artigo.

| Referência | Decisão ou risco fundamentado | Tarefa e caso existentes | Critério de avaliação e efeito no desenvolvimento |
|---|---|---|---|
| [Q34-02 — Moura 2024a](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-02) | Concordância com saída do exportador pode ser circular; Qto precisa de origem/unidade | [M2-01](#m2-t01), [M2-09](#m2-t09); C16/C17 | Base existente: corpus com esperado independente e valores preservados. **Proposta:** contrastar valor autoral, Qto exportado e referência geométrica independente; declarar a pergunta avaliada sem prometer exatidão geral de quantitativos. |
| [Q34-03 — Weijh](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-03) | Objeto visível pode ter quantidade zero; painel facilita localizar problema mas não prova cobertura total | [M2-09](#m2-t09), [M2-14](#m2-t14), [M2-15](#m2-t15); C17/C28 | Base existente: zero não vira ausência e exportação conserva diagnóstico. **Proposta:** zero legítimo e zero incompatível com requisito devem permanecer distinguíveis; ganho temporal relatado de até 50% não será meta local. |
| [Q34-04 — Costa/Andrade](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-04) | Regra interpretada por humano pode envolver geometria fora do IDS padrão | [M2-06](#m2-t06), [M2-12](#m2-t12); C11/C20/C21 | Base existente: matriz de capacidade e separação entre resultado formal e alerta complementar. **Proposta:** regra geométrica não suportada deve aparecer como limitação ou checagem complementar identificada, sem certificação global/legal. |
| [Q34-06 — Souza](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-06) | Painel e paredes constituintes dão quantidades diferentes; bruto/líquido depende da seleção | [M2-09](#m2-t09), [M2-10](#m2-t10); C18/C19/C21 | Base existente: origem, relações e limites geométricos. **Proposta:** fixture de agregado/parte com vãos, evitando dupla contagem e substituição da quantidade líquida por bounding box; não reproduzir números do caso como GT local. |
| [Q34-08 — Pereira](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-08) | Função/carga/hardware mudam desempenho; 17 IFCs de piloto não são universo de 16.736 | [M2-11](#m2-t11), [M2-13](#m2-t13), [M2-16](#m2-t16); C24/C28 | Base existente: diagnóstico completo, limites/cancelamento e ensaio por capacidade. **Proposta:** relatar tamanho em bytes medidos, elementos, requisitos, etapas, memória e hardware; não converter o “Mb” ambíguo do artigo nem importar seus tempos como SLA. |
| [Q34-10 — Gaspar](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-10) | Extração de área depende da representação; complemento geométrico tem domínio limitado | [M2-10](#m2-t10), [M2-16](#m2-t16); C20/C21/C31 | Base existente: geometria indisponível não é quantidade nula. **Proposta:** ensaios independentes de perfil/vazio/rotação para operações que venham a ser suportadas; fórmula demonstrada em `IfcFooting` não aprova suporte universal ou nova família no domínio. |
| [Q34-11 — Andrade](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-11) | Erros deliberados permitem verificar regra; cobertura normativa não é acurácia | [M2-01](#m2-t01), [M2-07](#m2-t07), [M2-16](#m2-t16); C01–C11 | Base existente: corpus positivo/negativo e suporte declarado. **Proposta:** preservar esperado independente para cada erro plantado e mostrar não avaliados; não usar 60% de itens selecionados como taxa de acerto. |
| [Q310-02 — Pérez-García](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-02) | Resumo relata lacunas de propriedades em cinco casos; ausência informacional não é ausência física | [M2-11](#m2-t11), [M2-15](#m2-t15); C02/C03 | Peso limitado, **apenas resumo/metadados**. Base existente: esperado/encontrado/origem e independência do catálogo. **Proposta:** revisar linguagem de “ausente” para não afirmar desempenho físico; obter integral antes de usar amostra ou método como comparador. |
| [Q310-03 — Cerovsek/Omar](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-03) | Verificações explícitas, implícitas e não suportadas não respondem à mesma pergunta | [M2-06](#m2-t06), [M2-12](#m2-t12), [M2-16](#m2-t16); C11/C20/C23 | Base existente: suporte por versão/capacidade e erro ≠ aprovação. **Proposta:** relatório dizer se apenas leu o valor armazenado ou confrontou outra evidência; limites de ferramentas de 2024 não serão tratados como auditoria do ambiente atual. |
| [Q310-05 — Fischer](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-05) | Extensões relacionais podem excluir objetos sem relação; 10 implementados + 2 teóricos não equivalem a 12 validados | [M2-06](#m2-t06), [M2-08](#m2-t08), [M2-10](#m2-t10); C10/C11/C19 | Base existente: população indeterminada quando aplicabilidade não pode ser avaliada, suporte parcial explícito. **Proposta:** omitir relação seletora e verificar que não vira lista vazia aprovada; backend padrão não aceita extensão silenciosamente. |
| [Q310-06 — Garlet 2023](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-06) | Artigo e suplemento divergem em schema; software autoral/portador afeta exportação | [M2-03](#m2-t03), [M2-09](#m2-t09), [M2-16](#m2-t16); C15/C16/C23 | Base existente: bundle autêntico e origem tipo/ocorrência. **Proposta:** corpus pareado por exportador/schema, fórmula/unidade preservadas e instrumento legado identificado; não copiar `ids_09.xsd` como release atual ou inferir absortância ausente. |
| [Q310-07 — Bigai](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-07) | Uso, tipo e instância determinam aplicabilidade; dado perdido na exportação altera diagnóstico | [M2-08](#m2-t08), [M2-09](#m2-t09); C08/C09/C10/C15 | Base existente: cardinalidade e herança com origem. **Proposta:** retirar seletivamente parâmetro do tipo e ocorrência, contando avaliados/excluídos/indeterminados; amostra pequena do artigo não demonstra cobertura do perfil Daiane. |
| [Q310-09 — Mendonça/Ferreira](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-09) | A sem Psets e B com seletor falso ficam fora da aplicabilidade; só C/D são avaliados | [M2-08](#m2-t08), [M2-11](#m2-t11); C08/C09/C10 | Base existente: não aplicável, não verificado, conforme e não conforme distintos. **Proposta:** quatro casos inspirados no estudo, com ausente/falso/falha/passa e cardinalidade explícita; A/B nunca entram no numerador de aprovação. |
| [Q310-11 — Djukic/Caires/Lino](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-11) | IDS e scripts complementares detectam tipos diferentes de problema; contagens não são sensibilidade | [M2-06](#m2-t06), [M2-12](#m2-t12), [M2-14](#m2-t14); C11/C28/C29 | Base existente: diagnóstico unificado e sem LLM. **Proposta:** executar futuramente o baseline determinístico com evidência equivalente e esperado independente, reportando falsos positivos/negativos por mecanismo; não atribuir limite de uma UI ao padrão IDS. |
| [Q310-16 — Kremer/Beetz](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-16) | XLink/funções Python/Topologic são extensão experimental; BCF comunica achados | [M2-03](#m2-t03), [M2-06](#m2-t06), [M2-12](#m2-t12); C11/C22/C28 | Base existente: parsing seguro e complemento separado do IDS. **Proposta:** referência a função/URL desconhecida não executa código nem aprova requisito; operação local futura exige versão/teste. Exportar BCF não prova correção e não torna a extensão parte do IDS padrão. |
| [Q310-17 — Tomczak/revisão](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-17) | Dicionário não substitui verificador; método de entrega não garante verdade dos dados | [M2-07](#m2-t07), [M2-15](#m2-t15); C03/C13/C29 | Base existente: validar requisito suportado mesmo sem mapping e manter nome/Pset exatos. **Proposta:** comparação lado a lado entre significado mapeado, conformidade formal e evidência observada, sem fundir os três estados. |

**Limite de inferência e pesquisa pendente:** nenhuma dessas publicações executa o nosso backend fixado ou valida a combinação local de catálogo, IDS e LLM. Continuam pendentes os ensaios de capacidade, IFC4.3 real, corpus com referência independente, diagnóstico completo sob interrupção e estudo de esforço humano. A matriz acrescenta motivação e casos propostos, sem alterar os IDs C01–C32 ou suas expectativas existentes. O IDS continua vindo pronto; a reserva [Q310-13 — Owerko](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-13) pertence à autoria futura D06.


[Voltar ao planejamento](README.md) · [Índice documental](../README.md) · [Mapa das sete frentes](mapa-sete-frentes.md) · [Plano do módulo 1](modulo-01-dominio-catalogo.md).
