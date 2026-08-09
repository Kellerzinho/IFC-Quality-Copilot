"""Runtime Windows isolado, reproduzível e sem mutações globais.

As fronteiras de rede e processo são injetáveis para que o caminho crítico seja
testado sem baixar ferramentas, modelos ou iniciar um Ollama real.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
import socket
import stat
import subprocess
import time
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from src.experiment.model_lock import ModelMatrixLock

OLLAMA_VERSION = "0.32.5"
LLMFIT_VERSION = "1.1.8"
OLLAMA_RUNTIME_RELATIVE = Path("tools/ollama/0.32.5/windows-amd64")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


class RuntimeIntegrityError(RuntimeError):
    """Indica que um artefato ou resposta não satisfaz o lock congelado."""


class DownloadSpec(BaseModel):
    """Registro imutável de um download reproduzível."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: HttpUrl
    sha256: str
    size_bytes: int = Field(gt=0)

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            msg = "sha256 deve conter 64 caracteres hexadecimais minúsculos"
            raise ValueError(msg)
        return value


@dataclass(frozen=True)
class RuntimeAssetPlan:
    """Assets necessários, mantendo Ollama e llmfit em fases separadas."""

    ollama: Sequence[DownloadSpec]
    llmfit: DownloadSpec


@dataclass(frozen=True)
class PullProgress:
    """Evento validado emitido pelo stream NDJSON do Ollama."""

    status: str
    digest: str | None = None
    total: int | None = None
    completed: int | None = None


_OLLAMA = DownloadSpec(
    url=(
        "https://github.com/ollama/ollama/releases/download/v0.32.5/"
        "ollama-windows-amd64.zip"
    ),
    sha256="7c941ae084569d298062d29f8139163a3187c76dbca0479c70d085e78fd8c7bb",
    size_bytes=1_457_824_795,
)
_OLLAMA_ROCM = DownloadSpec(
    url=(
        "https://github.com/ollama/ollama/releases/download/v0.32.5/"
        "ollama-windows-amd64-rocm.zip"
    ),
    sha256="f2284e7008ffd64eadb7a05ac4ca1a0de843d1e8d0c861aa0923ef855ca94615",
    size_bytes=245_370_090,
)
_LLMFIT = DownloadSpec(
    url=(
        "https://github.com/AlexsJones/llmfit/releases/download/v1.1.8/"
        "llmfit-v1.1.8-x86_64-pc-windows-msvc.zip"
    ),
    sha256="bf8a509d68bc02f4cafc7040501938a30841eeb8c496eda51ae886a2f43a88e2",
    size_bytes=5_249_067,
)

PINNED_TOOL_SHA256 = {
    "ollama": _OLLAMA.sha256,
    "ollama_rocm": _OLLAMA_ROCM.sha256,
    "llmfit": _LLMFIT.sha256,
}

_PINNED_TOOLS: dict[str, dict[str, str | int]] = {
    "ollama": {
        "version": OLLAMA_VERSION,
        "url": str(_OLLAMA.url),
        "sha256": _OLLAMA.sha256,
        "size_bytes": _OLLAMA.size_bytes,
    },
    "ollama_rocm": {
        "version": OLLAMA_VERSION,
        "url": str(_OLLAMA_ROCM.url),
        "sha256": _OLLAMA_ROCM.sha256,
        "size_bytes": _OLLAMA_ROCM.size_bytes,
    },
    "llmfit": {
        "version": LLMFIT_VERSION,
        "url": str(_LLMFIT.url),
        "sha256": _LLMFIT.sha256,
        "size_bytes": _LLMFIT.size_bytes,
    },
}


def select_runtime_assets(gpu_names: Sequence[str]) -> RuntimeAssetPlan:
    """Seleciona ROCm somente quando o inventário indicar GPU AMD/Radeon."""
    needs_rocm = any(
        "amd" in name.casefold() or "radeon" in name.casefold() for name in gpu_names
    )
    ollama = (_OLLAMA, _OLLAMA_ROCM) if needs_rocm else (_OLLAMA,)
    return RuntimeAssetPlan(ollama=ollama, llmfit=_LLMFIT)


