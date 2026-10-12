# Módulo 7 — Avaliação científica

> **PLANEJAMENTO DOCUMENTAL CONCLUÍDO E VERIFICADO — 12/10/2026.** Evidência na seção 20 e no relatório de apoio.
> **Avaliação nova não implementada nem executada. Nenhum resultado científico novo é declarado.**
> **Nonato lidera M7, inclusive prospecção de modelos. Felipe auxilia nos critérios BIM, gabaritos e revisão técnica.**

**Objetivo:** avaliar como a preparação e a recuperação do contexto influenciam o enriquecimento de propriedades BIM para orçamento por LLMs locais, comparando modelos e regras determinísticas nos mesmos casos e distinguindo recuperação, qualidade da sugestão e benefício da revisão humana.

**Arquitetura proposta:** uma camada de pesquisa sobre os snapshots e contratos de M1–M6, com corpus e gabarito independentes, partições por grupos de origem, condições congeladas, registro por chamada/campo e análise reproduzível. O núcleo inicial mede recuperação/contexto e enriquecimento; o estudo com pessoas é secundário. Não são sete serviços nem um novo motor IFC/IDS.

**Base técnica:** Python e formatos locais JSON/JSONL/CSV, utilitários de identidade e avaliação já existentes, M2 como fonte do diagnóstico, M3 como executor de receitas/contexto e M6 como responsável pela fila/recursos/persistência. Os novos objetos, diretórios, testes e métodos abaixo são propostas de implementação e pesquisa, não APIs existentes.

**Especificação:** pedido integral de Felipe encaminhado em 12/10/2026, após brainstorming encerrado e aprovado; dezesseis decisões rastreadas em D7. O alinhamento formal do recorte com o orientador permanece etapa acadêmica prevista, **sem aprovação acadêmica inventada**. A autorização documental não depende de uma nova confirmação pessoal.

**Coordenação:** tarefas reconciliadas pelo pai; não há outro M7 ativo. M3/M4/M5 e protótipo foram entregues nas respectivas tarefas; isso não certifica implementação integral dos módulos. M6 foi concluído durante esta elaboração e sua versão final foi relida para reconciliação: SHA-256 `3069bd87f64c6e4e80909f3b12e3af1fc4fb347102ee8f35aaa058968639a8c1`, 125.435 bytes. O relatório M6 registra 51 verificações documentais, sem ensaios operacionais. Apenas este plano e apoios exclusivos M7 são escritos aqui. Índices, M1–M6, código, experimentos e protótipo permanecem sob seus responsáveis.

