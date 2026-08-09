"""Inventario Windows anonimo e recomendacoes auxiliares do llmfit."""

from __future__ import annotations

import csv
import ipaddress
import json
import math
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from src.experiment.evidence_bundle import (
    filter_llmfit_recommendations,
    parse_llmfit_recommendations,
    redact_sensitive,
)

ProbeStatus = Literal["ok", "unavailable"]
InventoryStatus = Literal["ok", "partial", "unavailable"]
ErrorType = Literal["CommandNotFound", "Timeout", "ParseError", "ExitCode"]
CommandRunner = Callable[..., Any]

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_COLLECTOR = _PROJECT_ROOT / "windows" / "collect-hardware.ps1"
_ERROR_TYPES = frozenset({"CommandNotFound", "Timeout", "ParseError", "ExitCode"})
_MISSING_NUMERIC = frozenset({"", "n/a", "na", "[n/a]", "[not supported]"})
_MAC_RE = re.compile(r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", re.IGNORECASE)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_PROFILE_RE = re.compile(r"(?i)\b[a-z]:\\users\\[^\\/\s]+")
_UNC_RE = re.compile(r"(?i)\\\\[^\\\s]+\\[^\\\s]+")
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_ASSIGNED_SECRET_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,;]+"
)


@dataclass(frozen=True)
class ProbeRecord:
    """Estado publico de um comando auxiliar, sem mensagem ou caminho privado."""

    status: ProbeStatus
    error_type: ErrorType | None = None


@dataclass(frozen=True)
class LlmfitInventoryResult:
    """Resumo dos quatro probes llmfit e dos modelos que nao estao no lock."""

    status: InventoryStatus
    commands: dict[str, ProbeRecord]
    extra_models: list[dict[str, Any]]


def _text_output(result: object, attribute: str) -> str:
    value = getattr(result, attribute, "")
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _run(
    runner: CommandRunner,
    command: list[str],
    *,
    timeout_seconds: float,
) -> object:
    return runner(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )


def _exception_error(error: BaseException) -> ErrorType:
    if isinstance(error, subprocess.TimeoutExpired):
        return "Timeout"
    if isinstance(error, (FileNotFoundError, PermissionError, OSError)):
        return "CommandNotFound"
    return "ParseError"


def _unavailable(error_type: str | None = None) -> dict[str, str]:
    safe_type = error_type if error_type in _ERROR_TYPES else "ParseError"
    return {"status": "unavailable", "error_type": safe_type}


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _lookup(source: Mapping[str, Any], *aliases: str) -> Any:
    indexed = {_normalized_key(key): value for key, value in source.items()}
    for alias in aliases:
        key = _normalized_key(alias)
        if key in indexed:
            return indexed[key]
    return None


