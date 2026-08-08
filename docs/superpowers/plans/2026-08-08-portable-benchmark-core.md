# Portable Benchmark Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o benchmark de prédio e casa reprodutível, retomável e capaz de produzir evidências portáveis antes de conectá-lo ao instalador Windows.

**Architecture:** O núcleo continua em Python e separa três responsabilidades: lock estrito de runtime/modelos, fila dos dois datasets e utilitários de evidência/privacidade. O launcher Windows consumirá essas APIs sem duplicar regras de digest, retomada ou empacotamento.

**Tech Stack:** Python 3.12.13, uv 0.12.3, Pydantic v2, pytest, Ruff, psutil, PyYAML, pandas, API HTTP local do Ollama.

## Global Constraints

- Os datasets oficiais são exatamente `predio` e `casa`, ambos em Deodoro, Rio de Janeiro/RJ, ZB 4A.
- Prédio usa contexto `Residencial multifamiliar`; casa usa `Residencial unifamiliar`.
- O launcher oficial sempre usa uma réplica, cache de sugestões desligado e `reuse_equivalent=True`.
- O lock usa Ollama `0.32.5` para `windows-amd64` e digest de modelo com 64 caracteres hexadecimais.
- Divergência de digest é erro impeditivo, nunca warning nem atualização silenciosa.
- Um estágio existente só é retomável quando seu JSON é íntegro e todos os metadados esperados coincidem.
- Evidências não podem conter usuário, hostname, IP, MAC, seriais, tokens, chaves Ollama ou conteúdo de `.env`.
- Nenhuma mudança desta fase abre, modifica ou redistribui os dois IFCs.

---

### Task 1: Fixar o ambiente Python de runtime

**Files:**

- Create: `.python-version`
- Create: `uv.lock`
- Modify: `pyproject.toml`
- Create: `tests/experiment/test_runtime_environment.py`

**Interfaces:**

- Consumes: `pyproject.toml` atual e os imports reais usados por `scripts/run_benchmark.py` e `src/experiment`.
- Produces: CPython exato `3.12.13`, lock universal do uv e grupo de dependências de runtime completo.

- [ ] **Step 1: Escrever teste de contrato que falha**

```python
from pathlib import Path

import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_dependencies_and_python_are_pinned():
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12.13"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = {value.split("[", 1)[0].split(">", 1)[0].split("=", 1)[0].lower()
             for value in project["project"]["dependencies"]}
    assert {"pandas", "pyyaml", "psutil"} <= names
    assert (ROOT / "uv.lock").is_file()
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/experiment/test_runtime_environment.py -q`

Expected: FAIL porque `.python-version`, `uv.lock` e três dependências ainda não existem.

- [ ] **Step 3: Declarar o runtime e gerar o lock**

Criar `.python-version` com uma única linha:

```text
3.12.13
```

Adicionar a `project.dependencies`:

```toml
    "pandas>=2.2",
    "PyYAML>=6.0",
    "psutil>=6.0",
```

Baixar `uv-x86_64-pc-windows-msvc.zip` 0.12.3, conferir SHA-256
`b23350c79e8ad0192b8124af13a0f17e8d4e4549524785e1aef389ae5a06990e`
e executar o binário extraído:

```powershell
uv.exe lock --python 3.12.13
uv.exe lock --check
uv.exe sync --frozen --no-dev --managed-python
```

- [ ] **Step 4: Verificar imports e lock**

Run:

```powershell
uv.exe run --frozen --no-dev python -c "import ifcopenshell,pandas,psutil,yaml; print('runtime-ok')"
uv.exe run --frozen --no-dev python -m pytest tests/experiment/test_runtime_environment.py -q
```

Expected: `runtime-ok`; teste PASS.

- [ ] **Step 5: Commit atômico**

```powershell
git add -- .python-version uv.lock pyproject.toml tests/experiment/test_runtime_environment.py
git commit -m "build: fixar ambiente Python do benchmark"
```

### Task 2: Atualizar e validar o lock do Ollama/modelos

**Files:**

- Modify: `src/experiment/results/models.lock.json`
- Create: `src/experiment/model_lock.py`
- Create: `tests/experiment/test_model_lock.py`

