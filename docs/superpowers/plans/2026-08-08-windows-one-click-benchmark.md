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
- A identidade de retomada é o digest canônico de release, `project.zip`, model
  lock, ordem/hashes IFC/GT/IDS, réplica, cache, prompt e reuso; qualquer mudança
  cria outro run em vez de misturar resultados.
- O preflight tem duas fases: a fase offline PowerShell valida plataforma,
  payload e escrita antes de qualquer rede; a fase Python valida ambiente,
  ground truths, locks, drivers e espaço antes de ferramentas/modelos pesados.
- ZIP final nunca contém IFC, modelos, executáveis, `.env`, usuário, hostname, IP/MAC, seriais, tokens ou chaves.
- llmfit é auxiliar não impeditivo; incompatibilidade de OS/payload/digest/modelo/espaço é impeditiva.
- As normas ABNT são link-only; nenhum PDF protegido entra no pacote.
- SHA-256 sem assinatura detecta divergência em relação ao manifesto congelado,
  mas não autentica o publicador; a pasta deve chegar por canal confiável.
- Testes Python desta fase usam `uv run --frozen --group dev`; o instalador de
  produção continua com `uv sync/run --frozen --no-dev`.
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
            "scripts/build_ground_truths.py",
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

    with zipfile.ZipFile(release / manifest["project"]["path"]) as archive:
        model_lock = manifest["inputs"]["models_lock"]
        prompt = manifest["inputs"]["prompt_templates"]
        for record in (model_lock, prompt):
            payload = archive.read(record["project_path"])
            assert record["sha256"] == hashlib.sha256(payload).hexdigest()
        for dataset in manifest["inputs"]["datasets"].values():
            for key in ("ground_truth", "ids"):
                record = dataset[key]
                payload = archive.read(record["project_path"])
                assert record["sha256"] == hashlib.sha256(payload).hexdigest()
```

Adicionar casos negativos completos:

```python
@pytest.mark.parametrize(
    "missing",
    [
        "data/evaluation/predio/predio_v1.ifc",
        "data/evaluation/casa/casa_v1.ifc",
        "data/evaluation/predio/ground_truth.yaml",
        "data/evaluation/casa/ground_truth.yaml",
        "data/ids_templates/residencial_nbr15575.ids",
    ],
)
def test_builder_rejects_missing_required_input(project_fixture, tmp_path, missing):
    (project_fixture / missing).unlink()
    with pytest.raises(ReleaseBuildError, match="ausente"):
        build_release(project_fixture, tmp_path / "dist")


def test_builder_rejects_wrong_ifc_hash_symlink_and_nonempty_destination(
        project_fixture, tmp_path, monkeypatch):
    (project_fixture / "data/evaluation/casa/casa_v1.ifc").write_bytes(b"tampered")
    with pytest.raises(ReleaseBuildError, match="IFC.*SHA-256"):
        build_release(project_fixture, tmp_path / "dist-a")

    restore_valid_casa_ifc(project_fixture)
    link = project_fixture / "src/linked.py"
    link.write_text("x", encoding="utf-8")
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda self: self == link or real_is_symlink(self)
    )
    with pytest.raises(ReleaseBuildError, match="symlink"):
        build_project_zip(project_fixture, tmp_path / "project.zip")

    destination = tmp_path / "dist-b" / expected_release_dir(project_fixture)
    destination.mkdir(parents=True)
    (destination / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ReleaseBuildError, match="não está vazio"):
        build_release(project_fixture, tmp_path / "dist-b")
```

`restore_valid_casa_ifc` copia o byte fixture cujo SHA consta no manifesto de
teste; `expected_release_dir` deriva o mesmo `release_id` determinístico do
builder. Nenhum helper consulta o workspace real.

- [ ] **Step 3: Confirmar RED**

Run: `uv run --frozen --group dev python -m pytest tests/windows/test_release_builder.py -q`

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
    "scripts/build_ground_truths.py",
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
que permanece sob a raiz do projeto. A contenção usa
`os.path.commonpath((str(root.resolve()), str(candidate.resolve()))) == str(root.resolve())`;
um simples `startswith` não é aceito porque confunde `app` com `app-evil`.

O manifesto acrescenta `release_id` como `ifcqc-2026-08-08-<commit12>`,
`source_commit`, registro completo de `project.zip`, registros dos dois IFCs
externos e o objeto `inputs`. Construir os registros internos diretamente dos
bytes, sem valor manual:

```python
def project_input_record(root: Path, project_path: str) -> dict[str, object]:
    source = root / project_path
    return {
        "project_path": project_path,
        "size_bytes": source.stat().st_size,
        "sha256": sha256_file(source),
    }


ids_record = project_input_record(root, "data/ids_templates/residencial_nbr15575.ids")
inputs = {
    "models_lock": project_input_record(
        root, "src/experiment/results/models.lock.json"
    ),
    "prompt_templates": {
        **project_input_record(root, "src/suggestion_engine/prompt_templates.py"),
        "version": "v7.2",
    },
    "datasets": {
        "predio": {
            "ifc": manifest_datasets["predio"],
            "ground_truth": project_input_record(
                root, "data/evaluation/predio/ground_truth.yaml"
            ),
            "ids": dict(ids_record),
        },
        "casa": {
            "ifc": manifest_datasets["casa"],
            "ground_truth": project_input_record(
                root, "data/evaluation/casa/ground_truth.yaml"
            ),
            "ids": dict(ids_record),
        },
    },
}
```

`manifest_datasets` é o mapa de `ArchiveRecord` dos dois IFCs já copiados, cada
registro com `path`, `size_bytes` e `sha256`. Os testes exigem regex
`^[0-9a-f]{64}$` e igualdade com os bytes do ZIP/payload. O builder recusa GT,
IDS, model lock ou prompt ausente e recusa se `PROMPT_VERSION` lido do módulo não
for `v7.2`. Os IFCs esperados são:

```text
predio A71C8BE30D82760218F5B3F3A1C476B49E3F30E608B0065916B9D5206A1A6DD0
casa   3B84789C7396449F2C8A3D2F4A66468D81E59F8351EBD4B71FAD161FA06112F2
```

- [ ] **Step 6: Rodar testes e lint**

Run:

```powershell
uv run --frozen --group dev python -m pytest tests/windows/test_release_builder.py -q
uv run --frozen --group dev python -m ruff check scripts/build_windows_release.py tests/windows/test_release_builder.py
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
- Produces: `install.ps1 -PackageRoot <path> [-ValidateOnly] [-PlanOnly]`,
  `Test-OfflinePreflight`, ambiente uv/Python sincronizado, chamada ao orquestrador
  e bundle mínimo em `finally` quando Python ainda não conseguiu produzir o ZIP.

