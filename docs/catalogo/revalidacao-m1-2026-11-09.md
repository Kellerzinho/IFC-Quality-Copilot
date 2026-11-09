# Revalidação do fechamento técnico M1 — 09/11/2026

Base: `codex/m1-domain-catalog`, commit `6965639bbc3e5e199705ae26d81b6d3928a5d519`.
Este registro complementa a validação de 27/10 com as evidências locais de 28/10 e a verificação de 09/11. Não constitui aprovação de catálogo nem autorização operacional.

**Estado atual:** smoke HTTP aprovado; cinco GT pendentes passaram; dois testes de symlink permanecem skipped por privilégio do Windows. Consolidação por identidade: **3.322 passes e dois skips em 3.324 casos**, não uma nova execução integral. Aceites humanos continuam pendentes. As seções iniciais preservam a sequência histórica; a atualização final registra a superação do bloqueio de memória.

## Evidência histórica recuperada e compatibilidade

A retomada de 28/10 concluiu a reconciliação dos 3.324 nodeids elegíveis: **3.172 passes e 152 skips**, zero ausentes, extras ou duplicatas. Os dois testes `windows_e2e` foram deselecionados por marcador, não classificados como skips. A reconciliação preserva tentativas anteriores e substitui nominalmente cinco erros de setup por suas reexecuções.

Dos 152 skips, 145 são de dados externos, cinco são de ground truth sem IFC no caminho esperado e dois de symlink. A evidência privada compatível cobre os 145 primeiros; por identidade, a consolidação corresponde a **3.317 passes e sete skips**, mais 11 casos exclusivamente privados. Não se somam 156 casos novos ao universo público. A rodada dependeu de pré-requisitos privados e não prova distribuição pública autossuficiente dos datasets.

Cobertura histórica combinada: 85,2076% em `src`, mínimo de 86,3248% entre os módulos core M1/backup, nenhum core abaixo de 80%. Ruff check/format dos 180 arquivos selecionados passaram. Mypy histórico: 101 erros legados em 26 arquivos tanto na integração quanto na base, zero diagnósticos novos. Não é um mypy limpo; a tentativa posterior interrompida não é um resultado novo.

Em 09/11 foram verificados os hashes dos **404 arquivos de código/testes** contra o manifesto da execução final de 27–28/10: zero divergências. Os totais acima são evidência histórica compatível, não uma nova execução integral.

## Primeira verificação em 09/11 (histórico)

Smoke HTTP Streamlit: **PASS** para `/_stcore/health`, `/` e `/catalogo` (HTTP 200). Servidor temporário limitado a loopback, headless, telemetria desativada, encerrado ao final. Python 3.12.13 e Streamlit 1.61.0 no ambiente existente. A rota `/catalogo` retorna o shell Streamlit: este teste não comprova renderização interativa, fluxo de curadoria, acessibilidade ou observação humana de usabilidade.

O ambiente temporário usado em outubro foi parcialmente removido; seu executável não inicia por ausência de `pyvenv.cfg`. O ambiente existente utilizado para o smoke não contém IfcTester. Nenhuma dependência foi instalada e nenhuma configuração persistente foi alterada.

A tentativa de iniciar os sete testes restantes foi interrompida **antes do primeiro teste** pelo guard de memória: 656 MiB livres, abaixo do mínimo de 1.200 MiB. Portanto cinco GT e dois symlink continuam sem nova execução; não foram convertidos em passes. Nenhum processo alheio foi encerrado. Não há novo resultado de suíte completa, cobertura ou mypy.

## Estado antes da nova execução (histórico)

- Engenharia M1 implementada, com a suíte histórica reconciliada e smoke HTTP agora verificado.
- Fechamento sem ressalvas ainda não declarado: retestar os cinco GT e dois symlink quando houver memória suficiente e ambiente compatível; documentar indisponibilidade de symlink caso persista.
- Aprovação humana de conteúdo/fontes, equivalências A/B, portador `Area_Forma`, políticas institucionais e usabilidade permanece separada. Dados reais continuam sem aprovação/publicação automática.
- Nenhuma alteração de código, fonte real, IFC ou catálogo, nem commit, push, PR, merge ou deploy nesta rodada. Apenas documentação local de estado foi atualizada; os registros históricos foram preservados.

Os logs, JUnits e manifestos privados permanecem fora da distribuição. O bloqueio de clone remoto por política de rede não foi contornado: utilizou-se a cópia local preexistente do SHA verificado.


## Atualização após liberação de memória — 09/11/2026

A nova solicitação de verificação encontrou memória suficiente. Os sete casos restantes foram executados sequencialmente na mesma cópia do commit `6965639`, usando o ambiente existente, sem instalação ou mudanças de permissões. O guard de 1.200 MiB foi conferido antes de cada subprocesso; mínimo observado: **4.500 MiB**.

**Resultado novo: cinco passes, dois skips, zero falhas e zero erros.** Os cinco casos de ground truth passaram. Os testes `test_symlinked_data_file_blocks_opening` e `test_symlinked_input_is_refused` foram executados, mas registraram skip porque a criação de links simbólicos não está disponível com o privilégio atual do Windows. Não se alterou a política de segurança para forçar sua execução.

Foram auditados os sete JUnits por identidade exata e outcome. Os 404 arquivos de código/testes permanecem iguais ao manifesto histórico e os IFCs de entrada mantiveram seus hashes após cada caso. Nenhum aplicativo do usuário foi encerrado.

A consolidação histórica por identidade, incluindo a evidência privada compatível e estes cinco passes novos, é agora **3.322 passes e dois skips no universo de 3.324 casos**, além dos 11 casos exclusivamente privados já documentados. Esta consolidação não é uma nova execução integral nem nova medição de cobertura ou mypy. O bloqueio de memória anteriormente registrado foi superado nesta rodada; a indisponibilidade de symlink permanece explícita.

O ambiente existente mostrou-se suficiente para estes sete testes legados, embora não contenha IfcTester para toda a suíte E3. Smoke HTTP e cinco GT pendentes estão resolvidos. Aceites humanos de conteúdo, operação e usabilidade continuam separados e pendentes. Durante a validação não houve commit, push, PR, merge ou publicação. A publicação posterior deste registro na branch de desenvolvimento não aprova dados reais nem autoriza merge.
