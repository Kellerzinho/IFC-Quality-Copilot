# Windows One-Click Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produzir a pasta transportável `IFCQC-Benchmark-Windows-x64` cujo duplo clique instala um ambiente isolado, baixa/verifica Ollama e modelos, executa prédio+casa com reuse-equivalent e entrega um ZIP privado de evidências.

**Architecture:** `install.ps1` faz apenas o bootstrap confiável sem Python: valida payload, baixa uv fixado, instala CPython e sincroniza o lock. Em seguida, `scripts/windows_benchmark.py` orquestra componentes Python testáveis para Ollama, llmfit, inventário, retomada e ZIP; o construtor de release usa allowlist determinística e inclui os IFCs ignorados localmente.

**Tech Stack:** Windows PowerShell 5.1+, cmd.exe, Python 3.12.13 gerenciado por uv 0.12.3, Ollama standalone 0.32.5, llmfit 1.1.8, CIM/WMI, psutil, pytest e zipfile.

## Global Constraints

- Alvo mínimo: Windows 10 22H2 build 19045 ou Windows 11, x64.
- Nenhuma etapa exige administrador, instala driver, altera ExecutionPolicy persistente ou modifica Python/Git/Ollama do sistema.
- Instalação e caches ficam sob `%LOCALAPPDATA%\IFCQualityCopilot`; nenhum script redefine `$HOME`, `$home` ou `$CODEX_HOME`.
- O usuário transporta exatamente os sete arquivos descritos na especificação e inicia `EXECUTAR_BENCHMARK.cmd`.
- Downloads de ferramenta usam URL/versão/SHA-256 fixos, `.partial`, retry e extração segura.
- Modelos ficam em store próprio identificado pelo SHA-256 de `models.lock.json`; tags divergentes abortam.
- Benchmark oficial: uma réplica, `predio` e `casa`, cache desligado e `--reuse-equivalent`.
- ZIP final nunca contém IFC, modelos, executáveis, `.env`, usuário, hostname, IP/MAC, seriais, tokens ou chaves.
- llmfit é auxiliar não impeditivo; incompatibilidade de OS/payload/digest/modelo/espaço é impeditiva.
- As normas ABNT são link-only; nenhum PDF protegido entra no pacote.
- Este plano começa somente depois de `2026-08-08-portable-benchmark-core.md` estar concluído.

---

### Task 1: Construir uma release local determinística

**Files:**

- Create: `windows/release-manifest.template.json`
- Create: `scripts/build_windows_release.py`
- Create: `tests/windows/test_release_builder.py`

**Interfaces:**

- Consumes: raiz do projeto, dois IFCs locais, ground truths congelados, lock Python e lock de modelos.
- Produces: `build_project_zip(root, output) -> ArchiveRecord`, `build_release(root, output_root) -> Path` e pasta com manifesto/payload completo.

- [ ] **Step 1: Escrever testes de allowlist e determinismo**

```python
def test_project_archive_is_deterministic_and_allowlisted(project_fixture, tmp_path):
    first = build_project_zip(project_fixture, tmp_path / "first.zip")
    second = build_project_zip(project_fixture, tmp_path / "second.zip")
    assert first.sha256 == second.sha256
    with zipfile.ZipFile(first.path) as archive:
        names = set(archive.namelist())
    assert {"pyproject.toml", "uv.lock", ".python-version",
            "scripts/run_benchmark.py", "scripts/windows_benchmark.py",
            "src/experiment/results/models.lock.json"} <= names
    assert not any(name.startswith((".git/", "Artigo/", ".venv/")) for name in names)
    assert not any(name.endswith((".env", "BENCHMARK_RUNNING", "BENCHMARK_STOP")) for name in names)
    assert not any("src/experiment/results/20" in name for name in names)
```

O fixture mínimo cria arquivos permitidos e arquivos sentinela proibidos; não usa
o workspace do usuário.

- [ ] **Step 2: Escrever testes de payload e manifesto**

```python
def test_release_contains_exact_public_shape(project_fixture, tmp_path):
    release = build_release(project_fixture, tmp_path / "dist")
    relative = {path.relative_to(release).as_posix() for path in release.rglob("*") if path.is_file()}
    assert relative == {
        "EXECUTAR_BENCHMARK.cmd", "LEIA-ME.txt", "install.ps1",
        "release-manifest.json", "payload/project.zip",
        "payload/datasets/predio_v1.ifc", "payload/datasets/casa_v1.ifc",
    }


def test_manifest_hashes_every_local_payload(project_fixture, tmp_path):
    release = build_release(project_fixture, tmp_path / "dist")
    manifest = json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))
    for record in (manifest["project"], *manifest["datasets"].values()):
        path = release / record["path"]
        assert record["size_bytes"] == path.stat().st_size
        assert record["sha256"] == sha256_file(path)
```