**Interfaces:**

- Consumes: JSON schema v2 descrito abaixo e mapeamento instalado `{tag: digest}` vindo da API `/api/tags`.
- Produces: `load_model_lock(path: Path) -> ModelMatrixLock`, `model_digest_mismatches(lock, installed) -> list[str]` e `required_free_bytes(lock, installed) -> int`.

- [ ] **Step 1: Escrever testes que falham para schema, drift e espaço**

```python
def test_official_lock_has_full_digests_and_exact_total():
    lock = load_model_lock(LOCK_PATH)
    assert lock.schema_version == 2
    assert lock.runtime.version == "0.32.5"
    assert lock.runtime.platform == "windows-amd64"
    assert len(lock.models) == 10
    assert all(len(model.digest) == 64 for model in lock.models)
    assert sum(model.size_bytes for model in lock.models) == 45_852_962_404


def test_all_missing_requires_partial_and_reserve_space():
    lock = load_model_lock(LOCK_PATH)
    assert required_free_bytes(lock, {}) == 57_032_733_355


def test_digest_drift_is_reported_with_full_expected_and_actual():
    lock = load_model_lock(LOCK_PATH)
    installed = {lock.models[0].name: "0" * 64}
    errors = model_digest_mismatches(lock, installed)
    assert lock.models[0].name in errors[0]
    assert lock.models[0].digest in errors[0]
    assert "0" * 64 in errors[0]
```

Adicionar testes que rejeitem digest curto, digest não hexadecimal, tamanho não
positivo, tag duplicada e runtime diferente de `windows-amd64`.

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/experiment/test_model_lock.py -q`

Expected: FAIL por módulo/schema inexistentes.

- [ ] **Step 3: Implementar modelos estritos e cálculos puros**

```python
class RuntimeLock(BaseModel):
    name: Literal["ollama"]
    version: Literal["0.32.5"]
    platform: Literal["windows-amd64"]
    asset_sha256: str


class ModelLockEntry(BaseModel):
    name: str
    digest: str
    size_bytes: int = Field(gt=0)
    architecture: str
    parameters: str
    context_length: int = Field(gt=0)
    quantization: str


class ModelMatrixLock(BaseModel):
    schema_version: Literal[2]
    runtime: RuntimeLock
    models: list[ModelLockEntry]
```

Validar com `field_validator` a regex `^[0-9a-f]{64}$`, nomes únicos e exatamente
dez entradas. O cálculo de espaço é:

```python
missing = [model.size_bytes for model in lock.models
           if installed.get(model.name) != model.digest]
