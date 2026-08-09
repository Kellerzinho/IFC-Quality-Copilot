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
- Um estágio existente só é retomável quando o par indivisível `run_N.json` +
  `run_N_issues.jsonl` é íntegro: o JSON tem todos os metadados esperados e o
  JSONL é UTF-8 estrito, não vazio, termina em newline, contém JSON válido em
  cada linha e tem exatamente `issue_counts.total_issues` linhas.
- Isolar um par inválido é uma transação recuperável: todo erro normal termina
  com os membros juntos nos paths ativos ou numa quarentena finalizada. Se o OS
  impedir essa co-localização, somente journal `recovery_required` é permitido e
  ele bloqueia todo `run_single` até reconciliação comprovada.
- A identidade canônica da execução é imutável e inclui `release_id`, SHA-256 do
  `project.zip` e do `models.lock.json`, ordem e hashes IFC/GT/IDS dos datasets,
  quantidade de réplicas, estado do cache, versão e SHA-256 dos prompts e modo de reuso.
- A matriz oficial só termina como `complete` depois de revalidar 20 pares de
  estágio íntegros: 10 modelos × 2 datasets × 1 réplica; vinte JSONs agregados
  sem seus vinte JSONLs válidos nunca constituem uma matriz completa.
- `BENCHMARK_STOP` criado ou regravado depois do início e `Ctrl+C` encerram com código
  130 e estado `interrupted`; um STOP preexistente permanece inerte.
- Evidências não podem conter usuário, hostname, IP, MAC, seriais, tokens, chaves Ollama ou conteúdo de `.env`.
- ZIP principal e parcial são determinísticos e aceitam somente a allowlist
  textual `.json`, `.jsonl`, `.txt`, `.log`, `.yaml`, `.yml`, `.csv` e `.md`;
  qualquer symlink, path escape ou formato desconhecido falha fechado.
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


def test_partial_and_complete_store_have_exact_space_budgets():
    lock = load_model_lock(LOCK_PATH)
    partial = {model.name: model.digest for model in lock.models[:-1]}
    only_missing = lock.models[-1].size_bytes
    assert required_free_bytes(lock, partial) == (
        only_missing + only_missing + max(only_missing // 10, 4 * 1024**3)
    )
    complete = {model.name: model.digest for model in lock.models}
    assert required_free_bytes(lock, complete) == 0


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
  `QuarantineMember`, `QuarantineJournal`, `QuarantineRecoveryError`,
  `_load_and_validate_execution_identity(path)`,
  `_stage_path(results_root, dataset_key, model, replica) -> Path`,
  `_stage_artifact_paths(json_path) -> tuple[Path, Path]`,
  `_stage_done(json_path, expectation)`,
  `_quarantine_invalid_stage_pair(json_path, results_root) -> Path | None`,
  `_reconcile_quarantine_transactions(results_root) -> None`,
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
    valid_export_paths: set[Path] = set()
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
                metadata=SimpleNamespace(
                    model_name=kwargs["model_name"],
                    replica_index=kwargs["replica_index"],
                ),
                evaluation=SimpleNamespace(accuracy_top1=1.0, accuracy_top3=1.0),
                stability=SimpleNamespace(failed_count=0),
            )

        @staticmethod
        def _export(result, output_root):
            path = (
                Path(output_root) / module._sanitize(result.metadata.model_name)
                / f"run_{result.metadata.replica_index}.json"
            )
            valid_export_paths.add(path)
            return str(path)

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
    monkeypatch.setattr(
        module, "_stage_done", lambda path, expectation: path in valid_export_paths
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


def test_main_revalidates_pair_immediately_after_export(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    monkeypatch.setattr(module.ExperimentRunner, "_export", lambda *args: None)
    assert module.main([
        "--only-model", "m:test", "--no-cache", "--reuse-equivalent",
        "--execution-identity", str(tmp_path / "identity.json"),
        "--results-root", str(tmp_path / "results"),
    ]) == 1
    assert calls
```

Redirecionar `PID_FILE`, `STOP_FILE`, `LOCK_FILE`, IFCs e GTs para `tmp_path`; não
usar Ollama nem IFC real.

- [ ] **Step 2: Escrever testes que falham para retomada e sentinelas**

Cobrir:

```python
import hashlib


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


def _write_stage_pair(
    path: Path,
    metadata: dict[str, object],
    outcomes: list[dict[str, object]] | None = None,
) -> None:
    rows = outcomes or [{"issue_id": "issue-1"}]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "metadata": metadata,
            "issue_counts": {"total_issues": len(rows)},
        }) + "\n",
        encoding="utf-8",
    )
    _, issues_path = module._stage_artifact_paths(path)
    issues_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_stage_done_rejects_corrupt_json(tmp_path):
    path = tmp_path / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    path.write_text("{", encoding="utf-8")
    assert not module._stage_done(path, _expectation())


@pytest.mark.parametrize(
    "damage",
    ["missing", "empty", "invalid_utf8", "truncated", "invalid_json", "blank_line",
     "missing_final_newline", "count_mismatch"],
)
def test_stage_done_rejects_invalid_issues_jsonl(tmp_path, damage):
    expectation = _expectation()
    path = tmp_path / "run_0.json"
    _write_stage_pair(path, asdict(expectation))
    _, issues_path = module._stage_artifact_paths(path)
    if damage == "missing":
        issues_path.unlink()
    elif damage == "empty":
        issues_path.write_bytes(b"")
    elif damage == "invalid_utf8":
        issues_path.write_bytes(b"\xff\n")
    elif damage == "truncated":
        issues_path.write_text('{"issue_id":"issue-1"}\n{"issue_id":', encoding="utf-8")
    elif damage == "invalid_json":
        issues_path.write_text("not-json\n", encoding="utf-8")
    elif damage == "blank_line":
        issues_path.write_text('{"issue_id":"issue-1"}\n\n', encoding="utf-8")
    elif damage == "missing_final_newline":
        issues_path.write_text('{"issue_id":"issue-1"}', encoding="utf-8")
    else:
        issues_path.write_text(
            '{"issue_id":"issue-1"}\n{"issue_id":"extra"}\n', encoding="utf-8"
        )
    assert not module._stage_done(path, expectation)


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
    _write_stage_pair(path, metadata)
    assert not module._stage_done(path, expectation)


def test_stage_done_accepts_exact_metadata(tmp_path):
    expectation = _expectation()
    path = tmp_path / "run_0.json"
    _write_stage_pair(path, asdict(expectation))
    assert module._stage_done(path, expectation)


def test_stage_done_rejects_nested_execution_identity_change(tmp_path):
    expectation = _expectation()
    metadata = asdict(expectation)
    metadata["execution_identity"]["project_sha256"] = "9" * 64
    path = tmp_path / "run_0.json"
    _write_stage_pair(path, metadata)
    assert not module._stage_done(path, expectation)


def test_invalid_stage_pair_is_quarantined_as_a_unit_before_rerun(tmp_path):
    expectation = _expectation()
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(expectation))
    _, issues_path = module._stage_artifact_paths(path)
    issues_path.write_text('{"issue_id":', encoding="utf-8")

    quarantine = module._quarantine_invalid_stage_pair(path, results_root)

    assert quarantine is not None
    assert not path.exists() and not issues_path.exists()
    assert (quarantine / path.name).is_file()
    assert (quarantine / issues_path.name).is_file()