Adicionar testes que rejeitem IFC ausente/hash diferente, GT ausente, árvore suja
nos caminhos allowlisted e arquivo extra no diretório final.

- [ ] **Step 3: Confirmar RED**

Run: `python -m pytest tests/windows/test_release_builder.py -q`

Expected: FAIL por módulos/template inexistentes.

- [ ] **Step 4: Criar template com pins exatos**

```json
{
  "schema_version": 1,
  "platform": "windows-x86_64",
  "minimum_windows_build": 19045,
  "python_version": "3.12.13",
  "tools": {
    "uv": {
      "version": "0.12.3",
      "url": "https://github.com/astral-sh/uv/releases/download/0.12.3/uv-x86_64-pc-windows-msvc.zip",
      "sha256": "b23350c79e8ad0192b8124af13a0f17e8d4e4549524785e1aef389ae5a06990e",
      "size_bytes": 19013455
    },
    "ollama": {
      "version": "0.32.5",
      "url": "https://github.com/ollama/ollama/releases/download/v0.32.5/ollama-windows-amd64.zip",
      "sha256": "7c941ae084569d298062d29f8139163a3187c76dbca0479c70d085e78fd8c7bb",
      "size_bytes": 1457824795
    },
    "ollama_rocm": {
      "version": "0.32.5",
      "url": "https://github.com/ollama/ollama/releases/download/v0.32.5/ollama-windows-amd64-rocm.zip",
      "sha256": "f2284e7008ffd64eadb7a05ac4ca1a0de843d1e8d0c861aa0923ef855ca94615",
      "size_bytes": 245370090
    },
    "llmfit": {
      "version": "1.1.8",
      "url": "https://github.com/AlexsJones/llmfit/releases/download/v1.1.8/llmfit-v1.1.8-x86_64-pc-windows-msvc.zip",
      "sha256": "bf8a509d68bc02f4cafc7040501938a30841eeb8c496eda51ae886a2f43a88e2",
      "size_bytes": 5249067
    }
  }
}
```

- [ ] **Step 5: Implementar ZIP determinístico e allowlist**

```python
PROJECT_PATTERNS = (
    ".python-version", "uv.lock", "pyproject.toml",
    "src/**/*.py", "src/experiment/results/models.lock.json",
    "scripts/run_benchmark.py", "scripts/windows_benchmark.py",
    "windows/collect-hardware.ps1",
    "data/ids_templates/**/*.ids", "data/ids_schema/**",
    "data/cache/bsdd_cache.json",
    "data/evaluation/predio/ground_truth.yaml", "data/evaluation/predio/README.md",
    "data/evaluation/casa/ground_truth.yaml", "data/evaluation/casa/README.md",
    "references/normative/public/**",
)


def _write_deterministic_member(archive: zipfile.ZipFile, relative: str, data: bytes) -> None:
    info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)
```

Ordenar caminhos POSIX, recusar symlink e resolver cada caminho para confirmar
que permanece sob a raiz do projeto. O manifesto acrescenta `release_id` como
`ifcqc-2026-08-08-<commit12>`, `source_commit`, registros do project.zip/IFCs/GTs,
hash do lock e os pins do template. Os IFCs esperados são:

```text
predio A71C8BE30D82760218F5B3F3A1C476B49E3F30E608B0065916B9D5206A1A6DD0
casa   3B84789C7396449F2C8A3D2F4A66468D81E59F8351EBD4B71FAD161FA06112F2
```

- [ ] **Step 6: Rodar testes e lint**

Run:

```powershell
python -m pytest tests/windows/test_release_builder.py -q
python -m ruff check scripts/build_windows_release.py tests/windows/test_release_builder.py
```

Expected: PASS.

- [ ] **Step 7: Commit atômico**

```powershell
git add -- windows/release-manifest.template.json scripts/build_windows_release.py tests/windows/test_release_builder.py
git commit -m "feat: construir release local do benchmark"
```

### Task 2: Criar o bootstrap PowerShell sem administrador

**Files:**

- Create: `windows/EXECUTAR_BENCHMARK.cmd`
- Create: `windows/install.ps1`
- Create: `tests/windows/test_install_contract.py`

**Interfaces:**

- Consumes: pasta da release e `release-manifest.json`.
- Produces: `install.ps1 -PackageRoot <path> [-ValidateOnly] [-PlanOnly]`, ambiente uv/Python sincronizado e chamada ao orquestrador.

- [ ] **Step 1: Escrever testes executáveis de validação e paths**

