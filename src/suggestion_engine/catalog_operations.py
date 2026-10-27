"""Bundle explícito com as duas operações M3 concretas e sua execução (plano §7.3).

``E3OperationBundle`` tem registro explícito, mapa fechado e imutável
``(operation_id, versão) → handler``, especificações e manifesto com hash. Toda
construção (fábrica ou direta) exige correspondência biunívoca spec/handler, a spec
versionada desta condição e exatamente o callable autorizado para cada chave; o
manifesto nomeia a implementação de cada chave. ``OperationSpec.implementation`` é só
referência documental: nada é importado dinamicamente. ``DEFAULT_OPERATION_REGISTRY``
continua vazio.
Nenhum handler chama LLM, HTTP ou normalizador legado.

- ``recover_exact_property@1.0.0``: valor textual observado sem transformação.
- ``normalize_code_nfc_trim@1.0.0``: ``unicodedata.normalize('NFC', v).strip(' \\t\\r\\n')``
  só do valor observado, comparado literalmente aos códigos originais (exatamente um).

Guardas sempre aplicadas, mesmo com ``preconditions=()``; precondição textual fora da
lista fechada (igualdade exata) é ``unsupported_precondition`` antes do handler.
"""

import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

from src.domain_catalog.operations import OperationRegistry, OperationSpec
from src.ifc_analyzer.observations import BooleanValue, IntegerValue, TextValue
from src.operations.contracts import canonical_sha256
from src.suggestion_engine.catalog_contracts import (
    NOT_REQUESTED_REASONS,
    TECHNICAL_REASONS,
    UNSUPPORTED_REASONS,
    EvidenceAssessment,
    FieldAlternative,
    FieldEnrichmentResult,
    FieldEvidenceContext,
    M3Reason,
)
from src.validation.candidate_validation import validate_candidate

COMMON_PRECONDITIONS: Final = frozenset(
    {
        "same_snapshot",
        "literal_property_single_value",
        "complete_search",
        "strict_typed_value",
        "compatible_unit",
        "no_conflict",
        "occurrence_target",
    }
)
ACCEPTED_PRECONDITIONS: Final[dict[tuple[str, str], frozenset[str]]] = {
    ("recover_exact_property", "1.0.0"): COMMON_PRECONDITIONS,
    ("normalize_code_nfc_trim", "1.0.0"): COMMON_PRECONDITIONS
    | frozenset({"textual_enum", "unique_exact_code"}),
}
NORMALIZATION: Final = "normalize_code_nfc_trim@1.0.0"


class BundleError(Exception):
    """Bundle de operações incoerente (spec sem handler, handler sem spec, versão)."""

    code = "operation_bundle_invalid"


@dataclass(frozen=True)
class HandlerOutcome:
    """Decisão do handler: candidato tipado com método, ou motivo sem proposta."""

    candidate: TextValue | BooleanValue | IntegerValue | None = None
    method: str | None = None
    transformation: str | None = None
    evidence_refs: tuple[str, ...] = ()
    status: str | None = None
    reason: M3Reason | None = None


Handler = Callable[[FieldEvidenceContext, EvidenceAssessment], HandlerOutcome]


def _present(context: FieldEvidenceContext, assessment: EvidenceAssessment) -> list[Any]:
    return [context.observation(i) for i in assessment.admissible_observation_ids]


def recover_exact_property(
    context: FieldEvidenceContext, assessment: EvidenceAssessment
) -> HandlerOutcome:
    """Valor observado exato, sem extrair código do enum, trocar rótulo ou converter tipo."""
    observations = _present(context, assessment)
    values = {(o.typed_value.tag, o.typed_value.value) for o in observations}
    if len(values) != 1:
        return HandlerOutcome(status="abstained", reason="evidence_conflict")
    return HandlerOutcome(
        candidate=observations[0].typed_value,
        method="exact_recovery",
        evidence_refs=tuple(o.observation_id for o in observations),
    )


