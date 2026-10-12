# M3 — Baseline observado e pesquisa existente

Registro de 12/10/2026. Integra o [planejamento M3](../../planejamento/modulo-03-contexto-enriquecimento.md) e distingue inspeção estática, resultados já presentes e ensaios futuros. **Não houve inferência nova, suíte funcional ou reprocessamento de métricas nesta consolidação.**

## Checkout e preservação

Branch `feat/semantic-foundation`, HEAD `a76c2d7a85983ef246761a49db9266c411ea90fd`. O manifesto inicial desta consolidação contém 384 arquivos rastreados ou não rastreados não ignorados. Havia alterações locais em `.claude/settings.local.json`, `CLAUDE.md`, `PROJECT_CONTEXT.md` e `docs/arquitetura/fundacao-semantica.md`, além de documentos e materiais não rastreados. Elas não são descartadas, incorporadas ao índice ou atribuídas a esta tarefa. A nota de precedência acrescentada à fundação preserva seu conteúdo anterior.

A [verificação final](verificacao-documental.json) compara esse conjunto e documenta os novos apoios. Arquivos ignorados e toda a máquina não são o universo desse manifesto. M1/M2, consolidação de 09/10, bibliografia dos 29 artigos, código, configurações e artefatos experimentais permanecem protegidos.

## Código existente e limites da leitura estática

O levantamento anterior desta sequência identificou 110 arquivos Python sob `src` (29.835 linhas), 21 sob `scripts` (6.843 linhas) e 111 sob `tests` (30.575 linhas), com 1.346 definições `test_*`. São contagens de arquivos/definições, não número de casos executados ou aprovados. O inventário mais amplo encontrou 794 arquivos ao excluir áreas geradas como ambiente virtual, Git e distribuição; não se confunde com o manifesto Git de preservação.

| Base reaproveitável | Consequência no M3 |
|---|---|
| [Contratos da fundação](../../../src/foundation/contracts.py) | Protocolos dão forma às fronteiras, mas não provam que consumidores as aplicam. `SemanticCatalog` não basta para o builder legado completo |
| [Localidade](../../../src/foundation/locality.py) e [pipeline](../../../src/pipeline.py) | Default local/helper de host literal não prova controle transversal de todos os clientes. A nova exceção bSDD exige filtro de parâmetros públicos e observação dos efeitos de rede |
| [Extrator universal](../../../src/ifc_analyzer/universal_extractor.py) | Cortes de conjuntos/propriedades, achatamento e perda de IDs prejudicam recuperação e proveniência; M3-03/04/11 devem tornar isso mensurável |
| [Leitor de materiais](../../../src/ifc_analyzer/material_reader.py) | Partes/camadas são base real; heurística por nome/ordem não prova papel ou homogeneidade. M3-06 deve conservar perfis, usos, constituintes e associações |
| [Quantidades](../../../src/ifc_analyzer/extractors/quantity_extractor.py) | Declarado, calculado e aproximado precisam de identidades distintas. Cobertura genérica não demonstra leitura de Covering/ReinforcingBar |
| [Pós-validação](../../../src/validation/post_validator.py) | Na leitura estática, `_run_schema_check` pode retornar lista vazia com aviso quando falta IfcOpenShell ou ocorre erro; `_build_status` pode interpretar ausência de erros como aprovação. É risco a proteger por teste de indisponibilidade, não falha reproduzida nesta entrega |
| [Cliente Ollama](../../../src/suggestion_engine/ollama_client.py), [worker](../../../src/suggestion_engine/worker.py), [cache](../../../src/suggestion_engine/suggestion_cache.py) | Reaproveitar transporte/telemetria, mas ensaiar budget antes do envio, execução serial, identidade completa, retries e resultados parciais |
| [Revisão](../../../src/foundation/review.py), [writer](../../../src/writer/ifc_writer.py) e [BCF](../../../src/bcf/exporter.py) | Preservar proposta/decisão/aplicação/resolução; o exportador legado não demonstra esse fluxo por marcar estado não pending como Closed |

Regras legadas de IsExternal/LoadBearing não foram ratificadas como verdade de engenharia. Aritmética térmica fora da LLM é reaproveitável apenas com insumos e unidades verificáveis. Esses pontos originam tarefas/negativos, não correções funcionais nesta etapa.

## Experimentos e resultados brutos já existentes

O projeto **já tem pesquisa de modelos, prompts, contexto e bSDD**, com artefatos brutos. A auditoria anterior desta sequência encontrou 155 arquivos `run_*.json`, 120 JSONL e 180.580 registros analisados sob `src/experiment/results`. Foram também inspecionados seis pacotes RESULTADO únicos no nível superior de `dist`, totalizando 120 runs, 120 JSONL e 298.980 registros. São 275 runs e 479.560 registros de saída nesses dois conjuntos, **não observações estatisticamente independentes nem corpus validado para o novo M3**. Uma cópia repetida de pacote na pasta de release não foi contada novamente.

