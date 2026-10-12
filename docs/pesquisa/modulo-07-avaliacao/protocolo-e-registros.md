# M7 — Caderno de protocolo e registros futuros

**Versão documental: 2026-10-12-r1. Não executado.** Complementa as seções 5–16 do [plano M7](../../planejamento/modulo-07-avaliacao-cientifica.md). Nonato coordena; Felipe auxilia no domínio/gabarito. Identificadores e campos abaixo são contrato proposto, não schema implementado ou dados de experimento preenchidos.

## 1. Gates antes de coletar dados novos

| Gate | Evidência exigida | Quem fecha |
|---|---|---|
| G7-A — Recorte | Registro da discussão com orientador e delimitação núcleo/secundário/extensões; não inventar aprovação | Nonato + orientador; Felipe participa |
| G7-B — Corpus | Fontes/uso, pendências reais, mapa de exposição/linhagem, cobertura e splits | Felipe + Nonato |
| G7-C — Gabarito | GoldCase revisado, D/U/T/G e evidência/suficiência; desacordos/adjudicação | Felipe + especialistas; Nonato versiona |
| G7-D — Instrumento | Regras, pacotes, fatorial e controles factuais, comparador sem vazamento e testes de contrato | Nonato + Felipe/M3 |
| G7-E — Capacidade | Runtime/hardware/licença/digest confirmados, fila e persistência M6, limites/erros explícitos | Nonato |
| G7-F — Piloto | Variação/custo observados, repetições/budgets/método/ordem justificados, sem exposição ao final | Nonato; Felipe revisa erros |
| G7-G — Congelamento | Protocolo, modelos/opções, corpus/splits/GT e análise com hashes; data anterior ao final | Nonato |
| G7-H — Fechamento da rodada | Unidades previstas reconciliadas, falhas preservadas, julgamentos e relatório com alcance | Nonato + Felipe |

Gate não satisfeito bloqueia sua etapa dependente, não apaga os trabalhos independentes. Corpus escasso pode sustentar estudo exploratório; exige rotulagem e impede confirmação externa fictícia. Não exigir estudo humano para fechar o núcleo. Somente a documentação destes gates foi concluída nesta tarefa.

## 2. Registro de caso e grupos

| Campo | Regra de preenchimento futuro |
|---|---|
| `case_id`, `schema_version` | Identidade estável do campo na revisão; alteração incompatível de contrato gera nova versão |
| `project_id`, `model_id`, `ifc_revision_id`, `ifc_sha256`, `express_id` | Chave do elemento conforme M2; GlobalId adicional com estado validado |
| `pair_id`, `ids_sha256`, `requirement_refs` | Vínculo IFC–IDS M4 e caminho/índice dos requisitos; vários requisitos de um campo não multiplicam observação |
| `analysis_id`, `snapshot_sha256`, `catalog_pin`, `capabilities` | Diagnóstico e capacidades exatos que produziram a pendência |
| `field_ref`, `source_record_ids`, `family_id` | Campo/binding/papel e referência à matriz Daiane, preservando grafia literal e reconciliação |
| `real_gap`, `gap_reason`, `observed_value` | Evidência de pendência existente, sem remover dados para produzir caso |
| `building_lineage`, `type_family_group`, `related_revisions`, `exposure_history` | Origem, parentesco, uso em prompts/desenvolvimento/histórico e autores que viram valores |
| `split_group_id`, `split` | Grupo indivisível; desenvolvimento, seleção ou final; sem cruzar edifício/revisões |
| `evidence_regime_labels` | Explícita, dispersa, conflitante e ausente; múltiplos rótulos permitidos com definição |
| `eligibility`, `exclusion_reason`, `technical_state` | Selecionado, excluído, pendente ou não suportado; motivo/denominador conservados |

Unidade sem elemento por cardinalidade fica no fluxo de diagnóstico, com requisito/especificação e motivo; não inventar FieldRef com elemento inexistente. Mesmo GlobalId entre arquivos não compartilha caso. Tipos/famílias correlacionados e cópias transformadas permanecem no grupo pai.

## 3. GoldCase e referência de evidência

Registrar valor/alternativas tipadas somente em D quando fundamentadas. Em U, registrar informação necessária, conflito ou associação faltante, resposta esperada de abstenção/esclarecimento e proibição de inferência não sustentada. T registra fonte/operação técnica indispensável; G registra por que não há referência independente. Conflito pode ser determinável se uma regra de prioridade justificada resolve; caso contrário U. Requisito inadequado tem etiqueta própria e ação de revisão, sem transformar fato para satisfazê-lo.

