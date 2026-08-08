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
- A identidade canônica da execução é imutável e inclui `release_id`, SHA-256 do
  `project.zip` e do `models.lock.json`, ordem e hashes IFC/GT/IDS dos datasets,
  quantidade de réplicas, estado do cache, versão e SHA-256 dos prompts e modo de reuso.
- A matriz oficial só termina como `complete` depois de revalidar os 20 estágios
  esperados: 10 modelos × 2 datasets × 1 réplica.
- `BENCHMARK_STOP` criado ou regravado depois do início e `Ctrl+C` encerram com código
  130 e estado `interrupted`; um STOP preexistente permanece inerte.
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
- Produces: CPython exato `3.12.13`, lock universal do uv, dependências de runtime
  completas e grupo de desenvolvimento `dev` que instala pytest/lint/type-checker.

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
    assert {"pytest", "pytest-cov", "ruff", "mypy"} <= {
        value.split("[", 1)[0].split(">", 1)[0].split("=", 1)[0].lower()
        for value in project["dependency-groups"]["dev"]
    }
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

Migrar o extra opcional de testes para o grupo que o uv sincroniza explicitamente:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "mypy>=1.10",
]
```

Baixar `uv-x86_64-pc-windows-msvc.zip` 0.12.3, conferir SHA-256
`b23350c79e8ad0192b8124af13a0f17e8d4e4549524785e1aef389ae5a06990e`
e executar o binário extraído:

```powershell
uv.exe lock --python 3.12.13
uv.exe lock --check
uv.exe sync --frozen --no-dev --managed-python
uv.exe sync --frozen --group dev --managed-python
```

- [ ] **Step 4: Verificar imports e lock**

Run:

```powershell
uv.exe run --frozen --no-dev python -c "import ifcopenshell,pandas,psutil,yaml; print('runtime-ok')"
uv.exe run --frozen --group dev python -m pytest tests/experiment/test_runtime_environment.py -q
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

Acrescentar casos negativos concretos usando uma cópia do JSON oficial:

```python
@pytest.mark.parametrize(
    ("field", "value"),
    [("digest", "abc"), ("digest", "z" * 64), ("size_bytes", 0)],
)
def test_model_entry_rejects_invalid_digest_or_size(field, value):
    raw = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    raw["models"][0][field] = value
    with pytest.raises(ValidationError):
        ModelMatrixLock.model_validate(raw)


def test_lock_rejects_duplicate_tag_and_wrong_platform():
    duplicate = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    duplicate["models"][1]["name"] = duplicate["models"][0]["name"]
    with pytest.raises(ValidationError, match="duplicado"):
        ModelMatrixLock.model_validate(duplicate)
    wrong_platform = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    wrong_platform["runtime"]["platform"] = "linux-amd64"
    with pytest.raises(ValidationError):
        ModelMatrixLock.model_validate(wrong_platform)
```

- [ ] **Step 2: Confirmar RED**

Run: `uv run --frozen --group dev python -m pytest tests/experiment/test_model_lock.py -q`

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
uv run --frozen --group dev python -m pytest tests/experiment/test_model_lock.py -q
uv run --frozen --group dev python -m ruff check src/experiment/model_lock.py tests/experiment/test_model_lock.py
```

Expected: PASS.

- [ ] **Step 6: Commit atômico**

```powershell
git add -- src/experiment/model_lock.py src/experiment/results/models.lock.json tests/experiment/test_model_lock.py
git commit -m "feat: validar lock completo dos modelos"
```

### Task 3: Registrar contexto e identidade imutável no resultado

**Files:**

- Modify: `src/experiment/metrics.py`
- Modify: `src/experiment/environment.py`
- Modify: `src/experiment/runner.py`
- Create: `src/experiment/execution_identity.py`
- Create: `tests/experiment/test_execution_identity.py`
- Modify: `tests/experiment/test_runner_harness.py`
- Modify: `tests/test_experiment_environment.py`

**Interfaces:**

- Consumes: `building_context` já obrigatório em `ExperimentRunner.run_single` e
  identidade fornecida pela fila oficial.
- Produces: `DatasetIdentity`, `ExecutionIdentity`,
  `canonical_identity_sha256(identity) -> str`, `RunMetadata.building_context`,
  `RunMetadata.dataset_key`, snapshot/digest da identidade em cada `run_N.json` e
  `hardware_snapshot()` anônimo por padrão.

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

Em `tests/experiment/test_execution_identity.py`, provar que cada dimensão
experimental participa do digest, sem depender de ordem de chaves JSON:

```python
def identity(**overrides) -> ExecutionIdentity:
    values = {
        "release_id": "ifcqc-r1",
        "project_sha256": "1" * 64,
        "models_lock_sha256": "2" * 64,
        "datasets": (
            DatasetIdentity(
                key="predio", ifc_sha256="3" * 64, ground_truth_sha256="4" * 64,
                ids_sha256="5" * 64,
                building_context=(("bioclimatic_zone", "4A"),
                                  ("building_type", "Residencial multifamiliar")),
            ),
            DatasetIdentity(
                key="casa", ifc_sha256="6" * 64, ground_truth_sha256="7" * 64,
                ids_sha256="5" * 64,
                building_context=(("bioclimatic_zone", "4A"),
                                  ("building_type", "Residencial unifamiliar")),
            ),
        ),
        "replica_count": 1,
        "cache_enabled": False,
        "prompt_version": "v7.2",
        "prompt_sha256": "8" * 64,
        "reuse_equivalent": True,
    }
    values.update(overrides)
    return ExecutionIdentity(**values)