def _safe_scalar(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return None


def _select_fields(
    source: Mapping[str, Any], fields: Mapping[str, tuple[str, ...]]
) -> dict[str, str | int | float | bool | None]:
    return {
        destination: _safe_scalar(_lookup(source, destination, *aliases))
        for destination, aliases in fields.items()
    }


def _unwrap_probe(source: object) -> tuple[object | None, str | None]:
    if not isinstance(source, Mapping):
        return source, None
    status = _lookup(cast(Mapping[str, Any], source), "status")
    if isinstance(status, str) and status.casefold() == "unavailable":
        error = _lookup(cast(Mapping[str, Any], source), "error_type")
        return None, str(error) if error is not None else "ParseError"
    if isinstance(status, str) and status.casefold() == "ok" and _lookup(
        cast(Mapping[str, Any], source), "data"
    ) is not None:
        return _lookup(cast(Mapping[str, Any], source), "data"), None
    return source, None


def _record_sort_key(record: Mapping[str, object]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalise_one(
    source: object, fields: Mapping[str, tuple[str, ...]]
) -> dict[str, Any]:
    raw, error = _unwrap_probe(source)
    if error is not None or not isinstance(raw, Mapping):
        return _unavailable(error)
    return _select_fields(cast(Mapping[str, Any], raw), fields)


def _normalise_many(
    source: object, fields: Mapping[str, tuple[str, ...]]
) -> list[dict[str, Any]] | dict[str, str]:
    raw, error = _unwrap_probe(source)
    if error is not None:
        return _unavailable(error)
    if isinstance(raw, Mapping):
        rows: list[object] = [raw]
    elif isinstance(raw, list):
        rows = raw
    else:
        return _unavailable("ParseError")
    clean = [
        cast(dict[str, object], _select_fields(cast(Mapping[str, Any], row), fields))
        for row in rows
        if isinstance(row, Mapping)
    ]
    return sorted(clean, key=_record_sort_key)


_OS_FIELDS = {
    "caption": ("Caption",),
    "version": ("Version",),
    "build_number": ("BuildNumber",),
    "architecture": ("OSArchitecture",),
}
_COMPUTER_FIELDS = {
    "manufacturer": ("Manufacturer",),
    "model": ("Model",),
    "system_type": ("SystemType",),
    "total_physical_memory": ("TotalPhysicalMemory",),
    "hypervisor_present": ("HypervisorPresent",),
}
_CPU_FIELDS = {
    "name": ("Name",),
    "manufacturer": ("Manufacturer",),
    "cores": ("NumberOfCores",),
    "logical_processors": ("NumberOfLogicalProcessors",),
    "max_clock_mhz": ("MaxClockSpeed",),
    "l2_cache_kib": ("L2CacheSize",),
    "l3_cache_kib": ("L3CacheSize",),
    "virtualization_firmware_enabled": ("VirtualizationFirmwareEnabled",),
}
_MEMORY_FIELDS = {
    "capacity_bytes": ("Capacity",),
    "speed_mhz": ("Speed",),
    "configured_clock_mhz": ("ConfiguredClockSpeed",),
    "manufacturer": ("Manufacturer",),
    "part_number": ("PartNumber",),
    "form_factor": ("FormFactor",),
}
_GPU_FIELDS = {
    "name": ("Name", "CardName"),
    "adapter_ram_bytes": ("AdapterRAM",),
    "driver_version": ("DriverVersion",),
    "driver_date": ("DriverDate",),
    "video_processor": ("VideoProcessor", "ChipType"),
    "status": ("Status",),
}
_DISK_FIELDS = {
    "model": ("Model",),
    "size_bytes": ("Size",),
    "interface_type": ("InterfaceType",),
    "media_type": ("MediaType",),
    "firmware_revision": ("FirmwareRevision",),
}
_VOLUME_FIELDS = {
    "device_id": ("DeviceID",),
    "drive_type": ("DriveType",),
    "file_system": ("FileSystem",),
    "size_bytes": ("Size",),
    "free_bytes": ("FreeSpace",),
}
_BIOS_FIELDS = {
    "manufacturer": ("Manufacturer",),
    "smbios_version": ("SMBIOSBIOSVersion",),
    "release_date": ("ReleaseDate",),
}
_BOARD_FIELDS = {
    "manufacturer": ("Manufacturer",),
    "product": ("Product",),
    "version": ("Version",),
}
_DRIVER_FIELDS = {
    "name": ("Name",),
    "driver_version": ("DriverVersion",),
    "driver_date": ("DriverDate",),
    "status": ("Status",),
}
_POWER_FIELDS = {"active_scheme_name": ("ActiveSchemeName",)}


def _normalise_powershell_inventory(payload: Mapping[str, Any]) -> dict[str, Any]:
    computer = _normalise_one(_lookup(payload, "computer"), _COMPUTER_FIELDS)
    memory_source, memory_error = _unwrap_probe(_lookup(payload, "memory"))
    if memory_error is not None:
        memory: dict[str, Any] = _unavailable(memory_error)
    else:
        modules = _normalise_many(memory_source, _MEMORY_FIELDS)
        total = computer.get("total_physical_memory")
        if not isinstance(total, int) or isinstance(total, bool):
            if isinstance(modules, list):
                capacities = [
                    row.get("capacity_bytes")
                    for row in modules
                    if isinstance(row.get("capacity_bytes"), int)
                    and not isinstance(row.get("capacity_bytes"), bool)
                ]
                total = sum(cast(list[int], capacities)) or None
            else:
                total = None
        memory = {"total_bytes": total, "modules": modules}

    storage_source, storage_error = _unwrap_probe(_lookup(payload, "storage"))
    if storage_error is not None or not isinstance(storage_source, Mapping):
        storage: dict[str, Any] = _unavailable(storage_error)
    else:
        storage_mapping = cast(Mapping[str, Any], storage_source)
        storage = {
            "disks": _normalise_many(_lookup(storage_mapping, "disks"), _DISK_FIELDS),
            "volumes": _normalise_many(
                _lookup(storage_mapping, "volumes"), _VOLUME_FIELDS
            ),
        }

    return {
        "schema_version": 1,
        "collector": {"status": "ok"},
        "os": _normalise_one(_lookup(payload, "os"), _OS_FIELDS),
        "computer": computer,
        "cpu": _normalise_many(_lookup(payload, "cpu"), _CPU_FIELDS),
        "memory": memory,
        "gpu": _normalise_many(_lookup(payload, "gpu"), _GPU_FIELDS),
        "storage": storage,
        "bios": _normalise_one(_lookup(payload, "bios"), _BIOS_FIELDS),
        "baseboard": _normalise_one(_lookup(payload, "baseboard"), _BOARD_FIELDS),
        "display_drivers": _normalise_many(
            _lookup(payload, "display_drivers"), _DRIVER_FIELDS
        ),
        "power": _normalise_one(_lookup(payload, "power"), _POWER_FIELDS),
    }


def _failed_powershell_inventory(error_type: ErrorType) -> dict[str, Any]:
    unavailable = _unavailable(error_type)
    return {
        "schema_version": 1,
        "collector": unavailable,
        "os": dict(unavailable),
        "computer": dict(unavailable),
        "cpu": dict(unavailable),
        "memory": dict(unavailable),
        "gpu": dict(unavailable),
        "storage": dict(unavailable),
        "bios": dict(unavailable),
        "baseboard": dict(unavailable),
        "display_drivers": dict(unavailable),
        "power": dict(unavailable),
    }


def _optional_int(value: str) -> int | None:
    if value.strip().casefold() in _MISSING_NUMERIC:
        return None
    number = int(value.strip())
    if number < 0:
        raise ValueError("negative numeric field")
    return number


def _optional_float(value: str) -> float | None:
    if value.strip().casefold() in _MISSING_NUMERIC:
        return None
    number = float(value.strip())
    if not math.isfinite(number) or number < 0:
        raise ValueError("invalid numeric field")
    return number


def parse_nvidia_smi(text: str) -> list[dict[str, object]]:
    """Converte o CSV restrito do nvidia-smi sem consultar UUID ou serial."""
    parsed: list[dict[str, object]] = []
    for row in csv.reader(text.splitlines(), skipinitialspace=True):
        if not row or not any(field.strip() for field in row):
            continue
        if len(row) != 7:
            raise ValueError("nvidia-smi CSV field count changed")
        index = _optional_int(row[0])
        if index is None or not row[1].strip():
            raise ValueError("nvidia-smi missing GPU identity")
        parsed.append(
            {
                "index": index,
                "name": row[1].strip(),
                "memory_total_mib": _optional_int(row[2]),
                "driver_version": row[3].strip() or None,
                "compute_capability": row[4].strip() or None,
                "performance_state": row[5].strip() or None,
                "power_limit_w": _optional_float(row[6]),
            }
        )
    if not parsed:
        raise ValueError("nvidia-smi returned no GPUs")
    return sorted(parsed, key=lambda row: (cast(int, row["index"]), str(row["name"])))


def _local_tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _child_text(parent: ET.Element | None, name: str) -> str | None:
    if parent is None:
        return None
    for child in parent:
        if _local_tag(child) == name:
            value = (child.text or "").strip()
            return value or None
    return None


def _first_descendant(root: ET.Element, name: str) -> ET.Element | None:
    return next((element for element in root.iter() if _local_tag(element) == name), None)


def parse_dxdiag(payload: str | bytes) -> dict[str, Any]:
    """Extrai somente DirectX e campos publicos de display do XML do dxdiag."""
    root = ET.fromstring(payload)
    system = _first_descendant(root, "SystemInformation")
    directx_version = _child_text(system, "DirectXVersion")
    displays: list[dict[str, str | None]] = []
    for device in (item for item in root.iter() if _local_tag(item) == "DisplayDevice"):
        displays.append(
            {
                "name": _child_text(device, "CardName"),
                "manufacturer": _child_text(device, "Manufacturer"),
                "video_processor": _child_text(device, "ChipType"),
                "display_memory": _child_text(device, "DisplayMemory"),
                "dedicated_memory": _child_text(device, "DedicatedMemory"),
                "shared_memory": _child_text(device, "SharedMemory"),
                "current_mode": _child_text(device, "CurrentMode"),
                "driver_name": _child_text(device, "DriverName"),
                "driver_version": _child_text(device, "DriverVersion"),
                "driver_date": _child_text(device, "DriverDate"),
                "feature_levels": _child_text(device, "FeatureLevels"),
                "driver_model": _child_text(device, "DriverModel"),
            }
        )
    if directx_version is None and not displays:
        raise ValueError("dxdiag XML has no supported fields")
    return {
        "directx_version": directx_version,
        "displays": sorted(displays, key=_record_sort_key),
    }


def _runtime_private_values(values: set[str] | None) -> set[str]:
    private = set(values or ())
    for name in (
        "USERNAME",
        "USER",
        "COMPUTERNAME",
        "HOSTNAME",
        "USERPROFILE",
        "HOME",
    ):
        value = os.environ.get(name)
        if value and len(value) >= 3:
            private.add(value)
    return private


def _redact_text(text: str, forbidden_values: set[str]) -> str:
    clean = text
    for forbidden in sorted(forbidden_values, key=lambda item: (-len(item), item.casefold())):
        if forbidden:
            clean = re.sub(re.escape(forbidden), "[REDACTED]", clean, flags=re.IGNORECASE)
    clean = _PROFILE_RE.sub("[REDACTED-PROFILE]", clean)
    clean = _UNC_RE.sub("[REDACTED-UNC]", clean)
    clean = _MAC_RE.sub("[REDACTED-MAC]", clean)
    clean = _BEARER_RE.sub("Bearer [REDACTED]", clean)
    clean = _ASSIGNED_SECRET_RE.sub("[REDACTED-SECRET]", clean)

    def redact_ipv4(match: re.Match[str]) -> str:
        try:
            ipaddress.IPv4Address(match.group())
        except ipaddress.AddressValueError:
            return match.group()
        return "[REDACTED-IP]"

    return _IPV4_RE.sub(redact_ipv4, clean)


def _redact_public_value(value: Any, forbidden_values: set[str]) -> Any:
    clean, _removed = redact_sensitive(value, forbidden_values=forbidden_values)
    if isinstance(clean, dict):
        return {
            str(key): _redact_public_value(child, forbidden_values)
            for key, child in clean.items()
        }
    if isinstance(clean, list):
        return [_redact_public_value(child, forbidden_values) for child in clean]
    if isinstance(clean, str):
        return _redact_text(clean, forbidden_values)
    return clean


def collect_windows_inventory(
    runner: CommandRunner = subprocess.run,
    *,
    powershell_script: Path | None = None,
    timeout_seconds: float = 30.0,
    forbidden_values: set[str] | None = None,
) -> dict[str, Any]:
    """Coleta hardware por fontes independentes e nunca propaga erro opcional."""
    private_values = _runtime_private_values(forbidden_values)
    collector = powershell_script or _DEFAULT_COLLECTOR
    powershell_command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(collector),
    ]
    try:
        result = _run(runner, powershell_command, timeout_seconds=timeout_seconds)
        if int(getattr(result, "returncode", 1)) != 0:
            inventory = _failed_powershell_inventory("ParseError")
        else:
            decoded = json.loads(_text_output(result, "stdout"))
            if not isinstance(decoded, Mapping):
                raise ValueError("PowerShell inventory root must be an object")
            inventory = _normalise_powershell_inventory(cast(Mapping[str, Any], decoded))
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        inventory = _failed_powershell_inventory(_exception_error(error))

    nvidia_command = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,driver_version,compute_cap,pstate,power.limit",
        "--format=csv,noheader,nounits",
    ]
    try:
        nvidia_result = _run(runner, nvidia_command, timeout_seconds=timeout_seconds)
        if int(getattr(nvidia_result, "returncode", 1)) != 0:
            raise ValueError("nvidia-smi failed")
        inventory["nvidia_smi"] = {
            "status": "ok",
            "data": parse_nvidia_smi(_text_output(nvidia_result, "stdout")),
        }
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        inventory["nvidia_smi"] = _unavailable(_exception_error(error))

    try:
        with tempfile.TemporaryDirectory(prefix="ifcqc-dxdiag-") as temporary:
            xml_path = Path(temporary) / "dxdiag.xml"
            dxdiag_result = _run(
                runner,
                ["dxdiag.exe", "/whql:off", "/x", str(xml_path)],
                timeout_seconds=timeout_seconds,
            )
            if int(getattr(dxdiag_result, "returncode", 1)) != 0:
                raise ValueError("dxdiag failed")
            inventory["dxdiag"] = {
                "status": "ok",
                "data": parse_dxdiag(xml_path.read_bytes()),
            }
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        inventory["dxdiag"] = _unavailable(_exception_error(error))

    return cast(dict[str, Any], _redact_public_value(inventory, private_values))


