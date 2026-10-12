# Módulo 5 — Saídas e revisões

> **PLANEJAMENTO DOCUMENTAL CONCLUÍDO E VERIFICADO — 12/10/2026.**
> **Implementação não concluída; testes funcionais e ensaios de interoperabilidade não executados.**
> Responsável: **Felipe**. Nonato participa pelas interfaces M4/M6 e lidera M7, com ajuda de Felipe.
> **Sem pendência de aprovação de Felipe para esta conclusão documental.**

**Objetivo:** entregar, por execução e revisão, os IFCs arquitetônico e estrutural separados,
com apenas as alterações aprovadas, verificação do arquivo efetivamente salvo, diagnóstico
final, comparação antes/depois, registro de alterações e BCF das pendências selecionadas.

**Arquitetura proposta:** coordenador local com transação de publicação por IFC, plano de
mudanças imutável, writer restrito a capacidades testadas, verificação após reabertura,
revalidação pelo serviço M2, histórico de issues e projeções do mesmo resultado canônico.
O pacote reúne artefatos independentes e explicita sucessos, falhas e omissões.

**Base tecnológica:** Python/IfcOpenShell/Pydantic e componentes locais existentes, API
Python para M4 React/TypeScript/Vite/shadcn, armazenamento transacional com M6. Biblioteca
BCF, renderizador PDF e versões efetivas serão fixados por ensaios técnicos. Nomes de DTOs,
serviços e arquivos futuros neste plano são **propostas**, não código já implementado.

