"""Aplicabilidade cadastral declarativa (M1-05); regras SINTÉTICAS.

Aplicabilidade do catálogo orienta uso e receita; a aplicabilidade formal continua
sendo a do IDS fornecido. Contexto desconhecido produz ``indeterminate``, nunca falso.
"""

import pytest
from pydantic import ValidationError

from src.domain_catalog.applicability import ApplicabilityContext, evaluate_applicability
from src.domain_catalog.contracts import PredefinedTypeContext
from src.domain_catalog.models import ApplicabilityRule, Condition

RULE_ID = "urn:uuid:00000000-0000-4000-8000-0000000000c1"


def _occurrence(value: str) -> PredefinedTypeContext:
    """PredefinedType efetivo lido na própria ocorrência."""
    return PredefinedTypeContext.determined(value, origin="occurrence")


def _rule(**changes: object) -> ApplicabilityRule:
    data: dict[str, object] = {
        "id": RULE_ID,
        "entity_classes": ("IfcCovering",),
        "include_subtypes": False,
        "predefined_types": ("FLOORING",),
        "conditions": (),
        "lifecycle": "approved",
    }
    data.update(changes)
    return ApplicabilityRule.model_validate(data)


def _masonry_rule(operator: str = "in") -> ApplicabilityRule:
    return _rule(
        entity_classes=("IfcWall",),
        predefined_types=None,
        conditions=(
            Condition(fact="construction_system", operator=operator, values=("alvenaria",)),
        ),
    )


@pytest.mark.parametrize(
    ("entity", "predefined_type", "expected"),
    [
        ("IfcCovering", "FLOORING", "applicable"),
        ("IFCCOVERING", "FLOORING", "applicable"),
        ("IfcCovering", "CEILING", "not_applicable"),
        ("IfcSlab", "FLOORING", "not_applicable"),
        ("IfcCovering", None, "indeterminate"),
        (None, "FLOORING", "indeterminate"),
        ("IfcSlab", None, "not_applicable"),
    ],
)
def test_class_and_predefined_type_use_three_valued_logic(
    entity: str | None, predefined_type: str | None, expected: str
) -> None:
    context = ApplicabilityContext(
        entity=entity,
        predefined_type=None if predefined_type is None else _occurrence(predefined_type),
    )

    assert evaluate_applicability(_rule(), context).state == expected


# --- Decisão de 13/10: PredefinedType efetivo, com origem e conflitos -------------------


def _context(**predefined: object) -> ApplicabilityContext:
    return ApplicabilityContext(
        entity="IfcCovering", predefined_type=PredefinedTypeContext.model_validate(predefined)
    )


def _read(value: str, origin: str) -> dict[str, str]:
    return {"origin": origin, "value": value}


def test_predefined_type_inherited_from_the_type_object_applies() -> None:
    # Ausência na ocorrência não é ausência definitiva: o tipo associado pode declarar.
    context = _context(
        status="determined", effective_origin="type", readings=[_read("FLOORING", "type")]
    )

    assert evaluate_applicability(_rule(), context).state == "applicable"


def test_insufficient_predefined_type_information_stays_indeterminate_with_reason() -> None:
    context = _context(
        status="undetermined", reason="ocorrência sem valor; tipo associado não consultado"
    )

    result = evaluate_applicability(_rule(), context)

    assert result.state == "indeterminate"
    assert any("tipo associado não consultado" in reason for reason in result.reasons)


def test_definitive_absence_of_predefined_type_does_not_apply() -> None:
    result = evaluate_applicability(_rule(), _context(status="absent"))

    assert result.state == "not_applicable"
    assert any("ocorrência e tipo associado" in reason for reason in result.reasons)


@pytest.mark.parametrize(
    ("allowed", "expected"),
    [
        (("FLOORING",), "indeterminate"),
        (("FLOORING", "CLADDING"), "applicable"),
        (("CEILING",), "not_applicable"),
    ],
    ids=["leituras-divergem-no-uso", "ambas-admitidas", "nenhuma-admitida"],
)
def test_conflicting_readings_never_pick_a_side(allowed: tuple[str, ...], expected: str) -> None:
    # Efetivo pelo tipo (regra formal do M2), ocorrência divergente preservada.
    context = _context(
        status="determined",
        effective_origin="type",
        readings=[_read("FLOORING", "type"), _read("CLADDING", "occurrence")],
    )

    result = evaluate_applicability(_rule(predefined_types=allowed), context)

    assert result.state == expected
    if expected == "indeterminate":
        assert any("CLADDING" in r and "FLOORING" in r for r in result.reasons)


