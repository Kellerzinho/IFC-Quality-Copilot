Fase 3 — IFC Quality Copilot
Enriquecimento Semântico de IFC com LLMs sob Restrições openBIM

1. Síntese da Nova Direção
O recorte anterior (comparação interna entre a camada determinística e o LLM) responde a uma pergunta interna do sistema: "qual camada resolve mais issues?". É uma pergunta válida, mas defensiva — otimiza o que já existe sem avançar a fronteira do projeto nem da literatura.
A nova direção responde a uma pergunta externa e mais relevante: "um LLM pode enriquecer semanticamente um modelo IFC de forma confiável quando opera sob restrições formais do ecossistema openBIM?". Essa pergunta é mais forte por três razões:
Primeiro, é a pergunta que a literatura está fazendo agora. Fuchs & Borrmann (EG-ICE 2025) e Forth & Borrmann (2024) exploram enriquecimento semântico com LLMs, mas sem governança formal — sem IDS como gate de requisitos, sem bSDD como âncora semântica, sem validação pós-correção e sem aprovação humana auditável. Há uma lacuna clara entre "LLM sugere" e "LLM sugere dentro de um framework verificável".
Segundo, alinha o projeto diretamente ao ecossistema openBIM. IDS define o que é esperado; bSDD define o vocabulário correto; BCF comunica os problemas; IFC recebe as correções. Nenhum sistema existente fecha esse ciclo com LLM no meio e governança end-to-end.
Terceiro, é mais publicável. Uma comparação interna camada-determinística vs. LLM gera um artigo incremental. "LLM governado por padrões openBIM para enriquecimento semântico" posiciona o trabalho na intersecção de três áreas ativas (LLM para AEC, interoperabilidade openBIM, governança de IA em engenharia) e produz contribuição metodológica, não apenas empírica.

2. Recorte Principal Escolhido
Enriquecimento semântico e correção assistida de modelos IFC com LLMs locais operando sob restrições formais de bSDD (vocabulário padronizado) e IDS (requisitos verificáveis), com validação pós-correção, auditoria de proveniência e aprovação humana, produzindo artefatos BCF interoperáveis.
Em uma frase para abstract: o projeto investiga se o grounding de LLMs em padrões openBIM (bSDD + IDS) reduz erros semânticos e aumenta aceitação humana no enriquecimento de modelos IFC, comparando estratégias com e sem restrições formais em um pipeline auditável.

3. Pergunta de Pesquisa Central
Quais LLMs locais, operando sob grounding openBIM (bSDD + IDS 1.0), produzem sugestões de enriquecimento de modelos IFC com melhor precisão, consistência semântica, aceitação humana e eficiência computacional no hardware-alvo?

4. Hipótese Principal
LLMs locais (7–9B, quantizados) operando com grounding IDS+bSDD atingem conformidade IDS pós-correção e taxa de aceitação adequadas ao uso assistido (com revisão humana), com zero regressões de schema IFC e diferenças mensuráveis de qualidade e eficiência entre famílias (Qwen/Llama/Mistral/Gemma/Phi) — permitindo recomendar quais modelos são viáveis no hardware-alvo, nas 3 tarefas de enriquecimento (nomeação de espaços, preenchimento de Psets, classificação de sistemas).

5. Contribuição Científica Esperada
O que é engenharia/integração (necessário, mas não publicável isoladamente)

Integrar a API do bSDD ao pipeline Python.
Parsear IDS contra XSD e executar regras.
Exportar issues para BCFXML.
Implementar validação pós-correção com ifcopenshell.validate.

O que é contribuição acadêmica legítima

Framework de grounding openBIM para LLMs em enriquecimento de IFC. Nenhum trabalho publicado combina bSDD + IDS como restrições formais para um LLM que enriquece modelos IFC. Propor e avaliar esse framework é a contribuição principal.
Evidência empírica quantitativa da viabilidade de LLMs locais para enriquecimento de IFC sob grounding openBIM. A literatura de LLM em BIM carece de avaliação quantitativa com modelos locais reprodutíveis. Medir conformidade, aceitação, consistência e custo computacional por família de modelo é dado que o campo não possui.
Protocolo de avaliação reprodutível para enriquecimento semântico de IFC. Dataset + IDS + ground truth + métricas + script de reprodução — contribuição metodológica que permite comparação futura por outros pesquisadores.
Pipeline auditável com proveniência end-to-end. Demonstrar que cada correção tem rastreabilidade completa (issue → evidência bSDD/IDS → sugestão LLM → decisão humana → escrita → validação) é contribuição para governança de IA em engenharia.