@pytest.mark.parametrize(
    "replacement",
    [
        {"release_id": "ifcqc-r2"}, {"project_sha256": "9" * 64},
        {"models_lock_sha256": "a" * 64}, {"replica_count": 2},
        {"cache_enabled": True}, {"prompt_version": "v-next"},
        {"prompt_sha256": "b" * 64}, {"reuse_equivalent": False},
        {"datasets": tuple(reversed(identity().datasets))},
        {"datasets": (replace(identity().datasets[0], ifc_sha256="c" * 64),
                       identity().datasets[1])},
        {"datasets": (replace(identity().datasets[0], ground_truth_sha256="d" * 64),
                       identity().datasets[1])},
        {"datasets": (replace(identity().datasets[0], ids_sha256="e" * 64),
                       identity().datasets[1])},
    ],
)
def test_every_experimental_input_changes_identity_digest(replacement):
    assert canonical_identity_sha256(identity(**replacement)) != canonical_identity_sha256(identity())
```

- [ ] **Step 2: Confirmar RED**

Run: `uv run --frozen --group dev python -m pytest tests/experiment/test_execution_identity.py tests/experiment/test_runner_harness.py -q`

Expected: FAIL por atributo ausente.

- [ ] **Step 3: Implementar captura compatível**

Criar tipos realmente imutáveis; normalizar contexto para tupla ordenada antes
da construção e validar todos os SHA-256 com `^[0-9a-f]{64}$`:

```python
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_sha_fields(value: object) -> None:
    for descriptor in fields(value):
        if descriptor.name.endswith("_sha256"):
            digest = getattr(value, descriptor.name)
            if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                raise ValueError(f"{descriptor.name} deve ser SHA-256 lowercase")


@dataclass(frozen=True)
class DatasetIdentity:
    key: str
    ifc_sha256: str
    ground_truth_sha256: str
    ids_sha256: str
    building_context: Sequence[tuple[str, str]]

    def __post_init__(self) -> None:
        if not isinstance(self.building_context, tuple):
            raise TypeError("building_context deve ser tuple")
        if tuple(sorted(self.building_context)) != self.building_context:
            raise ValueError("building_context deve estar ordenado")
        _validate_sha_fields(self)


@dataclass(frozen=True)
class ExecutionIdentity:
    release_id: str
    project_sha256: str
    models_lock_sha256: str
    datasets: Sequence[DatasetIdentity]
    replica_count: int
    cache_enabled: bool
    prompt_version: str
    prompt_sha256: str
    reuse_equivalent: bool

    def __post_init__(self) -> None:
        if not isinstance(self.datasets, tuple):
            raise TypeError("datasets deve ser tuple")
        if [dataset.key for dataset in self.datasets] != ["predio", "casa"]:
            raise ValueError("datasets devem estar na ordem predio,casa")
        if self.replica_count < 1:
            raise ValueError("replica_count deve ser positivo")
        _validate_sha_fields(self)


