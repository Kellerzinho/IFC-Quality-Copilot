"""Testes para src/audit/logger.py."""

import json
import threading
from pathlib import Path

import pytest

from src.audit.logger import AuditLogger
from src.models import AuditEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GUID_A = "A" * 22
_GUID_B = "B" * 22


def _make_entry(
    guid: str = _GUID_A,
    action: str = "preencher_pset",
    field: str = "ThermalTransmittance",
    old_value: float | None = None,
    new_value: float = 2.48,
    decision: str = "accepted",
    confidence: str = "alta",
    source: str = "llm",
    normative_ref: str | None = "NBR 15575-4",
) -> AuditEntry:
    """Cria AuditEntry mínima para testes."""
    return AuditEntry(
        element_guid=guid,
        element_class="IfcWall",
        action=action,
        field=field,
        old_value=old_value,
        new_value=new_value,
        decision=decision,  # type: ignore[arg-type]
        confidence=confidence,
        normative_ref=normative_ref,
        source=source,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# test_logger_auto_generates_session_id
# ---------------------------------------------------------------------------


def test_logger_auto_generates_session_id():
    """AuditLogger deve gerar session_id automaticamente se não fornecido."""
    logger_a = AuditLogger()
    logger_b = AuditLogger()

    assert logger_a.session_id is not None
    assert len(logger_a.session_id) == 12
    assert logger_a.session_id != logger_b.session_id


def test_logger_uses_provided_session_id():
    """AuditLogger deve usar o session_id fornecido explicitamente."""
    al = AuditLogger(session_id="minha-sessao")
    assert al.session_id == "minha-sessao"


# ---------------------------------------------------------------------------
# test_logger_log_and_retrieve
# ---------------------------------------------------------------------------


def test_logger_log_and_retrieve():
    """log() deve adicionar entrada e atribuir session_id; entries deve expô-la."""
    al = AuditLogger(session_id="sess-01")
    entry = _make_entry()

    al.log(entry)

    assert len(al.entries) == 1
    assert al.entries[0].session_id == "sess-01"
    assert al.entries[0].element_guid == _GUID_A


def test_logger_log_multiple_entries():
    """log() deve acumular entradas na ordem de inserção."""
    al = AuditLogger()
    al.log(_make_entry(guid=_GUID_A, action="acao_a"))
    al.log(_make_entry(guid=_GUID_B, action="acao_b"))
    al.log(_make_entry(guid=_GUID_A, action="acao_c"))

    assert len(al.entries) == 3
    assert al.entries[0].action == "acao_a"
    assert al.entries[2].action == "acao_c"


# ---------------------------------------------------------------------------
# test_logger_export_csv_creates_file
# ---------------------------------------------------------------------------


def test_logger_export_csv_creates_file(tmp_path: Path):
    """export_csv deve criar arquivo CSV com cabeçalho e dados corretos."""
    al = AuditLogger(session_id="sess-csv")
    al.log(_make_entry(new_value=2.48, decision="accepted"))
    al.log(_make_entry(new_value=3.10, decision="edited"))

    csv_path = str(tmp_path / "audit.csv")
    result = al.export_csv(csv_path)

    assert result == csv_path
    assert Path(csv_path).exists()

    content = Path(csv_path).read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    # cabeçalho + 2 linhas de dados
    assert len(lines) == 3
    assert "timestamp" in lines[0]
    assert "session_id" in lines[0]
    assert "sess-csv" in content


def test_logger_export_csv_empty_file(tmp_path: Path):
    """export_csv deve criar arquivo com apenas cabeçalho quando não há entradas."""
    al = AuditLogger()
    csv_path = str(tmp_path / "empty.csv")
    al.export_csv(csv_path)

    content = Path(csv_path).read_text(encoding="utf-8")
    lines = [l for l in content.strip().splitlines() if l]
    assert len(lines) == 1  # apenas cabeçalho
    assert "timestamp" in lines[0]


# ---------------------------------------------------------------------------
# test_logger_export_json_creates_file
# ---------------------------------------------------------------------------


def test_logger_export_json_creates_file(tmp_path: Path):
    """export_json deve criar arquivo JSON Lines com uma entrada por linha."""
    al = AuditLogger(session_id="sess-json")
    al.log(_make_entry(new_value=1.5, decision="accepted"))
    al.log(_make_entry(new_value=2.5, decision="rejected"))

    json_path = str(tmp_path / "audit.jsonl")
    result = al.export_json(json_path)

    assert result == json_path
    assert Path(json_path).exists()

    lines = Path(json_path).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    # Cada linha deve ser JSON válido com os campos esperados
    for line in lines:
        obj = json.loads(line)
        assert "element_guid" in obj
        assert "decision" in obj
        assert obj["session_id"] == "sess-json"


# ---------------------------------------------------------------------------
# test_logger_get_summary_counts
# ---------------------------------------------------------------------------


def test_logger_get_summary_counts():
    """get_summary deve contar corretamente por decisão, confidence e source."""
    al = AuditLogger()
    al.log(_make_entry(decision="accepted", confidence="alta", source="llm"))
    al.log(_make_entry(decision="accepted", confidence="alta", source="llm"))
    al.log(_make_entry(decision="edited",   confidence="media", source="llm"))
    al.log(_make_entry(decision="rejected", confidence="baixa", source="llm"))

    summary = al.get_summary()

    assert summary["total_entries"] == 4
    assert summary["accepted"] == 2
    assert summary["edited"] == 1
    assert summary["rejected"] == 1
    assert summary["by_confidence"]["alta"] == 2
    assert summary["by_confidence"]["media"] == 1
    assert summary["by_confidence"]["baixa"] == 1
    assert summary["by_source"]["llm"] == 4


def test_logger_get_summary_empty():
    """get_summary deve retornar zeros quando não há entradas."""
    al = AuditLogger()
    summary = al.get_summary()

    assert summary["total_entries"] == 0
    assert summary["accepted"] == 0
    assert summary["by_action"] == {}


# ---------------------------------------------------------------------------
# test_logger_thread_safety
# ---------------------------------------------------------------------------


def test_logger_thread_safety():
    """log() deve ser seguro para uso concorrente por múltiplas threads."""
    al = AuditLogger()
    errors: list[Exception] = []

    def _log_many(n: int) -> None:
        try:
            for _ in range(n):
                al.log(_make_entry())
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_log_many, args=(50,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Exceções em threads: {errors}"
    assert len(al.entries) == 200


# ---------------------------------------------------------------------------
# test_logger_get_entries_for_element
# ---------------------------------------------------------------------------


def test_logger_get_entries_for_element():
    """get_entries_for_element deve retornar apenas entradas do GUID solicitado."""
    al = AuditLogger()
    al.log(_make_entry(guid=_GUID_A, action="acao_1"))
    al.log(_make_entry(guid=_GUID_B, action="acao_2"))
    al.log(_make_entry(guid=_GUID_A, action="acao_3"))

    result = al.get_entries_for_element(_GUID_A)

    assert len(result) == 2
    assert all(e.element_guid == _GUID_A for e in result)
    assert result[0].action == "acao_1"
    assert result[1].action == "acao_3"


def test_logger_get_entries_for_element_not_found():
    """get_entries_for_element deve retornar lista vazia para GUID inexistente."""
    al = AuditLogger()
    al.log(_make_entry(guid=_GUID_A))

    result = al.get_entries_for_element(_GUID_B)

    assert result == []


# ---------------------------------------------------------------------------
# test_logger_clear
# ---------------------------------------------------------------------------


def test_logger_clear():
    """clear() deve remover todas as entradas sem alterar session_id."""
    al = AuditLogger(session_id="sess-clear")
    al.log(_make_entry())
    al.log(_make_entry())

    al.clear()

    assert al.entries == []
    assert al.session_id == "sess-clear"


def test_logger_export_csv_includes_grounding_fields(tmp_path: Path):
    al = AuditLogger(session_id="sess-ground")
    al.log(_make_entry())

    csv_path = str(tmp_path / "audit_ground.csv")
    al.export_csv(csv_path)

    header = Path(csv_path).read_text(encoding="utf-8").splitlines()[0]
    assert "grounding_sources" in header
    assert "post_validation" in header