return 0 if not missing else sum(missing) + max(missing) + max(sum(missing) // 10, 4 * 1024**3)
```

- [ ] **Step 4: Substituir o JSON pelo schema v2 completo**

Usar estes pares `name`, `digest`, `size_bytes`, sem abreviação:

```text
lfm2.5:8b             9cf756159fc2f3b9128c6a3f544ec90c5e9b8afdbb4179a57b8aea9de589cfb2  5156075525
granite4:tiny-h       566b725534ea0e9824f844abe6a78e1ab6f7357f1efb549be94908cb681513bb  4230995221
phi4-mini:latest      78fad5d182a7c33065e153a5f8ba210754207ba9d91973f57dffa7f487363753  2491876774
gemma2:9b             ff02c3702f322b9e075e9568332d96c0a7028002f1a5a056e0a6784320a4db0b  5443152417
qwen2.5:7b-instruct   845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e  4683087332
llama3.1:8b           46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e  4920753328
falcon3:7b            472ea1c89f64f932368963bfb8c7f54bd797f2161932cf0a72766a587b2e586d  4569738977
mistral:7b            6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf  4372824384
qwen3.5:4b            2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd  3389983735
qwen3.5:9b            6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7  6594474711
```

Em `runtime.asset_sha256`, usar
`7c941ae084569d298062d29f8139163a3187c76dbca0479c70d085e78fd8c7bb`.

- [ ] **Step 5: Rodar testes e lint**

Run:

```powershell
python -m pytest tests/experiment/test_model_lock.py -q
python -m ruff check src/experiment/model_lock.py tests/experiment/test_model_lock.py
```

Expected: PASS.

- [ ] **Step 6: Commit atômico**

```powershell
git add -- src/experiment/model_lock.py src/experiment/results/models.lock.json tests/experiment/test_model_lock.py
git commit -m "feat: validar lock completo dos modelos"
```

### Task 3: Registrar contexto do dataset no resultado

**Files:**

- Modify: `src/experiment/metrics.py`
- Modify: `src/experiment/environment.py`
- Modify: `src/experiment/runner.py`
- Modify: `tests/experiment/test_runner_harness.py`
- Modify: `tests/test_experiment_environment.py`

**Interfaces:**

- Consumes: `building_context` já obrigatório em `ExperimentRunner.run_single`.
- Produces: `RunMetadata.building_context: dict[str, str]`, serializado em cada `run_N.json`, e `hardware_snapshot()` anônimo por padrão.

- [ ] **Step 1: Escrever teste que falha**

No teste existente do `run_single`, acrescentar:

```python
assert result.metadata.building_context == {
    "building_type": "Residencial multifamiliar",
    "bioclimatic_zone": "4A",
}
```

Adicionar teste Pydantic provando que metadados antigos sem o campo continuam
carregando com `{}`.

Em `tests/test_experiment_environment.py`, trocar o contrato que exigia hostname
por:

```python
def test_hardware_snapshot_omite_identificadores_pessoais():
    snapshot = hardware_snapshot()
    assert "hostname" not in snapshot
    assert "username" not in snapshot
    assert "serial" not in snapshot
```

- [ ] **Step 2: Confirmar RED**

Run: `python -m pytest tests/experiment/test_runner_harness.py -q`

Expected: FAIL por atributo ausente.

- [ ] **Step 3: Implementar captura compatível**

Em `RunMetadata`:

```python
building_context: dict[str, str] = Field(default_factory=dict)
```

Na criação dos metadados em `run_single`:

```python
building_context={str(key): str(value) for key, value in building_context.items()},
```

Remover `hostname` do retorno de `hardware_snapshot()` e atualizar a docstring de
`RunMetadata.hardware` para dizer que o retrato é anônimo. A coleta rica do
instalador também será anônima e não deve depender desse campo.

- [ ] **Step 4: Rodar regressões**

Run:

```powershell
python -m pytest tests/experiment/test_runner_harness.py tests/experiment/test_report.py tests/test_experiment_environment.py -q
python -m ruff check src/experiment/metrics.py src/experiment/environment.py src/experiment/runner.py tests/experiment/test_runner_harness.py tests/test_experiment_environment.py
```

Expected: PASS.

- [ ] **Step 5: Commit atômico**

```powershell
git add -- src/experiment/metrics.py src/experiment/environment.py src/experiment/runner.py tests/experiment/test_runner_harness.py tests/test_experiment_environment.py
git commit -m "feat: registrar contexto do dataset no benchmark"
```

### Task 4: Executar prédio e casa com retomada validada

**Files:**

- Modify: `scripts/run_benchmark.py`
- Create: `tests/test_run_benchmark.py`

**Interfaces:**

- Consumes: `load_model_lock`, hashes de IFC/GT, `RunMetadata.building_context` e `ExperimentRunner.run_single`.
- Produces: `DATASETS` com dois itens, `StageExpectation`, `_stage_done(path, expectation)`, `_pid_record_is_live(record)`, `_acquire_pidfile(path)`, `_stop_requested(path, launch_ns)`, `_installed_digest(model)`, `_assert_model_digest(model, expected, actual)` e `main()` estrito.

- [ ] **Step 1: Escrever testes que falham para o registro e forwarding**

```python
import scripts.run_benchmark as module


def install_fake_runner(monkeypatch, tmp_path):
    calls: list[dict[str, object]] = []
    datasets = []
    for key, building_type in (("predio", "Residencial multifamiliar"),
                               ("casa", "Residencial unifamiliar")):
        ifc = tmp_path / f"{key}.ifc"
        gt = tmp_path / f"{key}.yaml"
        ifc.write_bytes(key.encode())
        gt.write_text("metadata: {}\nitems: []\nskipped: []\n", encoding="utf-8")
        datasets.append({
            "key": key, "ifc": ifc, "gt": gt, "issue_types": None,
            "building_context": {"building_type": building_type, "bioclimatic_zone": "4A"},
        })

    class FakeRunner:
        def run_single(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                evaluation=SimpleNamespace(accuracy_top1=1.0, accuracy_top3=1.0),
                stability=SimpleNamespace(failed_count=0),
            )

        @staticmethod
        def _export(result, output_root):
            return None

    monkeypatch.setattr(module, "DATASETS", datasets)
    monkeypatch.setattr(module, "PID_FILE", tmp_path / "RUNNING")
    monkeypatch.setattr(module, "STOP_FILE", tmp_path / "STOP")
    monkeypatch.setattr(module, "ExperimentRunner", FakeRunner)
    monkeypatch.setattr(module, "_locked_models", lambda: ["m:test"])
    monkeypatch.setattr(module, "_locked_digests", lambda: {"m:test": "a" * 64})
    monkeypatch.setattr(module, "_installed_digest", lambda model: "a" * 64)
    monkeypatch.setattr(module, "_unload_model", lambda model: None)
    return calls


def test_dataset_registry_has_predio_and_casa_only():
    assert [item["key"] for item in module.DATASETS] == ["predio", "casa"]
    assert module.DATASETS[0]["building_context"]["building_type"] == "Residencial multifamiliar"
    assert module.DATASETS[1]["building_context"]["building_type"] == "Residencial unifamiliar"
    assert {item["building_context"]["bioclimatic_zone"] for item in module.DATASETS} == {"4A"}


def test_main_forwards_context_and_reuse(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    assert module.main(["--only-model", "m:test", "--reuse-equivalent",
                        "--results-root", str(tmp_path / "results")]) == 0
    assert [call["building_context"] for call in calls] == [
        module.DATASETS[0]["building_context"], module.DATASETS[1]["building_context"]
    ]
    assert all(call["reuse_equivalent"] is True for call in calls)
```

Redirecionar `PID_FILE`, `STOP_FILE`, `LOCK_FILE`, IFCs e GTs para `tmp_path`; não
usar Ollama nem IFC real.

- [ ] **Step 2: Escrever testes que falham para retomada e sentinelas**

Cobrir:

```python
def _expectation() -> module.StageExpectation:
    return module.StageExpectation(
        model_name="m:test", model_digest="a" * 64, replica_index=0,
        reuse_equivalent=True, ifc_sha256="b" * 64, ground_truth_sha256="c" * 64,
        building_context={"building_type": "Residencial unifamiliar", "bioclimatic_zone": "4A"},
    )


def _write_stage(path: Path, metadata: dict[str, object]) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"metadata": metadata}), encoding="utf-8")