```python
def _powershell(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(INSTALL_PS1), *args],
        text=True, capture_output=True, check=False, timeout=30,
    )


def test_validate_only_accepts_matching_payload(release_fixture):
    result = _powershell("-PackageRoot", str(release_fixture), "-ValidateOnly")
    assert result.returncode == 0
    assert "PAYLOAD_OK" in result.stdout


def test_validate_only_rejects_tampered_ifc(release_fixture):
    (release_fixture / "payload/datasets/casa_v1.ifc").write_bytes(b"tampered")
    result = _powershell("-PackageRoot", str(release_fixture), "-ValidateOnly")
    assert result.returncode != 0
    assert "SHA-256" in result.stderr


def test_plan_only_handles_spaces_without_writing_outside_app_root(release_fixture):
    result = _powershell("-PackageRoot", str(release_fixture), "-PlanOnly")
    plan = json.loads(result.stdout.splitlines()[-1])
    assert plan["python_version"] == "3.12.13"
    assert "IFCQualityCopilot" in plan["install_root"]
    assert not (release_fixture / ".venv").exists()
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/windows/test_install_contract.py -q`

Expected: FAIL porque cmd/PowerShell não existem.

- [ ] **Step 3: Implementar o entrypoint CMD**

```bat
@echo off
setlocal
chcp 65001 >nul
title IFC Quality Copilot - Benchmark
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -PackageRoot "%~dp0"
set "IFCQC_EXIT=%ERRORLEVEL%"
echo.
if not "%IFCQC_EXIT%"=="0" echo Falha. Consulte o log exibido acima.
pause
exit /b %IFCQC_EXIT%
```

- [ ] **Step 4: Implementar validação e plano PowerShell**

O script usa `Set-StrictMode -Version Latest`, `$ErrorActionPreference='Stop'` e
parâmetros literais. Implementar:

```powershell
param(
  [string]$PackageRoot = $PSScriptRoot,
  [switch]$ValidateOnly,
  [switch]$PlanOnly
)

function Get-Sha256([string]$LiteralPath) {
  (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-Record([string]$Root, $Record) {
  $target = [IO.Path]::GetFullPath((Join-Path $Root $Record.path))
  if (-not $target.StartsWith([IO.Path]::GetFullPath($Root), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Caminho fora do pacote: $target"
  }
  if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Arquivo ausente: $target" }
  if ((Get-Sha256 $target) -ne $Record.sha256.ToLowerInvariant()) { throw "SHA-256 divergente: $target" }
  if ((Get-Item -LiteralPath $target).Length -ne [int64]$Record.size_bytes) { throw "Tamanho divergente: $target" }
}
```

Validar project e datasets. `-PlanOnly` imprime uma linha JSON e não cria pasta,
baixa ou extrai. `-ValidateOnly` valida e sai com `PAYLOAD_OK`.

- [ ] **Step 5: Implementar download do uv e sync fixado**

`Get-VerifiedDownload` usa cache
`%LOCALAPPDATA%\IFCQualityCopilot\downloads\<sha256>`, destino `.partial`, três
tentativas e `Start-BitsTransfer` quando disponível; fallback
`Invoke-WebRequest -UseBasicParsing`. Só move para o destino final após hash.

Extrair uv para `tools\uv\0.12.3`, definir `UV_PYTHON_INSTALL_DIR` para
`runtime\python`, instalar `3.12.13` com `--managed-python`, extrair project.zip
em `releases\<release-id>`, copiar/verificar os IFCs e executar:

```powershell
& $uvExe python install 3.12.13 --managed-python --install-dir $pythonRoot
& $uvExe sync --project $projectRoot --frozen --no-dev --managed-python --python 3.12.13
& $uvExe run --project $projectRoot --frozen --no-dev python `
  (Join-Path $projectRoot 'scripts/windows_benchmark.py') `
  --manifest (Join-Path $PackageRoot 'release-manifest.json') `
  --package-root $PackageRoot --launch-dir (Get-Location).Path