**Especificação:** decisões explícitas de Felipe recebidas em 12/10/2026, [precedência
vigente](README.md#decisoes-posteriores-de-1210), [M2](modulo-02-nucleo-ifc-ids.md),
[M3](modulo-03-contexto-enriquecimento.md) e [M4](modulo-04-interface-revisao.md).

**Reconciliação:** M3 está concluído documentalmente, com 44 verificações reportadas em seu
apoio; isso não constitui resultado de testes M5. M4 tem documento completo e verificado,
com escolha visual pendente. Não havia plano M5 neste caminho nem tarefa M5 anterior
confirmada no encaminhamento. O protótipo HTML M4 em `prototypes/` evolui separadamente.
Este trabalho não o edita nem certifica seu estado.

**Precedência:** as decisões de 12/10 sobre dois pares IFC–IDS no MVP, responsáveis,
PDF/CSV/JSON, pacote parcial e revisão de saídas substituem previsões históricas diferentes
dos planos anteriores. M2 continua somente leitura. M3 propõe; M4 registra a decisão;
M5 aplica em cópia e solicita revalidação a M2. Consulta pública bSDD restrita pertence ao
fluxo M1/M3 já acordado; M5 não consulta serviços externos para escrever ou exportar.

**Navegação:** [Decisões](#m5-decisoes) · [Escopo e inventário](#m5-base) ·
[Arquitetura](#m5-arquitetura) · [Contratos](#m5-contratos) · [Estados](#m5-estados) ·
[Transação e escrita](#m5-escrita) · [Verificação e comparação](#m5-verificacao) ·
[Pacote e relatórios](#m5-pacote) · [BCF](#m5-bcf) · [Novas revisões](#m5-revisoes) ·
[Operação e erros](#m5-operacao) · [Tarefas](#m5-tarefas) · [Testes futuros](#m5-testes) ·
[Entregas](#m5-entregas) · [Riscos e aceite](#m5-aceite) · [Fontes](#m5-fontes) ·
[Cobertura](#m5-cobertura) · [Encerramento e integração](#m5-encerramento).

<a id="m5-decisoes"></a>

## 1. Decisões aprovadas e restrições globais

Os IDs D5 organizam esta entrega sem renumerar decisões de outros módulos. A matriz da
[seção 17](#m5-cobertura) liga **cada decisão** a uma especificação, tarefa e caso futuro.
Marcar cobertura documental não significa executar o caso ou aprovar uma capacidade.

| ID | Decisão recebida | Obrigação do planejamento |
|---|---|---|
| D5-01 | Pacote por execução/revisão com arquitetura e estrutura separadas | Dois IFCs, dois recibos, diagnósticos e vínculos próprios; nenhum IFC fundido |
| D5-02 | Originais preservados | Fontes imutáveis e hashes antes/depois; saída tem nova revisão |
| D5-03 | Vínculo arquivo/elemento/requisito/revisão | Identidade composta; GUID repetido entre arquivos não colapsa registros |
| D5-04 | Aprovações precisam corresponder a IFC, IDS e catálogo | Conferir versões/hashes, valores anteriores e decisões vigentes antes de escrever |
| D5-05 | Mudanças exigem reavaliação | Invalidar prévia/checagem afetada; nova análise e nova decisão quando necessário |
| D5-06 | Somente campos aprovados; criar Psets/propriedades quando necessário | Allowlist exata de operações e criações; nenhum preenchimento preparatório implícito |
| D5-07 | Cópia temporária por IFC, fechar/reabrir o salvo | Verificação lê bytes persistidos em sessão nova, sem reutilizar handle mutável |
| D5-08 | Conferir campos, valores, tipos, unidades e IDs | Comparar intenção aprovada e valor relido, incluindo portador e alcance |
| D5-09 | Depois da conferência, revalidar IDS | Mesmo serviço M2 e verificador identificado, nova análise vinculada à anterior |
| D5-10 | Falha técnica difere de requisitos não atendidos | Escrita/leitura/verificação técnica e resultado formal têm estados separados |
| D5-11 | Pacote parcial explícito; baixar sucessos | Um IFC ou artefato falho não elimina saídas verificadas independentes |
| D5-12 | IFC verificado com pendências exige ciência explícita | Recibo de ciência ligado ao diagnóstico; jamais declarar conformidade total |
| D5-13 | Comparação antes/depois: resolvidos, abertos e novos | Por arquivo, elemento e requisito; informar também indeterminados e mudanças de escopo |
| D5-14 | Não verificado nunca vira aprovado | Cobertura, erro, não aplicável e conforme permanecem distintos |
| D5-15 | Consulta completa UI, resumo PDF, CSV, JSON e índice | Projeções da mesma revisão, com totais, filtros, hashes e limitações |
| D5-16 | BCF somente das pendências selecionadas, com prévia | Seleção congelada de issues, sem exportar tudo por padrão ou perder exclusões |
| D5-17 | BCF com problema, requisito, elemento, vista e responsável se definido | Referências corretas; falta de vista/identidade explicitada, sem inventar componente |
| D5-18 | Corrigido e revalidado permanece no histórico | Evento de resolução com evidência; exclusão da seleção residual não apaga issue |
| D5-19 | Rejeitar/pular sugestão não encerra issue | Estado de decisão independente do estado da pendência |
| D5-20 | Evitar duplicados; mesma issue conserva ID/histórico, problema novo recebe ID | Registro persistente de identidade e política de reconciliação |
| D5-21 | MVP somente download, sem e-mail/serviços externos | Geração e devolução por arquivos locais, sem envio automático ou BCF-API |
| D5-22 | IFC revisado inicia nova análise/comparação | Histórico preservado; decisões não migram automaticamente |
| D5-23 | GUID alterado não autoriza associação por semelhança | Propor vínculo para revisão ou registrar ausência de correspondência segura |
| D5-24 | BCF devolvido preserva respostas/histórico | Importação identificada e idempotente, mantendo autores, comentários e versões |
| D5-25 | Resolvido externamente aguarda conferência | “Resolução informada, aguardando conferência” até verificar modelo e requisito |
| D5-26 | Mudança de requisito depende do responsável | Pedido de revisão, nova versão IDS/análise; sem ajustar requisito silenciosamente |
| D5-27 | Preservar IFC2X3, IFC4 e IFC4.3; sem conversão automática | Escrita anunciada por schema/release/operação testados, sem inferir suporte |
| D5-28 | Preservar elementos, relações e geometria fora das alterações aprovadas | Diff semântico e allowlist; diferença de serialização não equivale a mudança semântica |
| D5-29 | Tipo compartilhado: mostrar todos os afetados e confirmar alcance | Incluir ocorrências fora do filtro, também as sem requisito aplicável |
| D5-30 | Override na ocorrência somente quando suportado e semanticamente compatível | Não usar override como atalho; prévia/decisão e teste da resolução efetiva |
| D5-31 | Distinguir novas falhas, preexistentes e regressões confirmadas | Base comparável, cobertura e causalidade explicitadas; regressões destacadas |
| D5-32 | Correção que falhou não se encerra | Recibo de falha, issue aberta e possibilidade de revisar/repetir com identidade |
| D5-33 | Permitir revisão/desfazer na cópia preservando antes/depois | Revogação antes do início; nova revisão compensatória após exportação |
| D5-34 | Contratos M1–M7 e responsáveis atuais | Felipe M1/M2/M3/M5; Nonato M4/M6 e liderança M7 com Felipe |
| D5-35 | Ensaios obrigatórios de dois IFCs, escrita, tipo, falha parcial, comparação e BCF ida/volta | Casos futuros com oráculos e evidências definidos; sem execução nesta entrega |
| D5-36 | M3, M4 e M5 conservam estados independentes | Proposta, aprovação, gravação, revalidação e resolução não são sinônimos |
| D5-37 | LLM não altera IFC; sem serviços externos no fluxo M5 | Diagnóstico/exportação independem de inferência, rede externa e geração de propostas |
| D5-38 | Sem contexto cruzado entre IFCs no MVP | Federação visual não autoriza transferência de valor/evidência, inclusive manual |
| D5-39 | Transações e proveniência como proposta concreta | Definir operações, recibos, idempotência, concorrência e recuperação, sem alegar código pronto |
| D5-40 | BCF versão/compatibilidade são escolhas técnicas pesquisadas e testadas | Plano de seleção e ensaio com dono; nenhuma pendência pessoal de aprovação documental |

Nesta entrega, escrita limitada a este documento e apoios exclusivos M5. Preservar planos,
índices, protótipo, alterações locais, código, IFC/IDS, prompts/pinos, GTs, resultados e
locks. Não implementar produto, instalar, executar inferência, benchmark ou teste funcional;
não fazer stage, commit ou push. Verificações documentais temporárias são permitidas.
Os critérios funcionais futuros não bloqueiam o encerramento documental autorizado.

<a id="m5-base"></a>

## 2. Escopo, responsabilidades e inventário real

### 2.1 Dentro e fora do MVP

Inclui diagnóstico exportável sem LLM; prévia e escrita controlada; reabertura/verificação;
revalidação e comparação; pacote completo/parcial; BCF selecionado e devolvido; continuidade
segura de issues; revisão do requisito e desfazer rastreável. Dois pares arquitetura/estrutura
são o piso demonstrável, não o limite permanente de modelos de um projeto.

Não inclui mesclar IFCs, alterar geometria para corrigir projeto, reparar arbitrariamente
relações espaciais, converter schema, reconstruir GUIDs, autoria IDS, ingestão automática de
memorial, inferência entre modelos, e-mail, CDE, sincronização BCF-API ou publicação externa.
Criação de relações estritamente necessárias a um Pset aprovado integra a operação declarada;
não autoriza criar aberturas, vínculos estruturais ou zonas porque existe método legado.

### 2.2 Responsáveis e colaboração

| Frente/papel | Responsável | Entrega para M5 / limite |
|---|---|---|
| M1 | Felipe; curador no papel de publicação | Release/pin, binding, semântica/tipos/unidades; catálogo não decide valor real |
| M2 | Felipe | Fontes preservadas, identidade, observações, capacidades, diagnóstico e revalidação somente leitura |
| M3 | Felipe | Alternativa/manual validado, fundamento, abstenção, conflito e pedido residual; não escreve |
| M4 | Nonato | Decisões duráveis, seleção BCF, vista, prévia, ciência e recibos exibidos; não executa writer |
| M5 | Felipe | Contratos de saída, writer controlado, verificação, pacote, BCF e comparação; liderança deste plano |
| M6 | Nonato | Autorização, armazenamento local/IME, isolamento, limites, backup e recuperação |
| M7 | Nonato, com Felipe | Protocolo, oráculos independentes, métricas de falha/cobertura/esforço; sem reescrever históricos |
| Engenheiro/revisor | Ator identificado pela aplicação | Confirma valor, fundamento, alcance em tipo e ciência de pendências |
| Responsável pelo requisito | Papel identificado no projeto | Decide revisão de IDS e justificativa; M5 registra e encaminha |
| Responsável BCF | Quando definido pela equipe | Recebe atribuição no arquivo; atribuição não envia mensagem nem prova recebimento |

### 2.3 Inspeção estática em 12/10/2026

Acesso real confirmado por listagem, leitura e `git status` no checkout
`C:\Users\Keller_\Desktop\Projetos FC\Pesquisa\ifc-quality-copilot`, branch
`feat/semantic-foundation`, HEAD `a76c2d7a85983ef246761a49db9266c411ea90fd`.
Havia quatro arquivos rastreados modificados e documentos/artefatos não rastreados.
Não havia `AGENTS.md` nos ancestrais consultados nem `.agents/skills` no checkout.
Foram consultados `CLAUDE.md`, contexto, planos e suas seções de contratos/decisões/aceite.
`rg` não está disponível; a busca documental usou PowerShell. Nenhuma dessas leituras
executou o aplicativo ou confirmou capacidade funcional.

| Arquivo existente | Evidência observada | Consequência para o desenvolvimento |
|---|---|---|
| [writer IFC](../../src/writer/ifc_writer.py) | Busca por GUID, `get_psets`, criação/edição de Pset e `salvar` por `file.write` | Reaproveitar operações após ensaio; introduzir alvo composto, portador/alcance e releitura em nova sessão |
| [pipeline](../../src/pipeline.py) | `apply_correction` escreve e chama pós-validação; registra entrada e resolve issue; `export` grava IFC/CSV/JSONL/BCF | Separar decisão/aplicação/resolução e orquestrar publicação transacional; export atual não é prova da nova política |
| [pós-validador](../../src/validation/post_validator.py) | Usa handle em memória; ausência/falha do validador pode devolver erros vazios com avisos | Adaptar ao serviço M2 e preservar não verificado/erro; proibir aprovação por lista vazia |
| [exportador BCF](../../src/bcf/exporter.py) | Declara 3.0, cria markup, usa GUID de elemento em `IfcProject`, fecha qualquer status diferente de `pending` | Corrigir identidade e ciclo; validar schema/receiver; declaração de versão não comprova interoperabilidade |
| [auditoria](../../src/audit/logger.py) | Exporta CSV e JSONL a partir de entradas em memória | Acrescentar eventos duráveis, identidades, operações tentadas/aplicadas/verificadas e proveniência exata |
| [revisão da fundação](../../src/foundation/review.py) | `accepted`/`edited` autorizam; decisão contém GUID e revisor | Reutilizar princípio; modelo precisa revisões, candidato exato, alcance e recibo, conforme M3/M4 |
| [dependências declaradas](../../pyproject.toml) | Piso `ifcopenshell>=0.8`, Python 3.11+, Pydantic, lxml | Piso não é versão instalada/testada; não instalar nem atualizar para escrever o plano |

Ausência de um novo serviço nesta tabela não significa inexistência de toda funcionalidade
semelhante; significa que o contrato proposto não foi certificado por esta inspeção. Os
achados são estáticos, sem reprodução funcional. O exportador BCF existente não deve ser
reutilizado inalterado como gate de conformidade.

### 2.4 Foco da revisão

Cinco condições orientam as tarefas e seus oráculos: aprovação obsoleta (T5-04/T5-05);
tipo/Pset compartilhado com afetados ocultos (T5-10/T5-11); arquivo salvo diferente do
handle validado (T5-02/T5-17); sucesso parcial confundido com conformidade total
(T5-21/T5-22); retorno BCF encerrando issue sem modelo conferido (T5-37/T5-38).

<a id="m5-arquitetura"></a>

## 3. Arquitetura e organização física propostas

### 3.1 Componentes e fronteiras

```text
M1 pin/binding ─┐
M2 diagnóstico ├─> M4 decisões duráveis ─> M5 prévia imutável
M3 candidatos ─┘                              │
                                 conferir identidade/alcance
                                             │
              ┌──────────────────────────────┴─────────────────────────────┐
              │ IFC arquitetura TEMP                IFC estrutura TEMP    │
              │ aplicar -> salvar -> fechar -> reabrir -> conferir        │
              │ nova revisão -> M2 revalidar -> comparar -> liberar       │
              └──────────────────────────────┬─────────────────────────────┘
                                  recibos independentes
                                             │
                              diagnóstico + histórico canônicos
                                             │
                       UI / PDF / CSV / JSON / BCF / índice / download

IFC revisado ou BCF devolvido -> ingestão identificada -> nova análise/merge
                            -> conferência -> histórico, sem autoaprovação
M6 envolve acesso/persistência/limites; M7 consome evidências versionadas.
```

`OutputCoordinator` coordena jobs; `ChangePlanner` resolve operações sem mutação;
`ControlledWriter` altera somente a cópia; `SavedArtifactVerifier` confere bytes reabertos;
`RevisionComparator` compara diagnósticos e preservação; `PackageBuilder` produz derivados;
`IssueRegistry` conserva identidade; `BcfExchangeService` exporta/importa por arquivo.
Nenhum desses nomes representa componente novo já existente no checkout.

M2 permanece autoridade do diagnóstico. M5 não replica parser IDS, tradução de requisitos
ou avaliação formal. A checagem de gravação verifica se a operação aprovada ocorreu; a
revalidação verifica o requisito. São evidências complementares, produzidas em etapas distintas.

### 3.2 Fronteira transacional

A unidade de publicação é **um IFC completo da partição selecionada**. A proposta é aplicar
todas as operações elegíveis confirmadas para aquele IFC ou não publicar sua cópia revista.
Falha numa operação não publica um IFC com metade das mudanças sem novo plano revisado.
Um arquivo pode continuar com pendências não selecionadas: isso é parcialidade de conformidade,
não execução silenciosa de metade do plano aprovado. O pacote admite sucesso de arquitetura
e falha de estrutura, além de falhas isoladas de PDF/BCF, sempre indicadas no índice.

Banco e filesystem não formam automaticamente uma transação única. M6 implementará diário
de intenção, artefatos imutáveis com hash, renomeação atômica no mesmo volume quando disponível
e marcador durável de publicação. Download só consulta artefatos referenciados por recibo
finalizado. Reinício reconcilia intenção, bytes e recibo antes de anunciar sucesso.

### 3.3 Mapa de arquivos futuros

Todos os caminhos abaixo são **propostos para implementação posterior**; não serão criados
nesta entrega. Pastas separadas permitem adaptar o legado sem substituir o instrumento histórico.

| Caminho futuro | Responsabilidade |
|---|---|
| `src/outputs/contracts.py` | DTOs M5, estados, schemas e invariantes de fronteira |
| `src/outputs/change_planner.py` | Pré-condições, portadores, conflitos e plano/alcance congelado |
| `src/outputs/coordinator.py` | Ciclo por arquivo/pacote, recibos, cancelamento e recuperação |
| `src/outputs/store.py` | Eventos, identidades e publicação via persistência acordada com M6 |
| `src/outputs/writer_adapter.py` | Allowlist, tipos/unidades e chamadas controladas ao writer |
| `src/outputs/saved_verifier.py` | Fechar/reabrir, readback, esquema e preservação semântica |
| `src/outputs/revalidation.py` | Solicitar nova análise M2 e relacionar snapshots |
| `src/outputs/comparison.py` | Delta de resultados, cobertura, correspondências e regressões |
| `src/outputs/package.py` | Manifesto, índice, hashes, artefatos e recibo de download |
| `src/outputs/reports.py` | Projeções PDF/CSV/JSON do snapshot canônico, sem motor paralelo |
| `src/outputs/issues.py` | Continuidade de issue, eventos e resolução verificada |
| `src/outputs/bcf_exchange.py` | Adaptador de biblioteca/schema BCF, prévia e merge de retorno |
| `src/outputs/revisions.py` | Ingestão revisada, correspondência e pedidos de revisão de requisito |
| `tests/outputs/` | Contratos, fixtures mínimas, falhas injetadas e integração M2/M4/M6 |
| `tests/fixtures/outputs/` | Corpus identificado, esperado independente e arquivos BCF de intercâmbio |

Modificar posteriormente os pontos de [pipeline](../../src/pipeline.py),
[writer](../../src/writer/ifc_writer.py), [pós-validação](../../src/validation/post_validator.py),
[auditoria](../../src/audit/logger.py) e [BCF](../../src/bcf/exporter.py) só por adaptadores/testes
de compatibilidade e condição versionada. Rotas da nova API Python e UI serão integradas com
Nonato no destino definido pelo M4; não pressupor que `src/ui` Streamlit seja a nova interface.

<a id="m5-contratos"></a>

## 4. Contratos entre M1–M7, identidade e proveniência

### 4.1 Contratos reutilizados

Reutilizar o significado de `SourceArtifactRef`, `AnalysisIdentity`, `ElementRef`,
`EvidenceObservation`, `RequirementResult`, `DiagnosticSnapshot` e `TypedValue` de
[M2](modulo-02-nucleo-ifc-ids.md#m2-dados); `CatalogReleaseRef` e capacidades de
[M1](modulo-01-dominio-catalogo.md#m1-interfaces); `FieldRef`, `FieldAlternative`,
`ManualCandidate`, `CandidateValidation`, `ReviewEnvelope` e `ResidualRequest` de
[M3](modulo-03-contexto-enriquecimento.md#m3-contratos); decisões, prévias e
`ExportHandoff` de [M4](modulo-04-interface-revisao.md#m4-contratos).

`PairRef` identifica o vínculo confirmado entre modelo IFC e IDS; corresponde ao
`ModelPairBinding` M4, não a um terceiro formato de associação. `SessionRef` agrupa a UI,
mas não compartilha evidência nem autoriza escrita entre pares.

```text
modelo lógico = project_id + model_id
fonte = model_id + ifc_revision_id + sha256
elemento = model_id + ifc_revision_id + express_id, com GlobalId adicional
requisito = ids_sha256 + caminho/índice estrutural, com ID declarado adicional
decisão = decision_id + review_revision + hash do candidato/escopo
execução de saída = export_run_id + partição model_id + attempt_id
artefato = artifact_id + hash + tamanho + papel + revisão + recibo
issue = issue_id persistente + vínculos de ocorrência/requisito/revisão
```

STEP ID só localiza na revisão exata. GUID igual em arquivos diferentes continua sendo duas
identidades; GUID ausente/duplicado dentro do arquivo bloqueia seleção ambígua, sem inventar
um novo GUID. Unicidade confirmada no arquivo é necessária para referência interoperável
por GUID. Mesmo GUID em nova revisão não transfere aprovação.

### 4.2 Objetos propostos M5

| Objeto | Campos essenciais | Invariante |
|---|---|---|
| `OutputRequest` | projeto/sessão, pares, snapshots, decisões duráveis, seleção de formatos, command_id, revisão esperada | Não aceita caminho arbitrário, valor livre ou campo não aprovado |
| `ChangeOperation` | operation_id, FieldRef, requisitos, decisão, portador, caminho literal, ação, valor anterior/novo tipados, unidade, tipo IFC, efeitos permitidos | Aprovação identifica exatamente valor, origem, alvo e alcance |
| `ImpactScope` | entidade portadora, todos os ElementRefs afetados, valores efetivos antes/depois, compartilhamento, hash do conjunto | Filtro/página UI não reduz os afetados reais |
| `ChangePlan` | plan_id/hash, partições, identidade IFC/IDS/catálogo/verificador, operações, exclusões/motivos, impactos, capabilities | Imutável; qualquer mudança relevante cria nova prévia |
| `PreflightReceipt` | hash do plano, comparação de versões, permissões, checagens atuais, elegíveis/bloqueados | Ausência de gate ou erro não é autorização |
| `ExportRun` | export_run_id, solicitação, planos, estado, eventos/seq, jobs por arquivo, artefatos | Estado do pacote não apaga resultados individuais |
| `FileWriteReceipt` | run/model/attempt, original e cópia, operações tentadas/aplicadas, erros e instante | Applied em memória não implica saved/verified |
| `SavedVerification` | hash salvo/reaberto, schema, readback por operação, mapa de IDs, diff semântico, geometria/relações, cobertura/erros | Só refere bytes efetivamente reabertos; ausência de comparação não vira preservado |
| `RevalidationReceipt` | nova revisão/hash, analysis_id M2, verificador/capacidades, snapshot/hash, estado/cobertura | Mesmo núcleo M2; execução concluída pode conter não conformidades |
| `ResultDelta` | pares antes/depois, correspondências, categoria de mudança, comparabilidade e fundamento | Separar falha nova, regressão, limite e mudança de requisito |
| `ReleaseAcknowledgement` | ator M6, UTC, artifact/hash, diagnóstico/hash, lista de pendências/regressões/limites, texto e versão | Ciência não muda resultado IDS; nova revisão invalida o recibo |
| `IssueRecord` | issue_id, problema/requisito, linhagem de alvo, estado interno, episódios, comentários, BCF topic ID | Mesmo problema conserva histórico; não deduplicar apenas por campo/GUID |
| `BcfPreview` | bcf_selection_id/hash, issues/revisões, destinatário quando definido, viewpoints/snapshots, limitações e perfil BCF | Só a seleção confirmada é serializada |
| `BcfImportReceipt` | arquivo/hash, versão, fonte declarada, tópicos novos/conhecidos/ambíguos, eventos mesclados, rejeições | Retorno não escreve IFC nem fecha por status externo |
| `RevisionMatch` | modelo, referências antiga/nova, método, evidência, estado, ator/UTC se revisado | Semelhança é candidata; relação não autoriza reaplicar valor |
| `PackageManifest` | package_id, revisão, run, inventário por arquivo/formato, resultados/omissões, hashes, recibos e vínculos | Artefato faltante não aparece como sucesso ou link válido |
| `DownloadReceipt` | request_id, artefatos e hashes liberados, ciência necessária, UTC, resultado de entrega | Disponibilizado/solicitado não prova abertura pelo receptor |

`Actor` é principal autenticado/autorizado M6. `ErrorRecord` contém código, etapa, escopo,
causa segura, correlation_id e ação possível. `Event` contém ID único, sequência, UTC,
ator/origem, entidade, estado anterior/novo e referências imutáveis. `CapabilityRef`
identifica schema/release, operação, portador, tipo/unidade, versão do writer/verificador,
fixture, evidência e limitações. Nenhum ID enviado pelo navegador funciona como credencial.

`TypedValue` conserva zero, falso, string vazia, nulo e ausência. Decimal tem representação
controlada; `"01"` não vira inteiro 1; unidade desconhecida não vira adimensional. Antes/depois
guardam lexical original, valor tipado, tipo IFC, unidade explícita/herdada e eventual
transformação já exibida e aprovada. Não normalizar valor diferente após a decisão silenciosamente.

### 4.3 Fronteiras e contratos de serviço

| Fronteira | M5 recebe | M5 entrega / critério |
|---|---|---|
| M1 | Pin, binding, semântica, versão e capacidade operacional | Mudança de pin invalida plano dependente; campo literal sem mapping não ganha equivalência automática |
| M2 | Diagnóstico completo/observações, schema, fontes, leitor e serviço de análise | Nova revisão salva para revalidar; recebe resultado com todos os estados, sem motor concorrente |
| M3 | Candidato exato, checagem, evidência e motivo residual | Aplicação/erro e vínculo de revisão; falha M3 não impede exportar diagnóstico/BCF |
| M4 | `ExportHandoff`, confirmação de prévia, seleção BCF, vista e ciência | Progresso por arquivo, prévia integral, recibos e URLs locais autorizadas; ajustes visuais nunca vão ao IFC |
| M6 | Principal/ACL, diretórios, lock/lease, armazenamento, limites e builds | Eventos duráveis, recuperação, métricas e erros seguros; autorização também no serviço |
| M7 | Corpus/oráculos, condição, protocolo e limites de interpretação | Evidência por capacidade, deltas/cobertura, tempos/erros e ensaios; testes não são ganho científico |

Operações de referência, **sem implementação**:

| Operação | Entrada → saída | Regra |
|---|---|---|
| `preview_outputs` | OutputRequest + Actor → ChangePlan + PreflightReceipt | Leitura apenas; prévia identifica tudo que será criado/alterado |
| `start_outputs` | plan_id/hash + command_id + Actor → ExportRun | Reconfere gates e congela decisões por IFC |
| `get_output_run` | run_id + Actor → ExportRun + recibos | Consulta independente da vida da aba |
| `cancel_outputs` | run_id/partições + command_id + Actor → CancelReceipt | Recebimento não é confirmação de parada |
| `acknowledge_release` | artefato/diagnóstico exatos + ciência + Actor → ReleaseAcknowledgement | Não modifica conformidade nem recupera artefato tecnicamente falho |
| `build_package` | run_id + formatos/seleção BCF + Actor → PackageManifest | Só usa snapshots/recibos congelados |
| `download_artifacts` | package/revisão + seleção + Actor → DownloadReceipt | Confere disponibilidade, integridade e ciência exigida |
| `preview_bcf` | issues/revisões selecionadas + Actor → BcfPreview | Sem inferência e sem seleção implícita de todas as issues |
| `import_bcf` | artefato local identificado + perfil + command_id + Actor → BcfImportReceipt | Ingestão segura; merge não autoriza correção IFC |
| `compare_revisions` | revisões/snapshots antigos e novos + Actor → ResultDelta + RevisionMatches | Comparabilidade explícita e conflitos preservados |
| `review_match` | candidata + decisão/fundamento + Actor → RevisionMatch | Correspondência humana não aprova valor nem requisito |

`CancelReceipt` conserva o sentido M2/M3: ID e registro durável do pedido. As operações
se integram às rotas propostas no [M4](modulo-04-interface-revisao.md#m4-contratos), sem
inventar um segundo endpoint que escreva fora da revisão. Wire format versionado e adaptadores
serão acordados em M5-02; alteração incompatível exige nova versão, migração testada e histórico.

<a id="m5-estados"></a>

## 5. Estados independentes e política de liberação

### 5.1 Eixos

| Eixo | Estados de referência | Interpretação |
|---|---|---|
| Proposta M3 | proposed, abstained, unsupported, failed, cancelled, not_requested | Não autoriza escrita |
| Decisão M4 | pending, draft, accepted, edited, rejected, skipped, revoked | Somente accepted/edited vigentes e checados entram no plano |
| Job M5 | queued, preflight, applying, saving, reopening, checking, revalidating, packaging, completed, partial, blocked, failed, cancelled | completed descreve execução, não conformidade |
| Operação de escrita | not_attempted, applied_in_memory, saved, readback_verified, failed, discarded | Recibo distingue intenção, persistência e resultado relido |
| Verificação técnica | pending, verified, failed, not_verified | verified exige todos os gates obrigatórios do perfil identificado |
| Avaliação M2 | conforme, não conforme, não aplicável, não verificado, erro | Mantém exatamente o estado e razão fornecidos pelo núcleo |
| Liberação IFC | withheld, awaiting_acknowledgement, downloadable, superseded | Download não apaga pendências |
| Issue interna | open, awaiting_external, resolution_reported, resolved_verified, reopened, superseded_requirement | Superseded não significa corrigida no modelo |
| Artefato | planned, generating, available, failed, omitted, cancelled | Omitido tem motivo, mesmo quando BCF não foi selecionado |

Rótulo UI de `resolution_reported`: **“Resolução informada, aguardando conferência”**.
“Corrigido e revalidado” só aparece com gravação conferida e resultado pertinente conforme.
Issue sem correção do sistema pode resolver na nova revisão externa quando M2 comprovar o
requisito e a correspondência; a origem da resolução permanece externa.

### 5.2 Matriz de liberação

| Situação por IFC | Download da cópia IFC | Diagnóstico/registro e estado |
|---|---|---|
| Gravação, reabertura ou readback falhou | Retido | Falha técnica explícita; original íntegro; sem encerrar correção |
| Preservação semântica obrigatória falhou ou ficou indeterminada | Retido | Diff/limite identificado; não chamar de tecnicamente verificado |
| Reabriu e conferiu, mas revalidação M2 não iniciou/falhou inteiramente | Retido como saída regular | Diagnóstico de falha pode ser baixado; nenhum selo IDS |
| Verificado tecnicamente, revalidação completa e conforme no escopo | Liberável | Informar exatamente escopo/capacidade, sem certificação global do edifício |
| Verificado tecnicamente, revalidação com não conformidades | Exige ciência explícita | Mostrar pendências, antes/depois e “sem conformidade total” |
| Verificado tecnicamente, cobertura IDS parcial ou erros localizados | Exige ciência explícita do escopo desconhecido | Demais resultados válidos preservados; não verificado/erro nunca aprovados |
| Regressão IDS confirmada após escrita tecnicamente íntegra | Retido até revisão específica; liberação só com ciência da regressão identificada | Oferta de revisar/desfazer; issue da correção falha permanece aberta |
| Arquitetura liberada e estrutura falhou | Arquitetura pode ser baixada | Pacote parcial, estrutura ausente e motivo visível |
| IFCs liberados e PDF ou BCF falhou | IFCs podem ser baixados | Pacote parcial; derivados bem-sucedidos conservados |

“Tecnicamente verificado” significa gates executados com evidências e sem erro bloqueante
no perfil declarado, incluindo preservação. Não é promessa de todos os possíveis checks
EXPRESS/geométricos nem equivalência a conformidade IDS. Falhas técnicas preexistentes que
impedem interpretação confiável bloqueiam; advertências preexistentes não bloqueantes são
comparadas e declaradas, sem desaparecer do relatório.

A liberação com pendências é decisão de produto aprovada; a implementação proposta exige
ator, UTC, hashes, revisão do diagnóstico e lista de limites/regressões reconhecidos. Ciência
não autoriza alterar mais campos nem contorna falha técnica. Uma nova cópia, novo diagnóstico
ou mudança relevante de pendência exige nova ciência. Filtrar a tela não reduz o que é reconhecido.

<a id="m5-escrita"></a>

## 6. Pré-escrita, transação por IFC e alteração controlada

### 6.1 Pré-condições verificadas duas vezes

Conferir ao produzir a prévia e novamente ao iniciar a transação:

1. Projeto/ator autorizado, par IFC–IDS confirmado e snapshot M2 persistido.
2. Bytes/revisões IFC e IDS, pin/hash catálogo e verificador/capabilities iguais aos da decisão.
3. Decisão durável, não revogada, alternativa/manual exatos e checagem válida para seu hash.
4. Fonte/fundamento existentes e pertinentes; sem contexto cruzado entre arquivos.
5. Elemento/portador localizados univocamente na revisão; valor anterior ainda igual ao aprovado.
6. Operação, tipo IFC, unidade, criação e schema/release cobertos por capacidade testada.
7. Lista de afetados completa e confirmada, inclusive compartilhamento por tipo ou Pset.
8. Ausência de operações incompatíveis para o mesmo alvo; requisitos simultâneos preservados.
9. Espaço/recursos e destino interno disponíveis, original protegido e cópia com caminho distinto.
10. Plano/decisões ainda vigentes sob controle de concorrência e chave idempotente válida.

Qualquer divergência bloqueia a partição afetada, produz motivo e exige novo plano/revisão.
Não “atualizar” hashes no pedido antigo para fazê-lo passar. Se apenas BCF/PDF precisa ser
regenerado a partir do mesmo snapshot, reusar IFC verificado sem reaplicar operações.

### 6.2 Sequência transacional proposta

| Etapa | Ação | Recibo/evidência |
|---|---|---|
| W0 | Reservar job/partição e congelar revisão de decisões; serializar com undo | command_id, hashes e evento de início |
| W1 | Conferir preflight; copiar fonte imutável para diretório temporário exclusivo | Hash igual à origem, tentativa e owner do diretório |
| W2 | Abrir apenas a cópia e conferir alvo/antes; aplicar allowlist completa | Journal de operações e mudanças efetivas, inclusive entidades criadas |
| W3 | Salvar arquivo temporário completo, finalizar handles/buffers e registrar hash/tamanho | Recibo saved; sem link de download ainda |
| W4 | Descartar sessão mutável; abrir arquivo salvo em nova sessão/processo | Hash relido, parser/schema e falhas independentes |
| W5 | Conferir operações, IDs e preservação; fechar sessão de conferência | SavedVerification, diff e cobertura |
| W6 | Identificar cópia como nova revisão; pedir análise M2 com IDS/pin fixados | RevalidationReceipt e DiagnosticSnapshot posterior |
| W7 | Comparar antes/depois, atualizar histórico e decidir liberação | ResultDelta, issues e eventual pedido de ciência |
| W8 | Publicar artefato imutável e recibo recuperável; gerar derivados | Hash final igual ao verificado, manifesto e links locais |

Se W2–W5 falhar, a cópia fica indisponível para download regular e é descartada ou mantida
em quarentena local conforme retenção M6. Journal e diagnósticos permanecem. Nunca desfazer
“no original”. Se W6 falhar, pode repetir somente análise dos mesmos bytes verificados;
se bytes/plano mudaram, criar outra tentativa/revisão. Não marcar sucesso por saída temporária
existente ou por worker terminar com código zero sem os recibos obrigatórios.

### 6.3 Allowlist de escrita

Primeira fatia: atributos alfanuméricos permitidos e propriedades em Psets, incluindo criação
quando necessária. Cada operação declara `set_attribute`, `set_property` ou `create_property`
e, se necessário, `create_pset` como dependência explícita da mesma decisão. Expansões para
classificações/Qto só ficam habilitadas após contrato tipado e ensaio específico; a existência
de um método legado não as torna suportadas. Campos sem capacidade seguem como pendência/BCF.

Pset novo conserva nome literal/caminho aprovado e portador correto; não escolher alias,
substituir conjunto nem criar propriedades vizinhas “úteis”. Relações/IDs de novas entidades
necessárias são inventariados como efeitos estruturais autorizados da operação. Não mudar
GlobalId de elemento existente, unidades globais, classe, placement ou representação geométrica.

Valor nulo, exclusão e propriedade ausente não são equivalentes. A proposta inicial não oferece
purga genérica; qualquer remoção futura exige operação/decisão própria. Configurar explicitamente
o comportamento de bibliotecas para não transformar `None` em exclusão acidental. Tipos não
podem ser deduzidos só de Python ou do nome da propriedade. Conversão de unidade precisa ter
grandeza compatível, precisão e valor resultante aprovados; unidade do projeto não muda.

### 6.4 Tipo compartilhado e outros portadores compartilhados

M2 informa ocorrência, tipo, associação e propriedades efetivas sem achatar proveniência.
M5 expande inversas do portador para enumerar **TODOS os afetados**, inclusive ocultos,
fora da página, de outras classes, sem IDS aplicável e ocorrências com override existente.
A prévia mostra valores efetivos antes/depois por ocorrência e o conjunto completo com hash.
Uma alteração no tipo pode não mudar o valor efetivo de uma ocorrência com override; ainda
assim ela integra a análise do alcance, com esse motivo explícito.

Confirmar alcance integral antes de alterar tipo. Se o usuário aprovar só uma ocorrência,
o writer não pode modificar o tipo compartilhado. Um override na ocorrência é alternativa
somente quando schema, portador, requisito e regra de herança forem compatíveis e testados;
exige prévia própria com o efeito efetivo verificado depois de salvar. Se não houver rota
segura, bloquear essa operação e manter pendência. Clonar tipo/desassociar ocorrências não é
fallback automático no MVP.

Psets/valores compartilhados diretamente por várias ocorrências também exigem análise do
alcance. Não basta verificar `IfcRelDefinesByType`; nenhum objeto referenciado em comum pode
ser alterado silenciosamente fora do escopo. Se a lista mudar entre prévia e escrita, invalidar
o plano. Todas as ocorrências afetadas entram na revalidação e no diff.

### 6.5 Desfazer e repetição

Antes de W0, `UndoCommand` M4 registra revogação e invalida a prévia. Se W0 já congelou a
decisão, a UI mostra exportação em curso: cancelamento é solicitado, sem prometer revogação
retroativa. Depois da publicação, desfazer cria novo ciclo/revisão a partir de fonte preservada
ou operações compensatórias novamente aprovadas e verificadas; o arquivo entregue e seus
recibos permanecem históricos. Não apagar alteração anterior nem devolver “conforme” por desfazer.

`command_id` repetido com payload igual retorna job/recibo anterior; payload distinto é
conflito. Retry de falha usa attempt_id novo ligado à intenção original, sem duplicar issue,
decisão ou alteração. Duas solicitações concorrentes para a mesma revisão/decisões são
serializadas; trabalhos de modelos diferentes podem ter recursos separados sob M6.

<a id="m5-verificacao"></a>

## 7. Arquivo salvo, preservação e comparação de diagnósticos

### 7.1 Conferência depois da reabertura

Conferir o hash do arquivo que será entregue, parser, schema declarado/efetivo e identidade.
Ler novamente cada alvo e portador: caminho literal, existência da propriedade/Pset, valor
bruto/tipado, tipo IFC, unidade explícita/herdada e valor efetivo. Comparar com a operação
aprovada; tolerância numérica só quando declarada e testada no perfil, sem tolerância genérica
que transforme valor diferente em igual. Zero, falso, códigos, acentos e caracteres escapados
recebem casos específicos.

Verificar GlobalIds existentes, classes e relação original–cópia. STEP IDs podem mudar na
serialização: produzir mapa confiável durante transformação/releitura, com prova de unicidade,
sem assumir estabilidade numérica. IDs novos só pertencem às entidades novas da allowlist.
Duplicação, perda de identidade ou correspondência ambígua impede a verificação do escopo.

### 7.2 Preservação semântica

Registrar baseline antes da alteração e comparar depois de reabrir: população de elementos,
atributos fora da allowlist, relacionamentos e associações, estrutura espacial, tipos,
materiais/classificações, unidades, placements e representações geométricas. A diferença
permitida é o fechamento explícito das operações aprovadas: propriedade/Pset/ligação necessária
e metadados técnicos declarados pelo perfil. Mudança de cabeçalho/data de serialização fica
separada; alteração de propriedade não pode esconder mudança geométrica como “metadado”.

Hash de bytes diferente é esperado na saída; não prova corrupção nem preservação. Usar diff
semântico versionado com normalização somente de aspectos sem efeito, como ordem de linhas,
STEP IDs renumerados e espaços. Não normalizar ordem de coleções que tenha significado,
unidades, placements ou relações para esconder delta. Contagem igual de entidades também
não é prova suficiente: uma entidade pode ter sido substituída por outra.

Para geometria, comparar grafo de representação e placements identificados; ensaio adicional
de geometria calculada, quando suportado, registra kernel/opções/tolerâncias e esperado
independente. Não exigir gerar malha inexistente para validar propriedade, mas exigir evidência
de que representações existentes não foram alteradas. Se o comparador não cobrir uma estrutura
necessária, registrar preservação não verificada e reter a cópia regular até ensaio/solução.
Não há autorização para presumir invariância porque “o writer só edita Psets”.

### 7.3 Revalidação M2

Depois de W5, M2 analisa os bytes reabertos como nova revisão, usando o mesmo IDS, pin,
verificador, opções e capacidades do baseline. Reavaliar o arquivo inteiro e requisitos
suportados no MVP, incluindo aplicabilidade/cardinalidade, para detectar efeitos fora dos
campos alterados. Otimização incremental só poderá substituir esse percurso após equivalência
demonstrada; não basta revalidar apenas GUIDs aceitos.

Se motor/build/capacidade mudou, preservar antes original e produzir baseline comparável
com o mesmo verificador, identificado separadamente. Sem isso, delta é não comparável quanto
à regressão formal. Falha geométrica não converte requisito informacional independente em
falha; cada escopo conserva capacidade/limite. Erro de execução não vira não conformidade
factual nem conforme por ausência de falhas.

### 7.4 Classificação antes/depois

| Antes → depois, com alvo/requisito comparáveis | Categoria | Interpretação |
|---|---|---|
| Não conforme → conforme | Resolvido verificado | Registrar evidência; se houve operação M5 conferida, “corrigido e revalidado” |
| Não conforme → não conforme | Aberto/preexistente | A tentativa não resolveu; manter esperado/encontrado e eventual mudança parcial |
| Conforme → não conforme | Regressão confirmada | Mesmas condições comparáveis; destacar, investigar causa e oferecer revisão/desfazer |
| Não verificado/erro → não conforme | Nova falha observada | Não afirmar que a escrita criou o problema; antes não havia prova de conformidade |
| Não conforme → não verificado/erro | Aberto com verificação incompleta | Não resolver; destacar perda de cobertura |
| Qualquer → não aplicável/elemento ausente | Mudança de escopo | Reavaliar cardinalidade, remoção e aplicabilidade; não contar automaticamente como corrigido |
| Sem avaliação antiga → avaliação nova | Novo escopo/novo problema quando houver falha | Comparação limitada; causa a investigar |
| IDS/verificador/identidade incompatíveis | Não comparável | Exibir lado a lado, motivo e revisão responsável |

“Novo problema” designa nova ocorrência de problema identificada; “regressão confirmada”
exige evidência anterior satisfatória comparável. Atribuir causalidade à operação M5 exige
examinar diff/alcance e reproduzir sob condição controlada no desenvolvimento; não atribuir
culpa pelo simples fato de o diagnóstico ocorrer depois. Problema técnico e alerta complementar
têm linhas/categorias próprias e não entram como falha IDS no denominador.

Somar pares elemento–requisito comparáveis separadamente de especificações sem elementos,
novos/removidos e indeterminados. Totais por arquivo e conjunto mostram contribuintes e
denominadores; não subtrair listas de issues para inferir quantos requisitos foram aprovados.
As mesmas classificações alimentam UI, PDF, CSV, JSON e seleção BCF residual.

<a id="m5-pacote"></a>

## 8. Pacote por execução/revisão, relatórios e download

### 8.1 Inventário proposto

O pacote é um conjunto identificado; ZIP é uma conveniência de download local, sem obrigação
de juntar os IFCs em um modelo. Nomes abaixo são um exemplo de organização, não arquivos
gerados nesta entrega. Nomes reais usam IDs seguros e nomes de exibição sanitizados.

```text
pacote-<package_id>-<revision>/
  indice.html
  manifesto.json
  resumo.pdf
  avaliacoes.csv
  alteracoes.csv
  registro.json
  modelos/
    arquitetura-<model_id>-<revision>.ifc
    estrutura-<model_id>-<revision>.ifc
  diagnosticos/
    arquitetura-antes.json
    arquitetura-depois.json
    estrutura-antes.json
    estrutura-depois.json
  bcf/
    arquitetura-pendencias.bcf
    estrutura-pendencias.bcf
```

Ausência de artefato aparece no manifesto com `failed`, `omitted` ou `cancelled` e motivo.
Não colocar arquivo vazio com nome de sucesso. Se não houve escrita solicitada, informar
“somente diagnóstico”, com snapshot inicial como resultado final daquele percurso; não
fabricar revisão IFC ou comparação. Se não há pendências selecionadas, BCF fica omitido
por seleção vazia e contagem zero, sem uma issue fictícia.

`manifesto.json` identifica projeto, pacote/revisão, execução, modelos/pares, hashes/revisões
IFC/IDS, catálogo, writer/M2/build/capabilities, estado/cobertura, artefatos com tamanho/hash,
ciências, erros, filtros e vínculos antes/depois. O hash do próprio manifesto pertence ao
recibo externo de publicação, evitando autorreferência. O índice humano apresenta esses
estados e links relativos. Nenhum caminho privado absoluto ou URL externa é necessário.

### 8.2 Fonte canônica e projeções

`registro.json` é o intercâmbio versionado de operações, decisões, proveniência, resultados
de verificação/revalidação, issues/eventos e referências aos diagnósticos completos. Preservar
ordem de eventos, tipos/unidades, antes/depois, erros e tentativas descartadas. O formato JSONL
legado pode ser entrada de migração explícita; não renomear JSONL como JSON único válido.
Registros grandes podem ser particionados com índice/hash e contrato publicado, sem perder
consulta completa nem truncar silenciosamente.

| Saída aprovada | Conteúdo mínimo | Critério de fidelidade |
|---|---|---|
| UI completa M4 | Diagnóstico inteiro consultável por elemento/requisito, todos os estados, operações, issues e histórico | Paginação não limita universo; filtros/contagens e snapshot visíveis |
| Resumo PDF | Identidade, arquivos, visão antes/depois, resolvidos/abertos/novos/regressões, cobertura/limites, ciência e índice de detalhes | Dizer “resumo”; não ocultar não verificados nem simular relatório integral |
| CSV de avaliações | Uma linha por avaliação/escopo, arquivo, ElementRef, requisito, esperado/encontrado, antes/depois e categoria | Zero aplicáveis usa escopo de especificação, sem elemento inventado |
| CSV de alterações | Uma linha por operação/efeito identificado, decisão, portador, antes/depois tipados/unidades, estado e erro | Operação tentada não é contada como aplicada; não perder afetados de tipo |
| Registro JSON | Histórico/auditoria e vínculos canônicos completos | Schema versionado, referência resolvível, contagens e hashes coerentes |
| Índice do pacote | Inventário, estado completo/parcial, sucesso/falha por IFC/formato e links | Nunca chamar conjunto incompleto de pacote completo |
| BCF por arquivo | Somente seleção confirmada de pendências, com prévia e perfil de intercâmbio | Mesmo registro de issues e diagnóstico; limites de receptor explícitos |

Campos CSV propostos: `package_id`, `export_run_id`, `model_id`, `ifc_revision_before`,
`ifc_revision_after`, `ids_sha256`, `analysis_before`, `analysis_after`, `element_ref_before`,
`element_ref_after`, `requirement_id`, `scope_kind`, `state_before`, `state_after`,
`delta_category`, `expected`, `observed_before`, `observed_after`, `value_type`, `unit`,
`issue_id`, `operation_id`, `comparison_reason`. CSV de alteração acrescenta decisão/ator,
fonte, portador, tipo IFC, verificação e erro. Colunas não pertinentes ficam vazias com
semântica definida no dicionário do formato; vazio não é evidência de valor nulo IFC.

Coleções e valores estruturados são serializados de forma declarada por célula, conservando
JSON como autoridade. Exportação UTF-8 e delimitador/quoting têm perfil fixado e teste de
reimportação. Neutralizar fórmulas perigosas na apresentação CSV e registrar a transformação;
o valor original permanece no JSON. Datas UTC, separador decimal e unidades não dependem
silenciosamente do locale da máquina.

PDF deve permitir identificar os dois arquivos, revisão, condição da análise, data, páginas,
limites e onde consultar a informação completa. Texto extenso tem regra de quebra/continuação;
nomes longos não são cortados sem indicação. Fontes/ícones ficam locais. Links ao pacote usam
IDs e caminhos relativos quando úteis; PDF isolado conserva identificadores legíveis mesmo
sem resolver hyperlinks.

### 8.3 Sucesso parcial e ciência

Exemplo: arquitetura teve 8 operações conferidas, 5 falhas resolvidas e 2 abertas; estrutura
falhou ao reabrir. O índice mostra arquitetura verificada com pendências, estrutura retida,
pacote parcial, diagnósticos disponíveis e ação de ciência para liberar o IFC arquitetônico.
As contagens do exemplo são sintéticas, não resultados medidos. Se o PDF falhar depois,
arquitetura/JSON/CSV disponíveis continuam baixáveis com esse segundo motivo de parcialidade.

Um botão “baixar arquivos disponíveis” mostra exatamente o subconjunto, seus estados e
ciências exigidas. A ciência pode ser feita para uma seleção explícita de artefatos, mantendo
recibos por arquivo/hash. Não aceitar um checkbox genérico antigo da sessão para qualquer
revisão futura. Download individual carrega referência ao diagnóstico e registro correspondente;
não depender apenas de o usuário ter aberto a tela de falhas.

Retentar PDF/CSV/BCF a partir do mesmo snapshot gera nova revisão de manifesto/recibo, sem
reescrever IFC nem apagar o pacote anterior. Revalidar um IFC é outra análise e pode exigir
novo pacote. Objeto publicado é imutável; substituição de arquivo de mesmo nome não atualiza
um recibo antigo.

<a id="m5-bcf"></a>

## 9. BCF selecionado, interoperabilidade e retorno

### 9.1 Escolha técnica e limites de evidência

Proposta: **BCF-XML 3.0 como primeiro perfil de ensaio**, **BCF-XML 2.1 como perfil alternativo
de compatibilidade**, sem downgrade automático. Motivo: o legado declara 3.0, mas necessita
correção; os dois formatos permitem testar troca por arquivo. A documentação IfcOpenShell
**0.9.1** declara leitura/escrita BCF-XML 2.1/3.0 na biblioteca BCF; isso é evidência de candidata,
não de pacote instalado ou compatibilidade da combinação local. [Biblioteca BCF oficial](https://docs.ifcopenshell.org/bcf.html).

O formato 3.0 distingue tópico, referência a arquivo/IfcProject e componente; contém markup,
viewpoints e metadados de projeto/extensões. Viewpoints têm identidade própria e são imutáveis;
coordenadas numéricas usam unidades fixas. Essas distinções fundamentam o adaptador e seus
ensaios. [BCF-XML 3.0, documentação oficial da branch release_3_0](https://raw.githubusercontent.com/buildingSMART/BCF-XML/release_3_0/Documentation/README.md).

Não misturar estruturas XML entre versões. O ensaio alternativo usa documentação e XSD
próprios, incluindo organização do arquivo ZIP, sem apenas trocar `VersionId`.
[BCF-XML 2.1, branch release_2_1](https://raw.githubusercontent.com/buildingSMART/BCF-XML/release_2_1/Documentation/README.md).

M5-11 fixa commit/tag e hashes dos schemas/fontes, biblioteca e ferramenta receptora local
com versão/licença. Primeiro validar o pacote pelos schemas, depois importar/exportar em
ferramenta compatível e conferir a volta. Escolher 3.0 se cumprir o corpus obrigatório; escolher
2.1 se o receptor necessário não cumprir 3.0 e 2.1 preservar os dados obrigatórios. Registrar
perdas/limites; se nenhum cumprir, manter BCF não liberado para aquele perfil e corrigir o
adaptador. Esta é responsabilidade técnica de Felipe com Nonato na vista; não pergunta de
aprovação pessoal nem pendência que impeça fechar o plano documental.

Nenhum schema foi incorporado, nenhuma biblioteca instalada e nenhuma ferramenta receptora
foi testada nesta entrega. O nome e versão vencedores só serão anunciados com recibos do
ensaio futuro. Não deduzir compatibilidade a partir do método atual chamado `export`.

### 9.2 Política Copilot para seleção e prévia

BCF comunica pendências selecionadas: não conformidades ainda abertas, informação ausente,
abstenções pertinentes, necessidade de decisão externa ou revisão de requisito. Erro técnico
pode ser selecionado como tópico de diagnóstico separado, sem se passar por falha IDS.
Corrigidos/revalidados permanecem no histórico/JSON/PDF e saem da seleção residual.
A exportação BCF deste MVP contém somente pendências selecionadas; a resolução verificada
fica registrada internamente e nos relatórios, sem incluir tópicos resolvidos nessa saída.

A prévia enumera issue_id, tópico BCF, modelo/revisão, requisito e problema, esperado/encontrado,
elemento/portador, severidade, estado, responsável se definido, comentário, vista/snapshot,
limites e ação necessária. O usuário escolhe os tópicos e confirma o hash da seleção. Mudança
de diagnóstico/issue/vista invalida a prévia afetada. Uma issue com vários requisitos guarda
todos; só agrupar se problema e ação forem os mesmos, sem apagar requisitos independentes.

Proposta inicial: um `.bcf` por IFC no pacote. Isso conserva origem e reduz ambiguidade quando
GUIDs se repetem entre arquitetura e estrutura. Ainda exigir associação do arquivo no receptor;
um arquivo BCF separado não prova que o receptor abriu o IFC correto. Não incluir o IFC dentro
do BCF por conveniência; arquivos são entregues separadamente com índice e hashes.

### 9.3 Identidade, vista e informação suficiente

`IfcProject` deve referir o projeto IFC correto quando usado; `IfcGuid` do componente aponta
ao elemento. `topic_guid` é identificador BCF persistente da issue. Nenhum deles é intercambiável
com model_id, hash de arquivo, STEP ID ou GUID de outro objeto. O manifesto conserva todos os
vínculos, e a prévia mostra o arquivo/revisão. Nomes iguais não resolvem ambiguidade.

Vista exportada: câmera, seleção/visibilidade e cortes suportados pelo perfil, snapshot local
quando disponível e referência à revisão IFC. M4 fornece `ViewerAssetManifest`/`DisplayTransform`.
M5 converte a vista para o referencial/unidades do perfil BCF e do IFC correspondente; uma
transformação visual federada não é gravada no IFC. Registrar transformações aplicadas à vista
e testar escala, eixos, rotação, origem distante, corte e elemento selecionado no receptor.

Snapshot é apoio visual, não prova de identidade nem conformidade. Se a vista não puder ser
gerada, mostrar a limitação antes de exportar: repetir captura, retirar tópico ou autorizar
um tópico documental sem localização gráfica, desde que o perfil o admita e isso seja marcado
como capacidade limitada. Esse caso não satisfaz o aceite de BCF com vista funcional. Falha
3D não bloqueia diagnóstico/JSON; não inventar câmera ou imagem de outro modelo.

GUID ausente/duplicado ou issue de cardinalidade sem elemento exige tópico documental com
identidade interna/descrição e limitação de seleção, ou exclusão explícita. Não fabricar
`IfcGuid`/`AuthoringToolId` nem usar STEP ID como identificador universal. Se o receptor não
conservar a distinção de arquivos com GUID igual, limitar o perfil à abertura isolada do IFC
correto e declarar essa condição; não anunciar interoperabilidade federada.

Responsável somente quando informado pelo ator autorizado; não adivinhar pessoa/e-mail.
Autor do tópico/evento é identidade registrada, distinta de responsável. O arquivo pode
conter atribuição sem enviar qualquer notificação. Links a requisitos/catálogo usam identidade
e descrição legíveis; se o receptor não suportar referência estruturada, manter referência
textual e sidecar JSON, com perda declarada e ensaio. Não depender de URI interna inacessível
para que o destinatário saiba qual requisito e revisão precisa conferir.

### 9.4 Ciclo de issue e prevenção de duplicados

O `IssueRegistry` nasce do diagnóstico/residual identificado. Chave de busca de continuidade
combina projeto, modelo lógico, linhagem de elemento confirmada, identidade/linhagem do
requisito, campo/portador e natureza do problema. Não usar somente `(guid, issue_type)` nem
igualdade de título. `issue_id` e `topic_guid` são atribuídos uma vez e persistidos; exportar
novamente a mesma issue não cria UUID novo.

Mesma pendência não resolvida, mesmo contexto e correspondência segura: acrescentar revisão,
evidência e comentários ao mesmo histórico. Problema diferente, novo requisito sem continuidade
aprovada ou outro elemento: ID novo, com relação ao anterior quando pertinente. Um problema
idêntico que reaparece após resolução pode reabrir a mesma issue com novo episódio, apenas se
a continuidade for demonstrada; uma causa/condição distinta recebe nova issue. Registrar a
decisão de reconciliação e não apagar a resolução anterior.

Rejeitar/pular sugestão altera apenas revisão M4; aceitar altera autorização. Gravar em memória
não resolve. `resolved_verified` exige snapshot posterior pertinente, correspondência segura e
resultado conforme; correção M5 exige também readback da operação. Falha mantém issue aberta
com tentativa registrada. Retirada/alteração do requisito usa `superseded_requirement`, com
decisão do responsável e vínculo da substituição; não contar como correção do IFC.

### 9.5 Importação do BCF devolvido

1. Ingerir arquivo local sem executar conteúdo; identificar hash, versão e perfil. Preservar
   bytes recebidos como fonte, inclusive quando houver itens não suportados.
2. Validar ZIP/XML e referências, limites, IDs e modelo/revisão esperados. Não abrir URLs,
   baixar anexos externos ou assumir associação pelo nome do arquivo.
3. Resolver topic_guid conhecido dentro do projeto/par correto. Colisão ou origem ambígua
   vai para revisão, sem sobrescrever issue de outro projeto/modelo.
4. Deduplicar evento/comentário por ID e conteúdo. Mesmo ID com conteúdo modificado preserva
   versão anterior, origem/importação e autoria declarada; não sobrescrever texto silenciosamente.
5. Acrescentar respostas, comentários, vistas e status externos ao histórico, distinguindo
   autor declarado no BCF de usuário autenticado que fez a importação.
6. `Closed`/resolvido externo vira `resolution_reported`: “Resolução informada, aguardando
   conferência”. Solicitar/referenciar IFC revisado ou verificar revisão já fornecida no M2.
7. Conferir elemento/requisito na nova análise: conforme e correspondência segura permite
   resolução verificada; ainda falha mantém aberto; não verificado mantém conferência pendente.
8. Produzir recibo: novos/conhecidos/duplicados/conflitantes/rejeitados, perdas de campos,
   associação escolhida e próximo passo, sem nenhuma escrita IFC.

Mesma importação repetida é idempotente. BCF sem IFC revisado ainda pode adicionar discussão,
mas não prova correção. Tópico desconhecido entra como issue externa identificada e pede
associação/revisão, sem criar automaticamente requisito ou autorização. Histórico externo
com data fora de ordem conserva data original e data de ingestão; ordem de chegada não é
verdade de engenharia. Extensões não interpretadas permanecem no original e no inventário
de limitações; não prometer round-trip sem perda se o adaptador não as preservou.

<a id="m5-revisoes"></a>

## 10. IFC revisado, correspondência e requisito alterado

### 10.1 Nova revisão

Receber IFC revisado cria `SourceArtifactRef` novo com hash, modelo lógico explicitamente
associado, revisão predecessora e proveniência. Rodar M2 com o IDS/pin escolhido e registrar
se mudou. O arquivo antigo, diagnósticos, decisões e pacotes permanecem consultáveis.
Não substituir o conteúdo do caminho antigo e tratá-lo como mesma análise.

Correspondência tem dois níveis: localização na revisão e continuidade entre revisões.
Dentro da cópia produzida pelo próprio writer, journal/mapeamento mais conferência do grafo
sustentam continuidade. Entre exportações de ferramenta externa, usar modelo/linhagem,
unicidade de GUID e verificação de contexto. Mesmo GUID com classe/papel incompatíveis ou
conflito de linhagem fica ambíguo. Não copiar valor/decisão só porque a correspondência existe.

| Condição | Resultado de correspondência | Uso permitido |
|---|---|---|
| Mesmo modelo, GUID único persistente, contexto sem contradição | Correspondência por identidade, com evidência registrada | Comparar; reavaliar o conteúdo novo antes de decidir |
| GUID alterado, candidato parecido por nome/tipo/localização/geometria | Candidata para revisão humana | Mostrar diferenças e fundamento; não vincular automaticamente |
| Vários candidatos, GUID duplicado ou linhagem desconhecida | Ambígua | Comparação por conjuntos e inspeção, sem encerrar issue específica |
| Nenhum candidato seguro | Sem correspondência segura | Conservar issue anterior e marcar novo/removido/indeterminado |
| Split/merge de elementos | Relação proposta um–muitos/muitos–um | Revisão explícita; sem tratar como identidade um–um automática |
| Arquivos distintos, ainda que mesmos GUIDs | Modelos distintos | Sem matching/evidência cruzada no MVP |

Vínculo humano exige ator, fundamento, referências antiga/nova e escopo. Pode ser revogado
por evento posterior, invalidando comparações dependentes; histórico não é apagado. A seleção
de um candidato não revalida requisitos nem autoriza reaplicar correções antigas.

### 10.2 Requisito e catálogo

`RequirementReviewRequest` M3/M4 identifica IDS/hash, localização, problema, evidência e
responsável. M5 conserva falha original e estado “revisão de requisito solicitada”. Quando
o responsável fornecer nova versão aprovada, registrar justificativa, diff, associação entre
requisitos e nova análise. Alteração de nome/título não estabelece equivalência; semântica,
aplicabilidade e restrições precisam ser comparadas.

Mudança de requisito é apresentada como mudança de condição, nunca “resolvida por escrita”.
Se o requisito foi retirado, histórico fica supersedido com motivo e responsável, não corrigido.
Novo requisito cria identidade nova e eventual issue nova. Continuidade do problema só é
mantida quando revisão responsável estabelecer vínculo e escopo, preservando ambas as versões.

Catálogo atualizado exige novo pin explícito e rechecagem/reprocessamento pertinente M1/M3.
Resultado IDS independente continua conforme M2, mas aprovações de escrita associadas à
versão anterior precisam reavaliação. Um mapping novo não pode converter erro/não verificado
em aprovação sem execução real. Alteração do verificador recebe nova identidade e baseline
comparável conforme seção 7.3.

<a id="m5-operacao"></a>

## 11. Operação local, cancelamento, erros e rastreabilidade

### 11.1 Persistência e proveniência

Proposta: banco transacional local para jobs/eventos/índices e armazenamento imutável por
artefato para IFC/IDS/BCF/diagnósticos, alinhado a M1–M4/M6. SQLite é candidato para desktop;
uso institucional/multiusuário exige topologia e ensaio próprios. Não presumir que compartilhar
arquivo de banco em rede resolve concorrência/backup.

Cada evento de alteração identifica projeto/par, modelo/revisão, ElementRef, requisito,
FieldRef, operação, decisão exata, candidato/fundamento, autor, UTC, antes/depois, tipo/unidade,
capacidades, tentativa, resultado técnico e snapshot M2. Auditoria append-only proposta
significa histórico lógico não apagado por edição normal; hashes encadeados podem detectar
alteração, mas não constituem assinatura digital ou não repúdio por si.

Não auditar a primeira sugestão quando foi escolhida a segunda. Falha antes de aplicar gera
tentativa sem mudança; falha depois de salvar gera registro de cópia não liberada; operação
descartada continua rastreável. Logs técnicos resumidos ficam separados da auditoria de
engenharia, com ACL/retenção definidas por M6, sem registrar segredos e caminhos pessoais.

### 11.2 Concorrência, interrupção e cancelamento

Pedidos têm revisão esperada, idempotency key e ownership da partição. Lock/lease controla
o ciclo que conflita com undo, troca de pin e exportação concorrente. Não bloquear navegação
somente leitura da UI enquanto o worker aplica. Preferir worker isolado para chamadas nativas;
limites concretos serão calibrados no corpus e hardware registrados.

| Momento do cancelamento | Comportamento proposto |
|---|---|
| Antes de W0/W1 | Confirmar cancelado, nenhuma cópia publicada e nenhuma escrita |
| Durante W2/W3 | Pedido recebido; parar em fronteira segura, descartar/quarentenar temporário e manter journal |
| Chamada nativa não retorna | M6 pode encerrar somente worker/job pertencente ao pedido, sob política testada |
| Durante W4–W6 | Preservar evidência concluída; cópia não recebe liberação por etapa faltante; permitir nova tentativa de verificação |
| Depois de publicação confirmada | Informar conclusão anterior ao cancelamento; artefato histórico não é revogado silenciosamente |
| Entre os dois IFCs | Conservar sucesso já confirmado, cancelar partição restante e marcar pacote parcial/cancelado |
| Durante relatório/ZIP | Manter IFCs/artefatos finalizados; arquivo derivado incompleto não vira disponível |

Após queda, comparar journal, hashes, marcadores e banco: confirmar publicação já concluída,
retomar etapa idempotente ou registrar tentativa interrompida. Não repetir writer por abrir
a sessão. Cópia desconhecida é isolada; reconciliação não inventa recibo. Backup inclui fontes,
artefatos, banco, capacidades e versões; restauração confere hashes e referências antes de
liberar downloads. Limpeza apaga somente temporários pertencentes ao job e sob diretório
autorizado, com retenção de evidência de falha; nunca original ou saída já publicada.

### 11.3 Catálogo de erros e recuperação

| Código proposto | Escopo/efeito | Recuperação e apresentação |
|---|---|---|
| `approval_stale` | IFC/IDS/pin/candidato/decisão divergiu | Bloquear partição e mostrar mudança; nova análise/checagem/prévia |
| `identity_ambiguous` | Elemento/portador não unívoco | Não selecionar primeiro; revisão de identidade/BCF documental |
| `unsupported_write` | Schema/operação/portador sem prova | Manter pendência; ensaio de capacidade antes de habilitar |
| `scope_changed` | Afetados diferentes da prévia | Listar diferença e pedir nova confirmação do alcance |
| `conflicting_operations` | Valores/ações incompatíveis no mesmo campo | Voltar à revisão, preservar requisitos e decisões conflitantes |
| `write_failed` | Operação/salvamento falhou | Sem cópia regular; repetir de fonte preservada com nova tentativa |
| `readback_failed` | Parser/valor/tipo/unidade/IDs divergem | Reter IFC; mostrar operação e encontrado, sem encerrar issue |
| `preservation_failed` | Delta fora da allowlist | Reter, conservar diff e investigar regressão técnica |
| `preservation_not_verified` | Comparador não cobre estrutura necessária | Reter, declarar limite e desenvolver ensaio |
| `revalidation_failed` | M2 indisponível/execução sem resultado confiável | Sem selo IDS; retry análise dos mesmos bytes quando possível |
| `ids_pending` | Revalidação confiável contém falhas/limites | Ciência explícita e diagnóstico, sem conformidade total |
| `regression_confirmed` | Resultado satisfatório comparável virou falha | Destaque/revisão/desfazer; ciência específica se liberar |
| `artifact_failed` | PDF/CSV/JSON/BCF/ZIP não gerado | Pacote parcial; baixar sucessos e repetir só o derivado |
| `bcf_invalid_or_unsupported` | Arquivo/schema/versão inválidos ou sem suporte | Preservar original devolvido, recusar merge afetado e informar perfil |
| `bcf_merge_conflict` | ID igual/contexto conflitante | Revisão explícita, sem sobrescrever issue/comentário |
| `storage_or_resource_limit` | Disco/memória/tempo excedidos | Parar seguramente; manter recibos; calibrar/repetir sem consumo ilimitado |
| `permission_denied` | Projeto/operação sem autorização | Não revelar dados nem disponibilizar artefato de outro projeto |

Cada erro contém etapa, escopo, código, correlation_id, mensagem segura e ação possível.
Stack trace não é mensagem principal. “Sem pendências selecionadas”, “nenhum elemento
aplicável”, “não analisado” e “falhou” não são a mesma lista vazia.

### 11.4 Entradas/saídas não confiáveis e limites

BCF é ZIP/XML: rejeitar travessia de diretório, caminhos absolutos, links especiais, DTD/entidade
externa, referências externas automáticas, bombas de expansão e arquivos fora do perfil.
Validar limites de membros/tamanho expandido/profundidade/tempo antes de extrair em área do
job. Usar schemas locais fixados. Comentários, nomes e imagens são dados; escapar HTML/PDF,
neutralizar fórmulas CSV, verificar imagens/anexos sem executar scripts ou seguir instruções.

Downloads locais passam por ACL de projeto e artefato, hash e ciência quando exigida. URLs
de download não podem ser caminhos livres. Relatórios não carregam fontes, CDN, telemetria,
imagens ou URIs externas. Ausência de rede/LLM não impede pacote determinístico. Limites de
tamanho, memória, disco, duração, retenção e simultaneidade pertencem à matriz M6/M5-17:
medir antes de publicar valores, mas configurar limites explícitos antes de uso operacional.

<a id="m5-tarefas"></a>

## 12. Tarefas futuras, dependências, entregáveis e responsáveis

Todas as caixas abaixo são **trabalho funcional futuro não executado**. Felipe é responsável
M5 em cada tarefa; participações de Nonato e dos papéis de domínio estão explicitadas.
Os caminhos são propostas da seção 3.3. Cada tarefa começa por um caso com esperado
independente, demonstra a falha/ausência de capacidade, implementa a menor fatia e comprova
o comportamento. Não executar esses passos durante a presente entrega documental.

<a id="m5-t01"></a>

### M5-01 — Fixar baseline, corpus e condição de ensaio

**Responsável:** Felipe, com Nonato/M7 nos oráculos. **Dependências:** decisões e fontes
preservadas M1–M4. **Arquivos futuros:** `tests/fixtures/outputs/manifest.json`,
`tests/outputs/conftest.py`, documentação de capacidade M5. **Consome:** fontes/licenças,
requisitos e verificador identificados. **Produz:** corpus/oráculos versionados e baseline.

- [ ] Registrar hash/schema/release/exportador dos dois modelos, IDS/pin e fontes autorizadas.
- [ ] Criar fixtures mínimas de propriedades, tipo compartilhado, GUID repetido, falhas e BCF;
  esperado não é produzido pelo writer ou comparador em teste.
- [ ] Separar casos reais, sintéticos e instrumentos históricos; reservar casos negativos.
- [ ] Conferir T5-01/T5-02/T5-56 e publicar manifesto com lacunas, incluindo caso real IFC4.3.

**Entregável/aceite:** corpus reproduzível com proveniência, esperado, condição e capacidade
alvo por caso; ausência de caso real impede generalização daquela capacidade, não outras tarefas.

<a id="m5-t02"></a>

### M5-02 — Estabilizar contratos, identidade e estados

**Responsável:** Felipe com Nonato/M4/M6. **Dependência:** M5-01 e contratos M1–M4.
**Arquivos:** `src/outputs/contracts.py`, `tests/outputs/test_contracts.py`.
**Consome:** DTOs de origem. **Produz:** contratos M5 versionados da seção 4, sem redefinir M2.

- [ ] Especificar schemas de operações, planos, recibos, deltas, pacote e erros com referências.
- [ ] Criar casos de GUID igual entre arquivos e estado aceito/não aplicado/não conforme.
- [ ] Implementar validação de identidade, TypedValue e transições permitidas por eixo.
- [ ] Verificar T5-01/T5-14/T5-23/T5-57 e alinhar a projeção UI sem status único de sucesso.

**Entregável/aceite:** contrato publicado e exemplos válidos/inválidos; IDs e estados conservam
significado em todos os consumidores. JSON ilustrativo não substitui teste de contrato.

<a id="m5-t03"></a>

### M5-03 — Planejar alterações e bloquear aprovações obsoletas

**Responsável:** Felipe. **Dependências:** M5-02, M2 e decisões duráveis M4.
**Arquivos:** `src/outputs/change_planner.py`, `tests/outputs/test_preflight.py`.
**Consome:** ExportHandoff, CandidateValidation, ReviewEnvelope e snapshots.
**Produz:** ChangePlan imutável e PreflightReceipt com operações/exclusões explícitas.

- [ ] Cobrir mudança de IFC/IDS/catálogo, candidato, valor anterior, permissão e revogação.
- [ ] Resolver alvos literais e portadores; detectar comandos conflitantes e criações necessárias.
- [ ] Congelar decisões/valores/escopos e repetir os gates no início da partição.
- [ ] Verificar T5-04 a T5-09/T5-59, incluindo segunda alternativa e manual sem mapping.

**Entregável/aceite:** plano revisável por arquivo, nenhuma operação sem aprovação exata;
divergência retorna conflito e conserva rascunho/histórico, sem ajustar pedido antigo.

<a id="m5-t04"></a>

### M5-04 — Demonstrar alcance de tipo e portador compartilhado

**Responsável:** Felipe com Nonato/M4 e revisor BIM. **Dependências:** M5-03, leitura M2.
**Arquivos:** `src/outputs/change_planner.py`, `tests/outputs/test_shared_scope.py`.
**Consome:** grafo de portadores/associações e plano. **Produz:** ImpactScope completo/hash.

- [ ] Preparar tipo com três ocorrências, uma fora do filtro e outra com override existente.
- [ ] Enumerar todas as inversas e valores efetivos, também Pset compartilhado sem tipo.
- [ ] Validar confirmação do conjunto e bloquear alcance mudado; oferecer override só se testado.
- [ ] Demonstrar T5-10 a T5-13 e conferir alcance igual na UI, plano, escrita e revalidação.

**Entregável/aceite:** nenhum afetado oculto; aprovação de uma ocorrência não modifica tipo
inteiro. Opção sem capacidade fica bloqueada com motivo e encaminhamento residual.

<a id="m5-t05"></a>

### M5-05 — Implementar writer restrito e valores tipados

**Responsável:** Felipe. **Dependências:** M5-03/M5-04, capacidade e corpus.
**Arquivos:** `src/outputs/writer_adapter.py`, adaptação de `src/writer/ifc_writer.py`,
`tests/outputs/test_writer_values.py`. **Consome:** operações autorizadas sobre cópia.
**Produz:** mudanças efetivas e journal de entidades/portadores criados.

- [ ] Fixar operações permitidas e testes de atributo/Pset/propriedade, tipo IFC e unidade.
- [ ] Aplicar no portador exato; criação necessária faz parte da mesma operação aprovada.
- [ ] Recusar purga, normalização posterior diferente, schema incompatível e campos extras.
- [ ] Conferir T5-03/T5-14/T5-15/T5-16 e ausências/duplicações sem chamadas a serviço externo.

**Entregável/aceite:** alterações em memória correspondem à allowlist e são rastreáveis;
salvamento e validade ainda dependem das próximas tarefas. Nenhum suporte universal inferido.

<a id="m5-t06"></a>

### M5-06 — Orquestrar cópia, persistência e publicação por IFC

**Responsável:** Felipe com Nonato/M6. **Dependências:** M5-02/M5-05.
**Arquivos:** `src/outputs/coordinator.py`, `src/outputs/store.py`,
`tests/outputs/test_transactions.py`. **Consome:** plano confirmado e fontes imutáveis.
**Produz:** ExportRun/FileWriteReceipt, journal e candidatos de artefato para verificação.

- [ ] Injetar falhas em W1/W2/W3 e após renomeação antes do recibo; definir recuperação esperada.
- [ ] Implementar diretório exclusivo por job/arquivo, hash da fonte e transação de publicação.
- [ ] Serializar início/undo, deduplicar command_id e manter partições independentes.
- [ ] Verificar T5-21/T5-45/T5-47/T5-48/T5-54; nunca publicar meio plano por IFC.

**Entregável/aceite:** fonte preservada e recibo inequívoco mesmo com timeout/queda; pacote
pode ser parcial entre arquivos. Arquivo temporário existente não significa sucesso.

<a id="m5-t07"></a>

### M5-07 — Reabrir, conferir gravação e preservação

**Responsável:** Felipe com revisor BIM. **Dependências:** M5-05/M5-06.
**Arquivos:** `src/outputs/saved_verifier.py`, `tests/outputs/test_saved_verification.py`.
**Consome:** bytes salvos, allowlist e baseline semântico. **Produz:** SavedVerification.

- [ ] Preparar caso com memória correta/arquivo adulterado e caso de delta geométrico oculto.
- [ ] Fechar sessão mutável, abrir novamente bytes persistidos e verificar campos/tipos/unidades/IDs.
- [ ] Comparar população, relações, placements e representações fora da allowlist por perfil.
- [ ] Executar futuramente T5-02/T5-17 a T5-20; bloquear verificação incompleta ou delta indevido.

**Entregável/aceite:** evidência de que o artefato entregue é o conferido; diff de serialização
separado de semântica. Não validar somente o objeto em memória ou comparar contagens.

<a id="m5-t08"></a>

### M5-08 — Revalidar a cópia pelo núcleo M2

**Responsável:** Felipe. **Dependências:** M5-07 e serviço M2 versionado.
**Arquivos:** `src/outputs/revalidation.py`, adaptador de `src/validation/post_validator.py`,
`tests/outputs/test_revalidation.py`. **Consome:** revisão/hash conferidos e identidade IDS/pin.
**Produz:** nova análise M2/DiagnosticSnapshot e RevalidationReceipt.

- [ ] Cobrir erro do verificador, faceta não suportada, zero aplicáveis e cobertura parcial.
- [ ] Submeter arquivo inteiro ao mesmo núcleo; conservar configurações/verificador do baseline.
- [ ] Persistir todos os resultados, inclusive conforme/não aplicável/não verificado/erro.
- [ ] Verificar T5-23/T5-24/T5-26/T5-57 e funcionamento independente de M3/LLM.

**Entregável/aceite:** revalidação é da cópia salva e não segundo motor permissivo;
falha completa retém saída regular, sem converter aviso em aprovação.

<a id="m5-t09"></a>

### M5-09 — Comparar antes/depois e destacar regressões

**Responsável:** Felipe com Nonato/M7. **Dependências:** M5-08 e identidade M5-02.
**Arquivos:** `src/outputs/comparison.py`, `tests/outputs/test_comparison.py`.
**Consome:** snapshots comparáveis e mapeamento de alvo/requisito. **Produz:** ResultDelta.

- [ ] Criar oráculos para resolvido, aberto, novo, regressão e perda de cobertura.
- [ ] Classificar mudanças por arquivo/elemento/requisito e explicitar denominadores/escopo.
- [ ] Distinguir alteração de IDS/verificador de mudança no modelo e causalidade não demonstrada.
- [ ] Verificar T5-25/T5-26/T5-55/T5-57 e consistência dos totais de comparação.

**Entregável/aceite:** regressão exige antes satisfatório comparável; desconhecido nunca vira
aprovado/resolvido; falhas preexistentes e novas observações permanecem distinguíveis.

<a id="m5-t10"></a>

### M5-10 — Produzir pacote e relatórios da mesma revisão

**Responsável:** Felipe com Nonato/M4. **Dependências:** M5-06/M5-08/M5-09.
**Arquivos:** `src/outputs/package.py`, `src/outputs/reports.py`,
`tests/outputs/test_package_reports.py`. **Consome:** snapshots, operações/deltas e recibos.
**Produz:** manifesto/índice, PDF/CSV/JSON e consultas para UI completa.

- [ ] Definir dicionário de colunas, schema JSON e layout do resumo com contagens/limites.
- [ ] Gerar por snapshot, registrar filtros, hashes, ausências e sucesso parcial por formato.
- [ ] Tratar texto longo, UTF-8, fórmulas CSV, tipos, paginação e erro do renderizador.
- [ ] Conferir T5-27 a T5-30 e pacote diagnóstico sem LLM de T5-52.

**Entregável/aceite:** formatos coerentes com resultado canônico; resumo não finge completude,
índice não promete arquivo faltante e retry de derivado não reaplica writer.

<a id="m5-t11"></a>

### M5-11 — Fixar perfil e validar estrutura BCF

**Responsável:** Felipe; Nonato apoia vista/runtime. **Dependências:** M5-01/M5-02 e fontes oficiais.
**Arquivos:** `src/outputs/bcf_exchange.py`, `tests/outputs/test_bcf_schema.py`,
`tests/fixtures/outputs/bcf/`. **Consome:** perfis 3.0/2.1 e requisito de troca local.
**Produz:** matriz de escolha, bundle versionado/hash/licença e adaptador de perfil.

- [ ] Adquirir por procedimento autorizado schemas/releases e biblioteca com versão fixada.
- [ ] Selecionar receptor local com importação/exportação no perfil e registrar versão/licença.
- [ ] Validar negativos/positivos contra schemas corretos, inclusive metadados e identidade.
- [ ] Ensaiar T5-35/T5-36; decidir perfil por critérios da seção 9.1 e reservar T5-37 para ida/volta.

**Entregável/aceite:** escolha técnica fundamentada e capacidade delimitada; XSD aprovado não
substitui receptor. Se só um perfil for entregue, o outro permanece não anunciado.

<a id="m5-t12"></a>

### M5-12 — Exportar seleção BCF com vista e origem corretas

**Responsável:** Felipe com Nonato/M4. **Dependências:** M5-11, M5-13 e snapshots M2.
**Arquivos:** `src/outputs/bcf_exchange.py`, adaptação de `src/bcf/exporter.py`,
`tests/outputs/test_bcf_export.py`. **Consome:** BcfPreview e IssueRecords selecionados.
**Produz:** BCF por IFC e recibo do perfil/limites.

- [ ] Preparar seleção parcial com requisito, elemento, responsável e vista de cada modelo.
- [ ] Confirmar prévia/hash e serializar só tópicos selecionados, mantendo topic_guid persistente.
- [ ] Transformar a câmera/cortes corretamente e preservar ausência/ambiguidade de componente.
- [ ] Verificar T5-31 a T5-34/T5-37, incluindo GUID repetido entre arquivos e vista indisponível.

**Entregável/aceite:** BCF localizável no receptor para perfil anunciado; metadados de projeto,
componente e tópico corretos; atribuir responsável não dispara comunicação externa.

<a id="m5-t13"></a>

### M5-13 — Persistir issue, histórico e resolução verificada

**Responsável:** Felipe. **Dependências:** M5-02/M5-09.
**Arquivos:** `src/outputs/issues.py`, `src/outputs/store.py`,
`tests/outputs/test_issue_lifecycle.py`. **Consome:** diagnóstico/residual, decisões e delta.
**Produz:** IssueRecord e eventos, mapeamento topic_guid estável.

- [ ] Distinguir mesmo problema, novo problema e reaparecimento após resolução por oráculos.
- [ ] Implementar registro/continuidade e vínculo de episódios sem deduplicar só por GUID/título.
- [ ] Separar aceito/rejeitado/pulado de resolução; exigir evidência posterior para resolver.
- [ ] Verificar T5-25/T5-38/T5-40/T5-44, preservando histórico de corrigidos e tentativas falhas.

**Entregável/aceite:** reexportar não duplica issue; problema novo recebe ID; rejeição/erro de
correção não fecha; retirada de requisito não conta como correção de modelo.

<a id="m5-t14"></a>

### M5-14 — Importar BCF devolvido sem fechamento automático

**Responsável:** Felipe com Nonato/M6 na ingestão. **Dependências:** M5-11/M5-13.
**Arquivos:** `src/outputs/bcf_exchange.py`, `tests/outputs/test_bcf_import.py`.
**Consome:** arquivo BCF local e contexto de associação. **Produz:** BcfImportReceipt/eventos.

- [ ] Criar retorno com comentário, vista, responsável, status resolvido e um conflito de ID.
- [ ] Validar/importar de forma segura; preservar original, autores declarados e histórico.
- [ ] Mesclar idempotentemente, marcar resolução informada e encaminhar conferência em M2.
- [ ] Verificar T5-37 a T5-39/T5-50/T5-58 com importação repetida e tópico desconhecido.

**Entregável/aceite:** nenhuma resposta perdida/duplicada silenciosamente; status externo
nunca escreve IFC nem encerra issue sem verificação modelo–requisito.

<a id="m5-t15"></a>

### M5-15 — Comparar IFC revisado e revisar correspondências/requisitos

**Responsável:** Felipe com responsável BIM/IDS. **Dependências:** M5-09/M5-13 e ingestão M2.
**Arquivos:** `src/outputs/revisions.py`, `tests/outputs/test_revision_matching.py`.
**Consome:** nova revisão IFC/IDS/pin e histórico. **Produz:** RevisionMatches e comparação.

- [ ] Cobrir GUID mantido com conteúdo alterado, GUID novo semelhante, duplicado e split/merge.
- [ ] Produzir candidatas justificadas sem associação automática por semelhança; registrar revisão humana.
- [ ] Tratar requisito alterado/retirado com responsável, diff, nova análise e estado próprio.
- [ ] Verificar T5-41 a T5-44/T5-55/T5-59 sem migrar decisões nem evidência entre arquivos.

**Entregável/aceite:** falta de correspondência segura é resultado válido; comparações não
comparáveis explicitam causa; mudança de IDS não apaga falha histórica.

<a id="m5-t16"></a>

### M5-16 — Integrar M4: prévia, ciência, download e desfazer

**Responsável:** Felipe no serviço, Nonato na UI/API. **Dependências:** M5-03/M5-10/M5-12/M5-15.
**Arquivos:** fachada API acordada em M4-02; `src/outputs/coordinator.py`,
`tests/outputs/test_review_handoff.py`. **Consome:** comandos M4 e recibos M5.
**Produz:** percurso revisável com estados, ciência e download por artefato.

- [ ] Apresentar antes/depois, criações, todos os afetados, exclusões e pendências por IFC.
- [ ] Exigir ciência ligada a hash/diagnóstico quando houver pendências ou regressões revisadas.
- [ ] Integrar cancelamento/retomada/undo e perda de resposta sem duplicação de comando.
- [ ] Verificar T5-06/T5-21/T5-22/T5-45/T5-48 e teste de compreensão de T5-60.

**Entregável/aceite:** UI distingue recebido/aplicado/verificado/revalidado/liberado; rascunho
não confirmado não chega ao writer. Não alterar o protótipo M4 durante este planejamento.

<a id="m5-t17"></a>

### M5-17 — Ensaiar isolamento, limites, cancelamento e recuperação

**Responsável:** Felipe com Nonato/M6. **Dependências:** M5-06/M5-10/M5-14.
**Arquivos:** `src/outputs/coordinator.py`, `src/outputs/store.py`,
`tests/outputs/test_recovery_security.py`. **Consome:** política M6 e corpus de falhas.
**Produz:** limites medidos/configurados e evidência operacional.

- [ ] Definir budgets de bytes/expansão/tempo/memória/disco e ownership de worker/temporário.
- [ ] Injetar cancelamentos, quedas, disco cheio, XML/ZIP hostil, ACL negada e rede indisponível.
- [ ] Demonstrar reconciliação após reinício/backup com hashes e sem auto-repetir writer.
- [ ] Verificar T5-46 a T5-54 e registrar o que permanece não suportado no hardware testado.

**Entregável/aceite:** nenhum original alterado, nenhum projeto acessa outro e nenhum
resultado incompleto vira publicado; offline demonstrado por observação, não por configuração.

<a id="m5-t18"></a>

### M5-18 — Publicar matriz de escrita por schema e portador

**Responsável:** Felipe com Nonato/M7 e revisor BIM. **Dependências:** M5-05/M5-07/M5-08/M5-17.
**Arquivos:** manifesto de capacidades M5, `tests/outputs/test_capabilities.py`, corpus.
**Consome:** versões efetivas e recibos de ensaio. **Produz:** capacidade anunciável e limites.

- [ ] Fixar IFC2X3/IFC4/IFC4.3 por release efetivo e operação/portador/tipo/unidade.
- [ ] Repetir positivos, negativos, criação e tipo compartilhado em cada combinação anunciada.
- [ ] Conferir schema preservado e casos reais pertinentes, sem conversão automática.
- [ ] Validar T5-16/T5-19/T5-56; uma célula testada não preenche linha inteira da matriz.

**Entregável/aceite:** suporte explicitamente comprovado, planejado, limitado ou indisponível;
ausência do IFC4.3 real não é escondida nem apresentada como reprovação de todos os schemas.

<a id="m5-t19"></a>

### M5-19 — Demonstrar percurso integrado e interoperabilidade

**Responsável:** Felipe, com Nonato no M4/M6 e liderança M7. **Dependências:** M5-01 a M5-18.
**Arquivos:** `tests/outputs/test_end_to_end.py`, relatório de ensaio com artefatos/hash.
**Consome:** serviços reais e perfil BCF escolhido. **Produz:** evidências dos casos obrigatórios.

- [ ] Executar exportação/reabertura dos dois IFCs, gravação tipada e tipo compartilhado.
- [ ] Provocar falha parcial, conferir comparação e baixar sucesso mediante ciência quando necessária.
- [ ] Abrir BCF na ferramenta compatível, responder/exportar, importar retorno e verificar IFC revisado.
- [ ] Demonstrar T5-02/T5-03/T5-10/T5-21/T5-25/T5-37/T5-60, com defeitos/limites registrados.

**Entregável/aceite:** seis percursos obrigatórios comprovados e integração real diferenciada
de mocks. Um teste somente na própria biblioteca BCF não comprova ida/volta interoperável.

<a id="m5-t20"></a>

### M5-20 — Consolidar entrega operacional, limites e integração documental

**Responsável:** Felipe com Nonato/M7/M6. **Dependências:** M5-19 e revisão dos riscos.
**Arquivos futuros:** relatório final M5, matriz de suporte e pontes coordenadas nos índices.
**Consome:** evidências, problemas residuais e critérios da seção 15. **Produz:** aceite por fatia.

- [ ] Conferir cobertura das decisões e resultados por capacidade, sem contar não verificado como aprovação.
- [ ] Separar testes técnicos, teste formativo Felipe/Nonato e evidência científica independente.
- [ ] Registrar versões, migração/rollback, limitações, operação local e responsabilidades de manutenção.
- [ ] Integrar links/status nos índices somente em turno autorizado, após reler alterações concorrentes.

**Entregável/aceite:** documentação operacional corresponde ao implementado e testado; módulos
não são declarados completos por existirem planos. Esta tarefa futura não condiciona concluir
o documento de planejamento agora.

### 12.1 Ordem e dependências

Caminho principal: M5-01 → M5-02 → M5-03 → M5-04 → M5-05 → M5-06 → M5-07 → M5-08 →
M5-09 → M5-10 → M5-16 → M5-19 → M5-20. BCF: M5-11 pode começar após contratos/corpus;
M5-13 após comparação; M5-12/M5-14 usam ambos. M5-15 integra revisões; M5-17 fecha operação;
M5-18 consolida capacidades. M5-19 depende de todos os contratos necessários reais.

Mocks locais permitem desenvolver projeções/erros enquanto M2/M4 evoluem; sempre rotular
simulação. Nenhum mock encerra ensaio de arquivo salvo, revalidação real ou receptor BCF.
Espera por biblioteca/receptor/caso IFC4.3 é dependência técnica com tarefa definida, sem
transferir escolhas técnicas ao usuário como aprovação documental.

<a id="m5-testes"></a>

## 13. Corpus e testes planejados — não executados

### 13.1 Níveis de evidência

Nível A: contrato/unitário com fixtures mínimas e falhas injetadas. Nível B: integração local
com writer, disco, reabertura e M2 reais. Nível C: receptor BCF independente em versão
registrada e modelos pertinentes. Nível D: uso observado Felipe/Nonato e protocolo M7.
Cada recibo informa nível; nenhum teste A substitui B/C/D. Não rodar inferência para verificar
um fluxo determinístico M5. Fixtures de decisões podem ser sintéticas, explicitamente rotuladas.

Todo caso registra fonte/hash/schema, requisito/esperado independente, versão do serviço,
plano/decisão, resultado por etapa, artefatos/hashes e motivo de falha/limite. Para preservação,
guardar diff de original–cópia e hashes das fontes; para BCF, arquivos de ida e volta e capturas
do receptor. Verificação científica exige protocolo separado, sem transformar taxa de exports
concluídos em ganho de qualidade semântica.

### 13.2 Matriz de 60 casos com resultado observável

| ID | Entrada/ação futura | Oráculo/resultado esperado | Tarefa responsável |
|---|---|---|---|
| T5-01 | Dois IFCs com mesmo GlobalId e STEP ID | Dois ElementRefs, decisões e issues distintos; nenhuma seleção cruzada | M5-01/M5-02 |
| T5-02 | Exportar arquitetura e estrutura com operações aprovadas; fechar/reabrir ambos | Dois arquivos separados, originais com hash igual, campos relidos e revalidação vinculada por arquivo | M5-07/M5-19 |
| T5-03 | Criar Pset/propriedade ausente e alterar outra existente | Nome/portador/valor/tipo/unidade aprovados, sem campo extra, confirmado após reabertura | M5-05/M5-19 |
| T5-04 | IFC ou valor anterior muda após aprovação/prévia | Preflight bloqueia partição, preserva decisão antiga e exige reavaliação | M5-03 |
| T5-05 | IDS, catálogo, candidato ou checker muda | Prévia/checagem obsoleta não autoriza; novo contexto e reavaliação identificados | M5-03 |
| T5-06 | Revogar decisão antes do início e concorrer undo com start | Ordem durável decide; sem escrita da revogada e sem revogação retroativa falsa | M5-03/M5-16 |
| T5-07 | Aprovar segunda alternativa e depois manual editado | Auditoria vincula valor/fonte efetivamente escolhidos, preservando alternativas anteriores | M5-03 |
| T5-08 | Manual fundamentado em campo sem mapping | Pode seguir se checagens literais suportadas; não cria equivalência M1 | M5-03 |
| T5-09 | Dois requisitos/comandos contraditórios no mesmo campo | Conflito visível e bloqueio; nenhuma escolha por ordem de processamento | M5-03 |
| T5-10 | Tipo com ocorrências visíveis/ocultas e override | Prévia enumera todos, confirma alcance, escreve tipo somente autorizado e revalida afetados | M5-04/M5-19 |
| T5-11 | Pset compartilhado entre ocorrências sem tipo | Detecta inversas e alcance; bloqueia alteração silenciosa nas demais | M5-04 |
| T5-12 | Override suportado apenas na ocorrência escolhida | Valor efetivo correto após salvar; outras ocorrências/tipo preservados | M5-04 |
| T5-13 | Override incompatível/sem capacidade ou alcance mudou | Operação bloqueada, pendência/BCF disponível e nova prévia quando aplicável | M5-04 |
| T5-14 | Zero, falso, vazio, nulo, ausência e código “01” | Estados/tipos distintos; sem coerção para ausência ou purga acidental | M5-02/M5-05 |
| T5-15 | mm/m, unidade explícita/projeto e grandeza incompatível | Conversão aprovada rastreável; incompatível bloqueado; unidade global inalterada | M5-05 |
| T5-16 | IFC2X3/IFC4/IFC4.3, capacidade presente/ausente | Schema/release preservado; só combinação testada habilitada; sem conversão | M5-05/M5-18 |
| T5-17 | Handle correto e arquivo salvo truncado/valor diferente | Reabertura/readback falha, cópia retida, correção não encerrada | M5-07 |
| T5-18 | Renumeração STEP e IDs perdidos/duplicados | Mapa seguro quando possível; ambiguidades bloqueiam; GUID existente não refeito | M5-07 |
| T5-19 | Mutação indevida de elemento, relação, placement ou geometria | Diff fora da allowlist bloqueia liberação mesmo com propriedade correta | M5-07/M5-18 |
| T5-20 | Só whitespace/ordem de serialização muda; contraste com lista semanticamente ordenada | Primeiro não é regressão semântica; segundo não é normalizado indevidamente | M5-07 |
| T5-21 | Arquitetura verifica e estrutura falha ao salvar/reabrir | Pacote parcial explícito; sucesso pode ser baixado; nenhum IFC meio aplicado | M5-06/M5-16/M5-19 |
| T5-22 | IFC tecnicamente verificado com falhas/limites IDS | Download exige ciência por hash/diagnóstico, sem conformidade total; nova revisão invalida ciência | M5-16 |
| T5-23 | Revalidação completa com todos os cinco estados M2 | Estados/cobertura preservados; não aplicável/não verificado/erro não viram conforme | M5-02/M5-08 |
| T5-24 | M2 indisponível ou execução inteira falha | Cópia não recebe selo nem liberação regular; diagnóstico e retry explícitos | M5-08 |
| T5-25 | Antes/depois com resolvido, aberto, novo e conforme→falha | Classificação por arquivo/elemento/requisito, regressão destacada e correção falha aberta | M5-09/M5-13/M5-19 |
| T5-26 | Aplicabilidade muda ou elemento desaparece | Mudança de escopo/cardinalidade, sem resolução automática por sumiço | M5-08/M5-09 |
| T5-27 | Mesma revisão em UI, PDF, CSV, JSON e índice | Totais/IDs/estados iguais; resumo rotulado e links/hashes válidos | M5-10 |
| T5-28 | Muitas linhas e nomes longos, filtro/página reduzida | Consulta completa e export completo não limitados à página; filtros explícitos | M5-10 |
| T5-29 | Acentos, aspas, quebras, decimal e células iniciadas por fórmula | CSV legível/seguro, JSON conserva original e transformação identificada | M5-10 |
| T5-30 | Falha PDF/CSV/BCF/ZIP depois de IFC verificado | Derivado falho no índice, sucessos disponíveis; retry não reaplica IFC | M5-10 |
| T5-31 | Selecionar duas de cinco pendências e alterar seleção após prévia | Só seleção congelada exporta; prévia obsoleta rejeitada; exclusões preservadas | M5-12 |
| T5-32 | IfcProject, componente e tópico com IDs distintos | Referências nos campos corretos e modelo/revisão do índice; sem GUID de elemento como projeto | M5-12 |
| T5-33 | Câmera com rotação/escala/origem distante/cortes e transformação visual | Vista localiza componente certo no receptor; IFC não recebe transformação visual | M5-12 |
| T5-34 | Elemento sem geometria, GUID ausente/duplicado e cardinalidade sem elemento | Prévia indica limite; tópico documental ou exclusão consciente, sem referência fictícia | M5-12 |
| T5-35 | Perfil BCF 3.0 positivo e XML estruturalmente inválido | Validação no bundle fixado aceita/rejeita conforme esperado, com versão/hash | M5-11 |
| T5-36 | Perfil BCF 2.1 alternativo e tentativa de apenas trocar VersionId | Estrutura correta ensaiada; mistura rejeitada; perdas documentadas | M5-11 |
| T5-37 | BCF ida/volta em ferramenta compatível: abrir, localizar, comentar, exportar e reimportar | Tópico, requisito, componente, vista, autor/resposta e histórico conferidos em arquivos reais | M5-12/M5-14/M5-19 |
| T5-38 | Retorno BCF marcado resolvido, IFC ainda falha ou não foi fornecido | “Resolução informada, aguardando conferência”; só M2 pertinente permite resolver | M5-13/M5-14 |
| T5-39 | Reimportar mesmo BCF e comentário modificado com mesmo ID | Sem duplicação; nova versão preserva texto/autoria anteriores e origem | M5-14 |
| T5-40 | Reexportar mesma issue, rejeitar/pular sugestão, introduzir problema novo e reaparecimento após resolução | ID estável na mesma issue, rejeição/pulo mantêm pendência aberta, ID novo no problema distinto e episódio/reabertura justificados | M5-13 |
| T5-41 | Nova revisão com mesmo GUID e conteúdo alterado | Nova análise, histórico antigo e nenhuma decisão reaplicada automaticamente | M5-15 |
| T5-42 | GUID alterado com nome/geometria semelhantes | Apenas candidata revisável ou sem correspondência segura; nunca auto-vínculo | M5-15 |
| T5-43 | Duplicação de GUID, split/merge ou vários candidatos | Ambiguidade/revisão explícita; nenhuma associação pelo primeiro candidato | M5-15 |
| T5-44 | Requisito alterado/retirado ou pin novo | Responsável, diff e nova análise; supersedido separado de corrigido no IFC | M5-13/M5-15 |
| T5-45 | Desfazer antes/depois de cópia publicada | Revogação ou revisão compensatória; original/artefato antigo e antes/depois preservados | M5-06/M5-16 |
| T5-46 | Cancelar em cada fronteira W0–W8 e entre arquivos | Recebimento/parada distintos, sucesso confirmado preservado, temporário não publicado | M5-17 |
| T5-47 | Queda antes/depois de salvar/publicar/confirmar banco | Recuperação reconcilia journal/hash, sem escrita duplicada ou sucesso inventado | M5-06/M5-17 |
| T5-48 | Repetir command_id, payload distinto e pedidos simultâneos | Igual retorna recibo; distinto conflita; decisões/start/undo ordenados | M5-06/M5-16 |
| T5-49 | Disco cheio, limite de memória/tempo/expansão | Interrupção segura, motivo e recibos; nenhum original danificado | M5-17 |
| T5-50 | ZIP traversal/bomba, XML externo e imagens/referências maliciosas | Recusa/isolamento sem execução, escrita fora do job ou acesso externo | M5-14/M5-17 |
| T5-51 | Dois projetos/atores tentam consultar/baixar artefato alheio | ACL no serviço, sem vazamento; ID/URL não é credencial | M5-17 |
| T5-52 | Rede externa e LLM indisponíveis; diagnóstico/BCF direto | Percurso determinístico local funciona; sem fallback externo ou inferência obrigatória | M5-10/M5-17 |
| T5-53 | Backup/restauração com derivado ausente e hash divergente | Não liberar objeto incoerente; diagnóstico de restauração e fonte preservada | M5-17 |
| T5-54 | Queda entre renomeação do arquivo e recibo; tentativa de download cedo | Download indisponível até reconciliação/publicação durável, sem depender de existência do arquivo | M5-06/M5-17 |
| T5-55 | Antes/depois usam verificadores distintos ou cobertura diferente | Não comparável ou nova falha observada; nenhuma regressão causal inventada | M5-09/M5-15 |
| T5-56 | Matriz de releases/operações em fixtures e casos reais, incluindo meta IFC4.3 | Evidência por célula; caso ausente limita anúncio, sem assumir suporte por abertura | M5-01/M5-18 |
| T5-57 | Zero aplicáveis obrigatório/opcional e população indeterminada | Resultado de especificação/cardinalidade preservado em relatórios e comparação | M5-02/M5-08/M5-09 |
| T5-58 | BCF desconhecido, status/extensão sem suporte ou topic ID colidido | Original e limitações preservados, revisão de merge; sem perda silenciosa/fechamento | M5-14 |
| T5-59 | Evidência do estrutural enviada a campo arquitetônico, inclusive manual | Rejeitada no MVP; federação não autoriza preenchimento cruzado | M5-03/M5-15 |
| T5-60 | Felipe/Nonato percorrem exportação, parcial, BCF e revisão nova com serviços reais | Compreendem estados, obtêm dois IFCs corretos, histórico/ciência e evidência de uso registrada | M5-16/M5-19 |

### 13.3 Seis demonstrações obrigatórias

1. **Exportar e reabrir dois IFCs:** T5-02, com arquivos separados e original preservado.
2. **Gravação correta:** T5-03/T5-14/T5-15, incluindo criação, tipos e unidades.
3. **Tipo compartilhado:** T5-10, incluindo ocorrência fora da seleção e confirmação integral.
4. **Falha parcial:** T5-21/T5-30, com índice inequívoco e download do sucesso.
5. **Comparação antes/depois:** T5-25/T5-26/T5-55, com resolvidos/abertos/novos/regressões.
6. **BCF ida/volta em ferramenta compatível:** T5-37/T5-38, preservando discussão e verificando
   correção no IFC/requisito antes de fechar.

Cada demonstração guarda arquivos e recibos suficientes para revisão por outra pessoa.
Vídeo/screenshot pode ajudar a verificar vista/uso; não substitui hashes, diagnóstico e
comparação de valores. Todos esses cenários continuam **planejados, não executados**.

<a id="m5-entregas"></a>

## 14. Entregas graduais, dependências externas e esforço

| Marco | Entrega | Dependências | Evidência de saída / responsável |
|---|---|---|---|
| E5-0 | Planejamento documental completo e verificado | Autorização e leitura M2–M4 | Documento, cobertura e relatório de verificação; Felipe |
| E5-1 | Contratos, corpus, prévia e alcance | M5-01 a M5-04, M2/M4 | Plano congelado com negativos/identidade; Felipe/Nonato |
| E5-2 | Dois IFCs escritos/conferidos e revalidados | M5-05 a M5-09, serviço M2 e persistência M6 | Originais preservados, duas cópias reabertas, deltas e parcialidade demonstrados; Felipe |
| E5-3 | Pacote UI/PDF/CSV/JSON/índice com ciência/download | M5-10/M5-16 | Fidelidade, acesso e parcialidade por arquivo/formato; Felipe/Nonato |
| E5-4 | BCF selecionado e ida/volta, histórico e nova revisão | M5-11 a M5-15 | Receptor versionado, retorno e resolução verificada; Felipe/Nonato |
| E5-5 | Suporte declarado, recuperação e aceite integrado | M5-17 a M5-20 | Matriz, seis demonstrações, limites/riscos e roteiro operacional; Felipe com Nonato/M7 |

Primeira fatia vertical: dois modelos mínimos com uma propriedade aprovável em cada um,
decisões duráveis, cópias separadas, releitura, revalidação M2 e manifesto/JSON simples.
Introduzir logo um erro de salvamento no segundo arquivo para provar sucesso parcial; depois
expandir tipo compartilhado, formatos e BCF. Essa ordem não retira os formatos ou testes
obrigatórios do aceite final. Diagnóstico/relatório podem evoluir sem LLM e sem catálogo completo.

| Insumo externo ao código M5 | Dono/encaminhamento | Efeito da ausência |
|---|---|---|
| M2 com resultado completo e revalidação versionada | Felipe/M2 | Mocks permitem contrato; não permitem fechar E5-2 |
| Decisões duráveis, vista e ciência na UI | Nonato/M4, Felipe nas interfaces | Backend isolado pode avançar; E5-3/E5-4 exigem integração real |
| Armazenamento/ACL/recuperação e limites | Nonato/M6 | Não anunciar operação institucional; ensaios locais delimitados |
| Corpus real IFC4.3 de arquitetura/estrutura | Felipe com responsáveis por modelos | Não anunciar capacidade real IFC4.3 ainda sem evidência |
| Receptor BCF local/versionado/licenciado | Felipe/M5, Nonato na vista | Gate de interoperabilidade pendente de ensaio técnico, não aprovação do plano |
| Revisor BIM/IDS e esperado independente | Felipe com especialistas; Nonato/M7 | Não substituir esperado por saída do próprio sistema |
| Domínio/bindings divergentes de M1/M3 | Curadoria e Felipe | Campo afetado continua sem operação; restante suportado pode prosseguir |

Disponibilidade semanal, hardware, cronograma e prazo de implementação não foram confirmados.
Estimativa relativa para planejamento: contratos/corpus e relatórios têm esforço médio;
escrita tipada/compartilhamento, preservação semântica, recuperação e interoperabilidade têm
esforço alto; integração/aceite depende dos serviços reais. Reestimar após E5-1 e primeiro
ensaio de reabertura, separando esforço de execução e espera por insumo. Não prometer prazo
ou throughput sem medição; suporte limitado é declarado, não reduzido silenciosamente.

<a id="m5-aceite"></a>

## 15. Riscos, conclusão funcional futura e revisão crítica

### 15.1 Registro de riscos

| Risco | Consequência | Contenção e dono |
|---|---|---|
| Aprovação associada a outra revisão/alternativa | Escrita indevida | Preflight, hash e decisão exata; Felipe/M5-03 |
| GUID global usado como chave única | Alteração/issue em arquivo errado | Identidade composta e ACL; Felipe/M5-02 |
| Tipo ou Pset compartilhado escondido | Efeito em ocorrências não aprovadas | Inversas, todos os afetados e confirmação; Felipe/Nonato/M5-04 |
| Inferência de tipo/unidade pelo nome ou Python | Valor semanticamente errado | DTO tipado, capacidade e readback; Felipe/M5-05/M5-07 |
| Validação do handle em vez do arquivo | Export corrompido apresentado como verificado | Nova sessão sobre hash salvo; Felipe/M5-07 |
| Diff superficial ou serialização confundida com semântica | Perda de geometria/relação ou falso alarme | Baseline, allowlist e comparador versionado; Felipe/M5-07 |
| Motor indisponível retornando lista vazia | Falsa conformidade | Estados/coverage M2, falha explícita; Felipe/M5-08 |
| Delta sem comparabilidade | Falsa resolução/regressão | Identidade de requisito/motor/escopo; Felipe/Nonato/M5-09 |
| Pacote com arquivo ausente ou fonte errada | Entrega ambígua | Manifesto/índice/hash e recibo; Felipe/M5-10 |
| Relatório ou filtro apaga desconhecidos | Leitor interpreta conformidade total | Mesmo snapshot, contagens e ciência; Felipe/Nonato/M5-10/M5-16 |
| BCF válido no XSD e inútil no receptor | Perda de seleção/vista/discussão | Ida/volta independente e matriz; Felipe/M5-11/M5-19 |
| Retorno BCF fecha sem evidência | Correção fictícia | Resolução informada, análise M2 e vínculo; Felipe/M5-14 |
| GUID novo associado por similaridade | Histórico aplicado ao objeto errado | Candidata e revisão humana; Felipe/M5-15 |
| Queda, timeout ou concorrência duplica escrita | Recibo divergente/perda de rastreabilidade | Diário, idempotência, ordem e recuperação; Felipe/Nonato/M5-06/M5-17 |
| ZIP/XML/CSV/conteúdo hostil | Escrita indevida, execução ou vazamento | Parsers fechados, limites e escaping; Nonato/Felipe/M5-17 |
| Caso/schema sem evidência anunciado como suportado | Generalização indevida | Matriz por célula e corpus real; Felipe/Nonato/M5-18 |
| Documento completo confundido com produto pronto | Planejamento/usuário guiados por estado falso | Status por nível e recibos de ensaio; Felipe/M5-20 |

### 15.2 Pronto para iniciar uma fatia de implementação

- [ ] Destino de implementação e baseline protegidos, sem colisão com protótipo ou outro writer.
- [ ] Corpus/esperados independentes e fontes autorizadas da fatia registrados.
- [ ] Contratos M2/M3/M4/M6 alinhados e capacidade alvo delimitada.
- [ ] Biblioteca/schema/versões e política de ativos escolhidos para o ensaio da fatia.
- [ ] Forma de registrar falhas, limites e evidência de preservação definida.

São pré-condições futuras de desenvolvimento. A autorização atual é de planejamento;
esta lista não exige nova aprovação pessoal para encerrar a documentação já solicitada.

### 15.3 Pronto para anunciar capacidade de escrita

- [ ] Schema/release IFC, operação, portador, tipo/unidade, writer e verificador identificados.
- [ ] Positivo, negativo, ausência, duplicidade e compartilhamento pertinentes testados.
- [ ] Arquivo salvo fechado/reaberto, campo/valor/tipo/unidade/IDs conferidos e original preservado.
- [ ] Elementos, relações, placements e geometria fora da allowlist preservados com evidência.
- [ ] Revalidação M2 e antes/depois com cinco estados, cobertura e regressões demonstrados.
- [ ] Limites publicados; nenhum resultado não verificado anunciado como suporte completo.

### 15.4 Pronto para concluir funcionalmente M5 no MVP

- [ ] Dois IFCs independentes por execução/revisão, sem mistura de evidência ou originais alterados.
- [ ] Aprovações atuais, prévia integral, criações aprovadas e tipo compartilhado sob controle.
- [ ] Transação por IFC, reabertura/readback, preservação e revalidação M2 comprovados.
- [ ] Falha técnica distinta de pendência IDS; pacote parcial e download de sucessos demonstrados.
- [ ] Ciência explícita de pendências/regressões vinculada ao artefato, sem conformidade total falsa.
- [ ] UI completa, PDF resumo, CSV, JSON e índice coerentes, com limites/contagens corretos.
- [ ] BCF selecionado com vista/requisito/elemento/responsável quando definido e ida/volta testada.
- [ ] IDs/histórico de issue preservados; rejeitar/pular/aceitar não fecha; falha de correção continua aberta.
- [ ] BCF resolvido externamente aguarda modelo/requisito conferidos; retorno não perde respostas.
- [ ] Revisão IFC/IDS/catálogo gera análise e comparação novas, sem associação insegura ou autoaprovação.
- [ ] Desfazer/revisar, cancelamento, queda, recuperação, ACL, limites e operação local ensaiados.
- [ ] Matriz IFC2X3/IFC4/IFC4.3 declara apenas capacidades comprovadas, sem conversão silenciosa.
- [ ] Seis demonstrações obrigatórias registradas e limitações remanescentes avaliadas por Felipe/Nonato.
- [ ] Evidência técnica separada de estudo humano/científico e histórico experimental preservado.

Nenhum item funcional acima é marcado como concluído nesta entrega. Se um gate falhar,
reter a capacidade/artefato afetado, registrar causa e executar revisão/desfazer/novo ciclo.
Não retornar silenciosamente ao writer/validador legado permissivo para obter um resultado verde.

<a id="m5-fontes"></a>

## 16. Fontes, versões e limites do que foi verificado

### 16.1 Fontes locais

- [M2: identidade](modulo-02-nucleo-ifc-ids.md#m2-dados),
  [contratos](modulo-02-nucleo-ifc-ids.md#m2-interfaces) e
  [testes](modulo-02-nucleo-ifc-ids.md#m2-testes): leitura imutável e revalidação pelo mesmo núcleo.
- [M3: decisões](modulo-03-contexto-enriquecimento.md#m3-decisoes),
  [contratos](modulo-03-contexto-enriquecimento.md#m3-contratos),
  [interfaces](modulo-03-contexto-enriquecimento.md#m3-interfaces) e
  [verificação](../pesquisa/modulo-03-contexto/verificacao-documental.json): proposta/manual,
  revisão e resolução distintas; estado documental atual preservado.
- [M4: contratos](modulo-04-interface-revisao.md#m4-contratos),
  [persistência](modulo-04-interface-revisao.md#m4-persistencia) e
  [saídas](modulo-04-interface-revisao.md#m4-saidas): decisões duráveis, undo, prévia e dois arquivos.
- [Planejamento atual](README.md), [mapa](mapa-sete-frentes.md),
  [consolidação histórica](CONSOLIDACAO-2026-10-09.md),
  [arquitetura](../arquitetura/base-do-projeto.md),
  [orientações](../../CLAUDE.md) e [contexto](../../PROJECT_CONTEXT.md): precedência e inventário.

Foram lidas as seções pertinentes dos planos M2/M3/M4 e arquivos de código citados no
inventário. Não se alega leitura integral de toda a bibliografia associada, execução do
pipeline ou auditoria de cada módulo legado. Aprovações de produto derivam da instrução
recebida, não da presença de funções ou declarações históricas na documentação.

### 16.2 Fontes primárias consultadas em 12/10/2026

| Fonte | Versão/contexto observado | Uso e limite |
|---|---|---|
| [buildingSMART BCF-XML 3.0](https://raw.githubusercontent.com/buildingSMART/BCF-XML/release_3_0/Documentation/README.md) | `release_3_0`, documentação v3.0 | Estrutura/identidades/vistas; branch pode evoluir, fixar commit/XSD no ensaio |
| [buildingSMART BCF-XML 2.1](https://raw.githubusercontent.com/buildingSMART/BCF-XML/release_2_1/Documentation/README.md) | `release_2_1`, documentação v2.1 | Perfil alternativo e estrutura de pacote; não misturar com 3.0 |
| [IfcOpenShell BCF](https://docs.ifcopenshell.org/bcf.html) | Cabeçalho 0.9.1 na consulta | Candidata de biblioteca e troca por arquivo; suporte declarado pelo fornecedor não certifica ambiente/receptor |
| [IfcOpenShell edit_pset](https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/pset/edit_pset/index.html) | Documentação 0.9.1 | Tipagem/templates e parâmetros de edição/purga exigem configuração/ensaio; nenhum default assumido como política do produto |
| [IfcOpenShell validate](https://docs.ifcopenshell.org/autoapi/ifcopenshell/validate/index.html) | Documentação 0.9.1 | Validação após parsing tem limites; não substituir análise de logs, readback e capacidades M2 |
| [buildingSMART IfcRelDefinesByType](https://standards.buildingsmart.org/IFC/DEV/IFC4_3/HTML/lexical/IfcRelDefinesByType.html) | Página se identifica IFC 4.3.2.0; URL de release redirecionou a DEV | Referência de relação de tipo; não extrapolar regra de override a todos os portadores/schemas nem tratar URL móvel como bundle fixado |

A API `edit_pset` documentada permite adicionar/editar/remover propriedades; sua assinatura
expõe `should_purge`, cujo comportamento exige configuração explícita e negativos com nulo.
Isso reforça a proposta de não permitir exclusão acidental no writer.
[Referência oficial da API](https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/pset/edit_pset/index.html).

A validação após parsing pode não detectar certos erros de sintaxe e identificadores
numéricos duplicados; por isso abertura, logs, preservação e IDS permanecem gates distintos.
[Limites documentados do validador](https://docs.ifcopenshell.org/autoapi/ifcopenshell/validate/index.html).

As páginas são evidência de desenho, não versões instaladas. Fixar release/build, dependências,
schemas/hash, licenças e corpus no desenvolvimento. Consultas públicas de documentação não
transmitiram IFC/IDS/valores do projeto. Não foram pesquisados serviços externos para executar
escrita ou inferência. Páginas GitHub de diretório falharam na leitura; os documentos oficiais
raw acima foram acessados, sem alegar inspeção de um bundle completo de schemas.

<a id="m5-cobertura"></a>

## 17. Checklist de cobertura de cada decisão

Esta matriz verifica presença e coerência **documental**, não aprovação de implementação.
Cada linha aponta para a regra concreta, tarefa com entregável e caso com resultado esperado.

| Decisão | Regra no documento | Tarefas | Casos futuros |
|---|---|---|---|
| D5-01 | [Pacote por arquivo](#m5-pacote) | M5-06/M5-10 | T5-02/T5-21 |
| D5-02 | [Cópia e publicação](#m5-escrita) | M5-06/M5-07 | T5-02/T5-19 |
| D5-03 | [Identidade](#m5-contratos) | M5-02/M5-15 | T5-01/T5-41 |
| D5-04 | [Pré-condições](#m5-escrita) | M5-03 | T5-04/T5-05 |
| D5-05 | [Revisões](#m5-revisoes) | M5-03/M5-15 | T5-05/T5-41/T5-44 |
| D5-06 | [Allowlist](#m5-escrita) | M5-05 | T5-03/T5-09/T5-14 |
| D5-07 | [Reabertura](#m5-verificacao) | M5-06/M5-07 | T5-02/T5-17 |
| D5-08 | [Readback](#m5-verificacao) | M5-05/M5-07 | T5-03/T5-14/T5-15/T5-18 |
| D5-09 | [Revalidação M2](#m5-verificacao) | M5-08 | T5-23/T5-24/T5-57 |
| D5-10 | [Eixos e liberação](#m5-estados) | M5-02/M5-08 | T5-17/T5-22/T5-24 |
| D5-11 | [Parcialidade](#m5-pacote) | M5-06/M5-10/M5-16 | T5-21/T5-30 |
| D5-12 | [Ciência](#m5-estados) | M5-16 | T5-22/T5-25 |
| D5-13 | [Comparação](#m5-verificacao) | M5-09 | T5-25/T5-26/T5-55 |
| D5-14 | [Estados/cobertura](#m5-estados) | M5-02/M5-08/M5-09 | T5-23/T5-24/T5-57 |
| D5-15 | [Formatos](#m5-pacote) | M5-10 | T5-27/T5-28/T5-29 |
| D5-16 | [Seleção BCF](#m5-bcf) | M5-12 | T5-31 |
| D5-17 | [Conteúdo e vista BCF](#m5-bcf) | M5-11/M5-12 | T5-32/T5-33/T5-34/T5-37 |
| D5-18 | [Histórico](#m5-bcf) | M5-13 | T5-25/T5-40 |
| D5-19 | [Ciclo de issue](#m5-bcf) | M5-13 | T5-38/T5-40/T5-60 |
| D5-20 | [Identidade persistente](#m5-bcf) | M5-13/M5-14 | T5-39/T5-40 |
| D5-21 | [Download local](#m5-operacao) | M5-10/M5-17 | T5-51/T5-52 |
| D5-22 | [Nova revisão](#m5-revisoes) | M5-15 | T5-41 |
| D5-23 | [Correspondência segura](#m5-revisoes) | M5-15 | T5-42/T5-43 |
| D5-24 | [Retorno BCF](#m5-bcf) | M5-14 | T5-37/T5-39/T5-58 |
| D5-25 | [Conferência da resolução](#m5-bcf) | M5-13/M5-14 | T5-38 |
| D5-26 | [Revisão do requisito](#m5-revisoes) | M5-15 | T5-44/T5-55 |
| D5-27 | [Capacidades/schema](#m5-escrita) | M5-18 | T5-16/T5-56 |
| D5-28 | [Preservação semântica](#m5-verificacao) | M5-07 | T5-18/T5-19/T5-20 |
| D5-29 | [Alcance integral](#m5-escrita) | M5-04 | T5-10/T5-11 |
| D5-30 | [Override condicionado](#m5-escrita) | M5-04 | T5-12/T5-13 |
| D5-31 | [Novas falhas/regressões](#m5-verificacao) | M5-09 | T5-25/T5-26/T5-55 |
| D5-32 | [Falha permanece aberta](#m5-bcf) | M5-08/M5-13 | T5-17/T5-24/T5-25 |
| D5-33 | [Desfazer preservando histórico](#m5-escrita) | M5-06/M5-16 | T5-06/T5-45 |
| D5-34 | [M1–M7 e responsáveis](#m5-contratos) | M5-02/M5-20 | T5-60 |
| D5-35 | [Seis demonstrações](#m5-testes) | M5-19 | T5-02/T5-03/T5-10/T5-21/T5-25/T5-37 |
| D5-36 | [Estados independentes](#m5-estados) | M5-02/M5-16 | T5-23/T5-38/T5-60 |
| D5-37 | [Determinístico/local](#m5-operacao) | M5-05/M5-17 | T5-52 |
| D5-38 | [Isolamento entre IFCs](#m5-contratos) | M5-03/M5-15 | T5-01/T5-59 |
| D5-39 | [Transações/proveniência](#m5-operacao) | M5-06/M5-17 | T5-46/T5-47/T5-48/T5-54 |
| D5-40 | [Escolha técnica BCF](#m5-bcf) | M5-11/M5-19 | T5-35/T5-36/T5-37 |

### 17.1 Coerência revisada entre contratos

- O mesmo `ElementRef` identifica observação, decisão, plano, readback, comparação e issue;
  referências de revisões diferentes precisam de `RevisionMatch` explícito.
- `ReviewEnvelope` M3/M4 não é recibo de escrita; `FileWriteReceipt` não é resultado IDS;
  `RevalidationReceipt` não é ciência; `DownloadReceipt` não comprova resolução.
- Fonte imutável, candidato exato, pin e diagnóstico viajam juntos até a publicação;
  nenhum endpoint M5 recebe valor novo sem porta de revisão.
- BCF/CSV/PDF/UI derivam do mesmo histórico/diagnóstico, sem fechar issue por rejeição/pulo
  ou mudar o resultado para favorecer taxa de correção.
- Responsabilidades atualizadas e dois IFCs prevalecem sobre registros históricos dos planos;
  nenhum desses planos foi reescrito nesta entrega.

<a id="m5-encerramento"></a>

## 18. Verificação documental, preservação e integração posterior

### 18.1 Escopo de escrita e evidência

Alvos desta entrega: `docs/planejamento/modulo-05-saidas-revisoes.md` e o apoio exclusivo
`docs/planejamento/apoios-modulo-05/verificacao-documental.json`. O relatório registra contagens,
IDs, links/âncoras, Markdown, cobertura, SHA-256 do plano e preservação. Scripts de checagem
documental são temporários, sem importar aplicativo ou rodar testes funcionais.

Antes da escrita, foi capturado manifesto de **400 arquivos rastreados e não rastreados não
ignorados**, branch, HEAD, status e hash do índice Git. `prototypes/` é área concorrente fora
do escopo de certificação M5; mudanças ali são discriminadas, não revertidas nem atribuídas
ao M5. Arquivos ignorados não integram esse universo de comparação. O estado de trabalho
nunca foi presumido limpo. Manifesto completo foi retido na sessão de verificação; o apoio
final guarda o resultado e hashes dos documentos protegidos.

SHA-256 inicial do índice: `fe66e494402e7a741c2aa982958ab74384444b8a96aede668e4defe9f32db16d`.
Nenhuma operação de stage/commit/push, alteração de branch/remote ou implementação foi feita.
O diretório TEMP virtual do sandbox muda entre chamadas; por isso a preservação não depende
de um caminho temporário antigo continuar acessível. Os manifestos foram conservados no
estado da sessão de ferramentas para comparação efetiva, sem gravar em outros planos.

### 18.2 Critérios de fechamento documental

- Texto integral salvo e relido, distinguindo decisão aprovada, proposta e capacidade não testada.
- 40 decisões D5 com cobertura individual, 20 tarefas M5 com dependências/entregáveis/donos e
  60 casos T5 com resultado observável; seis demonstrações obrigatórias explicitadas.
- Contratos M1–M7, identidade, estados, erros, cancelamento, proveniência e limites coerentes.
- Links locais/âncoras resolvidos, tabelas/cercas Markdown consistentes e UTF-8 válido.
- Fontes primárias identificadas por versão/contexto, sem inferir suporte instalado.
- Preservação dos arquivos anteriores e do índice Git conferida no universo declarado.
- Nenhuma conclusão de implementação, teste funcional, inferência, benchmark ou interoperabilidade.

Resultado final e contagens efetivamente verificadas constam do
[relatório documental exclusivo M5](apoios-modulo-05/verificacao-documental.json).
O encerramento documental não depende dos testes futuros nem da escolha visual M4.

**Encerramento verificado:** texto integral relido, cobertura individual das 40 decisões,
20 tarefas e 60 casos futuros conferida; 38 âncoras, 22 tabelas e 97 referências locais
verificadas. As 44 checagens estruturais/de conteúdo passaram, além da conferência de
preservação: 400 arquivos anteriores com SHA-256 igual, nenhuma remoção, branch/HEAD/índice
inalterados. A checagem de cobertura combina referências automáticas e revisão semântica;
busca por palavras não comprova funcionalidade. Somente o plano e seu relatório M5 são novos.
Nenhuma implementação, inferência, benchmark, instalação, teste funcional, stage, commit
ou push foi executado. Não há bloqueio documental remanescente.

### 18.3 Integração proposta, não executada neste turno

| Destino futuro | Ajuste sugerido |
|---|---|
| `docs/planejamento/README.md` | Incluir link M5 e registrar decisões atuais de pacote/BCF/revisões; manter M3 concluído e M4 com escolha visual pendente |
| `docs/README.md` e `README.md` | Acrescentar link para plano M5 e sua verificação, sem declarar produto implementado |
| `docs/planejamento/mapa-sete-frentes.md` | Frente 5: Felipe, dois IFCs, transação, revalidação M2, relatórios/BCF e ciclo de revisão |
| `docs/arquitetura/base-do-projeto.md` | Registrar separação decisão/aplicação/verificação/resolução e publicação por arquivo |
| M2/M3/M4 | Pontes coordenadas ao contrato M5, substituindo pendências históricas de política parcial/formato por decisões de 12/10 |

Texto de ponte sugerido: “Em 12/10/2026, o planejamento M5 definiu pacote por execução/revisão
com IFCs arquitetônico e estrutural separados, cópia temporária, verificação após reabertura,
revalidação M2, relatórios e BCF selecionado. Pacote parcial e IFC tecnicamente verificado com
pendências têm estados e ciência explícitos. Planejamento documental concluído não equivale
a implementação ou interoperabilidade testada.”

Reconciliar os destinos com seu estado mais recente antes de qualquer integração autorizada.
Não tocar no protótipo M4 como parte dessa ponte. A continuidade é implementação por fatias
e ensaios identificados, sem nova pendência pessoal para aprovar a conclusão documental.