def test_stage_done_rejects_corrupt_json(tmp_path):
    path = tmp_path / "run_0.json"
    path.write_text("{", encoding="utf-8")
    assert not module._stage_done(path, _expectation())


@pytest.mark.parametrize(
    ("field", "wrong"),
    [("ifc_sha256", "d" * 64), ("ground_truth_sha256", "e" * 64),
     ("model_name", "other"), ("model_digest", "f" * 64),
     ("replica_index", 2), ("reuse_equivalent", False),
     ("building_context", {"bioclimatic_zone": "3"})],
)
def test_stage_done_rejects_any_metadata_mismatch(tmp_path, field, wrong):
    expectation = _expectation()
    metadata = asdict(expectation)
    metadata[field] = wrong
    path = tmp_path / "run_0.json"
    _write_stage(path, metadata)
    assert not module._stage_done(path, expectation)


def test_stage_done_accepts_exact_metadata(tmp_path):
    expectation = _expectation()
    path = tmp_path / "run_0.json"
    _write_stage(path, asdict(expectation))
    assert module._stage_done(path, expectation)


def test_stale_pid_is_replaced_but_live_matching_pid_blocks(monkeypatch, tmp_path):
    path = tmp_path / "running.json"
    path.write_text('{"pid":7,"create_time":1.0,"token":"old"}', encoding="utf-8")
    monkeypatch.setattr(module, "_pid_record_is_live", lambda record: False)
    lease = module._acquire_pidfile(path)
    assert lease is not None and lease.token != "old"
    monkeypatch.setattr(module, "_pid_record_is_live", lambda record: True)
    assert module._acquire_pidfile(path) is None