- [ ] **Step 1: Escrever testes executáveis de validação e paths**

```python
def _powershell(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    child_env = os.environ.copy()
    child_env.update(env or {})
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(INSTALL_PS1), *args],
        text=True, capture_output=True, check=False, timeout=30, env=child_env,
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


def test_plan_only_handles_spaces_without_writing_outside_app_root(
        release_fixture, tmp_path):
    spaced = tmp_path / "Pacote com espaços"
    shutil.copytree(release_fixture, spaced)
    planned_app_root = tmp_path / "App planejado com espaços"
    result = _powershell(
        "-PackageRoot", str(spaced), "-AppRoot", str(planned_app_root), "-PlanOnly"
    )
    plan = json.loads(result.stdout.splitlines()[-1])
    assert plan["python_version"] == "3.12.13"
    assert Path(plan["install_root"]).resolve() == planned_app_root.resolve()
    assert not (spaced / ".venv").exists()
    assert not planned_app_root.exists()


@pytest.mark.parametrize(
    "probe",
    [
        {"windows_build": 19044, "os_architecture": "64-bit", "process_architecture": "AMD64"},
        {"windows_build": 19045, "os_architecture": "32-bit", "process_architecture": "x86"},
    ],
)
def test_platform_failure_happens_before_any_network(release_fixture, tmp_path, probe):
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(json.dumps(probe), encoding="utf-8")
    sentinel = tmp_path / "network-called"
    result = _powershell(
        "-PackageRoot", str(release_fixture), "-TestProbeJson", str(probe_path),
        env={"IFCQC_TESTING": "1", "IFCQC_NETWORK_SENTINEL": str(sentinel)},
    )
    assert result.returncode != 0
    assert not sentinel.exists()


def test_payload_failure_happens_before_network(release_fixture, tmp_path):
    sentinel = tmp_path / "network-called"
    (release_fixture / "payload/project.zip").write_bytes(b"tampered")
    result = _powershell(
        "-PackageRoot", str(release_fixture), "-AppRoot", str(tmp_path / "app"),
        env={"IFCQC_TESTING": "1", "IFCQC_NETWORK_SENTINEL": str(sentinel)},
    )
    assert result.returncode != 0
    assert not sentinel.exists()


def test_write_failure_happens_before_network(release_fixture, tmp_path):
    sentinel = tmp_path / "network-called"
    app_root_is_a_file = tmp_path / "not-a-directory"
    app_root_is_a_file.write_text("x", encoding="utf-8")
    result = _powershell(
        "-PackageRoot", str(release_fixture), "-AppRoot", str(app_root_is_a_file),
        env={"IFCQC_TESTING": "1", "IFCQC_NETWORK_SENTINEL": str(sentinel)},
    )
    assert result.returncode != 0
    assert not sentinel.exists()


@pytest.mark.parametrize(
    ("forced_stage", "expected_code", "expected_status"),
    [("uv_download", 1, "failed"), ("cancel", 130, "interrupted")],
)
def test_bootstrap_finally_creates_minimum_bundle(
        release_fixture, tmp_path, forced_stage, expected_code, expected_status):
    result = _powershell(
        "-PackageRoot", str(release_fixture), "-AppRoot", str(tmp_path / "app"),
        env={"IFCQC_TESTING": "1", "IFCQC_TEST_FAIL_STAGE": forced_stage},
    )
    assert result.returncode == expected_code
    bundle = next(tmp_path.rglob("RESULTADO_IFCQC_*.zip"))
    with zipfile.ZipFile(bundle) as archive:
        assert set(archive.namelist()) == {
            "README.txt", "status.json", "privacy-report.json", "manifest.json"
        }
        assert json.loads(archive.read("status.json"))["status"] == expected_status
```

- [ ] **Step 2: Confirmar RED**

Run: `uv run --frozen --group dev python -m pytest tests/windows/test_install_contract.py -q`

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
parâmetros literais. `-AppRoot` permite escolher outro diretório app-owned;
`-TestProbeJson` só é aceito quando `IFCQC_TESTING=1`, caso contrário falha. Implementar:

```powershell
param(
  [string]$PackageRoot = $PSScriptRoot,
  [string]$AppRoot = (Join-Path $env:LOCALAPPDATA 'IFCQualityCopilot'),
  [switch]$ValidateOnly,
  [switch]$PlanOnly,
  [string]$TestProbeJson = ''
)

function Get-Sha256([string]$LiteralPath) {
  (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-Record([string]$Root, $Record) {
  $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd([char[]]@('\', '/'))
  $relative = [string]$Record.path
  if ([IO.Path]::IsPathRooted($relative) -or $relative.Contains('\') -or
      $relative.Contains(':') -or $relative.Split('/') -contains '..') {
    throw "Caminho de payload inválido: $relative"
  }
  $target = [IO.Path]::GetFullPath((Join-Path $rootFull $relative))
  $boundary = $rootFull + [IO.Path]::DirectorySeparatorChar
  if (-not $target.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Caminho fora do pacote: $target"
  }
  if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Arquivo ausente: $target" }
  if ((Get-Sha256 $target) -ne $Record.sha256.ToLowerInvariant()) { throw "SHA-256 divergente: $target" }
  if ((Get-Item -LiteralPath $target).Length -ne [int64]$Record.size_bytes) { throw "Tamanho divergente: $target" }
}
```

`Test-OfflinePreflight` executa, nesta ordem, sem chamar função de rede:

1. obtém `Win32_OperatingSystem.BuildNumber`, confirma build `>=19045`,
   `Win32_OperatingSystem.OSArchitecture` 64-bit e processo `AMD64`;
2. valida schema/pins literais do manifesto e tamanho/SHA de `project.zip` e dois IFCs;
3. testa escrita no `AppRoot` criando e removendo um arquivo UUID, confirma espaço
   para o bootstrap e registra se `launch_dir` aceita o ZIP ou exigirá fallback.

Para o seam de teste, `Get-VerifiedDownload` cria o caminho indicado por
`IFCQC_NETWORK_SENTINEL` na primeira entrada; assim os testes acima provam que
build, x64, payload adulterado e escrita falham antes da rede. `-PlanOnly` roda a
fase offline, imprime uma linha JSON e não baixa nem extrai. `-ValidateOnly`
valida e sai com `PAYLOAD_OK`. Ainda sob `IFCQC_TESTING=1`, valor
`IFCQC_TEST_FAIL_STAGE=uv_download` lança `WebException` ao entrar no download e
valor `cancel` lança `OperationCanceledException`; fora desse modo essas
variáveis são ignoradas.

Quando `AppRoot` ainda não existe, o probe de `-PlanOnly` cria um diretório UUID
no ancestral existente mais próximo, remove-o no mesmo `finally` e deixa
`AppRoot` ausente; a execução normal cria `AppRoot` somente depois que as três
validações offline passam.

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
& $uvExe --directory $projectRoot sync --frozen --no-dev --managed-python --python 3.12.13
& $uvExe --directory $projectRoot run --frozen --no-dev python `
  (Join-Path $projectRoot 'scripts/windows_benchmark.py') `
  --manifest (Join-Path $PackageRoot 'release-manifest.json') `
  --package-root $PackageRoot --launch-dir (Get-Location).Path `
  --bootstrap-receipt $bootstrapReceipt
```

`Expand-Archive` só opera depois do hash; antes de substituir uma release
incompleta, resolver os caminhos e mover a pasta app-owned anterior para
`state\recovery\<release-id>` em vez de apagá-la.

Envolver `Invoke-Install` em `try/catch/finally`. Registrar
`[Console]::CancelKeyPress` durante a execução e converter cancelamento controlado
em `OperationCanceledException`; esse catch define código 130/status
`interrupted`, enquanto os demais definem 1/`failed`. O Python grava
`$bootstrapReceipt` por temporário+replace somente depois de criar seu ZIP. No
`finally`, se o receipt não apontar para ZIP existente, chamar
`Write-MinimumBundle` com apenas status, código de etapa enumerado, aviso de
parcialidade e relatório de privacidade; não incluir exceção, caminho, usuário,
hostname ou log bruto. O manifesto desse fallback calcula SHA-256 de
`README.txt`, `status.json` e `privacy-report.json`; o ZIP é escrito em `.partial`
e movido atomicamente. Remover o handler no `finally` e sair com o código salvo.

- [ ] **Step 6: Rodar testes e análise PowerShell**

Run:

```powershell
uv run --frozen --group dev python -m pytest tests/windows/test_install_contract.py -q
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
- Produces: `DownloadSpec`, `PullProgress`, `download_verified`,
  `safe_extract_zip`, `pull_model_streaming`, `OllamaServer`,
  `installed_model_digests`, `ensure_model_matrix` e `select_runtime_assets`.

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


@pytest.mark.parametrize(
    "member",
    [
        "../escape", "/absolute", "C:/escape", "C:\\escape",
        "\\\\server\\share\\escape", "//server/share/escape",
        "folder\\backslash.txt", "folder/file.txt:stream", "folder/../escape",
    ],
)
def test_safe_extract_rejects_parent_absolute_unc_drive_backslash_and_ads(tmp_path, member):
    archive = malicious_zip(tmp_path, [member])
    with pytest.raises(RuntimeIntegrityError, match="inseguro|fora"):
        safe_extract_zip(archive, tmp_path / "target")


def test_app_owned_boundary_does_not_accept_prefix_sibling(tmp_path):
    app_root = tmp_path / "app"
    sibling = tmp_path / "app-evil" / "asset.zip"
    sibling.parent.mkdir()
    with pytest.raises(RuntimeIntegrityError, match="app-owned"):
        assert_app_owned(sibling, app_root)
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


def test_pull_streams_ndjson_reports_progress_and_reconnects(tmp_path, reconnecting_http):
    journal = tmp_path / "pull.json"
    progress = []
    reconnecting_http.streams = [
        [b'{"status":"pulling manifest"}\n',
         b'{"status":"downloading","digest":"sha256:abc","total":100,"completed":40}\n',
         ConnectionResetError("drop")],
        [b'{"status":"downloading","digest":"sha256:abc","total":100,"completed":100}\n',
         b'{"status":"success"}\n'],
    ]
    pull_model_streaming(
        "m:test", reconnecting_http, journal,
        on_progress=lambda event: progress.append(event), max_reconnects=3,
    )
    assert reconnecting_http.posts == [
        ("/api/pull", {"model": "m:test", "stream": True}),
        ("/api/pull", {"model": "m:test", "stream": True}),
    ]
    assert [event.completed for event in progress if event.total] == [40, 100]
    assert json.loads(journal.read_text())["status"] == "success"
    assert reconnecting_http.model_store_deleted is False


