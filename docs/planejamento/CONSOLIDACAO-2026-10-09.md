# IFC Quality Copilot — consolidação das decisões e da base real

**Data:** 9 de outubro de 2026.  
**Origem das decisões:** conversa com Felipe em 8–9 de outubro de 2026, incluindo as atualizações expressas de responsabilidade e de sequência de trabalho.  
**Estado:** consolidação documental. Este documento não implementa a arquitetura proposta nem atesta correção integral do programa.  
**Prioridade mais recente:** registrar agora no repositório; organizar os documentos depois, se necessário.

## 1. Finalidade e precedência

Este registro reúne o direcionamento do projeto, as sete frentes, as decisões confirmadas, as propostas ainda abertas e o inventário obtido por leitura do repositório. Seu propósito é evitar perda de contexto antes de aprofundar cada módulo.

A sequência acordada passou a ser:

1. Compreender e documentar a base real do repositório e o mapa das sete frentes.
2. Discutir e aprofundar cada módulo em plano próprio, completo e verificável.
3. Implementar incrementos delimitados, com testes e revisão.

A autorização de Felipe para escrever esta consolidação substitui a orientação anterior de aguardar antes de gravar documentos. Ela não autoriza executar aqui as correções funcionais, alterar o prompt, reorganizar código ou modificar configurações.

Quando houver conflito de planejamento, prevalecem as decisões mais recentes explicitadas na conversa. Os documentos antigos permanecem como histórico, sem reinterpretação silenciosa dos experimentos publicados.

### Fontes de continuidade

- **Plano anterior:** `IFC_Quality_Copilot_Plano_de_Desenvolvimento.docx`, versão 1, 26 páginas, de 8 de outubro de 2026; Library `libfile_14a871cb91f481919ad968dfa8acf9df`. Foi consultado pela Library, mas não foi materializado nesta pasta. É baseline de planejamento anterior à inspeção do código, não prova de implementação.
- **Conversa de 8–9 de outubro:** fonte das decisões atuais de escopo, responsabilidades, sequência e autorização documental.
- **Leitura do repositório em 9 de outubro:** fonte do inventário técnico e dos achados deste documento.
- **Complemento sobre notas anteriores:** a consulta independente ao Second Brain confirmou estudos e síntese das dissertações, mas não localizou ata atual das sete frentes ou das atribuições recentes. Não se presume que toda a discussão já estivesse salva. Não são reproduzidos caminhos nem referências a notas privadas.

### Estados usados neste documento

| Estado | Significado |
|---|---|
| Confirmado | Direcionamento explicitado por Felipe na conversa |
| Verificado por leitura | Observado em arquivos, código, testes ou metadados; sem execução funcional nesta sessão |
| Relatado | Informação recebida ou registrada em documentação, sem repetição da medição aqui |
| Proposto | Desenho ou distribuição sugerida, ainda sujeito a discussão |
| Pendente | Decisão ou evidência necessária para fechar o respectivo assunto |

## 2. Resultado pretendido e limites confirmados

A primeira versão de pesquisa deve oferecer um percurso independente de Blender/Bonsai, executado na máquina local ou em infraestrutura interna do IME, que:

1. Recebe IFC e IDS dentro de uma matriz explícita de suporte.
2. Preserva o original e identifica a revisão importada.
3. Verifica requisitos computáveis e registra o que foi ou não executado.
4. Recupera contexto pertinente do próprio IFC, com evidência e procedência.
5. Produz recuperação, padronização, cálculo, interpretação, inferência experimental ou abstenção, mantendo essas rotas distinguíveis.
6. Permite revisão por elemento e por campo, com lista, visualização 3D e evidências inspecionáveis.
7. Aplica somente decisões humanas aprovadas em uma cópia IFC.
8. Revalida a cópia e entrega auditoria, relatório e BCF de pendências.
9. Compara uma nova revisão IFC sem reaplicar cegamente valores ou aprovações antigas.

### Escopo de domínio

- **Confirmado:** arquitetura e estrutura.
- **Confirmado:** partir da cobertura completa dos quadros A.1–A.10 e do Apêndice B da dissertação de Daiane, incluindo Psets padronizados, propriedades, atributos, classificações, materiais, quantidades e `EB_Orçamento`.
- **Confirmado:** `EB_Orçamento` é um Pset personalizado do perfil de referência, não um padrão universal obrigatório para qualquer modelo.
- **Confirmado:** o motor deve aceitar outros perfis, namespaces, IFCs e IDS dentro dos recursos suportados. A base de Daiane é o piso de cobertura, não uma restrição universal de nomes.
- **Confirmado:** catálogo estruturado, extensível e versionado, separado do código de execução.
- **Confirmado:** Juliana desenvolverá o bSDD brasileiro; o protótipo deve funcionar com catálogo provisório local substituível, sem esperar essa entrega.
- **Confirmado:** SINAPI operacional, seleção de composições, preços por competência/UF, cálculo de custos e produção de orçamento permanecem em etapa futura.
- **Pendente:** inclusão de memoriais, especificações e outras evidências documentais externas, a discutir com o orientador. O núcleo IFC/IDS deve funcionar sem essa extensão.

### Localidade e controle técnico

- IFC, IDS, BCF, catálogos, índices, modelos de IA, inferência, contexto, logs, dados de avaliação e backups ficam na máquina ou em ambiente interno do IME.
- Não haverá API externa, telemetria externa, CDN necessária à operação ou fallback para provedores externos no fluxo com projetos.
- Dependências públicas legadas precisam ser inventariadas. Download para preparação de um pacote e comunicação durante a operação são situações distintas, que precisam de política explícita.
- Uma interface de API compatível com outro protocolo não autoriza usar o respectivo serviço público.
- O LLM sugere; não recebe autoridade para escrever IFC, executar shell ou ampliar acesso à rede.
- Confiança declarada pelo LLM não substitui verificação de suporte nem aprovação humana.
- Falha da inferência deve preservar a validação determinística e a possibilidade de revisão.