```

`Expand-Archive` só opera depois do hash; antes de substituir uma release
incompleta, resolver os caminhos e mover a pasta app-owned anterior para
`state\recovery\<release-id>` em vez de apagá-la.

- [ ] **Step 6: Rodar testes e análise PowerShell**

Run:

```powershell
python -m pytest tests/windows/test_install_contract.py -q
powershell.exe -NoProfile -Command "$e=$null; [void][Management.Automation.Language.Parser]::ParseFile('windows/install.ps1',[ref]$null,[ref]$e); if($e){$e; exit 1}"
```

Expected: PASS.

- [ ] **Step 7: Commit atômico**

```powershell
git add -- windows/EXECUTAR_BENCHMARK.cmd windows/install.ps1 tests/windows/test_install_contract.py
git commit -m "feat: adicionar bootstrap Windows sem administrador"
```

### Task 3: Gerenciar downloads, Ollama e modelos em Python

**Files:**

- Create: `src/experiment/windows_runtime.py`
- Create: `tests/windows/test_windows_runtime.py`

**Interfaces:**

- Consumes: manifesto, `ModelMatrixLock`, diretórios app-owned e callable de subprocess/HTTP injetável.
- Produces: `DownloadSpec`, `download_verified`, `safe_extract_zip`, `OllamaServer`, `installed_model_digests`, `ensure_model_matrix` e `select_runtime_assets`.

- [ ] **Step 1: Escrever testes de download e extração**

```python
import hashlib


def test_download_reuses_exact_cached_file(tmp_path, fake_http):
    destination = tmp_path / "asset.zip"
    destination.write_bytes(b"correct")
    spec = DownloadSpec(
        url="https://official.invalid/a",
        sha256=hashlib.sha256(b"correct").hexdigest(),
        size_bytes=7,
    )
    assert download_verified(spec, destination, http=fake_http) == destination
    assert fake_http.calls == []


def test_download_resumes_partial_and_verifies_before_replace(tmp_path, range_http):
    destination = tmp_path / "asset.zip"
    partial = destination.with_suffix(".zip.partial")
    partial.write_bytes(b"first-")
    spec = DownloadSpec(
        url="https://official.invalid/a",
        sha256=hashlib.sha256(b"first-second").hexdigest(),
        size_bytes=12,
    )
    download_verified(spec, destination, http=range_http)
    assert range_http.range_header == "bytes=6-"
    assert destination.read_bytes() == b"first-second"
    assert not partial.exists()


def test_safe_extract_rejects_parent_and_absolute_members(tmp_path):
    archive = malicious_zip(tmp_path, ["../escape", "C:/escape"])
    with pytest.raises(RuntimeIntegrityError, match="fora"):
        safe_extract_zip(archive, tmp_path / "target")
```

Adicionar hash errado, resposta sem suporte a Range (reinicia do zero), retry
limitado e overwrite somente dentro do diretório app-owned.

- [ ] **Step 2: Escrever testes de processo/modelos**

```python
def test_exact_models_are_reused_without_pull(lock, fake_ollama):
    fake_ollama.tags = {model.name: model.digest for model in lock.models}
    ensure_model_matrix(lock, fake_ollama)
    assert fake_ollama.pulls == []


def test_missing_model_is_pulled_then_verified(lock, fake_ollama):
    missing = lock.models[0]
    fake_ollama.tags = {model.name: model.digest for model in lock.models[1:]}
    fake_ollama.after_pull[missing.name] = missing.digest
    ensure_model_matrix(lock, fake_ollama)
    assert fake_ollama.pulls == [missing.name]


def test_existing_or_post_pull_digest_drift_is_fatal(lock, fake_ollama):
    fake_ollama.tags = {lock.models[0].name: "0" * 64}
    with pytest.raises(RuntimeIntegrityError, match="digest"):
        ensure_model_matrix(lock, fake_ollama)


def test_ollama_server_terminates_only_owned_process(fake_process, tmp_path):
    with OllamaServer(fake_process.exe, tmp_path / "models", process_factory=fake_process) as server:
        assert server.base_url.startswith("http://127.0.0.1:")
    assert fake_process.terminated_pid == fake_process.started_pid
```

- [ ] **Step 3: Confirmar RED**

Run: `python -m pytest tests/windows/test_windows_runtime.py -q`

Expected: FAIL por módulo ausente.

- [ ] **Step 4: Implementar downloads e pins em profundidade**

```python
class DownloadSpec(BaseModel):
    url: HttpUrl
    sha256: str
    size_bytes: int = Field(gt=0)


