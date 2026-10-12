# Módulo 6 — Infraestrutura e governança

> **PLANEJAMENTO DOCUMENTAL CONCLUÍDO E VERIFICADO — 12/10/2026.**
> **Implementação não concluída; ensaios operacionais descritos neste plano não executados.**
> Responsável: **Nonato**. Felipe participa nas integrações M1/M2/M3/M5.
> Pedido e decisões aprovados por Felipe em 12/10/2026; não há nova aprovação pessoal pendente para concluir o planejamento documental.

**Objetivo:** sustentar o MVP instalado no computador local, com interface responsiva,
dados separados por projeto, decisões duráveis, execução recuperável, backup verificável
e rastreabilidade honesta, preparando uma evolução posterior para o IME.

**Arquitetura proposta:** interface React/TypeScript/Vite/shadcn/ui servida localmente,
API Python e coordenador único de persistência/fila, workers isolados para tarefas
demoradas, banco local e artefatos imutáveis fora do código. Uma inferência ativa por
instalação; pesos Ollama compartilhados. Não são sete serviços distribuídos.

**Base técnica:** reaproveitar Python, Pydantic, Starlette/Uvicorn, sqlite3, httpx,
Loguru e psutil já presentes na base ou biblioteca padrão. A adoção operacional de
SQLite, o adaptador ASGI e os mecanismos de processo/armazenamento abaixo são propostas
fundamentadas, com alternativas e gates de ensaio. Nenhum pacote foi instalado.

