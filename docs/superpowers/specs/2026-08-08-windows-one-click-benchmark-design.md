# Benchmark Windows em um clique — design

**Data:** 2026-08-08  
**Plataforma-alvo:** Windows 10 22H2 ou mais recente e Windows 11, x64  
**Estado:** aprovado para implementação pelas confirmações do usuário em 2026-08-08

## 1. Objetivo

Entregar uma pasta transportável que possa ser copiada para um computador novo e
iniciada por duplo clique em `EXECUTAR_BENCHMARK.cmd`. A execução prepara um
ambiente isolado, baixa ferramentas e modelos fixados, executa o benchmark do
`predio_v1.ifc` e do `casa_v1.ifc` com `reuse-equivalent` e produz um único ZIP
para análise e uso no artigo.

O fluxo não depende de Python, Git, Ollama ou llmfit previamente instalados e não
exige privilégios de administrador. Instalações existentes não são removidas nem
alteradas. Downloads já presentes no cache próprio e com SHA-256 correto são
reutilizados.

## 2. Alternativas consideradas

### 2.1 Clonar o projeto e instalar no sistema

Rejeitada. O repositório atual não tem remoto configurado, os IFCs estão ignorados
por Git e instalações globais introduziriam diferenças entre máquinas.

### 2.2 Distribuir tudo offline, inclusive os dez modelos

Não será o padrão. Isso criaria um pacote superior a 46 GB, exigiria análise de
redistribuição de cada modelo e ainda duplicaria o armazenamento do usuário. Uma
cópia offline/mirror pode ser acrescentada no futuro como variante separada.

### 2.3 Pacote híbrido local com downloads fixados — selecionada

O código e os dois IFCs viajam na pasta. Ferramentas e modelos são baixados de
fontes oficiais, verificados por SHA-256/digest e guardados em uma instalação
isolada por usuário. É a combinação mais simples para o operador e mais segura
para reprodutibilidade.

## 3. Conteúdo da pasta entregue

```text
IFCQC-Benchmark-Windows-x64/
├── EXECUTAR_BENCHMARK.cmd
├── LEIA-ME.txt
├── install.ps1
├── release-manifest.json
└── payload/
    ├── project.zip
    └── datasets/
        ├── predio_v1.ifc
        └── casa_v1.ifc
```

Esses sete arquivos, organizados na raiz e na pasta `payload`, constituem a unidade de distribuição. O
usuário não precisa acrescentar Python, Git, normas, modelos ou executáveis. O
construtor da release gera `project.zip` por allowlist e exclui `.git`, `.env`,
credenciais, caches, ambientes virtuais, resultados históricos, `Artigo/`,
`BENCHMARK_RUNNING` e `BENCHMARK_STOP`.

Os textos integrais da ABNT não fazem parte do pacote. Os READMEs e
`references/normative/public/sources.yaml` distribuem apenas metadados e links
oficiais.

## 4. Componentes e limites

### 4.1 Núcleo do benchmark

`scripts/run_benchmark.py` passa a ter exatamente os datasets `predio` e `casa`,
cada um com IFC, um `ground_truth.yaml` e contexto próprio:

- prédio: `Residencial multifamiliar`, `ZB 4A`;
- casa: `Residencial unifamiliar`, `ZB 4A`.

O launcher sempre chama o runner com uma réplica e `--reuse-equivalent`. A fila
continua réplica-major e separa resultados por dataset. Um estágio só é tratado
como concluído quando o JSON existente é legível e seus metadados correspondem a
dataset, modelo, réplica, hashes de entrada, digest do modelo e modo de reuso. Um
PID antigo só bloqueia se ainda identificar o processo iniciado pela mesma fila;
um arquivo `STOP` anterior à execução não encerra uma release nova.

Ao relançar uma execução incompleta, o bootstrap reutiliza seu diretório e o
runner continua nos estágios válidos. Depois de uma execução concluída, um novo
duplo clique cria outro identificador de run.

### 4.2 Ambiente Python isolado

O bootstrap baixa `uv 0.12.3` x64, arquivo
`uv-x86_64-pc-windows-msvc.zip`, SHA-256
`b23350c79e8ad0192b8124af13a0f17e8d4e4549524785e1aef389ae5a06990e`.
Ele instala CPython `3.12.13` gerenciado numa pasta da aplicação e executa
`uv sync --frozen --no-dev --managed-python` contra um `uv.lock` versionado.
`.python-version` fixa a mesma versão. `pyproject.toml` passa a declarar também
as dependências de runtime já usadas pelo benchmark: `pandas`, `PyYAML` e
`psutil`.