PINNED_TOOL_SHA256 = {
    "ollama": "7c941ae084569d298062d29f8139163a3187c76dbca0479c70d085e78fd8c7bb",
    "ollama_rocm": "f2284e7008ffd64eadb7a05ac4ca1a0de843d1e8d0c861aa0923ef855ca94615",
    "llmfit": "bf8a509d68bc02f4cafc7040501938a30841eeb8c496eda51ae886a2f43a88e2",
}
```

`validate_tool_pins(manifest)` exige igualdade com URL, versão, tamanho e hash do
template. `download_verified` faz hash streaming, grava somente `.partial`, usa
Range quando possível, reinicia se receber HTTP 200 para partial, faz três
tentativas com backoff 1/2/4 s e nunca aceita hash/tamanho divergente.

- [ ] **Step 5: Implementar Ollama isolado**

`select_runtime_assets(gpu_names)` retorna base sempre e ROCm apenas se algum nome
contiver `AMD` ou `Radeon`. Extrair base para
`tools/ollama/0.32.5/windows-amd64`; extrair ROCm na mesma raiz somente após ambos
os hashes passarem.

`OllamaServer` escolhe porta loopback livre, inicia com `CREATE_NO_WINDOW`,
`OLLAMA_HOST=127.0.0.1:<porta>` e `OLLAMA_MODELS=<store>/<models-lock-sha>`, espera
`/api/version`, exige `0.32.5` e termina apenas o processo cujo PID guardou.
`installed_model_digests` lê `/api/tags`. `ensure_model_matrix` primeiro aborta
qualquer tag existente divergente; depois puxa ausentes um a um e reconfere o
digest completo imediatamente.

- [ ] **Step 6: Rodar testes e lint**

Run:

```powershell
python -m pytest tests/windows/test_windows_runtime.py tests/experiment/test_model_lock.py -q
python -m ruff check src/experiment/windows_runtime.py tests/windows/test_windows_runtime.py
```

Expected: PASS.

- [ ] **Step 7: Commit atômico**

```powershell
git add -- src/experiment/windows_runtime.py tests/windows/test_windows_runtime.py
git commit -m "feat: preparar Ollama e modelos no Windows"
```

### Task 4: Coletar hardware e recomendações llmfit

**Files:**

- Create: `windows/collect-hardware.ps1`
- Create: `src/experiment/windows_inventory.py`
- Create: `tests/windows/test_windows_inventory.py`
- Create: `tests/windows/fixtures/nvidia-smi.csv`
- Create: `tests/windows/fixtures/dxdiag.xml`
- Create: `tests/windows/fixtures/llmfit-recommend.json`

**Interfaces:**

- Consumes: comandos PowerShell/nvidia-smi/dxdiag/llmfit por runner injetável.
- Produces: `collect_windows_inventory`, `parse_nvidia_smi`, `parse_dxdiag`, `run_llmfit_inventory` e JSONs anônimos.

- [ ] **Step 1: Escrever testes de inventário e privacidade**

```python
def test_inventory_keeps_research_fields_and_drops_identifiers(command_runner):
    inventory = collect_windows_inventory(command_runner)
    assert inventory["os"]["build_number"] == "22631"
    assert inventory["cpu"][0]["logical_processors"] == 16
    assert inventory["memory"]["total_bytes"] > 0
    assert inventory["gpu"][0]["name"]
    serialized = json.dumps(inventory).lower()
    assert "serialnumber" not in serialized
    assert "hostname" not in serialized
    assert "macaddress" not in serialized
    assert "ipaddress" not in serialized


def test_optional_sources_become_unavailable_instead_of_failing(failing_runner):
    inventory = collect_windows_inventory(failing_runner)
    assert inventory["nvidia_smi"]["status"] == "unavailable"
    assert inventory["dxdiag"]["status"] == "unavailable"
```

- [ ] **Step 2: Escrever testes de llmfit**

```python
def test_llmfit_runs_system_two_contexts_and_doctor(fake_llmfit, tmp_path):
    result = run_llmfit_inventory(fake_llmfit.exe, tmp_path, runner=fake_llmfit)
    assert fake_llmfit.commands == [
        ["--json", "system"],
        ["--max-context", "2048", "recommend", "--json", "--limit", "20"],
        ["--max-context", "8192", "recommend", "--json", "--limit", "20"],
        ["doctor"],
    ]
    assert result.status == "ok"


def test_extra_recommendations_exclude_project_models(fake_llmfit, model_lock, tmp_path):
    result = run_llmfit_inventory(fake_llmfit.exe, tmp_path, runner=fake_llmfit,
                                  locked_names={model.name for model in model_lock.models})
    assert not ({row["model"] for row in result.extra_models}
                & {model.name for model in model_lock.models})
