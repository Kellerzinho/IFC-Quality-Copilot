"""Reconciliação E4 do perfil Daiane: fechamento A/B, destinos e capacidade (M1-04).

Usa os artefatos REAIS da E4 (matriz M3 r2, transcrição B r2, reconciliação e
candidatos em rascunho) para o fechamento e mutações em memória para os negativos. As
capacidades são testadas com evidência SINTÉTICA (``synthetic_contract``), que nunca
eleva um eixo a ``real_model_verified``. Nada aqui aprova ou publica conteúdo real.
"""

import hashlib
import json
from collections import Counter
from typing import Any

import pytest

from src.domain_catalog.content import validate_content
from src.domain_catalog.errors import CatalogValidationError
from src.domain_catalog.importers.daiane import (
    MATRIX_PATH,
    DaianeImport,
    import_appendix_a,
    load_matrix,
)
from src.domain_catalog.importers.daiane_b import APPENDIX_B_PATH, load_appendix_b
from src.domain_catalog.profile import (
    CANDIDATES_PATH,
    RECONCILIATION_PATH,
    ProfileReconciliationError,
    binding_sha256,
    build_daiane_profile,
    ids_cells_for_binding,
    load_candidates,
    load_reconciliation,
    policy_sha256,
    summarize_daiane_profile,
)
from src.domain_catalog.profile_models import (
    ABCorrespondence,
    AppendixBInventory,
    CapabilityCaseManifest,
    CapabilityClaim,
    CapabilityTrust,
    DaianeProfileInventory,
    ProfileCapabilityEvidence,
    ProfileReconciliation,
)
from src.validation.ids_constraints import CAPABILITY_MANIFEST_SHA256

PDF_SHA256 = "82ead7b5f06fd06247f9f057727bab071ab1c08de4fe42412bebeb9e0c06877a"
CONCRETAGEM = "urn:uuid:46252489-8bcb-458d-ac1e-8b05011661e7"
REVESTIMENTOS = {
    "dai2025:A2-013": "urn:uuid:b20c24be-8204-46e2-a984-4aa47cf7085c",
    "dai2025:A5-009": "urn:uuid:79679e9c-8314-4a8a-995e-70995a5e1365",
    "dai2025:A6-009": "urn:uuid:96d044f7-1ba7-4a38-a669-0d8ec06a44a6",
}
AREA_FORMA_DECISION = "urn:uuid:acbdec55-6250-4d8a-ae36-78abcd05fbbb"
AREA_FORMA_BINDING = "urn:uuid:f479f781-6821-4d29-86e0-cec9b150fcb4"
SYN_NODEID = "tests/synthetic_case.py::test_case"
TRUST = CapabilityTrust(approved_nodeids=(SYN_NODEID,))
"""Âncoras de confiança fornecidas fora da evidência: só o nodeid sintético é aprovado."""


@pytest.fixture(scope="module")
def appendix_a() -> DaianeImport:
    return import_appendix_a(load_matrix(MATRIX_PATH))


@pytest.fixture(scope="module")
def appendix_b() -> AppendixBInventory:
    return load_appendix_b(APPENDIX_B_PATH, expected_pdf_sha256=PDF_SHA256)


@pytest.fixture(scope="module")
def reconciliation() -> ProfileReconciliation:
    return load_reconciliation(RECONCILIATION_PATH)


@pytest.fixture(scope="module")
def profile(
    appendix_a: DaianeImport, appendix_b: AppendixBInventory, reconciliation: ProfileReconciliation
) -> DaianeProfileInventory:
    candidates = load_candidates(CANDIDATES_PATH, appendix_a, appendix_b)
    return build_daiane_profile(
        appendix_a, appendix_b, reconciliation, candidates, capabilities=ProfileCapabilityEvidence()
    )


def _mutated(reconciliation: ProfileReconciliation, change: Any) -> ProfileReconciliation:
    data = reconciliation.model_dump(mode="json")
    change(data)
    return ProfileReconciliation.model_validate(data)


def _build(
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
    capabilities: ProfileCapabilityEvidence | None = None,
    trust: CapabilityTrust | None = None,
) -> DaianeProfileInventory:
    candidates = load_candidates(CANDIDATES_PATH, appendix_a, appendix_b)
    return build_daiane_profile(
        appendix_a,
        appendix_b,
        reconciliation,
        candidates,
        capabilities=capabilities or ProfileCapabilityEvidence(),
        trust=trust if trust is not None else TRUST,
    )


# --- Fechamento do inventário ---------------------------------------------------------------


@pytest.mark.external_data
def test_every_a_and_b_record_has_exactly_one_disposition(
    profile: DaianeProfileInventory, appendix_a: DaianeImport, appendix_b: AppendixBInventory
) -> None:
    dispositions = [d.source_record_id for d in profile.reconciliation.dispositions]
    a_ids = {a.id for a in appendix_a.assertions}
    b_ids = {r.id for r in appendix_b.records}

    assert len(dispositions) == len(set(dispositions)) == 313 + 276
    assert set(dispositions) == a_ids | b_ids
    report = summarize_daiane_profile(profile)
    assert (report.a_total, report.a_alphanumeric, report.a_auxiliary) == (313, 203, 110)
    assert report.b_total == 276
    assert report.inventory_accounted_for is True


