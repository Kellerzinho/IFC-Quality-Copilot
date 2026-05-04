# Estado Atual do Projeto IFC Quality Copilot

Data: 2026-04-17

## Resumo Executivo
O projeto `IFC Quality Copilot` está em estado funcional para análise, sugestão assistida, revisão humana, escrita controlada no IFC, auditoria e pós-validação. O pipeline principal está operacional de ponta a ponta e passou por um endurecimento recente para reduzir variabilidade do LLM, aumentar previsibilidade na escrita e eliminar dependência de campos semânticos inventados.

No estado atual, o sistema:
- analisa modelos IFC e detecta issues de qualidade;
- aplica heurísticas quando possível;
- usa LLM para gerar sugestões quando a heurística não resolve;
- normaliza e valida as sugestões antes da aplicação;
- exige revisão humana para aplicação individual ou em lote;
- escreve no IFC com coerção defensiva;
- registra auditoria completa;
- executa pós-validação estrutural, IDS e semântica.

Resultado de validação atual:
- suíte automatizada completa passando: `717 passed`

## Arquitetura Atual
Os principais módulos ativos do projeto são:

- `src/pipeline.py`
  Orquestra o fluxo diagnóstico -> heurística -> LLM -> validação -> escrita -> auditoria -> exportação.

- `src/ifc_analyzer/*`
  Extrai contexto do IFC e gera `Issue` para problemas como `space_unnamed`, `pset_missing`, `relation_broken` e `system_unclassified`.

- `src/rule_engine/*`
  Resolve parte das issues via heurísticas determinísticas antes de enviar ao LLM.

- `src/suggestion_engine/*`
  Responsável por prompts, chamada ao Ollama, parsing do JSON do LLM, normalização e filtragem das sugestões.

- `src/suggestion_engine/normalization.py`
  Camada nova de tipagem/normalização forte das sugestões antes da aplicação.

- `src/writer/ifc_writer.py`
  Escreve valores no IFC com coerção defensiva por propriedade.

- `src/validation/post_validator.py`
  Executa schema check, revalidação IDS e checks semânticos após a escrita.

- `src/bsdd/*`
  Constrói grounding semântico e resolve dados confiáveis do bSDD.

- `src/ui/*`
  Interface Streamlit para execução do pipeline, revisão das sugestões e exportação dos artefatos.

## Fluxo Atual do Pipeline
1. O modelo IFC é aberto e analisado pelo `IFCAnalyzer`.
2. Issues são geradas com contexto técnico suficiente para heurísticas e LLM.
3. O `RuleEngine` tenta resolver issues determinísticas.
4. Issues não resolvidas seguem para o `SuggestionGenerator`.
5. O `SuggestionGenerator`:
   - monta prompt;
   - chama o Ollama;
   - parseia o JSON;
   - normaliza e tipa os valores;
   - filtra saídas inválidas;
   - valida consistência com bSDD quando houver grounding.
6. A UI apresenta as sugestões ao engenheiro.
7. A aplicação da correção passa novamente por normalização no `QualityPipeline`.
8. O `IFCWriter` escreve no modelo.
9. O `PostValidator` valida schema, IDS e semântica.
10. Auditoria, BCF, métricas e IFC corrigido podem ser exportados.

## Endurecimentos Implementados Recentemente
### 1. Normalização forte de sugestões
Foi introduzido um módulo dedicado para impedir que valores textuais decorados do LLM cheguem brutos à escrita.

Comportamentos atuais:
- `ThermalTransmittance`
  É extraído como `float` mesmo em strings como:
  - `2.50 W/(m².K)`
  - `2,50`
  - `Pset_WallCommon.ThermalTransmittance = 2.50 W/(m².K)`

- `FireRating`
  É canonicalizado para o formato:
  - `REI 60`
  - `REI 90`
  - `REI 120`

  Entradas como `60`, `60min`, `1h`, `2h`, `REI60` são convertidas.
  Entradas semanticamente inadequadas como `A1` ou `0` são rejeitadas.

- `system_unclassified`
  Passou a usar canonicalização textual para reduzir duplicidade semântica em sistemas construtivos, especialmente em lajes.

### 2. Política de aceitação de saída do LLM
O sistema agora descarta opções inválidas e mantém apenas as válidas.