O Python e o Git do sistema são ignorados; assim, versões existentes não mudam o
experimento. A release do uv é imutável, assinada e oferece binário x64 com
checksum publicado em sua página oficial:
https://github.com/astral-sh/uv/releases/tag/0.12.3 . O suporte a Python gerenciado
e versões exatas está documentado em
https://docs.astral.sh/uv/concepts/python-versions/ .

### 4.3 Ollama e matriz de modelos

A aplicação usa a distribuição standalone oficial
`ollama-windows-amd64.zip` `v0.32.5`, SHA-256
`7c941ae084569d298062d29f8139163a3187c76dbca0479c70d085e78fd8c7bb`.
Em AMD compatível, acrescenta
`ollama-windows-amd64-rocm.zip`, SHA-256
`f2284e7008ffd64eadb7a05ac4ca1a0de843d1e8d0c861aa0923ef855ca94615`.
O runtime e o armazenamento de modelos ficam em
`%LOCALAPPDATA%\IFCQualityCopilot`, sem alterar um Ollama do sistema. A versão
standalone e os requisitos de Windows estão documentados em
https://docs.ollama.com/windows e a release fixada em
https://github.com/ollama/ollama/releases/tag/v0.32.5 .

`models.lock.json` recebe schema v2 com versão/plataforma do runtime, digest
completo de 64 caracteres e `size_bytes` para cada um dos dez modelos. Antes de
baixar, o bootstrap soma os modelos ausentes e exige espaço livre correspondente
mais o maior download parcial e uma reserva de `max(10%, 4 GiB)`. Com todos
ausentes, a mensagem recomenda pelo menos 55 GiB livres.

Um modelo com digest exato é pulado. Um modelo ausente é baixado e conferido pela
API local após o pull. Se uma tag pública passar a apontar para outro digest, a
execução para e grava a divergência; ela não declara reprodutibilidade nem altera
silenciosamente o lock. A recuperação futura do digest exato exige snapshot ou
mirror autorizado, pois o lock detecta drift, mas a API pública não garante pull
por digest.

### 4.4 Perfil de hardware e outros modelos

O bootstrap baixa por padrão `llmfit v1.1.8` x64,
arquivo `llmfit-v1.1.8-x86_64-pc-windows-msvc.zip`, SHA-256
`bf8a509d68bc02f4cafc7040501938a30841eeb8c496eda51ae886a2f43a88e2`.
A fonte é https://github.com/AlexsJones/llmfit/releases/tag/v1.1.8 . Falha do
llmfit não invalida o benchmark; fica registrada como evidência indisponível.

São preservadas as saídas brutas de:

- `llmfit --json system`;
- `llmfit --max-context 2048 recommend --json --limit 20`;
- `llmfit --max-context 8192 recommend --json --limit 20`;
- `llmfit doctor`.

Uma saída derivada remove os dez modelos já presentes no lock e lista somente
candidatos adicionais, mantendo score, preset/contexto e justificativas fornecidas
pelo llmfit. Ela é uma recomendação de capacidade, não uma validação de qualidade
nem autorização para baixar automaticamente modelos extras.

### 4.5 Coleta de evidências e privacidade

O ZIP final contém, quando disponível:

```text
README.txt
status.json
manifest.json
privacy-report.json
hardware/
  windows.json
  cpu.json
  memory.json
  gpu.json
  storage.json
  drivers.json
  power.json
software/
  versions.json
  python-lock.txt
  ollama-models.json
  input-hashes.json
llmfit/
  system.json
  recommend-2048.json
  recommend-8192.json
  recommend-extra-models.json
  doctor.txt
benchmark/
  runner.log
  results/...
```

As coletas usam CIM/PowerShell, `Get-ComputerInfo`, `nvidia-smi` quando presente,
API do Ollama, Python/psutil e os próprios resultados do runner. Incluem build do
Windows, arquitetura, fabricante/modelo do equipamento, CPU, núcleos/threads,
RAM total e módulos sem serial, GPUs, VRAM reportada por cada fonte, drivers,
DirectX quando disponível, volumes e espaço, plano de energia, versões de
ferramentas, lock Python, hashes de todas as entradas, tempos, métricas e
resultados por issue.