**Navegação:** [Decisões](#m7-decisoes) · [Inventário](#m7-inventario) · [Perguntas](#m7-perguntas) · [Arquitetura](#m7-arquitetura) · [Contratos](#m7-contratos) · [Corpus](#m7-corpus) · [Gabarito](#m7-gabarito) · [Condições](#m7-condicoes) · [Métricas](#m7-metricas) · [Execução](#m7-execucao) · [Análise](#m7-analise) · [Estudo humano](#m7-humano) · [Prospecção](#m7-prospeccao) · [Extensões](#m7-extensoes) · [Tarefas](#m7-tarefas) · [Verificações futuras](#m7-testes) · [Entregas](#m7-entregas) · [Riscos](#m7-riscos) · [Cobertura](#m7-cobertura) · [Fechamento](#m7-verificacao).

<a id="m7-decisoes"></a>

## 1. Decisões aprovadas e restrições globais

| ID | Decisão recebida | Consequência verificável |
|---|---|---|
| D7-01 | Recuperação, sugestão e benefício humano separados; revisão humana secundária | Três avaliações, denominadores e conclusões próprios; núcleo inicial independente do recrutamento |
| D7-02 | Gabarito por caso com alternativas, evidência, suficiência, conflitos e abstenção/esclarecimento | Revisão BIM/especialista; IFC original e outra LLM não são verdade automática |
| D7-03 | Desenvolvimento, seleção e avaliação final separados por grupos correlacionados | Projetos, edifícios, tipos repetidos e revisões não cruzam partições; exposição da casa/prédio declarada |
| D7-04 | Regras; mesmas regras + LLM/contexto básico; mesmas regras + LLM/contexto por propriedade | Pacotes disponíveis/selecionados registrados; controles de evidência igual separam recuperação de interpretação |
| D7-05 | Chamada por elemento versus por propriedade residual | Fatorial separa divisão das perguntas de filtragem; qualidade por campo e tempo total; nenhuma estratégia vencedora prévia |
| D7-06 | Dez categorias de Daiane e propriedades conforme casos reais | Matriz MODELOS × PROPRIEDADES, cortes por categoria, contagens e lacunas explícitas |
| D7-07 | Pendências reais na primeira etapa | Não remover campos para criar lacunas; masking histórico e eventual extensão separados |
| D7-08 | Correção, evidência/associação, propostas sem fundamento, abstenções, conflitos, requisitos, cobertura e recursos | Passar IDS não prova verdade de engenharia; erro técnico não vira abstenção correta |
| D7-09 | Configurações comparáveis, versões/digests, hardware/software e repetições pelo piloto | Manifesto completo, seed quando suportada, tempo de carga/inferência/fluxo separado |
| D7-10 | Contagens, variação e incerteza adequadas | Não forçar vencedor; desenho estatístico fechado antes da avaliação final |
| D7-11 | Roteamento por propriedade/grupo considera qualidade, sustentação, abstenção e recursos | Selecionar fora do teste; confirmar no reservado; futura política configurável M3 |
| D7-12 | Reaproveitar legado preservando instrumento e entradas | Matriz de comparabilidade e necessidade de repetição; mudanças geram rodadas distintas |
| D7-13 | Estudo secundário sem sugestões versus assistido | Dificuldade semelhante, casos distintos/ordem contrabalançada, tempo/consultas/correções/erros finais |
| D7-14 | Documentos externos são opção com orientador | Extensão IFC versus IFC+documentos, incluindo regras, extração/associação/conflito; não obrigação do MVP |
| D7-15 | Prospecção contínua por Nonato em duas linhas: pessoal e servidor IME | Hardware real antes de porte; licença/procedência/versão/quantização/contexto/runtime; triagem antes de benchmark |
| D7-16 | Participantes/configurações fixos por rodada | Novos modelos somente em rodadas posteriores; sem automação, download, treino ou fine-tuning inicial |

Aplicam-se também as decisões finais M6: **MVP localhost, sem login/contas/admin**, dados separados por projeto, pesos Ollama compartilhados por instalação, uma inferência ativa por vez inclusive aquecimento/retry, fila persistente, cancelamento com parciais, backup local e limites explícitos. Acesso em rede IME depende de autenticação e permissões reais, ainda futuros. Declaração local de nome não autentica pesquisador ou revisor.

O MVP admite dois pares IFC–IDS (arquitetura/estrutura) na mesma sessão visual, com processamento e evidência separados por arquivo; a federação visual não autoriza contexto cruzado. A API pública bSDD pode fornecer semântica pública, sem enviar conteúdo de projeto; a resposta usada é fixada localmente para reprodução. Validar/exportar diagnóstico não depende da LLM. M2 não altera IFC; M3 propõe; M4 registra decisão exata; M5 escreve em cópia e M2 revalida.

Não executar neste planejamento: implementação funcional, suíte operacional, benchmark/inferência, download de modelos, modificação de gabaritos/resultados históricos, commit, stage, push, publicação ou automação recorrente.

<a id="m7-inventario"></a>

## 2. Inventário efetivo e continuidade da pesquisa

### 2.1 Artefatos reconferidos em 12/10/2026

O [inventário legível](../pesquisa/modulo-07-avaliacao/inventario-legado.md), o [JSON integral de metadados](../pesquisa/modulo-07-avaliacao/inventario-experimentos.json) e o [CSV por run](../pesquisa/modulo-07-avaliacao/inventario-runs.csv) registram localização, hashes, configuração disponível, pares de sidecars e limites da auditoria. A contagem usa artefatos efetivamente encontrados, sem executar o harness.

| Universo | Contagem verificada | Limite |
|---|---:|---|
| `src/experiment/results/**/run_*.json` | 155 | Versões v3, v4, v5, v6, v7, v7.1, v7.2 e v7.6; são runs, não rodadas independentes |
| Outros JSON nesse diretório | 3 | Lock, identidade de execução e resumo smoke; não somados como runs |
| Seis `dist/RESULTADO*.zip` únicos de primeiro nível | 120 runs | 20 v7.5 + 100 v7.7; vinte runs por pacote |
| Sidecars em diretório | 120 / 180.580 linhas | 35 runs não têm sidecar adjacente; granularidade de reanálise limitada |
| Sidecars nos seis ZIPs | 120 / 298.980 linhas | Todas as linhas parseadas; isso não revisa correção de cada resposta |
| Total inventariado | 275 runs / 479.560 linhas JSONL | 275 hashes de run distintos; linhas não equivalem a chamadas nem unidades independentes |
| Metadados sem digest do modelo | 121 runs locais | Não preencher pelo lock atual; reprodução exata limitada |
| `review_proxy` | 275/275 runs | Simulação pelo gabarito, não observação humana |
| Runs v7.8 localizados nesse universo | 0 | Código vigente v7.8 e verificação de prompts não provam inferência executada |

Há uma cópia do ZIP de 14/08 dentro da pasta de release: seu SHA-256 coincide com o pacote de primeiro nível e ela é excluída da soma. Os `payload/project.zip` são pacotes de distribuição, não runs adicionais. Para os seis ZIPs de resultados, hashes/tamanhos de **240 membros** (120 JSON + 120 JSONL) coincidiram com seus manifestos. Não foi feita auditoria semântica dos logs volumosos ou binários.

**Modelos com evidência:** os dez principais, os dez de escala e `phi3.5` em um smoke inicial, totalizando **21 tags históricas**. `qwen3:14b` aparece tanto no smoke inicial quanto na escala, sem virar um modelo adicional. O [registro por modelo](../pesquisa/modulo-07-avaliacao/registro-modelos.json) contém todos os caminhos de runs, digests observados e locks históricos. Tag móvel/`latest` não basta para reproduzir o artefato.

Os snapshots `software/ollama-models.json` dos seis ZIPs registram dez instalados em cada ambiente histórico; neste conjunto coincidem com as dez tags participantes do respectivo pacote. A comprovação de teste vem dos runs, não dessa coincidência. **Inventário atual do Ollama não foi consultado.** Nem estar instalado hoje, nem aparecer em lock, documento, `llmfit` ou lista de candidatos comprova participação em benchmark.

O arquivo de raiz `--help` foi lido como JSON de prompts, **nunca executado como comando**. `casa_v1.ifc`, `predio_v1.ifc`, cópias em `data/evaluation` e `predio_v1_masked.ifc` têm exposição histórica; deduplicar por hash e linhagem, sem tratá-los como novos projetos. `pavilhao_comando_norte.ifc` é arquivo disponível, não corpus independente aprovado: procedência, exposição, licença e pendências precisam ser examinadas antes da seleção.

### 2.2 Código, configurações e limitações identificadas

| Base lida | Reaproveitamento possível | Cuidado para M7 |
|---|---|---|
| [runner.py](../../src/experiment/runner.py) | Diagnóstico, filtros/amostragem, metadados, timing, sidecars e cópia descartável | Chama geração e revisor simulado; não executar como inspeção; adaptar a nova condição sem substituir a histórica |
| [evaluator.py](../../src/experiment/evaluator.py) | Alternativas aceitas, comparador normalizado, cortes por equivalência/confiança | Chave GUID/tipo/campo é insuficiente entre arquivos; correção numérica/textual não mede sustentação ou associação; itens sem GT são omitidos da correção histórica |
| [metrics.py](../../src/experiment/metrics.py), [per_issue.py](../../src/experiment/per_issue.py) | Metadados, estabilidade, tempo, exportação e pareamento por estímulo real | Denominadores e independência precisam corresponder ao novo desenho; não aplicar McNemar por cópias de uma chamada |
| [reviewer.py](../../src/experiment/reviewer.py) | Simula aceitação/edição segundo casamento com GT e pós-valida cópia | Não mede tempo, esforço, erros ou escolhas de pessoas; não reutilizar proxy como benefício humano |
| [ground_truth_policy.py](../../src/experiment/ground_truth_policy.py), auditoria/validação/value policy | Rastreabilidade de confiança, fonte, equivalência e emendas | Política histórica exige valor concreto e inclui hipótese `low/probable`; não representa diretamente U/T/G do novo gabarito |
| [gt_extractor.py](../../src/experiment/gt_extractor.py), [mask_extractor.py](../../src/experiment/mask_extractor.py) | Conhecimento das entradas/transformações históricas | Extração do valor original não ratifica verdade; remoção artificial não entra na primeira etapa M7 |
| [execution_identity.py](../../src/experiment/execution_identity.py), [model_lock.py](../../src/experiment/model_lock.py), [evidence_bundle.py](../../src/experiment/evidence_bundle.py) | Identidade canônica, locks e manifestos | Acrescentar corpus/split, receitas, evidências, granularidade, métricas e protocolo por adaptação versionada |
| [environment.py](../../src/experiment/environment.py), inventário/runtime Windows | Captura de ambiente e residência | Presença de GPU/residência não é pico de VRAM; caminhos de instalação/benchmark podem baixar/gerar, fora desta tarefa |
| [config.py](../../src/config.py) e lock atual | Default qwen3.5:9b, `fixed=4096`, teto `fit=8192`, saída 768, seed 42, temperatura 0,1, concorrência 1 | Configuração de código lida, não snapshot de runtime nem recomendação de vencedor/limite universal |
| [EvaluationSuite](../../src/foundation/contracts.py) | Fronteira `evaluate(issues)` | Protocolo mínimo não implementa a arquitetura científica proposta |
| [tests/evaluation](../../tests/evaluation/), [tests/experiment](../../tests/experiment/) | Regressões e contratos existentes a selecionar na implementação | Leitura estática não equivale à execução nem prova cobertura M7 |

O [protocolo histórico de métricas](../metricas-avaliacao.md), a [emenda de GT](../emenda-gt-2026-08-12.md), as condições [v7.7](../condicao-v7-7-2026-08-13.md), [escala](../condicao-escala-4070-2026-08-16.md), [ablação bSDD](../condicao-ablacao-bsdd-2026-08-18.md) e [v7.8](../condicao-v7-8-2026-08-19.md) permanecem instrumentos históricos. Não copiar suas conclusões, tolerâncias ou hipóteses como verdade do novo orçamento.

### 2.3 Política de reaproveitamento

Classificar cada artefato como: referência histórica; entrada reavaliável; medição comparável sob contrato integral; ou comparabilidade insuficiente. Para comparar, conferir caso/linhagem/split, hash IFC/IDS/GT, catálogo/receita, evidência enviada, prompt/schema/comparador, tag/digest/quantização, runtime/equipamento, parâmetros, cache/reuso e definição da métrica. Uma divergência não declarada impede agrupar como réplica.

Reutilizar bytes de respostas para nova análise exige adequação da saída à nova rubrica, versão separada da análise e explicação de que não houve nova inferência. Sem evidência enviada recuperável, não certificar sustentação retroativamente. Repetir apenas lacunas necessárias ao recorte de orçamento, justificadas por campo/condição. Preservar originais e resultados negativos; nunca reescrever `run_0.json` para fazer a nova rodada parecer histórica.

<a id="m7-perguntas"></a>

## 3. Perguntas, estimandos e interpretação prevista

| Pergunta | Efeito a estimar | Unidade/cuidado |
|---|---|---|
| Q1 — Recuperação | Qual evidência pertinente é encontrada e associada corretamente ao campo/componente? | Evidência/campo, antes da LLM; extração, busca e seleção com medidas separadas |
| Q2 — Enriquecimento | Qual ganho ou dano de acrescentar LLM às mesmas regras e de preparar contexto por propriedade? | Diferença pareada de correção sustentada, falso preenchimento, abstenção e cobertura no mesmo conjunto |
| Q3 — Organização/chamadas | Como elemento/propriedade e contexto básico/preparado mudam qualidade por campo e custo total? | Fatorial com modelos/casos iguais; preparação e chamadas compartilhadas contabilizadas |
| Q4 — Modelos/recursos | Em que propriedades/grupos cada configuração é útil e viável? | Configuração completa, estratos e casos reservados; número de parâmetros não determina superioridade |
| Q5 — Pessoas, secundária | Sugestões mudam tempo, consultas, correções e erros finais? | Participante/tarefa/caso, com contrabalanço e julgamento final independente |

Hipóteses de trabalho: preparação pode aumentar a recuperação e a qualidade sustentada, mas também introduzir ruído, associação indevida ou custo; LLM pode ajudar apenas campos residuais interpretativos; granularidade pode melhorar um campo e piorar tempo/outros campos. São resultados válidos ganho nulo, dano, empate inconclusivo ou utilidade limitada. O protocolo não presume vencedor.

Cinco focos de revisão: valor correto por coincidência sem evidência (T7-10/11); evidência do componente errado (T7-07/08); vazamento por revisão/tipo repetido (T7-03/04); ganho de coleta atribuído à LLM (T7-15/16); truncamento/falha/cancelamento excluído do denominador (T7-20/21/22). Cada foco tem responsável nas tarefas e oráculo na seção 16.

<a id="m7-arquitetura"></a>

## 4. Arquitetura de avaliação e organização futura

```text
Corpus real + fontes imutáveis + manifesto de exposição
          → grupos/partições → gabarito BIM e evidências revisados (área separada)
          → diagnóstico M2 → mesmas regras M3 → pacotes básico/preparado
          → condições fixadas → CallPlan → fila serial M6 → resultados por campo
          → julgamento cego + métricas de recuperação/sugestão + recursos
          → análise por propriedade/categoria/modelo → confirmação reservada
          → recomendação versionada para política M3
Secundário: casos distintos equivalentes → tarefa manual/assistida M4 → erros finais
```

O armazenamento da pesquisa fica sob diretório local de dados configurado por M6, separado por projeto. O namespace lógico `research/M7/<round_id>/` contém `protocol/`, `corpus/`, `gold/`, `inputs/`, `attempts/`, `outcomes/`, `analysis/` e `reports/`. São **caminhos futuros relativos à área operacional**, não diretórios criados nesta entrega. Gabarito/adjudicação nunca entram no índice/contexto disponível ao executor; separar arquivos e interfaces, sem prometer segurança de contas inexistentes no MVP.

| Área futura de código | Responsabilidade | Dono da integração |
|---|---|---|
| `src/experiment/budget_v1/contracts.py` | Objetos M7, validação documental e migração explícita do legado | Nonato |
| `corpus.py`, `gold.py` no mesmo pacote | Manifestos, grupos, partições, revisão e adjudicação | Nonato + Felipe |
| `conditions.py`, `orchestrator.py` | Congelamento, expansão do desenho, adaptadores M2/M3/M6 | Nonato + Felipe |
| `evidence_metrics.py`, `field_metrics.py` | Recuperação, suficiência, sustentação, abstenção e denominadores | Nonato + Felipe |
| `analysis.py`, `reporting.py` | Comparações pareadas, incerteza, matriz, rastreio e relatório | Nonato |
| `human_study.py` | Eventos e análise do estudo secundário quando autorizado | Nonato |
| `tests/experiment/budget_v1/` | Contratos, fixtures sintéticas de software e regressões da nova condição | Nonato + Felipe |

Arquivos do produto serão modificados somente pelos donos das respectivas capacidades, em etapa posterior autorizada. M7 não duplica extrator, catálogo, scheduler, UI ou writer. Fixtures sintéticas de teste de software validam contratos, sem serem apresentadas como casos científicos reais.

<a id="m7-contratos"></a>

## 5. Contratos, identidade e reconciliação M1–M6

### 5.1 Objetos de pesquisa propostos

Usar `SourceArtifactRef`, `AnalysisIdentity`, `ElementRef`, `RequirementResult`, `DiagnosticSnapshot` e `TypedValue` de M2; `FieldRef`, `EvidenceAssessment`, `ElementContextPackage`, `CallPlan`, `FieldAlternative` e `RoutingPolicyRef` de M3. `PairRef` é o vínculo `ModelPairBinding` M4, não nova associação. Projeto + modelo lógico + revisão/hash + express ID identifica o alvo; GUID é adicional e validado. Não usar nome, STEP ID ou GUID isolado entre arquivos/revisões.

| Registro M7 | Conteúdo mínimo | Invariante |
|---|---|---|
| `StudyProtocol` | protocol_id/revisão/hash, perguntas/estimandos, escopo, métricas, análise, regras de parada/repetição, responsáveis, registro com orientador | Mudança após inspeção do teste final gera emenda e limita confirmação |
| `CorpusCase` | case_id, projeto/linhagem/grupo, PairRef, AnalysisIdentity, ElementRef/FieldRef, fonte Daiane, pendência real, elegibilidade/motivo, exposição prévia | Caso é campo de elemento na revisão exata; requisito sem elemento mantém escopo próprio |
| `SplitManifest` | grupos, atribuição desenvolvimento/seleção/final, seed de divisão se usada, autor/data/hash, verificações de interseção | Arquivos/revisões/duplicatas/tipos relacionados do mesmo edifício ficam juntos |
| `GoldCase` | caso/versão, valor ou alternativas tipadas, unidades/tolerâncias justificadas, fontes, conjuntos suficientes de evidência, D/U/T/G, conflitos, aplicabilidade e ação esperada | Valor esperado não vira evidência enviada; alteração conserva histórico/adjudicação |
| `EvidenceReference` | observation_id/hash, revisão, caminho/portador/componente/papel, conteúdo, unidade, associação e transformação permitida | Referência deve ser resolvível e pertinente; existência do ID não prova validade |
| `ConditionManifest` | braço, corpus/split/GT/receitas/regras/contexto/schema/comparador, modelos/digests/configurações, hardware, repetições, cache, seeds, retries, budgets | Participantes e opções não mudam no meio da rodada |
| `EvidenceExposure` | universo observado, seleção enviada por campo/chamada, fatos/IDs/hash, rejeições/omissões/motivos, limites e tokens | Distingue informação disponível, recuperada e efetivamente enviada |
| `EvaluationAttempt` | round/condition/case/model/repetition, M6 job/attempt/retry_of, CallPlan, entradas/respostas brutas locais, tempos/recursos/status | Retry não é nova observação independente; tentativa incompleta permanece |
| `FieldOutcome` | FieldRef, resultado regra/LLM, alternativas, decisão principal, correção/sustentação/associação, abstenção, conflito/requisito, erro e julgamento | Um campo com múltiplos requisitos não é contado várias vezes como sucesso |
| `AnalysisManifest` | hashes dos dados/metodologia/código, inclusões/exclusões, agregações/pesos, intervalos/testes e desvios | Toda célula pode voltar aos casos, chamadas e evidências |
| `ModelProspectionRecord` | fonte primária/data, licença, tag/revisão/digest, quantização, contexto, memória, runtime, hardware-alvo, triagem/decisão/rodada | Instalado, testado e selecionado são estados distintos |
| `RoutingRecommendation` | propriedade/grupo, modelos elegíveis, critérios/trocas qualidade-recursos, incerteza, condição e confirmação reservada | Ausência de evidência mantém política conservadora; não altera M3 automaticamente |

Estados de rodada: `draft`, `frozen`, `running`, `partial`, `completed`, `invalidated`, `archived`. `completed` significa unidades previstas contabilizadas, inclusive falhas; não significa hipótese confirmada. `invalidated` conserva tudo com motivo. Estado de job M6, estado IDS M2, suficiência D/U/T/G, saída M3 e decisão M4 são eixos diferentes.

### 5.2 Sete fronteiras e seus critérios

| Fronteira | M7 recebe | M7 devolve / critério | Responsáveis |
|---|---|---|---|
| M1 — catálogo | Pin/release/hash, fonte/registro Daiane, binding, política e capacidade | Lacunas/ambiguidade e cobertura, sem publicar equivalência; conceito não é valor do IFC | Felipe + Nonato |
| M2 — diagnóstico | Snapshot exato, observações, aplicabilidade, cinco estados, verificador/schema/capacidade | Corpus de pendências reais e achados de extração/validação; sem mutar original nem confundir erro com não conforme | Felipe + Nonato |
| M3 — contexto/LLM | Regras/receitas, pacotes, seleção/omissão, CallPlan, alternativas/abstenção e identidade | Condições pareadas, erros por etapa e recomendação de roteamento versionada; mesmos fatos quando o contraste exigir | Felipe + Nonato |
| M4 — revisão | Eventos locais e recibos da tarefa, escolhas/edições/consultas/pausas, contexto exibido | Roteiro do estudo secundário e análise de uso; nome declarado não vira identidade autenticada | Nonato; Felipe apoia domínio |
| M5 — saídas | Recibos de aplicação, arquivo salvo/reaberto, revalidação e deltas/BCF | Separação entre sugestão, aceitação, gravação e resolução; conformidade formal não substitui julgamento de engenharia | Felipe + Nonato |
| M6 — operação | RuntimeManifest, LocalActorContext, JobRecord/AttemptRecord/checkpoints, recursos, backup e limites | Perfil de ensaio/calibração, métricas e capacidade por equipamento; uma inferência por instalação, sem contexto entre projetos | Nonato |
| M7 — pesquisa | Protocolo, corpus/gabarito, resultados e prospecção sob versões próprias | Pacote reproduzível, matriz/relatório e recomendações; conclusão compatível com alcance dos dados | Nonato; Felipe e especialistas no gabarito |

### 5.3 Precedência e divergências resolvidas no M7

| ID | Texto anterior / risco de integração | Regra adotada aqui |
|---|---|---|
| I7-01 | Responsáveis antigos em M1/mapa | Nonato lidera M7 e prospecção; Felipe M1/M2/M3/M5 e auxílio BIM em M7 |
| I7-02 | M1/M2 descrevem federação como extra | Decisão posterior M4: dois pares no MVP; sem evidência cruzada; agrupá-los pelo edifício para split |
| I7-03 | M4/M5 e trechos M2/M3 esperam principal/ACL | M6 final: `LocalActorContext`, `identity_assurance=unverified_local`; autenticação antes da rede IME |
| I7-04 | M3 §14 propõe retirada de evidência/contrafactuais | D7-07 prevalece para o núcleo científico inicial: pendências reais; transformações artificiais ficam extensão e testes de contrato |
| I7-05 | M3 chama agrupamento/contexto de ablação secundária | D7-04/05 tornam contexto e granularidade comparações do núcleo M7; estudo humano permanece secundário |
| I7-06 | R/R+L M3 exige evidência equivalente; básico/preparado pode mudar fatos | Manter R básico/preparado e controles equivalentes; decompor ganho de recuperação e organização |
| I7-07 | GT histórico requer resposta concreta/hipótese provável | Novo GT aceita D/U/T/G e abstenção; preserva GT antigo sem conversão automática |
| I7-08 | M6 inventaria legado com defaults e filas em memória | Manifestos/custos e persistência durável são contratos a implementar; defaults não são limites medidos para orçamento |
| I7-09 | Pesquisa preliminar de novos modelos ocorre na conversa principal | Não incorporada neste plano como decisão, seleção ou ensaio; registro externo futuro exige fonte/triagem |

M6 final foi reconciliado também quanto a backup: pacote de pesquisa deve referenciar dados/versões/restauração; guardar somente hash de um peso sem manter forma autorizada de recuperá-lo limita reprodução. Pesos opcionais no backup e compartilhados na instalação; não duplicar por projeto. Reabrir/restaurar projeto não dispara geração automaticamente.

<a id="m7-corpus"></a>

## 6. Corpus real, cobertura Daiane e partições

### 6.1 Seleção sem lacunas artificiais

Inventariar IFCs/IDSs autorizados e sua origem, finalidade, disciplina, edifício, revisões, schema e histórico de uso. M2 produz diagnóstico completo; selecionar pendências reais, inclusive propriedade ausente no caminho exigido mas com evidência em outro local. Confirmar a necessidade do requisito e excluir como preenchimento os requisitos inadequados, mantendo-os no estrato de revisão. Não remover campos, ocultar nomes ou criar dano ao IFC para produzir casos na primeira etapa.

Guardar fluxo de inclusão: arquivos disponíveis → legíveis → requisitos suportados/aplicáveis → pendências reais → campos únicos → campos revisados D/U/T/G → campos selecionados em cada split. Toda exclusão traz motivo e contagem por categoria. Requisito sem elementos, não suportado ou não aplicável aparece no relatório, sem virar sugestão fictícia.

### 6.2 Dez categorias e matriz inicial

A fonte operacional documental é a matriz canônica M3 `2026-10-12-r2`: 203 registros alfanuméricos + 110 auxiliares. Essa contagem atual substitui, para planejamento de cobertura, as 195 entradas relatadas no levantamento anterior M1; não transforma registros de fonte em 203 conceitos únicos nem em casos existentes. O XML original das dez especificações e a planilha editável continuam dependências de curadoria, conforme M1/M3; o pacote público `Cost_Prop` não substitui silenciosamente `EB_Orçamento`.

| Família | Registros alfanuméricos + auxiliares | Verificação científica principal por propriedade |
|---|---:|---|
| A1 — Janela / IfcWindow | 24 + 11 | Vidro versus caixilho/peitoril; dimensões do vão versus marco; material e associação fills/voids |
| A2 — Porta / IfcDoor | 28 + 11 | Folha/marco/ferragens, OperationType, dimensões e unidade de Densidade_Porta |
| A3 — Parede / IfcWall | 26 + 11 | Sistema/camadas, função portante declarada, material e relação; pilares no edifício não provam função da parede |
| A4 — Forro / IfcCovering CEILING | 22 + 11 | Suspensão/material/suporte; divergência literal de Pset na fonte exige revisão |
| A5 — Piso / IfcCovering FLOORING | 19 + 11 | Acabamento/camadas, área líquida e consumo; bounding box não prova quantidade real |
| A6 — Revestimento / IfcCovering CLADDING | 24 + 11 | Papel da camada e associação ao hospedeiro; classe/código fonte preservados |
| A7 — Laje / IfcSlab FLOOR | 18 + 11 | Volume/espessura/material/fôrma; área de piso não é área de fôrma |
| A8 — Pilar / IfcColumn | 16 + 11 | Perfil/seção/concreto/fôrma/Qto e material; não transferir peso para barras |
| A9 — Viga / IfcBeam | 17 + 11 | Seção/eixo/comprimento; dimensão global não substitui seção rotacionada |
| A10 — Armadura / IfcReinforcingBar | 9 + 11 | Diâmetro/comprimento/massa, multiplicidade e representação de conjunto |

A [matriz MODELOS × PROPRIEDADES](../pesquisa/modulo-07-avaliacao/matriz-modelos-propriedades.csv) contém uma linha para cada um dos 313 registros, com ID, categoria, propriedade/campo literal, Pset, página, receita e elegibilidade LLM **proposta** em M3. Colunas R e 21 tags históricas são um quadro inicial de rastreio, **não seleção obrigatória de 21 modelos**. Todas as células estão `nao_avaliado_M7`, campos novos avaliados = 0 e quantidade de casos reais = `nao_inventariado`; zero ensaios novos não significa zero pendências no IFC.

Após seleção, o formato analítico longo terá chave `(round_id, condition_id, model_digest ou R, property_id/binding/papel, family_id, split, hardware_profile)`, contagens N/D/U/T/G, erros, correção, sustentação, abstenção, recursos e links aos casos. Gerar a visão cruzada da mesma base, sem planilhas independentes. Mostrar todas as propriedades, inclusive sem casos, gabarito pendente, sem operação ou insuficientes; não preencher métricas vazias com zero ou 100%. Auxiliares documentais/geometria não viram exigência de multimodalidade ou ingestão documental no MVP.

Estratificar fatos explícitos, dispersos, conflitantes e ausentes; essas etiquetas descrevem evidência e podem coexistir (dispersa e conflitante). D/U/T/G é outro eixo, não sinônimo desses rótulos. Caso real não disponível em algum estrato gera lacuna explícita, não fixture artificial para completar a tabela científica.

### 6.3 Separação desenvolvimento, seleção e confirmação

1. Construir grafo de parentesco por projeto/edifício, modelos de disciplinas do mesmo edifício, revisões/exportações, hashes iguais, famílias/tipos repetidos e variantes de um caso. Componentes conectados formam grupos indivisíveis. Mesmo nome de classe genérica em projetos distintos não basta para fundi-los; um template copiado com valores/casos exige exame de linhagem.
2. **Desenvolvimento:** casa/prédio já expostos, fixtures de software e outros casos identificados; aqui ajustar receitas, prompts, comparadores e esquema. **Seleção/piloto:** grupos distintos quando disponíveis para triagem de modelos, repetições, budgets e política. **Final reservado:** grupos não usados em nenhum ajuste/seleção, com lista/hash e acesso aos gabaritos separado do executor.
3. Não dividir instâncias de um tipo entre treino/ajuste e teste; não declarar revisão nova do mesmo edifício como projeto novo. Repetições de inferência preservam o grupo do caso. Casa/prédio não ganham independência por estar em duas pastas ou hardware diferente.
4. Se o corpus não permitir três conjuntos independentes, declarar estudo exploratório com validação interna agrupada, quando viável, e obter outros projetos antes de confirmação externa. Não usar o mesmo reservado para escolher e provar o roteamento. Avaliação final pode permanecer pendente sem bloquear a entrega documental.
5. Registrar quem viu quais dados e quando. Congelar split antes da seleção; registrar qualquer exposição acidental. Nova análise posterior ao resultado é exploratória, ainda que código esteja perfeito.

<a id="m7-gabarito"></a>

## 7. Gabarito, evidências e julgamento

Cada campo exige: identidade exata, requisito/versão e adequação, significado/papel, valor ou alternativas aceitáveis quando determinável, tipo/unidade, tolerância com justificativa BIM, evidências aplicáveis e conjuntos suficientes, conflitos, informação faltante, transformações permitidas, ação esperada (propor, abster, pedir esclarecimento ou revisar requisito), revisor/data e adjudicação. Valores de IFC são observações, sujeitos a erro e conflito; outra LLM pode ajudar a organizar rascunho, nunca ratificar a verdade.

| Estado de referência | Regra | Julgamento |
|---|---|---|
| D — determinável no universo de evidência permitido | Há pelo menos um conjunto suficiente para resposta fundamentada | Recuperação pode falhar; isso não converte D em U para favorecer o sistema |
| U — indeterminado | Falta informação, associação ou decisão; conflito não resolvível no universo permitido | Esperar abstenção/esclarecimento, com motivo; acerto por sorte continua sem suporte |
| T — não avaliável tecnicamente | Fonte/operação indispensável ilegível/sem suporte impede o oráculo técnico | Reportar barreira e capacidade; não premiar como abstenção de domínio |
| G — gabarito pendente | Especialista ainda não consegue julgar de forma independente | Fora da correção semântica, dentro do inventário operacional, com motivo |

O estado é definido em relação ao universo permitido da condição. Na comparação IFC sozinho, conhecimento externo do especialista pode justificar que existe resposta real, mas não que o sistema a poderia inferir. Para os braços básico/preparado, manter um oráculo do universo IFC comum e registrar também a suficiência do pacote efetivamente enviado. Assim é possível identificar **falha de recuperação em D** e ao mesmo tempo reconhecer uma recusa responsável diante de pacote insuficiente. Não transformar essa recusa em recuperação bem-sucedida nem classificar saída não sustentada como acerto.

A evidência de referência inclui conjuntos alternativos suficientes: não exigir simultaneamente todos os caminhos equivalentes para contar recuperação. Anotar granularidade (fato/caminho/trecho), validade, pertinência, portador, papel/componente e relação com o alvo. Informação explícita de material da folha não autoriza material do marco. Exigência IDS e definição bSDD têm papel de requisito/semântica, não evidência observacional do componente.

Fluxo futuro: Felipe prepara rubrica e casos → revisor BIM verifica sem ver modelo/braço/confiança LLM → segundo especialista revisa amostra estratificada ou conjunto integral conforme viabilidade → divergências conservadas e adjudicadas por regra documentada. Priorizar dupla revisão dos conflitos, falsos preenchimentos e casos que alteram conclusão. Se só houver um revisor, rotular referência com revisão única e limitar validade; não inventar consenso. Quantidade e disponibilidade de especialistas são gates da coleta.

Tolerâncias não vêm automaticamente de `DEFAULT_FLOAT_TOLERANCE`; unidade física equivalente pode ser aceita, mas comparador não completa classe, material ou papel ausente. Zero/falso, string vazia, nulo, ausente e placeholder são distintos. Corrigir erro do gabarito após resultados exige emenda, registro do motivo, análise anterior preservada e avaliação do impacto em todos os braços, sem escolher correções favoráveis a um modelo.

<a id="m7-condicoes"></a>

## 8. Desenho das comparações: regras, contexto e chamadas

### 8.1 Regras fortes e contexto básico/preparado

Congelar as mesmas regras determinísticas nos braços: leitura exata, herança válida, bindings/aliases curados, normalização/conversão e cálculos sustentados. Regras não são reduzidas a baseline propositalmente fraco. Campos resolvidos por regras não exigem LLM na operação; o subconjunto residual é fixado pelo mesmo resultado determinístico antes de comparar elemento/propriedade. Manter todos os campos na contabilidade do fluxo, mesmo quando nenhum chama LLM.

`E_B` é o pacote básico padronizado: seleção fixa por versão de atributos/contexto comum, requisito, semântica e evidências, com política explícita; não significa prompt vazio nem escolha ad hoc por modelo. `E_P` é o pacote preparado por propriedade, seguindo receitas/canais/associações M3. Em ambos guardar universo observado, fatos selecionados, rejeitados/omitidos e sua causa. Extração e fatos disponíveis podem diferir; o contraste de ponta a ponta mede a combinação de recuperação e apresentação, sem atribuir todo ganho à LLM.

| Braço | Determinístico | LLM e pacote | Uso |
|---|---|---|---|
| R-B | Regras fixas sobre E_B | Sem chamada | Baseline correspondente ao contexto básico |
| L-B-E | Mesmas regras de R-B | E_B, uma chamada por elemento reunindo pendências residuais | Referência LLM/contexto básico padronizado |
| L-B-P | Mesmas regras de R-B | Mesmo E_B completo em cada chamada, uma por propriedade residual | Efeito da divisão das perguntas sem filtragem por campo |
| R-P | Regras fixas sobre E_P | Sem chamada | Baseline forte correspondente à recuperação preparada |
| L-P-E | Mesmas regras de R-P | Comum + blocos preparados de todos os campos residuais, uma chamada por elemento | Contexto preparado com agrupamento |
| L-P-P | Mesmas regras de R-P | Comum + bloco preparado do campo, uma chamada por propriedade residual | Contexto preparado com filtragem por campo |

Para isolar **só granularidade** no contexto preparado, acrescentar controle L-P-P-U: uma chamada por propriedade recebendo a **mesma união integral de E_P** que L-P-E. Contrastar L-P-E × L-P-P-U (perguntas) e L-P-P-U × L-P-P (filtragem). L-B-E × L-B-P já controla granularidade com E_B igual. Não concluir efeito puro de divisão comparando apenas L-P-E e L-P-P.

As condições R-B e R-P usam o mesmo algoritmo/regras; a diferença é evidência disponível. O contraste L-B − R-B e L-P − R-P identifica o acréscimo da LLM dentro de cada preparação. O contraste R-P − R-B mostra efeito determinístico da recuperação. Fixar elegibilidade residual por nível de evidência; quando R-P resolver campos adicionais, informar que o número de chamadas caiu por contribuição determinística, não por modelo melhor.

### 8.2 Mesmas evidências para isolar organização/interpretação

Quando viável, congelar um pacote factual comum `E*` com mesmas observações, relações, unidades e semântica. Serializar como bloco básico e como blocos organizados por propriedade, preservando fatos e referências; diferença de tokenização/ordem permanece registrada. Comparar R(E*) e L(E*) para contribuição interpretativa; comparar formas de L(E*) para organização. O gabarito, rótulo correto e notas de adjudicação não entram em E*. Um pacote factual revisado também pode isolar falha do extrator.

Se E* não couber em determinada configuração, não truncar silenciosamente. Registrar inviabilidade, omissões e conjunto comparável. A análise de subgrupo que cabe usa o mesmo subconjunto para todos os braços e mostra sua fração do corpus; análise operacional integral mantém os casos limitados. Não enfraquecer R para caber na LLM: relatar também regras sobre toda evidência admissível como baseline forte.

### 8.3 Controle de custo e de múltiplos campos

Mesmos casos, modelos/digests, instrução de tarefa, regras, schema e critérios nos contrastes; variar apenas o fator identificado. A ordem das condições/modelos é randomizada ou contrabalançada em blocos viáveis por custo de carregamento, com sequência registrada. O baseline serial M6 vale em todos os braços. Compartilhar preparação por elemento é permitido se a política for igual e seu custo contabilizado; reportar custo frio e amortizado, sem cobrar coleta compartilhada uma vez por campo artificialmente.

Uma chamada de elemento retorna status por campo; JSON parcialmente útil não apaga campos inválidos/omitidos. Conflito em um campo não autoriza completar os outros por analogia. A estratégia por propriedade continua serial e paga suas múltiplas chamadas, overhead e repetições do contexto. Agrupamento intermediário por grupos pode ser extensão de desenvolvimento; não substitui a comparação elemento versus propriedade aprovada.

<a id="m7-metricas"></a>

## 9. Métricas, denominadores e atribuição de erro

`N` = campos únicos selecionados da população operacional, com `N = D + U + T + G`. `E = D + U` é a população semanticamente julgável. Em E, particionar saída terminal em `P` (proposta), `A` (abstenção de domínio válida), `F` (falha técnica/saída inválida) e `I` (incompleto/cancelado/não executado), de modo que `E = P + A + F + I`. Proposta acompanhada de aviso ainda é P se oferece valor utilizável. Emissão parcial inválida pode ser F e conservar sugestões indevidas para auditoria de risco.

`C` = campos D cuja proposta principal é tecnicamente correta **e** sustentada por evidência válida associada ao componente. `P_N` conta campos propostos em N; propostas em T/G são reportadas separadamente. Alternativas têm unidade própria: uma correta não apaga outra sem fundamento. Métrica por requisito IDS conserva denominador formal separado do campo.

| Métrica | Numerador / denominador ou medida | Observação |
|---|---|---|
| Precisão de recuperação | Fatos recuperados pertinentes e associados corretamente / fatos recuperados julgados | Duplicatas do mesmo fato não inflacionam; reportar não julgados |
| Recall de evidência | Fatos pertinentes recuperados / fatos pertinentes anotados no universo auditado | Se referência não exaustiva, chamar recall relativo à referência, não recall universal |
| Suficiência recuperada | Campos D com ao menos um conjunto suficiente recuperado / D | Complementa recall quando existem conjuntos alternativos de prova |
| Suficiência enviada | Campos D com conjunto suficiente efetivamente no prompt / D | Separa extração/recuperação de perda no empacotamento |
| Validade e associação | Citações resolvíveis, revisão/papel/alvo corretos e admissíveis / citações emitidas | Separar existência, pertinência, associação e suficiência |
| Correção técnica top-1 | Propostas principais com valor/ação aceitável / propostas julgáveis | Exibir também sustentação; igualdade isolada não vira C |
| Precisão sustentada | C / P | Cobertura baixa pode produzir precisão alta; publicar conjuntamente |
| Recuperação sustentada em D | C / D | Abstenção, erro e cancelamento em D não saem do denominador |
| Cobertura de proposta | P/E e P_N/N | Exibir parcelas em T/G; preencher mais não implica qualidade |
| Cobertura operacional | Campos concluídos por método/estado / N | Separar regra, LLM, abstenção, erro, limite e não executado |
| Sugestão sem fundamento | Campos com principal sem suporte / P; e alternativas sem suporte / alternativas emitidas | Separar valor incorreto, falta de suporte e interseção |
| Falso preenchimento em U | Campos U com qualquer alternativa de valor / U | Mesmo valor coincidente por sorte é falso preenchimento relativo à evidência permitida |
| Abstenção correta | U com abstenção/esclarecimento compatível com GT / U | Timeout, modelo ausente e JSON quebrado não contam |
| Abstenção indevida | D com abstenção / D | Separar pacote insuficiente por falha de busca de recusa apesar de evidência enviada suficiente |
| Conflitos | Precisão/recall da identificação e ações adequadas nos conflitos anotados | Valor escolhido sem fundamento é erro, mesmo se formalmente permitido |
| Requisito inadequado | Acertos de encaminhamento / casos anotados inadequados, e falsos alarmes / adequados | Não premiar alteração de fato legítimo para satisfazer IDS |
| Estrutura/estabilidade | Respostas válidas por tentativa, campos válidos por solicitados; variação entre repetições | Antes/depois de reparos; stop reason, chaves omitidas e duplicadas |
| Tempo | Extração, recuperação, seleção, fila, carga, inferência, parsing/validação, persistência e fluxo total | Relógio monotônico; UTC para correlação; mediana, cauda e dispersão quando sustentadas |
| Recursos | Pico RAM/VRAM, residência/offload, tokens, chamadas, retries, disco e falhas | Método/frequência de amostragem e metadados ausentes explícitos |
| Uso humano, secundário | Tempo ativo/total, consultas, edições, rejeições, correções e erros finais por tarefa | Aceitação não comprova correção; análise antes/depois separada |

Denominador zero = `não aplicável` com contagem, nunca 100%. Contagem desconhecida = `não medido`, não zero. Publicar por propriedade/binding/papel, família, D/U/T/G, regime de evidência, schema/capacidade, modelo/configuração e equipamento. Microagregação conta campos; macroagregação dá pesos declarados às propriedades/famílias representadas e informa ausentes. Não diluir problema de armadura em milhares de atributos simples.

Taxonomia de erro com rótulos múltiplos e causa primária adjudicada: fonte ilegível; requisito/aplicabilidade inadequado; mapping; extração; associação; recuperação; seleção/omissão; limite de contexto; geração; parse/tipo/unidade; evidência inexistente; revisão humana; escrita/revalidação. Guardar estágios e interseções, sem inferir causalidade apenas da resposta final. A revalidação IDS mede conformidade computável, em coluna própria.

<a id="m7-execucao"></a>

## 10. Protocolo reproduzível e instrumentação

O [caderno operacional](../pesquisa/modulo-07-avaliacao/protocolo-e-registros.md) detalha campos de registro e gates. Sua execução é futura. Antes de qualquer rodada, Nonato congela protocolo, corpus/split, GT revisado, condições, lista de modelos e configurações; Felipe confere critérios BIM e ausência de vazamento. O manifesto aponta bytes exatos, não somente caminhos locais mutáveis.

Registrar por modelo: produtor/repositório e revisão, tag/digest completo, arquitetura/quantização, tokenizer/chat template, licença e runtime suportado. Por condição: `num_ctx` solicitado e efetivo observável, política de contexto, saída máxima, temperatura, top_p, repeat_penalty, seed suportada/enviada, think, keep_alive, timeout/retries e schema. Metadado desconhecido permanece desconhecido. Não supor que a mesma seed produz determinismo entre modelos, versões ou GPUs.

Por equipamento: CPU, GPU(s), VRAM física/disponível, RAM, driver/OS, versão Ollama/Python/bibliotecas/build/locks, disco, processos concorrentes relevantes e configuração de offload. Medir em cada instalação elegível; computadores históricos RTX 4070/4060/5050 não comprovam hardware atualmente disponível nem capacidade do servidor IME. Não comparar velocidade entre máquinas como se fosse efeito apenas de modelo/contexto.

Piloto em desenvolvimento/seleção estima variação de respostas, falhas, tempo/memória e custo por condição. Antes do final, registrar número de repetições e justificativa pela estabilidade/precisão desejada e recursos, seeds/ordem, regra de parada, intervalo de incerteza, tratamento de falhas e contrastes primários. **Não há número de repetições, limiar de qualidade, SLA ou quantidade de participantes inventados neste plano.** Se recursos só permitirem uma execução, reportar essa limitação e não estimar variabilidade estocástica inexistente.

Tempos: `t_fluxo` é início do preparo até resultado persistido de todo o escopo; `t_fila` separado; carga fria e estado aquecido registrados; preparação compartilhada não é recontada por campo. Tempos Ollama disponíveis complementam relógio do fluxo, sem presumir que cada campo do servidor corresponde a inferência pura. Distinguir geração real, cache e reuso de equivalente. Na comparação causal de chamadas, evitar reuso que altere número real de gerações; se uma otimização for avaliada, fazê-lo em condição identificada com número de estímulos únicos e campos beneficiados.

M6 reserva slot global também para aquecimento e retries. Guardar prompt exato/contexto/hash, resposta bruta, stop reason, tokens estimados/efetivos quando expostos, falhas e reparos. Fonte original íntegra; seleção/omissão declarada. Se evidência mínima não couber, status de limite e pendência; nunca truncamento silencioso. Cancelamento preserva concluídos, tentativa interrompida, unidades restantes e relação de retomada. Não reclassificar a melhor tentativa como primeira nem descartar timeouts para melhorar média.

Backup/restauração da pesquisa usa M6: corpus e permissões de uso, GT, protocolos, manifestos, contextos/respostas, resultados, análise e dependências fixadas; pesos conforme política e licença. A execução não libera IFC corrigido automaticamente. Exportação técnica de M5 e julgamento científico são entregas separadas.

<a id="m7-analise"></a>

## 11. Análise, incerteza e recomendação de modelos

Primeiro publicar contagens e perdas por grupo e condição; depois diferenças pareadas, erros representativos e custos. Unidade primária operacional é campo; inferência estatística respeita grupos de projeto/edifício/tipo e estímulos compartilhados. Repetir chamada reduz incerteza sobre aleatoriedade do runtime, não aumenta número de projetos independentes. Quando reuso existir, cópias de resposta têm um estímulo, com peso operacional explicitado.

O protocolo escolherá antes do final:

- Com grupos independentes suficientes para o desenho, intervalos por reamostragem agrupada ou modelo hierárquico justificado, mantendo campos e repetições dentro do grupo. Documentar unidade de reamostragem, nível e número de reamostragens escolhidos no piloto.
- Com poucos projetos, contagens, diferenças pareadas observadas, variação entre casos/tipos e análise de sensibilidade; inferência restrita ao estudo de caso. Não usar milhares de elementos correlacionados para fabricar significância.
- Para desfecho binário pareado, teste exato como McNemar somente se a unidade e suas premissas forem adequadas; a função legada não autoriza tratar campos dependentes como independentes. Para tempos, diferenças/razões pareadas com estado frio/aquecido e custo total; método fixado pela distribuição observada no piloto.
- Definir contrastes primários e família de comparações antes do final; multiplicidade controlada quando houver testes confirmatórios múltiplos. Comparações adicionais por muitas propriedades/modelos são exploratórias e rotuladas.

Não interpretar resultado sem significância como equivalência. Margem de equivalência ou diferença mínima relevante, se usada, precisa de fundamento técnico e registro prévio. Resultados próximos, intervalos largos ou estratos escassos mantêm conclusão inconclusiva; não ordenar modelos como vencedor universal. Relatar robustez a ponderação micro/macro, exclusões e regras de julgamento, sem escolher a variante favorável após ver o resultado.

Roteamento futuro: usar seleção para definir modelos elegíveis por propriedade/grupo, considerando correção sustentada, falso preenchimento, abstenção, falhas, memória e tempo. Uma fronteira de compromissos qualidade/recursos pode ser mais informativa que um escore único. Se usar escore/pesos ou restrições mínimas, defini-los no protocolo com Nonato/Felipe antes do reservado. Confirmar política fixada em casos reservados; se não houver evidência suficiente, recomendar manter regra/abstenção/revisão ou modelo já validado no escopo, sem extrapolar.

Entregar `RoutingRecommendation` a M3-27 como proposta versionada, com cobertura e limites; M6 confere viabilidade local antes de ativação. Falta do modelo escolhido não autoriza fallback silencioso. A seleção de hardware e modelo considera a configuração completa; comparação de gerações/arquiteturas/quantizações distintas não isola somente quantidade de parâmetros.

<a id="m7-humano"></a>

## 12. Estudo secundário de revisão humana

Depende do núcleo e de fluxo M4/M5 estável, disponibilidade de pessoas e enquadramento institucional aplicável acordado com o orientador antes de recrutar/coletar. Registrar finalidade, participação voluntária/consentimento quando aplicável, tratamento local/pseudônimos e uso permitido dos dados. Não há recrutamento ou autorização ética presumida nesta entrega.

Comparar preenchimento/revisão **sem sugestões** e **assistido**, ambos com acesso equivalente ao IFC, requisito, ferramentas e fontes permitidas. Usar conjuntos de casos distintos, pareados por dificuldade (propriedade, suficiência, dispersão/conflito, familiaridade e carga), com ordem contrabalançada entre participantes. Evitar apresentar o mesmo campo nas duas condições à mesma pessoa. Distribuir conjuntos entre pessoas para não confundir dificuldade com assistência; registrar treinamento prévio em exemplos fora da coleta.

Fixar versão/modelo/condição de sugestões. Capturar tempo ativo e total, pausas, consultas à evidência/documentos, correções/edições, aceites/rejeições e erros finais julgados por rubrica independente, além de pendências preservadas. A assistência pode economizar consultas mas induzir erro; medir ambos. Comparador final cego ao braço quando viável. Separar atraso do sistema do tempo de decisão humana.

Análise por participante e caso, com experiência BIM e efeito de ordem declarados; número de tarefas não substitui número de participantes. Poucos participantes produzem **piloto**, sem produtividade geral comprovada. Teste de usabilidade com Felipe/Nonato, logs de protótipo e `review_proxy` não substituem esse estudo. Sua indisponibilidade não impede concluir o núcleo de recuperação/enriquecimento, desde que não se faça alegação de benefício humano.

<a id="m7-prospeccao"></a>

## 13. Prospecção paralela de modelos — Nonato

A prospecção é uma frente de trabalho contínua do projeto, independente da lista congelada de uma rodada. O registro inicial contém apenas os **21 nomes historicamente observados**, sem endosso atual de licença, disponibilidade, adequação ou seleção. A pesquisa preliminar pedida na conversa principal em paralelo não foi incorporada como decisão ou resultado.

| Linha | Primeiro gate | Avaliação necessária |
|---|---|---|
| Computador pessoal | Inventário real da máquina/perfil M6 | RAM/VRAM livres, contexto/saída, residência/offload, latência, disco e compatibilidade; não limitar por rótulo de tamanho arbitrário |
| Modelos maiores / candidato IME | Confirmar servidor, acesso permitido, GPU/VRAM/RAM e concorrência reais | Capacidade por configuração, licença e operação local; rede só após controles M6; não presumir disponibilidade ou superioridade |

Sequência por candidato: referência primária do produtor e licença específica → revisão/tag/digest/quantização/procedência → runtime/tokenizer/formato/contexto declarado → estimativa de recursos com premissas → preflight sem inferência/download → ensaio curto autorizado em desenvolvimento → decisão de incluir/excluir/adiar com motivo → rodada posterior congelada. Contexto máximo anunciado não é contexto utilizável no equipamento; memória dos pesos não inclui todo KV/overhead. Estimativa permanece estimativa até medição.

Triagem curta mede JSON/abstenção/evidência em casos de desenvolvimento representativos, memória/tempo e falhas de execução local. Um bom smoke não certifica qualidade científica. Candidato incompatível não substitui modelo no meio do benchmark; encerrar/invalidar condição afetada ou planejar outra rodada conforme protocolo. Não baixar, treinar, fazer fine-tuning ou criar monitoramento/automação agora.

<a id="m7-extensoes"></a>

## 14. Extensões opcionais e gates acadêmicos

**Documentos externos:** discutir com orientador a utilidade de memoriais descritivos e planilhas de especificação; não ampliar MVP. Se aprovado depois, protocolo próprio compara IFC sozinho e IFC + documentos com mesmas regras/modelos/casos, controle de evidência igual quando possível e baseline de regras para trechos explícitos. Medir extração (inclusive OCR se necessário), recuperação, revisão/data documental, associação ao elemento/componente, conflito entre documentos/IFC, abstenção e ganho final. Gabarito distingue conhecimento externo da informação disponível em cada braço. Ligação futura com M3, sem ingestor automático nesta etapa.

**Lacunas artificiais/contrafactuais:** extensão separada, preservando fonte e linhagem, transformação e oráculo. Não requisito da primeira etapa com pendências reais; não misturar métricas de casos alterados com reais. Testes sintéticos de software podem testar invariantes sem sustentar conclusões científicas.

**Fine-tuning:** opção futura distinta, ainda não aprovada como requisito. Exigiria corpus/licenças, treinamento/validação/teste separados por origem, recursos e comparação com o mesmo modelo sem ajuste. Prospecção não autoriza treino. Modelos multimodais, evidência cruzada entre arquivos e servidor institucional também exigem novos escopos, não surgem por disponibilidade de ferramenta.

<a id="m7-tarefas"></a>

## 15. Tarefas futuras, dependências, responsáveis e aceite

Todas as caixas abaixo estão abertas: representam pesquisa/implementação posteriores. Paths em `research/M7/` são relativos à pasta operacional M6. Cada tarefa produz evidência própria; concluir o plano não marca nenhuma como executada. A implementação deverá ler os planos donos de cada contrato e adaptar o legado sob condição distinta.

### M7-01 — Formalizar recorte e protocolo acadêmico

**Dependências:** pedido aprovado; disponibilidade do orientador. **Responsável:** Nonato, com Felipe.
**Arquivos futuros:** `research/M7/protocol/recorte.md`, `decisoes.json`.
**Entrada → saída:** Q1–Q5, limites e inventário → recorte/protocolo versionados com registro real da discussão.

- [ ] Apresentar núcleo contexto/enriquecimento e estudo humano secundário, corpus disponível e limites de generalização.
- [ ] Registrar perguntas, estimandos, contribuição pretendida e decisões/dependências acadêmicas com data/autor.
- [ ] Delimitar documentos externos/fine-tuning como opções e conferir T7-01/40.

**Aceite:** documento distingue aprovação de Felipe, alinhamento acadêmico realizado e pendências; nenhuma aprovação presumida.

### M7-02 — Consolidar inventário e comparabilidade do legado

**Dependências:** inventário documental desta entrega. **Responsável:** Nonato; Felipe revisa critérios históricos.
**Arquivos futuros:** `research/M7/legacy/inventory.json`, `comparability.csv`; adaptador de leitura em `budget_v1/contracts.py` se necessário.
**Entrada → saída:** runs/ZIPs/locks/condições → mapa de reuso, perdas e repetições necessárias.

- [ ] Validar artefatos/hashes e distinguir run, chamada, cópia equivalente, smoke, instalação e candidato.
- [ ] Classificar comparabilidade por entradas/instrumento/equipamento e justificar o que precisa ser repetido para orçamento.
- [ ] Conferir T7-02/29/30; manter originais imutáveis e separar qualquer reanálise.

**Aceite:** cada modelo testado aponta para artefato; nenhum GT/revisor histórico é promovido automaticamente à nova avaliação.

### M7-03 — Inventariar pendências reais e cobertura por propriedade

**Dependências:** M7-02; M2 diagnóstico/capacidades e M1/M3 matriz. **Responsável:** Felipe, sob coordenação Nonato.
**Arquivos futuros:** `research/M7/corpus/cases.jsonl`, `coverage.csv`; `budget_v1/corpus.py`.
**Entrada → saída:** IFC/IDS reais autorizados → campos/casos e fluxo de inclusão/exclusão.

- [ ] Identificar fonte, licença, edifício/linhagem, revisão/schema, uso prévio e pendência real.
- [ ] Associar FieldRef aos registros Daiane, mantendo múltiplos requisitos, classes ausentes e suporte incompleto.
- [ ] Preencher contagens reais e lacunas das dez categorias; verificar T7-05/06/31/32.

**Aceite:** nenhum caso inicial foi produzido removendo campo; todas as propriedades têm destino ou motivo de não avaliação.

### M7-04 — Construir grupos e reservar avaliação final

**Dependências:** M7-03. **Responsável:** Nonato; Felipe confirma linhagens BIM.
**Arquivos futuros:** `research/M7/corpus/lineage.json`, `splits.json`; `budget_v1/corpus.py`.
**Entrada → saída:** fontes/exposição/tipos → partições congeladas e auditoria de independência.

- [ ] Construir grupos conectados por edifício, disciplinas, revisão, cópia e tipo/variante correlacionada.
- [ ] Separar desenvolvimento, seleção e final; buscar outros projetos se os grupos não sustentarem a separação.
- [ ] Registrar exposição e executar verificações T7-03/04/33 antes de liberar seleção.

**Aceite:** nenhum grupo cruza partição; ausência de corpus independente é limite/gate explícito, sem falso teste externo.

### M7-05 — Preparar gabaritos e referência de evidências

**Dependências:** M7-03/04 e rubrica M7-01. **Responsável:** Felipe com especialistas; Nonato coordena versões.
**Arquivos futuros:** `research/M7/gold/cases.jsonl`, `evidence.jsonl`, `adjudication.jsonl`; `budget_v1/gold.py`.
**Entrada → saída:** caso/requisito/fonte → GoldCase D/U/T/G, conjuntos suficientes e ações esperadas.

- [ ] Anotar valor/alternativas, unidades/tolerância, evidência/associação, conflitos, requisito inadequado e esclarecimento.
- [ ] Revisar cegamente ao modelo/braço, conservar desacordos e adjudicar sem usar LLM ou valor original como verdade automática.
- [ ] Conferir T7-07/08/09/10/11/12; separar gold do runtime.

**Aceite:** todo caso avaliável tem rubrica rastreável; T/G não ganham resposta concreta inventada; disponibilidade de revisão é declarada.

### M7-06 — Fechar contratos e armazenamento da avaliação

**Dependências:** M7-04/05; contratos M1–M6. **Responsável:** Nonato com Felipe nas integrações.
**Arquivos futuros:** `budget_v1/contracts.py`, `research/M7/protocol/schema.json`, testes de contrato M7.
**Entrada → saída:** objetos da seção 5 → schema/wire format versionados e adaptadores isolados.

- [ ] Validar chaves compostas, hashes, estados separados, campos desconhecidos e migração explícita do legado.
- [ ] Integrar RuntimeManifest/AttemptRecord/Checkpoint/LocalActorContext M6 com armazenamento por projeto.
- [ ] Conferir T7-08/13/22/23/24/34 e rejeitar referências de outra revisão/projeto.

**Aceite:** um outcome é reconstituível até fonte/chamada/GT, sem autenticação local fictícia ou mistura de arquivos.

### M7-07 — Fixar regras e medir recuperação antes da LLM

**Dependências:** M7-05/06; operações M3 suportadas. **Responsável:** Felipe integra M3; Nonato avalia.
**Arquivos futuros:** `research/M7/conditions/rules.json`, `evidence-exposure.jsonl`; `budget_v1/evidence_metrics.py`.
**Entrada → saída:** diagnóstico/receitas/GT → R-B/R-P e medidas de fatos/associação/suficiência.

- [ ] Congelar regras e receitas; executar busca/coleta sem LLM e guardar observações/seleção/omissões.
- [ ] Comparar com conjuntos de referência sem exigir todos os caminhos equivalentes; contar erros de associação.
- [ ] Conferir T7-07/14/15/20/31 e apresentar custo de preparação.

**Aceite:** ganho de extração é mensurado separadamente; regras fortes mantêm capacidade e campos resolvidos dispensam LLM.

### M7-08 — Construir condições de contexto e granularidade

**Dependências:** M7-07. **Responsável:** Nonato + Felipe/M3.
**Arquivos futuros:** `budget_v1/conditions.py`, `research/M7/conditions/design.json`, pacotes/contextos imutáveis.
**Entrada → saída:** R-B/R-P e residuais → braços L-B-E/L-B-P/L-P-E/L-P-P, controle união e E*.

- [ ] Congelar E_B/E_P, CallPlan, instruções e saída por campo, com mesma elegibilidade residual em cada contraste.
- [ ] Construir L-P-P-U e equivalência factual E*; explicitar inviabilidade se não couber.
- [ ] Conferir T7-15/16/17/18/19/20/35 com cliente simulado, antes de inferência.

**Aceite:** divisão das perguntas, filtragem, evidência adicional e organização têm contrastes identificáveis; ninguém elege estratégia vencedora.

### M7-09 — Prospectar modelos e verificar equipamentos

**Dependências:** M7-02; acesso a inventário M6. Pode avançar em paralelo a M7-03–08.
**Responsável:** Nonato; Felipe ajuda na relevância BIM.
**Arquivos futuros:** `research/M7/prospection/models.jsonl`, `hardware-profiles.json`.
**Entrada → saída:** fontes primárias e hardware observado → candidatos por linha pessoal/IME com elegibilidade justificada.

- [ ] Conferir licença, procedência, revisão/digest/quantização, contexto, execução local e recursos estimados.
- [ ] Confirmar hardware/VRAM/RAM/disponibilidade/concorrência reais, sem presumir servidor IME.
- [ ] Registrar instalar/testar/selecionar separadamente e verificar T7-25/26/36/40.

**Aceite:** candidato tem fonte/data e gate explícito; pesquisa não modifica rodada congelada nem inicia downloads/automação.

### M7-10 — Triar modelos e calibrar piloto

**Dependências:** M7-06/08/09; execução local M6 apta; autorização de ensaio futuro.
**Responsável:** Nonato; Felipe revisa respostas e erros BIM.
**Arquivos futuros:** `research/M7/pilot/`, `protocol/pilot-decisions.json`.
**Entrada → saída:** candidatos/condições em desenvolvimento/seleção → modelos elegíveis, repetições e budgets fundamentados.

- [ ] Executar ensaio curto por candidato com casos representativos fora do reservado, formato/abstenção/sustentação e recursos.
- [ ] Medir variação/custo e fixar repetições, seeds, política de retries, limites e ordem antes do final.
- [ ] Justificar inclusão/exclusão e aplicar T7-18/20/21/25/26/27/28.

**Aceite:** nenhuma configuração ou número é adotado apenas por default; piloto não é prova final nem autorização para substituir modelo no meio da rodada.

### M7-11 — Congelar protocolo estatístico e seleção

**Dependências:** M7-01/04/05/10. **Responsável:** Nonato; Felipe valida critérios de relevância técnica.
**Arquivos futuros:** `research/M7/protocol/final.json`, `analysis-plan.md`, manifesto de congelamento.
**Entrada → saída:** piloto/grupos/recursos → protocolo final com estimandos, métricas e limites.

- [ ] Definir contrastes primários, agregações, unidade de incerteza, multiplicidade e critérios de interpretação/roteamento.
- [ ] Fixar população/modelos/versões/opções/GT/splits, repetições, parada, falhas e regras de desvio.
- [ ] Conferir T7-03/13/27/28/29/33; registrar quando desenho só sustenta exploração.

**Aceite:** seleção termina antes de abrir resultados reservados; há protocolo reproduzível mesmo se resultado futuro for negativo.

### M7-12 — Instrumentar execução e recuperação sem perda de evidência

**Dependências:** M7-06/08/11; M6 fila, métricas e backup. **Responsável:** Nonato com integrações M3/M6.
**Arquivos futuros:** `budget_v1/orchestrator.py`, adaptadores M6, testes de tentativas e artefatos.
**Entrada → saída:** condição congelada → tentativas/resultados persistentes e auditáveis.

- [ ] Registrar tempos/carga/inferência/fila/preparo, RAM/VRAM, tokens, contexto/resposta e parâmetros observáveis.
- [ ] Integrar serialização global, cancelamento/parciais, reuso explícito, retomada e drift de digest/configuração.
- [ ] Demonstrar T7-19/20/21/22/23/24/25/34 sem perder casos ou apagar erros.

**Aceite:** harness seco reproduz o plano de chamadas e contagens; nenhum teste de contrato seco é reportado como benchmark.

### M7-13 — Executar núcleo final congelado

**Dependências:** M7-11/12, corpus reservado e gates acadêmicos/operacionais satisfeitos.
**Responsável:** Nonato; Felipe acompanha problemas BIM sem ajustar o teste para favorecer resultados.
**Arquivos futuros:** `research/M7/<round_id>/attempts/`, `outcomes/`, `deviations.jsonl`.
**Entrada → saída:** protocolo final → resultados brutos de todos os braços ou execução parcial justificada.

- [ ] Fazer preflight sem inferência oculta, conferir hashes/modelos/hardware e executar ordem congelada.
- [ ] Preservar todas as falhas/cancelamentos/retries e novos modelos para rodada posterior.
- [ ] Aplicar gates T7-13/20/22/25/29/30; invalidar condição com drift sem descartar seus artefatos.

**Aceite:** unidades previstas reconciliadas, identidade íntegra e nenhuma conclusão antes de julgamento/análise; não requer superar regras.

### M7-14 — Julgar saídas e produzir matriz/estatísticas

**Dependências:** M7-05/11/13. **Responsável:** Nonato; Felipe/especialistas julgam sem identificação do braço quando viável.
**Arquivos futuros:** `budget_v1/field_metrics.py`, `analysis.py`, `reporting.py`; `analysis/`, `reports/matrix.csv`.
**Entrada → saída:** evidências/saídas/GT → matriz por propriedade/modelo/categoria com incerteza e erros.

- [ ] Julgar correção/sustentação/associação, abstenção/conflito e requisitos inadequados, com desacordos preservados.
- [ ] Conferir N/D/U/T/G e P/A/F/I; aplicar método pré-fixado por grupos e mostrar contagens/micro/macro.
- [ ] Verificar T7-09/10/11/12/27/28/31/32/35 e reconstituir células até artefatos brutos.

**Aceite:** resultados próximos/poucos casos admitem inconclusão; conformidade IDS e acerto sem suporte ficam separados.

### M7-15 — Confirmar recomendação e integrar política M3

**Dependências:** M7-11/14; política de seleção congelada e reservado não usado para ajuste.
**Responsável:** Nonato; Felipe implementará eventual política em M3 em tarefa própria.
**Arquivos futuros:** `research/M7/reports/routing-recommendation.json`, `limitations.md`.
**Entrada → saída:** comparação e confirmação reservada → recomendação condicionada por propriedade/grupo/recursos.

- [ ] Avaliar política definida na seleção, incluindo regras/abstenção quando modelo não agrega valor seguro.
- [ ] Registrar cobertura, incerteza e compromisso memória/tempo; limitar ou recusar recomendação sem confirmação.
- [ ] Conferir T7-26/28/33/36 e entregar contrato RoutingRecommendation para M3-27/M6-17.

**Aceite:** modelo não é escolhido e avaliado no mesmo teste; integração não troca default ou fallback automaticamente.

### M7-16 — Planejar e conduzir estudo humano secundário

**Dependências:** M7-01/05/14; M4/M5 estáveis, participantes e enquadramento institucional pertinente.
**Responsável:** Nonato; Felipe apoia dificuldade/rubrica BIM.
**Arquivos futuros:** `research/M7/human/protocol.json`, eventos pseudonimizados e relatório; `budget_v1/human_study.py` se necessário.
**Entrada → saída:** casos distintos equivalentes e fluxo estável → piloto/estudo humano com alcance declarado.

- [ ] Fixar critérios de participação, treinamento, consentimento/tratamento local e ordem contrabalançada.
- [ ] Medir manual sem sugestões e assistido, com consultas/tempo/edições e erros finais independentes.
- [ ] Conferir T7-37/38/39 e declarar piloto se participantes/casos insuficientes.

**Aceite:** proxy não entra como pessoa; conclusão de produtividade proporcional ao desenho, sem bloquear o núcleo.

### M7-17 — Avaliar gates de extensões opcionais

**Dependências:** M7-01 e resultados/limites do núcleo. **Responsável:** Nonato com Felipe e orientador.
**Arquivos futuros:** `research/M7/extensions/decision-record.md` e protocolo próprio somente quando aprovado.
**Entrada → saída:** necessidade observada → decisão datada sobre documentos, contrafactuais ou ajuste de modelo.

- [ ] Discutir cada opção separadamente, com custo, corpus/licenças e ameaça à validade.
- [ ] Para documentos aprovados, desenhar IFC versus IFC+documentos e regras para trechos explícitos, extração/associação/conflito.
- [ ] Conferir T7-05/40; não incluir extensão não aprovada como requisito de conclusão inicial.

**Aceite:** opção permanece fora do MVP até decisão específica; nenhum dado artificial misturado ao corpus real inicial.

### M7-18 — Consolidar relatório, reprodução e continuidade

**Dependências:** M7-02/14/15; M7-16/17 somente se executados no escopo declarado.
**Responsável:** Nonato; Felipe revisa interpretação BIM e limites.
**Arquivos futuros:** `research/M7/reports/final.md`, manifesto de reprodução e registro de próximos candidatos.
**Entrada → saída:** evidências completas/parciais → relatório verificável e pacote local preservado.

- [ ] Publicar fluxo do corpus, matriz completa com lacunas, resultados/variação, ameaças e conclusões proporcionais.
- [ ] Conferir reprodutibilidade de tabelas a partir de artefatos, versão do instrumento e backup M6; separar arquivos restritos dos redistribuíveis.
- [ ] Verificar T7-02/29/30/34/40 e registrar próximos passos sem modificar rodadas anteriores.

**Aceite:** entrega científica pode concluir ausência de benefício; transparência sobre limites e pendências é obrigatória.

<a id="m7-testes"></a>

## 16. Verificações e ensaios futuros — NÃO EXECUTADOS

Estes quarenta casos são oráculos para software/protocolo e execução futura, não evidência nova. Dados sintéticos em teste de contrato não contam no corpus científico real. Toda tarefa acima tem critérios próprios; a equipe implementará os testes pertinentes em `tests/experiment/budget_v1/` e ensaiará dados reais somente após gates.

| Caso | Situação / esperado observável | Tarefa |
|---|---|---|
| T7-01 | Recorte ainda não discutido com orientador → registrar pendência, sem aprovação inventada | M7-01 |
| T7-02 | Run em ZIP repetido e modelo apenas instalado → deduplicar pacote por hash; teste só comprovado por run | M7-02/18 |
| T7-03 | Duas revisões ou disciplinas do mesmo edifício → mesmo grupo/split | M7-04/11 |
| T7-04 | Centenas de instâncias/tipo repetido → não repartir entre seleção e final | M7-04 |
| T7-05 | Pedido de remover campo para primeira etapa → excluir transformação do núcleo real, registrar extensão separada | M7-03/17 |
| T7-06 | Categoria real ausente → matriz mantém categoria e `sem casos`, sem fabricar lacunas | M7-03 |
| T7-07 | Material explícito da folha usado no marco → associação inválida, sem correção sustentada | M7-05/07 |
| T7-08 | GUID igual em dois arquivos → identidades e evidências separadas por revisão/modelo | M7-05/06 |
| T7-09 | Falso/zero legítimo e placeholder → não reduzir a mesma ausência | M7-05/14 |
| T7-10 | Valor igual ao GT, sem evidência aplicável → correção de valor separada, sustentação falha | M7-05/14 |
| T7-11 | Evidência ausente/conflito irresolúvel e valor plausível → U; proposta conta falso preenchimento | M7-05/14 |
| T7-12 | Requisito contradiz fato legítimo → encaminhar revisão, sem inventar valor para passar IDS | M7-05/14 |
| T7-13 | GT/notas reservadas no pacote ou drift após freeze → bloquear/invalidate e registrar vazamento/desvio | M7-06/11/13 |
| T7-14 | Dois conjuntos alternativos suficientes → recuperar um satisfaz suficiência; não exige todos | M7-07 |
| T7-15 | E_P recupera fato que E_B não tinha → ganho de coleta explícito; comparar R-P/R-B | M7-07/08 |
| T7-16 | Mesmo E* em organização diferente → conferir igualdade factual e alteração apenas de organização/instrução fixada | M7-08 |
| T7-17 | Elemento versus propriedade → L-P-P-U conserva união factual; separar filtragem L-P-P | M7-08 |
| T7-18 | Campo resolvido por regra → zero chamadas operacionais; residuais iguais no contraste | M7-08/10 |
| T7-19 | Preparação compartilhada e várias chamadas → custo contado uma vez no fluxo, overhead/chamadas preservados | M7-08/12 |
| T7-20 | Evidência mínima excede janela → limite/pendência, fonte íntegra, omissões visíveis; sem truncamento silencioso | M7-07/08/10/12/13 |
| T7-21 | JSON incompleto/timeout → F/erro com tentativas, não abstenção correta nem caso removido | M7-10/12 |
| T7-22 | Cancelamento e retomada → concluídos preservados, incompletos I, retry vinculado e sem escolher melhor tentativa | M7-06/12/13 |
| T7-23 | Dois projetos solicitam inferência/warm-up/retry → um slot ativo global, sem contexto compartilhado | M7-06/12 |
| T7-24 | Revisor informa nome local → `unverified_local`, sem login/conta/autor autenticado fictício | M7-06/12 |
| T7-25 | Modelo ausente/tag com digest alterado → preflight bloqueia sem pull/fallback; histórico conservado | M7-09/10/12/13 |
| T7-26 | Modelo maior requer memória não medida / servidor não confirmado → candidato condicionado, sem afirmar viabilidade | M7-09/10/15 |
| T7-27 | Réplicas/reuso de uma resposta → reportar estímulos e grupos; não aumentar amostra independente | M7-10/11/14 |
| T7-28 | Poucos casos/diferença próxima → contagens/intervalos/limites, sem vencedor ou equivalência automática | M7-10/11/14/15 |
| T7-29 | Prompt/caso/GT/métrica/população muda → nova rodada/versão, sem misturar com a anterior | M7-02/11/13/18 |
| T7-30 | Resultado negativo ou falha → conservar bruto e incluir no relatório e comparabilidade | M7-02/13/18 |
| T7-31 | Gabarito G ou limite T → manter N e lacunas, separar E; denominador zero não vira 100% | M7-03/07/14 |
| T7-32 | Grande família domina micro → publicar macro/contagens e propriedades não avaliadas | M7-03/14 |
| T7-33 | Seleção de modelo após ver teste → resultado exploratório; novo reservado necessário para confirmar | M7-04/11/15 |
| T7-34 | Backup sem contexto/GT/modelo recuperável → limitação de reprodução registrada; restore não relança inferência | M7-06/12/18 |
| T7-35 | Uma resposta por elemento omite campo / alternativa inventada → campo contabilizado e risco não apagado por outra opção boa | M7-08/14 |
| T7-36 | Novo candidato durante rodada → registrar prospecção e adiar participação à rodada seguinte | M7-09/15 |
| T7-37 | Pessoa vê o mesmo caso nas duas condições → desenho revisto para casos distintos/ordem contrabalançada | M7-16 |
| T7-38 | Assistido aceita erro rapidamente → tempo melhora mas erro final registrado, sem benefício geral falso | M7-16 |
| T7-39 | Poucos participantes/proxy → piloto/indicador simulado, sem produtividade humana comprovada | M7-16 |
| T7-40 | Documento externo/fine-tuning/automação sem aprovação → opção futura, fora de entregável inicial | M7-01/09/17/18 |

<a id="m7-entregas"></a>

## 17. Entregáveis, marcos e dependências

| Marco | Entregável verificável | Dependência/gate | Estado nesta entrega |
|---|---|---|---|
| P0 — Planejamento | Plano, inventário, quadro de cobertura, registro histórico/modelos e verificações documentais | Leitura/reconciliação M1–M6 e pedido integral | Produzido documentalmente; ver seção 20 |
| E1 — Base da pesquisa | Casos reais/gabaritos/evidências revisados, grupos/splits e lacunas | M7-01–06, fontes/IDS/revisores/projetos | Futuro; matriz inicial não é corpus revisado |
| E2 — Instrumento | Regras/contextos/chamadas, harness e protocolo reproduzível | M7-07–12, M3/M6 e piloto | Futuro; sem chamadas/novas métricas executadas |
| E3 — Núcleo científico | Resultados/incerteza, matriz modelo × propriedade, comparação regras/contexto/granularidade | M7-13/14; reservado ou caráter exploratório explícito | Futuro |
| E4 — Recomendações | Roteamento/recursos, limites e pacote reproduzível | M7-15/18; confirmação fora da seleção | Futuro; nenhum vencedor selecionado |
| E5 — Secundário humano | Piloto/estudo manual versus assistido | M7-16 e condições de participação | Opcional ao núcleo; sem ganho humano comprovado |
| E6 — Continuidade | Registro de prospecção e decisões de extensões | M7-09/17; Nonato e orientador conforme escopo | Registro inicial histórico criado; busca/triagem novas futuras |

Caminho crítico: M7-03 → 04 → 05 → 06 → 07 → 08 → 10 → 11 → 12 → 13 → 14 → 15/18. M7-01/02 alimentam o percurso; M7-09 pode ocorrer em paralelo ao corpus; M7-16/17 não bloqueiam o núcleo. M1/M2/M3 fornecem capacidades e dados, M6 viabilidade/persistência; não marcar integração pronta só porque o plano foi entregue.

Não há prazo semanal, quantidade final de casos, custo de GPU ou orçamento institucional confirmado. Nonato estimará esforço após inventário/triagem; Felipe dimensionará revisão BIM. Usar marcos/gates em vez de datas fictícias. A obtenção do XML/planilha de Juliana, casos de categorias ausentes e projetos não expostos pode limitar cobertura; entregar resultados parciais com denominadores, sem declarar piso científico integral.

<a id="m7-riscos"></a>

## 18. Riscos e critérios de conclusão científica futura

| Risco | Contenção / evidência exigida | Dono |
|---|---|---|
| R7-01 — Vazamento de caso/revisão/tipo | Grafo de origem, splits sem interseção e registro de exposição | Nonato + Felipe |
| R7-02 — GT circular/hipótese convertida em fato | Referência por evidência, revisão independente e D/U/T/G | Felipe |
| R7-03 — Extração melhor atribuída à LLM | R-B/R-P, EvidenceExposure e controle E* | Nonato + Felipe |
| R7-04 — Ganho de divisão confundido com filtragem | L-P-P-U e contrastes definidos | Nonato |
| R7-05 — Categoria/propriedade sem casos | Matriz completa e obtenção de outros projetos; sem masking inicial | Felipe + Nonato |
| R7-06 — Pseudorreplicação/seleção no teste | Agrupamento/estímulos, protocolo prévio e confirmação reservada | Nonato |
| R7-07 — Truncamento/retry/falha apagados | Manifesto por chamada, limite explícito e denominadores integrais | Nonato/M6 |
| R7-08 — Hardware/versão drift | Preflight/digest/configuração congelados; nova condição quando mudar | Nonato/M6 |
| R7-09 — Escopo maior que recursos | Triagem, núcleo reduzido justificado e resultados por cobertura, sem prometer 21 modelos | Nonato |
| R7-10 — Benefício humano exagerado | Estudo secundário contrabalançado, erros finais e limite de piloto | Nonato |
| R7-11 — Legado não reproduzível integralmente | Hashes ausentes declarados, originais preservados, análise separada | Nonato |
| R7-12 — Documentos/fine-tuning ampliam MVP | Gate específico com orientador e protocolo próprio | Nonato + Felipe |

Para iniciar coleta: fontes/uso permitidos e reais, gabarito/partições definidos, capacidades necessárias testadas, runtime local identificado e protocolo/piloto compatíveis com recursos. Para declarar resultado científico: população e exclusões rastreadas; braços comparáveis; artefatos/tentativas íntegros; julgamentos/denominadores/variação e incerteza publicados; efeito de recuperação separado de interpretação e resultado proporcional ao número de grupos. Para recomendar rota: confirmação reservada ou limite exploratório explícito. Para alegar benefício humano: pessoas reais e desenho pertinente; proxy não basta.

**Conclusão do núcleo não exige vitória da LLM.** Exige resposta às perguntas no alcance observado, inclusive dano/abstenção/custo, ou declaração de quais perguntas continuam inconclusivas. Cobertura parcial não pode ser chamada de avaliação integral das dez categorias. Documentação completa não satisfaz esses critérios empíricos.

<a id="m7-cobertura"></a>

## 19. Rastreabilidade das decisões

| Decisão | Seções / tarefa | Verificação futura |
|---|---|---|
| D7-01 | 3, 9, 12; M7-01/14/16 | T7-01/39 |
| D7-02 | 7; M7-05 | T7-07–12 |
| D7-03 | 6.3, 11; M7-04/11 | T7-03/04/33 |
| D7-04 | 8.1/8.2; M7-07/08 | T7-14/15/16 |
| D7-05 | 8.1/8.3; M7-08/12/14 | T7-17/18/19/35 |
| D7-06 | 6.2, 9; M7-03/14 | T7-06/31/32 |
| D7-07 | 6.1, 14; M7-03/17 | T7-05 |
| D7-08 | 7, 9; M7-05/14 | T7-07–12/21/31 |
| D7-09 | 10; M7-09/10/12 | T7-19–27 |
| D7-10 | 11; M7-11/14 | T7-27/28/32 |
| D7-11 | 11; M7-11/15 | T7-26/28/33 |
| D7-12 | 2.3; M7-02/18 | T7-02/29/30 |
| D7-13 | 12; M7-16 | T7-37/38/39 |
| D7-14 | 14; M7-17 | T7-40 |
| D7-15 | 13; M7-09/10 | T7-25/26/36 |
| D7-16 | 10, 13, 14; M7-09/11/13/17 | T7-29/36/40 |

A pesquisa bibliográfica [dos 29 artigos de Daiane](../pesquisa/sintese-bibliografica-daiane-29-artigos.md) e o [baseline M3](../pesquisa/modulo-03-contexto/baseline.md) fornecem continuidade metodológica: separar catálogo/requisito/evidência, considerar regra forte, proveniência e revisão. São fontes locais de pesquisa anterior; PDFs originais e fontes web não foram novamente auditados nesta tarefa. Seus controles contrafactuais são compatibilizados com D7-07 como extensão, sem inclusão automática no núcleo.

<a id="m7-verificacao"></a>

## 20. Fontes, verificação documental e integração posterior

Foram inspecionados os planos [M1](modulo-01-dominio-catalogo.md), [M2](modulo-02-nucleo-ifc-ids.md), [M3](modulo-03-contexto-enriquecimento.md), [M4](modulo-04-interface-revisao.md), [M5](modulo-05-saidas-revisoes.md) e a versão final [M6](modulo-06-infraestrutura-governanca.md), com foco em escopo, identidades, contratos, tarefas e avaliação. O [relatório final M6](apoios-modulo-06/verificacao-documental.json) foi lido e seu hash do plano coincide com os bytes consultados; as 51 verificações são evidência recebida de M6, não executadas novamente como testes de produto.

A [verificação M7](../pesquisa/modulo-07-avaliacao/verificacao-documental.json) documenta releitura, cobertura D7, tarefas/testes futuros, links/âncoras, tabelas, parse dos apoios, preservação e hash do plano final. O [manifesto de preservação](../pesquisa/modulo-07-avaliacao/manifesto-preservacao.json) reutiliza a referência de 907 hashes do snapshot M6, com data/proveniência explícitas, e registra a finalização concorrente autorizada de M6, sem atribuí-la a M7. O temporário do primeiro snapshot M7 (803 arquivos) não permaneceu acessível entre chamadas; não se alega comparação contra aqueles hashes perdidos. A pasta `.agents/skills` estava ausente; foram usadas as skills de planejamento e verificação disponíveis na sessão, adaptadas ao pedido exclusivamente documental.

Escopo gravado: este plano e arquivos em `docs/pesquisa/modulo-07-avaliacao/`. O [guia dos apoios](../pesquisa/modulo-07-avaliacao/README.md) diferencia inventário histórico, matriz ainda não avaliada, contratos/protocolo e registro de prospecção. Nenhum plano anterior, índice, código, configuração, resultado experimental, GT, IFC/IDS ou protótipo foi editado por esta tarefa.

**Fechamento documental:** os 907 arquivos da referência M6 coincidiram por SHA-256/tamanho, sem ausentes ou alterados; as versões consultadas M1–M6 e apoios M6 também coincidiram. HEAD, branch e index permaneceram iguais às referências registradas. A releitura conferiu dezesseis decisões, sete fronteiras, dezoito tarefas, quarenta verificações futuras, nove reconciliações e doze riscos. Links/âncoras, tabelas, JSON/CSV e correspondência dos 313 registros à matriz M3 foram checados. Não resta bloqueador documental; alinhamento acadêmico, corpus/gabaritos, hardware/licenças, piloto, avaliação final e estudo humano são etapas futuras com gates próprios.

Não foram executados testes funcionais, análise IFC/IDS, benchmarks, inferência, consulta atual ao Ollama, downloads, treino ou automações. Não houve commit/stage/push. Verificação documental não certifica engenharia, capacidades do produto, desempenho, independência de corpus ainda não curado ou ganho humano. O fechamento não promete que casos/gabaritos revisados ou novos resultados já existam.

Após encerramento, o pai comunica os caminhos e pode coordenar atualização dos índices/mapa em tarefa própria. A única integração proposta é adicionar referência a este plano, seu status documental e precedência dos contratos; esta tarefa não modifica índices nem reabre M1–M6. Os gates empíricos listados nas seções 15–18 continuam para execução posterior.