def normalize_code_nfc_trim(
    context: FieldEvidenceContext, assessment: EvidenceAssessment
) -> HandlerOutcome:
    """NFC + trim ASCII do valor observado contra os códigos textuais aprovados."""
    observations = _present(context, assessment)
    values = {(o.typed_value.tag, o.typed_value.value) for o in observations}
    if len(values) != 1:
        return HandlerOutcome(status="abstained", reason="evidence_conflict")
    value = observations[0].typed_value
    projection = context.projection
    if (
        not isinstance(value, TextValue)
        or projection is None
        or projection.effective_value_set is None
    ):
        return HandlerOutcome(status="unsupported", reason="unsupported_value_type")
    if projection.effective_value_set.lifecycle != "approved":
        return HandlerOutcome(status="abstained", reason="unapproved_content")
    codes = [option.code for option in projection.effective_value_set.values]
    if any(not isinstance(code, str) for code in codes):
        return HandlerOutcome(status="unsupported", reason="unsupported_value_type")
    raw = value.value
    transformed = unicodedata.normalize("NFC", raw).strip(" \t\r\n")
    if raw in codes and transformed != raw and transformed in codes:
        return HandlerOutcome(status="abstained", reason="ambiguous_normalization")
    matches = [code for code in codes if code == transformed]
    if len(matches) != 1:
        return HandlerOutcome(status="abstained", reason="no_matching_code")
    unchanged = transformed == raw
    return HandlerOutcome(
        candidate=TextValue(value=transformed),
        # Sem mudança não há transformação a registrar: é o valor observado exato.
        method="exact_recovery" if unchanged else "code_standardization",
        transformation=None if unchanged else NORMALIZATION,
        evidence_refs=tuple(o.observation_id for o in observations),
    )


E3_SPECS: Final = (
    OperationSpec(
        operation_id="normalize_code_nfc_trim",
        version="1.0.0",
        description="Padroniza o código textual observado (NFC e trim ASCII); exige um código.",
        inputs=("FieldEvidenceContext", "EvidenceAssessment"),
        output="FieldEnrichmentResult",
        preconditions=tuple(sorted(ACCEPTED_PRECONDITIONS[("normalize_code_nfc_trim", "1.0.0")])),
        implementation="src.suggestion_engine.catalog_operations:normalize_code_nfc_trim",
        tests=("tests/suggestion_engine/test_catalog_operations.py",),
    ),
    OperationSpec(
        operation_id="recover_exact_property",
        version="1.0.0",
        description="Recupera o valor textual observado sem transformação, por caminho pertinente.",
        inputs=("FieldEvidenceContext", "EvidenceAssessment"),
        output="FieldEnrichmentResult",
        preconditions=tuple(sorted(ACCEPTED_PRECONDITIONS[("recover_exact_property", "1.0.0")])),
        implementation="src.suggestion_engine.catalog_operations:recover_exact_property",
        tests=("tests/suggestion_engine/test_catalog_operations.py",),
    ),
)


AUTHORIZED_HANDLERS: Final[Mapping[tuple[str, str], Handler]] = MappingProxyType(
    {
        ("normalize_code_nfc_trim", "1.0.0"): normalize_code_nfc_trim,
        ("recover_exact_property", "1.0.0"): recover_exact_property,
    }
)
"""Único callable autorizado por operação/versão desta condição (E3-05)."""
_VERSIONED_SPECS: Final = {(spec.operation_id, spec.version): spec for spec in E3_SPECS}


def _implementation(handler: Handler) -> str:
    return f"{handler.__module__}:{handler.__qualname__}"


def _manifest(
    specs: tuple[OperationSpec, ...], handlers: Mapping[tuple[str, str], Handler]
) -> dict[str, Any]:
    keys = sorted((spec.operation_id, spec.version) for spec in specs)
    return {
        "bundle_id": "m1-e3-operations",
        "version": "1.0.0",
        "operations": [
            spec.model_dump(mode="json") for spec in sorted(specs, key=lambda s: s.operation_id)
        ],
        "accepted_preconditions": {
            f"{op}@{version}": sorted(ACCEPTED_PRECONDITIONS[(op, version)]) for op, version in keys
        },
        "handlers": [f"{op}@{version}" for op, version in keys],
        "implementations": {
            f"{op}@{version}": _implementation(handlers[(op, version)]) for op, version in keys
        },
    }


