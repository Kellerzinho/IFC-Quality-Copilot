# Planejamento atual

**Atualização:** 12 de outubro de 2026. **Origem:** decisões confirmadas por Felipe
em 8–12/10, integração bibliográfica de 10/10 e consolidação documental M3 autorizada depois.

## Ordem de leitura e precedência

1. [Consolidação de 09/10](CONSOLIDACAO-2026-10-09.md): inventário e registro original preservados.
2. [Decisões posteriores de 09/10](#decisoes-posteriores-de-0910): complementos confirmados após a gravação.
3. [Mapa das sete frentes](mapa-sete-frentes.md): responsabilidades, interfaces e base existente.
4. [Arquitetura base](../arquitetura/base-do-projeto.md): relação entre componentes atuais e evolução pretendida.
5. [Plano do módulo 1 — Domínio e catálogo](modulo-01-dominio-catalogo.md): modelo, curadoria, fontes, contratos, 18 tarefas, testes e entregas propostos; nenhuma implementação executada.
6. [Plano do módulo 2 — Núcleo IFC/IDS](modulo-02-nucleo-ifc-ids.md): leitura/verificação sem mutação, identidade, facetas/cardinalidade, estados, diagnóstico/exportação independente de LLM, 18 tarefas e 32 casos propostos.
7. [Módulo 3 — Contexto e enriquecimento](modulo-03-contexto-enriquecimento.md): **planejamento concluído e verificado, sem pendência de aprovação de Felipe; implementação não concluída**. [Apoios](../pesquisa/modulo-03-contexto/README.md) com 203 registros alfanuméricos + 110 auxiliares, fonte/operação separadas, JSON/CSV e critérios por registro; políticas atuais de bSDD, manual e roteamento.
8. [Síntese bibliográfica dos 29 artigos de Daiane](../pesquisa/sintese-bibliografica-daiane-29-artigos.md): nova integração autorizada em 10/10 nos três planos, com referências originais/correções, páginas, níveis de evidência e matrizes por módulo. Na pesquisa de origem: 27 integrais e dois resumos/metadados. A integração de 10/10 não aprovou M3; a consolidação posterior tem status próprio no plano, sem validar a combinação LLM local.

Decisões mais recentes explicitamente confirmadas prevalecem no planejamento.
A consolidação mantém seus bytes e seu histórico. Propostas de brainstorming
só entram como decisões depois de confirmadas; o debate paralelo do módulo 1
não autoriza incorporar automaticamente todas as propostas dessa conversa.

<a id="decisoes-posteriores-de-1210"></a>

## Decisões posteriores de 12/10 — precedência vigente

A [consolidação M3](modulo-03-contexto-enriquecimento.md#m3-decisoes) registra a autorização
de concluir o planejamento após verificação, sem nova rodada de aprovação. Os planos M1/M2
e a consolidação de 09/10 permanecem preservados; quando seus textos anteriores divergirem,
prevalecem aqui: **API pública bSDD inicialmente**, consultando só semântica pública sem
dados de projeto; estudo de armazenamento integral local futuro; inferência, evidências,
histórico e processamento locais/IME. Bindings/receitas continuam curados e versionados.

Conflitos mostram valores/fontes e exigem decisão fundamentada. Há preenchimento manual
com rechecagens antes de aprovação e BCF residual. M2 valida requisitos suportados mesmo
sem mapping; M3 não deixa LLM publicar equivalência. Requisito inadequado pede revisão do
requisito. Uma inferência por vez no baseline; agrupamentos e roteamento por campo/grupo
serão comparados no desenvolvimento segundo M7/M6, sem eleger modelo vencedor no plano.

Felipe conduz **M1/M2/M3/M5**; Nonato **M4/M6** e lidera **M7**, com ajuda de Felipe.
A matriz PDF/ZIP foi reconciliada em 203 + 110 registros. XML/planilha/fixtures ausentes
e síntese Library ainda não acessível são pendências delimitadas de desenvolvimento,
não impedimento para concluir a documentação. Planejamento M4 autorizado em tarefa separada.

**Decisão M4 posterior de 12/10, que substitui o extra federado de D17:** MVP com dois
pares IFC–IDS (arquitetura e estrutura), visualização federada prioritária e mesma sessão.
Identidade, diagnóstico, evidência e exportação permanecem separados por arquivo; não há
evidência cruzada entre arquivos no MVP. M3 processa por modelo, com uma fila LLM serial
para a sessão. Stack M4: React/TypeScript/Vite/shadcn e API Python; That Open é candidato.
M1/M2 preservam seus registros anteriores; esta decisão posterior define a precedência.

<a id="decisoes-posteriores-de-0910"></a>

## Decisões posteriores de 09/10

| Registro | Decisão confirmada | Consequência para o planejamento |
|---|---|---|
| D01 — Entrada IDS | Inicialmente o operador fornece um IDS pronto; autoria de IDS pela UI fica fora do escopo inicial | Planejar importação, leitura, validação e estados de suporte; não incluir editor ou gerador de IDS nesta primeira entrega |
| D02 — Requisitos sem cadastro | IDS pode conter propriedades desconhecidas pelo catálogo; requisitos suportados devem ser validados independentemente do cadastro | Separar validação formal e mapeamento semântico; explicitar campos sem mapeamento e não preenchê-los automaticamente por equivalência inventada |
| D03 — Publicação do catálogo | Operador pode solicitar novos mapeamentos; somente curador aprova e publica uma versão; LLM pode sugerir correspondência sem cadastrá-la automaticamente como verdade | Distinguir solicitação, proposta e publicação aprovada; implementação de papéis e fluxo ainda será planejada |
| D04 — Perfil e extensão | Perfil inicial inclui `EB_Orçamento` fiel/reconciliado à dissertação, sem substituição silenciosa por `Cost_Prop`; cadastro/extensão de propriedades deve ser acessível pela plataforma | Preservar fonte e reconciliação; nova linha cadastral não implementa operação de extração/inferência nem altera IDS/IFC silenciosamente |
| D05 — Direção da curadoria visual | Tabela editável com detalhamento foi aprovada como direção; o escopo posterior do plano inclui adicionar/duplicar linha | Layout e interação serão detalhados; duplicação cria rascunho sujeito à revisão de identidade e publicação |
| D06 — Autoria IDS futura | Autoria/criação de IDS será um módulo futuro previsto, com aprofundamento posterior | Manter IDS pronto no escopo inicial; vincular a extensão às frentes 1, 2 e 4 sem renumerar as sete frentes |
| D07 — Conceito e uso | Separar definição, aplicabilidade e evidências, reutilizando o conceito quando o significado for o mesmo | Evitar duplicação por classe sem fundir significados distintos; estrutura concreta será aprofundada no módulo 1 |
| D08 — Versão por projeto | Fixar a versão do catálogo por projeto; atualizar explicitamente com diff e reprocessamento, preservando históricos rastreáveis | Atualização não é silenciosa; mecanismo e alcance do reprocessamento serão detalhados no plano |
| D09 — Extensão sem código | Cadastrar usando operações suportadas; novas extrações/cálculos exigem implementação e ficam sem enriquecimento até então | Cadastro não cria executor; explicitar a capacidade ainda indisponível e preservar a validação dos requisitos suportados |
| D10 — Fontes originais | Buscar com Juliana o IDS original de dez especificações e a planilha editável; enquanto isso, estruturar a base pelos apêndices com divergências pendentes | Obtenção e conferência ainda pendentes; não substituir `EB_Orçamento` por `Cost_Prop` nem presumir equivalência entre versões |
| D11 — Prosseguimento parcial | Após checar arquivos, prosseguir com requisitos suportados e limitações explícitas; bloquear arquivos ilegíveis/inválidos quando impedirem interpretação confiável; não verificado nunca é aprovado | Planejar estados de execução e limites claros na frente 2, sem implementar essa política nesta revisão |
| D12 — Categorias de resultado | Separar problemas técnicos (ilegibilidade, incompatibilidade, não suportado), falhas de requisitos IDS e alertas complementares fora do IDS | Alerta complementar não é resultado de conformidade formal; preservar as três categorias na apresentação e na interpretação |
| D13 — Navegação do diagnóstico | Visão principal por elemento e alternativa por requisito, com esperado, encontrado e origem | Preservar requisito sem elementos aplicáveis na visualização; detalhe de UI ainda será planejado |
| D14 — Identidade da análise | Cada análise está vinculada às versões exatas de IFC, IDS e catálogo; mudanças geram nova análise, mantendo histórico | Não sobrescrever análises nem reutilizar decisões/cache sem verificar a identidade das entradas |
| D15 — Estados de validação | Conforme, não conforme, não aplicável, não verificado e erro são distintos; ausência de elementos deve seguir cardinalidade/exigência do IDS | Lista vazia não aprova automaticamente; mostrar ausência e fundamento da interpretação |
| D16 — Leitura sem mutação | Módulo 2 somente lê/verifica, sem criar propriedades ou alterar valores IFC | Propostas de enriquecimento e escrita posterior com revisão humana pertencem a outras etapas |
| D17 — Análise individual e extra federado | Primeira entrega com análise individual; visualização conjunta de vários IFCs fica como extra posterior, integrado à frente 4, com arquivos e saídas separados | Prever identidade arquivo/revisão/elemento, alinhamento e proveniência; não fundir arquivos nem restringir definitivamente projeto a um IFC |
| D18 — Metas de schemas | IFC2X3, IFC4 e IFC4.3 como metas, com suporte anunciado por capacidade testada, caso real e fixtures | Testar leitura/validação/visualização/escrita separadamente e fixar releases; não ampliar domínio para infraestrutura nem presumir suporte instalado |
| D19 — Diagnóstico independente | Validar e exportar diagnóstico sem depender de enriquecimento/LLM; resultado completo rastreável na plataforma e relatório exportável | BCF da frente 5 consome o mesmo diagnóstico; formatos, limites e timing serão definidos por ensaios |


D07–D10 foram confirmadas em conjunto por Felipe em 09/10, às 13:47, conforme
mensagem recebida. Substituem os estados anteriores de proposta para esses
pontos. D11 foi confirmada explicitamente às 13:52. O detalhamento técnico dos
módulos continua posterior. D12 foi confirmada explicitamente às 13:53.
D13 foi confirmada no escopo do plano do módulo 1. D14 foi confirmada às 13:59,
D15 às 14:00, D16 às 14:06, D17 às 14:15, D18 às 14:17 e D19 às 14:18,
conforme mensagens recebidas. Esses registros descrevem metas e comportamento
acordados, sem atestar implementação ou suporte já verificado.

A busca com Juliana é encaminhamento confirmado, não contato realizado nem
arquivo obtido nesta revisão.

**Evidência relatada pela pesquisa paralela, sem reinspeção nesta aplicação:** o
pacote público Daiane 2026, registro Zenodo `19150057`, contém `IDS_Cost.ids` com
seis especificações de arquitetura, IFC4 e `Cost_Prop`. Sua fonte e versão são
distintas da dissertação de 2025 com dez famílias A.1–A.10 e `EB_Orçamento`.
O arquivo público não comprova a cobertura integral do piso arquitetura e
estrutura. O levantamento de 195 entradas na consolidação é relato do plano
anterior; a curadoria e a reconciliação continuam necessárias.

<a id="extensao-futura--autoria-ids"></a>

## Extensão futura — Autoria IDS

**Confirmado por Felipe em 09/10, às 13:42 conforme mensagem recebida:** autoria
e criação de IDS serão um módulo futuro previsto, a aprofundar depois. O escopo
inicial continua recebendo IDS pronto. A extensão se vincula à frente 1
(catálogo), à 2 (validação) e à 4 (interface), sem criar uma oitava frente.

Reutilizar catálogo, selecionar classes/aplicabilidade/requisitos e validar ou
exportar IDS são direções propostas para esse aprofundamento, não detalhamento
fechado. Cadastrar uma propriedade no catálogo não a torna requisito obrigatório
automaticamente. Catálogo e instrumento IDS fornecido são distintos. Nenhuma
interface ou função de autoria IDS é implementada nesta organização documental.

## Sequência de trabalho

1. Organizar a base documental e mapear as sete frentes a partir do repositório.
2. Debater cada módulo e produzir seu plano verificável com escopo confirmado.
3. Implementar incrementos delimitados, verificar e revisar.

A organização documental anterior reuniu cinco documentos novos e três ajustes
pontuais. O plano extenso do módulo 1 acrescenta uma proposta implementável e
atualiza a navegação e as decisões posteriores, mantendo caminhos de código e
o registro consolidado. O plano completo do módulo 2 foi elaborado em seguida,
com inventário real, contratos consistentes com o módulo 1 e critérios de suporte
por capacidade. Ambos são entregas documentais; implementação depende de etapa
própria autorizada. O módulo 3 recebe consolidação posterior em 12/10, com fonte
reconciliada, políticas atuais e critérios individuais. Conclusão documental não significa
implementação concluída. Nenhuma ação no Todoist é feita nesta etapa. As sete
frentes são uma organização do trabalho, sem decisão de criar sete serviços.
Achados B01–B10 permanecem no backlog funcional da consolidação.

## Responsabilidades confirmadas

| Frente | Responsabilidade | Detalhes abertos |
|---|---|---|
| 1 — Domínio e catálogo | **Felipe** | Curador e especialistas por conteúdo a designar |
| 2 — Núcleo IFC/IDS | **Felipe** | Capacidades por schema/release a ensaiar |
| 3 — Contexto e enriquecimento | **Felipe** | Interfaces, receitas e critérios no plano M3 |
| 4 — Interface e revisão | **Nonato** | Planejamento próprio; dois pares/federação visual no MVP; stack definida, fluxo visual a detalhar |
| 5 — Saídas e revisões | **Felipe** | Política de cópia/revalidação e interoperabilidade a detalhar |
| 6 — Infraestrutura e governança | **Nonato** | Recursos, operação e atribuições institucionais a detalhar |
| 7 — Avaliação científica | **Nonato lidera, com ajuda de Felipe** | Protocolo, especialistas e estudo humano a definir no desenvolvimento |

Responsabilidades atualizadas em 12/10 substituem os recortes parciais anteriores.
O papel de curador foi confirmado como autoridade de publicação; a pessoa que
o exercerá e os procedimentos de aprovação ainda precisam ser definidos.

## Assistência ao desenvolvimento neste ciclo

- Etapa 1 — estudo e handoff: **Astra high**.
- Etapa 2 — aplicação documental: **GPT-6.1 Sol high**.
- Etapa 3 — revisão da aplicação: **Astra high**.
- Etapa 4 — plano extenso do módulo 1: **Astra XHIGH**, conforme solicitação posterior; entrega documental, sem implementação.
- Etapa 5 — plano completo do módulo 2: **Astra XHIGH**, conforme solicitação de 09/10 às 14:23; entrega documental, preservando o plano 1 e a consolidação.

- Etapa 6 — consolidação e verificação documental do M3: **Astra XHIGH**, conforme solicitado; sem implementação ou escolha do LLM do produto.

Este acordo posterior especifica o ciclo atual, complementando a distribuição
registrada na consolidação. Não seleciona o LLM local do produto. A revisão documental independente Astra xhigh
e a verificação das correções M3 estão registradas no relatório dos apoios; não são
validação operacional das receitas nem pesquisa empírica nova.

## Invariantes e assuntos abertos

- `PROMPT_VERSION v7.8`, seus três pinos, GTs, comparadores, dados e resultados
  históricos preservam suas identidades. Não há nova condição experimental nesta etapa.
- Arquitetura e estrutura, Daiane, `EB_Orçamento` personalizado, catálogo provisório
  substituível por Juliana, SINAPI operacional futuro e execução local/interna
  permanecem com os complementos D01–D19 e as decisões de 12/10 acima.
- Carga semanal, prazo acadêmico, hardware, detalhes visuais, releases/capacidades
  concretas IFC/IDS, receptor BCF, política de cópia parcial e estudo humano
  continuam abertos; metas de schemas seguem D18. O extra federado de D17 foi
  substituído pela decisão M4 posterior acima, preservando processamento por arquivo.
- `feat/semantic-foundation` é a branch de integração indicada. Destino final dos
  PRs e publicação precisam de definição; não há merge automático.
- A aplicação documental não realiza staging, commit, push, merge, instalação,
  suíte funcional, mudanças de configuração ou correções B01–B10.

[Voltar ao índice documental](../README.md).
