# Proveniência desta base (2026-10-08)

Este repositório substitui o versionamento acidental do projeto dentro do Git da
pasta de usuário. O conteúdo e o histórico foram transferidos com conferência
por hash. A pasta original fica preservada intacta, e o plano é renomeá-la
para `ifc-quality-copilot-legado`. Os registros da troca ficam em
`Pesquisa/_migracao-ifcqc-2026-10-08/logs`.

## Origem

- **Pasta:** `Desktop/Projetos FC/Pesquisa/ifc-quality-copilot`, sem `.git`
  próprio.
- **Git de origem:** repositório acidental em `C:\Users\Keller_`, sem remote.
  - Branch `fase0-experimental`, HEAD `cadd884` (2026-08-19).
  - 187 commits tocam o projeto.
- **`master`** (`3d99ce7`) é ancestral de `fase0-experimental`, então não há
  histórico exclusivo a separar.

## Histórico importado

1. `git subtree split --prefix="Desktop/Projetos FC/Pesquisa/ifc-quality-copilot" fase0-experimental`
   deu `3683cb2`: 187 commits, 85 deles com a identidade `construcaobrasil-eng`,
   que pertence a outro projeto.
2. `git filter-branch --env-filter` passou autor e committer para
   `Keller <felipe.keller@icloud.com>`, decisão de 2026-09-30. O resultado foi
   **`818347b`**, idêntico em hash e árvore (`7be417a7…`) ao `main` publicado em
   `github.com/Kellerzinho/IFC-Quality-Copilot`.
3. Tudo isso foi feito num clone temporário. O `.git` da home não foi alterado:
   o índice dele não é gravado desde 2026-09-30.
4. Este repositório não tem remote. O `main` é `818347b`, e o trabalho segue em
   `feat/semantic-foundation`.

## Dados não versionados

- **Cópia:** 863 arquivos, 8.053.780.326 bytes.
  - Inclui os arquivos modificados, os não rastreados e os ignorados.
  - Entre eles: IFCs da raiz e de `data/evaluation`, `data/cache`
    (`suggestion_cache.db` com `-wal`/`-shm`), `src/experiment/results`, `dist`
    e `--help`, que é um JSON de experimento de 12/08.
- **Conferência:** SHA-256 arquivo a arquivo, 863 de 863 idênticos. Os
  manifestos ficam fora do repositório, em
  `_migracao-ifcqc-2026-10-08/manifestos`.
- **Excluídas por serem regeneráveis:** `.venv`, `.mypy_cache`,
  `.pytest_cache`, `.ruff_cache`, `__pycache__`, `*.egg-info`. Recrie com
  `uv sync`.
- **Estado do Git reproduzido:** uma modificação real
  (`.claude/settings.local.json`) e 10 itens não rastreados, que **continuam
  fora dos commits**. Treze arquivos que diferiam só no fim de linha tiveram o
  stat do índice atualizado, sem staging e sem mudar bytes.

## Testes na migração

- **Linha de base no original:** 1665 passed, 2 deselected (`network`,
  `windows_e2e`).
- **Esta base antes das mudanças:** 1665 passed, os mesmos testes, 0 resultados
  diferentes.
- **Defeito preexistente encontrado:** a suíte alterava
  `data/cache/suggestion_cache.db`, fazendo checkpoint do WAL e apagando
  `-wal`/`-shm`.
  - O conteúdo lógico ficou preservado: 101 linhas, mesmo hash.
  - O original foi restaurado byte a byte.
  - A correção está no commit `9f5632f`. Depois dela a suíte deu 1667 passed,
    com `data/cache` intacto.