def _check_keys(keys: list[tuple[str, str]], handlers: Mapping[tuple[str, str], Handler]) -> None:
    if len(keys) != len(set(keys)) or set(keys) != set(handlers):
        raise BundleError("specs e handlers não se correspondem um a um")
    if any(key not in ACCEPTED_PRECONDITIONS for key in keys):
        raise BundleError("operação sem lista fechada de precondições")


@dataclass(frozen=True)
class E3OperationBundle:
    """Registro explícito, handlers fechados e autorizados, specs e manifesto com hash."""

    specs: tuple[OperationSpec, ...]
    handlers: Mapping[tuple[str, str], Handler]
    registry: OperationRegistry = field(compare=False)
    manifest: dict[str, Any] = field(compare=False)
    manifest_sha256: str = ""

    def __post_init__(self) -> None:
        """Valida o conteúdo efetivo em toda construção e congela o mapa de handlers."""
        keys = [(spec.operation_id, spec.version) for spec in self.specs]
        _check_keys(keys, self.handlers)
        for spec, key in zip(self.specs, keys, strict=True):
            if _VERSIONED_SPECS.get(key) != spec:
                raise BundleError(f"spec de {key[0]}@{key[1]} difere da versionada")
            if self.handlers[key] is not AUTHORIZED_HANDLERS.get(key):
                raise BundleError(f"handler de {key[0]}@{key[1]} não é o autorizado")
        manifest = _manifest(self.specs, self.handlers)
        if self.manifest != manifest or self.manifest_sha256 != canonical_sha256(manifest):
            raise BundleError("manifesto não corresponde ao conteúdo do bundle")
        if self.registry.operation_ids != OperationRegistry(self.specs).operation_ids:
            raise BundleError("registro não corresponde às specs")
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))

    @classmethod
    def create(
        cls, specs: tuple[OperationSpec, ...], handlers: Mapping[tuple[str, str], Handler]
    ) -> "E3OperationBundle":
        """Bundle só com specs versionadas e os callables autorizados de cada chave."""
        _check_keys([(spec.operation_id, spec.version) for spec in specs], handlers)
        manifest = _manifest(tuple(specs), handlers)
        return cls(
            specs=tuple(specs),
            handlers=dict(handlers),
            registry=OperationRegistry(specs),
            manifest=manifest,
            manifest_sha256=canonical_sha256(manifest),
        )


def build_e3_operation_bundle() -> E3OperationBundle:
    """Bundle desta condição: as duas operações versionadas e testadas."""
    return E3OperationBundle.create(E3_SPECS, AUTHORIZED_HANDLERS)


def _result(
    context: FieldEvidenceContext,
    assessment: EvidenceAssessment | None,
    status: str,
    reason: M3Reason,
    *more: M3Reason,
) -> FieldEnrichmentResult:
    return FieldEnrichmentResult(
        field=context.field,
        context_sha256=context.context_sha256,
        assessment=assessment,
        status=status,  # type: ignore[arg-type]
        reason=reason,
        reasons=(reason, *(r for r in more if r != reason)),
    )


def _status_for(reason: M3Reason) -> str:
    if reason in TECHNICAL_REASONS:
        return "failed"
    if reason in UNSUPPORTED_REASONS:
        return "unsupported"
    if reason in NOT_REQUESTED_REASONS:
        return "not_requested"
    return "abstained"


_FORMAL: Final[dict[str, tuple[str, M3Reason]]] = {
    "compliant": ("not_requested", "already_satisfied"),
    "not_applicable": ("not_requested", "not_applicable"),
    "not_verified": ("unsupported", "formal_not_verified"),
    "error": ("failed", "formal_error"),
}