def test_stop_file_older_than_launch_is_ignored(tmp_path):
    path = tmp_path / "STOP"
    path.write_text("stop", encoding="utf-8")
    launch_ns = path.stat().st_mtime_ns + 1
    assert not module._stop_requested(path, launch_ns)


def test_model_digest_mismatch_aborts():
    with pytest.raises(RuntimeError, match="digest"):
        module._assert_model_digest("m:test", expected="a" * 64, actual="b" * 64)
```

- [ ] **Step 3: Confirmar RED**

Run: `python -m pytest tests/test_run_benchmark.py -q`

Expected: FAIL porque o runner ainda usa prédio+masked, contexto único, PID por
existência e retomada por simples presença de arquivo.

- [ ] **Step 4: Implementar registro e expectativa de estágio**

```python
@dataclass(frozen=True)
class StageExpectation:
    model_name: str
    model_digest: str
    replica_index: int
    reuse_equivalent: bool
    ifc_sha256: str
    ground_truth_sha256: str
    building_context: dict[str, str]
```

`DATASETS` deve apontar para:

```python
{"key": "predio", "ifc": EVAL_ROOT / "predio/predio_v1.ifc",
 "gt": EVAL_ROOT / "predio/ground_truth.yaml", "issue_types": None,
 "building_context": {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "4A"}}
{"key": "casa", "ifc": EVAL_ROOT / "casa/casa_v1.ifc",
 "gt": EVAL_ROOT / "casa/ground_truth.yaml", "issue_types": None,
 "building_context": {"building_type": "Residencial unifamiliar", "bioclimatic_zone": "4A"}}
```

`_stage_done` abre e valida o JSON; qualquer ausência, erro de parse ou diferença
retorna `False` com log da causa. `_check_digest` levanta `RuntimeError` em drift.

- [ ] **Step 5: Implementar PID/STOP robustos**

O PID file é JSON com `pid`, `create_time` e token UUID. Usar psutil para conferir
PID, tempo de criação e linha de comando contendo `run_benchmark.py`. Substituir
atomicamente arquivo inválido ou processo morto. No `finally`, remover somente se
o token ainda for o desta execução.

Capturar `launch_time_ns = time.time_ns()` e considerar parada apenas quando
`STOP_FILE.stat().st_mtime_ns >= launch_time_ns`.

- [ ] **Step 6: Rodar testes e regressões**

Run:

```powershell
python -m pytest tests/test_run_benchmark.py tests/experiment/test_runner_harness.py -q
python -m ruff check scripts/run_benchmark.py tests/test_run_benchmark.py
```

Expected: PASS.

- [ ] **Step 7: Commit atômico**

```powershell
git add -- scripts/run_benchmark.py tests/test_run_benchmark.py
git commit -m "feat: executar benchmark de predio e casa"
```

### Task 5: Criar utilitários de evidência e privacidade

**Files:**

- Create: `src/experiment/evidence_bundle.py`
- Create: `tests/experiment/test_evidence_bundle.py`

**Interfaces:**

- Consumes: diretório de evidências, valores sensíveis conhecidos, JSON bruto do llmfit e nomes do lock.
- Produces: `RemovedField`, `PrivacyFinding`, `EvidencePrivacyError`, `redact_sensitive`, `redact_text_files`, `scan_sensitive_text`, `filter_llmfit_recommendations`, `build_file_manifest`, `write_manifest`, `validate_manifest` e `create_evidence_zip`.

- [ ] **Step 1: Escrever testes de privacidade que falham**

```python
def test_redacts_sensitive_keys_and_known_values():
    raw = {"hostname": "PC-KELLER", "nested": {"serial_number": "ABC", "cpu": "Ryzen"}}
    clean, removed = redact_sensitive(raw, forbidden_values={"PC-KELLER"})
    assert clean == {"nested": {"cpu": "Ryzen"}}
    assert {item.path for item in removed} == {"hostname", "nested.serial_number"}


