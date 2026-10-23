"""Inventário e comparabilidade do legado experimental — tarefa M7-02.

Somente leitura sobre os resultados históricos (runs ``run_*.json``, sidecars
``*_issues.jsonl`` e pacotes ``RESULTADO*.zip``). Nenhum arquivo de resultado é
aberto para escrita, movido ou apagado, e nenhuma inferência é executada.

Duas leituras:

- **(b) documental** — parte do inventário de 12/10/2026
  (``docs/pesquisa/modulo-07-avaliacao/inventario-experimentos.json`` + CSV) e
  revalida por SHA-256 os runs que existirem neste clone. Os demais ficam
  ``nao_verificado``; valores de métricas ficam ``nao_registrado``.
- **(a) pasta legada** — confere cada artefato listado no inventário documental
  contra o SHA-256 já registrado (``confere`` / ``divergente`` / ``ausente``) e,
  quando confere, lê os valores das métricas do próprio run.

Cada run recebe exatamente uma das quatro classes da política de
reaproveitamento (plano M7, §2.3), com motivos explícitos, e duas flags
independentes: ``dataset_contaminado`` (casa/prédio e variantes foram usados no
desenvolvimento, §6.3) e ``revisao_simulada`` (``review_proxy`` aplica valores
pelo GT, não mede pessoas, §2.2). O que a fonte não registra fica
``nao_registrado``: nada é inferido pelo lock atual, pelo nome da pasta de data
ou por documentação.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

# Base única das saídas. Provisória, como na M7-09: o plano (§4) põe research/M7/
# na pasta operacional do M6, que ainda não existe; migrar quando o M6 a criar.
LEGACY_DIR = Path("research") / "M7" / "legacy"
INVENTORY_FILE = "inventory.json"
COMPARABILITY_FILE = "comparability.csv"

DOCUMENTAL_DIR = Path("docs") / "pesquisa" / "modulo-07-avaliacao"
DOCUMENTAL_JSON = DOCUMENTAL_DIR / "inventario-experimentos.json"
DOCUMENTAL_CSV = DOCUMENTAL_DIR / "inventario-runs.csv"

SCHEMA_VERSION = "m7-legacy-1.0"
NAO_REGISTRADO = "nao_registrado"
ZIP_MEMBER_SEPARATOR = "!/"

# Totais declarados no inventário documental de 12/10/2026 (plano M7, §2.1).
# Servem para conferência: divergência é reportada, nunca forçada.
EXPECTED_TOTALS: dict[str, int] = {"runs": 275, "modelos": 21, "runs_v7.8": 0}

# Conjuntos expostos no desenvolvimento (plano M7, §2.1 e §6.3): casa, prédio e
# as variantes mascaradas do prédio, que herdam a linhagem.
DEVELOPMENT_DATASETS = frozenset({"casa", "predio", "predio-masked"})

ComparabilityClass = Literal[
    "referencia_historica",
    "entrada_reavaliavel",
    "medicao_comparavel",
    "comparabilidade_insuficiente",
]
COMPARABILITY_CLASSES: tuple[ComparabilityClass, ...] = (
    "referencia_historica",
    "entrada_reavaliavel",
    "medicao_comparavel",
    "comparabilidade_insuficiente",
)
HashStatus = Literal["confere", "divergente", "ausente", "nao_verificado", "sem_artefato"]
Flag = Literal["sim", "nao", "nao_registrado"]
ArtifactKind = Literal["run", "smoke"]
DatasetSource = Literal["dataset_key", "pasta", "hash_ifc", "nao_registrado"]
ReviewType = Literal["review_proxy", "humana", "nao_registrado"]
ReadMode = Literal["documental", "pasta_legada"]

Scalar = str | int | float | bool | None


class HashCheck(BaseModel):
    """Conferência de um artefato contra o SHA-256 registrado no inventário documental."""

    artifact: str | None = None
    expected_sha256: str | None = None
    observed_sha256: str | None = None
    status: HashStatus = "nao_verificado"


class LegacyRunRecord(BaseModel):
    """Um run histórico, com o que a fonte registra e sua classe de comparabilidade.

    ``run_id`` é o caminho do artefato (único no inventário); ``sha256`` identifica
    os bytes. Campos que a fonte não traz valem ``nao_registrado``. Os elementos
    do contrato integral que o legado nunca gravou (split, receita, evidência
    enviada, comparador e definição de métrica da nova rodada) também ficam
    ``nao_registrado`` — é isso que impede ``medicao_comparavel``.
    """

    run_id: str
    artifact: str
    sha256: str
    artifact_kind: ArtifactKind
    copy_of: str | None = None
    date: str = NAO_REGISTRADO
    date_field: str = NAO_REGISTRADO
    instrument_version: str = NAO_REGISTRADO
    study: str
    condition: dict[str, Scalar] = Field(default_factory=dict)
    model_tag: str = NAO_REGISTRADO
    model_digest: str = NAO_REGISTRADO
    quantization: str = NAO_REGISTRADO
    quantization_lock_by_digest: str = NAO_REGISTRADO
    quantization_lock_source: str = NAO_REGISTRADO
    ollama_version: str = NAO_REGISTRADO
    gpu: str = NAO_REGISTRADO
    dataset: str = NAO_REGISTRADO
    dataset_source: DatasetSource = "nao_registrado"
    ifc_sha256: str = NAO_REGISTRADO
    ids_sha256: str = NAO_REGISTRADO
    ground_truth_sha256: str = NAO_REGISTRADO
    ground_truth_items: int | str = NAO_REGISTRADO
    n_items: int | str = NAO_REGISTRADO
    sidecar_records: int | str = NAO_REGISTRADO
    sidecar_json_valid: bool | str = NAO_REGISTRADO
    metrics_available: list[str] = Field(default_factory=list)
    metric_values: dict[str, Scalar] | str = NAO_REGISTRADO
    review_type: ReviewType = "nao_registrado"
    split_manifest_sha256: str = NAO_REGISTRADO
    recipe_sha256: str = NAO_REGISTRADO
    evidence_exposure_sha256: str = NAO_REGISTRADO
    comparator_version: str = NAO_REGISTRADO
    metric_definition_version: str = NAO_REGISTRADO
    run_hash: HashCheck = Field(default_factory=HashCheck)
    sidecar_hash: HashCheck = Field(default_factory=lambda: HashCheck(status="sem_artefato"))
    dataset_contaminado: Flag = "nao_registrado"
    revisao_simulada: Flag = "nao_registrado"
    comparability_class: ComparabilityClass = "comparabilidade_insuficiente"
    comparability_reasons: list[str] = Field(default_factory=list)
    round_key: str = ""


# ---------------------------------------------------------------------------
# Leitura de valores
# ---------------------------------------------------------------------------


def _text(value: object) -> str:
    """Converte valor registrado em texto; ausente/vazio vira ``nao_registrado``."""
    if value is None or value == "":
        return NAO_REGISTRADO
    return str(value)


def _registered(value: object) -> bool:
    """Diz se um campo textual traz valor de fato registrado na fonte."""
    return value not in (None, "", NAO_REGISTRADO)


def _gpu_names(metadata: Mapping[str, Any]) -> str:
    """Nome(s) de GPU declarados em ``metadata.hardware.gpus``, sem completar."""
    hardware = metadata.get("hardware")
    if not isinstance(hardware, Mapping):
        return NAO_REGISTRADO
    names = [str(g.get("name")) for g in hardware.get("gpus") or [] if g.get("name")]
    return " + ".join(names) if names else NAO_REGISTRADO


def _run_date(metadata: Mapping[str, Any]) -> tuple[str, str]:
    """Data registrada no run e o campo de origem; nunca deduzida do nome da pasta."""
    for field in ("timestamp", "stage_started_utc"):
        if _registered(metadata.get(field)):
            return str(metadata[field]), field
    return NAO_REGISTRADO, NAO_REGISTRADO


CONDITION_FIELDS: tuple[str, ...] = (
    "num_ctx",
    "num_ctx_policy",
    "num_predict",
    "seed",
    "temperature",
    "top_p",
    "repeat_penalty",
    "grounding_bsdd",
    "cache_enabled",
    "reuse_equivalent",
    "replica_index",
    "bsdd_cache_sha256",
    "repo_commit",
)


def _condition(metadata: Mapping[str, Any]) -> dict[str, Scalar]:
    """Parâmetros declarados da condição; ausência explícita, sem default do código atual."""
    out: dict[str, Scalar] = {}
    for field in CONDITION_FIELDS:
        value = metadata.get(field)
        out[field] = NAO_REGISTRADO if value is None or isinstance(value, dict | list) else value
    return out


def dataset_hash_index(runs: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Mapa ``ifc_sha256 → dataset`` montado só com pares registrados na própria fonte.

    Usa ``metadata.dataset_key`` e as identidades de execução dos pacotes; um hash
    associado a dois nomes diferentes fica fora do mapa (ambíguo).
    """
    seen: dict[str, set[str]] = defaultdict(set)
    for run in runs:
        metadata = run.get("metadata") or {}
        if metadata.get("dataset_key") and metadata.get("ifc_sha256"):
            seen[metadata["ifc_sha256"]].add(str(metadata["dataset_key"]))
        identity = metadata.get("execution_identity") or {}
        for ds in identity.get("datasets") or []:
            if ds.get("key") and ds.get("ifc_sha256"):
                seen[ds["ifc_sha256"]].add(str(ds["key"]))
    return {h: next(iter(keys)) for h, keys in seen.items() if len(keys) == 1}