@pytest.mark.parametrize(
    "data",
    [
        {"status": "determined"},
        {
            "status": "determined",
            "effective_origin": "type",
            "readings": [_read("X", "occurrence")],
        },
        {"status": "absent", "readings": [_read("FLOORING", "occurrence")]},
        {"status": "absent", "effective_origin": "type"},
        {"status": "undetermined"},
        {
            "status": "determined",
            "effective_origin": "type",
            "readings": [_read("FLOORING", "type"), _read("CLADDING", "type")],
        },
    ],
    ids=[
        "determinado-sem-origem",
        "origem-sem-leitura",
        "ausente-com-leitura",
        "ausente-com-origem",
        "indeterminado-sem-motivo",
        "duas-leituras-no-mesmo-nivel",
    ],
)
def test_predefined_type_context_rejects_contradictory_states(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PredefinedTypeContext.model_validate(data)


def test_unknown_construction_system_is_indeterminate_not_false() -> None:
    result = evaluate_applicability(_masonry_rule(), ApplicabilityContext(entity="IfcWall"))

    assert result.state == "indeterminate"
    assert any("construction_system" in reason for reason in result.reasons)


@pytest.mark.parametrize(
    ("operator", "system", "expected"),
    [
        ("in", "alvenaria", "applicable"),
        ("in", "drywall", "not_applicable"),
        ("not_in", "alvenaria", "not_applicable"),
        ("not_in", "drywall", "applicable"),
    ],
)
def test_known_construction_system_decides(operator: str, system: str, expected: str) -> None:
    context = ApplicabilityContext(entity="IfcWall", facts={"construction_system": system})

    assert evaluate_applicability(_masonry_rule(operator), context).state == expected


def test_context_facts_are_immutable() -> None:
    context = ApplicabilityContext(entity="IfcWall", facts={"construction_system": "alvenaria"})

    with pytest.raises(TypeError):
        context.facts["construction_system"] = "drywall"  # type: ignore[index]

    assert evaluate_applicability(_masonry_rule(), context).state == "applicable"


def test_element_name_is_not_evidence_of_construction_system() -> None:
    context = ApplicabilityContext(entity="IfcWall", facts={"name": "Parede drywall 12,5"})

    assert evaluate_applicability(_masonry_rule(), context).state == "indeterminate"


def test_exact_class_rule_does_not_cover_subtypes() -> None:
    rule = _rule(entity_classes=("IfcWall",), predefined_types=None, include_subtypes=False)
    context = ApplicabilityContext(entity="IfcWallStandardCase", ifc_schema="IFC4")

    assert evaluate_applicability(rule, context).state == "not_applicable"


@pytest.mark.parametrize("schema", ["IFC2X3", "IFC4"])
def test_subtype_rule_covers_standard_case_in_declared_schema(schema: str) -> None:
    rule = _rule(entity_classes=("IfcWall",), predefined_types=None, include_subtypes=True)
    context = ApplicabilityContext(entity="IfcWallStandardCase", ifc_schema=schema)

    assert evaluate_applicability(rule, context).state == "applicable"


def test_subtype_rule_without_schema_is_indeterminate() -> None:
    rule = _rule(entity_classes=("IfcWall",), predefined_types=None, include_subtypes=True)

    result = evaluate_applicability(rule, ApplicabilityContext(entity="IfcWallStandardCase"))

    assert result.state == "indeterminate"


def test_subtype_rule_with_class_unknown_to_schema_is_indeterminate() -> None:
    rule = _rule(entity_classes=("IfcWall",), predefined_types=None, include_subtypes=True)
    context = ApplicabilityContext(entity="IfcParedeInventada", ifc_schema="IFC4")

    assert evaluate_applicability(rule, context).state == "indeterminate"


def test_unrelated_class_with_subtype_rule_is_not_applicable() -> None:
    rule = _rule(entity_classes=("IfcWall",), predefined_types=None, include_subtypes=True)
    context = ApplicabilityContext(entity="IfcSlab", ifc_schema="IFC4")

    assert evaluate_applicability(rule, context).state == "not_applicable"