| Pacote em `dist` (prefixo de data/ID) | Condição identificada | Limite de comparação |
|---|---|---|
| `RESULTADO_IFCQC_20260810T183938Z_e2b94a5a…zip` | 20 runs, v7.5, RTX 4070, contexto 8192 | Condição/GT anteriores; não combinar como réplica v7.7 |
| `RESULTADO_IFCQC_20260813T164437Z_8b2516e1…zip` | 20 runs, v7.7, RTX 4070 | Par de condição unificada, com identidade de instrumento própria |
| `RESULTADO_IFCQC_20260814T174140Z_1de27843…zip` | 20 runs, v7.7, RTX 4060 | Mesmo identificador de instrumento do par; hardware distinto |
| `RESULTADO_IFCQC_20260817T131446Z_eafb5188…zip` | 20 runs, v7.7, escala de modelos, RTX 4070 | Dez modelos maiores; lock próprio não é o lock do par principal |
| `RESULTADO_IFCQC_20260818T185722Z_54c4f307…zip` | 20 runs, v7.7, bSDD OFF, RTX 4070 | Ablação com ressalvas de repetição e empacotamento |
| `RESULTADO_IFCQC_20260818T190222Z_96f42b02…zip` | 20 runs, v7.7, bSDD ON, RTX 5050 | Hardware/condição devem permanecer explícitos |

Os pacotes v7.7 registram Ollama 0.32.5, contexto 4096, saída 768, seed 42, temperatura 0,1, cache desativado e reutilização por equivalência habilitada. Prédio (4.720 itens / 202 classes de estímulo) e casa (263 / 101) dão 4.983 itens / 303 estímulos por modelo; repetição de elementos não aumenta a independência. Nos 120 runs dos pacotes, o indicador de revisão humana é uma **simulação/proxy**, não estudo com participantes reais. Logs de centenas de MB até mais de 1 GB não foram lidos integralmente; examinar manifestos/JSONL não equivale a auditar todos os binários e logs.

O conjunto principal inclui `lfm2.5:8b`, `granite4:tiny-h`, `phi4-mini:latest`, `gemma2:9b`, `qwen2.5:7b-instruct`, `llama3.1:8b`, `falcon3:7b`, `mistral:7b`, `qwen3.5:4b` e `qwen3.5:9b`. O de escala inclui `deepseek-r1:14b`, `falcon3:10b`, `gemma3:12b`, `gemma4:12b`, `gpt-oss:20b`, `mistral-nemo:12b`, `mistral-small:22b`, `phi4:14b`, `qwen2.5:14b-instruct` e `qwen3:14b`. Os tags são localizadores históricos; digest, quantização e parâmetros nos manifestos/locks definem a reprodução. Não representam disponibilidade atual ou recomendação de um vencedor.

Os 155 runs em diretório distribuem versões registradas v3/v4/v5/v6/v7/v7.1/v7.2/v7.6. **Não foi localizada rodada v7.8 nesses 275 runs examinados.** A [condição v7.8](../../condicao-v7-8-2026-08-19.md) documenta correção de empacotamento e inspeção de estímulos, sem nova inferência medida. O default de configuração `qwen3.5:9b` não elege esse modelo para o M3.

## O que a pesquisa anterior sustenta — e o que ainda medir

As condições v5/v6 e as [métricas históricas](../../metricas-avaliacao.md) dão razões para estudar conteúdo do contexto e baseline forte. Há limites de um prédio/IDS e de anotação, mudanças combinadas e análises posteriores; não tratar tudo como intervenção isolada ou gabarito independente do novo estudo.

O [relatório da ablação bSDD](../../resultado-ablacao-bsdd-2026-08-19.md) informa diferença de 2,34 pontos percentuais em classificação e discute composição/truncamento do contexto. Não é prova de que todo dicionário/API reduz qualidade, de que truncamento foi instrumentalmente confirmado em todas as chamadas ou de que a nova recuperação terá o mesmo efeito. Manter hardware, condição, intervalo entre rodadas, uma repetição e alternativas de explicação visíveis.

Para M7, liderado por Nonato com Felipe, o novo estudo deve separar:

1. **Recuperação:** evidência encontrada contra referência de caminhos, portadores, papéis e unidades. Medir cobertura/precisão, omissões, tempo e falhas técnicas.
2. **Interpretação:** regras e regras+LLM sobre o mesmo pacote congelado, incluindo pacote de referência revisado para isolar erro de extração. Não usar valor-alvo como evidência.
3. **Fluxo completo:** coleta, seleção, geração, manual/revisão, escrita em cópia e revalidação, com custos por etapa e estudo humano real separado do proxy histórico.
4. **Roteamento e agrupamento:** comparar propriedade, grupo e elemento durante desenvolvimento, por família/papel/modelo, mantendo uma inferência ativa no baseline. Fixar política em desenvolvimento antes de avaliar o conjunto reservado.

A mudança de receita, fonte, seleção, agrupamento, modelo, comparador ou schema de saída exige identidade de condição. Os 29 artigos curados e a pesquisa de contexto fundamentam decisões e negativos; nenhum substitui esse experimento ou autoriza reutilizar resultados históricos como validação da nova combinação.