### Revisão e saída

- O operador aceita, corrige ou encaminha pendências por BCF; rejeição, adiamento e pendência precisam de significado próprio.
- Aprovação é por campos explicitamente selecionados. Um elemento pode conter alterações aprovadas e pendências simultaneamente.
- Alteração em tipo precisa apresentar seu alcance sobre ocorrências.
- Correção humana acrescenta uma origem identificada; não transforma retroativamente uma hipótese em dado extraído.
- A cópia IFC deve conter somente alterações aprovadas. O original é preservado.
- Cópia parcial pode ser uma saída válida, desde que pendências, limites e resultado da revalidação sejam explícitos.
- Aprovação, escrita bem-sucedida e conformidade são estados distintos.
- BCF comunica pendências; não substitui relatório de validação nem prova ausência de problemas quando vazio.

## 3. Cobertura de Daiane e curadoria pendente

O plano anterior relata **195 entradas semânticas por especificação** na união dos Apêndices A e B, excluídas as facetas de classe: 137 propriedades/quantidades, 29 atributos, 19 classificações e 10 materiais. Há repetição entre classes; não são 195 propriedades únicas.

| Quadro | Família | Entradas relatadas |
|---|---|---:|
| A.1 | Janelas — IfcWindow | 23 |
| A.2 | Portas — IfcDoor | 29 |
| A.3 | Paredes — IfcWall | 25 |
| A.4 | Revestimentos de teto — IfcCovering | 21 |
| A.5 | Revestimentos de piso — IfcCovering | 18 |
| A.6 | Revestimentos de parede — IfcCovering | 23 |
| A.7 | Lajes — IfcSlab | 17 |
| A.8 | Pilares — IfcColumn | 15 |
| A.9 | Vigas — IfcBeam | 16 |
| A.10 | Barras de armadura — IfcReinforcingBar | 8 |
| Total | Arquitetura e estrutura | 195 |

As contagens, os **88 caminhos Pset/Qto propostos** e os **34 pontos de reconciliação** são informação do levantamento anterior. Não foram recontados diretamente na dissertação nesta leitura, nem constituem catálogo operacional aprovado.

O aprofundamento da frente 1 deve preservar a transcrição da fonte e a interpretação operacional aprovada, com rastreabilidade entre ambas. Prioridades de reconciliação já relatadas: `Weight/Weigth`, `Height/Heigth`, Status de revestimento associado a conjunto de porta, significado/unidade de `Densidade_Porta`, tipo de `Usos_Forma`, armazenamento de `Area_Forma`, requisitos de armadura e condicionamento de alvenaria/drywall.

Cada entrada deve registrar identidade, fonte/página, classe, aplicabilidade, caminho, schema, tipo, unidade, vocabulário, evidência mínima, método permitido, teste, responsável e estado de cobertura. Cláusulas qualitativas de geometria, posicionamento, representação e conexões precisam de checklist complementar com método e limite explícitos.

Cobertura não exige inventar um valor para toda lacuna. Uma entrada pode exigir decisão especializada, evidência adicional ou abstenção. Novos comportamentos geométricos ou relacionais exigem executores e testes; extensibilidade declarativa não elimina engenharia.

## 4. Responsabilidades e modelos de trabalho

### Distribuição mais recente

| Frente | Responsabilidade confirmada | Detalhamento ainda proposto |
|---|---|---|
| 1 — Domínio/catálogo | Felipe coordena BIM e semântica | Implementação, curadoria e aprovação especializada a acordar |
| 2 — Núcleo IFC/IDS | Felipe coordena critérios BIM | Liderança de implementação e revisão técnica a acordar |
| 3 — Contexto/enriquecimento | **Nonato é responsável principal** | Felipe colaborar nos critérios BIM e evidências por propriedade |
| 4 — Interface/revisão | Nonato terá **participação parcial** | Integração UI/processamento e estado de tarefas como possível recorte; liderança restante a acordar |
| 5 — Saídas/revisões | Felipe coordena critérios BIM | Distribuição de implementação a acordar |
| 6 — Infraestrutura/governança | **Nonato é responsável principal** | Atribuições institucionais concretas dependem de infraestrutura e autorizações |
| 7 — Avaliação científica | Felipe coordena pesquisa; Nonato participa **parcialmente** | Automação de benchmarks, coleta de métricas e reprodutibilidade como possível recorte de Nonato |

Esta tabela substitui a proposta anterior de atribuir a Nonato toda a parte computacional da frente 4. Os recortes parciais das frentes 4 e 7 **não estão confirmados**. Nenhum contato com Nonato ou outros participantes foi realizado nesta sessão.

### Modelos acordados para assistência ao desenvolvimento

- Planejamento e análise: **Astra, esforço xhigh**, conforme seleção/direcionamento da tarefa.
- Aplicação da reorganização e implementação subsequente delimitada: **GPT-6.1 Sol, esforço high**, conforme sequência indicada.
- Revisão após aplicação: **Astra**; não presumir esforço adicional não explicitado para essa rodada.

Essa distribuição se refere aos assistentes de desenvolvimento. Não escolhe o LLM que será implantado no Copilot. O código configura Ollama com modelo padrão `qwen3.5:9b`, mas o modelo de operação e a matriz de pesquisa precisam de decisão e registro de versões/digests próprios. Não houve troca de modelo ou configuração pelo executor nesta consolidação.

## 5. Estado do repositório verificado em 9 de outubro

Conferência de leitura concluída às **13:05 UTC**, antes da autorização para criar este documento. Branch e HEAD foram novamente conferidos antes da gravação.

