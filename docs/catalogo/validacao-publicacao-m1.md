# Validação da integração pública M1

Base integrada: `7b29cb824c659cec13fc2bc7fcb1b525136d8edc` (main com PRs #2, #3 e #4). Não inclui PRs #5/#6 nem correções isoladas reservadas. Esta é uma entrega de software com perfil de pesquisa externo, não publicação de catálogo aceito.

## Estado do candidato

Revisão independente em gpt-6-astra/medium identificou e confirmou correções de edição após revisão/aprovação, conversão de URI file e documentação de provisionamento. Cinco regressões falharam antes da correção; o conjunto focal posterior passou com 24 casos. A fronteira POSIX foi exercitada por emulação da conversão/path; isso não declara execução integral em Linux. A montagem real do schema foi exercitada no Windows.

A primeira verificação da seleção pública teve 978 passes, um skip e uma falha de expectativa de rótulo após generalização do nome sintético; corrigida e revalidada no focal. A seleção foi depois refinada para manter testes dependentes de fontes externas como integrações opt-in. Esses resultados iniciais não certificam a árvore final.

G3 integrada completa, comparação de tipos com a base, cobertura combinada e validação privada externa ainda estão em andamento. Este candidato não deve ser apresentado como aprovado nesses gates antes da atualização deste registro.

As fontes reais e logs pessoais não são distribuídos. Casos externos e motivos estão em `testes-externos.json`; skips padrão não contam como passes. Aprovação de código não aprova conteúdo, identidade, publicação operacional ou alteração IFC.


## Compatibilidade histórica e entradas externas

A primeira G3 integrada foi interrompida após cinco grupos concluídos, por uma correção necessária: generalizar um nome em `HUMAN_GATES` alterava os bytes serializados de uma projeção histórica. Um teste privado reproduziu a diferença; o texto contratual original foi restaurado sem regenerar dados nem afrouxar asserções. Essa rodada parcial não é um gate final.

Após a correção, os 156 casos privados externos passaram em três grupos sequenciais (60 + 60 + 36), sem skips/falhas/erros. Incluem 145 parametrizações das 119 funções externas versionadas e 11 parametrizações das seis funções de transcrição mantidas somente na validação privada. Os dados permaneceram idênticos. Os seis testes sintéticos reintegrados pertencem à suíte pública. Comparação estrutural do código do catálogo, ignorando apenas docstrings e formatação, confirma equivalência com o domínio original preservado; a distribuição não muda a ciência.

Mypy sobre a integração e a main-base: 101 erros legados em 26 arquivos em cada árvore, zero diagnósticos acrescentados/removidos. O resultado não é um mypy limpo. A G3 pública final será uma nova execução integral após o commit da correção, com 3.324 nodeids esperados, 145 skips externos nominais previstos e os recursos legados identificados separadamente.
