"""Projeto SINTÉTICO com pares IFC–IDS reais e catálogo de duas operações (aceite E3).

Binding ``SYN_Conjunto.SYN_Metodo`` com política de recuperação exata e binding
``SYN_Conjunto.SYN_Codigo`` com política de normalização de código; aliases
``SYN_Legado.Metodo``/``SYN_Legado.Codigo``. O par A tem recuperação, normalização,
conflito e ausência; o par B tem campo já satisfeito e normalização sem mudança. Todo
conteúdo, ator e arquivo é sintético; nenhuma publicação aqui aprova dado real.
"""

import uuid
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.models import AllowedValue, AllowedValueSet, EvidencePolicy, IFCBinding
from src.suggestion_engine.catalog_operations import E3OperationBundle, build_e3_operation_bundle
from src.validation.analysis_identity import AnalysisRun
from src.validation.catalog_analysis import CatalogAnalysisRequest
from tests.domain_catalog import factories as f
from tests.operations.adoption_env import AdoptionEnv, add_pair, make_adoption_env
from tests.suggestion_engine import m3_helpers as m
from tests.validation import ids_builders as x
from tests.validation import ifc_builders as ib

CODE_POLICY = "urn:uuid:00000000-0000-4000-8000-00000000e311"
CODE_VALUES = "urn:uuid:00000000-0000-4000-8000-00000000e312"
CODE_ALIAS = "urn:uuid:00000000-0000-4000-8000-00000000e313"
CODE_BINDING = "urn:uuid:00000000-0000-4000-8000-00000000e314"
CODE_CONCEPT = "urn:uuid:00000000-0000-4000-8000-00000000e315"
CODES = ("Café", "Outro")
EntityT = TypeVar("EntityT", bound=BaseModel)
RAW_CODE = "  Cafe\u0301\t"


def code_policy(**changes: object) -> EvidencePolicy:
    """Política de normalização do código (aprovada; o envelope decide o estado)."""
    return EvidencePolicy.model_validate(
        {
            "id": CODE_POLICY,
            "operation_id": "normalize_code_nfc_trim",
            "operation_version": "1.0.0",
            "admissible_channels": ("P", "T"),
            "preconditions": ("textual_enum", "unique_exact_code"),
            "on_missing": "abstain",
            "on_conflict": "abstain",
            "lifecycle": "approved",
            **changes,
        }
    )


def as_draft(content: CatalogContent) -> CatalogContent:
    """Mesmo conteúdo com toda entidade cadastral em ``draft`` (importação E2)."""
    data: dict[str, Any] = {}
    for kind, entities in content.model_dump().items():
        data[kind] = [
            {**entity, "lifecycle": "draft"} if "lifecycle" in entity else entity
            for entity in entities
        ]
    return CatalogContent.model_validate(data)


def draft_entity(entity: EntityT) -> EntityT:
    """Mesma entidade em ``draft``, para propor mudança num rascunho E2."""
    return entity.model_copy(update={"lifecycle": "draft"})


def catalog(*, metodo_sets: tuple[str, ...] = ("SYN_Legado",)) -> CatalogContent:
    """Catálogo sintético de dois bindings, em ``draft`` para importação."""
    base = m.content(aliases=(m.alias(sets=metodo_sets),))
    concept = f.concept().model_copy(
        update={"id": CODE_CONCEPT, "code": "SYN_CODIGO", "value_set_id": CODE_VALUES}
    )
    binding = IFCBinding.model_validate(
        {
            **f.binding().model_dump(),
            "id": CODE_BINDING,
            "concept_id": CODE_CONCEPT,
            "field_name": "SYN_Codigo",
            "evidence_policy_id": CODE_POLICY,
        }
    )
    values = AllowedValueSet(
        id=CODE_VALUES,
        value_type="code",
        values=tuple(AllowedValue(code=c) for c in CODES),
        lifecycle="approved",
    )
    data = base.model_dump()
    additions = {
        "concepts": concept.model_dump(),
        "bindings": binding.model_dump(),
        "value_sets": values.model_dump(),
        "evidence_policies": code_policy().model_dump(),
        "aliases": m.alias(CODE_ALIAS, "Codigo", target=CODE_BINDING).model_dump(),
    }
    for kind, entity in additions.items():
        data[kind] = (*data[kind], entity)
    return as_draft(CatalogContent.model_validate(data))


def ids_bytes(name: str) -> bytes:
    """IDS com os dois requisitos sobre ``IfcSlab``."""
    return x.ids(
        x.spec(
            name,
            x.entity("IFCSLAB"),
            m.TARGET + x.prop("SYN_Conjunto", "SYN_Codigo", value=x.enum(*CODES)),
        )
    )


def _slab(model: Any, set_name: str, *props: tuple[str, str]) -> Any:
    element = ib.element(model, "IfcSlab")
    singles = [ib.single(model, name, "IfcLabel", value) for name, value in props]
    ib.pset(model, element, set_name, singles)
    return element


def ifc_a() -> bytes:
    """Recuperação + normalização (laje 1); conflito + ausência (laje 2)."""
    model = ib.model()
    _slab(model, "SYN_Legado", ("Metodo", "A"), ("Codigo", RAW_CODE))
    conflicted = _slab(model, "SYN_Legado", ("Metodo", "A"))
    slab_type = ib.typed(model, conflicted, "IfcSlabType")
    ib.pset(model, slab_type, "SYN_Legado", [ib.single(model, "Metodo", "IfcLabel", "B")])
    return model.to_string().encode()


def ifc_b() -> bytes:
    """Campo já satisfeito e código válido observado em alias."""
    model = ib.model()
    slab = _slab(model, "SYN_Conjunto", ("SYN_Metodo", "A"))
    ib.pset(model, slab, "SYN_Legado", [ib.single(model, "Codigo", "IfcLabel", "Outro")])
    return model.to_string().encode()


def make_analysis_env(base: Path, *, purpose: str = "synthetic_test") -> AdoptionEnv:
    """Projeto com o par A (arquitetura) e o par B (estrutura) de fontes reais."""
    aenv = make_adoption_env(base, pairs=0, purpose=purpose)  # type: ignore[arg-type]
    add_pair(aenv, "arquitetura", ifc=ifc_a(), ids=ids_bytes("Lajes A"))
    add_pair(aenv, "estrutura", ifc=ifc_b(), ids=ids_bytes("Lajes B"))
    return aenv


def operation_bundle() -> E3OperationBundle:
    """Bundle de operações explícito da condição."""
    return build_e3_operation_bundle()


def request_for(run: AnalysisRun, command_id: uuid.UUID | None = None) -> CatalogAnalysisRequest:
    """Pedido de execução de um run enfileirado, com o hash da identidade congelada."""
    return CatalogAnalysisRequest(
        analysis_id=run.analysis_id,
        command_id=command_id or uuid.uuid4(),
        expected_identity_sha256=run.identity.digest(),
    )


def runs_in_pair_order(aenv: AdoptionEnv, analysis_ids: tuple[uuid.UUID, ...]) -> list[AnalysisRun]:
    """Runs das análises dadas na ordem dos pares do projeto (A, B)."""
    runs = {r.identity.pair_id: r for r in (run_of(aenv, a) for a in analysis_ids)}
    return [runs[pair] for pair in aenv.pairs]


def run_of(aenv: AdoptionEnv, analysis_id: uuid.UUID) -> AnalysisRun:
    """Run persistido pela identidade."""
    return next(r for r in aenv.adoption.list_runs(aenv.project_id) if r.analysis_id == analysis_id)
