# M1: catálogo de domínio e curadoria local

A entrega integra o catálogo ao pipeline existente e oferece uma área de trabalho Streamlit. A distribuição pública contém código, schema e testes sintéticos. Não contém um catálogo de pesquisa aprovado, fontes reais novas, transcrições, perfis reais, bancos operacionais ou evidências pessoais. Aprovar este código não aprova conteúdo de catálogo nem alteração de IFC.

## Executar

Instale as dependências de desenvolvimento e o extra de validação com `uv sync --extra e3`. Inicie `uv run streamlit run src/ui/app.py` e abra a página do catálogo. O modo de simulação usa dados inventados em armazenamento temporário próprio. A área operacional vazia permite criar o primeiro catálogo ou importar `candidates.json` produzido pelo staging; importar cria rascunho, nunca release aprovada.

O catálogo separa conceito, definição, unidade/domínio, regra de aplicabilidade, binding IFC, política de evidência, alias e decisão de reconciliação. A UI permite autoria desses registros pela autoridade de comandos existente. Decisões A/B mantêm referências às assertivas/fontes e à revisão; não reescrevem fontes. Não há equivalência automática por igualdade de nome.

## Curadoria e identidade

O ator local `unverified_local` é uma declaração, não autenticação. Aprovação exige conteúdo/revisão/hash exatos; editar invalida a aprovação correspondente. A publicação do catálogo não adota automaticamente uma versão no projeto. A adoção usa plano explícito com hash e nova análise; propostas e aprovações IFC anteriores não são transportadas.

Comandos usam chave de idempotência, ator e payload íntegro. Repetir criação/duplicação de uso com a mesma chave mantém IDs e recibo; payload diferente com a mesma chave é conflito. A UI conserva edições locais no conflito e envia apenas campos efetivamente alterados após recarregar. Toda escrita de IFC continua sujeita ao mecanismo existente de aprovação humana.

`Area_Forma` permanece com portador `property_or_quantity`, tipo nulo, reconciliação pendente e escrita bloqueada. A distribuição de código não decide esse domínio.

## Integração e limites

O pipeline dispõe de identidade de análise, artefatos locais, núcleo IFC/IDS somente leitura, diagnóstico, evidência de catálogo e contratos de operações. Dependências E3 são fixadas; o bundle IDS offline acompanha atribuições, licenças e hashes. O registro de um conceito não instala uma operação executável.

O shell é o Streamlit existente. Não inclui os PRs abertos de plataforma M4 nem inventário M3, autenticação institucional, editor IDS ou API administrativa bSDD. Decisões de conteúdo, termos por fonte, qualidade com referência independente e observação humana de usabilidade continuam pendentes.

## Dados externos e testes

`data/catalogs/schemas/catalog-v1.json` é genérico. `tests/domain_catalog/factories.py`, as fixtures bSDD/avaliação e `workspace_simulation.py` geram exclusivamente exemplos sintéticos. A UI funciona sem fontes de pesquisa.

Os parsers e o perfil de pesquisa aceitam entradas locais explícitas. Transcrição B, rascunho E1, reconciliação/candidatos E4, projeções e arquivos históricos de fonte real não são distribuídos neste PR. A matriz A já existente na base não é alterada nem autoriza distribuir derivados. Nenhum dado ausente é substituído silenciosamente por exemplo inventado.

A [classificação de testes](testes-externos.json) preserva 119 funções de integração externa versionadas com `external_data`, seis funções sintéticas reintegradas e exclui apenas seis funções que transcrevem literais/domínios reais. As demais funções sintéticas dos módulos mistos também permanecem. Sem opt-in, as integrações externas recebem skip nominal antes das fixtures. Para exercê-las, disponibilize em cópia privada as fontes e projeções autorizadas nas posições relativas documentadas pelos importadores e defina `IFCQC_RUN_EXTERNAL_CATALOG_TESTS=1`. Entrada ausente com opt-in é falha explícita; erro de parser/hash nunca vira skip. Dados não acompanham o PR.

A suíte pública tem denominador próprio; passes sintéticos e skips externos são registrados separadamente. As seis verificações de transcrição excluídas permanecem somente na validação privada, sem apagar originais. Os resultados integrados constam no [relatório de validação](validacao-publicacao-m1.md).

Para os testes públicos: `uv run pytest -q -m "not network and not windows_e2e"`. Os testes legados que exigem IFC local ou outro recurso externo mantêm seus requisitos; não são downloads automáticos. Para memória limitada, use o [runner sequencial Windows](evidencias-e5/g3_partition_e5.py) com Python, diretório de evidências e diretório temporário explícitos. Ele conserva a coleta, JUnit, comandos, memória e exit code; incompletude não equivale a passe.

Consulte [operação e recuperação](operacao-e-recuperacao.md) antes de usar armazenamento real.
