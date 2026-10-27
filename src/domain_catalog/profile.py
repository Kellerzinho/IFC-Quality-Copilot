"""Perfil Daiane na E4: reconciliação A/B, capacidades por evidência e projeções (M1-04).

A reconciliação (``data/catalogs/profiles/daiane-e4/reconciliation-v1.json``) é um
documento declarativo: destinos, correspondências A↔B, divergências e identidades,
todos propostos e revisáveis. Este módulo só valida o fechamento contra as bases
exatas (matriz A, transcrição B, candidatos em rascunho), confere capacidades por
evidência local recalculada e deriva relatório e projeções. Não une conceitos por nome,
não cria decisão humana, não aprova nem publica: candidatos seguem em ``draft``.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from loguru import logger
from pydantic import ValidationError

from src.config import BASE_DIR
from src.domain_catalog.canonical import (
    CanonicalJSONError,
    canonical_json_bytes,
    canonical_json_text,
    parse_json_strict,
)
from src.domain_catalog.content import CatalogContent
from src.domain_catalog.curation_models import content_sha256
from src.domain_catalog.drafts import load_draft
from src.domain_catalog.importers.daiane import (
    ALPHANUMERIC_CATEGORIES,
    MATRIX_PATH,
    DaianeImport,
    import_appendix_a,
    load_matrix,
)
from src.domain_catalog.importers.daiane_b import (
    APPENDIX_B_PATH,
    appendix_b_assertions,
    appendix_b_check_level,
    load_appendix_b,
    transcription_artifact_id,
)
from src.domain_catalog.models import (
    ApplicabilityRule,
    CatalogModel,
    EvidencePolicy,
    IFCBinding,
    SourceArtifact,
    SourceCategory,
)
from src.domain_catalog.profile_models import (
    AppendixBInventory,
    CapabilityClaim,
    CapabilityTrust,
    DaianeProfileInventory,
    ProfileCapabilityEvidence,
    ProfileDisposition,
    ProfileReconciliation,
    ProfileReport,
    VerifiedCapability,
)

PROFILE_DIR = BASE_DIR / "data" / "catalogs" / "profiles" / "daiane-e4"
RECONCILIATION_PATH = PROFILE_DIR / "reconciliation-v1.json"
CANDIDATES_PATH = PROFILE_DIR / "candidates-v1.json"
PROJECTIONS_DIR = BASE_DIR / "docs" / "catalogo" / "e4"
PDF_SHA256 = "82ead7b5f06fd06247f9f057727bab071ab1c08de4fe42412bebeb9e0c06877a"
COVERAGE_FILE = "cobertura-daiane.csv"
DIVERGENCE_FILE = "divergencias-daiane.csv"
CORRESPONDENCE_FILE = "correspondencia-a-b.csv"
MANIFEST_FILE = "projecoes-daiane.json"
REVISIONS_DIR = "revisoes"
ARCHIVE_RECORD_FILE = "arquivamento.json"
RECONCILIATION_HASH_SCHEME = "ifcqc-daiane-recon-hash-2"
COVERAGE_FIELDS: tuple[str, ...] = (
    "source_kind",
    "source_record_id",
    "family_id",
    "specification",
    "printed_page",
    "pdf_page",
    "category",
    "literal",
    "destination",
    "reason_code",
    "reason",
    "candidate_ids",
    "decision_ids",
    "correspondence_ids",
    "transcription",
    "catalog",
    "validation",
    "enrichment",
)
DIVERGENCE_FIELDS: tuple[str, ...] = (
    "divergence_id",
    "origin",
    "reported_before",
    "source_record_ids",
    "text",
    "status",
    "decision_ids",
)
CORRESPONDENCE_FIELDS: tuple[str, ...] = (
    "correspondence_id",
    "relation",
    "review_state",
    "a_record_ids",
    "b_record_ids",
    "compared_fields",
    "justification",
    "decision_ids",
)
HUMAN_GATES: tuple[str, ...] = (
    "revisão de significados, agrupamentos e equivalências por curador/especialista",
    "aceite do perfil de domínio (conteúdo exato, com hash) e publicação pela cadeia E2",
    "portador histórico de Area_Forma (IFC/exportação do IDS_Mestrado ou confirmação da autora)",
    "recebimento e conferência do XML IDS_Mestrado e da planilha editável (D10)",
    "termos de distribuição por componente de fonte real",
)
_UNVERIFIED_STATES = frozenset({"not_evaluated", "unsupported"})
_FACET_OF_CARRIER: dict[str, str] = {
    "attribute": "attribute",
    "property": "property",
    "quantity": "property",
    "property_or_quantity": "property",
    "material": "material",
    "classification": "classification",
}
"""Faceta IDS 1.0 que examina cada portador (conjuntos de propriedades e de quantidades
usam a faceta ``property``); faceta diferente não testa o portador afirmado."""


class ProfileReconciliationError(ValueError):
    """Reconciliação que não fecha com as bases, cita o inexistente ou presume capacidade."""


class ProfileProjectionManifest(CatalogModel):
    """Manifesto das projeções E4: bases, hashes LF e linhas de cada arquivo."""

    generator: str
    reconciliation_revision: str
    reconciliation_hash_scheme: str
    reconciliation_sha256: str
    candidates_content_sha256: str
    bases: dict[str, str]
    outputs: dict[str, dict[str, Any]]
    report: dict[str, Any]
    note: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory_sha256(inventory: AppendixBInventory) -> str:
    """Hash canônico da transcrição validada (sem as assertivas derivadas)."""
    dump = inventory.model_dump(mode="json")
    for record in dump["records"]:
        record.pop("assertion", None)
    return _sha256(canonical_json_bytes(dump))


_KEYED_COLLECTIONS: dict[str, str] = {
    "dispositions": "source_record_id",
    "correspondences": "id",
    "divergences": "id",
    "identities": "local_id",
    "family_map": "family_id",
    "decisions": "ref",
}
_ID_SETS: dict[str, tuple[str, ...]] = {
    "dispositions": ("candidate_ids", "decision_ids", "correspondence_ids"),
    "correspondences": ("a_record_ids", "b_record_ids", "compared_fields", "decision_ids"),
    "divergences": ("source_record_ids", "decision_ids"),
}


def canonical_reconciliation(reconciliation: ProfileReconciliation) -> dict[str, Any]:
    """Forma canônica da reconciliação para identidade (esquema ``ifcqc-daiane-recon-hash-2``).

    Nenhuma coleção da reconciliação tem ordem significativa: disposições,
    correspondências, divergências, identidades, mapa de famílias e decisões são
    ordenadas pela chave única; contagens históricas e fontes pendentes, pelo JSON
    canônico de cada item; listas de IDs e campos comparados dentro dos itens são
    conjuntos e também são ordenadas. A ordem da fonte vive na transcrição B
    (``locator.order``) e na matriz A, não aqui; textos não são normalizados.
    """
    data = reconciliation.model_dump(mode="json")
    for collection, key in _KEYED_COLLECTIONS.items():
        items = sorted(data[collection], key=lambda item: str(item[key]))
        for item in items:
            for field in _ID_SETS.get(collection, ()):
                item[field] = sorted(item[field])
        data[collection] = items
    for collection in ("historical_counts", "pending_sources"):
        data[collection] = sorted(data[collection], key=canonical_json_text)
    return data


def reconciliation_sha256(reconciliation: ProfileReconciliation) -> str:
    """Hash da forma canônica: permutar coleções não ordenadas não muda a identidade.

    O esquema anterior (r1, até 22/10/2026) usava a ordem do arquivo; a identidade
    histórica fica registrada na migração de revisões, não é recalculada aqui.
    """
    return _sha256(canonical_json_bytes(canonical_reconciliation(reconciliation)))


def binding_sha256(binding: IFCBinding) -> str:
    """Hash canônico de um binding, usado para amarrar evidência de capacidade."""
    return _sha256(canonical_json_bytes(binding.model_dump(mode="json")))


def policy_sha256(policy: EvidencePolicy) -> str:
    """Hash canônico de uma política de evidência citada por binding."""
    return _sha256(canonical_json_bytes(policy.model_dump(mode="json")))


def load_reconciliation(path: Path) -> ProfileReconciliation:
    """Lê a reconciliação com JSON estrito e modelo fechado."""
    try:
        return ProfileReconciliation.model_validate(
            parse_json_strict(path.read_bytes().decode("utf-8"))
        )
    except (UnicodeDecodeError, CanonicalJSONError, ValidationError) as exc:
        raise ProfileReconciliationError(f"reconciliação inválida em {path.name}: {exc}") from exc


def candidates_base(appendix_a: DaianeImport, appendix_b: AppendixBInventory) -> dict[str, str]:
    """Base exata que o arquivo de candidatos precisa declarar."""
    return {
        "matrix_revision": appendix_a.report.matrix_revision,
        "matrix_sha256": appendix_a.report.matrix_sha256,
        "appendix_b_revision": appendix_b.revision,
        "appendix_b_sha256": inventory_sha256(appendix_b),
    }


def load_candidates(
    path: Path, appendix_a: DaianeImport, appendix_b: AppendixBInventory
) -> CatalogContent:
    """Candidatos em rascunho sobre as bases A e B; base diferente é recusada."""
    transcription = SourceArtifact(
        id=transcription_artifact_id(appendix_b),
        title="Transcrição do Apêndice B (relatório IDS_Mestrado) — E4",
        artifact_type="research_matrix",
        terms="Artefato interno do projeto; transcreve fonte não redistribuída",
    )
    return load_draft(
        path,
        source_artifacts=(*appendix_a.artifacts, transcription),
        source_assertions=(*appendix_a.assertions, *appendix_b_assertions(appendix_b)),
        expected_base=candidates_base(appendix_a, appendix_b),
    )


def _fail(message: str) -> ProfileReconciliationError:
    return ProfileReconciliationError(message)


def _check_bases(
    reconciliation: ProfileReconciliation,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    candidates: CatalogContent,
) -> None:
    bases = reconciliation.bases
    actual = (
        appendix_a.report.matrix_revision,
        appendix_a.report.matrix_sha256,
        appendix_b.revision,
        inventory_sha256(appendix_b),
        appendix_b.source.pdf_sha256,
    )
    declared = (
        bases.matrix_revision,
        bases.matrix_sha256,
        bases.appendix_b_revision,
        bases.appendix_b_sha256,
        bases.pdf_sha256,
    )
    if actual != declared:
        raise _fail(f"base declarada {declared} difere das fontes lidas {actual}")
    if bases.candidates_content_sha256 != content_sha256(candidates):
        raise _fail("hash dos candidatos difere do declarado na reconciliação")


def _check_dispositions(
    reconciliation: ProfileReconciliation,
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    candidates: CatalogContent,
) -> dict[str, ProfileDisposition]:
    a_by_id = {a.id: a for a in appendix_a.assertions}
    b_by_id = {r.id: r for r in appendix_b.records}
    family_of_spec = {m.specification: m.family_id for m in reconciliation.family_map}
    counts = Counter(d.source_record_id for d in reconciliation.dispositions)
    repeated = sorted(k for k, v in counts.items() if v > 1)
    if repeated:
        raise _fail(f"registro com mais de uma disposição: {repeated[:5]}")
    unknown = sorted(set(counts) - set(a_by_id) - set(b_by_id))
    if unknown:
        raise _fail(f"disposição para registro inexistente: {unknown[:5]}")
    missing = sorted((set(a_by_id) | set(b_by_id)) - set(counts))
    if missing:
        raise _fail(f"registro sem disposição: {missing[:5]} (total {len(missing)})")
    entity_ids = {getattr(e, "id") for _, e in candidates.iter_entities()}  # noqa: B009
    cited: dict[str, set[str]] = {}
    for _, entity in candidates.iter_entities():
        for assertion_id in getattr(entity, "source_assertion_ids", ()):
            cited.setdefault(assertion_id, set()).add(getattr(entity, "id"))  # noqa: B009
    decisions = {d.id for d in candidates.reconciliation_decisions}
    correspondences = {c.id for c in reconciliation.correspondences}
    by_id: dict[str, ProfileDisposition] = {}
    for item in reconciliation.dispositions:
        rid = item.source_record_id
        if rid in a_by_id:
            source = a_by_id[rid]
            category: SourceCategory | None = source.category
            kind, status = "A", source.transcription_status
            family: str | None = str(source.locator.row_ref).split("-")[0]
        else:
            record = b_by_id[rid]
            category = record.category
            kind, status = "B", record.transcription_status
            family = family_of_spec.get(record.specification or "")
        if (item.source_kind, item.family_id) != (kind, family):
            raise _fail(
                f"{rid}: tipo/família {item.source_kind}/{item.family_id} ≠ {kind}/{family}"
            )
        if item.category != category:
            raise _fail(f"{rid}: categoria {item.category} difere da fonte ({category})")
        if item.axes.transcription != status:
            raise _fail(f"{rid}: eixo de transcrição {item.axes.transcription} ≠ fonte {status}")
        for candidate_id in item.candidate_ids:
            if candidate_id not in entity_ids:
                raise _fail(f"{rid}: candidato {candidate_id} não existe nos candidatos")
            if candidate_id not in cited.get(rid, set()):
                raise _fail(f"{rid}: candidato {candidate_id} não cita esta fonte")
        for decision_id in item.decision_ids:
            if decision_id not in decisions:
                raise _fail(f"{rid}: decisão {decision_id} não existe nos candidatos")
        for corr in item.correspondence_ids:
            if corr not in correspondences:
                raise _fail(f"{rid}: correspondência {corr} não existe")
        by_id[rid] = item
    return by_id


def _check_correspondences(
    reconciliation: ProfileReconciliation,
    dispositions: dict[str, ProfileDisposition],
    candidates: CatalogContent,
) -> None:
    decisions = {d.id for d in candidates.reconciliation_decisions}
    ids = Counter(c.id for c in reconciliation.correspondences)
    if any(v > 1 for v in ids.values()):
        raise _fail("ID de correspondência duplicado")
    for corr in reconciliation.correspondences:
        for record_id in (*corr.a_record_ids, *corr.b_record_ids):
            item = dispositions.get(record_id)
            if item is None:
                raise _fail(f"{corr.id}: registro {record_id} inexistente")
            if corr.id not in item.correspondence_ids:
                raise _fail(f"{corr.id}: disposição de {record_id} não a referencia")
            expected = "A" if record_id in corr.a_record_ids else "B"
            if item.source_kind != expected:
                raise _fail(f"{corr.id}: {record_id} no lado errado")
        for decision_id in corr.decision_ids:
            if decision_id not in decisions:
                raise _fail(f"{corr.id}: decisão {decision_id} não existe")


def _check_divergences(
    reconciliation: ProfileReconciliation,
    dispositions: dict[str, ProfileDisposition],
    appendix_a: DaianeImport,
) -> tuple[int, int]:
    matrix: Counter[str] = Counter()
    ids = Counter(d.id for d in reconciliation.divergences)
    if any(v > 1 for v in ids.values()):
        raise _fail("ID de divergência duplicado")
    for entry in reconciliation.divergences:
        for record_id in entry.source_record_ids:
            if record_id not in dispositions:
                raise _fail(f"{entry.id}: registro {record_id} inexistente")
        if entry.origin == "matrix_finding":
            if not entry.reported_before or len(entry.source_record_ids) != 1:
                raise _fail(f"{entry.id}: achado da matriz é já relatado e de um registro")
            matrix[entry.source_record_ids[0]] += 1
    expected = {k: v for k, v in appendix_a.divergence_counts.items() if v}
    if dict(matrix) != expected:
        raise _fail("ledger de divergências da matriz difere dos achados importados")
    return sum(expected.values()), len(expected)


def _check_identities(reconciliation: ProfileReconciliation, candidates: CatalogContent) -> None:
    proposals = {
        getattr(e, "id")  # noqa: B009
        for kind, e in candidates.iter_entities()
        if kind not in ("source_artifacts", "source_assertions")
    }
    registered = [i.local_id for i in reconciliation.identities]
    if len(registered) != len(set(registered)) or set(registered) != proposals:
        raise _fail(
            "registro de identidade não cobre exatamente os candidatos: faltam "
            f"{sorted(proposals - set(registered))[:3]}, "
            f"sobram {sorted(set(registered) - proposals)[:3]}"
        )


def ids_cells_for_binding(
    binding: IFCBinding, claim: CapabilityClaim, rule: ApplicabilityRule
) -> frozenset[str]:
    """Células da matriz IDS E3 (``m1-e3-ids-capability``) aplicáveis ao binding afirmado.

    Lê a matriz efetivamente carregada (``src.validation.ids_constraints``) e só admite
    o que ela cobre: aplicabilidade com uma classe, sem subtipos, sem condições extras e
    com no máximo um PredefinedType ordinário (não ``USERDEFINED``); IFC4, faceta
    ``property``, portador ``property`` (o backend exige
    ``IfcPropertySingleValue`` por elemento) e tipo textual ou escalar sem unidade.
    ``property_or_quantity`` (portador não reconciliado, ``ifc_type`` nulo) e medidas
    ficam fora: a função nunca amplia a matriz nem afirma suporte universal.
    """
    from src.validation.ids_constraints import (
        CAPABILITY_MANIFEST,
        SCALAR_DATATYPES,
        TEXT_DATATYPES,
    )

    applicability = cast(dict[str, Any], CAPABILITY_MANIFEST["applicability"])
    predefined = rule.predefined_types or ()
    if (
        len(rule.entity_classes) != 1
        or not _is_ifc4_object_subtype(rule.entity_classes[0])
        or rule.include_subtypes != applicability["include_subtypes"]
        or rule.conditions
        or len(predefined) > 1
        or "USERDEFINED" in predefined
    ):
        raise _fail(
            f"aplicabilidade {rule.id} de {binding.id} fora da célula E3 (uma classe, sem "
            "subtipos nem condições, PredefinedType ordinário único)"
        )
    requirements = cast(dict[str, Any], CAPABILITY_MANIFEST["requirements"])
    if claim.ifc_schema not in cast(list[str], CAPABILITY_MANIFEST["ifc_schemas"]):
        raise _fail(f"schema {claim.ifc_schema} fora da matriz IDS E3")
    if claim.facet not in requirements["facets"]:
        raise _fail(f"faceta {claim.facet} fora da matriz IDS E3")
    if binding.carrier_kind != "property":
        raise _fail(
            f"portador {binding.carrier_kind} de {binding.id} fora da matriz IDS E3 "
            f"({requirements['carrier']})"
        )
    data_type = (binding.ifc_type or "").upper()
    cell = "requirement:property"
    if data_type in TEXT_DATATYPES:
        return frozenset({f"{cell}:presence", f"{cell}:literal", f"{cell}:enumeration"})
    if data_type in SCALAR_DATATYPES:
        return frozenset({f"{cell}:presence"})
    raise _fail(f"tipo {binding.ifc_type} de {binding.id} fora da matriz IDS E3")


def _is_ifc4_object_subtype(name: str) -> bool:
    """Classe declarada no IFC4 e subtipo de ``IfcObject`` (célula ``IfcObject_subtype_only``)."""
    import ifcopenshell.ifcopenshell_wrapper as wrapper

    try:
        entity = wrapper.schema_by_name("IFC4").declaration_by_name(name).as_entity()
    except (RuntimeError, AttributeError):
        return False
    while entity is not None:
        if entity.name() == "IfcObject":
            return True
        entity = entity.supertype()
    return False


def _check_case_reuse(evidence: ProfileCapabilityEvidence) -> None:
    """O mesmo caso executado (nodeid) não sustenta dois bindings.

    Relatório bruto compartilhado por casos distintos é normal (um JUnit por execução) e
    não conta como reaproveitamento."""
    owners: dict[str, set[str]] = {}
    for case in evidence.cases:
        owners.setdefault(case.nodeid, set()).add(case.binding_id)
    reused = sorted(key for key, bindings in owners.items() if len(bindings) > 1)
    if reused:
        raise _fail(
            f"mesmo caso executado declarado para bindings diferentes: {reused[:3]}; "
            "cada binding precisa do seu próprio caso"
        )


def _bundle_anchor(trust: CapabilityTrust) -> None:
    """A âncora do bundle precisa ser o hash do bundle E3 que o próprio código carrega."""
    from src.suggestion_engine.catalog_operations import build_e3_operation_bundle

    if trust.operation_bundle_manifest_sha256 != build_e3_operation_bundle().manifest_sha256:
        raise _fail(
            "âncora do bundle de operações difere do bundle E3 carregado pelo código (ou ausente)"
        )


def _ids_manifest_anchor(trust: CapabilityTrust) -> None:
    """A matriz IDS carregada precisa ter o hash ancorado fora da evidência."""
    from src.operations.contracts import canonical_sha256
    from src.validation.ids_constraints import CAPABILITY_MANIFEST

    if trust.ids_capability_manifest_sha256 != canonical_sha256(CAPABILITY_MANIFEST):
        raise _fail("matriz IDS E3 carregada difere da âncora de confiança (ou âncora ausente)")


def verify_capabilities(
    evidence: ProfileCapabilityEvidence,
    candidates: CatalogContent,
    reconciliation: ProfileReconciliation,
    trust: CapabilityTrust,
) -> tuple[VerifiedCapability, ...]:
    """Confere cada afirmação contra caso executado, bytes fornecidos, binding e bases.

    Recusa nodeid fora da lista confiável, caso não executado, artefato ausente ou com
    hash diferente, implementação ou relatório sem âncora, binding ou base divergente,
    faceta incompatível com o portador, validação fora da célula IDS E3 que o caso
    exercitou, operação fora do bundle cujo hash foi ancorado fora da evidência e
    ``real_model`` sem insumo reconhecido. Fixture sintética resulta em
    ``verified_for_case``, nunca em ``real_model_verified``.
    """
    bindings = {b.id: b for b in candidates.bindings}
    policies = {p.id: p for p in candidates.evidence_policies}
    cases = {c.case_id: c for c in evidence.cases}
    rules = {r.id: r for r in candidates.applicability_rules}
    _check_case_reuse(evidence)
    approved = set(trust.approved_nodeids)
    handlers: set[str] | None = None
    if evidence.operation_manifest_json is not None:
        _bundle_anchor(trust)
        manifest = parse_json_strict(evidence.operation_manifest_json)
        if (
            trust.operation_bundle_manifest_sha256 is None
            or _sha256(canonical_json_bytes(manifest)) != trust.operation_bundle_manifest_sha256
        ):
            raise _fail(
                "manifesto de operações não corresponde ao bundle carregado (âncora de confiança)"
            )
        handlers = set(manifest.get("handlers", []))
    verified: list[VerifiedCapability] = []
    for claim in evidence.claims:
        binding = bindings.get(claim.binding_id)
        if binding is None or binding_sha256(binding) != claim.binding_sha256:
            raise _fail(f"binding {claim.binding_id} ausente ou com hash divergente")
        if binding.evidence_policy_id is not None:
            policy = policies[binding.evidence_policy_id]
            if claim.policy_sha256 != policy_sha256(policy):
                raise _fail(f"política de {claim.binding_id} com hash divergente")
        if (claim.base_a_sha256, claim.base_b_sha256) != (
            reconciliation.bases.matrix_sha256,
            reconciliation.bases.appendix_b_sha256,
        ):
            raise _fail(f"afirmação de {claim.binding_id} sobre outra base A/B")
        if (
            claim.carrier_kind != binding.carrier_kind
            or claim.ifc_schema not in binding.declared_schemas
        ):
            raise _fail(f"portador/schema da afirmação difere do binding {claim.binding_id}")
        if claim.facet != _FACET_OF_CARRIER[binding.carrier_kind]:
            raise _fail(
                f"faceta {claim.facet} incompatível com o portador {binding.carrier_kind} de "
                f"{claim.binding_id}"
            )
        case = cases.get(claim.case_id)
        if case is None:
            raise _fail(f"caso {claim.case_id} ausente do manifesto de evidência")
        if case.nodeid not in approved:
            raise _fail(f"nodeid {case.nodeid} não aprovado para evidência")
        if (case.binding_id, case.binding_sha256) != (claim.binding_id, claim.binding_sha256):
            raise _fail(
                f"caso {case.case_id} exercitou o binding {case.binding_id}, não "
                f"{claim.binding_id} (ou outra versão dele)"
            )
        if case.outcome != "passed" or case.exit_code != 0:
            raise _fail(
                f"caso {case.case_id} não executado com sucesso ({case.outcome}/{case.exit_code})"
            )
        for name, digest in (
            (case.test_file, case.test_file_sha256),
            (case.implementation_file, case.implementation_sha256),
            (case.raw_report_file, case.raw_report_sha256),
            (case.inputs_file, case.inputs_sha256),
        ):
            data = evidence.artifacts.get(name)
            if data is None:
                raise _fail(f"artefato {name} ausente: evidência não fornecida explicitamente")
            if _sha256(data) != digest:
                raise _fail(f"hash de {name} difere do manifesto do caso")
        if case.implementation_sha256 not in trust.approved_implementation_sha256s:
            raise _fail(
                f"implementação do caso {case.case_id} sem âncora de confiança: hash "
                "autodeclarado não comprova o código executado"
            )
        if case.raw_report_sha256 not in trust.executed_report_sha256s:
            raise _fail(
                f"relatório bruto do caso {case.case_id} sem âncora de execução fora da evidência"
            )
        if claim.axis == "validation":
            _ids_manifest_anchor(trust)
            cells = ids_cells_for_binding(binding, claim, rules[binding.applicability_rule_id])
            if claim.capability_cell not in cells or case.capability_cell != claim.capability_cell:
                raise _fail(
                    f"célula {claim.capability_cell} não é a célula IDS E3 exercitada pelo caso "
                    f"{case.case_id} ({case.capability_cell}) entre as aplicáveis {sorted(cells)}"
                )
        if claim.axis == "enrichment":
            if (
                binding.carrier_kind != "property"
                or binding.ifc_type is None
                or binding.carrier_status != "approved"
            ):
                raise _fail(
                    f"portador {binding.carrier_kind}/{binding.ifc_type} de {binding.id} fora do "
                    "alcance das operações E3 (IfcPropertySingleValue com tipo reconciliado)"
                )
            key = f"{claim.operation_id}@{claim.operation_version}"
            if handlers is None:
                raise _fail("enriquecimento exige o manifesto do bundle de operações carregado")
            if key not in handlers:
                raise _fail(f"operação {key} não está no bundle carregado")
        if (
            case.classifier == "real_model"
            and case.inputs_sha256 not in trust.real_model_input_sha256s
        ):
            raise _fail(
                f"caso {case.case_id} declara real_model sem insumo de modelo real reconhecido"
            )
        verified.append(
            VerifiedCapability(
                binding_id=claim.binding_id,
                axis=claim.axis,
                state="real_model_verified"
                if case.classifier == "real_model"
                else "verified_for_case",
                case_id=case.case_id,
                nodeid=case.nodeid,
                classifier=case.classifier,
                capability_cell=claim.capability_cell,
            )
        )
    return tuple(verified)


def _check_capability_axes(
    dispositions: dict[str, ProfileDisposition], verified: tuple[VerifiedCapability, ...]
) -> None:
    for record_id, item in dispositions.items():
        for axis in ("validation", "enrichment"):
            state = getattr(item.axes, axis)
            if state in _UNVERIFIED_STATES:
                continue
            ok = [
                v
                for v in verified
                if v.axis == axis and v.binding_id in item.candidate_ids and v.state == state
            ]
            if not ok:
                raise _fail(
                    f"{record_id}: eixo {axis}={state} sem capacidade conferida para o caso"
                )


def build_daiane_profile(
    appendix_a: DaianeImport,
    appendix_b: AppendixBInventory,
    reconciliation: ProfileReconciliation,
    candidates: CatalogContent,
    *,
    capabilities: ProfileCapabilityEvidence,
    trust: CapabilityTrust | None = None,
) -> DaianeProfileInventory:
    """Valida fechamento, referências, identidades e capacidades; não cria decisões.

    ``trust`` traz as âncoras de confiança separadas da evidência; sem ela, nenhuma
    afirmação de capacidade é aceita.
    """
    _check_bases(reconciliation, appendix_a, appendix_b, candidates)
    dispositions = _check_dispositions(reconciliation, appendix_a, appendix_b, candidates)
    _check_correspondences(reconciliation, dispositions, candidates)
    items, records = _check_divergences(reconciliation, dispositions, appendix_a)
    _check_identities(reconciliation, candidates)
    lifecycles = {
        getattr(e, "lifecycle")  # noqa: B009
        for _, e in candidates.iter_entities()
        if hasattr(e, "lifecycle")
    }
    if lifecycles - {"draft"}:
        raise _fail(f"candidato fora de rascunho: {sorted(lifecycles)}")
    verified = verify_capabilities(
        capabilities, candidates, reconciliation, trust or CapabilityTrust()
    )
    _check_capability_axes(dispositions, verified)
    return DaianeProfileInventory(
        reconciliation=ProfileReconciliation.model_validate(
            canonical_reconciliation(reconciliation)
        ),
        reconciliation_sha256=reconciliation_sha256(reconciliation),
        candidates=candidates,
        a_record_ids=tuple(a.id for a in appendix_a.assertions),
        a_categories={a.id: a.category for a in appendix_a.assertions},
        b_inventory=appendix_b,
        matrix_divergence_items=items,
        matrix_divergence_records=records,
        verified_capabilities=verified,
    )


def summarize_daiane_profile(profile: DaianeProfileInventory) -> ProfileReport:
    """Relatório com inventário, cadastro e capacidades em estados separados."""
    recon = profile.reconciliation
    a_alpha = sum(1 for c in profile.a_categories.values() if c in ALPHANUMERIC_CATEGORIES)
    by_destination: dict[str, Counter[str]] = {"A": Counter(), "B": Counter()}
    by_family: dict[str, Counter[str]] = {}
    axes: dict[str, Counter[str]] = {
        a: Counter() for a in ("transcription", "catalog", "validation", "enrichment")
    }
    pending: Counter[str] = Counter()
    for item in recon.dispositions:
        by_destination[item.source_kind][item.destination] += 1
        by_family.setdefault(item.family_id or "documento", Counter())[item.destination] += 1
        for axis in axes:
            axes[axis][getattr(item.axes, axis)] += 1
        if item.destination == "pending":
            pending[item.reason_code] += 1
    b_records = profile.b_inventory.records
    accounted = {d.source_record_id for d in recon.dispositions} == set(profile.a_record_ids) | {
        r.id for r in b_records
    }
    divergences = Counter(f"{d.origin}" for d in recon.divergences)
    return ProfileReport(
        reconciliation_revision=recon.revision,
        reconciliation_sha256=profile.reconciliation_sha256,
        candidates_content_sha256=recon.bases.candidates_content_sha256,
        a_total=len(profile.a_record_ids),
        a_alphanumeric=a_alpha,
        a_auxiliary=len(profile.a_record_ids) - a_alpha,
        b_total=len(b_records),
        b_by_role=dict(sorted(Counter(r.role for r in b_records).items())),
        inventory_accounted_for=accounted,
        appendix_b_transcription_complete=len(profile.b_inventory.specifications) == 10
        and all(
            r.transcription_state != "redacted" or r.role == "specification_metadata"
            for r in b_records
        ),
        appendix_b_research_checked=all(
            r.transcription_status in ("checked_by_research", "checked_by_curator")
            for r in b_records
        ),
        appendix_b_check_level=appendix_b_check_level(profile.b_inventory),
        domain_review_complete=False,
        original_instrument_equivalence_verified=False,
        profile_operational=False,
        by_destination={k: dict(sorted(v.items())) for k, v in by_destination.items()},
        by_family_destination={k: dict(sorted(v.items())) for k, v in sorted(by_family.items())},
        by_axis={k: dict(sorted(v.items())) for k, v in axes.items()},
        pending_by_reason=dict(sorted(pending.items())),
        correspondences_by_relation=dict(
            sorted(Counter(c.relation for c in recon.correspondences).items())
        ),
        correspondences_by_review_state=dict(
            sorted(Counter(c.review_state for c in recon.correspondences).items())
        ),
        divergences=dict(sorted(divergences.items())),
        matrix_divergence_items=profile.matrix_divergence_items,
        matrix_divergence_records=profile.matrix_divergence_records,
        historical_counts=recon.historical_counts,
        verified_capabilities=profile.verified_capabilities,
        pending_sources=recon.pending_sources,
        human_gates=HUMAN_GATES,
    )


# --- Projeções -----------------------------------------------------------------------------


def _csv_bytes(fieldnames: Sequence[str], rows: Sequence[dict[str, str]]) -> bytes:
    """CSV UTF-8/LF com cabeçalho explícito: lista vazia gera só o cabeçalho."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fieldnames), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _ids(values: Sequence[str]) -> str:
    """Conjunto de IDs em ordem canônica (a ordem na reconciliação não é significativa)."""
    return "|".join(sorted(values))