@pytest.mark.parametrize("missing_member", ["json", "jsonl"])
def test_partial_stage_quarantines_whichever_member_exists(tmp_path, missing_member):
    expectation = _expectation()
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(expectation))
    _, issues_path = module._stage_artifact_paths(path)
    missing_path = path if missing_member == "json" else issues_path
    existing_path = issues_path if missing_member == "json" else path
    missing_path.unlink()

    quarantine = module._quarantine_invalid_stage_pair(path, results_root)

    assert quarantine is not None
    assert not path.exists() and not issues_path.exists()
    assert (quarantine / existing_path.name).is_file()
    assert not (quarantine / missing_path.name).exists()


def test_first_move_failure_keeps_pair_co_located_active(monkeypatch, tmp_path):
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    _, issues_path = module._stage_artifact_paths(path)
    before = (path.read_bytes(), issues_path.read_bytes())
    real_replace = os.replace
    failed = False

    def fail_first_active_move_once(source, destination):
        nonlocal failed
        if Path(source) == path and not failed:
            failed = True
            raise OSError("busy")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_first_active_move_once)
    with pytest.raises(RuntimeError, match="quarentena"):
        module._quarantine_invalid_stage_pair(path, results_root)

    assert (path.read_bytes(), issues_path.read_bytes()) == before
    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    assert not list(quarantine_root.rglob("*.journal.json"))


def test_second_move_failure_rolls_back_pair_to_active_paths(monkeypatch, tmp_path):
    expectation = _expectation()
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(expectation))
    _, issues_path = module._stage_artifact_paths(path)
    before = (path.read_bytes(), issues_path.read_bytes())
    real_replace = os.replace
    failed_second_move = False

    def fail_second_active_move_once(source, destination):
        nonlocal failed_second_move
        if Path(source) == issues_path and not failed_second_move:
            failed_second_move = True
            raise OSError("busy")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second_active_move_once)

    with pytest.raises(RuntimeError, match="quarentena"):
        module._quarantine_invalid_stage_pair(path, results_root)

    assert (path.read_bytes(), issues_path.read_bytes()) == before
    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    assert not list(quarantine_root.rglob(path.name))
    assert not list(quarantine_root.rglob(issues_path.name))
    assert not list(quarantine_root.rglob("*.journal.json"))


def test_rollback_failure_finishes_quarantine_before_raising(monkeypatch, tmp_path):
    results_root = tmp_path / "results"
    path = results_root / "casa" / "m_test" / "run_0.json"
    _write_stage_pair(path, asdict(_expectation()))
    _, issues_path = module._stage_artifact_paths(path)
    before = (path.read_bytes(), issues_path.read_bytes())
    before_sha256 = tuple(hashlib.sha256(payload).hexdigest() for payload in before)
    real_replace = os.replace
    failed = {"second_move": False, "rollback": False}

    def fail_once_then_allow_forward_recovery(source, destination):
        source = Path(source)
        destination = Path(destination)
        if source == issues_path and not failed["second_move"]:
            failed["second_move"] = True
            raise OSError("second move")
        if destination == path and not failed["rollback"]:
            failed["rollback"] = True
            raise OSError("rollback")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_once_then_allow_forward_recovery)
    with pytest.raises(RuntimeError, match="quarentena"):
        module._quarantine_invalid_stage_pair(path, results_root)

    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    json_copies = list(quarantine_root.rglob(path.name))
    jsonl_copies = list(quarantine_root.rglob(issues_path.name))
    assert len(json_copies) == len(jsonl_copies) == 1
    assert json_copies[0].parent == jsonl_copies[0].parent
    assert not json_copies[0].parent.name.endswith(".partial")
    after = (json_copies[0].read_bytes(), jsonl_copies[0].read_bytes())
    after_sha256 = tuple(hashlib.sha256(payload).hexdigest() for payload in after)
    assert after == before
    assert after_sha256 == before_sha256
    assert not path.exists() and not issues_path.exists()
    assert not list(quarantine_root.rglob("*.journal.json"))


def _leave_unresolved_split_transaction(monkeypatch, path, results_root):
    _, issues_path = module._stage_artifact_paths(path)
    real_replace = os.replace

    def fail_second_move_and_rollback(source, destination):
        source = Path(source)
        destination = Path(destination)
        if source == issues_path or destination == path:
            raise OSError("locked")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second_move_and_rollback)
    with pytest.raises(module.QuarantineRecoveryError, match="recovery_required"):
        module._quarantine_invalid_stage_pair(path, results_root)
    return issues_path