Cada evidência contém caminho/portador no IFC, revisão/hash, papel/componente, valor lexical/tipado, unidade, relação com alvo, versão da operação se derivada e validade/pertinência julgada. Conjuntos alternativos suficientes têm IDs próprios. Critério de recuperação deve aceitar qualquer conjunto suficiente admissível; recall de caminhos e suficiência são métricas distintas.

Armazenar `reviewer_id` pseudonimizado quando pertinente, origem da referência, revisão única/dupla, data, desacordo original, decisão de adjudicação e fundamento. `LocalActorContext` informa identidade não verificada pelo aplicativo; protocolo de pesquisa registra a responsabilidade real sem alegar login. Especialista pode consultar documento para julgar insuficiência do IFC, mas esse conhecimento não torna U determinável na condição IFC sozinho.

Gold, anotações e decisões de adjudicação ficam separados das entradas do runtime. Seu hash pode identificar o estudo, mas conteúdo do valor esperado não pode aparecer como fato observado em prompt, nome de arquivo, índice de recuperação, exemplo de few-shot ou comparador que complete resposta.

## 4. ConditionManifest

Uma condição identifica o desenho científico e uma configuração executável. Sua chave inclui:

- Protocolo/revisão/hash, corpus/split/GT/hashes e data de congelamento.
- Braço R-B, R-P, L-B-E, L-B-P, L-P-E, L-P-P, L-P-P-U ou controle E*; definição da diferença manipulada.
- Versões de regras, receita, catálogo/binding, captura semântica bSDD, extração, seleção/organização, prompt/schema e comparador/rubrica.
- Participantes da rodada: modelos por digest/configuração, linha de hardware, runtime e política de rota. R é baseline sem digest LLM.
- Janela de contexto, orçamento de saída, tokenizer/template, opções enviadas e observabilidade das opções efetivas.
- Repetições, seeds se suportadas, ordem/blocos, carga fria/aquecida, cache/reuso, retries/reparos, timeout e cancelamento.
- Unidades de análise/grupo, desfechos primários/secundários, critérios de qualidade, métodos de incerteza/multiplicidade e regra de parada.

Não completar parâmetros desconhecidos com defaults supostos. Alias/digest divergiu, corpus mudou ou comparador recebeu emenda? Preservar condição e criar nova identidade/análise; não atualizar a mesma rodada retroativamente. Novo modelo não entra no meio. Comparar hardware diferente exige estrato e controle, sem atribuir diferença à LLM apenas.

## 5. Registro de contexto, chamada e tentativa

`EvidenceExposure` guarda universo IFC acessível, fatos encontrados, seleção do pacote, observações rejeitadas e razão, fatos enviados a cada chamada, omissões e budget. Separar fatos, requisitos IDS e semântica bSDD. Em E*, o conjunto de fatos é igual nas formas básica/organizada; ordem/serialização podem variar com registro. O pacote não contém rótulo do GoldCase.

`EvaluationAttempt` liga rodada/condição/modelo/repetição aos IDs M6 de job, tentativa, geração do worker, checkpoint e retry. Contém CallPlan/FieldRefs, `prompt_ref/hash`, `raw_response_ref/hash`, resultado parseado, stop reason, limites, erro/estágio e carimbos UTC/tempos monotônicos. Hash sem bytes recuperáveis permite verificar integridade apenas se a fonte for obtida; não basta para reproduzir a chamada.

Para chamada por elemento, cada campo previsto tem outcome. Para chamada por propriedade, registrar contexto repetido e overhead. Campos resolvidos por regras têm resultado com `method=rule`, sem chamadas artificiais para preencher planilha. Se cache/reuso for analisado, contar estímulos reais e campos beneficiados; não usar tempo de cache como velocidade de inferência.

Registrar primeira resposta e reparos/retries. Limite de tokens/JSON incompleto é falha de execução, não recusa de domínio. Uma proposta errada emitida antes do parse falhar permanece auditável como risco de alternativa, sem virar resposta válida. Cancelamento mantém campos concluídos e restante I; retomada não duplica unidade nem seleciona a resposta mais favorável.

## 6. Cronometragem e memória

| Medida | Fronteira operacional | Cuidado |
|---|---|---|
| Extração/diagnóstico | Início leitura/indexação M2 → snapshot pronto | Cache/entrada já aberta identificados |
| Recuperação/preparo | Início coleta/seleção M3 → pacotes prontos | Custo comum por elemento e custo por propriedade separados |
| Fila | Job elegível/enfileirado → início real de execução | Não misturar com inferência |
| Carga | Pedido/medida de carregamento → modelo pronto quando observável | Se runtime não expõe separação, registrar limitação; sem aquecimento oculto |
| Geração | Envio → resposta concluída; métricas internas do servidor em campos próprios | Relógio de parede pode incluir carga/rede local/preenchimento do prompt |
| Pós-processamento | Resposta → validação/parse/persistência | Retries e reparos entram no fluxo |
| Fluxo total | Início do preparo do escopo → resultado durável de todo o escopo | Pareado pelos mesmos campos; sem soma duplicada de partes compartilhadas |
| RAM/VRAM | Amostras com horário/processo/dispositivo e pico observado | Frequência de coleta declarada; pico amostrado pode não capturar máximo instantâneo |
| Recurso base | Memória/VRAM antes da rodada e processos concorrentes | Separar peso/residência/offload, contexto e overhead; tamanho em disco não é VRAM total |

