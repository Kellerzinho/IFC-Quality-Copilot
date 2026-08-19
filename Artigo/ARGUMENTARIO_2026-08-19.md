# Argumentário do artigo — fundamentações e evidências (2026-08-19)

Documento de trabalho para a reescrita do artigo e para a conversa de
orientação (modelo, formatação e veículo são decisões do orientador; este
documento concentra o **mérito**: tese, lacuna, contribuições, resultados como
argumentos, objeções prováveis e respostas, e o que não afirmar). Cada claim
aponta o documento datado que o sustenta — os números não estão soltos.

Estado experimental em 19/08/2026: **cinco estudos completos e analisados**
(matriz v6, par unificado v7.7 nas RTX 4070+4060, escala-4070, ablação-bSDD,
replicação RTX 5050), dois IFCs com ground truth integral congelado, release
Windows reprodutível de um clique, e um resultado oficial declarado (par
v7.7). Nenhum artefato de escrita reflete isso ainda: o LaTeX do artigo IME e
o resumo ERA BIM são de 22/05, anteriores a todos os resultados.

**Alvo e calendário (atualizado 19/08 com o segundo cérebro):** o resumo do
ERA BIM foi **negado** (parecer de 01/08 — rejeição *por maturidade de
evidência, não por mérito*: os dois pareceres validam o desenho e pedem
resultados reais e validação com usuário — e **antecedem todos os cinco
estudos**). Decisão vigente (01/08, a confirmar com o orientador): **seguir
só no PIBIT**, sem congresso por ora; a janela real de submissão reabre em
**nov/2026–fev/2027** (alvo principal **ISARC 2027**, hedge de revista
**ITcon**, nacional **SBTIC 2027** — Roadmap no vault). Este argumentário
serve ao **relatório PIBIT agora** e vira a espinha do paper de
dez/2026–jan/2027 depois.

---

## 1. Tese e enquadramento

**Tese em uma frase:** um fluxo com supervisão humana, governado por padrões
openBIM (IDS como requisito computável, bSDD como âncora terminológica, BCF
como saída interoperável), permite usar LLMs **locais** para enriquecimento
semântico de modelos IFC de forma **medível, auditável e reprodutível** — e a
medição mostra onde o grounding paga (evidência do arquivo), onde não paga
(catálogo sem conteúdo normativo) e por que o humano permanece no circuito
(erro silencioso e instabilidade entre ambientes).

**Versão para abstract:** o trabalho investiga se LLMs locais (4–14B,
quantizados), operando sob grounding openBIM e revisão humana, produzem
sugestões de enriquecimento de IFC com qualidade suficiente para uso
assistido; um protocolo reprodutível (2 IFCs, 4.983 itens em 303 classes de
equivalência, 10+10 modelos, 3 GPUs) mede acurácia top-1/top-3 por item e por
classe, estabilidade entre ambientes, custo computacional e o efeito causal de
cada camada de grounding.

**O que o trabalho É:** avaliação quantitativa + framework de governança +
protocolo reprodutível. **O que NÃO é:** automação integral (o LLM só sugere);
prova de generalização entre tipologias (2 IFCs residenciais); comparação com
modelos de nuvem (escopo é local-first por soberania de dados).

---

## 2. Lacuna e posicionamento na literatura

*(Fontes: `RELATORIO_DEEP_RESEARCH.md` [RDR, maio], `DOSSIE_TECNICO…` [DTC,
04/08], `refs.bib` — localizações por linha; mineração de 19/08.)*

**A lacuna, na formulação mais forte já redigida** (RDR L11): a contribuição
não é "provar que LLM resolve BIM", é demonstrar **arquitetura controlada,
auditável e reprodutível** para enriquecimento semântico em openBIM — a
literatura de ACC, semantic enrichment e BIM+LLM explora rule checking,
ontologias e agentes, mas há pouca evidência sobre **pipelines end-to-end que
unam IFC + IDS + bSDD + LLM local + revisão humana + pós-validação +
auditoria**. A frase citável (RDR L366): *"o espaço entre 'gerar resposta' e
'alterar IFC com segurança' permanece relativamente menos consolidado — é
justamente nesse espaço que se insere o IFC Quality Copilot."* Complementos:
readiness semântica sem protocolo operacional (RDR L131, conecta Du 2024);
bSDD como mecanismo de restrição terminológica é literatura rarefeita (RDR
L139) — exatamente onde R5–R7 entregam dado novo.

**Mapa de vizinhanças** (o que cada um faz / não faz; chave do refs.bib):