def test_rollback_failure_persists_recovery_journal_and_blocks_runner(
        monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    results_root = tmp_path / "results"
    path = module._stage_path(results_root, "casa", "m:test", 0)
    _write_stage_pair(path, asdict(_expectation()))
    issues_path = _leave_unresolved_split_transaction(monkeypatch, path, results_root)
    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    journals = list(quarantine_root.rglob("*.journal.json"))
    assert len(journals) == 1
    assert json.loads(journals[0].read_text(encoding="utf-8"))["state"] == (
        "recovery_required"
    )
    assert not path.exists() and issues_path.exists()

    assert module.main([
        "--only-model", "m:test", "--no-cache", "--reuse-equivalent",
        "--execution-identity", str(tmp_path / "identity.json"),
        "--results-root", str(results_root),
    ]) == 1
    assert calls == []
    journals_after = list(quarantine_root.rglob("*.journal.json"))
    assert journals_after == journals
    assert json.loads(journals_after[0].read_text(encoding="utf-8"))["state"] == (
        "recovery_required"
    )


def test_next_invocation_reconciles_split_before_any_run_single(monkeypatch, tmp_path):
    results_root = tmp_path / "results"
    path = module._stage_path(results_root, "casa", "m:test", 0)
    _write_stage_pair(path, asdict(_expectation()))
    _, original_issues_path = module._stage_artifact_paths(path)
    before = (path.read_bytes(), original_issues_path.read_bytes())
    before_sha256 = tuple(hashlib.sha256(payload).hexdigest() for payload in before)
    with monkeypatch.context() as transaction_fault:
        issues_path = _leave_unresolved_split_transaction(
            transaction_fault, path, results_root
        )

    calls = install_fake_runner(monkeypatch, tmp_path)
    original_run_single = module.ExperimentRunner.run_single
    original_acquire_pidfile = module._acquire_pidfile
    original_reconcile = module._reconcile_quarantine_transactions
    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    acquired_tokens: list[str] = []
    reconcile_tokens: list[str] = []

    def capture_owned_pid_lease(pid_path):
        lease = original_acquire_pidfile(pid_path)
        assert lease is not None
        acquired_tokens.append(lease.token)
        return lease

    def assert_owned_pid_lease_during_reconcile(root):
        assert acquired_tokens
        record = json.loads(module.PID_FILE.read_text(encoding="utf-8"))
        assert record["pid"] == os.getpid()
        assert record["token"] == acquired_tokens[-1]
        reconcile_tokens.append(record["token"])
        return original_reconcile(root)

    def assert_reconciled_before_runner(self, **kwargs):
        json_copies = list(quarantine_root.rglob(path.name))
        jsonl_copies = list(quarantine_root.rglob(issues_path.name))
        assert len(json_copies) == len(jsonl_copies) == 1
        assert json_copies[0].parent == jsonl_copies[0].parent
        assert not json_copies[0].parent.name.endswith(".partial")
        after = (json_copies[0].read_bytes(), jsonl_copies[0].read_bytes())
        after_sha256 = tuple(hashlib.sha256(payload).hexdigest() for payload in after)
        assert after == before
        assert after_sha256 == before_sha256
        assert not path.exists() and not issues_path.exists()
        assert not list(quarantine_root.rglob("*.journal.json"))
        return original_run_single(self, **kwargs)

    monkeypatch.setattr(module, "_acquire_pidfile", capture_owned_pid_lease)
    monkeypatch.setattr(
        module, "_reconcile_quarantine_transactions",
        assert_owned_pid_lease_during_reconcile,
    )
    monkeypatch.setattr(
        module.ExperimentRunner, "run_single", assert_reconciled_before_runner
    )
    assert module.main([
        "--only-model", "m:test", "--no-cache", "--reuse-equivalent",
        "--execution-identity", str(tmp_path / "identity.json"),
        "--results-root", str(results_root),
    ]) == 0
    assert reconcile_tokens == acquired_tokens
    assert not module.PID_FILE.exists()
    assert {call["dataset_key"] for call in calls} == {"predio", "casa"}


def test_main_quarantines_both_old_members_before_rerun(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    results_root = tmp_path / "results"
    path = module._stage_path(results_root, "casa", "m:test", 0)
    _write_stage_pair(path, asdict(_expectation()))
    _, issues_path = module._stage_artifact_paths(path)
    issues_path.write_text('{"issue_id":', encoding="utf-8")
    original_run_single = module.ExperimentRunner.run_single

    def assert_isolated_before_rerun(self, **kwargs):
        if kwargs["dataset_key"] == "casa":
            assert not path.exists() and not issues_path.exists()
        return original_run_single(self, **kwargs)

    monkeypatch.setattr(module.ExperimentRunner, "run_single", assert_isolated_before_rerun)
    assert module.main([
        "--only-model", "m:test", "--no-cache", "--reuse-equivalent",
        "--execution-identity", str(tmp_path / "identity.json"),
        "--results-root", str(results_root),
    ]) == 0
    quarantine_root = results_root.parent / ".invalid-stage-artifacts"
    assert len(list(quarantine_root.rglob(path.name))) == 1
    assert len(list(quarantine_root.rglob(issues_path.name))) == 1
    assert {call["dataset_key"] for call in calls} == {"predio", "casa"}


def test_main_never_reruns_stage_when_quarantine_fails(monkeypatch, tmp_path):
    calls = install_fake_runner(monkeypatch, tmp_path)
    results_root = tmp_path / "results"
    path = module._stage_path(results_root, "casa", "m:test", 0)
    _write_stage_pair(path, asdict(_expectation()))
    real_quarantine = module._quarantine_invalid_stage_pair

    def fail_target_stage(json_path, root):
        if json_path == path:
            raise RuntimeError("quarentena indisponível")
        return real_quarantine(json_path, root)

    monkeypatch.setattr(module, "_quarantine_invalid_stage_pair", fail_target_stage)
    assert module.main([
        "--only-model", "m:test", "--no-cache", "--reuse-equivalent",
        "--execution-identity", str(tmp_path / "identity.json"),
        "--results-root", str(results_root),
    ]) == 1
    assert all(call["dataset_key"] != "casa" for call in calls)


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


@pytest.mark.parametrize("missing_member", ["json", "jsonl"])
def test_complete_requires_exact_twenty_valid_stage_pairs(tmp_path, missing_member):
    identity = official_identity()
    models = [(f"model:{index}", f"{index:064x}") for index in range(10)]
    write_valid_matrix(tmp_path, identity, models)
    assert module._invalid_matrix_stages(tmp_path, identity, models) == []
    stage = module._stage_path(tmp_path, "casa", "model:9", 0)
    _, issues_path = module._stage_artifact_paths(stage)
    (stage if missing_member == "json" else issues_path).unlink()
    assert module._invalid_matrix_stages(tmp_path, identity, models) == [
        "casa/model:9/run_0"
    ]


@pytest.mark.parametrize("extra_shape", ["pair", "json_only", "jsonl_only"])
def test_complete_rejects_unexpected_stage_pair_or_orphan(tmp_path, extra_shape):
    identity = official_identity()
    models = [(f"model:{index}", f"{index:064x}") for index in range(10)]
    write_valid_matrix(tmp_path, identity, models)
    extra = module._stage_path(tmp_path, "casa", "model:9", 1)
    _write_stage_pair(extra, asdict(_expectation()))
    _, extra_jsonl = module._stage_artifact_paths(extra)
    if extra_shape == "json_only":
        extra_jsonl.unlink()
    elif extra_shape == "jsonl_only":
        extra.unlink()
    relative_stem = extra.relative_to(tmp_path).as_posix().removesuffix(".json")

    assert module._invalid_matrix_stages(tmp_path, identity, models) == [
        f"unexpected:{relative_stem}"
    ]
```

`official_identity()` e `write_valid_matrix()` são helpers completos do próprio
arquivo de teste: o primeiro constrói os dois `DatasetIdentity` com hashes fixos;
o segundo percorre `identity.datasets`, os dez pares `(nome, digest)` e a réplica
zero, gravando com `_write_stage_pair` exatamente o metadata de cada
`StageExpectation`, `issue_counts.total_issues` e pelo menos uma linha JSON de
outcome. Assim o teste materializa 20 pares, remove alternadamente o JSON ou o
JSONL de um deles e espera o nome exato do único estágio inválido. O helper nunca
cria um JSON sem o JSONL correspondente, para que os testes de matriz não possam
aprovar por presença isolada do agregado. O segundo teste acrescenta um 21º stem
como par completo ou órfão em cada direção e exige um único diagnóstico
`unexpected:<stem>`.

Nos testes de recuperação forward e de relançamento, capturar antes da falha os
bytes e SHA-256 de agregado e JSONL separadamente e comparar os mesmos dois valores
no diretório final. No relançamento, o wrapper de `_acquire_pidfile` captura o token
do lease; o wrapper de `_reconcile_quarantine_transactions` só delega depois de
provar que o PID file contém o PID atual e exatamente esse token.

- [ ] **Step 3: Confirmar RED**

Run: `uv run --frozen --group dev python -m pytest tests/test_run_benchmark.py -q`

Expected: FAIL porque o runner ainda usa prédio+masked, contexto único, PID por
existência e retomada por simples presença do JSON agregado; os testes de JSONL
ausente, vazio, truncado, não UTF-8, inválido e com contagem divergente também
permanecem RED. Os testes de segundo move, rollback, journal
`recovery_required` e reconciliação antes de `run_single` também ficam RED.

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


class QuarantineMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["aggregate", "issues"]
    source_relative: str
    size_bytes: int
    sha256: str


class QuarantineJournal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    transaction_id: UUID
    state: Literal["prepared", "moving", "recovery_required", "finalized"]
    results_root_relative: str
    staging_relative: str
    final_relative: str
    members: tuple[QuarantineMember, ...]


class QuarantineRecoveryError(RuntimeError):
    """A fila não pode executar enquanto a transação não for reconciliada."""
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

`_stage_artifact_paths` recebe o caminho canônico `run_N.json` e deriva exatamente
o par `(run_N.json, run_N_issues.jsonl)`. `_stage_done` abre e valida ambos. O JSON
agregado deve ter metadata literal idêntico ao esperado e
`issue_counts.total_issues` inteiro maior que zero. O JSONL deve ser decodificável
como UTF-8 estrito, ter tamanho maior que zero, terminar com `\n`, não ter linhas
vazias, conter `json.loads` válido em cada linha e ter exatamente a quantidade de
linhas declarada no agregado. Ausência ou erro em qualquer membro, metadata
divergente, truncamento, conteúdo não UTF-8, linha inválida ou contagem diferente
retorna `False` com log da causa.

Antes de examinar qualquer estágio, depois de adquirir o PID lease e antes da
primeira chamada de digest, `run_single` ou exportação, `main` chama
`_reconcile_quarantine_transactions(results_root)`. Journal inválido, path escape,
hash/tamanho divergente, membro duplicado/ausente ou falha que impeça co-localizar
o conjunto originalmente presente levanta `QuarantineRecoveryError`; `main`
registra o marcador literal `QUARANTINE_RECOVERY_REQUIRED` sem paths absolutos,
retorna 1, conserva o journal e não chama nenhum `run_single` nessa invocação.

Se `_stage_done` retornar `False` e qualquer membro antigo existir, o loop chama
`_quarantine_invalid_stage_pair` antes de `run_single`. A raiz transacional é
`results_root.parent / ".invalid-stage-artifacts"`, portanto fica no mesmo volume
e fora da matriz viva. Para cada UUID, criar:

- `.transactions/<uuid>.journal.json`, escrito por temporário, `flush`, `os.fsync`
  e `os.replace` antes do primeiro movimento;
- `.transactions/<uuid>.partial/`, staging dos membros;
- `quarantine/<uuid>/`, único destino final.

O journal guarda somente paths relativos a `results_root.parent`, os membros que
realmente existiam, tamanho e SHA-256 pré-movimento. Rejeitar campos
extras, paths absolutos, `..`, symlinks e qualquer source/destination fora das
raízes esperadas. Mover cada membro ativo para o staging com `os.replace`, sem
sobrescrever destino existente, após persistir estado `moving` e verificando
tamanho/hash depois de cada passo.
Quando todos os membros originalmente presentes estiverem no mesmo staging e
nenhum permanecer ativo, renomear o diretório staging inteiro para o destino final
com um único `os.replace`, verificar novamente, persistir `finalized` e só então
remover o journal.

Se um movimento falhar, tentar rollback compensatório de todo membro já movido.
Rollback comprovado significa todos os membros nos sources originais, nenhum no
staging/final e hashes idênticos; remover journal/staging e levantar `RuntimeError`
para impedir a reexecução nesta invocação. Se o rollback falhar, tentar completar
para frente: mover os membros ainda ativos ao mesmo staging e finalizar o diretório
como acima. Recuperação forward comprovada também remove o journal, mas ainda
levanta `RuntimeError` e não executa o estágio nesta invocação. Somente se nenhuma
direção conseguir co-localizar/provar o conjunto, persistir atomicamente estado
`recovery_required`, levantar `QuarantineRecoveryError` e deixar a fila bloqueada.
Nunca apagar bytes nem aceitar um membro ativo e outro em staging como resultado
normal de erro.

`_reconcile_quarantine_transactions` processa journals em ordem lexical. Para
cada membro, localiza exatamente uma cópia válida entre source, staging e final.
Se todos estiverem ativos, conclui o rollback e limpa a transação; se todos já
estiverem no final, apenas valida e limpa o journal; se houver split source/staging,
prefere completar para frente e renomear o staging inteiro. Se forward falhar,
tenta rollback integral. Qualquer estado ambíguo ou ainda dividido após essas
tentativas mantém `recovery_required` e bloqueia a fila. Isso também torna seguro
um crash entre a renomeação final e a remoção do journal. Pares parciais usam o
mesmo protocolo, considerando somente os membros registrados como presentes.

Depois de `ExperimentRunner._export`, o loop chama `_stage_done` novamente e trata
o estágio como falho se o novo par não passar integralmente; só então incrementa
`completed`.

`_check_digest` levanta `RuntimeError` em drift. Ao final da fila,
`_invalid_matrix_stages` recompõe os 20 `StageExpectation`, usa `_stage_done` para
cada par e também percorre recursivamente somente nomes que casem exatamente
`run_\d+\.json` ou `run_\d+_issues\.jsonl`. Normaliza ambos os sufixos para um
stem relativo POSIX, compara o conjunto encontrado ao conjunto esperado e emite
uma única entrada ordenada `unexpected:<stem>` para cada par extra ou órfão; JSONs
de relatório com outros nomes são ignorados. O processo só retorna 0 quando há os
20 stems esperados, cada qual com os dois membros válidos, e nenhum stem de estágio
inesperado; retorno 0 do subprocesso sem essa cardinalidade exata é falha.

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
- Produces: `RemovedField`, `PrivacyFinding`, `FailureCode`,
  `EvidencePrivacyError`, `EvidenceManifestError`, `collect_forbidden_values`,
  `failure_code_for_exception`, `redact_sensitive`, `sanitize_text_files`, `scan_sensitive_text`,
  `parse_llmfit_recommendations`, `filter_llmfit_recommendations`,
  `build_file_manifest`, `write_manifest`, `validate_manifest`,
  `validate_evidence_archive`,
  `create_evidence_zip` e `create_partial_evidence_zip`.

- [ ] **Step 1: Escrever testes de privacidade que falham**

```python
import hashlib
import json
import os
from pathlib import Path
import zipfile

import pytest

from src.experiment import evidence_bundle as module
from src.experiment.evidence_bundle import (
    EvidenceManifestError,
    EvidencePrivacyError,
    FailureCode,
    build_file_manifest,
    collect_forbidden_values,
    create_evidence_zip,
    create_partial_evidence_zip,
    failure_code_for_exception,
    filter_llmfit_recommendations,
    parse_llmfit_recommendations,
    redact_sensitive,
    sanitize_text_files,
    scan_sensitive_text,
    validate_evidence_archive,
    validate_manifest,
    write_manifest,
)


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


def test_json_and_jsonl_scanner_find_unknown_sensitive_keys_even_with_null_value(tmp_path):
    (tmp_path / "legacy.json").write_text(
        '{"hostname":"NEVER-SEEN-PC"}\n', encoding="utf-8"
    )
    (tmp_path / "legacy.jsonl").write_text(
        '{"safe":1}\n{"api_key":null}\n{"serial_number":42}\n', encoding="utf-8"
    )
    findings = scan_sensitive_text(tmp_path, forbidden_values=set())
    assert {(item.path, item.kind, item.line) for item in findings} >= {
        ("legacy.json", "sensitive-key", 1),
        ("legacy.jsonl", "sensitive-key", 2),
        ("legacy.jsonl", "sensitive-key", 3),
    }


def test_json_scanner_is_fail_closed_when_structured_payload_is_invalid(tmp_path):
    (tmp_path / "broken.json").write_text('{"hostname":', encoding="utf-8")
    with pytest.raises(EvidencePrivacyError, match="JSON invalido"):
        scan_sensitive_text(tmp_path, forbidden_values=set())


def test_ipv6_candidates_are_validated_so_times_and_versions_survive(tmp_path):
    path = tmp_path / "versions.log"
    path.write_text(
        "clock=12:34:56 version=1:2:3 address=2001:db8::7 "
        "compressed=fe80::1 short=::2 mapped=::ffff:192.0.2.1 loop=::1\n",
        encoding="utf-8",
    )
    findings = scan_sensitive_text(tmp_path, forbidden_values=set())
    ipv6 = [item for item in findings if item.kind == "ipv6"]
    assert len(ipv6) == 4
    sanitize_text_files(tmp_path, forbidden_values=set())
    clean = path.read_text(encoding="utf-8")
    assert "12:34:56" in clean and "1:2:3" in clean
    assert all(address not in clean for address in (
        "2001:db8::7", "fe80::1", "::2", "::ffff:192.0.2.1",
    ))
    assert "::1" in clean


def test_collects_nonempty_secret_and_dotenv_values_without_output(
        tmp_path, caplog, capsys):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "TOKEN=dotenv-secret\nEMPTY=\nQUOTED='quoted-secret'\n", encoding="utf-8"
    )
    values = collect_forbidden_values(
        {"OPENAI_API_KEY": "process-secret", "EMPTY_SECRET": "", "PATH": "safe-path"},
        dotenv_paths=(dotenv,),
        base_values={"PC-01", ""},
    )
    assert values == {"PC-01", "process-secret", "dotenv-secret", "quoted-secret"}
    assert not caplog.records
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("bad_name", ["weights.gguf", "payload.bin", "helper.exe", ".env"])
def test_unknown_binary_and_forbidden_names_are_rejected(tmp_path, bad_name):
    (tmp_path / bad_name).write_bytes(b"not evidence")
    with pytest.raises(EvidencePrivacyError, match="nao permitido"):
        build_file_manifest(tmp_path)


@pytest.mark.parametrize("payload", [b"\xff\xfe\x00\x01", b"valid utf8\x00binary"])
def test_allowed_suffix_still_rejects_non_utf8_or_nul_binary(tmp_path, payload):
    (tmp_path / "renamed.txt").write_bytes(payload)
    with pytest.raises(EvidencePrivacyError, match="texto UTF-8 invalido"):
        scan_sensitive_text(tmp_path, forbidden_values=set())


def test_symlink_is_rejected_without_requiring_windows_symlink_privilege(tmp_path, monkeypatch):
    linked = tmp_path / "linked.txt"
    linked.write_text("safe", encoding="utf-8")
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda self: self == linked or original(self)
    )
    with pytest.raises(EvidencePrivacyError, match="symlink"):
        build_file_manifest(tmp_path)