def resolve_dataset(
    artifact: str, metadata: Mapping[str, Any], hash_index: Mapping[str, str]
) -> tuple[str, DatasetSource]:
    """Dataset do run: chave registrada, pasta do artefato ou hash do IFC já registrado.

    A pasta só conta quando é um dos nomes de dataset conhecidos na estrutura
    ``.../<dataset>/<modelo>/run_N.json``; nomes de estudo não viram dataset.
    """
    if _registered(metadata.get("dataset_key")):
        return str(metadata["dataset_key"]), "dataset_key"
    parts = artifact.split("/")
    if len(parts) >= 3 and parts[-3] in DEVELOPMENT_DATASETS:
        return parts[-3], "pasta"
    ifc = metadata.get("ifc_sha256")
    if ifc and ifc in hash_index:
        return hash_index[ifc], "hash_ifc"
    return NAO_REGISTRADO, "nao_registrado"


def quantization_index(locks: Iterable[Mapping[str, Any]]) -> dict[str, tuple[str, str]]:
    """Mapa ``digest → (quantização, lock)`` dos locks históricos.

    Só serve para run cujo digest coincide exatamente (plano M7, §2.1): sem
    digest no run, nada é imputado.
    """
    out: dict[str, tuple[str, str]] = {}
    for lock in locks:
        for model in (lock.get("data") or {}).get("models") or []:
            digest, quant = model.get("digest"), model.get("quantization")
            if digest and quant and digest not in out:
                out[digest] = (str(quant), str(lock.get("artifact", NAO_REGISTRADO)))
    return out