| Item | Estado verificado |
|---|---|
| Raiz | `C:\Users\Keller_\Desktop\Projetos FC\Pesquisa\ifc-quality-copilot` |
| Branch | `feat/semantic-foundation` |
| HEAD | `a76c2d7a85983ef246761a49db9266c411ea90fd` |
| main | `818347b51ca96962f98529d5d68507b831cf40ea` |
| Commits sobre main | `9f5632f`, `113ee9b`, `a76c2d7` |
| Remote configurado | Nenhum |
| Arquivos de teste inventariados | 106 arquivos `test_*.py` |
| Suíte executada nesta leitura | Nenhuma |
| Resultado de 1.700 testes passando | Relatado por Claude; não reexecutado aqui |
| Prompt | `v7.8` confirmado no template, builder Windows e instalador |

Não foram localizados `AGENTS.md` nos caminhos ancestrais consultados nem nas árvores `src`, `tests` e `docs`. Foram lidos [CLAUDE.md](../../CLAUDE.md), [PROJECT_CONTEXT.md](../../PROJECT_CONTEXT.md), a [fundação semântica](../arquitetura/fundacao-semantica.md) e a [proveniência](../migracao/PROVENIENCIA-2026-10-08.md), além de documentação, código e testes relacionados às sete frentes.

O `rg` não estava instalado. A leitura prosseguiu com ferramentas nativas do PowerShell; não houve escalonamento, mudança de permissão ou contorno de restrição de acesso.

### Estado local preexistente a preservar

```text
 M .claude/settings.local.json
?? --help
?? Artigo/ERABIM_RESUMO_2026/
?? Artigo/Instituto_Militar_de_Engenharia__IME_RJ___1_.zip
?? Artigo/RELATORIO_DEEP_RESEARCH.md
?? Artigo/Resumo para submissão ao A ERA BIM 2026.md
?? Artigo/artigo_ime_ifc_quality_copilot/
?? Artigo/logoIME.png
?? Resumo IFC-Quality-Copilot corrigido.pdf
?? docs/AVALIACAO_CRITICA_PESQUISA_2026-09-09.md
?? docs/reviews/
```

Esta consolidação acrescenta um arquivo documental novo. Não incorpora, move, apaga ou normaliza os itens acima. Nunca usar `git add -A` para integrar o trabalho sem seleção explícita de arquivos.

### Dependências registradas

O [uv.lock](../../uv.lock) registra IfcOpenShell `0.8.5`, Streamlit `1.61.0`, Pydantic `2.13.4`, MCP `2.0.0` e cliente Python Ollama `0.6.2`. O [pyproject.toml](../../pyproject.toml) declara Python `>=3.11`. Esses são dados dos arquivos de dependências, não uma certificação das versões efetivamente instaladas nem da versão do servidor Ollama.

## 6. Casos iniciais e patrimônio experimental

| Arquivo da raiz | Bytes | Schema do cabeçalho | Exportador declarado |
|---|---:|---|---|
| `casa_v1.ifc` | 98.786.386 | IFC2X3 | Revit 26.2.0.20 |
| `predio_v1.ifc` | 195.710.000 | IFC4 | Revit 26.2.0.20 |

Hashes SHA-256 lidos:

```text
casa_v1.ifc
3b84789c7396449f2c8a3d2f4a66468d81e59f8351ebd4b71fad161fa06112f2

predio_v1.ifc
a71c8be30d82760218f5b3f3a1c476b49e3f30e608b0065916b9d5206a1a6dd0

data/evaluation/casa/ground_truth.yaml
e72b344f5b1bd30ac73a02db77868322fae1458e3d4d050f2ccd667f66f6138b

data/evaluation/predio/ground_truth.yaml
040c871f1797f4237bc7c7bd94c03870b1b7c2d7ea1ccabc318b044cae6d56fe
```

As cópias IFC em `data/evaluation` são byte a byte equivalentes às respectivas entradas da raiz, conforme os hashes. Não contam como projetos independentes adicionais. Há também `pavilhao_comando_norte.ifc` na raiz, apenas inventariado por nome nesta sessão; ele não foi selecionado nem validado como novo caso de avaliação.

Os cabeçalhos e hashes foram examinados sem parsing completo ou geração de geometria. A matriz inicial de suporte deverá tratar IFC2X3 e IFC4 explicitamente. O uso de um dicionário IFC 4.3 no bSDD não comprova suporte funcional a modelos IFC4.3. Versões de IDS, variantes de schema, exportadores e ferramentas receptoras de BCF precisam de ensaios próprios.

Os READMEs dos datasets relatam 263 itens/101 classes de equivalência para a casa e 4.720 itens/202 classes para o prédio. Incluem referências tipológicas e hipóteses congeladas. São patrimônio experimental a preservar, não verdade física independente de todos os elementos.

Referências: [casa](../../data/evaluation/casa/README.md), [prédio](../../data/evaluation/predio/README.md), [emenda do GT](../emenda-gt-2026-08-12.md), [métricas](../metricas-avaliacao.md).

## 7. Mapa das sete frentes na implementação existente

### Frente 1 — Domínio, catálogo de propriedades e bSDD

**Objetivo:** representar significado, requisitos e evidência admissível de forma versionada e extensível. Pergunta: como operacionalizar a base completa sem institucionalizar ambiguidades da fonte?

**Reaproveitar/adaptar:** [cliente bSDD](../../src/bsdd/client.py), [cache](../../src/bsdd/cache.py), [context builder](../../src/bsdd/context_builder.py), [modelos bSDD](../../src/bsdd/models.py), [matcher](../../src/semantic/property_match.py), [registro semântico](../../src/semantic_registry/registry.py), [resolvedor](../../src/semantic_registry/resolver.py) e [perfis](../../src/profiles/registry.py).

