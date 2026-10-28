"""Modo real do estudo de formato de contexto: cliente Ollama, seleção de modelos e execução.

BLOQUEADO até autorização: a execução só acontece pela linha de comando com
``--real --confirmo-autorizacao "<registro>"`` (``scripts/estudo_formato_contexto.py``).
Nada aqui roda em import ou em teste contra um Ollama de verdade: os testes usam
``httpx.MockTransport`` e um amostrador de VRAM falso.

- **Cliente**: ``POST /api/chat`` sem streaming, ``format`` = JSON Schema da saída
  (saída estruturada do Ollama), temperatura 0, seed fixa, ``num_ctx`` fixo,
  ``think: false`` e timeout por chamada. Separado do ``suggestion_engine`` para não
  tocar no instrumento do produto (``PROMPT_VERSION``).
- **Seleção**: registros da prospecção M7-09 (``research/M7/prospection/``) filtrados por
  licença (Apache-2.0/MIT por padrão; licença condicionada, como a do Llama, só com
  decisão registrada do orientador), tag publicada (sem tag, a procedência fica
  condicionada) e "GPU inteira" no perfil de 6 GB a 4k (cenário nominal).
- **Execução**: uma inferência por vez, retomada por JSONL (linha já gravada não é
  refeita), latência medida no relógio e pelos tempos do Ollama, VRAM de pico por
  amostragem do ``nvidia-smi`` durante a chamada.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Final

import httpx
from loguru import logger
from pydantic import BaseModel, ConfigDict

from src.experiment.budget_v1.context_format import (
    FORMATS,
    LANGUAGES,
    SCOPES,
    ContextFormat,
    ContextScope,
    Language,
    SyntheticCase,
    build_prompt,
    output_json_schema,
    score,
)
from src.experiment.budget_v1.prospection import ModelProspectionRecord

RUNNER_VERSION: Final = "formato-contexto-runner/1"
DEFAULT_BASE_URL: Final = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_S: Final = 120.0
DEFAULT_NUM_CTX: Final = 4096
DEFAULT_SEED: Final = 20261028
DEFAULT_REPETITIONS: Final = 3
ALLOWED_LICENSES: Final = frozenset({"apache-2.0", "mit"})
PERSONAL_PROFILE: Final = "pessoal-nvidia-geforce-rtx-4050-laptop-gpu"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- seleção de modelos --------------------------------------------------------------


class ModelChoice(_Model):
    """Configuração modelo × quantização candidata ao estudo, com o motivo da decisão."""

    record_id: str
    tag: str | None
    model: str
    quantization: str
    license: str
    estimated_gib: float | None
    fit_nominal: str | None
    fit_instant: str | None
    selected: bool
    reasons: tuple[str, ...]


def _fit(record: ModelProspectionRecord, profile: str, scenario: str, ctx: int) -> str | None:
    for f in record.memory.fit:
        if f.hardware_profile_id == profile and f.scenario == scenario and f.context_tokens == ctx:
            return f.classification
    return None


def select_models(
    records: Iterable[ModelProspectionRecord],
    profile: str = PERSONAL_PROFILE,
    num_ctx: int = DEFAULT_NUM_CTX,
    allowed_licenses: frozenset[str] = ALLOWED_LICENSES,
    conditioned_license_decision: str | None = None,
) -> list[ModelChoice]:
    """Aplica os gates (licença, procedência/tag, memória) e explica cada exclusão.

    ``conditioned_license_decision`` é o registro da decisão do orientador que libera
    licenças condicionadas (Llama); sem ele, ficam fora.
    """
    choices: list[ModelChoice] = []
    for r in records:
        reasons: list[str] = []
        license_value = str(r.license.value or "").lower()
        license_gate = next((g for g in r.screening.gates if g.kind == "licenca"), None)
        if license_value not in allowed_licenses:
            if (
                license_gate is not None
                and license_gate.status == "condicionado"
                and conditioned_license_decision
            ):
                reasons.append(
                    f"licença condicionada liberada por decisão: {conditioned_license_decision}"
                )
            else:
                reasons.append(
                    f"licença fora da lista permitida ({r.license.value}); "
                    "aguarda decisão do orientador"
                )
        if not r.tag:
            reasons.append("sem tag publicada no Ollama (procedência condicionada)")
        nominal = _fit(r, profile, "nominal", num_ctx)
        instant = _fit(r, profile, "instantaneo", num_ctx)
        if nominal != "gpu_inteira":
            reasons.append(f"não cabe inteiro na GPU a {num_ctx} tokens (nominal: {nominal})")
        blocked = any(not x.startswith("licença condicionada liberada") for x in reasons)
        if not blocked and instant != "gpu_inteira":
            reasons.append(f"aviso: no instantâneo medido fica {instant}; feche outros programas")
        ctx_mem = next(
            (c.total_gib for c in r.memory.per_context if c.context_tokens == num_ctx), None
        )
        choices.append(
            ModelChoice(
                record_id=r.record_id,
                tag=r.tag,
                model=r.model,
                quantization=r.quantization,
                license=str(r.license.value),
                estimated_gib=ctx_mem,
                fit_nominal=nominal,
                fit_instant=instant,
                selected=not blocked,
                reasons=tuple(reasons),
            )
        )
    return choices


def load_prospection_records(directory: Path) -> list[ModelProspectionRecord]:
    """Registros da M7-09 (``models.jsonl``)."""
    path = directory / "models.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ModelProspectionRecord.model_validate_json(x) for x in lines if x.strip()]


# --- cliente Ollama ------------------------------------------------------------------


class CallResult(_Model):
    """Resultado bruto de uma chamada (ou da falha técnica)."""

    raw: str | None
    error: str | None = None
    wall_ms: float
    total_ms: float | None = None
    load_ms: float | None = None
    prompt_tokens: int | None = None
    eval_tokens: int | None = None


def _ns_to_ms(value: Any) -> float | None:
    return round(value / 1e6, 1) if isinstance(value, int | float) else None


class OllamaStructuredClient:
    """``/api/chat`` com saída estruturada; ``transport`` permite HTTP simulado nos testes."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Cria o cliente HTTP (nenhuma conexão é aberta aqui)."""
        self._client = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    def chat(
        self, model: str, prompt: str, schema: dict[str, Any], seed: int, num_ctx: int
    ) -> CallResult:
        """Uma chamada determinística (temperatura 0, seed); falha vira ``error``, não exceção."""
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "format": schema,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "seed": seed, "num_ctx": num_ctx},
        }
        start = time.perf_counter()
        try:
            resp = self._client.post("/api/chat", json=payload)
            resp.raise_for_status()
            body = resp.json()
        except httpx.TimeoutException:
            return CallResult(raw=None, error="timeout", wall_ms=_elapsed(start))
        except httpx.HTTPStatusError as exc:
            return CallResult(
                raw=None, error=f"http_{exc.response.status_code}", wall_ms=_elapsed(start)
            )
        except (httpx.HTTPError, ValueError) as exc:
            return CallResult(
                raw=None, error=f"transporte: {type(exc).__name__}", wall_ms=_elapsed(start)
            )
        return CallResult(
            raw=(body.get("message") or {}).get("content"),
            wall_ms=_elapsed(start),
            total_ms=_ns_to_ms(body.get("total_duration")),
            load_ms=_ns_to_ms(body.get("load_duration")),
            prompt_tokens=body.get("prompt_eval_count"),
            eval_tokens=body.get("eval_count"),
        )

    def close(self) -> None:
        """Fecha o cliente HTTP."""
        self._client.close()