def _artifact_kind(study: str) -> ArtifactKind:
    """``smoke`` quando a própria fonte agrupa o run como smoke; senão ``run``."""
    return "smoke" if "smoke" in study.lower() else "run"


def record_from_documental(
    entry: Mapping[str, Any],
    *,
    hash_index: Mapping[str, str],
    quant_index: Mapping[str, tuple[str, str]],
) -> LegacyRunRecord:
    """Converte uma entrada ``runs[]`` do inventário documental em ``LegacyRunRecord``.

    Formato aceito tanto para run local (``src/experiment/results/...``) quanto
    para membro de ZIP (``dist/X.zip!/benchmark/results/...``). Valores de
    métricas não estão no inventário documental e ficam ``nao_registrado``.
    """
    metadata: Mapping[str, Any] = entry.get("metadata") or {}
    artifact = str(entry["artifact"])
    study = str(entry.get("group") or NAO_REGISTRADO)
    date, date_field = _run_date(metadata)
    dataset, dataset_source = resolve_dataset(artifact, metadata, hash_index)
    digest = _text(metadata.get("model_digest"))
    quant, quant_source = quant_index.get(digest, (NAO_REGISTRADO, NAO_REGISTRADO))
    sidecar_info = entry.get("sidecar_info") or {}
    has_proxy = bool(entry.get("has_review_proxy"))
    metrics = [f"evaluation.{k}" for k in entry.get("evaluation_keys") or []]
    if has_proxy:
        metrics.append("review_proxy")

    return LegacyRunRecord(
        run_id=artifact,
        artifact=artifact,
        sha256=str(entry["sha256"]),
        artifact_kind=_artifact_kind(study),
        date=date,
        date_field=date_field,
        instrument_version=_text(metadata.get("prompt_version")),
        study=study,
        condition=_condition(metadata),
        model_tag=_text(metadata.get("model_name")),
        model_digest=digest,
        quantization=_text(metadata.get("quantization")),
        quantization_lock_by_digest=quant,
        quantization_lock_source=quant_source,
        ollama_version=_text(metadata.get("ollama_version")),
        gpu=_gpu_names(metadata),
        dataset=dataset,
        dataset_source=dataset_source,
        ifc_sha256=_text(metadata.get("ifc_sha256")),
        ids_sha256=_text(metadata.get("ids_sha256")),
        ground_truth_sha256=_text(metadata.get("ground_truth_sha256")),
        ground_truth_items=metadata.get("ground_truth_items") or NAO_REGISTRADO,
        sidecar_records=sidecar_info.get("records", NAO_REGISTRADO),
        sidecar_json_valid=sidecar_info.get("all_lines_json_valid", NAO_REGISTRADO),
        metrics_available=metrics,
        review_type="review_proxy" if has_proxy else "nao_registrado",
        run_hash=HashCheck(artifact=artifact, expected_sha256=str(entry["sha256"])),
        sidecar_hash=(
            HashCheck(artifact=entry["sidecar"], expected_sha256=sidecar_info.get("sha256"))
            if entry.get("sidecar")
            else HashCheck(status="sem_artefato")
        ),
    )