def canonical_identity_sha256(identity: ExecutionIdentity) -> str:
    payload = json.dumps(
        asdict(identity), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

Em `RunMetadata`:

```python
building_context: dict[str, str] = Field(default_factory=dict)
dataset_key: str = ""
execution_identity: dict[str, Any] = Field(default_factory=dict)
execution_identity_sha256: str = ""
```

Acrescentar a `run_single` os argumentos opcionais e retrocompatíveis
`dataset_key: str = ""` e `execution_identity: ExecutionIdentity | None = None`.
Na criação dos metadados:

```python
building_context={str(key): str(value) for key, value in building_context.items()},
dataset_key=dataset_key,
execution_identity=asdict(execution_identity) if execution_identity else {},
execution_identity_sha256=(
    canonical_identity_sha256(execution_identity) if execution_identity else ""
),
```

Remover `hostname` do retorno de `hardware_snapshot()` e atualizar a docstring de
`RunMetadata.hardware` para dizer que o retrato é anônimo. A coleta rica do
instalador também será anônima e não deve depender desse campo.

- [ ] **Step 4: Rodar regressões**

Run:

```powershell
uv run --frozen --group dev python -m pytest tests/experiment/test_execution_identity.py tests/experiment/test_runner_harness.py tests/experiment/test_report.py tests/test_experiment_environment.py -q
uv run --frozen --group dev python -m ruff check src/experiment/execution_identity.py src/experiment/metrics.py src/experiment/environment.py src/experiment/runner.py tests/experiment/test_execution_identity.py tests/experiment/test_runner_harness.py tests/test_experiment_environment.py
```

Expected: PASS.

- [ ] **Step 5: Commit atômico**

```powershell
git add -- src/experiment/execution_identity.py src/experiment/metrics.py src/experiment/environment.py src/experiment/runner.py tests/experiment/test_execution_identity.py tests/experiment/test_runner_harness.py tests/test_experiment_environment.py
git commit -m "feat: registrar contexto do dataset no benchmark"
```

### Task 4: Executar prédio e casa com retomada validada

**Files:**

- Modify: `scripts/run_benchmark.py`
- Create: `tests/test_run_benchmark.py`

**Interfaces:**

- Consumes: `load_model_lock`, `ExecutionIdentity`, hashes reais de IFC/GT/IDS/prompt,
  `RunMetadata` e `ExperimentRunner.run_single`.
- Produces: `DATASETS` com dois itens, `StageExpectation`, `StopBaseline`,
  `_load_and_validate_execution_identity(path)`, `_stage_done(path, expectation)`,
  `_invalid_matrix_stages(results_root, identity, models)`,
  `_pid_record_is_live(record)`, `_acquire_pidfile(path)` com lease `O_EXCL`,
  `_capture_stop_baseline(path)`, `_stop_requested(path, baseline)`,
  `_installed_digest(model)`, `_assert_model_digest(model, expected, actual)` e
  `main()` que distingue sucesso, falha e interrupção.

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
    monkeypatch.setattr(
        module, "_load_and_validate_execution_identity", lambda path: official_identity()
    )
    monkeypatch.setattr(module, "_invalid_matrix_stages", lambda *args, **kwargs: [])
    return calls


def test_dataset_registry_has_predio_and_casa_only():
    assert [item["key"] for item in module.DATASETS] == ["predio", "casa"]
    assert module.DATASETS[0]["building_context"]["building_type"] == "Residencial multifamiliar"
    assert module.DATASETS[1]["building_context"]["building_type"] == "Residencial unifamiliar"
    assert {item["building_context"]["bioclimatic_zone"] for item in module.DATASETS} == {"4A"}


def test_main_forwards_context_and_reuse(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    assert module.main(["--only-model", "m:test", "--no-cache", "--reuse-equivalent",
                        "--execution-identity", str(tmp_path / "identity.json"),
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
        dataset_key="casa", model_name="m:test", model_digest="a" * 64,
        replica_index=0, execution_identity=asdict(official_identity()),
        execution_identity_sha256=canonical_identity_sha256(official_identity()),
        ifc_sha256="b" * 64, ground_truth_sha256="c" * 64, ids_sha256="d" * 64,
        prompt_version="v7.2", cache_enabled=False, reuse_equivalent=True,
        building_context={"building_type": "Residencial unifamiliar",
                          "bioclimatic_zone": "4A"},
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
    [("dataset_key", "predio"), ("ifc_sha256", "e" * 64),
     ("ground_truth_sha256", "f" * 64), ("ids_sha256", "0" * 64),
     ("model_name", "other"), ("model_digest", "f" * 64),
     ("replica_index", 2), ("reuse_equivalent", False),
     ("cache_enabled", True), ("prompt_version", "v-next"),
     ("execution_identity_sha256", "1" * 64),
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


def test_stage_done_rejects_nested_execution_identity_change(tmp_path):
    expectation = _expectation()
    metadata = asdict(expectation)
    metadata["execution_identity"]["project_sha256"] = "9" * 64
    path = tmp_path / "run_0.json"
    _write_stage(path, metadata)
    assert not module._stage_done(path, expectation)


def test_pid_lease_uses_exclusive_create(monkeypatch, tmp_path):
    seen_flags = []
    real_open = os.open
    monkeypatch.setattr(
        os, "open",
        lambda path, flags, mode=0o777: (seen_flags.append(flags), real_open(path, flags, mode))[1],
    )
    lease = module._acquire_pidfile(tmp_path / "running.json")
    assert lease is not None
    assert seen_flags[0] & os.O_EXCL


def test_stale_pid_is_reaped_but_live_matching_pid_blocks(monkeypatch, tmp_path):
    path = tmp_path / "running.json"
    path.write_text('{"pid":7,"create_time":1.0,"token":"old"}', encoding="utf-8")
    monkeypatch.setattr(module, "_pid_record_is_live", lambda record: False)
    lease = module._acquire_pidfile(path)
    assert lease is not None and lease.token != "old"
    monkeypatch.setattr(module, "_pid_record_is_live", lambda record: True)
    assert module._acquire_pidfile(path) is None


def test_stop_existing_at_launch_is_ignored_but_rewrite_is_interruption(tmp_path):
    path = tmp_path / "STOP"
    path.write_text("stop", encoding="utf-8")
    baseline = module._capture_stop_baseline(path)
    assert not module._stop_requested(path, baseline)
    path.write_text("stop-new", encoding="utf-8")
    assert module._stop_requested(path, baseline)


def test_new_stop_and_keyboard_interrupt_return_130(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    original_run_single = module.ExperimentRunner.run_single

    def stop_during_first_stage(self, **kwargs):
        result = original_run_single(self, **kwargs)
        module.STOP_FILE.write_text("novo", encoding="utf-8")
        return result

    monkeypatch.setattr(module.ExperimentRunner, "run_single", stop_during_first_stage)
    assert module.main(["--only-model", "m:test", "--no-cache", "--reuse-equivalent",
                        "--execution-identity", str(tmp_path / "identity.json"),
                        "--results-root", str(tmp_path / "results")]) == 130
    module.STOP_FILE.unlink()
    monkeypatch.setattr(module.ExperimentRunner, "run_single",
                        lambda self, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert module.main(["--only-model", "m:test", "--no-cache", "--reuse-equivalent",
                        "--execution-identity", str(tmp_path / "identity.json"),
                        "--results-root", str(tmp_path / "results2")]) == 130


def test_model_digest_mismatch_aborts():
    with pytest.raises(RuntimeError, match="digest"):
        module._assert_model_digest("m:test", expected="a" * 64, actual="b" * 64)


def test_complete_requires_exact_twenty_valid_stages(tmp_path):
    identity = official_identity()
    models = [(f"model:{index}", f"{index:064x}") for index in range(10)]
    write_valid_matrix(tmp_path, identity, models)
    assert module._invalid_matrix_stages(tmp_path, identity, models) == []
    stage = module._stage_path(tmp_path, "casa", "model:9", 0)
    stage.unlink()
    assert module._invalid_matrix_stages(tmp_path, identity, models) == [
        "casa/model:9/run_0"
    ]
```

`official_identity()` e `write_valid_matrix()` são helpers completos do próprio
arquivo de teste: o primeiro constrói os dois `DatasetIdentity` com hashes fixos;
o segundo percorre `identity.datasets`, os dez pares `(nome, digest)` e a réplica
zero, gravando com `_write_stage` exatamente o metadata de cada
`StageExpectation`. Assim o teste materializa 20 JSONs, remove um e espera o nome
exato do único estágio inválido.

- [ ] **Step 3: Confirmar RED**

Run: `uv run --frozen --group dev python -m pytest tests/test_run_benchmark.py -q`

Expected: FAIL porque o runner ainda usa prédio+masked, contexto único, PID por
existência e retomada por simples presença de arquivo.

- [ ] **Step 4: Implementar registro e expectativa de estágio**

```python
@dataclass(frozen=True)
class StageExpectation:
    dataset_key: str
    model_name: str
    model_digest: str
    replica_index: int
    execution_identity: dict[str, object]
    execution_identity_sha256: str
    reuse_equivalent: bool
    ifc_sha256: str
    ground_truth_sha256: str
    ids_sha256: str
    prompt_version: str
    cache_enabled: bool
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

O CLI exige `--execution-identity <identity.json>` e aceita somente
`--no-cache` no modo oficial. A função de carga rejeita
campos extras, SHA fora de `^[0-9a-f]{64}$`, ordem/datasets diferente de
`predio,casa`, `replica_count != --replicas`, cache diferente de `False`, reuso
diferente da flag, `prompt_version` diferente de `PROMPT_VERSION`, hash diferente
de `src/suggestion_engine/prompt_templates.py` e divergência ao recalcular
`models.lock.json`, IFC, GT ou IDS. `release_id` e hash do `project.zip` são
conferidos pelo manifesto no instalador e permanecem no snapshot de cada estágio.

`_stage_done` abre e valida o JSON; qualquer ausência, erro de parse ou diferença
em qualquer campo literal acima retorna `False` com log da causa. `_check_digest`
levanta `RuntimeError` em drift. Ao final da fila,
`_invalid_matrix_stages` recompõe os 20 `StageExpectation` e o processo só retorna
0 se a lista for vazia; retorno 0 do subprocesso sem os 20 JSONs válidos é falha.

- [ ] **Step 5: Implementar PID/STOP robustos**

O PID file é JSON com `pid`, `create_time` e token UUID. A primeira aquisição
obrigatoriamente usa `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)`;
dois concorrentes nunca podem considerar o lease adquirido. Usar psutil para
conferir PID, tempo de criação e linha de comando contendo `run_benchmark.py`.
Para colher um registro morto, adquirir também `<pidfile>.reap` com `O_EXCL`,
reler bytes+stat sob esse lease, remover somente se ainda for o registro morto e
tentar a criação exclusiva novamente. No `finally`, remover o PID file somente
se o token ainda for o desta execução.

`StopBaseline` guarda existência, `mtime_ns`, tamanho e SHA-256 no instante de
lançamento. `_stop_requested` retorna `True` somente para arquivo que não existia
e passou a existir ou cujo fingerprint mudou. Antes de cada estágio e depois de
cada exportação, STOP novo retorna 130. Capturar `KeyboardInterrupt` fora do loop,
registrar `interrupted`, descarregar o modelo residente e retornar 130; não
converter interrupção em sucesso nem em falha genérica.

- [ ] **Step 6: Rodar testes e regressões**

Run:

```powershell
uv run --frozen --group dev python -m pytest tests/test_run_benchmark.py tests/experiment/test_runner_harness.py -q
uv run --frozen --group dev python -m ruff check scripts/run_benchmark.py tests/test_run_benchmark.py
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
- Produces: `RemovedField`, `PrivacyFinding`, `FailureCode`, `EvidencePrivacyError`,
  `redact_sensitive`, `sanitize_text_files`, `scan_sensitive_text`,
  `parse_llmfit_recommendations`, `filter_llmfit_recommendations`,
  `build_file_manifest`, `write_manifest`, `validate_manifest`,
  `create_evidence_zip` e `create_partial_evidence_zip`.

- [ ] **Step 1: Escrever testes de privacidade que falham**

```python
def test_redacts_sensitive_keys_and_known_values():
    raw = {"hostname": "PC-KELLER", "nested": {"serial_number": "ABC", "cpu": "Ryzen"}}
    clean, removed = redact_sensitive(raw, forbidden_values={"PC-KELLER"})
    assert clean == {"nested": {"cpu": "Ryzen"}}
    assert {item.path for item in removed} == {"hostname", "nested.serial_number"}


def test_scanner_finds_username_hostname_ipv4_ipv6_mac_and_tokens(tmp_path):
    path = tmp_path / "leak.txt"
    path.write_text(
        "Keller PC-01 192.168.0.2 2001:db8::7 aa:bb:cc:dd:ee:ff "
        "Bearer secret api_key=abc123 token:xyz789",
        encoding="utf-8",
    )
    findings = scan_sensitive_text(tmp_path, forbidden_values={"Keller", "PC-01"})
    assert {finding.kind for finding in findings} >= {
        "known-value", "ipv4", "ipv6", "mac", "bearer-token", "assigned-secret"
    }


def test_sanitizer_redacts_all_patterns_before_scanner_but_allows_loopback(tmp_path):
    path = tmp_path / "runner.log"
    path.write_text(
        r"C:\Users\Keller 10.0.0.4 2001:db8::7 aa-bb-cc-dd-ee-ff "
        "Bearer segredo token=valor local=127.0.0.1 local6=::1",
        encoding="utf-8",
    )
    removed = sanitize_text_files(tmp_path, forbidden_values={"Keller"})
    assert removed
    clean = path.read_text(encoding="utf-8")
    assert all(secret not in clean for secret in
               ["Keller", "10.0.0.4", "2001:db8::7", "aa-bb-cc-dd-ee-ff", "segredo", "valor"])
    assert "127.0.0.1" in clean and "::1" in clean
    assert not scan_sensitive_text(tmp_path, forbidden_values={"Keller"})
```

- [ ] **Step 2: Escrever testes de recomendações, manifesto e ZIP**

```python
def test_filters_models_already_in_project_lock():
    raw = {"models": [
        {"name": "google/gemma-2-9b", "ollama_name": "gemma2:9b", "score": 90},
        {"name": "org/extra-14b", "ollama_name": None, "score": 80},
    ]}
    rows = parse_llmfit_recommendations(raw)
    assert filter_llmfit_recommendations(rows, {"gemma2:9b"}) == [
        {"name": "org/extra-14b", "ollama_name": None, "score": 80}
    ]


def test_manifest_is_sorted_and_hashes_every_payload_file(tmp_path):
    (tmp_path / "z.txt").write_text("z", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    manifest = build_file_manifest(tmp_path)
    assert [entry["path"] for entry in manifest] == ["a.txt", "z.txt"]
    assert manifest[0]["sha256"] == hashlib.sha256(b"a").hexdigest()
    write_manifest(tmp_path / "manifest.json", manifest)
    assert validate_manifest(tmp_path / "manifest.json", tmp_path) == []


def test_zip_rejects_privacy_findings_that_remain_after_sanitizer(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "leak.txt").write_text("PC-PRIVATE", encoding="utf-8")
    monkeypatch.setattr(module, "sanitize_text_files", lambda *args, **kwargs: [])
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
        manifest = json.loads(archive.read("manifest.json"))
        assert {row["path"] for row in manifest["files"]} == {"public.txt"}
        for row in manifest["files"]:
            payload = archive.read(row["path"])
            assert row["size_bytes"] == len(payload)
            assert row["sha256"] == hashlib.sha256(payload).hexdigest()


def test_partial_zip_uses_only_generated_safe_documents(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "scan_sensitive_text",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    output = create_partial_evidence_zip(
        tmp_path / "partial.zip", status="failed",
        reason_code=FailureCode.UV_DOWNLOAD_FAILED,
    )
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {
            "README.txt", "status.json", "privacy-report.json", "manifest.json"
        }
        status = json.loads(archive.read("status.json"))
        assert status == {
            "partial": True, "reason_code": "UV_DOWNLOAD_FAILED", "status": "failed"
        }
```

- [ ] **Step 3: Confirmar RED**

Run: `uv run --frozen --group dev python -m pytest tests/experiment/test_evidence_bundle.py -q`

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


class FailureCode(str, Enum):
    OFFLINE_PREFLIGHT_FAILED = "OFFLINE_PREFLIGHT_FAILED"
    UV_DOWNLOAD_FAILED = "UV_DOWNLOAD_FAILED"
    PYTHON_SYNC_FAILED = "PYTHON_SYNC_FAILED"
    PHASE2_PREFLIGHT_FAILED = "PHASE2_PREFLIGHT_FAILED"
    TOOL_DOWNLOAD_FAILED = "TOOL_DOWNLOAD_FAILED"
    MODEL_PULL_FAILED = "MODEL_PULL_FAILED"
    RUNNER_FAILED = "RUNNER_FAILED"
    PRIVACY_SCAN_FAILED = "PRIVACY_SCAN_FAILED"
    INTERRUPTED = "INTERRUPTED"
    UNKNOWN_FAILED = "UNKNOWN_FAILED"


SENSITIVE_KEYS = re.compile(
    r"(?:user(?:name)?|host(?:name)?|serial|mac|ip_address|token|secret|password|ollama_key)",
    re.IGNORECASE,
)

SENSITIVE_TEXT_PATTERNS = {
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "ipv6": re.compile(
        r"(?<![\w:])(?:[0-9a-f]{1,4}:){2,7}[0-9a-f:]{0,4}(?![\w:])", re.I
    ),
    "mac": re.compile(r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", re.I),
    "bearer-token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.I),
    "assigned-secret": re.compile(
        r"\b(?:api[_-]?key|token|secret|password|ollama[_-]?key)\s*[:=]\s*[^\s,;]+",
        re.I,
    ),
}


def _allowed_local_ip(kind: str, raw: str) -> bool:
    if kind not in {"ipv4", "ipv6"}:
        return False
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


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

`create_evidence_zip` deve rodar a sanitização e depois o scanner antes de escrever, criar
`manifest.json`, usar caminhos relativos e recusar symlinks ou arquivos fora da
raiz. Não incluir `.env`, chaves Ollama, blobs/modelos, IFCs nem executáveis.
`write_manifest` usa JSON UTF-8 indentado com chaves ordenadas;
`validate_manifest(path, root)` recalcula tamanho/hash e retorna uma lista de
erros vazia somente quando não há arquivo ausente, extra ou divergente.

Implementar as funções com as regras literais e os corpos abaixo:

```python
TEXT_SUFFIXES = {".json", ".jsonl", ".txt", ".log", ".yaml", ".yml", ".csv", ".md"}
FORBIDDEN_NAMES = {".env", "id_ed25519", "id_ed25519.pub"}
FORBIDDEN_SUFFIXES = {".ifc", ".ifczip", ".exe", ".dll", ".bin", ".zip"}


def _evidence_files(root: Path) -> list[Path]:
    root_resolved = root.resolve(strict=True)
    files: list[Path] = []
    for candidate in sorted(root.rglob("*")):
        if candidate.is_symlink():
            raise EvidencePrivacyError(f"symlink proibido: {candidate}")
        if not candidate.is_file() or candidate.name == "manifest.json":
            continue
        resolved = candidate.resolve(strict=True)
        if os.path.commonpath((str(root_resolved), str(resolved))) != str(root_resolved):
            raise EvidencePrivacyError(f"arquivo fora da raiz: {candidate}")
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
    findings: list[PrivacyFinding] = []
    for candidate in _evidence_files(root):
        if candidate.suffix.lower() not in TEXT_SUFFIXES:
            continue
        for number, line in enumerate(candidate.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for forbidden in (item for item in forbidden_values if item):
                if forbidden.casefold() in line.casefold():
                    findings.append(PrivacyFinding(candidate.relative_to(root).as_posix(), "known-value", number))
            for kind, pattern in SENSITIVE_TEXT_PATTERNS.items():
                for match in pattern.finditer(line):
                    if _allowed_local_ip(kind, match.group()):
                        continue
                    findings.append(PrivacyFinding(candidate.relative_to(root).as_posix(), kind, number))
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind))


def parse_llmfit_recommendations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("models")
    if not isinstance(rows, list):
        raise ValueError("llmfit JSON deve conter envelope models[]")
    if any(not isinstance(row, dict) or not isinstance(row.get("name"), str)
           or not row["name"].strip() for row in rows):
        raise ValueError("cada modelo llmfit deve ter name não vazio")
    return [dict(row) for row in rows]


def filter_llmfit_recommendations(rows: list[dict[str, Any]], locked: set[str]) \
        -> list[dict[str, Any]]:
    return [
        row for row in rows
        if {str(row["name"]), str(row.get("ollama_name") or "")}.isdisjoint(locked)
    ]


def sanitize_text_files(root: Path, *, forbidden_values: set[str]) -> list[RemovedField]:
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
        for kind, pattern in SENSITIVE_TEXT_PATTERNS.items():
            replacements = 0

            def replace_match(match: re.Match[str], pattern_kind: str = kind) -> str:
                nonlocal replacements
                if _allowed_local_ip(pattern_kind, match.group()):
                    return match.group()
                replacements += 1
                return "[REDACTED]"

            text = pattern.sub(replace_match, text)
            if replacements:
                removed.append(RemovedField(
                    candidate.relative_to(root).as_posix(), f"{kind}:{replacements}"
                ))
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
    sanitize_text_files(root, forbidden_values=forbidden_values)
    findings = scan_sensitive_text(root, forbidden_values=forbidden_values)
    if findings:
        raise EvidencePrivacyError(
            "; ".join(f"{item.kind}:{item.path}:{item.line}" for item in findings)
        )
    payload_files = _evidence_files(root)
    manifest_path = root / "manifest.json"
    write_manifest(manifest_path, [
        {"path": candidate.relative_to(root).as_posix(),
         "size_bytes": candidate.stat().st_size, "sha256": sha256_file(candidate)}
        for candidate in payload_files
    ])
    temporary = output.with_suffix(output.suffix + ".partial")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(manifest_path, "manifest.json")
            for candidate in payload_files:
                archive.write(candidate, candidate.relative_to(root).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            packed_manifest = json.loads(archive.read("manifest.json"))["files"]
            expected_names = {"manifest.json"} | {row["path"] for row in packed_manifest}
            if set(archive.namelist()) != expected_names:
                raise EvidencePrivacyError("arvore ZIP diverge do manifesto")
            for row in packed_manifest:
                payload = archive.read(row["path"])
                digest = hashlib.sha256(payload).hexdigest()
                if len(payload) != row["size_bytes"] or digest != row["sha256"]:
                    raise EvidencePrivacyError(f"hash ZIP diverge: {row['path']}")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output
```

No corpo de `sanitize_text_files`, aplicar primeiro os valores conhecidos e depois
os mesmos cinco padrões do scanner. Para IPs, substituir somente endereços que
não sejam loopback nem unspecified; substituir o match inteiro de MAC, Bearer e
atribuição de segredo por `[REDACTED]`. O scanner é uma verificação posterior,
não o mecanismo primário de remoção.

`create_partial_evidence_zip(output, *, status, reason_code)` aceita somente
`status in {"failed", "interrupted"}` e `reason_code` em uma enum interna de
códigos sem mensagem/caminho livre. Ele monta em memória apenas `README.txt`,
`status.json` e `privacy-report.json` controlados pelo programa, calcula um
`manifest.json` para esses três membros e faz replace atômico do ZIP. Não lê o
diretório bruto, não chama parser/scanner e, portanto, continua disponível quando
a coleta, a sanitização ou o bundle principal falha. Erro de E/S ao criar esse
último recurso é exibido no console sem afirmar que existe um ZIP.

Implementar o fallback somente com bytes gerados:

```python
def create_partial_evidence_zip(
    output: Path, *, status: Literal["failed", "interrupted"], reason_code: FailureCode
) -> Path:
    members = {
        "README.txt": b"Pacote parcial: o benchmark nao foi concluido.\n",
        "status.json": (
            json.dumps({"partial": True, "reason_code": reason_code.value,
                        "status": status}, sort_keys=True) + "\n"
        ).encode("utf-8"),
        "privacy-report.json": b'{"raw_files_included":false,"status":"safe-minimal"}\n',
    }
    manifest = [
        {"path": name, "size_bytes": len(payload),
         "sha256": hashlib.sha256(payload).hexdigest()}
        for name, payload in sorted(members.items())
    ]
    members["manifest.json"] = (
        json.dumps({"files": manifest}, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    temporary = output.with_suffix(output.suffix + ".partial")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(members.items()):
            archive.writestr(name, payload)
    temporary.replace(output)
    return output
```

Para `sha256_file`, importar a implementação streaming já testada de
`src.experiment.ground_truth_validation`. Strings sensíveis encontradas em campos
não removidos são substituídas por `[REDACTED]` antes de serem gravadas. Antes de
`create_evidence_zip`, o orquestrador chama `sanitize_text_files` com usuário,
hostname e caminho do perfil; qualquer ocorrência restante no scanner impede a
criação do ZIP. IPv4 loopback/unspecified é permitido porque identifica somente o
serviço local, não a máquina; a mesma exceção vale para IPv6 `::1` e `::`.

- [ ] **Step 5: Rodar testes e lint**

Run:

```powershell
uv run --frozen --group dev python -m pytest tests/experiment/test_evidence_bundle.py -q
uv run --frozen --group dev python -m ruff check src/experiment/evidence_bundle.py tests/experiment/test_evidence_bundle.py
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
assert len(runs) == 20
assert len({run["metadata"]["execution_identity_sha256"] for run in runs}) == 1
assert not scan_sensitive_text(evidence_root, forbidden_values={username, hostname})
assert validate_manifest(evidence_root / "manifest.json", evidence_root) == []
```

- [ ] **Step 2: Rodar testes focados e suíte completa**

Run:

```powershell
uv run --frozen --group dev python -m pytest tests/experiment/test_runtime_environment.py tests/experiment/test_model_lock.py tests/experiment/test_execution_identity.py tests/experiment/test_runner_harness.py tests/test_run_benchmark.py tests/experiment/test_evidence_bundle.py tests/experiment/test_portable_benchmark_core.py -q
uv run --frozen --group dev python -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: Rodar qualidade estática e checks de lock**

Run:

```powershell
uv lock --check
uv run --frozen --group dev python -m ruff check src/experiment/model_lock.py src/experiment/execution_identity.py src/experiment/evidence_bundle.py src/experiment/metrics.py src/experiment/runner.py scripts/run_benchmark.py tests/experiment/test_model_lock.py tests/experiment/test_execution_identity.py tests/experiment/test_evidence_bundle.py tests/experiment/test_portable_benchmark_core.py tests/test_run_benchmark.py
uv run --frozen --group dev python -m mypy src/experiment/model_lock.py src/experiment/execution_identity.py src/experiment/evidence_bundle.py
git diff --check
```

Expected: PASS. Se mypy expuser erro preexistente fora dos arquivos listados, não
ampliar o comando nem ocultar o resultado.

- [ ] **Step 4: Commit do smoke**

```powershell
git add -- tests/experiment/test_portable_benchmark_core.py
git commit -m "test: verificar nucleo portatil do benchmark"
```