6. Arquitetura da Próxima Fase
Módulos que permanecem inalterados

models.py — modelos Pydantic existentes.
ifc_analyzer/ — os 4 diagnósticos + extratores.
writer/ifc_writer.py — operações de escrita.
audit/logger.py — base do AuditLogger.
mcp_server/ — estável, não é foco.
ui/ — ajustes pontuais na sidebar e cards.

Módulos que precisam ser estendidos
suggestion_engine/prompt_templates.py

Novos templates que injetam contexto bSDD (classes válidas, propriedades permitidas, URIs) e contexto IDS (requisito violado, tipo de check, severidade) diretamente no prompt.

suggestion_engine/suggestion.py (SuggestionGenerator)

Receber bsdd_context: BSDDContext | None e ids_context: IDSContext | None como parâmetros.
Passar para o template de prompt correto conforme a condição experimental.

translator/

Validação do IDS contra XSD antes de parsear.
Tratamento de unidades SI em comparações numéricas.
Expor IDSContext (requisito violado, tipo de check, valores esperados) para uso nos prompts.

pipeline.py

Integrar gate de validação pós-correção.
Integrar chamada bSDD antes de gerar sugestões.

audit/logger.py

Novos campos: grounding_sources: list[str], bsdd_uri: str | None, ids_requirement: str | None, post_validation: Literal["pass", "fail", "skip"].

models.py

Adicionar BSDDContext e IDSContext como modelos Pydantic.
Estender Suggestion com bsdd_uri: str | None e ids_requirement_id: str | None.

Módulos novos
src/bsdd/client.py — Cliente para a API bSDD (REST).

search_class(query, domain) → lista de classes candidatas com URI.
get_class_properties(class_uri) → propriedades válidas para aquela classe.
get_property_values(property_uri) → valores permitidos, tipo, unidade.
Cache local (dict ou SQLite) para evitar chamadas repetidas durante a sessão.
Fallback gracioso se API offline (usa cache anterior ou retorna vazio).

src/bsdd/context_builder.py — Constrói BSDDContext para uma issue.

Dado um element_class (ex: IfcWall) e issue_type, busca no bSDD as classes e propriedades relevantes.
Formata como bloco de texto estruturado para injeção no prompt.

src/validation/post_validator.py — Gate pós-correção.

validate_element(ifc_file, guid) → ValidationResult.
Executa: (1) schema check via ifcopenshell.validate, (2) re-execução das regras IDS no elemento corrigido.
Retorna pass/fail com lista de erros.

src/bcf/exporter.py — Exportador BCFXML.

Issue → BCF Topic (GUID como component ref, severity → priority, description → markup).
Gera .bcf importável em ferramentas BCF.
Sem viewpoints 3D nesta fase.

src/experiment/runner.py — Execução em lote dos experimentos.

Configura e executa o pipeline para cada modelo do benchmark (grounding IDS+bSDD).
Coleta métricas por issue e agrega.

src/experiment/metrics.py — Cálculo de métricas.

Conformidade IDS antes/depois, aceitação, edição, regressão, F1, consistência semântica.

Como cada componente openBIM entra
bSDD: O BSDDContextBuilder consulta a API bSDD antes de cada chamada ao LLM. O contexto retornado (classes válidas, propriedades, valores permitidos) é injetado no prompt como "vocabulário de restrição". O LLM deve escolher entre opções ancoradas no bSDD. Se o bSDD não retorna resultados, o LLM opera sem essa restrição (registrado na auditoria).
IDS: O IDSTranslator continua gerando issues a partir do IDS. O contexto do requisito violado (IDSContext) é injetado no prompt para que o LLM saiba o que é esperado e por que está faltando. Após a correção, o mesmo IDS é reexecutado no elemento para validar se a correção resolve o requisito.
Validação pós-correção: O PostValidator é um gate obrigatório após apply_correction(). Se falhar, a correção é marcada como post_validation: fail na auditoria e a issue volta como "requer revisão". Nunca se exporta um IFC com correções não validadas.
BCF: Ao final do diagnóstico (ou a qualquer momento), as issues podem ser exportadas como .bcf para comunicação com outras ferramentas. O BCF inclui referência ao GUID, descrição da issue, prioridade e status.
Auditoria/proveniência: Cada AuditEntry agora registra: fontes de grounding usadas (bSDD URI, IDS requirement ID), modo de grounding ativo, resultado da pós-validação, prompt hash (para reprodutibilidade). Isso cria uma cadeia de custódia completa: issue → evidência → sugestão → decisão → escrita → validação.
LLM no loop: O LLM opera dentro de um "sandbox semântico" — recebe contexto estruturado (IFC + bSDD + IDS), gera sugestões em JSON, e as sugestões passam por: (1) parsing defensivo, (2) validação contra valores permitidos pelo bSDD (quando disponível), (3) aprovação humana, (4) escrita, (5) pós-validação IDS + schema. O LLM nunca escreve diretamente no IFC.
Diagrama de fluxo
Upload IFC + IDS
    │
    ▼