- **LLM+BIM próximos:** Fuchs & Borrmann 2025 — LM sobre representações IFC;
  não fecha o ciclo até escrita segura (`Fuchs2025SemanticIFCLM`; entrada
  @misc **sem venue — completar EG-ICE**). Forth & Borrmann 2024 — BIM→BEPS
  com fine-tuning; domínio restrito, sem revisão humana nem escrita
  controlada (`Forth2024BIMBEPSLLM`). Hellin et al. 2025 — consulta agentic,
  só leitura (`Hellin2025BIMQA`). Zheng & Fischer (BIMS-GPT) — recuperação
  por prompts, só consulta (**falta no bib**). Chen et al. 2024 e Madireddy
  et al. 2025 — compliance com LLM: verificam, não corrigem
  (`Chen2024LLMOntologyCompliance`, `Madireddy2025LLMCodeCompliance`).
  Iversen et al. — LLM p/ ACC (**falta no bib**, completar dados).
- **Semantic enrichment:** Bloch 2022 — revisão; sem a ponte
  enriquecimento↔controle de qualidade operacional (RDR L143)
  (`Bloch2022SemanticEnrichmentReview`). Belsky et al. 2016 — enriquecimento
  por regras, pré-LLM (`Belsky2016SemanticEnrichment`).
- **ACC/rule checking (fundação):** Eastman et al. 2009 — as 4 etapas, param
  no reporte (`Eastman2009RuleChecking`); Solihin & Eastman 2015 — taxonomia
  de regras (`Solihin2015RuleClassification`); Amor & Dimyadi 2021 — a
  "promessa" com gargalos abertos (`Amor2021PromiseACC`); Doukari et al. 2022
  (`Doukari2022ObjectCentredACC`).
- **Motivação (qualidade/interoperabilidade IFC):** Noardo et al. 2021 —
  incompletude em modelos da prática (`Noardo2021InspectionIFC`); Lai & Deng
  2018, Sibenik & Kovacic 2020, Lee et al. 2018 — perdas semânticas nas
  trocas; Du et al. 2024 — readiness BIM/IA sem operacionalização
  (`Du2024DataReadinessAI`).
- **IDS:** Tomczak et al. 2022 — nenhum método de requisito cobre tudo
  (`Tomczak2022RequirementsReview`); **de Marco et al. 2024 — enriquecimento
  dirigido por IDS, determinístico, sem LLM — o vizinho mais próximo do lado
  openBIM** (`deMarco2024IDSenrichment`); Fischer et al. 2024 — limites do
  IDS padrão (`Fischer2024ExtendIDS`).
- **IA de apoio/governança:** Lewis et al. 2020 — RAG genérico; o nosso é
  grounding normativo-terminológico auditável (`Lewis2020RAG`); Wu et al.
  2022 — HITL survey; reposicionar o humano de anotador para **instância
  deliberativa e de segurança** (RDR L113) (`Wu2022HITLSurvey`); Geng et al.
  2025 — structured outputs: conformidade estrutural ≠ qualidade semântica
  (`Geng2025StructuredOutputs`); NIST AI RMF/GenAI — TEVV e override humano
  (`NIST2023AIRMF`, `NIST2024GenAIProfile`).

**Como os resultados ocupam a lacuna:** cada vizinho para antes da escrita
segura no modelo; nós medimos o ciclo inteiro e devolvemos ao campo o que ele
não tinha — o custo medido do grounding ingênuo (R5/R6), o censo do catálogo
bSDD (R7) e o protocolo reprodutível multi-GPU com modelos locais (C-B/C-C).

**Estado da bibliografia:** o `refs.bib` está largamente pronto (7 entradas
buildingSMART, 5 IfcOpenShell/IfcTester, 4 Ollama, reprodutibilidade
Boettiger/Nüst/Leipzig). **Faltas obrigatórias:** ABNT NBR 15575 (base do
perfil IDS) e ABNT NBR 15220-2 (método do argumento térmico R8); ISO
16739-1:2024 (IFC 4.3 — hoje só páginas web); Zheng & Fischer; Iversen et
al.; venue do Fuchs 2025. **Higiene:** remover as autocitações de arquivos
locais (`DossieTecnico2026`, `RelatorioDeepResearch2026`); não citar claims
do RDR ancorados em marcadores `citeturn…` sem recuperar a fonte primária.

**Texto pronto para reuso (não reescrever do zero):** resumo/abstract do
artigo (RDR L332/L340); "a ideia central" (RDR L354); "LLM cercado, não
soberano" (DTC L23); fronteira LLM×código com o achado aritmético (DTC L65);
reprodutibilidade como contribuição (RDR L155); tabelas de baselines (RDR
L471-481), métricas (L483-499) e ameaças à validade (L418-423); matriz de
lacunas com "frases honestas" (L201-214). **Ressalva:** RDR e DTC são
pré-campanha — as seções de "resultados esperados" deles estão obsoletas;
a fonte dos números é a §4/§9 deste argumentário e os docs datados.