**Lacunas:** catálogo versionado de domínio, fluxo de curadoria, correspondências aprovadas, provedor local e migração entre pacotes. Não foram encontradas ocorrências de `Daiane`, `EB_Orçamento` ou `EB_Orcamento` nos textos pesquisados de `src`, `docs`, `scripts` e `data/ids_templates`; essa busca não demonstra catálogo aprovado implementado.

**Contrato inicial existente:** `SemanticCatalog.search_classes_text`, `get_class_metadata` e `resolve_property`. O builder atual também usa interfaces legadas como `search_class`, `get_class_properties` e `get_property_values`; será necessário um adaptador ou evolução explícita de contrato.

**Primeiro aprofundamento:** matriz de cobertura/reconciliação; organização/dicionário/versão/conceito; namespace provisório distinto de URI publicada; consulta offline; projeto fixado em versão; teste de troca de pacote sem equivalência presumida por nome.

**Entradas/saídas:** recebe fontes e decisões de curadoria; fornece campos, aplicabilidade, vocabulários e receitas às frentes 2–4 e versões congeladas à 7. Depende da infraestrutura da 6. SINAPI operacional fica fora.

### Frente 2 — Núcleo IFC e IDS

**Objetivo:** leitura confiável e validação rastreável sem depender do LLM. Pergunta: quais dimensões foram realmente verificadas em cada schema e requisito?

**Reaproveitar/adaptar:** [IFCAnalyzer](../../src/ifc_analyzer/analyzer.py), [leitura de materiais](../../src/ifc_analyzer/material_reader.py), [extrator universal](../../src/ifc_analyzer/universal_extractor.py), [quantidades](../../src/ifc_analyzer/extractors/quantity_extractor.py), [parser IDS](../../src/translator/ids_parser.py), [geração/aplicação de regras](../../src/translator/rule_generator.py), [resolução de propriedades](../../src/translator/pset_resolver.py) e [pós-validação](../../src/validation/post_validator.py).

**Lacunas:** identidade por revisão; evidência com origem ocorrência/tipo; resultados completos, inclusive erro e não execução; conformidade IDS efetiva; unidades e métodos; conflitos e duplicação de GUIDs; matriz de recursos suportados.

**Contratos existentes:** `ModelInspector.get_element/get_model_summary` e `RequirementSource.specifications`. Esses contratos não representam ainda toda a identidade, paginação ou resultado de validação necessários.

**Primeiro aprofundamento:** distinguir validação formal de recuperação flexível; testar enumeração, cardinalidade, Qto, atributos, materiais, classificações, relações, zero elementos aplicáveis, recurso não suportado e falha de leitura. Quantidade deve conservar portador, unidade e método.

**Entradas/saídas:** recebe IFC/IDS e catálogo; produz evidências e resultados para 3/4/5; recebe casos de referência da 7 e armazenamento da 6. Não promete suporte irrestrito a versões futuras.

### Frente 3 — Extração de contexto, regras e LLM local

**Objetivo:** reunir contexto pertinente por campo e propor resultado sustentado ou abstenção. Pergunta: que ganho o LLM acrescenta às regras e à recuperação, com que risco?

**Responsável principal confirmado:** Nonato. Colaboração de Felipe nos critérios BIM e nas evidências por propriedade é proposta de detalhamento.

**Reaproveitar/adaptar:** [grounding](../../src/suggestion_engine/grounding.py), [sugestão determinística](../../src/suggestion_engine/deterministic.py), [gerador](../../src/suggestion_engine/suggestion.py), [normalização](../../src/suggestion_engine/normalization.py), [plausibilidade](../../src/suggestion_engine/plausibility.py), [cálculo térmico](../../src/suggestion_engine/thermal_recompute.py), [Ollama](../../src/suggestion_engine/ollama_client.py), [cache](../../src/suggestion_engine/suggestion_cache.py), [worker](../../src/suggestion_engine/worker.py) e [evidência agregada](../../src/ifc_analyzer/model_evidence.py).

**Lacunas:** receitas de travessia por propriedade; evidência identificável e pertinente ao alvo; separação entre recuperar, padronizar, calcular, interpretar, inferir e solicitar decisão; verificador de suporte; motivos estruturados de abstenção; invalidação por revisão/catálogo.

**Primeiro aprofundamento:** uma recuperação direta, uma normalização, uma inferência delimitada e um caso sem solução; incluir conflitos e distratores. Alumínio no caixilho não prova material do vidro; espessura global não prova espessura de componente; proximidade não prova conexão; uso residencial não determina resistência do concreto ou método de execução.

**Entradas/saídas:** consome catálogo e evidências IFC; produz propostas, conflitos e abstenções para revisão; nunca escreve o IFC. Runtime, cancelamento e limites são acordados com a frente 6; a 7 mede o ganho incremental.

### Frente 4 — Interface visual 3D e revisão por elemento

**Objetivo:** permitir decisão compreensível, acessível e rastreável. Pergunta: como reduzir esforço sem aumentar aceites incorretos?

**Reaproveitar/adaptar:** [app Streamlit](../../src/ui/app.py), [cards](../../src/ui/components/issue_card.py), [dashboard](../../src/ui/components/dashboard.py), [filtros/ações em lote](../../src/ui/components/filters.py), [sidebar/exportação](../../src/ui/components/sidebar.py), [IssueStore](../../src/suggestion_engine/issue_store.py) e [modelos de revisão](../../src/foundation/review.py).

**Lacunas:** implementação da fila por elemento, visualizador 3D, correspondência entre identidade semântica e malhas, lista incluindo elementos sem geometria, persistência/retomada e decisões por campo vinculadas à revisão correta.

**Primeiro aprofundamento:** seleção sincronizada lista/3D, antes/depois, evidências e conflitos, alcance de alteração no tipo, aceite/correção/encaminhamento BCF, proposta obsoleta e operação por teclado. Cor e manipulação 3D não podem ser os únicos meios de revisão.