@pytest.mark.external_data
def test_missing_disposition_is_refused(
    appendix_a: DaianeImport, appendix_b: AppendixBInventory, reconciliation: ProfileReconciliation
) -> None:
    broken = _mutated(reconciliation, lambda d: d["dispositions"].pop(0))
    with pytest.raises(ProfileReconciliationError, match="sem disposição"):
        _build(appendix_a, appendix_b, broken)


@pytest.mark.external_data
def test_duplicate_disposition_is_refused(
    appendix_a: DaianeImport, appendix_b: AppendixBInventory, reconciliation: ProfileReconciliation
) -> None:
    broken = _mutated(reconciliation, lambda d: d["dispositions"].append(d["dispositions"][0]))
    with pytest.raises(ProfileReconciliationError, match="mais de uma disposição"):
        _build(appendix_a, appendix_b, broken)


@pytest.mark.external_data
def test_orphan_disposition_is_refused(
    appendix_a: DaianeImport, appendix_b: AppendixBInventory, reconciliation: ProfileReconciliation
) -> None:
    def orphan(data: dict[str, Any]) -> None:
        clone = dict(data["dispositions"][0])
        clone["source_record_id"] = "dai2025:A7-999"
        data["dispositions"].append(clone)

    with pytest.raises(ProfileReconciliationError, match="inexistente"):
        _build(appendix_a, appendix_b, _mutated(reconciliation, orphan))


@pytest.mark.external_data
def test_category_other_than_the_source_is_refused(
    appendix_a: DaianeImport, appendix_b: AppendixBInventory, reconciliation: ProfileReconciliation
) -> None:
    def recategorize(data: dict[str, Any]) -> None:
        item = next(
            d for d in data["dispositions"] if d["source_record_id"] == "dai2025:B-E07-0018"
        )
        item["category"] = "custom_property"

    with pytest.raises(ProfileReconciliationError, match="categoria"):
        _build(appendix_a, appendix_b, _mutated(reconciliation, recategorize))


@pytest.mark.external_data
def test_unprojected_b_record_stays_pending_with_reason(profile: DaianeProfileInventory) -> None:
    disposition = next(
        d for d in profile.reconciliation.dispositions if d.source_record_id == "dai2025:B-E07-0018"
    )
    record = profile.b_inventory.record("dai2025:B-E07-0018")

    assert record.assertion is None
    assert record.category is None
    assert disposition.destination == "pending"
    assert "Area_Forma" in disposition.reason
    assert disposition.correspondence_ids


@pytest.mark.external_data
def test_base_other_than_the_inputs_is_refused(
    appendix_a: DaianeImport, appendix_b: AppendixBInventory, reconciliation: ProfileReconciliation
) -> None:
    changed = _mutated(reconciliation, lambda d: d["bases"].update(matrix_sha256="0" * 64))
    with pytest.raises(ProfileReconciliationError, match="base"):
        _build(appendix_a, appendix_b, changed)

    other_candidates = _mutated(
        reconciliation, lambda d: d["bases"].update(candidates_content_sha256="1" * 64)
    )
    with pytest.raises(ProfileReconciliationError, match="candidatos"):
        _build(appendix_a, appendix_b, other_candidates)


@pytest.mark.external_data
def test_unknown_candidate_or_decision_reference_is_refused(
    appendix_a: DaianeImport, appendix_b: AppendixBInventory, reconciliation: ProfileReconciliation
) -> None:
    def bad_candidate(data: dict[str, Any]) -> None:
        item = next(d for d in data["dispositions"] if d["destination"] == "candidate")
        item["candidate_ids"] = ["urn:uuid:00000000-0000-4000-8000-00000000dead"]

    def bad_decision(data: dict[str, Any]) -> None:
        data["dispositions"][0]["decision_ids"] = ["urn:uuid:00000000-0000-4000-8000-00000000beef"]

    for change in (bad_candidate, bad_decision):
        with pytest.raises(ProfileReconciliationError, match="não existe"):
            _build(appendix_a, appendix_b, _mutated(reconciliation, change))


@pytest.mark.external_data
def test_candidate_destination_requires_a_candidate_citing_the_source(
    appendix_a: DaianeImport, appendix_b: AppendixBInventory, reconciliation: ProfileReconciliation
) -> None:
    def promote(data: dict[str, Any]) -> None:
        item = next(d for d in data["dispositions"] if d["source_record_id"] == "dai2025:A2-015")
        item.update(destination="candidate", candidate_ids=[CONCRETAGEM])
        item["axes"]["catalog"] = "candidate_draft"

    with pytest.raises(ProfileReconciliationError, match="não cita"):
        _build(appendix_a, appendix_b, _mutated(reconciliation, promote))