---

## 3. As quatro contribuições defensáveis

**C-A. Framework de grounding openBIM para LLMs em enriquecimento de IFC.**
Primeira combinação publicada de IDS + bSDD como restrições formais em torno
de um LLM que enriquece IFC, com humano no circuito e pós-validação. Evidência
de que é framework e não retórica: cada componente tem efeito **medido**
(etapa determinística cria os campos IDS antes do LLM; bloco bSDD ablacionado
com kill-switch; pós-validação e proveniência em 100% das escritas simuladas).

**C-B. Evidência empírica quantitativa de viabilidade de LLMs locais.**
20 modelos medidos (10 de 8 GB + 10 de 12 GB), 2 IFCs, 4.983 itens/303
classes, 3 GPUs, com recomendação por faixa de VRAM e por métrica. O campo não
tinha esse dado com modelos locais fixados por digest.

**C-C. Protocolo de avaliação reprodutível.** Dataset + IDS + GT congelado por
SHA-256 + release Windows de um clique + identidade de execução por hash +
métricas por item e por classe de equivalência. Prova de reprodutibilidade:
duas máquinas com **identidade idêntica** (`5cab7c70…`) produziram o mesmo
pódio; uma terceira (arquitetura nova) replicou o pool de classes dentro de
0,9 pp.

**C-D. Governança e auditabilidade de IA em engenharia.** Pré-registro em
docs datados, mudança de prompt tratada como mudança de instrumento, emenda de
GT governada e ratificada, comparador tratado como instrumento, vazamento de
gabarito **medido** (13,6 pp; 77,8 pp) e bloqueado por teste automatizado. O
episódio fills-element demonstra a auditabilidade na prática: um "defeito
declarado" do par foi requalificado pela ablação como efeito quantificado do
tratamento — o método detectou e explicou o próprio artefato.

---

## 4. Resultados como argumentos (R1–R12)

Cada linha: claim → evidência → fonte.

**R1. Uso assistido é viável em hardware de escritório.** gemma2:9b atinge
0,8216/0,8250/0,8232 top-1 por item nas três GPUs; qwen3.5:9b 0,94 top-3.
Em 12 GB, qwen3:14b chega a 0,9199 por item e qwen2.5:14b a 0,983 top-3.
→ `resultado-par-v77`, `resultado-escala-4070`, `resultado-replicacao-5050`.

**R2. O pódio depende da métrica — e isso é um resultado, não um problema.**
Item × classe × top-3 elegem líderes diferentes (item: gemma2; classe:
mistral↔qwen3.5:9b, empate estatístico cujo líder pontual alterna com a GPU;
top-3: qwen3.5:9b). Para fluxo com revisor, top-3 é a métrica operativa
(caso qwen2.5: 1.379/1.470 itens de fogo com a resposta certa em 2º lugar).
→ `resultado-v75` (primeira observação), par v7.7 (confirmação), 5050 (empate).

**R3. A classe de equivalência é a unidade honesta de leitura.** 6 estímulos
de FireRating respondem por 40% do GT do prédio; 1 estímulo térmico vale 40 pp
de estrato; na 5050 o top-3 de item do mistral subiu +11,5 pp por exatamente
2 decisões (574 itens) sem que o top-3 de classe se movesse. Testes pareados
por item dão significância espúria (p<0,0001 vs p=0,82 por estímulo).
→ `licoes-metodologicas`, `achado-aritmetica-termica`, `replicacao-5050`.

**R4. Escala paga; novidade não.** 7-9B → 12-14B: +13,9 pp em classes
(4 pares estritos de família, n=1.212, McNemar p=1,2e-16; qwen2.5 7→14b
+30,2 pp em itens). Geração nova no mesmo porte: n.s. Pós-treino de raciocínio
(r1): **−9,6 pp** (p=0,0022), com 38/303 gerações vazias sob format=json.
MoE (gpt-oss): colapso de formato (7/303 válidas), não de capacidade (6/7
corretas quando parseia). → `resultado-escala-4070`.

**R5. Grounding só ajuda se contiver a resposta.** Decomposição das camadas
do prompt: evidência do arquivo **+31,2 pp** (masking, matriz v6) · bloco bSDD
como entregue hoje **−2,34 pp** (ablação com kill-switch, p=0,00022) · camada
normativa dos templates: não medida (extensão declarada). Corolário: o espaço
do prompt é soma zero — cada token paga aluguel ou atrapalha quem paga.
→ `resultado-matriz-v6`, `resultado-ablacao-bsdd`, `licoes-grounding`.

