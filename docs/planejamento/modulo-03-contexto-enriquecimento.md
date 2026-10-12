# Módulo 3 — Contexto e enriquecimento por LLM local

> **PLANEJAMENTO CONCLUÍDO E VERIFICADO SEM PENDÊNCIA DE APROVAÇÃO DE FELIPE.**
> **IMPLEMENTAÇÃO NÃO CONCLUÍDA — nenhuma implementação executada nesta entrega.**

**Registro inicial:** 09/10/2026. **Consolidação:** 12/10/2026, conforme a autorização
posterior de Felipe para concluir e verificar o planejamento, incorporando a pesquisa,
as decisões atuais e o exame do repositório. A redação antiga de rascunho e a espera por
nova revisão de Felipe são histórico, não gates adicionais desta consolidação.

**Responsabilidades vigentes:** Felipe conduz M1, M2, M3 e M5. Nonato conduz M4 e M6
e lidera M7, com ajuda de Felipe. Especialistas revisam premissas de engenharia e o
curador publica versões; esses papéis não são substituídos pelo LLM ou pelo programador.

**Entradas iniciais:** IFC + IDS pronto + catálogo. Consulta à **API pública bSDD** é
permitida para semântica pública, sem transmitir conteúdo IFC, valores, nomes ou contexto
de projeto. Evidência, inferência, decisões, histórico e processamento permanecem locais/IME.
Armazenar integralmente os dicionários é estudo futuro; respostas usadas precisam de
proveniência e snapshot local para reprodução. Memorial permanece extensão futura.

**Base verificada:** PDF integral localizado no computador (217 páginas), páginas do
Apêndice A examinadas (impressas 161–170; PDF 162–171) e ZIP local de pesquisa reconciliado.
Os [apoios curados](../pesquisa/modulo-03-contexto/README.md) contêm **203 registros
alfanuméricos + 110 auxiliares**, com fonte separada de interpretação, exportações da
mesma revisão e fichas por registro. Essa cobertura documental não equivale a receitas
implementadas, leitura integral de todas as 217 páginas ou equivalência ao XML original.

**Limitações preservadas:** XML/planilha originais de 2025 e fixtures citadas no ZIP ainda
não estão disponíveis. A síntese `sintese-para-felipe.md` da Library não foi materializada
pelo helper oficial nesta plataforma; não se atribuem achados à sua leitura. São tarefas
de desenvolvimento/documentação com impacto delimitado, sem impedir concluir este plano.

