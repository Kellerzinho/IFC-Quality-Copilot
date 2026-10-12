# Arquitetura base do projeto

**Data:** 9 de outubro de 2026. Baseada na leitura consolidada do repositório e
nas decisões confirmadas; descreve organização modular, sem mudança de stack,
movimentação de código ou implementação funcional nesta etapa.

Leia a [consolidação](../planejamento/CONSOLIDACAO-2026-10-09.md), as
[decisões posteriores](../planejamento/README.md#decisoes-posteriores-de-0910) e o
[mapa das sete frentes](../planejamento/mapa-sete-frentes.md).

## Implementação observada

O Python é a base semântica existente. `QualityPipeline` orquestra diagnóstico,
integração IDS, geração progressiva de sugestões, revisão e exportação.
Streamlit apresenta issues; MCP oferece ferramentas de leitura/escrita.
Há extratores IFC, cliente/cache bSDD, Ollama, writer, auditoria, BCF e avaliação.

```text
IFC + IDS opcional no pipeline atual
  → análise e regras
  → contexto / sugestões determinísticas e LLM
  → revisão por issue na UI ou ferramentas MCP
  → aplicação em memória / auditoria / exportação
```

O fluxo é observado no código, não certificado como integralmente conforme.
Escrita e leitura compartilham o objeto IFC; auditoria/decisões não têm toda a
persistência necessária; há lacunas de pós-validação, proveniência e BCF.
O backlog B01–B10 da consolidação contém evidências e propostas de aceite.

## Evolução pretendida

**Decisão de entrada:** na primeira versão o operador fornece IDS pronto.
Autoria de IDS pela UI fica fora do escopo inicial. A validação de requisitos
suportados independe de a propriedade estar cadastrada no catálogo. Ausência
de mapeamento semântico deve ser explícita, sem preenchimento automático por
equivalência inventada.

**Prosseguimento parcial confirmado em 09/10 às 13:52:** após checar os arquivos,
o fluxo deve prosseguir com requisitos suportados e limitações sinalizadas.
Arquivos ilegíveis/inválidos bloqueiam quando impedem interpretação confiável;
não verificado nunca é aprovado. Trata-se de política a implementar, não de
garantia do parser ou validador atuais.

Às 13:53 foi confirmada a separação dos resultados em problemas técnicos
(ilegibilidade, incompatibilidade, não suportado), falhas de requisitos IDS
e alertas complementares fora do IDS. Estes últimos não representam conformidade
formal. A visão principal por elemento e a alternativa por requisito estão
confirmadas, com esperado, encontrado e origem. Cada análise identifica versões
exatas de IFC, IDS e catálogo; mudança gera nova análise e preserva a anterior.
Os estados são conforme, não conforme, não aplicável, não verificado e erro.
Ausência de elementos aplicáveis segue cardinalidade/exigência do IDS e fica
explícita; lista vazia não é aprovação automática.

O módulo 2 somente lê/verifica, sem criar propriedades ou alterar valores IFC.
A primeira entrega analisa individualmente. A decisão posterior de 12/10 inclui no MVP dois pares IFC–IDS, arquitetura e estrutura,
com visualização federada prioritária na mesma sessão M4. Diagnóstico, identidade,
evidência e exportação permanecem por arquivo; não há evidência cruzada entre arquivos
no MVP. M3 processa por modelo e a sessão compartilha uma fila LLM serial.

Validar e exportar diagnóstico independe de enriquecimento/LLM. O resultado
completo deve ser rastreável na plataforma e em relatório exportável; BCF da
frente 5 consome esse mesmo diagnóstico. Formatos/limites/timing serão ensaiados.

```text
IFC original identificado + IDS pronto
  → leitura / validação rastreável
  → evidência por elemento e campo
  → catálogo quando houver mapeamento + regras / contexto / proposta ou abstenção
  → revisão humana por campo, vinculada à evidência e à revisão do modelo
  → cópia IFC com alterações aprovadas / delta / revalidação
  → relatório, auditoria e BCF de pendências

Nova revisão IFC → comparação / invalidação → nova revisão humana
```

Identidade da revisão, evidência, proposta, decisão humana e resultado de
aplicação devem ser distinguíveis. Aprovação, escrita bem-sucedida e conformidade
são estados diferentes. O original será preservado; cópia parcial exige
pendências e resultados explícitos. Os detalhes dessa política continuam abertos.

Atualização de 12/10: o catálogo é extensível, curado e versionado; inicialmente
consulta a API pública bSDD para semântica, sem enviar conteúdo de projeto. A execução
conserva snapshots e versões das respostas usadas; armazenamento integral local dos
dicionários é estudo futuro. Migração para o bSDD brasileiro de Juliana continua controlada. Operador pode solicitar mapeamentos; curador aprova e
publica versões. O LLM sugere correspondências sem transformá-las automaticamente
em cadastro aprovado. Conforme confirmação de 09/10 às 13:47, cada projeto
fixa a versão do catálogo; atualização explícita apresenta diff, reprocessa
e mantém históricos rastreáveis. Definição, aplicabilidade e evidências são
separadas, reutilizando conceitos quando o significado é o mesmo. Estruturas
e mecanismos estão propostos no [plano do módulo 1](../planejamento/modulo-01-dominio-catalogo.md),
ainda sem implementação. SINAPI operacional continua futuro.

O perfil inicial inclui `EB_Orçamento` fiel/reconciliado à dissertação, sem
substituição silenciosa por `Cost_Prop`. Cadastro/extensão de propriedades pela
plataforma são requisitos confirmados; tabela editável com detalhamento é a
direção aprovada, incluindo adicionar/duplicar rascunho no plano, com layout e
interação a aprofundar na implementação. Uma nova
linha cadastral não implementa automaticamente extração/inferência, não torna
o campo obrigatório e não altera IDS/IFC silenciosamente.

Cadastro sem código usa operações suportadas. Novas extrações ou cálculos
exigem implementação e ficam sem enriquecimento até então; isso não impede
validar requisitos suportados. Foi confirmado buscar com Juliana o IDS original
de dez especificações e a planilha editável; enquanto as fontes não forem
obtidas e conferidas, estruturar a base pelos apêndices com divergências pendentes.

Autoria/criação IDS é um
[módulo futuro previsto](../planejamento/README.md#extensao-futura--autoria-ids),
ligado às frentes 1, 2 e 4. Sua primeira entrega permanece fora do escopo inicial
que recebe IDS pronto. Reutilização de catálogo, seleção de requisitos e
validação/exportação são direções propostas, com detalhamento posterior.

## Contratos existentes e limites

Fonte: [contracts.py](../../src/foundation/contracts.py),
[adapters.py](../../src/foundation/adapters.py),
[review.py](../../src/foundation/review.py) e
[test_contracts.py](../../tests/foundation/test_contracts.py).

| Fronteira | Contrato existente | Limite relevante |
|---|---|---|
| Catálogo | `SemanticCatalog` | `BSDDClient` consulta API pública; builder usa chamadas legadas adicionais. Política de 12/10 exige adaptador compatível, filtro sem dados de projeto e snapshots; implementação ainda não demonstrada |
| Leitura IFC | `ModelInspector` | `get_element`/`get_model_summary` não representam toda a identidade, evidência e paginação futuras |
| Requisitos IDS | `RequirementSource` | Adaptador chama parser atual; forma e template de teste não certificam conformidade completa |
| Contexto | `GroundingContextBuilder` | `build` existe; falta contrato completo de evidência/procedência por campo |
| Inferência | `LocalLanguageModel` | `require_local_model` verifica endpoint quando chamado; pipeline não aplica essa verificação transversalmente |
| Revisão | `ElementReviewQueue`, `ElementReviewItem`, `ReviewDecision` | Fila não implementada; decisão ainda não contém toda a identidade de revisão, catálogo e valores tipados |
| Exportação | `IssueExporter` | `BCFExporter` tem forma compatível; ensaio de versão/schema/receptor ainda necessário |
| Auditoria | `AuditTrail` | `AuditLogger` registra em memória; não equivale à persistência durável da revisão |
| Avaliação | `EvaluationSuite` | Adaptador calcula métricas existentes; estudo humano e protocolo ampliado permanecem futuros |

Testes de forma verificam fronteiras pontuais. Não provam adoção operacional
transversal, cobertura semântica completa ou conformidade integral de saída.
A [fundação de 08/10](fundacao-semantica.md) conserva o registro inicial.

## Organização e responsabilidades

Uma aplicação modular pode sustentar as sete frentes. Elas não exigem sete
serviços, bancos ou árvores físicas. Preservar `src/`, `tests/`, `data/`,
`scripts/` e `windows/`; usar o mapa para localizar responsabilidades.
`pipeline.py`, `models.py`, contratos, validação e auditoria são compartilhados.

Responsabilidades confirmadas em 12/10: **Felipe M1/M2/M3/M5; Nonato M4/M6 e
liderança M7, com ajuda de Felipe**. O [plano M3](../planejamento/modulo-03-contexto-enriquecimento.md)
tem planejamento concluído e verificado, sem pendência de aprovação de Felipe;
implementação não concluída. Consolida evidência por registro, manual fundamentado e
revisão de requisito inadequado.
M3 propõe, M4 registra decisão, M5 escreve em cópia e M2 revalida. Uma inferência por vez
é o baseline; roteamento por campo/grupo será avaliado por M7 com recursos M6.

## Limites de domínio, operação e pesquisa

- Arquitetura/estrutura: operacionalizar Daiane A.1–A.10 e Apêndice B, incluindo
  `EB_Orçamento` personalizado, com curadoria e teste de cada entrada.
- Fontes distintas: o IDS público Daiane 2026 relatado no planejamento, com
  seis especificações arquitetônicas/`Cost_Prop`, não comprova cobertura da
  dissertação de 2025 nem do piso arquitetura/estrutura.
- IFC2X3 e IFC4 existem nos casos casa/prédio. A meta confirmada inclui IFC4.3,
  com caso real/fixtures de arquitetura e estrutura e suporte por capacidade
  testada. Leitura, validação, visualização e escrita serão ensaiadas separadamente;
  releases exatos, facetas IDS, exportadores e receptor BCF serão definidos/testados.
  Não há suporte universal certificado nem expansão para infraestrutura.
- Execução deve manter dados, inferência e ativos locais/internos ao IME.
  Dependências externas legadas constam do inventário; operação integralmente
  offline e governança multiusuário ainda precisam de implementação/verificação.
- Visualização 3D, persistência e comparação de revisões não estão implementadas.
  Stack M4 definida: React/TypeScript/Vite/shadcn e API Python; That Open é candidato
  a ensaio. Hardware e detalhes operacionais permanecem abertos.
- `PROMPT_VERSION v7.8`, GTs, comparadores, locks e resultados históricos ficam
  preservados. Novos estudos exigirão condição e identidade explícitas.

## Próxima entrega

Prosseguir com o planejamento autorizado do módulo 4 em tarefa separada, usando os contratos do
[planejamento M3](../planejamento/modulo-03-contexto-enriquecimento.md). No desenvolvimento,
alinhar identidade, evidência e resultado canônico com o
[plano do módulo 1](../planejamento/modulo-01-dominio-catalogo.md) e o
[plano do módulo 2](../planejamento/modulo-02-nucleo-ifc-ids.md). O módulo 2 propõe serviço
somente leitura, bundle IDS autêntico/offline, suporte por capacidade e diagnóstico
independente de LLM; essas capacidades ainda precisam de implementação e ensaio.
Instrumentar a avaliação desde a primeira fatia funcional, preservando decisões
confirmadas e identificando propostas técnicas. Esta organização não aplica correções B01–B10 nem cria uma
nova condição experimental.

[Voltar ao índice documental](../README.md).