def _scalars(section: object, prefix: str) -> dict[str, Scalar]:
    """Valores escalares de primeiro nível de uma seção do run, com prefixo."""
    if not isinstance(section, Mapping):
        return {}
    return {
        f"{prefix}.{k}": v
        for k, v in section.items()
        if v is None or isinstance(v, str | int | float | bool)
    }


def apply_run_payload(record: LegacyRunRecord, payload: Mapping[str, Any]) -> LegacyRunRecord:
    """Completa o registro com o conteúdo de um ``run_*.json`` já conferido por hash.

    Lê ``evaluation``, ``review_proxy``, ``stability`` e ``timing``. Seção ausente
    não vira zero; run sem ``evaluation`` fica com ``n_items`` não registrado.
    O tipo de revisão vem de ``review_proxy.simulation`` quando presente.
    """
    values: dict[str, Scalar] = {}
    for section in ("evaluation", "review_proxy", "stability", "timing"):
        values.update(_scalars(payload.get(section), section))
    evaluation = payload.get("evaluation")
    n_items: int | str = NAO_REGISTRADO
    if isinstance(evaluation, Mapping) and isinstance(evaluation.get("total_evaluated"), int):
        n_items = evaluation["total_evaluated"]
    proxy = payload.get("review_proxy")
    review_type: ReviewType = record.review_type
    if isinstance(proxy, Mapping):
        review_type = "review_proxy" if proxy.get("simulation", True) else "nao_registrado"
    return record.model_copy(
        update={
            "metric_values": values or NAO_REGISTRADO,
            "metrics_available": sorted(values),
            "n_items": n_items,
            "review_type": review_type,
        }
    )


