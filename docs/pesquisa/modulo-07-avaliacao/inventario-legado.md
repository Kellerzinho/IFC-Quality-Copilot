# M7 — Inventário do legado experimental

**Inspeção documental em 12/10/2026; nenhuma inferência, benchmark ou nova apuração de acurácia.** Este documento acompanha o [plano M7](../../planejamento/modulo-07-avaliacao-cientifica.md) e foi produzido a partir dos arquivos locais, incluindo ZIPs sem extração.

## Universo e método

Foram lidos os 155 `run_*.json` em `src/experiment/results`, os 120 runs nos seis ZIPs RESULTADO únicos de primeiro nível de `dist` e todas as 479.560 linhas não vazias dos 240 sidecars JSONL correspondentes. JSON válido não atesta correção técnica de cada linha. Os 35 runs sem sidecar adjacente permanecem no inventário. Há 158 JSON no diretório: os três demais são lock, identidade de execução e resumo smoke com cinco linhas, excluídos do total de runs.

Os 275 agregados têm hashes de bytes distintos; todos contêm `review_proxy`. Isso comprova presença de artefatos históricos, não 275 replicações independentes, nem estudo humano. 121 metadados locais não informam digest; não inferimos o digest pelo lock atual. Não encontramos v7.8 nesses runs. O arquivo `--help` foi parseado como lista JSON de prompts e nunca executado.

O [JSON de inventário](inventario-experimentos.json) conserva os metadados brutos de cada run, caminhos, hashes, sidecars/contagens, manifestos selecionados, locks e snapshots históricos de modelos instalados. O [CSV](inventario-runs.csv) é uma projeção para revisão. A lista abaixo distingue grupos de pasta/pacote, não declara comparabilidade por ter mesmo nome.

## Grupos em diretório

| Grupo em `src/experiment/results/` | Runs | Versões declaradas |
|---|---:|---|
| 2026-07-02-benchmark | 8 | v3: 1, v4: 7 |
| 2026-07-02-smoke | 1 | v3: 1 |
| 2026-07-02-smoke-matriz | 6 | v3: 6 |
| 2026-07-27-benchmark-top10 | 20 | v4: 20 |
| 2026-07-27-breakdown | 4 | v5: 4 |
| 2026-07-27-corrigido | 2 | v5: 2 |
| 2026-07-27-evidencia | 2 | v5: 2 |
| 2026-07-27-final | 4 | v5: 4 |
| 2026-07-27-final2 | 6 | v5: 6 |
| 2026-07-28-benchmark-limpo | 20 | v5: 20 |
| 2026-08-02-benchmark-v6 | 20 | v6: 20 |
| 2026-08-04-benchmark | 34 | v7.2: 34 |
| 2026-08-12-benchmark-4060 | 20 | v7.6: 20 |
| estrato-a-pos-fix-bsdd | 1 | v5: 1 |
| estrato-b-pos-material | 1 | v5: 1 |
| estrato-v6-pset-gemma2 | 1 | v6: 1 |
| estrato-v7-fogo-termico-gemma2 | 1 | v7: 1 |
| estrato-v71-fogo-termico-gemma2 | 1 | v7.1: 1 |
| estrato-v72-fogo-termico-gemma2 | 1 | v7.2: 1 |
| gate-v72-gemma2-piloto | 2 | v7.2: 2 |

Versões somadas: v3=8, v4=27, v5=40, v6=21, v7=1, v7.1=1, v7.2=37 e v7.6=20. Os 120 sidecars locais somam 180.580 linhas. Uma pasta pode combinar smoke, correção ou subconjunto; não agrupar por data sem conferir identidade completa.

## Pacotes únicos de resultados

