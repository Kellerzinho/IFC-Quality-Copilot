# Módulo 4 — Interface e revisão humana

> **PLANEJAMENTO DOCUMENTAL CONCLUÍDO E VERIFICADO — 12/10/2026.**
> **Implementação, testes funcionais e ensaios técnicos não executados. Escolha visual pendente.**
> Responsável: **Nonato**. Felipe participa da conferência dos contratos e do teste de uso.

**Objetivo:** permitir que o engenheiro carregue dois pares IFC/IDS, examine arquitetura e
estrutura em uma cena federada, compreenda cada pendência e sua evidência, registre decisões
individuais ou em lote, retome o trabalho e encaminhe saídas separadas ao M5.

**Arquitetura aprovada:** aplicação para desktop com React, TypeScript, Vite e shadcn/ui,
consumindo API Python. Desenvolvimento diretamente nessa arquitetura; Streamlit deixa de
ser a UI de uso da nova versão. Processamento, experimentos e código legado permanecem
preservados para reaproveitamento criterioso. Operação inicial em localhost; IME posteriormente.

**Base de decisão:** briefing consolidado do brainstorming de voz de Felipe, recebido nesta
tarefa, e contratos vigentes de [M1](modulo-01-dominio-catalogo.md#m1-interfaces),
[M2](modulo-02-nucleo-ifc-ids.md#m2-interfaces) e
[M3](modulo-03-contexto-enriquecimento.md#m3-interfaces). Não há transcrição integral da voz
anexada a este arquivo. As decisões abaixo registram o briefing recebido, sem inventar
aprovação de biblioteca, proposta visual ou resultado experimental.

**Como executar futuramente:** ler primeiro as decisões e os contratos deste documento;
usar a skill de execução de planos aplicável ao ambiente, por tarefas com revisão verificável.
As caixas desmarcadas são trabalho futuro. Esta entrega é o arquivo de texto solicitado;
não inicia implementação, instalação, benchmark, staging, commit ou publicação.

**Precedência:** as decisões M4 de 12/10 substituem, para a nova versão, a antiga previsão de
federação como extra futuro e de stack visual ainda aberta. Os planos M1–M3, a consolidação,
os índices e o mapa de frentes foram preservados nesta tarefa. Os pontos de integração
documental estão em [Integração posterior](#m4-integracao).

**Navegação:** [Decisões](#m4-decisoes) · [Escopo](#m4-escopo) · [Inventário](#m4-inventario) ·
[Arquitetura](#m4-arquitetura) · [Contratos](#m4-contratos) · [Estados](#m4-estados) ·
[Percursos](#m4-percursos) · [Federação e 3D](#m4-3d) · [Revisão](#m4-revisao) ·
[Persistência](#m4-persistencia) · [Saídas](#m4-saidas) · [Perfis](#m4-perfis) ·
[Pesquisa e visual](#m4-pesquisa) · [Tarefas](#m4-tarefas) · [Testes](#m4-testes) ·
[Entregas e dependências](#m4-entregas) · [Riscos](#m4-riscos) · [Aceite](#m4-aceite) ·
[Integração posterior](#m4-integracao) · [Fontes e verificação](#m4-fontes).

<a id="m4-decisoes"></a>

## 1. Decisões aprovadas e escolhas ainda sujeitas a ensaio

### 1.1 Registro das decisões recebidas

| ID | Decisão aprovada no briefing | Consequência verificável |
|---|---|---|
| D4-01 | Desktop exclusivo na v1; tablet e celular futuros | Fluxo completo testado em desktop; não anunciar atendimento móvel |
| D4-02 | React + TypeScript + Vite + shadcn/ui e API Python | Nova UI nessa arquitetura; versões e framework da API ainda serão fixados |
| D4-03 | Desenvolver diretamente na arquitetura nova, retirando Streamlit do percurso de uso | Reaproveitar serviços e experimentos, preservando o legado; não fazer nova UI sobre reruns Streamlit |
| D4-04 | Localhost inicialmente; ambiente IME posteriormente | Distribuição local primeiro; acesso institucional depende de trabalho M6 |
| D4-05 | That Open é candidata, sujeita a comparação e testes | Nenhuma escolha final, licença, capacidade ou desempenho é certificado neste plano |
| D4-06 | MVP com dois pares IFC/IDS, arquitetura e estrutura no mesmo projeto; federação prioritária | Duas linhas de entrada, análise por arquivo, cena conjunta e exportações separadas na primeira entrega de uso |
| D4-07 | Análises independentes na mesma sessão; LLM serial | Falha de um modelo não bloqueia o outro; uma inferência ativa por vez no baseline |
| D4-08 | Cada IFC mantém identidade, requisitos, decisões e saídas; sem evidência cruzada entre arquivos | Chave por arquivo/revisão/elemento; teste negativo de contaminação entre os dois modelos |
| D4-09 | Confirmar vínculos disciplina–IFC–IDS antes de analisar | Associação explícita por linha, sem deduzir IDS por nome ou ordem de seleção |
| D4-10 | Coordenadas IFC iniciais, conferência visual e ajustes manuais apenas de visualização, registrados | Original/export não recebem transformação visual; nenhum detector universal de alinhamento |
| D4-11 | Dois percursos sem recarregar: validação sem LLM e revisão/enriquecimento | Alternar abas/modos conserva projeto, análises, seleção e decisões |
| D4-12 | Três áreas redimensionáveis: lista/filtros à esquerda, 3D no centro, detalhes à direita | Seleção sincronizada; valores e evidências acessíveis também pela lista |
| D4-13 | 3D funcional é requisito de qualidade; revisão por lista permanece disponível | Recuperação por lista durante falha não constitui aceite final de um viewer defeituoso |
| D4-14 | Cores por classe/status com legenda, contorno de seleção, texto e ícone | Informação não depende apenas de cor; eixo de coloração visível |
| D4-15 | Ocultar disciplinas/classes, destacar, isolar, enquadrar, cortes; modos só pendências e contexto transparente | Ações visuais reversíveis; filtro visual não altera resultado formal nem fonte |
| D4-16 | Por propriedade: atual, exigido, sugestão, evidências; aceitar, editar/preencher, rejeitar, manter pendente | Decisão por campo; valor original e candidato preservados separadamente |
| D4-17 | Manual exige fonte, justificativa e checagens; decisão registrada não significa valor gravado/revalidado | Checagens e recibos separados; sem aprovação automática por satisfazer apenas o IDS |
| D4-18 | Ver origem por campo/valor, ocorrência/tipo/componente relacionado; destacar outro elemento no 3D | Navegação de evidência mantém alvo de revisão e contexto da origem |
| D4-19 | Filtros classe/requisito/disciplina/status, contagens por arquivo/conjunto, anterior/próxima pendência e busca nome/ID/tipo | Filtros preservados; vazio por filtro distinto de zero aplicáveis; cinco estados M2 explícitos |
| D4-20 | Lote com prévia de afetados; sugestões verificadas sem conflitos; manual com motivo válido para o conjunto | Prévia identifica cada campo/alvo e exclusões; servidor verifica novamente antes de registrar |
| D4-21 | Salvar progresso com confirmação real; falha visível e edição preservada; retomar sessão; desfazer antes de exportar com histórico | Recibo durável, retomada após reinício e evento de revogação; original imutável |
| D4-22 | Topo mostra IFCs/revisões, IDSs e catálogo; nova revisão gera nova análise e preserva anteriores | Sem reaplicação silenciosa de decisões ou mudança de pin |
| D4-23 | Diagnóstico e sugestões independem de 3D carregado; falha 3D mostra aviso, repetição e diagnóstico técnico | Estado de geometria separado do estado da análise; retry não reexecuta LLM |
| D4-24 | Memória e performance devem ser testadas antes de estabelecer limites | Limites operacionais e matriz de suporte só são anunciados com ensaios reais |
| D4-25 | Pré-exportação resume elementos/campos criados ou alterados, antes/depois e pendências; M5 escreve cópia e revalida | Recebimento, escrita, revalidação e falhas aparecem como etapas diferentes, por arquivo |
| D4-26 | Perfis consulta, revisão e curadoria; servidor verifica permissões/autoria com M6 | Botão oculto não substitui autorização; ator não é texto livre enviado pelo navegador |
| D4-27 | Dados e imagens da aplicação locais, sem CDN externa obrigatória | UI, fontes, ícones, workers e ativos necessários servidos localmente no ensaio |
| D4-28 | Protótipo e teste com Felipe e Nonato no percurso completo | Aceite exige demonstração observada, registrada por cenário, com defeitos e limites |

### 1.2 Propostas técnicas, sem aprovação implícita

São propostas deste plano: adaptador de viewer desacoplado; API HTTP JSON versionada;
consulta paginada; eventos de progresso com retomada por sequência; controle de concorrência
por revisão esperada; chave idempotente; persistência transacional local; documentos
imutáveis para fontes e derivados; histórico por eventos de decisão; particionamento de
resultados/lotes por modelo; caminhos físicos listados adiante. A implementação deve
compatibilizá-las com M1/M2/M3/M5/M6, registrar alterações de contrato e testá-las.

SQLite local é uma opção coerente com os planos anteriores, não compromisso com banco
institucional. Polling ou stream de eventos, biblioteca de estado, gerenciador de pacotes,
framework da API, versões de dependências, formato de malhas e estratégia de conversão são
escolhas técnicas a medir. Este documento não anuncia suporte de um pacote não ensaiado.

A escolha entre **claro limpo**, **escuro com foco no 3D** e **painéis compactos** permanece
aberta. O arranjo de três áreas e os comportamentos aprovados valem para as três propostas.
Pesquisar e desenhar opções não equivale a aprová-las; não gerar mockups duplicados nesta tarefa.

<a id="m4-escopo"></a>

## 2. Escopo, responsabilidades e foco de revisão

### 2.1 O que compõe a v1

Projeto com dois modelos lógicos, arquitetura e estrutura, cada qual com IFC e IDS pronto
confirmados; histórico de análises por modelo; catálogo fixado por projeto; navegação conjunta
e por disciplina; diagnóstico por elemento e por requisito; revisão por campo; evidência
localizável; preenchimento manual fundamentado; lote com prévia; sessão persistente;
desfazer anterior à exportação; encaminhamento separado ao M5; interface de consulta e
curadoria do catálogo nos limites dos serviços M1.

Dois pares são o piso demonstrável do MVP, não limite permanente de projeto. O domínio
inicial continua arquitetura/estrutura. Um projeto pode estar parcialmente disponível,
por exemplo arquitetura concluída e estrutura com arquivo inválido, sem simular completude.
Receber um IDS repetido nas duas linhas é permitido apenas quando o usuário confirmar essa
associação; o resultado continua sendo duas análises distintas. Não se cria um IDS composto.

### 2.2 Limites

Tablet/celular, autoria de IDS, federação de evidências entre arquivos, detector automático
universal de alinhamento, edição de geometria IFC, incorporação automática de memoriais,
colaboração simultânea avançada e operação institucional pronta ficam fora da v1. M4 não
implementa motor IDS, receita de engenharia, publicação semântica, writer IFC ou motor de BCF.
Ele usa esses contratos e apresenta seus resultados com identidade e limites.

A meta IFC2X3/IFC4/IFC4.3 permanece, com leitura, validação, visualização e escrita verificadas
separadamente. Suporte do leitor Python não comprova suporte do viewer. Quando uma capacidade
necessária falhar, conservar diagnóstico disponível e declarar o limite; não aprovar a entrega
completa do caso que exige aquela capacidade.

### 2.3 Responsáveis e fronteiras

| Frente | Responsável vigente | Participação na entrega M4 |
|---|---|---|
| M1 — Domínio e catálogo | Felipe | Identidade, significado, mapeamento, versões, curadoria e checagens cadastrais |
| M2 — Núcleo IFC/IDS | Felipe | Ingestão/leitura imutável, diagnóstico canônico, elementos, evidência e revalidação |
| M3 — Contexto/enriquecimento | Felipe | Propostas/abstenções, fonte, conflitos, validação de candidato manual e fila serial |
| M4 — Interface/revisão | Nonato | Experiência de uso, viewer, seleção, comandos de revisão e apresentação de recibos |
| M5 — Saídas/revisões | Felipe | Prévia de operações, cópia, aplicação, revalidação acionada em M2 e BCF residual |
| M6 — Infraestrutura/governança | Nonato | Ator, acesso, isolamento, persistência, recursos, empacotamento e recuperação |
| M7 — Avaliação científica | Nonato, com Felipe | Protocolo de uso, medidas de tempo/erros/esforço e ensaios de recursos |

Curador e especialistas são papéis de domínio, não automaticamente os autores do software.
Felipe e Nonato avaliam juntos o protótipo; esse teste inicial não substitui estudo humano
independente ou certificação científica.

### 2.4 Cinco riscos que guiam a revisão

1. Mesmo GUID nos dois IFCs ou duplicado no mesmo IFC seleciona/aprova o elemento errado:
   testar identidade composta e ambiguidade, em T4-03/T4-04, tarefas M4-02/M4-05.
2. Sugestão muda durante edição ou lote: testar revisão esperada, conflito e preservação
   do rascunho, em T4-21/T4-25, tarefas M4-10/M4-11.
3. Falha entre gravação e resposta anuncia perda ou duplica decisão: testar recibo
   consultável e repetição idempotente, em T4-27, tarefa M4-12.
4. Escrever no tipo altera ocorrências fora do filtro: testar prévia integral do alcance,
   em T4-22/T4-24, tarefas M4-10/M4-11/M4-15.
5. 3D indisponível ou desalinhado gera confiança indevida: testar aviso, continuidade da
   lista e bloqueio do aceite de qualidade do caso, em T4-09/T4-13, tarefas M4-05/M4-07/M4-18.

<a id="m4-inventario"></a>

## 3. Base existente e reaproveitamento

### 3.1 Inspeção efetiva do checkout

Em 12/10/2026 foi confirmado acesso ao diretório `ifc-quality-copilot`, listagem real de
arquivos e Git na branch `feat/semantic-foundation`, com HEAD `a76c2d7`. A consulta a remotes
não retornou configuração. Havia alterações e arquivos não rastreados anteriores, incluindo
documentos e materiais de pesquisa. Não foi encontrado `AGENTS.md` nos diretórios ancestrais
consultados, na raiz, em `docs` ou em `docs/planejamento`. As orientações de `CLAUDE.md` e a
continuidade documental foram lidas. `rg` não estava disponível; a leitura usou PowerShell.

Não havia `modulo-04-interface-revisao.md` na listagem inicial. M3 estava em consolidação
concorrente autorizada. Durante a redação, a coordenação informou seu encerramento com
44/44 verificações documentais e a releitura local confirmou o cabeçalho “PLANEJAMENTO
CONCLUÍDO E VERIFICADO”, com implementação não concluída. Esta tarefa não repetiu as
44 verificações do M3 nem alterou seus apoios.

| Base inspecionada | Uso futuro possível | Limite observado/relevante |
|---|---|---|
| [UI atual](../../src/ui/app.py) e [componentes](../../src/ui/components/) | Vocabulário, casos de uso e entendimento do fluxo existente | UI Streamlit com `session_state`; não é a nova arquitetura |
| [Filtros](../../src/ui/components/filters.py) | Referência de ações atuais | `render_filters` retorna todas as issues; busca/filtros desativados; precisa de fluxo novo |
| [Estilos](../../src/ui/styles.py) | Inventário visual histórico | Importa Google Fonts; app referencia jsDelivr; não copiar dependência externa obrigatória |
| [Revisão da fundação](../../src/foundation/review.py) | Princípio de revisão humana e adaptação compatível | `ReviewDecision` usa GUID e valor editado textual; faltam arquivo/revisão, campo/alternativa exata e recibo durável |
| [Contratos da fundação](../../src/foundation/contracts.py) | Pontos de contato entre módulos | `ElementReviewQueue` é protocolo; contrato de forma não prova implementação |
| [IssueStore](../../src/suggestion_engine/issue_store.py) e [auditoria](../../src/audit/logger.py) | Eventos/status a adaptar | Estado em memória não comprova retomada após reinício |
| [Pipeline](../../src/pipeline.py) | Processamento existente e adaptadores pontuais | Não ligar botão novo diretamente a correção mutante do objeto em memória |
| [Writer](../../src/writer/ifc_writer.py), [validador](../../src/validation/post_validator.py) e [BCF](../../src/bcf/exporter.py) | Implementações a integrar através do M5/M2 | Limites B03/B05 da consolidação permanecem; não certificar escrita/BCF por sua existência |
| [Dependências Python](../../pyproject.toml) | Base Python/Pydantic e serviços existentes | A listagem inicial não continha frontend React ou API específica de revisão |
| [Testes da fundação](../../tests/foundation/test_contracts.py) | Regressões selecionadas na implementação | Não houve execução de testes funcionais nesta entrega documental |

A UI atual escolhe top-1 de confiança alta para parte do lote. Isso não satisfaz o requisito
novo de alternativa exata, evidência verificada e ausência de conflito. Os achados B04/B06
orientam a nova integração, sem serem corrigidos por escrever este plano. As orientações
legadas de Streamlit continuam contexto do legado; D4-02/D4-03 regem a UI nova.

### 3.2 Política de preservação

Manter `src/ui`, processamento Python, scripts, dados, resultados, GTs e `PROMPT_VERSION v7.8`.
A futura UI consome fachadas de serviços; não precisa apagar ou reorganizar todo o repositório.
Mudanças de contrato compartilhado entram em revisão conjunta, preservando adaptadores e
testes úteis. Uma chamada que depende de escrita imediata no legado não se torna segura por
ser exposta via HTTP: essa fronteira deve ser corrigida no módulo responsável antes do uso.

<a id="m4-arquitetura"></a>

## 4. Arquitetura proposta e organização física

### 4.1 Responsabilidades de execução

```text
Desktop / navegador
  React + TypeScript + componentes shadcn/ui
    projeto / pares IFC-IDS / lista / detalhe / revisão / catálogo / saídas
    adaptador 3D local: geometria + mapa visual <-> ElementRef
                  |
          API Python local versionada
                  |
  sessão + autorização M6 + comandos/recibos de revisão
       | M1 catálogo | M2 diagnóstico | M3 candidatos | M5 saídas |
                  |
   metadados transacionais + originais/snapshots/derivados imutáveis
                  |
      workers independentes de análise/geometria; fila LLM serial
```

O navegador controla apresentação e rascunhos. A API controla identidade, autorização,
pré-condições, consulta, persistência e comandos. O backend M2 é a autoridade dos dados
do diagnóstico; leitura auxiliar no viewer não substitui observações M2. M3 gera e verifica
candidatos, M4 registra decisões e M5 aplica em cópia. A API de revisão não importa o writer
para executar alterações durante o aceite.

O coordenador referencia duas análises independentes. Independência não obriga processamento
CPU simultâneo: M6 regula workers conforme recursos medidos. A fila de inferência compartilha
um limite de **uma chamada LLM ativa** no baseline, inclusive entre os dois IFCs. Mostrar
modelo em espera, em execução e terminal, sem confundir espera da LLM com travamento da UI.

Diagnóstico, sugestões e geometria têm tarefas e estados separados. Resultado M2/M3 pode
chegar antes da cena; a UI abre a lista e os detalhes imediatamente. Falha do viewer não
destrói a análise nem dispara novo enriquecimento. Eventos atrasados carregam a identidade
da execução e só atualizam a tela a que pertencem.

### 4.2 Estado e persistência

- Estado durável: projeto, modelos/revisões, vínculos IFC/IDS, pins, análises, decisões,
  candidatos/fundamentos, recibos, histórico, preferências de sessão e ajustes visuais.
- Estado transitório: texto ainda não salvo, arrasto de painel, hover, carregamento de malha
  e cache de consulta. Identificar claramente o que permanece apenas no navegador.
- Estado derivado: contagens, elegibilidade de ações, fila filtrada e resumo de exportação.
  Calcular a partir de snapshots/revisões identificados, sem criar autoridade paralela.

Uma camada de consulta normaliza referências e cancela/descarta respostas obsoletas ao trocar
de análise. Tabelas extensas usam paginação/virtualização a ensaiar. Geometria fica fora do
estado serializado da aplicação; recursos gráficos são liberados ao descarregar a revisão.
Não duplicar bytes integrais IFC em cada componente ou evento de progresso.

### 4.3 Arquivos futuros propostos

Os caminhos de código seguintes **não foram criados nesta entrega**. São pontos de implementação;
validar conflito de nomes quando o trabalho começar. M1–M3 podem evoluir antes disso.
O diretório de apoios M4 já recebe apenas a pesquisa documental vinculada na seção 13.

| Caminho futuro | Responsabilidade |
|---|---|
| `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json` | Build e versões fixadas da UI, definidos na primeira fatia |
| `frontend/src/app/App.tsx`, `frontend/src/app/ReviewWorkspace.tsx` | Rotas e arranjo das três áreas, topo e status da sessão |
| `frontend/src/shared/contracts.ts`, `frontend/src/shared/api.ts` | Tipos de transporte alinhados ao schema e cliente com erros/recibos |
| `frontend/src/features/project/ModelPairTable.tsx` | Entrada e confirmação dos dois pares, metadados e revisões |
| `frontend/src/features/diagnostic/DiagnosticList.tsx`, `DiagnosticFilters.tsx` no mesmo diretório | Visões por elemento/requisito, busca, contagens e paginação |
| `frontend/src/features/selection/selection.ts` | Alvo de revisão, origem de evidência e sincronização lista/3D/detalhe |
| `frontend/src/features/viewer/ViewerPort.ts`, `ViewerPanel.tsx`, `DisplayControls.tsx` no mesmo diretório | Porta neutra de viewer, ciclo de recursos e controles visuais |
| `frontend/src/features/evidence/EvidencePanel.tsx` | Atual/exigido/proposta/origem e relações com portadores |
| `frontend/src/features/review/FieldReview.tsx`, `BatchPreview.tsx`, `ReviewHistory.tsx` no mesmo diretório | Decisão individual, lote, prévia e revogação |
| `frontend/src/features/session/SessionStatus.tsx` | Salvar, recibo, retomada, conflito e falha de persistência |
| `frontend/src/features/catalog/CatalogWorkspace.tsx` | Consulta, rascunho, validação e publicação via M1 |
| `frontend/src/features/export/ExportPreview.tsx`, `ExportStatus.tsx` no mesmo diretório | Resumo M5 e recibos separados por arquivo/etapa |
| `frontend/src/assets/` | Fontes, ícones, imagens e ativos de UI distribuídos localmente |
| `src/review_api/app.py`, `schemas.py`, `errors.py` no mesmo diretório | Composição da API de revisão, transporte versionado e erros seguros |
| `src/review_api/routes/projects.py`, `analysis.py`, `review.py`, `exports.py`, `catalog.py` no mesmo diretório | Rotas finas para serviços; nenhuma regra de engenharia duplicada |
| `src/review_session/service.py`, `repository.py`, `commands.py`, `events.py` no mesmo diretório | Sessão, transação, histórico e idempotência; persistência acordada com M6 |
| `src/review_session/batch.py`, `preconditions.py` no mesmo diretório | Prévia congelada, elegibilidade e revisão esperada |
| `src/viewer_bridge/assets.py`, `mapping.py`, `transforms.py` no mesmo diretório | Derivados locais, vínculo visual e transformações apenas de apresentação |
| `tests/review_api/`, `tests/review_session/`, `tests/viewer_bridge/` | Contratos, autorização, persistência e identidade testados em Python |
| `frontend/tests/components/`, `frontend/tests/e2e/` | Interações e percursos de navegador |
| `tests/fixtures/m4/manifest.json` | Manifesto do corpus M4 e resultados esperados |
| `docs/planejamento/apoios-modulo-04/` | Relatos de comparação, protocolo e evidências de aceite futuros |

Não adotar sete serviços por existirem sete frentes. A API pode ser um processo modular local,
com workers onde isolamento e interrupção exigirem. Não reutilizar sessão global do MCP como
sessão de projeto. A composição de deployment e o eventual banco IME pertencem ao M6.

<a id="m4-contratos"></a>

## 5. Contratos M1–M7 e identidade

### 5.1 Regras comuns de identidade

Reutilizar `SourceArtifactRef`, `AnalysisIdentity`, `ElementRef`, `DiagnosticSnapshot`,
`EvidenceObservation` e `TypedValue` de [M2](modulo-02-nucleo-ifc-ids.md#m2-dados);
`CatalogReleaseRef`/pin de M1; `FieldRef`, `FieldAlternative`, `ManualCandidate`,
`CandidateValidation` e `ReviewEnvelope` de [M3](modulo-03-contexto-enriquecimento.md#m3-contratos).
O wire format final será negociado, sem inventar um segundo significado para esses nomes.

Chaves operacionais mínimas:

```text
modelo:       project_id + model_id
fonte:        model_id + revision_id + sha256
elemento:     model_id + ifc_revision_id + express_id
requisito:    ids_sha256 + caminho/índice estrutural do requisito
avaliação:    analysis_id + requirement_id + ElementRef ou escopo de especificação
campo:        analysis_id + FieldRef + portador/caminho alvo
alternativa:  enrichment_run_id + field_id + alternative_id + hash do conteúdo
decisão:      decision_id + revisão do conjunto de revisão
```

GlobalId é atributo adicional. Nome de arquivo, nome de elemento e GUID isolado não são chave.
Se M2 não puder localizar uma entidade de modo confiável, a UI apresenta a ambiguidade; não
escolhe a primeira. Dentro do mesmo arquivo, GUID duplicado preserva duas linhas distintas
por localizador válido e informa a limitação de interoperabilidade. O mapa gráfico contém
`viewer_model_id` e IDs de fragmentos associados à referência completa, inclusive relações
um elemento–várias malhas. STEP ID não é continuidade entre revisões.

Dois IFCs visualmente sobrepostos continuam fontes diferentes. A federação permite navegar,
não inferir que um valor no modelo estrutural é evidência para campo do arquitetônico.
Fonte manual também não serve de atalho para essa transferência na v1: referências entre
IFCs são rejeitadas como evidência de preenchimento. Uma extensão futura precisaria de
política e autorização próprias, fora deste contrato.

### 5.2 Objetos adicionais propostos para M4

| Objeto | Conteúdo obrigatório | Regra |
|---|---|---|
| `ProjectReviewSession` | projeto/sessão, ator autorizado, revisão durável, pares, pin, preferência visual | Não é credencial; acesso verificado em cada operação |
| `ModelPairBinding` | model_id, disciplina, IFC/revisão/hash, IDS/revisão/hash, confirmação do vínculo | Cada linha produz análise independente; nome não decide vínculo |
| `AnalysisViewRef` | análise M2, snapshot/hash, enriquecimento M3 opcional, revisão da fila | Tela mostra a identidade consultada e descarta resposta de outra análise |
| `ViewerAssetManifest` | revisão/hash IFC, gerador/versão, hash do derivado, unidades/eixos, mapa gráfico | Derivado pertence à revisão e não é evidência semântica |
| `DisplayTransform` | revisão IFC, matriz, unidade/referencial, motivo, ator, UTC, revisão visual | Só apresentação; identidade distinta de transformação efetivamente gravada no IFC |
| `SelectionState` | ElementRef alvo, FieldRef ativo, origem de evidência opcional, seleção visual | Explorar origem não troca silenciosamente o alvo da decisão |
| `ReviewQuery` | análises/modelos, classe, requisito, disciplina, estados por eixo, busca, ordenação/cursor | Busca/filtragem não revalida o IFC e não apaga itens |
| `FieldReviewView` | campo, requisitos, atual bruto/tipado, exigido, alternativas, evidência, estados e ações permitidas | Enumeração do IDS não vira sugestão observada |
| `ReviewCommand` | command_id, revisão esperada, alvo, ação, alternativa exata ou manual validado, justificativa, escopo | Ator vem do servidor; comparação de pré-condições antecede registro |
| `DecisionReceipt` | command_id, decision_id, revisão persistida, UTC servidor, resultado e vínculo da decisão | Confirmar salvamento somente após persistência concluída |
| `BatchPreview` | ID/hash, revisões, ação, linhas afetadas, exclusões/motivos, antes/depois, alcance em tipos | Conjunto congelado; não usar apenas predicado de filtro para executar |
| `BatchReceipt` | preview/hash, sub-recibos por modelo, decisões por campo, rejeições e estado agregado | Parcial explícito; uma falha não transforma outro modelo em falha |
| `SessionSaveReceipt` | sessão, revisão persistida, comandos confirmados, preferências salvas e UTC | “Salvo” cobre somente a revisão identificada |
| `UndoCommand` | command_id, decisão a revogar, revisão esperada, motivo | Acrescenta evento; não apaga história nem altera arquivo já exportado |
| `ExportHandoff` | modelo/revisão original, snapshot, IDS/pin, decisões vigentes, prévia M5 e hash | Exclui ajuste visual; exporta por IFC, sem mescla |
| `UiError` | código, escopo, ação possível, correlation_id e mensagem segura | Detalhe técnico local acessível conforme perfil, sem expor segredo na tela |

`TypedValue` conserva zero, falso, string vazia, nulo e ausência como casos diferentes.
Decimal e unidade são transmitidos conforme contrato M2/M3; não converter tudo para texto
para simplificar o editor. Caminho literal do IDS e portador de escrita ficam visíveis.

### 5.3 Contratos por fronteira

| Fronteira | M4 consome | M4 envia | Condição de aceite da integração |
|---|---|---|---|
| M1 | Release/pin, conceitos/bindings, capacidades, validações de rascunho e diff | Busca, solicitação de mapping, edição de rascunho, validação/publicação autorizada, atualização explícita de pin | Rascunho não aparece como release; falta de mapping não oculta diagnóstico; publicação exige curador |
| M2 | Pares/revisões confirmados, elementos, especificações, observações, diagnóstico/cobertura, progresso | Pedido de análise independente, query, cancelamento e exportação de diagnóstico | Cinco estados preservados; zero aplicáveis aparece por requisito; original não sofre mutação |
| M3 | Contexto por campo, alternativas identificadas, abstenção/conflitos, validação de candidato | Campos/execução a enriquecer, manual com fundamento, pedido de revisão de requisito | Um LLM ativo; proposta de B nunca atualiza A; segunda alternativa mantém sua própria origem |
| M5 | Prévia de mudanças/alcance, recibos de aplicação/exportação, resultado da revalidação e BCF | Decisões vigentes e autorizadas, snapshot e identidade das entradas por modelo | Aceito não significa escrito; cópia é nova revisão; falha de escrita/revalidação não vira sucesso |
| M6 | Principal/ACL, diretórios internos, política de armazenamento, budgets, identidade/build e ativos locais | Operações autenticadas, eventos/erros, pedidos de salvar/retomar e medidas de recurso | Reinício preserva decisão confirmada; cliente não forja papel/autoria; projeto isolado |
| M7 | Protocolo, cenário, critérios e consentimento de avaliação quando aplicável | Eventos locais de tarefa, tempos, escolhas/reversões, falhas, hardware/build e denominadores | Métrica tem contexto/revisão; teste Felipe/Nonato não é generalizado para população de usuários |

M5/M6/M7 ainda precisam de detalhamento próprio. As obrigações dessa tabela são propostas
de integração e requisitos do M4, não alegação de APIs prontas nesses módulos.

### 5.4 Operações de API propostas

Prefixo ilustrativo: `/api/v1`. Rotas não existem por constarem aqui. `project_id`,
`session_id`, `analysis_id` e IDs de artefato sempre são resolvidos sob autorização M6.
Reutilizar serviços de M1/M2/M3; não duplicar seu motor dentro das rotas.

| Operação proposta | Entrada/retorno | Invariantes |
|---|---|---|
| `POST /projects/{id}/sessions` | projeto autorizado → `ProjectReviewSession` | Criar/retomar contexto sem abrir arquivo por caminho arbitrário |
| `POST /sessions/{id}/model-pairs/confirm` | linhas/revisão esperada → pares confirmados | IFC/IDS identificados antes de analisar; confirmação cobre hashes efetivos |
| `POST /model-pairs/{id}/analyses` | fontes/pin/opções → referência M2 | Nova execução, sem sobrescrever a anterior |
| `GET /analyses/{id}/diagnostic` | `ReviewQuery` → resultados, cobertura, cursor e snapshot | Contagens totais independentes da página |
| `POST /analyses/{id}/enrichments` | campos identificados → referência M3 | Sem autorizar escrita; usa fila serial |
| `GET /analyses/{id}/events` | última sequência → eventos ou snapshot de recuperação | Duplicados não duplicam estado; evento fora da análise não é aplicado |
| `GET /model-revisions/{id}/viewer-assets` | revisão autorizada → manifesto/estado | URL interna por artefato, sem caminhos livres ou CDN necessária |
| `POST /sessions/{id}/manual-candidates` | `ManualCandidate` → `CandidateValidation` identificado | Falta de evidência/tipo/suporte conserva bloqueio; permite salvar rascunho |
| `POST /sessions/{id}/decisions` | `ReviewCommand` → `DecisionReceipt` | Atômico; command_id repetido retorna recibo anterior se payload igual |
| `POST /sessions/{id}/batch-previews` | seleção explícita/ação → `BatchPreview` | Todos os afetados e excluídos enumerados, inclusive fora da página |
| `POST /sessions/{id}/batch-decisions` | preview/hash/revisões → `BatchReceipt` | Rechecagem; subtransação por modelo com resultado inequívoco |
| `POST /sessions/{id}/save` | revisão/comandos/preferências → `SessionSaveReceipt` | Sem mensagem de sucesso antes da confirmação durável |
| `GET /sessions/{id}/commands/{command_id}` | chave idempotente → recibo/estado conhecido | Resolve timeout após possível gravação, sem repetir como comando novo |
| `POST /sessions/{id}/undo` | `UndoCommand` → novo recibo | Revogação serializada com exportação e preservação de histórico |
| `POST /model-revisions/{id}/export-previews` | decisões vigentes → prévia M5 | Inclui valores anteriores, operações, pendências e limites |
| `POST /model-revisions/{id}/exports` | ID/hash da prévia M5 → job/recibos M5 | Apenas fonte correspondente; bloqueia prévia obsoleta |

Consultas de catálogo e comandos de curadoria usam a fachada M1 com seus mesmos nomes e
revisões esperadas. O detalhamento de rotas será fixado junto ao schema publicado na tarefa
M4-02, sem inventar endpoints de publicação desconectados do serviço M1.

Contrato comum de erro: código, mensagem, escopo, revisão atual se autorizada e ID de suporte.
Proposta de transporte: `403` para ação sem permissão, `409` para revisão/prévia obsoleta,
`422` para candidato semanticamente inválido, `503` para serviço temporariamente indisponível.
Ingestão também declara arquivo/tamanho/formato rejeitado conforme M2/M6. O frontend não
converte esses erros em lista vazia ou decisão aceita. Uma mesma command_id com payload
distinto é conflito, nunca nova operação silenciosa.

<a id="m4-estados"></a>

## 6. Estados, contagens e linguagem da interface

### 6.1 Eixos separados

| Eixo | Estados/rótulos de apresentação | Regra de interpretação |
|---|---|---|
| Execução por arquivo | Aguardando, processando, concluída, parcial, cancelamento solicitado, cancelada, falhou | Pedido de cancelamento não é confirmação de parada |
| Validação M2 | Conforme, não conforme, não aplicável, não verificado, erro | Corresponde ao resultado formal e sua razão; não depende de revisão humana |
| Observação | Presente, ausente, nula, vazia, inválida, não suportada, erro, conflitante | Zero e falso não são ausência |
| Mapeamento M1 | Mapeado, sem mapeamento, ambíguo, indisponível | Não altera o resultado IDS independente |
| Enriquecimento M3 | Não solicitado, em fila, processando, proposta disponível, abstenção, não suportado, falhou, cancelado | Sem proposta não implica que o campo foi revisado |
| Revisão M4 | Pendente, rascunho, aceito, editado/preenchido, rejeitado, mantido pendente, revogado | Aceito/editado autoriza encaminhamento sob pré-condições, não marca conformidade |
| Persistência | Há alterações não salvas, salvando, salvo na revisão X, falhou ao salvar, confirmação desconhecida | “Salvo” exige recibo; timeout pode exigir consulta pelo command_id |
| Geometria por modelo | Não solicitada, preparando, carregando, disponível, parcialmente disponível, falhou, descarregada | Não substitui execução M2/M3 |
| Aplicação M5 | Não solicitada, prévia, em aplicação, aplicada, falhou, resultado parcial identificado | Aplicada não implica revalidada |
| Revalidação M2 da cópia | Não iniciada, em execução, concluída com resultados, parcial, erro | Mostrar conformidade/cobertura reais da nova revisão |

Os nomes de transporte podem seguir os enums dos módulos de origem, com tradução explícita.
Não criar um único `status=success` para substituir todos os eixos. Um campo pode estar
“Não conforme”, “Proposta disponível”, “Aceito e salvo”, “Não aplicado” ao mesmo tempo.
Rejeitar a proposta ou manter pendente não resolve a pendência IDS e não fecha BCF.

### 6.2 Cores, legenda e agregação

Seletor de coloração: **Classe** ou **Status de validação**. Na segunda opção, cinco estados
têm rótulos e símbolos próprios; quando um elemento reúne estados distintos, apresentar
composição e contagens, com regra de prioridade documentada. Proposta técnica: erro,
não verificado e não conformidade recebem destaque de atenção sem esconder uns aos outros;
o detalhe lista todos. “Não aplicável” não usa o mesmo selo de conformidade.

Seleção recebe contorno independente da paleta, com foco visível na lista e identificação
textual no painel. Origem de evidência pode receber destaque secundário, com legenda
“Origem consultada” e botão “Voltar ao alvo”. Não depender de vermelho/verde para decidir.
Paleta final, densidade e tema pertencem à escolha visual ainda pendente.

### 6.3 Contagens e vazios

Apresentar por arquivo e pelo conjunto: elementos, pares elemento/requisito avaliados,
especificações sem população, campos com decisão pendente, revisão salva e limitações.
Não somar contagens de naturezas distintas em um percentual de “qualidade”. No conjunto,
somar apenas unidades compatíveis e exibir quais arquivos contribuíram e quais estão parciais.

Cada consulta traz total antes do filtro, total filtrado e página carregada. Contagem de
pendências de revisão é separada da contagem de não conformidades; aprovar um candidato
reduz pendências de decisão, sem reduzir não conformidades do snapshot original.

Mensagens obrigatórias e distintas:

- “Nenhum resultado corresponde aos filtros” com opção de limpar filtros.
- “Nenhum elemento aplicável nesta especificação” com cardinalidade/resultado M2.
- “Aplicabilidade não determinada” quando o motor não conseguiu avaliar.
- “Modelo ainda não analisado” ou “Análise parcial” com escopo faltante.
- “Elemento sem geometria disponível” quando a linha é válida, mas não possui malha utilizável.

<a id="m4-percursos"></a>

## 7. Percursos e organização da tela

### 7.1 Entrada do projeto

1. Abrir/criar projeto autorizado e identificar catálogo fixado ou limitação explícita.
2. Exibir tabela de modelos com uma linha Arquitetura e outra Estrutura. Cada linha recebe
   IFC, IDS pronto, nome de exibição, disciplina e versões/hashes fornecidos pelo backend.
3. Mostrar problemas de arquivo e suporte por linha; permitir corrigir o vínculo antes de
   confirmar. Nomes semelhantes não autorizam associação automática.
4. Confirmar tabela completa de vínculos. Persistir confirmação com os bytes efetivos.
5. Iniciar análises independentes; oferecer início do segundo modelo ainda que o primeiro
   esteja processando ou tenha falhado. A política de recursos pode colocá-lo em fila.
6. Preparar a cena conjunta, indicando o estado de geometria de cada modelo. A lista já
   mostra resultados disponíveis e cobertura parcial antes da conclusão do 3D.

Topo permanente: projeto, ator/perfil, os dois IFCs/revisões, IDS de cada linha, pin do
catálogo, análise ativa, estado de salvamento e acesso ao histórico. Um seletor “Conjunto /
Arquitetura / Estrutura” altera o recorte visível, conservando a identificação do arquivo
em cada linha e detalhe. Trocar revisão requer ação explícita e avisa sobre rascunhos locais.

### 7.2 Percurso “Validação” sem LLM

Executar M2 e consultar problemas técnicos, falhas IDS e alertas complementares em grupos
distintos. Abrir requisito ou elemento, comparar exigido/encontrado e localizar sua origem.
Mostrar exportação do diagnóstico e encaminhamento BCF via M5, sem exigir enriquecimento,
modelo LLM disponível ou catálogo mapeado. Solicitar LLM nunca é efeito colateral de abrir
a tela, selecionar uma linha ou exportar diagnóstico.

### 7.3 Percurso “Revisão e enriquecimento”

Reutilizar as análises já carregadas; selecionar campos elegíveis e solicitar M3. Mostrar
fila por modelo, uma inferência ativa, alternativas verificadas e abstenções. A UI não
substitui manualmente um resultado falho por candidato inventado. Abertura do percurso
não descarta diagnóstico, seleção, filtros ou revisões já salvas.

Para cada campo, apresentar quatro blocos: **Atual no IFC**, **Exigido pelo IDS**,
**Sugestão/valor em revisão** e **Evidências**. Método, limitações, conflito e motivo de
abstenção ficam junto ao candidato. Os controles de decisão explicitam o campo e o arquivo.

### 7.4 As três áreas

| Área | Conteúdo principal | Interação e preservação |
|---|---|---|
| Esquerda | Lista por elemento, alternativa por requisito, busca, filtros e contagens | Seleção ativa persistida; anterior/próxima percorre o conjunto filtrado completo |
| Centro | Cena federada, legenda, modelo ativo, câmera, recortes e controles | Clique resolve ElementRef; não limpa filtros nem muda o alvo de revisão silenciosamente |
| Direita | Identidade, campos, esperado/atual/candidato, evidência, decisões e histórico | Troca de campo preserva rascunho; largura ajustável e conteúdo rolável |

Redimensionamento deve preservar áreas mínimas utilizáveis e foco de teclado. Limites de
largura/resolução serão fixados nos ensaios desktop; não inventar suporte móvel por os
painéis poderem ser recolhidos. Preferências de painel pertencem à sessão/usuário, não ao IFC.

Busca por nome, GlobalId, identificador local e tipo retorna itens com arquivo de origem;
busca por ID local sem arquivo pode ter várias respostas. Filtros de status devem indicar
o eixo: validação, proposta ou revisão. “Selecionar todos os filtrados” declara quantidade
total e produz prévia no servidor, não apenas os itens da página.

“Anterior/próxima pendência” conserva filtros e ordenação estável. Se decidir o item o remove
do filtro de pendentes, a interface confirma o recibo e oferece o próximo sem perder o
acesso ao anterior no histórico. Clique 3D em item fora do filtro mostra seleção contextual
e ação explícita para revelar o item, sem alterar a consulta silenciosamente.

<a id="m4-3d"></a>

## 8. Federação, visualização e navegação de origem

### 8.1 Porta de viewer e integridade

A porta neutra proposta deve carregar/descarregar um manifesto, resolver clique para
ElementRef, selecionar por referência, destacar, enquadrar, alterar visibilidade/opacidade,
aplicar cortes e informar erros/progresso. Esses são requisitos da porta, não afirmações
de que cada biblioteca candidata os cumpre sem adaptação.

O backend mantém manifesto IFC→derivado→mapa gráfico. Chave de cache inclui hash/revisão
da fonte, gerador/versão/configuração e política de coordenadas/classes. Um cache gerado
para outro IFC com nome igual é recusado. ID local do renderer não é presumido como
EXPRESS ID; a tradução é explícita, testada e admite uma entidade com várias geometrias.

Malha ausente, classe excluída na conversão ou parte não renderizável não remove a entidade
da lista nem prova ausência no IFC. Exibir cobertura visual e limitações por modelo. Se a
identidade de um fragmento não puder ser comprovada, desabilitar decisão a partir daquele
clique, conservando o acesso pela referência M2 confiável.

### 8.2 Coordenadas e alinhamento

Abrir usando placements, unidades e coordenadas IFC interpretados pelo adaptador. Registrar
as conversões necessárias para coordenadas de renderização, inclusive eventual origem
comum para estabilidade numérica. Não “centralizar cada modelo” de forma que destrua seu
posicionamento relativo sem informar o usuário.

Exibir uma etapa de conferência visual da federação: ambos os modelos visíveis, referências
reconhecíveis, unidades/offsets conhecidos e estado “alinhamento visual conferido” ou “não
conferido”. Conferência visual não certifica georreferenciamento ou precisão universal.

Proposta de ajuste manual: translação/rotação de visualização por modelo, com valores,
referencial, ator, motivo e opção de reset. Não oferecer escala arbitrária para mascarar
unidade incorreta; inconsistência de unidade deve ser diagnosticada. O conjunto de controles
será ensaiado. Toda transformação manual permanece marcada na tela e no histórico visual.

M5 recebe identidade original, nunca transformação de apresentação como instrução de
escrita. Se um viewpoint BCF usar câmera/cortes da cena ajustada, M5 deve transformar as
referências corretamente para o sistema da fonte ou declarar a limitação e exportar apenas
informação suportada; não anexar viewpoint sabidamente incorreto.

Ensaiar carregar A→B e B→A: a ordem de inserção não pode mudar o significado espacial da
federação nem a correspondência lista/3D. Não propor detector universal de alinhamento.

### 8.3 Controles visuais

- Ocultar/mostrar disciplina ou classe sem alterar análise e contagens formais.
- Destacar seleção, isolar elemento/conjunto, enquadrar e restaurar vista anterior.
- Criar/mover/remover planos de corte, restaurando seleção coerente após cada operação.
- Modo “Só pendências”: elementos correspondentes ao recorte de pendência declarado.
- Modo “Contexto”: alvo destacado, entorno transparente, com legenda do estado visual.
- Restaurar visibilidade, opacidade, cortes e câmera sem apagar ajustes registrados.

“Pendência” deve indicar se se refere à falha de validação ou à revisão ainda necessária.
O modo não mistura rejeição com resolução. Testar transparência e seleção com câmera em
movimento, elementos sobrepostos, isolados e cortados; geometria invisível não deve capturar
cliques indevidos. Cortes são visuais, nunca exclusão de elementos do diagnóstico.

### 8.4 Evidência em outro elemento

“Ver origem” abre o registro original: arquivo/revisão, entidade, caminho, valor bruto,
valor tipado, unidade, método e portador ocorrência/tipo/parte/relação. Evidência derivada
mostra operação e entradas. Definição do catálogo e exigência IDS têm rótulos diferentes
de observação do IFC.

Se a origem pertence a outro elemento **do mesmo IFC**, destacar esse elemento no 3D e
preservar o campo alvo no painel; um marcador textual mostra os dois papéis. Se não houver
geometria, abrir o registro de origem na lista/detalhe. Fonte manual mostra autoria e
fundamento local registrado, sem se apresentar como extração automática.

### 8.5 Falha e recuperação

Mostrar modelo afetado, etapa, mensagem compreensível, “Tentar novamente” e acesso a
diagnóstico técnico local com correlation_id. Liberar recursos do modelo falho; manter
o outro modelo, lista, detalhes e decisões. Retry da geometria reutiliza revisão fixa e
não cria análise nova. Remoção/cancelamento invalida callbacks atrasados para impedir que
o modelo reapareça depois. Perda do contexto gráfico deve poder reconstruir a cena usando
manifestos, sem reconstruir decisões a partir de cores.

O percurso por lista dá continuidade durante a falha. A entrega de qualidade permanece
reprovada para cenários em que o 3D exigido não funciona, até correção ou restrição de
capacidade explícita revisada com Felipe e Nonato.

<a id="m4-revisao"></a>

## 9. Revisão individual, manual e em lote

### 9.1 Decisão por campo

Aceitar exige alternativa exata e verificações M3 válidas para a revisão atual. Editar
cria candidato manual vinculado à alternativa original, mantendo ambos os valores; preencher
sem proposta segue o mesmo contrato manual. Rejeitar registra o motivo e mantém o estado
formal existente; manter pendente registra adiamento sem produzir valor ou autorização.

O comando contém valor anterior esperado, caminho/portador alvo, revisão IFC/IDS/catálogo,
snapshot e versão da proposta/checagem. Se qualquer precondição mudou, o servidor responde
conflito, conserva a edição e exige reapresentação do contexto atual para nova decisão.
Não trocar automaticamente para a sugestão mais recente nem para a primeira alternativa.

Vários requisitos podem atingir o mesmo campo. Exibir todos e suas divergências antes de
aprovar; não criar comandos contraditórios para o mesmo alvo. Escrever no tipo pode afetar
várias ocorrências: M5/M2 devem fornecer alcance completo, incluindo itens fora do filtro.
A autorização individual só cobre o escopo expressamente apresentado e confirmado.

### 9.2 Manual com fundamento e conflitos

Campos obrigatórios: valor tipado/unidade quando pertinente, fonte/fundamento registrado,
justificativa, portador/caminho e alvo/revisão. Fonte humana é declaração identificada;
referência documental deve resolver localmente conforme política M3, sem ingestão automática
de documentos nesta v1. Uma URL ou ID digitado não prova que a fonte existe ou é pertinente.

Checagens antes de habilitar aprovação: tipo, unidade, restrições IDS suportadas,
aplicabilidade, fonte existente/pertinente, alcance e conflito. Persistir relatório da
checagem ligado ao hash do candidato. Alterar um caractere relevante invalida a checagem.
Rascunho incompleto pode ser salvo como rascunho, sem habilitar exportação.

Campo sem mapping conserva caminho literal e validação suportada M2; a UI oferece manual
fundamentado quando M3/M2 puderem checar o alvo. Não criar equivalência de catálogo por
preenchimento. Se o requisito é inadequado, abrir `RequirementReviewRequest` com justificativa
e evidência; não fabricar valor para satisfazê-lo. Novo IDS implicará nova análise.

Conflito mostra valores e fontes concorrentes, suas unidades/qualificadores e o componente
de origem. Não resolver por ordem, maior confiança autodeclarada ou primeiro portador.
Decisão humana fundamentada é registrada com o conflito que resolveu; não apaga a evidência
divergente. Quando o conflito não puder ser tecnicamente resolvido, manter pendente/BCF.

### 9.3 Lote

1. Selecionar explicitamente elementos/campos, com arquivo e quantidade total. Ação sobre
   todos os filtrados usa IDs congelados pelo servidor, não a página carregada.
2. Solicitar prévia: elegíveis, excluídos e razões, antes/depois, alternativa por campo,
   efeitos em tipo e fundamento. Sugestão verificada sem conflito é critério de elegibilidade;
   confiança “alta” sozinha não é critério suficiente.
3. Em manual em lote, registrar motivo/fonte cujo alcance seja válido para cada alvo.
   Justificativa genérica repetida não valida pertinência ao conjunto. Divergência de tipo,
   unidade, requisito ou componente divide o lote ou exclui itens com motivo.
4. Confirmar a prévia identificada. O servidor revalida permissões, hashes e revisões;
   mudança após a prévia requer nova prévia, não substituição silenciosa de itens.
5. Persistir decisões por campo com recibos e identidade de lote. Proposta: atomicidade
   por modelo; se uma partição falhar, informar exatamente as decisões confirmadas na outra.
6. Atualizar contagens somente após recibos. Oferecer histórico e desfazer das decisões
   ainda não comprometidas com uma exportação em curso/concluída.

O lote pode abranger a seleção federada, mas continua particionado por IFC. Não transporta
evidência entre arquivos nem emite uma decisão única que oculte seus destinatários.

<a id="m4-persistencia"></a>

## 10. Salvar, retomar, desfazer e nova revisão

### 10.1 Confirmação real

“Salvar progresso” persiste decisões/rascunhos e preferências acordadas, retornando revisão
durável e instante do servidor. Enquanto aguarda, exibir “Salvando”; quando falha, conservar
o formulário e exibir “Não foi possível salvar”. A UI informa que a edição ainda local
pode se perder se a aba/processo encerrar; não promete durabilidade antes de recibo.

Se a resposta se perder depois de possível commit da transação, consultar command_id antes
de repetir. Repetição usa a mesma chave/payload. Não emitir toast de sucesso por o navegador
ter enviado a requisição. Ação de exportar exige decisões confirmadas; rascunhos não salvos
ficam fora da prévia e aparecem como pendência explícita.

### 10.2 Retomada

Após fechar e reabrir navegador e serviço, localizar projeto/sessão pelo armazenamento
autorizado. Restaurar análises, decisões confirmadas, filtros, alvo quando ainda disponível
e preferências visuais salvas; reconstituir geometria a partir de manifestos. Mostrar
comandos com confirmação anteriormente desconhecida e reconciliá-los pelos recibos.

Jobs interrompidos mantêm identidade, tentativas e parciais. Não reiniciar LLM ou exportação
automaticamente só por abrir a sessão. M2/M3/M5 definem retomada idempotente de seus jobs.
Fonte/derivado ausente recebe mensagem específica; não carregar outro arquivo de mesmo nome.
Restauração de backup precisa conferir hashes e compatibilidade do schema de persistência.

### 10.3 Desfazer

Antes da exportação, desfazer acrescenta revogação da decisão e devolve o campo ao estado
de revisão apropriado, preservando autor, valor e histórico. Revogar parte de um lote lista
quais decisões foram afetadas. Isso invalida a prévia M5 que dependia delas.

Desfazer e iniciar exportação devem ser serializados no servidor. Uma exportação em curso
usa snapshot imutável das decisões: não declarar revogação retroativa sobre esse snapshot.
Após exportar, eventual correção demanda novo ciclo/revisão; nenhum botão altera o original
ou “desfaz” bytes já entregues silenciosamente.

### 10.4 Nova revisão IFC, IDS ou catálogo

Receber nova fonte cria revisão/hash novos e nova análise, com vínculo à anterior. Topo
mostra qual conjunto está ativo. Histórico permanece acessível; comparação e sugestão de
correspondência pertencem ao M5, com ambiguidade explícita.

Mesmo GUID ou nome não reaplica decisão. Catálogo atualizado apresenta diff/impacto M1,
novo pin explícito e reprocessamento necessário; o catálogo antigo continua identificando
a análise anterior. Decisão antiga só pode servir de referência para nova revisão humana,
após rechecagens, sem se tornar autorização automática.

<a id="m4-saidas"></a>

## 11. Pré-exportação e acompanhamento do M5

A tela de prévia usa plano de mudanças produzido/verificado pelo M5. Por IFC: fonte/hash,
IDS/pin, decisões incluídas/excluídas, elementos afetados, campos/conjuntos a criar ou alterar,
valores antes/depois, portador, efeitos em tipo, pendências e limitações. Mostrar rascunhos,
rejeições, adiamentos e campos não verificados sem tratá-los como correções concluídas.

Separar “Exportar diagnóstico” de “Gerar cópia IFC com decisões”. O diagnóstico canônico
é exportável sem LLM, sem decisão e sem 3D. Download filtrado identifica filtros e cobertura;
relatório completo não se limita às linhas visíveis. M5 também pode produzir BCF residual
diretamente, sem forçar o usuário a solicitar sugestão ou preencher manualmente primeiro.

Após confirmar prévia válida, apresentar por arquivo:

1. Pedido recebido e job identificado.
2. Cópia em preparação/aplicação, com estado de cada operação quando disponível.
3. Aplicação concluída ou falha; original permanece intacto.
4. Nova revisão submetida ao mesmo serviço M2 para revalidação.
5. Resultado da revalidação, cobertura, falhas anteriores, regressões e limitações.
6. Artefatos liberados pelo M5, hashes/recibos e pendências/BCF associados.

Erro de revalidação não recebe selo “IFC validado”. A política de disponibilizar cópia
parcial ou cópia após falha é responsabilidade a fechar no M5; a UI não a decide por
conveniência. Até haver regra implementada, não oferecer saída ambígua como validada.

Arquitetura e estrutura recebem arquivos e recibos distintos, mesmo se um botão coordenar
os dois jobs. Falha de um deixa visível o sucesso confirmado do outro e o estado geral
parcial. Rejeitar/pular/aceitar não fecha automaticamente BCF; fechamento depende da
verificação pertinente na revisão de saída, com vínculo ao tópico anterior.

<a id="m4-perfis"></a>

## 12. Perfis, curadoria e localidade

### 12.1 Permissões propostas para discussão com M6

| Ação | Consulta | Revisão | Curadoria |
|---|---|---|---|
| Ver análise, evidência, histórico e 3D do projeto autorizado | Sim | Sim | Conforme acesso ao projeto |
| Exportar diagnóstico já autorizado | Conforme política M6/M5 | Conforme política M6/M5 | Conforme acesso ao projeto |
| Solicitar análise/enriquecimento e registrar decisões | Não | Sim, no projeto autorizado | Somente se acumular permissão de revisão |
| Editar/preencher candidato, lote e desfazer | Não | Sim, com checagens | Somente se acumular permissão de revisão |
| Solicitar novo mapping ou revisão de requisito | Conforme política de solicitação | Sim | Sim |
| Editar/validar rascunho de catálogo | Não | Solicitar mudança; sem publicação | Sim |
| Aprovar/publicar release de catálogo | Não | Não | Sim, sob revisão exata e política M1 |
| Gerar cópia IFC a partir das decisões | Não por padrão | Conforme autorização M5/M6 | Não por ser curador apenas |

A matriz distingue capacidades de produto; ACL e atribuição de pessoas precisam de acordo
M6. Curadoria não concede revisão de qualquer projeto. No localhost, mesmo que haja um
operador, o servidor deve produzir identidade de ator definida e verificar ações; não
aceitar `reviewer="engineer"` ou papel livre do navegador como autenticação suficiente.

### 12.2 Curadoria de catálogo

Tela separada dentro da aplicação, por tabela com filtros fonte/classe/perfil/estado e
detalhe. Permitir adicionar/duplicar rascunho, editar campos, mostrar original versus
reconciliado, conceito/binding, aplicabilidade, tipo/unidade, aliases, operação disponível,
fontes, histórico e impacto. Duplicar exige revisão de identidade; não publica cópia.

Salvar rascunho, validar, revisar candidato e publicar são ações distintas via serviços M1.
Erro de concorrência preserva edição local e apresenta diff. Publicação exige curador,
hash/revisão exatos e recibo. Nenhuma dessas ações muda o IDS, IFC ou pin de projeto
silenciosamente. Falta de operação implementada aparece como capacidade indisponível,
sem apresentar cadastro como executor pronto.

### 12.3 Dados e ativos locais

Servir UI, fontes, imagens, ícones, WASM, workers e artefatos a partir do pacote/servidor
local. Não depender de CDN para abrir lista, renderizar componentes ou visualizar IFC.
Logs e medidas M7 permanecem locais, com acesso e retenção M6. Textos vindos de IFC/IDS,
catálogo e LLM são dados não confiáveis: renderizar como texto seguro, sem HTML executável.

A política vigente M3 permite consulta à API pública bSDD apenas para semântica pública,
sem dados de projeto. Essa exceção controlada de backend não autoriza envio de IFC, nomes,
valores ou contexto do projeto a serviços de UI/viewer. No ensaio offline do M4, usar
catálogo/snapshots locais previamente disponíveis, registrar semântica indisponível quando
necessário e exigir zero tráfego externo para o percurso visual.

M6 deve fixar loopback inicial, origem autorizada, proteção de comandos e isolamento por
projeto. Operação IME exige autenticação, deployment, concorrência, backup e recursos
ensaiados; funcionamento em localhost não comprova esses requisitos institucionais.

<a id="m4-pesquisa"></a>

## 13. Pesquisa de visualizadores, propostas visuais e ensaios

### 13.1 Evidência recebida

O levantamento paralelo foi recebido durante esta redação. O apoio exclusivo M4
[Pesquisa de visualizadores](apoios-modulo-04/pesquisa-visualizadores.md) registra links
primários, limites, estados relatados e implicações para testes. Documentação oficial
descreve APIs; issues são relatos individuais e não foram reproduzidas neste projeto.
Não foi executado benchmark ou instalado viewer nesta tarefa.

O levantamento reforça três precauções: derivado visual não é a fonte IFC; IDs do renderer
precisam de tradução explícita; disponibilidade do parser não garante memória, cancelamento,
transparência ou seleção adequados no aplicativo completo. Fixar versões e comparar
resultados com o corpus, sem transformar relato isolado em limite operacional universal.

### 13.2 Comparação técnica proposta

Comparar That Open com pelo menos uma alternativa viável após triagem de licença e esforço.
O apoio inclui xeokit, geometria Python IfcOpenShell com camada visual própria e IfcViewer
web exploratório. Nenhuma alternativa está escolhida nem é presumida intercambiável.

| Dimensão | Evidência a produzir no ensaio | Regra de decisão proposta |
|---|---|---|
| Identidade | Cliques/lista/origens em dois arquivos, GUID repetido, várias malhas e três conversões frias | Nenhum alvo errado; contagem de triângulos sozinha não prova integridade |
| Completude visual | Manifesto de classes/entidades convertidas, ausentes e motivos | Ausências declaradas; caso essencial sem geometria impede aceite do cenário |
| Coordenadas | Carregamento isolado e A→B/B→A, unidades/placements e ajuste visual/reset | Posição relativa compreensível, sem transformação silenciosa de exportação |
| Interação | Seleção rápida com câmera, transparência, corte, ocultar/isolar/restaurar | Resultado visual corresponde à referência selecionada |
| Recuperação | Cancelar/remover durante carga, perder contexto gráfico, falhar um modelo | Não ressuscitar callback obsoleto; outro modelo e decisões preservados |
| Localidade | Rebuild/pacote com ativos locais e navegação sem internet | Zero chamadas externas necessárias ao percurso M4 |
| Recursos | RAM do processo/worker, heap/WASM e GPU quando mensurável; ciclos abrir/fechar | Registrar limites da medição; liberar recursos e fixar orçamento antes de uso operacional |
| Tempo | Ingestão, conversão, primeira imagem útil, lista pronta, seleção p50/p95 e cache frio/quente | Metas numéricas negociadas com hardware/corpus medidos |
| Licença/manutenção | Versão, licença de cada dependência/ativo, distribuição pretendida, integração | Condição de distribuição aceita por responsável; dúvida bloqueia seleção final |

Ensaios de geometria não são benchmark científico de LLM. Serão executados futuramente sob
autorização da etapa de desenvolvimento, sem alterar resultados experimentais históricos.

### 13.3 Corpus e limites

Inspecionar hashes, schema, unidades, quantidade de entidades/geometria e direitos de uso
dos IFCs locais antes do ensaio. `casa_v1.ifc` e `predio_v1.ifc` são fontes candidatas existentes,
não automaticamente dois modelos coordenados do mesmo projeto ou disciplinas distintas.
O teste final de federação exige um par arquitetura/estrutura compatível e seus IDSs;
fixtures sintéticas podem complementar colisões, falhas e alinhamento conhecido, identificadas
como sintéticas. Não substituir o caso real exigido apenas por imagens ou mocks.

Medir antes de prometer capacidade em MB, entidades ou número de modelos. Um arquivo pequeno
pode exigir geometria cara; tamanho em bytes não é proxy suficiente. O ensaio fixa hardware,
SO, navegador/build, drivers relevantes, parser/conversor/viewer e configurações. Antes do
uso operacional, M6 registra limites explícitos e tratamento de ultrapassagem; durante
exploração usar recursos controlados, nunca consumo ilimitado por falta de limite final.

### 13.4 Três propostas visuais pendentes

Outra frente ficou responsável por produzir as três propostas: claro limpo, escuro com
foco no 3D e painéis compactos. Todas devem mostrar **o mesmo cenário federado**, janela de
revisão em português, arquivo/disciplina do alvo, campo atual/exigido/sugestão/evidência,
legenda, lista, painel direito e estado de salvamento. Isso permite comparar apresentação
sem confundir diferença de cenário com preferência de layout.

A coordenação informou em 12/10 que as três imagens já foram entregues ao usuário.
As referências recebidas são: claro `libfile_69d1ea9f0e08819193d6d42426142856`,
escuro `libfile_1ce49fa64e448191980c8c9773ab243a` e compacto
`libfile_aab5be6794f08191913e2c4e1466cb47`. São identificadores informados da Library,
não caminhos locais verificados nesta tarefa. As imagens não foram reinspecionadas
por este executor nem copiadas como dependências de runtime da aplicação.

**Comparação e escolha visual pendentes.** Não há imagem aprovada ou avaliação de
usabilidade concluída. Registrar decisão, comentários, versão e cópia local autorizada
quando a escolha ocorrer; exibir opções não comprova aprovação. Nenhum mockup duplicado
foi criado nesta tarefa.

Critérios para a escolha: leitura de valores longos, hierarquia de estados, espaço útil 3D,
identificação do arquivo, legibilidade da origem, redimensionamento e acesso às ações sem
ocultar consequências. Preferência de tema não dispensa ensaio do fluxo funcional.

<a id="m4-tarefas"></a>

## 14. Tarefas de implementação futura

Todas as tarefas são de responsabilidade M4 de **Nonato**, com parceiros de fronteira
indicados. Os caminhos são propostos, não entregues. Cada tarefa começa com casos que
falham pelo comportamento ausente, implementa a fatia e termina com evidência dos casos
pertinentes. Os IDs T4 são definidos na seção 15. Testes com mocks não comprovam integração
real. Nenhuma tarefa abaixo foi executada nesta entrega documental.

<a id="m4-t01"></a>

### M4-01 — Preparar shell desktop e corpus

**Arquivos:** `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`,
`frontend/src/app/App.tsx`, `tests/fixtures/m4/manifest.json`.
**Dependências:** decisões D4 e recursos M6. **Entrada → saída:** briefing → shell, versões e corpus identificados.

- [ ] Registrar hardware, navegador, disponibilidade de dois IFC/IDS coordenados, hashes e direitos de uso.
- [ ] Fixar versões da stack aprovada e scripts de build/teste, com ativos de runtime locais.
- [ ] Criar topo e três áreas redimensionáveis em português, com dados sintéticos rotulados.
- [ ] Verificar T4-40/T4-41; registrar o que depende de serviços/viewer reais.

**Aceite:** shell abre localmente e redimensiona sem perder foco/dados; tema final ainda depende da escolha visual.

<a id="m4-t02"></a>

### M4-02 — Fechar identidade e contratos

**Arquivos:** `frontend/src/shared/contracts.ts`, `frontend/src/shared/api.ts`,
`src/review_api/schemas.py`, `src/review_api/errors.py`, `tests/review_api/test_contracts.py`.
**Dependências:** M4-01, M1/M2/M3/M5/M6. **Entrada → saída:** tipos dos módulos → schema versionado de transporte.

- [ ] Reconciliar nomes/campos com os contratos efetivos, preservando a seção 5 e sem criar autoridade paralela.
- [ ] Definir valores/estados discriminados, referências compostas e envelope idempotente com ator do servidor.
- [ ] Especificar exemplos válidos/inválidos para pares, candidatos, decisões, lotes e recibos.
- [ ] Verificar T4-03/T4-04/T4-26/T4-37/T4-43/T4-53 e ida/volta sem perder zero, falso, precisão ou unidade.

**Aceite:** Felipe/Nonato revisam contrato; GUID isolado, fonte cruzada e estado desconhecido não viram sucesso.

<a id="m4-t03"></a>

### M4-03 — Comparar viewers e decidir estratégia

**Arquivos:** `frontend/src/features/viewer/ViewerPort.ts`,
`docs/planejamento/apoios-modulo-04/ensaio-viewer.md`, `tests/viewer_bridge/test_identity.py`.
**Dependências:** M4-01/M4-02, pesquisa, corpus e M6/M7. **Entrada → saída:** requisitos/corpus → matriz e decisão técnica.

- [ ] Triar That Open e alternativas por licença, ativos locais e esforço; nenhuma adoção por default.
- [ ] Executar provas delimitadas dos casos T4-05/T4-06/T4-07/T4-08/T4-15/T4-42/T4-50.
- [ ] Medir conversão/carga/seleção/memória, classes omitidas e repetibilidade da identidade geométrica.
- [ ] Registrar escolha ou bloqueio, versões e limites; revisar com Felipe antes de anunciar capacidades.

**Aceite:** biblioteca/estratégia escolhida por evidência real; documentação de API não substitui ensaio.

<a id="m4-t04"></a>

### M4-04 — Confirmar pares e análises independentes

**Arquivos:** `frontend/src/features/project/ModelPairTable.tsx`,
`src/review_api/routes/projects.py`, `src/review_api/routes/analysis.py`, `frontend/tests/e2e/model-pairs.spec.ts`.
**Dependências:** M4-02, ingestão M2. **Entrada → saída:** fontes identificadas → vínculos confirmados e análises.

- [ ] Criar duas linhas disciplina–IFC–IDS com metadados reais e mensagens de arquivo por linha.
- [ ] Confirmar os hashes efetivos antes da análise; trocar arquivo invalida confirmação anterior.
- [ ] Mostrar execução, cancelamento e parcial por arquivo; ignorar eventos de outra análise.
- [ ] Verificar T4-01/T4-02/T4-43/T4-48, incluindo falha de B com continuidade de A.

**Aceite:** duas análises distintas no mesmo projeto, sem mescla de requisitos ou bloqueio global indevido.

<a id="m4-t05"></a>

### M4-05 — Federação e seleção sincronizada

**Arquivos:** `frontend/src/features/viewer/ViewerPanel.tsx`, `frontend/src/features/selection/selection.ts`,
`src/viewer_bridge/assets.py`, `src/viewer_bridge/mapping.py`, `frontend/tests/e2e/federation.spec.ts`.
**Dependências:** M4-02/M4-03/M4-04 e M2. **Entrada → saída:** manifestos/ElementRefs → cena e seleção.

- [ ] Consumir derivados com hash/versão/classes e mapa explícito renderer–ElementRef.
- [ ] Carregar os dois modelos e sincronizar clique, lista e detalhe, inclusive várias malhas por entidade.
- [ ] Manter linhas sem geometria e impedir decisão por fragmento de identidade não comprovada.
- [ ] Verificar T4-03/T4-04/T4-05/T4-07/T4-09 com erro em apenas um modelo.

**Aceite:** nenhum clique seleciona outro arquivo; geometria parcial não reduz o diagnóstico disponível.

<a id="m4-t06"></a>

### M4-06 — Lista, filtros, estados e navegação

**Arquivos:** `frontend/src/features/diagnostic/DiagnosticList.tsx`,
`frontend/src/features/diagnostic/DiagnosticFilters.tsx`, `frontend/tests/components/diagnostic.test.tsx`.
**Dependências:** M4-02/M4-04 e queries M2. **Entrada → saída:** snapshot → fila filtrada e contagens.

- [ ] Implementar paginação, ordenação estável, busca nome/ID/tipo e filtros por eixo explícito.
- [ ] Exibir cinco estados, categorias técnicas/IDS/complementares e totais por arquivo/conjunto.
- [ ] Preservar filtros em anterior/próxima e alternância de percurso; indicar clique fora do filtro.
- [ ] Verificar T4-10/T4-11/T4-12/T4-16/T4-44/T4-45 com mais de uma página de resultados.

**Aceite:** vazio por filtro, zero aplicáveis e indeterminação são distintos; contagem não é tamanho da página.

<a id="m4-t07"></a>

### M4-07 — Controles 3D, alinhamento e recuperação

**Arquivos:** `frontend/src/features/viewer/DisplayControls.tsx`,
`src/viewer_bridge/transforms.py`, `frontend/tests/e2e/viewer-controls.spec.ts`.
**Dependências:** M4-05/M4-06 e coordenadas ensaiadas. **Entrada → saída:** cena → vista controlável/recuperável.

- [ ] Implementar legenda, cores/contorno, ocultar/isolar/enquadrar, cortes e entorno transparente.
- [ ] Registrar conferência visual, ajustes/reset e distinção entre transformação visual e fonte IFC.
- [ ] Implementar retry/descarregamento e invalidar callbacks atrasados após cancelamento/remoção.
- [ ] Verificar T4-08/T4-09/T4-13/T4-14/T4-15/T4-35/T4-42/T4-48.

**Aceite:** ordem A→B/B→A não corrompe relação espacial; recuperação não perde decisões nem o outro modelo.

<a id="m4-t08"></a>

### M4-08 — Campo e origem rastreável

**Arquivos:** `frontend/src/features/evidence/EvidencePanel.tsx`, `frontend/tests/components/evidence.test.tsx`.
**Dependências:** M4-02/M4-05/M4-06, M2/M3. **Entrada → saída:** campo/observações → detalhe e origem navegável.

- [ ] Apresentar bruto/tipado/unidade, caminho IDS, portador e método sem trocar fato por requisito.
- [ ] Expor fontes concorrentes, conflitos, derivados e ausência de mapping/capacidade.
- [ ] Implementar “Ver origem” no mesmo IFC com alvo preservado e destaque secundário.
- [ ] Verificar T4-18/T4-19/T4-20/T4-26/T4-46/T4-47.

**Aceite:** cada candidato tem origem localizável; nenhum vínculo visual autoriza evidência cruzada entre IFCs.

<a id="m4-t09"></a>

### M4-09 — Enriquecimento independente da cena

**Arquivos:** `src/review_api/routes/analysis.py`, `frontend/src/features/review/EnrichmentStatus.tsx`,
`frontend/tests/e2e/enrichment.spec.ts`.
**Dependências:** M4-04/M4-06/M4-08, M3/M6. **Entrada → saída:** campos selecionados → jobs/resultados M3 por arquivo.

- [ ] Solicitar enriquecimento explicitamente; diagnóstico não instancia LLM como efeito colateral.
- [ ] Mostrar uma inferência ativa, filas, parciais, tentativas e falhas por campo/modelo.
- [ ] Preservar M2 quando M3/LLM/viewer falhar; reconsulta não cria nova chamada.
- [ ] Verificar T4-02/T4-09/T4-16/T4-17/T4-43 no serviço e na UI.

**Aceite:** mudar percurso não recarrega fontes; LLM indisponível não impede diagnóstico/exportação.

<a id="m4-t10"></a>

### M4-10 — Revisão individual e manual fundamentado

**Arquivos:** `frontend/src/features/review/FieldReview.tsx`, `src/review_session/commands.py`,
`src/review_session/preconditions.py`, `tests/review_session/test_field_decisions.py`.
**Dependências:** M4-02/M4-08/M4-09, checagens M3, alcance M2/M5, ator M6.
**Entrada → saída:** alternativa/manual validado → ReviewCommand/DecisionReceipt.

- [ ] Implementar aceitar alternativa exata, editar/preencher, rejeitar e manter pendente.
- [ ] Exigir fonte/justificativa, checagem vinculada ao candidato e revisão esperada; preservar rascunho em erro.
- [ ] Mostrar alcance em tipo e requisitos concorrentes antes da decisão.
- [ ] Verificar T4-19/T4-20/T4-21/T4-22/T4-26/T4-37/T4-46/T4-47.

**Aceite:** autor, alternativa, valor e escopo reais persistidos; aceitar não chama writer; inválido não é aprovável.

<a id="m4-t11"></a>

### M4-11 — Lote com prévia e recibo por arquivo

**Arquivos:** `frontend/src/features/review/BatchPreview.tsx`, `src/review_session/batch.py`,
`tests/review_session/test_batch_decisions.py`.
**Dependências:** M4-06/M4-10 e transações M6. **Entrada → saída:** seleção/ação → BatchPreview/BatchReceipt.

- [ ] Enumerar elegíveis/excluídos, motivo, alternativa, antes/depois e alcance integral em tipos.
- [ ] Validar fundamento manual para cada alvo; impedir evidência entre IFCs e repetição de motivo sem pertinência.
- [ ] Rechecar preview/hash/revisões e persistir recibos por campo/modelo.
- [ ] Verificar T4-22/T4-23/T4-24/T4-25/T4-49, inclusive sucesso de uma partição seguido de falha da outra.

**Aceite:** nenhuma aceitação só por confiança alta; parciais explícitos e todos os afetados presentes na prévia.

<a id="m4-t12"></a>

### M4-12 — Persistência, recibos e retomada

**Arquivos:** `src/review_session/service.py`, `src/review_session/repository.py`, `src/review_session/events.py`,
`frontend/src/features/session/SessionStatus.tsx`, `tests/review_session/test_recovery.py`.
**Dependências:** M4-02/M4-10/M4-11 e M6. **Entrada → saída:** comandos/preferências → sessão durável e recibos.

- [ ] Confirmar somente após commit transacional; permitir consultar comando pela chave idempotente.
- [ ] Distinguir falha de gravação e confirmação desconhecida; preservar formulário e explicar seu estado.
- [ ] Restaurar decisões após reinício do navegador/serviço; conferir fontes e jobs interrompidos.
- [ ] Verificar T4-27/T4-28/T4-29/T4-30/T4-51 com falhas injetadas antes/depois da persistência.

**Aceite:** decisão confirmada reaparece após reinício; timeout não duplica comando; rascunho local não é chamado salvo.

<a id="m4-t13"></a>

### M4-13 — Histórico e desfazer

**Arquivos:** `frontend/src/features/review/ReviewHistory.tsx`, `src/review_session/events.py`,
`tests/review_session/test_undo.py`.
**Dependências:** M4-10/M4-11/M4-12 e snapshot/bloqueio M5. **Entrada → saída:** decisão vigente → revogação auditável.

- [ ] Exibir autor, instante, campo, alternativa, valores e motivo de decisão/revogação.
- [ ] Desfazer individual ou parte de lote, preservando eventos e invalidando prévia dependente.
- [ ] Serializar desfazer versus exportar; não alterar retroativamente snapshot já em aplicação.
- [ ] Verificar T4-31/T4-32 e histórico reaberto após reinício.

**Aceite:** decisão revogada não entra em nova exportação; nenhuma alteração apaga o registro de uso anterior.

<a id="m4-t14"></a>

### M4-14 — Consulta e curadoria de catálogo

**Arquivos:** `frontend/src/features/catalog/CatalogWorkspace.tsx`, `src/review_api/routes/catalog.py`,
`frontend/tests/e2e/catalog.spec.ts`.
**Dependências:** M4-02/M4-12, M1/M6. **Entrada → saída:** catálogo/rascunhos → comandos e recibos M1.

- [ ] Criar tabela/detalhe com fonte fiel, reconciliação, conceito/binding e operação disponível.
- [ ] Adicionar/duplicar rascunho com nova identidade e validações por campo.
- [ ] Separar salvar, revisar, publicar e atualizar pin; conferir revisão e papel no servidor.
- [ ] Verificar T4-37/T4-38/T4-39, inclusive conflito de edição sem perder o trabalho local.

**Aceite:** só curador publica versão exata; cadastro não muda IDS/IFC ou cria operação não implementada.

<a id="m4-t15"></a>

### M4-15 — Prévia e acompanhamento de saídas M5

**Arquivos:** `frontend/src/features/export/ExportPreview.tsx`, `frontend/src/features/export/ExportStatus.tsx`,
`src/review_api/routes/exports.py`, `frontend/tests/e2e/export.spec.ts`.
**Dependências:** M4-10 a M4-13, M5 e revalidação M2. **Entrada → saída:** decisões vigentes → prévia/recibos por IFC.

- [ ] Mostrar afetados, campos criados/alterados, antes/depois, portador e pendências.
- [ ] Separar diagnóstico, cópia IFC, aplicação, revalidação e BCF residual.
- [ ] Exigir decisões salvas/prévia vigente e política M5 para saída parcial; conservar falhas de cada etapa.
- [ ] Verificar T4-22/T4-32/T4-33/T4-34/T4-35/T4-36/T4-45/T4-49.

**Aceite:** cópia é nova revisão com revalidação real; aceitar não fecha BCF nem grava transformação visual.

<a id="m4-t16"></a>

### M4-16 — Nova revisão sem reaplicação

**Arquivos:** `frontend/src/features/project/RevisionHistory.tsx`, `src/review_session/service.py`,
`frontend/tests/e2e/revisions.spec.ts`.
**Dependências:** M4-04/M4-12 a M4-15, M1/M5. **Entrada → saída:** nova fonte/pin → análise e histórico separados.

- [ ] Mostrar diferenças de identidade e conservar análises antigas acessíveis.
- [ ] Isolar cache/decisões/geometria por revisão; GUID igual não autoriza transportar decisões.
- [ ] Expor atualização explícita de pin/reprocessamento e proteger rascunho não salvo.
- [ ] Verificar T4-30/T4-36/T4-39/T4-43 com troca rápida de revisões e respostas atrasadas.

**Aceite:** tela sempre identifica IFC/IDS/catálogo efetivos; nenhuma autorização antiga é reaplicada silenciosamente.

<a id="m4-t17"></a>

### M4-17 — Instrumentar uso e recursos com M7

**Arquivos:** `frontend/src/shared/telemetry.ts`, `src/review_session/metrics.py`,
`docs/planejamento/apoios-modulo-04/protocolo-uso.md`.
**Dependências:** M4-01/M4-06/M4-08/M4-10, protocolo M7 e retenção M6.
**Entrada → saída:** eventos de tarefas → medidas locais com denominadores.

- [ ] Registrar tarefa, ação, erro/reversão, espera e recibo sem conteúdo de projeto desnecessário em log geral.
- [ ] Separar tempo humano, espera de serviço e carga 3D; identificar cenário/build/hardware.
- [ ] Preparar roteiro e forma de registrar observações de Felipe/Nonato, com critérios prévios.
- [ ] Verificar T4-41/T4-42/T4-52 e ausência de telemetria externa.

**Aceite:** métricas auditáveis; avaliação interna não é generalizada como resultado científico de população.

<a id="m4-t18"></a>

### M4-18 — Verificar integração e compatibilidade

**Arquivos:** `tests/review_api/`, `tests/review_session/`, `tests/viewer_bridge/`, `frontend/tests/e2e/`,
`docs/planejamento/apoios-modulo-04/matriz-suporte.md`.
**Dependências:** M4-03 a M4-17 e serviços reais. **Entrada → saída:** fatias integradas → matriz de suporte/falhas.

- [ ] Executar T4-01 a T4-53 nos níveis pertinentes, distinguindo mocks de serviços e geometria reais.
- [ ] Injetar falha em viewer/API/persistência/LLM/escrita/revalidação e verificar isolamento.
- [ ] Ensaiar schemas/corpus/navegadores disponíveis; não preencher célula não testada como suportada.
- [ ] Corrigir falhas críticas e repetir casos afetados/percurso completo; registrar restrições restantes.

**Aceite:** sem seleção incorreta, perda de decisão confirmada, escrita indevida ou sucesso falso;
caso sem 3D funcional não é aprovado só porque a lista funciona.

<a id="m4-t19"></a>

### M4-19 — Empacotar operação local

**Arquivos:** `frontend/src/assets/`, `src/review_api/app.py`,
`docs/planejamento/apoios-modulo-04/operacao-local.md`.
**Dependências:** M4-03/M4-12/M4-18 e M6. **Entrada → saída:** build/manifestos → pacote e guia de recuperação.

- [ ] Distribuir fontes, ícones, imagens, workers e WASM locais nas versões/licenças testadas.
- [ ] Fixar loopback/origem autorizada e checagem de acesso em leitura e mutação.
- [ ] Ensaiar build/instalação quando autorizados, runtime offline, reinício e restauração.
- [ ] Registrar T4-37/T4-40/T4-42/T4-50/T4-51 e exigências restantes para implantação IME.

**Aceite:** percurso local independe de CDN; operação institucional não é presumida pelo sucesso em localhost.

<a id="m4-t20"></a>

### M4-20 — Protótipo e teste com Felipe/Nonato

**Arquivos:** `docs/planejamento/apoios-modulo-04/aceite-felipe-nonato.md` e componentes da fatia corrigida.
**Dependências:** escolha visual registrada, M4-18/M4-19 e M5 funcional.
**Entrada → saída:** protótipo/integração e roteiro → evidências, defeitos e decisão de aceite.

- [ ] Comparar as três propostas sobre cenário igual e registrar escolha/correções, sem presumir aprovação.
- [ ] Executar seção 18 no protótipo e depois com serviços reais, identificando cada nível de prova.
- [ ] Registrar resultado por passo, entendimento, tempos/erros e bloqueadores.
- [ ] Corrigir/retestar cenários afetados e concluir somente com evidências revistas pelos responsáveis.

**Aceite:** os dois usuários completam dois pares → federação → pendência → evidência → revisão
individual/lote → salvar/retomar → saídas M5, na matriz de suporte explicitamente declarada.

<a id="m4-testes"></a>

## 15. Testes propostos e evidências

### 15.1 Níveis e corpus

Contrato Python testa tipos, autorização, pré-condições e transações. Componente testa
apresentação/interação. E2E testa navegador/API/serviços/retomada. Ensaio gráfico usa versões
efetivas e hardware. Teste humano observa compreensão/execução. Um nível não substitui outro.

Fixtures mínimas: dois modelos coordenados e seus IDS, GUID repetido entre arquivos e dentro
de um arquivo, localizadores válidos, entidade sem malha, tipo compartilhado, unidades,
requisitos conflitantes, zero aplicáveis, não verificado/erro, fonte manual e conflitos.
Separar falhas sintéticas de casos reais; registrar esperado antes de executar.

### 15.2 Matriz com resultado observável

| Caso | Entrada/ação | Resultado esperado |
|---|---|---|
| T4-01 | Dois IFC/IDS escolhidos em ordem trocada | Análise usa somente associação por hash explicitamente confirmada |
| T4-02 | B ilegível ou M3 de B falha; A funciona | A utilizável; B com etapa/erro; conjunto parcial |
| T4-03 | Mesmo GUID em arquitetura e estrutura | Duas identidades; clicar/decidir A nunca altera B |
| T4-04 | GUID duplicado dentro de A | Duas entidades preservadas quando localizáveis; ambiguidade sem escolha arbitrária |
| T4-05 | localId gráfico difere de EXPRESS ID; várias malhas | Tradução explícita retorna ElementRef correto em todas as malhas |
| T4-06 | Três conversões frias do mesmo IFC/versões | Comparar associação por entidade; divergência bloqueia capacidade mesmo com total de triângulos igual |
| T4-07 | Classe excluída ou entidade sem geometria | Linha continua no diagnóstico com motivo visual explícito |
| T4-08 | A→B e B→A com placements/unidades conhecidos | Relação espacial equivalente no referencial registrado e seleção correta |
| T4-09 | Viewer falha e depois recebe retry | M2/M3/lista/decisões preservados; retry apenas visual; falha 3D não é aceite final |
| T4-10 | Busca nome/ID/tipo e filtros em várias páginas | Consulta/contagens coerentes; seleção não truncada à página |
| T4-11 | Filtro vazio, zero aplicáveis, aplicabilidade indeterminada | Três mensagens distintas; nenhuma conformidade inferida de lista vazia |
| T4-12 | Próxima/anterior, decisão retira item do filtro, clique fora do filtro | Filtros/ordem preservados; seleção contextual e acesso ao histórico |
| T4-13 | Modelos desalinhados; ajuste visual e reset | Aviso/registro, reset correto e nenhuma promessa universal |
| T4-14 | Ocultar/isolar/enquadrar/cortar/contexto/só pendências | Ações reversíveis sem alterar resultado IDS ou contagens formais |
| T4-15 | Cliques rápidos com câmera, corte e transparência | Contorno/lista/detalhe concordam; objeto oculto não captura decisão |
| T4-16 | Validação/exportação com LLM indisponível | Zero chamadas LLM e diagnóstico exportável com cobertura |
| T4-17 | Enriquecer os dois arquivos | Uma inferência ativa no máximo; fila e respostas por modelo |
| T4-18 | Origem ocorrência/tipo/componente do mesmo IFC | Fonte/caminho/valor visíveis; navegar origem preserva alvo |
| T4-19 | Evidência de B usada em A, inclusive manual | Rejeição no servidor; nenhuma transferência no lote |
| T4-20 | Escolher alternativa 2 ou editar candidato | Auditoria guarda alternativa/valor/fontes efetivos, não top-1 |
| T4-21 | Proposta/revisão muda durante edição | Conflito, rascunho preservado e nova revisão do contexto exigida |
| T4-22 | Escrita em tipo afeta ocorrências fora do filtro | Prévia mostra alcance completo e confirmação desse escopo |
| T4-23 | Lote com verificada, conflito, abstenção e alta confiança sem fonte | Só elegíveis sem conflitos; excluídos e motivos explícitos |
| T4-24 | Fundamento manual vale para parte do conjunto | Dividir/excluir alvos inválidos; motivo não se propaga sem pertinência |
| T4-25 | Mudança depois da prévia de lote | Hash/revisão obsoleta impede registro e exige nova prévia |
| T4-26 | Zero/falso/vazio, unidade errada, manual sem fonte ou ID inventado | Valores legítimos preservados; inválidos não aprováveis e estados distintos |
| T4-27 | Commit seguido de perda da resposta e retry | Consulta da chave recupera único recibo; sem duplicação |
| T4-28 | Disco/falha antes do commit | Erro visível, edição preservada e nenhum recibo de sucesso |
| T4-29 | Salvar, fechar navegador/serviço, reabrir | Revisão confirmada, decisões e preferências salvas restauradas |
| T4-30 | Fonte ausente ou outros bytes com mesmo nome | Não carregar substituto silencioso; limitação explícita |
| T4-31 | Desfazer decisão/parte de lote antes de exportar | Revogação durável, histórico intacto e preview invalidado |
| T4-32 | Exportar concorre com desfazer | Ordem inequívoca e snapshot imutável; sem revogação retroativa falsa |
| T4-33 | Aceitar/salvar sem exportar | Aceito/salvo e ainda não aplicado; resultado original inalterado |
| T4-34 | Escrita falha, revalidação falha ou regressão | Etapas separadas; sem selo validado; política M5 explícita |
| T4-35 | Exportar após ajuste visual | Original intacto; sem gravar transformação; viewpoint correto ou limitação declarada |
| T4-36 | Novo IFC com mesmo GUID e dados alterados | Nova análise sem autorizações antigas, com histórico preservado |
| T4-37 | Consulta tenta decidir; revisão tenta publicar; ID alheio forjado | Servidor rejeita acesso/mutação indevidos e não confia no papel/ator do cliente |
| T4-38 | Duplicar rascunho; publicar revisão diferente da validada | Nova identidade sem publicação automática; revisão divergente recusada |
| T4-39 | Novo catálogo publicado com projeto no pin antigo | Pin permanece; diff/atualização explícita gera análise nova |
| T4-40 | Build sem rede externa e assets sem cache prévio | UI/worker/WASM/fontes/imagens locais; sem CDN necessária ou telemetria externa |
| T4-41 | Teclado, foco, painel estreito e percepção de cores | Texto/ícone/contorno suficientes; resize preserva foco/dados |
| T4-42 | Abrir/fechar repetidamente, cache frio/quente | Tempos e recursos medidos/liberados; limites definidos por evidência |
| T4-43 | Evento duplicado, atrasado ou com salto de sequência | Duplicado ignorado; identidade respeitada; gap recuperado por snapshot |
| T4-44 | Misturar os cinco estados M2 | Estados/motivos preservados; agregado não encobre incompletude |
| T4-45 | Exportar completo ou filtrado com paginação | Completo usa universo; filtrado declara seleção/denominador |
| T4-46 | Requisito sem mapping; requisito inadequado | Diagnóstico continua; manual só com alvo verificável; revisão não altera IDS |
| T4-47 | Rejeitar/adiar/aceitar sem revalidação | Pendência/BCF não fecha; fontes/conflitos conservados |
| T4-48 | Cancelar/remover durante carga, callback tardio | Pedido/parada distintos; modelo não reaparece; outro preservado |
| T4-49 | Lote/exportação: A tem sucesso e B falha | Recibos/saídas separados, agregado parcial e retry delimitado |
| T4-50 | Candidata falha em licença/distribuição/localidade/schema | Bloqueio e alternativa registrados; sem suporte anunciado por existir exemplo público |
| T4-51 | Restaurar backup ou schema persistente incompatível | Hash/schema conferidos; migração explícita ou erro sem corromper histórico |
| T4-52 | Felipe/Nonato executam e explicam o percurso | Passos, tempos/erros e entendimento registrados; dificuldade exige correção/reteste |
| T4-53 | Nomes/valores IFC, texto IDS/LLM e erro técnico contêm HTML/script ou instruções | Conteúdo exibido como dado inerte; não executa script/comando, não altera permissão e não expõe segredo/caminho privado |

Cada caso tem tarefa responsável indicada na seção 14; M4-18 consolida a matriz inteira.
Evidência guarda caso, fixture/hash, versões, hardware, esperado/observado, data, responsável,
log e captura local quando útil. Imagem não prova persistência/identidade: verificar recibos,
referências e hashes. Testes de recurso devem declarar o que não foi mensurável.

### 15.3 Execução futura

Após os arquivos/scripts existirem e a execução ser autorizada, proposta de comandos:
`python -m pytest tests/review_api tests/review_session tests/viewer_bridge`,
`npm --prefix frontend run test`, `npm --prefix frontend run test:e2e` e
`npm --prefix frontend run build`. Gerenciador/scripts serão fixados em M4-01.
Nenhum desses comandos foi executado ou é pressuposto como já existente nesta entrega.

Selecionar regressões pertinentes em `tests/foundation/test_contracts.py`, `tests/test_pipeline.py`,
`tests/test_audit_provenance.py`, `tests/test_writer.py`, `tests/test_post_validator.py` e
`tests/test_bcf_exporter.py` na integração futura. Teste legado que exige comportamento
incompatível precisa de revisão fundamentada; suíte verde não é garantia semântica.

<a id="m4-entregas"></a>

## 16. Entregas, dependências e esforço

| Marco | Entrega demonstrável | Dependência e limite |
|---|---|---|
| E4-0 | Plano e pesquisa | Entrega documental, sem protótipo implementado |
| E4-1 | Shell, contratos, corpus e escolha técnica do viewer | M4-01 a M4-03; identidade/licença/localidade testadas |
| E4-2 | Dois pares, análises, cena, lista/filtros/origem | M4-04 a M4-08 e M2 real; 3D funcional |
| E4-3 | M3 serial, individual/manual/lote, salvar/retomar/desfazer | M4-09 a M4-13, M3 e M6; nenhuma escrita durante revisão |
| E4-4 | Curadoria, nova revisão/pin e saída por arquivo | M4-14 a M4-16, M1/M5/M2 e permissões M6 |
| E4-5 | Métricas, suporte, pacote e teste de uso | M4-17 a M4-20, percurso completo observado |

Caminho crítico: contratos → ensaio viewer → federação/lista/evidência → revisão checada →
persistência/undo → saída M5/revalidação → aceite integrado. M7 acompanha as fatias desde os
primeiros ensaios. Curadoria avança conforme M1; não exige LLM pronta. Componentes podem
usar fixtures enquanto serviços evoluem, com simulação rotulada; isso não fecha E4-2/E4-5.

M4 não exige todas as receitas A.1–A.10 prontas para testar uma fatia, mas apresenta campos
sem suporte e a cobertura do domínio, sem escondê-los. Disponibilidade semanal, hardware e
prazo não foram confirmados. Hipótese de esforço: identidade/integração, viewer e retomada/
saídas são altos; lista/detalhe/curadoria são médios após contratos; shell é menor. Reestimar
após E4-1 com Nonato, separando bloqueio de integração de esforço de implementação.
Não reduzir federação ou requisito 3D silenciosamente para cumprir uma estimativa.

<a id="m4-riscos"></a>

## 17. Riscos e decisões abertas

| Risco | Efeito | Contenção / responsável |
|---|---|---|
| Associação visual errada | Aprovação no elemento errado | Identidade composta, T4-03 a T4-06; Nonato/M2 |
| Parser/viewer divergem | Entidade some da cena | M2 autoritativo e cobertura visual; Nonato |
| Coordenadas/unidades/ordem | Federação enganosa | A→B/B→A, conferência e ajuste registrado; Nonato/Felipe |
| Memória/conversão | Travamento/perda de trabalho | Persistência independente, workers e limites medidos; M6 |
| Proposta sem fonte ou auditada errada | Falsa rastreabilidade | Alternativa exata/checagem/precondição; M3/M4 |
| Lote/tipo com alcance oculto | Alteração não revisada | Prévia integral congelada; M4/M5 |
| Salvamento sem recibo | Perda/duplicação | Transação, chave idempotente, reinício testado; M6/M4 |
| Desfazer versus exportação | UI diverge da cópia | Snapshot imutável e ordem transacional; M5/M4 |
| Nova revisão reusa decisão | Autorização indevida | Identidade completa, análise nova; M1/M2/M3/M5 |
| Confusão decisão/conformidade | Falsa conclusão de correção | Estados separados e teste de compreensão; M4/M7 |
| Serviços ainda evoluindo | Mock parece integração | Rotular simulação e aceite por nível; Felipe/Nonato |
| Dependência externa oculta | Falha offline/vazamento | Assets locais e observação de rede; M6/M4 |
| Permissão apenas na UI | Ação/autoria forjada | Verificação no servidor por projeto/operação; M6 |
| Licença incompatível | Distribuição inviável | Revisar dependências/ativos e forma de distribuir antes da escolha; M6 |
| Issue extrapolada | Conclusão técnica sem prova | Versão/data/limite e ensaio próprio; M4/M7 |
| Teste interno generalizado | Alegação científica sem suporte | Avaliação formativa separada de protocolo científico; M7 |
| Edição documental concorrente | Sobrescrita do M3/índices | Somente M4 nesta tarefa; integrar pontes depois |

Decisões abertas delimitadas: biblioteca/releases/pipeline de geometria; tema visual;
navegadores e limites; framework da API/persistência final; política M5 de cópia parcial
e viewpoints; autenticação/retenção/backup M6; corpus coordenado, máquina e cronograma.
Cada uma tem tarefa/gate, sem impedir este planejamento documental.

Se ensaio invalidar candidata, trocar adaptador e repetir gates de identidade/coordenadas/
recuperação. Não remover 3D do MVP sem nova decisão de escopo. Perda de integridade exige
suspender comandos/saídas afetados, preservar fontes/recibos e corrigir antes da liberação;
não apagar história ou voltar silenciosamente ao caminho mutante do legado.

<a id="m4-aceite"></a>

## 18. Aceite verificável com Felipe e Nonato

### 18.1 Roteiro obrigatório

1. Abrir aplicação desktop local, conferir ator/projeto e catálogo.
2. Carregar dois pares arquitetura/estrutura e confirmar vínculo IFC–IDS por linha.
3. Acompanhar análises independentes e abrir federação 3D funcional, reconhecendo parciais.
4. Conferir alinhamento, ocultar/restaurar disciplina, enquadrar e usar corte/contexto.
5. Localizar pendência por lista/filtro/busca e 3D; conferir mesmo arquivo/elemento/campo.
6. Comparar atual/exigido/proposta e navegar origem, incluindo outro elemento do mesmo IFC.
7. Aceitar alternativa exata, editar/preencher com fundamento, rejeitar e manter pendente.
8. Conferir lote, exclusões e alcance; confirmar resultado separado por arquivo.
9. Salvar com recibo; provocar falha controlada e reconhecer edição ainda não salva preservada.
10. Fechar/reabrir navegador e serviço; retomar decisões. Desfazer uma e conferir histórico.
11. Ver prévia M5, campos criados/alterados, antes/depois e pendências; gerar saídas separadas.
12. Distinguir aplicação/revalidação, conferir original preservado e recibos/pendências.
13. Abrir nova revisão e constatar histórico antigo preservado, sem reaplicação silenciosa.

Executar também diagnóstico/exportação sem LLM e falha 3D com continuidade pela lista.
Registrar se a pessoa explica o estado do campo, sua evidência e o que falta gravar/revalidar.
Protótipo clicável avalia compreensão; serviços reais comprovam persistência, geometria e saída.

### 18.2 Definição de conclusão funcional futura

- [ ] Dois pares reais, identidade completa, análises independentes e federação prioritária.
- [ ] 3D e seleção corretos, controles utilizáveis e ausências visuais declaradas.
- [ ] Dois percursos, filtros/contagens, cinco estados e zero aplicáveis sem ambiguidade.
- [ ] Evidência localizável por campo, com isolamento entre IFCs demonstrado.
- [ ] Individual/manual/lote checados, autorizados e sem escrita durante decisão.
- [ ] Salvar/retomar/desfazer verificados com falhas, idempotência e histórico.
- [ ] Curadoria M1 e atualização de pin explícitas, com permissão no servidor.
- [ ] Saídas M5 por IFC, original imutável e escrita/revalidação apresentadas separadamente.
- [ ] Runtime local, recursos e matriz de suporte verificados no hardware registrado.
- [ ] Protótipo e integração avaliados por Felipe/Nonato, bloqueios corrigidos e limites acordados.

Nenhum desses itens funcionais é declarado concluído nesta entrega. O resultado agora é
o planejamento escrito, a pesquisa integrada e os critérios para desenvolvimento/avaliação.

<a id="m4-integracao"></a>

## 19. Sugestões de integração posterior aos índices

**Nenhum destino abaixo foi editado nesta tarefa.** Rever seu estado depois do encerramento
M3, preservando a consolidação autorizada e os índices que seu executor atualizou.

| Destino | Link/ajuste sugerido |
|---|---|
| `docs/planejamento/README.md` | Incluir `[Módulo 4 — Interface e revisão](modulo-04-interface-revisao.md)` na leitura e registrar decisões M4 de 12/10 |
| `docs/README.md` | Incluir `[Plano M4](planejamento/modulo-04-interface-revisao.md)` e apoio de pesquisa |
| `README.md` | Acrescentar link `docs/planejamento/modulo-04-interface-revisao.md` à relação de planos |
| `docs/planejamento/mapa-sete-frentes.md` | Frente 4: Nonato, stack aprovada, dois pares/federação MVP, plano disponível e ensaios futuros |
| `docs/arquitetura/base-do-projeto.md` | Ponte datada para nova UI/API e federação inicial, mantendo inventário legado |
| Planos M1/M2/M3 | Se necessário e coordenado, ponte para `modulo-04-interface-revisao.md#m4-decisoes`, sem reescrever histórico |

Texto sugerido: “Em 12/10, o M4 passou a prever desktop React/TypeScript/Vite/shadcn/ui com
API Python e federação de dois pares IFC/IDS no MVP, mantendo análises por arquivo e LLM
serial. Substitui a previsão de federação como extra futuro. That Open, tema visual,
limites e compatibilidade seguem sujeitos a ensaio. Plano salvo não é implementação.”

Preservar responsáveis, exceção bSDD vigente e dados reconciliados M3. Não recolocar M3
como rascunho aguardando aprovação. Alterações autorizadas do executor M3 não são alterações
indevidas atribuíveis a esta tarefa; diferenças concorrentes devem ser reconhecidas como tais.

<a id="m4-fontes"></a>

## 20. Fontes e verificação documental

### 20.1 Referências locais

- [Planejamento vigente](README.md), [consolidação preservada](CONSOLIDACAO-2026-10-09.md)
  e [mapa](mapa-sete-frentes.md): precedência, inventário e responsabilidades.
- [M1 contratos](modulo-01-dominio-catalogo.md#m1-interfaces): catálogo, versões e curadoria.
- [M2 identidade](modulo-02-nucleo-ifc-ids.md#m2-dados),
  [interfaces](modulo-02-nucleo-ifc-ids.md#m2-interfaces) e [testes](modulo-02-nucleo-ifc-ids.md#m2-testes).
- [M3 contratos](modulo-03-contexto-enriquecimento.md#m3-contratos),
  [evidência](modulo-03-contexto-enriquecimento.md#m3-evidencia) e [interfaces](modulo-03-contexto-enriquecimento.md#m3-interfaces).
- [Arquitetura](../arquitetura/base-do-projeto.md), [fundação](../arquitetura/fundacao-semantica.md),
  [orientações](../../CLAUDE.md) e [contexto](../../PROJECT_CONTEXT.md).
- [Pesquisa M4 de visualizadores](apoios-modulo-04/pesquisa-visualizadores.md): fontes primárias,
  relatos com limites e ensaios propostos.

Foram lidas as seções pertinentes; não se alega leitura integral de toda a bibliografia
nem reprodução de issues. Textos antigos sobre federação/stack/responsabilidades/bSDD
devem ser lidos com as decisões atuais e a precedência declarada.

### 20.2 Manifesto de escrita e preservação

Escrita autorizada no repositório: este arquivo e apoios exclusivos M4. O apoio desta
entrega é `docs/planejamento/apoios-modulo-04/pesquisa-visualizadores.md`. Não há staging,
commit ou push. Índices, M1–M3, mapa, código, configuração, IFC/IDS, experimentos e resultados
não são alvos de escrita desta tarefa. Não foi criada branch, alterado remote ou executado
benchmark, instalação, build ou suíte funcional.

O estado Git inicial foi registrado na saída de leitura e comparado à listagem final;
os mesmos quatro caminhos rastreados já modificados continuam presentes e o índice não
tem alterações staged. O diretório de planejamento já era não rastreado, portanto o status
resumido não enumera sozinho os novos arquivos M4. As operações de escrita desta tarefa
foram dirigidas exclusivamente aos dois arquivos M4 identificados acima.

Um manifesto de hashes documentais foi gravado em diretório temporário do sandbox, mas
esse diretório não permaneceu acessível entre chamadas. **Não se alega comparação completa
de hashes antes/depois dos demais documentos.** A preservação reportada refere-se ao escopo
efetivo das operações de escrita e ao estado Git observado. As alterações M3 concorrentes
autorizadas não são classificadas como indevidas; não se exige working tree limpa.
Validação Markdown é verificação documental, não teste do produto.

### 20.3 Verificação da entrega

Os dois arquivos foram relidos e verificados por checagem documental em Python da `.venv`,
sem importar o aplicativo ou executar sua suíte. Conferência de links ignora exemplos de
links dentro de código simples, que são sugestões de integração. Caminhos futuros em
código simples são propostas; links navegáveis apontam para arquivos/âncoras existentes.

- UTF-8 estrito, sem caractere de substituição; cercas de código balanceadas.
- 59 referências locais verificadas e 44 âncoras explícitas sem duplicação nos dois arquivos.
- 22 ocorrências de links externos no apoio de pesquisa, com as páginas primárias abertas
  nesta integração; essa leitura não comprova funcionamento das bibliotecas.
- 28 decisões, 20 tarefas e 53 casos futuros, com IDs únicos e referências internas consistentes.
- Nenhum trecho de preenchimento incompleto; pendências técnicas e visuais têm encaminhamento explícito.
- Cobertura das decisões revisada na matriz abaixo; nenhuma implementação ou aprovação visual declarada.

### 20.4 Rastreabilidade das decisões para tarefas e testes

| Decisão | Tarefas | Casos principais |
|---|---|---|
| D4-01 — Desktop | M4-01/M4-18/M4-20 | T4-41/T4-52 |
| D4-02 — Stack nova | M4-01/M4-02/M4-19 | T4-40/T4-53 |
| D4-03 — Preservar legado/processamento | M4-02/M4-18 | T4-16/T4-33/T4-35 |
| D4-04 — Localhost e IME posterior | M4-19 | T4-37/T4-40/T4-51 |
| D4-05 — Candidata sujeita a comparação | M4-03 | T4-05/T4-06/T4-42/T4-50 |
| D4-06 — Dois pares/federação MVP | M4-04/M4-05/M4-20 | T4-01/T4-03/T4-08/T4-52 |
| D4-07 — Independência e LLM serial | M4-04/M4-09 | T4-02/T4-17/T4-49 |
| D4-08 — Identidade/sem cruzar evidência | M4-02/M4-05/M4-08/M4-10 | T4-03/T4-04/T4-19 |
| D4-09 — Confirmar vínculos | M4-04 | T4-01/T4-30 |
| D4-10 — Coordenadas/ajuste apenas visual | M4-03/M4-07/M4-15 | T4-08/T4-13/T4-35 |
| D4-11 — Dois percursos sem recarga | M4-06/M4-09 | T4-12/T4-16/T4-17 |
| D4-12 — Três áreas e seleção | M4-01/M4-05/M4-06 | T4-05/T4-12/T4-41 |
| D4-13 — Lista e 3D como qualidade | M4-05/M4-18/M4-20 | T4-07/T4-09/T4-52 |
| D4-14 — Cor/legenda/contorno/texto | M4-06/M4-07 | T4-14/T4-15/T4-41/T4-44 |
| D4-15 — Controles e modos visuais | M4-07 | T4-14/T4-15 |
| D4-16 — Campo/ações | M4-08/M4-10 | T4-18/T4-20/T4-33/T4-47 |
| D4-17 — Manual/checagem/estados distintos | M4-10/M4-15 | T4-21/T4-26/T4-33/T4-34/T4-46 |
| D4-18 — Origem e outro elemento | M4-08 | T4-18/T4-19 |
| D4-19 — Filtros/contagens/vazios | M4-06 | T4-10/T4-11/T4-12/T4-44/T4-45 |
| D4-20 — Lote e fundamento | M4-11 | T4-22/T4-23/T4-24/T4-25/T4-49 |
| D4-21 — Salvar/retomar/desfazer | M4-12/M4-13 | T4-27 a T4-32/T4-51 |
| D4-22 — Revisões e pin | M4-04/M4-14/M4-16 | T4-30/T4-36/T4-39/T4-43 |
| D4-23 — Independência e falha 3D | M4-05/M4-07/M4-09 | T4-09/T4-16/T4-48 |
| D4-24 — Medir antes dos limites | M4-03/M4-17/M4-18 | T4-42/T4-50 |
| D4-25 — Prévia/cópia/revalidação | M4-15 | T4-22/T4-33/T4-34/T4-35/T4-49 |
| D4-26 — Perfis/autoria no servidor | M4-02/M4-10/M4-14/M4-19 | T4-37/T4-38/T4-53 |
| D4-27 — Dados/ativos locais | M4-01/M4-19 | T4-40/T4-53 |
| D4-28 — Teste Felipe/Nonato | M4-17/M4-20 | T4-52 e percurso completo da seção 18 |