**R6. O custo do bSDD tem mecanismo, não é mistério.** (1) Bloco sem escopo
nos estímulos de relação = catálogo de 42,5 KB (mediana dos blocos: 434
chars) → janela estourada → a tarefa é truncada → modelos respondem tokens do
catálogo (`BARREL`, `TEU`) obedecendo "use apenas o vocabulário fornecido" —
fills 0/20 **nas três GPUs**; sem bloco, 16/20. (2) Instrução de obediência
sobre vocabulário aberto → ancoragem conservadora (EI 30 em vez da banda
EI/REI 60; gemma2 0×22 flips direcionais, p=4,8e-7). (3) Diluição difusa:
+1,71 pp mesmo sem os estímulos de relação. Latência: zero diferença — bSDD
não custa tempo, custa acurácia. → `resultado-ablacao-bsdd`.

**R7. A lacuna é do catálogo, não do padrão — crítica construtiva.** Censo ao
vivo (18/08): 426 dicionários no bSDD, 11 pt-BR, **nenhum** com valores de
desempenho (fogo/térmica/acústica); ABNT ausente; propriedades do experimento
são IfcLabel/measure (texto livre por design do schema). O mecanismo
`allowedValues` funciona onde há conteúdo (enum de `Status`; precedente ACCA
Antincendio modela resistência ao fogo). Call-to-action: dicionários NBR de
desempenho publicados no bSDD tornariam a hipótese "grounding ajuda"
testável — e o canal IDS de vocabulário está mapeado (4 travas documentadas).
→ `auditoria-bsdd-ids`.

**R8. Aritmética não é tarefa de LLM — é tarefa do sistema.** No colapso
térmico do v6 (top-1 0,624→0,219 com top-3 idêntico), o modelo montou a
memória de cálculo **verbatim** à derivação do GT e errou a soma; recomputando
as 4 memórias produzidas, 3 cruzam a banda de 10%. Consequência de
arquitetura: o LLM declara os termos, o código executa a conta
(`thermal_recompute`), e `valor ≠ 1/R_total` vira critério objetivo de
rejeição — governança, não prompt. → `achado-aritmetica-termica`,
`condicao-v7`.

**R9. Estabilidade entre ambientes é propriedade do modelo (eixo novo).**
3 GPUs, 3 pares, 2 arquiteturas: no agregado, trocar GPU desloca ~7% das
classes de forma **simétrica** (McNemar n.s. nos 3 pares) — mas a variância é
do modelo: gemma2 flippa 1–2 classes por par (0,2–0,5% dos itens) enquanto
lfm2.5 flippa 42–44 classes (até 23% dos itens), cai de 0,540 para 0,391 e
apresenta a 5ª distribuição de fogo em 5 rodadas. Implicação de engenharia:
escolher modelo por estabilidade, não só por acurácia média. O piso de ruído
cross-GPU vira régua para separar efeito real de instabilidade.
→ `resultado-par-v77`, `resultado-replicacao-5050`, `resultado-ablacao-bsdd`.

**R10. Erro silencioso é a métrica que conecta LLM e revisor.** Errado com
confiança alta: de 2,6% (qwen3:14b) a 45,9% (mistral-small) — e instável
entre ambientes (mistral 13,1%→25,1% na troca de GPU; qwen3.5:4b converte o
pilar térmico em abstenção visível: 231 itens). Nuance da ablação: o bloco
bSDD servia de sinal de cautela — sem ele, llama sinaliza 4,5%→0,02% e sobe a
confiança. O revisor humano não é decoração: é a defesa contra a fração do
erro que chega confiante. → `resultado-escala-4070`, `replicacao-5050`,
`resultado-ablacao-bsdd`.

**R11. Viabilidade computacional com números de campo.** 4070 12 GB: fila
4,35 h, tudo residente. 8 GB (4060/5050): os dois líderes **transbordam**
(gemma2 frac 0,78–0,80; qwen3.5:9b 0,86–0,88) — recomendação de compromisso
qwen3.5:9b, plano B residente llama3.1. Blackwell 8 GB é ~1,49× mais rápida
que Ada 8 GB por chamada, mas o transbordo persiste — a fronteira útil é
VRAM, não geração. Em 12 GB, nemo é o ótimo de classe+custo (p50 3,68 s).
Reuso por equivalência corta 95,7% das chamadas. → `resultado-par-v77`,
`resultado-escala-4070`, `resultado-replicacao-5050`.

**R12. Determinismo e reprodutibilidade demonstrados, não prometidos.**
Estratos com template intocado: 0,0 de variação em 10 modelos entre runs
separados por 5 dias e 14 commits. Par com identidade idêntica nas duas
máquinas; 0 divergências do comparador em 99.660 + 199.320 + 99.660
vereditos recomputados. → `resultado-matriz-v6`, `resultado-par-v77`,
`replicacao-5050`.