```

- [ ] **Step 3: Confirmar RED**

Run: `python -m pytest tests/windows/test_windows_inventory.py -q`

Expected: FAIL por arquivos inexistentes.

- [ ] **Step 4: Implementar coletor PowerShell anônimo**

O script retorna um único JSON com seções `os`, `computer`, `cpu`, `memory`,
`gpu`, `storage`, `bios`, `baseboard`, `display_drivers` e `power`. Selecionar
explicitamente somente:

```powershell
$os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture
$computer = Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,SystemType,TotalPhysicalMemory,HypervisorPresent
$cpu = Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,L2CacheSize,L3CacheSize,VirtualizationFirmwareEnabled
$memory = Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity,Speed,ConfiguredClockSpeed,Manufacturer,PartNumber,FormFactor
$gpu = Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion,DriverDate,VideoProcessor,Status
$disks = Get-CimInstance Win32_DiskDrive | Select-Object Model,Size,InterfaceType,MediaType,FirmwareRevision
$volumes = Get-CimInstance Win32_LogicalDisk | Select-Object DeviceID,DriveType,FileSystem,Size,FreeSpace
$bios = Get-CimInstance Win32_BIOS | Select-Object Manufacturer,SMBIOSBIOSVersion,ReleaseDate
$board = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product,Version
```

Não usar `PSComputerName`, `Name` do computador, UUID, UserName, SerialNumber,
PNPDeviceID, endereços de rede ou chaves de registro pessoais. Capturar plano de
energia com `powercfg /getactivescheme` sem GUID persistente no resultado; manter
apenas o nome legível.

- [ ] **Step 5: Implementar parsers e execução auxiliar**

`nvidia-smi` consulta
`index,name,memory.total,driver_version,compute_cap,pstate,power.limit`; não
consulta UUID/serial. `dxdiag /whql:off /x <temp.xml>` é parseado somente para
versão DirectX e campos de display já permitidos. Toda fonte inclui
`{"status":"ok|unavailable", "error_type":"CommandNotFound|Timeout|ParseError"}`
sem caminho absoluto no erro.

Baixar/extrair llmfit pelo `windows_runtime`, executar os quatro comandos com
timeout de 120 s cada, preservar stdout/stderr redigidos e gerar
`recommend-extra-models.json` via `filter_llmfit_recommendations`. Falha retorna
`status=unavailable` e não levanta para o orquestrador.

- [ ] **Step 6: Rodar testes, parser PowerShell e lint**

Run:

```powershell
python -m pytest tests/windows/test_windows_inventory.py -q
python -m ruff check src/experiment/windows_inventory.py tests/windows/test_windows_inventory.py
powershell.exe -NoProfile -Command "$e=$null; [void][Management.Automation.Language.Parser]::ParseFile('windows/collect-hardware.ps1',[ref]$null,[ref]$e); if($e){$e; exit 1}"
```

Expected: PASS.

- [ ] **Step 7: Commit atômico**

```powershell
git add -- windows/collect-hardware.ps1 src/experiment/windows_inventory.py tests/windows/test_windows_inventory.py tests/windows/fixtures/nvidia-smi.csv tests/windows/fixtures/dxdiag.xml tests/windows/fixtures/llmfit-recommend.json
git commit -m "feat: coletar hardware e modelos adicionais"
```

### Task 5: Orquestrar instalação, retomada, benchmark e ZIP

**Files:**

- Create: `scripts/windows_benchmark.py`
- Create: `tests/windows/test_windows_benchmark.py`

**Interfaces:**

- Consumes: manifesto, runtime/model lock, inventário, evidence bundle e runner por subprocesso injetável.
- Produces: `RunState`, `select_or_create_run`, `run_benchmark_release(args) -> int` e ZIP final/partial.

- [ ] **Step 1: Escrever testes de estado e retomada**

```python
def test_incomplete_matching_run_is_resumed(tmp_path):
    existing = write_state(tmp_path, status="interrupted", release_id="r1",
                           models_lock_sha256="a" * 64)
    selected = select_or_create_run(tmp_path, release_id="r1", models_lock_sha256="a" * 64)
    assert selected.run_id == existing.run_id


def test_completed_or_different_input_creates_new_run(tmp_path):
    existing = write_state(tmp_path, status="complete", release_id="r1",
                           models_lock_sha256="a" * 64)
    selected = select_or_create_run(tmp_path, release_id="r1", models_lock_sha256="a" * 64)
    assert selected.run_id != existing.run_id
```

O state contém `run_id`, `release_id`, `models_lock_sha256`, hashes IFC/GT,
`status`, `started_at_utc`, `updated_at_utc`, `results_root` relativo e último
estágio. Escrita sempre temporária+replace.

- [ ] **Step 2: Escrever teste feliz inteiramente simulado**

```python
def test_happy_path_runs_reuse_and_creates_private_zip(orchestrator_fixture):
    exit_code = run_benchmark_release(orchestrator_fixture.args,
                                      services=orchestrator_fixture.services)
    assert exit_code == 0
    command = orchestrator_fixture.runner.commands.single()
    assert command[-5:] == ["--replicas", "1", "--reuse-equivalent",
                            "--results-root", str(orchestrator_fixture.results_root)]
    assert orchestrator_fixture.zip_path.is_file()
    with zipfile.ZipFile(orchestrator_fixture.zip_path) as archive:
        names = set(archive.namelist())
    assert {"status.json", "privacy-report.json", "manifest.json",
            "hardware/windows.json", "software/ollama-models.json",
            "llmfit/recommend-extra-models.json", "benchmark/runner.log"} <= names