def _literal(profile: DaianeProfileInventory, record_id: str) -> tuple[str, str, str, str]:
    """Literal, especificação, página impressa e página PDF de um registro B."""
    record = profile.b_inventory.record(record_id)
    return (
        record.text_literal,
        record.specification or "",
        str(record.locator.printed_pages[0]),
        str(record.locator.pdf_pages[0]),
    )


def coverage_rows(
    profile: DaianeProfileInventory, a_literals: dict[str, tuple[str, str, str]]
) -> list[dict[str, str]]:
    """Uma linha por registro A ou B, ordenada por ID, com eixos separados."""
    rows = []
    for item in sorted(profile.reconciliation.dispositions, key=lambda d: d.source_record_id):
        if item.source_kind == "A":
            literal, printed, pdf = a_literals[item.source_record_id]
            spec = ""
        else:
            literal, spec, printed, pdf = _literal(profile, item.source_record_id)
        rows.append(
            {
                "source_kind": item.source_kind,
                "source_record_id": item.source_record_id,
                "family_id": item.family_id or "",
                "specification": spec,
                "printed_page": printed,
                "pdf_page": pdf,
                "category": item.category or "",
                "literal": literal,
                "destination": item.destination,
                "reason_code": item.reason_code,
                "reason": item.reason,
                "candidate_ids": _ids(item.candidate_ids),
                "decision_ids": _ids(item.decision_ids),
                "correspondence_ids": _ids(item.correspondence_ids),
                "transcription": item.axes.transcription,
                "catalog": item.axes.catalog,
                "validation": item.axes.validation,
                "enrichment": item.axes.enrichment,
            }
        )
    return rows