def validate_tool_pins(manifest: Mapping[str, object]) -> None:
    """Falha fechado se o manifesto divergir dos pins compilados no runtime."""
    tools = manifest.get("tools")
    if not isinstance(tools, Mapping):
        raise RuntimeIntegrityError("manifesto sem objeto tools para validar pins")
    for name, expected in _PINNED_TOOLS.items():
        record = tools.get(name)
        if not isinstance(record, Mapping):
            raise RuntimeIntegrityError(f"pin obrigatório ausente para {name}")
        for field, expected_value in expected.items():
            if record.get(field) != expected_value:
                raise RuntimeIntegrityError(
                    f"pin divergente para {name}.{field}: manifesto não corresponde à release"
                )


def _normalized_path(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=False)))


def assert_app_owned(path: Path, app_root: Path) -> Path:
    """Exige contenção real por caminho, sem aceitar irmãos por prefixo textual."""
    root_resolved = app_root.resolve(strict=False)
    candidate_resolved = path.resolve(strict=False)
    try:
        common = os.path.commonpath(
            (_normalized_path(root_resolved), _normalized_path(candidate_resolved))
        )
    except ValueError as exc:
        raise RuntimeIntegrityError(f"caminho fora do diretório app-owned: {path}") from exc
    if os.path.normcase(common) != _normalized_path(root_resolved):
        raise RuntimeIntegrityError(f"caminho fora do diretório app-owned: {path}")
    return candidate_resolved


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _assert_no_link_components(path: Path, boundary: Path) -> None:
    """Recusa links/junctions existentes entre a raiz confiável e o alvo."""
    boundary_resolved = boundary.resolve(strict=False)
    assert_app_owned(path, boundary_resolved)
    current = path
    existing: list[Path] = []
    while current != current.parent:
        existing.append(current)
        if current == boundary_resolved:
            break
        current = current.parent
    for candidate in reversed(existing):
        if candidate.exists() and _is_link_or_junction(candidate):
            raise RuntimeIntegrityError(
                f"link/junction inseguro em caminho app-owned: {candidate}"
            )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_download(path: Path, spec: DownloadSpec) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == spec.size_bytes
        and _sha256_file(path) == spec.sha256
    )