def _elapsed(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


# --- VRAM ----------------------------------------------------------------------------


def query_vram_used_mib() -> int | None:
    """Memória de vídeo em uso (MiB) pela primeira GPU, via nvidia-smi; None se indisponível."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
        return int(out.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


class VramSampler:
    """Amostra a VRAM em segundo plano enquanto o bloco ``with`` roda; guarda o pico."""

    def __init__(
        self, query: Callable[[], int | None] = query_vram_used_mib, interval_s: float = 0.25
    ) -> None:
        """``query`` devolve MiB em uso; injetável para teste."""
        self._query = query
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.peak_mib: int | None = None

    def _sample(self) -> None:
        value = self._query()
        if value is not None:
            self.peak_mib = value if self.peak_mib is None else max(self.peak_mib, value)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._sample()

    def __enter__(self) -> VramSampler:
        self.peak_mib = None
        self._stop.clear()
        self._sample()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._sample()


# --- execução com retomada -------------------------------------------------------------


class RunRecord(_Model):
    """Uma linha do JSONL de resultados (uma chamada)."""

    runner: str = RUNNER_VERSION
    key: str
    model: str
    case_id: str
    formato: ContextFormat
    escopo: ContextScope
    idioma: Language
    repeticao: int
    seed: int
    num_ctx: int
    result: CallResult
    vram_peak_mib: int | None
    json_valido: bool
    acerto_top1: bool
    abstencao_correta: bool
    proposta_indevida: bool
    erro_unidade: bool


def record_key(model: str, case_id: str, fmt: str, scope: str, language: str, rep: int) -> str:
    """Chave única de uma chamada, usada na retomada."""
    return f"{model}|{case_id}|{fmt}|{scope}|{language}|r{rep}"


def done_keys(path: Path) -> set[str]:
    """Chaves já gravadas (linhas inválidas no fim, de uma interrupção, são ignoradas)."""
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            keys.add(json.loads(line)["key"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return keys


ProgressFn = Callable[[int, int], None]


def run_real(
    cases: Sequence[SyntheticCase],
    models: Sequence[str],
    out_path: Path,
    client: OllamaStructuredClient,
    sampler_factory: Callable[[], VramSampler] | None = None,
    repetitions: int = DEFAULT_REPETITIONS,
    seed: int = DEFAULT_SEED,
    num_ctx: int = DEFAULT_NUM_CTX,
    formats: Sequence[ContextFormat] = FORMATS,
    scopes: Sequence[ContextScope] = SCOPES,
    languages: Sequence[Language] = LANGUAGES,
    progress: ProgressFn | None = None,
) -> tuple[int, int]:
    """Executa a grade em série, modelo a modelo; devolve (feitas agora, puladas por retomada)."""
    schema = output_json_schema()
    make_sampler = sampler_factory or VramSampler  # resolvido na chamada (substituível)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    already = done_keys(out_path)
    total = len(models) * len(cases) * len(formats) * len(scopes) * len(languages) * repetitions
    done = skipped = 0
    with out_path.open("a", encoding="utf-8", newline="\n") as handle:
        for model in models:  # blocos por modelo: uma carga por modelo
            for rep in range(1, repetitions + 1):
                for fmt in formats:
                    for scope in scopes:
                        for language in languages:
                            for case in cases:
                                key = record_key(model, case.case_id, fmt, scope, language, rep)
                                if key in already:
                                    skipped += 1
                                    continue
                                prompt = build_prompt(case, fmt, scope, language)
                                with make_sampler() as sampler:
                                    result = client.chat(model, prompt, schema, seed, num_ctx)
                                s = score(case, result.raw if result.raw is not None else "")
                                row = RunRecord(
                                    key=key,
                                    model=model,
                                    case_id=case.case_id,
                                    formato=fmt,
                                    escopo=scope,
                                    idioma=language,
                                    repeticao=rep,
                                    seed=seed,
                                    num_ctx=num_ctx,
                                    result=result,
                                    vram_peak_mib=sampler.peak_mib,
                                    json_valido=s.json_valido,
                                    acerto_top1=s.acerto_top1,
                                    abstencao_correta=s.abstencao_correta,
                                    proposta_indevida=s.proposta_indevida,
                                    erro_unidade=s.erro_unidade,
                                )
                                handle.write(row.model_dump_json() + "\n")
                                handle.flush()
                                done += 1
                                if progress:
                                    progress(done + skipped, total)
    logger.info("modo real: {} chamadas feitas, {} puladas (já no JSONL)", done, skipped)
    return done, skipped


class RealCellSummary(_Model):
    """Agregado por modelo × formato × escopo × idioma (todas as repetições)."""

    model: str
    formato: str
    escopo: str
    idioma: str
    chamadas: int
    falhas_tecnicas: int
    json_valido: float
    acerto_top1: float | None
    abstencao_correta: float | None
    proposta_indevida: int
    erro_unidade: int
    latencia_mediana_ms: float | None
    latencia_p90_ms: float | None
    vram_pico_mib: int | None


def summarize_real(path: Path, cases: Sequence[SyntheticCase]) -> list[RealCellSummary]:
    """Lê o JSONL e agrega por célula; denominadores separados para valor e abstenção."""
    gold = {c.case_id: c.gold.outcome for c in cases}
    groups: dict[tuple[str, str, str, str], list[RunRecord]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = RunRecord.model_validate_json(line)
        except ValueError:
            continue
        groups[(row.model, row.formato, row.escopo, row.idioma)].append(row)
    out: list[RealCellSummary] = []
    for (model, fmt, scope, language), rows in sorted(groups.items()):
        lat = sorted(r.result.wall_ms for r in rows if r.result.error is None)
        val = [r for r in rows if gold.get(r.case_id) == "valor"]
        abst = [r for r in rows if gold.get(r.case_id) == "abstencao"]
        vram = [r.vram_peak_mib for r in rows if r.vram_peak_mib is not None]
        out.append(
            RealCellSummary(
                model=model,
                formato=fmt,
                escopo=scope,
                idioma=language,
                chamadas=len(rows),
                falhas_tecnicas=sum(r.result.error is not None for r in rows),
                json_valido=round(sum(r.json_valido for r in rows) / len(rows), 4),
                acerto_top1=round(sum(r.acerto_top1 for r in val) / len(val), 4) if val else None,
                abstencao_correta=round(sum(r.abstencao_correta for r in abst) / len(abst), 4)
                if abst
                else None,
                proposta_indevida=sum(r.proposta_indevida for r in rows),
                erro_unidade=sum(r.erro_unidade for r in rows),
                latencia_mediana_ms=round(statistics.median(lat), 1) if lat else None,
                latencia_p90_ms=round(lat[int(0.9 * (len(lat) - 1))], 1) if lat else None,
                vram_pico_mib=max(vram) if vram else None,
            )
        )
    return out
