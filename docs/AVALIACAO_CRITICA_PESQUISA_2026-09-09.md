# Parecer crítico sobre o IFC Quality Copilot

Avaliação iniciada em 08/09/2026 e concluída em 09/09/2026. Escopo: pesquisa, implementação, resultados experimentais, posicionamento científico e continuidade do desenvolvimento.

## Veredito

Vale a pena continuar, com uma mudança clara de prioridade: transformar a infraestrutura já construída em evidência de que o sistema ajuda a tomar decisões corretas, verificáveis e úteis em modelos novos.

O problema é relevante e a infraestrutura experimental tem qualidades reais. Entretanto, os resultados atuais ainda não demonstram superioridade sobre boas regras determinísticas, agentes generalistas com ferramentas ou revisão manual. Também não demonstram conformidade normativa completa nem segurança integral das correções.

Minha avaliação é que o maior risco imediato está na validade da avaliação e na amplitude das afirmações do artigo. O risco de obsolescência aumenta se a contribuição ficar concentrada em prompts, integração de ferramentas e rankings de modelos locais. Diminui se o resultado principal for um método verificável para distinguir informação recuperável, estimativa condicionada e informação que exige documentação ou decisão humana.

As recomendações abaixo são julgamento técnico fundamentado nas evidências indicadas. As projeções sobre o futuro são cenários, não previsões comprovadas.

## 1. O que foi efetivamente examinado

Foram examinados o contexto do projeto, os manuscritos e o argumentário, documentos de condições e resultados, as políticas de referência, o avaliador, o revisor simulado e componentes de diagnóstico, sugestão, IDS, escrita, auditoria e MCP. A revisão paralela ajudou a confrontar as afirmações do artigo com a implementação.

Também foi feita uma conferência nova dos resultados arquivados:

| Verificação | Resultado |
|---|---|
| Pacotes reavaliados | RTX 4070 com bSDD; RTX 4060 com bSDD; RTX 4070 sem bSDD; RTX 5050 com bSDD |
| Estágios examinados | 80, sendo 20 por pacote |
| Registros de ocorrências | 199.320, incluindo respostas reutilizadas |
| Comparações top-1/top-3 recalculadas | 398.640 |
| Divergências entre vereditos arquivados e recalculados | Zero |
| Divergências entre valores/alternativas arquivados e GT atual | Zero |
| Identificação dos GTs nos estágios | Compatível com os hashes atuais |
| Revisão humana nos quatro pacotes | Simulada em todos os estágios |
| Repetições por modelo/dataset em cada pacote | Uma |

Esses números confirmam consistência da apuração. Não representam 398.640 decisões independentes nem validam a verdade física do gabarito.

Foram executados 405 testes selecionados de avaliação, referências, vazamento e contexto, e outros 145 de pipeline, IDS, pós-validação e MCP. Os 550 passaram após repetir isoladamente um teste de atributos Git inicialmente impedido pela restrição de acesso do ambiente. Isso não equivale à execução de toda a suíte. A importação do servidor MCP também foi confirmada no ambiente atual, com MCP 2.0.0; uma incompatibilidade relatada na revisão paralela com outra versão não foi tratada como indisponibilidade atual.

A conferência não executou novos LLMs nem refez toda a campanha histórica. Os resultados de escala e os estudos v5/v6 foram analisados documentalmente. O código de produção e os manuscritos não foram corrigidos durante este parecer.

A apuração reproduzível desta avaliação está em [resultados da conferência](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/docs/reviews/2026-09-08/evidence_audit.json>), acompanhada de seu [procedimento de recálculo](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/docs/reviews/2026-09-08/audit_evidence.py>).

## 2. Problema, importância e contribuição possível

O problema prático é a distância entre possuir um arquivo IFC e possuir informação suficiente, consistente e corretamente interpretada para um uso específico. O projeto detecta lacunas, reúne contexto, sugere valores e permite aplicar decisões com registros de auditoria.

A pergunta científica mais produtiva é: **em quais condições a combinação de evidência do modelo, requisitos computáveis, inferência e revisão profissional melhora o enriquecimento semântico sem introduzir afirmações sem suporte?**

Essa pergunta requer distinguir três situações:

| Situação | Exemplo conceitual | Tratamento adequado |
|---|---|---|
| Informação existente em outro lugar | Propriedade presente em alias, tipo ou documento vinculado | Recuperar, reconciliar e registrar a origem |
| Informação calculável com premissas disponíveis | Grandeza derivada de dados e método explicitados | Validar premissas, calcular e informar limitações |
| Informação não determinada pelas evidências | Desempenho de um produto sem especificação ou ensaio | Solicitar evidência, registrar incerteza ou abster-se |

Um modelo de IA mais capaz pode melhorar as duas primeiras atividades. Ele não torna um dado ausente automaticamente conhecido. Essa distinção sustenta a relevância futura da pesquisa.

A proposta combina técnicas existentes. Isso não impede uma contribuição científica: integração, benchmark e achados experimentais podem ser contribuições válidas, desde que a avaliação mostre algo novo e transferível. A alegação de pioneirismo por reunir IFC, IDS, bSDD, LLM e revisão humana precisa de comparação explícita com os trabalhos mais próximos; a combinação de nomes de tecnologias não basta.

