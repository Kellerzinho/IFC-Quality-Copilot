"""Contratos do inventario Windows anonimo e das recomendacoes llmfit."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from src.experiment import evidence_bundle, windows_inventory
from src.experiment.windows_inventory import (
    collect_windows_inventory,
    parse_dxdiag,
    parse_llmfit_recommendations,
    parse_nvidia_smi,
    run_llmfit_inventory,
)

FIXTURES = Path(__file__).with_name("fixtures")


def _powershell_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "os": {
            "caption": "Microsoft Windows 11 Pro",
            "version": "10.0.22631",
            "build_number": "22631",
            "architecture": "64-bit",
            "hostname": "DESKTOP-PRIVATE",
        },
        "computer": {
            "manufacturer": "Framework",
            "model": "Laptop 16",
            "system_type": "x64-based PC",
            "total_physical_memory": 34359738368,
            "hypervisor_present": False,
            "username": "PRIVATE\\researcher",
        },
        "cpu": [
            {
                "name": "AMD Ryzen 7 7840HS",
                "manufacturer": "AuthenticAMD",
                "cores": 8,
                "logical_processors": 16,
                "max_clock_mhz": 3801,
                "l2_cache_kib": 8192,
                "l3_cache_kib": 16384,
                "virtualization_firmware_enabled": True,
                "processor_id": "PRIVATE-CPU-ID",
            }
        ],
        "memory": {
            "total_bytes": 34359738368,
            "modules": [
                {
                    "capacity_bytes": 17179869184,
                    "speed_mhz": 5600,
                    "configured_clock_mhz": 5600,
                    "manufacturer": "Micron",
                    "part_number": "MTC8C1084S1SC48BA1",
                    "form_factor": 12,
                    "serial_number": "PRIVATE-RAM-SERIAL",
                }
            ],
        },
        "gpu": [
            {
                "name": "NVIDIA GeForce RTX 4060 Laptop GPU",
                "adapter_ram_bytes": 8589934592,
                "driver_version": "32.0.15.5599",
                "driver_date": "2026-05-01T00:00:00Z",
                "video_processor": "NVIDIA GeForce RTX 4060 Laptop GPU",
                "status": "OK",
                "pnp_device_id": "PCI\\PRIVATE",
            }
        ],
        "storage": {
            "disks": [
                {
                    "model": "NVMe SSD",
                    "size_bytes": 2000398934016,
                    "interface_type": "SCSI",
                    "media_type": "Fixed hard disk media",
                    "firmware_revision": "1.0",
                    "serialnumber": "PRIVATE-DISK-SERIAL",
                }
            ],
            "volumes": [
                {
                    "device_id": "C:",
                    "drive_type": 3,
                    "file_system": "NTFS",
                    "size_bytes": 1999851040768,
                    "free_bytes": 1099511627776,
                }
            ],
        },
        "bios": {
            "manufacturer": "INSYDE Corp.",
            "smbios_version": "03.05",
            "release_date": "2026-01-01T00:00:00Z",
            "serial_number": "PRIVATE-BIOS-SERIAL",
        },
        "baseboard": {
            "manufacturer": "Framework",
            "product": "FRANMDCP09",
            "version": "A9",
            "serial_number": "PRIVATE-BOARD-SERIAL",
        },
        "display_drivers": [
            {
                "name": "NVIDIA GeForce RTX 4060 Laptop GPU",
                "driver_version": "32.0.15.5599",
                "driver_date": "2026-05-01T00:00:00Z",
                "status": "OK",
            }
        ],
        "power": {"active_scheme_name": "Balanced", "guid": "PRIVATE-GUID"},
        "macaddress": "00:11:22:33:44:55",
        "ipaddress": "192.168.50.22",
    }


class HardwareRunner:
    def __init__(self, *, fail_nvidia: bool = False, fail_dxdiag: bool = False) -> None:
        self.fail_nvidia = fail_nvidia
        self.fail_dxdiag = fail_dxdiag

    def __call__(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        executable = Path(command[0]).name.casefold()
        if executable in {"powershell", "powershell.exe"}:
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(_powershell_payload()),
                "",
            )
        if executable == "nvidia-smi":
            if self.fail_nvidia:
                raise FileNotFoundError("C:\\private\\nvidia-smi.exe")
            stdout = (FIXTURES / "nvidia-smi.csv").read_text(encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout, "")
        if executable in {"dxdiag", "dxdiag.exe"}:
            if self.fail_dxdiag:
                raise subprocess.TimeoutExpired(command, timeout=30)
            destination = Path(command[command.index("/x") + 1])
            destination.write_text(
                (FIXTURES / "dxdiag.xml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"comando inesperado: {command!r}")


def test_nvidia_parser_handles_csv_fields_without_leaking_identifiers() -> None:
    rows = parse_nvidia_smi(
        '0, "NVIDIA Test, Edition", 24564, 555.99, 8.9, P0, 285.00\n'
    )

    assert rows == [
        {
            "index": 0,
            "name": "NVIDIA Test, Edition",
            "memory_total_mib": 24564,
            "driver_version": "555.99",
            "compute_capability": "8.9",
            "performance_state": "P0",
            "power_limit_w": 285.0,
        }
    ]


def test_nvidia_parser_keeps_gpu_when_optional_power_limit_is_bracketed_na() -> None:
    rows = parse_nvidia_smi(
        "0, NVIDIA GeForce RTX 4060 Laptop GPU, 8188, 591.74, 8.9, P0, [N/A]\n"
    )

    assert rows[0]["name"] == "NVIDIA GeForce RTX 4060 Laptop GPU"
    assert rows[0]["power_limit_w"] is None


def test_dxdiag_parser_keeps_allowed_display_fields_only() -> None:
    parsed = parse_dxdiag((FIXTURES / "dxdiag.xml").read_text(encoding="utf-8"))

    assert parsed["directx_version"] == "DirectX 12"
    assert parsed["displays"][0]["name"] == "NVIDIA GeForce RTX 4060 Laptop GPU"
    assert parsed["displays"][0]["driver_model"] == "WDDM 3.2"
    serialized = json.dumps(parsed).casefold()
    assert "desktop-private" not in serialized
    assert "deviceidentifier" not in serialized
    assert "device_key" not in serialized
    assert "ven_10de" not in serialized


def test_inventory_keeps_research_fields_and_drops_identifiers() -> None:
    inventory = collect_windows_inventory(HardwareRunner())

    assert inventory["os"]["build_number"] == "22631"
    assert inventory["cpu"][0]["logical_processors"] == 16
    assert inventory["memory"]["total_bytes"] == 34359738368
    assert inventory["gpu"][0]["name"] == "NVIDIA GeForce RTX 4060 Laptop GPU"
    assert inventory["nvidia_smi"]["data"][0]["memory_total_mib"] == 8188
    assert inventory["dxdiag"]["data"]["directx_version"] == "DirectX 12"
    serialized = json.dumps(inventory, sort_keys=True).casefold()
    for forbidden in (
        "hostname",
        "username",
        "serialnumber",
        "serial_number",
        "macaddress",
        "ipaddress",
        "pnp_device_id",
        "processor_id",
        "private-",
        "00:11:22:33:44:55",
        "192.168.50.22",
    ):
        assert forbidden not in serialized


def test_optional_sources_become_unavailable_instead_of_failing() -> None:
    inventory = collect_windows_inventory(HardwareRunner(fail_nvidia=True, fail_dxdiag=True))

    assert inventory["nvidia_smi"] == {
        "status": "unavailable",
        "error_type": "CommandNotFound",
    }
    assert inventory["dxdiag"] == {"status": "unavailable", "error_type": "Timeout"}
    assert inventory["os"]["build_number"] == "22631"
    assert "private" not in json.dumps(inventory).casefold()


class FakeLlmfit:
    def __init__(self, *, fail_key: str | None = None, malformed_key: str | None = None) -> None:
        self.fail_key = fail_key
        self.malformed_key = malformed_key
        self.commands: list[list[str]] = []

    @staticmethod
    def _key(arguments: list[str]) -> str:
        if arguments == ["--json", "system"]:
            return "system"
        if arguments[:2] == ["--max-context", "2048"]:
            return "recommend_2048"
        if arguments[:2] == ["--max-context", "8192"]:
            return "recommend_8192"
        if arguments == ["doctor"]:
            return "doctor"
        raise AssertionError(f"argumentos llmfit inesperados: {arguments!r}")

    def __call__(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        arguments = command[1:]
        self.commands.append(arguments)
        key = self._key(arguments)
        if key == self.fail_key:
            return subprocess.CompletedProcess(
                command,
                7,
                "",
                "falha em C:\\Users\\PRIVATE\\AppData e 192.168.50.22",
            )
        if key == self.malformed_key:
            return subprocess.CompletedProcess(command, 0, "{invalid", "")
        if key == "system":
            payload: dict[str, Any] = {
                "system": {
                    "backend": "CUDA",
                    "cpu_cores": 20,
                    "gpu_name": "NVIDIA GeForce RTX 4060 Laptop GPU",
                    "gpu_vram_gb": 8.0,
                    "total_ram_gb": 15.73,
                },
                "hostname": "DESKTOP-PRIVATE",
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        if key == "recommend_2048":
            stdout = (FIXTURES / "llmfit-recommend-v1.1.8.json").read_text(encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout, "")
        if key == "recommend_8192":
            payload = {
                "models": [
                    {
                        "name": "gemma-project-alias",
                        "ollama_name": "gemma2:9b",
                        "best_quant": "Q4_K_M",
                        "effective_context_length": 8192,
                    },
                    {
                        "name": "research/New-14B",
                        "ollama_name": None,
                        "best_quant": "Q4_K_M",
                        "effective_context_length": 8192,
                    },
                ]
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        return subprocess.CompletedProcess(
            command,
            0,
            "Hardware diagnostics OK\nProfile C:\\Users\\PRIVATE\\bench\n"
            "IP 192.168.50.22 MAC 00:11:22:33:44:55\n",
            "",
        )


def test_parser_matches_llmfit_1_1_8_models_name_envelope() -> None:
    payload = json.loads((FIXTURES / "llmfit-recommend-v1.1.8.json").read_text())
    rows = parse_llmfit_recommendations(payload)

    assert rows[0]["name"] == "Orion-zhen/Qwen2.5-Coder-7B-Instruct-AWQ"
    assert rows[0]["best_quant"] == "AWQ-4bit"
    assert rows[0]["effective_context_length"] == 2048


def test_windows_inventory_uses_core_llmfit_parser_and_filter_as_single_source() -> None:
    assert windows_inventory.parse_llmfit_recommendations is (
        evidence_bundle.parse_llmfit_recommendations
    )
    assert windows_inventory.filter_llmfit_recommendations is (
        evidence_bundle.filter_llmfit_recommendations
    )


def test_llmfit_runs_system_two_contexts_and_doctor(tmp_path: Path) -> None:
    fake = FakeLlmfit()

    result = run_llmfit_inventory(
        tmp_path / "llmfit.exe",
        tmp_path / "evidence",
        runner=fake,
        locked_names={"gemma2:9b"},
        forbidden_values={"PRIVATE", "DESKTOP-PRIVATE"},
    )

    assert fake.commands == [
        ["--json", "system"],
        ["--max-context", "2048", "recommend", "--json", "--limit", "20"],
        ["--max-context", "8192", "recommend", "--json", "--limit", "20"],
        ["doctor"],
    ]
    assert result.status == "ok"
    assert [row["recommended_context"] for row in result.extra_models] == [2048, 8192]
    assert {row["name"] for row in result.extra_models} == {
        "Orion-zhen/Qwen2.5-Coder-7B-Instruct-AWQ",
        "research/New-14B",
    }
    assert json.loads((tmp_path / "evidence/system.json").read_text())["system"][
        "backend"
    ] == "CUDA"
    assert json.loads(
        (tmp_path / "evidence/recommend-extra-models.json").read_text()
    )["models"] == result.extra_models
    public_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((tmp_path / "evidence").iterdir())
    ).casefold()
    for forbidden in (
        "hostname",
        "desktop-private",
        "private",
        "192.168.50.22",
        "00:11:22:33:44:55",
    ):
        assert forbidden not in public_text


@pytest.mark.parametrize("failed_key", ["system", "recommend_2048", "recommend_8192", "doctor"])
def test_each_llmfit_failure_is_independent(tmp_path: Path, failed_key: str) -> None:
    fake = FakeLlmfit(fail_key=failed_key)

    result = run_llmfit_inventory(
        tmp_path / "llmfit.exe",
        tmp_path / "evidence",
        runner=fake,
        locked_names={"gemma2:9b"},
        forbidden_values={"PRIVATE"},
    )

    assert len(fake.commands) == 4
    assert result.status == "partial"
    assert result.commands[failed_key].status == "unavailable"
    assert result.commands[failed_key].error_type == "ExitCode"
    assert all(
        record.status == "ok" for key, record in result.commands.items() if key != failed_key
    )
    assert {path.name for path in (tmp_path / "evidence").iterdir()} == {
        "system.json",
        "recommend-2048.json",
        "recommend-8192.json",
        "recommend-extra-models.json",
        "doctor.txt",
    }
    assert "private" not in "\n".join(
        path.read_text(encoding="utf-8") for path in (tmp_path / "evidence").iterdir()
    ).casefold()


def test_malformed_llmfit_json_does_not_skip_remaining_probes(tmp_path: Path) -> None:
    fake = FakeLlmfit(malformed_key="recommend_2048")

    result = run_llmfit_inventory(
        tmp_path / "llmfit.exe",
        tmp_path / "evidence",
        runner=fake,
        locked_names={"gemma2:9b"},
    )

    assert len(fake.commands) == 4
    assert result.status == "partial"
    assert result.commands["recommend_2048"].error_type == "ParseError"
    assert json.loads((tmp_path / "evidence/recommend-2048.json").read_text()) == {
        "error_type": "ParseError",
        "status": "unavailable",
    }
    assert {row["name"] for row in result.extra_models} == {"research/New-14B"}
