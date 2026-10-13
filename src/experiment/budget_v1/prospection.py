"""Prospecção de modelos e perfil de hardware — tarefa M7-09.

Três partes, todas sem inferência:

1. **Coleta somente leitura** do equipamento (GPU/VRAM, CUDA, RAM, disco, SO) e
   dos metadados do Ollama (``--version``, ``list``, ``show``). Comando ausente
   vira ``indisponivel``; nada derruba a coleta.
2. **Estimativa de memória** por célula modelo × quantização × contexto:
   pesos (parâmetros × bits efetivos ÷ 8) + KV cache
   (2 × camadas × cabeças_KV × dim_cabeça × contexto × bytes) + reserva de
   runtime. É ESTIMATIVA, não medição (plano M7, §13).
3. **Registro** ``ModelProspectionRecord`` com os campos do §5.1 e uma tabela
   Markdown de leitura gerada a partir dos arquivos gravados.

Instalado, testado e selecionado são estados distintos: aqui ``tested`` e
``selected`` são sempre falsos (nenhuma inferência roda nesta tarefa) e
``installed`` vem apenas do ``ollama list`` ou dos manifests em disco.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from src.experiment.windows_inventory import _redact_public_value, _runtime_private_values

# Base única das saídas. Provisória: o plano (§4) põe research/M7/ na pasta
# operacional do M6, que ainda não existe; migrar quando o M6 a criar.
PROSPECTION_DIR = Path("research") / "M7" / "prospection"
MODELS_FILE = "models.jsonl"
HARDWARE_FILE = "hardware-profiles.json"
MARKDOWN_FILE = "prospeccao.md"

GIB = 1024**3
DEFAULT_CONTEXTS: tuple[int, ...] = (4096, 8192)
DEFAULT_RUNTIME_RESERVE_GIB = 0.7
DEFAULT_RAM_RESERVE_GIB = 4.0
KV_BYTES_F16 = 2

CommandRunner = Callable[..., Any]

SourceStatus = Literal[
    "fonte_primaria",
    "espelho_a_verificar",
    "catalogo_runtime",
    "derivado",
    "medido",
    "premissa",
    "a_verificar",
    "nao_medido",
    "indisponivel",
    "pendente_M7-02",
]
QuantName = Literal["Q8_0", "Q5_K_M", "Q4_K_M", "Q3_K_M"]
FitClass = Literal[
    "gpu_inteira",
    "offload_parcial",
    "inviavel",
    "condicionado_hardware_nao_confirmado",
]
HardwareLine = Literal["pessoal", "ime"]

QUANTIZATIONS: tuple[QuantName, ...] = ("Q8_0", "Q5_K_M", "Q4_K_M", "Q3_K_M")

# Bits efetivos por peso do arquivo GGUF inteiro, medidos pelo llama.cpp no
# Llama-3.1-8B. Em modelos com vocabulário grande ou partes mantidas em maior
# precisão, o arquivo real fica acima da fórmula (ver catalog_size_gib).
BITS_PER_WEIGHT: dict[QuantName, float] = {
    "Q8_0": 8.5008,
    "Q5_K_M": 5.7036,
    "Q4_K_M": 4.8944,
    "Q3_K_M": 3.9960,
}
BITS_PER_WEIGHT_SOURCE = (
    "https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md "
    "(tabela medida em meta-llama/Llama-3.1-8B; acesso 2026-10-12)"
)

# Subcomandos do Ollama que só leem metadados. run/pull/serve/create/cp/rm/push
# ficam de fora de propósito: esta tarefa não carrega nem baixa modelo.
OLLAMA_READONLY_SUBCOMMANDS = frozenset({"--version", "list", "show"})


class SourcedValue(BaseModel):
    """Valor com procedência: de onde veio, quando e com que grau de confirmação."""

    value: str | int | float | bool | None = None
    status: SourceStatus
    source: str | None = None
    accessed_on: str | None = None
    note: str | None = None


class OllamaTagInfo(BaseModel):
    """Tag publicada no catálogo do Ollama e o tamanho exibido na página."""

    tag: str
    catalog_size_gb: float
    catalog_context: str
    source: str
    accessed_on: str


class ArchitectureSpec(BaseModel):
    """Insumos da estimativa de um modelo candidato, cada um com sua fonte."""

    family: str
    model: str
    params_billion: SourcedValue
    kv_layers: SourcedValue
    kv_heads: SourcedValue
    head_dim: SourcedValue
    recurrent_state_gib: SourcedValue | None = None
    context_advertised: SourcedValue
    license: SourcedValue
    ollama_tags: dict[QuantName, OllamaTagInfo | None]
    notes: list[str] = Field(default_factory=list)


class GpuInfo(BaseModel):
    """GPU observada pelo nvidia-smi."""

    name: str
    memory_total_mib: int | None = None
    driver_version: str | None = None


class InstalledModel(BaseModel):
    """Modelo presente na instalação local do Ollama (não implica testado)."""

    name: str
    model_id: str | None = None
    size: str | None = None
    details: dict[str, str] = Field(default_factory=dict)


class HardwareProfile(BaseModel):
    """Retrato anônimo de um equipamento candidato, sem usuário nem caminhos."""

    profile_id: str
    line: HardwareLine
    status: Literal["observado", "nao_confirmado"]
    collected_on: str | None = None
    os: SourcedValue
    gpus: list[GpuInfo] = Field(default_factory=list)
    gpu_probe: SourcedValue
    cuda_driver_max: SourcedValue
    cuda_toolkit: SourcedValue
    ram_total_gib: SourcedValue
    ram_available_gib: SourcedValue
    disk_free_gib: SourcedValue
    ollama_version: SourcedValue
    ollama_server: SourcedValue
    ollama_installed_source: SourcedValue
    ollama_installed: list[InstalledModel] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FitAssessment(BaseModel):
    """Classificação de uma célula num equipamento; derivada da estimativa."""

    hardware_profile_id: str
    context_tokens: int
    classification: FitClass
    classification_by_catalog_size: FitClass | None = None
    vram_margin_gib: float | None = None
    basis: str


class ContextMemory(BaseModel):
    """Memória estimada para um tamanho de contexto."""

    context_tokens: int
    kv_cache_gib: float
    recurrent_state_gib: float
    runtime_reserve_gib: float
    total_gib: float
    total_with_catalog_size_gib: float | None = None


class MemoryEstimate(BaseModel):
    """ESTIMATIVA de memória (pesos + KV + reserva); não é medição."""

    kind: Literal["estimativa"] = "estimativa"
    formula: str = (
        "pesos = parâmetros × bits_efetivos ÷ 8; "
        "KV = 2 × camadas_com_KV × cabeças_KV × dim_cabeça × contexto × 2 bytes (f16); "
        "total = pesos + KV + estado recorrente + reserva de runtime"
    )
    params_billion: float
    bits_per_weight: float
    bits_per_weight_source: str = BITS_PER_WEIGHT_SOURCE
    weights_gib: float
    catalog_size_gib: float | None = None
    kv_bytes_per_token: int
    per_context: list[ContextMemory]
    fit: list[FitAssessment] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class ContextInfo(BaseModel):
    """Contexto anunciado pela fonte versus contexto utilizável no equipamento."""

    advertised: SourcedValue
    runtime_catalog: SourcedValue
    usable: SourcedValue


class RuntimeInfo(BaseModel):
    """Runtime pretendido e versão observada na máquina de coleta."""

    name: Literal["ollama"] = "ollama"
    observed_version: SourcedValue


class Screening(BaseModel):
    """Triagem do candidato; dados do legado ficam pendentes da M7-02."""

    status: Literal["nao_triado", "triado"] = "nao_triado"
    legacy_runs: SourcedValue = Field(
        default_factory=lambda: SourcedValue(
            status="pendente_M7-02",
            note="Participação em runs históricos depende do inventário de comparabilidade",
        )
    )
    notes: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    """Decisão de incluir/excluir/adiar; nesta tarefa nenhuma é tomada."""

    status: Literal["pendente", "incluir", "excluir", "adiar"] = "pendente"
    reason: str = "Sem triagem nem ensaio autorizado (M7-10)"


class ModelProspectionRecord(BaseModel):
    """Registro de prospecção do plano M7 §5.1, um por modelo × quantização.

    Campos do §5.1: fonte primária/data (``primary_sources``), licença
    (``license``), tag/revisão/digest, quantização, contexto, memória, runtime,
    hardware-alvo, triagem/decisão/rodada. Os estados ``installed``, ``tested``
    e ``selected`` são independentes entre si.
    """

    record_id: str
    family: str
    model: str
    primary_sources: list[SourcedValue]
    license: SourcedValue
    tag: str | None
    revision: SourcedValue
    digest: SourcedValue
    quantization: QuantName
    context: ContextInfo
    memory: MemoryEstimate
    runtime: RuntimeInfo
    hardware_target: list[str]
    screening: Screening = Field(default_factory=Screening)
    decision: Decision = Field(default_factory=Decision)
    round_id: str | None = None
    installed: bool = False
    tested: bool = False
    selected: bool = False
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Estimativa de memória
# --------------------------------------------------------------------------


def weights_bytes(params_billion: float, bits_per_weight: float) -> float:
    """Bytes dos pesos: parâmetros × bits efetivos ÷ 8."""
    if params_billion <= 0 or bits_per_weight <= 0:
        raise ValueError("parâmetros e bits por peso precisam ser positivos")
    return params_billion * 1e9 * bits_per_weight / 8


def kv_cache_bytes(
    layers: int,
    kv_heads: int,
    head_dim: int,
    context_tokens: int,
    bytes_per_element: int = KV_BYTES_F16,
) -> int:
    """Bytes do KV cache: 2 (K e V) × camadas × cabeças_KV × dim_cabeça × contexto × bytes."""
    for name, value in (
        ("layers", layers),
        ("kv_heads", kv_heads),
        ("head_dim", head_dim),
        ("context_tokens", context_tokens),
        ("bytes_per_element", bytes_per_element),
    ):
        if value <= 0:
            raise ValueError(f"{name} precisa ser positivo")
    return 2 * layers * kv_heads * head_dim * context_tokens * bytes_per_element


def classify_fit(
    required_gib: float,
    vram_gib: float | None,
    ram_budget_gib: float | None,
    runtime_reserve_gib: float = DEFAULT_RUNTIME_RESERVE_GIB,
) -> tuple[FitClass, float | None]:
    """Classifica uma célula: GPU inteira, offload parcial ou inviável.

    ``required_gib`` é pesos + KV (+ estado recorrente), sem a reserva; a
    reserva de runtime CUDA sai da VRAM. Sem VRAM ou RAM observadas, o
    resultado é ``condicionado_hardware_nao_confirmado`` — nunca uma
    viabilidade presumida (T7-26). Retorna também a margem de VRAM.
    """
    if vram_gib is None or ram_budget_gib is None:
        return "condicionado_hardware_nao_confirmado", None
    usable_vram = vram_gib - runtime_reserve_gib
    margin = usable_vram - required_gib
    if margin >= 0:
        return "gpu_inteira", margin
    if required_gib <= usable_vram + max(ram_budget_gib, 0.0):
        return "offload_parcial", margin
    return "inviavel", margin


def _profile_budget(
    profile: HardwareProfile, ram_reserve_gib: float
) -> tuple[float | None, float | None]:
    """VRAM e RAM disponível para offload de um perfil, só se observadas."""
    if profile.status != "observado" or not profile.gpus:
        return None, None
    vram_mib = profile.gpus[0].memory_total_mib
    ram_total = profile.ram_total_gib.value
    if vram_mib is None or not isinstance(ram_total, (int, float)):
        return None, None
    return vram_mib / 1024, float(ram_total) - ram_reserve_gib


def _int_value(value: SourcedValue) -> int:
    if not isinstance(value.value, (int, float)):
        raise ValueError(f"valor numérico ausente: {value}")
    return int(value.value)


def estimate_memory(
    spec: ArchitectureSpec,
    quantization: QuantName,
    profiles: Sequence[HardwareProfile],
    *,
    contexts: Sequence[int] = DEFAULT_CONTEXTS,
    runtime_reserve_gib: float = DEFAULT_RUNTIME_RESERVE_GIB,
    ram_reserve_gib: float = DEFAULT_RAM_RESERVE_GIB,
) -> MemoryEstimate:
    """Estima a memória de uma célula e a classifica em cada perfil de hardware."""
    params = spec.params_billion.value
    if not isinstance(params, (int, float)):
        raise ValueError(f"{spec.model}: parâmetros sem valor numérico")
    bits = BITS_PER_WEIGHT[quantization]
    weights = weights_bytes(float(params), bits) / GIB
    tag = spec.ollama_tags.get(quantization)
    catalog = tag.catalog_size_gb * 1e9 / GIB if tag else None
    per_token = kv_cache_bytes(
        _int_value(spec.kv_layers), _int_value(spec.kv_heads), _int_value(spec.head_dim), 1
    )
    state = spec.recurrent_state_gib
    state_gib = float(state.value) if state and isinstance(state.value, (int, float)) else 0.0

    per_context: list[ContextMemory] = []
    fit: list[FitAssessment] = []
    for ctx in contexts:
        kv = per_token * ctx / GIB
        required = weights + kv + state_gib
        required_catalog = catalog + kv + state_gib if catalog is not None else None
        per_context.append(
            ContextMemory(
                context_tokens=ctx,
                kv_cache_gib=round(kv, 3),
                recurrent_state_gib=round(state_gib, 3),
                runtime_reserve_gib=runtime_reserve_gib,
                total_gib=round(required + runtime_reserve_gib, 3),
                total_with_catalog_size_gib=(
                    round(required_catalog + runtime_reserve_gib, 3)
                    if required_catalog is not None
                    else None
                ),
            )
        )
        for profile in profiles:
            vram, ram_budget = _profile_budget(profile, ram_reserve_gib)
            klass, margin = classify_fit(required, vram, ram_budget, runtime_reserve_gib)
            klass_catalog = (
                classify_fit(required_catalog, vram, ram_budget, runtime_reserve_gib)[0]
                if required_catalog is not None
                else None
            )
            fit.append(
                FitAssessment(
                    hardware_profile_id=profile.profile_id,
                    context_tokens=ctx,
                    classification=klass,
                    classification_by_catalog_size=klass_catalog,
                    vram_margin_gib=round(margin, 3) if margin is not None else None,
                    basis=(
                        "estimativa contra VRAM/RAM observadas"
                        if vram is not None
                        else "hardware não confirmado: sem VRAM/RAM observadas"
                    ),
                )
            )

    return MemoryEstimate(
        params_billion=float(params),
        bits_per_weight=bits,
        weights_gib=round(weights, 3),
        catalog_size_gib=round(catalog, 3) if catalog is not None else None,
        kv_bytes_per_token=per_token,
        per_context=per_context,
        fit=fit,
        assumptions=[
            "ESTIMATIVA, não medição: o pico real só existe após ensaio autorizado (M7-10).",
            "KV em f16 (padrão do Ollama), uma sequência por vez (fila serial M6).",
            f"Reserva de runtime CUDA de {_fmt(runtime_reserve_gib)} GiB, descontada da VRAM.",
            f"RAM para offload = RAM total − {_fmt(ram_reserve_gib)} GiB reservados ao sistema "
            "e aplicativos (premissa declarada).",
            "Buffers de computação do grafo não estão incluídos.",
        ],
    )


# --------------------------------------------------------------------------
# Parsers de saída de comandos (puros, testáveis sem GPU)
# --------------------------------------------------------------------------


def parse_nvidia_smi_csv(text: str) -> list[GpuInfo]:
    """Lê ``nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv``.

    Aceita a linha de cabeçalho e a unidade ``MiB``; linhas malformadas são
    ignoradas.
    """
    gpus: list[GpuInfo] = []
    for row in csv.reader(text.splitlines(), skipinitialspace=True):
        if len(row) != 3 or row[0].strip().casefold() == "name":
            continue
        name, memory, driver = (field.strip() for field in row)
        if not name:
            continue
        match = re.match(r"(\d+)", memory)
        gpus.append(
            GpuInfo(
                name=name,
                memory_total_mib=int(match.group(1)) if match else None,
                driver_version=driver or None,
            )
        )
    return gpus


def parse_cuda_driver_version(text: str) -> str | None:
    """Versão máxima de CUDA suportada pelo driver, do cabeçalho do ``nvidia-smi``."""
    match = re.search(r"CUDA Version:\s*([\d.]+)", text or "")
    return match.group(1) if match else None


def parse_nvcc_version(text: str) -> str | None:
    """Versão do CUDA toolkit a partir de ``nvcc --version``."""
    match = re.search(r"release\s+([\d.]+)", text or "")
    return match.group(1) if match else None


def parse_ollama_version(text: str) -> tuple[str | None, bool]:
    """Extrai a versão e se o servidor respondeu, de ``ollama --version``.

    Com o servidor no ar a saída é ``ollama version is X``; sem ele, o cliente
    avisa que não conectou e informa só a própria versão.
    """
    content = text or ""
    reachable = "could not connect" not in content.casefold()
    match = re.search(r"(\d+\.\d+\.\d+)", content)
    return (match.group(1) if match else None), reachable and match is not None


def parse_ollama_list(text: str) -> list[InstalledModel]:
    """Lê a tabela de ``ollama list`` (colunas separadas por 2+ espaços)."""
    models: list[InstalledModel] = []
    for line in (text or "").splitlines():
        if not line.strip() or line.strip().upper().startswith("NAME"):
            continue
        columns = re.split(r"\s{2,}|\t+", line.strip())
        models.append(
            InstalledModel(
                name=columns[0],
                model_id=columns[1] if len(columns) > 1 else None,
                size=columns[2] if len(columns) > 2 else None,
            )
        )
    return models


def parse_ollama_show(text: str) -> dict[str, str]:
    """Lê a seção ``Model`` de ``ollama show`` (arquitetura, parâmetros, contexto...)."""
    details: dict[str, str] = {}
    in_model = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = re.split(r"\s{2,}", line)
        if len(parts) == 1:
            in_model = line.casefold() == "model"
            continue
        if in_model and len(parts) == 2:
            details[parts[0].casefold()] = parts[1]
    return details


def read_ollama_manifests(models_dir: Path) -> list[InstalledModel]:
    """Lista modelos pelos manifests em disco, sem falar com o servidor.

    O identificador é o prefixo do SHA-256 do manifest, o mesmo ``ID`` do
    ``ollama list``. O caminho lido não entra no resultado.
    """
    manifests = models_dir / "manifests"
    if not manifests.is_dir():
        return []
    found: list[InstalledModel] = []
    for path in sorted(p for p in manifests.rglob("*") if p.is_file()):
        parts = path.relative_to(manifests).parts
        if len(parts) < 4:
            continue
        registry, namespace, model, tag = parts[-4:]
        name = f"{model}:{tag}"
        if registry != "registry.ollama.ai" or namespace != "library":
            name = f"{registry}/{namespace}/{model}:{tag}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        found.append(InstalledModel(name=name, model_id=digest))
    return found


# --------------------------------------------------------------------------
# Coleta somente leitura
# --------------------------------------------------------------------------


def _run(runner: CommandRunner, command: list[str], timeout: float) -> str | None:
    """Executa um comando e devolve stdout+stderr, ou None se falhar de qualquer jeito."""
    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("{} indisponível: {}", command[0], type(exc).__name__)
        return None
    if getattr(result, "returncode", 1) != 0:
        logger.debug("{} terminou com código {}", command[0], result.returncode)
        return None
    return f"{result.stdout or ''}{result.stderr or ''}"


def run_ollama_readonly(
    runner: CommandRunner, args: Sequence[str], timeout: float = 30.0
) -> str | None:
    """Roda só subcomandos de metadados do Ollama; recusa qualquer outro."""
    if not args or args[0] not in OLLAMA_READONLY_SUBCOMMANDS:
        raise ValueError(f"subcomando do Ollama não autorizado: {list(args)[:1]}")
    return _run(runner, ["ollama", *args], timeout)


def _measured(value: str | int | float | None, source: str) -> SourcedValue:
    if value is None:
        return SourcedValue(status="indisponivel", source=source)
    return SourcedValue(value=value, status="medido", source=source)


def _unconfirmed() -> SourcedValue:
    return SourcedValue(status="indisponivel", note="equipamento não confirmado")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")


def _default_ollama_models_dir() -> Path:
    configured = os.environ.get("OLLAMA_MODELS")
    return Path(configured) if configured else Path.home() / ".ollama" / "models"


def collect_hardware_profile(
    runner: CommandRunner = subprocess.run,
    *,
    project_root: Path,
    collected_on: str,
    timeout: float = 30.0,
    ollama_models_dir: Path | None = None,
) -> HardwareProfile:
    """Coleta o perfil da máquina local sem carregar modelo nem iniciar serviço.

    ``ollama list``/``show`` só rodam se ``ollama --version`` confirmar o
    servidor no ar: no Windows esses dois comandos tentam abrir o aplicativo do
    Ollama quando não o encontram, e esta coleta não pode iniciar serviço.
    Com o servidor fora, os modelos instalados vêm dos manifests em disco.
    """
    smi = _run(
        runner,
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv"],
        timeout,
    )
    gpus = parse_nvidia_smi_csv(smi) if smi else []
    banner = _run(runner, ["nvidia-smi"], timeout)
    nvcc = _run(runner, ["nvcc", "--version"], timeout)

    ram_total: float | None = None
    ram_available: float | None = None
    try:
        import psutil

        memory = psutil.virtual_memory()
        ram_total = round(memory.total / GIB, 2)
        ram_available = round(memory.available / GIB, 2)
    except Exception as exc:
        logger.debug("psutil indisponível: {}", type(exc).__name__)

    try:
        disk_free: float | None = round(shutil.disk_usage(project_root).free / GIB, 1)
    except OSError:
        disk_free = None

    version_text = run_ollama_readonly(runner, ["--version"], timeout)
    version, reachable = parse_ollama_version(version_text or "")
    installed: list[InstalledModel] = []
    if reachable:
        listing = run_ollama_readonly(runner, ["list"], timeout)
        installed = parse_ollama_list(listing) if listing is not None else []
        installed_source = SourcedValue(
            value="ollama list",
            status="medido" if listing is not None else "indisponivel",
            source="ollama list",
        )
        for model in installed:
            shown = run_ollama_readonly(runner, ["show", model.name], timeout)
            model.details = parse_ollama_show(shown or "")
    else:
        installed = read_ollama_manifests(ollama_models_dir or _default_ollama_models_dir())
        installed_source = SourcedValue(
            value="manifests em disco",
            status="medido",
            source="manifests do Ollama (caminho omitido)",
            note="servidor fora do ar; ollama list não executado",
        )

    profile_id = f"pessoal-{_slug(gpus[0].name)}" if gpus else "pessoal-sem-gpu-nvidia"
    return HardwareProfile(
        profile_id=profile_id,
        line="pessoal",
        status="observado",
        collected_on=collected_on,
        os=_measured(
            f"{platform.system()} {platform.release()} (build {platform.version()})",
            "platform",
        ),
        gpus=gpus,
        gpu_probe=_measured("ok" if gpus else None, "nvidia-smi --query-gpu"),
        cuda_driver_max=_measured(
            parse_cuda_driver_version(banner or ""), "nvidia-smi (cabeçalho)"
        ),
        cuda_toolkit=_measured(parse_nvcc_version(nvcc or ""), "nvcc --version"),
        ram_total_gib=_measured(ram_total, "psutil.virtual_memory"),
        ram_available_gib=SourcedValue(
            value=ram_available,
            status="medido" if ram_available is not None else "indisponivel",
            source="psutil.virtual_memory",
            note="instantâneo no momento da coleta; varia com os aplicativos abertos",
        ),
        disk_free_gib=_measured(disk_free, "shutil.disk_usage (unidade do projeto)"),
        ollama_version=_measured(version, "ollama --version"),
        ollama_server=SourcedValue(
            value="no_ar" if reachable else "fora_do_ar",
            status="medido" if version_text is not None else "indisponivel",
            source="ollama --version",
        ),
        ollama_installed_source=installed_source,
        ollama_installed=installed,
    )


def unconfirmed_profile(profile_id: str, note: str) -> HardwareProfile:
    """Perfil de equipamento ainda não confirmado (ex.: laboratório IME)."""
    return HardwareProfile(
        profile_id=profile_id,
        line="ime",
        status="nao_confirmado",
        os=_unconfirmed(),
        gpu_probe=_unconfirmed(),
        cuda_driver_max=_unconfirmed(),
        cuda_toolkit=_unconfirmed(),
        ram_total_gib=_unconfirmed(),
        ram_available_gib=_unconfirmed(),
        disk_free_gib=_unconfirmed(),
        ollama_version=_unconfirmed(),
        ollama_server=_unconfirmed(),
        ollama_installed_source=_unconfirmed(),
        notes=[note],
    )


def redact_profile(profile: HardwareProfile) -> HardwareProfile:
    """Remove usuário, máquina e caminhos de perfil com a redação do inventário Windows."""
    clean = _redact_public_value(profile.model_dump(mode="json"), _runtime_private_values(None))
    return HardwareProfile.model_validate(clean)


# --------------------------------------------------------------------------
# Registros
# --------------------------------------------------------------------------


def build_records(
    specs: Iterable[ArchitectureSpec],
    profiles: Sequence[HardwareProfile],
    *,
    contexts: Sequence[int] = DEFAULT_CONTEXTS,
    runtime_reserve_gib: float = DEFAULT_RUNTIME_RESERVE_GIB,
    ram_reserve_gib: float = DEFAULT_RAM_RESERVE_GIB,
) -> list[ModelProspectionRecord]:
    """Gera um registro por modelo × quantização para os perfis informados."""
    installed: dict[str, InstalledModel] = {
        model.name: model for profile in profiles for model in profile.ollama_installed
    }
    observed_version = next(
        (p.ollama_version for p in profiles if p.status == "observado"),
        SourcedValue(status="indisponivel"),
    )
    records: list[ModelProspectionRecord] = []
    for spec in specs:
        for quant in QUANTIZATIONS:
            tag = spec.ollama_tags.get(quant)
            local = installed.get(tag.tag) if tag else None
            sources = [spec.params_billion, spec.kv_layers, spec.license]
            notes = list(spec.notes)
            if tag is None:
                notes.append(
                    f"{quant} não publicado no catálogo do Ollama para {spec.model}: "
                    "exigiria importar GGUF de terceiros (procedência a verificar)."
                )
            records.append(
                ModelProspectionRecord(
                    record_id=f"{_slug(spec.model)}-{quant.casefold()}",
                    family=spec.family,
                    model=spec.model,
                    primary_sources=sources,
                    license=spec.license,
                    tag=tag.tag if tag else None,
                    revision=SourcedValue(
                        status="a_verificar",
                        note="revisão upstream do GGUF do Ollama não publicada na página de tags",
                    ),
                    digest=(
                        SourcedValue(
                            value=local.model_id, status="medido", source="ollama list/manifests"
                        )
                        if local
                        else SourcedValue(
                            status="a_verificar", note="modelo não instalado nesta máquina"
                        )
                    ),
                    quantization=quant,
                    context=ContextInfo(
                        advertised=spec.context_advertised,
                        runtime_catalog=(
                            SourcedValue(
                                value=tag.catalog_context,
                                status="catalogo_runtime",
                                source=tag.source,
                                accessed_on=tag.accessed_on,
                            )
                            if tag
                            else SourcedValue(status="indisponivel", note="tag não publicada")
                        ),
                        usable=SourcedValue(
                            status="nao_medido",
                            note="contexto anunciado não é contexto utilizável (§13)",
                        ),
                    ),
                    memory=estimate_memory(
                        spec,
                        quant,
                        profiles,
                        contexts=contexts,
                        runtime_reserve_gib=runtime_reserve_gib,
                        ram_reserve_gib=ram_reserve_gib,
                    ),
                    runtime=RuntimeInfo(observed_version=observed_version),
                    hardware_target=[p.profile_id for p in profiles],
                    installed=local is not None,
                    notes=notes,
                )
            )
    return records


# --------------------------------------------------------------------------
# Gravação e leitura
# --------------------------------------------------------------------------


def write_outputs(
    out_dir: Path,
    profiles: Sequence[HardwareProfile],
    records: Sequence[ModelProspectionRecord],
) -> None:
    """Grava ``hardware-profiles.json`` e ``models.jsonl`` (UTF-8, ordem estável)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "task": "M7-09",
        "profiles": [p.model_dump(mode="json") for p in profiles],
    }
    (out_dir / HARDWARE_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [json.dumps(r.model_dump(mode="json"), ensure_ascii=False) for r in records]
    (out_dir / MODELS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_outputs(out_dir: Path) -> tuple[list[HardwareProfile], list[ModelProspectionRecord]]:
    """Relê os arquivos gravados, validando contra os modelos."""
    raw = json.loads((out_dir / HARDWARE_FILE).read_text(encoding="utf-8"))
    profiles = [HardwareProfile.model_validate(p) for p in raw["profiles"]]
    records = [
        ModelProspectionRecord.model_validate_json(line)
        for line in (out_dir / MODELS_FILE).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return profiles, records


# --------------------------------------------------------------------------
# Markdown de leitura
# --------------------------------------------------------------------------

_FIT_LABEL: dict[str, str] = {
    "gpu_inteira": "GPU inteira",
    "offload_parcial": "offload parcial",
    "inviavel": "inviável",
    "condicionado_hardware_nao_confirmado": "condicionado",
}


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}".replace(".", ",")


def _sv(value: SourcedValue) -> str:
    if value.value is None:
        return value.status
    shown = str(value.value).replace(".", ",") if isinstance(value.value, float) else value.value
    return f"{shown} ({value.status})"


def _fit_cell(record: ModelProspectionRecord, profile_id: str, ctx: int) -> str:
    for fit in record.memory.fit:
        if fit.hardware_profile_id == profile_id and fit.context_tokens == ctx:
            label = _FIT_LABEL[fit.classification]
            if (
                fit.classification_by_catalog_size
                and fit.classification_by_catalog_size != fit.classification
            ):
                label += f" → {_FIT_LABEL[fit.classification_by_catalog_size]}*"
            return label
    return "—"


def render_markdown(
    profiles: Sequence[HardwareProfile], records: Sequence[ModelProspectionRecord]
) -> str:
    """Tabela de leitura gerada a partir de ``hardware-profiles.json`` e ``models.jsonl``."""
    personal = next((p for p in profiles if p.status == "observado"), None)
    others = [p for p in profiles if p is not personal]
    contexts = sorted({c.context_tokens for r in records for c in r.memory.per_context})
    out: list[str] = [
        "# Prospecção de modelos — M7-09",
        "",
        "> Arquivo gerado por `scripts/prospecta_modelos.py` a partir de "
        f"`{HARDWARE_FILE}` e `{MODELS_FILE}`. Não editar à mão.",
        ">",
        "> **Todos os valores de memória são ESTIMATIVA (pesos + KV + reserva), "
        "não medição.** Nenhum modelo foi carregado, baixado ou testado. "
        "Contexto anunciado não é contexto utilizável (plano M7, §13).",
        "",
        "## Equipamentos",
        "",
    ]
    for profile in profiles:
        out.append(f"### `{profile.profile_id}` ({profile.line}, {profile.status})")
        out.append("")
        if profile.status != "observado":
            out.extend(f"- {note}" for note in profile.notes)
            out.append("")
            continue
        gpu = profile.gpus[0] if profile.gpus else None
        out.extend(
            [
                f"- Coleta (data UTC): {profile.collected_on}",
                f"- SO: {_sv(profile.os)}",
                (
                    f"- GPU: {gpu.name}, {gpu.memory_total_mib} MiB, driver {gpu.driver_version}"
                    if gpu
                    else "- GPU: indisponível"
                ),
                f"- CUDA máximo do driver: {_sv(profile.cuda_driver_max)}; "
                f"toolkit (nvcc): {_sv(profile.cuda_toolkit)}",
                f"- RAM total: {_sv(profile.ram_total_gib)} GiB; "
                f"livre na coleta: {_sv(profile.ram_available_gib)} GiB",
                f"- Disco livre (unidade do projeto): {_sv(profile.disk_free_gib)} GiB",
                f"- Ollama: {_sv(profile.ollama_version)}, servidor {_sv(profile.ollama_server)}",
                f"- Modelos instalados ({profile.ollama_installed_source.value}): "
                + (", ".join(m.name for m in profile.ollama_installed) or "nenhum"),
                "",
            ]
        )

    header = [
        "Família",
        "Modelo",
        "Quant. (bits efetivos)",
        "Tag Ollama",
        "Pesos fórmula (GiB)",
        "Catálogo (GiB)",
    ]
    header += [f"KV {c // 1024}k (GiB)" for c in contexts]
    header += [f"Total {c // 1024}k (GiB)" for c in contexts]
    if personal:
        header += [f"Pessoal {c // 1024}k" for c in contexts]
    header += [f"{p.profile_id}" for p in others]
    out += ["## Tabela", "", "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for record in records:
        mem = record.memory
        by_ctx = {c.context_tokens: c for c in mem.per_context}
        row = [
            record.family,
            record.model,
            f"{record.quantization} ({str(mem.bits_per_weight).replace('.', ',')})",
            f"`{record.tag}`" if record.tag else "não publicada",
            _fmt(mem.weights_gib),
            _fmt(mem.catalog_size_gib),
        ]
        row += [_fmt(by_ctx[c].kv_cache_gib + by_ctx[c].recurrent_state_gib) for c in contexts]
        row += [_fmt(by_ctx[c].total_gib) for c in contexts]
        if personal:
            row += [_fit_cell(record, personal.profile_id, c) for c in contexts]
        row += [_fit_cell(record, p.profile_id, contexts[0]) for p in others]
        out.append("| " + " | ".join(row) + " |")

    first = records[0].memory if records else None
    out += [
        "",
        "`*` a classificação muda quando se usa o tamanho publicado no catálogo do "
        "Ollama no lugar da fórmula (o arquivo real costuma ser maior: embeddings e "
        "partes multimodais ficam em maior precisão).",
        "",
        "## Premissas",
        "",
    ]
    if first:
        out.append(f"- Fórmula: {first.formula}.")
        out.append(f"- Bits efetivos: {first.bits_per_weight_source}.")
        out.extend(f"- {a}" for a in first.assumptions)
    out += [
        "- 1 GiB = 1024³ bytes; tamanhos do catálogo Ollama convertidos de GB decimais.",
        "- Qwen3.5: só 8 das 32 camadas têm KV por token; as 24 lineares têm estado "
        "recorrente de tamanho fixo, somado na coluna KV.",
        "",
        "## Contexto, licença e estado por modelo",
        "",
        "| Modelo | Contexto anunciado | Contexto no catálogo | Contexto utilizável "
        "| Licença | Instalado | Testado | Selecionado | Runs antigos |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    seen: set[str] = set()
    for record in records:
        if record.model in seen:
            continue
        seen.add(record.model)
        ctx = record.context
        tagged = [r for r in records if r.model == record.model and r.tag]
        out.append(
            f"| {record.model} | {_sv(ctx.advertised)} | "
            f"{tagged[0].context.runtime_catalog.value if tagged else '—'} | "
            f"{ctx.usable.status} | {record.license.value} ({record.license.status}) | "
            f"{'sim' if any(r.installed for r in records if r.model == record.model) else 'não'} | "
            f"não | não | {record.screening.legacy_runs.status} |"
        )
    out += ["", "## Notas", ""]
    seen_notes: set[str] = set()
    for record in records:
        for note in record.notes:
            key = f"{record.model}: {note}"
            if key not in seen_notes:
                seen_notes.add(key)
                out.append(f"- **{record.model}**: {note}")
    return "\n".join(out) + "\n"