@pytest.mark.external_data
def test_correspondence_with_unknown_record_is_refused(
    appendix_a: DaianeImport, appendix_b: AppendixBInventory, reconciliation: ProfileReconciliation
) -> None:
    def bad(data: dict[str, Any]) -> None:
        data["correspondences"][0]["a_record_ids"] = ["dai2025:A1-999"]

    with pytest.raises(ProfileReconciliationError, match="inexistente"):
        _build(appendix_a, appendix_b, _mutated(reconciliation, bad))


@pytest.mark.external_data
def test_capability_axis_without_verified_evidence_is_refused(
    appendix_a: DaianeImport, appendix_b: AppendixBInventory, reconciliation: ProfileReconciliation
) -> None:
    def claim(data: dict[str, Any]) -> None:
        item = next(d for d in data["dispositions"] if d["source_record_id"] == "dai2025:A7-010")
        item["axes"]["validation"] = "verified_for_case"

    with pytest.raises(ProfileReconciliationError, match="capacidade"):
        _build(appendix_a, appendix_b, _mutated(reconciliation, claim))


@pytest.mark.external_data
def test_identity_registry_must_cover_every_candidate(
    appendix_a: DaianeImport, appendix_b: AppendixBInventory, reconciliation: ProfileReconciliation
) -> None:
    with pytest.raises(ProfileReconciliationError, match="identidade"):
        _build(appendix_a, appendix_b, _mutated(reconciliation, lambda d: d["identities"].pop()))


# --- Negativos de domínio -------------------------------------------------------------


@pytest.mark.external_data
def test_tipo_revestimento_stays_three_concepts_and_is_not_merged(
    profile: DaianeProfileInventory,
) -> None:
    by_record = {d.source_record_id: d for d in profile.reconciliation.dispositions}
    concepts = {c.id for c in profile.candidates.concepts}

    for record_id, concept_id in REVESTIMENTOS.items():
        assert concept_id in by_record[record_id].candidate_ids
        assert concept_id in concepts
    for correspondence in profile.reconciliation.correspondences:
        assert len(set(correspondence.a_record_ids) & set(REVESTIMENTOS)) <= 1


@pytest.mark.external_data
def test_tipo_concretagem_keeps_one_concept_with_three_uses(
    profile: DaianeProfileInventory,
) -> None:
    bindings = [b for b in profile.candidates.bindings if b.concept_id == CONCRETAGEM]

    assert len(bindings) == 3
    assert sorted(b.source_assertion_ids[0] for b in bindings) == [
        "dai2025:A7-010",
        "dai2025:A8-008",
        "dai2025:A9-009",
    ]


@pytest.mark.external_data
def test_area_forma_stays_pending_unwritable_and_linked_to_its_decision(
    profile: DaianeProfileInventory,
) -> None:
    bindings = [b for b in profile.candidates.bindings if b.field_name == "Area_Forma"]
    decision = next(
        d for d in profile.candidates.reconciliation_decisions if d.id == AREA_FORMA_DECISION
    )
    corr = {c.id: c for c in profile.reconciliation.correspondences}
    b_area = [
        d
        for d in profile.reconciliation.dispositions
        if d.source_record_id in ("dai2025:B-E07-0018", "dai2025:B-E08-0016", "dai2025:B-E09-0017")
    ]

    assert len(bindings) == 3
    assert all(
        (b.carrier_kind, b.carrier_status, b.ifc_type, b.write_enabled, b.scope)
        == ("property_or_quantity", "pending_reconciliation", None, False, "unspecified")
        for b in bindings
    )
    assert decision.status == "pending"
    assert len(b_area) == 3
    for item in b_area:
        relations = {corr[c].relation for c in item.correspondence_ids}
        assert relations == {"unresolved"}
        assert all(AREA_FORMA_DECISION in corr[c].decision_ids for c in item.correspondence_ids)


@pytest.mark.external_data
def test_cost_prop_never_replaces_eb_orcamento(profile: DaianeProfileInventory) -> None:
    sets = {b.set_name for b in profile.candidates.bindings}
    text = json.dumps(profile.reconciliation.model_dump(mode="json"), ensure_ascii=False)

    assert sets == {"EB_Orçamento"}
    assert "Cost_Prop" not in sets
    assert "Cost_Prop" not in text or "não substitui" in text


@pytest.mark.external_data
def test_source_literals_are_not_corrected(
    profile: DaianeProfileInventory, appendix_a: DaianeImport
) -> None:
    a = {x.id: x for x in appendix_a.assertions}
    corr = next(
        c for c in profile.reconciliation.correspondences if "dai2025:A3-024" in c.a_record_ids
    )

    assert a["dai2025:A3-024"].target_identifier_literal == "Heigth"
    assert (
        profile.b_inventory.record("dai2025:B-E10-0011").structured["property_name_literal"]
        == "Weigth"
    )
    assert corr.relation == "unresolved"
    assert "Heigth" in corr.justification
    assert "Height" in corr.justification