def download_verified(
    spec: DownloadSpec,
    destination: Path,
    *,
    http: Any | None = None,
    app_root: Path | None = None,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Baixa via ``.partial``, retoma com Range e promove somente bytes verificados."""
    if max_attempts < 1:
        raise ValueError("max_attempts deve ser positivo")
    owner = (app_root or destination.parent).resolve(strict=False)
    assert_app_owned(destination, owner)
    partial = destination.with_suffix(destination.suffix + ".partial")
    assert_app_owned(partial, owner)
    _assert_no_link_components(destination, owner)
    _assert_no_link_components(partial, owner)

    if _valid_download(destination, spec):
        return destination

    owner.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_dir():
            raise RuntimeIntegrityError(f"destino de download é diretório: {destination}")
        destination.unlink()
    if partial.exists() and (
        not partial.is_file() or partial.stat().st_size > spec.size_bytes
    ):
        if partial.is_dir():
            raise RuntimeIntegrityError(f"arquivo parcial é diretório: {partial}")
        partial.unlink()
    if _valid_download(partial, spec):
        os.replace(partial, destination)
        return destination

    owned_http = http is None
    client: Any = http or httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(60.0, connect=30.0),
    )
    last_error = "download incompleto"
    try:
        for attempt in range(max_attempts):
            offset = partial.stat().st_size if partial.is_file() else 0
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            try:
                manager = client.stream("GET", str(spec.url), headers=headers)
                with manager as response:
                    status_code = int(getattr(response, "status_code", 0))
                    if offset and status_code == 206:
                        mode = "ab"
                    elif status_code == 200:
                        mode = "wb"
                        offset = 0
                    else:
                        raise RuntimeIntegrityError(
                            f"HTTP {status_code} ao baixar {spec.url}"
                        )
                    with partial.open(mode) as output:
                        for chunk in response.iter_bytes():
                            if not isinstance(chunk, bytes):
                                raise RuntimeIntegrityError(
                                    "resposta de download contém bytes inválidos"
                                )
                            output.write(chunk)

                actual_size = partial.stat().st_size
                if actual_size != spec.size_bytes:
                    last_error = (
                        f"tamanho divergente: esperado {spec.size_bytes}, atual {actual_size}"
                    )
                    if actual_size > spec.size_bytes:
                        partial.unlink(missing_ok=True)
                    raise OSError(last_error)
                actual_hash = _sha256_file(partial)
                if actual_hash != spec.sha256:
                    last_error = (
                        f"SHA-256 divergente: esperado {spec.sha256}, atual {actual_hash}"
                    )
                    partial.unlink(missing_ok=True)
                    raise OSError(last_error)
                os.replace(partial, destination)
                return destination
            except (OSError, httpx.TransportError, RuntimeIntegrityError) as exc:
                last_error = str(exc) or type(exc).__name__
                if attempt + 1 == max_attempts:
                    break
                sleep(float(2**attempt))
    finally:
        if owned_http:
            close = getattr(client, "close", None)
            if close is not None:
                close()

    partial.unlink(missing_ok=True)
    raise RuntimeIntegrityError(f"download não verificado; {last_error}")


@dataclass(frozen=True)
class _ArchiveMember:
    info: zipfile.ZipInfo
    target: Path
    is_directory: bool


def _validate_archive_member(
    info: zipfile.ZipInfo, destination: Path, app_root: Path
) -> _ArchiveMember:
    # No Windows, ``zipfile`` normaliza barras invertidas em ``filename``.
    # ``orig_filename`` preserva o nome cru da central directory para o gate.
    raw = info.orig_filename
    if not raw or "\\" in raw or raw.startswith(("/", "//", "\\\\")):
        raise RuntimeIntegrityError(f"membro ZIP inseguro: {raw!r}")
    if ntpath.splitdrive(raw)[0] or ":" in raw:
        raise RuntimeIntegrityError(f"membro ZIP inseguro: {raw!r}")
    is_directory = info.is_dir() or raw.endswith("/")
    normalized = raw[:-1] if is_directory else raw
    parts = normalized.split("/")
    if not normalized or any(part in {"", ".", ".."} for part in parts):
        raise RuntimeIntegrityError(f"membro ZIP inseguro: {raw!r}")
    posix_path = PurePosixPath(normalized)
    if posix_path.is_absolute():
        raise RuntimeIntegrityError(f"membro ZIP inseguro: {raw!r}")

    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if file_type == stat.S_IFLNK:
        raise RuntimeIntegrityError(f"membro ZIP symlink inseguro: {raw!r}")
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise RuntimeIntegrityError(f"tipo de membro ZIP inseguro: {raw!r}")

    target = destination.joinpath(*parts)
    assert_app_owned(target, destination)
    assert_app_owned(target, app_root)
    return _ArchiveMember(info=info, target=target, is_directory=is_directory)


def safe_extract_zip(
    archive_path: Path,
    destination: Path,
    *,
    app_root: Path | None = None,
) -> Path:
    """Extrai ZIP após validar todos os membros como nomes POSIX não confiáveis."""
    owner = (app_root or destination).resolve(strict=False)
    assert_app_owned(destination, owner)
    _assert_no_link_components(destination, owner)

    with zipfile.ZipFile(archive_path) as archive:
        members = [
            _validate_archive_member(info, destination, owner) for info in archive.infolist()
        ]
        seen: set[str] = set()
        files: set[str] = set()
        for member in members:
            relative = member.target.relative_to(destination).as_posix()
            collision_key = relative.casefold()
            if collision_key in seen:
                raise RuntimeIntegrityError(f"membro ZIP duplicado/inseguro: {relative}")
            seen.add(collision_key)
            parents = PurePosixPath(relative).parents
            if any(parent.as_posix().casefold() in files for parent in parents):
                raise RuntimeIntegrityError(f"conflito arquivo/diretório no ZIP: {relative}")
            if not member.is_directory:
                files.add(collision_key)

        destination.mkdir(parents=True, exist_ok=True)
        for member in members:
            _assert_no_link_components(member.target, owner)
            if member.is_directory:
                member.target.mkdir(parents=True, exist_ok=True)
                continue
            member.target.parent.mkdir(parents=True, exist_ok=True)
            temporary = member.target.with_name(member.target.name + ".extracting")
            assert_app_owned(temporary, owner)
            try:
                with archive.open(member.info, "r") as source, temporary.open("wb") as output:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(chunk)
                os.replace(temporary, member.target)
            finally:
                temporary.unlink(missing_ok=True)
    return destination


def ollama_executable(release_root: Path) -> Path:
    """Retorna o único caminho canônico do executável standalone fixado."""
    return release_root / OLLAMA_RUNTIME_RELATIVE / "ollama.exe"


def _response_json(response: object) -> Mapping[str, object]:
    status_code = int(getattr(response, "status_code", 200))
    if status_code < 200 or status_code >= 300:
        raise RuntimeIntegrityError(f"Ollama respondeu HTTP {status_code}")
    json_method = getattr(response, "json", None)
    payload = json_method() if json_method is not None else response
    if not isinstance(payload, Mapping):
        raise RuntimeIntegrityError("resposta JSON inválida do Ollama")
    return cast(Mapping[str, object], payload)


def installed_model_digests(ollama: object) -> dict[str, str]:
    """Consulta ``/api/tags`` e exige digests SHA-256 completos."""
    get_json = getattr(ollama, "get_json", None)
    if get_json is None:
        raise TypeError("cliente Ollama deve fornecer get_json")
    payload = get_json("/api/tags")
    if not isinstance(payload, Mapping):
        raise RuntimeIntegrityError("resposta inválida de /api/tags")
    rows = payload.get("models")
    if not isinstance(rows, list):
        raise RuntimeIntegrityError("resposta de /api/tags sem lista models")
    installed: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise RuntimeIntegrityError("entrada inválida em /api/tags")
        name = row.get("name") or row.get("model")
        digest_value = row.get("digest")
        if not isinstance(name, str) or not name:
            raise RuntimeIntegrityError("tag sem nome em /api/tags")
        if not isinstance(digest_value, str):
            raise RuntimeIntegrityError(f"digest ausente para tag {name}")
        digest = (
            digest_value[len("sha256:") :]
            if digest_value.startswith("sha256:")
            else digest_value
        )
        if not _SHA256_RE.fullmatch(digest):
            raise RuntimeIntegrityError(f"digest incompleto ou inválido para tag {name}")
        previous = installed.get(name)
        if previous is not None and previous != digest:
            raise RuntimeIntegrityError(f"digest duplicado e divergente para tag {name}")
        installed[name] = digest
    return installed


def _journal_progress(path: Path, model: str, progress: PullProgress) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    payload = {"model": model, **asdict(progress)}
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _parse_progress(line: bytes) -> PullProgress:
    try:
        decoded = line.decode("utf-8", errors="strict")
        payload = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeIntegrityError("linha NDJSON inválida retornada por /api/pull") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeIntegrityError("linha NDJSON deve ser um objeto JSON")
    error = payload.get("error")
    if error is not None:
        raise RuntimeIntegrityError(f"Ollama recusou modelo: {error}")
    status_value = payload.get("status")
    if not isinstance(status_value, str) or not status_value:
        raise RuntimeIntegrityError("linha NDJSON sem status válido")

    digest_value = payload.get("digest")
    if digest_value is not None and not isinstance(digest_value, str):
        raise RuntimeIntegrityError("digest inválido no progresso do modelo")

    numeric: dict[str, int | None] = {}
    for field in ("total", "completed"):
        value = payload.get(field)
        if value is None:
            numeric[field] = None
        elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RuntimeIntegrityError(f"{field} inválido no progresso do modelo")
        else:
            numeric[field] = value
    if (
        numeric["total"] is not None
        and numeric["completed"] is not None
        and numeric["completed"] > numeric["total"]
    ):
        raise RuntimeIntegrityError("completed excede total no progresso do modelo")
    return PullProgress(
        status=status_value,
        digest=digest_value,
        total=numeric["total"],
        completed=numeric["completed"],
    )


def _iter_ndjson(response: object) -> Iterator[bytes]:
    iterator = getattr(response, "iter_bytes", None)
    if iterator is None:
        raise RuntimeIntegrityError("resposta de /api/pull não oferece stream de bytes")
    buffer = b""
    for chunk in iterator():
        if not isinstance(chunk, bytes):
            raise RuntimeIntegrityError("stream NDJSON retornou conteúdo não binário")
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if line.strip():
                yield line
    if buffer.strip():
        raise RuntimeIntegrityError("linha NDJSON truncada ao final do stream")


def _default_progress(model: str, event: PullProgress) -> None:
    if event.total and event.completed is not None:
        percentage = event.completed * 100 / event.total
        print(f"Modelo {model}: {percentage:6.2f}% ({event.status})", flush=True)


def pull_model_streaming(
    model: str,
    http: Any,
    journal: Path,
    *,
    on_progress: Callable[[PullProgress], None] | None = None,
    max_reconnects: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Puxa modelo via NDJSON, preservando journal e blobs entre reconexões."""
    if not model:
        raise ValueError("model não pode ser vazio")
    if max_reconnects < 0:
        raise ValueError("max_reconnects não pode ser negativo")
    callback = on_progress or (lambda event: _default_progress(model, event))
    reconnections = 0
    payload = {"model": model, "stream": True}

    while True:
        try:
            manager = http.stream("POST", "/api/pull", json=payload)
            with manager as response:
                status_code = int(getattr(response, "status_code", 0))
                if status_code < 200 or status_code >= 300:
                    raise RuntimeIntegrityError(
                        f"Ollama respondeu HTTP {status_code} em /api/pull"
                    )
                for line in _iter_ndjson(response):
                    progress = _parse_progress(line)
                    _journal_progress(journal, model, progress)
                    callback(progress)
                    if progress.status == "success":
                        return
            raise ConnectionError("stream terminou antes de status success")
        except RuntimeIntegrityError:
            raise
        except (ConnectionError, OSError, httpx.TransportError) as exc:
            if reconnections >= max_reconnects:
                raise RuntimeIntegrityError(
                    f"limite de reconexões excedido ao puxar {model}"
                ) from exc
            sleep(float(2**reconnections))
            reconnections += 1


def ensure_model_matrix(lock: ModelMatrixLock, ollama: object) -> None:
    """Reutiliza tags exatas, aborta drift e verifica cada modelo após o pull."""
    installed = installed_model_digests(ollama)
    drift = [
        f"digest divergente para {model.name}: esperado {model.digest}, atual {actual}"
        for model in lock.models
        if (actual := installed.get(model.name)) is not None and actual != model.digest
    ]
    if drift:
        raise RuntimeIntegrityError("; ".join(drift))

    pull_model = getattr(ollama, "pull_model", None)
    if pull_model is None:
        raise TypeError("cliente Ollama deve fornecer pull_model")
    for model in lock.models:
        if installed.get(model.name) == model.digest:
            continue
        pull_model(model.name)
        installed = installed_model_digests(ollama)
        actual = installed.get(model.name)
        if actual != model.digest:
            current = actual if actual is not None else "<ausente>"
            raise RuntimeIntegrityError(
                f"digest divergente após pull de {model.name}: "
                f"esperado {model.digest}, atual {current}"
            )


class _Process(Protocol):
    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


class OllamaServer:
    """Servidor Ollama standalone cujo ciclo de vida pertence a este processo."""

    def __init__(
        self,
        ollama_exe: Path,
        model_store: Path,
        *,
        process_factory: Callable[..., _Process] = subprocess.Popen,
        http: object | None = None,
        startup_timeout: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.ollama_exe = ollama_exe
        self.model_store = model_store
        self.process_factory = process_factory
        self._injected_http = http
        self._http: object | None = None
        self._owns_http = False
        self.startup_timeout = startup_timeout
        self.sleep = sleep
        self.base_url = ""
        self._process: _Process | None = None

    @staticmethod
    def _loopback_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])

    def __enter__(self) -> OllamaServer:
        if not self.ollama_exe.is_file():
            raise RuntimeIntegrityError(f"executável Ollama ausente: {self.ollama_exe}")
        self.model_store.mkdir(parents=True, exist_ok=True)
        port = self._loopback_port()
        self.base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        for key in list(env):
            if key.upper().startswith("OLLAMA_"):
                del env[key]
        env.update(
            {
                "OLLAMA_HOST": f"127.0.0.1:{port}",
                "OLLAMA_MODELS": str(self.model_store),
                "NO_PROXY": "127.0.0.1,localhost,::1",
            }
        )
        self._http = self._injected_http or httpx.Client(timeout=10.0)
        self._owns_http = self._injected_http is None
        try:
            self._process = self.process_factory(
                [str(self.ollama_exe), "serve"],
                env=env,
                creationflags=_CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._wait_until_ready()
        except BaseException:
            self.close()
            raise
        return self

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self.startup_timeout
        last_error: BaseException | None = None
        while time.monotonic() < deadline:
            if self._process is None or self._process.poll() is not None:
                raise RuntimeIntegrityError("processo Ollama encerrou durante a inicialização")
            try:
                payload = self.get_json("/api/version")
                version = payload.get("version")
                if version != OLLAMA_VERSION:
                    raise RuntimeIntegrityError(
                        f"versão Ollama divergente: esperada {OLLAMA_VERSION}, atual {version}"
                    )
                return
            except RuntimeIntegrityError:
                raise
            except (ConnectionError, OSError, httpx.TransportError) as exc:
                last_error = exc
                self.sleep(0.2)
        raise RuntimeIntegrityError("timeout aguardando Ollama privado") from last_error

    def _url(self, path: str) -> str:
        if not path.startswith("/") or "://" in path:
            raise RuntimeIntegrityError(f"endpoint Ollama inseguro: {path}")
        return self.base_url + path

    def get_json(self, path: str) -> Mapping[str, object]:
        if self._http is None:
            raise RuntimeError("servidor Ollama ainda não foi iniciado")
        get = getattr(self._http, "get", None)
        if get is None:
            raise TypeError("cliente HTTP deve fornecer get")
        return _response_json(get(self._url(path), timeout=10.0))

    def stream(self, method: str, path: str, **kwargs: object) -> AbstractContextManager[Any]:
        if self._http is None:
            raise RuntimeError("servidor Ollama ainda não foi iniciado")
        stream = getattr(self._http, "stream", None)
        if stream is None:
            raise TypeError("cliente HTTP deve fornecer stream")
        response = stream(method, self._url(path), **kwargs)
        if hasattr(response, "__enter__"):
            return cast(AbstractContextManager[Any], response)
        return nullcontext(response)

    def pull_model(self, model: str) -> None:
        journal_name = hashlib.sha256(model.encode("utf-8")).hexdigest() + ".json"
        pull_model_streaming(
            model,
            self,
            self.model_store / ".pull-journal" / journal_name,
        )

    def close(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
        if self._owns_http and self._http is not None:
            close = getattr(self._http, "close", None)
            if close is not None:
                close()
        self._http = None
        self._owns_http = False

    def __exit__(self, *_args: object) -> None:
        self.close()
