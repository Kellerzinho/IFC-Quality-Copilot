# Mapa das sete frentes

> Atualização de 12/10: Felipe M1/M2/M3/M5; Nonato M4/M6 e liderança M7 com Felipe.
> A [precedência vigente](README.md#decisoes-posteriores-de-1210) permite API pública
> bSDD para semântica sem conteúdo de projeto; mantém execução/evidência locais/IME.

**Data:** 9 de outubro de 2026. Mapa de organização da base existente, com
responsabilidades confirmadas e lacunas para a discussão posterior dos módulos.
Os planos detalhados do [módulo 1](modulo-01-dominio-catalogo.md) e do
[módulo 2](modulo-02-nucleo-ifc-ids.md) estão disponíveis para revisão.
Este mapa não constitui sete planos nem atesta capacidades futuras.

Fontes: [consolidação preservada](CONSOLIDACAO-2026-10-09.md),
[decisões posteriores confirmadas](README.md#decisoes-posteriores-de-0910) e
[arquitetura base](../arquitetura/base-do-projeto.md).

## Frente 1 — Domínio e catálogo

**Objetivo:** representar significado, aplicabilidade, vocabulário e evidência
admissível em catálogo extensível e versionado. **Responsabilidade:** Felipe
conduz a frente, incluindo sua implementação, conforme atualização de 12/10.
Pessoas responsáveis pela curadoria/aprovação especializada permanecem a designar.

**Base existente:** [bSDD](../../src/bsdd/), [semântica compartilhada](../../src/semantic/),
[registro semântico](../../src/semantic_registry/), [perfis](../../src/profiles/) e
[templates IDS](../../data/ids_templates/). `SemanticCatalog` está nos
[contratos](../../src/foundation/contracts.py); o builder usa também chamadas legadas.

**Interfaces:** fornece significado e mapeamentos às frentes 2–4, versões e
fontes à 7; depende da infraestrutura da 6. Não controla se um requisito IDS
suportado pode ser validado.

**Decisões confirmadas em 09/10:** o operador fornece IDS pronto; autoria pela UI
fica fora do escopo inicial. IDS pode conter propriedades desconhecidas pelo
catálogo; validar requisitos suportados independentemente de cadastro. Campos
sem mapeamento semântico devem ser explicitados e não preenchidos automaticamente
por equivalência inventada. Operador pode solicitar mapeamentos; somente curador
aprova e publica versões. O LLM pode sugerir correspondências sem cadastrá-las
automaticamente como verdade. Confirmação posterior às 13:47: cada projeto
fixa uma versão do catálogo; atualização explícita apresenta diff, provoca
reprocessamento e preserva históricos rastreáveis. O mecanismo proposto consta
do plano do módulo 1; nenhuma implementação foi feita nesta etapa.

**Lacunas:** catálogo local de domínio, matriz de cobertura, reconciliação de
fontes, correspondências aprovadas e fluxo de publicação. Daiane A.1–A.10 e
Apêndice B são piso a operacionalizar; `EB_Orçamento` é personalizado. Catálogo
provisório deve ser substituível pelo bSDD brasileiro de Juliana. SINAPI
operacional continua futuro.

**Requisitos adicionais confirmados em 09/10:** perfil inicial inclui
`EB_Orçamento` fiel/reconciliado à dissertação, sem substituição silenciosa por
`Cost_Prop`; curadoria com cadastro/extensão de linhas e propriedades acessível
pela plataforma. Tabela editável com detalhamento foi aprovada como direção;
layout/interação serão aprofundados na implementação. Adicionar/duplicar linha
faz parte da direção de curadoria do plano; duplicação gera rascunho sujeito a
revisão de identidade, nunca publicação automática. Adicionar linha cadastral não implementa
automaticamente extração/inferência, não torna o campo obrigatório e não altera
IDS/IFC silenciosamente. Confirmação posterior às 13:47: separar definição,
aplicabilidade e evidências, reutilizando conceitos de mesmo significado.
Cadastro sem código usa operações suportadas; novas extrações ou cálculos
exigem implementação e ficam sem enriquecimento até então. A validação de
requisitos suportados continua independente do cadastro e desse enriquecimento.

**Fonte ainda em verificação:** a pesquisa paralela relatou `IDS_Cost.ids` no
pacote Daiane 2026, Zenodo `19150057`: seis especificações de arquitetura, IFC4,
`Cost_Prop`. Preservar essa fonte/versão separada da dissertação de 2025 e de
`EB_Orçamento`; o pacote público não cobre o piso completo arquitetura/estrutura.
O arquivo não foi incorporado nem reinspecionado nesta reorganização.

**Encaminhamento confirmado às 13:47:** buscar com Juliana o IDS original de dez
especificações e a planilha editável. Enquanto isso, estruturar a base pelos
apêndices, mantendo divergências pendentes. Contato, obtenção e conferência
dessas fontes não foram realizados nesta revisão.

**Plano disponível:** [Módulo 1 — Domínio e catálogo](modulo-01-dominio-catalogo.md),
com inventário de código, lacuna dos contratos legados, modelo detalhado,
curadoria/publicação, cobertura A.1–A.10/B, reconciliação dos 34 pontos relatados,
18 tarefas, testes, migração, rollback e entregas. As estruturas técnicas são
propostas; decisões confirmadas estão no índice. Próximo passo: revisão do plano.

## Frente 2 — Núcleo IFC e IDS

**Objetivo:** leitura confiável e validação rastreável. **Responsabilidade:**
Felipe conduz a frente, conforme atualização de 12/10.

**Base existente:** [análise IFC](../../src/ifc_analyzer/),
[registro IFC](../../src/ifc_registry/), [tradução IDS](../../src/translator/),
[validação](../../src/validation/) e [schema IDS atual](../../data/ids_schema/ids.xsd).
Contratos `ModelInspector` e `RequirementSource` existem na fundação.

**Interfaces:** recebe IFC, IDS fornecido pelo operador e catálogo quando
disponível; produz evidências e resultados para 3–5. Validação formal de
requisitos suportados independe de cadastro semântico; ausência de mapeamento,
recurso não suportado e erro de execução precisam ser distinguíveis.

**Decisão confirmada em 09/10 às 13:52:** após checar os arquivos, prosseguir
parcialmente com requisitos suportados e sinalizar limitações. Bloquear arquivos
ilegíveis ou inválidos quando impedirem interpretação confiável. Resultado não
verificado nunca é aprovado. Às 13:53 foi confirmada a separação em problemas
técnicos (ilegibilidade, incompatibilidade, não suportado), falhas de requisitos
IDS e alertas complementares fora do IDS. Alerta complementar não representa
conformidade formal.

**Confirmações posteriores de 09/10:** visão principal por elemento e alternativa
por requisito, com esperado, encontrado e origem (D13). Cada análise fica ligada
às versões exatas de IFC, IDS e catálogo; mudanças geram nova análise e preservam
o histórico (D14, 13:59). Os estados são conforme, não conforme, não aplicável,
não verificado e erro; ausência de elementos aplicáveis é explícita e segue
cardinalidade/exigência do IDS, nunca aprovação por lista vazia (D15, 14:00).

O módulo 2 somente lê/verifica: não cria propriedades nem altera valores IFC.
Propostas de enriquecimento e escrita posterior com revisão humana ficam em
outras etapas (D16, 14:06). A primeira entrega faz análise individual.
A decisão posterior de 12/10 substitui o extra de D17: MVP com dois pares IFC–IDS,
arquitetura e estrutura, visualização federada prioritária na frente 4 e mesma sessão.
Preservar identidade, diagnóstico, evidência e saídas por arquivo; sem evidência cruzada
entre arquivos no MVP. M3 processa por modelo e a sessão mantém fila LLM serial.

IFC2X3, IFC4 e IFC4.3 são metas aprovadas (D18, 14:17), com suporte declarado
somente por capacidade testada. Ensaiar leitura, validação, visualização e escrita
separadamente; incluir caso real e fixtures IFC4.3 de arquitetura/estrutura,
fixando release exato após ensaios. Não ampliar o domínio para infraestrutura.
A presença de IFC4X3_ADD2 na
[release IDS 1.0 da buildingSMART](https://github.com/buildingSMART/IDS/releases)
não comprova suporte da instalação atual.

O percurso validar e exportar diagnóstico é independente de enriquecimento/LLM
(D19, 14:18). O resultado completo permanece rastreável na plataforma e em
relatório exportável; BCF da frente 5 consome o mesmo diagnóstico. Formatos,
limites e timing serão definidos por ensaios, sem decisão arbitrária aqui.

**Lacunas:** matriz de suporte, schema IDS efetivo, cardinalidade/enumerações,
identidade por revisão, ocorrência/tipo, unidade, método e estados de validação.
O XSD atual é placeholder; contrato ou retorno positivo não certificam conformidade.

**Plano disponível:** [Módulo 2 — Núcleo IFC/IDS](modulo-02-nucleo-ifc-ids.md),
com pipeline/estados, identidade arquivo/revisão/elemento, parsing seguro e bundle
IDS oficial versionado/offline, facetas/cardinalidade, leitura de materiais,
unidades/Qto e geometria, diagnóstico/exportação sem LLM, 18 tarefas e 32 casos.
B01/B02/B07/B08 são prioridades planejadas; B03–B06/B09/B10 entram pelas fronteiras
pertinentes, sem correções nesta entrega. Suporte IFC2X3/IFC4/IFC4.3 dependerá dos
ensaios por capacidade; caso real IFC4.3 permanece pendente. Próximo passo: revisão
do plano e definição da primeira fatia autorizada.

## Frente 3 — Contexto e enriquecimento

**Objetivo:** contexto pertinente por campo, proposta sustentada ou abstenção.
**Responsabilidade principal confirmada em 12/10:** Felipe.

**Base existente:** [suggestion_engine](../../src/suggestion_engine/) e
[evidência do modelo](../../src/ifc_analyzer/model_evidence.py). Inclui grounding,
regras determinísticas, normalização, plausibilidade, cálculo, Ollama, cache e worker.

**Interfaces:** recebe catálogo/evidências de 1–2, produz propostas para 4,
usa runtime da 6 e observação da 7. Não autoriza escrita ou publicação no catálogo.

**Lacunas:** receitas por propriedade; procedência de evidência; distinção entre
recuperar, padronizar, calcular, interpretar, inferir e solicitar decisão;
conflitos, suporte verificável, abstenção e invalidação por revisão.

**Planejamento:** [M3 consolidado](modulo-03-contexto-enriquecimento.md) e
[matriz reconciliada](../pesquisa/modulo-03-contexto/README.md), com fonte/operação
separadas e critérios por registro. **Planejamento concluído e verificado, sem pendência
de aprovação de Felipe; implementação não concluída.** Ensaios continuam futuros; `v7.8` preservado.

## Frente 4 — Interface e revisão humana

**Objetivo:** decisão por elemento/campo, compreensível e rastreável.
**Responsabilidade confirmada em 12/10:** Nonato. Planejamento autorizado em tarefa própria.
Stack definida: React/TypeScript/Vite/shadcn e API Python; That Open é candidato a ensaio.
Fluxo visual e integração continuam a detalhar.

**Base existente:** [UI Streamlit](../../src/ui/),
[IssueStore](../../src/suggestion_engine/issue_store.py) e
[modelos de revisão](../../src/foundation/review.py). `ElementReviewQueue` é
protocolo sem implementação; a interface atual revisa por issue.

**Interfaces:** recebe resultados de 2 e propostas de 3, registra decisões para
5, depende de estado/governança da 6 e fornece medidas à 7.

**Lacunas:** visualização 3D, fila por elemento, correspondência com geometria,
persistência, proposta escolhida identificável, alcance de alteração em tipo
e estados distintos de rejeição, adiamento e pendência. Autoria IDS pela UI
fica fora do escopo inicial confirmado.

Cadastro/extensão de propriedades pela plataforma e direção de tabela editável
com detalhamento foram confirmados; forma de apresentação e interação serão
aprofundadas depois. Isso é interface de catálogo, distinta da autoria IDS
prevista para a extensão futura. A visão principal por elemento e a alternativa
por requisito estão confirmadas. Visualização federada dos dois pares IFC–IDS é prioridade do MVP, preservando
origem, diagnóstico, evidência e saídas por arquivo; sem evidência cruzada no MVP.

**Próximo debate:** seleção lista/3D, evidências, decisões por campo,
acessibilidade e retomada; avaliar o candidato 3D na stack definida.

## Frente 5 — Saídas IFC/BCF e revisões

**Objetivo:** integridade das alterações aprovadas, pendências e continuidade
entre revisões. **Responsabilidade confirmada em 12/10:** Felipe.

**Base existente:** [writer](../../src/writer/), [BCF](../../src/bcf/),
[auditoria](../../src/audit/), [pipeline](../../src/pipeline.py) e
[PostValidator](../../src/validation/post_validator.py).

**Interfaces:** recebe decisões de 4 e operações/validação de 2; entrega IFC,
auditoria e pendências. Identidade e armazenamento são compartilhados com a 6.

**Lacunas:** cópia separada do original, pré-condições, delta, revalidação de
publicação, identidade/viewpoint BCF e comparação/invalidação em novo IFC.
Forma de `IssueExporter` não prova compatibilidade BCF com receptor real.

**Próximo debate:** política de cópia parcial/regressões, alcance em tipos,
correspondência entre revisões e ensaio BCF. B03–B05 permanecem backlog.

## Frente 6 — Infraestrutura e governança

**Objetivo:** execução local/interna, reproduzível e recuperável.
**Responsabilidade principal confirmada:** Nonato.

**Base existente:** [configuração](../../src/config.py),
[localidade](../../src/foundation/locality.py), [adaptadores](../../src/foundation/adapters.py),
[MCP](../../src/mcp_server/), infraestrutura em [experiment](../../src/experiment/),
[scripts](../../scripts/) e [pacote Windows](../../windows/).

**Interfaces:** transversal às seis outras frentes; sustenta runtime, estado,
armazenamento e identidade de execução. Publicação de catálogo exige autoridade
de curador conforme D03; implementação de papéis ainda será planejada.

**Lacunas:** aplicação transversal da localidade, ativos internos, persistência,
isolamento, papéis, retenção, backup/restauração, licenças e recursos.
Servidor HTTP existente não comprova operação institucional multiusuário.

**Próximo debate:** infraestrutura disponível, limites operacionais e
continuidade de decisões após falhas. B06/B09 são inventário, sem alteração de
segurança ou configuração nesta etapa.

## Frente 7 — Avaliação científica

**Objetivo:** medir correção sustentada, abstenção, esforço de revisão e recursos.
**Responsabilidade confirmada em 12/10:** Nonato lidera M7, com ajuda de Felipe.
Recuperação de evidência, interpretação LLM e fluxo completo exigem avaliações separadas.

**Base existente:** [experiment](../../src/experiment/),
[testes de avaliação](../../tests/evaluation/), [testes experimentais](../../tests/experiment/),
[datasets](../../data/evaluation/) e [métricas documentadas](../metricas-avaliacao.md).

**Interfaces:** observa as entregas desde o início; recebe identidades, versões,
evidências, propostas, decisões e resultados. Casa/prédio são casos iniciais;
suas cópias idênticas não ampliam o corpus independente.

**Lacunas:** gabarito especializado independente, casos indeterminados,
projetos externos ao ajuste e estudo humano real. Revisor simulado não substitui
ensaio com pessoas; hipóteses históricas não devem ser reinterpretadas silenciosamente.

**Próximo debate:** perguntas, comparações, partições, denominadores e métricas
de suporte/abstenção/esforço. Preservar GT, resultados e condições existentes.

<a id="extensao-futura--autoria-ids"></a>

## Extensão futura — Autoria IDS

**Módulo futuro previsto, confirmado em 09/10:** autoria/criação de IDS, com
aprofundamento posterior, vinculada às frentes 1 (catálogo), 2 (validação) e
4 (UI). Preservar as sete frentes e a entrada por IDS pronto na primeira entrega.

Reutilização do catálogo, seleção de classes/aplicabilidade/requisitos e
validação/exportação são direções propostas. Cadastro de uma propriedade não
a torna obrigatória automaticamente no IDS. Ver o
[registro da decisão](README.md#extensao-futura--autoria-ids).
Não há implementação de autoria ou de UI de catálogo nesta etapa.

## Componentes compartilhados e próximos planos

[pipeline.py](../../src/pipeline.py), [models.py](../../src/models.py),
[foundation](../../src/foundation/), auditoria e validação atravessam frentes.
Os caminhos ficam preservados; a numeração organiza responsabilidades.
Os planos dos módulos 1, 2 e 3 estão disponíveis; o próximo planejamento é o
brainstorming do módulo 4. Os demais serão produzidos depois, ligados ao
[índice de planejamento](README.md). Nenhuma lacuna desta página foi implementada
pela organização documental.