def execute_catalog_operation(
    context: FieldEvidenceContext, assessment: EvidenceAssessment, bundle: E3OperationBundle
) -> FieldEnrichmentResult:
    """Resultado do campo: rota formal, guardas, handler exato e validação do candidato."""
    if context.formal_state in _FORMAL:
        status, reason = _FORMAL[context.formal_state]
        return _result(context, assessment, status, reason)
    if assessment.context_sha256 != context.context_sha256:
        return _result(context, assessment, "failed", "identity_mismatch")
    if assessment.status != "sufficient":
        primary = assessment.reasons[0]
        return _result(context, assessment, _status_for(primary), primary, *assessment.reasons)
    key = (assessment.operation_id or "", assessment.operation_version or "")
    handler = bundle.handlers.get(key)
    projection = context.projection
    if handler is None or projection is None:
        return _result(context, assessment, "unsupported", "operation_unavailable")
    guard = _guards(context, assessment)
    if guard is not None:
        return _result(context, assessment, _status_for(guard), guard)
    outcome = handler(context, assessment)
    if outcome.candidate is None:
        assert outcome.reason is not None
        assert outcome.status is not None
        return _result(context, assessment, outcome.status, outcome.reason)
    if _unchanged_at_target(context, assessment, outcome.candidate):
        # O verificador formal já reprovou exatamente este valor neste caminho.
        return _result(context, assessment, "abstained", "candidate_violates_requirement")
    validation = validate_candidate(context.expected, outcome.candidate, context.verifier)
    if validation.status == "violates":
        return _result(context, assessment, "abstained", "candidate_violates_requirement")
    if validation.status == "unsupported":
        return _result(context, assessment, "unsupported", "unsupported_candidate_validation")
    if validation.status == "error":
        return _result(context, assessment, "failed", "internal_error")
    field = context.field
    if field.target_set_name is None or field.target_field_name is None:
        return _result(context, assessment, "failed", "identity_mismatch")
    # Destino é o caminho literal do requisito IDS (que resolveu para este binding);
    # o caminho canônico do binding é só evidência, nunca destino substituto (E3-04).
    alternative = FieldAlternative(
        value=outcome.candidate,
        method=outcome.method,  # type: ignore[arg-type]
        evidence_refs=outcome.evidence_refs,
        transformation=outcome.transformation,
        candidate_validation=validation,
        target_binding_id=projection.binding.id,
        target_set_name=field.target_set_name,
        target_field_name=field.target_field_name,
        affected_elements=(field.element,),
    )
    return FieldEnrichmentResult(
        field=context.field,
        context_sha256=context.context_sha256,
        assessment=assessment,
        status="proposed",
        reason=None,
        alternatives=(alternative,),
        limitations=(
            "alternativa para revisão humana; não aprova nem escreve no IFC",
            "resultado formal IDS do caminho literal permanece inalterado",
        ),
    )


def _guards(context: FieldEvidenceContext, assessment: EvidenceAssessment) -> M3Reason | None:
    """Guardas obrigatórias, independentes das precondições declaradas na política."""
    projection = context.projection
    assert projection is not None
    observations = _present(context, assessment)
    if not observations or any(
        (o.analysis_id, o.element) != (context.field.analysis_id, context.field.element)
        for o in observations
    ):
        return "identity_mismatch"
    if any(o.carrier_kind != "IfcPropertySingleValue" for o in observations):
        return "unsupported_carrier"
    if any(c.status not in ("complete", "not_searched") for c in assessment.coverage):
        return "incomplete_search"
    if any(o.typed_value is None or o.state != "present" for o in observations):
        return "unsupported_value_type"
    if any(o.unit_state != "not_applicable" for o in observations):
        return "unit_mismatch"
    expected_type = context.expected.data_type
    if expected_type is not None and any(
        (o.ifc_type or "").upper() != expected_type.upper() for o in observations
    ):
        # Recuperar valor de outro tipo IFC seria conversão de tipo, nunca proposta.
        return "candidate_type_mismatch"
    if len({(o.typed_value.tag, o.typed_value.value) for o in observations}) != 1:
        return "evidence_conflict"
    if projection.binding.scope != "occurrence":
        return "unsupported_target_scope"
    return None


def _unchanged_at_target(
    context: FieldEvidenceContext, assessment: EvidenceAssessment, candidate: object
) -> bool:
    """Toda evidência está no próprio caminho-alvo de ocorrência, com o valor do candidato."""
    target = (context.field.target_set_name, context.field.target_field_name, "occurrence")
    return all(
        (o.set_name, o.field_name, o.origin) == target and o.typed_value == candidate
        for o in _present(context, assessment)
    )