def test_pull_rejects_bad_ndjson_and_server_error(tmp_path, fake_http):
    fake_http.streams = [[b'not-json\n']]
    with pytest.raises(RuntimeIntegrityError, match="NDJSON"):
        pull_model_streaming("m:test", fake_http, tmp_path / "pull.json")
    fake_http.streams = [[b'{"error":"registry denied"}\n']]
    with pytest.raises(RuntimeIntegrityError, match="registry denied"):
        pull_model_streaming("m:test", fake_http, tmp_path / "pull.json")


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

Run: `uv run --frozen --group dev python -m pytest tests/windows/test_windows_runtime.py -q`

Expected: FAIL por módulo ausente.

- [ ] **Step 4: Implementar downloads e pins em profundidade**

```python
class DownloadSpec(BaseModel):
    url: HttpUrl
    sha256: str
    size_bytes: int = Field(gt=0)


@dataclass(frozen=True)
class PullProgress:
    status: str
    digest: str | None = None
    total: int | None = None
    completed: int | None = None


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

`safe_extract_zip` trata o nome do membro como POSIX não confiável antes de criar
qualquer arquivo: rejeita `\`, nome vazio, raiz `/`, UNC `//`/`\\`, drive de
`ntpath.splitdrive`, qualquer `:`, segmento `.`/`..`, symlink pelo `external_attr`
e destino cujo `os.path.commonpath` não seja exatamente a raiz resolvida. Cada
escrita usa o caminho já validado e recusa sobrescrever fora de diretório
app-owned. `assert_app_owned` aplica o mesmo `commonpath`; prefixo textual não é
contenção.

- [ ] **Step 5: Implementar Ollama isolado**

`select_runtime_assets(gpu_names)` retorna base sempre e ROCm apenas se algum nome
contiver `AMD` ou `Radeon`. Extrair base para
`tools/ollama/0.32.5/windows-amd64`; extrair ROCm na mesma raiz somente após ambos
os hashes passarem.

`OllamaServer` escolhe porta loopback livre, inicia com `CREATE_NO_WINDOW`,
`OLLAMA_HOST=127.0.0.1:<porta>` e `OLLAMA_MODELS=<store>/<models-lock-sha>`, espera
`/api/version`, exige `0.32.5` e termina apenas o processo cujo PID guardou.
`installed_model_digests` lê `/api/tags`. `ensure_model_matrix` primeiro aborta
qualquer tag existente divergente; depois puxa ausentes um a um com
`pull_model_streaming` e reconfere o digest completo imediatamente.

`pull_model_streaming` faz `POST /api/pull` com
`{"model": name, "stream": true}`, consome uma linha NDJSON por vez, rejeita JSON
inválido/campo `error` e transforma `status`, `digest`, `total` e `completed` em
`PullProgress`. A cada evento grava journal por temporário+replace e emite
percentual no console quando `total > 0`. Em queda de conexão, repete o POST com
backoff 1/2/4 s, no máximo três reconexões, sem apagar blobs nem o store; o
Ollama retoma seus blobs endereçados por conteúdo. Somente `status == "success"`
encerra o stream, e ainda assim `/api/tags` precisa retornar o digest do lock.
Se o processo for interrompido, o journal e os blobs ficam para a próxima
execução.

- [ ] **Step 6: Rodar testes e lint**

Run:

```powershell
uv run --frozen --group dev python -m pytest tests/windows/test_windows_runtime.py tests/experiment/test_model_lock.py -q
uv run --frozen --group dev python -m ruff check src/experiment/windows_runtime.py tests/windows/test_windows_runtime.py
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
- Create: `tests/windows/fixtures/llmfit-recommend-v1.1.8.json`

**Interfaces:**

- Consumes: comandos PowerShell/nvidia-smi/dxdiag/llmfit por runner injetável.
- Produces: `collect_windows_inventory`, `parse_nvidia_smi`, `parse_dxdiag`,
  `parse_llmfit_recommendations`, `run_llmfit_inventory` e JSONs anônimos.

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
    assert not ({str(row["name"]) for row in result.extra_models}
                & {model.name for model in model_lock.models})


def test_parser_matches_llmfit_1_1_8_models_name_envelope():
    payload = json.loads((FIXTURES / "llmfit-recommend-v1.1.8.json").read_text())
    rows = parse_llmfit_recommendations(payload)
    assert rows[0]["name"] == "Orion-zhen/Qwen2.5-Coder-7B-Instruct-AWQ"
    assert rows[0]["best_quant"] == "AWQ-4bit"
    assert rows[0]["effective_context_length"] == 2048


@pytest.mark.parametrize("failed_key", ["system", "recommend_2048", "recommend_8192", "doctor"])
def test_each_llmfit_failure_is_independent(fake_llmfit, tmp_path, failed_key):
    fake_llmfit.fail_key = failed_key
    result = run_llmfit_inventory(fake_llmfit.exe, tmp_path, runner=fake_llmfit)
    assert len(fake_llmfit.commands) == 4
    assert result.status == "partial"
    assert result.commands[failed_key].status == "unavailable"
    assert all(
        record.status == "ok" for key, record in result.commands.items() if key != failed_key
    )
    assert {path.name for path in tmp_path.iterdir()} >= {
        "system.json", "recommend-2048.json", "recommend-8192.json", "doctor.txt"
    }
```