| ZIP em `dist/` | Runs / prompt | Hardware declarado | Contexto configurado | bSDD no metadata |
|---|---|---|---:|---|
| [RESULTADO_IFCQC_20260810T183938Z_e2b94a5a-647d-4f79-9b93-62fb4a7ed7c7.zip](../../../dist/RESULTADO_IFCQC_20260810T183938Z_e2b94a5a-647d-4f79-9b93-62fb4a7ed7c7.zip) | 20 / v7.5 | NVIDIA GeForce RTX 4070 | 8192 | ausente |
| [RESULTADO_IFCQC_20260813T164437Z_8b2516e1-0287-49f1-8b49-22a58a099cdb.zip](../../../dist/RESULTADO_IFCQC_20260813T164437Z_8b2516e1-0287-49f1-8b49-22a58a099cdb.zip) | 20 / v7.7 | NVIDIA GeForce RTX 4070 | 4096 | ausente |
| [RESULTADO_IFCQC_20260814T174140Z_1de27843-d185-4456-bc3e-810a6fd52c80.zip](../../../dist/RESULTADO_IFCQC_20260814T174140Z_1de27843-d185-4456-bc3e-810a6fd52c80.zip) | 20 / v7.7 | NVIDIA GeForce RTX 4060 Laptop GPU | 4096 | ausente |
| [RESULTADO_IFCQC_20260817T131446Z_eafb5188-3022-4999-b3f6-a70cbfb35a8a.zip](../../../dist/RESULTADO_IFCQC_20260817T131446Z_eafb5188-3022-4999-b3f6-a70cbfb35a8a.zip) | 20 / v7.7 | NVIDIA GeForce RTX 4070 | 4096 | ausente |
| [RESULTADO_IFCQC_20260818T185722Z_54c4f307-3e34-4be4-9575-acf0678ca94a.zip](../../../dist/RESULTADO_IFCQC_20260818T185722Z_54c4f307-3e34-4be4-9575-acf0678ca94a.zip) | 20 / v7.7 | NVIDIA GeForce RTX 4070 | 4096 | False |
| [RESULTADO_IFCQC_20260818T190222Z_96f42b02-422d-4795-a2c0-ab1e408aea86.zip](../../../dist/RESULTADO_IFCQC_20260818T190222Z_96f42b02-422d-4795-a2c0-ab1e408aea86.zip) | 20 / v7.7 | NVIDIA GeForce RTX 5050 Laptop GPU | 4096 | True |

Os seis ZIPs contêm 120 sidecars e 298.980 linhas. Foram comparados hash e tamanho de todos os 240 membros run/sidecar com `manifest.json`: zero divergências. `status.json` de cada pacote declara 20 estágios validados e completo; esse status é histórico recebido, não reexecução dos gates do benchmark nesta tarefa.

A cópia `dist/IFCQC-Benchmark-Windows-x64-ifcqc-2026-08-13-da0f471b44a9/RESULTADO_IFCQC_20260814T174140Z_1de27843-d185-4456-bc3e-810a6fd52c80.zip` tem SHA-256 `44c3457bc9fc740979e43285150f416bf54aa094dc888a37176b2130d097d913`, igual ao pacote do primeiro nível. Foi inspecionada, mas não somada novamente. A listagem de ZIPs de distribuição e `payload/project.zip` está no JSON; seus membros diretos não contêm runs adicionais. Nenhum ZIP foi extraído ou alterado.

Os pacotes v7.7 registram contexto configurado 4096, saída 768, seed 42, temperatura 0,1, cache desativado e reuso equivalente; isso não informa sozinho cada janela efetiva. No v7.5, 8192 é configuração declarada, enquanto políticas históricas podiam usar contextos menores. Conferir campo por chamada/residência e documentação da condição. Ausência de `grounding_bsdd` nos quatro primeiros ZIPs não vira `True` por default: a interpretação ON vem dos documentos históricos, e essa diferença de origem deve permanecer.

## Modelos com participação comprovada