---

## 5. Argumentos metodológicos (M1–M7)

**M1. Pré-registro operacional:** cada condição tem doc datado *antes* da
rodada (condicao-v7, v7.6, v7.7, escala-4070, ablacao-bsdd), com hipóteses —
inclusive as refutadas (H2/H3/H4 da ablação), relatadas como tal.

**M2. Mudança de prompt = mudança de instrumento:** versões pinadas em três
pontos + sha256 do template na identidade; delta entre versões medido **sem
GPU** com espião de prompts antes de qualquer rodada.

**M3. Anti-vazamento de gabarito medido e automatizado:** escrever prompt
olhando erros custou 13,6 pp (e comprime o ranking — infla os fracos); um
exemplar JSON com o valor do GT valia 77,8 pp; `test_prompt_nao_vaza_ground_truth`
trava colisões numéricas declaradas. O comparador também é instrumento:
presumir a parte difícil da resposta é vazamento.

**M4. GT governado:** protocolo `full-coverage-equivalent-v1`, pins SHA-256,
emenda EI/REI ratificada com hash, rótulos contestados rastreados (drywall
REI 60, fibrocimento 2,0) e reportados por fatia de confiança.

**M5. Unidade de análise correta:** item (micro) E classe de equivalência
(macro), sempre os dois; testes pareados por classe; estratos declarados.

**M6. Identidade de execução:** hash canônico de GT+IFC+IDS+prompt+lock+
parâmetros; estágios só validam com identidade correta; o tratamento da
ablação entrou na identidade (braços não se contaminam).

**M7. Honestidade instrumental:** janela de contexto reportada pelo efetivo
(2048/4096; nunca o teto 8192); fila absoluta da 4060 não é métrica (uso
diurno) — latência por chamada é; SHGC declarado como concordância com
convenção, não derivação.

---

## 6. Objeções: as reais (parecer ERA BIM) e as prováveis (O1–O10)

**As seis cobranças reais dos pareceres (01/08) × estado em 19/08.** Os
revisores validaram o desenho ("decisões certas", humano-no-loop e LLM local
elogiados) e cobraram maturidade — três semanas depois, o quadro é outro:

| Cobrança do parecer | Estado 19/08 | O que ainda fecha |
|---|---|---|
| Resultados reais, não prospectivos (P1) | **Dissolvida**: 5 estudos, 20 modelos, 3 GPUs, p-valores | Só escrever |
| Referência humana: quem, quantos, **concordância entre avaliadores** (P1) | GT integral congelado com protocolo, emenda ratificada, fatias de confiança — mas revisão **autoral de uma pessoa**, sem κ | **Fase C: 2º revisor + Cohen/Fleiss κ** — pendência metodológica nº 1 |
| Procedência/adequação com **custo × benefício** (P1) | Medido: latência, VRAM, fração residente, tok/s, recomendações por faixa (nemo 12 GB; qwen3.5:9b 8 GB) | Tabela acurácia/recurso no molde ARCHER (sem GPU; dados existem) |
| **Quem é o usuário**: projetista, contratante, ambos? (P2) | Nunca declarado no texto | Decisão de escopo escrita (§11) |
| É preciso preencher **todos** os campos? Por quê? (P2) | O sistema assume perfil IDS; perfis de readiness existem em `src/profiles/` | Justificar preenchimento por perfil de uso, ou admitir seletivo |
| Testar com **colegas em contexto real** (P2) | Nunca feito (proxy simulado) | Mini-estudo n≈6 no molde Ishigaki-IDS (§10) |

As objeções antecipadas para o próximo revisor:

**O1. "Só 2 IFCs, mesma tipologia residencial."** Correto e declarado. O
desenho troca amplitude por profundidade governada: GT integral (não
amostral), 303 classes, 3 GPUs, 5 condições de instrumento. Generalização de
tipologia é trabalho futuro explícito; o protocolo é reaplicável tal qual.

**O2. "O GT embute convenções normativas discutíveis."** Por isso bandas de
equivalência, fatias de confiança, emenda governada e a distinção
convenção×conhecimento (fogo: mínimo normativo no top-1, aceito no top-3;
nemo prova que a convenção é alcançável: 1,000). O resíduo de erro dos
líderes é convenção — quantificado, não escondido.

**O3. "Resultado do bSDD ataca o openBIM."** Não: a crítica é ao estado do
catálogo e ao **nosso** empacotamento (dois donos separados, R6/R7). O
mecanismo do padrão funciona onde há conteúdo; o bSDD permanece no pipeline
(URI canônica, classificação, rastreabilidade); a correção de engenharia
(v7.8) já existe, verificada sem GPU. Enquadrar como diagnóstico + agenda.

