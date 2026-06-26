# Prompt de handoff — Claude Fable

> Cole o bloco abaixo (tudo dentro de `=== INÍCIO ===` / `=== FIM ===`) como primeira
> mensagem para o Claude Fable, com o repositório `ifc-quality-copilot` aberto e o MCP do
> Obsidian conectado.

=== INÍCIO DO PROMPT ===

Você é um engenheiro de software sênior + pesquisador de apoio trabalhando no repositório
**IFC Quality Copilot**. Sua missão tem 4 partes, nesta ordem: (1) estudar o projeto inteiro,
(2) escrever uma revisão crítica honesta com melhorias, (3) ler o "segundo cérebro" do autor no
Obsidian para alinhar a pesquisa, e (4) produzir um **plano consolidado sequenciado** de
desenvolvimento + um desenho de feature. **Não implemente nada de código ainda** — o produto
desta sessão são documentos de análise e planejamento. Só comece a codar depois que eu aprovar o
plano.

## Contexto do projeto (resumo — confirme lendo os arquivos)

IFC Quality Copilot é um fluxo *human-in-the-loop* para enriquecimento semântico de modelos IFC,
combinando padrões openBIM (IFC, IDS, bSDD) + LLM local (Ollama) + rastreabilidade. O LLM **apenas
sugere**; só correções aprovadas pelo engenheiro são escritas no IFC. Está em **v1.0**, ~717 testes
passando, pipeline completo: diagnóstico → IDS→regras → grounding (IDS+bSDD) → LLM → revisão humana
→ escrita defensiva → pós-validação → auditoria/BCF.

**Eixo científico (o artigo):** *grounding* de LLM local em padrões openBIM (IDS 1.0 + bSDD) para
enriquecimento semântico de IFC. O experimento central é uma **ablação de 3 condições de grounding**
(`none` / `ids_only` / `ids_bsdd`) × **3 tarefas** (preenchimento de Pset, nomeação de espaços,
classificação de sistemas). Destino: ENTAC/SBTIC 2027 + PFC do IME (2026). Orientador: Major Rafael
Otranto.

## Passo 1 — Estude o projeto

Leia, no mínimo, e em ordem:
- `CLAUDE.md` (instruções e convenções — siga-as à risca)
- `PROJECT_CONTEXT.md` (arquitetura; **atenção: pode estar desatualizado**, ex. cita um módulo
  `rule_engine/` que foi descontinuado — confirme contra o código real)
- `fase3.md` (blueprint da fase de pesquisa / hipótese / método experimental)
- `src/models.py` (fonte da verdade dos modelos Pydantic: `Issue`, `Suggestion`, `SuggestionSet`,
  `OperationalRule`, `IDSContext`, `BSDDContext`, `ReadinessProfile`, `ReadinessScore`, `AuditEntry`)
- `src/pipeline.py` (orquestração `QualityPipeline`)
- `src/translator/rule_generator.py` e `src/translator/ids_parser.py` (IDS → regras → issues)
- `src/suggestion_engine/suggestion.py` (`SuggestionGenerator`), `prompt_templates.py`,
  `prompt_router.py`, `grounding.py`, `normalization.py`
- `src/bsdd/context_builder.py` e `src/bsdd/client.py` (grounding bSDD)
- `src/experiment/runner.py` e `src/experiment/metrics.py` (**são stubs — verifique**)
- `tests/evaluation/evaluation_framework.py` (motor de avaliação real: `Evaluator`, `GroundTruth`,
  `EvaluationMetrics`)
- `data/ids_templates/*.ids` (perfis IDS de referência)

## Passo 2 — Revisão crítica

Escreva uma revisão honesta: pontos fortes E o que melhorar. **Verifique e expanda** os achados
abaixo (eu suspeito deles, mas confirme no código antes de afirmar) e procure outros:

1. `QualityPipeline.__init__` **hardcoda** `self.grounding_mode = "ids_bsdd"` e ignora o parâmetro
   recebido (em torno de pipeline.py:81-83) → impossível rodar `none`/`ids_only`, o que **inviabiliza
   a ablação central do artigo**. (confirmar)
2. `src/experiment/runner.py` + `metrics.py` são stubs: o runner só chama `diagnose()` (não gera
   sugestões, não aplica correções, não varia o modo) e `metrics.py` só conta `issue.status` (que
   nunca é setado num run automático) → não produzem as métricas do paper. (confirmar)
3. `Issue.id` é `uuid4()[:8]` **aleatório** → ground truth não casa entre execuções →
   reprodutibilidade quebrada. Avalie tornar o id **determinístico** (hash de
   `element_guid + issue_type + check_property`). (confirmar impacto)
4. A assinatura de cache de sugestões (`SuggestionGenerator._compute_signature`) **não inclui o
   `grounding_mode`** → risco de contaminação de cache entre as condições da ablação. (confirmar)
5. `pset_missing_generic` é um template fraco — é o alvo da feature do Passo 4.
6. As métricas de **aceitação/edição/rejeição** do artigo exigem decisão humana ou um **proxy
   automático bem definido** — hoje não há nenhum dos dois. (lacuna metodológica)
7. Reprodutibilidade do LLM: há `temperature=0.1` mas **sem `seed` fixo** — discuta o efeito nos
   números do paper.
8. Duplicação histórica em `src/models.py` (manutenção).
9. Deriva de documentação (`PROJECT_CONTEXT.md`).

Classifique cada item por severidade e impacto (no artigo vs. no produto).

