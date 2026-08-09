# Aceite manual do pacote Windows em um clique

Data de preparação do checklist: 2026-08-09.

Este documento separa verificações automatizadas do aceite em computadores
limpos. O MVP pode ser montado e validado offline, mas os itens abaixo continuam
**PENDENTE** até serem executados nas duas versões reais do Windows. Não converter
uma linha em PASS sem registrar operador, data, evidência e SHA-256 do ZIP.

## Registro das máquinas

| Alvo | Estado | Data UTC | Operador | Build | CPU | RAM | GPU/VRAM | Driver | ZIP final | SHA-256 |
|---|---|---|---|---|---|---|---|---|---|---|
| Windows 10 22H2 build 19045 x64 | PENDENTE | — | — | — | — | — | — | — | — | — |
| Windows 11 x64 | PENDENTE | — | — | — | — | — | — | — | — | — |

Valores permitidos para estado: `PENDENTE`, `PASS` ou `FALHA`.

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
- PENDENTE: concluir o benchmark real de 20 etapas nas duas versões do Windows.
- PENDENTE: exercer as falhas de rede, interrupção e quarentena acima.
- PENDENTE: anexar os dois ZIPs finais e preencher seus SHA-256.

Essas pendências são testes de aceitação externa; não devem ser relatadas como
PASS com base apenas nos testes unitários ou no caminho offline.