@pytest.mark.external_data
def test_unspecified_scope_and_exact_class_are_preserved(profile: DaianeProfileInventory) -> None:
    assert {b.scope for b in profile.candidates.bindings} == {"unspecified"}
    rules = {r.id: r for r in profile.candidates.applicability_rules}
    assert all(not r.include_subtypes and r.predefined_types for r in rules.values())


@pytest.mark.external_data
def test_candidates_are_drafts_refused_for_release(profile: DaianeProfileInventory) -> None:
    lifecycles = {
        e.lifecycle for _, e in profile.candidates.iter_entities() if hasattr(e, "lifecycle")
    }

    assert lifecycles == {"draft"}
    with pytest.raises(CatalogValidationError):
        validate_content(profile.candidates, for_release=True)


@pytest.mark.external_data
def test_assistant_proposals_are_never_marked_as_human_decisions(
    profile: DaianeProfileInventory,
) -> None:
    assert {c.review_state for c in profile.reconciliation.correspondences} == {
        "assistant_proposal"
    }


# --- Capacidade por evidência ----------------------------------------------------------


SYN_FILES: dict[str, bytes] = {
    "tests/synthetic_case.py": b"def test_case(): pass\n",
    "src/synthetic_impl.py": b"IMPLEMENTACAO = 'sintetica'\n",
    "report.xml": b"<testsuite tests='1' failures='0'/>",
    "inputs.json": b'{"caso": "sintetico"}',
}
TRUSTED_TRUST = CapabilityTrust(
    approved_nodeids=(SYN_NODEID,),
    ids_capability_manifest_sha256=CAPABILITY_MANIFEST_SHA256,
    approved_implementation_sha256s=(
        hashlib.sha256(SYN_FILES["src/synthetic_impl.py"]).hexdigest(),
    ),
    executed_report_sha256s=(hashlib.sha256(SYN_FILES["report.xml"]).hexdigest(),),
)
"""Âncoras fora da evidência: nodeid, matriz IDS E3 carregada, implementação e relatório."""
CONCRETAGEM_A7_BINDING = "urn:uuid:0ba6dca1-8539-4556-8658-78489809bccf"
"""Binding ``property``/``IfcLabel``/IFC4 de Tipo_Concretagem (A7-010): dentro da matriz E3."""
PROPERTY_LITERAL_CELL = "requirement:property:literal"


def _evidence(
    profile: DaianeProfileInventory, binding_id: str = CONCRETAGEM_A7_BINDING, **changes: Any
) -> ProfileCapabilityEvidence:
    """Evidência SINTÉTICA de um caso de validação de um binding do perfil."""
    binding = next(b for b in profile.candidates.bindings if b.id == binding_id)
    case = CapabilityCaseManifest(
        case_id="syn-case-1",
        nodeid=SYN_NODEID,
        outcome="passed",
        exit_code=0,
        test_file="tests/synthetic_case.py",
        test_file_sha256=hashlib.sha256(SYN_FILES["tests/synthetic_case.py"]).hexdigest(),
        implementation_file="src/synthetic_impl.py",
        implementation_sha256=hashlib.sha256(SYN_FILES["src/synthetic_impl.py"]).hexdigest(),
        raw_report_file="report.xml",
        raw_report_sha256=hashlib.sha256(SYN_FILES["report.xml"]).hexdigest(),
        inputs_file="inputs.json",
        inputs_sha256=hashlib.sha256(SYN_FILES["inputs.json"]).hexdigest(),
        classifier="synthetic_contract",
        capability_cell=PROPERTY_LITERAL_CELL,
        binding_id=binding.id,
        binding_sha256=binding_sha256(binding),
    )
    claim = CapabilityClaim(
        binding_id=binding.id,
        binding_sha256=binding_sha256(binding),
        policy_sha256=policy_sha256(
            next(
                p
                for p in profile.candidates.evidence_policies
                if p.id == binding.evidence_policy_id
            )
        ),
        base_a_sha256=profile.reconciliation.bases.matrix_sha256,
        base_b_sha256=profile.reconciliation.bases.appendix_b_sha256,
        axis="validation",
        ifc_schema="IFC4",
        facet="property",
        carrier_kind=binding.carrier_kind,
        capability_cell=PROPERTY_LITERAL_CELL,
        case_id="syn-case-1",
    )
    data: dict[str, Any] = {
        "cases": [case.model_dump(mode="json")],
        "claims": [claim.model_dump(mode="json")],
        "artifacts": dict(SYN_FILES),
    }
    for key, value in changes.items():
        data[key] = value(data) if callable(value) else value
    return ProfileCapabilityEvidence.model_validate(data)


def _with_claim(
    reconciliation: ProfileReconciliation,
    record_id: str = "dai2025:A7-010",
    axis: str = "validation",
    state: str = "verified_for_case",
) -> ProfileReconciliation:
    def change(data: dict[str, Any]) -> None:
        item = next(d for d in data["dispositions"] if d["source_record_id"] == record_id)
        item["axes"][axis] = state
        item["axes"][f"{axis}_reason"] = "caso sintético syn-case-1"

    return _mutated(reconciliation, change)