def _set_id(files: dict[str, bytes]) -> str:
    """Identificador de um conjunto de projeções: hash da listagem nome→sha256."""
    listing = {name: _sha256(data) for name, data in sorted(files.items())}
    return _sha256(canonical_json_bytes(listing))[:16]


def _archive_previous(out_dir: Path, existing: dict[str, bytes]) -> Path:
    """Copia a revisão anterior para ``revisoes/<id>`` antes de qualquer sobrescrita.

    Destino preexistente só é aceito se contiver exatamente os mesmos bytes; a cópia é
    gravada numa pasta temporária irmã, conferida e só então renomeada.
    """
    archive = out_dir / REVISIONS_DIR / _set_id(existing)
    record = canonical_json_bytes(
        {
            "note": "Revisão anterior das projeções E4, preservada antes de gravar nova revisão.",
            "files": {
                name: {"bytes": len(data), "sha256": _sha256(data)}
                for name, data in sorted(existing.items())
            },
        }
    )
    expected = {**existing, ARCHIVE_RECORD_FILE: record}
    if archive.exists():
        present = {p.name: p.read_bytes() for p in archive.iterdir() if p.is_file()}
        if present != expected:
            raise _fail(f"destino de revisão {archive} já existe com outro conteúdo")
        return archive
    staging = archive.with_name(f".{archive.name}.tmp")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for name, data in expected.items():
        (staging / name).write_bytes(data)
    if {p.name: p.read_bytes() for p in staging.iterdir()} != expected:
        shutil.rmtree(staging)
        raise _fail(f"cópia da revisão anterior em {staging} não confere")
    os.replace(staging, archive)
    return archive


