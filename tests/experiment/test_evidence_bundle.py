import hashlib
import json
import os
import zipfile
from pathlib import Path

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
        "known-value",
        "ipv4",
        "ipv6",
        "mac",
        "bearer-token",
        "assigned-secret",
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
    assert all(
        secret not in clean
        for secret in [
            "Keller",
            "10.0.0.4",
            "2001:db8::7",
            "aa-bb-cc-dd-ee-ff",
            "segredo",
            "valor",
        ]
    )
    assert "127.0.0.1" in clean
    assert "::1" in clean
    assert not scan_sensitive_text(tmp_path, forbidden_values={"Keller"})


def test_json_and_jsonl_scanner_find_unknown_sensitive_keys_even_with_null_value(tmp_path):
    (tmp_path / "legacy.json").write_text('{"hostname":"NEVER-SEEN-PC"}\n', encoding="utf-8")
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
    assert "12:34:56" in clean
    assert "1:2:3" in clean
    assert all(
        address not in clean for address in ("2001:db8::7", "fe80::1", "::2", "::ffff:192.0.2.1")
    )
    assert "::1" in clean


def test_collects_nonempty_secret_and_dotenv_values_without_output(tmp_path, caplog, capsys):
    dotenv = tmp_path / ".env"
    dotenv.write_text("TOKEN=dotenv-secret\nEMPTY=\nQUOTED='quoted-secret'\n", encoding="utf-8")
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
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == linked or original(self))
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


def test_filters_models_already_in_project_lock():
    raw = {
        "models": [
            {"name": "google/gemma-2-9b", "ollama_name": "gemma2:9b", "score": 90},
            {"name": "org/extra-14b", "ollama_name": None, "score": 80},
        ]
    }
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
        create_evidence_zip(evidence, tmp_path / "result.zip", forbidden_values={"PC-PRIVATE"})


def test_zip_fails_closed_on_unknown_hostname_if_sanitizer_misses_it(tmp_path, monkeypatch):
    evidence = tmp_path / "legacy"
    evidence.mkdir()
    (evidence / "hardware.json").write_text('{"hostname":"UNSEEN-LEGACY-HOST"}\n', encoding="utf-8")
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
            module,
            name,
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()),
        )
    outputs = [tmp_path / "partial-a.zip", tmp_path / "partial-b.zip"]
    outputs[0].with_suffix(".zip.partial").write_bytes(b"stale")
    for output in outputs:
        create_partial_evidence_zip(
            output,
            status="failed",
            reason_code=FailureCode.UV_DOWNLOAD_FAILED,
        )
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    with zipfile.ZipFile(outputs[0]) as archive:
        assert set(archive.namelist()) == {
            "README.txt",
            "status.json",
            "privacy-report.json",
            "manifest.json",
        }
        status = json.loads(archive.read("status.json"))
        assert status == {
            "partial": True,
            "reason_code": "UV_DOWNLOAD_FAILED",
            "status": "failed",
        }
        assert validate_evidence_archive(outputs[0]) == []
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
        assert all((info.external_attr >> 16) & 0o777 == 0o644 for info in archive.infolist())


@pytest.mark.parametrize("status", ["complete", "running", "", None])
def test_partial_rejects_invalid_status(tmp_path, status):
    with pytest.raises(ValueError, match="status parcial invalido"):
        create_partial_evidence_zip(
            tmp_path / "partial.zip",
            status=status,
            reason_code=FailureCode.UV_DOWNLOAD_FAILED,
        )


def test_partial_requires_failure_code_enum_and_verifies_reopened_archive(tmp_path, monkeypatch):
    with pytest.raises(TypeError, match="FailureCode"):
        create_partial_evidence_zip(
            tmp_path / "wrong.zip",
            status="failed",
            reason_code="UV_DOWNLOAD_FAILED",  # type: ignore[arg-type]
        )
    monkeypatch.setattr(module, "validate_evidence_archive", lambda path: ["hash mismatch"])
    with pytest.raises(EvidenceManifestError, match="hash mismatch"):
        create_partial_evidence_zip(
            tmp_path / "invalid.zip",
            status="failed",
            reason_code=FailureCode.UV_DOWNLOAD_FAILED,
        )


def test_archive_reopen_io_error_is_not_reclassified_as_manifest(tmp_path, monkeypatch):
    def raise_io(_path):
        raise OSError("disk read")

    monkeypatch.setattr(module, "validate_evidence_archive", raise_io)
    with pytest.raises(OSError, match="disk read"):
        create_partial_evidence_zip(
            tmp_path / "io.zip",
            status="failed",
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