def _enrichment_claims(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            **data["claims"][0],
            "axis": "enrichment",
            "capability_cell": None,
            "operation_id": "recover_exact_property",
            "operation_version": "1.0.0",
        }
    ]


@pytest.mark.external_data
def test_synthetic_case_verifies_only_for_case(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
) -> None:
    built = _build(
        appendix_a, appendix_b, _with_claim(reconciliation), _evidence(profile), TRUSTED_TRUST
    )

    assert [(v.state, v.classifier) for v in built.verified_capabilities] == [
        ("verified_for_case", "synthetic_contract")
    ]
    assert built.verified_capabilities[0].capability_cell == PROPERTY_LITERAL_CELL


@pytest.mark.external_data
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"artifacts": lambda d: {**d["artifacts"], "report.xml": b"<adulterado/>"}}, "hash"),
        (
            {
                "artifacts": lambda d: {
                    k: v for k, v in d["artifacts"].items() if k != "inputs.json"
                }
            },
            "ausente",
        ),
        ({"cases": lambda d: [{**d["cases"][0], "outcome": "not_executed"}]}, "não executado"),
        ({"cases": lambda d: [{**d["cases"][0], "exit_code": 1}]}, "não executado"),
        ({"claims": lambda d: [{**d["claims"][0], "binding_sha256": "0" * 64}]}, "binding"),
        ({"claims": lambda d: [{**d["claims"][0], "base_b_sha256": "0" * 64}]}, "base"),
        ({"claims": lambda d: [{**d["claims"][0], "case_id": "outro"}]}, "caso"),
        ({"claims": _enrichment_claims}, "manifesto"),
    ],
)
def test_capability_evidence_is_rechecked_not_trusted(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
    changes: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ProfileReconciliationError, match=message):
        _build(
            appendix_a,
            appendix_b,
            _with_claim(reconciliation),
            _evidence(profile, **changes),
            TRUSTED_TRUST,
        )


@pytest.mark.external_data
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"claims": lambda d: [{**d["claims"][0], "facet": "material"}]}, "faceta"),
        ({"claims": lambda d: [{**d["claims"][0], "facet": "attribute"}]}, "faceta"),
        ({"claims": lambda d: [{**d["claims"][0], "ifc_schema": "IFC2X3"}]}, "schema"),
        (
            {"claims": lambda d: [{**d["claims"][0], "capability_cell": "requirement:attribute"}]},
            "célula",
        ),
        (
            {
                "cases": lambda d: [
                    {**d["cases"][0], "capability_cell": "requirement:property:enumeration"}
                ]
            },
            "célula",
        ),
        ({"cases": lambda d: [{**d["cases"][0], "capability_cell": None}]}, "célula"),
    ],
)
def test_validation_claim_needs_compatible_facet_schema_and_executed_e3_cell(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
    changes: dict[str, Any],
    message: str,
) -> None:
    """Faceta/schema/célula incompatíveis, com todos os hashes válidos: nada é promovido."""
    with pytest.raises(ProfileReconciliationError, match=message):
        _build(
            appendix_a,
            appendix_b,
            _with_claim(reconciliation),
            _evidence(profile, **changes),
            TRUSTED_TRUST,
        )


@pytest.mark.external_data
@pytest.mark.parametrize("facet", ["property", "material"])
def test_area_forma_validation_claim_is_outside_the_e3_ids_matrix(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
    facet: str,
) -> None:
    """Portador ``property_or_quantity`` sem ``ifc_type``: nenhuma célula E3 se aplica."""
    evidence = _evidence(
        profile,
        AREA_FORMA_BINDING,
        claims=lambda d: [{**d["claims"][0], "facet": facet}],
    )
    with pytest.raises(ProfileReconciliationError, match=r"faceta|portador|matriz"):
        _build(
            appendix_a,
            appendix_b,
            _with_claim(reconciliation, "dai2025:A7-013"),
            evidence,
            TRUSTED_TRUST,
        )


@pytest.mark.external_data
@pytest.mark.parametrize(
    ("trust_changes", "message"),
    [
        ({"ids_capability_manifest_sha256": None}, "matriz"),
        ({"ids_capability_manifest_sha256": "0" * 64}, "matriz"),
        ({"approved_implementation_sha256s": ()}, "implementação"),
        ({"executed_report_sha256s": ()}, "relatório"),
    ],
)
def test_validation_claim_needs_anchors_outside_the_evidence(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
    trust_changes: dict[str, Any],
    message: str,
) -> None:
    """Hash autodeclarado de implementação/relatório não prova execução sem âncora."""
    trust = TRUSTED_TRUST.model_copy(update=trust_changes)
    with pytest.raises(ProfileReconciliationError, match=message):
        _build(appendix_a, appendix_b, _with_claim(reconciliation), _evidence(profile), trust)