def _write_json(path: Path, payload: Mapping[str, Any], private_values: set[str]) -> None:
    clean = _redact_public_value(dict(payload), private_values)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_text(path: Path, text: str, private_values: set[str]) -> None:
    clean = _redact_text(text, private_values).rstrip() + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(clean, encoding="utf-8")
    os.replace(temporary, path)


def _llmfit_error_file(
    path: Path, error_type: ErrorType, private_values: set[str]
) -> None:
    if path.suffix.casefold() == ".json":
        _write_json(
            path,
            {"status": "unavailable", "error_type": error_type},
            private_values,
        )
    else:
        _write_text(
            path,
            f"status=unavailable error_type={error_type}",
            private_values,
        )


def run_llmfit_inventory(
    executable: Path,
    output_dir: Path,
    *,
    runner: CommandRunner = subprocess.run,
    locked_names: set[str] | None = None,
    forbidden_values: set[str] | None = None,
    timeout_seconds: float = 120.0,
) -> LlmfitInventoryResult:
    """Executa quatro comandos llmfit isolados e publica apenas texto anonimo."""
    output_dir.mkdir(parents=True, exist_ok=True)
    private_values = _runtime_private_values(forbidden_values)
    specifications = (
        ("system", ["--json", "system"], "system.json", None),
        (
            "recommend_2048",
            ["--max-context", "2048", "recommend", "--json", "--limit", "20"],
            "recommend-2048.json",
            2048,
        ),
        (
            "recommend_8192",
            ["--max-context", "8192", "recommend", "--json", "--limit", "20"],
            "recommend-8192.json",
            8192,
        ),
        ("doctor", ["doctor"], "doctor.txt", None),
    )
    commands: dict[str, ProbeRecord] = {}
    recommendations: list[dict[str, Any]] = []

    for key, arguments, filename, context in specifications:
        output_path = output_dir / filename
        try:
            result = _run(
                runner,
                [str(executable), *arguments],
                timeout_seconds=timeout_seconds,
            )
            if int(getattr(result, "returncode", 1)) != 0:
                error_type: ErrorType = "ExitCode"
                _llmfit_error_file(output_path, error_type, private_values)
                commands[key] = ProbeRecord("unavailable", error_type)
                continue

            stdout = _text_output(result, "stdout")
            stderr = _text_output(result, "stderr")
            if output_path.suffix.casefold() == ".json":
                payload = json.loads(stdout)
                if not isinstance(payload, Mapping):
                    raise ValueError("llmfit JSON root must be an object")
                document = dict(cast(Mapping[str, Any], payload))
                if context is not None:
                    rows = parse_llmfit_recommendations(document)
                    recommendations.extend(
                        {**row, "recommended_context": context} for row in rows
                    )
                if stderr.strip():
                    document["_capture"] = {"stderr": stderr}
                _write_json(output_path, document, private_values)
            else:
                combined = stdout
                if stderr.strip():
                    combined = f"{combined.rstrip()}\n[stderr]\n{stderr}"
                _write_text(output_path, combined, private_values)
            commands[key] = ProbeRecord("ok")
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            error_type = _exception_error(error)
            _llmfit_error_file(output_path, error_type, private_values)
            commands[key] = ProbeRecord("unavailable", error_type)

    deduplicated: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in filter_llmfit_recommendations(recommendations, set(locked_names or ())):
        context_value = int(row["recommended_context"])
        identity = (
            str(row["name"]),
            str(row.get("ollama_name") or ""),
            context_value,
        )
        deduplicated.setdefault(identity, row)
    extra_models = sorted(
        deduplicated.values(),
        key=lambda row: (
            str(row["name"]).casefold(),
            str(row.get("ollama_name") or "").casefold(),
            int(row["recommended_context"]),
        ),
    )

    success_count = sum(record.status == "ok" for record in commands.values())
    status: InventoryStatus
    if success_count == len(commands):
        status = "ok"
    elif success_count:
        status = "partial"
    else:
        status = "unavailable"
    _write_json(
        output_dir / "recommend-extra-models.json",
        {"models": extra_models},
        private_values,
    )
    return LlmfitInventoryResult(status, commands, extra_models)