def test_scanner_finds_username_hostname_ip_mac_and_token(tmp_path):
    path = tmp_path / "leak.txt"
    path.write_text("Keller PC-01 192.168.0.2 aa:bb:cc:dd:ee:ff Bearer secret", encoding="utf-8")
    findings = scan_sensitive_text(tmp_path, forbidden_values={"Keller", "PC-01"})
    assert {finding.kind for finding in findings} >= {"known-value", "ipv4", "mac", "bearer-token"}


def test_redacts_known_values_in_logs_but_allows_loopback(tmp_path):
    path = tmp_path / "runner.log"
    path.write_text(r"C:\Users\Keller projeto em 127.0.0.1", encoding="utf-8")
    removed = redact_text_files(tmp_path, forbidden_values={"Keller"})
    assert removed
    assert "Keller" not in path.read_text(encoding="utf-8")
    assert not scan_sensitive_text(tmp_path, forbidden_values={"Keller"})
```

- [ ] **Step 2: Escrever testes de recomendações, manifesto e ZIP**

```python
def test_filters_models_already_in_project_lock():
    raw = [{"model": "gemma2:9b", "score": 90}, {"model": "extra:14b", "score": 80}]
    assert filter_llmfit_recommendations(raw, {"gemma2:9b"}) == [
        {"model": "extra:14b", "score": 80}
    ]