def test_resolved_path_escape_is_rejected(tmp_path, monkeypatch):
    escaped = tmp_path / "escaped.txt"
    escaped.write_text("safe", encoding="utf-8")
    outside = tmp_path.parent / "outside.txt"
    original = Path.resolve

    def fake_resolve(self, *args, **kwargs):
        return outside if self == escaped else original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    with pytest.raises(EvidencePrivacyError, match="fora da raiz"):
        build_file_manifest(tmp_path)
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


@pytest.mark.parametrize("damage", ["altered", "missing", "extra"])
def test_manifest_rejects_altered_missing_and_extra_payload(tmp_path, damage):
    payload = tmp_path / "payload.txt"
    payload.write_text("original", encoding="utf-8")
    write_manifest(tmp_path / "manifest.json", build_file_manifest(tmp_path))
    if damage == "altered":
        payload.write_text("tampered", encoding="utf-8")
    elif damage == "missing":
        payload.unlink()
    else:
        (tmp_path / "extra.txt").write_text("extra", encoding="utf-8")
    assert validate_manifest(tmp_path / "manifest.json", tmp_path)


def test_zip_rejects_privacy_findings_that_remain_after_sanitizer(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "leak.txt").write_text("PC-PRIVATE", encoding="utf-8")
    monkeypatch.setattr(module, "sanitize_text_files", lambda *args, **kwargs: [])
    with pytest.raises(EvidencePrivacyError, match="known-value"):
        create_evidence_zip(
            evidence, tmp_path / "result.zip", forbidden_values={"PC-PRIVATE"}
        )