IFCAnalyzer.analyze()
    │
    ▼
IDSTranslator.apply_rules()  ◄── IDS validado contra XSD
    │
    ▼
IssueStore (issues unificadas)
    │
    ▼
Para cada issue:
    ├── BSDDContextBuilder.build(element_class, issue_type)
    │       └── bSDD API → classes, propriedades, valores válidos
    │
    ├── IDSContext extraído do requisito violado
    │
    ▼
SuggestionGenerator.generate(issue, bsdd_context, ids_context)
    │
    ├── Prompt com grounding (bSDD + IDS) → LLM → JSON
    │
    ▼
Parsing + validação contra vocabulário bSDD
    │
    ▼
UI: apresenta sugestões ao engenheiro
    ├── Aceitar / Editar / Rejeitar / Pular
    │
    ▼
IFCWriter.apply()
    │
    ▼
PostValidator.validate(element)  ◄── GATE OBRIGATÓRIO
    ├── pass → AuditEntry (grounding_sources, post_validation: pass)
    └── fail → issue volta para revisão
    │
    ▼
Exportação
    ├── IFC corrigido (só com correções validadas)
    ├── BCF (.bcf) com issues
    ├── Audit trail (CSV/JSONL) com proveniência completa
    └── Métricas do experimento

7. Papel do LLM no Novo Pipeline
O que o LLM pode sugerir

Nome funcional para IfcSpace (escolhendo entre opções ancoradas no contexto do modelo e, quando disponível, em classificações bSDD).
Valor de propriedade ausente (ex: ThermalTransmittance) com justificativa normativa.
Classificação de sistema construtivo, mapeada para classe bSDD quando possível.
Priorização qualitativa entre sugestões (confiança alta/média/baixa).

O que o LLM não deve decidir sozinho

Nunca escreve no IFC. Sempre gera sugestões que passam por aprovação humana.
Nunca inventa URIs, códigos de classificação ou valores de propriedade que não estejam no contexto fornecido (bSDD ou norma referenciada).
Nunca decide severidade de uma issue — isso vem do IDS/regra.
Nunca avalia se uma correção é suficiente — isso é papel do PostValidator.

Restrições formais que enquadram sua atuação

Vocabulário restrito: quando bSDD retorna propriedades/valores válidos, o prompt instrui o LLM a escolher exclusivamente entre eles. Sugestões fora do vocabulário são descartadas no parsing.
Requisito explícito: o prompt inclui o requisito IDS violado (o que é esperado, qual check falhou). O LLM deve responder ao requisito, não inventar correções fora do escopo.
Formato estruturado: resposta obrigatoriamente em JSON com campos tipados. Parsing defensivo rejeita respostas mal-formadas.
Limite de sugestões: máximo 3 opções + 1 editável. Cada opção deve incluir justificativa e referência normativa quando aplicável.

Como evitar alucinação e deriva semântica

Grounding em bSDD: o LLM recebe as opções válidas como contexto fechado. Se o bSDD diz que IfcWall pode ter FireRating com valores ["REI 30", "REI 60", "REI 90", "REI 120"], o LLM escolhe entre esses.
Grounding em IDS: o LLM sabe exatamente o que está faltando e qual é o critério de aceitação.
Validação pós-geração: antes de apresentar ao usuário, as sugestões passam por validação contra o vocabulário bSDD (quando disponível). Sugestões inconsistentes são filtradas ou marcadas com confiança rebaixada.
Pós-validação no IFC: mesmo que o humano aceite uma sugestão, o PostValidator verifica se a correção resolve o requisito IDS e não quebra o schema.

Aprovação humana
Idêntica ao fluxo atual: o engenheiro vê as sugestões, escolhe uma (ou edita), e só então o sistema escreve. A diferença é que agora cada sugestão exibe sua "proveniência" (de onde veio o grounding: bSDD URI, referência normativa, requisito IDS).