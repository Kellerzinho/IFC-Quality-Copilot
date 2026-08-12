# Aceite manual do pacote Windows em um clique

Data de preparação do checklist: 2026-08-09. Última atualização: 2026-08-12.

Este documento separa verificações automatizadas do aceite em computadores
limpos. O MVP pode ser montado e validado offline, e os itens abaixo continuam
**PENDENTE** até serem executados nas versões reais do Windows. Não converter
uma linha em PASS sem registrar operador, data, evidência e SHA-256 do ZIP.

A primeira execução externa ocorreu em **2026-08-10**, com o pacote v7.5, numa
máquina de terceiro. Ela resolveu o caminho feliz e revelou quatro defeitos de
instrumentação (§ "Rodada externa"); os ensaios de falha e o Windows 10 seguem
pendentes.

> **Correção de 2026-08-10 — o duplo clique não funcionava em máquina nenhuma.**
> `EXECUTAR_BENCHMARK.cmd` passava `-PackageRoot "%~dp0"`; como `%~dp0` termina em
> barra invertida, a sequência `\"` virava aspa literal e o `install.ps1` abortava
> com "Caracteres inválidos no caminho" antes de qualquer validação — com ou sem
> espaços e acentos no caminho. O aceite manual nunca chegou a rodar, então o
> defeito passou. Agora está coberto por
> `tests/windows/test_install_contract.py::test_cmd_entrega_package_root_utilizavel`,
> que roda o `.cmd` real contra um `install.ps1` de sondagem em três formatos de
> pasta e exige que o `PackageRoot` recebido resolva para o diretório do pacote.
> O teste que existia para o `.cmd` só afirmava `returncode != 0` e por isso
> ficava verde pelo motivo errado; passou a exigir que a falha seja a do payload.

## Registro das máquinas

| Alvo | Estado | Data UTC | Operador | Build | CPU | RAM | GPU/VRAM | Driver | ZIP final | SHA-256 |
|---|---|---|---|---|---|---|---|---|---|---|
| Windows 10 22H2 build 19045 x64 | PENDENTE | — | — | — | — | — | — | — | — | — |
| Windows 11 x64 | PASS | 2026-08-10 | externo (terceiro) | 11 Pro 10.0.26200 | i9-12900 (16C/24T) | 64 GB | RTX 4070 / 12 GB | 32.0.15.9186 | `RESULTADO_IFCQC_20260810T183938Z_e2b94a5a-647d-4f79-9b93-62fb4a7ed7c7.zip` | `e30fb4c5b4d6b91b4521148e65b6406adb950198c2369b793291e576a81b2730` |

Valores permitidos para estado: `PENDENTE`, `PASS` ou `FALHA`.

**Alcance do PASS de 2026-08-10.** Ele cobre o caminho feliz de ponta a ponta —
duplo clique, fila completa, evidência publicada e sanitizada — e nada além
disso. Os ensaios de falha de rede, interrupção, `BENCHMARK_STOP` e quarentena
**não** foram exercidos nessa máquina, nem o download em conta limpa; seguem em
"Pendências conhecidas". O operador é registrado como externo porque a evidência
é anônima por construção: o próprio scanner de privacidade existe para remover a
identidade da máquina e do usuário do ZIP publicado.

## Rodada externa de 2026-08-10 (release `ifcqc-2026-08-10-eb835f2ab43d`)

Pacote v7.5, entregue por canal confiável e executado por terceiro sem
acompanhamento remoto. Resultado da fila, lido do `runner.log` da evidência:

    FILA FINAL: 4.62h, 20 concluídos, 0 retomados, 0 falhas

Os **20 estágios (2 datasets × 10 modelos) saíram válidos**, com par JSON + JSONL
completo em cada um, e o ZIP de evidência foi publicado com o relatório de
privacidade em `sanitized-before-publication` (sem binários crus; caminhos de
usuário substituídos por `[REDACTED]` também dentro do log). Essa rodada é a que
o artigo passa a reportar como **calibração**, não como resultado final —
ver `docs/emenda-gt-2026-08-12.md` §5.

### Defeitos que a rodada revelou — corrigidos e verificados

Declarados em `docs/condicao-v7-6-2026-08-12.md` §8. Todos foram fechados no
código; a verificação em máquina externa é a rodada final do v7.6.

- [x] **`versions.json` publicava constante compilada, não observação.** O ZIP de
  2026-08-10 afirma `"llmfit": "1.1.8"` ao lado de um `llmfit/doctor.txt` que diz
  `status=unavailable error_type=CommandNotFound` — dois artefatos do mesmo
  pacote em contradição direta. Agora o arquivo declara **pino e observado**, e o
  observado vem das sondas.
- [x] **`llmfit.exe` era procurado em caminho plano.** Quando o ZIP upstream
  aninha o binário num subdiretório, a extração "sucede" e a execução falha com
  `CommandNotFound` — foi a causa provável do pacote ter saído sem nenhuma
  evidência útil de llmfit (`system.json` e `recommend-*.json` todos
  `unavailable`). Passa a ser resolvido por busca recursiva, como o instalador já
  fazia com o `uv.exe`.