**Continuidade:** [M1](modulo-01-dominio-catalogo.md), [M2](modulo-02-nucleo-ifc-ids.md)
e [consolidação congelada](CONSOLIDACAO-2026-10-09.md) conservam seus bytes. O
[índice](README.md) registra a precedência das decisões atuais sobre políticas antigas
de bSDD, responsabilidades e status. A [integração bibliográfica nova de 10/10](#m3-bibliografia)
nos três planos e a [síntese dos 29 artigos](../pesquisa/sintese-bibliografica-daiane-29-artigos.md)
permanecem preservadas. Nenhum desses artigos valida nossa combinação com LLM local.

Esta entrega não altera código, IFC/IDS, configuração, modelo, prompt, GT ou resultado
experimental; não executa inferência, testes funcionais, staging, commit ou push. O planejamento M4 foi autorizado em tarefa separada; o término deste documento não inicia implementação.

**Navegação:** [Escopo](#m3-escopo) · [Decisões](#m3-decisoes) · [Domínio e fontes](#m3-dominio) ·
[Inventário](#m3-inventario) · [Contratos](#m3-contratos) · [Evidência](#m3-evidencia) ·
[Receitas](#m3-receitas) · [Pipeline e orçamento](#m3-pipeline) · [LLM e saída](#m3-llm) ·
[Segurança](#m3-seguranca) · [Interfaces](#m3-interfaces) · [Tarefas](#m3-tarefas) ·
[Testes propostos](#m3-testes) · [Avaliação](#m3-avaliacao) · [Entregas e esforço](#m3-entregas) ·
[Riscos e rollback](#m3-riscos) · [Consolidação e pendências](#m3-revisao) · [Fontes e verificação](#m3-fontes) · [Bibliografia integrada](#m3-bibliografia).

<a id="m3-escopo"></a>

## 1. Objetivo, escopo e limites da versão 0.1

### 1.1 Objetivo e hipótese de trabalho

Produzir propostas de enriquecimento por campo, sustentadas por evidências identificáveis,
ou uma abstenção útil para revisão/BCF, a partir de IFC, IDS pronto e catálogo com
semântica pública bSDD e bindings/receitas curados, fixados por execução.
O módulo não declara verdadeiro um valor por ele ser admissível no catálogo ou satisfazer
o IDS. Também não concede autorização de escrita: isso exige decisão humana e fluxo da
frente 5 sobre uma cópia, com nova revisão e revalidação pelo núcleo da frente 2.

A hipótese aceita para aprofundamento é recuperar e padronizar informação que já existe
no IFC, mas está dispersa, em portadores diferentes ou descrita de forma heterogênea.
O ganho da LLM deve ser quantificado contra regras que recebem a mesma evidência.
Não é hipótese de preenchimento universal de lacunas por conhecimento prévio do modelo.
Uma decisão ausente do projeto pode continuar ausente após todo o processamento.

**Arquitetura proposta:** operações determinísticas coletam/normalizam/calculam; um pacote
comum por elemento e blocos por campo delimitam o contexto; a LLM local interpreta somente
os campos elegíveis; validadores produzem propostas ou abstenções rastreáveis. O baseline
executa **uma inferência por vez**. Elemento, propriedade e grupos são alternativas de
agrupamento a comparar durante o desenvolvimento. Contratos, armazenamento e limites
serão estabilizados por ensaio, sem reabrir aprovação documental do plano.

**Base tecnológica observada:** Python, IfcOpenShell, Pydantic, cliente HTTP Ollama,
cache SQLite e módulos existentes de análise, perfis, grounding e normalização. Reutilizar
essa base é proposta de continuidade; modelo e hardware continuam sem vencedor definido.
Para M4, a decisão posterior de 12/10 fixa React/TypeScript/Vite/shadcn e API Python;
That Open é candidato de visualização a ensaiar. Blender/Bonsai não integra a plataforma.

### 1.2 Dentro do recorte inicial proposto

- Consumir observações e resultados do módulo 2 sem alterar IFC/IDS nem a conformidade emitida.
- Resolver significado, binding e evidência admissível na revisão curada M1 e nas respostas
  públicas bSDD identificadas; sem usar definição de dicionário como fato do elemento.
- Preservar ocorrência, tipo, parte/componente, caminho, unidade, método e revisão da fonte.
- Identificar informação recuperável, normalizável, calculável e indeterminada por campo.
- Reunir campos de um elemento, conservando resultados parciais quando outro campo falhar.
- Permitir alternativas sustentadas; vincular cada alternativa às evidências que a apoiam.
- Permitir preenchimento manual fundamentado e resolução humana de conflito com rechecagens;
  abster-se e encaminhar pendência residual a BCF, inclusive diretamente quando apropriado.
- Fornecer contratos de revisão, auditoria, pendência e avaliação às demais frentes.
- Ampliar o inventário de capacidades pelas dez famílias Daiane, com limites publicados.

### 1.3 Fora do recorte inicial

Não incluir ingestão automática de memorial, OCR de documentos de projeto ou busca em
fontes externas para completar fatos. O humano pode consultar documentos externamente
ao fluxo para tratar uma pendência, sem transformar isso em ingestão automática autorizada.
Autoria IDS, SINAPI operacional, orçamento/preços, geração de geometria ausente, cálculo
estrutural de projeto e decisão autônoma de engenharia continuam fora do escopo inicial.

Não criar um oitavo módulo, novo validador IDS concorrente, viewer Blender/Bonsai, agente
com ferramentas irrestritas ou mecanismo de publicação automática do catálogo. Embeddings
podem ser objeto de estudo local; sua existência não é pré-requisito da primeira fatia.
Treinamento/fine-tuning e arquitetura RAG ampla não integram este plano inicial.

### 1.4 Responsabilidade das sete frentes

| Frente | Papel no fluxo | Fronteira que este plano preserva |
|---|---|---|
| M1 — Domínio/catálogo | Conceitos, bindings, políticas, fontes e versões aprovadas | Curadoria decide significado e publicação; LLM não publica verdade |
| M2 — IFC/IDS | Leitura/verificação, identidade, observações e diagnóstico | Somente leitura; validação suportada independe da LLM/cadastro |
| M3 — Contexto/enriquecimento | Recuperação, cálculo permitido, interpretação e proposta/abstenção | Não escreve IFC nem reclassifica resultado IDS como conforme |
| M4 — UI/3D/revisão | Apresentação por elemento/campo e decisão humana | Seleção visual não substitui evidência nem autorização do serviço |
| M5 — IFC/BCF/revisões | Cópia, escrita autorizada, pendências e comparação | Resolução confirmada em nova revisão, não por aceite isolado |
| M6 — Infraestrutura local/IME | Runtime, armazenamento, acesso, limites e recuperação | Dados/inferência/logs/embeddings permanecem locais/internos |
| M7 — Avaliação científica | Corpus, protocolo, métricas e interpretação dos resultados | Condições versionadas e gabarito independente |

<a id="m3-decisoes"></a>

## 2. Decisões confirmadas, propostas e dependências

### 2.1 Decisões confirmadas e atualizações de 12/10/2026

IDs C3 são preservados, sem renumerar D01–D19. C3-03/10/15/16 recebem a decisão posterior
confirmada em 12/10; o texto anterior permanece no histórico da seção 18. As decisões
novas C3-17–C3-25 tornam explícitos os limites operacionais solicitados, incluindo a
decisão posterior do MVP M4 com dois pares IFC–IDS.

| ID | Confirmação recebida | Consequência vinculante para a proposta |
|---|---|---|
| C3-01 | Entrada inicial IFC + IDS pronto + catálogo | Memorial é futuro; IDS é autoridade do requisito; catálogo não é fonte do valor real |
| C3-02 | Cobertura de domínio das dez famílias A.1–A.10 | Inventário inclui atributos, Psets padrão, materiais, classificações e Qto, além de EB_Orçamento |
| C3-03 | Uma execução LLM por vez no baseline; agrupamento é estudo de desenvolvimento | Comparar elemento, propriedade e grupos, com evidência equivalente e roteamento versionado; não bloquear planejamento pela escolha |
| C3-04 | Campo difícil não bloqueia os demais | Resultado e motivo independentes por campo; pacote pode ser parcial |
| C3-05 | Alternativas precisam de fundamento; resposta cita evidências ou se abstém | Sem obrigar melhor palpite nem usar confiança declarada como autorização |
| C3-06 | Revisão humana antes de escrita em cópia | Toda proposta, inclusive determinística, passa pela porta humana de escrita |
| C3-07 | Lacuna não resolvida segue para BCF; BCF direto é permitido | Decisão de responsável pode dispensar chamada LLM sem perder diagnóstico |
| C3-08 | Rejeitado/pulado não fecha pendência automaticamente | Resolução é verificada em nova revisão IFC, conforme fluxo da frente 5 |
| C3-09 | Dados, inferência, embeddings, evidências e logs locais/IME | Nada do projeto enviado a APIs OpenAI/Anthropic; sem fallback externo |
| C3-10 | API pública bSDD inicialmente; estudo de armazenamento integral local futuro | Consultar só semântica pública aprovada, sem dados de projeto; registrar versão/URI/resposta/hash local. Migração Juliana é curada |
| C3-11 | Catálogo descreve significado/classificação nominal/tipo/grandeza/unidade/domínio, não verdade do valor | Separar admissibilidade semântica de observação do elemento |
| C3-12 | IDs/valores IDS não viram evidência factual | Evitar copiar esperado, identificador ou texto da especificação como resposta |
| C3-13 | Recuperação/padronização de informação dispersa é hipótese central | Comparar regras e regras+LLM sob evidência equivalente |
| C3-14 | Sem Blender/Bonsai; autoria IDS e SINAPI operacional futuros | Não ampliar escopo por conveniência de ferramenta |
| C3-15 | PDF/ZIP locais incorporados e reconciliados nesta consolidação | 203 alfanuméricos + 110 auxiliares, fonte/operacional separados; originais XML/planilha e fixtures ausentes continuam identificados |
| C3-16 | Concluir o planejamento após revisão crítica e verificação documental | Não exigir nova aprovação de Felipe; conclusão documental não é implementação ou validação empírica |
| C3-17 | Conflitos mostram todos os valores e fontes | Responsável escolhe com justificativa; regra de leitura efetiva não decide intenção de projeto |
| C3-18 | Preenchimento manual fundamentado disponível | Revalidar tipo/unidade/IDS/origem antes de aprovação; escrita e resolução continuam separadas |
| C3-19 | Campo não mapeado não impede validação suportada M2 | M3 informa ausência de mapping, permite manual/curadoria; LLM não publica correspondência sozinho |
| C3-20 | Código verifica candidato antes de torná-lo aprovável | Tipo, unidade, restrições IDS, escopo e existência/pertinência da fonte; requisito inadequado pede revisão do requisito |
| C3-21 | Histórico local imutável e depuração | Preservar contexto, fontes, versões, resposta, decisão, erros e tentativas; falha técnica não é ausência de evidência |
| C3-22 | Fila, progresso, cancelamento e resultados parciais explícitos | Preservar determinísticos; reexecução delimitada e sem mutação IFC no M3 |
| C3-23 | Roteamento por propriedade/grupo conforme M7, sustentado por M6 | Nenhum modelo vencedor fixado; seleção/calibração separada da avaliação final e da coleta de evidência |
| C3-24 | Felipe M1/M2/M3/M5; Nonato M4/M6 e liderança M7 com Felipe | Alinhar interfaces; não manter atribuições parciais antigas como vigentes |
| C3-25 | MVP M4 com dois pares IFC–IDS, arquitetura e estrutura, na mesma sessão; visualização federada prioritária | M3 processa cada modelo separadamente, sem evidência cruzada; identidade, diagnóstico e exportação por arquivo. Uma fila LLM serial para a sessão, inclusive retries |

### 2.2 Propostas de implementação a ensaiar

| ID | Proposta técnica | Evidência/decisão necessária antes de estabilizar |
|---|---|---|
| P3-01 | Contexto comum por elemento + blocos por campo | Ensaiar utilidade, isolamento semântico e custo frente ao fluxo por issue |
| P3-02 | Receitas declarativas extensíveis em catálogo | Revisar schema, operações permitidas, precedência e ciclo de publicação |
| P3-03 | Estado de evidência distinto de execução, proposta, revisão e conformidade | Alinhar DTOs com M1/M2 e apresentação M4/M5 |
| P3-04 | Política de conflitos por conceito/componente/revisão | C3-17 fixa decisão humana em conflito; ensaiar critérios de equivalência e apresentação |
| P3-05 | Orçamento por pacote, campo e resposta | Calibrar com tokenizer/modelo/hardware; nenhum limite numérico aprovado |
| P3-06 | Dividir chamadas preservando campos inteiros | Ensaiar fragmentação e custo; mesma base imutável, sem inferência em cascata |
| P3-07 | Validação estrita da saída e referências de evidência | Especificar schema, união discriminada de tipos e semântica da abstenção |
| P3-08 | Persistência transacional local e objetos imutáveis | Definir topologia com M6; não presumir SQLite compartilhado em rede |
| P3-09 | Busca lexical/por bindings antes de considerar embeddings | Demonstrar ganho de recuperação; qualquer índice deve ser local e versionado |
| P3-10 | Nomes de APIs, arquivos novos e tarefas abaixo | Refinar durante desenvolvimento; não são interfaces já existentes ou implementação executada |

### 2.3 Dependências e gates

| Gate | Exigência | O que pode avançar sem ele | O que não pode ser anunciado |
|---|---|---|---|
| G3-01 — Pesquisa incorporada | **Fechado documentalmente nesta consolidação:** PDF/ZIP locais, hashes e matriz reconciliada | Projetar com os registros e limitações publicados | Não anunciar 203 receitas implementadas; fixtures F01–F24 e XML original não vieram no ZIP |
| G3-02 — Domínio operacional reconciliado | Fonte/operacional documentados; obter XML/planilha, resolver divergências com especialista e curadoria antes de publicar a receita afetada | Plano completo e implementação delimitada com fixtures rotuladas | Equivalência integral ao IDS original 2025 ou interpretação divergente já aprovada |
| G3-03 — Catálogo de execução | Revisão curada, bindings/políticas/receitas e snapshot da semântica pública utilizada | Ensaios isolados e manual fundamentado, sem publicar mapping implícito | Enriquecimento automático de campo não mapeado ou bSDD como prova de valor |
| G3-04 — Evidência M2 | Identidade/observações/capacidades rastreáveis para o escopo | Adaptadores/contratos testáveis de forma isolada | Fonte achatada tratada como evidência completa |
| G3-05 — Runtime local | Endpoint, ativos, armazenamento e política institucional ensaiados | Especificação de runtime e testes com substitutos locais | Garantia de operação offline baseada só em default localhost |
| G3-06 — Revisão/escrita/BCF | Contratos M4/M5, vínculo de decisão e revalidação demonstrados | Geração de propostas sem escrita | Fluxo operacional fechado ou BCF interoperável certificado |
| G3-07 — Condição científica | Corpus, splits, gabarito, modelos/parâmetros e protocolo fixados | Instrumentação e piloto separado | Ganho científico generalizável ou comparação com v7.8 equivalente |

<a id="m3-dominio"></a>

## 3. Domínio Daiane, fontes verificadas e cobertura por registro

### 3.1 Proveniência e reconciliação

O [README dos apoios](../pesquisa/modulo-03-contexto/README.md) registra nomes, hashes,
páginas e alcance da inspeção. O PDF local de 217 páginas e o ZIP de nove membros
foram encontrados em Downloads; não foi necessário repetir o download do ZIP.
As dez páginas A.1–A.10 foram examinadas e as linhas confrontadas com a matriz JSON/CSV.
O conteúdo original da pesquisa fica preservado em `source_matrix_original` no JSON
canônico, distinto das notas de correção e dos contratos operacionais propostos.

As contagens **195/88/34** permanecem históricas nos planos anteriores. A revisão atual
conta 203 registros alfanuméricos por família, dos quais 136 são propriedades/quantidades:
82 personalizados + 36 padrão + 18 Qto. Os outros são 10 entidades, 28 atributos,
10 materiais e 19 grupos de classificação (58 pares código/nome). Há 72 nomes lexicais
distintos e 85 pares conjunto/nome; não são 72/85 conceitos semanticamente curados. Essas contagens usam
`target_identifier_literal`; os rótulos completos com tradução explicativa produzem
79 textos e 90 pares conjunto/rótulo. A diferença é de apresentação, não sete conceitos novos.
A condição USERDEFINED de A1 foi desdobrada pela pesquisa em A1-007: agrupá-la novamente
à célula anterior produz 202 linhas agrupadas, sem invalidar os 203 IDs conservados.

Somam-se **50 metadados, 50 requisitos geométricos e 10 registros documentais**:
**313 registros de planejamento**. Isso não mede especificações do XML original ausente,
chamadas LLM, propriedades únicas nem capacidades implementadas. Cobertura de fonte
completa pode coexistir com abstenção em todos os campos sem evidência.

### 3.2 Fonte fiel, catálogo operacional e projeções da mesma revisão

| Artefato | Função e invariantes |
|---|---|
| [Matriz canônica JSON](../pesquisa/modulo-03-contexto/matriz-canonica.json) | Fonte literal, notas e operação separados; pesquisa original preservada; IDs, páginas, canais, papéis, limites, tarefas e cenários individuais |
| [CSV de revisão](../pesquisa/modulo-03-contexto/matriz-revisao.csv) | Mesmos 313 IDs/revisão, com células estruturadas JSON para evitar perda de listas/rotas; não é outra base editável independente |
| [Fichas por registro](../pesquisa/modulo-03-contexto/fichas-apendice-a.md) | Leitura humana por família e propriedade, origem, busca, unidades, rotas e negativos; não só EB_Orçamento |
| [Regras de interpretação e divergências](../pesquisa/modulo-03-contexto/README.md) | Canais IFC explícitos, limites de transformação, distinções fonte/contrato, auditoria dos denominadores |

Cada registro alfanumérico tem receita `REC3-<ID>` em estado **planning**, significado,
aplicabilidade, papel do componente, procura literal e por binding, caminhos IFC de
ocorrência/tipo/materiais/partes/relações, unidade/tipo e transformações permitidas.
Também explicita recuperação determinística, interpretação LLM quando elegível,
manual fundamentado, abstenção, conflito e revisão de requisito inadequado.
Todos têm tarefas e critérios individuais; as receitas documentadas não estão publicadas
no runtime. Metadados/geometria/documentação têm finalidade e capacidade delimitadas.

### 3.3 Dez famílias e perguntas de evidência

| Família | Alfanuméricos + auxiliares | Contexto e limite principal |
|---|---:|---|
| [A.1 Janela](../pesquisa/modulo-03-contexto/fichas-apendice-a.md#a1) | 24 + 11 | IfcWindow/WINDOW; vidro, caixilho, peitoril; fills/voids até hospedeiro. Vidro não herda material do caixilho; vão não é marco |
| [A.2 Porta](../pesquisa/modulo-03-contexto/fichas-apendice-a.md#a2) | 28 + 11 | IfcDoor/DOOR; folha/marco/tipo, OperationType, dimensões e ferragens. Densidade_Porta é massa superficial na explicação B, não densidade volumétrica |
| [A.3 Parede](../pesquisa/modulo-03-contexto/fichas-apendice-a.md#a3) | 26 + 11 | IfcWall; camadas, partes, vãos, função declarada, espaços/limites. Contagem global de pilares não determina LoadBearing |
| [A.4 Forro](../pesquisa/modulo-03-contexto/fichas-apendice-a.md#a4) | 22 + 11 | IfcCovering/CEILING; suporte, material, suspensão e composição. Pset_DoorCommon da fonte fica literal, divergência aberta na operação |
| [A.5 Piso](../pesquisa/modulo-03-contexto/fichas-apendice-a.md#a5) | 19 + 11 | IfcCovering/FLOORING; acabamento e camadas. Área aproximada não prova área líquida/consumo |
| [A.6 Revestimento](../pesquisa/modulo-03-contexto/fichas-apendice-a.md#a6) | 24 + 11 | IfcCovering/CLADDING; parede/espaço relacionado e papel de cada camada. Código da fonte conferido: 3E.14.02.04 |
| [A.7 Laje](../pesquisa/modulo-03-contexto/fichas-apendice-a.md#a7) | 18 + 11 | IfcSlab/FLOOR; tipo, volume, material, espessura e fôrmas. Área de fôrma não é área de piso por igualdade de unidade |
| [A.8 Pilar](../pesquisa/modulo-03-contexto/fichas-apendice-a.md#a8) | 16 + 11 | IfcColumn; perfil, seção, partes e material. Peso agregado do hospedeiro não é peso de barra |
| [A.9 Viga](../pesquisa/modulo-03-contexto/fichas-apendice-a.md#a9) | 17 + 11 | IfcBeam; seção, eixo, comprimento, partes e Qto. Altura geométrica global não substitui dimensão de seção rotacionada |
| [A.10 Armadura](../pesquisa/modulo-03-contexto/fichas-apendice-a.md#a10) | 9 + 11 | IfcReinforcingBar; diâmetro/comprimento/quantidade e representação. Uma entidade pode representar um conjunto; não ratear peso sem método e multiplicidade |

IFC2X3, IFC4 e IFC4.3 são metas por **release e capacidade testada**, não suporte anunciado
por existir classe ou receita genérica. Os canais detalham relações explícitas e guardas;
espaço no mesmo pavimento, texto semelhante e proximidade não substituem vínculo comprovado.

### 3.4 Divergências e achados com impacto no desenvolvimento

As [divergências curadas](../pesquisa/modulo-03-contexto/README.md#divergencias) incluem
`Heigth`, Weight/Weigth, tipos Label/Integer/Real/Measure, IfcQuantityArea em Pset,
Usos_Forma e Area_Forma, Densidade_Porta e aplicabilidades diferentes entre A/B.
Nunca corrigir o literal de origem silenciosamente, nem deixar a LLM arbitrar o contrato.
Admissibilidade semântica, exigência IDS e evidência do elemento são eixos independentes.

Páginas impressas 90–91 mostram decisões de janela que podem estar ausentes do modelo;
p. 100 descreve defaults FALSE/0/A definir para preenchimento posterior; pp. 124–125/131
distinguem peso no hospedeiro e Weight faltante nas barras. Esses trechos foram consultados
no PDF local, mas não demonstram que toda ocorrência de FALSE/0 é placeholder ou que toda
barra admite cálculo por massa típica. Os negativos das fichas transformam esses limites
em critérios futuros, preservando valores falsos/zero legítimos.

### 3.5 Fontes ainda ausentes e efeito limitado

XML IDS/planilha auditável originais de 2025 precisam de obtenção/reconciliação na M3-01/M3-20;
o pacote público 2026 de seis famílias/Cost_Prop não os substitui. A pesquisa cita fixtures
F01–F24 cujo arquivo não veio no ZIP: são referências históricas, não testes disponíveis.
A Library `libfile_030b0f9c3b60819182f3de320e3ed7a5` continua referência metodológica pendente
de acesso suportado, nunca ground truth. A falha do helper Windows foi registrada nos
apoios; não impede usar as fontes locais nem exige nova aprovação para fechar o plano.

### 3.6 Dissertações já estudadas como fontes revisáveis

O encaminhamento recebido em 12/10 situa **Daiane** como contrato informacional das
dez famílias; **Farias** como caso a revisitar de requisito `IsExternal` mal aplicável;
e **Rebeca/Larissa** como fontes dos fatores que afetam orçamento. Esta retomada não
atribui páginas, resultados ou transcrições novas às três últimas fontes: seus trechos
deverão ser recuperados e identificados antes de usá-los como evidência empírica.

M3-01/M3-20 registram origem/versão e revisam aplicabilidade; M3-26/CT3-78 preservam
o caso de requisito inadequado sem forçar alteração IFC. Fatores de orçamento orientam
significado, componente e informação necessária, sem converter custo típico, catálogo
ou prática usual em valor real. M3-21/CT3-40/64/72 exigem referência independente:
dissertações fornecem fontes e casos revisáveis, nunca gabaritos automáticos. Essa
conferência futura não reabre a conclusão documental nem amplia o escopo para orçamento.

<a id="m3-inventario"></a>

## 4. Inventário estático e estratégia de reaproveitamento

### 4.1 Evidência do checkout

O inventário abaixo parte da análise estática anterior recebida no handoff e do rascunho
local preexistente. Nesta complementação foram relidos os trechos pertinentes de extração,
análise/pipeline, materiais/quantidades, grounding, cache, parser e BCF. As localizações
servem à revisão do checkout; não são resultados de execução. Comentários históricos de
código sobre benchmarks não foram reproduzidos nem transformados em novos resultados.

| ID | Componente existente e localização | Reaproveitamento e lacuna concreta |
|---|---|---|
| I3-01 | [analyzer.py](../../src/ifc_analyzer/analyzer.py), 149–196 e 270–335; [pipeline.py](../../src/pipeline.py), 183–240 | analyze_from_ids enriquece por regra/universal; pipeline integra IDS por outro caminho. Unificar consumidores sem afirmar que todas as issues hoje recebem contexto rico |
| I3-02 | analyzer.py, 174–190 | Cache local à chamada por issue; reutilizar mecanismo, mas coletar por revisão/elemento/operação para não repetir varreduras por campo |
| I3-03 | [universal_extractor.py](../../src/ifc_analyzer/universal_extractor.py), 98–131 | Atributos e resumo Psets úteis; corta 15 conjuntos/20 propriedades e remove IDs, sem seleção por relevância ou proveniência |
| I3-04 | universal_extractor.py, 192–209 | Qto achatado em geometry; nomes homônimos podem sobrescrever valores e perder conjunto/método/unidade |
| I3-05 | [material_reader.py](../../src/ifc_analyzer/material_reader.py), 106–200 e 203–226 | Camadas, constituintes e partes são base; associação por ordem/nome é heurística; primeira parte não representa agregado heterogêneo; perfis não plenamente tratados |
| I3-06 | universal_extractor.py, 133–190 | Leitura paralela de materiais difere do leitor compartilhado; constituintes viram layers sem espessura recuperada; unificar por observações, preservando papel |
| I3-07 | [quantity_extractor.py](../../src/ifc_analyzer/extractors/quantity_extractor.py), 34–154 e 231–270 | Qto por classe e bounding box úteis; método declarado/calculado não fica na saída; não há rota especializada Covering/ReinforcingBar |
| I3-08 | [classification_extractor.py](../../src/ifc_analyzer/extractors/classification_extractor.py), 90–105 e 195–220 | Associação direta/primeira classificação; ampliar sem perder múltiplas fontes, herança, hierarquia e edição |
| I3-09 | [relation_diagnostics.py](../../src/ifc_analyzer/relation_diagnostics.py), 56–140 | Índices fills/voids/contenção reaproveitáveis; nearby_spaces usa mesmo/primeiro pavimento, não proximidade comprovada |
| I3-10 | [model_evidence.py](../../src/ifc_analyzer/model_evidence.py), 29–67 | Contagens Column/Beam compartilhadas; exceção vira zero e texto perde estado/origem. Contagem contextual não prova função portante de elemento |
| I3-11 | [pset_diagnostics.py](../../src/ifc_analyzer/pset_diagnostics.py), 208–234; universal_extractor.py, 98–106 | Legado busca PredefinedType no tipo, universal lê direto. get_psets combina ocorrência/tipo; origem por valor precisa ser explícita |
| I3-12 | [rule_generator.py](../../src/translator/rule_generator.py), 274–339; [profiles/registry.py](../../src/profiles/registry.py), 23–93 | required_context por palavras-chave e perfis não são receitas aprovadas; nomes não suportados podem ser ignorados |
| I3-13 | [grounding.py](../../src/suggestion_engine/grounding.py), 129–258; [thermal_extractor.py](../../src/ifc_analyzer/extractors/thermal_extractor.py), 175–197 | thickness_m/total_thickness versus total_thickness_m; existing_psets versus all_psets; laje devolve material/thickness. Adaptadores precisam eliminar perdas de contrato |
| I3-14 | [suggestion.py](../../src/suggestion_engine/suggestion.py), 107–341 e 483–558; [worker.py](../../src/suggestion_engine/worker.py), 74–185 | Geração por issue e cópia por equivalência, não chamada com vários campos de um elemento; métricas/fila são reaproveitáveis |
| I3-15 | [ollama_client.py](../../src/suggestion_engine/ollama_client.py), 64–127; [config.py](../../src/config.py), 24–70 | Há estimativa e limites; ao exceder teto o cliente registra e envia. Defaults 4096/8192/768 são históricos, não budgets aprovados para M3 |
| I3-16 | [prompt_templates.py](../../src/suggestion_engine/prompt_templates.py), 142–150 e 1824–1886; [models.py](../../src/models.py), 174–196 | Contrato pede valor mesmo sem candidato confiável; parser não preserva action=abstain. Saída por campo exige novo schema/validação |
| I3-17 | [suggestion_cache.py](../../src/suggestion_engine/suggestion_cache.py), 27–60; suggestion.py, 358–441 | Cache não fixa todas as revisões/políticas/evidências; reutilização precisa identidade completa e isolamento entre projetos |
| I3-18 | [bsdd/context_builder.py](../../src/bsdd/context_builder.py), 112–202; [contracts.py](../../src/foundation/contracts.py), 25–43 | Builder usa wrappers legados além do protocolo; cliente tem acesso público. API pública sem conteúdo de projeto é a política inicial; adaptar contrato, snapshots e filtro de saída explicitamente |
| I3-19 | [locality.py](../../src/foundation/locality.py), 61–84; pipeline.py, 110–136 | Política existe, mas pipeline instancia clientes diretamente. Enforcement transversal ainda não demonstrado |
| I3-20 | [review.py](../../src/foundation/review.py), 39–60; pipeline.py, 401–452 | Modelo de decisão é base; fluxo legado usa string e metadados de top_suggestion. Vincular decisão à proposta/valor/revisão escolhidos |
| I3-21 | [bcf/exporter.py](../../src/bcf/exporter.py), 84–98 | Todo estado não pending vira Closed; faltam pendência residual, fundamento e confirmação em nova revisão |
| I3-22 | [semantic/property_match.py](../../src/semantic/property_match.py), 19–53; [pset_resolver.py](../../src/translator/pset_resolver.py), 83–115 | Matching/aliases ajudam descoberta, mas não provam equivalência de conceito nem satisfação do caminho exato IDS |

A análise anterior relata leitura de `ifcopenshell.util.element`: `get_psets` usa
herança por padrão e combina o tipo com a ocorrência; `get_quantities` retorna valores
brutos. Esse relato ajuda a explicar os chamadores, mas não certifica a versão instalada
nesta entrega nem dispensa ensaios de unidades, schema e portadores na implementação.

### 4.2 Continuidade e isolamento do baseline

Reutilizar coletores, normalizadores e telemetria por adaptadores que produzam observações
tipadas. Não mudar silenciosamente funções usadas nas rodadas históricas para servir ao
novo fluxo. `PROMPT_VERSION v7.8` e pinos de distribuição, GTs, comparadores, dados e resultados
ficam congelados como baseline. Uma nova condição será identificada quando implementar
contexto/receita/catálogo/unidade de chamada distintos, mesmo sem mudar o texto do prompt.

Sugestões determinísticas existentes de IsExternal/LoadBearing são candidatos a revisão,
não regras de engenharia automaticamente ratificadas por este documento. Recomputação
térmica executa aritmética fora da LLM, mas precisa também validar a origem de espessuras,
condutividades e resistências; conta correta com termo inventado continua sem fundamento.

O [baseline auditado](../pesquisa/modulo-03-contexto/baseline.md) registra a pesquisa de
modelos/contextos já existente e seus resultados brutos. Isso evita pressupor ausência de
experimentos e evita tomar resultados anteriores como validação da nova arquitetura.

### 4.3 Organização física proposta

| Caminho proposto | Responsabilidade | Limite |
|---|---|---|
| `src/enrichment/contracts.py` | DTOs novos e envelopes por elemento/campo | Referenciar tipos comuns M1/M2; não duplicar identidades incompatíveis |
| `src/enrichment/evidence.py` | Seleção, proveniência, estados e conflitos de evidência | Não abrir arquivo por campo nem implementar segundo verificador |
| `src/enrichment/operations.py` | Registro de operações aprovadas e composição determinística | Sem eval/exec, SQL ou código cadastral arbitrário |
| `src/enrichment/recipes.py` | Resolver/validar receita do release fixado | Não editar/publicar catálogo operacional |
| `src/enrichment/context.py` | Pacote comum e blocos por campo | Produzir manifesto do incluído/omitido |
| `src/enrichment/budget.py` | Medir recursos e planejar chamadas | Não truncar silenciosamente nem fixar thresholds sem ensaio |
| `src/enrichment/response.py` | Parse estrito, validação e resultado por campo | JSON válido não é validade semântica |
| `src/enrichment/service.py` | Orquestração, resultados parciais e cancelamento | Sem writer IFC ou resolução automática de BCF |
| `src/enrichment/storage.py` | Repositório de execuções/artefatos/cache pela política M6 | Escolha física depende da revisão de infraestrutura |
| `tests/enrichment/` | Contratos, negativos, integração e contrafactuais | Pasta futura; nenhum teste criado/executado nesta redação |
| [docs/pesquisa/modulo-03-contexto/](../pesquisa/modulo-03-contexto/README.md) | Apoios documentais desta consolidação | Matriz e fichas existentes; implementação e fixtures funcionais continuam futuras |

Os caminhos de código/testes são propostas; o diretório documental acima já existe. Pode-se mantê-los dentro de
`suggestion_engine` se a revisão técnica preferir; a decisão deve preservar as fronteiras,
compatibilidade explícita e ausência de duplicação de M1/M2. Não fazer refatoração ampla
de código, UI ou armazenamento apenas para corresponder aos nomes deste plano.

<a id="m3-contratos"></a>

## 5. Contratos ilustrativos e identidade

### 5.1 Reutilização dos contratos M1/M2

Consumir `CatalogReleaseRef`, `ConceptDefinition`, `IFCBinding`, `EvidencePolicy`,
`OperationCapability` e `ResolutionResult` do [desenho M1](modulo-01-dominio-catalogo.md#m1-interfaces).
Consumir `AnalysisIdentity`, `ElementRef`, `EvidenceObservation`, `RequirementResult`,
`TechnicalProblem` e `DiagnosticSnapshot` do [desenho M2](modulo-02-nucleo-ifc-ids.md#m2-dados).
São contratos propostos nesses planos; sua citação não afirma implementação existente.

`ElementRef` combina revisão IFC e localizador da entidade naquela revisão, com GlobalId
opcional e estado do GUID. Não usar nome, GUID isolado ou STEP ID entre revisões como chave
de identidade suficiente. No MVP com dois pares IFC–IDS, `PairRef`/arquivo/revisão
integram a identidade, mesmo com GlobalId ou STEP ID iguais nos dois arquivos. `SessionRef`
apenas reúne navegação/fila; não autoriza compartilhar evidência, tipo, material, relação
ou cache de inferência entre pares. Uma execução M3 referencia o snapshot M2 exato e acrescenta
identidade de catálogo/receitas/operações/contexto/runtime; não sobrescreve a análise M2.

### 5.2 Objetos propostos e invariantes

| Objeto | Conteúdo mínimo | Invariante |
|---|---|---|
| `EnrichmentIdentity` | run ID M3, analysis/run ID M2, hash do snapshot, catálogo/pin, contexto/condição e build | Qualquer mudança relevante produz nova identidade, preservando histórico |
| `FieldRef` | ID local, ElementRef, requirement IDs, conceito/binding alvo, portador/caminho | Múltiplos requisitos do mesmo campo permanecem rastreáveis; conflito não colapsa |
| `ObservationRef` | ID/hash da EvidenceObservation M2 ou derivada M3 | Referência resolvível na análise, com ACL; ID não comprova conteúdo sozinho |
| `DerivedObservation` | Entradas, operação/versão, parâmetros, unidades, resultado e estado | Grafo acíclico; valor calculado não vira observação declarada no IFC |
| `EvidenceAssessment` | Admissíveis/rejeitadas, suficiência, conflitos, motivos e política | Suficiência é avaliada por campo, não por existência de grounding |
| `RecipeRef` | ID/versão/hash e EvidencePolicy, operações/capacidades requeridas | Receita publicada precisa apontar para capacidades efetivamente disponíveis |
| `CommonElementContext` | ElementRef, tipo, atributos selecionados, relações e evidências compartilhadas | Referências de navegação distinguem-se de evidências que autorizam inferência |
| `FieldEvidenceBlock` | FieldRef, requisito, semântica, observações, conflitos e ações admissíveis | Expected IDS e definição do catálogo ocupam papéis diferentes de observações |
| `ElementContextPackage` | Identidade, comum, blocos, manifesto/hash de seleção | Pacote imutável; campos omitidos/inelegíveis aparecem com motivo |
| `CallPlan` | Chamadas planejadas, campos por chamada, tokenização, reservas e limites | Sem campo perdido/duplicado silenciosamente; agrupamento/rota e execução serial identificados |
| `RuntimeIdentity` | Modelo/digest, tokenizer/chat template, servidor, quantização, parâmetros e hardware relevante | Alias de modelo sozinho não identifica o instrumento |
| `FieldAlternative` | ID, valor tipado/unidade, método, evidências, justificativa curta e limitações | Nenhum efeito de escrita; alternativa é proposta, não fato do IFC |
| `FieldEnrichmentResult` | Campo, estado, alternativas, abstenção/motivo, erros técnicos e tentativa | Ausência de valor pode ser resultado válido; falha técnica não é abstenção de domínio |
| `ElementEnrichmentResult` | Pacote/CallPlan, resultados por campo, cobertura e estado agregado | Campo terminal não desaparece quando outro falha |
| `EnrichmentRun` | Identidade, estado, eventos, resultados e métricas | Retomada idempotente e entradas fixadas; resultados antigos imutáveis |
| `ReviewEnvelope` | Proposta/alternativa exata, valores exibidos, evidências, revisões, ator e decisão | Aprovação anterior não migra automaticamente para outra revisão |
| `ResidualRequest` | Campo/diagnóstico, motivo, informação necessária, responsáveis candidatos e vínculos | Pendência pode ser criada sem LLM; fechar depende do ciclo M5/M2 |
| `EnrichmentReceipt` | Identidade/hash dos resultados e exportação local, completude/limitações | Artefato não substitui decisão humana ou revalidação |

`TypedValue` segue a união discriminada proposta em M2: booleano, inteiro, decimal,
string, enum/código, data/hora, referência ou coleção tipada. Preservar tipo IFC e
valor original separadamente. Unidade desconhecida não vira adimensional; enum numérico
em string não vira número por conveniência. Arrays de alternativas não misturam tipos
incompatíveis com o conceito sem uma divergência explícita de reconciliação.

### 5.2.1 Complementos obrigatórios de contrato

Acrescentar à identidade ilustrativa os snapshots da semântica bSDD efetivamente usados
(URI/release ou data quando release não existir, resposta/hash), `RoutingPolicyRef` e
modelo/parâmetros de cada chamada. `CallPlan` não contém execução simultânea no baseline.
As definições de wire format serão fechadas na implementação; nenhuma chave de exemplo
abaixo é API de produção pronta.

`ManualCandidate` proposto contém FieldRef, caminho/portador literal, valor bruto/tipado,
unidade, ator, justificativa, origem humana/documental declarada, referência persistida
do fundamento e revisão. Quando o catálogo não mapeia o campo, `concept_id` pode ser
ausente: M2/IDS sustentam a validação literal; esse ato não cria mapping de M1.
`CandidateValidation` registra separadamente tipo, unidade, IDS, origem existente,
pertinência e resultado, com erros/limites. Somente resultado satisfatório habilita aprovação.
Uma declaração humana registrada é uma fonte humana identificada, não prova automática
de exatidão e não observação extraída do IFC. Documento não é ingerido automaticamente.

`RequirementReviewRequest` guarda requisito/versão, incompatibilidade, evidência e ator,
sem mudar requisito ou IFC. `unmapped` e `needs_requirement_review` são razões/categorias
separadas da falha de execução: não confundir com conformidade M2 ou recurso não suportado.
Valor que satisfaz IDS pode seguir sem evidência suficiente; nesse caso não fica aprovável
como enriquecimento fundamentado. Tipo/unidade corretos também não provam engenharia.

### 5.3 API de referência, sem implementação

As assinaturas são proposta de fronteira para revisão. `EnrichmentRequest` referencia
snapshot, seleção de FieldRefs, pin e opções permitidas; `Actor` vem da autorização M6;
`EnrichmentHandle` contém run ID; `EnrichmentQuery` filtra/pagina; `EnrichmentPage` retorna
resultados/cursor; `CancelReceipt` acusa recebimento e não promete parada imediata.

```python
class EnrichmentService:
    def start(self, request: EnrichmentRequest, actor: Actor) -> EnrichmentHandle: ...
    def get_run(self, run_id: str, actor: Actor) -> EnrichmentRun: ...
    def query_results(self, run_id: str, query: EnrichmentQuery, actor: Actor) -> EnrichmentPage: ...
    def get_context(self, run_id: str, element: ElementRef, actor: Actor) -> ElementContextPackage: ...
    def cancel(self, run_id: str, actor: Actor) -> CancelReceipt: ...
    def export_results(self, run_id: str, actor: Actor) -> EnrichmentReceipt: ...
```

O serviço usa o reader fixado M1 e a sessão/observações M2. Acesso adicional à fonte IFC
deve passar por operação de leitura versionada com proveniência, sem contornar a identidade
da sessão e do par IFC–IDS. Não reconstruir contexto lendo um caminho que agora aponta para outra revisão.
O endpoint não recebe instruções arbitrárias, URL de modelo livre ou comando de shell.

### 5.4 Exemplo JSON sintético de resultado parcial

Exemplo de forma, **não executado, não publicável e sem equivalência Daiane afirmada**.
IDs `demo-*` e hashes nulos identificam ilustração; schema de produção exigirá referências
resolvidas/hashes reais antes de permitir processamento. O campo de abertura do exemplo
nunca é reutilizado como dimensão externa de marco.

```json
{
  "format_version": "draft-0.1",
  "illustrative_only": true,
  "identity": {
    "enrichment_run_id": "demo-enrichment-1",
    "analysis_run_id": "demo-analysis-1",
    "diagnostic_snapshot_sha256": null,
    "catalog": {"catalog_id": "demo-local", "version": "draft", "sha256": null},
    "context_version": "m3-draft-0.1",
    "condition_id": "demo-condition"
  },
  "element": {
    "ifc_revision_id": "demo-ifc-rev-1",
    "express_id": 42,
    "global_id": null,
    "global_id_state": "missing",
    "ifc_class": "IfcDoor"
  },
  "common_observation_ids": ["demo-obs-material-leaf"],
  "observations": [
    {
      "observation_id": "demo-obs-opening-width",
      "value_state": "present",
      "typed_value": {"kind": "decimal", "value": "900"},
      "unit": "mm",
      "origin_scope": "occurrence",
      "component_role": "opening",
      "source_path": "Demo_Set.OpeningWidth",
      "method": "declared_property"
    },
    {
      "observation_id": "demo-obs-material-leaf",
      "value_state": "present",
      "typed_value": {"kind": "string", "value": "madeira"},
      "unit": null,
      "origin_scope": "occurrence",
      "component_role": "leaf",
      "source_path": "Demo_Set.LeafMaterial",
      "method": "declared_property"
    }
  ],
  "fields": [
    {
      "field_id": "demo-field-opening-width",
      "requirement_ids": ["demo-req-opening-width"],
      "state": "proposed",
      "alternatives": [
        {
          "alternative_id": "demo-alt-1",
          "typed_value": {"kind": "decimal", "value": "0.900"},
          "unit": "m",
          "method": "unit_conversion",
          "operation_ref": "demo-mm-to-m-v1",
          "evidence_ids": ["demo-obs-opening-width"],
          "justification": "Conversão da largura declarada da abertura, preservando seu papel."
        }
      ],
      "human_review_required": true
    },
    {
      "field_id": "demo-field-fixing-method",
      "requirement_ids": ["demo-req-fixing-method"],
      "state": "abstained",
      "alternatives": [],
      "reason_code": "responsible_design_decision_required",
      "missing_information": ["Método de fixação confirmado pelo responsável"],
      "llm_called": false,
      "residual_request_ref": "demo-residual-1"
    }
  ],
  "write_authorized": false
}
```

O exemplo não é payload direto de escrita nem resposta que o modelo possa usar para
atribuir `write_authorized=true`. Esse campo ilustra estado do serviço. O contrato LLM
será menor e aceitará apenas IDs/valores/motivos autorizados pelo CallPlan. Revisão e
aplicação são objetos externos à resposta; a decisão humana não vem de uma string da LLM.

<a id="m3-evidencia"></a>

## 6. Ciclo de evidência por campo

### 6.1 Cinco planos de estado separados

| Plano | Estados/conteúdo propostos | O que não significa |
|---|---|---|
| Verificação M2 | Conforme, não conforme, não aplicável, não verificado, erro | Não é confiança da LLM nem disponibilidade de proposta |
| Observação | Presente, ausente, nulo, vazio, inválido, não suportado, erro, conflitante | Presente não prova autenticidade ou suficiência; zero/falso não são ausência |
| Evidência para o campo | Suficiente para operação determinada, parcial, insuficiente, conflitante, indisponível | Não é nota universal; depende de receita, componente e revisão |
| Enriquecimento M3 | proposed, abstained, unsupported, failed, cancelled, not_requested | proposed não aprova escrita; failed não deve virar abstenção de domínio silenciosa |
| Revisão/aplicação M4/M5 | Pendente, aceito, editado, rejeitado, pulado; aplicação/revalidação separadas | Aceite/rejeição/pulo não confirma resolução na nova revisão IFC |

Os nomes em inglês são proposta de wire format, não vocabulário aprovado de interface.
Um campo pode estar não conforme no IDS, ter evidência parcial e resultar em abstenção.
Outro pode ter alternativa correta, aceita por humano, mas escrita/revalidação ainda pendentes.
Uma incompatibilidade de schema não deve ser apresentada como falta de decisão de projeto.

### 6.2 Percurso de uma observação até uma proposta

1. Identificar o alvo e os requisitos, preservando caminho literal, localização IDS e ElementRef.
2. Resolver conceito/binding/receita no catálogo fixado, conservando candidatos ambíguos.
3. Solicitar observações M2 e operações adicionais de leitura necessárias e suportadas.
4. Verificar origem, revisão, tipo/ocorrência/parte e papel do componente observado.
5. Preservar valor bruto e construir valor tipado; unidades/conversões registradas separadamente.
6. Avaliar suspeitas de placeholder, inconsistência, duplicação e informação conflitante.
7. Classificar o caso: recuperação exata, mapeamento aprovado, padronização, cálculo,
   interpretação contextual delimitada, falta de capacidade ou decisão humana necessária.
8. Produzir alternativa determinística quando a operação é suficiente; quando apropriado,
   preparar bloco LLM com evidências admissíveis e ações restritas àquele campo.
9. Validar saída, referências, tipos, unidades e aplicação das pré-condições da receita.
10. Persistir proposta/abstenção e cobertura; encaminhar à revisão ou pendência residual.

Não substituir o fato observado pelo valor desejado. A LLM pode interpretar descrições
heterogêneas somente quando isso preserva o conceito e o papel; não pode decidir um detalhe
construtivo ausente para satisfazer requisito. A decisão humana que consultar fonte externa
precisa indicar seu fundamento no fluxo de revisão, sem atribuí-lo retroativamente ao IFC.

### 6.2.1 Manual, campo não mapeado e requisito inadequado

Quando não houver proposta suficiente, o operador pode preencher manualmente com
fundamento explícito, ou solicitar curadoria/decisão externa. M3 registra a origem humana
e executa as mesmas barreiras de tipo, unidade, aplicabilidade e restrições IDS. Fonte
precisa resolver para registro local existente e ser pertinente ao componente/revisão;
um ID de evidência inventado ou a definição de um dicionário não satisfaz esse teste.

Falta de mapping não impede M2 validar requisito suportado. M3 mostra `unmapped`, permite
manual com alvo literal tipado e abre demanda curatorial; se nem o portador/tipo puder ser
verificado, conserva `unsupported` e não oferece bypass. LLM pode sugerir correspondência
para curadoria, nunca publicá-la. Se o requisito for incompatível com o elemento real,
usar `needs_requirement_review` e justificar; não ajustar o IFC para satisfazer uma
exigência inadequada. Alterar IDS futuramente produz nova versão/análise, não apaga a falha.

Todo manual validado ainda passa por decisão humana M4, escrita em cópia M5 e revalidação
M2. Até então permanece candidato/aprovação/aplicação pendente, sem resolução antecipada.
BCF residual é permitido após essas tentativas e diretamente quando a decisão está fora
do escopo do operador; não tornar preenchimento ou LLM uma etapa obrigatória para exportar.

### 6.3 Origem, herança e conflitos

Política confirmada C3-17: antes de chamar algo de conflito, conferir se os valores
tratam do mesmo conceito, componente, qualificador, unidade compatível e revisão. Larguras
da abertura e do marco são fatos distintos. Materiais de vidro e caixilho não são alternativas
concorrentes para um campo que pede exclusivamente material do vidro.

Ocorrência e tipo devem ser registrados separadamente, junto ao valor efetivo interpretado
pelo schema/backend quando aplicável. A precedência técnica pode resolver a leitura formal,
sem apagar o valor divergente e sem decidir que a intenção de projeto do tipo é incorreta.
Se a receita exige um valor confiável e a divergência permanece, o enriquecimento se abstém
ou oferece alternativas sustentadas e claramente incompatíveis para decisão humana.

Não usar ordem de dicionário, primeira parte agregada, primeira classificação, nome mais
parecido ou maior confiança autodeclarada como precedência técnica. O conjunto de políticas
permitidas e sua aplicabilidade precisam da revisão de Felipe/especialista e da curadoria M1.
Quando não houver política aplicável, retornar motivo explícito em vez de decidir por default.
Em conflito, mostrar todos os valores e fontes ao responsável; sua escolha exige justificativa.
A precedência formal de leitura não elimina essa decisão nem transforma uma fonte em verdade.

### 6.4 Materiais, quantidades e relações

Para materiais, registrar associação IFC, entidade material, conjunto/uso, componente,
posição de camada quando declarada, perfil ou constituinte e origem no tipo/ocorrência/parte.
Frações de constituintes não equivalem a espessuras de camadas. Uma ordenação atribuída pelo
exportador é hipótese de leitura que precisa de evidência específica, não invariante universal.
Papéis como glass, frame, sill, leaf e host devem ter origem ou estado desconhecido.

Qto deve conservar nome de conjunto, quantidade, portador IFC, tipo de medida, unidade
explícita/efetiva, método quando disponível e escopo. Um valor derivado de geometria leva
configuração, unidade, revisão e método de cálculo; bounding box não se apresenta como
área líquida, área de forma ou volume líquido sem operação validada para essa finalidade.
Precisão/tolerância dependem da operação e serão calibradas por capacidade durante desenvolvimento.

Relações comprovadas incluem referências às entidades de relação e aos extremos. Relações
candidatas, adjacências inferidas e elementos do mesmo pavimento devem ter categoria distinta.
Traversal usa relações permitidas, conjunto de visitados e orçamento de recursos definido em
ensaio. Ciclo, profundidade excedida ou associação ausente resultam em limitação, não conclusão
de inexistência física do componente. Campos independentes de geometria continuam avaliáveis.

### 6.5 Placeholders, evidência negativa e conhecimento de domínio

Definir uma política de suspeita de valor provisório por fonte/exportador/campo, com
evidência revisada e versão. Não converter todos os zeros/falsos em null; não aceitar todos
os valores não vazios como informação válida. Representar o valor e o sinal de suspeita
separadamente para permitir revisão e medir falsos positivos dessa detecção.

Ausência no arquivo significa “não observado no escopo examinado”, não “inexistente no
edifício”. Distinguir leitura completa que não encontrou relação, leitura não suportada e
busca limitada que pode ter omitido uma parte. Evidência negativa precisa informar cobertura.
Definição do catálogo e regularidade de engenharia explicam interpretação, mas não suprem
uma especificação de projeto ou documento que o fluxo inicial não recebeu.

### 6.6 Exemplos de decisão por campo

| Situação | Operação/caminho proposto | Resultado admissível |
|---|---|---|
| Propriedade exata no tipo e ausente na ocorrência | Ler as duas origens; aplicar regra de herança pertinente | Observação efetiva com origem preservada; não criar cópia sem revisão |
| Mesmo conceito em Pset alternativo com alias aprovado | Recuperar como candidato, mantendo caminho original | Proposta para revisão; não alterar resultado formal do caminho IDS |
| Material “madeira” presente em folha, alvo é marco | Conferir papéis antes de reaproveitar texto | Abstenção para marco se não houver evidência própria |
| Fixação de janela não declarada em atributo, relação ou Pset | Classificar informação necessária ao responsável | BCF direto, sem chamar LLM para escolher solução construtiva |
| Weight agregado em hospedeiro e barras sem massa individual | Conservar entidade/escopo do agregado | Não distribuir massa proporcionalmente sem operação e insumos fundamentados |
| Um campo excede suporte, outro tem conversão segura | Processar cada FieldRef separadamente | unsupported/abstained em um e proposta revisável no outro |
| IDS exige um código, IFC não contém observação correspondente | Preservar exigência como esperado | Abstenção; não copiar o código esperado como fato observado |

<a id="m3-exemplo-peitoril"></a>

**Exemplo conceitual proposto por Felipe e discutido em voz em 10/10/2026:** uma janela de correr tem caixilho de madeira e um Pset existente declara `peitoril = granito`; o IDS espera `EB_Orçamento → Tipo_Peitoril`. Com significado/papel comprovados e mapping, tipo/valores e operação compatíveis, o Copilot poderá propor o mapeamento/cópia fundamentada de `granito` ao campo esperado para revisão humana. A aplicação depende do aceite explícito e do percurso de escrita em cópia/revalidação, preservando elemento/revisão, caminho do Pset/propriedade de origem, valor observado, requisito-fonte e versões do catálogo/receita. Madeira do caixilho e granito do peitoril pertencem a componentes distintos e **não constituem conflito por si**. Sem evidência do peitoril, madeira ou o valor esperado no IDS não autorizam deduzir granito. É uma concretização dos critérios existentes de papel e proveniência, incluindo CT3-27, sem comportamento implementado; a autorização de concluir o planejamento decorre do registro posterior de 12/10.

<a id="m3-receitas"></a>

## 7. Catálogo, receitas extensíveis e governança

### 7.1 Separar política, receita e capacidade

`EvidencePolicy` define o que pode sustentar um campo e as condições de conflito/abstenção.
`ContextRecipe` é proposta de composição declarativa dessa política: seletores, operações,
dependências, apresentação e ações admissíveis. `OperationCapability` declara a implementação
disponível, tipos/schema/portadores, versão e evidência de teste. Cadastrar uma receita não
implementa uma capacidade; copiar receita entre classes não comprova aplicabilidade.

O catálogo local do projeto permanece fixado. Curador pode publicar uma nova versão após
revisão; operador pode solicitar mapeamento e LLM pode sugerir uma correspondência. Nenhum
desses pedidos altera silenciosamente a análise atual. Migrar para o dicionário de Juliana
conserva IDs locais/histórico, correspondências revisadas, diferenças e compatibilidade.
Não tratar string URI construída por convenção como resolução oficial de um conceito.

### 7.2 Registro inicial de operações a discutir

| Família de operação proposta | Entradas e saída | Condição de uso |
|---|---|---|
| `read_attribute` | ElementRef + binding → observação de atributo | Atributo e schema existem; null/ausente distintos |
| `read_occurrence_type` | ElementRef + caminho → observações separadas e vínculo de tipo | Preservar override, múltiplos vínculos/erro e origem |
| `read_pset_property` | Binding exato → valor/portador/tipo/unidade | Não buscar alias fora da política sem marcar candidato |
| `read_qto_quantity` | Binding de quantidade → observação com conjunto/método | Não achatar conjuntos; tipos de medida preservados |
| `read_material_roles` | Associação/conjunto/partes → observações por papel | Papel inferido deve ser marcado; não escolher primeiro material como todo |
| `read_classification` | Relações → sistema/edição/código/cadeia | Múltiplas classificações e herança não se perdem |
| `read_host_opening` | Relações fills/voids válidas → caminho entre entidades | Relação candidata não substitui vínculo existente |
| `read_parts_relations` | Relações permitidas → subgrafo limitado com cobertura | Ciclos/limites e elementos sem GUID são tratados por ElementRef |
| `resolve_approved_mapping` | Fonte observada + alias escopado → correspondência revisada | Identidade do conceito, componente e namespace compatíveis |
| `convert_unit` | Valor/unidade/dimensão → derivação rastreável | Unidade conhecida, transformação aprovada e reversibilidade explicável |
| `calculate_quantity` | Insumos verificados + método → observação derivada | Implementação/versão e hipótese geométrica explícitas |
| `interpret_context` | Evidências admissíveis + domínio → proposta LLM ou abstenção | Sem escolha de projeto ausente ou instrução externa |
| `request_responsible_decision` | Campo + lacuna → ResidualRequest | Não exige chamada LLM; não escolhe destinatário externo automaticamente |

Os identificadores acima são candidatos, não API publicada. Nova propriedade pode compor
operações existentes aprovadas. Nova capacidade requer implementação, testes e revisão de
domínio quando altera significado/cálculo. Expressões Python/SQL, executáveis, URLs de
serviço e prompts irrestritos enviados no cadastro não são operações aceitas.

`interpret_context` declara a necessidade de interpretação; o motor de receitas compila
esse passo em um bloco de campo, sem disparar uma chamada por receita. O orquestrador
reúne os blocos elegíveis no CallPlan do elemento. Assim, extensibilidade por propriedade
permanece compatível com os agrupamentos por elemento, propriedade ou grupo a
comparar no desenvolvimento; o baseline admite uma inferência ativa por vez.

### 7.3 Exemplo JSON de receita, ainda rascunho

Exemplo sintético sem valor de produção. Usa leitura exata e interpretação delimitada;
não pretende representar uma linha Daiane. `draft` não deve ser ativável em análise
operacional. Os limites numéricos vêm de perfil ensaiado, não deste exemplo.

```json
{
  "recipe_id": "demo-recipe-leaf-material",
  "version": "draft-0.1",
  "lifecycle": "draft",
  "concept_id": "demo-concept-leaf-material",
  "binding_id": "demo-binding-leaf-material",
  "evidence_policy_id": "demo-policy-leaf-material",
  "applicability": {
    "entity": "IfcDoor",
    "component_role": "leaf",
    "unknown_behavior": "abstain"
  },
  "operations": [
    {
      "step_id": "read_leaf_material",
      "operation_id": "read_material_roles",
      "operation_version": "demo-1",
      "depends_on": [],
      "parameters": {"required_role": "leaf"}
    },
    {
      "step_id": "interpret_label",
      "operation_id": "interpret_context",
      "operation_version": "demo-1",
      "depends_on": ["read_leaf_material"],
      "parameters": {"allowed_actions": ["propose", "abstain"]}
    }
  ],
  "required_evidence": ["material_association", "component_role"],
  "forbidden_as_fact": ["ids_expected_value", "ids_identifier", "catalog_example"],
  "conflict_policy_ref": "demo-policy-preserve-and-review",
  "missing_evidence_action": "request_responsible_decision",
  "budget_policy_ref": null,
  "write_enabled": false
}
```

### 7.4 Curadoria e compatibilidade de receitas

Validar sintaxe, referências, grafo sem ciclos, operações disponíveis, tipos compatíveis,
papéis, unidade, pré-condições e limites de expansão. A validação técnica não aprova a
premissa de engenharia: Felipe/especialista precisa revisar a evidência admissível e o
alcance das transformações. Curador publica somente o conteúdo exato revisado.

Registrar versões do catálogo, receita, operação e condição. Mudança só de apresentação
pode mudar estímulo/tokenização e exige análise de impacto científico. Mudança em alias,
precedência ou domínio pode invalidar propostas existentes. Atualizar projeto exige diff,
nova análise e revisão dos resultados afetados; não transformar uma aprovação antiga em
aprovação do novo valor. Pacote ausente/inválido não autoriza busca arbitrária nem publicação
de mapping. A consulta pública bSDD ocorre apenas pelo adaptador semântico de C3-10/M3-25,
sem dados de projeto e sem transformar resposta pública em receita publicada.

<a id="m3-pipeline"></a>

## 8. Pipeline, agrupamento por elemento e orçamento de recursos

### 8.1 Fluxo proposto

```text
Snapshot M2 + revisão curada e semântica bSDD identificada + seleção de campos
  → conferir identidade, acesso e capacidades
  → resolver bindings/políticas/receitas
  → coletar observações compartilhadas e executar derivações determinísticas
  → avaliar suficiência, conflito, placeholder e necessidade de responsável
  → propostas determinísticas / manual fundamentado / BCF direto / campos LLM elegíveis
  → contexto comum + blocos por campo + manifesto de seleção
  → roteamento por campo/grupo e orçamento; uma inferência por vez
  → runtime LLM local → JSON → validação por campo
  → persistir propostas/abstenções/erros e cobertura
  → revisão M4 → escrita autorizada em cópia M5 → nova revisão/verificação M2
  → pendências BCF continuam até resolução verificada
```

Um snapshot sem falhas IDS pode conter alertas complementares selecionados pelo operador;
esses campos conservam a categoria complementar. Não ampliar automaticamente o diagnóstico
para todos os campos do catálogo. Requisito não verificado por falta de suporte é tratado
como tal; uma sugestão não “conserta” o desconhecimento formal do verificador.

**Roteamento configurável:** `RoutingPolicy` proposta liga propriedade/grupo e capacidade
a um perfil local avaliado por M7; registrar regra/versão, evidência da seleção, digest do
modelo, parâmetros, recursos M6 e motivo de recusa. Não escolher modelo vencedor com base
apenas na disponibilidade/default atual. Alterar rota muda identidade/cache/condição.
Comparar agrupamentos no desenvolvimento não é bloqueio para concluir o planejamento.

### 8.2 Coleta compartilhada sem mistura de escopos

Índices por arquivo/revisão podem servir material, tipo, contenção, partes, classificação e relações.
A federação M4 é visual: no MVP nenhuma observação de arquitetura sustenta campo do modelo
estrutural, nem o inverso. Elemento visualmente coincidente não cria relação IFC entre arquivos.
Coletores retornam observações completas uma vez; blocos selecionam referências pertinentes.
Uma evidência comum pode apoiar vários campos, mas cada campo declara como a usa e sob qual
receita. A mesma observação pode ser admissível para um campo e inadequada para outro.

Resultado de cálculo precisa depender apenas de observações/derivações verificadas. Não
usar sugestão LLM ainda pendente como fato para outro campo. Dependência entre campos que
exija decisão aprovada gera nova etapa/análise com proveniência, não realimentação invisível
dentro da chamada. Evitar que alternativas incompatíveis de dois campos sejam compostas
como se fossem uma única solução coerente; eventual restrição conjunta deve ser explícita.

### 8.3 Agrupamento, roteamento e execução serial inicial

Primeiro obter resultados determinísticos e separar manual/BCF direto. O agrupamento por
elemento é candidato com contexto comum deduplicado; comparar também propriedade e grupos
de campos durante o desenvolvimento, com M7. Manter uma inferência ativa por vez no baseline,
inclusive em retries e quando o roteamento escolher modelos diferentes. Os dois pares IFC–IDS
da mesma sessão compartilham essa fila serial, sem juntar pacotes/evidências. Solicitar resultado por campo, sem
pedir à LLM para detectar quais requisitos deve responder. A cardinalidade das alternativas
será ensaiada por tarefa; não copiar a exigência histórica de sempre três opções.

Se o pacote não couber, reduzir conteúdo opcional por relevância antes de dividir. Não
remover evidência obrigatória para manter artificialmente uma chamada. Se for necessário
dividir, manter cada campo com seu conjunto mínimo de evidência e registrar CallPlan,
identidade comum e motivo. Se nem um campo completo couber, retornar limite explícito e
pendência; não enviar esperando que o servidor escolha o trecho a truncar.

Uma falha de parse global exige tratar a tentativa inteira como tecnicamente inválida.
Em envelope válido, erro semântico de um campo pode coexistir com propostas válidas dos
demais. Política de repetição parcial deve evitar regenerar e sobrescrever resultados já
aceitos pelo validador. Esse comportamento precisa de ensaio; não está implementado.

### 8.4 Orçamento formal a calibrar

Proposta de restrição: `T_sistema + T_comum + soma(T_campos) + T_saida_reservada + T_margem <= T_janela`.
Contar também chat template, schema de saída e metadados serializados. Reservar saída pelo
número de campos/alternativas e pelo schema, não por um único número histórico para toda
requisição. A estimativa por caracteres pode servir de fallback conservador somente se sua
incerteza e política forem explícitas; tokenizer real deve ser preferido quando disponível.

| Recurso | O que medir/limitar | Política proposta sem valores aprovados |
|---|---|---|
| Tokens de entrada | Comum, cada campo, definições, schema e overhead | Ordenação estável e eliminação apenas de conteúdo opcional |
| Tokens de saída | Campos, alternativas, evidências e justificativas curtas | Reserva antecipada e detecção de término/truncamento |
| Expansão de relações | Entidades visitadas, profundidade, fan-out, ciclos | Interromper operação e registrar cobertura/limitação |
| Tamanho de texto | Nomes/descrições/propriedades e listas | Limitar serialização; manter original local e registrar omissão |
| Execução nativa | Geometria, memória, CPU e duração | Isolar/controlar com M6; timeout não significa ausência de geometria |
| Fila/runtime | Concorrência, VRAM, carregamento, cancelamento | Calibrar no hardware local; não prometer throughput |
| Armazenamento | Fontes, observações, prompts, respostas e cache | Retenção/ACL M6; deduplicação sem misturar projetos |

Limites precisam existir e ser testáveis antes do uso, mas seus valores são pendência de
ensaio. Defaults atuais do código não viram acordo. Registrar estimado versus efetivo,
campos omitidos, razão de divisão, tokenização, janela realmente enviada e stop reason.

### 8.5 Cache, idempotência e retomada

Proposta de chave: identidade de projeto/análise autorizada, revisões IFC/IDS, snapshot,
ElementRef/FieldRefs, catálogo/políticas/receitas, operações e parâmetros, observações
selecionadas, contexto/CallPlan, schema de resposta, condição, modelo/digest e opções.
Qualquer simplificação precisa demonstrar que não reutiliza resposta sob evidência diferente.
Contexto de edificação incluído no prompt também participa da identidade.

Reaproveitar extração não equivale a reaproveitar inferência entre elementos. O primeiro
reuso pode ser seguro por revisão/operação; o segundo exige equivalência explícita e ensaio,
sem copiar IDs de evidência ou decisões entre elementos. Para o primeiro fluxo, estudar
reuso conservador por pacote exato, deixando equivalência aproximada como hipótese separada.

Persistir eventos/tentativas e resultados com chaves idempotentes. Cancelamento deve permitir
diagnóstico completo M2, resultados M3 já confirmados e restante marcado incompleto. Falha
entre inferência e persistência não autoriza duplicar aplicação ou fechar pendência. Retomar
confere as entradas; se mudaram, cria nova execução e conserva a anterior.

<a id="m3-llm"></a>

## 9. LLM local, JSON, alternativas e abstenção

### 9.1 Papel e escolha do modelo

A LLM recebe tarefa restrita de interpretar evidência fornecida e propor valor/alternativa
ou abster-se. Não recebe ferramentas de escrita, terminal, rede pública, editor de catálogo
ou exportador BCF. O serviço executa somente operações determinísticas aprovadas e os
comandos humanos da etapa própria. Modelo não decide sua própria autorização.

Não escolher neste plano um modelo vencedor, tamanho, quantização, temperatura ou SLA.
Selecionar candidatos compatíveis com hardware/licença/localidade e comparar sob protocolo
fixado. Registrar modelo e digest, runtime, tokenizer/chat template, quantização, parâmetros,
seed quando suportada e características do hardware. Seed fixada não prova determinismo.

### 9.2 Contrato da resposta

Envelope proposto contém request/context hash e lista de resultados indexados por FieldRef.
Para cada campo, a união de saída permite `propose` com alternativas tipadas e evidências,
ou `abstain` com motivo estruturado e informação faltante. IDs de catálogo/elemento/evidência
devem ser selecionados de conjuntos fornecidos; o modelo não cria URI oficial ou identidade
de fonte. Justificativa é síntese verificável, não solicitação de cadeia interna de raciocínio.

Exigir campo esperado uma vez, sem duplicação/omissão. Arrays extras, valores não finitos,
tipo incompatível, unidade desconhecida, IDs de outro elemento/revisão e ação fora do enum
devem gerar erro explícito. Motivos podem ter vocabulário controlado, com texto curto para
explicar a lacuna. Confiança autodeclarada, se coletada para estudo, não libera escrita,
não substitui checagem de fundamento e não decide fechamento de BCF.

#### Exemplo do envelope de saída LLM, distinto do resultado do serviço

Este JSON é sintético e parcial quanto ao protocolo de produção. O hash nulo impede
seu uso operacional; a tarefa M3-14 deverá exigir o hash real fornecido na requisição.
O exemplo admite uma alternativa e uma abstenção, sem exigir valor para o segundo campo.

```json
{
  "request_id": "demo-request-1",
  "context_sha256": null,
  "results": [
    {
      "field_id": "demo-field-leaf-material",
      "action": "propose",
      "alternatives": [
        {
          "typed_value": {"kind": "string", "value": "madeira"},
          "unit": null,
          "evidence_ids": ["demo-obs-material-leaf"],
          "justification": "O material está declarado para a folha."
        }
      ]
    },
    {
      "field_id": "demo-field-fixing-method",
      "action": "abstain",
      "reason_code": "insufficient_evidence",
      "missing_information": ["Método de fixação do conjunto"]
    }
  ]
}
```

No schema proposto, `action` discrimina dois objetos: `propose` exige alternativas
não vazias, tipo/valor e evidências; `abstain` exige motivo e não aceita valor ou
alternativas. `additionalProperties` será falso nos objetos de controle. Validar também
chaves JSON duplicadas, não apenas o objeto que sobra depois do parse. A união de
`TypedValue` deverá manter os tipos M2, sem transformar todos em strings; decimais terão
representação canônica finita e booleanos JSON continuarão booleanos.

IDs de alternativas, método verificado, resultado de validação, estado de revisão,
autor e autorização são atribuídos pelo serviço. O modelo não pode emitir esses atos.
`action=propose` só se torna `state=proposed` após os verificadores; saída inválida
produz falha localizada ou de envelope. `action=abstain` válido torna-se `abstained`,
com origem `llm`; abstenção determinística/BCF direto guarda outra origem e nenhuma
chamada. Operação indisponível conserva `unsupported`, mesmo quando gera pendência.

Conferir cada requisito relacionado ao campo separadamente. Proposta sustentada que não
satisfaz o IDS evidencia uma divergência: não trocar o valor para fazê-la passar, nem
anunciar conformidade. Distinguir violação do domínio do conceito, incompatibilidade do
binding e desacordo com a exigência daquele IDS. Encaminhar conflito à revisão; qualquer
correção do instrumento seria outra decisão, fora deste fluxo e desta entrega.

### 9.3 Camadas de validação

1. **Transporte/runtime:** resposta recebida, sem timeout, truncamento ou término indevido.
2. **Sintaxe/envelope:** JSON único, schema estrito, request/context e cardinalidade corretos.
3. **Identidade:** FieldRefs solicitados, ElementRef correto e evidências existentes no pacote.
4. **Tipo/dimensão/domínio:** TypedValue, portador e unidades compatíveis com catálogo/receita.
5. **Sustentação:** evidências admissíveis para esse conceito/componente; pré-condições satisfeitas.
6. **Coerência:** alternativas e dependências não contradizem restrições conjuntas declaradas.
7. **Revisão humana:** apresentação de fontes/limites e decisão sobre valor exato, fora da LLM.

Schema válido não garante sustentação. Uma referência existente pode ser irrelevante; o
validador deve detectar usos proibidos e operações sem pré-condições. Quando entailment
semântico exigir julgamento humano, manter essa limitação explícita. Não prometer que um
segundo LLM torna a verificação factual infalível ou dispensa revisão especializada.

### 9.4 Reparos, retries e preservação de abstenção

Abstenção válida termina o campo; não repetir automaticamente até obter valor. Repetir
somente falha técnica elegível segundo política limitada e registrada. Separar transporte,
JSON inválido, omissão de campo, erro semântico e ausência de evidência. Retry não pode
introduzir valor correto do gabarito ou orientar o modelo a preencher para passar no IDS.

Reparo permissivo de JSON pode ocultar perda de campos; o caminho novo deve preferir
rejeição explícita ou reparo restrito verificável, preservando resposta original e evento.
Se o modelo não suporta schema restrito, avaliar fallback local de parsing sob a mesma
validação. Nunca trocar para API externa. Não reaproveitar o parser legado que descarta
`action=abstain` sem adaptá-lo e declarar a nova condição.

### 9.5 Abstenção útil e BCF direto

Motivos propostos: `insufficient_evidence`, `conflicting_evidence`, `unmapped_concept`,
`unsupported_operation`, `ambiguous_component_role`, `unknown_unit`,
`responsible_design_decision_required` e `context_budget_exceeded`. Alguns descrevem
limite técnico e precisam manter categoria correspondente, sem culpar o projetista.

ResidualRequest deve dizer qual campo/requisito ficou pendente, o que foi encontrado,
quais caminhos foram examinados, o dado necessário e por que uma alternativa não foi
sustentada. Pode incluir uma referência à informação agregada do hospedeiro sem distribuí-la.
Não fabricar destinatário, prazo, material, resistência, peso ou detalhe construtivo.
Criar/exportar tópico não equivale a enviar comunicação externa a uma pessoa.

<a id="m3-seguranca"></a>

## 10. Conteúdo não confiável, segurança e localidade

### 10.1 Instruções embutidas no IFC/IDS/catálogo

Nome, Description, ObjectType, propriedades textuais e referências de documento podem
conter comandos como “ignore as regras”, falsos schemas de resposta, URLs e pedidos de
exfiltração. São dados de projeto não confiáveis, nunca instruções de sistema. O mesmo
vale para texto livre do IDS, descrições de catálogo e saída de ferramenta/modelo.

Serializar em campos tipados/delimitados, com origem e papel de dado. Escapar aspas e
marcação, limitar tamanho e evitar concatenação de texto bruto em posições de controle.
Não executar código, abrir link, seguir caminho de arquivo, baixar conteúdo ou alterar
receita por instrução encontrada no modelo. Delimitadores ajudam leitura, mas a proteção
principal é ausência de ferramentas/permissões de efeito no runtime e validação de saída.

Exercitar ataques com instrução em Name, Pset, material, classificação e texto de requisito.
Testar respostas que tentam alterar IDs, aprovar a si mesmas, substituir catálogo, escrever
arquivo ou declarar que a revisão já ocorreu. Todas devem ser rejeitadas como ação, mesmo
quando o texto possa permanecer armazenado como observação original para auditoria local.

### 10.2 Fronteiras de execução

Aplicar política M6 em todos os pontos de saída. LLMs, embeddings, dados, evidências,
telemetria e logs do projeto permanecem locais/IME. A exceção inicial autorizada é a
consulta **semântica pública bSDD**: apenas URIs/identificadores/termos públicos previamente
aprovados, nunca IFC, GUID, nome de elemento, texto livre do projeto, valores ou prompt.
O adaptador constrói parâmetros a partir do catálogo público permitido; não usa texto do
IFC como consulta. Política de rede permite destinos/rotas bSDD necessários e recusa URLs
fornecidas pelo modelo/LLM, redirecionamentos indevidos e anexos de projeto.

Conservar URI, versão quando oferecida, data, resposta bruta, hash e snapshot semântico
usado. Falha pública gera indisponibilidade técnica; pode usar snapshot previamente fixado
e compatível, explicitamente identificado, sem ocultar sua data. API não publica binding,
não determina conformidade IDS e não fornece valor real do elemento. Armazenamento integral
dos dicionários é estudo futuro, distinto desse registro mínimo de reprodução. Modelos e
dependências não são baixados dinamicamente pelo worker.

Hosts internos permitidos precisam de política explícita e ensaio de redirecionamentos,
proxies/configuração, DNS e topologia institucional. O helper atual de host literal é base,
não prova de contenção de rede completa. Caso a política não possa ser garantida, bloquear
a inferência afetada e preservar diagnóstico/pendências, sem fallback silencioso.

### 10.3 Operações declarativas e limites

Receita só invoca IDs de operações aprovadas. Validar grafo, parâmetros, escopo e custo
antes da execução. Não aceitar caminhos arbitrários, expressão executável ou extensão de
permissão pelo conteúdo. Separar leitura de IFC dos processos que podem escrever cópia.
Processos nativos/geométricos precisam de limites de memória/tempo e cancelamento seguro.

Restringir expansão de relações e tamanho de listas, tratar ciclos e payloads grandes,
preservar resultado parcial. Segurança de importação de pacote inclui hashes, caminhos,
conflitos e licença, em coordenação M1/M6. Testes adversariais não usam endpoints públicos
com dados reais; substitutos locais controlados fornecem evidência de bloqueio.

### 10.4 Logs, revisão e armazenamento

Prompts e respostas podem revelar dados do projeto; armazenar somente em espaço local/IME
com ACL/retenção definidas. Separar log operacional de artefato de reprodução científica.
Registrar hashes/IDs/métricas sem imprimir indiscriminadamente textos e caminhos privados.
Se a política exigir retenção completa de estímulos, garantir acesso e finalidade explícitos.

Escapar dados exibidos em UI/HTML/CSV/BCF; fórmulas em CSV e markup não viram código ativo.
Run ID não é credencial. Não misturar evidência/cache entre projetos ou usuários sem acesso.
Uma decisão humana fica ligada a ator autenticado/contexto local confiável, proposta exata
e revisão vigente; texto “aprovado” no IFC ou na resposta LLM não concede autorização.

<a id="m3-interfaces"></a>

## 11. Interfaces com M1, M2, M4, M5, M6 e M7

### 11.1 M1 — Significado, catálogo e publicação

Usar `open_catalog(CatalogReleaseRef)`, `resolve_binding(BindingRequest)`,
`get_evidence_policy()` e `get_capability()` propostos no plano 1. Acrescentar acesso à
receita somente após alinhar o contrato, sem presumir que os três métodos de SemanticCatalog
existente cobrem o builder legado. Resolver significado é diferente de produzir evidência.

Retornar solicitações de mapeamento/capacidade ao fluxo de curadoria, com fonte e escopo.
LLM pode propor correspondência, mas não alterar release nem declarar equivalência oficial.
Campos sem mapeamento continuam no diagnóstico M2; sua falta de enriquecimento é explícita.
Migração Juliana exige diff, decisão curatorial, novo pin/análise e invalidação apropriada.

<a id="m3-interface-camadas"></a>

**Duas camadas confirmadas em 10/10 e concretizadas em 12/10:** consumir a
[representação M1](modulo-01-dominio-catalogo.md#m1-duas-camadas): fonte fiel por requisito
e catálogo operacional separado. Os apoios desta consolidação são uma revisão canônica
com CSV/JSON equivalentes e fichas derivadas, sem tabelas independentes mantidas à mão.
Receita conserva requisito–registro/página e versões de catálogo/operação/evidência.
O [exemplo do peitoril](#m3-exemplo-peitoril) continua ilustrativo; cada registro agora tem
sua própria ficha. G3-01 fica fechado documentalmente, sem publicar receitas de produção.

### 11.2 M2 — Fonte confiável de observações e diagnóstico

Receber snapshot identificado, RequirementResults e observações. Solicitar leitura adicional
pela mesma revisão/sessão e operações disponíveis. Manter categorias de problema técnico,
falha IDS e alerta complementar. O estado M2 não muda porque uma alternativa foi gerada.
Uma falha de LLM não afeta exportação do diagnóstico ou resultados independentes.

Extratores de baixo nível, unidade, tipo/ocorrência e relações pertencem à fronteira comum
com M2; M3 seleciona, deriva e compõe evidência para enriquecimento. Não duplicar o parsing
IFC, o motor IDS, a identidade ou os cálculos sem alinhar responsabilidades/versionamento.
Compartilhar testes de contrato e usar fixtures sem afirmar integração real antes de existir.

### 11.3 M4 — Visão por elemento e decisão por campo

Entregar pacote/resultados com fontes localizáveis, encontrado/esperado, método, alternativas,
conflitos e motivo de abstenção. A visão principal é por elemento, com alternativa por
requisito. Mostrar separadamente resultado formal, mapeamento, disponibilidade de evidência
e estado de proposta/revisão. Não esconder campos sem proposta ou falhas de processamento.

Revisão aceita/edita/rejeita/pula valor específico. Edição preserva proposta original e
novo valor/fundamento; escolha da segunda alternativa não pode auditar a primeira. Exibir
impacto de eventual escrita em tipo compartilhado antes da decisão, com escopo inequívoco.
Viewer apenas localiza ElementRef e suas partes; ausência de geometria não elimina a linha.
Nonato conduz M4; seu planejamento foi autorizado em tarefa separada. O MVP prioriza
visualização federada de arquitetura e estrutura na mesma sessão, com dois pares IFC–IDS.
Seleção visual conserva `PairRef`/arquivo/revisão; diagnóstico, evidência e exportação são
separados por arquivo e M3 não usa evidência cruzada. React/TypeScript/Vite/shadcn e API
Python foram definidos; That Open permanece candidato a ensaio. Layout continua no M4.

### 11.4 M5 — Escrita em cópia, BCF residual e revisão seguinte

M3 fornece proposta, dados para revisão e ResidualRequest; M4 registra o ReviewEnvelope
após a decisão humana, inclusive no preenchimento manual. Antes de tornar o candidato
aprovável, código verifica tipo, unidade, IDS, aplicabilidade e fonte/fundamento. M3 não
cria essa autorização nem chama writer. M5 verifica ator,
decisão e revisões vigentes, aplica em cópia e produz recibo de aplicação. A cópia é nova
revisão IFC, avaliada pelo mesmo serviço M2. Resultado de aplicação, revalidação e decisão
humana permanecem distintos. Política de exportação parcial será definida na frente 5.

Lacuna não resolvida, abstenção e campo que exige decisão externa podem originar BCF.
Rejeitado/pulado continua pendente; não mapear tudo para Closed. Aceitação de proposta
também não basta para resolução: exigir verificação pertinente na nova revisão e vínculo
com a pendência anterior. Mesmo GUID com conteúdo alterado não conserva aprovação por si.
Identidade de projeto IFC, arquivo/revisão, componente e tópico BCF não são intercambiáveis.

Se GUID é ausente/duplicado, o exportador precisa declarar limitação de seleção interoperável
e preservar diagnóstico interno, sem inventar referência válida. Versão BCF, receptor e
política de atualização/fechamento exigem ensaio; o exportador atual não é certificação.
O humano pode usar documentos externamente para resolver BCF; a nova evidência/decisão
deve ser rastreável, sem atribuir essa consulta ao fluxo automático inicial.

### 11.5 M6 — Operação, ativos e governança

Nonato lidera esta fronteira, articulando com regras institucionais. Receber endpoint/modelo
autorizados, ativos locais, adaptador público bSDD restrito, armazenamento, identidade do ator
e budgets de recursos.
Definir retenção, backup, recuperação e isolamento antes do uso real. Recursos sem licença,
hash ou capacidade compatível não são baixados dinamicamente pelo worker.

Expor progresso por elemento e campo, métricas de fila/execução, cancelamento e status parcial.
Persistência não deve depender só de session_state ou variável global. Concorrência e
multiusuário exigem ensaio; uma configuração que serve um desktop não prova operação IME.
Interrupção/reinício mantém tentativas e resultados sem duplicar escrita ou decisão.

### 11.6 M7 — Identidade experimental e pesquisa

Nonato lidera M7, com ajuda de Felipe em domínio e pesquisa e especialistas no gabarito. Exportar manifesto local com inputs, corpus/split, versões,
contexto, receita, modelo, parâmetros, tokens, custos de tempo/memória e resultados.
Separar erro do extrator, mapeamento, geração, parse, evidência e revisão humana.

Comparar regras versus regras+LLM com evidência equivalente, incluindo campo sem resposta
e decisão necessariamente humana. Não premiar preenchimento indevido por aumentar cobertura.
Mudar catálogo, agrupamento, truncamento ou schema altera condição; preservar resultados
históricos e identificar claramente novos ensaios e limitações de generalização.

<a id="m3-tarefas"></a>

## 12. Tarefas propostas, dependências e critérios de aceite

As tarefas funcionais desta seção são **futuras e não executadas**. A parte documental
de M3-01 foi realizada nesta consolidação; não conta como execução dos casos CT3.
Detalhes de schema/política dependem da revisão indicada; um critério abaixo descreve
comportamento a demonstrar, não teste que já passou. Nenhuma tarefa autoriza automaticamente
commit, push, merge, instalação, uso de dado real ou execução de modelos.

Felipe responde pelo M3 e pelas interfaces com M1/M2/M5. Nonato responde por M4/M6
e lidera M7 com Felipe. “Curador M1” é papel de publicação e especialistas revisam
premissas BIM; implementação técnica não concede autoridade de projeto. As atribuições
abaixo seguem essa divisão, substituindo os papéis parciais antigos.

Cada incremento funcional futuro deve começar por casos que exponham o comportamento
ausente, implementar o recorte mínimo e produzir evidência de execução/revisão. Caminhos
novos abaixo são propostos; arquivos existentes só mudam em implementação autorizada.

<a id="m3-t01"></a>

### M3-01 — Fixar baseline, fontes e pendências documentais

**Dependências:** fontes locais e preservação do checkout. **Papéis:** Felipe; M7/Nonato
na identidade experimental. **Artefatos existentes:** [baseline](../pesquisa/modulo-03-contexto/baseline.md)
e [apoios](../pesquisa/modulo-03-contexto/README.md). **Consome/produz:** fontes reais →
inventário, hashes, denominadores e limites de G3-01/G3-02.

- [x] Identificar PDF/ZIP locais, hashes e registros por família, sem alterar os originais.
- [x] Separar fonte e operação e produzir projeções JSON/CSV da mesma revisão.
- [x] Distinguir análise estática, resultados históricos e desenvolvimento não executado.
- [ ] Obter XML/planilha 2025 e fixtures F01–F24 citadas, reconciliar por diff curado.
- [ ] Ler a síntese da Library quando disponível por fluxo suportado; avaliar contribuição
  metodológica sem adotá-la como gabarito ou substituir a fonte primária.

**Aceite documental:** 203 alfanuméricos + 110 auxiliares rastreáveis, denominadores
72/85 identificadores/pares, 79/90 rótulos/pares e 136/202 explicados e JSON/CSV equivalentes. **Aceite futuro:** novas fontes não
sobrescrevem literais/IDs nem publicam receitas automaticamente. CT3-01/02/71/72/73.

<a id="m3-t02"></a>

### M3-02 — Definir contratos e identidade compartilhados

**Dependências:** M3-01 e alinhamento dos contratos M1/M2. **Papéis:** Felipe/M1/M2, com revisão especializada de estados. **Arquivos:** `src/enrichment/contracts.py`,
`tests/enrichment/test_contracts.py`; adaptar fundação somente pela nova fronteira.
**Consome/produz:** AnalysisIdentity/ElementRef/observações → envelopes descritos na seção 5.

- [ ] Formalizar identidade de execução, campos, propostas, evidências e tipos discriminados.
- [ ] Preservar múltiplos requisitos, GUID ausente/duplicado, arquivo/par IFC–IDS e revisões diferentes; sessão compartilhada não mistura fontes (CT3-81).
- [ ] Separar estados formal, técnico, evidência, proposta, revisão e aplicação.
- [ ] Criar fixtures válidas/inválidas de contratos, sem hashes fictícios em uso operacional.

**Aceite:** serialização preserva origem/tipos e rejeita mistura de revisões/IDs; zero/falso
são valores. Consumidores M1/M2 conseguem trocar fixtures sem converter tudo a string.
CT3-03–CT3-06, CT3-40/CT3-41 e CT3-54 verificam contratos e identidade.

<a id="m3-t03"></a>

### M3-03 — Unificar o acesso ao contexto do diagnóstico

**Dependências:** M3-02 e G3-04 para integração real. **Papéis:** Felipe/M2.
**Arquivos:** `src/enrichment/evidence.py`; adaptadores de `analyzer.py`/`pipeline.py`;
`tests/enrichment/test_diagnostic_adapter.py`. **Consome/produz:** snapshot/sessão M2
fixados → observações consultáveis com erro/ausência/cobertura diferenciados.

- [ ] Mapear caminhos legado, analyze_from_ids e integração IDS do pipeline.
- [ ] Criar adaptador único para o fluxo novo, eliminando perda por rota de entrada.
- [ ] Memorizar coleta por revisão/elemento/operação, mantendo observações compartilhadas.
- [ ] Conferir que falta de LLM/catálogo não altera o diagnóstico independente.

**Aceite:** mesmo snapshot e seleção produzem pacote equivalente pela entrada autorizada;
novas issues IDS não ficam sem evidência por falta de chamada do extrator. Instrumentação
conta coleta reutilizada e estado técnico real. CT3-07/CT3-08 e CT3-57.

<a id="m3-t04"></a>

### M3-04 — Preservar atributos, Psets, tipo e ocorrência

**Dependências:** M3-02/M3-03; capacidades de leitura M2. **Papéis:** frente 2 na leitura,
Felipe no adaptador e revisão de herança/portador. **Arquivos:** adaptadores em
`src/enrichment/evidence.py`, leitores M2 a acordar; `tests/enrichment/test_property_origin.py`.
**Consome/produz:** binding + ElementRef → observações individuais e vínculo de tipo.

- [ ] Ler atributos e propriedades com identidade do portador e tipo IFC original.
- [ ] Conservar ocorrência e tipo, inclusive PredefinedType efetivo e origem de override.
- [ ] Separar propriedade exata de candidato em outro conjunto/alias.
- [ ] Preservar valores conflitantes, coleções/portadores não suportados e falhas de leitura.

**Aceite:** get_psets combinado não é única fonte de proveniência. Mudança de origem é
observável mesmo com valor igual; alias não satisfaz automaticamente IDS exato. CT3-09–CT3-13.

<a id="m3-t05"></a>

### M3-05 — Tratar unidades, Qto e geometria derivada

**Dependências:** M3-04 e capacidades M2 de unidade/quantidade. **Papéis:** Felipe/M2,
com Felipe/especialista revisando grandeza e método. **Arquivos:** adaptadores de
`quantity_extractor.py`, `operations.py`; `tests/enrichment/test_units_quantities.py`.
**Consome/produz:** Qto/atributos/medidas identificados → valores tipados e derivações.

- [ ] Preservar conjunto, quantidade, tipo, unidade explícita/projeto e método.
- [ ] Implementar apenas conversões dimensionais aprovadas, mantendo bruto e convertido.
- [ ] Diferenciar leitura declarada, cálculo geométrico validado e aproximação por caixa.
- [ ] Recusar substituição de abertura por marco e massa agregada por individual.

**Aceite:** mm/m equivalentes convertem com proveniência; dimensão incompatível/unidade
ausente produz motivo; quantidades homônimas não sobrescrevem; cálculo não comprova presença
de Qto requerido. CT3-14–CT3-20 e CT3-28/CT3-29.

<a id="m3-t06"></a>

### M3-06 — Preservar composição e papéis de materiais

**Dependências:** M3-04/M3-05 e leitura de materiais M2. **Papéis:** Felipe/M2;
Felipe/especialista revisa interpretação. **Arquivos:** adaptadores de `material_reader.py`,
`universal_extractor.py`; `tests/enrichment/test_material_roles.py`.
**Consome/produz:** associações/partes/tipos → observações por material e componente.

- [ ] Unificar saídas divergentes sem apagar distinções entre layers/profiles/constituents.
- [ ] Conservar usos, perfis, frações, espessuras, partes e origem tipo/ocorrência.
- [ ] Registrar associação por ordem/nome como hipótese quando não houver vínculo explícito.
- [ ] Impedir que primeiro material/parte represente automaticamente o conjunto inteiro.

**Aceite:** vidro/caixilho/peitoril/folha não se confundem; perfil não desaparece; agregado
heterogêneo e papel desconhecido produzem limitação por campo. CT3-21–CT3-24 e CT3-27.

<a id="m3-t07"></a>

### M3-07 — Indexar relações, classificações e evidência agregada

**Dependências:** M3-03/M3-04 e capacidades M2. **Papéis:** Felipe/M2 e revisão especializada.
**Arquivos:** adaptadores de `relation_diagnostics.py`, `classification_extractor.py`,
`model_evidence.py`; `tests/enrichment/test_relations_classification.py`.
**Consome/produz:** relações/associações da revisão → subgrafo e inventário com cobertura.

- [ ] Preservar referências de fills/voids, partes, contenção e tipo sem depender só de GUID.
- [ ] Separar relação comprovada, candidato do mesmo pavimento e inferência de proximidade.
- [ ] Conservar múltiplas classificações, cadeia, edição e herança quando suportadas.
- [ ] Distinguir erro de contagem de zero; controlar ciclos/expansão sem perder limitações.

**Aceite:** não inventar hospedeiro para órfão; erro em count_structural_frame não prova
ausência de estrutura; contagem não determina LoadBearing. CT3-25/CT3-26 e CT3-30–CT3-33.

<a id="m3-t08"></a>

### M3-08 — Avaliar suficiência, placeholders e conflitos

**Dependências:** M3-04–M3-07 e revisão P3-04. **Papéis:** Felipe/especialista define
critérios; Felipe conduz implementação; curador publica políticas. **Arquivos:** `evidence.py`,
`tests/enrichment/test_evidence_assessment.py`; políticas pertencem ao release M1.
**Consome/produz:** observações + EvidencePolicy → EvidenceAssessment por campo.

- [ ] Conferir mesmo conceito/componente/revisão antes de classificar divergência.
- [ ] Registrar política de precedência e manter todas as origens relevantes.
- [ ] Distinguir falso/zero legítimos de suspeita fundamentada de placeholder.
- [ ] Identificar decisão humana necessária e informação ausente sem fabricar valor.

**Aceite:** ausência/erro/conflito não viram default; placeholder não é detector universal
por igualdade a FALSE/0; conflito irresolúvel tem fundamento rastreável. CT3-10/CT3-11,
CT3-34–CT3-38 e CT3-64.

<a id="m3-t09"></a>

### M3-09 — Formalizar receitas e registro de operações

**Dependências:** M3-02 e G3-03; não depende de todas as famílias implementadas.
**Papéis:** Felipe/M1; especialista revisa admissibilidade; curador publica.
**Arquivos:** `recipes.py`, `operations.py`, `tests/enrichment/test_recipe_contract.py`.
**Consome/produz:** receita do pacote fixado → plano declarativo de operações ou recusa.

- [ ] Validar referências, versão, aplicabilidade, parâmetros e grafo sem ciclos.
- [ ] Vincular IDs a implementações registradas; recusar operação inexistente/arbitrária.
- [ ] Preservar draft/publicado, pin e atualização explícita com impacto/invalidação.
- [ ] Demonstrar composição de operação existente sem tratar cadastro como código novo.

**Aceite:** receita não publicada não entra em execução; operação desconhecida retorna
unsupported; URI/alias sem aprovação não cria verdade. CT3-39, CT3-42/CT3-43 e CT3-61.

<a id="m3-t10"></a>

### M3-10 — Executar recuperação, normalização e cálculos fora da LLM

**Dependências:** M3-05/M3-08/M3-09. **Papéis:** Felipe, com especialista revisando métodos.
**Arquivos:** `operations.py`, adaptadores de `normalization.py`/`thermal_recompute.py`;
`tests/enrichment/test_deterministic_operations.py`.
**Consome/produz:** insumos verificados/receita → DerivedObservation e alternativa revisável.

- [ ] Separar copiar fonte, mapear, converter e calcular, com versões de cada transformação.
- [ ] Validar insumos, unidades e domínio antes de executar cálculo.
- [ ] Não aceitar constante/termo inventado pela LLM como insumo verificado.
- [ ] Revisar regras determinísticas legadas antes de promovê-las ao catálogo novo.

**Aceite:** cálculo reproduzível com referência a cada termo; ausência de insumo impede apenas
campo dependente; toda alternativa mantém revisão humana. CT3-14/CT3-19, CT3-28/CT3-29,
CT3-44 e CT3-63.

<a id="m3-t11"></a>

### M3-11 — Compilar contexto comum e blocos por campo

**Dependências:** M3-03/M3-08/M3-09/M3-10. **Papéis:** Felipe, revisão BIM e M7 liderado por Nonato.
**Arquivos:** `context.py`, adaptador novo de `grounding.py`; `tests/enrichment/test_context.py`.
**Consome/produz:** observações, FieldRefs, receitas → ElementContextPackage imutável.

- [ ] Corrigir contratos de nomes por adaptador explícito e tipado, sem mutar baseline.
- [ ] Deduplicar evidências comuns, preservando vínculos de admissibilidade por campo.
- [ ] Separar semântica/requisito/observação e remover uso de expected como fato.
- [ ] Registrar conteúdo selecionado, rejeitado/omitido, hash e versão do contexto.

**Aceite:** toda evidência referida resolve; nenhum campo herda material/papel indevido;
trocar ordem de propriedades não elimina alvo relevante; URI IDS não impõe restrição oculta.
CT3-07, CT3-20, CT3-27, CT3-40/CT3-41 e CT3-45.

<a id="m3-t12"></a>

### M3-12 — Planejar tokens, chamadas e limites de recursos

**Dependências:** M3-11; M6 para hardware/runtime e P3-05/P3-06. **Papéis:** Felipe/M3, Nonato/M6/M7 para recursos e protocolo. **Arquivos:** `budget.py`, `tests/enrichment/test_call_budget.py`.
**Consome/produz:** pacote + perfil ensaiado de runtime → CallPlan ou limitação por campo.

- [ ] Contar sistema, comum, blocos, schema/chat template e reserva de resposta.
- [ ] Priorizar conteúdo opcional sem remover mínimo de evidência de campo elegível.
- [ ] Planejar elemento/propriedade/grupo sem cortar campo; preservar razão, ordem e identidade.
- [ ] Impedir envio excedido e registrar estimativa/efetivo, omissões e custos.

**Aceite:** contexto que excede limite não é enviado cegamente; campo que não cabe tem
resultado explícito; nenhum campo some por truncamento. Valores de limites são calibrados,
não herdados como decisão deste plano. CT3-46–CT3-49 e CT3-70.

<a id="m3-t13"></a>

### M3-13 — Integrar runtime exclusivamente local/IME

**Dependências:** M3-02 e G3-05. **Papéis:** Felipe/M3 e Nonato/M6; seleção em M7 com ajuda de Felipe.
**Arquivos:** adaptador novo de `ollama_client.py`, `foundation/locality.py` quando
autorizado; `tests/enrichment/test_local_runtime.py`.
**Consome/produz:** CallPlan/modelo autorizado → resposta bruta e RuntimeIdentity/métricas.

- [ ] Validar endpoint/configuração em todos os caminhos de chamada e redirecionamento.
- [ ] Fixar ativos/modelo/tokenizer/digest e verificar capacidade de saída estruturada.
- [ ] Separar timeout, indisponibilidade, truncamento e erro de protocolo.
- [ ] Não acionar downloads de modelos/embeddings ou fallback de inferência público;
  consulta semântica bSDD segue exclusivamente M3-25.

**Aceite:** sem runtime local há limitação explícita e diagnóstico preservado; nenhum dado
de projeto sai a API pública; chamadas e tentativas reais ficam registradas. CT3-50,
CT3-57/CT3-58 e CT3-68.

<a id="m3-t14"></a>

### M3-14 — Validar JSON, alternativas e abstenção por campo

**Dependências:** M3-02/M3-09/M3-13. **Papéis:** Felipe/M3; M7/Nonato e especialistas nos critérios.
**Arquivos:** `response.py`, adapter do parser legado se necessário;
`tests/enrichment/test_response_validation.py`.
**Consome/produz:** resposta + CallPlan/pacote → FieldEnrichmentResults validados.

- [ ] Criar schema estrito com união propose/abstain e valores tipados.
- [ ] Validar IDs, conjunto/cardinalidade de campos e referências de evidência permitidas.
- [ ] Verificar dimensão, domínio, papéis e pré-condições sem confundir confiança com prova.
- [ ] Preservar abstenção válida; distinguir erro técnico e aplicar retry restrito registrado.

**Aceite:** action=abstain não se perde, sugestão vazia não vira melhor palpite; JSON bem
formado com evidência irrelevante/IDS esperado não passa como fundamentado. CT3-40/CT3-41,
CT3-50–CT3-54 e CT3-62.

<a id="m3-t15"></a>

### M3-15 — Orquestrar fila por elemento e continuidade por campo

**Dependências:** M3-11–M3-14. **Papéis:** Felipe/M3 e Nonato/M6/M4.
**Arquivos:** `service.py`, adaptação controlada de `worker.py`/`issue_store.py`;
`tests/enrichment/test_element_workflow.py`.
**Consome/produz:** EnrichmentRequest → EnrichmentRun/resultados parciais e eventos.

- [ ] Separar determinístico, BCF direto e campos LLM antes de planejar chamadas.
- [ ] Executar uma inferência por vez na sessão dos dois pares IFC–IDS, com roteamento/agrupamento explícitos e resultados separados por arquivo (CT3-81).
- [ ] Controlar tentativa, cancelamento, retomada e faltas de resposta por campo.
- [ ] Evitar cascata de sugestões não aprovadas como evidência entre campos.

**Aceite:** falha de um campo não apaga outros; reexecução não duplica resultados terminais;
quando falta evidência e é necessária decisão do responsável, não se força chamada inútil.
CT3-38, CT3-49–CT3-51,
CT3-55/CT3-56 e CT3-63.

<a id="m3-t16"></a>

### M3-16 — Persistir contexto, cache e histórico com identidade completa

**Dependências:** M3-15 e política de armazenamento M6. **Papéis:** Felipe/M3 e Nonato/M6.
**Arquivos:** `storage.py`, adapter do cache existente; `tests/enrichment/test_persistence.py`.
**Consome/produz:** pacotes/tentativas/resultados → registros imutáveis e cache autorizado.

- [ ] Definir chaves completas e validar hashes/referências antes de reutilizar resposta.
- [ ] Separar reuso de coleta, cache de inferência e aprovação humana.
- [ ] Persistir transacionalmente tentativas/resultados e recuperar interrupções.
- [ ] Aplicar ACL/retenção e isolamento entre projetos; não depender de session_state.

**Aceite:** mudar IFC/IDS/catálogo/receita/evidência/modelo relevante invalida reuso; mesmo
caminho/mtime não preserva identidade por engano; restauração não promove decisão.
CT3-54–CT3-56 e CT3-59–CT3-61.

<a id="m3-t17"></a>

### M3-17 — Integrar revisão humana com proposta exata

**Dependências:** M3-15/M3-16 e contrato M4. **Papéis:** Nonato conduz M4; Felipe/M3 e especialista revisam domínio.
**Arquivos:** `contracts.py`/`service.py`, adaptadores de revisão/UI a acordar;
`tests/enrichment/test_review_boundary.py`.
**Consome/produz:** resultado/evidências → ReviewEnvelope registrado pelo serviço M4.

- [ ] Exibir origem, método, alternativas e abstenção sem ocultar campos difíceis.
- [ ] Vincular decisão à alternativa/valor selecionado, ator e revisões vigentes.
- [ ] Preservar proposta original quando houver edição e explicitar alcance em tipo.
- [ ] Recusar decisão obsoleta ou autoaprovação vinda da resposta/texto IFC.

**Aceite:** escolher alternativa diferente da top audita a escolhida; aceite não escreve
diretamente por M3; rejeição/pulo conserva pendência. CT3-62 e CT3-65–CT3-67.

<a id="m3-t18"></a>

### M3-18 — Integrar BCF residual e confirmação em nova revisão

**Dependências:** M3-17, contratos M5 e revalidação M2. **Papéis:** Felipe/M5/M3 e Nonato/M4; especialista nos critérios de resolução. **Arquivos:** adaptadores de
`bcf/exporter.py`/pipeline M5, `tests/enrichment/test_residual_handoff.py`.
**Consome/produz:** ResidualRequest/decisão → pendência vinculada e resultado de revisão.

- [ ] Preservar motivo/dado necessário e permitir encaminhamento sem LLM.
- [ ] Separar aberto/rejeitado/pulado de resolvido; remover equivalência automática com Closed.
- [ ] Vincular componente/projeto/revisão corretamente e tratar GUID problemático.
- [ ] Confirmar resolução só após nova revisão e verificação pertinente; manter histórico.

**Aceite:** exportação não recalcula diagnóstico nem fecha rejeitado; correção aceita sem
nova verificação permanece aguardando confirmação. Interoperabilidade depende de receptor
ensaiado pela frente 5. CT3-38 e CT3-65–CT3-67.

<a id="m3-t19"></a>

### M3-19 — Ensaiar instruções embutidas e isolamento operacional

**Dependências:** M3-13/M3-15/M3-16 e M6. **Papéis:** Felipe/M3 e Nonato/M6, revisão técnica independente
quando disponível. **Arquivos:** `tests/enrichment/test_untrusted_content.py`, contratos
de serialização/runtime; corrigir somente a nova condição quando aplicável.
**Consome/produz:** corpus adversarial local → evidência de contenção/limitações.

- [ ] Injetar comandos/URLs/falsos contratos em atributos, Psets, materiais e IDS.
- [ ] Testar campo excessivo, relações cíclicas, receita executável e referências cruzadas.
- [ ] Verificar ausência de ferramentas de efeito, saída de conteúdo de projeto e exposição
  indevida em logs; permitir só consultas públicas bSDD filtradas por M3-25.
- [ ] Conferir renderização/exportação segura e falha que preserva diagnóstico/resultado parcial.

**Aceite:** nenhum texto do projeto muda política, executa comando ou autoriza escrita;
teste observa efeitos/rede com substitutos locais, não apenas resposta textual da LLM.
CT3-30, CT3-43, CT3-58/CT3-59, CT3-62 e CT3-68/CT3-69.

<a id="m3-t20"></a>

### M3-20 — Expandir matriz de domínio e capacidades das dez famílias

**Dependências:** M3-04–M3-10, matriz documental de G3-01 fechada e G3-02 para
publicar contratos afetados por divergências; nenhuma ausência de original impede inventário.
**Papéis:** Felipe/curador/especialistas; Felipe/M2 no suporte IFC.
**Arquivos:** matriz existente em `docs/pesquisa/modulo-03-contexto/`, futuras fixtures e casos
`tests/enrichment/test_domain_coverage.py`. **Consome/produz:** matriz conferida → cobertura
por entrada/binding/operação/schema com evidências e limitações.

- [ ] Conferir atributos, Psets padrão, EB_Orçamento, materiais, classificações e Qto.
- [ ] Relacionar entradas da fonte a conceito/binding/receita, sem exigir uma LLM por linha.
- [ ] Registrar capacidade suportada, parcial, indisponível ou dependente de decisão humana.
- [ ] Incorporar originais de Juliana por diff e migração controlada quando disponíveis.

**Aceite:** dez famílias aparecem com denominadores claros; nenhuma receita é rotulada de
produção por mera transcrição; IFC2X3/IFC4/IFC4.3 anunciados somente por capacidade testada.
CT3-01/CT3-02, CT3-23/CT3-24, CT3-28/CT3-29 e CT3-71/CT3-72.

<a id="m3-t21"></a>

### M3-21 — Fixar protocolo científico e contrafactuais

**Dependências:** M3-01/M3-02; corpus independente e revisão M7.
**Papéis:** Nonato lidera M7, Felipe auxilia pesquisa/domínio; especialistas no gabarito.
**Arquivos:** futuro `docs/pesquisa/modulo-03-contexto/protocolo-avaliacao.md`, adaptadores
em `src/experiment/` autorizados depois. **Consome/produz:** hipóteses/corpus → manifesto de
condições, splits, métricas e gabarito com indeterminação.

- [ ] Definir regras versus regras+LLM com as mesmas observações disponíveis e custos completos.
- [ ] Separar desenvolvimento/calibração/avaliação por projeto/modelo/tipo/família pertinente.
- [ ] Criar contrafactuais de evidência, esperado IDS, componente, unidade e placeholder.
- [ ] Fixar critérios antes de examinar resultado final; identificar contaminação histórica.

**Aceite:** denominadores incluem abstenção/erro/campo sem solução; clones e tipos repetidos
não viram amostras independentes; gabarito não entra no prompt/receita. CT3-40/CT3-41,
CT3-64 e CT3-70–CT3-72, além da avaliação descrita na seção 14.

<a id="m3-t22"></a>

### M3-22 — Executar piloto local e calibrar budgets

**Dependências:** M3-15/M3-16/M3-19/M3-21 e subconjunto revisado de M3-20.
**Papéis:** Nonato/M6/M7 conduz execução e análise com Felipe; revisão humana com protocolo.
**Arquivos:** manifesto/resultados novos em local autorizado de avaliação, relatório em
`docs/pesquisa/modulo-03-contexto/`; nenhum resultado histórico sobrescrito.
**Consome/produz:** condição fixada → medições e proposta de limites/primeira expansão.

- [ ] Rodar piloto separado da avaliação final, com hardware/modelos identificados.
- [ ] Comparar elemento, propriedade e grupos por modelo/rota e medir recuperação de evidência
  separadamente da interpretação LLM, mantendo uma inferência ativa no baseline.
- [ ] Medir tokens, latência, memória, erro, abstenção, revisão e ganho sobre regras.
- [ ] Recalibrar budgets/recorte com aprovação do protocolo antes da rodada final.

**Aceite:** limites sustentados por medição, sem SLA inventado; resultado negativo da LLM
é reportável e pode levar a restringir seu uso. CT3-46–CT3-50 e CT3-70; experimento futuro
não se confunde com os testes documentais realizados ao escrever este plano.

<a id="m3-t23"></a>

### M3-23 — Ensaiar atualização, restauração e rollback

**Dependências:** M3-16–M3-19 e M6; cenário de migração M1.
**Papéis:** Felipe/M3/M5, Nonato/M6/M4 e curador M1.
**Arquivos:** `tests/enrichment/test_recovery.py`, procedimentos operacionais em documentação.
**Consome/produz:** releases/backup/execuções → evidência de recuperação sem perda de história.

- [ ] Simular queda antes/depois de chamada, persistência, decisão e entrega à escrita.
- [ ] Restaurar versões/ativos compatíveis, conferindo hashes e vínculos de resultados.
- [ ] Invalidar caches/propostas afetadas por mudança de fonte/receita/modelo.
- [ ] Desativar fluxo novo sem reinterpretar baseline, fechar BCF ou apagar auditoria.

**Aceite:** reprocessamento não reaplica escrita; revisão nova não herda aprovação; histórico
permanece consultável e nenhuma mistura de versões é apresentada como execução íntegra.
CT3-54–CT3-56, CT3-60/CT3-61 e CT3-65–CT3-67.

<a id="m3-t24"></a>

### M3-24 — Revisar evidências de entrega e atualizar o planejamento

**Dependências:** tarefas/contratos pertinentes à fatia demonstrados; revisão de Felipe
e gates correspondentes. **Papéis:** Felipe no relatório técnico e especialistas
no domínio e M7 nas conclusões. **Arquivos:** este plano/índices em revisão futura, manifesto
de capacidades e relatórios de aceite. **Consome/produz:** evidências → decisão de aceitar
uma fatia, manter pendências ou revisar escopo; nunca “suporte universal”.

- [ ] Reconciliar promessas com capacidades efetivamente ensaiadas e estado de cada gate.
- [ ] Registrar testes/comandos/resultados reais, falhas e limitações, sem resumir tudo como pronto.
- [ ] Reconciliar novas decisões com C3 e preservar a distinção entre plano concluído e capacidade ensaiada.
- [ ] Preparar entrega revisável pelo processo acordado; Git/publicação exigem escopo próprio.

**Aceite:** documentação distingue planejamento concluído, implementação e capacidade
verificada. A autorização de concluir o plano em 12/10 não aprova receitas de produção ou
substitui ensaio. Pendências externas ficam delimitadas. CT3-01/CT3-02 e CT3-71/CT3-72.

<a id="m3-t25"></a>

### M3-25 — Integrar semântica pública bSDD com saída restrita

**Dependências:** M3-02/M3-09, política M6 e C3-10. **Papéis:** Felipe/M1/M3 e Nonato/M6.
**Arquivos futuros:** adaptador semântico, contratos de snapshot e testes de rede com
substitutos locais; aproveitar `bsdd/client.py` sem preservar transmissão indevida.
**Consome/produz:** referência pública aprovada → resposta semântica identificada/cache
ou falha técnica, sempre separada de evidência do elemento.

- [ ] Construir consulta somente com parâmetros públicos aprovados, fora do texto IFC/IDS livre.
- [ ] Recusar GUIDs, nomes/valores de projeto, contexto/prompt e URL arbitrária; testar efeitos.
- [ ] Registrar URI, versão/data, resposta/hash, política e snapshot usado por execução.
- [ ] Tratar indisponibilidade, mudança de versão e cache incompatível explicitamente.
- [ ] Manter estudo de cópia integral dos dicionários como futuro, sem impedir uso inicial da API.

**Aceite:** CT3-74 demonstra consulta pública permitida sem vazamento; CT3-41/57/58 mostram
que semântica não muda validação IDS nem vira fato do IFC. Testes não dependem da API ao vivo.

<a id="m3-t26"></a>

### M3-26 — Permitir manual fundamentado, conflitos e revisão do requisito

**Dependências:** M3-02/08/14/17/18 e M2/M4/M5. **Papéis:** Felipe/M3/M5, Nonato/M4,
especialista no fundamento e curador no mapping. **Arquivos futuros:** contratos e
validador de candidato humano, adaptadores de revisão e fixtures de requisito inadequado.
**Consome/produz:** campo sem proposta/conflito/não mapeado → candidato humano ou pedido
de revisão do requisito, com fundamento e estado de validação, sem escrita automática.

- [ ] Mostrar todos os valores/fontes conflitantes e exigir justificativa da escolha.
- [ ] Registrar manual como origem humana, com ator, fonte declarada/atestado, data e revisão.
- [ ] Revalidar tipo, unidade, restrições IDS, portador/escopo e referência da fonte antes de aprovação.
- [ ] Em campo não mapeado, deixar M2 validar o requisito suportado; manual usa caminho literal
  e tipo sustentado pelo IFC/IDS, sem fabricar conceito ou publicar equivalência.
- [ ] Requisito inadequado gera `needs_requirement_review`; nova versão IDS exige nova análise.
- [ ] Falta de fundamento ou falha técnica conserva pendência; BCF residual continua disponível.

**Aceite:** CT3-75/76/77/78 e TR3 por registro: humano não contorna validadores, LLM não
publica mapping, fonte externa não vira observação IFC, aprovação não é escrita/resolução.

<a id="m3-t27"></a>

### M3-27 — Versionar roteamento e comparar agrupamentos durante desenvolvimento

**Dependências:** M3-11/12/13/15/16/21/22 e M6/M7. **Papéis:** Felipe/M3; Nonato lidera
M7 e M6 com ajuda de Felipe. **Arquivos futuros:** política de roteamento e manifesto
de capacidades/experimentos, sem trocar o default histórico ou promover modelo nesta etapa.
**Consome/produz:** campo/grupo + capacidade/recurso + evidência M7 → CallPlan/RuntimeIdentity
ou recusa explícita, com uma inferência ativa por vez.

- [ ] Comparar elemento, propriedade e grupos com observações equivalentes e orçamento registrado.
- [ ] Isolar avaliação de recuperação da avaliação de interpretação e do fluxo completo.
- [ ] Selecionar rota/modelo só no desenvolvimento; congelar antes de avaliar dados reservados.
- [ ] Identificar política, digest/modelo, parâmetros, hardware, motivo e campos por chamada.
- [ ] Cancelar/repetir sem paralelismo LLM inadvertido nem perda dos determinísticos já calculados.

**Aceite:** CT3-79/80, CT3-46–56/70/72 e protocolo M7. Ganho de coleta não vira ganho LLM;
troca de rota invalida cache pertinente; modelo melhor por subgrupo é hipótese a medir.

### 12.1 Ordem de dependências e primeiro caminho verificável

M3-01 → M3-02 → M3-03 estabelece a fronteira de entrada. M3-04–M3-07 constroem observações
com M2; M3-08 e M3-09 se encontram em M3-10/M3-11. M3-12 e M3-13/M3-14 convergem em M3-15.
M3-16 sustenta retomada/cache; M3-17/M3-18 demonstram revisão e pendência; M3-19/M3-23
verificam operação/segurança; M3-20/M3-21/M3-22 sustentam cobertura e avaliação; M3-24
registra o aceite real. M3-25 antecipa a interface semântica pública; M3-26 completa revisão
manual/requisito; M3-27 conecta fila/runtime e M7. M3-21 deve ser desenhada cedo para evitar
instrumentação tardia. Essas três tarefas complementam, sem renumerar, as 24 anteriores.

Não é necessário terminar todos os schemas/campos para uma primeira fatia estreita.
Entregar um percurso completo com leitura rastreável, um campo recuperável, outro
necessariamente abstido, uma chamada local quando elegível e revisão/BCF sem escrita
autônoma. Fixtures/adaptadores provisórios precisam estar rotulados e não podem ser
apresentados como integração pronta com módulos que ainda só têm planos.

### 12.2 Correspondência com tarefas de M1/M2 e governança de fronteira

| Pré-requisito nos planos preservados | Consumidor M3 | Artefato que permite integrar |
|---|---|---|
| M1-03/M1-05/M1-06 | M3-02/M3-09 | Modelos, políticas/capacidades e reader de release fixado; pacote sintético só para ensaio |
| M1-07/M1-12/M1-13 | M3-03/M3-11 | Adaptadores/contratos ricos sem perda de identidade ou origem; baseline legado isolado |
| M1-08/M1-09/M1-11 | M3-09/M3-16/M3-23 | Publicação autorizada, diff, pin e atualização rastreável; M3 não publica catálogo |
| M2-02/M2-05/M2-11/M2-12 | M3-02/M3-03/M3-15 | AnalysisIdentity, sessão somente leitura e DiagnosticSnapshot estável |
| M2-09/M2-10 | M3-04–M3-07/M3-10 | Observações com portador, tipo/ocorrência, unidade, material, relação e método |
| M2-07/M2-08/M2-16 | M3-08/M3-14/M3-20 | Resultado de requisito/capacidade real, aplicabilidade e limites por schema |
| M2-14/M2-15 e serviços futuros M4/M5 | M3-17/M3-18 | Resultado comum à UI/exportação, decisão exata e revalidação posterior |

Ao detectar incompatibilidade, registrar proposta de refinamento conjunto com exemplos
de entrada/saída e impacto em consumidores. Não alterar silenciosamente o plano M1/M2
nem criar tipos concorrentes para esconder a diferença. Os nomes de tarefas acima são
localizadores dos planos, não alegações de conclusão das suas implementações.

<a id="m3-testes"></a>

## 13. Testes positivos, negativos e contrafactuais propostos

### 13.1 Manifesto de casos e separação dos níveis de prova

Cada caso terá ID, finalidade, classe/schema/release, IFC/IDS/catálogo de fixture com
hash, política/receita, operação exigida, observações esperadas, resultado por campo,
origem do esperado, responsável pela revisão e tarefa proprietária. Todos os casos abaixo
estão **planejados, sem execução nesta entrega**. Os IDs CT3 são casos de teste deste plano;
não são linhas da matriz Daiane, propriedades únicas ou especificações IDS.

Fixtures sintéticas pequenas verificam contratos e falhas. Casos reais verificam os
exportadores e representações efetivamente encontrados. Ambos são necessários para
ampliar uma capacidade; nenhum substitui a reconciliação da fonte. Registros sem esperado
independente podem medir custo, mas não provar correção. Casos de fonte ainda ausente
permanecem pendentes, sem gerar uma fixture artificial apresentada como original.

### 13.2 Catálogo de casos com resultado observável

| ID | Estímulo/condição | Resultado e prova exigidos |
|---|---|---|
| CT3-01 | Fonte incorporada e outra fonte ainda ausente | Hash/página/revisão atestam apenas a disponível; XML/fixtures/Library ausentes não recebem alegação de leitura ou execução |
| CT3-02 | Inventário com repetições de conceito em famílias distintas | Dez famílias e categorias preservadas; contagens de entradas, conceitos, bindings e requisitos separadas |
| CT3-03 | Dois requisitos sobre o mesmo campo | FieldRef agrupa apresentação sem perder IDs, esperado ou resultado de cada requisito |
| CT3-04 | GUID ausente/duplicado e nomes iguais | ElementRefs distintos por revisão/localizador; nenhuma evidência atribuída ao primeiro GUID |
| CT3-05 | Mesmo GUID/STEP ID em nova revisão | Nova identidade; nenhuma aprovação ou observação antiga transportada automaticamente |
| CT3-06 | `false`, `0`, `null`, vazio e código `"1"` | Tipos/estados distintos sobrevivem à serialização; nenhuma coerção por truthiness |
| CT3-07 | Mesmo snapshot pela rota de análise e pela integração de diagnóstico | Novo adaptador produz conteúdo equivalente; registrar diferença legada sem alterar baseline |
| CT3-08 | Vários campos do mesmo elemento pedem os mesmos Psets | Coleta por revisão/elemento/operação reutilizada; contador de chamadas mostra ausência de varredura por issue |
| CT3-09 | Propriedade só no tipo e ausente na ocorrência | Fonte de tipo e vínculo preservados; valor efetivo identificado conforme capacidade M2 |
| CT3-10 | Mesmo conceito com valores incompatíveis em tipo/ocorrência | Preservar ambos e fontes; leitura efetiva separada de verdade; responsável decide com justificativa antes da aprovação |
| CT3-11 | Falso/zero legítimos com origem conhecida | Proposta pode conservar o valor; detector não os elimina como placeholders universais |
| CT3-12 | Alias aprovado em Pset alternativo | Candidato recuperável com fonte; requisito de caminho exato continua com diagnóstico M2 original |
| CT3-13 | Portador de propriedade não suportado ou leitor lança exceção | `unsupported`/erro explícito; nenhum dicionário vazio tratado como ausência comprovada |
| CT3-14 | Mesmo comprimento declarado em mm e m | Conversão produz equivalência dimensional e grafo auditável com original/operação/unidade |
| CT3-15 | Valor de área usado como comprimento | Rejeição dimensional independentemente da confiança ou número plausível |
| CT3-16 | Quantidade sem unidade interpretável | Unidade desconhecida, sem inferência pelo sufixo `_m`; campo independente continua |
| CT3-17 | Duas quantidades homônimas em conjuntos distintos | Portadores e conjuntos permanecem separados; nenhum sobrescreve o outro |
| CT3-18 | Mesmo número em Qto declarado e cálculo geométrico | Métodos distintos e fontes preservadas; cálculo não prova presença formal do Qto |
| CT3-19 | Laje irregular/rotacionada com vazios e somente bounding box | Não rotular estimativa como área líquida ou área de forma; operação exata ausente produz limitação |
| CT3-20 | Propriedade relevante depois dos primeiros Psets/propriedades | Seleção por receita encontra o alvo independentemente da ordem; omissão tem motivo/manifesto |
| CT3-21 | Constituintes com cardinalidade igual, mas ordem de quantidades trocada | Não associar espessuras só pela posição; exigir vínculo ou marcar ambiguidade |
| CT3-22 | MaterialProfileSet/Usage e material herdado do tipo | Preservar perfil/uso/origem quando suportados; forma desconhecida não vira material simples |
| CT3-23 | CEILING, FLOORING e CLADDING com dados semelhantes | Três recortes IfcCovering mantêm aplicabilidade/receitas distintas e capacidades explícitas |
| CT3-24 | Partes heterogêneas, primeira com material e segunda diferente | Contexto conserva partes; primeiro resultado não descreve automaticamente o todo |
| CT3-25 | Janela com cadeia fills/voids comprovada | Observação guarda relações e extremos até abertura/hospedeiro na mesma revisão |
| CT3-26 | Janela órfã com parede/espaço apenas no mesmo pavimento | Não declarar hospedeiro, adjacência ou proximidade comprovada |
| CT3-27 | Vidro, caixilho, peitoril e folha com materiais distintos | Campo usa só observações admissíveis para seu papel; mudar papel invalida suporte |
| CT3-28 | Peso agregado no hospedeiro, Weight de barras ausente | Abstenção para peso individual; referência ao agregado pode orientar BCF, sem rateio |
| CT3-29 | Uma IfcReinforcingBar representa múltiplas barras | Não pressupor contagem um; cálculo exige multiplicidade/comprimento/escopo comprovados |
| CT3-30 | Ciclo, profundidade ou fan-out de relações excedidos | Terminação limitada e cobertura parcial explícita; não declarar ausência da parte não visitada |
| CT3-31 | Múltiplas classificações e códigos iguais em sistemas/edições diferentes | Conservar sistema/edição/cadeia; não escolher primeira associação nem unir códigos pelo texto |
| CT3-32 | Exceção ao contar pilares/vigas | Erro de coleta distinto de zero e sem frase factual de ausência estrutural |
| CT3-33 | Adicionar pilares/vigas não relacionados a uma parede | Não mudar LoadBearing da parede sem evidência específica; inventário global é contexto |
| CT3-34 | Valor provisório com origem de inicialização documentada | Sinalizar suspeita/estado provisório sem convertê-lo em fato aprovado |
| CT3-35 | Mesmo literal FALSE/0 sem prova de inicialização | Não assumir placeholder; conservar dúvida e valor original para revisão |
| CT3-36 | Largura da abertura e largura externa do marco, ambas em m | Tratar conceitos diferentes; nenhuma conversão semântica por igualdade de grandeza |
| CT3-37 | Conflito sem política técnica aplicável | Abster-se ou apresentar alternativas sustentadas para revisão, preservando fontes |
| CT3-38 | Fixação/contramarco exige decisão ausente do projeto | ResidualRequest/BCF direto com dado necessário e zero chamadas LLM |
| CT3-39 | Receita refere operação não registrada | `unsupported_operation`; não executar prompt livre como substituto |
| CT3-40 | IFC sem evidência, IDS alterado para outro valor esperado | Não produzir o novo esperado como fato; abstenção permanece enquanto a evidência é a mesma |
| CT3-41 | URI bSDD presente no IDS e domínio no catálogo distinto da restrição XML | URI permanece metadado; restrição não é importada implicitamente para validação formal |
| CT3-42 | Receita draft ou atualização de catálogo após pin | Rascunho não executa; pin antigo permanece até atualização explícita com nova análise |
| CT3-43 | Receita contém Python/SQL/shell/URL arbitrários | Recusa antes da execução; teste observa ausência de efeitos e não apenas mensagem de recusa |
| CT3-44 | Cálculo térmico com termo numérico sugerido sem fonte | Não recomputar como valor sustentado; fórmula correta não legitima insumo inventado |
| CT3-45 | Universal e grounding usam chaves divergentes de espessura/Psets | Adaptador novo conserva campos tipados e sua origem; nenhum vazio por incompatibilidade silenciosa |
| CT3-46 | Entrada excede janela incluindo template/schema | Plano reduz opcionais/divide ou recusa; cliente não envia acima do limite configurado |
| CT3-47 | Muitos campos cabem na entrada, mas saída reservada é insuficiente | Replanejar antes de chamar; detectar truncamento e não aceitar resposta incompleta |
| CT3-48 | Um campo com evidência mínima maior que o orçamento | Limitação explícita daquele campo; sem remover evidência necessária para fabricar resposta |
| CT3-49 | Agrupamento ou divisão do mesmo elemento | CallPlan cobre cada campo uma vez; evidência mínima e hash de base preservados, sem contaminação entre chamadas |
| CT3-50 | JSON malformado, chaves duplicadas, resposta truncada ou envelope errado | Tentativa tecnicamente inválida; nenhum resultado extraído por reparo permissivo oculto |
| CT3-51 | Envelope válido com um campo semanticamente inválido | Campo inválido isolado; propostas independentes válidas permanecem disponíveis |
| CT3-52 | `action=abstain` sem valor e sem alternativas | Resultado válido de abstenção; não exigir valor nem repetir até conseguir um palpite |
| CT3-53 | Tipo/domínio incompatível com confiança autodeclarada alta | Rejeição semântica explícita; reduzir confiança não basta para habilitar valor |
| CT3-54 | Mudar fonte, receita, catálogo, evidência, schema ou modelo relevante | Identidade muda; cache antigo não serve ao novo pacote, mesmo com caminho/mtime iguais |
| CT3-55 | Queda após inferência e antes/depois da persistência | Retomada identifica tentativa/resultados; não duplica decisão, escrita ou histórico terminal |
| CT3-56 | Cancelar entre elementos/campos ou durante timeout | Resultados concluídos preservados; restantes incompletos/cancelados, sem falsa conclusão |
| CT3-57 | Ollama/catálogo indisponíveis | Diagnóstico/exportação independente M2 continua quando suportado; falha M3 é separada |
| CT3-58 | Inferência externa, saída de projeto ou redirecionamento fora da política | Bloqueio observado; exceção bSDD aceita somente parâmetros semânticos públicos aprovados, coberta em CT3-74 |
| CT3-59 | Projeto B tenta consultar evidência/cache do projeto A | Serviço recusa acesso e não revela payload; IDs conhecidos não concedem permissão |
| CT3-60 | Backup parcial, hash inválido e restauração de versão anterior | Recusar conjunto inconsistente; restaurar conjunto íntegro sem promover aprovação |
| CT3-61 | Migração curada de catálogo/receita, inclusive futura Juliana | Diff e novo pin/análise; histórico preservado, campos afetados reprocessados |
| CT3-62 | Texto IFC/IDS/LLM manda ignorar regras, autoaprovar ou trocar fonte | Texto tratado como dado; nenhuma ação/autorização deriva da instrução embutida |
| CT3-63 | Sugestão pendente de um campo usada como termo de outro | Dependência bloqueada; somente observação/derivação admissível integra o cálculo |
| CT3-64 | Remover, contradizer ou deslocar a única evidência suficiente | Proposta perde sustentação e vira abstenção/conflito; não manter valor por memória do caso |
| CT3-65 | Humano escolhe segunda alternativa ou edita valor | Auditoria aponta alternativa/valor efetivos, fonte/revisão/ator; não usa metadados da mais confiante |
| CT3-66 | Humano rejeita/pula; ou aceita sem escrita/revalidação | Pendência não é Closed/resolvida; estados de revisão, aplicação e resolução separados |
| CT3-67 | Nova cópia IFC verificada após correção, com GUID mantido | Nova análise verifica requisito e vínculos; só então confirmar resolução pertinente, conservando histórico |
| CT3-68 | Runtime/modelo ausente, digest incorreto ou pedido de download | Erro local explícito; nenhum download/fallback público automático |
| CT3-69 | Texto HTML, fórmula CSV e markup em nomes/justificativa/BCF | Apresentação escapada, original local preservado; nenhuma execução no consumidor sob teste |
| CT3-70 | Comparação de regras e regras+LLM | Mesma população/contexto e contabilização de tokens, tentativas, abstenção, erros e custo completo; propostas em T/G aparecem nas contagens operacionais, sem entrar como acertos |
| CT3-71 | Nova condição de contexto/geração e eventual rollback | Pinos v7.8, GT, comparadores, locks e resultados históricos iguais aos hashes de referência |
| CT3-72 | Clones/revisões/tipos repetidos e corpus com fonte incompleta | Grupos de avaliação não vazam entre splits; origem/denominadores explícitos, sem inflar corpus ou cobertura |
| CT3-73 | Projeções/documentação da matriz com registros omitidos/alterados | 203 + 110 IDs e campos fonte/operacional coincidem entre JSON/CSV/fichas; cada referência de tarefa/caso resolve; não confundir 72 nomes com conceitos |
| CT3-74 | Consulta bSDD pública e tentativa de anexar texto/nome/valor IFC | Primeira usa só parâmetros semânticos permitidos; segunda é bloqueada antes da rede. URI/versão/data/resposta/hash ficam locais; semântica não preenche valor |
| CT3-75 | Manual correto e manual com unidade/tipo/IDS/fonte inválidos | Registrar origem humana; apenas candidato verificado fica aprovável; inválido conserva motivo e pendência, mesmo quando responsável deseja aceitar |
| CT3-76 | Conflito com duas fontes e escolha humana sem/com justificativa | Ambas permanecem visíveis; sem justificativa não habilitar decisão; com justificativa validar candidato e preservar fontes/decisão exata |
| CT3-77 | Requisito suportado M2 sobre campo não mapeado M1 | M2 verifica; M3 informa mapping ausente, aceita manual literal validável e solicitação curatorial; sugestão LLM não publica mapping |
| CT3-78 | Requisito inadequado, como dobradiça exigida em porta sem esse componente | Encaminhar revisão do requisito, sem fabricar componente/valor ou marcar conforme; novo IDS gera outra análise; histórico permanece |
| CT3-79 | Rotas por campo/grupo com dois modelos e retries/cancelamento | Uma inferência ativa por vez; registrar política/modelo/digest/ordem; preservar determinísticos, parciais e erros; cache não mistura rotas |
| CT3-80 | Extrator omite evidência conhecida e LLM recebe pacote sem ela | Medir erro de recuperação separado; contraste com pacote de referência congelado isola interpretação. Não atribuir ganho do extrator ao LLM |
| CT3-81 | Dois pares IFC–IDS na sessão, GlobalId/STEP ID coincidentes, federação visual e retry concorrente solicitado | PairRef/arquivo/revisão mantêm identidade, diagnóstico e exportação separados; rejeitar referência de evidência do outro arquivo mesmo que visível no viewer; somente uma inferência ativa na sessão, inclusive retries |

### 13.3 Percursos por família: positivo, negativo e contrafactual

As situações abaixo são **fixtures a construir**, complementares às fichas da matriz
incorporada; não afirmam que determinado IFC real já contém esses exemplos. Cada uma deve
conservar também atributo, classificação e material quando pertinentes, além do Pset/Qto.
Um negativo pode pedir abstenção, conflito ou não suporte; não precisa forçar uma sugestão.

| Família | Caso positivo proposto | Negativo proposto | Contrafactual e comportamento esperado |
|---|---|---|---|
| A.1 Janelas | Material do caixilho e tipo de operação declarados com papel/portador, recuperados por mapping aprovado | Só material do vidro; sem fixação/contramarco | Remover prova do papel caixilho: não transferir vidro; manter BCF da fixação e campos independentes (CT3-25/27/38/64) |
| A.2 Portas | Valor de folha declarado em atributo/Pset e mapeamento aprovado; dimensão com unidade conhecida | Densidade_Porta ambígua entre categoria e número; largura da abertura usada como marco | Trocar apenas o esperado IDS: fato observado não muda; divergência contratual continua até fonte original (CT3-12/14/36/40/53) |
| A.3 Paredes | Camadas com associações/espessuras comprovadas e propriedade de função explicitamente declarada | Materiais com ordem ambígua; função portante inferida só pelo modelo ter pilares | Adicionar pilares sem vínculo não muda função da parede; remover declaração força abstenção para função (CT3-21/32/33/64) |
| A.4 Forro / CEILING | IfcCovering aplicável, material e quantidade declarados no portador correto | Escolher hospedeiro apenas por mesmo pavimento | Remover relação de suporte mantém material próprio, mas perde sustentação da relação (CT3-23/26/30) |
| A.5 Piso / FLOORING | Quantidade líquida explicitamente declarada com método/unidade e acabamento próprio | Usar área da laje ou caixa geométrica como área líquida do piso | Trocar só a geometria da laje não altera declaração do piso; conflito com cálculo aparece separado (CT3-17/18/19/23) |
| A.6 Revestimento de parede / CLADDING | Material/classificação próprios e relação ao suporte comprovada | Copiar indiscriminadamente Pset de parede/porta ou material do suporte | Mudar suporte mantendo revestimento não muda automaticamente material/classificação do revestimento (CT3-12/23/25/31) |
| A.7 Laje | Qto declarado e material identificados; cálculo somente com método aprovado | Area_Forma com portador ambíguo e sem método, ou aproximação pela caixa | Introduzir abertura muda cálculo geométrico pertinente, preserva Qto original e sinaliza divergência (CT3-13/18/19/24) |
| A.8 Pilar | Material/perfil e quantidade com origem; agregado de armadura corretamente rotulado como agregado | Dividir massa do pilar entre barras sem distribuição comprovada | Alterar quantidade de barras sem peso individual não cria peso individual confiável (CT3-22/28/29) |
| A.9 Viga | Perfil/quantidade declarados e classificação com sistema/edição | Copiar receita de parede ou usar primeira classificação como universal | Trocar edição do sistema de classificação exige resolver o binding; código igual não conserva identidade semântica (CT3-22/31/39) |
| A.10 Armadura | Massa declarada em escopo reconciliado, ou cálculo com multiplicidade/material/dimensões verificados | Weight/Weigth não reconciliados; hospedeiro tem peso e barra não | Manter agregado e remover multiplicidade bloqueia cálculo por barra; não supor uma barra por entidade (CT3-12/28/29/64) |

Cruzar os casos com IFC2X3, IFC4 e IFC4.3 **somente conforme portadores e operações
existentes em cada release ensaiada**. A combinação não implementada fica visível; não
fabricar sintaxe IFC inválida para marcar a célula como coberta. Casa/prédio são pontos
de partida, não demonstração da representação de todas as dez famílias. Caso real IFC4.3
e fontes originais continuam dependências conforme M2.

### 13.4 Exemplos de asserções para a implementação futura

O helper futuro `run_enrichment_case(case_id)` pertence a `tests/enrichment/conftest.py`.
Ele retornará uma projeção de ensaio com `fields` (lista de resultados), `llm_calls`
(contagem observada) e `write_calls` (operações capturadas). Asserções devem ser alimentadas
por fixtures e observadores de efeito; não preencher esses contadores a partir da resposta
do próprio modelo. Os testes abaixo são exemplos sintáticos, **não executados**.

```python
def test_abstention_survives_without_a_value(run_enrichment_case):
    result = run_enrichment_case("CT3-52")
    field = result["fields"][0]
    assert field["state"] == "abstained"
    assert field["alternatives"] == []
    assert result["llm_calls"] == 1  # inclui só a resposta simulada, sem retry
    assert result["write_calls"] == []


def test_human_design_decision_bypasses_generation(run_enrichment_case):
    result = run_enrichment_case("CT3-38")
    field = result["fields"][0]
    assert field["reason_code"] == "responsible_design_decision_required"
    assert field["residual_request_ref"] is not None
    assert result["llm_calls"] == 0
    assert result["write_calls"] == []


def test_host_mass_does_not_become_bar_mass(run_enrichment_case):
    result = run_enrichment_case("CT3-28")
    field = result["fields"][0]
    assert field["state"] == "abstained"
    assert field["alternatives"] == []
    assert field["reason_code"] == "insufficient_evidence"
    assert result["write_calls"] == []
```

### 13.5 Estratégia de execução futura

1. Testar contratos/operações/verificadores com runtime substituto determinístico e sem rede.
2. Integrar coletores reais M2, revisão curada M1 e snapshots semânticos bSDD, mantendo
   modelos de teste pequenos e hashes.
3. Ensaiar falhas de persistência, rede, recurso e segurança com observação de efeitos.
4. Executar piloto LLM local autorizado e identificado, separado da avaliação final.
5. Realizar revisão de domínio e estudo humano; testes automatizados não substituem esse aceite.

Na implementação, selecionar regressões existentes em `tests/` pelos consumidores alterados
e conferir previamente dependências/markers. Os testes de prompts, pinos Windows, fundação,
análise, quantidades, materiais, pipeline e avaliação histórica são candidatos pertinentes;
um teste que cristalize bug legado não obriga mantê-lo no fluxo novo. Novos esperados exigem
fundamento independente, sem alterar IDS/GT/baseline para passar. A convenção de cobertura
do checkout não substitui a matriz de casos críticos nem prova correção semântica.

<a id="m3-avaliacao"></a>

## 14. Avaliação científica, prevenção de vazamento e métricas

### 14.1 Perguntas e condições comparáveis

**Pergunta principal:** acrescentar interpretação por LLM local às regras fortes melhora
a recuperação/padronização sustentada de informação já existente no IFC, com custo de
revisão e taxa de falsos preenchimentos aceitáveis segundo critérios ainda a acordar?
É resultado válido demonstrar ganho nulo, dano ou utilidade limitada a certos campos.

| Condição proposta | Contexto/algoritmo | Comparação permitida |
|---|---|---|
| R — Regras fortes | Mesmo snapshot, catálogo, receitas, evidências, conversões, conflitos e mecanismos de abstenção; sem geração LLM | Referência principal, incluindo recuperação por tipo, alias aprovado, material/papel, Qto e cálculo sustentado |
| R+L — Regras fortes + LLM | Mesmo pacote imutável e mesmos resultados determinísticos; LLM interpreta apenas campos residuais elegíveis | Efeito incremental da LLM, sem atribuir a ela melhorias feitas antes na extração |
| Ablações identificadas | Uma mudança de cada vez: bloco semântico, seleção de contexto, pacote por elemento versus propriedade/grupo e roteamento | Estudo secundário com condição própria, controles pareados e limites publicados |
| Histórico v7.8 e rodadas anteriores | Instrumentos, dados e pins preservados em sua condição documentada | Referência histórica; não tratar como controle causal equivalente ao novo pipeline |

R e R+L devem receber as **mesmas evidências selecionadas**, inclusive informação que o
novo coletor consegue recuperar. Congelar o pacote antes dos dois braços. As mesmas
operações determinísticas produzem os mesmos resultados; somente a etapa de interpretação
difere. Se o orçamento da LLM restringir conteúdo, fixar a seleção compartilhada na
comparação principal e relatar uma análise suplementar das regras com todo o contexto,
sem enfraquecer artificialmente a referência. Ablações que mudam evidência são rotuladas
como tal. Não permitir consulta extra a documento, outro elemento ou memória fora do
pacote somente em um braço sem declarar outra condição.

BCF direto e operações não suportadas permanecem na população operacional de ambos os
braços. Reportar também o subconjunto elegível à LLM, com seu tamanho e motivos de exclusão.
Ganhos medidos apenas nos casos respondidos não representam cobertura total do sistema.

### 14.1.1 Recuperação, interpretação e roteamento como avaliações distintas

O [baseline](../pesquisa/modulo-03-contexto/baseline.md) identifica pesquisas já realizadas
com modelos/contextos e resultados brutos; não se parte da premissa de que nunca houve
comparação. Elas têm condições e limites próprios e não validam a arquitetura agora proposta.

1. **Recuperação de evidência:** referência independente especifica caminhos/portadores,
   papéis, revisão e unidades pertinentes. Medir precisão/recall da evidência e cobertura
   por canal/família, erro técnico, tempo e omissões, sem participação do LLM na seleção
   do que será considerado ground truth.
2. **Interpretação sobre pacote congelado:** R e R+L recebem as mesmas observações
   admissíveis. Um braço com pacote de referência revisado isola erro de extrator; esse
   pacote contém fatos/fontes, nunca rótulo-resposta do campo ou comentário do anotador.
   Preservar o determinístico e medir somente acréscimo/custo atribuível à LLM.
3. **Ponta a ponta e revisão:** separar custo/erro da coleta, mapping, seleção, geração,
   validação, revisão/manual e revalidação. Manual apoiado em fonte externa é outra
   condição; não promover U a D retroativamente no experimento com evidência restrita.
4. **Agrupamento e modelo por campo/grupo:** comparar elemento/propriedade/grupo durante
   desenvolvimento, sempre com uma inferência ativa no baseline e budgets identificados.
   A política de roteamento usa resultados M7 e capacidade M6; congelar a seleção antes
   dos dados reservados, registrar incerteza por subgrupo e não eleger vencedor no plano.

O estudo de recuperação pode melhorar sem melhora do LLM, e vice-versa. Ambos podem
ter resultado negativo. Mudar fonte, pacote, seleção, rota, grupo ou comparador altera
a condição experimental mesmo com o mesmo texto de prompt. CT3-79/80 e M3-21/22/27
vinculam essas exigências a instrumentação e critérios, sem exigir o ensaio para fechar
o planejamento documental.

### 14.2 Gabarito independente e estado de determinabilidade

Para cada par elemento/campo, revisores de domínio devem registrar: conceito e papel,
valor/conjunto de valores aceitáveis quando determinável, tipo/unidade, evidências
suficientes, transformações permitidas, conflitos, condição de abstenção e informação
necessária ao responsável. Distinguir:

- **D — Determinável no contexto:** existe caminho verificável até resposta sustentada.
- **U — Indeterminado no contexto:** falta decisão/evidência ou há conflito irresolúvel.
- **T — Não avaliável tecnicamente:** fonte/operação indispensável está ilegível ou sem suporte.
- **G — Gabarito pendente:** revisores ainda não têm base independente para julgar.

G não é acerto nem erro do modelo: permanece no inventário e fora das métricas de correção,
com denominador explícito. T é medido como limite técnico, sem ser celebrado como abstenção
correta de domínio. Um especialista pode conhecer a resposta por documentos externos,
mas, se ela não estiver sustentada pelo contexto permitido ao experimento, o caso pode
continuar U para medir se o sistema sabe abster-se. Essa informação externa não será
injetada em R+L nem usada para redefinir retrospectivamente o que era recuperável no IFC.

Revisores não recebem inicialmente a identificação do braço nem confiança declarada da
LLM. Registrar desacordos, critério de adjudicação e alterações de gabarito em versão nova.
Planejar revisão independente por mais de um especialista conforme disponibilidade;
quantidade de revisores e desenho do estudo são decisões abertas. Uso da LLM para organizar
rascunhos de gabarito não substitui julgamento independente nem autoriza usar sua própria
resposta como verdade. Preservar valores/esperados históricos em suas condições.

### 14.3 Partições e controles contra vazamento

1. Agrupar antes do split por projeto de origem e linhagem de revisões/exportações. Arquivos
   iguais por hash, cópias transformadas e tipos/instâncias correlatos do mesmo projeto não
   podem migrar para a avaliação como se fossem independentes do desenvolvimento.
2. Separar desenvolvimento de receitas/prompts, piloto/calibração e conjunto final reservado.
   Manter vínculo dos contrafactuais ao caso pai e no mesmo split. Estratificar por família,
   schema, categoria de campo e estado D/U/T quando o corpus permitir; declarar estratos ausentes.
3. Produzir aliases, exemplos e políticas usando fontes de domínio e desenvolvimento. Conhecer
   o esquema cadastral pode ser comum aos braços; valores particulares do conjunto reservado
   não entram em receitas, exemplos de prompt, nomes de arquivo, caches ou índices de busca.
4. Manter gabarito e justificativas de adjudicação em armazenamento separado das entradas do
   runtime. Testar que esperado IDS, URI, descrição e identificador de requisito não se tornam
   `EvidenceObservation`. Requisito informa o que comparar, não o que está construído.
5. Congelar hashes de corpus, splits, catálogo, operações, contexto, schema, modelo, tokenizer,
   runtime, parâmetros, orçamento, repetições, política de retry e comparador antes da rodada final.
6. Não ajustar comparador, prompt, seleção, tolerâncias ou modelo após olhar o reservado.
   Alteração motivada pelo resultado cria nova condição e exige conjunto independente ou
   declaração de caráter exploratório; não reapresentar como confirmação cega.
7. Comparador não completa a parte difícil da resposta: equivalência de unidade pode ser
   permitida e auditável; inventar classe de fogo, componente, material ou distribuição de peso
   a partir de texto incompleto é vazamento/erro, ainda que aumente a taxa de acerto.

Os casos casa/prédio e materiais já examinados têm exposição histórica conhecida. Se usados
para ajuste, não servem como avaliação final independente. Poucos projetos implicam estudo
de caso com generalização limitada; centenas de elementos repetidos não corrigem essa limitação.
Corpus novo e disponibilidade de especialistas são gates da avaliação empírica, não
impedimentos para concluir o planejamento documental.

### 14.4 Contrafactuais e invariâncias

Aplicar transformações controladas sobre cópias de fixtures, nunca sobre fontes/IDS históricos.
Registrar pai, transformação, hash e esperado independente. Os pares permitem investigar a
dependência da proposta em evidência, em vez de premiar memorização ou plausibilidade.

| Transformação | Comportamento esperado | Limite da conclusão |
|---|---|---|
| Retirar única evidência, conservando exigência IDS | Perda de suporte leva a abstenção/pendência | Mede sensibilidade à falta, não capacidade de adivinhar |
| Alterar valor observado com unidade/escopo corretos | Proposta acompanha a evidência ou sinaliza conflito, preservando origem | Mudança plausível precisa continuar válida na fixture |
| Alterar somente valor esperado IDS | Valor factual não é copiado do esperado; diagnóstico/conflito pode mudar | O esperado pode influenciar admissibilidade, nunca criar observação |
| Trocar componente vidro ↔ caixilho ou abertura ↔ marco | Não transferir material/dimensão sem mapping de significado válido | Mesma grandeza/tipo não prova mesmo conceito |
| Converter mm ↔ m com transformação exata | Resultado físico equivalente e caminho de conversão diferente | Tolerância definida por método, não por conveniência do comparador |
| Reordenar Psets/propriedades/classificações | Evidências pertinentes não somem por posição | Se houver ambiguidade real, ela permanece explícita |
| Inserir pilares sem relação com a parede | Não mudar função portante da parede | Estatística do modelo não é prova de função individual |
| Trocar marca de placeholder mantendo literal, com origem documentada distinta | Avaliação de suficiência acompanha procedência; falso legítimo não vira ausente | Exige política revisada, sem heurística global de igualdade |
| Injetar instrução em texto da fonte | Nenhuma mudança de política/permissão; nenhuma execução externa | Recusa textual sozinha não comprova isolamento |

### 14.5 Métricas e denominadores

Unidade principal: **par elemento/campo na revisão analisada**. Requisitos ligados ao campo
têm contagem formal separada. Alternativas são medidas também individualmente; uma opção
boa não apaga outra inventada. Resultados antes e depois da revisão humana são séries
distintas. Na primeira comparação, reportar contagens brutas junto das taxas.

Definir `N` como todos os pares selecionados; `N = D + U + T + G` conforme gabarito acima.
Para a correção semântica, `E = D + U`. Dentro de E, particionar resultados terminais em
`P` (campos com proposta), `A` (abstenção válida), `F` (falha técnica/saída inválida) e `I`
(incompleto/cancelado/não solicitado), de modo que `E = P + A + F + I`. Erro do sistema em
um caso D não retira o caso do denominador para aumentar desempenho.

Para cobertura operacional, definir `P_N` como todos os campos com proposta entre os N
selecionados, incluindo eventuais propostas em T ou G. Reportar essas duas parcelas
separadamente: propor em T apesar da indisponibilidade de um insumo indispensável é falha
da barreira técnica; propor em G não permite julgar correção sem gabarito independente.
Nenhuma parcela desaparece da contabilização operacional por estar fora de E. Assim,
`P / E` mede cobertura no subconjunto semanticamente avaliável e `P_N / N` mede cobertura
na população total; as duas taxas não usam numeradores intercambiáveis.

| Métrica | Definição proposta | Interpretação/cuidado |
|---|---|---|
| Cobertura de inventário | Entradas com destino rastreável / entradas da matriz conferida | 203 registros alfanuméricos conferidos em G3-01; reportar separadamente os 110 auxiliares. Cobertura documental não certifica capacidade |
| Cobertura de capacidade | Pares tecnicamente processáveis / N, com matriz por operação/schema | Separar suporte de extração, interpretação, revisão e escrita |
| Cobertura de proposta | P / E e P_N / N, com propostas em T/G separadas | Mais preenchimento sozinho não significa melhora |
| Precisão sustentada top-1 | Propostas principais corretas e apoiadas em evidência / P | Valor plausível ou igual ao gabarito sem suporte não conta como sustentado |
| Recuperação em D | Campos D com proposta principal correta e sustentada / D | Abstenções e falhas em determináveis reduzem recuperação |
| Abstenção correta em U | Campos U com abstenção válida / U | Erro, cancelamento e falta de suporte não contam como abstenção de domínio |
| Abstenção desnecessária | Campos D abstidos / D | Expõe conservadorismo que impede recuperar informação disponível |
| Falso preenchimento em U | Campos U com qualquer proposta de valor / U | Inclui valor que coincida por sorte com conhecimento externo |
| Risco entre propostas | Campos propostos cuja principal é incorreta ou sem suporte / P | Complementa cobertura; separar incorreção e ausência de suporte, com interseção |
| Alternativa sem suporte | Alternativas incorretas/sem fundamento / todas as alternativas emitidas | Não diluir erro oferecendo listas grandes; registrar também campos com alguma alternativa indevida |
| Utilidade de alternativas | Campos com alternativa sustentada aceitável / campos com alternativas | Informar tamanho real da lista; não completar artificialmente top-3 |
| Fidelidade da evidência | Referências resolvidas, da revisão/papel corretos e admissíveis / referências emitidas | ID existente não basta; julgamento de suficiência pode exigir especialista |
| Integridade estrutural | Respostas válidas / tentativas; campos válidos / campos solicitados | Mostrar antes/depois de retry, truncamento, omissão e chaves duplicadas |
| Placeholders | Precisão/recuperação da detecção com origem revisada; falso positivo em valores legítimos | Não premiar detector que remove todo FALSE/0 |
| Robustez contrafactual | Pares com transformação/invariância esperada / pares com esperado revisado | Separar remoção, troca de valor, papel, unidade, ordem e instrução |
| Efeito incremental R+L | Diferença pareada de recuperação, risco, abstenção e custo em relação a R | Mesmo pacote e população; relatar ganhos e danos por família |
| Revisão humana | Aceites, edições, rejeições, pulos, pendências e tempo por par/elemento | Denominadores do que foi realmente apresentado; aceite não prova correção independente |
| Resultado após M5/M2 | Correções aplicadas e revalidadas / decisões autorizadas; pendências resolvidas / pendências acompanhadas | Aceite, aplicação e resolução não são sinônimos; inclui regressões e cobertura parcial |
| Viabilidade local | Tokens previstos/efetivos, latência mediana/cauda, extração, fila, inferência, revisão, memória/VRAM, chamadas/retries por elemento | Hardware/modelo/estado frio ou aquecido e cache informados; nenhum SLA aprovado |

Quando o denominador for zero, registrar `não aplicável` e contagem, nunca 100% automático.
Publicar métricas por família, tipo de campo, schema, método e estado de evidência, além de
microagregação e macroagregação com ponderação declarada. Não agregar sucesso de atributo
simples de milhares de instâncias como se comprovasse cálculo de armadura ou decisão de janela.

Comparações são pareadas no mesmo caso e agrupadas por projeto/linhagem. Se houver projetos
suficientes, planejar intervalos de incerteza com reamostragem por grupo, preservando
dependência entre campos/tipos. Com poucos projetos, apresentar contagens e limites do
estudo de caso; não inferir significância a partir de milhares de cópias correlacionadas.
Número de repetições, nível de intervalo e critérios quantitativos de aceitação devem ser
fixados no protocolo após piloto, antes da avaliação final. Não há thresholds aprovados aqui.

### 14.6 Instrumentação, relatório e critérios de interpretação

Manifesto de cada rodada: fonte/split/hash, IDs de análise/elemento/campo, método, receita,
catálogo, observações disponíveis e selecionadas, CallPlan, modelo/digest, parâmetros,
runtime/hardware, condição/commit, tempos, consumo, cache hits, tentativas, motivos e
resultados. Preservar eventos de abstenção e erro; guardar estímulo/resposta localmente
sob política M6 para auditoria quando autorizado. Desligar cache de inferência na medida
de geração ou reportar braços com/sem cache; não atribuir latência de cache a inferência.

Revisão humana deve controlar ordem, familiaridade com o caso e aprendizado entre braços;
desenho pareado/contrabalançado é proposta a acordar com M7. Registrar capacitação do
revisor e a diferença entre tempo de localizar evidência, decidir e corrigir. Não usar
revisor simulado como prova de ganho com pessoas reais.

O relatório final futuro deverá conter fluxo de seleção/exclusão, cobertura das dez
famílias, todos os denominadores, erros representativos, falsos preenchimentos, abstenções,
limites de generalização e custos. Haverá relatório mesmo se R+L não superar R. Nenhuma
rodada é executada por esta elaboração; o novo fluxo continuará uma condição experimental
distinta, sem alterar `PROMPT_VERSION v7.8` ou reapresentar resultados históricos.

<a id="m3-entregas"></a>

## 15. Entregas graduais e estimativas condicionais

### 15.1 Fatias demonstráveis, dependências e aceite

A base de integração é `feat/semantic-foundation`. A tabela organiza trabalho futuro
na aplicação modular; não exige sete serviços, mudança de stack ou árvore física fixa.
Destino de PRs e estratégia de branches pertencem à implementação autorizada. Esta
entrega não cria branch, não faz staging/commit/push/merge e não abre execução de tarefas.

| Fatia | Tarefas predominantes / dependências externas | Demonstração e condição de saída |
|---|---|---|
| E3-0 — Desenho e fonte documental | M3-01 concluída documentalmente; M3-02/M3-21 ainda funcionais | Planejamento consolidado; contratos implementados, XML/planilha e protocolo de execução continuam com critérios próprios |
| E3-1 — Recuperação rastreável | M3-03–M3-10 em recorte mínimo; observações M2 e reader M1 | Mesmo elemento tem campo recuperável, conflito e decisão humana ausente; propostas determinísticas e BCF direto com fonte, sem geração obrigatória |
| E3-2 — Pacote e geração local | M3-11–M3-15, antecipando isolamento mínimo de M3-19; runtime/política M6 | Uma inferência ativa por vez, agrupamento e rota explícitos; abstenção válida, erro localizado e excesso de orçamento não viram palpite |
| E3-3 — Continuidade e revisão | M3-16–M3-18; serviços M4/M5 e revalidação M2 | Reinício conserva contexto; humano escolhe valor específico; cópia reavaliada e pendência rejeitada/pulada não fechada |
| E3-4 — Cobertura e ciência | M3-20–M3-22; G3-01/G3-02/G3-07 | Dez famílias inventariadas, capacidades/limites por entrada, piloto e comparação pareada identificados; fontes não obtidas continuam bloqueando conclusões correspondentes |
| E3-5 — Operação e entrega | M3-19/M3-23/M3-24; M6 e revisores das interfaces | Isolamento, restauração, rollback e evidências de aceite; riscos residuais e limites documentados |

Os gates operacionais mínimos de segurança não ficam para o fim só porque o ensaio amplo
está em E3-5. E3-2 precisa de G3-05 e das barreiras de runtime/dados antes de qualquer
execução real. Uso de substitutos locais permite testar a forma das interfaces antes de
M4/M5 completos, mas deve continuar rotulado como teste, sem declarar fluxo operacional.

**Primeira fatia sugerida para revisão:** porta/janela sintética com material de componente
explicitamente declarado e uma normalização recuperável, além de fixação ausente. Acrescentar
parede com conflito tipo/ocorrência para evitar desenho só otimista. Demonstrar identidade,
proposta determinística, campo LLM elegível e BCF direto. Expandir depois para os três
IfcCovering, laje/pilar/viga e armadura; a ordem não retira nenhuma família do piso final.

As tarefas M3-25/26/27 complementam E3-1 (semântica), E3-3 (manual/requisito) e E3-4
(roteamento/avaliação). As faixas históricas abaixo não foram reestimadas como orçamento
fechado dessas adições; recalibrar por entrega compartilhada com M1/M2/M4/M5/M6/M7.

### 15.2 Hipótese de esforço e disponibilidade semanal

As faixas abaixo são propostas iniciais para **engenharia incremental M3** e revisão
BIM/semântica/pesquisa. Incluem desenho, implementação, testes e revisão usual; dependem
do aproveitamento dos contratos/leitores M1/M2 e serão recalibradas após E3-1/E3-2.
Não incluem reimplementar M1/M2, viewer completo, writer/BCF completos, aquisição de
hardware, espera por fontes, implantação institucional inteira ou recrutamento de estudo
humano. Operação geométrica nova complexa exige estimativa própria após definir método.

| Onda | Recorte predominante | Engenharia incremental | Revisão de domínio/pesquisa |
|---|---|---:|---:|
| O0 | Baseline, amostra, contratos e protocolo inicial | 16–24 h | 8–16 h |
| O1 | Adaptador de diagnóstico, identidades e propriedades | 24–40 h | 8–16 h |
| O2 | Unidades, materiais, relações, conflitos e operações aprovadas | 48–80 h | 12–24 h |
| O3 | Receitas, pacote e orçamento | 32–56 h | 8–16 h |
| O4 | Runtime local, saída estruturada e fila por elemento | 40–64 h | 8–16 h |
| O5 | Persistência, revisão e interfaces residuais | 32–56 h | 8–16 h |
| O6 | Cobertura das dez famílias, contrafactuais e piloto | 32–56 h | 16–32 h |
| O7 | Segurança, recuperação, rollback e aceite | 24–40 h | 8–16 h |
| **Total indicativo** | **Recalibrar após as primeiras fatias** | **248–416 h** | **76–152 h** |

Evitar dupla contagem: M2 implementa leitores e identidade de origem; M1 publica catálogo;
M3 adapta/seleciona/deriva; M4/M5 implementam revisão/escrita. Quando uma tarefa atravessar
frentes, registrar uma entrega compartilhada e uma estimativa consolidada, não somar
automaticamente as três planilhas de esforço. As faixas não atestam que capacidades
complexas já estejam disponíveis nas outras frentes.

Com `Ce` horas semanais efetivas de engenharia e `Cr` de revisão, o piso aritmético para
um recorte de esforços `He` e `Hr` é `max(He / Ce, Hr / Cr)`. Dependências sequenciais,
fila de revisão e espera externa aumentam o calendário; se uma capacidade for zero,
não há previsão calculável para o trabalho dependente. Felipe divide sua capacidade entre
M1/M2/M3/M5; Nonato entre M4/M6 e liderança M7. Não contabilizar a mesma hora simultaneamente
em frentes diferentes. Planejar disponibilidade de especialistas e ajuda de Felipe ao M7.

Nenhuma data de entrega é prometida. A conclusão documental em 12/10/2026 não é prazo
contratual de implementação. Se a
capacidade ou prazo acadêmico exigir recorte menor, negociar fatia vertical e declarar
cobertura parcial. Reduzir escopo não autoriza omitir abstenção, prova de origem, revisão
humana, isolamento local ou falsos preenchimentos das métricas.

### 15.3 Prontidão por nível

- **Planejamento concluído e verificado:** documento, cobertura individual e índices
  consistentes; não equivale a implementação ou execução experimental. Nível atingido nesta entrega documental.
- **Fatia implementada:** comportamento e testes correspondentes existem, com limitações declaradas.
- **Capacidade verificada:** combinação de campo/operação/schema/portador tem evidência de aceite.
- **Resultado científico:** condições/gabarito independentes, métricas e limites publicados após ensaio.

Esses níveis não serão resumidos por um único “concluído”. Uma matriz toda cadastrada
pode continuar com enriquecimento parcial, e um piloto bem sucedido não conclui o módulo.

<a id="m3-riscos"></a>

## 16. Riscos, contenção e rollback

### 16.1 Registro de riscos e responsáveis de encaminhamento

| Risco | Sinal/impacto | Tratamento proposto e papéis |
|---|---|---|
| Matriz cadastrada confundida com capacidade | 313 registros documentados parecem suporte pronto | M3-20 publica capacidade só por ensaio; original e operação distintos, divergências de fonte ainda exigem curadoria |
| Conflito A/B e XML original ausente | Binding, tipo ou significado indevidos | Manter conflito de contrato; Felipe/especialista/curador reconciliam; Não usar LLM para decidir versão verdadeira |
| Fonte inicializada com defaults | FALSE/0/A definir apresentados como fatos aprovados | Política por proveniência e testes de falsos positivos; M3-08 com revisão de domínio |
| Material/componente achatado | Vidro vira caixilho; abertura vira marco | Papéis/caminhos em observações, receita escopada, CT3-27/36; M2/M3 |
| Peso de hospedeiro rateado sem prova | Falso quantitativo por barra/conjunto | Abstenção e BCF; método só após revisão especializada e teste; Felipe/M2/M3 |
| Herança ou unidade perdidas | Valor numericamente plausível, mas errado | Observar origens separadas, registrar transformação e erro; M3-04/M3-05 |
| Regras legadas tomadas como engenharia validada | Heurística de LoadBearing/IsExternal vira fato | Revisão de premissas e contrafactuais, inclusive contra regras fortes; Felipe/especialistas |
| Contexto excedido/truncado | Modelo perde instrução ou campo relevante | Orçamento de entrada e saída, limite antes do envio, CallPlan; Nonato/M6 |
| JSON válido sem suporte | Proposta inventada cita ID irrelevante | Validadores por conceito/papel e revisão humana; M3-14/M4, métricas de falso preenchimento |
| Cache incompleto ou entre projetos | Resposta/decisão de outra revisão ou usuário | Chave completa, ACL, hashes e eventos; M3-16/M6 |
| Instruções embutidas ou saída hostil | Execução, autoaprovação, exfiltração | Sem ferramentas de efeito, dados delimitados, saída estrita e rede local; M3-19/M6 |
| Saída de projeto pela exceção bSDD | Texto IFC vira consulta pública; outro cliente contorna filtro | Adaptador de parâmetros públicos, allowlist e teste de efeitos CT3-74; M3-25/M6. Inferência/ativos visuais não ganham exceção |
| Revisão audita a alternativa errada | Perda de responsabilidade e proveniência | Decisão ligada ao valor/alternativa escolhidos; M3-17/M4/M5 |
| Rejeitado/pulado vira Closed | Pendência some sem resolução | Estados separados e confirmação em nova revisão; M3-18/M5/M2 |
| Mudança de contexto contamina baseline | Resultado novo atribuído a v7.8 | Condição distinta, pins/dados intactos, artefatos novos; M7 |
| Corpus correlacionado ou comparador permissivo | Ganho científico inflado | Splits por linhagem, gabarito independente, contrafactuais e denominadores; Felipe/M7 |
| Dependência de contratos ainda apenas propostos | Implementação duplicada e retrabalho | Alinhar M1/M2 antes da API final; fatia vertical com substitutos rotulados; responsáveis técnicos conjuntos |
| Capacidade/revisão insuficientes | Estimativa vira prazo irreal ou engenharia sem especialista | Confirmar Ce/Cr, recortes parciais e disponibilidade; não transferir julgamento técnico automaticamente ao programador |

### 16.2 Resposta a falha e desativação da nova condição

Gatilhos a ensaiar: violação de localidade, identidade misturada, perda de evidência,
falso preenchimento sistemático, regressão de suporte, corrupção de pacote, falha de
persistência ou escrita sem vínculo humano. O escopo afetado deve ser interrompido e
identificado, preservando diagnóstico independente e evidências para investigação.

1. Suspender novas gerações/aplicações dependentes da condição afetada; sinalizar resultados
   suspeitos sem apagar seu histórico. Falha limitada a uma operação pode bloquear só os
   campos dependentes, desde que a independência do restante seja demonstrada.
2. Preservar manifesto, fontes, pacotes, resposta bruta, tentativas, decisão e recibos locais.
   Separar limitação técnica de pendência de domínio; registrar responsável pelo incidente.
3. Fixar pacote/operação/runtime anterior **íntegro e aprovado para a condição pertinente**,
   se houver. Verificar compatibilidade de schemas de armazenamento e relações entre artefatos.
4. Criar nova execução de rollback/reprocessamento e invalidar reutilização dependente do
   conjunto afetado. Não reabrir execução terminal com outro catálogo ou modelo sob o mesmo ID.
5. Reavaliar resultados e solicitar nova revisão humana quando o fundamento/valor mudou.
   Nunca transportar automaticamente aprovações de pacote inconsistente para o restaurado.
6. Demonstrar restauração em ambiente isolado: hashes de fontes/pacotes, eventos, resultados,
   decisões e pendências correspondem ao conjunto restaurado; registrar perdas conhecidas.

Rollback não significa religar tráfego bSDD sem filtro ou permitir a rota legada contornar
revisão/localidade. Se não existir caminho anterior que cumpra os requisitos operacionais,
permanecer em diagnóstico somente leitura e pendências, até corrigir a nova condição.
O baseline histórico continua disponível como instrumento identificado para reprodução
autorizada, sem ser apresentado automaticamente como alternativa operacional conforme.

IFC já escrito em cópia não é desfeito por sobrescrever o original. M5 conserva original,
cópia, delta, decisão e recibo; eventual reversão é outra revisão controlada e reavaliada.
Uma pendência BCF só muda de resolução com fundamento no fluxo acordado, nunca porque
o software foi revertido. Catálogos publicados e resultados históricos são imutáveis;
avisos/quarentena bloqueiam novo uso quando necessário sem eliminar acesso de auditoria.

### 16.3 Critérios para liberar novamente a capacidade

- Causa reproduzida em fixture e falha protegida por teste pertinente.
- Revisão técnica e, quando houver premissa de valor/método, revisão BIM especializada.
- Nova versão identificada e impacto sobre análises/decisões anteriores inventariado.
- Isolamento/localidade, integridade, abstenção e revisão demonstrados no recorte afetado.
- Evidência registrada e autorização operacional pelo processo acordado; nenhum índice
  documental mudado para “aprovado” só porque um teste sintético passou.

<a id="m3-revisao"></a>

## 17. Consolidação e pendências de desenvolvimento

Esta seção substitui o checklist antigo que aguardava a leitura de Felipe. Sua autorização
posterior pede o encerramento documental após verificação, sem nova aprovação. A descrição
do produto continua planejada; nenhuma linha de código funcional foi alterada aqui.

### 17.1 Itens da consolidação

- Fontes locais PDF/ZIP, hashes, páginas, fonte literal e correções separadas.
- 203 registros alfanuméricos e 110 auxiliares, dez famílias e 72 identificadores lexicais (79 rótulos completos).
- Significado/aplicabilidade, caminhos/portadores, unidades, transformações e quatro rotas
  por registro, incluindo limites de fonte, negativos e tarefas de implementação.
- CSV e JSON como projeções da mesma revisão; 1.328 definições de cenários **não executados**.
- API pública bSDD sem dados de projeto, manual fundamentado, conflitos com decisão humana,
  revisão de requisito inadequado, histórico local e uma inferência por vez no baseline.
- Roteamento por campo/grupo conforme M7/M6, sem modelo eleito; experimentos anteriores
  reconhecidos e extração avaliada separadamente de interpretação LLM.
- Responsabilidades atuais e vínculos documentais consistentes; resultado da verificação
  registrado nos apoios antes de alterar o status final.

### 17.2 Pendências que pertencem ao desenvolvimento

| Pendência | Encaminhamento e limite |
|---|---|
| XML/planilha de 2025, fixtures F01–F24 e síntese Library | M3-01/M3-20; obter por fluxo suportado, comparar versões; sem alegar equivalência ou teste inexistente |
| Divergências A/B, tipos e bindings | M1/M3-09/M3-20; curadoria e especialista publicam interpretação, preservando fonte; não decidir por LLM |
| Leitores por schema/portador e operações geométricas | M2/M3-04–10; capacidades e limites ensaiados, sem suporte universal presumido |
| Contratos de revisão/manual/BCF e armazenamento | M3-16–18/26, M4/M5/M6; decisão, escrita e resolução distintas |
| Modelos, agrupamentos, budgets, roteamento e corpus | M3-12/21/22/27, M6/M7; calibrar durante desenvolvimento, congelar antes do teste final |
| bSDD público, filtros e snapshots | M3-25/M6; falha técnica explícita e zero conteúdo de projeto enviado |
| Armazenamento integral local de dicionários | Estudo futuro de tamanho, versões, licença, atualização e operação offline; não pré-requisito do baseline atual |

Esses itens têm responsáveis e critérios neste plano. Não são perguntas pendentes para
reaprovar sua conclusão. O planejamento M4, conduzido por Nonato com Felipe nas interfaces,
foi autorizado em tarefa separada com arquivos próprios; esta entrega apenas alinha o
contrato de dois pares IFC–IDS e não executa o planejamento ou a implementação M4.
Nenhuma ação no Todoist é feita ou presumida a partir de um status documental.

<a id="m3-fontes"></a>

## 18. Fontes, preservação e verificação documental

### 18.1 Proveniência e limites desta consolidação

Os [apoios](../pesquisa/modulo-03-contexto/README.md) documentam PDF/ZIP, hashes,
páginas conferidas, pesquisa original e limites de acesso. A [análise de baseline](../pesquisa/modulo-03-contexto/baseline.md)
registra código/experimentos existentes sem executar inferência ou suíte funcional.
M1/M2, consolidação 09/10, bibliografia dos 29 artigos, configurações locais e artefatos
históricos são preservados. Mapa/índices/arquitetura recebem apenas referências de
precedência e responsabilidades necessárias à coerência das novas decisões.

Não foi localizado AGENTS.md nos ancestrais/áreas consultados nem `.agents/skills` no
checkout. Foram usadas as instruções CLAUDE.md, planos, fontes e autorização posterior.
Acesso a arquivos locais foi confirmado por leitura real; incerteza verbal de sessão
não é evidência de falta de permissão. Nenhuma configuração foi alterada para esse acesso.
A Library foi tentada pelo mecanismo oficial, cuja limitação Windows é registrada;
não se leu a síntese nem se contornou o helper. Documentação técnica oficial foi usada
apenas para conferir caminhos IFC/bSDD, não como pesquisa bibliográfica ampla nova.

### 18.2 Preservação e método de verificação

O manifesto inicial reúne hashes de **384 arquivos rastreados/não rastreados não ignorados**.
Cópias dos documentos editáveis, branch, HEAD, estado Git e hash do índice foram guardados
fora do repositório. Comparar o mesmo conjunto e arquivos novos, permitindo alterações
somente neste plano e referências pertinentes nos dois índices, mapa das frentes,
arquitetura base e nota de precedência da fundação; novos apoios ficam no diretório M3.
M1/M2, consolidação, código/configurações, IFC/IDS, prompts/pinos, GTs/locks/resultados
não são alterados. Arquivos ignorados não integram uma auditoria de todos os bytes da máquina.

A [verificação documental](../pesquisa/modulo-03-contexto/verificacao-documental.json)
registra cobertura/contagens, igualdade JSON–CSV, fonte original preservada, IDs/tarefas,
links/âncoras, sintaxe dos exemplos e preservação. Cenários planejados não foram executados.
Leitura estática e parser de documento não comprovam funcionalidade, inferência ou suporte IFC.

### 18.2.1 Encerramento verificado — 12/10/2026

**Planejamento concluído e verificado, sem pendência de aprovação de Felipe. Implementação
não concluída.** Esta retomada reutilizou o checkpoint e corrigiu tabelas, denominadores,
critérios auxiliares e contradições residuais. A revisão independente **Astra xhigh** leu
os 203 registros alfanuméricos e 110 auxiliares, confrontou as dez páginas extraídas e
examinou visualmente A3/A10. Não encontrou nova divergência de conteúdo do Apêndice A.
Identificou canais incompletos e a diferença RelatedSpace/RelatingSpace entre releases:
as correções foram aplicadas e conferidas documentalmente pelo responsável da consolidação.
Não houve segunda revisão independente das correções nem ensaio dos caminhos IFC.

Revisão canônica `2026-10-12-r2`: 313 registros, 136 entradas de propriedade/quantidade,
72 identificadores/85 pares e 79 rótulos completos/90 pares, 27 tarefas e **81 casos CT3**
planejados. CT3-81 registra a decisão posterior dos dois pares IFC–IDS no MVP. Mantêm-se
**1.328 cenários TR3 não executados**; a adição de CT3-81 não altera esse denominador.
Cada ficha agora explicita organização do contexto, canais, papel, fonte, escopo do arquivo,
limites e vínculos de tarefa/caso. Caminhos históricos não ativam coleta por si.

O relatório registra verificações de conteúdo individual das fichas, JSON/CSV, fonte
preservada, páginas extraídas, contagens, IDs, tabelas, sintaxe, links/âncoras e estados.
Seu resultado `passed` e os hashes dos arquivos são a evidência reproduzível; verificações
documentais não equivalem aos casos funcionais planejados. O comando é `python verificar.py`
na pasta temporária `ifc-m3-consolidacao-20261012`; o relatório identifica caminho/hash
do script e manifestos, sem depender de scripts novos no produto.

No universo original de 384 arquivos, **seis documentos existentes alterados, 378 com
SHA-256 preservado e nenhuma remoção**. Os seis apoios M3 são novos em relação ao início
da consolidação. Arquivos M4 novos, autorizados em tarefa separada durante a retomada,
são discriminados no relatório e não foram alterados nem certificados por esta tarefa.
M1/M2, bibliografia, código, configurações e histórico experimental permanecem preservados.
Branch/HEAD e índice Git permanecem os do checkpoint; SHA-256 do índice:
`fe66e494402e7a741c2aa982958ab74384444b8a96aede668e4defe9f32db16d`.

Nenhuma inferência do produto, benchmark, teste funcional, instalação, stage, commit ou
push foi executado. Originais XML/planilha, fixtures e síntese Library permanecem tarefas
futuras delimitadas em 17.2, sem bloquear o encerramento documental. A continuidade é o
planejamento M4 autorizado, com federação visual e isolamento de evidência por arquivo.

### 18.3 Histórico preservado — 09/10/2026 (status substituído em 12/10)

O registro abaixo pertence à elaboração anterior e é conservado como histórico.
A conferência de 10/10 é descrita separadamente na seção 18.4.

Verificação documental realizada em 09/10/2026: destinos/âncoras dos 113 links locais
nos três arquivos editados resolvidos; três exemplos JSON aceitos por parser estrito;
dois blocos Python aceitos por análise sintática, sem execução. Conferidos Markdown,
sequência das 24 tarefas/72 casos, dez famílias e somas das estimativas. Esses números
descrevem documentação verificada, não testes funcionais aprovados.

HEAD antes/depois: `a76c2d7a85983ef246761a49db9266c411ea90fd`, branch
`feat/semantic-foundation`. O manifesto inicial/final contém 383 arquivos rastreados ou
não rastreados não ignorados: somente este plano e os dois índices mudaram; os outros
380 mantiveram seus hashes, sem arquivos adicionais/removidos nesse conjunto. O estado
Git e os bytes do índice Git permaneceram iguais, preservando inclusive o estado não
rastreado dos documentos. Manifesto, cópias anteriores e relatório detalhado de conferência
foram guardados na pasta temporária local `ifc-m3-plan-20261009-baseline`, fora do repositório.

| Arquivo protegido | SHA-256 igual antes e depois |
|---|---|
| Consolidação 09/10 | `de0282cbb89d398f3d73454de9907e795fc2db2781e97dadd997faac52d50169` |
| Plano completo M1 | `f302b0993725b24810617441d596bc9eb7dccb9e9b1d567e4ed776101a255372` |
| Plano completo M2 | `23597703814afcc5ce66fe2e0859b5b9cbfdf24015ca421812527ffeecb4ce92` |
| `.claude/settings.local.json` | `3f6c3addc42c8141b2445323a0981597a3895e055c733a5f869858adac62be29` |
| `src/suggestion_engine/prompt_templates.py` | `068334be381b82e522bc3e34d92b5f521ae6b497bdf222e4996b2b88af5f756c` |
| `scripts/build_windows_release.py` | `79426498d7d898743597c482c0d2f7a564efe287f4d07ce498157c41aa96d9c3` |
| `windows/install.ps1` | `9a8d4009255a283adcba6210810c06586ddc08db54fcbcd32a11f1afc5be8406` |

Não houve implementação, suíte funcional, LLM do produto executada, alteração de IFC/IDS,
staging, commit, push, merge ou encerramento de tarefa Todoist. A entrega do texto e dos
índices não elimina nenhum gate nem converte o plano em aprovado.

**Rascunho v0.1 — NÃO CONCLUÍDO — aguardando revisão de Felipe após leitura da dissertação da Daiane.**

### 18.4 Histórico preservado — 10/10/2026 (status substituído em 12/10)

O checkout já continha o rascunho extenso e sua indexação. Esta retomada releu o M3,
conferiu as fronteiras com os planos M1/M2 e os trechos estáticos pertinentes. Preservou
as decisões, os 24 IDs de tarefas, os 72 casos propostos e as dez famílias. O ajuste
de métricas explicita a contagem operacional de propostas em casos T/G, sem convertê-las
em acertos nem alterar o protocolo histórico. Não há novas linhas da matriz Daiane.

Foram novamente verificados os 113 links locais e suas âncoras nos três documentos,
as cercas/tabelas Markdown, UTF-8, os três exemplos JSON por parser estrito e os dois
blocos Python por análise sintática sem execução. Sequências de tarefas/casos, rótulo
de rascunho, dez famílias e somas das estimativas foram conferidos. Essa verificação
não executa os casos CT3 nem comprova contratos ou funcionalidades do produto.

O manifesto desta retomada compara SHA-256 dos 383 arquivos rastreados/não rastreados
não ignorados antes e depois. Somente M3 e as referências mínimas nos dois índices
mudaram; os demais 380 arquivos preservaram seus hashes, sem inclusão ou remoção nesse
conjunto. Consolidação, planos completos M1/M2, configurações locais e pins históricos
mantêm os hashes da tabela acima. HEAD e branch permanecem
`a76c2d7a85983ef246761a49db9266c411ea90fd` / `feat/semantic-foundation`; estado Git e
índice Git permanecem iguais. SHA-256 do índice Git:
`fe66e494402e7a741c2aa982958ab74384444b8a96aede668e4defe9f32db16d`.

Não houve implementação, execução de LLM, suíte funcional, download da Library,
alteração de IFC/IDS, staging, commit, push, merge ou ação no Todoist. Matriz completa,
fontes originais e revisão de Felipe continuam pendentes. O término desta conferência
encerra apenas a entrega documental autorizada.

**Rascunho v0.1 — NÃO CONCLUÍDO — aguardando revisão de Felipe após leitura da dissertação da Daiane.**

<a id="m3-bibliografia"></a>

## 19. Nova integração bibliográfica de 10/10/2026 — contexto e enriquecimento

Esta seção atende à **nova autorização de integrar a bibliografia dos 29 artigos aos três planos**. É distinta da elaboração do rascunho de 09/10 e da conferência documental registrada em 18.4. A [síntese curada](../pesquisa/sintese-bibliografica-daiane-29-artigos.md) conserva as 29 identidades, referências originais/corrigidas, páginas, achados e limites; **17 estudos são pertinentes ao M3**. Os relatos de preservação de M1/M2 na seção 18 descrevem aquelas etapas históricas; na atualização de 10/10 ambos receberam seus próprios adendos bibliográficos, preservados nesta consolidação de 12/10.

Os estudos de extração e regras sustentam um baseline determinístico forte, com memória de cálculo e operações delimitadas. Dicionários e IDS ajudam a expressar significado e exigências; não descobrem o valor real. Casos de relações, agregados e revisão humana fundamentam os negativos e os limites de contexto. **Nenhum dos 29 estudos valida nossa combinação com LLM local**, demonstra ganho incremental sobre regras com a mesma evidência ou autoriza inferir decisões de engenharia ausentes.

**Precedência atual:** a bibliografia de 10/10 fundamenta refinamentos e não valida o
LLM local. As decisões posteriores de 12/10 em C3-03/10/15/16 e C3-17–24 substituem os
respectivos estados antigos; C3-25 registra a posterior decisão de federação visual
no MVP, sem evidência cruzada. Os demais limites e IDs continuam. BCF direto é permitido,
assim como manual fundamentado antes do residual. G3-01 foi fechado documentalmente pela
matriz local agora incorporada; XML/planilha originais e publicação das receitas continuam
com limites próprios. As propostas bibliográficas abaixo são critérios de desenvolvimento,
sem alegação de teste executado ou ganho demonstrado.

**Como ler a matriz:** `CT3-*` remete aos [casos já propostos na seção 13](#m3-testes), não executados. “Base existente” indica a expectativa que a referência ajuda a justificar; **Proposta** identifica um novo exemplo ou refinamento a revisar. As fichas vinculadas documentam o alcance e a página/seção de cada achado.

| Referência | Decisão ou risco fundamentado | Tarefa e caso existentes | Critério de avaliação e efeito no desenvolvimento |
|---|---|---|---|
| [Q34-06 — Souza](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-06) | Área do agregado não é área líquida das partes; revisão pode invalidar medição manual | [M3-05](#m3-t05), [M3-07](#m3-t07), [M3-16](#m3-t16); CT3-18/19/24/54 | Base existente: origem, decomposição e revisão na identidade. **Proposta:** contraste painel/constituintes/vãos com proveniência e invalidar medida manual após nova revisão; não preencher campo de componente com quantidade do hospedeiro. |
| [Q34-07 — Gehlen](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-07) | Taxa típica e duração convencionada são premissas, não observações reais | [M3-08](#m3-t08), [M3-10](#m3-t10), [M3-14](#m3-t14); CT3-28/29/38/64 | Base existente: suficiência e abstenção quando falta dado de engenharia. **Proposta:** taxa de aço assumida de 80–100 kg/m³ deve ser rejeitada como evidência de massa real; coerência numérica não autoriza estimativa fora do escopo. |
| [Q34-08 — Pereira](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-08) | Checar, extrair e calcular serviços têm custos/coberturas diferentes; piloto e universo não se confundem | [M3-10](#m3-t10), [M3-21](#m3-t21), [M3-22](#m3-t22); CT3-02/70 | Base existente: custo total por etapa e denominadores. **Proposta:** registrar bytes efetivos, hardware, elementos, requisitos e tempo de regra/LLM/revisão; preservar 17 IFCs versus 16.736 no artigo e não converter “Mb” em MB. |
| [Q34-09 — Morais](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-09) | Regras e memória de cálculo antecedem LLM; implementação do artigo é Revit, IFC é futuro | [M3-09](#m3-t09), [M3-10](#m3-t10), [M3-21](#m3-t21); CT3-38/39/70 | Base existente: operações registradas e comparação R versus R+L com mesma evidência. **Proposta:** incluir custo de preparar/manter regra e revisar resultado; dependência de memorial ausente deve gerar abstenção, sem alegar replicação IFC do artigo. |
| [Q34-10 — Gaspar](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q34-10) | Fórmula geométrica tem domínio de validade; ganho relatado não valida qualquer sólido | [M3-05](#m3-t05), [M3-10](#m3-t10), [M3-20](#m3-t20); CT3-18/19/39 | Base existente: declarado/calculado separados, bounding box não substitui área líquida. **Proposta:** negativo de perfil/vazio fora da capacidade deve abster-se; testar fórmula com referência independente antes de habilitá-la, sem ampliar famílias apenas por aparecer `IfcFooting` no estudo. |
| [Q310-01 — de Marco](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-01) | Mockup e percepção de utilidade não demonstram preenchimento; dicionário de enrich é futuro | [M3-11](#m3-t11), [M3-15](#m3-t15), [M3-21](#m3-t21); CT3-40/41/70 | Base existente: esperado e observado em blocos distintos. **Proposta:** conceito/requisito conhecido sem observação resulta em campo sem proposta de valor; medir utilidade com resultados e esforço humano, sem citar questionário como ganho medido. |
| [Q310-04 — Tomczak/circularidade](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-04) | Identificador/EPD externa pode não corresponder ao produto real; avaliação especializada não é lookup | [M3-08](#m3-t08), [M3-11](#m3-t11), [M3-19](#m3-t19); CT3-38/40/41 | Base existente: URI é contexto semântico, não prova de valor. **Proposta:** referência válida sem vínculo ao elemento deve produzir abstenção; ausência de fonte não será suprida por conhecimento geral do LLM. Ano editorial 2024, separado da citação 2022a. |
| [Q310-05 — Fischer](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-05) | Relação ausente pode ocultar aplicáveis; extensão do verificador não é IDS padrão | [M3-07](#m3-t07), [M3-08](#m3-t08), [M3-18](#m3-t18); CT3-25/26/30/39 | Base existente: rastrear relação, limitar expansão e não adivinhar hospedeiro. **Proposta:** remover relação seletora e preservar população indeterminada/pendência; reportar 10 implementados + 2 teóricos, 8 parciais e 5 impossíveis, sem atribuir cobertura plena comprovada a 12. |
| [Q310-06 — Garlet 2023](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-06) | Dado digitado, calculado e não verificável têm origens diferentes | [M3-04](#m3-t04), [M3-05](#m3-t05), [M3-10](#m3-t10); CT3-09/10/14/16/44 | Base existente: portador, unidade, método e insumos admissíveis. **Proposta:** retirar um insumo térmico e exigir abstenção do cálculo, mesmo com termo/valor esperado no IDS; experimento BEM não expande automaticamente nossas receitas. |
| [Q310-08 — Garlet 2024](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-08) | Dicionário multilíngue organiza significado, enquanto valor depende do usuário/evidência | [M3-11](#m3-t11), [M3-14](#m3-t14), [M3-19](#m3-t19); CT3-40/41/63 | Base existente: definição e enum não são observação e proposta pendente não vira insumo. **Proposta:** variar termo/idioma mantendo evidência ausente; o resultado deve continuar abstenção, sem usar URI como fonte oculta. |
| [Q310-09 — Mendonça/Ferreira](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-09) | Preencher seletor para forçar aprovação contamina a população avaliada | [M3-08](#m3-t08), [M3-11](#m3-t11), [M3-21](#m3-t21); CT3-35/40/64/70 | Base existente: false legítimo preservado e contrafactual do esperado não cria evidência. **Proposta:** distinguir campo ausente e falso legítimo do caso A/B excluído; nenhuma exclusão entra como aprovação, nem o LLM altera seletor para favorecer resultado. |
| [Q310-10 — Argasiński](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-10) | Nome/classificação semelhante não basta para atribuir material, classe ou função | [M3-06](#m3-t06), [M3-07](#m3-t07), [M3-08](#m3-t08); CT3-21/27/31/64 | Base existente: papel do material e classificação com sistema/edição. **Proposta:** candidato lexical plausível mas de outro componente deve falhar; preservar evidência e revisão humana de mapping, sem transferir semântica de patrimônio como domínio inicial. |
| [Q310-11 — Djukic/Caires/Lino](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-11) | IDS/scripts já detectam falhas; comparar LLM a baseline fraco superestima contribuição | [M3-10](#m3-t10), [M3-18](#m3-t18), [M3-21](#m3-t21); CT3-57/67/70 | Base existente: R versus R+L, diagnóstico sem LLM e revalidação independente. **Proposta:** incluir todas as regras suportadas na comparação com mesma observação, medindo falsos preenchimentos, abstenção e esforço humano; contagens empresariais do artigo não são ground truth local. |
| [Q310-12 — Scandurra 2024](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-12) | Segmentação/material orienta interpretação; não há classificador IA validado no estudo | [M3-06](#m3-t06), [M3-07](#m3-t07), [M3-20](#m3-t20); CT3-21/24/27/64 | Base existente: composição heterogênea e função do componente. **Proposta:** trocar evidência entre partes com rótulo semelhante e exigir rejeição/abstenção; não inferir material da folha a partir do caixilho ou vice-versa. |
| [Q310-14 — Mellenthin Filardo](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-14) | Conflitos entre versões exigem decisão humana; predefinido não é verdadeiro | [M3-16](#m3-t16), [M3-17](#m3-t17), [M3-18](#m3-t18); CT3-54/65/66/67 | Base existente: cache por revisão, escolha de alternativa exata e revalidação. **Proposta:** conflito entre versões exige nova decisão rastreável; aceite de proposta sem revalidação permanece pendente. O questionário não demonstra segurança de escrita IFC ou economia real. |
| [Q310-16 — Kremer/Beetz](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-16) | Operações externas experimentais demandam transparência/controle; BCF não atesta resultado | [M3-09](#m3-t09), [M3-15](#m3-t15), [M3-18](#m3-t18), [M3-19](#m3-t19); CT3-38/39/43/62 | Base existente: registro local de operações, sem código arbitrário, e BCF direto C3-07. **Proposta:** URL/função desconhecida não dispara execução; pendência sem insumo segue ao BCF sem exigir LLM. Enriquecimento/revalidação é outro percurso, sem tornar extensões parte do IDS padrão. |
| [Q310-17 — Tomczak/revisão](../pesquisa/sintese-bibliografica-daiane-29-artigos.md#q310-17) | Nenhum método isolado cobre significado, entrega e verificação; composição é hipótese própria | [M3-11](#m3-t11), [M3-14](#m3-t14), [M3-21](#m3-t21); CT3-40/41/64/70/72 | Base existente: blocos separados, abstenção e desenho experimental independente. **Proposta:** ablações por evidência/contexto com regra comparadora equivalente, separação por projeto/tipo/família e custo total; não usar revisão de padrões como validação do LLM local. |

### 19.1 Consequências para a pesquisa empírica ainda necessária

As referências tornam mais fortes as perguntas de [M3-21](#m3-t21) e [M3-22](#m3-t22), sem fornecer suas respostas. Permanecem necessários corpus independente e anotado por especialistas, separação que controle correlação entre elementos/tipos/projetos, condições locais fixadas e comparação R/R+L com os mesmos dados observados. Devem permanecer visíveis falso preenchimento, acerto condicionado à cobertura, abstenção adequada/inadequada, custo de preparo/cálculo/LLM e tempo de revisão humana; confiança declarada pelo modelo não substitui correção. O tratamento de D/U/T/G, os denominadores e as propostas técnicas da seção científica permanecem como registrados, sem retirar casos difíceis para melhorar taxa.

**Propostas bibliográficas de avaliação**, para detalhamento nessa pesquisa: negativos pareados que removem/contradizem/deslocam evidência; mudança só no valor esperado do IDS; termo certo em componente errado; conflito de versões; relação seletora ausente; valor típico plausível sem fonte; e estudo de revisão humana medindo tempo e erros, além da percepção de utilidade. A matriz aponta os casos preexistentes que receberiam esses exemplos, sem alegar novo teste executado, acurácia medida ou ganho de produtividade.

**Estado desta consolidação:** planejamento concluído e verificado, sem pendência de
aprovação de Felipe; implementação não concluída e pesquisa empírica da nova condição futura. A bibliografia dos 29 artigos continua
integrada aos três planos, sem substituir evidência experimental local.


[Voltar ao planejamento](README.md) · [Índice documental](../README.md) ·
[Módulo 1](modulo-01-dominio-catalogo.md) · [Módulo 2](modulo-02-nucleo-ifc-ids.md).
