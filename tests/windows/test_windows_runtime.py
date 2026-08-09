"""Contratos do runtime Windows isolado usado pelo pacote de benchmark."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from src.experiment.model_lock import ModelMatrixLock, load_model_lock
from src.experiment.windows_runtime import (
    OLLAMA_RUNTIME_RELATIVE,
    DownloadSpec,
    OllamaServer,
    PullProgress,
    RuntimeIntegrityError,
    assert_app_owned,
    download_verified,
    ensure_model_matrix,
    installed_model_digests,
    ollama_executable,
    pull_model_streaming,
    safe_extract_zip,
    select_runtime_assets,
    validate_tool_pins,
)

ROOT = Path(__file__).resolve().parents[2]


class ByteResponse:
    """Resposta externa controlada; o filesystem exercitado continua sendo real."""

    def __init__(self, status_code: int, chunks: list[bytes | BaseException]) -> None:
        self.status_code = status_code
        self._chunks = chunks

    def __enter__(self) -> ByteResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def iter_bytes(self) -> Iterator[bytes]:
        for chunk in self._chunks:
            if isinstance(chunk, BaseException):
                raise chunk
            yield chunk


class QueueHTTP:
    def __init__(self, responses: list[ByteResponse | BaseException]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, str], object | None]] = []

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: object | None = None,
        **_kwargs: object,
    ) -> ByteResponse:
        self.calls.append((method, url, dict(headers or {}), json))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


@pytest.fixture
def model_lock() -> ModelMatrixLock:
    return load_model_lock(ROOT / "src/experiment/results/models.lock.json")


def _spec(payload: bytes) -> DownloadSpec:
    return DownloadSpec(
        url="https://official.invalid/a.zip",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _zip_with_members(path: Path, members: Mapping[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            # ZipInfo normaliza ``\\`` para ``/`` no Windows. Gravamos o membro
            # e restauramos o byte cru depois para realmente simular ZIP hostil.
            archive.writestr(name.replace("\\", "/"), payload)
    raw = path.read_bytes()
    for name in members:
        if "\\" in name:
            raw = raw.replace(name.replace("\\", "/").encode(), name.encode())
    path.write_bytes(raw)
    return path


def test_download_reuses_exact_cached_file_without_network(tmp_path: Path) -> None:
    destination = tmp_path / "asset.zip"
    destination.write_bytes(b"correct")
    http = QueueHTTP([])

    assert download_verified(_spec(b"correct"), destination, http=http) == destination

    assert http.calls == []


def test_download_resumes_partial_and_verifies_before_replace(tmp_path: Path) -> None:
    destination = tmp_path / "asset.zip"
    destination.with_suffix(".zip.partial").write_bytes(b"first-")
    http = QueueHTTP([ByteResponse(206, [b"second"])])

    download_verified(_spec(b"first-second"), destination, http=http, sleep=lambda _: None)

    assert http.calls[0][2] == {"Range": "bytes=6-"}
    assert destination.read_bytes() == b"first-second"
    assert not destination.with_suffix(".zip.partial").exists()


def test_download_restarts_when_server_ignores_range(tmp_path: Path) -> None:
    destination = tmp_path / "asset.zip"
    destination.with_suffix(".zip.partial").write_bytes(b"stale-")
    http = QueueHTTP([ByteResponse(200, [b"fresh-content"])])

    download_verified(_spec(b"fresh-content"), destination, http=http, sleep=lambda _: None)

    assert destination.read_bytes() == b"fresh-content"


def test_download_retries_transport_failure_and_never_promotes_wrong_hash(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "asset.zip"
    http = QueueHTTP(
        [
            ConnectionResetError("drop"),
            ByteResponse(200, [b"wrong"]),
            ByteResponse(200, [b"correct"]),
        ]
    )

    download_verified(_spec(b"correct"), destination, http=http, sleep=lambda _: None)

    assert len(http.calls) == 3
    assert destination.read_bytes() == b"correct"


def test_download_wrong_hash_exhausts_retries_without_overwriting_cache(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "asset.zip"
    destination.write_bytes(b"old-invalid")
    http = QueueHTTP([ByteResponse(200, [b"corrupt"]) for _ in range(3)])

    with pytest.raises(RuntimeIntegrityError, match="SHA-256"):
        download_verified(_spec(b"correct"), destination, http=http, sleep=lambda _: None)

    assert not destination.exists()
    assert not destination.with_suffix(".zip.partial").exists()


def test_download_refuses_destination_outside_app_owned_root(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    outside = tmp_path / "outside" / "asset.zip"
    http = QueueHTTP([ByteResponse(200, [b"correct"])])

    with pytest.raises(RuntimeIntegrityError, match="app-owned"):
        download_verified(_spec(b"correct"), outside, http=http, app_root=app_root)

    assert http.calls == []


@pytest.mark.parametrize(
    "member",
    [
        "../escape",
        "/absolute",
        "C:/escape",
        "C:\\escape",
        "\\\\server\\share\\escape",
        "//server/share/escape",
        "folder\\backslash.txt",
        "folder/file.txt:stream",
        "folder/../escape",
        "./relative",
    ],
)
def test_safe_extract_rejects_unsafe_member_before_writing(
    tmp_path: Path, member: str
) -> None:
    archive = _zip_with_members(tmp_path / "malicious.zip", {member: b"bad"})
    target = tmp_path / "target"

    with pytest.raises(RuntimeIntegrityError, match=r"inseguro|fora"):
        safe_extract_zip(archive, target)

    assert not target.exists()


def test_safe_extract_rejects_symlink_member_before_writing(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "target")

    with pytest.raises(RuntimeIntegrityError, match="symlink"):
        safe_extract_zip(archive_path, tmp_path / "target")

    assert not (tmp_path / "target").exists()


def test_app_owned_boundary_does_not_accept_prefix_sibling(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    sibling = tmp_path / "app-evil" / "asset.zip"
    sibling.parent.mkdir()

    with pytest.raises(RuntimeIntegrityError, match="app-owned"):
        assert_app_owned(sibling, app_root)


def test_ollama_post_extract_executable_uses_canonical_windows_path(tmp_path: Path) -> None:
    release_root = tmp_path / "release"
    archive = _zip_with_members(tmp_path / "ollama.zip", {"ollama.exe": b"MZ-test"})
    destination = release_root / OLLAMA_RUNTIME_RELATIVE

    safe_extract_zip(archive, destination, app_root=release_root)

    executable = ollama_executable(release_root)
    assert executable == release_root / "tools/ollama/0.32.5/windows-amd64/ollama.exe"
    assert executable.read_bytes() == b"MZ-test"


def test_runtime_assets_are_exact_and_rocm_is_only_selected_for_amd() -> None:
    cpu = select_runtime_assets(["Intel UHD Graphics"])
    amd = select_runtime_assets(["AMD Radeon RX 7900 XTX"])

    assert [str(item.url) for item in cpu.ollama] == [
        "https://github.com/ollama/ollama/releases/download/v0.32.5/ollama-windows-amd64.zip"
    ]
    assert [item.sha256 for item in amd.ollama] == [
        "7c941ae084569d298062d29f8139163a3187c76dbca0479c70d085e78fd8c7bb",
        "f2284e7008ffd64eadb7a05ac4ca1a0de843d1e8d0c861aa0923ef855ca94615",
    ]
    assert amd.llmfit.sha256 == (
        "bf8a509d68bc02f4cafc7040501938a30841eeb8c496eda51ae886a2f43a88e2"
    )


def test_manifest_tool_pin_drift_is_fatal() -> None:
    plan = select_runtime_assets([])
    manifest = {
        "tools": {
            "ollama": {
                "version": "0.32.5",
                "url": str(plan.ollama[0].url),
                "sha256": plan.ollama[0].sha256,
                "size_bytes": plan.ollama[0].size_bytes,
            },
            "ollama_rocm": {
                "version": "0.32.5",
                "url": str(select_runtime_assets(["AMD"]).ollama[1].url),
                "sha256": select_runtime_assets(["AMD"]).ollama[1].sha256,
                "size_bytes": select_runtime_assets(["AMD"]).ollama[1].size_bytes,
            },
            "llmfit": {
                "version": "1.1.8",
                "url": str(plan.llmfit.url),
                "sha256": plan.llmfit.sha256,
                "size_bytes": plan.llmfit.size_bytes,
            },
        }
    }
    validate_tool_pins(manifest)
    manifest["tools"]["ollama"]["sha256"] = "0" * 64

    with pytest.raises(RuntimeIntegrityError, match=r"pin.*ollama|ollama.*pin"):
        validate_tool_pins(manifest)


class PullingOllama:
    def __init__(self, tags: Mapping[str, str]) -> None:
        self.tags = dict(tags)
        self.after_pull: dict[str, str] = {}
        self.pulls: list[str] = []

    def get_json(self, path: str) -> dict[str, object]:
        assert path == "/api/tags"
        return {
            "models": [
                {"name": name, "model": name, "digest": f"sha256:{digest}"}
                for name, digest in self.tags.items()
            ]
        }

    def pull_model(self, name: str, **_kwargs: object) -> None:
        self.pulls.append(name)
        if name in self.after_pull:
            self.tags[name] = self.after_pull[name]


def test_exact_models_are_reused_without_pull(model_lock: ModelMatrixLock) -> None:
    ollama = PullingOllama({model.name: model.digest for model in model_lock.models})

    ensure_model_matrix(model_lock, ollama)

    assert ollama.pulls == []


def test_missing_model_is_pulled_then_verified(model_lock: ModelMatrixLock) -> None:
    missing = model_lock.models[0]
    ollama = PullingOllama(
        {model.name: model.digest for model in model_lock.models[1:]}
    )
    ollama.after_pull[missing.name] = missing.digest

    ensure_model_matrix(model_lock, ollama)

    assert ollama.pulls == [missing.name]


def test_existing_digest_drift_aborts_before_any_pull(model_lock: ModelMatrixLock) -> None:
    first, second = model_lock.models[:2]
    ollama = PullingOllama({first.name: "0" * 64})
    ollama.after_pull[second.name] = second.digest

    with pytest.raises(RuntimeIntegrityError, match="digest"):
        ensure_model_matrix(model_lock, ollama)

    assert ollama.pulls == []


def test_post_pull_digest_drift_is_fatal(model_lock: ModelMatrixLock) -> None:
    missing = model_lock.models[0]
    ollama = PullingOllama(
        {model.name: model.digest for model in model_lock.models[1:]}
    )
    ollama.after_pull[missing.name] = "0" * 64

    with pytest.raises(RuntimeIntegrityError, match="digest"):
        ensure_model_matrix(model_lock, ollama)


def test_installed_models_require_full_sha256_digest() -> None:
    ollama = PullingOllama({"m:test": "abc"})

    with pytest.raises(RuntimeIntegrityError, match="digest"):
        installed_model_digests(ollama)


def test_pull_streams_ndjson_reports_progress_and_reconnects(tmp_path: Path) -> None:
    journal = tmp_path / "pull.json"
    progress: list[PullProgress] = []
    http = QueueHTTP(
        [
            ByteResponse(
                200,
                [
                    b'{"status":"pulling manifest"}\n',
                    b'{"status":"downloading","digest":"sha256:abc",',
                    b'"total":100,"completed":40}\n',
                    ConnectionResetError("drop"),
                ],
            ),
            ByteResponse(
                200,
                [
                    b'{"status":"downloading","digest":"sha256:abc",'
                    b'"total":100,"completed":100}\n',
                    b'{"status":"success"}\n',
                ],
            ),
        ]
    )

    pull_model_streaming(
        "m:test",
        http,
        journal,
        on_progress=progress.append,
        max_reconnects=3,
        sleep=lambda _: None,
    )

    assert [(call[1], call[3]) for call in http.calls] == [
        ("/api/pull", {"model": "m:test", "stream": True}),
        ("/api/pull", {"model": "m:test", "stream": True}),
    ]
    assert [event.completed for event in progress if event.total] == [40, 100]
    assert json.loads(journal.read_text(encoding="utf-8"))["status"] == "success"


@pytest.mark.parametrize(
    ("line", "message"),
    [
        (b"not-json\n", "NDJSON"),
        (b'{"error":"registry denied"}\n', "registry denied"),
    ],
)
def test_pull_rejects_malformed_ndjson_and_server_error(
    tmp_path: Path, line: bytes, message: str
) -> None:
    http = QueueHTTP([ByteResponse(200, [line])])

    with pytest.raises(RuntimeIntegrityError, match=message):
        pull_model_streaming(
            "m:test", http, tmp_path / "pull.json", sleep=lambda _: None
        )


def test_pull_stops_after_three_reconnections_without_deleting_journal(
    tmp_path: Path,
) -> None:
    http = QueueHTTP(
        [ByteResponse(200, [ConnectionResetError("drop")]) for _ in range(4)]
    )
    journal = tmp_path / "pull.json"

    with pytest.raises(RuntimeIntegrityError, match="reconex"):
        pull_model_streaming(
            "m:test", http, journal, max_reconnects=3, sleep=lambda _: None
        )

    assert len(http.calls) == 4


class JsonResponse:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.status_code = 200
        self._payload = dict(payload)

    def json(self) -> dict[str, object]:
        return dict(self._payload)


class ServerHTTP:
    def __init__(self, version: str = "0.32.5") -> None:
        self.version = version
        self.urls: list[str] = []

    def get(self, url: str, **_kwargs: object) -> JsonResponse:
        self.urls.append(url)
        if url.endswith("/api/version"):
            return JsonResponse({"version": self.version})
        return JsonResponse({"models": []})


class OwnedProcess:
    def __init__(self) -> None:
        self.pid = 4242
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class ProcessFactory:
    def __init__(self) -> None:
        self.process = OwnedProcess()
        self.command: list[str] | None = None
        self.kwargs: dict[str, Any] = {}

    def __call__(self, command: list[str], **kwargs: object) -> OwnedProcess:
        self.command = command
        self.kwargs = dict(kwargs)
        return self.process


def test_ollama_server_uses_private_store_and_terminates_only_owned_process(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "release" / OLLAMA_RUNTIME_RELATIVE / "ollama.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"MZ-test")
    store = tmp_path / "models" / ("a" * 64)
    factory = ProcessFactory()
    http = ServerHTTP()

    with OllamaServer(
        executable,
        store,
        process_factory=factory,
        http=http,
        sleep=lambda _: None,
    ) as server:
        assert server.base_url.startswith("http://127.0.0.1:")
        assert factory.process.terminated is False

    assert factory.command == [str(executable), "serve"]
    assert factory.kwargs["env"]["OLLAMA_MODELS"] == str(store)
    assert factory.kwargs["env"]["OLLAMA_HOST"].startswith("127.0.0.1:")
    assert factory.process.terminated is True
    assert factory.process.killed is False


def test_ollama_server_rejects_wrong_version_and_stops_owned_process(tmp_path: Path) -> None:
    executable = tmp_path / "ollama.exe"
    executable.write_bytes(b"MZ-test")
    factory = ProcessFactory()

    with pytest.raises(RuntimeIntegrityError, match="versão"), OllamaServer(
        executable,
        tmp_path / "models",
        process_factory=factory,
        http=ServerHTTP("0.99.0"),
        sleep=lambda _: None,
    ):
        pass

    assert factory.process.terminated is True