**Entradas/saídas:** consome resultados da 2 e propostas da 3; envia decisões à 5; usa sessão/papéis da 6 e instrumentação da 7. Nonato participa parcialmente; integração UI/processamento é apenas recorte sugerido. Stack definitiva permanece aberta.

### Frente 5 — Exportação IFC/BCF e novas revisões

**Objetivo:** entregar somente alterações aprovadas e continuar o ciclo entre revisões. Pergunta: como demonstrar integridade do delta e evitar transferência indevida de decisões?

**Reaproveitar/adaptar:** [writer IFC](../../src/writer/ifc_writer.py), [pipeline](../../src/pipeline.py), [PostValidator](../../src/validation/post_validator.py), [BCFExporter](../../src/bcf/exporter.py) e [AuditLogger](../../src/audit/logger.py).

**Lacunas:** plano de alterações com pré-condições, cópia de trabalho separada da evidência original, publicação controlada, diff semântico, manifesto de saída, BCF residual com identidade/viewpoint e comparação entre revisões.

**Primeiro aprofundamento:** original com hash preservado; zero ou parte das mudanças aprovadas; alteração no tipo; falha durante aplicação; reabertura e revalidação da cópia; pendências existentes versus regressões introduzidas; GlobalIds mantidos, alterados, duplicados e removidos. Correspondência incerta exige nova revisão humana.

**Entradas/saídas:** recebe decisões explícitas da 4 e operações/validação da 2; produz IFC, auditoria, relatório, manifesto e BCF. Requer governança da 6. Compatibilidade BCF precisa de ensaio na ferramenta receptora escolhida.

### Frente 6 — Infraestrutura institucional e governança

**Objetivo:** execução interna, reproduzível e recuperável. Pergunta: como provar o limite de localidade e a continuidade das decisões após falhas?

**Responsável principal confirmado:** Nonato.

**Reaproveitar/adaptar:** [configuração](../../src/config.py), [política de localidade](../../src/foundation/locality.py), [adaptadores](../../src/foundation/adapters.py), [auditoria](../../src/audit/logger.py), [MCP HTTP](../../src/mcp_server/http_server.py), [inventário Windows](../../src/experiment/windows_inventory.py), [runtime Windows](../../src/experiment/windows_runtime.py), [model locks](../../src/experiment/model_lock.py), [evidence bundle](../../src/experiment/evidence_bundle.py) e [builder Windows](../../scripts/build_windows_release.py).

**Lacunas:** aplicação transversal da política; ativos e modelos disponíveis internamente; armazenamento durável; isolamento de projetos/sessões; papéis de operador/curador/aprovador; retenção; backup/restauração; inventário de componentes/licenças; dimensionamento de recursos.

**Primeiro aprofundamento:** inventário de destinos e dependências, instalação representativa, operação sem acesso externo, falha do LLM, interrupção, falta de recursos e restauração. Separar dados originais de derivados regeneráveis.

**Interfaces:** transversal às outras seis frentes. Implantação multiusuário depende de capacidade e autorizações institucionais; não está automaticamente entregue por existir um servidor HTTP.

### Frente 7 — Avaliação científica

**Objetivo:** demonstrar em quais condições o sistema melhora correção sustentada, abstenção ou esforço de revisão. Pergunta: qual benefício existe sobre regras e trabalho manual, em casos independentes?

**Reaproveitar/adaptar:** [runner](../../src/experiment/runner.py), [avaliador](../../src/experiment/evaluator.py), [métricas](../../src/experiment/metrics.py), [identidade de execução](../../src/experiment/execution_identity.py), [resultados por issue](../../src/experiment/per_issue.py), [revisor simulado](../../src/experiment/reviewer.py), [política de GT](../../src/experiment/ground_truth_policy.py), [validação de GT](../../src/experiment/ground_truth_validation.py) e datasets existentes.

**Lacunas:** protocolo para suporte e abstenção, gabarito especializado independente, casos indeterminados, projetos externos ao ajuste, comparação determinística forte, estudo humano real e análise de revisões.

**Primeiro aprofundamento:** separar dado literal recuperável, valor artificialmente oculto, cálculo com premissas, hipótese e decisão técnica não tomada. Manter quase duplicatas/revisões no mesmo grupo de partição. Não usar milhares de ocorrências equivalentes como milhares de observações independentes.

**Comparações prioritárias:** regras sem LLM; LLM com contexto mínimo; mesmo LLM com contexto por propriedade; verificação de suporte/abstenção; revisão manual e assistida. Documentos adicionais só entram como braço próprio se aprovados.

**Métricas separadas:** cobertura por entrada, correção de valor/unidade/alvo, suporte verificável, recuperação útil, afirmação indevida em caso sem solução, abstenção em caso solucionável, conformidade formal, erro aprovado por humano, tempo ativo e recursos. Denominadores e unidade de análise devem ser explícitos.

Felipe coordena a pesquisa. Nonato participa parcialmente; automação/coleta/reprodutibilidade são recortes propostos. O revisor simulado existente não comprova benefício ou segurança de revisão humana real.

## 8. Arquitetura base proposta e contratos comuns

**Proposta:** manter o repositório e uma aplicação modular, evoluindo por interfaces verificáveis. As sete frentes não exigem sete serviços, bancos ou diretórios espelhados. O fluxo básico já existe e deve ser reaproveitado.

O Python continua como referência semântica da base existente. Eventual frontend novo pode ser isolado no mesmo repositório após ensaio de identidade, recursos, offline, manutenção e licença. IfcTester, TypeScript e That Open mencionados no plano anterior continuam candidatos a investigar; não foram adotados, instalados ou validados nesta etapa.

Fluxo lógico proposto:

```text
Catálogo versionado → leitura IFC / requisitos IDS → contexto e propostas
                                               ↘ revisão por elemento
Propostas + evidências → decisão humana → cópia IFC + diff + revalidação
                                                      ↘ relatório / BCF
Nova revisão IFC → comparação e invalidação → nova revisão humana

Infraestrutura/governança sustentam todo o percurso.
Avaliação científica observa resultados, suporte, revisão e recursos.
```

Contratos existentes estão em [src/foundation/contracts.py](../../src/foundation/contracts.py). Os testes em [tests/foundation/test_contracts.py](../../tests/foundation/test_contracts.py) verificam forma e regras pontuais; não certificam conformidade operacional de todos os módulos.

| Registro a aprofundar | Conteúdo mínimo proposto |
|---|---|
| Revisão do modelo | Identidade, hash original, schema, exportador, origem, instante |
| Elemento | Revisão, ID do parser, GlobalId quando disponível, unicidade, vínculo visual |
| Referência semântica | Catálogo/versão, namespace, conceito, caminho, aplicabilidade, tipo/unidade |
| Evidência | Revisão, entidade/caminho, bruto/normalizado, unidade, ocorrência/tipo/componente, relações, método |
| Validação | Execução/verificador, requisito, população aplicável, esperado/observado e estado explícito |
| Proposta | Campo, valor anterior/candidato, método, evidências, transformações, conflitos e abstenção |
| Decisão humana | Proposta/campos escolhidos, revisor, ação, valor efetivo, instante, justificativa e alcance |
| Alterações | Decisões aprovadas, origem esperada, valores anteriores, operações e resultado |
| Saída | Hashes, catálogo/IDS, mudanças, revalidação, pendências, BCF e limitações |

Não fundir estado do dado, estado da geração, decisão humana e resultado da aplicação. Zero e `False` podem ser válidos; não são marcadores universais de desconhecido. Aprovar catálogo e aprovar um valor de elemento são ações diferentes.

## 9. Achados técnicos para backlog funcional separado

Os itens abaixo resultam de leitura estática e inspeção de testes. Não foram reproduzidos executando o programa nesta sessão. Registrar não significa corrigir nesta reorganização.

| ID / prioridade | Evidência e implicação | Aceite/teste futuro proposto |
|---|---|---|
| B01 — Alta | [ids.xsd](../../data/ids_schema/ids.xsd), linha 3, declara placeholder; estrutura permissiva. O parser reduz enumerações à primeira alternativa e não preserva todo o contrato de aplicabilidade/cardinalidade | Fixar schema oficial e versão; corpus positivo/negativo; múltiplas enumerações, cardinalidade, limites e recursos não suportados; validar templates locais |
| B02 — Alta | [rule_generator.py](../../src/translator/rule_generator.py) admite retorno positivo para certos operadores/checks desconhecidos. [PostValidator](../../src/validation/post_validator.py), linhas 77–99, pode tratar validação de schema indisponível como aviso e manter aprovação. `_integrate_ids()` captura erro e continua | Falha de schema, IDS inválido, zero aplicáveis e recurso desconhecido devem ter estados próprios, sem aprovação implícita |
| B03 — Alta | [pipeline.py](../../src/pipeline.py), `apply_correction`, mantém alteração/aceite após pós-validação falhar; exportação salva sem nova validação integral. [Teste atual](../../tests/test_pipeline.py), linha 438, exige status accepted nesse cenário | Impedir publicação como validada após falha. Distinguir regressão introduzida de pendências anteriores e acordar política de cópia parcial |
| B04 — Alta | Pipeline usa `top_suggestion` para proveniência/confiança; a [UI](../../src/ui/app.py) pode encaminhar valor de outra opção sem sua identidade | Aceitar segunda opção e editar manualmente; auditoria deve identificar proposta efetiva, origem, valor e evidências corretos |
| B05 — Alta | [BCFExporter](../../src/bcf/exporter.py) usa GUID do elemento em `IfcProject`, não gera viewpoint e fecha todo estado diferente de pending. [Testes](../../tests/test_bcf_exporter.py) verificam o próprio formato emitido | Pendências puladas/rejeitadas/adiadas continuam abertas quando requisito falha; conferir projeto/componente, versão BCF, schema e ferramenta receptora |
| B06 — Alta | Pipeline instancia Ollama/bSDD diretamente; política da fundação ainda não é aplicada transversalmente. [styles.py](../../src/ui/styles.py) usa Google Fonts; app usa jsDelivr; runtime Windows contém downloads públicos | Percurso com acesso externo indisponível e observação de tentativas de conexão; falha de LLM sem fallback e sem perda de revisão |
| B07 — Alta | [pset_resolver.py](../../src/translator/pset_resolver.py) aceita aliases e outros Psets. Isso auxilia recuperação, mas pode mascarar divergência do caminho exigido no IDS. Escrita precisa explicitar ocorrência/tipo | Propriedade fora do caminho formal gera falha e eventual proposta de normalização; testar conflitos, herança e alcance de escrita no tipo |
| B08 — Média/alta | [QuantityExtractor](../../src/ifc_analyzer/extractors/quantity_extractor.py), linhas 95–110, usa bounding box para volume e áreas, inclusive campos líquidos | Testar rotação, aberturas e formas irregulares; distinguir estimativa de quantidade declarada, com unidade, método e limites |
| B09 — Alta para implantação | [MCP HTTP](../../src/mcp_server/http_server.py) permite acesso sem token quando não configurado, CORS amplo e host padrão `0.0.0.0`; [server.py](../../src/mcp_server/server.py) mantém `_session` global | Política de acesso e isolamento entre projetos/sessões antes de anunciar operação multiusuário |
| B10 — Alta para pesquisa | [GT policy](../../src/experiment/ground_truth_policy.py) exige valor concreto; referências incluem hipóteses congeladas; [revisor](../../src/experiment/reviewer.py) é simulado. Identidade experimental atual fixa datasets casa/prédio | Novo protocolo para casos indeterminados, gabarito independente e projetos adicionais; preservar histórico e medir revisão humana real separadamente |

