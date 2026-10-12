# Apoios M7 — Avaliação científica

**12/10/2026. Escrita documental; nenhuma avaliação nova executada.**
O [plano completo](../../planejamento/modulo-07-avaliacao-cientifica.md) é a referência de decisões, responsabilidades, arquitetura, tarefas, dependências e aceite.

| Arquivo | Conteúdo e limite |
|---|---|
| [inventario-legado.md](inventario-legado.md) | Síntese da inspeção atual: 275 runs, 21 tags e diferenças de instrumento; não constitui novos resultados |
| [inventario-experimentos.json](inventario-experimentos.json) | Metadados de cada run, hashes, sidecars, locks e snapshots históricos de instalação; caminhos internos a ZIP usam `!/` |
| [inventario-runs.csv](inventario-runs.csv) | Projeção do mesmo inventário por artefato, modelo, versão e configuração |
| [matriz-modelos-propriedades.csv](matriz-modelos-propriedades.csv) | 313 registros da matriz M3 (203 alfanuméricos + 110 auxiliares), colunas R e 21 tags históricas; todas as células `nao_avaliado_M7` |
| [registro-modelos.json](registro-modelos.json) | Proveniência de participação e locks dos modelos históricos; nenhuma seleção M7, adequação atual ou licença nova validada |
| [protocolo-e-registros.md](protocolo-e-registros.md) | Procedimento de congelamento, contratos de coleta e análise futura; não é protocolo empírico já executado |
| [manifesto-preservacao.json](manifesto-preservacao.json) | Referência M6 de 907 arquivos, versões consultadas e limites temporais da prova de preservação |
| [verificacao-documental.json](verificacao-documental.json) | Checagens efetivamente executadas nesta entrega, hashes finais, cobertura e limites |

Na matriz, `real_case_count=nao_inventariado` indica que o corpus real por registro ainda precisa ser selecionado. `new_M7_evaluated_fields=0` significa zero campos avaliados na **nova** pesquisa nesta tarefa; não apaga resultados históricos. Linhas incluem entidade, atributo, material, classificação, propriedades, quantidades e auxiliares da fonte, sem chamar tudo de propriedade inferível. `llm_eligible_planning` é classificação proposta em M3, não capacidade implementada nem decisão científica final.

MODELOS × PROPRIEDADES é apresentada com propriedades/registros nas linhas e modelos nas colunas para revisão. A lista de 21 tags é histórica, não obrigação de executar todas na primeira rodada. Cada rodada futura terá matriz própria por modelo/configuração/condição/hardware, derivada do formato longo definido no plano. Uma célula com evidência insuficiente terá motivo e denominador, não uma nota inventada.

M6 final foi relido e reconciliado; SHA-256 do plano: `3069bd87f64c6e4e80909f3b12e3af1fc4fb347102ee8f35aaa058968639a8c1`. Sem contas no localhost, ator local não verificado, dados por projeto, um slot de inferência por instalação e autenticação antes da rede permanecem os contratos vigentes. A pesquisa preliminar de modelos em paralelo na conversa principal não está incorporada como decisão ou modelo testado.

Não houve escrita em M1–M6, índices, código, experimentos, GTs ou protótipo. Sem benchmark, inferência, download, consulta atual ao Ollama, commit ou automação. Planejamento documental e inventário do legado não significam implementação/conclusão científica.