def test_manifest_is_sorted_and_hashes_every_payload_file(tmp_path):
    (tmp_path / "z.txt").write_text("z", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    manifest = build_file_manifest(tmp_path)
    assert [entry["path"] for entry in manifest] == ["a.txt", "z.txt"]
    assert manifest[0]["sha256"] == hashlib.sha256(b"a").hexdigest()
    write_manifest(tmp_path / "manifest.json", manifest)
    assert validate_manifest(tmp_path / "manifest.json", tmp_path) == []


def test_zip_rejects_privacy_findings(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "leak.txt").write_text("PC-PRIVATE", encoding="utf-8")
    with pytest.raises(EvidencePrivacyError, match="known-value"):
        create_evidence_zip(
            evidence, tmp_path / "result.zip", forbidden_values={"PC-PRIVATE"}
        )


def test_zip_excludes_itself_and_forbidden_file_types(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "public.txt").write_text("ok", encoding="utf-8")
    (evidence / ".env").write_text("TOKEN=x", encoding="utf-8")
    output = evidence / "result.zip"
    create_evidence_zip(evidence, output, forbidden_values=set())
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ["manifest.json", "public.txt"]
```

- [ ] **Step 3: Confirmar RED**

Run: `python -m pytest tests/experiment/test_evidence_bundle.py -q`

Expected: FAIL por módulo ausente.

- [ ] **Step 4: Implementar APIs puras e determinísticas**

```python
@dataclass(frozen=True)
class RemovedField:
    path: str
    reason: str


@dataclass(frozen=True)
class PrivacyFinding:
    path: str
    kind: str
    line: int


class EvidencePrivacyError(ValueError):
    pass


SENSITIVE_KEYS = re.compile(
    r"(?:user(?:name)?|host(?:name)?|serial|mac|ip_address|token|secret|password|ollama_key)",
    re.IGNORECASE,
)


def build_file_manifest(root: Path) -> list[dict[str, object]]:
    return [
        {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size,
         "sha256": sha256_file(path)}
        for path in _evidence_files(root)
    ]


def write_manifest(path: Path, entries: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"files": entries}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
```

`create_evidence_zip` deve rodar o scanner antes de escrever, criar
`manifest.json`, usar caminhos relativos e recusar symlinks ou arquivos fora da
raiz. Não incluir `.env`, chaves Ollama, blobs/modelos, IFCs nem executáveis.
`write_manifest` usa JSON UTF-8 indentado com chaves ordenadas;
`validate_manifest(path, root)` recalcula tamanho/hash e retorna uma lista de
erros vazia somente quando não há arquivo ausente, extra ou divergente.

Implementar os demais corpos com estas regras literais:

```python
TEXT_SUFFIXES = {".json", ".jsonl", ".txt", ".log", ".yaml", ".yml", ".csv", ".md"}
FORBIDDEN_NAMES = {".env", "id_ed25519", "id_ed25519.pub"}
FORBIDDEN_SUFFIXES = {".ifc", ".ifczip", ".exe", ".dll", ".bin", ".zip"}


def _evidence_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for candidate in sorted(root.rglob("*")):
        if candidate.is_symlink():
            raise EvidencePrivacyError(f"symlink proibido: {candidate}")
        if not candidate.is_file() or candidate.name == "manifest.json":
            continue
        if candidate.name.lower() in FORBIDDEN_NAMES or candidate.suffix.lower() in FORBIDDEN_SUFFIXES:
            continue
        files.append(candidate)
    return files


def redact_sensitive(value: Any, *, forbidden_values: set[str], path: str = "") \
        -> tuple[Any, list[RemovedField]]:
    removed: list[RemovedField] = []
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, child in value.items():
            child_path = f"{path}.{key}".strip(".")
            if SENSITIVE_KEYS.search(str(key)):
                removed.append(RemovedField(child_path, "sensitive-key"))
                continue
            clean_child, child_removed = redact_sensitive(
                child, forbidden_values=forbidden_values, path=child_path
            )
            clean[str(key)] = clean_child
            removed.extend(child_removed)
        return clean, removed
    if isinstance(value, list):
        clean_list: list[Any] = []
        for index, child in enumerate(value):
            clean_child, child_removed = redact_sensitive(
                child, forbidden_values=forbidden_values, path=f"{path}[{index}]"
            )
            clean_list.append(clean_child)
            removed.extend(child_removed)
        return clean_list, removed
    if isinstance(value, str):
        clean_text = value
        for forbidden in sorted((item for item in forbidden_values if item), key=len, reverse=True):
            if forbidden.casefold() in clean_text.casefold():
                clean_text = re.sub(re.escape(forbidden), "[REDACTED]", clean_text, flags=re.I)
                removed.append(RemovedField(path, "known-value"))
        return clean_text, removed
    return value, removed


def scan_sensitive_text(root: Path, *, forbidden_values: set[str]) \
        -> list[PrivacyFinding]:
    patterns = {
        "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "mac": re.compile(r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", re.I),
        "bearer-token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.I),
    }
    findings: list[PrivacyFinding] = []
    for candidate in _evidence_files(root):
        if candidate.suffix.lower() not in TEXT_SUFFIXES:
            continue
        for number, line in enumerate(candidate.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for forbidden in (item for item in forbidden_values if item):
                if forbidden.casefold() in line.casefold():
                    findings.append(PrivacyFinding(candidate.relative_to(root).as_posix(), "known-value", number))
            for kind, pattern in patterns.items():
                for match in pattern.finditer(line):
                    if kind == "ipv4" and (ipaddress.ip_address(match.group()).is_loopback
                                            or ipaddress.ip_address(match.group()).is_unspecified):
                        continue
                    findings.append(PrivacyFinding(candidate.relative_to(root).as_posix(), kind, number))
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind))


def filter_llmfit_recommendations(rows: list[dict[str, Any]], locked: set[str]) \
        -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("model", "")) not in locked]


def redact_text_files(root: Path, *, forbidden_values: set[str]) -> list[RemovedField]:
    removed: list[RemovedField] = []
    for candidate in _evidence_files(root):
        if candidate.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        for forbidden in sorted((item for item in forbidden_values if item), key=len, reverse=True):
            matches = len(re.findall(re.escape(forbidden), text, flags=re.I))
            if matches:
                text = re.sub(re.escape(forbidden), "[REDACTED]", text, flags=re.I)
                removed.append(RemovedField(candidate.relative_to(root).as_posix(),
                                            f"known-value:{matches}"))
        candidate.write_text(text, encoding="utf-8")
    return removed