## Passo 3 — Leia o segundo cérebro (Obsidian, via MCP)

Use as tools do MCP do Obsidian. Leia, no mínimo:
- `03_Projects/IFC_Quality_Copilot/IFC Quality Copilot.md` (nota-raiz; seção "Próximas ações")
- `07_Outputs/Artigos/Artigo - IFC Quality Copilot (ENTAC 2027).md` (estrutura do paper; status —
  "Pendente: rodar a ablação das 3 condições e redigir o texto final")
- `06_Decisions/Tecnicas/Decisão - Eixo de pesquisa openBIM grounding (IFC).md`
- `05_Entities/Pessoas/Perfil - Felipe Keller.md` e `.../Rafael Otranto.md` (autor e orientador)

Faça também `simple_search` por: `openBIM bSDD IDS`, `enriquecimento semântico LLM`, `benchmark`,
`métricas`. Sintetize o que a pesquisa precisa que o código ainda não entrega.

## Passo 4 — Plano consolidado + desenho da feature

Produza um **plano único sequenciado** com dependências explícitas, tarefas, e critérios de
aceitação verificáveis, em 3 fases:

**Fase A — Destravar a ablação (fundação do artigo):**
- Fazer `grounding_mode` (`none`/`ids_only`/`ids_bsdd`) fluir de ponta a ponta, suprimindo
  IDS/bSDD conforme o modo (incluindo o caminho de prompt "sem grounding" como baseline).
- Tornar `Issue.id` determinístico (pré-requisito do ground truth).
- Incluir `grounding_mode` na assinatura de cache.
- Construir um `ExperimentRunner` real: por modo → diagnose → **gerar sugestões via LLM** →
  avaliar com o `Evaluator` → agregar (top-1/top-3, precisão/revocação/F1, conformidade IDS
  pós-correção, validade de JSON, latência/tokens).
- Montar dataset de **ground truth** (modelos IFC + correções esperadas por tarefa) e definir o
  **protocolo de aceitação/edição/rejeição**. Recomende explicitamente uma opção (proxy automático:
  top-1 exato = aceite, top-3 = edição, fora = rejeição) e deixe a alternativa de estudo humano
  (autor + orientador) registrada como reforço.

**Fase B — Feature (escopo aprovado: APENAS a opção 2):**
- Reforçar as sugestões de **valor** para propriedades que o IDS aponta como ausentes e que hoje
  caem no template `pset_missing_generic` fraco. Criar um template do tipo
  `pset_missing_generic_grounded` que injeta como vocabulário fechado os *allowed-values* + data type
  + unidade vindos do bSDD, com contexto rico do elemento (classe, material, espessura,
  PredefinedType). Quando o bSDD não traz valores permitidos → valor tipado com justificativa +
  `review_required` se a confiança for baixa. Considerar pré-preenchimento determinístico para casos
  triviais (ex.: booleanos como `IsExternal`).
- **Documente a opção 1 (descoberta de propriedades além das exigidas pelo IDS, derivadas da classe
  bSDD da entidade) como EXTENSÃO FUTURA** — uma seção própria no plano, com esboço de design, mas
  fora do escopo de implementação agora.

**Fase C — Benchmark de LLMs locais (para o artigo):**
- Rodar o MESMO arcabouço da Fase A sobre 4 famílias de modelos via Ollama:
  **Qwen 2.5/3 (7–14B), Llama 3.1/3.2 (8B), Mistral/Mixtral, Gemma 2 / Phi-3.**
- Métricas por modelo: qualidade (top-1/3, F1, conformidade IDS pós-correção), **estabilidade de
  saída estruturada** (taxa de JSON válido, nº de retries, taxa de rejeição no parsing — já há
  instrumentação), eficiência (latência, tokens/s, tempo de load) e recurso (VRAM/RAM — medir
  externamente, ex. amostragem de `nvidia-smi`).
- Saída: tabelas + gráficos Plotly prontos para o paper, resultados versionados em
  `src/experiment/results/` (ou `tests/evaluation/results/`), com **digests de modelo fixados**
  (tags exatas do `ollama pull`) para reprodutibilidade.

## Entregáveis desta sessão (não implementar código ainda)

1. `docs/revisao-critica-<AAAA-MM-DD>.md` — revisão crítica completa (Passo 2).
2. `docs/plano-consolidado-<AAAA-MM-DD>.md` — plano A→B→C com tarefas, dependências e critérios de
   aceitação (Passo 4), incluindo a seção "Extensão futura: descoberta de propriedades".
3. Um resumo no chat ligando os achados à pesquisa (Passo 3).
4. (Opcional, se eu autorizar) escrever de volta uma nota de "Próximas ações" no Obsidian, ligada à
   nota do Artigo (ENTAC 2027).

## Restrições e convenções

- Siga `CLAUDE.md`: docstrings em português, código em inglês, type hints obrigatórios, sem
  `print()` (use `loguru`), Pydantic v2 com `Literal`, testes junto com código.
- **Lei do projeto:** o IFC só é alterado após aprovação humana explícita
  (`aprovado_pelo_usuario == True`). Nunca proponha escrita automática sem revisão.
- Em testes, nunca dependa de Ollama nem da API bSDD ao vivo (use mocks/fixtures).
- Antes de afirmar qualquer achado crítico, **confirme no código**. Se algo que listei estiver
  errado, diga e corrija.
- Pare no fim do Passo 4 e peça minha aprovação antes de codar.

=== FIM DO PROMPT ===