Se nenhuma opção sobreviver à normalização:
- a sugestão não é aplicada;
- o `SuggestionSet` volta vazio;
- a issue fica para revisão manual.

### 3. Remoção da confiança em `bsdd_uri` inventado pelo LLM
O LLM não é mais tratado como fonte confiável para URI.

Comportamento atual:
- `bsdd_uri` só é aceito quando compatível com contexto confiável;
- URIs fora de hosts oficiais do bSDD/buildingSMART são descartadas;
- quando não há resolução segura, o campo fica `None`.

### 4. Escrita defensiva no IFC
Mesmo após a validação da sugestão, o writer passou a aplicar coerção defensiva:
- `ThermalTransmittance` deve virar float positivo;
- `FireRating` deve virar `REI n`.

Isso protege tanto:
- aplicação normal;
- aceite em lote;
- valor editado manualmente pelo usuário.

### 5. Pós-validação semântica
Além da validação estrutural e IDS, o pipeline agora valida:
- `ThermalTransmittance` deve ser numérico positivo;
- `FireRating` deve seguir `REI n`.

## Estado Atual da UI
A UI Streamlit segue funcional para:
- upload e contexto do IFC;
- diagnóstico;
- geração progressiva de sugestões;
- revisão por card;
- aceite em lote;
- dashboard;
- exportação.

Atualização recente:
- remoção do uso depreciado de `use_container_width`;
- substituição pela API nova com `width="stretch"`.

## Estado Atual do Cliente Ollama
O cliente Ollama está funcional e agora mais robusto para chamadas longas.

Comportamento atual:
- timeout de geração configurável;
- múltiplas tentativas configuráveis;
- backoff exponencial entre retries;
- tratamento explícito de timeout, conexão e HTTP error.

## Modelos e Estruturas de Dados
O projeto usa Pydantic como base para:
- `Issue`
- `Suggestion`
- `SuggestionSet`
- `BSDDContext`
- `IDSContext`
- `ValidationResult`
- `AuditEntry`

Observação técnica:
- `src/models.py` ainda contém algumas redefinições históricas de modelos compatíveis entre si.
- Isso não está quebrando o sistema atual, mas é um ponto de manutenção futura para simplificação.

## Cobertura de Testes Atual
O projeto possui suíte extensa cobrindo:
- parser de resposta LLM;
- grounding IDS/bSDD;
- suggestion engine;
- pipeline principal;
- writer IFC;
- post-validator;
- Ollama client;
- analyzer, translator, rule engine, UI indireta e exportação.

Foram adicionados testes específicos para:
- parse de float com unidade/texto extra;
- normalização de `FireRating`;
- rejeição de `bsdd_uri` inválido;
- aplicação de valores mistos em fluxo de correção;
- canonicalização de sistemas repetidos;
- regressão de depreciação do Streamlit.

Estado atual:
- `717 passed in 10.38s`

## Limitações Conhecidas
Apesar do endurecimento recente, ainda existem limites naturais do desenho atual:

- o LLM continua sendo uma fonte probabilística;
- a canonicalização de sistemas construtivos é baseada em vocabulário controlado interno, não em ontologia externa completa;
- parte dos prompts ainda é sensível à qualidade do contexto extraído do IFC;
- a semântica de propriedades além das atualmente tratadas ainda pode exigir novos validadores por domínio;
- o arquivo `src/models.py` merece consolidação futura para reduzir ambiguidade estrutural.

## Situação de Prontidão
No estado atual, o projeto está apto para:
- uso técnico supervisionado;
- demonstração funcional;
- operação assistida com revisão humana obrigatória;
- evolução incremental orientada a casos reais.

Não deve ser tratado ainda como sistema totalmente autônomo sem revisão humana, porque:
- várias decisões continuam dependentes de contexto de engenharia;
- a confiabilidade semântica foi aumentada, mas não elimina necessidade de validação profissional.

## Próximos Passos Recomendados
- consolidar duplicidades históricas em `src/models.py`;
- ampliar validadores semânticos por propriedade IFC crítica;
- expandir canonicalização de sistemas construtivos com vocabulário controlado central;
- adicionar observabilidade mais detalhada sobre taxas de descarte de saída do LLM;
- criar relatório técnico versionado por release com changelog de robustez.