**O4. "Seed único, uma réplica por condição."** A réplica relevante é entre
máquinas (n=3 GPUs, McNemar n.s.) e entre condições (invariantes de template:
0,0 de variação). Réplicas de seed medem outra coisa (variância de amostragem
do decoder) e temp=0,1 a minimiza; instabilidade real está medida no eixo
cross-GPU — mais informativo que reamostrar na mesma máquina.

**O5. "Prompt engineering contamina a comparação entre modelos."** Prompt
uniforme para todos os modelos (hints por modelo prototipados e removidos);
três naturezas legítimas de estímulo declaradas (evidência, vocabulário
genérico, formato); mudanças de instrumento versionadas e medidas antes de
rodar (M2/M3).

**O6. "Por que não GPT-4/nuvem/fine-tuning/RAG?"** Escopo declarado:
soberania de dados de projeto (escritório BR), custo previsível, hardware
alvo 8–12 GB. Fine-tuning quebraria a comparação de famílias off-the-shelf e
o RAG aqui É o grounding estruturado (IDS/bSDD) — a versão auditável dele.

**O7. "As taxas de aceitação/edição são simuladas."** Verdade — `review_proxy`
com `simulation: true`. Ou se roda o mini-estudo humano antes da submissão
(ver §8), ou se reescreve a promessa: o benchmark mede qualidade da sugestão
e carga esperada de revisão (top-3, erro silencioso, abstenção), e o estudo
de revisão real fica como etapa seguinte. Nunca apresentar o proxy como
medida de comportamento humano.

**O8. "n=115/303 estímulos não ranqueia 10 modelos."** Por isso o artigo
reporta perfis e empates estatísticos (mistral×qwen3.5:9b), testes pareados
por classe, e conclusões que sobrevivem ao piso de ruído (escala +13,9 pp,
p=1,2e-16; ablação +2,34 pp, p=2,2e-4; r1 −9,6 pp, p=0,0022).

**O9. "Ollama/quantização não representa os modelos 'de verdade'."** É o
ponto: o objeto é o que roda no hardware do escritório. Versão do servidor
pinada (0.32.5), digests dos blobs registrados, formato de saída forçado
igual para todos — e o colapso do gpt-oss sob format=json está diagnosticado
como artefato de formato, com sonda declarada como extensão.

**O10. "Cadê a comparação com a camada determinística?"** Redirecionada por
desenho (fase3): a camada determinística cria os campos exigidos pelo IDS
*antes* do LLM — as tarefas do LLM começam onde a determinística termina. A
pergunta interna virou a pergunta externa (governança), que é a contribuição.

---

## 7. O que NÃO afirmar (lista dura)

- "bSDD é inútil" → escrever: *no estado atual do dicionário IFC 4.3 e sem
  dicionários normativos brasileiros, o grounding textual do bSDD não
  contribui além da âncora de classe, e a injeção sem escopo tem custo
  mensurável.*
- Automação integral, "o LLM corrige o modelo" → o LLM **sugere**; só escreve
  o que o humano aprovou, e depois valida.
- Janela de contexto 8192 → efetivas 2048/4096 (20 chamadas a 8192,
  justamente o mecanismo do fills).
- Fila absoluta da 4060 como métrica de hardware → latência por chamada.
- "Mistral é o melhor em top-3" (5050) → é peso de 2 classes-pilar; classe
  top-3 não se move. Idem qualquer claim que só exista numa métrica-item.
- Vencedor único em classe → mistral×qwen3.5:9b é empate; a ordem alterna.
- Ranking do smoke de julho (refutado pelo benchmark de 28/07).
- Números do par misturados com legado v6 sem a ressalva de procedimento
  (`accuracy_legacy` compartilha população, não procedimento).

---

## 8. Reconciliação: o que o resumo de maio prometeu × o que existe

| Promessa (maio) | Estado real (agosto) | Como escrever |
|---|---|---|
| Condições "sem grounding / IDS / IDS+bSDD" | Braços medidos: com/sem bSDD (kill-switch); evidência via masking (v6); canal IDS de vocabulário **desligado por 4 travas** (diagnóstico documentado) | Reformular como decomposição de camadas de grounding + diagnóstico do canal IDS como achado |
| Accuracy top-1/top-3, P/R/F1 | Top-1/top-3 por item e por classe, 3 GPUs. P=R=F1 no desenho atual (1 sugestão/issue) — métrica redundante | Reportar top-k item/classe + estratos; retirar P/R/F1 |
| Taxas de aceitação/edição/rejeição + tempo médio de revisão | **Só proxy simulado**; tempo nunca medido | Ou mini-estudo humano antes da submissão, ou reescrever como trabalho em andamento (O7) |
| Conformidade IDS antes/depois | Medida em simulação de aplicação (ex.: ids_post_pass por modelo) | Reportar como pós-validação simulada, rotulada |
| Falhas de pós-validação | Instrumentadas no pipeline e no benchmark | OK, reportar |
| "Resultados esperados…" (futuro) | Cinco estudos completos | Reescrever tudo no pretérito, com números e p-valores |