O patrimônio já construído inclui a identidade experimental, o registro por ocorrência, o tratamento das equivalências, a rastreabilidade das mudanças de gabarito, a separação parcial entre inferência e cálculo e os casos documentados de falha. A existência desses mecanismos foi observada no [avaliador](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/experiment/evaluator.py:621>), no [registro por ocorrência](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/experiment/per_issue.py:45>) e nos [relatórios de replicação](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/docs/resultado-replicacao-5050-2026-08-19.md>).

## 3. As cinco maiores ameaças

### 1. Uma métrica pode premiar uma resposta sem conhecimento do elemento

**Achado novo desta avaliação:** usando o comparador real e as alternativas atualmente aceitas, a resposta constante “REI 120” recebe acerto em **68 de 69 classes de resistência ao fogo: 98,55%**. Por ocorrência, são 1.191 de 1.543, ou 77,19%.

A sonda ignora geometria, materiais, função, especificação e contexto. Foi feita depois de examinar o benchmark, portanto é um teste exploratório da capacidade discriminante da métrica, não um baseline independente nem uma proposta de preenchimento.

Isso demonstra que alta pontuação nesse estrato pode ser obtida sem reconhecer o desempenho do elemento. Não demonstra que “REI 120” seja um valor verdadeiro, seguro ou tecnicamente adequado para esses elementos.

O mecanismo está nas [alternativas aceitas para fogo](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/experiment/ground_truth_value_policy.py:196>). Aceitar uma classe superior como se fosse o mesmo valor pode confundir o atendimento a um requisito com a descrição do desempenho efetivamente documentado. São tarefas diferentes.

**Consequência:** revisar esse estrato antes de usar sua acurácia como evidência de competência técnica. Incluir controles de resposta constante e de superestimação; avaliar requisito, desempenho documentado e estimativa separadamente.

### 2. Referência completa foi obtida, em parte, impondo valores ao desconhecido

A leitura direta dos dois GTs confirmou:

| Proveniência declarada | Ocorrências | Classes |
|---|---:|---:|
| High | 2.359 | 122 |
| Medium | 1.497 | 96 |
| Low | 1.127 | 85 |
| Total | 4.983 | 303 |

Os 1.127 itens low representam 22,62% das ocorrências e 28,05% das classes. Os itens medium também precisam de distinção interna: predominam referências tipológicas, não medições. High inclui referência autoral preservada e aliases do IFC; não significa automaticamente confirmação externa da realidade construída.

Todos os 4.983 itens estão marcados como verified. A [política do GT](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/experiment/ground_truth_policy.py:29>) rejeita estados como desconhecido, não aplicável e revisão necessária como valor esperado. Já o [resolvedor](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/experiment/ground_truth_value_policy.py:628>) atribui valores tipológicos ou prováveis em várias situações de evidência incompleta.

A documentação é transparente sobre isso, o que é positivo. Mas transparência e congelamento não substituem validação independente. Nesse desenho, uma abstenção tecnicamente adequada pode perder para um palpite coincidente com a convenção autoral.

Há ainda ajustes após observação dos resultados: [emendas de agosto](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/docs/emenda-gt-2026-08-12.md>) e a justificativa da [tolerância térmica de 10%](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/experiment/evaluator.py:50>). Corrigir um instrumento defeituoso é legítimo; depois disso, os casos usados para desenvolvê-lo deixam de constituir um teste independente convincente. Não encontrei demonstração de fraude ou vazamento direto generalizado; o risco principal é ajuste iterativo ao conjunto avaliado.

**Consequência:** produzir referência independente, distinguir verificação editorial de confirmação técnica e reservar projetos novos para avaliação final.

### 3. Ainda falta demonstrar o benefício incremental da IA e do sistema

Comparar vários LLMs dentro do mesmo pipeline mostra diferenças entre configurações. Não responde quanto das tarefas seria resolvido por recuperação de aliases, tabelas simples, regras ou calculadoras.

A justificativa de que já existe preenchimento determinístico antes do LLM não substitui um comparador determinístico nas tarefas residuais. Um baseline pode resolver parte delas e abster-se nas demais; seu desempenho deve ser medido junto da cobertura e do custo.

Também faltam comparações realizadas com um agente generalista competente usando ferramentas IFC e com revisão manual real. Sem elas, não há evidência suficiente para afirmar superioridade sobre o que modelos mais fortes já conseguem fazer.

A lacuna está reconhecida, mas parcialmente relativizada, no [argumentário](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/Artigo/ARGUMENTARIO_2026-08-19.md:373>). Recomendo tratá-la como uma prioridade experimental.

### 4. O número de ocorrências excede muito a diversidade e a independência experimental

As 4.983 ocorrências se reduzem a 303 classes nos dois modelos residenciais. O uso da classe como unidade é uma melhoria importante. Entretanto, 303 classes de dois edifícios continuam sem representar a diversidade de autores, exportadores, disciplinas, tipologias e convenções do setor.

O pool de 3.030 resultados é 303 classes × 10 modelos. As mesmas classes aparecem em vários modelos; o teste agregado precisa tratar essa dependência. Reproduzi os números da ablação: 145 classes-modelo favorecem o braço com bSDD e 216 favorecem o braço sem bSDD, com p nominal de McNemar ≈ 0,00022. O recálculo confirma a conta, não a adequação de tratar todos esses pares como independentes.