- [x] **`last_stage` era string fixa.** Publicava um valor constante em vez do
  estágio efetivamente concluído; passa a ser lido do disco.
- [x] **Os 20 estágios traziam o mesmo instante** — o do lançamento da fila.
  Entram `stage_started_utc`, `stage_finished_utc` e `stage_duration_s` por
  estágio.

### O que a rodada não exerceu

Nenhum dos ensaios de falha: houve **0 retomadas e 0 falhas**, então nada de
queda de rede, `Ctrl+C`, `BENCHMARK_STOP` ou quarentena foi provocado. O
comportamento do llmfit também segue sem verificação real, porque ele não chegou
a executar nessa máquina.

## Checklist por máquina

Copie esta seção para cada linha da tabela e anexe os logs/ZIPs mencionados.

- [ ] Pacote recebido por canal confiável, extraído numa pasta de origem com
  espaços e iniciado por uma conta sem administrador.
- [ ] `install.ps1 -ValidateOnly` termina com `PAYLOAD_OK`, sem rede e sem escrita
  persistente fora do diretório temporário do probe.
- [ ] `install.ps1 -PlanOnly` retorna JSON sob
  `%LOCALAPPDATA%\IFCQualityCopilot`, sem baixar nem extrair ferramentas.
- [ ] Primeira execução com cache próprio vazio instala o Python gerenciado,
  Ollama e llmfit sem usar Python/Git/Ollama globais e sem pedir administrador.
- [ ] Queda e reconexão de rede durante `/api/pull` mantém blobs válidos e o
  relançamento retoma/refaz apenas o download incompleto.
- [ ] `Ctrl+C` retorna 130, produz ZIP `interrupted` e o relançamento retoma os
  estágios já válidos.
- [ ] Um `BENCHMARK_STOP` preexistente é ignorado; um novo arquivo criado durante
  a fila retorna 130 e produz ZIP `interrupted`.
- [ ] Após fault injection no segundo move/rollback, nenhum estágio inicia até
  o relançamento registrar **quarentena reconciliada**.
- [ ] Durante essa reconciliação, o **PID/token da execução** já está adquirido;
  JSON e JSONL ficam juntos nos sources ativos ou no mesmo diretório final.
- [ ] Bytes, tamanho e **SHA-256 dos dois membros** depois da reconciliação são
  idênticos aos valores capturados antes da falha.
- [ ] O run só fica `complete` com **20 pares válidos (JSON + JSONL)**: stems
  coincidem; cada JSONL é UTF-8 estrito, não vazio, termina em newline, todas as
  linhas são JSON e a quantidade iguala `issue_counts.total_issues`.
- [ ] O ZIP final abre e tem a árvore documentada; cada membro, exceto o próprio
  manifesto, confere em tamanho e SHA-256, e o scanner de privacidade retorna
  zero achados impeditivos.
- [ ] O ZIP não contém IFC, modelos, executáveis, `.env`, hostname, usuário,
  IP/MAC, seriais, tokens nem chaves.
- [ ] A saída do llmfit distingue os dez modelos oficiais de candidatos extras;
  nenhum candidato extra é baixado automaticamente.
- [ ] O caminho e o SHA-256 do ZIP final foram registrados na tabela acima.

## Smoke opt-in antes do aceite

O smoke de ground truth usa os dois IFCs reais. O smoke do Ollama exige uma
instância loopback e um modelo do lock **já instalado**; ele nunca executa pull.
O opt-in corresponde a `IFCQC_WINDOWS_SMOKE=1`.

```powershell
$env:IFCQC_WINDOWS_SMOKE='1'
$env:IFCQC_SMOKE_OLLAMA_URL='http://127.0.0.1:11434'
$env:IFCQC_SMOKE_MODEL='qwen3.5:4b'
uv run --frozen --group dev python -m pytest tests/windows/test_windows_release_smoke.py -q -m windows_e2e
```

Registrar aqui o resultado, mesmo em falha:

| Data UTC | Máquina | Ground truth | Ollama local | Log/evidência |
|---|---|---|---|---|
| — | — | PENDENTE | PENDENTE | — |

## Pendências conhecidas do MVP

- PENDENTE: executar o download integral das ferramentas e dos dez modelos em
  uma conta limpa, com cache vazio.
- PENDENTE: concluir o benchmark real de 20 etapas em **Windows 10 22H2**
  (o Windows 11 foi coberto em 2026-08-10).
- PENDENTE: exercer as falhas de rede, interrupção e quarentena acima.
- PENDENTE: executar em **AMD/ROCm** e em **CPU-only** — a única máquina externa
  até aqui é NVIDIA.
- PENDENTE: rodar a **rodada final com o pacote v7.6**, release
  `ifcqc-2026-08-12-96a3e7522b46`, que é onde as quatro correções de
  instrumentação acima passam a ser verificáveis em máquina externa.
- PENDENTE: anexar o ZIP final do Windows 10 e preencher seu SHA-256 (o do
  Windows 11 está na tabela).

Essas pendências são testes de aceitação externa; não devem ser relatadas como
PASS com base apenas nos testes unitários ou no caminho offline.