Outras lacunas de contrato relevantes:

- `ReviewDecision` atual não vincula a decisão à revisão do modelo, ao catálogo e ao valor anterior; `edited_value` é texto. A evolução deve contemplar valores tipados e pré-condições.
- `ElementReviewQueue` é protocolo sem implementação nesta entrega da fundação.
- `IssueStore` e `AuditLogger` mantêm estado em memória; cache de sugestões em SQLite não equivale a persistência durável de uma revisão humana.
- Na UI atual, Pular e Revisão posterior convergem para `skipped`; filtros/busca foram desativados em `filters.py`; aceite em lote seleciona top-1 por confiança alta. O novo fluxo exige revisão desse desenho.
- O [denominador de readiness](../dividas-tecnicas.md) já é dívida registrada: não representa número real de checks. Não tratá-lo como certificado de conformidade.
- O [material_reader](../../src/ifc_analyzer/material_reader.py) contém decisões de associação por ordem/nome e herança de partes que exigem proveniência e testes de conflito antes da generalização.

Catálogo completo, visualização 3D, persistência e comparação de revisões são capacidades ainda planejadas, não defeitos de funcionalidades anteriormente entregues.

## 10. Preservação do instrumento científico

**Confirmado:** `PROMPT_VERSION v7.8` é instrumento de medição e não será alterado silenciosamente.

Pinos existentes:

- [src/suggestion_engine/prompt_templates.py](../../src/suggestion_engine/prompt_templates.py), linha 111.
- [scripts/build_windows_release.py](../../scripts/build_windows_release.py), linha 25.
- [windows/install.ps1](../../windows/install.ps1), validação de `v7.8`.

A [condição v7.8](../condicao-v7-8-2026-08-19.md) registra que v7.7 é o instrumento das rodadas publicadas ali citadas e que a execução de v7.8 estava pendente naquele documento. Nenhuma rodada foi executada nesta leitura.

Mudança futura de prompt, contexto apresentado, catálogo, comparador, GT, modelo, quantização, parâmetros ou reutilização precisa de identidade e condição experimental explícitas. Mesmo sem alterar o texto-base do template, mudar evidência enviada pode mudar o instrumento efetivamente avaliado.

Preservar GTs, hashes, locks, resultados e emendas históricas. A política antiga de referência completa não deve ser silenciosamente reinterpretada como protocolo de abstenção. Estudos novos terão hipóteses, denominadores, partições e critérios de anotação próprios.

## 11. Organização posterior e sequência de integração

### O que foi autorizado para agora

Persistir esta consolidação em `docs/planejamento`, reler e verificar links. Não é necessário aguardar arquitetura perfeita ou sete planos extensos. Não há autorização nesta etapa para aplicar B01–B10.

### Proposta de reorganização documental posterior

| Origem | Destino/ação sugerida |
|---|---|
| Entrada dispersa do projeto | Criar `README.md` e `docs/README.md` com mapa e limites atuais |
| Inventário desta consolidação | Eventualmente separar em `docs/inventario/2026-10-09-base-verificada.md` |
| Arquitetura proposta | Eventualmente separar em `docs/arquitetura/base-do-projeto.md` |
| Decisões e backlog | Eventualmente separar em `docs/planejamento/decisoes.md` e `backlog-tecnico.md` |
| Sete frentes | Criar um plano por frente após a discussão do módulo, ligado ao índice de planejamento |
| CLAUDE.md / PROJECT_CONTEXT.md / fundação semântica | Preservar caminhos e acrescentar pontes datadas, quando a reorganização for aplicada |
| Planos antigos, condições, resultados, migração e pareceres | Preservar caminhos e indexar como histórico |
| src / tests / scripts / windows / data / references / Artigo | Preservar na primeira reorganização; não mover para espelhar artificialmente sete frentes |

Os caminhos futuros da tabela não são arquivos já criados. Este documento permanece a fonte consolidada até eventual redistribuição explícita, com links de continuidade.

### Dependências e entregas verticais

| Entrega | Dependências e demonstração esperada |
|---|---|
| Base documentada | Inventário, decisões e mapa das sete frentes acessíveis no repositório |
| Contratos e suporte | Identidade de revisão, versão do catálogo, estados de validação e decisões de escrita acordados entre 1/2/4/5/6 |
| Primeira fatia completa | Catálogo local → IFC/IDS → evidência/proposta ou abstenção → revisão → cópia revalidada/BCF; instrumentação da 7 desde o início |
| Expansão sistemática | Famílias A.1–A.10, cada entrada com semântica, aplicabilidade, tratamento, apresentação e teste ou bloqueio explícito |
| Revisões e robustez | Comparação de novo IFC, invalidação, BCF receptor, retomada, backup e execução local |
| Avaliação e consolidação | Protocolo/corpus congelados, comparações prioritárias, revisão humana e limites de generalização |

As três cadeias críticas são significado (curadoria → catálogo → receita), integridade (revisão → evidência → decisão → cópia → revalidação) e pesquisa (casos → gabarito → partições → comparações). A frente 7 começa junto da base; não deve esperar o software ficar pronto.

### Primeiro ciclo executável após esta consolidação

1. Revisar a consolidação e priorizar ambiguidades dos contratos e os achados B01–B07 que afetam a primeira fatia.
2. Acordar versões e estados de validação, sem anunciar suporte ainda não testado.
3. Aprofundar catálogo local, identidade/leitura IFC e decisão/aplicação como fronteiras integradas.
4. Selecionar nos casos reais uma família arquitetônica e um caso estrutural manejáveis; usar fixtures sintéticas identificadas quando necessário.
5. Definir testes de recuperação, normalização, inferência delimitada, conflito, abstenção, revisão e saída.
6. Só então implementar a fatia por incrementos revisáveis, preservando o histórico experimental.

