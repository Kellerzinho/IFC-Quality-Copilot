"""Testes para formatacao e combinacao de grounding."""

from src.bsdd.context_builder import build_grounding_block, format_ids_context
from src.models import BSDDContext, BSDDProperty, IDSContext


def _make_ids_context() -> IDSContext:
    return IDSContext(
        issue_id="issue-1",
        requirement_id="req-1",
        specification_name="Paredes externas devem ter transmitancia",
        check_pset="Pset_WallCommon",
        check_property="ThermalTransmittance",
        check_type="is_numeric",
        severity="high",
    )


def _make_bsdd_context() -> BSDDContext:
    return BSDDContext(
        class_name="Wall",
        class_uri="https://example.org/classes/wall",
        related_properties=[
            BSDDProperty(
                name="ThermalTransmittance",
                data_type="real",
                unit="W/(m²·K)",
            )
        ],
    )


def test_format_ids_context_with_data():
    text = format_ids_context(_make_ids_context())

    assert "REQUISITO IDS VIOLADO:" in text
    assert 'Especificacao: "Paredes externas devem ter transmitancia"' in text
    assert "Check: Pset_WallCommon.ThermalTransmittance must exist and be numeric" in text
    assert "Pset esperado: Pset_WallCommon" in text
    assert "Propriedade esperada: ThermalTransmittance" in text
    assert "Severidade: high" in text


def test_format_ids_context_none_returns_empty():
    assert format_ids_context(None) == ""


def test_build_grounding_block_none_mode():
    result = build_grounding_block(_make_ids_context(), _make_bsdd_context(), "none")

    assert result == ""


def test_build_grounding_block_ids_only():
    result = build_grounding_block(_make_ids_context(), _make_bsdd_context(), "ids_only")

    assert "REQUISITO IDS VIOLADO:" in result
    assert "VOCABULARIO bSDD" not in result


def test_build_grounding_block_ids_bsdd():
    result = build_grounding_block(_make_ids_context(), _make_bsdd_context(), "ids_bsdd")

    assert "REQUISITO IDS VIOLADO:" in result
    assert "VOCABULARIO bSDD" in result
    assert "ThermalTransmittance (real, W/(m²·K))" in result