O fixture `llmfit-recommend-v1.1.8.json` é uma saída reduzida, mas estruturalmente
literal, capturada do binário fixado e verificado por SHA-256:

```json
{
  "models": [
    {
      "best_quant": "AWQ-4bit",
      "effective_context_length": 2048,
      "estimated_tps": 39.3,
      "fit_label": "Perfect",
      "memory_required_gb": 4.42,
      "name": "Orion-zhen/Qwen2.5-Coder-7B-Instruct-AWQ",
      "ollama_name": null,
      "parameter_count": "7.6B",
      "provider": "orion-zhen",
      "runtime": "vLLM",
      "score": 91.7
    }
  ],
  "system": {
    "backend": "CUDA",
    "cpu_cores": 20,
    "gpu_name": "NVIDIA GeForce RTX 4060 Laptop GPU",
    "gpu_vram_gb": 8.0,
    "total_ram_gb": 15.73
  }
}
```

- [ ] **Step 3: Confirmar RED**

Run: `uv run --frozen --group dev python -m pytest tests/windows/test_windows_inventory.py -q`

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

Baixar/extrair llmfit pelo `windows_runtime` e executar cada um dos quatro comandos
em seu próprio `try/except`, timeout de 120 s. Preservar stdout/stderr redigidos e
gravar o arquivo correspondente mesmo na falha, usando apenas
`{"status":"unavailable","error_type":"CommandNotFound|Timeout|ParseError|ExitCode"}`
para JSON ou a mesma linha para `doctor.txt`. Uma falha não pula os comandos
seguintes. O status agregado é `ok` para quatro sucessos, `partial` para um a três
e `unavailable` para zero; nenhum deles levanta para o orquestrador.

`parse_llmfit_recommendations` exige objeto raiz, `models` como lista e `name`
string não vazia em cada item. Nunca procura uma chave raiz/lista chamada
`recommendations` nem campo `model`. `recommend-extra-models.json` combina as
linhas válidas de 2048 e 8192, adiciona `recommended_context` a cada linha,
deduplica por `(name, ollama_name, recommended_context)` e filtra os dez locks
comparando tanto `name` quanto `ollama_name`.

- [ ] **Step 6: Rodar testes, parser PowerShell e lint**

Run:

```powershell
uv run --frozen --group dev python -m pytest tests/windows/test_windows_inventory.py -q
uv run --frozen --group dev python -m ruff check src/experiment/windows_inventory.py tests/windows/test_windows_inventory.py
powershell.exe -NoProfile -Command "$e=$null; [void][Management.Automation.Language.Parser]::ParseFile('windows/collect-hardware.ps1',[ref]$null,[ref]$e); if($e){$e; exit 1}"
```

Expected: PASS.

- [ ] **Step 7: Commit atômico**

```powershell
git add -- windows/collect-hardware.ps1 src/experiment/windows_inventory.py tests/windows/test_windows_inventory.py tests/windows/fixtures/nvidia-smi.csv tests/windows/fixtures/dxdiag.xml tests/windows/fixtures/llmfit-recommend-v1.1.8.json
git commit -m "feat: coletar hardware e modelos adicionais"
```

### Task 5: Orquestrar instalação, retomada, benchmark e ZIP

**Files:**

- Create: `scripts/windows_benchmark.py`
- Create: `tests/windows/test_windows_benchmark.py`

**Interfaces:**

- Consumes: manifesto, `ExecutionIdentity`, runtime/model lock, inventário,
  evidence bundle e runner por subprocesso injetável.
- Produces: `RunState`, `Phase2Result`, `select_or_create_run`,
  `run_preflight_phase2`, `build_child_env`, `run_benchmark_release(args) -> int`
  e ZIP final/partial com receipt atômico para o bootstrap.

- [ ] **Step 1: Escrever testes de estado e retomada**

```python
def test_incomplete_matching_run_is_resumed(tmp_path):
    identity = execution_identity()
    existing = write_state(tmp_path, status="interrupted", identity=identity)
    selected = select_or_create_run(tmp_path, identity=identity)
    assert selected.run_id == existing.run_id


def test_completed_or_different_input_creates_new_run(tmp_path):
    identity = execution_identity()
    existing = write_state(tmp_path, status="complete", identity=identity)
    selected = select_or_create_run(tmp_path, identity=identity)
    assert selected.run_id != existing.run_id
    changed = replace(identity, prompt_sha256="f" * 64)
    interrupted = write_state(tmp_path, status="interrupted", identity=identity)
    assert select_or_create_run(tmp_path, identity=changed).run_id != interrupted.run_id


def test_tampered_state_identity_is_not_resumed(tmp_path):
    identity = execution_identity()
    state = write_state(tmp_path, status="interrupted", identity=identity)
    raw = json.loads(state.path.read_text(encoding="utf-8"))
    raw["execution_identity"]["release_id"] = "tampered"
    state.path.write_text(json.dumps(raw), encoding="utf-8")
    assert select_or_create_run(tmp_path, identity=identity).run_id != state.run_id


def test_child_environment_is_merged_and_sanitized(tmp_path):
    base = {
        "PATH": r"C:\Windows\System32", "SYSTEMROOT": r"C:\Windows",
        "TEMP": str(tmp_path), "OLLAMA_HOST": "remote:11434",
        "OLLAMA_MODELS": r"D:\other", "OPENAI_API_KEY": "secret",
        "IFCQC_TOKEN": "secret-2", "LANG": "pt_BR.UTF-8",
    }
    merged = build_child_env(
        base,
        ollama_url="http://127.0.0.1:49152",
        model_store=tmp_path / "models",
    )
    assert {key: merged[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "LANG")} == {
        key: base[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "LANG")
    }
    assert merged["OLLAMA_HOST"] == "127.0.0.1:49152"
    assert merged["OLLAMA_URL"] == "http://127.0.0.1:49152"
    assert merged["OLLAMA_MODELS"] == str(tmp_path / "models")
    assert merged["NO_PROXY"] == "127.0.0.1,localhost,::1"
    assert "OPENAI_API_KEY" not in merged and "IFCQC_TOKEN" not in merged
```