**Especificação e precedência:** treze decisões recebidas no encaminhamento de
12/10/2026, reproduzidas em [D6](#m6-decisoes), e contratos dos planos
[M1](modulo-01-dominio-catalogo.md), [M2](modulo-02-nucleo-ifc-ids.md),
[M3](modulo-03-contexto-enriquecimento.md), [M4](modulo-04-interface-revisao.md),
[M5](modulo-05-saidas-revisoes.md) e [mapa das sete frentes](mapa-sete-frentes.md).
**A decisão atual SEM login, contas ou administração de usuários no MVP substitui
exigências anteriores de principal autenticado/ACL nesta fase.** Acesso pela rede do
IME só poderá ser habilitado após autenticação, permissões por projeto e administração.

**Reconciliação:** o encaminhamento informa M3, M4, protótipo e M5 concluídos nas
respectivas tarefas, sem outra tarefa M6 confirmada. Conclusão documental não certifica
implementação. O apoio [M5](apoios-modulo-05/verificacao-documental.json) foi consultado
como evidência documental recebida, sem reexecutar sua entrega. Não havia plano M6 nos
nomes ou cabeçalhos pesquisados. Este arquivo é o único plano M6 criado neste turno.
Planos anteriores, índices, código, dados, resultados, materiais e protótipo permanecem
preservados; propostas de integração estão [neste próprio documento](#m6-integracao).

**Navegação:** [Decisões](#m6-decisoes) · [Base real](#m6-base) ·
[Arquitetura](#m6-arquitetura) · [Dados e contratos](#m6-contratos) ·
[Governança local](#m6-governanca) · [Fila e recuperação](#m6-fila) ·
[Concorrência](#m6-concorrencia) · [Ollama e limites](#m6-runtime) ·
[Armazenamento](#m6-armazenamento) · [Backup](#m6-backup) ·
[Instalação e migração](#m6-instalacao) · [Saúde e diagnóstico](#m6-saude) ·
[Localidade](#m6-localidade) · [Tarefas](#m6-tarefas) · [Testes futuros](#m6-testes) ·
[Riscos e aceite](#m6-aceite) · [Integração](#m6-integracao) ·
[Fontes](#m6-fontes) · [Cobertura](#m6-cobertura) · [Verificação](#m6-verificacao).

<a id="m6-decisoes"></a>

## 1. Decisões aprovadas e limites

Os IDs D6 mantêm correspondência um a um com as treze decisões do pedido, sem
renumerar decisões históricas. A [matriz final](#m6-cobertura) liga especificação,
tarefa e teste futuro; cobertura documental não significa teste funcional aprovado.

| ID | Decisão aprovada | Obrigação do M6 |
|---|---|---|
| D6-01 | MVP instalado localmente, preparado para IME; UI/API só localhost; sem login, contas ou administração; controles multiusuário antes da rede | Fixar topologia loopback e distinguir identificação informada de identidade verificada |
| D6-02 | IFCs originais, IDSs, revisões, análises, decisões, exportações e versões de catálogo separados por projeto; pesos compartilhados | Namespace por projeto e vínculos imutáveis; nenhum cache de contexto cruza projetos |
| D6-03 | Fila de tarefas demoradas, UI responsiva/progresso, uma inferência GPU por vez; cancelamento conserva concluídos | Coordenador durável e controle global da instalação, inclusive retries e aquecimento |
| D6-04 | Análises e decisões salvas sobrevivem a fechamento/reinício; detectar/retomar interrupções; LLM interrompida pode repetir com registro | Recibos transacionais, checkpoints e tentativas identificadas; sem reaplicar resultados concluídos |
| D6-05 | Conferir Ollama/modelo antes de inferir; informar faltas sem baixar; registrar modelo, contexto e parâmetros; validar/consultar sem LLM | Preflight sem geração e sem pull; manifests por chamada e degradação por capacidade |
| D6-06 | Pasta de dados configurável, fora do código; banco local para análises/decisões/fila; mostrar local/uso; espaço e falhas | Armazenamento controlado, reservas estimadas, escrita recuperável e erro explícito |
| D6-07 | Backup local por botão com banco/projetos/catálogos; consistência/restauração testadas; destino separado, idealmente outro disco; pesos opcionais | Snapshot coerente, manifesto e restauração isolada; configuração preservada sem prometer download futuro |
| D6-08 | Logs com retenção limitada, etapa/horário/execução/detalhes; mensagem clara e diagnóstico acessível; pacote com prévia sem IFC integral por padrão | Separar logs, auditoria e reprodução; seleção explícita de dados para diagnóstico |
| D6-09 | Instalação/início documentados, versões fixadas, UI/backend/Ollama; backup antes de migração banco/catálogo; verificar/recuperar falha | Release identificada, migrador isolado e recuperação ensaiada; sem promessa de rollback automático |
| D6-10 | IFC/contexto LLM locais; internet somente necessária, como bSDD com termos/conceitos pertinentes; falha explícita não bloqueia validação independente | Gateway semântico restrito e ativos locais; sem contexto de projeto na saída pública |
| D6-11 | Limites configuráveis de arquivos/duração/contexto definidos por testes no equipamento; aviso/parcial ao atingir limite | Política de recursos versionada, cobertura/omissões visíveis, sem truncamento silencioso ou sucesso incompleto |
| D6-12 | Indicador discreto no topo com ícone/cor/texto; detalhe de backend/Ollama/modelo/armazenamento; bloqueios com orientação | Saúde por capacidade e freshness, sem reduzir tudo a um sinal verde |
| D6-13 | Impedir gravações incompatíveis na mesma revisão; início/fim simples com progresso salvo e interrupções registradas | Instância coordenadora exclusiva, revisão esperada, lease cercado por geração e desligamento controlado |

O MVP recebe dois pares confirmados IFC–IDS, arquitetônico e estrutural, na mesma
sessão visualmente federada. Processamento, evidência e saída continuam separados.
Identidade inclui arquivo e elemento. M3 propõe, M4 registra aprovação humana,
M5 escreve cópias e solicita revalidação M2; **aprovado, escrito e revalidado são eixos
independentes**. M6 não concede aprovação de engenharia ao concluir um job.

Ficam fora: hospedagem IME, servidor compartilhado, login/contas, administração de
usuários, sincronização em nuvem, telemetria externa, downloads automáticos de modelos,
escolha de vencedor LLM sem ensaio M7 e alteração do instrumento científico histórico.

<a id="m6-base"></a>

## 2. Acesso, inventário real e estratégia de reaproveitamento

### 2.1 Evidência desta elaboração

Diretório efetivamente listado e lido:
`C:\Users\Keller_\Desktop\Projetos FC\Pesquisa\ifc-quality-copilot`.
Branch observada: `feat/semantic-foundation`; HEAD:
`a76c2d7a85983ef246761a49db9266c411ea90fd`. O checkout já estava alterado e continha
arquivos não rastreados, inclusive `docs/planejamento/` e `prototypes/`. Nada foi
adicionado ao index. O inventário inicial contou 907 arquivos e 8.063.921.028 bytes,
com exclusões explícitas. O temporário que continha seus hashes não persistiu entre
chamadas do sandbox. Para não atribuir prova inexistente, a comparação anterior/final
usa os 401 hashes disponíveis no apoio M5 preservado; o inventário integral de 907
arquivos recebe novo snapshot após a redação, identificado como tal. O
[apoio de verificação](apoios-modulo-06/verificacao-documental.json) distingue esses
níveis de evidência, o estado Git e a comparação da fase final.

Não foi encontrado `AGENTS.md` na busca do conteúdo inventariado nem nos ancestrais
consultados até o diretório de usuário; `.agents/skills` não existe neste checkout.
Foram consultados `CLAUDE.md`, o índice de planejamento e os planos M1–M5, com foco
em decisões, contratos, persistência, estados, localidade e aceite. Regras históricas
incompatíveis com a decisão atual são registradas na seção de integração.

`rg` não está disponível no shell; listagem, leitura UTF-8 e buscas usaram PowerShell
e biblioteca padrão Python. O inventário é inspeção estática: não inicia API, Ollama,
IFC parser, testes de produto nem inferência. Bibliotecas instaladas não foram
importadas para comprovar capacidade. O lock existente não foi regenerado.

### 2.2 Componentes observados

| Base existente | Evidência e capacidade observada no código | Reaproveitar / lacuna a resolver |
|---|---|---|
| [Configuração](../../src/config.py) e [.env de exemplo](../../.env.example) | Pydantic Settings; URL/modelo/timeout/contexto, cache em `data/cache`, uploads relativos, concorrência default 1 | Manter carregamento tipado; novo perfil operacional fora do código. Defaults de pesquisa não viram limites aprovados |
| [Dependências](../../pyproject.toml) e [lock](../../uv.lock) | Python >=3.11; IfcOpenShell, Streamlit, httpx, Starlette, Uvicorn, Pydantic, Loguru, psutil; restrições `>=` no manifesto | Fixar release efetiva e hash do lock; não confundir intervalo de dependência com pacote reproduzível |
| [Localidade](../../src/foundation/locality.py), [adaptadores](../../src/foundation/adapters.py) | Classificação por host literal permite loopback e redes internas configuradas; `require_local_model` oferece fronteira | Perfil MVP somente loopback e aplicação em todos os caminhos; helper não prova resolução/DNS/proxy/egresso seguros |
| [Contratos](../../src/foundation/contracts.py), [revisão](../../src/foundation/review.py) | Protocols e ReviewDecision; `ElementReviewQueue` sem implementação | Evoluir envelopes versionados; forma de método/booleano não substitui persistência, revisão esperada ou autoria verificada |
| [Worker](../../src/suggestion_engine/worker.py) e [IssueStore](../../src/suggestion_engine/issue_store.py) | Thread daemon, evento de parada, join limitado; dicionários/deque e threading.Lock em memória | Reusar lógica de progresso/adaptar gerador; substituir autoridade em memória por fila/checkpoints duráveis; parar thread não comprova parar GPU |
| [Cliente Ollama](../../src/suggestion_engine/ollama_client.py) | Disponibilidade/lista por `/api/tags`; geração, timeout/retries e warm-up por `/api/generate` | Separar saúde sem inferência de aquecimento; preflight do digest/modelo, tentativa explícita e política local |
| [Cache de sugestões](../../src/suggestion_engine/suggestion_cache.py) | SQLite/WAL, assinatura por modelo/prompt/campo/contexto; tabela contém sugestões | Aproveitar experiência sqlite3; cache não é banco de decisões/fila. Assinatura atual não demonstra isolamento explícito por projeto/revisão/receita |
| [Auditoria](../../src/audit/logger.py) | Lista `entries` em memória, CSV/JSON, `clear`, default de usuário `engineer`; debug inclui valor novo | Usar formato exportável como adaptação, não como trilha durável; retirar presunção de autor e conteúdo sensível de log técnico |
| [bSDD](../../src/bsdd/client.py), [cache bSDD](../../src/bsdd/cache.py) | HTTP/cache JSON e APIs de busca textual/URI | Gateway com parâmetros públicos permitidos e snapshot por análise; cliente genérico não é barreira de privacidade |
| [MCP HTTP](../../src/mcp_server/http_server.py) | Starlette/Uvicorn, CORS `*`, bearer opcional e bind padrão `0.0.0.0` | Não iniciar este servidor no launcher MVP. Reusar stack ASGI, não a exposição nem a autorização opcional como API do produto |
| [UI Streamlit](../../src/ui/app.py) | Estado UI legado; importação Mermaid por CDN identificada | Referência comportamental, não shell React pronto. Ativos do MVP devem ser empacotados localmente |
| [Runtime Windows](../../src/experiment/windows_runtime.py) | Processo Ollama com loopback/pasta de modelos; hashes, extração segura, downloads e `ensure_model_matrix` com pull | Extrair/adaptar capacidades gerais após testes; não chamar fluxo de download/matriz no início ou preflight do MVP |
| [Identidade experimental](../../src/experiment/execution_identity.py), [model lock](../../src/experiment/model_lock.py), [ambiente](../../src/experiment/environment.py) | Hashes de condição, opções, digest/hardware; contratos especializados em casa/prédio e matriz de dez modelos | Reusar princípios e funções gerais comprovadas; não impor corpus/matriz experimental ao produto nem renomear resultados históricos |
| [Pacote de evidência](../../src/experiment/evidence_bundle.py) | Manifestos, hashes, saneamento e validação de arquivo | Candidato a utilitários de diagnóstico; prévia e seleção do MVP precisam contrato próprio, sem exportar corpus por padrão |
| [Instalador](../../windows/install.ps1), [builder](../../scripts/build_windows_release.py), [guia Windows](../../windows/LEIA-ME.txt) | Release de benchmark com pins e fontes/corpus | Novo pacote operacional separado; preservar scripts/resultados atuais. Não basta renomear o benchmark para instalador do produto |

### 2.3 Escolhas técnicas e alternativas

| Tema | Proposta inicial fundamentada | Alternativa e critério para mudar |
|---|---|---|
| API Python | Starlette/Uvicorn como base já declarada; fachada de serviços M1–M5 | FastAPI apenas se schemas/OpenAPI/injeção justificarem dependência e ensaio. Não exigir framework novo para fila/persistência |
| Persistência | SQLite da biblioteca padrão, um coordenador escritor, disco local; JSON/IFC externos imutáveis | PostgreSQL somente no desenho institucional se múltiplos escritores/isolamento/operação justificarem custo. Nunca SQLite compartilhado por pasta de rede |
| Fila | Tabelas de job/tentativa/checkpoint no mesmo banco da aplicação; worker processado fora do request HTTP | Redis/Celery/RQ não exigidos no MVP; avaliar se topologia distribuída futura demonstrar necessidade operacional |
| Worker | Processo separado para IFC/geometria/escrita nativa; coordenador mantém UI e estado; I/O leve pode usar async/thread | Thread isolada somente se cancelamento e consumo forem controláveis; medir serialização/IPC antes de aumentar número de processos |
| Frontend | Build React/Vite servido pela API na mesma origem; shadcn/ui e ativos locais | Servidor Vite separado só no desenvolvimento, também loopback e origem explícita; Electron/Tauri/Docker não exigidos |
| Banco e arquivos | Commit curto no banco, journal de publicação e reconciliação de artefatos por hash | Guardar IFC integral no banco só se ensaio mostrar vantagem; não presumir transação ACID conjunta de SQLite e filesystem |
| Progresso | Consulta paginada de estado/eventos por sequência; SSE opcional após ensaio de reconexão | WebSocket somente se interação bidirecional demonstrar necessidade; desconexão de transporte não cancela execução |
| Ollama | Adaptador de runtime local provisionado, pesos únicos por instalação e identificação por digest | Processo gerenciado pelo launcher facilita serialização/encerramento; servidor externo existente só quando política local e exclusividade puderem ser verificadas |
| Backup | Snapshot coordenado do banco e inventário de arquivos imutáveis com manifesto | Backup quente sem pausa requer protocolo de retenção/snapshot mais complexo; só adotar após ensaio superior ao fluxo inicial |

SQLite WAL permite leitores simultâneos a uma escrita, mas mantém um escritor por vez
e exige processos no mesmo host; por isso a proposta usa disco local, transações curtas
e coordenador único. A política inicial a ensaiar inclui `foreign_keys=ON`,
`synchronous=FULL`, tempo finito para busy, checkpoints e observação do tamanho WAL.
São escolhas de durabilidade a verificar no equipamento, não garantia contra defeito de
disco/energia. [Documentação primária SQLite WAL](https://www.sqlite.org/wal.html).

<a id="m6-arquitetura"></a>

## 3. Arquitetura operacional proposta

```text
Atalho local / launcher (instância exclusiva, perfil, start/stop)
  ├─ navegador → UI React + ativos locais
  └─ API Python em 127.0.0.1 (e ::1 apenas se configurado/testado)
       ├─ serviços M1/M2/M3/M4/M5 + consultas paginadas
       ├─ coordenador M6: comandos, banco, eventos, fila, publicação
       ├─ workers filhos por job: M2, M3 determinístico, M5, derivados
       ├─ gate LLM único da instalação → Ollama loopback → pesos locais
       ├─ gateway bSDD → somente conceitos/termos públicos permitidos
       └─ DATA_ROOT local: banco + projetos + logs + configuração
                 └─ backup manual → BACKUP_ROOT separado
```

1. Frontend recebe referências opacas, estados e recibos; não escolhe caminho físico,
   papel de segurança, identidade verificada, digest supostamente instalado ou resultado.
2. API valida envelope, pertencimento ao projeto, pré-condições de domínio e proteção
   da instância local. Enfileira tarefas longas e devolve `job_id`; não faz parsing IFC,
   inferência, exportação ou backup inteiro dentro do request de interação.
3. Coordenador é autoridade sobre commits, revisão de estado, locks lógicos e promoção
   de arquivos. Workers não escrevem tabelas de decisões nem publicam artefatos diretamente.
4. Workers recebem snapshot de entrada e diretório temporário exclusivo. Resultados
   voltam identificados por tentativa e geração; apenas o coordenador confirma persistência.
5. Módulos têm dependências injetáveis: consulta e validação M2 não constroem um cliente
   LLM obrigatório. Falha do Ollama degrada enriquecimento, não a leitura de resultados.
6. Um arquivo IFC novo nunca substitui fonte histórica. Federação M4 combina cenas,
   sem unir bancos de evidência ou permitir que o worker use o par errado.

### 3.1 Organização física futura

Estes caminhos são **propostas para implementação futura**, não arquivos criados aqui.
Não criar infraestrutura em `src/experiment/` só por conter utilitários semelhantes.

| Caminho proposto | Responsabilidade |
|---|---|
| `src/operations/contracts.py` | Envelopes M6 e identidade de ator local/runtime |
| `src/operations/settings.py` | Perfil MVP, caminhos, política de limites e versões |
| `src/operations/database.py`, `repositories.py` | Transações, constraints, CAS e consultas por projeto |
| `src/operations/jobs.py`, `recovery.py` | Agenda, tentativas, checkpoints e reconciliação |
| `src/operations/locks.py`, `workers.py` | Instância exclusiva, fencing, ownership e processos filhos |
| `src/operations/artifacts.py`, `storage.py` | Bytes imutáveis, temporários, uso e reservas de disco |
| `src/operations/ollama_runtime.py` | Preflight, identidade de modelo e slot de inferência |
| `src/operations/backup.py`, `migrations.py` | Snapshot coerente, restore isolado e migrações verificadas |
| `src/operations/health.py`, `diagnostics.py` | Saúde por capacidade, erros, logs e pacote de diagnóstico |
| `src/operations/local_access.py`, `egress.py` | Loopback/origem/instância e saída semântica restrita |
| `src/api/app.py`, `src/api/routes/operations.py` | Adaptação ASGI das operações M6 para M4 |
| `frontend/src/features/system/` | Indicador, painel de saúde, backup e diagnóstico junto a M4 |
| `scripts/build_desktop_release.py`, `windows/start-copilot.ps1`, `windows/stop-copilot.ps1` | Pacote e ciclo de vida do produto, separados do benchmark |
| `tests/operations/`, `tests/integration/operations/` | Contratos e falhas simuladas/integração sem rede pública |
| `docs/operacao/instalacao-local.md`, `backup-restauracao.md`, `recuperacao.md` | Procedimentos operacionais versionados entregues no futuro |

A nomenclatura final será alinhada com M4/M5 antes da primeira fatia; não criar
DTOs rivais para conceitos já definidos. Direção visual do protótipo está preservada.

<a id="m6-contratos"></a>

## 4. Dados, identidade e contratos M1–M7

### 4.1 Chaves e entidades duráveis

Reutilizar os conceitos de [identidade M2](modulo-02-nucleo-ifc-ids.md#m2-dados),
[contratos M3](modulo-03-contexto-enriquecimento.md#m3-contratos),
[M4](modulo-04-interface-revisao.md#m4-contratos) e
[M5](modulo-05-saidas-revisoes.md#m5-contratos).

```text
projeto       = project_id
modelo        = project_id + model_id
fonte         = project_id + model_id + revision_id + sha256
elemento      = fonte + express_id (GlobalId adicional, nunca chave global isolada)
requisito     = ids_sha256 + caminho/índice estrutural
par           = ModelPairBinding de M4 (PairRef é alias M5, não novo vínculo)
análise       = analysis_id + IFC/IDS/pin/capacidades/verificador/condição exatos
decisão       = decision_id + review_revision + candidato/escopo/hash exatos
job           = job_id + operation_kind + input_identity_hash
tentativa     = job_id + attempt_id + worker_generation
resultado     = job_id + unit_key + result_revision + content_hash
artefato      = project_id + artifact_id + revision_id + sha256 + bytes
```

| Registro M6 proposto | Campos obrigatórios | Invariante |
|---|---|---|
| `LocalActorContext` | installation_id, session_id, actor_kind, declared_name opcional, identity_assurance, UTC de registro | `identity_assurance=unverified_local`; servidor define esse estado, texto do usuário não o promove |
| `CommandEnvelope` | schema_version, command_id, project_id/escopo, expected_revision, payload_hash, actor_context_id | Mesma chave/payload devolve mesmo recibo; chave com payload diferente é conflito |
| `CommitReceipt` | command_id, entity/revision, event_seq, committed_at_utc, result_ref | Só é emitido após commit confirmado; resposta HTTP não é a própria transação |
| `JobRecord` | job_id, tipo/módulo, escopo, inputs/hash, dependências, estado, planned/completed/remaining, motivo | Estado técnico separado da conformidade/aprovação |
| `AttemptRecord` | attempt_id, job, início/fim UTC, worker_id/generation, heartbeat, resultado técnico, retry_of | Tentativa interrompida nunca apagada nem transformada em concluída sem recibo |
| `Checkpoint` | job, unit_key, versão do executor, inputs/hash, output refs/hash, completed_at, result_revision | Unidade só é concluída quando bytes e metadados foram confirmados |
| `RevisionLease` | project/model/revision, operação, owner, geração crescente, prazo/heartbeat, escopos afetados | Expiração sozinha não permite que worker antigo publique; geração precisa coincidir |
| `ArtifactRecord` | origem/revisão, hash/tamanho, papel, caminho relativo gerado, estado, publication_intent_id | Caminho não é autoridade e arquivo existente não significa publicado |
| `PublicationIntent` | job/attempt, destino imutável, hash/tamanho esperados, gates M5/M1, estado, recibos | Recuperação não inventa verificação, aprovação ou resultado IDS |
| `RuntimeManifest` | build/lock, OS/hardware, Ollama versão, modelo/digest, contexto e opções, capability/policy hashes | Mudança relevante cria nova condição, não reutiliza silenciosamente cache |
| `OperationEvent` | event_id, sequência, projeto/execução/etapa, UTC, monotonic_duration, origem/ator, antes/depois, refs | Evento de domínio persistido com efeito; log técnico é complemento |
| `HealthSnapshot` | sampled_at, freshness, backend/ollama/model/storage, available_capabilities, blocker/action | Falha LLM não impede saúde de consulta/validação; estado desconhecido não vira OK |
| `BackupManifest` | backup_id/formato, instante/corte event_seq, banco/hash/schema, arquivos/hash/tamanho, releases/pins, exclusões, runtime | Identifica conjunto coerente; restauração valida antes de ativar |
| `MigrationReceipt` | migration_id, versões antes/depois, backup_id, candidato, checks, etapa/status/erro | Migração só fica concluída depois de validação e ativação confirmadas |

Armazenar no banco projetos, pares/revisões, pins, análises/resultados indexáveis,
decisões, fila/tentativas, checkpoints, leases, comandos/recibos, eventos e inventário
de artefatos. IFCs/IDSs, snapshots extensos, contextos/respostas e exportações ficam em
arquivos imutáveis referenciados. Índices/constraints sempre incluem projeto quando
o registro pertence a ele; joins conferem a origem. Resultados de cardinalidade sem
elemento preservam escopo da especificação. Grandes resultados são paginados, sem
perder denominadores nem omitir linhas fora da página.

### 4.2 Fronteiras e responsáveis

| Fronteira | Consome de M6 | Entrega a M6 | Critério verificável e responsável |
|---|---|---|---|
| M1 — domínio/catálogo | Armazenamento de versões, comandos/revisões, backup e ator local declarado | Pacote/candidato/hash, publicação, pin explícito, diff e invalidações | Pacote publicado imutável; atualizar pin não muda análise antiga; governança local descrita em D6-01. Felipe + Nonato |
| M2 — leitura/IDS | Fonte imutável, ResultSink durável, ExecutionControl, worker/limites | DiagnosticSnapshot, cobertura, cinco estados, VerifierIdentity e checkpoints | Continua sem LLM/bSDD; não muta original; retomada só reutiliza unidades de mesma identidade. Felipe + Nonato |
| M3 — contexto/enriquecimento | Slot LLM, RuntimeManifest, checkpoints/cache por projeto e preflight | CallPlan/contexto/hash, alternativas/abstenção, métricas e tentativas | Uma chamada de cada vez; sem resposta de outro modelo/arquivo/projeto; falha não altera diagnóstico M2. Felipe + Nonato |
| M4 — interface/revisão | Saúde, eventos, consultas, CommitReceipt, salvar/retomar/cancelar | CommandEnvelope, decisão explícita, preferências, seleção para backup/diagnóstico | “Salvo” apenas por recibo; nome informado não aparece como autor autenticado; UI permanece responsiva. Nonato |
| M5 — saídas/revisões | Journal/leases, storage, fila, ator local e recibos | ChangePlan, FileWriteReceipt, SavedVerification, RevalidationReceipt, PackageManifest | Preservar W0–W8, cópia por arquivo, estado parcial e gates; restaurar não libera cópia não verificada. Felipe + Nonato |
| M6 — infraestrutura | Políticas/runtime e contratos de domínio versionados | Serviços de durabilidade, publicação e erro; suporte comum aos seis módulos | Não duplica motor IDS nem writer; disponibilizar artefato requer recibos do módulo dono. Nonato |
| M7 — avaliação | Manifestos, tentativas, erros, recursos e exportação local das medidas | Corpus, condição, critérios e ensaios para escolher modelos/limites | Nonato lidera com Felipe; configuração atual e modelo default não são vencedor; preservar v7.8 e resultados anteriores |

### 4.3 Operações de infraestrutura propostas

| Operação | Entrada → saída | Semântica |
|---|---|---|
| `submit_job` | CommandEnvelope + JobRecord inicial → job/ref + CommitReceipt | Congela inputs e dependências; mesma chave não cria dois jobs |
| `get_job` / `query_events` | project/job + cursor → snapshot/página + última sequência | Replay de evento não reaplica efeito; lacuna retorna snapshot completo |
| `request_cancel` | job/escopo + command_id → CancelReceipt | Confirma pedido salvo; terminal vem depois da fronteira segura |
| `resume_job` | job + identity_hash + command_id → tentativa/plano de retomada | Lista concluídos, pendentes e chamadas a refazer antes de iniciar |
| `commit_result` | attempt/generation + unit_key + refs → Checkpoint/CommitReceipt | Rejeita geração antiga; transação com evento/resultado |
| `reserve_revision` / `release_revision` | escopo + revisão esperada + owner → RevisionLease/recibo | Protege início/publicação/undo/pin segundo matriz de conflito |
| `prepare_artifact` / `publish_artifact` | intenção + bytes/hash + gates → ArtifactRecord/recibo | Worker não decide liberação; publicação somente após gates do dono |
| `get_health` / `get_storage_usage` | perfil/escopo → HealthSnapshot/uso e instante | Read-only; não aquece modelo nem baixa pesos |
| `create_backup` / `verify_backup` | destino configurado + command_id → job/manifesto/relatório | Não altera projeto; “verificado” é integridade do backup, não ensaio de restauração |
| `restore_backup` | manifesto + diretório novo + command_id → relatório/candidato | Operação exclusiva; ativação explícita após validação, sem sobrescrever original |
| `preview_diagnostics` / `export_diagnostics` | seleção/correlation_id → inventário/hash → arquivo local | Mesma seleção exibida; sem upload automático |

São fachadas internas; rotas M4 existentes no plano permanecem referência, inclusive
consulta de `command_id` após timeout. Transporte candidato: `202` para job aceito,
`409` para revisão/chave em conflito, `413` para tamanho, `422` para entrada inválida,
`503` para dependência bloqueante; erro de disco usa código `storage_unavailable` com
causa explícita. Não expor traceback como mensagem principal. Nenhuma dessas operações
está implementada por este documento.

<a id="m6-governanca"></a>

## 5. Governança local e limites de auditoria

### 5.1 Sem contas no MVP

O operador abre o aplicativo sob sua sessão do sistema operacional. A aplicação não
oferece login, cadastro, troca de usuário, gestão de papéis nem recuperação de senha.
Todos os projetos da instalação pertencem ao mesmo domínio de confiança local.
Separação por projeto evita mistura e gravação errada; **não constitui controle de
acesso entre pessoas que usam a mesma conta do sistema operacional**.

O serviço cria IDs de instalação/sessão/operação. Se o operador informa “Nonato” ou
“Felipe”, registrar `declared_name` e `identity_assurance=unverified_local`.
Ausência de nome é “Operador local não identificado”. Identidade de processo/conta OS,
quando observável, é metadado técnico e não comprova qual pessoa clicou. A UI e os
relatórios devem usar “identificação informada”, sem selo de autor autenticado.
O backend rejeita tentativa do navegador de mudar a assurance para `authenticated`.

A proteção de comandos por segredo efêmero da instância/origem descrita adiante é
contra requisições indevidas; não cria conta nem verifica identidade humana.
`Actor` dos contratos anteriores será adaptado para contexto local, preservando campo
reservado para identidade verificada futura, sem inventar um usuário autenticado hoje.

### 5.2 Curadoria e decisão técnica

M1 continua distinguindo solicitar, editar rascunho, revisar candidato e publicar.
No MVP, “curador” é responsabilidade de trabalho declarada da pessoa que opera a
instalação, sem atribuição de papel autenticado. A pessoa especialista/curadora nominal
continua a definir conforme M1; Nonato responde pela infraestrutura, não aprova
automaticamente toda definição de domínio.

Publicação requer ação explícita sobre candidato/hash exatos, declaração de responsável,
justificativa, validações do pacote e recibo. Não se pode garantir tecnicamente “somente
a pessoa curadora publica” sem autenticação: essa limitação substitui a exigência
anterior nesta fase e deve aparecer no histórico/exportação. Validações de conteúdo e
barreiras contra publicação automática pelo LLM continuam obrigatórias. No IME, o
serviço deverá efetivamente aplicar a permissão de curadoria a principal verificado.

### 5.3 Três camadas de registro

| Camada | Conteúdo/finalidade | Retenção e confiança |
|---|---|---|
| Log operacional | Etapa, UTC, run/job/attempt/correlation_id, nível, código e detalhe técnico saneado | Rotação por idade e tamanho com limites finitos; não serve de única prova de decisão |
| Trilha de engenharia | Decisão exata, declarado/origem, antes/depois, revisão/hash, aprovações/revogações, aplicação/revalidação | Durável por vida do projeto e incluída em backup; não sofre rotação de logs |
| Artefato de reprodução | Contexto completo local quando necessário, prompt/schema/options, resposta, digest/condição | Escopo por projeto; política explícita de retenção/exportação, sem cópia automática no diagnóstico |

“Append-only” descreve comportamento da aplicação: correções criam novos eventos,
nunca apagam o histórico por edição normal. Um administrador do computador pode editar
o banco e recalcular hashes, e o relógio local pode estar errado. Hash e eventual cadeia
de hashes detectam inconsistências comparadas a um registro íntegro, mas **não são
assinatura digital, carimbo de tempo confiável nem não repúdio**. Não afirmar prova
forense ou autoria autenticada. UTC ordena exibição; sequência transacional ordena
eventos, relógio monotônico mede duração dentro de um processo. Mudança de relógio
gera aviso sem reordenar commits confirmados.

Exemplo: alguém informa “Felipe”, aprova um campo e encerra o app. O recibo comprova
que a instalação registrou aquela decisão e seus bytes, não que Felipe esteve presente.
Ao importar BCF, autor/comentário externo conservam origem declarada; não são convertidos
em decisões locais verificadas nem fecham issue automaticamente.

<a id="m6-fila"></a>

## 6. Fila, progresso, cancelamento e recuperação

### 6.1 Estados técnicos separados do domínio

| Estado de job | Significado | Transições permitidas |
|---|---|---|
| `queued` | Pedido persistido, aguardando dependência/recurso | running, blocked, cancel_requested |
| `running` | Tentativa com owner/generation ativos | completed, partial, failed, cancel_requested, interrupted |
| `blocked` | Falta modelo/espaço/entrada ou pré-condição | queued após correção explícita e rechecagem; cancelled |
| `cancel_requested` | Pedido durável, worker ainda pode estar finalizando fronteira segura | cancelled, partial, completed se já havia concluído, interrupted |
| `interrupted` | Processo terminou sem recibo terminal confiável | Plano de retomada; nova tentativa ou recuperação de recibo existente |
| `completed` | Todo escopo planejado daquele job terminou com recibos | Imutável; novo pedido/identidade para novo trabalho |
| `partial` | Há resultados confirmados e escopos não concluídos explícitos | Consulta/exportação parcial; retomada vinculada dos pendentes |
| `failed` | Falha técnica e causa registrada | Nova tentativa permitida por política; histórico permanece |
| `cancelled` | Não restam execuções ativas do escopo cancelado | Consulta dos concluídos; retomada exige comando explícito |

Unidade de checkpoint: lote de resultados M2 identificado, campo/grupo M3 com envelope
válido, ou etapa/artefato M5 conforme W0–W8. O dono do módulo define se a unidade pode
ser repetida; M6 persiste o compromisso. Concluir job IDS não significa todos os
requisitos conformes. Concluir geração M3 não aprova proposta. `partial` nunca vira
“100% validado”; UI mostra planejados, concluídos, pendentes, falhos e não verificados,
além da etapa atual. Quando o total ainda não é conhecido, usar progresso indeterminado
e contagens reais, não estimativa apresentada como exata.

### 6.2 Agendamento

Fila durável para importação pesada, análise, geometria, enriquecimento, escrita,
revalidação, exportação, backup e migração. CPU/I/O têm limites próprios configurados;
leituras/UI não esperam GPU livre. Uma capacidade global `llm_slot=1` por instalação
governa todos os projetos, dois pares, diferentes modelos, retries e aquecimento.
Prioridade inicial FIFO entre jobs elegíveis, com unidades de tamanho limitado para
evitar fome de outro projeto; mudança de prioridade registra evento. Dependência
bloqueada identifica o recurso e não mantém um worker ocupado em polling infinito.

Não abrir vários Uvicorn workers coordenadores com fila independente. Singleton do
launcher + lock OS do DATA_ROOT impede duas instâncias escritoras, e o gate de GPU
precisa cobrir instalações que apontem para o mesmo Ollama. Proposta: endpoint Ollama
gerenciado/dedicado ao Copilot e lock por runtime local; outros clientes não são
controlados por esse lock. Se houver inferência externa concorrente observada ou
exclusividade não comprovável, bloquear novo despacho e orientar liberar o runtime,
sem matar processos alheios. Não prometer exclusividade de toda a GPU contra software
externo. Perfil de servidor também deve limitar paralelismo na versão ensaiada.

### 6.3 Protocolo de persistência e idempotência

1. Receber comando; validar tipo, escopo, revisão e hash do payload canônico.
2. Em transação curta, buscar chave `(project_id, operation_kind, command_id)`.
   Se já existe e payload coincide, devolver estado/recibo anterior. Se difere, `409`.
3. Reservar/revisar estado necessário e registrar efeito + evento + recibo na mesma
   transação. Só enviar “Salvo” após commit. Gravação de arquivo segue journal próprio.
4. Worker envia unidade completa com generation. Coordenador valida refs/hashes e
   confirma resultado/checkpoint/evento; duplicata idêntica não duplica efeito.
5. Falta resposta HTTP após commit: UI consulta command_id. Sem registro confirmado,
   repete a mesma chave/payload; nunca inventa novo comando para resolver ambiguidade.

Unicidade do checkpoint considera identidade das entradas e versão do executor.
Não anunciar garantia universal “exactly once”: efeitos persistidos são idempotentes;
execução física pode ocorrer mais de uma vez antes de se obter resultado confirmado.
Prompts iguais com mesma seed não garantem resposta idêntica. Operação que depende de
catálogo/receita/modelo novo cria outra identidade e mantém o histórico anterior.

### 6.4 Cancelar e encerrar

| Momento | Comportamento exigido |
|---|---|
| Job ainda na fila | Registrar cancelamento e retirar elegibilidade; nenhum worker novo |
| M2/M3 entre unidades | Não iniciar próxima; preservar checkpoints confirmados e marcar restante |
| LLM ativa | Marcar pedido; tentar interromper cliente por mecanismo ensaiado. Fechar HTTP não comprova que GPU parou; manter slot ocupado/incerto até término confirmado ou recuperação controlada do runtime próprio |
| Chamada nativa travada | Após prazo de graça configurado, encerrar somente processo filho pertencente a job/geração; temporário vira incompleto/quarentena |
| M5 em escrita/verificação | Respeitar W0–W8; não publicar cópia sem gates; manter original e sucessos de outro IFC |
| Artefato já publicado | Informar que concluiu antes do pedido; cancelar não revoga bytes/histórico |
| Backup/derivado parcial | Destino parcial nunca recebe marcador de backup/artefato completo; fonte e último backup válido permanecem |

Fechar a aba não é encerrar o backend; o launcher informa execução em andamento e
permite reabrir a UI. “Encerrar Copilot” para de aceitar jobs, grava pedido de parada,
espera checkpoints em janela finita, reconcilia filhos e fecha conexões. Preferências
salvas sobrevivem; texto não confirmado deve continuar identificado como não salvo.
Salvar progresso não pode ser prometido apenas por evento `beforeunload` do navegador.
Desligamento forçado registra interrupção na próxima inicialização se não foi possível
gravar o evento antes. Ollama previamente iniciado por outro aplicativo não é encerrado
pelo Copilot; runtime próprio só é encerrado após política e ownership verificados.

### 6.5 Reinício e plano de retomada

Ao iniciar: obter lock exclusivo, verificar perfil/banco/versão, abrir recuperação antes
de admitir novos jobs e reconciliar jobs `running/cancel_requested` sem owner vivo.
Identificar worker por ID/PID + instante de criação + geração, não só PID reutilizável.
Registrar `interrupted`, verificar hashes e checkpoints e apresentar plano com etapas
concluídas, etapas recuperáveis e o que será refeito. **Abrir projeto não relança LLM
nem writer automaticamente.** “Retomar” cria tentativa vinculada, reaproveitando somente
unidades confirmadas e com identidade compatível; decisão salva não é repetida.

| Falha concreta | Recuperação planejada |
|---|---|
| Crash depois de 80/100 unidades M2 com checkpoints | Ler as 80, validar identidade; agendar 20. Índice em memória pode ser reconstruído, sem duplicar resultados confirmados |
| LLM respondeu mas não houve persistência | Tentativa permanece sem resultado confirmado; nova chamada permitida com `retry_of`, motivo e contagem. Resposta perdida não é inventada |
| Timeout da UI após salvar decisão | Consultar command_id; devolver recibo existente, mantendo apenas um evento de decisão |
| Crash após gravar temporário M5, antes de reabrir | Marcar saved/incompleto, conferir bytes e retomar verificação; não chamar writer de novo sobre a cópia modificada |
| Crash após revalidação, antes do recibo de publicação | Conferir intenção, hashes e recibos M5/M2. Finalizar somente se todos comprovados; caso contrário quarentena/retomada da etapa faltante |
| Arquivo sumiu ou hash mudou fora do app | Bloquear escopo, conservar metadados/evidência e orientar restauração; não procurar arquivo pelo nome |
| IFC/IDS/pin/receita mudou | Nova análise/execução vinculada; tarefa antiga continua histórica, sem “atualizar” chave do cache |
| GPU ainda processa tentativa órfã | Bloquear slot e mostrar estado incerto; reconciliar/encerrar apenas runtime próprio de forma controlada antes de qualquer nova inferência |

<a id="m6-concorrencia"></a>

## 7. Concorrência e publicação recuperável

### 7.1 Revisão esperada, locks e fencing

Duas abas locais já geram concorrência mesmo sem usuários diferentes. Toda mutação
leva revisão esperada; o banco faz compare-and-swap e devolve conflito com a revisão
atual quando não coincide. Nunca “última gravação vence” para decisão, pin ou prévia.

| Operações concorrentes | Política inicial |
|---|---|
| Consultar análise enquanto worker produz resultados | Permitido por snapshots/paginação e eventos confirmados |
| Duas edições da mesma revisão de decisões | Uma confirma; a outra recebe conflito, preserva formulário e apresenta diff |
| Exportação M5 versus undo/alteração de decisões | Reserva da revisão antes de W0; snapshot congelado. Segundo comando aguarda/recebe conflito; undo posterior não revoga exportação em curso retroativamente |
| Escritas/exportações incompatíveis na mesma revisão IFC | Uma lease por `(project_id, model_id, ifc_revision_id)` e escopo de decisão; segunda não começa |
| Trocar pin/IDS durante job dependente | Histórico fica fixo; comando cria nova revisão após serialização da transição; plano antigo não é atualizado em memória |
| Arquitetura e estrutura do mesmo projeto | Leituras independentes; escritas podem ser serializadas inicialmente por prudência de recursos, mas recibos independentes |
| Dois projetos inferindo | Fila compartilhada pelo runtime, sem compartilhar contexto/resultados |
| Backup/migração/restore versus publicação/GC | Barreira de manutenção; não capturar banco e arquivos em cortes diferentes |

Lease contém owner, heartbeat, prazo e **geração crescente**. Prazo vencido sinaliza
suspeita, não autorização para dupla execução. Antes de reassumir, reconciliar processo
antigo; cada resultado/publicação verifica geração atual. Worker antigo só grava seu
staging isolado e não pode renomear destino final. Transação de banco não fica aberta
durante inferência ou escrita IFC. Busy/retry tem prazo e erro visível. Deadlock é
evitado por ordem de aquisição: manutenção da instalação → projeto → modelo/revisão
→ recurso; jobs que aguardam slot LLM não seguram lock de escrita de revisão.

### 7.2 Banco e filesystem não são uma única transação

1. Persistir `PublicationIntent` com entrada/decisão/gates esperados e nome final novo.
2. Produzir arquivo em staging da tentativa no mesmo volume da futura publicação.
3. Fechar handles, descarregar buffers segundo API suportada, reabrir/verificar hash,
   tamanho e gates de domínio. Na implementação, testar durabilidade no Windows real.
4. Persistir recibos de verificação e estado preparado. Coordenador confere geração,
   revisão congelada e pré-condições imediatamente antes da promoção.
5. Promover para caminho imutável exclusivo; se já existe, conferir hash/identidade,
   não sobrescrever. Renomeação local é um passo, não commit conjunto com o banco.
6. Commit de ArtifactRecord + referência + evento de publicação. Disponibilizar link
   só após esse commit e conforme regra de liberação M5/M1.
7. Reinício compara intenção, arquivo e recibos. Arquivo sem intenção/gates vai à
   quarentena; registro sem bytes válidos fica indisponível. Nunca inferir sucesso
   de um `.ifc` presente ou de exit code zero.

Exemplo M5: `FileWriteReceipt=saved` e `SavedVerification=ok` com revalidação pendente
não equivalem a IFC liberado. O coordenador agenda M2 sobre os mesmos bytes e preserva
o gate. Se somente PDF falha, não reaplica as correções IFC já publicadas; repete
somente o derivado. Cada partição arquitetônica/estrutural pode ter estado diferente.

<a id="m6-runtime"></a>

## 8. Ollama, capacidade e política de recursos

### 8.1 Preflight sem inferência ou download

Antes de cada despacho: verificar loopback/perfil local, resposta do servidor com
prazo finito, versão runtime, modelo solicitado presente e digest/configuração
compatíveis com a execução. `/api/tags` fornece inventário com nome, tamanho, digest
e detalhes do modelo; servidor acessível não significa que o modelo solicitado esteja
instalado. [Ollama — List models](https://docs.ollama.com/api/tags).

Resultados possíveis: disponível; servidor indisponível; modelo ausente; modelo/digest
alterado; configuração incompatível; ocupado; identidade não verificável. Cada caso
produz mensagem e ação específica. Não chamar `/api/pull`, instalar modelo, escolher
outro modelo nem fazer warm-up como checagem de saúde. O operador pode providenciar
modelo fora desse fluxo pelo procedimento documentado; M7 define seleção por evidência.
Rechecagem após correção não deve gerar inferência sem pedido do usuário.

Ollama atual documenta modo local com recursos cloud desativados, bind em loopback e
pasta configurável de pesos. A implementação deve verificar essas capacidades na
versão fixada, controlar ambiente do processo próprio e bloquear modelos/recursos
remotos; URL localhost sozinha não garante inferência local. A FAQ também registra
atualizações automáticas em instalações desktop: detectar drift antes da próxima
execução e usar runtime fixado/gerenciado quando necessário para reprodução.
[Ollama FAQ](https://docs.ollama.com/faq).

Pesos pertencem à instalação, com `model_store` configurado e único; projetos guardam
apenas referências/digests/configurações. Não criar cópia por projeto nem apagar pesos
ao remover temporários de um job. Não baixar a matriz experimental de dez modelos
para poder consultar ou validar um IFC. Ausência de GPU compatível bloqueia ou exige
perfil CPU previamente ensaiado e explicitamente escolhido; não promover fallback
silencioso nem alegar desempenho medido.

### 8.2 Manifesto por execução e chamada

Persistir build/hashes de código/locks, Python e bibliotecas relevantes, OS/hardware
observados, versão Ollama, tag e digest completo, quantização/arquitetura quando
expostas, snapshot de configuração e ausência explícita de metadado não disponível.
Por chamada: projeto/análise/ElementRef/FieldRefs, CallPlan, contexto exato local ou
referência/hash recuperável, template/prompt/schema/receita/roteamento versionados,
opções efetivamente enviadas (`num_ctx`, política, saída, temperature, seed, top_p,
repeat_penalty, think, keep_alive, timeout/retries quando aplicáveis), estimativa e
tokens efetivos disponíveis, stop reason, tempos, cache/reuse, tentativa e erro.

Não preencher parâmetros desconhecidos com valores imaginados. Quando o servidor
não permite observar a opção efetiva, registrar enviada e grau de observabilidade;
ensaio mede a capacidade. Modelo alterado sob mesma tag invalida reuso; mudança no meio
da tentativa compromete identidade, isola o resultado e exige reconciliação. Guardar
contexto do projeto somente local e nunca no log técnico geral.

### 8.3 Limites configuráveis e ensaio de calibração

| Recurso | Limite/medida a configurar | Ao atingir |
|---|---|---|
| Entrada IFC/IDS e importações | Bytes recebidos, quantidade de arquivos, entidades/nós e formatos aceitos | Rejeitar antes de tarefa cara; importação incompleta não vira revisão válida |
| BCF/pacote/catálogo/backup | Membros, bytes expandidos, profundidade e tempo | Interromper extração confinada e preservar estado prévio |
| Processamento nativo | Memória/CPU, duração por etapa, tempo de graça e processos ativos | Encerrar apenas worker próprio quando necessário; resultado parcial/erro explícito |
| Contexto LLM | Janela, overhead/template/schema, reserva de saída, margem e política de tokenização | Dividir conforme M3 ou abster-se; nunca cortar evidência obrigatória silenciosamente |
| Resposta LLM | Bytes/tokens, duração, número de retries e reparos | Detectar truncamento/JSON inválido e registrar tentativa, sem proposta completa fictícia |
| Fila/API | Jobs pendentes, payload, consultas/página, polling, eventos por página | Recusar excesso com motivo; preservar jobs aceitos e consulta de estado |
| Armazenamento | Reserva livre mínima, staging por job, WAL, caches/logs e backup | Pausar novos produtores antes do esgotamento; manter dados duráveis |
| Viewer/derivados | Memória/bytes/tempo de tesselação e cache | Degradar visualização com aviso; consulta/validação independente continuam |

Nonato, com M7 e os módulos donos, ensaiará corpus pequeno, típico, grande e adversarial
no equipamento identificado; observará picos de RAM/VRAM/disco, latência da UI e tempos
de recuperação. Registrar perfil, amostras, versão, margem escolhida e oráculo antes
de fixar números. Repetir nos dois pares IFC–IDS e com falha/concorrência. Cada limite
operacional deve ter valor finito, unidade, versão, justificativa e teste de ultrapassagem
na release; zero/ausente não significa ilimitado. Sem calibração, capacidade afetada
não é anunciada pronta. Somente uma inferência simultânea já está aprovada numericamente.

Não truncar evidência no armazenamento para caber no prompt: fonte permanece íntegra;
seleção/omissão contextual traz itens, motivo e efeito na cobertura. Se um campo não
cabe com evidência mínima, devolver limite/abstenção e pendência. Valores históricos
4096/8192/768 no código são configuração de pesquisa, não orçamento universal do MVP.

<a id="m6-armazenamento"></a>

## 9. Pasta de dados, espaço e preservação

Layout **ilustrativo**; DATA_ROOT é absoluto, configurável, local, fora do checkout e
validado quanto a permissões, filesystem e links. Caminho de exemplo não é criação.

```text
DATA_ROOT/
  installation.json                 # perfil, versões e referências sem segredo de sessão
  database/copilot.sqlite            # análises, decisões, fila, eventos, pins, índices
  projects/<project_id>/
    sources/ifc/<model_id>/<revision_id>/
    sources/ids/<ids_revision_id>/
    catalog/releases/<release_id>/   # versões usadas pelo projeto, íntegras e fixadas
    analyses/<analysis_id>/
    enrichment/<run_id>/             # contexto/respostas/reprodução local
    decisions/                      # derivados exportáveis da autoridade no banco
    exports/<export_run_id>/<model_id>/
    viewer/<revision_id>/            # derivados regeneráveis identificados
    staging/<job_id>/<attempt_id>/
    quarantine/
  catalog-authoring/                 # rascunhos e releases mestres M1 da instalação
  logs/                             # técnicos, sujeitos a rotação
  diagnostics/                      # pacotes explicitamente gerados
  runtime/                          # ownership; segredos efêmeros excluídos de backup
MODEL_STORE/                        # um armazenamento Ollama por instalação
BACKUP_ROOT/                        # separado de DATA_ROOT; preferir outro disco
```

Separação de versões do catálogo significa pin e conteúdo recuperáveis por projeto;
releases mestres não mudam automaticamente projetos existentes. Proposta simples:
snapshot da versão usada na área do projeto, mais catálogo mestre de curadoria incluído
no backup completo. Deduplicação futura por hash só após provar que GC de um projeto
não remove versão referenciada por outro; pesos compartilhados são exigência imediata.

Na escolha/mudança de DATA_ROOT: parar mutações, criar backup, copiar para novo destino,
validar bytes/manifestos, abrir banco compatível e trocar referência do launcher só
depois. Não mover/destruir a pasta antiga automaticamente. Rejeitar destino dentro do
código, dispositivo não gravável, pasta de rede e sincronização conhecida incompatível;
detecção de sincronização pode ser incompleta, portanto documentar suporte apenas a
armazenamento local testado. Não depender de caminho textual por prefixo: resolver
contenção real, junctions/symlinks/reparse points e nomes reservados do Windows.

Exibir caminho absoluto do DATA_ROOT e MODEL_STORE, volume, uso por projeto/categoria,
livre/total, staging/quarentena/logs e horário da medição; cálculos de uso rodam em
background. UI não pode parecer travada durante varredura. Estimar espaço necessário
por operação: entrada + cópia temporária + saída + índices/WAL + margem calibrada;
backup também confere destino e staging. Reserva lógica não impede outro programa de
consumir disco: tratar ENOSPC/erro de I/O em toda etapa mesmo após preflight aprovado.

Falha antes do commit deixa última revisão válida intacta; falha no meio da publicação
mantém journal e arquivo incompleto isolado. Se não houver espaço nem para gravar erro,
mostrar falha no estado da instância e, no reinício, reconstruir interrupção do último
estado durável; não prometer evento que não foi salvo. Nunca limpar originais, decisões,
análises ou saídas válidas automaticamente para “abrir espaço”.

Limpeza automática só alcança caches regeneráveis/logs/temporários expirados sem refs
ativas, respeitando retenção da release e locks de backup/GC. Quarentena mantém metadados
da tentativa e política explícita; remoção de projeto/histórico é operação futura com
impacto/backup, não um efeito de cancelamento. Artefatos necessários para decisões ou
reprodução não são tratados como cache descartável.

<a id="m6-backup"></a>

## 10. Backup consistente e restauração

### 10.1 Conteúdo e interface

Botão “Criar backup local” mostra destino, projetos incluídos, tamanho estimado,
espaço, escopo e exclusões. Proposta inicial: **backup completo da instalação**, banco,
todos os projetos/fontes/revisões/decisões/análises/exportações, versões de catálogo
usadas e catálogo mestre/rascunhos, configuração e manifestos/capacidades necessários.
Seleção de projeto exigiria exportação referencial do banco, por isso não é prometida
como primeira fatia. Caches puramente regeneráveis/logs antigos podem ser excluídos
com lista explícita. Não excluir contexto/evidência necessário a uma decisão salva.

Pesos podem ficar fora, preservando tag/digest/runtime/configuração/localização de
referência e licença disponível. Aviso: restauração sem pesos permite consulta e
validação, mas enriquecimento depende de os pesos exatos estarem disponíveis por
provisionamento posterior; **não há garantia de download futuro**. Opção de incluir
pesos usa snapshot estável do MODEL_STORE, sem duplicação dentro de cada projeto;
ausência de garantia de estabilidade bloqueia essa opção, não o backup de dados.

Destino não pode ser DATA_ROOT, subdiretório dele ou caminho equivalente por link.
Também não pode causar inclusão recursiva de backups no conjunto copiado. Preferir
outro disco; se estiver no mesmo disco, mostrar “não protege contra perda deste disco”.
Não substituir backup válido anterior pelo mesmo nome. Backup é local, sem upload.

### 10.2 Corte consistente entre banco e arquivos

O mecanismo de backup do SQLite produz snapshot consistente do banco; copiar apenas
o arquivo `.sqlite` enquanto ativo não é o protocolo adotado. A API de backup não
garante, por si, a consistência dos IFCs e catálogos externos: essa parte exige
coordenação da aplicação. [SQLite Online Backup API](https://www.sqlite.org/backup.html).

Protocolo proposto, a demonstrar na implementação:

1. Persistir job de backup; validar destino/recursos e obter barreira de manutenção.
   Suspender novos despachos/mutações, publicação e GC. UI continua lendo e informa pausa.
2. Esperar fronteira segura de jobs ativos com prazo finito. Se não for possível,
   oferecer cancelar o backup/aguardar; não copiar silenciosamente estado instável.
3. Reconciliar publicações pendentes. Registrar corte `event_seq`/schema/build;
   tentativas não terminadas entram no snapshot como recuperáveis/interrompidas,
   nunca como leases vivas que devam ressuscitar no restore.
4. Com mutações de domínio bloqueadas, usar `sqlite3.Connection.backup` em destino
   temporário, verificar integridade/FKs e extrair o inventário referencial desse
   snapshot. Os estados transitórios do próprio job de backup ficam fora do corte
   de domínio ou são reconciliados sem afetar projetos.
5. Fixar retenção dos arquivos listados contra GC/alteração. Copiar bytes imutáveis,
   versões/configurações congeladas e, se escolhidos, pesos estáveis. Só liberar
   mutações antes do fim da cópia se o pin de retenção cobrir rigorosamente o conjunto;
   primeira fatia pode manter a barreira até concluir, com progresso/cancelamento.
6. Gerar manifesto com caminhos relativos seguros, hash/tamanho de cada membro,
   banco/schema, refs, pins, versão de formato e exclusões. Reabrir e verificar todos
   os membros e integridade referencial. Hash do manifesto fica em recibo separado,
   sem hash autorreferente.
7. Finalizar nome/marker de completo somente após verificações. Registrar recibo e
   liberar barreiras/pins. Falha libera recursos e conserva `.partial` identificado;
   não exibe “Backup concluído”. Último backup íntegro permanece.

Não manter grande transação de escrita SQLite durante a cópia de gigabytes. A barreira
é operacional, observável e cancelável; transações do coordenador continuam curtas.
Backup completo não implica restauração comprovada: recibo diferencia “integridade
verificada” e “restauração ensaiada”, com data/versão/evidência de cada uma.

### 10.3 Restauração isolada

1. Selecionar backup local e mostrar manifesto, versão, conteúdo e exclusões; rejeitar
   arquivo incompleto, versão desconhecida, caminho inseguro ou hash divergente.
2. Entrar em manutenção exclusiva, encerrar filhos próprios e preservar instalação
   atual. Restaurar em **novo diretório**, nunca sobre a pasta de trabalho ativa.
3. Verificar extração confinada/limites, hashes de todos os membros, integridade do
   banco, FKs, contagens/referências e disponibilidade de catálogo/fontes/saídas.
4. Conferir compatibilidade de release/schema. Banco futuro não é aberto em escrita
   por release antiga; migrar apenas com caminho ensaiado e backup prévio preservado.
5. Criar nova identidade de instância operacional/generation; conservar IDs de domínio
   e proveniência do backup. Invalidar leases/sessões/tokens antigos e marcar tarefas
   ativas no corte como interrompidas; não relançar inferência ou writer automaticamente.
6. Reabrir dois projetos/pares, consultas e decisões salvas; validar gates de artefatos.
   Mostrar pesos ausentes separadamente. Só então ativar o DATA_ROOT restaurado por
   ação explícita no aplicativo e devolver relatório de restauração.

O objetivo de perda recuperável é o instante do último backup válido (RPO observado),
não zero perda após esse instante. Tempo de recuperação (RTO) será medido no equipamento
e volume ensaiados; nenhum prazo está prometido. Backup manual não é redundância
automática; disco externo desconectado/ausente é erro claro, sem fallback para a pasta
de trabalho. Alteração posterior ao backup permanece fora daquela restauração.

<a id="m6-instalacao"></a>

## 11. Instalação, início, atualização e recuperação de migração

### 11.1 Release operacional futura

Nonato entregará pacote/documentação com versões exatas de Python/dependências do
backend, runtime SQLite efetivo, Node/gerenciador e lock/build do frontend, ativos
viewer/WASM/fontes/ícones, Ollama suportado e bibliotecas de exportação adotadas por M5.
Incluir hashes, origem e inventário de licenças/termos; recurso sem distribuição
permitida não entra no pacote silenciosamente. Hardware mínimo e suportado só após
ensaios. Registrar CPU/GPU/RAM/disco/driver e capacidades por schema, sem confundir
compatibilidade de biblioteca com validação de toda combinação IFC/IDS.

Reaproveitar práticas de pin/hash/extração segura dos scripts Windows em módulo de
produto separado; preservar pacote de pesquisa, sua matriz e `PROMPT_VERSION v7.8`.
`pyproject.toml` com `>=` não basta para release; usar lock resolvido e proveniência
do build. Não congelar número “mais recente” sem ensaio. Distribuição offline com
dependências empacotadas é candidata; instalação que precisa aquisição inicial deve
listar e solicitar essa ação fora do processamento de projetos, sem baixar pesos
automaticamente na inicialização.

### 11.2 Fluxo de inicialização

1. Atalho inicia launcher oculto quando cabível, sem exigir terminal aberto; resolve
   configuração absoluta e versão, confere permissões/espaço e lock de instância.
2. Segunda abertura localiza instância saudável e abre a mesma UI; se lock aparenta
   órfão, reconcilia owner antes de removê-lo. Porta ocupada por outro processo gera
   diagnóstico ou outra porta loopback conhecida, nunca bind em rede para contornar.
3. Verifica banco/manifestos e executa recuperação; migração necessária abre percurso
   próprio com backup, sem alterar banco em import de módulo.
4. Inicia API e serve build frontend local. Endpoints de saúde distinguem liveness de
   prontidão para leitura/escrita/LLM; abrir navegador somente quando shell está pronto.
5. Verifica Ollama e inventário sem inferência. App abre para consulta/validação quando
   LLM falta, com indicação discreta e orientação. Não instalar modelo ao abrir.
6. Exibe projetos e tarefas interrompidas. Encerrar segue protocolo da seção de fila;
   componentes não ficam abandonados como processos globais sem ownership.

Guia de instalação deve permitir instalação limpa e atualização de versão anterior,
com diretórios com espaços/acentos, conta OS sem privilégios administrativos quando
suportada, erro de permissão/porta, acesso offline e desinstalação preservando dados
por padrão. “Pronto” exige executar esse roteiro no equipamento, não só gerar ZIP.

### 11.3 Migração de banco e catálogo

Versão de schema de persistência, formato de pacote de catálogo e conteúdo de release
de catálogo são identidades diferentes. Atualização de pin M1 cria nova análise; não
é migração de banco nem rollback de código.

| Etapa | Ação / evidência |
|---|---|
| Planejar | Matriz origem→destino suportada, espaço, checks de compatibilidade, release do migrador e impacto |
| Preparar | Manutenção exclusiva; snapshot consistente completo verificado, `backup_id` e manifesto antes de qualquer mutação |
| Migrar candidato | Banco/catálogos em diretório isolado; migrações numeradas, checksums, journal de início/fim; não editar release histórico de catálogo |
| Validar | Integridade/FKs, contagens, semântica/pins/refs, decisões/recibos, jobs, artefatos e consultas; comparar invariantes antes/depois |
| Ativar | Troca controlada da referência da instalação para conjunto banco+arquivos compatível, com intenção/recibo recuperáveis; manter anterior |
| Recuperar falha | Não iniciar escritores; mostrar etapa/causa. Usar conjunto anterior íntegro quando comprovado ou restaurar backup em nova pasta e executar versão compatível |

Se migrador interrompe depois de copiar metade de um catálogo, candidato é inválido;
versão publicada antiga permanece. Se o banco migrou mas ativação caiu, startup lê
intenção e versões antes de escolher conjunto completo; nunca combina banco novo e
catálogo antigo incompatíveis. Se validação semântica falhar, não marcar concluído
porque SQL terminou sem erro. Rerun usa ID/checksum e prova de etapa concluída, não
executa DDL/transformações novamente às cegas.

Uma migração de formato deve preservar o release original e produzir representação
nova com vínculo/mapeamento explícitos; hashes antigos continuam resolvíveis. Uma
correção de conteúdo requer nova versão M1 e adoção explícita, não migração técnica
silenciosa. Antes de ativar, demonstrar leitura das análises históricas.

Não prometer rollback automático não testado. Voltar a release anterior pode exigir
restauração e não comportar gravações feitas depois da migração; o procedimento deve
listar perda potencial, cópia preservada e passos observados no ensaio. Operação fica
em manutenção ou consulta segura enquanto compatibilidade não foi demonstrada.

<a id="m6-saude"></a>

## 12. Indicador de saúde, erros e diagnóstico

Topo discreto: ícone + cor + texto curto acessível, não apenas cor. Exemplos de
conteúdo funcional: “Pronto”, “LLM indisponível”, “Modelo ausente”, “Pouco espaço”,
“Recuperação necessária”, “Verificação desatualizada”. Clique abre detalhes:

| Componente | Mostrar | Efeito sobre ações |
|---|---|---|
| Backend | Responde/pronto, versão, horário e modo manutenção/recuperação | Offline impede salvar; preservar formulário e avisar ausência de confirmação |
| Ollama | Disponível/ocupado/erro, versão, endpoint loopback verificado | Bloqueia apenas novas chamadas afetadas; consulta/validação continuam |
| Modelo | Tag/digest, instalado, compatibilidade, identidade insuficiente | Não selecionar substituto silencioso; indicar como provisionar/rever configuração |
| Armazenamento | DATA_ROOT, volume/uso/livre, gravabilidade, reserva, último backup | Espaço insuficiente bloqueia novos produtores; leitura possível quando íntegra |

Problema bloqueante recebe destaque junto da ação afetada, motivo e orientação:
“Não foi possível salvar. O disco está sem espaço. Suas decisões já confirmadas
permanecem disponíveis.” Quando não for possível atestar preservação, especificar
o último recibo conhecido e a necessidade de recuperação, sem garantia falsa.

Saúde é snapshot com timestamp e validade configurada; timeout/desconexão produz
desconhecido/desatualizado, não mantém verde indefinidamente. UI que perdeu backend
consegue mostrar estado de conexão a partir de timeout local. Preflight de execução
reconfere dependência mesmo que o ícone tenha estado OK segundos antes. Sondagens
são leves, com backoff e sem inferência/listagem custosa do disco em cada request.

### 12.1 Catálogo de falhas e mensagem útil

| Código proposto | Informação ao operador | Detalhe técnico / recuperação |
|---|---|---|
| `backend_unavailable` | Serviço local indisponível; salvar ainda não confirmado | correlation_id local, reconectar e consultar command_id |
| `ollama_unavailable` / `model_missing` | Ollama não responde / modelo escolhido não instalado | Endpoint saneado, timeout/inventário, instrução de provisionamento manual |
| `runtime_identity_changed` | Configuração/modelo mudou; execução requer nova checagem | Manifestos antes/depois e cache invalidado |
| `storage_unavailable` / `space_limit` | Não foi possível gravar / espaço insuficiente | Volume, etapa, estimativa, errno saneado; preservar última revisão |
| `revision_conflict` / `lease_conflict` | Outra ação alterou/reservou esta revisão | Revisão/owner operacional atual, refazer prévia sem perder formulário |
| `job_interrupted` / `resource_limit` | Tarefa interrompida / limite atingido | Unidades concluídas/pendentes, motivo e plano de retomada |
| `artifact_integrity_failed` | Arquivo ausente ou diferente do registrado | Hash esperado/observado, quarentena e orientação de restauração |
| `backup_incomplete` / `restore_invalid` | Backup incompleto / restauração recusada | Membro/etapa inválidos; manter destino anterior |
| `migration_failed` | Atualização não concluída; instalação em recuperação | backup_id, etapa/checks; abrir guia sem pedir para apagar banco |
| `egress_denied` / `bsdd_unavailable` | Consulta semântica bloqueada/indisponível | Política/rota sem payload sensível; validação local continua |

Logs técnicos possuem instante UTC, nível, etapa, projeto opaco, run/job/attempt,
correlation_id, código, duração e stack trace saneado no detalhe. Remover tokens,
credenciais, caminhos pessoais desnecessários e texto de projeto. Configuração tem
retenção por idade **e** tamanho total, rotação e limites finitos a fixar na release;
ensaiar overflow e disco cheio. Não usar `DEBUG` irrestrito como perfil de produção.
Retenção de logs não apaga auditoria, decisões, contexto necessário ou resultados.

### 12.2 Pacote de diagnóstico com prévia

Prévia enumera nomes/tamanhos/categorias, período/execuções, versões/hardware saneado,
erros selecionados e campos removidos. Default inclui logs saneados, saúde/configuração
sem segredos, contagens, manifestos e códigos de falha; **não inclui IFCs completos,
IDSs integrais, banco inteiro, prompts/contextos/respostas completos, nomes de projetos
ou pastas pessoais por padrão**. Hashes/IDs também podem ser correlacionáveis; permitir
revisar essa seleção antes da exportação.

Seleção adicional de arquivo/evidência precisa aparecer explicitamente na prévia com
impacto; o pacote gerado corresponde ao hash da seleção confirmada. Sanitização é
checagem adicional, não promessa de anonimização perfeita. Armazenar pacote local e
recibo; nenhum envio automático a suporte/email. Usar utilitários do evidence_bundle
apenas após avaliar contratos e ensaiar que corpus científico não entra por engano.

<a id="m6-localidade"></a>

## 13. Localidade e proteções coerentes com ausência de login

### 13.1 Entrada local

Perfil MVP permite apenas bind explícito `127.0.0.1`, e `::1` se habilitado/testado.
Recusar `0.0.0.0`, `::`, IP LAN/IME, proxy reverso/túnel e override que exponha a API.
Conferir listeners efetivos, não só arquivo de configuração. Nome localhost deve
resolver para loopback no caminho usado; não confiar em nome DNS arbitrário ou host
literal classificado como interno. Launcher não inicia MCP HTTP remoto, Streamlit
ou outro serviço legado como exposição adicional do produto.

Servir build UI e API na mesma origem. Allowlist exata de Host/Origin/porta; rejeitar
origens inesperadas, inclusive `null`, comandos cross-site e rebinding. Sem CORS `*`,
sem mutação por GET, tipos/métodos/payloads restritos. Exigir proteção de comando por
nonce/token de instância de curta vida, gerado pelo backend e entregue somente à UI
local autorizada; não em query string, log ou pacote de diagnóstico. Verificar Host
antes de servir UI/token. Cabeçalhos forwarded não ampliam confiança. Cookies, se
usados, têm política restritiva compatível com loopback testado. SSE/WS seguem as
mesmas fronteiras, sem endpoint alternativo permissivo.

Isso reduz risco de site malicioso comandar localhost, mas não impede processo local
com mesmo usuário/administrador de ler dados, obter token ou alterar aplicação.
UI/IDS/IFC/catálogos/LLM são conteúdo não confiável: escapar HTML, restringir ativos,
não executar comandos/URLs de fontes e tratar imports conforme parsing seguro M2/M5.
Conta do OS e permissões da pasta são a barreira local disponível, sem login de produto.

### 13.2 Saída pública restrita

IFCs, contexto, prompts, respostas, evidência e logs permanecem locais. Nem endpoint
localhost nem presença de modelo na lista são prova suficiente se o runtime puder
encaminhar a cloud: preflight e ensaio de tráfego precisam excluir esse caminho.
Não usar fallback externo para inferência/embeddings, viewer, ativos, crash reporting
ou telemetria. UI deve abrir e consultar dados sem CDN/fontes externas.

Exceção operacional inicial: API pública bSDD pelo backend, em rotas/destinos HTTPS
permitidos e com DTO de consulta semântica. Aceitar somente identificadores/URIs e
termos públicos selecionados de catálogo permitido, necessários à consulta. Nunca
enviar IFC, arquivo, GUID, nome de projeto/elemento, valor de propriedade, texto livre
do IFC/IDS ou contexto completo. Não copiar texto do modelo para busca pública nem
usar URL sugerida pelo LLM. Validar redirects/destino final, proxy, DNS/endpoint e
parâmetros; erro bloqueia a consulta afetada. Política de exceção não libera outros
destinos por conveniência.

Guardar snapshot semântico usado, hash/URI/data/versão disponível e estado de fonte.
Se bSDD falha, avisar; snapshot local compatível pode ser usado com origem/data
explícitas. Sem snapshot adequado, marcar semântica indisponível/abstenção quando
necessária, mantendo validação IFC–IDS independente. Runtime não baixa schemas IDS,
pacotes ou pesos para corrigir uma falha. Aquisição inicial de releases/dependências
é procedimento separado com fontes/hashes documentados, sem projeto no payload.

### 13.3 Pré-condições para fase IME

Hospedagem futura exige projeto próprio: autenticação real, gestão de contas/sessões,
permissões por projeto e ação aplicadas no servidor, administração/curadoria, transporte
protegido, publicação/segredos, recursos/quotas, concorrência, backup/restauração e
observabilidade institucionais ensaiados. Identidades locais antigas continuam marcadas
como não verificadas; migração de usuário não autentica retroativamente a autoria.
Não habilitar rede “provisoriamente” porque o banco ou API funcionou em um computador.
Nonato coordena com responsáveis institucionais; topologia, operação e orçamento do
IME são decisões futuras, não bloqueiam o fechamento deste plano documental.

<a id="m6-tarefas"></a>

## 14. Tarefas futuras, dependências e entregáveis

**Todas as tarefas abaixo permanecem por implementar.** Checkboxes não representam
execução nesta entrega. Nonato é responsável pelo M6; colaboradores são indicados em
cada tarefa. Arquivos citados como novos pertencem ao mapa proposto da seção 3.1.
Cada tarefa deve começar pelos casos/oráculos associados, observar falha antes da
implementação pertinente e terminar com evidência da capacidade na versão ensaiada.
Nenhuma etapa deste plano autoriza stage/commit/push neste trabalho documental.

<a id="m6-t01"></a>

### M6-01 — Congelar contratos e perfil MVP

**Dependências:** decisões D6 e contratos M1–M5. **Responsável:** Nonato; Felipe valida
interfaces de domínio, sem nova aprovação pessoal necessária para este documento.
**Arquivos futuros:** `src/operations/contracts.py`, `settings.py`; adaptar
`src/foundation/contracts.py`, `review.py` e `locality.py` em fatia própria.
**Entrada → saída:** decisões/DTOs existentes → schemas/envelopes e perfil versionados.

- [ ] Formalizar LocalActorContext, IDs, estados independentes, erros e versão de wire format.
- [ ] Definir perfil sem contas, loopback, origem, caminhos e opções proibidas; registrar precedência sobre principal/ACL históricos.
- [ ] Publicar exemplos válidos/inválidos de comando, ator declarado e colisão entre arquivos.
- [ ] Verificar T6-10, T6-11, T6-41 e T6-48; entregar schema e matriz de compatibilidade sem DTO concorrente.

**Aceite:** os sete contratos têm dono; backend não aceita identidade autenticada
forjada, e `completed` não altera conformidade, aprovação ou revalidação.

<a id="m6-t02"></a>

### M6-02 — Persistir projetos e revisões em armazenamento local

**Dependências:** M6-01. **Responsável:** Nonato; Felipe alinha SourceArtifactRef/pins.
**Arquivos futuros:** `database.py`, `repositories.py`, `storage.py`; adaptação isolada
de `src/config.py`. **Entrada → saída:** perfil/fontes → banco, projeto, revisão/hash e refs.

- [ ] Definir schema com FKs, chaves por projeto, versões, índices e política WAL/busy/durabilidade ensaiável.
- [ ] Importar fontes para área exclusiva e confirmar revisão somente após hash/bytes íntegros.
- [ ] Separar originais, pares, catálogo fixado e derivados; provar rejeição de referência de projeto errado.
- [ ] Verificar T6-10, T6-11, T6-13, T6-45 e T6-49; entregar inventário de dados e diagrama relacional.

**Aceite:** fechar/reabrir o banco não perde revisões confirmadas; leitura nunca exige
LLM; banco ativo só usa filesystem local suportado e caminho fora do código.

<a id="m6-t03"></a>

### M6-03 — Salvar decisões e recibos com M4

**Dependências:** M6-01, M6-02. **Responsável:** Nonato; Felipe participa do handoff M5.
**Arquivos futuros:** `repositories.py`, `src/api/routes/operations.py`, fachada de
revisão M4; adaptar AuditLogger por fronteira, sem apagar exports históricos.
**Entrada → saída:** ReviewCommand/CommandEnvelope → decisão/evento/CommitReceipt.

- [ ] Salvar decisão, evento e recibo na mesma transação com revisão esperada e chave idempotente.
- [ ] Expor consulta de command_id e manter “Salvando/Não salvo” até resultado durável conhecido.
- [ ] Persistir preferências e rascunhos explicitamente salvos, separando edição transitória.
- [ ] Verificar T6-02, T6-16, T6-27, T6-41 e T6-50; entregar percurso de duas abas e resposta HTTP perdida.

**Aceite:** uma decisão, um efeito durável e recibo recuperável por chave; nunca
atribuir autoria autenticada ao nome livre nem marcar salvo após erro de disco.

<a id="m6-t04"></a>

### M6-04 — Fila durável, checkpoints e retomada

**Dependências:** M6-02, M6-03. **Responsável:** Nonato; Felipe especifica unidades M2/M3/M5.
**Arquivos futuros:** `jobs.py`, `recovery.py`, repositórios e adaptador de `worker.py`.
**Entrada → saída:** pedido identificado → JobRecord, AttemptRecord, Checkpoint/eventos.

- [ ] Definir estados, dependências, contadores e unidade atômica de cada executor; remover memória como autoridade.
- [ ] Implementar despacho/reserva curtos, replay por cursor e duplicação idempotente de resultado.
- [ ] Reconciliar restart e apresentar plano de retomada sem relançar inferência/escrita ao abrir sessão.
- [ ] Verificar T6-03, T6-04, T6-05 e T6-42; entregar log de checkpoints antes/depois e pendentes enumerados.

**Aceite:** escopos concluídos confirmados não são repetidos; LLM sem confirmação pode
ser repetida em tentativa nova explícita, sem promessa de execução física única.

<a id="m6-t05"></a>

### M6-05 — Workers isolados e cancelamento seguro

**Dependências:** M6-04. **Responsável:** Nonato; Felipe adapta executores M2/M5.
**Arquivos futuros:** `workers.py`, `jobs.py`, `recovery.py` e adapters de ExecutionControl.
**Entrada → saída:** snapshot/limites/owner → resultados ou interrupção com escopo preservado.

- [ ] Iniciar processos filhos com ownership/generation e staging exclusivo, sem handle IFC mutável compartilhado.
- [ ] Testar cancelamento cooperativo, prazo de graça e encerramento só do processo próprio travado.
- [ ] Confirmar parada antes de terminal; manter resultados de unidades/arquivos já concluídos.
- [ ] Verificar T6-05, T6-07 e T6-36; entregar matriz de cancelamento por etapa nativa.

**Aceite:** UI/consultas continuam acessíveis durante trabalho pesado; cancelar não
atinge outro projeto/processo nem converte saída incompleta em publicada.

<a id="m6-t06"></a>

### M6-06 — Runtime Ollama e exclusividade de inferência

**Dependências:** M6-01, M6-04, M6-05. **Responsável:** Nonato; Felipe integra M3, M7 avalia modelos.
**Arquivos futuros:** `ollama_runtime.py`; adaptar `ollama_client.py` e extrair apenas
utilitários gerais do runtime experimental preservando sua condição.
**Entrada → saída:** modelo/CallPlan/configuração → preflight, RuntimeManifest e tentativa.

- [ ] Separar disponibilidade/inventário de geração/warm-up/download; detectar modelo ausente/digest alterado.
- [ ] Implementar slot único da instalação inclusive aquecimento/retry, reconciliação de GPU incerta e pesos compartilhados.
- [ ] Registrar contexto/opções/metadados sem vazar em logs; impedir runtime cloud/remoto.
- [ ] Verificar T6-04, T6-06, T6-08, T6-09, T6-12 e T6-42; entregar evidência de duas filas e zero pull.

**Aceite:** exatamente um despacho ativo do Copilot; nenhuma chamada nova enquanto
a anterior tem término incerto; validação e consulta permanecem úteis sem Ollama.

<a id="m6-t07"></a>

### M6-07 — Serializar mutações e cercar workers antigos

**Dependências:** M6-02, M6-03, M6-04. **Responsável:** Nonato; Felipe alinha preflight M5 e pins M1.
**Arquivos futuros:** `locks.py`, repositórios, fachada de undo/pin/exportação.
**Entrada → saída:** revisão/owner esperado → lease com geração ou conflito explícito.

- [ ] Implementar instância exclusiva por DATA_ROOT, CAS e unicidade da reserva por revisão.
- [ ] Serializar exportação/undo/pin; estabelecer ordem de aquisição e timeout finito.
- [ ] Simular lease vencida com worker antigo vivo; rejeitar retorno/publicação de geração antiga.
- [ ] Verificar T6-27, T6-28, T6-29, T6-40 e T6-49; entregar matriz de conflitos e event_seq observado.

**Aceite:** nenhuma gravação incompatível simultânea na mesma revisão e nenhuma
aprovação/prévia obsoleta aceita por corrida entre abas.

<a id="m6-t08"></a>

### M6-08 — Publicação de artefatos e reconciliação M5/M1

**Dependências:** M6-04, M6-05, M6-07. **Responsável:** Nonato; Felipe é dono dos gates M1/M5.
**Arquivos futuros:** `artifacts.py`, `recovery.py`, adaptadores de publication intent.
**Entrada → saída:** intenção + bytes + recibos do módulo → artefato publicado ou quarentena.

- [ ] Implementar staging imutável por tentativa e promoção controlada pelo coordenador.
- [ ] Injetar falha antes/depois de promoção e commit; reconciliar bytes/hash/recibos sem inventar gate.
- [ ] Preservar os três estados aprovado/escrito/revalidado e sucesso por IFC/derivado.
- [ ] Verificar T6-15, T6-28, T6-30 e T6-48; entregar mapa W0–W8 com pontos de crash.

**Aceite:** arquivo sem recibos não ganha link normal; nova execução de relatório não
reaplica writer; publicação já confirmada não duplica ao reiniciar.

<a id="m6-t09"></a>

### M6-09 — Integrar saúde e progresso na interface

**Dependências:** M6-03, M6-04, M6-06. **Responsável:** Nonato, junto ao M4.
**Arquivos futuros:** `health.py`, rotas e `frontend/src/features/system/`.
**Entrada → saída:** snapshots/eventos → indicador acessível e painel por componente.

- [ ] Mostrar backend, Ollama, modelo, armazenamento, horário/validade e capacidades disponíveis.
- [ ] Implementar estado desconhecido/offline, progresso indeterminado e bloqueio contextual com orientação.
- [ ] Reconectar por sequência/snapshot sem aplicar evento antigo à análise atualmente selecionada.
- [ ] Verificar T6-02, T6-08, T6-14 e T6-39; entregar capturas e roteiro de interação no futuro.

**Aceite:** ícone/cor/texto curto no topo; falha LLM não esconde consulta/validação;
falha backend não mantém “Salvo” para edição sem confirmação.

<a id="m6-t10"></a>

### M6-10 — Logs, auditoria e pacote de diagnóstico

**Dependências:** M6-01, M6-03, M6-04. **Responsável:** Nonato; Felipe confere conteúdo de domínio.
**Arquivos futuros:** `diagnostics.py`, configuração Loguru e adapters de auditoria/evidence_bundle.
**Entrada → saída:** eventos/erros + seleção → logs rotacionados, prévia e pacote local.

- [ ] Distinguir auditoria durável de log com retenção finita por idade/tamanho.
- [ ] Sanear mensagens/stack traces, correlacionar etapas e declarar autoria/relógio não verificados.
- [ ] Gerar prévia com inventário/hash/exclusões, sem IFC/banco/contexto completo por padrão; exportar somente seleção confirmada.
- [ ] Verificar T6-37, T6-38, T6-41 e T6-50; entregar exemplos de mensagem, detalhe e relatório de conteúdo removido.

**Aceite:** diagnóstico é acessível e útil sem upload automático; “append-only” não
é anunciado como proteção contra administrador local.

<a id="m6-t11"></a>

### M6-11 — Espaço, limites e ciclo de armazenamento

**Dependências:** M6-02, M6-05, M6-08. **Responsável:** Nonato; M2/M3/M4/M5 informam custos.
**Arquivos futuros:** `storage.py`, `settings.py`, integração do painel M4.
**Entrada → saída:** volume/escopo/custo estimado → reserva, uso, aviso/bloqueio e limpeza segura.

- [ ] Medir uso em background e aplicar preflight/reserva por operação, mantendo checks durante gravação.
- [ ] Tratar ENOSPC, I/O, permissão e arquivos bloqueados sem apagar trabalho confirmado.
- [ ] Implementar políticas finitas de cache/temporário/log e exclusão apenas de objetos sem refs/locks.
- [ ] Verificar T6-13, T6-14, T6-15, T6-16, T6-44, T6-45 e T6-47; entregar matriz de consumo e falha.

**Aceite:** localização/uso visíveis, backup/GC não disputam objetos fixados e nenhum
original/decisão é eliminado automaticamente por pressão de disco.

<a id="m6-t12"></a>

### M6-12 — Backup local por botão com corte coerente

**Dependências:** M6-07, M6-08, M6-10, M6-11. **Responsável:** Nonato; Felipe confere conjuntos M1/M5.
**Arquivos futuros:** `backup.py`, contratos/rotas e painel M4.
**Entrada → saída:** destino/escopo → job, banco snapshot, inventário e BackupManifest.

- [ ] Implementar barreira de manutenção, snapshot de banco e pin de arquivos do mesmo corte.
- [ ] Validar destino externo à pasta de trabalho e política de pesos opcionais/snapshot estável.
- [ ] Verificar cada membro, integridade referencial e marcador final; simular interrupção/disco cheio.
- [ ] Verificar T6-17, T6-18, T6-19, T6-22, T6-23 e T6-47; entregar backup e recibo sem confundir com restore ensaiado.

**Aceite:** manifesto referencia apenas conjunto recuperável; último backup válido
não é sobrescrito por tentativa falha e a interface conserva progresso/cancelamento.

<a id="m6-t13"></a>

### M6-13 — Restaurar e demonstrar continuidade

**Dependências:** M6-12. **Responsável:** Nonato; Felipe acompanha diagnóstico/saídas após restore.
**Arquivos futuros:** `backup.py`, `recovery.py`, `docs/operacao/backup-restauracao.md`.
**Entrada → saída:** backup validado + pasta nova → candidato restaurado e relatório de aceite.

- [ ] Restaurar isoladamente e conferir hashes, FKs, contagens, versões/pins, histórico e gates de saída.
- [ ] Invalidar ownership/sessão antiga, reconciliar tarefas interrompidas e mostrar pesos ausentes.
- [ ] Medir RPO/RTO observados e documentar ativação preservando conjunto anterior.
- [ ] Verificar T6-20, T6-21, T6-22 e T6-23; entregar prova de consultas/decisões iguais antes/depois.

**Aceite:** reabrir dois projetos/pares e retomar só pendentes sem inferência automática;
backup corrupto/incompatível não altera instalação atual.

<a id="m6-t14"></a>

### M6-14 — Migrar banco/catálogo com recuperação ensaiada

**Dependências:** M6-08, M6-13. **Responsável:** Nonato; Felipe define invariantes/formatos M1–M5.
**Arquivos futuros:** `migrations.py`, schema versionado e `docs/operacao/recuperacao.md`.
**Entrada → saída:** versão origem + backup → candidato validado, ativação ou falha recuperável.

- [ ] Fixar matriz de migração, checksum/id e backup obrigatório antes de mutar candidato.
- [ ] Verificar invariantes em staging e protocolo de ativação conjunto banco/artefatos.
- [ ] Interromper cada fronteira e recuperar com conjunto anterior/restore compatível; não prometer downgrade automático.
- [ ] Verificar T6-24, T6-25 e T6-26; entregar recibos e roteiro de recuperação realmente executado no futuro.

**Aceite:** perda potencial pós-backup explícita, releases históricos resolvíveis e
falha sem banco novo misturado a catálogo incompatível.

<a id="m6-t15"></a>

### M6-15 — Fechar fronteiras de localidade e entrada/saída

**Dependências:** M6-01, M6-06. **Responsável:** Nonato; Felipe alinha gateway bSDD/parsing M2/M5.
**Arquivos futuros:** `local_access.py`, `egress.py`, API do produto e adapter BSDDClient.
**Entrada → saída:** perfil/requisição/DTO público → operação local permitida ou erro registrado.

- [ ] Ensaiar listeners IPv4/IPv6, Host/Origin, segredo de instância e métodos; não iniciar MCP remoto legado.
- [ ] Restringir bSDD por destino/parâmetro/origem sem dados de projeto; testar redirects/proxy e cloud LLM bloqueados.
- [ ] Empacotar ativos UI/viewer locais e executar percurso offline com captura controlada de tráfego.
- [ ] Verificar T6-09, T6-12, T6-31, T6-32, T6-33 e T6-34; entregar matriz de acesso e egresso observado.

**Aceite:** nenhuma interface/API de produto acessível pela LAN/IME, nenhuma conta
criada e nenhum payload de projeto enviado à internet nos percursos ensaiados.

<a id="m6-t16"></a>

### M6-16 — Empacotar, iniciar e encerrar o produto

**Dependências:** M6-09, M6-14, M6-15. **Responsável:** Nonato; Felipe revisa preservação da pesquisa.
**Arquivos futuros:** builder/launcher/stop do produto e `docs/operacao/instalacao-local.md`.
**Entrada → saída:** builds/locks/ativos testados → release identificada e roteiro de instalação.

- [ ] Gerar manifesto com versões/hashes/licenças e separar pacote operacional do benchmark.
- [ ] Implementar início único, porta ocupada, reabertura, saúde sem inferir e shutdown com ownership.
- [ ] Ensaiar instalação limpa/atualização/offline, caminhos Windows e preservação dos dados.
- [ ] Verificar T6-01, T6-34, T6-40, T6-43 e T6-45; entregar guia com evidência e limitações da release.

**Aceite:** operador inicia/encerra sem terminal permanente; falta de Ollama é estado
utilizável para validar/consultar; reinstalação não apaga DATA_ROOT.

<a id="m6-t17"></a>

### M6-17 — Calibrar recursos e instrumentar M7

**Dependências:** M6-05, M6-06, M6-10, M6-11. **Responsável:** Nonato lidera M7 com Felipe.
**Arquivos futuros:** manifestos/medidas operacionais; adaptações controladas de utilitários
de `environment.py`, sem reescrever instrumentos/resultados históricos.
**Entrada → saída:** corpus/condições/hardware → limites versionados e evidência por capacidade.

- [ ] Definir casos e métricas de memória/VRAM, tempo/fila, UI, disco, cancelamento e recuperação.
- [ ] Executar perfis pequenos/típicos/grandes/adversariais e comparar modelos/roteamentos sob condição explícita.
- [ ] Fixar limites finitos, margens e política de contexto por resultado; registrar erro/abstenção e truncamento detectado.
- [ ] Verificar T6-35, T6-36 e T6-46; entregar tabela de capacidades e limites sem vencedor sem evidência.

**Aceite:** hardware/versão/corpus e denominadores acompanham resultados; configuração
não mede “correção semântica” por throughput, nem trata cópias iguais como corpus independente.

<a id="m6-t18"></a>

### M6-18 — Verificar integração e entregar operação do MVP

**Dependências:** M6-01 a M6-17 concluídas nas capacidades anunciadas; disponibilidade
das fachadas M1–M5. **Responsável:** Nonato; Felipe verifica fronteiras sob sua responsabilidade.
**Arquivos futuros:** relatórios de aceite e guias operacionais; índices só em tarefa autorizada.
**Entrada → saída:** release candidata + ensaios → matriz de capacidade, limitações e pacote utilizável.

- [ ] Executar percurso integrado dos dois pares IFC–IDS com consulta/validação sem LLM e enriquecimento quando disponível.
- [ ] Demonstrar salvar/reiniciar/retomar/cancelar, cópias M5 separadas, backup/restore e migração com falha.
- [ ] Repetir negativos críticos na release empacotada e conferir inventário de listeners/egresso/persistência.
- [ ] Consolidar T6-01 a T6-50 por evidência, release e resultado; publicar limites conhecidos e orientação de suporte.

**Aceite:** cada capacidade anunciada possui caso, resultado e evidência; qualquer
lacuna bloqueante mantém aquela capacidade indisponível. Conclusão do documento não
satisfaz este aceite funcional.

### 14.1 Sequência, marcos e esforço

| Marco futuro | Tarefas / entrega demonstrável | Gate de saída |
|---|---|---|
| E6-01 — Base durável | M6-01–03: projetos/revisões/decisões e recibos | Reinício/timeout não perde salvamento confirmado; sem autoria verificada fictícia |
| E6-02 — Execução recuperável | M6-04–08: fila, workers, runtime, locks e publicação | Crash/cancelamento não repete resultado nem publica cópia sem gates |
| E6-03 — Operação observável | M6-09–11 e M6-15: saúde, logs, armazenamento e localidade | UI responsiva, erro útil, fronteira exclusivamente local e egresso restrito |
| E6-04 — Continuidade | M6-12–14: backup, restore, migrações | Restauração e falha de migração demonstradas antes de uso operacional |
| E6-05 — Release medida | M6-16–18 e calibração M6-17 | Pacote/guia, cinquenta casos rastreáveis e limites apoiados em equipamento |

As dependências das tarefas são a ordem executável; marcos agrupam capacidades, não
prometem paralelismo irrestrito nem sete deploys. Primeira fatia: criar projeto e dois
pares, salvar decisão sintética identificada, reiniciar e consultar o mesmo recibo,
sem inferência ou escrita IFC. Em seguida integrar um job determinístico antes de GPU.

Estimativa inicial de planejamento: E6-01 de 4–7 dias de trabalho efetivo; E6-02 de
8–14; E6-03 de 5–9; E6-04 de 6–10; E6-05 de 5–9. Total indicativo 28–49 dias, com
incerteza alta, sem prazo/calendário aprovado e sem descontar dependências M1–M5.
Reestimar após primeiro percurso durável e primeiro ensaio de crash. Hardware, sistema
alvo, volume/corpus e disponibilização das fachadas podem alterar substancialmente o esforço.

<a id="m6-testes"></a>

## 15. Testes futuros e evidências esperadas — NÃO EXECUTADOS

Nenhum caso T6 foi executado nesta entrega. Níveis futuros: contrato/unitário com
filesystem/HTTP/processos substituídos; integração com SQLite/arquivos reais em pasta
temporária isolada; aceite Windows na release e equipamento identificados. Ollama real
e medições de GPU só em ensaio específico autorizado, nunca requisito dos testes
determinísticos. Rede adversarial usa simuladores locais, não dados reais enviados
para endpoints públicos. LLM/bSDD ausentes devem ser um cenário normal verificável.

Corpus futuro: dois projetos distintos; em um, dois pares arquitetônico/estrutural;
GUIDs iguais entre arquivos e duplicados/ausentes em fixture; IFC/IDS imutáveis; banco
com análises/decisões/saídas e versões diferentes de catálogo; modelos fictícios HTTP
para falhas/retries. Cases de escrita M5 usam capacidades já ensaiadas pelo dono e
incluem uma partição boa e outra falha. Preservar materiais e resultados de pesquisa.

Cada evidência terá caso, versão/hash do teste e release, hardware/OS/filesystem,
pré-condições, intervenção/falha, esperado/observado, IDs/hashes/contagens antes/depois,
logs saneados e resultado. “Passou” exige oráculo, não somente exit code ou screenshot.

| Caso | Cenário / intervenção | Oráculo verificável | Evidência futura |
|---|---|---|---|
| T6-01 | Instalação limpa, atualização e primeiro início sem Ollama | UI/API locais abrem; dados fora do código; consulta/validação disponíveis; falta LLM explícita | Manifesto, guia executado e listeners |
| T6-02 | Salvar decisão e perder resposta HTTP; fechar aba/reabrir | Mesmo command_id retorna um recibo; uma decisão persistida; UI reconcilia sem duplicar | Banco/eventos e gravação da UI |
| T6-03 | Queda após 80 de 100 unidades confirmadas; reiniciar | 80 hashes/IDs iguais; só 20 unidades pendentes agendadas após comando Retomar | Checkpoints e chamadas contadas |
| T6-04 | Interromper LLM antes/depois da confirmação de resultado | Confirmado não é regenerado; não confirmado pode repetir com nova attempt/retry_of e motivo | Tentativas e contador de chamadas |
| T6-05 | Cancelar fila, entre unidades e entre dois IFCs | Nenhuma nova unidade do escopo cancelado; concluídos preservados; pacote parcial explícito | Estados/recibos por arquivo |
| T6-06 | Timeout/cancelamento fecha cliente, mas servidor continua inferindo | Slot não é liberado prematuramente; nenhuma segunda geração até reconciliação; externo não é morto | Timeline de despacho e ownership |
| T6-07 | Worker nativo travado junto de processo não pertencente ao job | Só filho identificado/generation correta é encerrado após prazo; API responde | PIDs/instantes de criação e eventos |
| T6-08 | Ollama ausente ou health timeout | Não há generate/pull; erro orienta; análise e consulta continuam | Spy HTTP e percurso M2/M4 |
| T6-09 | Modelo ausente, digest alterado, tag cloud ou versão incompatível | Bloqueio só de inferência afetada; nenhum download/substituto; condição preservada | Manifestos antes/depois e HTTP |
| T6-10 | Dois projetos com nomes/arquivos semelhantes e tentativa de ref cruzada | Consulta/escrita/cache usa project_id correto; refs cruzadas rejeitadas; sem cópia de pesos por projeto | Constraints, manifests e inventário |
| T6-11 | Mesmo GlobalId nos dois IFCs; duplicado no próprio arquivo | ElementRefs distintos por arquivo/revisão/localizador; ambiguidade não escolhe primeiro | Registros e seleção UI |
| T6-12 | Sem LLM e sem internet/bSDD | Validação IDS suportada, consulta, diagnóstico/BCF determinístico continuam; semântica ausente explícita | Resultados/cobertura e tráfego |
| T6-13 | DATA_ROOT relativo, dentro do código, rede, link de fuga e destino válido | Inválidos recusados; válido local absoluto mostra caminho/uso e persiste após reinício | Perfil e checagens de caminhos |
| T6-14 | Espaço insuficiente já no preflight | Produtor não começa; leitura/decisões anteriores intactas; aviso de reserva e volume | Hashes e contagem zero de worker |
| T6-15 | Disco enche entre salvar arquivo, promover e commit | Sem artefato incompleto disponível; journal/quarentena ou recuperação; original e sucessos mantidos | Injeções por fronteira e hashes |
| T6-16 | Commit de decisão falha ou erro não cabe no disco | Sem “Salvo”; último recibo preservado; reinício identifica interrupção sem inventar log | UI, banco e eventos efetivamente salvos |
| T6-17 | Backup enquanto há decisões/jobs/publicações | Snapshot tem corte coerente, FKs/refs/hashes íntegros; nenhuma referência a arquivo pós-corte ausente | Manifesto, event_seq, banco restaurável |
| T6-18 | Backup para DATA_ROOT, subpasta/link equivalente ou mesmo disco | Destino recursivo recusado; mesmo disco separado é permitido com aviso de risco | Prévia e caminhos resolvidos |
| T6-19 | Cancelar backup/desconectar destino/esgotar disco | Sem marcador completo nem substituição do último válido; barreiras liberadas | Diretório parcial e recibos |
| T6-20 | Restaurar backup íntegro em novo diretório | Projetos/decisões/pins/artefatos iguais ao corte; leases antigos invalidados; nenhum job reinicia sozinho | Hashes/contagens e consultas comparadas |
| T6-21 | Backup corrupto, novo schema, caminho traversal ou expansão excessiva | Restore recusado/isolado; nenhum arquivo fora do destino nem mutação da instalação ativa | Relatório por membro/versão |
| T6-22 | Backup/restore sem pesos e sem internet | Identificação/configuração preservadas; validação/consulta operam; inferência informa falta sem baixar | Manifesto, UI e HTTP zero pull |
| T6-23 | Incluir pesos enquanto runtime/pull externo tenta alterá-los | Snapshot estável comprovado ou opção bloqueada; sem backup falsamente completo; apenas uma cópia por instalação | Hashes/estabilidade e exclusões |
| T6-24 | Migração compatível bem-sucedida | Backup anterior verificado; candidato válido; refs/histórico intactos e recibo de ativação | Checks, versões e consultas |
| T6-25 | Falha antes/durante/depois de banco, catálogo e ativação | Conjunto anterior íntegro ou restore compatível; candidato não liberado, erro/etapa explícitos | Matriz de crash e recuperação |
| T6-26 | Abrir banco mais novo com release antiga / tentativa de downgrade | Sem escrita incompatível nem rollback automático; instrução de restore e perda pós-backup explícita | Recibo e diretórios preservados |
| T6-27 | Duas abas editam mesma revisão; mesma key com payload igual/diferente | Um CAS vence; duplicata igual retorna recibo; diferente recebe conflito sem efeito adicional | Banco/event_seq e respostas API |
| T6-28 | Exportar M5 simultaneamente a undo/troca de pin/segunda escrita | Reserva serializa; prévia obsoleta rejeitada; snapshot em curso imutável; leitura permanece | Ordem de eventos e gates W0–W8 |
| T6-29 | Lease expira, worker antigo volta após nova geração | Resultado/publicação da geração antiga recusado; só tentativa vigente pode confirmar | Tokens/generation e artefatos |
| T6-30 | Crash entre bytes finais e recibo, inclusive W5/W6/W8 M5 | Reconciliar intenção/hash/gates; sem repetir writer confirmado nem inventar revalidação | Journal e matriz de pontos de queda |
| T6-31 | Override 0.0.0.0/::/IP LAN, teste IPv4/IPv6 e cliente LAN | Overrides proibidos; listeners só loopback; cliente externo não acessa UI/API; MCP remoto não iniciado | Sockets e tentativas de acesso |
| T6-32 | Origin/Host malicioso, null, rebinding, token ausente e GET mutante | Comando bloqueado; UI/token não servido a Host indevido; request legítimo sem login funciona | Requisições negativas controladas |
| T6-33 | Consulta bSDD válida e tentativa com nome/GUID/contexto/redirect/proxy indevido | Só DTO público permitido sai; conteúdo de projeto não sai; falha explícita mantém M2 | Captura/spy saneado e decisões de policy |
| T6-34 | Rede desligada e cache de navegador vazio | UI/lista/viewer com ativos empacotados; sem CDN/telemetria; origem de semântica local identificada | Inventário de assets e tráfego |
| T6-35 | Campo/contexto maior que janela e resposta truncada | Fonte inteira local; divisão/omissão explícita ou abstenção; não aceitar JSON parcial como proposta completa | CallPlan, tokens e cobertura |
| T6-36 | Exceder bytes/memória/duração/profundidade/filas | Limite finito aplicado; worker controlado, parcial/erro com escopo; UI segue consultável | Política/hash, métricas e erro |
| T6-37 | Logs passam limites de idade/tamanho e disco cheio | Rotação finita; auditoria/decisões preservadas; ausência de IFC/contexto/segredos no log geral | Arquivos/contagens e scanner |
| T6-38 | Diagnóstico padrão e seleção adicional com alteração após prévia | Padrão exclui conteúdo integral; exportação coincide com seleção/hash ou pede nova prévia; não há envio externo | Inventário/manifesto e comparação |
| T6-39 | Saúde muda OK→erro→desatualizado, backend some | Ícone/cor/texto acessíveis; detalhe dos quatro componentes; bloqueios só nas ações afetadas | Estados UI com horário e mensagem |
| T6-40 | Abrir duas vezes, porta ocupada, encerrar normal/forçado | Instância única; sem matar processo alheio; progresso salvo confirmado e órfãos reconciliados | Processo/lock/recibos e reinício |
| T6-41 | Informar nome de terceiro, publicar catálogo, importar autor BCF | Identificação continua não verificada; ação explícita/recibo não prova pessoa; sem contas/papéis falsos | Contextos de ator e relatório |
| T6-42 | Mudar IFC/IDS/pin/modelo/receita/contexto mantendo nome/GUID | Nova identidade/cache miss onde relevante; histórico preservado; sem reaplicar decisão antiga | Chaves completas e tentativas |
| T6-43 | Dependência/build/asset diverge do lock ou licença ausente | Release/capacidade não anunciada pronta; drift detectado; pacote benchmark preservado | Manifesto e relatório de build |
| T6-44 | Trocar DATA_ROOT e falhar durante cópia/validação | Pasta antiga íntegra, referência não aponta para candidato incompleto; novo destino só após checks | Hashes e configuração antes/depois |
| T6-45 | Espaços/acentos, permissão negada, antivírus mantém handle, links Windows | Erro específico e recuperação; sem overwrite fora da área; original não alterado | Casos filesystem na versão Windows |
| T6-46 | Coletar métricas e comparar configurações com M7 | Hardware/condição/corpus/digest completos, falhas denominadas; nenhum vencedor inferido do default | Exportação de medidas e condição |
| T6-47 | GC/limpeza durante backup e uso de catálogo/artefato por projeto | Arquivos referenciados/fixados não removidos; caches só quando regeneráveis; pesos mantidos | Pins, inventário e hashes |
| T6-48 | Aprovação salva, escrita falha, revalidação parcial e IDS não conforme | Eixos permanecem separados; job completo não dá selo conforme; M5 aplica gates de liberação | Recibos M4/M5/M2 e tela |
| T6-49 | Leituras simultâneas, busy SQLite prolongado e ordem de locks | Transações curtas; timeout finito/erro; sem deadlock ou fila congelada; dados íntegros | Timeline SQL/locks e integridade |
| T6-50 | Relógio do OS retrocede entre eventos e reinício | Sequência conserva ordem; UTC marca discrepância; duração não fica negativa por wall clock | event_seq, durações e aviso |

### 15.1 Demonstrações obrigatórias de conclusão funcional

1. Instalar/iniciar/encerrar release local com dois pares, ausência de Ollama e zero
   download; mostrar consulta/validação e indicador de saúde.
2. Salvar decisões, perder resposta, encerrar/reiniciar; recuperar recibos e retomar
   apenas unidades faltantes, com repetição LLM interrompida identificada.
3. Cancelar com uma partição concluída e outra em andamento; preservar a primeira,
   não publicar a segunda incompleta e manter UI responsiva.
4. Produzir erro de espaço antes e durante gravação, sem apagar fontes ou anunciar
   salvamento incerto; recuperar a partir dos checkpoints/journal.
5. Criar backup com atividade concorrente e restaurar isoladamente; conferir banco,
   arquivos/pins, decisões e pesos opcionais; registrar RPO/RTO observados.
6. Falhar migração de banco e catálogo em cada fronteira crítica e recuperar com
   conjunto compatível, sem promessa de rollback automático genérico.
7. Duas abas/instâncias tentam gravar a mesma revisão e worker antigo retorna;
   apenas efeito vigente confirmado, sem conflitar undo/exportação.
8. Comprovar listener exclusivamente local, bloqueio de requisição indevida e
   saída bSDD restrita, sem dados de projeto ou assets externos.

<a id="m6-aceite"></a>

## 16. Riscos, responsáveis e critérios de conclusão

| Risco | Falha concreta / consequência | Contenção e dono |
|---|---|---|
| R6-01 — Autoria fictícia | Nome “engineer” ou informado vira assinatura de pessoa | assurance local explícita e limites em relatório; Nonato com M4/M5 |
| R6-02 — Perda de revisão | UI diz salvo antes do commit ou só usa memória | Recibo/transação/consulta de comando; Nonato |
| R6-03 — GPU dupla | Timeout libera slot enquanto Ollama continua | Slot incerto bloqueado, runtime próprio/reconciliação e ensaio; Nonato/M3 |
| R6-04 — Publicação ambígua | Arquivo existe sem verificação ou banco aponta para bytes faltantes | Intenção/gates/hash/journal; Nonato + Felipe M5 |
| R6-05 — Corrida de revisão | Undo/pin/exportação simultâneos usam decisões diferentes | CAS, reserva, fencing e snapshot; Nonato + Felipe |
| R6-06 — Backup inutilizável | Banco de um instante e IFC/catálogo de outro | Barreira/corte/pins/manifests e restore testado; Nonato |
| R6-07 — Migração destrutiva | DDL passou mas histórico ou pin ficou incompatível | Candidato isolado, backup, invariantes e recuperação ensaiada; Nonato + Felipe |
| R6-08 — Exposição local/remota | MCP 0.0.0.0, CORS amplo, conteúdo do IFC em bSDD | Launcher próprio, loopback/Host/Origin/egresso e tráfego verificado; Nonato |
| R6-09 — Esgotamento de disco | Cache/WAL/temporários crescem e impedem salvar | Limites, reservas e falhas em cada etapa sem apagar trabalho; Nonato |
| R6-10 — Dependência/método muda | Atualização Ollama/modelo ou lock altera condição | Preflight/digest/build, nova condição e preservação de resultados; Nonato/M7 com Felipe |
| R6-11 — Truncamento oculto | Resultado incompleto aparece como concluído | Budgets, cobertura, stop reason e abstenção; Nonato + Felipe M2/M3 |
| R6-12 — Suporte não demonstrado | Proposta de arquitetura ou código existente é anunciada como capacidade | Matriz por release/hardware/caso e limites públicos; Nonato coordena |

**Pronto para implementar uma fatia:** contratos/esquemas de fronteira e teste negativo
identificados, diretório de ensaio seguro, baseline da pesquisa preservado, responsável
e dependências disponíveis. Não exige nova aprovação do texto já autorizado; execução
funcional é outro escopo de trabalho.

**Pronto funcionalmente no MVP:** todas as decisões D6 possuem capacidade entregue ou
bloqueio explícito que impede anúncio de conclusão; cinquenta casos rastreados nas
versões anunciadas; oito demonstrações acima concluídas, sem falha bloqueante aberta;
backup/restauração e recuperação de migração testados; fontes/histórico preservados;
UI/API exclusivamente locais; nenhuma conta/login incluída; pacote e guias utilizáveis;
limites concretos calibrados; matriz de compatibilidade e riscos residuais disponíveis.

Falha de autenticação/ACL institucional não é pendência de MVP porque rede/IME está
fora dele. Em contrapartida, loopback, defesa de requisições locais e isolamento lógico
por projeto são requisitos do MVP. Um teste mock não certifica GPU/Windows, e teste
operacional não mede qualidade semântica. M7 avalia essa qualidade em condição própria.

**Conclusão documental:** redação/releitura, cobertura D6, contratos, tarefas/testes,
links/âncoras e preservação verificados, com relatório de apoio. Não requer ensaios
de produto nem significa implementação concluída.

<a id="m6-integracao"></a>

## 17. Divergências e ajustes de integração propostos

Nenhum arquivo anterior ou índice foi alterado. A tabela registra a precedência
aplicável ao implementar contratos; eventual edição dos documentos antigos será
tarefa própria, preservando a origem/data da decisão.

| ID | Origem da divergência | Regra atual / ajuste proposto no M6 |
|---|---|---|
| I6-01 | M1 curadoria §4.1/§6.6 exige papéis/autorização; M4 §12 propõe perfis/ACL | MVP sem contas; curadoria como responsabilidade declarada com candidato exato/recibo, limite de enforcement humano explícito; autorização real antes de rede |
| I6-02 | M5 §4 define Actor como principal autenticado e recebe ACL; M2 §8.6/M3 §10.4 mencionam autenticação | Adaptar Actor para LocalActorContext não verificado. Preflight confere instância/escopo/revisão, não inventa pessoa autenticada |
| I6-03 | Mapa/M1/M2/M3 admitem local ou interno IME genericamente | Perfil MVP exclusivamente loopback; rede interna também exige fase posterior com autenticação, projeto e administração |
| I6-04 | M1/M2 ainda descrevem análise individual e federação posterior em trechos históricos | Dois pares no MVP conforme decisão posterior; fila GPU compartilhada, dados/saídas separados e sem evidência cruzada |
| I6-05 | Foundation/SemanticCatalog e M1 descrevem ausência de HTTP público como regra ampla | Exceção vigente bSDD M3/D6-10 com DTO público restrito; leitura de pacote local continua sem aquisição implícita |
| I6-06 | IssueStore/AuditLogger/session_state mantêm estado em memória; cache SQLite pode parecer persistência suficiente | Banco operacional é autoridade de decisões/fila/recibos; cache não comprova recuperação nem auditoria |
| I6-07 | MCP HTTP default 0.0.0.0/CORS * e CDN UI legados | Não integrar esses defaults ao launcher; UI/API do produto loopback/mesma origem e ativos empacotados |
| I6-08 | Runtime/install Windows e model_lock são benchmark e incluem pulls/matriz fixa | Reusar utilitários mediante adaptação; release do produto separada, nenhuma inferência/download ao verificar saúde |
| I6-09 | M1 rollback de pin e M3 tarefa de rollback podem ser confundidos com rollback de banco | Pin anterior cria nova análise; recuperação de migração usa conjunto compatível/backup ensaiado, sem rollback automático prometido |
| I6-10 | Responsabilidade histórica M7 em M1 é Felipe; mapa antigo tem próximos debates M4/M5 | Atualização: Felipe M1/M2/M3/M5; Nonato M4/M6 e liderança M7 com Felipe. Não reabrir planos/protótipo concluídos |
| I6-11 | M4 deixa política de saída parcial a fechar em M5 | M5 já fornece W0–W8, recibos e liberação; M6 sustenta gates sem criar política rival ou unir aprovado/escrito/revalidado |
| I6-12 | Índices ainda podem apontar frentes seguintes como “próximo debate” | Sugerir futuramente link para este M6 e seu status documental, sem alterar índices nesta tarefa |

As regras de publicação e escrita de domínio permanecem: LLM não publica catálogo nem
aprova campo, M2 não altera IFC, M4 salva decisão sobre candidato exato e M5 só aplica
o aprovado em cópia. “Sem contas” não remove confirmação técnica de conteúdo/revisão.

<a id="m6-fontes"></a>

## 18. Fontes, versões e limites da evidência

### 18.1 Fontes locais consultadas

- [Índice vigente](README.md) e [mapa das frentes](mapa-sete-frentes.md): decisões,
  responsáveis e escopo histórico; trechos superados tratados em I6.
- [M1: interfaces e pacotes](modulo-01-dominio-catalogo.md#m1-interfaces): catálogo
  imutável, curadoria, revisão esperada e pin por projeto.
- [M2: operação](modulo-02-nucleo-ifc-ids.md#m2-operacao): parsing, limites, worker
  isolado, estados e diagnóstico independente do LLM.
- [M3: pipeline](modulo-03-contexto-enriquecimento.md#m3-pipeline) e
  [segurança](modulo-03-contexto-enriquecimento.md#m3-seguranca): fila serial,
  contexto/cache por identidade e bSDD restrito.
- [M4: persistência](modulo-04-interface-revisao.md#m4-persistencia),
  [perfis](modulo-04-interface-revisao.md#m4-perfis): recibos, retomada e divergência
  de contas/ACL resolvida aqui pela decisão atual.
- [M5: escrita](modulo-05-saidas-revisoes.md#m5-escrita) e
  [operação](modulo-05-saidas-revisoes.md#m5-operacao): publicação por IFC,
  gates/revalidação, cancelamento, journal e retorno BCF.
- [Apoio documental M5](apoios-modulo-05/verificacao-documental.json): evidência
  recebida de verificação, não testes operacionais M6 nem reexecução de M5.
- [Convenções](../../CLAUDE.md) e código ligado na seção 2: inventário estático
  de implementação versus lacuna. Descrições antigas não prevalecem sobre D6.

### 18.2 Documentação primária consultada em 12/10/2026

| Fonte | Contribuição limitada à decisão técnica |
|---|---|
| [SQLite WAL](https://www.sqlite.org/wal.html) | Modelo de leitores/escritor, restrição de host/filesystem e durabilidade; fundamenta opção local, não certifica nosso banco |
| [SQLite Online Backup API](https://www.sqlite.org/backup.html) | Snapshot consistente de banco; M6 acrescenta coordenação dos arquivos externos |
| [SQLite locking](https://www.sqlite.org/lockingv3.html) | Referência de mecanismos de locking; comportamento exato do perfil escolhido será ensaiado |
| [Ollama List models](https://docs.ollama.com/api/tags) | Metadados de inventário para verificar presença/digest; não prova inferência nem disponibilidade de GPU |
| [Ollama FAQ](https://docs.ollama.com/faq) | Configuração local, cloud, pastas e runtime; requisitos concretos vinculados à versão instalada/ensaiada |

Os planos de protocolo/recuperação são desenho de engenharia, não uma alegação de que
as bibliotecas os implementam automaticamente. Documentação online pode evoluir;
na implementação guardar versão/trecho relevante e ensaiar a versão fixada. Tentativas
de abrir páginas `docs.ollama.com/api/show` e `www.uvicorn.org/settings/` não forneceram
conteúdo utilizável nesta consulta; nenhuma capacidade depende de informação dessas
páginas. Não houve ensaio de restore, benchmark, inferência ou instalação neste turno.

<a id="m6-cobertura"></a>

## 19. Matriz de cobertura das decisões aprovadas

| Decisão | Especificação neste plano | Tarefas futuras | Casos futuros |
|---|---|---|---|
| D6-01 | [Governança](#m6-governanca), [localidade/IME](#m6-localidade) | M6-01, M6-15, M6-16 | T6-01, T6-31, T6-32, T6-41 |
| D6-02 | [Dados/contratos](#m6-contratos), [layout](#m6-armazenamento) | M6-02, M6-06, M6-11 | T6-10, T6-11, T6-22, T6-42 |
| D6-03 | [Fila/cancelamento](#m6-fila), [runtime](#m6-runtime) | M6-04, M6-05, M6-06, M6-09 | T6-05, T6-06, T6-07, T6-39 |
| D6-04 | [Checkpoints/retomada](#m6-fila), [publicação](#m6-concorrencia) | M6-03, M6-04, M6-08 | T6-02, T6-03, T6-04, T6-30 |
| D6-05 | [Preflight/manifesto](#m6-runtime) | M6-06, M6-09 | T6-08, T6-09, T6-12, T6-42 |
| D6-06 | [Armazenamento/espaço](#m6-armazenamento) | M6-02, M6-11 | T6-13, T6-14, T6-15, T6-16, T6-44 |
| D6-07 | [Backup/restore](#m6-backup) | M6-12, M6-13 | T6-17, T6-18, T6-19, T6-20, T6-21, T6-22, T6-23 |
| D6-08 | [Auditoria](#m6-governanca), [logs/diagnóstico](#m6-saude) | M6-10 | T6-37, T6-38, T6-41, T6-50 |
| D6-09 | [Release/migração](#m6-instalacao) | M6-14, M6-16 | T6-01, T6-24, T6-25, T6-26, T6-43 |
| D6-10 | [Egresso/localidade](#m6-localidade) | M6-06, M6-15 | T6-09, T6-12, T6-33, T6-34 |
| D6-11 | [Limites/calibração](#m6-runtime), [espaço](#m6-armazenamento) | M6-05, M6-11, M6-17 | T6-14, T6-15, T6-35, T6-36, T6-46 |
| D6-12 | [Saúde no topo](#m6-saude) | M6-09 | T6-08, T6-14, T6-39 |
| D6-13 | [Concorrência](#m6-concorrencia), [fila/encerramento](#m6-fila), [launcher](#m6-instalacao) | M6-04, M6-05, M6-07, M6-16 | T6-27, T6-28, T6-29, T6-40, T6-49 |

### 19.1 Revisão cruzada de contratos

- M1/M4/M5: substituir principal autenticado por ator declarado no MVP sem apagar
  validação de candidato, revisão esperada e recibo; requisito institucional permanece futuro.
- M2/M3: ResultSink e checkpoints conservam identidade/cobertura; resultado parcial
  não vira conforme e alternativa gerada não vira decisão humana.
- M3/M6/M7: runtime serial inclui warm-up/retry, manifestos completos e modelo definido
  por ensaio; parâmetros/defaults históricos não são recomendação de vencedor.
- M4/M5/M6: decisão confirmada → plano congelado → escrita em cópia → verificação salva
  → revalidação M2 → liberação segundo M5; nenhuma etapa infere sucesso da próxima.
- M1–M7: projeto/arquivo/revisão/elemento e pins exatos; pesos compartilhados sem
  compartilhar contexto; hashes ajudam integridade, não autenticam pessoa local.
- Backup/migração/retomada: conjunto banco+arquivos coerente, leases novos e jobs
  antigos interrompidos; abrir/restaurar não relança writer/LLM.

<a id="m6-verificacao"></a>

## 20. Verificação documental, preservação e encerramento

### 20.1 Escopo de escrita

Somente este plano e documentos exclusivos em `apoios-modulo-06/`. O
[manifesto de preservação](apoios-modulo-06/manifesto-preservacao.json) contém baseline
SHA-256/bytes dos arquivos preexistentes, escopo/exclusões, proveniência temporal de
cada snapshot e estado Git observado.
O [relatório de verificação](apoios-modulo-06/verificacao-documental.json) registra
checagens, contagens, comparação final e limites. Nenhum script de verificação é
adicionado ao produto; verificações documentais usam apenas leitura e biblioteca padrão.

O inventário integral abrange 907 arquivos, inclusive código, planos anteriores,
resultados, materiais, dados e protótipo. Há comparação SHA-256 contra referência
anterior à tarefa para 401 arquivos: 400 do manifesto M5 e o próprio plano M5, cujo
hash entregue consta daquele apoio. Para os demais, a prova integral por hash cobre
o intervalo entre snapshot após redação e verificação final; a contagem/bytes totais
também são comparados ao output inicial. A perda do temporário inicial impede alegar
comparação dos 907 hashes desde antes da redação. O histórico de ferramentas contém
somente escritas no plano e apoios M6, além dos temporários de verificação.

Não se inclui `.git` como árvore de conteúdo, `.venv`, `node_modules`, `__pycache__`
e caches de ferramentas listados no manifesto; HEAD/index são verificados
separadamente. Não há certificação de arquivos fora desse escopo nem de mudanças
posteriores à captura final. Reutilizar hashes do apoio M5 para preservação não
reexecuta seus testes nem modifica sua entrega.

Coordenação posterior do pai autorizou uma tarefa M7 separada durante esta revisão.
Novos arquivos exclusivos de M7 são trabalho concorrente autorizado e não são
atribuídos ao M6 nem revertidos. O relatório registra seus caminhos concretos em
`authorized_concurrent_m7_files`; lista vazia significa nenhum caminho observado
naquele snapshot, não ausência de trabalho M7 em andamento.

### 20.2 Fechamento verificado

Releitura editorial e validação automática conferiram treze decisões com
rastreabilidade, sete fronteiras, dezoito tarefas com dependências/entregáveis e
cinquenta testes **futuros** com oráculos. Foram conferidos doze riscos, doze
divergências, 38 âncoras explícitas, 22 tabelas e 95 ocorrências de links locais,
sem destinos ou âncoras quebrados. O relatório consolida 51 checagens documentais,
incluindo a conferência final do status/hash do plano salvo; testes T6 não integram
essa contagem de execução.

Os 401 hashes com referência anterior coincidiram; os 907 arquivos do snapshot
após redação permaneceram idênticos na comparação final, com os limites temporais
descritos acima. HEAD, branch e index foram preservados. Não houve stage, commit,
push, implementação, instalação ou alteração dos planos anteriores/índices/protótipo.
**Planejamento documental concluído e verificado; sem bloqueador documental e sem
necessidade de nova aprovação pessoal. Implementação e ensaios permanecem futuros.**

As checagens documentais executadas e seus resultados ficam no JSON de apoio. Não
há teste de produto, restauração, migração, inferência, desempenho, interoperabilidade
ou segurança operacional executado aqui. Hardware/limites/releases definitivos e
topologia IME continuam decisões/ensaios de implementação, sem bloquear o planejamento.

### 20.3 Integração posterior

Propor aos responsáveis atualização dos índices/mapa com link e status documental
deste M6, precedência de ausência de contas e fronteira da fase IME; harmonizar Actor,
perfis M4 e preflight M5 com a seção 5. Esta sugestão não é alteração dos documentos
anteriores nem nova solicitação de aprovação pessoal para encerrar o M6 documental.