def test_zip_fails_closed_on_unknown_hostname_if_sanitizer_misses_it(
        tmp_path, monkeypatch):
    evidence = tmp_path / "legacy"
    evidence.mkdir()
    (evidence / "hardware.json").write_text(
        '{"hostname":"UNSEEN-LEGACY-HOST"}\n', encoding="utf-8"
    )
    monkeypatch.setattr(module, "sanitize_text_files", lambda *args, **kwargs: [])
    with pytest.raises(EvidencePrivacyError, match="sensitive-key"):
        create_evidence_zip(evidence, tmp_path / "result.zip", forbidden_values=set())


def test_zip_explicitly_excludes_existing_output_and_stale_partial(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "public.txt").write_text("ok", encoding="utf-8")
    output = evidence / "result.zip"
    output.write_bytes(b"old output")
    output.with_suffix(".zip.partial").write_bytes(b"stale partial")
    create_evidence_zip(evidence, output, forbidden_values=set())
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ["manifest.json", "public.txt"]
        manifest = json.loads(archive.read("manifest.json"))
        assert {row["path"] for row in manifest["files"]} == {"public.txt"}
        for row in manifest["files"]:
            payload = archive.read(row["path"])
            assert row["size_bytes"] == len(payload)
            assert row["sha256"] == hashlib.sha256(payload).hexdigest()


def test_main_zip_bytes_ignore_source_mtime_and_use_fixed_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "sanitize_text_files", lambda *args, **kwargs: [])
    roots = [tmp_path / "first", tmp_path / "second"]
    outputs = [tmp_path / "first.zip", tmp_path / "second.zip"]
    expected_mtimes = [1_600_000_000, 1_600_010_000]
    for index, root in enumerate(roots):
        root.mkdir()
        payload = root / "payload.json"
        payload.write_text('{"safe":true}\n', encoding="utf-8")
        os.utime(payload, (expected_mtimes[index],) * 2)
        create_evidence_zip(root, outputs[index], forbidden_values=set())
        assert payload.stat().st_mtime == expected_mtimes[index]
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    with zipfile.ZipFile(outputs[0]) as archive:
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert (info.external_attr >> 16) & 0o777 == 0o644


def make_valid_evidence_archive(tmp_path):
    source = tmp_path / "archive-source"
    source.mkdir()
    (source / "payload.txt").write_text("original", encoding="utf-8")
    output = tmp_path / "valid.zip"
    return create_evidence_zip(source, output, forbidden_values=set())


def rewrite_archive_with_damage(path, damage):
    with zipfile.ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    if damage == "altered":
        members["payload.txt"] = b"tampered"
    elif damage == "missing":
        members.pop("payload.txt")
    else:
        members["extra.txt"] = b"extra"
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


@pytest.mark.parametrize("damage", ["altered", "missing", "extra"])
def test_archive_manifest_rejects_altered_missing_and_extra_members(tmp_path, damage):
    archive_path = make_valid_evidence_archive(tmp_path)
    rewrite_archive_with_damage(archive_path, damage)
    assert validate_evidence_archive(archive_path)


