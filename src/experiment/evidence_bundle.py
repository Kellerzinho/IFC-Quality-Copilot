"""Empacotamento determinístico e privado das evidências do benchmark."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from src.experiment.ground_truth_validation import sha256_file


@dataclass(frozen=True)
class RemovedField:
    """Registra apenas onde e por que um valor foi removido."""

    path: str
    reason: str


@dataclass(frozen=True)
class PrivacyFinding:
    """Descreve uma ocorrência sensível sem guardar o seu conteúdo."""

    path: str
    kind: str
    line: int


class EvidencePrivacyError(ValueError):
    """Indica que uma evidência não pode ser publicada com segurança."""


class EvidenceManifestError(ValueError):
    """Indica que o manifesto não representa exatamente o pacote."""


class FailureCode(StrEnum):
    """Códigos estáveis das falhas observáveis pelo instalador."""

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
    r"(?:user(?:name)?|host(?:name)?|serial|mac|ip_address|api[_-]?key|token|secret|"
    r"password|ollama_key)",
    re.IGNORECASE,
)
SECRET_ENV_KEYS = re.compile(
    r"(?:TOKEN|SECRET|PASSWORD|API[_-]?KEY|OLLAMA[_-]?KEY)",
    re.IGNORECASE,
)
SENSITIVE_TEXT_PATTERNS = {
    "ipv6": re.compile(r"(?<![\w:.])\[?[0-9a-f:.]*:[0-9a-f:.]+\]?(?![\w:.])", re.I),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "mac": re.compile(r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", re.I),
    "bearer-token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.I),
    "assigned-secret": re.compile(
        r"\b(?:api[_-]?key|token|secret|password|ollama[_-]?key)\s*[:=]\s*[^\s,;]+",
        re.I,
    ),
}

SAFE_TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".txt",
    ".log",
    ".yaml",
    ".yml",
    ".csv",
    ".md",
}
FORBIDDEN_NAMES = {".env", "id_ed25519", "id_ed25519.pub"}
DETERMINISTIC_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _parsed_ip_candidate(
    kind: str, raw: str
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Valida um candidato textual e confirma a família solicitada."""
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
    """Permite somente endereços que identificam o serviço local."""
    address = _parsed_ip_candidate(kind, raw)
    return bool(address and (address.is_loopback or address.is_unspecified))