def test_validation_claim_without_cell_and_enrichment_claim_with_cell_are_refused() -> None:
    base = {
        "binding_id": CONCRETAGEM_A7_BINDING,
        "binding_sha256": "0" * 64,
        "base_a_sha256": "0" * 64,
        "base_b_sha256": "0" * 64,
        "ifc_schema": "IFC4",
        "facet": "property",
        "carrier_kind": "property",
        "case_id": "c",
    }
    with pytest.raises(ValueError, match="capability_cell"):
        CapabilityClaim.model_validate({**base, "axis": "validation"})
    with pytest.raises(ValueError, match="capability_cell"):
        CapabilityClaim.model_validate(
            {**base, "axis": "enrichment", "capability_cell": PROPERTY_LITERAL_CELL}
        )


@pytest.mark.external_data
def test_enrichment_claim_checks_the_loaded_bundle_manifest(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
) -> None:
    from src.suggestion_engine.catalog_operations import build_e3_operation_bundle

    bundle = build_e3_operation_bundle()
    manifest_json = json.dumps(
        bundle.manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    recon = _with_claim(reconciliation, axis="enrichment")
    trust = TRUSTED_TRUST.model_copy(
        update={"operation_bundle_manifest_sha256": bundle.manifest_sha256}
    )
    good = _evidence(profile, claims=_enrichment_claims, operation_manifest_json=manifest_json)
    built = _build(appendix_a, appendix_b, recon, good, trust)
    assert [v.axis for v in built.verified_capabilities] == ["enrichment"]

    unknown = _evidence(
        profile,
        claims=lambda d: [{**_enrichment_claims(d)[0], "operation_id": "inventada"}],
        operation_manifest_json=manifest_json,
    )
    with pytest.raises(ProfileReconciliationError, match="bundle"):
        _build(appendix_a, appendix_b, recon, unknown, trust)

    fabricated_manifest = json.dumps({"handlers": ["inventada@9.9.9"]}, separators=(",", ":"))
    fabricated = _evidence(
        profile,
        claims=lambda d: [
            {**_enrichment_claims(d)[0], "operation_id": "inventada", "operation_version": "9.9.9"}
        ],
        operation_manifest_json=fabricated_manifest,
    )
    with pytest.raises(ProfileReconciliationError, match="bundle"):
        _build(appendix_a, appendix_b, recon, fabricated, trust)
    with pytest.raises(ProfileReconciliationError, match="bundle"):
        _build(appendix_a, appendix_b, recon, good, TRUSTED_TRUST)


@pytest.mark.external_data
def test_nodeid_outside_the_trusted_allowlist_is_refused(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
) -> None:
    trust = TRUSTED_TRUST.model_copy(update={"approved_nodeids": ()})
    with pytest.raises(ProfileReconciliationError, match="não aprovado"):
        _build(appendix_a, appendix_b, _with_claim(reconciliation), _evidence(profile), trust)


@pytest.mark.external_data
def test_self_declared_real_model_classifier_is_refused(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
) -> None:
    real = _evidence(profile, cases=lambda d: [{**d["cases"][0], "classifier": "real_model"}])
    with pytest.raises(ProfileReconciliationError, match="real_model"):
        _build(
            appendix_a,
            appendix_b,
            _with_claim(reconciliation, state="real_model_verified"),
            real,
            TRUSTED_TRUST,
        )


# --- Retomada 23/10: alcance das correspondências (M24) ----------------------------------


def _correspondence(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "ab-9999",
        "a_record_ids": ["dai2025:A7-010"],
        "b_record_ids": ["dai2025:B-E07-0011"],
        "relation": "same_claim",
        "justification": "comparação sintética",
        "compared_fields": ["family/specification", "set_literal", "name_literal", "datatype"],
        "review_state": "assistant_proposal",
        "decision_ids": [],
    }
    data.update(changes)
    return data


def test_same_claim_without_domain_comparison_is_refused() -> None:
    """M24: mesmo alvo impresso sem comparar domínio/restrições não é a mesma afirmação."""
    with pytest.raises(ValueError, match="same_printed_target"):
        ABCorrespondence.model_validate(_correspondence())


def test_same_claim_with_domain_compared_and_printed_target_relation_are_accepted() -> None:
    compared = ["family/specification", "name_literal", "datatype", "domain/restriction"]
    assert ABCorrespondence.model_validate(_correspondence(compared_fields=compared))
    assert ABCorrespondence.model_validate(_correspondence(relation="same_printed_target"))


@pytest.mark.external_data
def test_real_correspondences_state_their_demonstrated_scope(
    profile: DaianeProfileInventory,
) -> None:
    relations = Counter(c.relation for c in profile.reconciliation.correspondences)

    assert relations["same_claim"] == 0
    assert relations["same_printed_target"] > 0
    assert all(
        c.review_state == "assistant_proposal" for c in profile.reconciliation.correspondences
    )
    for item in profile.reconciliation.correspondences:
        if item.relation == "same_printed_target":
            assert "não comparad" in item.justification


# --- Revisão independente de 23/10: I-A, I-B, I-C e aplicabilidade (menor 1) ------------


def _bundle_manifest_json() -> tuple[str, str]:
    from src.suggestion_engine.catalog_operations import build_e3_operation_bundle

    bundle = build_e3_operation_bundle()
    text = json.dumps(bundle.manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text, bundle.manifest_sha256


@pytest.mark.external_data
def test_area_forma_enrichment_claim_is_refused(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
) -> None:
    """I-A: a operação E3 só lê IfcPropertySingleValue; portador indefinido não é elevado."""
    manifest_json, manifest_sha = _bundle_manifest_json()
    evidence = _evidence(
        profile,
        AREA_FORMA_BINDING,
        claims=_enrichment_claims,
        operation_manifest_json=manifest_json,
    )
    trust = TRUSTED_TRUST.model_copy(update={"operation_bundle_manifest_sha256": manifest_sha})
    with pytest.raises(ProfileReconciliationError, match="portador"):
        _build(
            appendix_a,
            appendix_b,
            _with_claim(reconciliation, "dai2025:A7-013", axis="enrichment"),
            evidence,
            trust,
        )


@pytest.mark.external_data
def test_case_that_exercised_another_binding_does_not_verify_this_one(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
) -> None:
    """I-B: o caso cita o binding exercitado; afirmação sobre outro binding é recusada."""
    other = next(
        b
        for b in profile.candidates.bindings
        if b.id != CONCRETAGEM_A7_BINDING and b.carrier_kind == "property"
    )
    evidence = _evidence(
        profile,
        cases=lambda d: [
            {**d["cases"][0], "binding_id": other.id, "binding_sha256": binding_sha256(other)}
        ],
    )
    with pytest.raises(ProfileReconciliationError, match="binding"):
        _build(appendix_a, appendix_b, _with_claim(reconciliation), evidence, TRUSTED_TRUST)


@pytest.mark.external_data
def test_self_supplied_bundle_anchor_is_refused(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
) -> None:
    """I-C: a âncora do bundle é conferida contra o bundle E3 carregado pelo código."""
    from src.operations.contracts import canonical_sha256

    fabricated = {"handlers": ["recover_exact_property@1.0.0"]}
    evidence = _evidence(
        profile,
        claims=_enrichment_claims,
        operation_manifest_json=json.dumps(fabricated, separators=(",", ":")),
    )
    trust = TRUSTED_TRUST.model_copy(
        update={"operation_bundle_manifest_sha256": canonical_sha256(fabricated)}
    )
    with pytest.raises(ProfileReconciliationError, match="bundle"):
        _build(
            appendix_a,
            appendix_b,
            _with_claim(reconciliation, axis="enrichment"),
            evidence,
            trust,
        )


@pytest.mark.external_data
@pytest.mark.parametrize(
    ("changes", "accepted"),
    [
        ({}, True),
        ({"include_subtypes": True}, False),
        ({"entity_classes": ("IfcSlab", "IfcBeam")}, False),
        ({"predefined_types": ("USERDEFINED",)}, False),
        ({"predefined_types": ("FLOOR", "ROOF")}, False),
    ],
)
def test_ids_cells_respect_the_e3_applicability_cell(
    profile: DaianeProfileInventory, changes: dict[str, Any], accepted: bool
) -> None:
    """Menor 1: regra fora da célula de aplicabilidade E3 não recebe célula de requisito."""
    binding = next(b for b in profile.candidates.bindings if b.id == CONCRETAGEM_A7_BINDING)
    rule = next(
        r for r in profile.candidates.applicability_rules if r.id == binding.applicability_rule_id
    ).model_copy(update={"entity_classes": ("IfcSlab",), "include_subtypes": False, **changes})
    claim = _evidence(profile).claims[0]
    if accepted:
        assert PROPERTY_LITERAL_CELL in ids_cells_for_binding(binding, claim, rule)
    else:
        with pytest.raises(ProfileReconciliationError, match="aplicabilidade"):
            ids_cells_for_binding(binding, claim, rule)


@pytest.mark.external_data
@pytest.mark.parametrize(
    ("ifc_type", "cells"),
    [
        ("IfcBoolean", {"requirement:property:presence"}),
        ("IfcReal", None),
    ],
)
def test_scalar_type_gets_presence_only_and_measure_types_get_no_cell(
    profile: DaianeProfileInventory, ifc_type: str, cells: set[str] | None
) -> None:
    binding = next(
        b for b in profile.candidates.bindings if b.id == CONCRETAGEM_A7_BINDING
    ).model_copy(update={"ifc_type": ifc_type})
    rule = next(
        r for r in profile.candidates.applicability_rules if r.id == binding.applicability_rule_id
    )
    claim = _evidence(profile).claims[0]
    if cells is None:
        with pytest.raises(ProfileReconciliationError, match="tipo"):
            ids_cells_for_binding(binding, claim, rule)
    else:
        assert ids_cells_for_binding(binding, claim, rule) == cells


@pytest.mark.external_data
@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["family_map"].append(dict(d["family_map"][0])),
        lambda d: d["decisions"].append(dict(d["decisions"][0])),
        lambda d: d["dispositions"][0]["correspondence_ids"].extend(
            d["dispositions"][0]["correspondence_ids"][:1] or ["ab-0001", "ab-0001"]
        ),
        lambda d: d["correspondences"][0]["b_record_ids"].extend(
            d["correspondences"][0]["b_record_ids"][:1]
        ),
        lambda d: d["divergences"][0]["source_record_ids"].extend(
            d["divergences"][0]["source_record_ids"][:1]
        ),
    ],
)
def test_duplicate_keys_and_repeated_ids_in_sets_are_refused(
    reconciliation: ProfileReconciliation, change: Any
) -> None:
    """Menor 3: chave repetida ou ID repetido em conjunto não pode mudar a identidade."""
    data = reconciliation.model_dump(mode="json")
    change(data)
    with pytest.raises(ValueError, match="repetid"):
        ProfileReconciliation.model_validate(data)