| Tag histórica | Grupo | Runs totais | Runs sem digest | Quantização nos locks históricos |
|---|---|---:|---:|---|
| `deepseek-r1:14b` | escala | 2 | 0 | Q4_K_M |
| `falcon3:10b` | escala | 2 | 0 | Q4_K_M |
| `falcon3:7b` | principal | 22 | 8 | Q4_K_M |
| `gemma2:9b` | principal | 43 | 29 | Q4_0 |
| `gemma3:12b` | escala | 2 | 0 | Q4_K_M |
| `gemma4:12b` | escala | 2 | 0 | Q4_K_M |
| `gpt-oss:20b` | escala | 2 | 0 | MXFP4 |
| `granite4:tiny-h` | principal | 22 | 8 | Q4_K_M |
| `lfm2.5:8b` | principal | 22 | 8 | Q4_K_M |
| `llama3.1:8b` | principal | 25 | 11 | Q4_K_M |
| `mistral-nemo:12b` | escala | 2 | 0 | Q4_0 |
| `mistral-small:22b` | escala | 2 | 0 | Q4_0 |
| `mistral:7b` | principal | 23 | 11 | Q4_K_M |
| `phi3.5` | smoke inicial | 1 | 1 | não localizada em lock inspecionado |
| `phi4-mini:latest` | principal | 22 | 8 | Q4_K_M |
| `phi4:14b` | escala | 2 | 0 | Q4_K_M |
| `qwen2.5:14b-instruct` | escala | 2 | 0 | Q4_K_M |
| `qwen2.5:7b-instruct` | principal | 31 | 17 | Q4_K_M |
| `qwen3.5:4b` | principal | 20 | 8 | Q4_K_M |
| `qwen3.5:9b` | principal | 23 | 11 | Q4_K_M |
| `qwen3:14b` | escala | 3 | 1 | Q4_K_M |

São dez tags do conjunto principal, dez da escala e um smoke adicional `phi3.5`, totalizando 21. `qwen3:14b` já aparece no smoke e também na escala. `phi3.5` foi localizado em `src/experiment/results/2026-07-02-smoke-matriz/phi3.5/run_0.json`; preservar esse nome literal, sem completá-lo como `:latest` ou inferir digest. Um run smoke demonstra ensaio inicial, não benchmark completo.

O [registro de modelos](registro-modelos.json) lista cada artefato por tag, digests efetivamente observados e atributos de locks com caminho/origem. Quantização em lock é metadado de artefato histórico; não imputar essa quantização a run sem digest correspondente. O lock de escala é recuperável em `dist/IFCQC-Benchmark-Windows-x64-ifcqc-2026-08-16-6cb3c5498138/payload/project.zip!/src/experiment/results/models.lock.json`.

## Instalado, testado e candidato

Cada um dos seis `software/ollama-models.json` contém dez tags instaladas que, nesses snapshots, coincidem com as participantes do pacote. Participação é comprovada por `benchmark/results/.../run_0.json`, separadamente. Não foi consultado o Ollama atual nem feita busca de instalação na máquina. `models.lock`, recomendação llmfit e menção em documentação não bastam para marcar testado. A lista histórica não seleciona modelos do novo M7.

## Continuidade e limites

- [Métricas históricas](../../metricas-avaliacao.md) usam comparador e denominadores próprios; revisão simulada aplica valores pelo GT, não mede pessoas.
- [Emenda GT de 12/08](../../emenda-gt-2026-08-12.md) altera referências/alternativas; comparar com v7.5 exige registrar versão, sem sobrescrever o original.
- [Condição v7.7](../../condicao-v7-7-2026-08-13.md), [escala](../../condicao-escala-4070-2026-08-16.md) e [ablação bSDD](../../condicao-ablacao-bsdd-2026-08-18.md) documentam contextos, populações e hardware; a comparação nova de orçamento exige rubricagem/evidências próprias.
- [Condição v7.8](../../condicao-v7-8-2026-08-19.md) documenta correção e verificações sem GPU; nenhum run v7.8 foi encontrado no universo auditado. As previsões daquele documento não são resultados medidos novos.
- Casa/prédio e variantes mascaradas são expostos; linhas repetidas e reuso de estímulo não viram amostra independente.
- Não foram recomputados rankings, testes estatísticos ou acurácia. Não foram auditados integralmente logs, binários, todas as versões de projeto dentro dos ZIPs ou dados fora das raízes declaradas. Não houve validação de licença atual/model card pela rede.
- As dez categorias e 313 registros da matriz M3 são escopo documental; ainda não há seleção/gabarito revisado novo por caso de orçamento nesta tarefa.

Reusar resposta exige contrato de comparabilidade e evidência suficiente para a nova pergunta. Qualquer rodada com caso, prompt, GT, receita, comparador ou métrica alterada ganha identidade própria. Resultado histórico não fecha M7.