O state contém exatamente os campos de `RunState` definidos na Step 5; os hashes,
release e parâmetros experimentais vivem no snapshot de `execution_identity`.
Escrita sempre temporária+replace.

- [ ] **Step 2: Escrever teste feliz inteiramente simulado**

```python
def test_happy_path_runs_reuse_and_creates_private_zip(orchestrator_fixture):
    exit_code = run_benchmark_release(orchestrator_fixture.args,
                                      services=orchestrator_fixture.services)
    assert exit_code == 0
    command = orchestrator_fixture.runner.commands.single()
    assert command[-8:] == [
        "--replicas", "1", "--no-cache", "--reuse-equivalent",
        "--execution-identity", str(orchestrator_fixture.identity_path),
        "--results-root", str(orchestrator_fixture.results_root),
    ]
    assert orchestrator_fixture.zip_path.is_file()
    with zipfile.ZipFile(orchestrator_fixture.zip_path) as archive:
        names = set(archive.namelist())
        fixed = {
            "README.txt", "status.json", "manifest.json", "privacy-report.json",
            "hardware/windows.json", "hardware/cpu.json", "hardware/memory.json",
            "hardware/gpu.json", "hardware/storage.json", "hardware/drivers.json",
            "hardware/power.json", "software/versions.json", "software/python-lock.txt",
            "software/ollama-models.json", "software/input-hashes.json",
            "llmfit/system.json", "llmfit/recommend-2048.json",
            "llmfit/recommend-8192.json", "llmfit/recommend-extra-models.json",
            "llmfit/doctor.txt", "benchmark/runner.log",
        }
        assert fixed <= names
        stage_json = {name for name in names if name.startswith("benchmark/results/")
                      and name.endswith(".json")}
        stage_jsonl = {name for name in names if name.startswith("benchmark/results/")
                       and name.endswith("_issues.jsonl")}
        assert len(stage_json) == 20 and len(stage_jsonl) == 20

        manifest = json.loads(archive.read("manifest.json"))
        assert {row["path"] for row in manifest["files"]} == names - {"manifest.json"}
        for row in manifest["files"]:
            payload = archive.read(row["path"])
            assert row["size_bytes"] == len(payload)
            assert row["sha256"] == hashlib.sha256(payload).hexdigest()
```

O fixture feliz materializa dez modelos, dois datasets, uma réplica e os dois
arquivos exportados por estágio; não cria vinte nomes artificiais sem relação com
a identidade. Manter o `ZipFile` aberto durante leitura do manifesto no teste.

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


def test_runner_zero_without_twenty_valid_stages_is_failed(orchestrator_fixture):
    orchestrator_fixture.runner.returncode = 0
    orchestrator_fixture.runner.omit_stage = ("casa", "qwen3.5:9b", 0)
    assert run_benchmark_release(orchestrator_fixture.args,
                                 services=orchestrator_fixture.services) == 1
    status = read_json_from_zip(orchestrator_fixture.zip_path, "status.json")
    assert status["status"] == "failed"
    assert status["invalid_stages"] == ["casa/qwen3.5:9b/run_0"]


def test_runner_130_from_new_stop_is_interrupted(orchestrator_fixture):
    orchestrator_fixture.runner.returncode = 130
    assert run_benchmark_release(orchestrator_fixture.args,
                                 services=orchestrator_fixture.services) == 130
    assert load_state(orchestrator_fixture.state_path).status == "interrupted"


def test_phase2_failure_precedes_heavy_download(orchestrator_fixture):
    orchestrator_fixture.services.ground_truth_check_code = 1
    assert run_benchmark_release(orchestrator_fixture.args,
                                 services=orchestrator_fixture.services) == 1
    assert orchestrator_fixture.services.trace == [
        "phase2:manifest", "phase2:identity", "phase2:ground-truth-check"
    ]
    assert orchestrator_fixture.services.downloads == []


def test_primary_bundle_failure_falls_back_to_safe_partial(orchestrator_fixture):
    orchestrator_fixture.services.bundle_error = EvidencePrivacyError("scanner")
    assert run_benchmark_release(orchestrator_fixture.args,
                                 services=orchestrator_fixture.services) == 1
    with zipfile.ZipFile(orchestrator_fixture.zip_path) as archive:
        assert set(archive.namelist()) == {
            "README.txt", "status.json", "privacy-report.json", "manifest.json"
        }
        assert json.loads(archive.read("status.json"))["partial"] is True
```

- [ ] **Step 4: Confirmar RED**

Run: `uv run --frozen --group dev python -m pytest tests/windows/test_windows_benchmark.py -q`

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
    execution_identity: dict[str, object]
    execution_identity_sha256: str
    status: Literal["preparing", "running", "complete", "failed", "interrupted"]
    started_at_utc: datetime
    updated_at_utc: datetime
    results_root: str
    last_stage: str | None = None
```

Construir `ExecutionIdentity` somente dos valores validados do manifesto e dos
bytes extraídos; persistir seu dump canônico também em
`execution-identity.json`. `select_or_create_run` retoma apenas status
`preparing|running|failed|interrupted` com digest e objeto completos idênticos;
`complete` ou qualquer divergência cria UUID novo. Ao carregar state, recalcular
o digest canônico do snapshot antes de compará-lo ao campo digest; state
adulterado/corrupto é preservado para diagnóstico, mas nunca retomado.

