# Documentação do IFC Quality Copilot

**Índice atualizado em 12 de outubro de 2026.** Os caminhos existentes foram
preservados. Documentos históricos devem ser lidos com suas datas, versões e
condições; não representam automaticamente o estado atual do software.

## Planejamento e decisões atuais

- [Índice de planejamento](planejamento/README.md): sequência, responsabilidades e decisões posteriores ao registro inicial.
- [Consolidação de 09/10](planejamento/CONSOLIDACAO-2026-10-09.md): decisões de 8–9/10, inventário, casos, limites e achados B01–B10; registro preservado.
- [Mapa das sete frentes](planejamento/mapa-sete-frentes.md): organização de responsabilidades e módulos existentes.
- [Módulo 1 — Domínio e catálogo](planejamento/modulo-01-dominio-catalogo.md): plano extenso proposto, com modelo de dados, fontes Daiane, curadoria, pacotes locais, contratos, 18 tarefas e critérios de aceite.
- [Módulo 2 — Núcleo IFC/IDS](planejamento/modulo-02-nucleo-ifc-ids.md): plano completo proposto de leitura/verificação, identidade, estados, suporte por capacidade, diagnóstico sem LLM, 18 tarefas e 32 casos de teste.
- [Módulo 3 — Contexto e enriquecimento](planejamento/modulo-03-contexto-enriquecimento.md): **planejamento concluído e verificado, sem pendência de aprovação de Felipe; implementação não concluída**. [Apoios reconciliados](pesquisa/modulo-03-contexto/README.md): 203 registros alfanuméricos + 110 auxiliares, fichas individuais, JSON/CSV da mesma revisão, baseline e verificação. Decisões atuais no [índice de planejamento](planejamento/README.md#decisoes-posteriores-de-1210).
- [Síntese bibliográfica dos 29 artigos de Daiane](pesquisa/sintese-bibliografica-daiane-29-artigos.md): integração nova de 10/10 nos três planos, com IDs, DOI/links, páginas, evidência/limites e matrizes referência → decisão → tarefa/teste em [M1](planejamento/modulo-01-dominio-catalogo.md#m1-bibliografia), [M2](planejamento/modulo-02-nucleo-ifc-ids.md#m2-bibliografia) e [M3](planejamento/modulo-03-contexto-enriquecimento.md#m3-bibliografia). Recomendações novas permanecem propostas.

## Arquitetura e base técnica

- [Arquitetura base](arquitetura/base-do-projeto.md): implementação observada, evolução pretendida e fronteiras.
- [Fundação semântica de 08/10](arquitetura/fundacao-semantica.md): contratos iniciais e lacunas de integração.
- [Convenções do projeto](../CLAUDE.md) e [contexto técnico](../PROJECT_CONTEXT.md): entradas existentes com notas de continuidade.
- [Contratos em código](../src/foundation/contracts.py), [adaptadores](../src/foundation/adapters.py) e [testes de contratos](../tests/foundation/test_contracts.py).
- [Dívidas técnicas](dividas-tecnicas.md): limitações já registradas.

## Avaliação e condições experimentais

- [Definição de métricas](metricas-avaliacao.md) e [pontos de cálculo](pontos-de-calculo.md).
- [Condição v7.8](condicao-v7-8-2026-08-19.md): ler antes de alterar o instrumento.
- [Emenda do ground truth](emenda-gt-2026-08-12.md): origem e condição das referências históricas.
- [Condição de equivalências do GT](condicao-gt-equivalencias-2026-08-10.md).
- [Condição da ablação bSDD](condicao-ablacao-bsdd-2026-08-18.md) e [resultado correspondente](resultado-ablacao-bsdd-2026-08-19.md).
- [Condição de escala 4070](condicao-escala-4070-2026-08-16.md) e [replicação 5050](resultado-replicacao-5050-2026-08-19.md).
- [Caso casa](../data/evaluation/casa/README.md) e [caso prédio](../data/evaluation/predio/README.md).
- [Fontes normativas: política e limites](../references/normative/public/README.md).

Esses registros documentam experimentos específicos. A reorganização documental
não executa novas rodadas nem converte hipóteses congeladas em verdade independente.

## Planos, análises e pareceres históricos

- [Plano consolidado de junho](plano-consolidado-2026-06-09.md) e [orquestração de junho](plano-orquestracao-2026-06-25.md).
- [Baseline verificado de junho](baseline-verificado-2026-06-26.md).
- [Revisão crítica de junho](revisao-critica-2026-06-09.md) e [avaliação crítica de setembro](AVALIACAO_CRITICA_PESQUISA_2026-09-09.md).
- [Planos técnicos anteriores](superpowers/plans/) e [especificações anteriores](superpowers/specs/).
- [Pareceres existentes](reviews/) e [materiais de artigo](../Artigo/).

Itens preexistentes não rastreados, inclusive pareceres e materiais de artigo,
continuam nessa condição. A presença de um link não os incorpora ao versionamento.

## Proveniência

- [Proveniência da base de 08/10](migracao/PROVENIENCIA-2026-10-08.md): migração, preservação e verificações realizadas naquela etapa.
- [Entrada do repositório](../README.md).

Os planos M1/M2 e a integração bibliográfica dos 29 artigos permanecem preservados.
O M3 recebe consolidação posterior com a matriz local e as decisões de 12/10; seu status
é independente de implementação ou validação empírica. Fontes ainda ausentes têm
encaminhamento explícito no plano, sem reabrir a aprovação documental. O planejamento
da frente 4 foi autorizado em tarefa separada; sua decisão de dois pares IFC–IDS e
federação visual no MVP está no índice de planejamento, sem evidência cruzada entre arquivos.
Outros planos serão indexados quando elaborados, sem antecipar implementação.
Esta documentação não implementa capacidades nem altera resultados, dados ou código.

## Catálogo de domínio M1

[Implementação local, curadoria e distribuição pública](catalogo/README.md): código e testes sintéticos, perfil de pesquisa externo, operação/recuperação e validação integrada. Aceite semântico permanece separado.