```

- [ ] **Step 3: Escrever testes de falha com evidência**

```python
@pytest.mark.parametrize("failure", ["space", "tool_hash", "model_digest", "runner"])
def test_failures_still_create_failed_bundle_without_destroying_cache(
        orchestrator_fixture, failure):
    orchestrator_fixture.services.fail_at = failure
    assert run_benchmark_release(orchestrator_fixture.args,
                                 services=orchestrator_fixture.services) != 0
    assert orchestrator_fixture.zip_path.is_file()
    status = read_json_from_zip(orchestrator_fixture.zip_path, "status.json")
    assert status["status"] == "failed"
    assert orchestrator_fixture.services.cache_deleted is False


def test_keyboard_interrupt_creates_interrupted_resumable_bundle(orchestrator_fixture):
    orchestrator_fixture.runner.raise_error = KeyboardInterrupt()
    assert run_benchmark_release(orchestrator_fixture.args,
                                 services=orchestrator_fixture.services) == 130
    assert load_state(orchestrator_fixture.state_path).status == "interrupted"
```

- [ ] **Step 4: Confirmar RED**

Run: `python -m pytest tests/windows/test_windows_benchmark.py -q`

Expected: FAIL por script inexistente.

- [ ] **Step 5: Implementar preflight e orçamento de disco**

```python
@dataclass(frozen=True)
class AppPaths:
    app_root: Path
    release_root: Path
    download_cache: Path
    model_store: Path
    state_root: Path
    run_root: Path


class RunState(BaseModel):
    run_id: UUID
    release_id: str
    models_lock_sha256: str
    input_hashes: dict[str, str]
    status: Literal["preparing", "running", "complete", "failed", "interrupted"]
    started_at_utc: datetime
    updated_at_utc: datetime
    results_root: str
    last_stage: str | None = None
```

Validar manifesto/pins outra vez, GTs via `--check`, Windows x64/build, lock uv,
NVIDIA driver >= 452.39 quando houver NVIDIA e disco livre. O orçamento é
`required_free_bytes(models) + soma(runtime assets ausentes) + 2 GiB`; se faltar,
falhar antes de iniciar download, mostrando necessário/disponível em GiB.

- [ ] **Step 6: Implementar pipeline e bloco finally**

Ordem literal:

```python
inventory = collect_windows_inventory(services.commands)
assets = select_runtime_assets(gpu_names(inventory))
download_and_extract_tools(assets)
with OllamaServer(
    ollama_exe=paths.release_root / "tools/ollama/0.32.5/ollama.exe",
    model_store=paths.model_store,
    process_factory=services.process_factory,
    http=services.http,
) as ollama:
    ensure_model_matrix(model_lock, ollama)
    llmfit = run_llmfit_inventory(
        paths.release_root / "tools/llmfit/1.1.8/llmfit.exe",
        evidence_root / "llmfit",
        runner=services.commands,
        locked_names={model.name for model in model_lock.models},
    )
    runner_code = services.run([
        python, str(project / "scripts/run_benchmark.py"), "--replicas", "1",
        "--reuse-equivalent", "--results-root", str(results_root),
    ], env={"OLLAMA_URL": ollama.base_url, "OLLAMA_MODELS": str(model_store)})
