# Fundação semântica: contratos da reformulação

- **Data:** 2026-10-08
- **Branch:** `feat/semantic-foundation`
- **Código:** `src/foundation/`
- **Testes:** `tests/foundation/`

Esta etapa entrega a estrutura básica: contratos, política de localidade e
modelos de revisão. Nenhum módulo existente foi reescrito. Os contratos seguem
a forma das classes atuais, e os testes conferem essa forma.

## Princípios

1. **Tudo local ou interno ao IME.** Inferência e dados ficam na máquina ou na
   rede interna, e não há fallback para API externa.
   - `src/foundation/locality.py` classifica cada endpoint pelo host literal, sem
     resolver DNS, e recusa o que estiver fora da política com
     `ExternalEndpointError`.
   - Hosts e redes internos só valem se forem declarados.
2. **Humano no circuito.** A `ReviewDecision` é a única porta para escrita no
   IFC.
   - Só `accepted` e `edited` autorizam escrita.
   - O revisor precisa estar identificado.
   - Uma edição exige o valor editado.
3. **Reaproveitar antes de reescrever.** Cada contrato cita a classe atual que
   já tem a forma certa.
4. **Ter forma não é estar aprovado.** Uma classe pode ter a forma do contrato
   e mesmo assim violar a localidade. É o caso do `BSDDClient`, detalhado abaixo.

## Contratos e reaproveitamento

| Área | Contrato | Implementação existente | Situação |
|---|---|---|---|
| Catálogo/bSDD local | `SemanticCatalog` | `BSDDClient` (só a forma) | **Não cumpre a localidade**: consulta `api.bsdd.buildingsmart.org` quando o cache não responde. Falta um snapshot local. |
| IFC | `ModelInspector` | `IFCAnalyzer` | Forma verificada |
| IDS | `RequirementSource` | `IDSFileRequirementSource` → `parse_ids` | Verificado com `data/ids_templates/fire_safety_readiness.ids` |
| Contexto (grounding) | `GroundingContextBuilder` | `BSDDContextBuilder` (forma) | Depende do catálogo local |
| LLM local | `LocalLanguageModel` + `require_local_model` | `OllamaClient` | Cumpre com endpoint local; o padrão é `http://localhost:11434` |
| Revisão visual por elemento | `ElementReviewQueue`, `ElementReviewItem`, `ReviewDecision` | Não há fila por elemento; `ui/components/issue_card.py` revisa por issue | A implementar |
| Exportação/BCF | `IssueExporter` | `BCFExporter` | Forma verificada |
| Governança | `AuditTrail` | `AuditLogger` | Forma verificada |
| Avaliação científica | `EvaluationSuite` | `IssueMetricsEvaluation` → `calculate_metrics` | Forma verificada |

## Lacunas de localidade no código atual (inventário de 2026-10-08)

| Onde | Para onde vai | Natureza |
|---|---|---|
| `src/config.py` (`bsdd_base_url`, `bsdd_api_url`) | `https://api.bsdd.buildingsmart.org` | Chamada do `BSDDClient` em tempo de execução |
| `src/ui/styles.py` | `fonts.googleapis.com` | Recurso carregado pelo navegador |
| `src/ui/app.py` | `cdn.jsdelivr.net` (mermaid) | Recurso carregado pelo navegador |
| `src/experiment/windows_runtime.py` | `github.com` (Ollama v0.32.5, llmfit v1.1.8) | Download na instalação do pacote Windows |

As URIs de identificadores (`identifier.buildingsmart.org` e semelhantes) são
nomes, não chamadas de rede. Nenhuma dessas lacunas foi alterada nesta etapa.

## Próximos passos sugeridos

1. Criar um snapshot local do dicionário bSDD, servido por uma implementação de
   `SemanticCatalog`, e desligar a API pública por padrão.
2. Aplicar `ensure_local_endpoint` onde `OllamaClient` e `BSDDClient` são
   construídos, falhando fechado.
3. Servir localmente as fontes e o mermaid da UI.
4. Implementar `ElementReviewQueue` sobre o `issue_store`, com visualização
   local por elemento.

## Fora do escopo desta etapa

- Reescrever módulos.
- Mudar o prompt. O prompt é instrumento de medição e segue `PROMPT_VERSION`
  (ver `CLAUDE.md`).