No gemma2, o efeito é particularmente nítido: 22 classes ganhas e nenhuma perdida, +7,26 pontos, p nominal ≈ 4,77×10⁻⁷. Mesmo esse resultado vale para os casos, modelo e tratamento estudados; precisa ser confrontado com a qualidade da referência.

Há uma repetição por estágio. As três máquinas variam também em CPU, RAM e driver. McNemar não significativo não demonstra equivalência, e uma comparação entre máquinas não estima a variabilidade de repetições na mesma máquina.

**Consequência:** apresentar diferenças e intervalos, preservar agrupamentos e ampliar os projetos antes de generalizar. A [replicação](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/docs/resultado-replicacao-5050-2026-08-19.md:81>) e a [ablação](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/docs/resultado-ablacao-bsdd-2026-08-19.md:51>) já oferecem material para essa reanálise.

### 5. O ciclo de validação e revisão é menos forte que algumas afirmações sugerem

O [revisor simulado](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/experiment/reviewer.py:44>) conhece o gabarito: aceita a primeira sugestão compatível ou escolhe outra entre as três. Portanto, “aceitação” não é observação do comportamento de um engenheiro. O profissional pode não reconhecer a melhor opção, discordar do GT ou aceitar uma resposta convincente e errada.

A conformidade posterior é medida após essa seleção por um revisor que conhece a referência. Ela não mede a segurança de aplicar qualquer saída do sistema. O [readiness experimental](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/experiment/evaluator.py:716>) ainda simula a retirada das issues com GT, independentemente de a sugestão estar correta.

No código, a [correção](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/pipeline.py:415>) já foi escrita quando ocorre a pós-validação. Se o resultado é fail, há aviso e registro, mas a issue ainda é resolvida com a decisão recebida; a [exportação](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/pipeline.py:486>) não bloqueia esses casos. Além disso, o pipeline desliga a checagem de schema por elemento, enquanto o [resultado](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/validation/post_validator.py:45>) pode indicar schema_valid=True pela ausência de erros coletados.

**Consequência:** não afirmar segurança integral, ausência de regressões ou produtividade humana demonstrada. Separar “não verificado”, “aprovado” e “reprovado”; validar o arquivo resultante e medir a revisão humana real.

## 4. Avaliação técnica da arquitetura

A modularização é defensável para um protótipo de pesquisa. Diagnóstico, geração, escrita, avaliação e auditoria têm responsabilidades identificáveis. A recomputação térmica é uma escolha útil, embora uma conta correta possa usar materiais, condutividades ou premissas incorretas. É necessário verificar tanto os dados de entrada quanto o cálculo.

As limitações mais relevantes são:

| Componente | Evidência e implicação |
|---|---|
| Troca de modelos | Está demonstrada dentro do Ollama pelos resultados arquivados. |
| Troca de provedores | O [pipeline](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/pipeline.py:114>) instancia Ollama diretamente. Transporte e telemetria dependem dele. Uma interface comum e adaptadores ainda seriam necessários para comparação limpa com outros provedores. |
| IDS | O [parser](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/translator/ids_parser.py:70>) preserva apenas a primeira restrição em certos casos. O [gerador](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/translator/rule_generator.py:129>) transforma limites em checagem numérica, padrões em texto não vazio e igualdade booleana em checagem de tipo. Isso é um subconjunto operacional com perda de semântica. |
| Checagens de valores | No [executor](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/translator/rule_generator.py:624>), um número positivo não é testado contra o limite que foi perdido; um booleano não é necessariamente comparado com TRUE/FALSE exigido. XSD válido não prova avaliação fiel dos requisitos. |
| IDS nos benchmarks | Nos 80 estágios conferidos, existem cinco regras, mas zero issues adicionais atribuídas ao IDS. O vínculo de contexto exige [rule_id](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/pipeline.py:828>). A telemetria mostra bSDD ou nenhuma fonte de grounding, sem IDS. Isso não prova que o IDS não participe de nenhuma etapa; mostra que seu benefício como contexto das sugestões não foi demonstrado. |
| Auditoria da opção escolhida | A correção usa o valor escolhido, mas obtém confiança e referência da [primeira sugestão](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/pipeline.py:410>). Ao escolher outra opção, a proveniência pode ficar incorreta. |
| Escrita por MCP | Os [handlers diretos](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/mcp_server/tools_write.py:87>) checam uma flag fornecida pelo cliente e chamam o writer. Auditoria e pós-validação não são uniformemente impostas nesse caminho. A flag não é, por si, evidência de autorização humana independente. |
| Serviço HTTP | Sem token configurado, a [autorização](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/mcp_server/http_server.py:26>) permite a requisição. O estado global exige cuidado caso se evolua do uso individual para várias sessões. Não foi feito teste de intrusão nem verificado serviço exposto. |
| Cache | A [assinatura](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/suggestion_engine/suggestion.py:358>) considera modelo, prompt e partes do contexto, mas não toda a identidade da inferência. Mudanças de provedor, parâmetros e contexto da edificação precisam invalidar resultados. O cache persistente estava desligado nos benchmarks conferidos. |

A correção prioritária de engenharia é ter um único caminho de aplicação que vincule a decisão à sugestão escolhida, teste a alteração em uma cópia, valide e só então confirme a gravação, registrando também recusas e exceções. As restrições IDS não suportadas precisam ser explicitamente rejeitadas ou delegadas a um validador compatível, em vez de silenciosamente simplificadas.