Esta tabela também é a resposta ao "integralmente prospectivo" do parecer 1:
tudo que era promessa virou medição — exceto as duas linhas humanas (revisão
real e κ do GT), que são exatamente as lacunas 1–2 da §10.

---

## 9. Números-âncora para citar (fonte entre parênteses)

| Âncora | Valor |
|---|---|
| Corpus | 2 IFCs; 4.720+263 itens; 202+101 classes; 5 issue types (gt-integral) |
| Pódio oficial (par v7.7) | item gemma2 0,8216/0,8250; classe mistral 0,7063/0,6865 ≈ qwen3.5:9b; top-3 qwen3.5:9b 0,9430/0,9382 (par) |
| Replicação | pool classe 0,6053/0,5967/0,5980; McNemar n.s. nos 3 pares (5050) |
| Estabilidade | gemma2 17/26/9 flips-item; lfm2.5 483/898/1.167; fogo lfm 5 distribuições (par, 5050) |
| Escala | +13,9 pp classes, p=1,2e-16; qwen3:14b 0,9199 item; nemo 0,8086 classe e fogo 1,000; r1 −9,6 pp (escala) |
| Grounding | evidência +31,2 pp (v6); bSDD −2,34 pp, p=2,2e-4; fills 0/20→16/20; bloco 42,5 KB vs mediana 434 chars (ablação) |
| Censo bSDD | 426 dicionários; 11 pt-BR; 0 com valores de desempenho; allowedValues funciona (Status; ACCA) (auditoria) |
| Aritmética | 1 estímulo = 40 pp; soma verbatim errada; recompute recupera 3/4 (aritmética-térmica) |
| Vazamento medido | 13,6 pp (prompt pós-erro); 77,8 pp (exemplar solar) (licoes; condicao-v7-4) |
| Erro silencioso | 2,6% (qwen3:14b) a 45,9% (mistral-small); gemma2 ~11-12% (escala, 5050) |
| Viabilidade | 4070 fila 4,35 h; 4060 1,9–3,2× mais lenta/chamada; 5050 = 1,49× a 4060; transbordo dos líderes em 8 GB persiste em Blackwell (par, 5050) |
| Reprodutibilidade | identidade idêntica em 2 máquinas; 0 mismatches em ~400k vereditos recomputados; determinismo 0,0 em estratos intocados (par, v6) |

---

## 10. Lacunas que ainda dá para fechar (ordem nova, ditada pelo parecer)

1. **GT com segundo revisor + concordância (κ)** — cobrança explícita do
   parecer 1 ("toda a validade das métricas depende disso") e Fase C do
   plano. Custo: horas de um colega/orientador sobre as **303 classes** (a
   revisão é por classe, não pelos 4.983 itens) + Cohen/Fleiss κ. Sem GPU.
2. **Mini-estudo com praticantes (n≈6, molde Ishigaki-IDS)** — fecha o
   parecer 2 e a promessa de "tempo de revisão": colegas do IME revisando
   ~100 sugestões estratificadas na UI, medindo tempo/decisão, aceitação
   real×proxy e concordância. Custo: protocolo 1 dia + horas dos voluntários.
3. **Duas decisões de escopo em texto** (parecer 2; custo ≈ um parágrafo
   cada): usuário-alvo (projetista/contratante/ambos) e preenchimento
   exaustivo × seletivo (ancorar nos perfis de readiness).
4. **Tabela acurácia × custo de recurso** (molde ARCHER) — computável dos
   JSONs existentes, sem GPU.
5. **Ablação da camada normativa dos templates (extensão §8 declarada)** —
   completa a decomposição R5. ~1 dia de instrumentação (padrão kill-switch
   pronto) + 4,4 h GPU (4070) + análise.
6. Rodapés: **olmo2:13b** (~1 h, fecha o desvio MoE) e **sonda sem
   format=json** (~2 h, prova o colapso de formato do r1/gpt-oss).
7. **NÃO fazer:** re-rodar tudo em v7.8 (o braço off já é o teto empírico do
   que as correções compram; v7.8 é o instrumento do *próximo* estudo) —
   nem caçar chamada aberta hoje (decisão de 01/08: esperar nov/2026 não
   custa nada e o trabalho das lacunas 1–3 é exatamente o que os pareceres
   pediram).