`run_preflight_phase2` acontece antes de `download_and_extract_tools` e registra
no trace, nesta ordem: manifesto/pins novamente; identidade e hashes reais de
model lock/prompt/IFC/GT/IDS; subprocesso real
`[python, "scripts/build_ground_truths.py", "--check", "--dataset", "all"]` com
`cwd=project`; lock uv congelado; inventário/driver; espaço e porta loopback. GT
check diferente de zero é impeditivo e inclui stdout/stderr somente no log que
será sanitizado. Validar NVIDIA driver >= 452.39 quando houver NVIDIA. O orçamento é
`required_free_bytes(models) + soma(runtime assets ausentes) + 2 GiB`; se faltar,
falhar antes de iniciar download, mostrando necessário/disponível em GiB.

`build_child_env(base, ollama_url, model_store)` começa com cópia de `os.environ`
recebido, preservando `PATH`, `SYSTEMROOT`, `TEMP`, locale e demais variáveis de
sistema. Remove todas as chaves preexistentes que casem
`(?i)(?:^OLLAMA_|TOKEN|SECRET|PASSWORD|API[_-]?KEY)` e só então injeta
`OLLAMA_URL` com esquema para `Settings`, `OLLAMA_HOST` sem esquema para o
servidor, `OLLAMA_MODELS` app-owned e
`NO_PROXY=127.0.0.1,localhost,::1`. Passar esse mapa completo ao subprocesso; não
usar um `env` contendo apenas duas chaves.

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
        "--no-cache", "--reuse-equivalent",
        "--execution-identity", str(identity_path),
        "--results-root", str(results_root),
    ], env=build_child_env(os.environ, ollama.base_url, model_store))
```

Retorno 130 do runner ou `KeyboardInterrupt` define `interrupted` e retorno 130.
Retorno zero ainda chama `_invalid_matrix_stages` do núcleo sobre os dez modelos,
dois datasets e réplica zero; somente lista vazia permite `complete`. Qualquer
JSON ausente/corrupto ou metadata divergente define `failed`.

No `finally`, atualizar status, copiar/organizar resultados, versões, hashes e
logs sob evidence root; chamar `redact_sensitive` para JSON e
`sanitize_text_files` para logs usando `getpass.getuser()`, `platform.node()`,
`Path.home()` e `%USERPROFILE%`; gravar `privacy-report.json` apenas com
categorias/contagens; chamar `create_evidence_zip`. Não incluir os valores
removidos no relatório.

Materializar sempre a árvore fixa listada no teste: fonte indisponível recebe JSON
`{"status":"unavailable","error_type":"ParseError"}` ou linha equivalente, nunca
arquivo omitido. Copiar `results_root` inteiro sob `benchmark/results`. O
`manifest.json` lista caminho POSIX, tamanho e SHA-256 de cada outro membro do
ZIP; ele não lista a si mesmo porque auto-hash seria recursivo. Antes de aceitar o
ZIP, reabrir e recalcular cada entrada contra o manifesto.

Se sanitização, scanner, manifesto ou criação do bundle principal falhar, chamar
`create_partial_evidence_zip` com código enumerado e sem arquivos brutos. Em ambos
os casos gravar `--bootstrap-receipt` por temporário+replace com status, código de
saída e caminho do ZIP; não gravar valores sensíveis no receipt.

Nome: `RESULTADO_IFCQC_<UTC-basic>_<run-id>.zip`. Copiar atomicamente para
`launch_dir` se gravável; senão manter em `run_root` e imprimir o caminho. Retorno
0 para complete, 130 para interrupção e 1 para falha. O contexto encerra somente
o Ollama próprio; caches permanecem.

- [ ] **Step 7: Rodar testes e lint**

Run:

```powershell
uv run --frozen --group dev python -m pytest tests/windows/test_windows_benchmark.py tests/experiment/test_evidence_bundle.py tests/windows/test_windows_runtime.py tests/windows/test_windows_inventory.py -q
uv run --frozen --group dev python -m ruff check scripts/windows_benchmark.py tests/windows/test_windows_benchmark.py
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
- Create: `docs/testing/windows-one-click-acceptance.md`
- Create: `tests/windows/test_windows_release_smoke.py`
- Modify: `pyproject.toml`
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
    assert "sha-256 não é assinatura" in text.lower()
    assert "canal confiável" in text.lower()


def test_manual_checklist_requires_both_windows_versions_and_resume_cases():
    text = (ROOT / "docs/testing/windows-one-click-acceptance.md").read_text(
        encoding="utf-8"
    )
    required = [
        "Windows 10 22H2 build 19045 x64", "Windows 11 x64", "Ctrl+C",
        "BENCHMARK_STOP", "20 JSONs", "20 JSONLs", "/api/pull", "SHA-256",
    ]
    assert all(value in text for value in required)
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

Adicionar dois testes opt-in, ambos marcados `windows_e2e` e pulados salvo quando
`IFCQC_WINDOWS_SMOKE=1`:

```python
RUN_E2E = os.environ.get("IFCQC_WINDOWS_SMOKE") == "1"


@pytest.mark.windows_e2e
@pytest.mark.skipif(not RUN_E2E, reason="defina IFCQC_WINDOWS_SMOKE=1")
def test_opt_in_real_ground_truth_check_from_clean_release(tmp_path):
    release = build_release(ROOT, tmp_path / "dist")
    clean = tmp_path / "Pasta limpa com espaços"
    safe_extract_zip(release / "payload/project.zip", clean)
    for dataset in ("predio", "casa"):
        target = clean / "data/evaluation" / dataset / f"{dataset}_v1.ifc"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(release / "payload/datasets" / f"{dataset}_v1.ifc", target)
    before = {
        dataset: sha256_file(clean / "data/evaluation" / dataset / "ground_truth.yaml")
        for dataset in ("predio", "casa")
    }
    result = subprocess.run(
        [sys.executable, "scripts/build_ground_truths.py", "--check", "--dataset", "all"],
        cwd=clean, text=True, capture_output=True, timeout=900, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK predio" in result.stdout and "OK casa" in result.stdout
    assert before == {
        dataset: sha256_file(clean / "data/evaluation" / dataset / "ground_truth.yaml")
        for dataset in ("predio", "casa")
    }


@pytest.mark.windows_e2e
@pytest.mark.skipif(not RUN_E2E, reason="defina IFCQC_WINDOWS_SMOKE=1")
def test_opt_in_local_ollama_minimal_response():
    base_url = os.environ.get("IFCQC_SMOKE_OLLAMA_URL", "")
    model = os.environ.get("IFCQC_SMOKE_MODEL", "")
    assert base_url and model, (
        "defina IFCQC_SMOKE_OLLAMA_URL e IFCQC_SMOKE_MODEL para o smoke opt-in"
    )
    assert urllib.parse.urlsplit(base_url).hostname in {"127.0.0.1", "::1", "localhost"}
    locked = {entry.name: entry.digest for entry in load_model_lock(LOCK_PATH).models}
    tags = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=10).json()["models"]
    installed = {str(row["name"]): str(row["digest"]).removeprefix("sha256:")
                 for row in tags}
    assert model in locked and installed.get(model) == locked[model]
    response = httpx.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={"model": model, "prompt": "Responda apenas: ok", "stream": False},
        timeout=120,
    ).json()["response"]
    assert response.strip()
```

O segundo smoke nunca puxa modelo: exige URL loopback e um modelo do lock já
instalado com digest exato. Se `IFCQC_SMOKE_OLLAMA_URL` ou
`IFCQC_SMOKE_MODEL` faltar quando o opt-in está ativo, o teste falha explicando a
precondição, em vez de selecionar um modelo silenciosamente.

- [ ] **Step 3: Confirmar RED**

Run: `uv run --frozen --group dev python -m pytest tests/windows/test_windows_release_smoke.py -q`

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

Acrescentar a limitação literal: “SHA-256 não é assinatura digital: ele detecta
divergência em relação a este manifesto, mas não prova quem publicou a pasta.
Receba a pasta por canal confiável e não a execute se a origem for desconhecida.”

Registrar o marcador em `pyproject.toml`:

```toml
markers = [
    "slow: testes lentos (>1s)",
    "network: requer rede ou serviço externo (Ollama, bSDD)",
    "integration: testes de integração end-to-end",
    "windows_e2e: smoke opt-in e aceite manual do pacote Windows",
]
```

Criar `docs/testing/windows-one-click-acceptance.md` com tabela datada e caixas
para duas máquinas reais, uma Windows 10 22H2 build 19045 x64 e uma Windows 11
x64. Em cada linha registrar operador, build, CPU/RAM/GPU/driver e marcar:

- pasta de origem com espaços e conta sem administrador;
- primeira execução com cache vazio;
- queda/reconexão de rede durante `/api/pull` sem apagar blobs;
- `Ctrl+C` retorna 130, produz ZIP `interrupted` e relançamento retoma;
- `BENCHMARK_STOP` preexistente é ignorado e um novo retorna 130;
- run só fica `complete` com 20 JSONs e 20 JSONLs revalidados;
- ZIP abre, tem a árvore fixa, todos os membros exceto o manifesto conferem
  tamanho/SHA e o scanner de privacidade retorna zero achados.

- [ ] **Step 5: Copiar README e executar verificação completa**

Atualizar o builder para copiar `windows/LEIA-ME.txt` para a raiz como
`LEIA-ME.txt` e então rodar:

```powershell
uv run --frozen --group dev python -m pytest tests/windows -q -m "not windows_e2e"
uv run --frozen --group dev python -m pytest -q -m "not windows_e2e"
uv run --frozen --group dev python -m ruff check scripts/build_windows_release.py scripts/windows_benchmark.py src/experiment/windows_runtime.py src/experiment/windows_inventory.py tests/windows
git diff --check
uv run --frozen --no-dev python scripts/build_windows_release.py --output dist
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

- [ ] **Step 7: Rodar smokes opt-in e executar o checklist nas duas versões**

Na máquina de smoke com Ollama local já preparado:

```powershell
$env:IFCQC_WINDOWS_SMOKE='1'
$env:IFCQC_SMOKE_OLLAMA_URL='http://127.0.0.1:11434'
$env:IFCQC_SMOKE_MODEL='qwen3.5:4b'
uv run --frozen --group dev python -m pytest tests/windows/test_windows_release_smoke.py -q -m windows_e2e
```

Expected: o `--check` real dos dois IFCs e a resposta local mínima passam sem
download automático. Depois preencher todas as linhas de
`docs/testing/windows-one-click-acceptance.md` em Windows 10 e Windows 11; anexar
os dois ZIPs e registrar seus SHA-256 no documento. Ausência de uma das duas
máquinas mantém o aceite manual explicitamente pendente, sem convertê-lo em PASS.

- [ ] **Step 8: Commit final do pacote fonte**

```powershell
git add -- windows/LEIA-ME.txt docs/testing/windows-one-click-acceptance.md pyproject.toml scripts/build_windows_release.py tests/windows/test_windows_release_smoke.py
git commit -m "docs: finalizar pacote Windows do benchmark"
```

O conteúdo de `dist/` permanece ignorado e é o artefato local a transportar; não
forçar seu versionamento nem o dos IFCs.