def collect_forbidden_values(
    environment: Mapping[str, str],
    *,
    dotenv_paths: Iterable[Path] = (),
    base_values: Iterable[str] = (),
) -> set[str]:
    """Coleta segredos em memória sem registrá-los ou serializá-los."""
    values = {str(value) for value in base_values if str(value)}
    values.update(
        value for key, value in environment.items() if SECRET_ENV_KEYS.search(key) and value
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
    """Traduz uma exceção do empacotador para um código estável."""
    if isinstance(error, EvidencePrivacyError):
        return FailureCode.PRIVACY_SCAN_FAILED
    if isinstance(error, EvidenceManifestError):
        return FailureCode.EVIDENCE_MANIFEST_FAILED
    if isinstance(error, OSError):
        return FailureCode.EVIDENCE_IO_FAILED
    return FailureCode.UNKNOWN_FAILED


def _read_text_strict(path: Path) -> str:
    """Lê apenas UTF-8 textual, sem NUL nem controles C0 proibidos."""
    try:
        text = path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise EvidencePrivacyError(f"texto UTF-8 invalido: {path.name}") from error
    if "\x00" in text or any(
        ord(character) < 32 and character not in "\t\r\n" for character in text
    ):
        raise EvidencePrivacyError(f"texto UTF-8 invalido: {path.name}")
    return text


def _evidence_files(root: Path, *, excluded_paths: Iterable[Path] = ()) -> list[Path]:
    """Enumera arquivos textuais contidos na raiz e falha fechado."""
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
            contained = os.path.commonpath((str(root_resolved), str(resolved))) == str(
                root_resolved
            )
        except ValueError:
            contained = False
        if not contained:
            raise EvidencePrivacyError(f"arquivo fora da raiz: {relative}")
        if resolved in excluded:
            continue
        if (
            candidate.name.lower() in FORBIDDEN_NAMES
            or candidate.suffix.lower() not in SAFE_TEXT_SUFFIXES
        ):
            raise EvidencePrivacyError(f"arquivo nao permitido: {relative}")
        _read_text_strict(candidate)
        files.append(candidate)
    return files


def _write_deterministic_member(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    """Escreve um membro ZIP com metadados reproduzíveis."""
    info = zipfile.ZipInfo(name, date_time=DETERMINISTIC_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(
        info,
        payload,
        compress_type=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    )


def redact_sensitive(
    value: Any,
    *,
    forbidden_values: set[str],
    path: str = "",
) -> tuple[Any, list[RemovedField]]:
    """Remove chaves sensíveis e mascara valores conhecidos recursivamente."""
    removed: list[RemovedField] = []
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, child in value.items():
            child_path = f"{path}.{key}".strip(".")
            if SENSITIVE_KEYS.search(str(key)):
                removed.append(RemovedField(child_path, "sensitive-key"))
                continue
            clean_child, child_removed = redact_sensitive(
                child,
                forbidden_values=forbidden_values,
                path=child_path,
            )
            clean[str(key)] = clean_child
            removed.extend(child_removed)
        return clean, removed
    if isinstance(value, list):
        clean_list: list[Any] = []
        for index, child in enumerate(value):
            clean_child, child_removed = redact_sensitive(
                child,
                forbidden_values=forbidden_values,
                path=f"{path}[{index}]",
            )
            clean_list.append(clean_child)
            removed.extend(child_removed)
        return clean_list, removed
    if isinstance(value, str):
        clean_text = value
        for forbidden in sorted((item for item in forbidden_values if item), key=len, reverse=True):
            if forbidden.casefold() in clean_text.casefold():
                clean_text = re.sub(
                    re.escape(forbidden),
                    "[REDACTED]",
                    clean_text,
                    flags=re.I,
                )
                removed.append(RemovedField(path, "known-value"))
        return clean_text, removed
    return value, removed


def _sensitive_key_paths(value: Any, *, prefix: str = "") -> list[str]:
    """Localiza chaves estruturais proibidas em JSON ou JSONL."""
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
    """Carrega JSON ou cada registro não vazio de um JSONL."""
    try:
        if path.suffix.lower() == ".json":
            return [(1, json.loads(_read_text_strict(path)))]
        return [
            (line_number, json.loads(line))
            for line_number, line in enumerate(_read_text_strict(path).splitlines(), 1)
            if line.strip()
        ]
    except json.JSONDecodeError as error:
        raise EvidencePrivacyError(f"JSON invalido: {path.name}") from error


def scan_sensitive_text(
    root: Path,
    *,
    forbidden_values: set[str],
    excluded_paths: Iterable[Path] = (),
) -> list[PrivacyFinding]:
    """Procura ocorrências sensíveis restantes sem expor seus valores."""
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
                    if (
                        kind in {"ipv4", "ipv6"}
                        and _parsed_ip_candidate(kind, match.group()) is None
                    ):
                        continue
                    if _allowed_local_ip(kind, match.group()):
                        continue
                    findings.append(PrivacyFinding(relative, kind, number))
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind))


def sanitize_text_files(
    root: Path,
    *,
    forbidden_values: set[str],
    excluded_paths: Iterable[Path] = (),
) -> list[RemovedField]:
    """Sanitiza primeiro JSON estruturalmente e depois todo texto por padrões."""
    removed: list[RemovedField] = []
    for candidate in _evidence_files(root, excluded_paths=excluded_paths):
        suffix = candidate.suffix.lower()
        if suffix in {".json", ".jsonl"}:
            sanitized_documents: list[Any] = []
            for line_number, document in _structured_documents(candidate):
                clean, document_removed = redact_sensitive(
                    document,
                    forbidden_values=forbidden_values,
                    path=f"{candidate.relative_to(root).as_posix()}:{line_number}",
                )
                sanitized_documents.append(clean)
                removed.extend(document_removed)
            if suffix == ".json":
                serialized = (
                    json.dumps(
                        sanitized_documents[0],
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                )
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
                removed.append(
                    RemovedField(
                        candidate.relative_to(root).as_posix(),
                        f"known-value:{matches}",
                    )
                )
        for kind, pattern in SENSITIVE_TEXT_PATTERNS.items():
            replacements = 0

            def replace_match(match: re.Match[str], pattern_kind: str = kind) -> str:
                nonlocal replacements
                if (
                    pattern_kind in {"ipv4", "ipv6"}
                    and _parsed_ip_candidate(pattern_kind, match.group()) is None
                ):
                    return match.group()
                if _allowed_local_ip(pattern_kind, match.group()):
                    return match.group()
                replacements += 1
                return "[REDACTED]"

            text = pattern.sub(replace_match, text)
            if replacements:
                removed.append(
                    RemovedField(
                        candidate.relative_to(root).as_posix(),
                        f"{kind}:{replacements}",
                    )
                )
        candidate.write_bytes(text.encode("utf-8"))
    return removed


def parse_llmfit_recommendations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Valida o envelope mínimo da saída JSON do llmfit."""
    rows = payload.get("models")
    if not isinstance(rows, list):
        raise ValueError("llmfit JSON deve conter envelope models[]")
    if any(
        not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip()
        for row in rows
    ):
        raise ValueError("cada modelo llmfit deve ter name não vazio")
    return [dict(row) for row in rows]


def filter_llmfit_recommendations(
    rows: list[dict[str, Any]], locked: set[str]
) -> list[dict[str, Any]]:
    """Remove recomendações já representadas pelo lock do experimento."""
    return [
        row
        for row in rows
        if {str(row["name"]), str(row.get("ollama_name") or "")}.isdisjoint(locked)
    ]


def build_file_manifest(root: Path) -> list[dict[str, object]]:
    """Calcula caminho, tamanho e SHA-256 de cada evidência permitida."""
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in _evidence_files(root)
    ]


def write_manifest(path: Path, entries: list[dict[str, object]]) -> None:
    """Grava manifesto canônico em JSON UTF-8."""
    path.write_bytes(
        (
            json.dumps(
                {"files": entries},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    )


def _manifest_map(raw: bytes) -> dict[str, tuple[int, str]]:
    """Valida integralmente o schema e os caminhos de um manifesto."""
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
            if (
                not name
                or pure.is_absolute()
                or ".." in pure.parts
                or "\\" in name
                or pure.as_posix() != name
                or name == "manifest.json"
            ):
                raise ValueError("unsafe path")
            size = row["size_bytes"]
            digest = row["sha256"]
            if (
                not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
                or not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or name in result
            ):
                raise ValueError("invalid entry")
            result[name] = (size, digest)
        if list(result) != sorted(result):
            raise ValueError("unsorted entries")
        return result
    except (
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        raise EvidenceManifestError("manifesto invalido") from error


def validate_manifest(path: Path, root: Path) -> list[str]:
    """Compara o manifesto em disco à árvore textual atual."""
    try:
        expected = _manifest_map(path.read_bytes())
        actual = {
            str(item["path"]): (cast(int, item["size_bytes"]), str(item["sha256"]))
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
    """Reabre um ZIP e confere árvore, tamanho e SHA-256 de cada membro."""
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
    """Sanitiza, valida e publica atomicamente o pacote principal."""
    temporary = output.with_suffix(output.suffix + ".partial")
    excluded = (output, temporary)
    sanitize_text_files(
        root,
        forbidden_values=forbidden_values,
        excluded_paths=excluded,
    )
    findings = scan_sensitive_text(
        root,
        forbidden_values=forbidden_values,
        excluded_paths=excluded,
    )
    if findings:
        raise EvidencePrivacyError(
            "; ".join(f"{item.kind}:{item.path}:{item.line}" for item in findings)
        )
    payload_files = _evidence_files(root, excluded_paths=excluded)
    manifest_path = root / "manifest.json"
    write_manifest(
        manifest_path,
        [
            {
                "path": candidate.relative_to(root).as_posix(),
                "size_bytes": candidate.stat().st_size,
                "sha256": sha256_file(candidate),
            }
            for candidate in payload_files
        ],
    )
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            _write_deterministic_member(
                archive,
                "manifest.json",
                manifest_path.read_bytes(),
            )
            for candidate in payload_files:
                _write_deterministic_member(
                    archive,
                    candidate.relative_to(root).as_posix(),
                    candidate.read_bytes(),
                )
        validation_errors = validate_evidence_archive(temporary)
        if validation_errors:
            raise EvidenceManifestError("; ".join(validation_errors))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def create_partial_evidence_zip(
    output: Path,
    *,
    status: Literal["failed", "interrupted"],
    reason_code: FailureCode,
) -> Path:
    """Publica fallback mínimo sem ler evidências potencialmente sensíveis."""
    if status not in {"failed", "interrupted"}:
        raise ValueError("status parcial invalido")
    if not isinstance(reason_code, FailureCode):
        raise TypeError("reason_code deve ser FailureCode")
    members = {
        "README.txt": b"Pacote parcial: o benchmark nao foi concluido.\n",
        "status.json": (
            json.dumps(
                {
                    "partial": True,
                    "reason_code": reason_code.value,
                    "status": status,
                },
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
        "privacy-report.json": b'{"raw_files_included":false,"status":"safe-minimal"}\n',
    }
    manifest = [
        {
            "path": name,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
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