Por padrão, a coleta exclui e verifica a ausência de nome de usuário, hostname,
IP, MAC, seriais de BIOS/disco/memória, chaves Ollama, tokens e conteúdo de `.env`.
`privacy-report.json` lista os campos removidos e o scanner aplicado. O manifesto
final registra caminho relativo, tamanho e SHA-256 de cada arquivo no ZIP.

O ZIP é copiado para a pasta onde `EXECUTAR_BENCHMARK.cmd` foi iniciado, com nome
`RESULTADO_IFCQC_<UTC>_<run-id>.zip`. Se essa pasta não for gravável, ele permanece
no diretório de resultados e o console exibe o caminho absoluto.

## 5. Fluxo do duplo clique

1. `EXECUTAR_BENCHMARK.cmd` abre PowerShell em modo de processo, sem alterar a
   política de execução do usuário.
2. O preflight valida Windows x64/versão, rede, integridade de
   `release-manifest.json`, IFCs, ground truths e espaço livre.
3. O projeto é instalado em
   `%LOCALAPPDATA%\IFCQualityCopilot\releases\<release-id>`.
4. Downloads usam arquivo `.partial`, tentativas com backoff, hash antes da
   extração e cache por URL+SHA. Uma nova execução retoma ou refaz somente o item
   inválido.
5. O ambiente Python é sincronizado pelo lock e o Ollama standalone sobe apenas
   em `127.0.0.1`, com diretórios e porta controlados pela release.
6. Os dez modelos são verificados/baixados; depois são coletados hardware,
   software e llmfit pré-benchmark.
7. O runner executa prédio e casa com `--reuse-equivalent` e registra progresso
   no console e em log UTF-8.
8. Um bloco `finally` coleta o estado final e produz o ZIP mesmo em falha ou
   interrupção, marcado como `complete`, `failed` ou `interrupted`.
9. O processo próprio do Ollama é encerrado; modelos, ferramentas e ambiente
   permanecem em cache para retomada.

Drivers de GPU não serão instalados automaticamente: essa ação pode exigir
administrador, reinício e escolhas específicas de fabricante. O preflight coleta
e relata driver incompatível com instruções oficiais, sem modificar o sistema.

## 6. Erros e mensagens ao usuário

Cada falha mostra em português: etapa, motivo, ação sugerida, caminho do log e
estado de retomada. A execução falha antes do benchmark em OS/arquitetura
incompatível, payload adulterado, hash de ferramenta inválido, IFC/GT divergente,
espaço insuficiente, Ollama indisponível ou digest de modelo diferente do lock.

Falhas em uma etapa do benchmark ficam no resumo e não apagam estágios válidos.
Falhas de coleta auxiliar, como `nvidia-smi`, DirectX ou llmfit ausente, geram
campos `unavailable` com erro capturado e não falsificam valores.

## 7. Testes e critérios de aceite

- Testes unitários do registro dos dois datasets, passagem do contexto e
  `reuse_equivalent`, retomada validada e sentinelas obsoletos.
- Validação de schema v2 do lock, digest completo, tamanhos e cálculo de espaço.
- Testes de download com arquivo já correto, parcial, hash errado, retry e drift
  de tag, sem rede real.
- Testes do coletor com fixtures NVIDIA/AMD/CPU, ausência de comandos opcionais,
  filtragem de modelos já avaliados e scanner de privacidade.
- Testes do instalador em diretórios temporários para preflight, idempotência,
  paths com espaços, falha preservando evidências e manifesto final.
- Smoke do pacote construído sem Ollama real e smoke opt-in com uma resposta
  local mínima.
- Build por allowlist seguido de extração em pasta limpa; nenhum arquivo fora do
  manifesto pode ser necessário.
- Aceite manual em Windows 10 22H2 x64 e Windows 11 x64: duplo clique a partir de
  pasta com espaços, instalação sem administrador, retomada após interrupção e
  ZIP final abrindo com todos os hashes válidos.

## 8. Limitações explícitas

- A primeira execução exige internet e pode transferir aproximadamente 48 GB,
  além das dependências; duração do benchmark pode ser de muitas horas.
- O instalador mede o hardware que o Windows e os fornecedores expõem; sensores
  de temperatura/energia podem não existir.
- llmfit indica compatibilidade estimada. Modelos extras não entram na matriz do
  artigo e não são baixados automaticamente.
- A zona bioclimática 4A é contexto técnico público para Rio de Janeiro; o ZIP e
  os ground truths não constituem laudo ou declaração formal de conformidade.
- Normas ABNT integrais dependem de licença e permanecem fora da distribuição.