def validate_manifest(path: Path, root: Path) -> list[str]:
    expected = {
        str(item["path"]): (int(item["size_bytes"]), str(item["sha256"]))
        for item in json.loads(path.read_text(encoding="utf-8"))["files"]
    }
    actual = {
        str(item["path"]): (int(item["size_bytes"]), str(item["sha256"]))
        for item in build_file_manifest(root)
    }
    errors = [f"manifest mismatch: {key}" for key in sorted(expected.keys() | actual.keys())
              if expected.get(key) != actual.get(key)]
    return errors


def create_evidence_zip(root: Path, output: Path, *, forbidden_values: set[str]) -> Path:
    findings = scan_sensitive_text(root, forbidden_values=forbidden_values)
    if findings:
        raise EvidencePrivacyError(
            "; ".join(f"{item.kind}:{item.path}:{item.line}" for item in findings)
        )
    manifest_path = root / "manifest.json"
    write_manifest(manifest_path, build_file_manifest(root))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(manifest_path, "manifest.json")
        for candidate in _evidence_files(root):
            archive.write(candidate, candidate.relative_to(root).as_posix())
    return output
```

Para `sha256_file`, importar a implementação streaming já testada de
`src.experiment.ground_truth_validation`. Strings sensíveis encontradas em campos
não removidos são substituídas por `[REDACTED]` antes de serem gravadas. Antes de
`create_evidence_zip`, o orquestrador chama `redact_text_files` com usuário,
hostname e caminho do perfil; qualquer ocorrência restante no scanner impede a
criação do ZIP. IPv4 loopback/unspecified é permitido porque identifica somente o
serviço local, não a máquina.

- [ ] **Step 5: Rodar testes e lint**

Run:

```powershell
python -m pytest tests/experiment/test_evidence_bundle.py -q
python -m ruff check src/experiment/evidence_bundle.py tests/experiment/test_evidence_bundle.py
```

Expected: PASS.

- [ ] **Step 6: Commit atômico**

```powershell
git add -- src/experiment/evidence_bundle.py tests/experiment/test_evidence_bundle.py
git commit -m "feat: preparar pacote de evidencias privado"
```

### Task 6: Verificação integrada do núcleo

**Files:**

- Create: `tests/experiment/test_portable_benchmark_core.py`
- Verify: no production changes expected.

**Interfaces:**

- Consumes: lock v2, registro dos datasets, runner com double e empacotador de evidências.
- Produces: prova integrada sem Ollama/IFC grande.

- [ ] **Step 1: Escrever smoke integrado**

O teste cria IFC/GT/IDS mínimos ou usa doubles, executa um estágio por dataset com
`reuse_equivalent=True`, exporta resultados, passa-os pelo empacotador e afirma:

```python
assert set(dataset_keys) == {"predio", "casa"}
assert all(run["metadata"]["reuse_equivalent"] is True for run in runs)
assert all(run["metadata"]["building_context"]["bioclimatic_zone"] == "4A" for run in runs)
assert not scan_sensitive_text(evidence_root, forbidden_values={username, hostname})
assert validate_manifest(evidence_root / "manifest.json", evidence_root) == []
```

- [ ] **Step 2: Rodar testes focados e suíte completa**

Run:

```powershell
python -m pytest tests/experiment/test_runtime_environment.py tests/experiment/test_model_lock.py tests/experiment/test_runner_harness.py tests/test_run_benchmark.py tests/experiment/test_evidence_bundle.py tests/experiment/test_portable_benchmark_core.py -q
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: Rodar qualidade estática e checks de lock**

Run:

```powershell
uv.exe lock --check
python -m ruff check src/experiment/model_lock.py src/experiment/evidence_bundle.py src/experiment/metrics.py src/experiment/runner.py scripts/run_benchmark.py tests/experiment/test_model_lock.py tests/experiment/test_evidence_bundle.py tests/experiment/test_portable_benchmark_core.py tests/test_run_benchmark.py
python -m mypy src/experiment/model_lock.py src/experiment/evidence_bundle.py
git diff --check
```

Expected: PASS. Se mypy expuser erro preexistente fora dos arquivos listados, não
ampliar o comando nem ocultar o resultado.

- [ ] **Step 4: Commit do smoke**

```powershell
git add -- tests/experiment/test_portable_benchmark_core.py
git commit -m "test: verificar nucleo portatil do benchmark"
```