Uma inferência por instalação, inclusive warm-up/retry, conforme M6. Comparação de granularidade não ganha paralelismo artificial. Ensaiar perfis de recurso reais com M6-17; não promover configurações históricas 4096/8192/768 a limite universal. Backup restaura dados/configurações; abrir/restaurar não inicia chamada automaticamente.

## 7. Formato longo de resultados e relatório

Uma linha de resultado de campo liga `case_id`, grupo/split, `condition_id`, modelo/digest ou R, perfil de hardware, repetição/tentativa, propriedade/binding/papel, família, D/U/T/G, estado P/A/F/I, método, correção técnica, sustentação, validade/associação, conflito, adequação do requisito, alternativas e motivo. Anexar indicadores da suficiência no universo de evidência e no pacote enviado, para distinguir falha de recuperação e recusa diante de falta no prompt.

A projeção agregada por célula da matriz traz N/D/U/T/G, P/A/F/I em E, propostas em T/G, contagens de alternativas, número de chamadas/estímulos/repetições/grupos/projetos, estimativas e incerteza, além de custo e falhas. Contagens técnicas/formais IDS são separadas. Toda taxa aponta para numerador/denominador; vazio é não aplicável/não medido com motivo, nunca 100% ou zero inventado.

O relatório conterá: recorte/estado de alinhamento; seleção de fontes/casos; exposições e splits; gabarito/revisão/desacordos; condições exatas; hardware/versões; dados brutos; desvios/falhas; resultados de recuperação; resultados por propriedade/categoria/modelo; decomposição regra/LLM/contexto/chamadas; incerteza; erros representativos; recomendação/limites; estudo humano separado; continuidade histórica/prospecção. Resultados negativos permanecem.

Antes de publicar uma alegação, perguntar se é sobre recuperação, interpretação, fluxo, hardware ou pessoa, qual contraste a sustenta e qual população foi observada. A mesma diferença não prova todos esses efeitos.

## 8. Decisões a fixar pelo piloto, sem números inventados

| Decisão ainda empírica | Como fechar antes do final |
|---|---|
| Quantidade de casos/projetos e cobertura | Inventário real + disponibilidade/qualidade do GT + análise de grupos; registrar lacunas |
| Repetições/seeds | Variação/custo no piloto e alvo de precisão do estimando; declarar restrição se só uma execução |
| Janela/saída/timeout/retries | Testes de contexto completo e recursos no equipamento; limite finito e política de falha |
| Número de modelos | Elegibilidade/licença, smoke em seleção, custo e pergunta; não reproduzir toda lista por obrigação |
| Método estatístico/intervalo | Grupos independentes, desfecho e variação; contagens/estudo de caso quando inferência não sustentada |
| Margem prática/equivalência | Julgamento BIM prévio e finalidade; não escolher margem depois de olhar resultado |
| Participantes humanos | Objetivo/piloto, disponibilidade/experiência e enquadramento institucional; poucos implicam limite |

O protocolo final é fechado antes de abrir o reservado, com motivo/dado de piloto/autor/data/hash para cada decisão. Uma pendência aqui é tarefa futura delimitada, não lacuna preenchida com número fictício.

## 9. Prospecção e extensões

O [registro de modelos](registro-modelos.json) inicia com evidência histórica e metadados de locks; não valida licença ou viabilidade atual. Para novos candidatos, registrar fonte primária do produtor/model card e licença, versão/digest/quantização, distribuição/procedência, compatibilidade de runtime/JSON/abstenção, contexto anunciado e contexto medido, RAM/VRAM/offload, hardware pessoal/IME e decisão de triagem. Nenhuma sugestão paralela ainda não entregue foi inserida.

Sem servidor confirmado, linha IME é estudo de viabilidade. Sem licença/procedência/capacidade suficiente, candidato fica adiado/excluído com razão. Prospecção contínua não cria tarefa agendada nem autoriza download. Fine-tuning e documentos externos precisam de decisão distinta com orientador, de protocolo próprio e de comparação com baseline correspondente; permanecem opcionais.