def test_partial_zip_uses_only_generated_safe_documents(tmp_path, monkeypatch):
    for name in ("_evidence_files", "sanitize_text_files", "scan_sensitive_text"):
        monkeypatch.setattr(
            module, name, lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError())
        )
    outputs = [tmp_path / "partial-a.zip", tmp_path / "partial-b.zip"]
    outputs[0].with_suffix(".zip.partial").write_bytes(b"stale")
    for output in outputs:
        create_partial_evidence_zip(
            output, status="failed", reason_code=FailureCode.UV_DOWNLOAD_FAILED,
        )
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    with zipfile.ZipFile(outputs[0]) as archive:
        assert set(archive.namelist()) == {
            "README.txt", "status.json", "privacy-report.json", "manifest.json"
        }
        status = json.loads(archive.read("status.json"))
        assert status == {
            "partial": True, "reason_code": "UV_DOWNLOAD_FAILED", "status": "failed"
        }
        assert validate_evidence_archive(outputs[0]) == []
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0)
                   for info in archive.infolist())
        assert all((info.external_attr >> 16) & 0o777 == 0o644
                   for info in archive.infolist())


@pytest.mark.parametrize("status", ["complete", "running", "", None])
def test_partial_rejects_invalid_status(tmp_path, status):
    with pytest.raises(ValueError, match="status parcial invalido"):
        create_partial_evidence_zip(
            tmp_path / "partial.zip", status=status,
            reason_code=FailureCode.UV_DOWNLOAD_FAILED,
        )


def test_partial_requires_failure_code_enum_and_verifies_reopened_archive(
        tmp_path, monkeypatch):
    with pytest.raises(TypeError, match="FailureCode"):
        create_partial_evidence_zip(
            tmp_path / "wrong.zip", status="failed", reason_code="UV_DOWNLOAD_FAILED"
        )
    monkeypatch.setattr(module, "validate_evidence_archive", lambda path: ["hash mismatch"])
    with pytest.raises(EvidenceManifestError, match="hash mismatch"):
        create_partial_evidence_zip(
            tmp_path / "invalid.zip", status="failed",
            reason_code=FailureCode.UV_DOWNLOAD_FAILED,
        )


def test_archive_reopen_io_error_is_not_reclassified_as_manifest(tmp_path, monkeypatch):
    def raise_io(_path):
        raise OSError("disk read")

    monkeypatch.setattr(module, "validate_evidence_archive", raise_io)
    with pytest.raises(OSError, match="disk read"):
        create_partial_evidence_zip(
            tmp_path / "io.zip", status="failed",
            reason_code=FailureCode.UV_DOWNLOAD_FAILED,
        )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (EvidencePrivacyError("privacy"), FailureCode.PRIVACY_SCAN_FAILED),
        (EvidenceManifestError("manifest"), FailureCode.EVIDENCE_MANIFEST_FAILED),
        (OSError("disk"), FailureCode.EVIDENCE_IO_FAILED),
        (RuntimeError("other"), FailureCode.UNKNOWN_FAILED),
    ],
)
def test_evidence_failure_code_mapping_is_total_and_ordered(error, expected):
    assert failure_code_for_exception(error) is expected
```

- [ ] **Step 3: Confirmar RED**

Run: `uv run --frozen --group dev python -m pytest tests/experiment/test_evidence_bundle.py -q`

Expected: FAIL por módulo ausente.

- [ ] **Step 4: Implementar APIs puras e determinísticas**

```python
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Literal
import zipfile

from src.experiment.ground_truth_validation import sha256_file


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


class EvidenceManifestError(ValueError):
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
    EVIDENCE_MANIFEST_FAILED = "EVIDENCE_MANIFEST_FAILED"
    EVIDENCE_IO_FAILED = "EVIDENCE_IO_FAILED"
    INTERRUPTED = "INTERRUPTED"
    UNKNOWN_FAILED = "UNKNOWN_FAILED"


SENSITIVE_KEYS = re.compile(
    r"(?:user(?:name)?|host(?:name)?|serial|mac|ip_address|api[_-]?key|token|secret|password|ollama_key)",
    re.IGNORECASE,
)
SECRET_ENV_KEYS = re.compile(
    r"(?:TOKEN|SECRET|PASSWORD|API[_-]?KEY|OLLAMA[_-]?KEY)", re.IGNORECASE
)