# --- Revalidação de 23/10: R1–R3 ---------------------------------------------------------


@pytest.mark.external_data
def test_enrichment_requires_an_approved_carrier(
    profile: DaianeProfileInventory,
) -> None:
    """R1: binding ``property`` com portador ainda pendente não é elevado no enriquecimento."""
    from src.domain_catalog.profile import verify_capabilities

    manifest_json, manifest_sha = _bundle_manifest_json()
    binding = next(b for b in profile.candidates.bindings if b.id == CONCRETAGEM_A7_BINDING)
    pending = binding.model_copy(update={"carrier_status": "pending_reconciliation"})
    candidates = profile.candidates.model_copy(
        update={
            "bindings": tuple(
                pending if b.id == binding.id else b for b in profile.candidates.bindings
            )
        }
    )
    evidence = _evidence(
        profile,
        claims=lambda d: [{**_enrichment_claims(d)[0], "binding_sha256": binding_sha256(pending)}],
        cases=lambda d: [{**d["cases"][0], "binding_sha256": binding_sha256(pending)}],
        operation_manifest_json=manifest_json,
    )
    trust = TRUSTED_TRUST.model_copy(update={"operation_bundle_manifest_sha256": manifest_sha})
    with pytest.raises(ProfileReconciliationError, match="portador"):
        verify_capabilities(evidence, candidates, profile.reconciliation, trust)


