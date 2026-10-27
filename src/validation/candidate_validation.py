"""Validação pura de um valor candidato contra o esperado IDS (plano §6, ``validate_candidate``).

Verifica **um valor proposto**, não a conformidade do modelo: não constrói nem muta
IFC temporário para usar o backend. Suporte: texto (IFCLABEL/IFCTEXT/IFCIDENTIFIER),
unidade não aplicável, cardinalidade ``required``/``optional``, presença não vazia,
igualdade literal ou enumeração ``xs:string``. Sem normalização, defaults ou
coerção; ``prohibited`` não gera proposta de preencher; booleano/inteiro e demais
restrições ficam ``unsupported``.
"""

from typing import Literal

from src.domain_catalog.contracts import ContractModel
from src.domain_catalog.models import NonEmptyText, Sha256Hex
from src.ifc_analyzer.observations import BooleanValue, IntegerValue, TextValue
from src.validation.analysis_identity import VerifierIdentity
from src.validation.diagnostic_models import ExpectedField
from src.validation.ids_constraints import TEXT_DATATYPES

CandidateStatus = Literal["satisfied", "violates", "unsupported", "error"]


class CandidateValidation(ContractModel):
    """Resultado da validação do candidato, com a regra exata e a capacidade usada."""

    status: CandidateStatus
    rule_refs: tuple[str, ...]
    capability_id: NonEmptyText
    verifier_capability_sha256: Sha256Hex
    reasons: tuple[str, ...] = ()


def validate_candidate(
    expected: ExpectedField,
    candidate: TextValue | BooleanValue | IntegerValue,
    verifier: VerifierIdentity,
) -> CandidateValidation:
    """``satisfied``/``violates`` só nas células suportadas; o resto é ``unsupported``."""
    refs = (expected.requirement.key(), expected.fragment_sha256)

    def result(status: CandidateStatus, cell: str, *reasons: str) -> CandidateValidation:
        return CandidateValidation(
            status=status,
            rule_refs=refs,
            capability_id=cell,
            verifier_capability_sha256=verifier.capability_manifest_sha256,
            reasons=reasons,
        )

    if expected.facet_tag != "property":
        return result("unsupported", "candidate:facet", "unsupported_facet")
    if expected.set_name is None or expected.field_name is None:
        return result("error", "candidate:expected", "expected_incoherent")
    if expected.cardinality not in ("required", "optional"):
        return result("unsupported", "candidate:cardinality", "prohibited_not_fillable")
    if expected.data_type not in TEXT_DATATYPES:
        return result("unsupported", "candidate:datatype", "unsupported_datatype")
    if not isinstance(candidate, TextValue):
        return result("unsupported", "candidate:value_type", "unsupported_value_type")
    value = expected.value
    if value is not None and value.kind == "simple" and value.text == "":
        return result("unsupported", "candidate:text:literal", "unsupported_empty_simple_value")
    if candidate.value == "":
        return result("violates", "candidate:text:presence", "empty_candidate")
    if value is None:
        return result("satisfied", "candidate:text:presence")
    if value.kind == "simple":
        if candidate.value == value.text:
            return result("satisfied", "candidate:text:literal")
        return result("violates", "candidate:text:literal", "literal_mismatch")
    if (
        value.base == "xs:string"
        and value.facets
        and all(f.name == "enumeration" for f in value.facets)
    ):
        codes = [f.value for f in value.facets]
        if candidate.value in codes:
            return result("satisfied", "candidate:text:enumeration")
        return result("violates", "candidate:text:enumeration", "outside_enumeration")
    return result("unsupported", "candidate:text:restriction", "unsupported_constraint")