SENSITIVE_TEXT_PATTERNS = {
    "ipv6": re.compile(
        r"(?<![\w:.])\[?[0-9a-f:.]*:[0-9a-f:.]+\]?(?![\w:.])", re.I
    ),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "mac": re.compile(r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", re.I),
    "bearer-token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.I),
    "assigned-secret": re.compile(
        r"\b(?:api[_-]?key|token|secret|password|ollama[_-]?key)\s*[:=]\s*[^\s,;]+",
        re.I,
    ),
}


def _parsed_ip_candidate(kind: str, raw: str) -> ipaddress.IPv4Address \
        | ipaddress.IPv6Address | None:
    if kind not in {"ipv4", "ipv6"}:
        return None
    try:
        address = ipaddress.ip_address(raw.strip("[]"))
    except ValueError:
        return None
    if (kind == "ipv4") != isinstance(address, ipaddress.IPv4Address):
        return None
    return address


def _allowed_local_ip(kind: str, raw: str) -> bool:
    address = _parsed_ip_candidate(kind, raw)
    return bool(address and (address.is_loopback or address.is_unspecified))


def collect_forbidden_values(
    environment: Mapping[str, str], *, dotenv_paths: Iterable[Path] = (),
    base_values: Iterable[str] = (),
) -> set[str]:
    values = {str(value) for value in base_values if str(value)}
    values.update(
        value for key, value in environment.items()
        if SECRET_ENV_KEYS.search(key) and value
    )
    for dotenv in dotenv_paths:
        if not dotenv.is_file():
            continue
        for raw_line in dotenv.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            _, raw_value = line.removeprefix("export ").split("=", 1)
            value = raw_value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if value:
                values.add(value)
    return values


def failure_code_for_exception(error: BaseException) -> FailureCode:
    if isinstance(error, EvidencePrivacyError):
        return FailureCode.PRIVACY_SCAN_FAILED
    if isinstance(error, EvidenceManifestError):
        return FailureCode.EVIDENCE_MANIFEST_FAILED
    if isinstance(error, OSError):
        return FailureCode.EVIDENCE_IO_FAILED
    return FailureCode.UNKNOWN_FAILED


def build_file_manifest(root: Path) -> list[dict[str, object]]:
    return [
        {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size,
         "sha256": sha256_file(path)}
        for path in _evidence_files(root)
    ]


def write_manifest(path: Path, entries: list[dict[str, object]]) -> None:
    path.write_bytes(
        (json.dumps(
            {"files": entries}, ensure_ascii=False, indent=2, sort_keys=True,
        ) + "\n").encode("utf-8")
    )
```

`create_evidence_zip` deve rodar a sanitização e depois o scanner antes de
escrever, criar `manifest.json`, usar caminhos relativos e recusar
symlinks/junctions, arquivos fora da raiz e qualquer tipo que não pertença à
allowlist textual. Em vez de ignorar silenciosamente `.env`, blobs/modelos, IFCs,
executáveis ou binários desconhecidos, falhar fechado com
`EvidencePrivacyError`. `write_manifest` usa JSON UTF-8 indentado com chaves
ordenadas. A extensão permitida não basta: `_read_text_strict` exige UTF-8 sem
substituição, NUL ou controles C0 além de tab/CR/LF antes de manifestar, sanitizar
ou escanear qualquer membro;
`validate_manifest(path, root)` recalcula tamanho/hash e retorna uma lista de
erros vazia somente quando não há arquivo ausente, extra ou divergente.

Implementar as funções com as regras literais e os corpos abaixo:

```python
SAFE_TEXT_SUFFIXES = {
    ".json", ".jsonl", ".txt", ".log", ".yaml", ".yml", ".csv", ".md",
}
FORBIDDEN_NAMES = {".env", "id_ed25519", "id_ed25519.pub"}
DETERMINISTIC_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _read_text_strict(path: Path) -> str:
    try:
        text = path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise EvidencePrivacyError(f"texto UTF-8 invalido: {path.name}") from error
    if "\x00" in text or any(
            ord(character) < 32 and character not in "\t\r\n" for character in text):
        raise EvidencePrivacyError(f"texto UTF-8 invalido: {path.name}")
    return text


def _evidence_files(root: Path, *, excluded_paths: Iterable[Path] = ()) -> list[Path]:
    root_resolved = root.resolve(strict=True)
    excluded = {path.resolve(strict=False) for path in excluded_paths}
    excluded.add((root / "manifest.json").resolve(strict=False))
    files: list[Path] = []
    for candidate in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = candidate.relative_to(root).as_posix()
        is_junction = getattr(candidate, "is_junction", lambda: False)()
        if candidate.is_symlink() or is_junction:
            raise EvidencePrivacyError(f"symlink proibido: {relative}")
        if not candidate.is_file():
            continue
        resolved = candidate.resolve(strict=True)
        try:
            contained = os.path.commonpath(
                (str(root_resolved), str(resolved)),
            ) == str(root_resolved)
        except ValueError:
            contained = False
        if not contained:
            raise EvidencePrivacyError(f"arquivo fora da raiz: {relative}")
        if resolved in excluded:
            continue
        if (candidate.name.lower() in FORBIDDEN_NAMES
                or candidate.suffix.lower() not in SAFE_TEXT_SUFFIXES):
            raise EvidencePrivacyError(f"arquivo nao permitido: {relative}")
        _read_text_strict(candidate)
        files.append(candidate)
    return files


def _write_deterministic_member(
    archive: zipfile.ZipFile, name: str, payload: bytes,
) -> None:
    info = zipfile.ZipInfo(name, date_time=DETERMINISTIC_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(
        info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9,
    )


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


def _sensitive_key_paths(value: Any, *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}".strip(".")
            if SENSITIVE_KEYS.search(str(key)):
                paths.append(child_path)
            paths.extend(_sensitive_key_paths(child, prefix=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_sensitive_key_paths(child, prefix=f"{prefix}[{index}]"))
    return paths


def _structured_documents(path: Path) -> list[tuple[int, Any]]:
    try:
        if path.suffix.lower() == ".json":
            return [(1, json.loads(_read_text_strict(path)))]
        return [
            (line_number, json.loads(line))
            for line_number, line in enumerate(
                _read_text_strict(path).splitlines(), 1
            )
            if line.strip()
        ]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidencePrivacyError(f"JSON invalido: {path.name}") from error


def scan_sensitive_text(
    root: Path, *, forbidden_values: set[str], excluded_paths: Iterable[Path] = (),
) \
        -> list[PrivacyFinding]:
    findings: list[PrivacyFinding] = []
    for candidate in _evidence_files(root, excluded_paths=excluded_paths):
        relative = candidate.relative_to(root).as_posix()
        if candidate.suffix.lower() in {".json", ".jsonl"}:
            for line_number, document in _structured_documents(candidate):
                findings.extend(
                    PrivacyFinding(relative, "sensitive-key", line_number)
                    for _ in _sensitive_key_paths(document)
                )
        lines = _read_text_strict(candidate).splitlines()
        for number, line in enumerate(lines, 1):
            for forbidden in (item for item in forbidden_values if item):
                if forbidden.casefold() in line.casefold():
                    findings.append(PrivacyFinding(relative, "known-value", number))
            for kind, pattern in SENSITIVE_TEXT_PATTERNS.items():
                for match in pattern.finditer(line):
                    if kind in {"ipv4", "ipv6"} and _parsed_ip_candidate(
                            kind, match.group()) is None:
                        continue
                    if _allowed_local_ip(kind, match.group()):
                        continue
                    findings.append(PrivacyFinding(relative, kind, number))
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


def sanitize_text_files(
    root: Path, *, forbidden_values: set[str], excluded_paths: Iterable[Path] = (),
) -> list[RemovedField]:
    removed: list[RemovedField] = []
    for candidate in _evidence_files(root, excluded_paths=excluded_paths):
        suffix = candidate.suffix.lower()
        if suffix in {".json", ".jsonl"}:
            sanitized_documents: list[Any] = []
            for line_number, document in _structured_documents(candidate):
                clean, document_removed = redact_sensitive(
                    document, forbidden_values=forbidden_values,
                    path=f"{candidate.relative_to(root).as_posix()}:{line_number}",
                )
                sanitized_documents.append(clean)
                removed.extend(document_removed)
            if suffix == ".json":
                serialized = json.dumps(
                    sanitized_documents[0], ensure_ascii=False, indent=2, sort_keys=True,
                ) + "\n"
            else:
                serialized = "".join(
                    json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                    for item in sanitized_documents
                )
            candidate.write_bytes(serialized.encode("utf-8"))
        text = _read_text_strict(candidate)
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
                if pattern_kind in {"ipv4", "ipv6"} and _parsed_ip_candidate(
                        pattern_kind, match.group()) is None:
                    return match.group()
                if _allowed_local_ip(pattern_kind, match.group()):
                    return match.group()
                replacements += 1
                return "[REDACTED]"

            text = pattern.sub(replace_match, text)
            if replacements:
                removed.append(RemovedField(
                    candidate.relative_to(root).as_posix(), f"{kind}:{replacements}"
                ))
        candidate.write_bytes(text.encode("utf-8"))
    return removed


def _manifest_map(raw: bytes) -> dict[str, tuple[int, str]]:
    try:
        document = json.loads(raw.decode("utf-8"))
        if set(document) != {"files"} or not isinstance(document["files"], list):
            raise ValueError("schema")
        result: dict[str, tuple[int, str]] = {}
        for row in document["files"]:
            if set(row) != {"path", "size_bytes", "sha256"}:
                raise ValueError("entry schema")
            name = str(row["path"])
            pure = PurePosixPath(name)
            if (not name or pure.is_absolute() or ".." in pure.parts or "\\" in name
                    or pure.as_posix() != name or name == "manifest.json"):
                raise ValueError("unsafe path")
            size = row["size_bytes"]
            digest = row["sha256"]
            if (not isinstance(size, int) or isinstance(size, bool) or size < 0
                    or not isinstance(digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                    or name in result):
                raise ValueError("invalid entry")
            result[name] = (size, digest)
        if list(result) != sorted(result):
            raise ValueError("unsorted entries")
        return result
    except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise EvidenceManifestError("manifesto invalido") from error


def validate_manifest(path: Path, root: Path) -> list[str]:
    try:
        expected = _manifest_map(path.read_bytes())
        actual = {
            str(item["path"]): (int(item["size_bytes"]), str(item["sha256"]))
            for item in build_file_manifest(root)
        }
    except (OSError, EvidenceManifestError, EvidencePrivacyError) as error:
        return [f"manifest invalid: {type(error).__name__}"]
    return [
        f"manifest mismatch: {name}"
        for name in sorted(expected.keys() | actual.keys())
        if expected.get(name) != actual.get(name)
    ]


def validate_evidence_archive(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if names.count("manifest.json") != 1 or len(names) != len(set(names)):
                return ["duplicate or missing manifest/member"]
            expected = _manifest_map(archive.read("manifest.json"))
            if set(names) != {"manifest.json", *expected.keys()}:
                return ["archive tree differs from manifest"]
            errors: list[str] = []
            for name, (size, digest) in expected.items():
                payload = archive.read(name)
                if len(payload) != size or hashlib.sha256(payload).hexdigest() != digest:
                    errors.append(f"archive payload mismatch: {name}")
            return errors
    except OSError:
        raise
    except (KeyError, zipfile.BadZipFile, EvidenceManifestError) as error:
        return [f"archive invalid: {type(error).__name__}"]


def create_evidence_zip(root: Path, output: Path, *, forbidden_values: set[str]) -> Path:
    temporary = output.with_suffix(output.suffix + ".partial")
    excluded = (output, temporary)
    sanitize_text_files(
        root, forbidden_values=forbidden_values, excluded_paths=excluded,
    )
    findings = scan_sensitive_text(
        root, forbidden_values=forbidden_values, excluded_paths=excluded,
    )
    if findings:
        raise EvidencePrivacyError(
            "; ".join(f"{item.kind}:{item.path}:{item.line}" for item in findings)
        )
    payload_files = _evidence_files(root, excluded_paths=excluded)
    manifest_path = root / "manifest.json"
    write_manifest(manifest_path, [
        {"path": candidate.relative_to(root).as_posix(),
         "size_bytes": candidate.stat().st_size, "sha256": sha256_file(candidate)}
        for candidate in payload_files
    ])
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            _write_deterministic_member(
                archive, "manifest.json", manifest_path.read_bytes(),
            )
            for candidate in payload_files:
                _write_deterministic_member(
                    archive, candidate.relative_to(root).as_posix(), candidate.read_bytes(),
                )
        validation_errors = validate_evidence_archive(temporary)
        if validation_errors:
            raise EvidenceManifestError("; ".join(validation_errors))
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

`create_partial_evidence_zip(output, *, status, reason_code)` valida em runtime
`status in {"failed", "interrupted"}` e exige uma instância real de
`FailureCode`, nunca string arbitrária. Ele monta em memória apenas `README.txt`,
`status.json` e `privacy-report.json` controlados pelo programa, calcula um
`manifest.json` para esses três membros e faz replace atômico do ZIP. Usa o mesmo
writer determinístico do bundle principal, reabre o `.partial` e exige árvore,
tamanho e SHA-256 idênticos ao manifesto antes do replace. Não lê o diretório
bruto, não chama `_evidence_files`, sanitizador ou scanner e, portanto, continua
disponível quando a coleta, a sanitização ou o bundle principal falha. Erro de E/S
ao criar esse último recurso é exibido no console sem afirmar que existe um ZIP.

Implementar o fallback somente com bytes gerados:

```python
def create_partial_evidence_zip(
    output: Path, *, status: Literal["failed", "interrupted"], reason_code: FailureCode
) -> Path:
    if status not in {"failed", "interrupted"}:
        raise ValueError("status parcial invalido")
    if not isinstance(reason_code, FailureCode):
        raise TypeError("reason_code deve ser FailureCode")
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
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            for name, payload in sorted(members.items()):
                _write_deterministic_member(archive, name, payload)
        validation_errors = validate_evidence_archive(temporary)
        if validation_errors:
            raise EvidenceManifestError("; ".join(validation_errors))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output
```

Para `sha256_file`, importar a implementação streaming já testada de
`src.experiment.ground_truth_validation`. JSON e cada linha JSONL são parseados:
`sanitize_text_files` aplica `redact_sensitive` estruturalmente antes dos padrões
textuais, e `scan_sensitive_text` falha fechado se qualquer chave casar
`SENSITIVE_KEYS`, mesmo que o valor seja desconhecido, nulo ou numérico. JSON/JSONL
inválido também é falha de privacidade, não texto aceito por tolerância.

Antes de `create_evidence_zip`, o orquestrador constrói `forbidden_values` apenas
em memória com usuário, hostname, caminhos de perfil, valores não vazios de
variáveis cujo nome seja segredo e valores não vazios dos `.env` explícitos. O
conjunto nunca é serializado, registrado em log nem incluído em exceção/relatório;
`privacy-report.json` guarda somente categorias e contagens. Qualquer ocorrência
restante impede o ZIP. Candidatos de IPv4/IPv6 só são classificados ou substituídos
depois que `ipaddress.ip_address` os valida; assim timestamps e versões com `:`
permanecem. A regex deliberadamente ampla candidata formas completas,
comprimidas, entre colchetes e IPv4-mapped (`2001:db8::7`, `fe80::1`, `::2`,
`[::1]`, `::ffff:192.0.2.1`); `ipaddress`, e não a regex, decide se o token é um
endereço. Loopback/unspecified é permitido porque identifica somente o serviço
local: `127.0.0.0/8`, `0.0.0.0`, `::1` e `::`.

`failure_code_for_exception` é a única tradução de falha do empacotador:
`EvidencePrivacyError -> PRIVACY_SCAN_FAILED`, `EvidenceManifestError ->
EVIDENCE_MANIFEST_FAILED`, `OSError -> EVIDENCE_IO_FAILED` e qualquer outra
exceção -> `UNKNOWN_FAILED`. A ordem é literal para impedir que uma classe mais
genérica masque uma categoria específica. Tanto o ZIP principal quanto o parcial
removem seu `.partial` em `finally`; um `.partial` antigo é truncado pelo modo `w`,
nunca lido nem incluído como evidência.

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

O teste cria IFC/GT/IDS mínimos ou usa doubles, executa a matriz com
`reuse_equivalent=True`, exporta resultados, retém o caminho agregado e o
`StageExpectation` de cada estágio em `expectations_by_path` e os dez pares
`(nome, digest)` em `locked_model_pairs`, passa os artefatos pelo empacotador e
cria um `.env` fixture com `TOKEN=dotenv-secret`, constrói
`forbidden_values = collect_forbidden_values({"OPENAI_API_KEY":
"process-secret"}, dotenv_paths=(dotenv,), base_values=(username, hostname))` e
afirma:

```python
assert set(dataset_keys) == {"predio", "casa"}
assert all(run["metadata"]["reuse_equivalent"] is True for run in runs)
assert all(run["metadata"]["building_context"]["bioclimatic_zone"] == "4A" for run in runs)
assert len(runs) == 20
assert len(expectations_by_path) == 20
assert all(_stage_done(path, expectation)
           for path, expectation in expectations_by_path.items())
assert _invalid_matrix_stages(results_root, identity, locked_model_pairs) == []
assert len({run["metadata"]["execution_identity_sha256"] for run in runs}) == 1
assert {"process-secret", "dotenv-secret", username, hostname} <= forbidden_values
assert not scan_sensitive_text(evidence_root, forbidden_values=forbidden_values)
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