---

## 11. Perguntas para o Otranto (decisões que são dele)

1. **Relatório PIBIT — modelo, formatação e prazo:** template e estrutura
   exigidos, tamanho, idioma, data de entrega. É o alvo imediato da escrita.
   O esqueleto abntex2ime existe (RDR L301-322 recomenda a estrutura); os
   capítulos ainda são exemplos. Escrever o relatório já no esqueleto do
   futuro paper ISARC?
2. **Escopo de resultados no relatório:** todos os cinco estudos ou o par
   oficial + destaques? (recomendação nossa: todos — a narrativa é uma só:
   viabilidade → escala → grounding → estabilidade.)
3. **Fase C do GT:** ele topa ser o **segundo revisor** das 303 classes
   (concordância κ contra a revisão autoral)? É a resposta direta ao
   parecer 1 do ERA BIM.
4. **Mini-estudo com praticantes:** autorização e logística para n≈6
   colegas do IME (molde Ishigaki-IDS) — entra no relatório PIBIT ou fica
   para a versão ISARC?
5. **Usuário-alvo declarado** (parecer 2): projetista, contratante ou ambos
   — decisão de posicionamento que muda Introdução e Discussão.
6. **Tom do achado bSDD:** validar o enquadramento construtivo (diagnóstico
   do catálogo + call-to-action dicionário NBR) — é o resultado mais
   sensível politicamente na comunidade openBIM.
7. **Roadmap de publicação** (decisão de 01/08, "a confirmar com o
   orientador"): ISARC 2027 (deadline provável dez/26–jan/27) + ITcon como
   hedge + SBTIC 2027; reavaliar chamadas em nov/2026 (EG-ICE/EC3/CIB W78).
   Idioma do paper (inglês para ISARC/ITcon) — decidir cedo muda a escrita.
8. **Autoria, ordem e menções** (PIBIT, máquinas emprestadas de terceiros).

---

## 12. Mapa de materiais (onde está cada coisa)

- **Resultados (docs datados, prontos para virar seções):**
  `docs/resultado-matriz-v6-2026-08-03.md` · condição v7/v7.4/v7.6/v7.7 ·
  par v7.7 (memória + artifact "Par Unificado v7.7") ·
  `docs/resultado-ablacao-bsdd-2026-08-19.md` ·
  escala-4070 (artifact "Escala-4070") ·
  `docs/resultado-replicacao-5050-2026-08-19.md` ·
  `docs/auditoria-bsdd-ids-2026-08-18.md` ·
  `docs/achado-aritmetica-termica-2026-08-02.md` ·
  `docs/pontos-de-calculo.md` (constantes normativas).
- **Literatura:** `Artigo/RELATORIO_DEEP_RESEARCH.md` (revisão, maio) ·
  `Artigo/refs.bib` (15 KB) · `Artigo/DOSSIE_TECNICO_CIENTIFICO_DO_PROJETO.md`
  (arquitetura, 04/08 — anterior aos resultados finais).
- **Esqueletos LaTeX:** `Artigo/artigo_ime_ifc_quality_copilot/` (abntex2ime,
  capítulos ainda são exemplos) · `Artigo/ERABIM_RESUMO_2026/` (projeto do
  resumo negado — encerrado; serve só de referência de texto).
- **Governança da publicação (vault Second Brain):** `Parecer - A ERA BIM
  2026` (pareceres na íntegra + tradução em tarefas) · `Decisão - Pausar
  submissão a congresso e seguir no PIBIT` · `Roadmap de publicação - IFC
  Quality Copilot` (ISARC/ITcon/SBTIC, datas ✅/⚠️, alerta de predatório
  WASET) · `Artigo - IFC Quality Copilot (ENTAC 2027)` (estrutura do paper;
  o nome do arquivo está sabidamente errado — não existe ENTAC 2027).
- **Evidência de terceiros a citar (⚠️ conferir os números nos PDFs antes de
  citar — ainda não lidos na íntegra):** BIM-Edit (melhor LLM ~49,5% em
  edição de IFC, ≤3,4% de tarefas completas — justifica o
  `aprovado_pelo_usuario == True`), ARCHER (open-weights local ≈97,8% da
  acurácia de fronteira a ~1/4 do custo — justifica LLM local e dá o molde
  custo×acurácia), Ishigaki-IDS (verifier-aware, −54,7% de tempo, n=6
  praticantes — molde do mini-estudo). Fonte: nota "Pesquisa - LLM em IFC e
  IDS (achados do radar 2026-07)" no vault.