### Branches e PRs

- **Confirmado:** `feat/semantic-foundation` é a branch de integração indicada.
- **Confirmado:** trabalho futuro por módulo/branch e PR, com revisão; sem merge automático.
- **Pendente:** destino final dos PRs, incluindo relação entre integração e main, precisa de decisão explícita. Não deduzir esse destino da existência da branch de integração.
- **Verificado:** o repositório local não tem remote configurado. Configurar/publicar remote não faz parte desta documentação.
- **Nesta etapa:** nenhum commit, staging, push, merge, criação de branch ou alteração de Git.
- Separar futuramente PR documental/mecânico, correções de comportamento e mudanças do instrumento científico. Os testes atuais que codificam comportamentos inadequados precisam de revisão explícita, não apenas manutenção de uma suíte verde.

## 12. Marcos relativos e estimativas

O roteiro anterior de oito meses permanece um cenário ilustrativo de continuidade:

| Período relativo | Marco ilustrativo |
|---|---|
| Mês 1 | Inventário, contratos, curadoria inicial e protocolo científico |
| Mês 2 | Primeira fatia completa com catálogo local, revisão e saída |
| Meses 3–4 | Expansão rastreada da base A.1–A.10 |
| Mês 5 | Revisões IFC, interoperabilidade BCF e robustez operacional |
| Mês 6 | Experimentos controlados |
| Mês 7 | Estudo humano e piloto institucional, conforme condições disponíveis |
| Mês 8 | Consolidação, documentação e versão de pesquisa |

Não há carga semanal, início operacional ou prazo acadêmico final confirmados. O roteiro não é compromisso de duração. Reestimar depois do aprofundamento dos módulos e da primeira fatia, considerando curadoria especializada, hardware, disponibilidade e dependências reais.

Em termos relativos, o incremento documental é pequeno diante das frentes funcionais. Identidade/validação, curadoria completa, revisão 3D, integridade de saída e avaliação independente são trabalhos maiores, com riscos distintos. Não atribuir horas ou somar estimativas de módulos antes de discutir escopo e capacidade. A menor disponibilidade não autoriza retirar silenciosamente classes ou testes críticos do compromisso final.

## 13. Decisões abertas

1. Disponibilidade semanal, competências e prazo acadêmico de Felipe/Nonato.
2. Liderança de implementação das frentes 1, 2, 4 e 5; recortes parciais de Nonato em 4 e 7.
3. Hardware de desenvolvimento/ensaio e infraestrutura que poderá ser usada no IME.
4. Versões IFC/IDS, facetas, exportadores e ferramentas receptoras de BCF exigidas na primeira versão.
5. Stack visual e estratégia de geometria, após ensaio; sem mudança automática de stack.
6. Quem aprova reconciliações semânticas, medições e decisões técnicas de maior risco.
7. Política de pendências bloqueantes, cópia parcial e tratamento de regressões de validação.
8. Alcance permitido de escrita em tipos e apresentação das ocorrências afetadas.
9. Papéis, retenção, backup, acesso e eventual concorrência multiusuário.
10. Inclusão de documentos externos, dependente do orientador.
11. Especialistas, projetos independentes e participantes para gabarito e estudo humano.
12. Formulação e prioridade das perguntas científicas e das métricas de suporte/abstenção/esforço.
13. Destino final dos PRs e posterior publicação do trabalho.

Essas pendências não impedem a consolidação documental. Impedem declarar prazo fechado, catálogo aprovado, stack definitiva, conformidade completa ou generalização científica antes das respectivas evidências.

## 14. Referências locais e limites desta entrega

### Base e arquitetura

- [CLAUDE.md](../../CLAUDE.md)
- [PROJECT_CONTEXT.md](../../PROJECT_CONTEXT.md)
- [Fundação semântica de 08/10](../arquitetura/fundacao-semantica.md)
- [Proveniência da migração](../migracao/PROVENIENCIA-2026-10-08.md)
- [Contratos](../../src/foundation/contracts.py), [localidade](../../src/foundation/locality.py), [revisão](../../src/foundation/review.py) e [testes de contratos](../../tests/foundation/test_contracts.py)

### Histórico científico e planejamento

- [Plano consolidado de junho](../plano-consolidado-2026-06-09.md)
- [Plano de orquestração de junho](../plano-orquestracao-2026-06-25.md)
- [Avaliação crítica de setembro](../AVALIACAO_CRITICA_PESQUISA_2026-09-09.md) — arquivo preexistente não rastreado, preservado
- [Dívidas técnicas](../dividas-tecnicas.md)
- [Condição v7.8](../condicao-v7-8-2026-08-19.md)
- [Emenda do ground truth](../emenda-gt-2026-08-12.md)
- [Definição de métricas](../metricas-avaliacao.md)
- [Fontes normativas públicas: política e limites](../../references/normative/public/README.md)

Os documentos históricos podem conter escopos ou estados posteriormente modificados. Devem ser lidos com suas datas e condições; sua preservação não reafirma todas as afirmações como estado atual.

**O que esta entrega efetivamente faz:** registra em Markdown as decisões recebidas e a análise da base existente. Não altera implementação, prompt, configurações, dados ou resultados. Não grava fora do repositório e não toca a pasta legada nem os registros externos de migração.

**Verificação prevista para a própria documentação:** reler o arquivo criado, conferir existência dos destinos dos links relativos e conferir o estado Git, preservando a alteração local e os itens não rastreados anteriores. Não executar suíte funcional, benchmark, instalação ou build como parte desta consolidação.