## 5. Literatura atual e originalidade

A busca foi direcionada a fontes primárias próximas do problema; não é uma revisão sistemática exaustiva.

| Trabalho ou ferramenta | Relação com a pesquisa |
|---|---|
| Bloch, 2022 | Já sistematiza enriquecimento semântico BIM e seus métodos. O problema antecede a atual geração de LLMs. [Artigo em ITcon](https://www.itcon.org/paper/2022/20). |
| Fuchs e Borrmann, 2025 | Investiga inferência de informação IFC ausente por modelos de linguagem e representações de dados. “Usar linguagem para enriquecer IFC” não é, isoladamente, novidade. [Publicação EG-ICE](https://strathprints.strath.ac.uk/93271/). |
| IfcTester | Já permite validar IFC contra IDS e emitir relatórios. É um comparador de validação pertinente, embora não substitua a avaliação das sugestões. [Documentação oficial](https://docs.ifcopenshell.org/ifctester.html). |
| IfcMCP | Expõe ferramentas de consulta e edição IFC a assistentes de IA. A integração conversacional genérica já tem concorrência aberta. [Documentação oficial](https://docs.ifcopenshell.org/ifcmcp.html). |
| Hellin e colaboradores, 2026 | Avalia exploração adaptativa em 1.027 tarefas, 37 IFCs e 21 projetos. Investiga também a interação entre capacidade do modelo e recursos adicionais. É um comparador conceitual importante para a discussão de obsolescência. [Preprint](https://arxiv.org/abs/2605.01698). |
| BIM-Edit, 2026 | Avalia 324 tarefas de edição, considerando geometria, semântica e topologia. Mostra por que acertar um valor não esgota a avaliação de uma alteração IFC. [Preprint](https://arxiv.org/abs/2606.20146). |
| Ishigaki-IDS-Bench, 2026 | Reúne 166 exemplos de 83 cenários elaborados por especialistas e separa validade formal de fidelidade do conteúdo. A versão 3 informa aceite no CIKM 2026. [Artigo e artefatos](https://arxiv.org/abs/2605.22079v3). |

Esses estudos avaliam tarefas diferentes. Seus percentuais não devem ser comparados diretamente com o top-1 deste projeto.

O posicionamento mais defensável é uma investigação de **qualidade da evidência, limites da inferência e efeitos das decisões de contexto em enriquecimento IFC auditável**. A novidade pode estar no protocolo e nos mecanismos demonstrados, particularmente se houver referências independentes e validação em projetos novos.

Uma formulação como “primeira combinação publicada de todas estas tecnologias” é frágil. Uma contribuição delimitada e testável permanece valiosa mesmo que outro grupo use os mesmos componentes.

## 6. Risco de obsolescência

| Dimensão | Julgamento | Razão e resposta recomendada |
|---|---|---|
| Obsolescência tecnológica | Alto para componentes específicos | Prompts, runtimes e adaptações para um conjunto de modelos mudam rapidamente. Isolar adaptadores e contratos de dados. |
| Perda de relevância científica | Alto para um ranking isolado; menor para um protocolo válido | Um ranking perde atualidade; um benchmark independente e uma análise de falhas podem ser reaplicados. |
| Substituição por capacidades gerais de IA | Alto para consulta, classificação simples e geração de código | Comparar com agentes que realmente tenham ferramentas e condições adequadas de execução. |
| Valor durável | Promissor, mas ainda precisa ser demonstrado | Evidência vinculada ao projeto, tratamento do desconhecido, testes independentes, integridade das alterações e responsabilidade das decisões continuam necessários. |

Minha inferência é que modelos mais fortes reduzirão parte do valor de regras de prompt e ferramentas muito específicas. O trabalho de Hellin e colaboradores já explora a dependência entre capacidade do modelo e benefício de recursos adicionais, mas não resolve essa questão para o seu sistema. [Fonte](https://arxiv.org/html/2605.01698v1).

Não há garantia de que o produto atual preserve uma vantagem comercial. Existem cenários em que plataformas BIM incorporam funcionalidades semelhantes. Nesse caso, o projeto pode continuar relevante como protocolo, conjunto de testes ou componente especializado de validação.

Para os próximos 12–24 meses, faz sentido priorizar a prova de benefício incremental. Para um horizonte de três a cinco anos, a estratégia mais resistente é permitir que modelos melhores ocupem a etapa de inferência enquanto a referência, a validação e a rastreabilidade permanecem independentes deles. Esses horizontes são planejamento, não previsão da velocidade de evolução da IA.

## 7. Afirmações do artigo que precisam de revisão ou novas evidências

| Afirmação | Situação e formulação recomendada |
|---|---|
| “Grounding IDS+bSDD aumenta a confiabilidade” | O canal IDS não aparece no contexto registrado dos benchmarks; retirar o tratamento bSDD melhorou a concordância nessa condição. Delimitar fontes e tratamentos efetivamente medidos. |
| “bSDD prejudica a acurácia” | Restringir à versão, ao dicionário, às propriedades e ao empacotamento testados. Bloco e instrução foram alterados conjuntamente; não é efeito universal da plataforma. |
| “O v7.8 teria no máximo o resultado sem bSDD” | A afirmação de teto no [documento v7.8](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/docs/condicao-v7-8-2026-08-19.md:19>) não foi demonstrada. Contexto corrigido pode ajudar, empatar ou piorar. Uma condição não executada não tem resultado conhecido. |
| “+31,2 pontos provam o efeito global da evidência” | O número corresponde a Category na comparação v5/v6. Não é uma ablação global nem deve ser somado ao efeito do bSDD, medido em outra condição. [Fonte local](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/docs/resultado-matriz-v6-2026-08-03.md:35>). |
| “A recomputação explica a queda térmica de 40 pontos” | A queda veio de uma classe cuja resposta não trouxe memória. Os erros de soma estavam em outros casos. Separar cobertura da memória, correção aritmética e validade das premissas. [Fonte local](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/docs/achado-aritmetica-termica-2026-08-02.md:37>). |
| “Medimos o ciclo inteiro com revisão humana” | O sistema contém esse fluxo, mas o experimento usa revisão simulada. Não mede tempo, confiança ou erro do profissional. [Argumentário](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/Artigo/ARGUMENTARIO_2026-08-19.md:111>). |
| “Conformidade IDS e zero regressões” | Exigem semântica de requisitos preservada, validação independente e inspeção do arquivo final. A checagem atual é insuficiente para a afirmação geral. |
| “Determinismo e equivalência entre GPUs” | Distinguir identidade dos artefatos, estabilidade agregada e igualdade das respostas. Ausência de significância não comprova equivalência. |
| “82% de acerto” como qualidade geral | Identificar modelo, ambiente, instrumento, unidade e referência. No gemma2/4070/on: 82,16% por ocorrência e 66,34% por classe. |
| “O artigo já reflete o experimento concluído” | O [argumentário](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/Artigo/ARGUMENTARIO_2026-08-19.md>) é mais atual que o [resumo ERA BIM](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/Artigo/ERABIM_RESUMO_2026/resumo_final.md:15>) e partes do [manuscrito IME](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/Artigo/artigo_ime_ifc_quality_copilot/exemplo-conclusao.tex:5>), que ainda contêm formulações prospectivas ou pendências já superadas. |

Também recomendo substituir os rótulos secundários precision/recall/F1 por nomes que expressem exatamente o que medem. No [avaliador](<C:/Users/Keller_/Desktop/Projetos FC/Pesquisa/ifc-quality-copilot/src/experiment/evaluator.py:669>), são métricas de acerto condicionado à geração e cobertura da referência, não avaliação convencional de detecção. A qualidade do diagnóstico precisa de casos positivos e negativos anotados independentemente.

## 8. Melhorias por categoria

Estimativas de esforço são ordens de grandeza para alguém familiarizado com o projeto; não incluem integralmente recrutamento, autorizações de dados ou espera por execução. Prioridades: alta, média e baixa. Nenhuma alteração abaixo foi implementada por este parecer.

### M1 — Contribuições científicas

**Lacuna:** objetivo amplo e contribuições misturadas. **Implementação:** eleger uma questão central e limitar o artigo a três contribuições: protocolo, evidência comparativa e análise de falhas. **Evidência:** cada contribuição vinculada a uma pergunta, teste e resultado. **Impacto:** alto na clareza e defensabilidade. **Esforço:** 2–4 dias. **Prioridade:** alta.

### M2 — Desenho experimental

**Lacuna:** desenvolvimento e avaliação usam os mesmos casos; uma repetição e tratamentos combinados. **Implementação:** separar conjunto de desenvolvimento e teste externo; congelar protocolo antes do teste; fazer repetições e alternar a ordem das condições. **Evidência:** estimativa do ganho fora da calibração e da variabilidade. **Impacto:** muito alto no rigor. **Esforço:** 1 semana de desenho, seguida de coleta. **Prioridade:** alta.

### M3 — Conjuntos de dados e casos de teste

**Lacuna:** dois projetos residenciais e GT parcialmente convencional. **Implementação:** adicionar projetos de autores e exportadores diferentes; adjudicar um subconjunto de referência com dois especialistas; separar documentado, calculado, estimado, desconhecido e não aplicável. Incluir valores presentes porém errados e casos corretos que não precisam de alteração. **Evidência:** validade externa e avaliação do diagnóstico, além das sugestões. **Impacto:** muito alto. **Esforço:** 3–6 semanas, condicionado ao acesso aos dados. **Prioridade:** alta.

### M4 — Baselines e comparações

**Lacuna:** ausência de prova do valor incremental. **Implementação:** comparar regras e cópia de aliases, referência tipológica, LLM com contexto equivalente, agente com ferramentas e pipeline completo. Acrescentar sondas constantes para testar a métrica. **Evidência:** ganho líquido da inferência, do contexto e da governança. **Impacto:** decisivo para justificar o desenvolvimento. **Esforço:** 1–2 semanas, mais inferência. **Prioridade:** alta.

### M5 — Métricas quantitativas

**Lacuna:** alternativas permissivas e mistura entre verdade, plausibilidade e preenchimento. **Implementação:** redesenhar fogo e grandezas físicas; reportar acerto factual, erro numérico, cobertura, abstenção adequada, sugestão sem suporte e erro de alta confiança. Diferenciar validade sintática, fidelidade ao requisito e validade técnica. **Evidência:** capacidade discriminante contra respostas triviais. **Impacto:** decisivo. **Esforço:** 3–7 dias de definição, mais adjudicação. **Prioridade:** alta.

### M6 — Avaliação humana e especialistas

**Lacuna:** o revisor conhece o GT; produtividade não foi observada. **Implementação:** estudo contrabalanceado com e sem assistência, tarefas equivalentes e avaliação cega do resultado final. Medir tempo, correções corretas, aceitação de erros e discordância. Um piloto com 6–10 profissionais pode orientar um estudo dimensionado, sem ser apresentado como amostra suficiente por definição. **Evidência:** utilidade real e risco de confiança excessiva. **Impacto:** muito alto. **Esforço:** 3–6 semanas com recrutamento. **Prioridade:** alta.

### M7 — Análise estatística

**Lacuna:** dependência entre ocorrências, classes, modelos e projetos. **Implementação:** manter resultados por modelo e projeto; estimar intervalos por reamostragem que preserve agrupamentos; ajustar multiplicidade; planejar comparação de equivalência com margem prévia quando essa for a pergunta. Com apenas dois projetos, evitar inferência populacional forte. **Evidência:** incerteza compatível com o desenho. **Impacto:** alto. **Esforço:** 3–5 dias para reanálise; mais dados para generalização. **Prioridade:** alta.

### M8 — Explicabilidade e rastreabilidade

**Lacuna:** justificativa textual e URI de classe não verificam o valor. **Implementação:** vincular cada sugestão aos campos, relações, documentos e premissas usados; registrar a opção efetivamente escolhida; testar referências inexistentes e perturbação da evidência. **Evidência:** porcentagem de afirmações sustentadas e cadeia reproduzível de derivação. **Impacto:** alto e durável. **Esforço:** 1–2 semanas. **Prioridade:** alta.

### M9 — Robustez e generalização

**Lacuna:** dependência de nomenclatura, exportação e contexto. **Implementação:** testar aliases, idiomas, unidades, dados contraditórios, ausência de materiais, IFC2x3/IFC4/IFC4.3 quando houver suporte e diferentes disciplinas. Usar divisões por projeto e família, evitando clones entre desenvolvimento e teste. **Evidência:** degradação sob mudanças e limites de suporte. **Impacto:** alto. **Esforço:** 2–4 semanas após obter casos. **Prioridade:** alta.

### M10 — Reprodutibilidade

**Lacuna:** resultados existem, mas parte das análises remete a scratchpads e memórias. **Implementação:** consolidar suplemento persistente com versão de código, comandos, resultados por ocorrência, scripts de tabelas, ambiente e licença dos dados. Publicar artefatos autorizados com identificador persistente; documentar dados que não possam ser redistribuídos. **Evidência:** reprodução das tabelas por terceiro. **Impacto:** alto; aproveita trabalho já realizado. **Esforço:** 3–7 dias. **Prioridade:** alta.

### M11 — Segurança, privacidade e governança

**Lacuna:** pós-validação permissiva, caminhos de escrita distintos e ausência de prova completa de privacidade. **Implementação:** unificar aplicação/auditoria, registrar estados não verificados, impor confirmação após validação, controlar sessões e autenticação quando houver acesso remoto. Testar instruções maliciosas em campos IFC e destinos de gravação. Documentar o que sai do computador em consultas externas e o modo offline. **Evidência:** integridade do arquivo, bloqueio de operações indevidas e inventário de tráfego. **Impacto:** alto para alegações de confiabilidade. **Esforço:** 1–3 semanas. **Prioridade:** alta.

### M12 — Estado da arte

**Lacuna:** a alegação de novidade não compara suficientemente as abordagens mais próximas. **Implementação:** atualizar matriz de trabalhos com tarefa, dados, baseline, evidência, revisão humana e validação; distinguir artigos publicados de preprints. **Evidência:** contribuição específica que não dependa de reivindicar prioridade absoluta. **Impacto:** alto na argumentação. **Esforço:** 3–5 dias. **Prioridade:** alta.

### M13 — Estrutura e argumentação do artigo

**Lacuna:** versões narrativas desalinhadas e resultados de condições diferentes aproximados indevidamente. **Implementação:** estabelecer um manuscrito canônico; separar estudos exploratórios, instrumento oficial, ablação e replicação; identificar todos os denominadores e resultados simulados. **Evidência:** correspondência auditável entre afirmações e tabelas. **Impacto:** alto, com retorno rápido. **Esforço:** 1–2 semanas. **Prioridade:** alta.

Expansão de interface, inclusão indiscriminada de novos modelos e criação de um grande dicionário normativo próprio têm prioridade baixa neste momento. Adaptadores para comparações com outros provedores têm prioridade média de engenharia, mas tornam-se alta dentro do experimento que testa o benefício incremental.

## 9. Dez melhorias em ordem de prioridade

1. Corrigir a definição de verdade e a capacidade discriminante do estrato de fogo; a sonda constante deve deixar de produzir pontuação quase perfeita sem evidência.
2. Adjudicar uma referência independente e incluir desconhecido/não aplicável como estados legítimos.
3. Preparar teste externo com projetos novos, mantendo os atuais como desenvolvimento e estudo exploratório.
4. Executar baselines determinísticos, LLM com contexto equivalente e agente com ferramentas.
5. Corrigir a fidelidade das restrições IDS e validar o IFC final por uma implementação independente.
6. Unificar escrita, pós-validação e auditoria da opção escolhida; medir alterações indevidas.
7. Fazer estudo humano de tempo e qualidade final, com avaliação cega.
8. Isolar os efeitos de conteúdo, instrução, tamanho do contexto e recomputação, com repetições.
9. Reanalisar resultados por classe/projeto, confiança da referência e intervalos que respeitem dependências.
10. Consolidar suplemento reproduzível e reescrever o artigo com comparação atualizada à literatura.

Esta ordem prioriza a validade das conclusões. Para uma demonstração operacional próxima, os itens 5 e 6 devem avançar antes de colocar correções em uso.

## 10. Experimentos que testam relevância diante de IA mais capaz

### Experimento A — Benefício incremental do pipeline

Comparar, nas mesmas tarefas novas:

| Braço | Condição |
|---|---|
| A0 | Diagnóstico e revisão manual, no estudo humano |
| A1 | Regras, aliases, tabelas e cálculos; abstenção quando necessário |
| A2 | LLM recebe a mesma evidência relevante e produz a mesma estrutura de saída |
| A3 | Agente generalista acessa ferramentas IFC e validação, com orçamento de tempo e chamadas registrado |
| A4 | Pipeline proposto completo |

Usar ao menos um modelo local e um modelo forte contemporâneo no momento da execução, identificando versão e recursos. Acesso por API ou ferramentas pode exigir adaptação; não pressupor que o modelo consiga processar um IFC bruto apenas anexado.

Medir acerto sustentado por evidência, erro de alta confiança, cobertura, validade do arquivo, custo por correção correta e tempo de revisão. Comparar qualidade em cobertura equivalente e registrar o custo das abstenções.

**Resultado que sustentaria continuidade:** ganho relevante de qualidade, integridade ou custo total com A4 sobre os comparadores fortes. **Resultado que enfraqueceria a justificativa:** A3 alcançar o mesmo resultado com complexidade, custo e risco menores. Nesse caso, concentrar o projeto na avaliação e validação especializada.

### Experimento B — Contexto sem confundir conteúdo e instrução

Comparar ausência de bloco, bloco antigo, bloco escopado e bloco relevante com instrução condicionada. Acrescentar controles de tamanho e posição: contexto irrelevante de extensão semelhante e contexto pertinente dentro da janela.

Registrar tokens reais quando disponíveis, truncamento, evidência preservada e comportamento por propriedade. Separar o efeito de impedir truncamento do efeito de fornecer conhecimento útil. Repetir na mesma máquina e usar a versão corrigida como condição nova.

Esse desenho testa o mecanismo sugerido pela ablação. Não pressupõe que v7.8 empate com o braço sem bSDD.

### Experimento C — Reconhecer o que não pode ser inferido

Criar pares de casos com evidência suficiente, evidência ausente e evidência contraditória. A referência deve indicar qual decisão é possível e qual informação adicional seria necessária.

Medir abstenção correta, pedido de informação útil, afirmação sem suporte e cobertura. Um modelo que preenche tudo deve perder quando a realidade não está determinada. Esse experimento é particularmente importante para tornar a avaliação resistente a respostas plausíveis de modelos cada vez mais fluentes.

### Experimento D — Separar interpretação, recuperação e cálculo

Nas tarefas numéricas, comparar LLM sozinho, calculadora com entradas verificadas e LLM com extração estruturada seguida de cálculo. Julgar separadamente escolha dos materiais/dados, unidades, premissas, operação e resultado.

A ablação da calculadora deve usar os mesmos termos de entrada quando a pergunta for o efeito da aritmética. Se também mudar as premissas, a diferença não pode ser atribuída apenas ao cálculo.

### Experimento E — Generalização, modelos novos e custo total

Congelar o núcleo e comparar gerações de modelos sem ajustar prompts ao teste. Incluir um braço uniforme e outro com ajustes limitados a desenvolvimento, para não penalizar artificialmente modelos que exigem formatos ou orçamentos distintos.

Adicionar projetos e exportadores externos. Medir latências p50/p95, tokens, memória e tempo humano; energia somente se instrumentada. O custo local inclui hardware, manutenção e revisão, não apenas ausência de cobrança por chamada. Para cloud, documentar dados transmitidos e usar casos adequados à autorização de compartilhamento.

O tamanho final da amostra e o número de repetições devem vir de um piloto e do efeito mínimo considerado útil. Multiplicar modelos sem ampliar decisões independentes não resolve a falta de diversidade.

## 11. Perguntas de pesquisa e hipóteses testáveis

| Pergunta | Hipótese a testar | Desfecho principal |
|---|---|---|
| RQ1: O pipeline acrescenta valor a um agente com ferramentas? | Reduz erros sem suporte ou custo total por correção validada em cobertura equivalente. | Diferença pareada de qualidade/custo, com margem de relevância prévia |
| RQ2: Que contexto ajuda de fato? | Contexto pertinente e escopado supera bloco genérico de tamanho controlado. | Acerto por classe e preservação da evidência |
| RQ3: O sistema reconhece informação indeterminada? | Uma política explícita de suficiência de evidência reduz preenchimentos injustificados. | Erro sem suporte e abstenção adequada |
| RQ4: Qual parte do ganho térmico vem do cálculo? | Cálculo determinístico reduz inconsistência aritmética; não corrige sozinho premissas erradas. | Erro de operação e erro de premissa separados |
| RQ5: A assistência melhora o trabalho profissional? | Reduz tempo por tarefa mantendo qualidade final dentro de margem prévia. | Tempo e correção final avaliados de forma cega |
| RQ6: O benefício persiste com modelos e projetos novos? | Parte do ganho de validação/rastreabilidade permanece após substituir o gerador. | Interação entre modelo, pipeline e projeto |

Essas hipóteses são propostas para a próxima etapa. Não estão confirmadas pelos resultados atuais.

## 12. Reformulação da contribuição central e organização do artigo

Formulação compatível com o estágio atual:

> Este trabalho apresenta e avalia exploratoriamente um pipeline de sugestão de enriquecimento semântico de modelos IFC, com registro de evidências e decisões, empregando inferência local e componentes determinísticos. A avaliação distingue ocorrências de classes de equivalência e referências de diferentes proveniências, examinando a concordância das sugestões, a variabilidade entre ambientes e os efeitos do empacotamento do contexto. Os resultados caracterizam limitações do instrumento e das estratégias de sugestão, sem equiparar concordância com referências autorais a desempenho físico ou conformidade normativa certificada.

Após executar as melhorias, uma contribuição mais forte seria investigar **quando um pipeline condicionado à suficiência de evidência supera regras e agentes generalistas na qualidade e no custo da correção IFC**. Essa formulação depende de novos resultados.

Título possível: **“Evidência e incerteza no enriquecimento semântico de modelos IFC: avaliação de um pipeline híbrido com modelos de linguagem”**.

Organização recomendada: problema e lacuna; trabalhos relacionados; contrato de tarefa e referência; arquitetura necessária ao método; desenho experimental e comparadores; resultados por pergunta; análise de falhas; ameaças à validade; disponibilidade dos artefatos; conclusão limitada ao demonstrado.

Separar desempenho do software de desempenho da pesquisa. Resultados negativos bem controlados, como uma fonte de contexto que piora a tarefa, podem fortalecer o artigo. Falhas de instrumento precisam ser descritas e delimitadas, não atribuídas automaticamente à incapacidade dos modelos.

## 13. Notas e plano de trabalho

As notas são julgamento orientativo, não métricas calculadas nem previsão de aceite.

| Dimensão | Nota | Justificativa |
|---|---:|---|
| Relevância prática | 8/10 | Problema concreto e necessário em fluxos IFC; magnitude do benefício ainda sem estudo de campo. |
| Originalidade | 6/10 | Componentes conhecidos; protocolo e achados podem produzir contribuição específica. |
| Rigor científico atual | 5/10 | Excelente rastreabilidade relativa ao estágio; referência, teste externo e comparadores limitam as conclusões. |
| Robustez técnica | 6/10 | Modularização e testes relevantes; semântica IDS, escrita e proveniência exigem correções. |
| Potencial de publicação | 7/10 | Bom potencial com recorte honesto e correções; não significa manuscrito pronto para periódico exigente. |
| Resistência à obsolescência | 6/10 | Integração e prompts são substituíveis; validação, evidência e benchmark podem durar. |
| Qualidade da avaliação experimental | 5/10 | Campanha rastreável e ablação úteis; GT permissivo, apenas dois projetos e ausência de comparadores fortes. |

**Curto prazo — aproximadamente 1–2 semanas de trabalho:** corrigir a narrativa; documentar a sonda constante; definir tarefa e estados de incerteza; separar métricas; preparar a adjudicação e o protocolo de baselines. Corrigir os limites de IDS e de aplicação antes de alegar conformidade ou oferecer uso operacional. Critério de saída: cada afirmação do artigo tem uma evidência identificada ou é declarada hipótese/limitação.

**Médio prazo — aproximadamente 4–8 semanas, dependendo de dados e especialistas:** construir referência independente, obter projetos externos, executar baselines e ablações isoladas, realizar piloto humano e analisar incerteza. Critério de saída: benefício incremental estimado em dados não usados para ajustar o sistema, com custos e limitações explícitos.

**Longo prazo — aproximadamente 2–4 meses, conforme recursos:** ampliar validade externa, publicar benchmark e protocolo autorizados, testar troca de provedores/modelos e avaliar impacto em um uso downstream delimitado. Critério de saída: contribuição reaplicável que não dependa do ranking atual.

Não recomendo ampliar simultaneamente energia, incêndio, acústica, orçamento e manutenção para provar tudo em um único artigo. Um recorte com referências defensáveis, comparadores fortes e resultados claros tende a produzir mais força científica que uma plataforma extensa com validação superficial.

## Conclusão

Sim, vale a pena continuar. A pesquisa aborda um problema real, já possui infraestrutura experimental valiosa e contém achados aproveitáveis.

A continuidade deve depender da próxima evidência: o sistema consegue produzir decisões melhores, mais rastreáveis ou mais econômicas que alternativas simples e agentes modernos, em casos novos e com referência independente?

O resultado mais durável será esclarecer quando inferir, quando calcular, quando recuperar informação existente e quando pedir evidência adicional. Se o projeto conseguir medir e apoiar essas decisões, a evolução da IA pode ampliar sua utilidade. Se permanecer centrado em preencher lacunas com respostas plausíveis e comparar modelos no mesmo gabarito, o risco científico e tecnológico continuará elevado.