```

No `finally`, atualizar status, copiar/organizar resultados, versões, hashes e
logs sob evidence root; chamar `redact_sensitive` para JSON e
`redact_text_files` para logs usando `getpass.getuser()`, `platform.node()`,
`Path.home()` e `%USERPROFILE%`; gravar `privacy-report.json` apenas com
categorias/contagens; chamar `create_evidence_zip`. Não incluir os valores
removidos no relatório.

Nome: `RESULTADO_IFCQC_<UTC-basic>_<run-id>.zip`. Copiar atomicamente para
`launch_dir` se gravável; senão manter em `run_root` e imprimir o caminho. Retorno
0 para complete, 130 para interrupção e 1 para falha. O contexto encerra somente
o Ollama próprio; caches permanecem.

- [ ] **Step 7: Rodar testes e lint**

Run:

```powershell
python -m pytest tests/windows/test_windows_benchmark.py tests/experiment/test_evidence_bundle.py tests/windows/test_windows_runtime.py tests/windows/test_windows_inventory.py -q
python -m ruff check scripts/windows_benchmark.py tests/windows/test_windows_benchmark.py
```

Expected: PASS.

- [ ] **Step 8: Commit atômico**

```powershell
git add -- scripts/windows_benchmark.py tests/windows/test_windows_benchmark.py
git commit -m "feat: orquestrar benchmark Windows em um clique"
```

### Task 6: Documentar, montar e validar a pasta entregue

**Files:**

- Create: `windows/LEIA-ME.txt`
- Create: `tests/windows/test_windows_release_smoke.py`
- Modify: `scripts/build_windows_release.py`

**Interfaces:**

- Consumes: todas as tarefas anteriores e IFCs/GTs locais congelados.
- Produces: pasta final pronta para copiar, smoke sem rede e instruções ao usuário.

- [ ] **Step 1: Escrever teste do guia e shape final**

```python
def test_readme_explains_only_required_action_and_constraints():
    text = (ROOT / "windows/LEIA-ME.txt").read_text(encoding="utf-8")
    assert "EXECUTAR_BENCHMARK.cmd" in text
    assert "Windows 10 22H2" in text
    assert "55 GiB" in text
    assert "internet" in text.lower()
    assert "muitas horas" in text.lower()
    assert "RESULTADO_IFCQC" in text
    assert "não instale" in text.lower()
```

- [ ] **Step 2: Escrever smoke da release extraída**

O teste constrói a release em tmp, roda `install.ps1 -ValidateOnly`, extrai
`project.zip` numa pasta limpa com espaços e afirma:

```python
assert validate_result.returncode == 0
assert (clean / ".python-version").read_text().strip() == "3.12.13"
assert load_model_lock(clean / "src/experiment/results/models.lock.json").schema_version == 2
assert [item["key"] for item in load_runner_module(clean).DATASETS] == ["predio", "casa"]
assert sha256_file(release / "payload/datasets/predio_v1.ifc") == PREDIO_SHA
assert sha256_file(release / "payload/datasets/casa_v1.ifc") == CASA_SHA
```

O smoke não baixa uv/Ollama/modelos e não chama rede.

- [ ] **Step 3: Confirmar RED**

Run: `python -m pytest tests/windows/test_windows_release_smoke.py -q`

Expected: FAIL porque o README e a cópia dele para a release ainda faltam.

- [ ] **Step 4: Escrever o LEIA-ME operacional**

Texto direto em português:

```text
1. Mantenha todos os arquivos desta pasta juntos.
2. Confirme Windows 10 22H2/Windows 11 x64, internet estável e pelo menos 55 GiB livres.
3. Dê duplo clique em EXECUTAR_BENCHMARK.cmd. Não instale Python, Git, Ollama ou modelos manualmente.
4. Não feche a janela. A primeira preparação transfere cerca de 48 GB e o benchmark pode durar muitas horas.
5. Se interromper, execute o mesmo CMD novamente: etapas válidas serão retomadas.
6. Ao final, envie o arquivo RESULTADO_IFCQC_*.zip exibido na tela.
```

Acrescentar solução para proxy HTTPS, driver NVIDIA abaixo de 452.39, espaço
insuficiente e digest movido; sempre apontar o log e proibir editar o lock para
“fazer passar”.

- [ ] **Step 5: Copiar README e executar verificação completa**

Atualizar o builder para copiar `windows/LEIA-ME.txt` para a raiz como
`LEIA-ME.txt` e então rodar:

```powershell
python -m pytest tests/windows -q
python -m pytest -q
python -m ruff check scripts/build_windows_release.py scripts/windows_benchmark.py src/experiment/windows_runtime.py src/experiment/windows_inventory.py tests/windows
git diff --check
python scripts/build_windows_release.py --output dist
```

Expected: testes/lint/check PASS e uma única pasta
`dist/IFCQC-Benchmark-Windows-x64-<release-id>`.

- [ ] **Step 6: Verificar o artefato final sem rede**

Run:

```powershell
$release = Get-ChildItem -LiteralPath dist -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
& (Join-Path $release.FullName 'install.ps1') -PackageRoot $release.FullName -ValidateOnly
& (Join-Path $release.FullName 'install.ps1') -PackageRoot $release.FullName -PlanOnly
```

Expected: `PAYLOAD_OK`; JSON de plano aponta somente `%LOCALAPPDATA%\IFCQualityCopilot`.

- [ ] **Step 7: Commit final do pacote fonte**

```powershell
git add -- windows/LEIA-ME.txt scripts/build_windows_release.py tests/windows/test_windows_release_smoke.py
git commit -m "docs: finalizar pacote Windows do benchmark"
```

O conteúdo de `dist/` permanece ignorado e é o artefato local a transportar; não
forçar seu versionamento nem o dos IFCs.