@pytest.mark.external_data
def test_same_executed_case_cannot_be_reused_for_another_binding(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
) -> None:
    """R2: mesmo nodeid/relatório declarado para dois bindings é recusado."""
    other = next(
        b
        for b in profile.candidates.bindings
        if b.id != CONCRETAGEM_A7_BINDING and b.carrier_kind == "property"
    )
    evidence = _evidence(
        profile,
        cases=lambda d: [
            d["cases"][0],
            {
                **d["cases"][0],
                "case_id": "syn-case-2",
                "binding_id": other.id,
                "binding_sha256": binding_sha256(other),
            },
        ],
    )
    with pytest.raises(ProfileReconciliationError, match="mesmo caso executado"):
        _build(appendix_a, appendix_b, _with_claim(reconciliation), evidence, TRUSTED_TRUST)


@pytest.mark.external_data
@pytest.mark.parametrize("entity_class", ["IfcSlabType", "IfcWallType"])
def test_type_object_class_is_outside_the_e3_applicability_cell(
    profile: DaianeProfileInventory, entity_class: str
) -> None:
    """R3: a matriz E3 aceita só subtipos de IfcObject; classe de tipo fica fora."""
    binding = next(b for b in profile.candidates.bindings if b.id == CONCRETAGEM_A7_BINDING)
    rule = next(
        r for r in profile.candidates.applicability_rules if r.id == binding.applicability_rule_id
    ).model_copy(update={"entity_classes": (entity_class,), "include_subtypes": False})
    with pytest.raises(ProfileReconciliationError, match="aplicabilidade"):
        ids_cells_for_binding(binding, _evidence(profile).claims[0], rule)


@pytest.mark.external_data
def test_distinct_cases_from_one_run_may_share_the_junit_report(
    profile: DaianeProfileInventory,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
) -> None:
    """N1: um relatório JUnit por execução é normal; casos distintos de bindings distintos
    podem citá-lo. Só o mesmo nodeid declarado para dois bindings é reaproveitamento."""
    other = next(
        b
        for b in profile.candidates.bindings
        if b.id != CONCRETAGEM_A7_BINDING and b.carrier_kind == "property"
    )
    evidence = _evidence(
        profile,
        cases=lambda d: [
            d["cases"][0],
            {
                **d["cases"][0],
                "case_id": "syn-case-2",
                "nodeid": "tests/synthetic_case.py::test_other",
                "binding_id": other.id,
                "binding_sha256": binding_sha256(other),
            },
        ],
    )
    built = _build(appendix_a, appendix_b, _with_claim(reconciliation), evidence, TRUSTED_TRUST)
    assert [v.binding_id for v in built.verified_capabilities] == [CONCRETAGEM_A7_BINDING]