# ---------------------------------------------------------------------------
# Conferência de hashes (somente leitura)
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    """SHA-256 hexadecimal de um bloco de bytes."""
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    """SHA-256 de arquivo lido em blocos, aberto só para leitura binária."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_artifact_bytes(root: Path, artifact: str) -> bytes | None:
    """Lê os bytes de um artefato, arquivo comum ou membro ``x.zip!/caminho``.

    Retorna ``None`` quando o arquivo, o ZIP ou o membro não existe. ZIP é
    aberto em modo ``r`` e nada é extraído para disco.
    """
    if ZIP_MEMBER_SEPARATOR in artifact:
        archive, member = artifact.split(ZIP_MEMBER_SEPARATOR, 1)
        archive_path = root / archive
        if not archive_path.is_file():
            return None
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                return zf.read(member)
        except (KeyError, zipfile.BadZipFile):
            return None
    path = root / artifact
    return path.read_bytes() if path.is_file() else None


def check_artifact(
    root: Path, artifact: str | None, expected: str | None, *, missing_status: HashStatus
) -> tuple[HashCheck, bytes | None]:
    """Confere um artefato contra o hash esperado; devolve a conferência e os bytes lidos.

    ``missing_status`` define como registrar a falta: ``ausente`` na pasta
    legada (o artefato deveria estar lá) e ``nao_verificado`` no clone, que não
    contém o legado completo.
    """
    if not artifact:
        return HashCheck(status="sem_artefato"), None
    data = read_artifact_bytes(root, artifact)
    if data is None:
        return HashCheck(artifact=artifact, expected_sha256=expected, status=missing_status), None
    observed = _sha256_bytes(data)
    status: HashStatus = "confere" if expected and observed == expected else "divergente"
    return HashCheck(
        artifact=artifact, expected_sha256=expected, observed_sha256=observed, status=status
    ), data


def verify_record(
    record: LegacyRunRecord,
    root: Path,
    *,
    missing_status: HashStatus,
    read_values: bool,
) -> LegacyRunRecord:
    """Confere run e sidecar sob ``root``; com ``read_values``, lê métricas do run conferido."""
    run_check, data = check_artifact(
        root, record.artifact, record.sha256, missing_status=missing_status
    )
    sidecar_check, _ = check_artifact(
        root,
        record.sidecar_hash.artifact,
        record.sidecar_hash.expected_sha256,
        missing_status=missing_status,
    )
    updated = record.model_copy(update={"run_hash": run_check, "sidecar_hash": sidecar_check})
    if read_values and run_check.status == "confere" and data is not None:
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return updated
        if isinstance(payload, Mapping):
            updated = apply_run_payload(updated, payload)
    return updated


def check_archives(root: Path, archives: Iterable[Mapping[str, Any]]) -> list[HashCheck]:
    """Confere os pacotes ``RESULTADO*.zip`` inteiros contra o hash do inventário."""
    checks: list[HashCheck] = []
    for group in archives:
        artifact = str(group["archive"])
        path = root / artifact
        if not path.is_file():
            checks.append(
                HashCheck(artifact=artifact, expected_sha256=group.get("sha256"), status="ausente")
            )
            continue
        observed = _sha256_file(path)
        checks.append(
            HashCheck(
                artifact=artifact,
                expected_sha256=group.get("sha256"),
                observed_sha256=observed,
                status="confere" if observed == group.get("sha256") else "divergente",
            )
        )
    return checks


# ---------------------------------------------------------------------------
# Flags, classificação e invariantes T7-02/29/30
# ---------------------------------------------------------------------------


def contamination_flag(record: LegacyRunRecord) -> Flag:
    """``sim`` quando o dataset é casa/prédio (ou variante); ``nao_registrado`` se desconhecido."""
    if record.dataset == NAO_REGISTRADO:
        return "nao_registrado"
    return "sim" if record.dataset in DEVELOPMENT_DATASETS else "nao"


def simulated_review_flag(record: LegacyRunRecord) -> Flag:
    """``sim`` para ``review_proxy``; sem proxy, a fonte não prova revisão humana."""
    if record.review_type == "review_proxy":
        return "sim"
    if record.review_type == "humana":
        return "nao"
    return "nao_registrado"


# Elementos do contrato integral (plano M7, §2.3) e os campos que os registram.
CONTRACT_ELEMENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("caso/linhagem/split", ("split_manifest_sha256",)),
    ("hash IFC/IDS/GT", ("ifc_sha256", "ids_sha256", "ground_truth_sha256")),
    ("catálogo/receita", ("recipe_sha256",)),
    ("evidência enviada", ("evidence_exposure_sha256",)),
    ("prompt/schema/comparador", ("instrument_version", "comparator_version")),
    ("tag/digest/quantização", ("model_tag", "model_digest", "quantization")),
    ("runtime/equipamento", ("ollama_version", "gpu")),
    ("definição da métrica", ("metric_definition_version",)),
)


def missing_contract_elements(record: LegacyRunRecord) -> list[str]:
    """Elementos do contrato integral §2.3 que o run não registra."""
    return [
        label
        for label, fields in CONTRACT_ELEMENTS
        if not all(_registered(getattr(record, f)) for f in fields)
    ]


def classify(record: LegacyRunRecord) -> tuple[ComparabilityClass, list[str]]:
    """Atribui exatamente uma classe da §2.3 ao run, com os motivos.

    Ordem das regras:

    1. ``comparabilidade_insuficiente`` — bytes divergentes/ausentes, ou falta
       identificar modelo, versão do instrumento ou entradas (IFC/IDS/GT).
    2. ``medicao_comparavel`` — todos os elementos do contrato integral
       registrados (o legado nunca registra split, receita, evidência enviada,
       comparador e definição de métrica da nova rodada).
    3. ``entrada_reavaliavel`` — run completo (não smoke) com digest e sidecar
       por item legível: as respostas podem ser reanalisadas em versão separada,
       sem nova inferência e sem certificar sustentação retroativa.
    4. ``referencia_historica`` — demais runs identificados.
    """
    reasons: list[str] = []
    if record.run_hash.status in ("divergente", "ausente"):
        reasons.append(f"run {record.run_hash.status} na conferência de SHA-256")
    for label, value in (
        ("modelo", record.model_tag),
        ("versão do instrumento", record.instrument_version),
        ("hash do IFC", record.ifc_sha256),
        ("hash do IDS", record.ids_sha256),
        ("hash do GT", record.ground_truth_sha256),
    ):
        if not _registered(value):
            reasons.append(f"{label} não registrado")
    if reasons:
        return "comparabilidade_insuficiente", reasons

    missing = missing_contract_elements(record)
    if not missing:
        return "medicao_comparavel", ["todos os elementos do contrato integral §2.3 registrados"]
    contract_note = "contrato integral incompleto: " + ", ".join(missing)

    sidecar_ok = record.sidecar_hash.status in ("confere", "nao_verificado")
    has_items = isinstance(record.sidecar_records, int) and record.sidecar_records > 0
    if (
        record.artifact_kind == "run"
        and _registered(record.model_digest)
        and record.sidecar_json_valid is True
        and has_items
        and sidecar_ok
    ):
        return "entrada_reavaliavel", [
            f"sidecar com {record.sidecar_records} linhas JSON válidas e digest registrado",
            "reanálise só em versão separada, sem nova inferência; sustentação não certificada",
            contract_note,
        ]

    if record.artifact_kind == "smoke":
        reasons.append("smoke inicial, não benchmark completo")
    if not _registered(record.model_digest):
        reasons.append("digest do modelo não registrado")
    if record.sidecar_hash.status == "sem_artefato":
        reasons.append("sem sidecar por item")
    elif record.sidecar_hash.status in ("divergente", "ausente"):
        reasons.append(f"sidecar {record.sidecar_hash.status}")
    elif record.sidecar_json_valid is not True:
        reasons.append("sidecar sem todas as linhas JSON válidas")
    reasons.append(contract_note)
    return "referencia_historica", reasons


def round_key(record: LegacyRunRecord) -> str:
    """Identidade de rodada (T7-29): estudo, instrumento, população, GT e métricas.

    Mudar prompt, caso/IFC, IDS, GT, população ou conjunto de métricas gera outra
    chave; runs de chaves diferentes nunca são agregados como réplicas.
    """
    parts = {
        "study": record.study,
        "instrument_version": record.instrument_version,
        "dataset": record.dataset,
        "ifc_sha256": record.ifc_sha256,
        "ids_sha256": record.ids_sha256,
        "ground_truth_sha256": record.ground_truth_sha256,
        "metrics": sorted(m for m in record.metrics_available if m.startswith("evaluation.")),
    }
    return _sha256_bytes(json.dumps(parts, sort_keys=True).encode("utf-8"))[:16]


def group_rounds(records: Iterable[LegacyRunRecord]) -> dict[str, list[LegacyRunRecord]]:
    """Agrupa runs por ``round_key``; cada grupo tem uma só versão de instrumento e GT."""
    groups: dict[str, list[LegacyRunRecord]] = defaultdict(list)
    for record in records:
        groups[record.round_key or round_key(record)].append(record)
    return dict(groups)


def deduplicate(records: Sequence[LegacyRunRecord]) -> list[LegacyRunRecord]:
    """Marca cópias equivalentes por SHA-256 (T7-02), sem remover nenhum registro.

    O primeiro caminho em ordem alfabética fica como original; os demais ganham
    ``copy_of`` e saem das contagens de run.
    """
    first: dict[str, str] = {}
    out: list[LegacyRunRecord] = []
    for record in sorted(records, key=lambda r: r.artifact):
        if record.sha256 in first:
            out.append(record.model_copy(update={"copy_of": first[record.sha256]}))
        else:
            first[record.sha256] = record.artifact
            out.append(record)
    return out


def models_with_runs(records: Iterable[LegacyRunRecord]) -> dict[str, list[str]]:
    """Modelo → artefatos de run que comprovam o teste (T7-02: só run comprova)."""
    out: dict[str, list[str]] = defaultdict(list)
    for record in records:
        if record.copy_of is None and _registered(record.model_tag):
            out[record.model_tag].append(record.artifact)
    return {k: sorted(v) for k, v in sorted(out.items())}


def installed_only_models(
    records: Iterable[LegacyRunRecord], snapshots: Iterable[Mapping[str, Any]]
) -> list[str]:
    """Tags presentes em snapshots de instalação sem nenhum run correspondente."""
    tested = set(models_with_runs(records))
    installed = {
        str(m.get("name"))
        for snap in snapshots
        for m in (snap.get("snapshot") or {}).get("models") or []
        if m.get("name")
    }
    return sorted(installed - tested)


def finalize(records: Sequence[LegacyRunRecord]) -> list[LegacyRunRecord]:
    """Deduplica, calcula flags, chave de rodada e classe de cada registro."""
    out: list[LegacyRunRecord] = []
    for record in deduplicate(records):
        record = record.model_copy(
            update={
                "dataset_contaminado": contamination_flag(record),
                "revisao_simulada": simulated_review_flag(record),
                "round_key": round_key(record),
            }
        )
        klass, reasons = classify(record)
        if record.copy_of is not None:
            reasons = [f"cópia equivalente de {record.copy_of}", *reasons]
        if record.run_hash.status == "nao_verificado":
            reasons.append("bytes não reverificados nesta execução (fora do clone)")
        out.append(
            record.model_copy(
                update={"comparability_class": klass, "comparability_reasons": reasons}
            )
        )
    return out


# ---------------------------------------------------------------------------
# Montagem do inventário
# ---------------------------------------------------------------------------


def load_documental(project_root: Path) -> dict[str, Any]:
    """Carrega o inventário documental JSON de 12/10/2026."""
    return json.loads((project_root / DOCUMENTAL_JSON).read_text(encoding="utf-8"))


def csv_consistency(documental: Mapping[str, Any], csv_text: str) -> dict[str, int | list[str]]:
    """Confere o CSV por run contra o JSON: mesmo conjunto de artefatos e hashes."""
    by_artifact = {r["artifact"]: r["sha256"] for r in documental.get("runs") or []}
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    in_csv = {row["artifact"]: row["sha256"] for row in rows}
    divergent = sorted(a for a, h in in_csv.items() if a in by_artifact and by_artifact[a] != h)
    return {
        "linhas_csv": len(rows),
        "runs_json": len(by_artifact),
        "so_no_csv": sorted(set(in_csv) - set(by_artifact)),
        "so_no_json": sorted(set(by_artifact) - set(in_csv)),
        "hash_divergente": divergent,
    }


def build_records(
    documental: Mapping[str, Any],
    *,
    root: Path,
    mode: ReadMode,
) -> list[LegacyRunRecord]:
    """Gera os registros a partir do inventário documental e confere bytes sob ``root``.

    Em ``documental``, ``root`` é este clone: artefatos ausentes ficam
    ``nao_verificado`` e valores de métricas ficam ``nao_registrado``. Em
    ``pasta_legada``, ``root`` é a pasta original: ausência vira ``ausente`` e,
    quando o run confere, os valores são lidos dele.
    """
    runs = documental.get("runs") or []
    hash_index = dataset_hash_index(runs)
    quant_index = quantization_index(documental.get("model_locks") or [])
    missing_status: HashStatus = "ausente" if mode == "pasta_legada" else "nao_verificado"
    records = [
        verify_record(
            record_from_documental(entry, hash_index=hash_index, quant_index=quant_index),
            root,
            missing_status=missing_status,
            read_values=mode == "pasta_legada",
        )
        for entry in runs
    ]
    return finalize(records)


def _count(values: Iterable[str]) -> dict[str, int]:
    """Contagem ordenada por chave, para saídas estáveis."""
    return dict(sorted(Counter(values).items()))


def hash_summary(checks: Iterable[HashCheck]) -> dict[str, int]:
    """Contagem por status de conferência, com os cinco status sempre presentes."""
    counts = Counter(c.status for c in checks)
    return {
        s: counts.get(s, 0)
        for s in ("confere", "divergente", "ausente", "nao_verificado", "sem_artefato")
    }


def reconcile_totals(records: Sequence[LegacyRunRecord]) -> dict[str, Any]:
    """Compara totais observados com os esperados; diferença é reportada, não corrigida."""
    runs = [r for r in records if r.copy_of is None]
    observed = {
        "runs": len(runs),
        "modelos": len({r.model_tag for r in runs if _registered(r.model_tag)}),
        "runs_v7.8": sum(1 for r in runs if r.instrument_version == "v7.8"),
    }
    diff = {k: observed[k] - EXPECTED_TOTALS[k] for k in EXPECTED_TOTALS}
    return {
        "esperado": EXPECTED_TOTALS,
        "observado": observed,
        "diferenca": diff,
        "confere": not any(diff.values()),
    }


def summarize(records: Sequence[LegacyRunRecord]) -> dict[str, Any]:
    """Totais por classe, flag, versão e modelo (cópias equivalentes fora das contagens)."""
    runs = [r for r in records if r.copy_of is None]
    by_model: dict[str, dict[str, Any]] = {}
    for tag in sorted({r.model_tag for r in runs}):
        mine = [r for r in runs if r.model_tag == tag]
        by_model[tag] = {
            "runs": len(mine),
            "classes": _count(r.comparability_class for r in mine),
            "dataset_contaminado": _count(r.dataset_contaminado for r in mine),
            "revisao_simulada": _count(r.revisao_simulada for r in mine),
            "versoes": _count(r.instrument_version for r in mine),
            "digest_registrado": sum(1 for r in mine if _registered(r.model_digest)),
        }
    return {
        "runs": len(runs),
        "copias_equivalentes": len(records) - len(runs),
        "por_classe": {
            k: sum(1 for r in runs if r.comparability_class == k) for k in COMPARABILITY_CLASSES
        },
        "dataset_contaminado": _count(r.dataset_contaminado for r in runs),
        "revisao_simulada": _count(r.revisao_simulada for r in runs),
        "ambas_flags_sim": sum(
            1 for r in runs if r.dataset_contaminado == "sim" and r.revisao_simulada == "sim"
        ),
        "por_versao": _count(r.instrument_version for r in runs),
        "por_dataset": _count(r.dataset for r in runs),
        "quantizacao_no_run": _count(
            "registrada" if _registered(r.quantization) else NAO_REGISTRADO for r in runs
        ),
        "quantizacao_lock_por_digest": _count(
            "encontrada" if _registered(r.quantization_lock_by_digest) else NAO_REGISTRADO
            for r in runs
        ),
        "rodadas_distintas": len(group_rounds(runs)),
        "por_modelo": by_model,
    }


def build_inventory(
    documental: Mapping[str, Any],
    records: Sequence[LegacyRunRecord],
    *,
    mode: ReadMode,
    generated_at: str,
    sources: Mapping[str, str],
    csv_check: Mapping[str, Any] | None = None,
    archive_checks: Sequence[HashCheck] = (),
) -> dict[str, Any]:
    """Monta o ``inventory.json``: checklist M7-02, totais, modelos e registros."""
    run_checks = hash_summary(r.run_hash for r in records)
    sidecar_checks = hash_summary(r.sidecar_hash for r in records)
    verified_all = run_checks["confere"] == len(records) and sidecar_checks[
        "confere"
    ] + sidecar_checks["sem_artefato"] == len(records)
    tested = models_with_runs(records)
    return {
        "schema_version": SCHEMA_VERSION,
        "tarefa": "M7-02",
        "modo_leitura": mode,
        "gerado_em_utc": generated_at,
        "fontes": dict(sources),
        "checklist": {
            "validar_artefatos_hashes": {
                "status": "COMPLETO" if verified_all else "PARCIAL",
                "runs": run_checks,
                "sidecars": sidecar_checks,
                "pacotes_zip": hash_summary(archive_checks),
            },
            "distinguir_run_copia_smoke_instalacao": {
                "runs": sum(1 for r in records if r.copy_of is None and r.artifact_kind == "run"),
                "smokes": sum(
                    1 for r in records if r.copy_of is None and r.artifact_kind == "smoke"
                ),
                "copias_equivalentes": sum(1 for r in records if r.copy_of is not None),
                "instalados_sem_run": installed_only_models(
                    records, documental.get("model_installation_snapshots") or []
                ),
                "candidatos": "fora desta tarefa (M7-09); candidato não é modelo testado",
            },
            "conferencia_csv_json": dict(csv_check or {}),
        },
        "conferencia_totais": reconcile_totals(records),
        "totais": summarize(records),
        "repeticao_para_orcamento": (
            "Nenhum run registra split, receita, evidência enviada, comparador ou definição "
            "de métrica da rodada budget_v1; todo modelo que participar da avaliação de "
            "orçamento precisa de rodada nova. Runs reavaliáveis servem a reanálise "
            "exploratória separada; GT e revisão simulada históricos não são promovidos."
        ),
        "modelos_testados": tested,
        "pacotes_zip": [c.model_dump() for c in archive_checks],
        "registros": [r.model_dump() for r in records],
    }


COMPARABILITY_COLUMNS: tuple[str, ...] = (
    "run_id",
    "sha256",
    "artifact_kind",
    "copy_of",
    "study",
    "date",
    "instrument_version",
    "model_tag",
    "model_digest",
    "quantization",
    "quantization_lock_by_digest",
    "gpu",
    "dataset",
    "dataset_source",
    "n_items",
    "sidecar_records",
    "review_type",
    "run_hash_status",
    "sidecar_hash_status",
    "dataset_contaminado",
    "revisao_simulada",
    "comparability_class",
    "comparability_reasons",
    "round_key",
)


def comparability_rows(records: Iterable[LegacyRunRecord]) -> list[dict[str, str]]:
    """Projeção por run para o ``comparability.csv``."""
    rows: list[dict[str, str]] = []
    for r in records:
        data = r.model_dump()
        data["run_hash_status"] = r.run_hash.status
        data["sidecar_hash_status"] = r.sidecar_hash.status
        data["comparability_reasons"] = " | ".join(r.comparability_reasons)
        rows.append({c: "" if data.get(c) is None else str(data[c]) for c in COMPARABILITY_COLUMNS})
    return rows


def write_outputs(out_dir: Path, inventory: Mapping[str, Any]) -> None:
    """Grava ``inventory.json`` e ``comparability.csv`` com LF em qualquer SO."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / INVENTORY_FILE).write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    records = [LegacyRunRecord.model_validate(r) for r in inventory["registros"]]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COMPARABILITY_COLUMNS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(comparability_rows(records))
    (out_dir / COMPARABILITY_FILE).write_text(buffer.getvalue(), encoding="utf-8", newline="\n")


def ensure_outside(out_dir: Path, legacy_root: Path) -> None:
    """Recusa saída dentro da pasta legada: a leitura (a) não escreve lá."""
    out = out_dir.resolve()
    root = legacy_root.resolve()
    if out == root or root in out.parents:
        raise ValueError("a pasta de saída não pode ficar dentro da pasta legada")