def _write_outputs(out_dir: Path, outputs: dict[str, bytes], existing: dict[str, bytes]) -> None:
    """Grava cada arquivo por troca atômica; falha restaura os bytes anteriores."""
    written: list[str] = []
    try:
        for name, data in outputs.items():
            temp = out_dir / f".{name}.tmp"
            temp.write_bytes(data)
            os.replace(temp, out_dir / name)
            written.append(name)
    except OSError as exc:
        for name in written:
            if name in existing:
                (out_dir / name).write_bytes(existing[name])
            else:
                (out_dir / name).unlink(missing_ok=True)
        for name in outputs:
            (out_dir / f".{name}.tmp").unlink(missing_ok=True)
        raise _fail(
            f"gravação parcial revertida ({exc}); revisão anterior intacta no destino"
        ) from exc


def write_profile_projections(
    profile: DaianeProfileInventory,
    report: ProfileReport,
    out_dir: Path,
    *,
    a_literals: dict[str, tuple[str, str, str]],
    allow_new_revision: bool = False,
) -> ProfileProjectionManifest:
    """Gera CSV UTF-8/LF e manifesto determinísticos; recusa sobrescrita divergente.

    Tudo é calculado antes de tocar o disco. Sem ``allow_new_revision``, conjunto
    existente diferente é recusado sem criar nada. Com a opção, o conjunto anterior é
    copiado para ``revisoes/<id>`` (com ``arquivamento.json``) e só então substituído;
    falha na gravação restaura os arquivos anteriores. Regeneração idêntica não cria
    revisão.
    """
    recon = profile.reconciliation
    coverage = coverage_rows(profile, a_literals)
    divergences = [
        {
            "divergence_id": d.id,
            "origin": d.origin,
            "reported_before": "sim" if d.reported_before else "nao",
            "source_record_ids": _ids(d.source_record_ids),
            "text": d.text,
            "status": d.status,
            "decision_ids": _ids(d.decision_ids),
        }
        for d in sorted(recon.divergences, key=lambda d: d.id)
    ]
    correspondences = [
        {
            "correspondence_id": c.id,
            "relation": c.relation,
            "review_state": c.review_state,
            "a_record_ids": _ids(c.a_record_ids),
            "b_record_ids": _ids(c.b_record_ids),
            "compared_fields": _ids(c.compared_fields),
            "justification": c.justification,
            "decision_ids": _ids(c.decision_ids),
        }
        for c in sorted(recon.correspondences, key=lambda c: c.id)
    ]
    outputs = {
        COVERAGE_FILE: _csv_bytes(COVERAGE_FIELDS, coverage),
        DIVERGENCE_FILE: _csv_bytes(DIVERGENCE_FIELDS, divergences),
        CORRESPONDENCE_FILE: _csv_bytes(CORRESPONDENCE_FIELDS, correspondences),
    }
    rows = {
        COVERAGE_FILE: len(coverage),
        DIVERGENCE_FILE: len(divergences),
        CORRESPONDENCE_FILE: len(correspondences),
    }
    manifest = ProfileProjectionManifest(
        generator="src.domain_catalog.profile",
        reconciliation_revision=recon.revision,
        reconciliation_hash_scheme=RECONCILIATION_HASH_SCHEME,
        reconciliation_sha256=profile.reconciliation_sha256,
        candidates_content_sha256=recon.bases.candidates_content_sha256,
        bases=recon.bases.model_dump(mode="json"),
        outputs={
            name: {"sha256": _sha256(data), "rows": rows[name]} for name, data in outputs.items()
        },
        report=report.model_dump(mode="json"),
        note=(
            "Projeções derivadas; não editar à mão. Inventário coberto não significa perfil "
            "aprovado nem operacional. Regenerar com python -m src.domain_catalog.profile."
        ),
    )
    outputs[MANIFEST_FILE] = canonical_json_bytes(manifest.model_dump(mode="json"))
    existing = {
        name: (out_dir / name).read_bytes() for name in outputs if (out_dir / name).is_file()
    }
    divergent = sorted(name for name, data in existing.items() if data != outputs[name])
    if divergent and not allow_new_revision:
        raise _fail(
            f"projeções existentes diferem ({divergent}); "
            "use --new-revision para gravar outra revisão"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    if divergent:
        archive = _archive_previous(out_dir, existing)
        logger.info("Revisão anterior das projeções preservada em {}", archive)
    _write_outputs(out_dir, outputs, existing)
    return manifest


def a_literals(appendix_a: DaianeImport) -> dict[str, tuple[str, str, str]]:
    """Literal, página impressa e página PDF de cada registro A."""
    return {
        a.id: (a.target_literal, str(a.locator.printed_page or ""), str(a.locator.pdf_page or ""))
        for a in appendix_a.assertions
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Valida a reconciliação E4 e regenera as projeções em ``docs/catalogo/e4``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--appendix-b", type=Path, default=APPENDIX_B_PATH)
    parser.add_argument("--reconciliation", type=Path, default=RECONCILIATION_PATH)
    parser.add_argument("--candidates", type=Path, default=CANDIDATES_PATH)
    parser.add_argument("--out", type=Path, default=PROJECTIONS_DIR)
    parser.add_argument("--pdf-sha256", default=PDF_SHA256)
    parser.add_argument("--new-revision", action="store_true")
    args = parser.parse_args(argv)
    appendix_a = import_appendix_a(load_matrix(args.matrix))
    appendix_b = load_appendix_b(args.appendix_b, expected_pdf_sha256=args.pdf_sha256)
    reconciliation = load_reconciliation(args.reconciliation)
    candidates = load_candidates(args.candidates, appendix_a, appendix_b)
    profile = build_daiane_profile(
        appendix_a, appendix_b, reconciliation, candidates, capabilities=ProfileCapabilityEvidence()
    )
    report = summarize_daiane_profile(profile)
    manifest = write_profile_projections(
        profile,
        report,
        args.out,
        a_literals=a_literals(appendix_a),
        allow_new_revision=args.new_revision,
    )
    logger.info(
        "Projeções E4 em {}: {}", args.out, json.dumps(manifest.outputs, ensure_ascii=False)
    )
    return 0


__all__ = [
    "CANDIDATES_PATH",
    "RECONCILIATION_PATH",
    "ProfileReconciliationError",
    "binding_sha256",
    "build_daiane_profile",
    "canonical_json_text",
    "load_candidates",
    "load_reconciliation",
    "policy_sha256",
    "summarize_daiane_profile",
    "write_profile_projections",
]


if __name__ == "__main__":
    raise SystemExit(main())
