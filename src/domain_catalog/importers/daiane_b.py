"""Carregador estrito da transcrição do Apêndice B de Daiane (2025) (E4, M1-04).

A transcrição (``data/catalogs/sources/daiane-2025/appendix-b-v1.json``) foi feita
por extração assistida das páginas PDF 172–186, conferência visual e segunda
conferência independente, registradas no próprio arquivo. Este módulo não abre o PDF
nem a rede: confere a identidade declarada do PDF contra o hash esperado, o inventário
de páginas e especificações, a ordem e a localização de cada registro, e projeta
``SourceAssertion`` somente para registros cuja categoria foi declarada. Registros
sem categoria (propriedade sem portador determinado, metadado, texto não
classificável) continuam no inventário com o motivo; nada é descartado.
"""

import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from src.config import BASE_DIR
from src.domain_catalog.canonical import CanonicalJSONError, canonical_json_text, parse_json_strict
from src.domain_catalog.importers.daiane import DISSERTATION_ID
from src.domain_catalog.models import SourceAssertion, SourceLocator
from src.domain_catalog.profile_models import (
    PASSING_OUTCOMES,
    AppendixBInventory,
    AppendixBRecord,
    AppendixBTotals,
)

APPENDIX_B_PATH = BASE_DIR / "data" / "catalogs" / "sources" / "daiane-2025" / "appendix-b-v1.json"
EXPECTED_SPECIFICATIONS: tuple[str, ...] = tuple(f"E{n:02d}" for n in range(1, 11))
APPENDIX_B_PDF_PAGES: tuple[int, int] = (172, 186)
_DOMAIN_KEYS: tuple[str, ...] = (
    "modality_literal",
    "operator_literal",
    "value_literal",
    "qualifier_operator_literal",
    "qualifier_literal",
)


_RESEARCH_CHECKS: frozenset[str] = frozenset({"visual_check", "independent_second_check"})
_DATED_REVISION = re.compile(r"^(\d{4}-\d{2}-\d{2})-r(\d+)$")
CheckLevel = Literal["not_checked", "assistant_only", "includes_human", "curator"]


class AppendixBFormatError(ValueError):
    """Transcrição ilegível, de outro PDF, incompleta ou com registro incoerente."""


def transcription_artifact_id(inventory: AppendixBInventory) -> str:
    """ID do artefato de transcrição desta revisão (distinto da dissertação)."""
    return f"e4:apendice-b-transcricao-{inventory.revision}"


def _projection(record: AppendixBRecord, inventory: AppendixBInventory) -> SourceAssertion | None:
    """``SourceAssertion`` com os literais impressos, ou ``None`` sem categoria declarada."""
    if record.category is None or record.continuation_of is not None:
        return None
    structured = record.structured
    target = (
        structured.get("entity_literal")
        or structured.get("attribute_name_literal")
        or structured.get("system_literal")
        or structured.get("system_and_code_literal")
        or record.facet_literal
    )
    if target is None:
        raise AppendixBFormatError(
            f"{record.id}: categoria {record.category} declarada sem alvo impresso "
            "(entidade, atributo, sistema ou faceta); registro precisa de not_projectable_reason"
        )
    identifier = structured.get("entity_literal") or structured.get("attribute_name_literal")
    domain = {key: structured[key] for key in _DOMAIN_KEYS if key in structured}
    notes = list(record.doubts)
    instructions = structured.get("instructions_literal")
    if isinstance(instructions, str):
        notes.append(f"Instruções: {instructions}")
    try:
        return SourceAssertion(
            id=record.id,
            source_artifact_id=inventory.source.artifact_id,
            transcription_artifact_id=transcription_artifact_id(inventory),
            locator=SourceLocator(
                printed_page=record.locator.printed_pages[0],
                pdf_page=record.locator.pdf_pages[0],
                table=f"Apêndice B {record.specification}",
                row_ref=record.id.split(":", 1)[1],
            ),
            category=record.category,
            target_literal=str(target),
            target_identifier_literal=None if identifier is None else str(identifier),
            domain_literal_json=canonical_json_text(domain) if domain else None,
            notes=tuple(notes),
            transcription_status=record.transcription_status,
        )
    except ValidationError as exc:
        raise AppendixBFormatError(f"{record.id}: assertiva não representável: {exc}") from exc


def _reviewer_key(label: str) -> str:
    """Revisor declarado normalizado (NFC, sem caixa, espaços colapsados)."""
    return " ".join(unicodedata.normalize("NFC", label).casefold().split())


def _check_reviews(inventory: AppendixBInventory) -> None:
    """``checked_by_research`` exige conferência visual e segunda conferência aprovadas,
    declaradas por revisores distintos; mesmo assim é conferência de pesquisa, não de
    curador, e o nível efetivo fica em ``appendix_b_check_level``."""
    approved = [
        review
        for review in inventory.reviews
        if review.outcome in PASSING_OUTCOMES and review.pdf_pages == APPENDIX_B_PDF_PAGES
    ]
    passed = {review.kind for review in approved}
    visual = {_reviewer_key(r.reviewer_label) for r in approved if r.kind == "visual_check"}
    second = {
        _reviewer_key(r.reviewer_label) for r in approved if r.kind == "independent_second_check"
    }
    if visual and second and not (second - visual):
        passed.discard("independent_second_check")
        if any(r.transcription_status == "checked_by_research" for r in inventory.records):
            raise AppendixBFormatError(
                "segunda conferência declarada pelo mesmo revisor da conferência visual: "
                "não sustenta checked_by_research"
            )
    curator = {
        review.kind
        for review in inventory.reviews
        if review.kind == "curator_check" and review.reviewer_kind == "human"
    }
    for record in inventory.records:
        if (
            record.transcription_status == "checked_by_research"
            and not {
                "visual_check",
                "independent_second_check",
            }
            <= passed
        ):
            raise AppendixBFormatError(
                f"{record.id}: checked_by_research sem conferência visual e segunda conferência "
                "aprovadas sobre todo o Apêndice B"
            )
        if record.transcription_status == "checked_by_curator" and not curator & passed:
            raise AppendixBFormatError(
                f"{record.id}: checked_by_curator sem curator_check humano aprovado"
            )


def _revision_key(revision: str) -> tuple[str, int] | None:
    """Ordem de revisões ``AAAA-MM-DD-rN``; ``None`` para outra forma (só igualdade)."""
    match = _DATED_REVISION.fullmatch(revision)
    return None if match is None else (match.group(1), int(match.group(2)))


def _check_changes(inventory: AppendixBInventory, ids: set[str]) -> None:
    """Alterações citam registros existentes, sem repetição, e revisão não posterior."""
    current = _revision_key(inventory.revision)
    for change in inventory.changes:
        repeated = sorted(k for k, v in Counter(change.record_ids).items() if v > 1)
        if repeated:
            raise AppendixBFormatError(f"alteração {change.revision} com ID repetido {repeated}")
        unknown = sorted(set(change.record_ids) - ids)
        if unknown:
            raise AppendixBFormatError(
                f"alteração {change.revision} cita registro inexistente {unknown}"
            )
        key = _revision_key(change.revision)
        if change.revision != inventory.revision and (
            key is None or current is None or key > current
        ):
            raise AppendixBFormatError(
                f"alteração da revisão {change.revision} não é anterior nem igual à revisão "
                f"{inventory.revision} do inventário"
            )


def _check_specification_pages(inventory: AppendixBInventory) -> None:
    """Páginas declaradas de cada especificação = páginas ocupadas pelos seus registros."""
    pages: dict[str, set[int]] = {}
    for record in inventory.records:
        if record.specification is not None:
            pages.setdefault(record.specification, set()).update(record.locator.pdf_pages)
    for spec in inventory.specifications:
        declared = list(spec.pdf_pages)
        if declared != sorted(pages.get(spec.code, set())):
            raise AppendixBFormatError(
                f"especificação {spec.code} declara páginas {declared}, registros ocupam "
                f"{sorted(pages.get(spec.code, set()))}"
            )


def _check_inventory(inventory: AppendixBInventory) -> None:
    """Páginas, especificações, IDs, ordem e continuações fecham sem lacunas."""
    first, last = inventory.source.pdf_pages
    if (first, last) != APPENDIX_B_PDF_PAGES:
        raise AppendixBFormatError(f"intervalo {first}–{last} não é o do Apêndice B")
    page_numbers = [page.pdf_page for page in inventory.pages]
    if page_numbers != list(range(first, last + 1)):
        raise AppendixBFormatError(
            f"inventário de páginas incompleto ou fora de ordem: {page_numbers}"
        )
    for page in inventory.pages:
        if page.printed_page is not None and page.printed_page != page.pdf_page - 1:
            raise AppendixBFormatError(
                f"página PDF {page.pdf_page} com impressa {page.printed_page}"
            )
    codes = [spec.code for spec in inventory.specifications]
    missing = [code for code in EXPECTED_SPECIFICATIONS if code not in codes]
    if missing or codes != list(EXPECTED_SPECIFICATIONS):
        raise AppendixBFormatError(f"especificações ausentes ou fora de ordem: {missing or codes}")
    ids = Counter(record.id for record in inventory.records)
    duplicated = sorted(record_id for record_id, count in ids.items() if count > 1)
    if duplicated:
        raise AppendixBFormatError(f"ID de registro duplicado: {duplicated}")
    listed: dict[str, list[int]] = {}
    for page in inventory.pages:
        for record_id in page.record_ids:
            listed.setdefault(record_id, []).append(page.pdf_page)
    unknown = sorted(set(listed) - set(ids))
    if unknown:
        raise AppendixBFormatError(f"inventário da página cita registro inexistente: {unknown}")
    by_id = {record.id: record for record in inventory.records}
    last_order: dict[str, int] = {}
    for record in inventory.records:
        pages = record.locator.pdf_pages
        if pages[0] < first or pages[-1] > last:
            raise AppendixBFormatError(
                f"{record.id}: página {pages} fora do Apêndice B ({first}–{last})"
            )
        if [p - 1 for p in pages] != list(record.locator.printed_pages):
            raise AppendixBFormatError(f"{record.id}: páginas impressas incoerentes com o PDF")
        if listed.get(record.id) != list(pages):
            raise AppendixBFormatError(
                f"{record.id}: páginas {list(pages)} diferem do inventário da página "
                f"{listed.get(record.id)}"
            )
        scope = record.specification or "DOC"
        if record.locator.order <= last_order.get(scope, 0):
            raise AppendixBFormatError(f"{record.id}: ordem da fonte não crescente")
        last_order[scope] = record.locator.order
        if record.continuation_of is not None:
            previous = by_id.get(record.continuation_of)
            if (
                previous is None
                or previous.specification != record.specification
                or previous.role != record.role
                or previous.locator.order >= record.locator.order
                or pages[0]
                not in (previous.locator.pdf_pages[-1], previous.locator.pdf_pages[-1] + 1)
            ):
                raise AppendixBFormatError(
                    f"{record.id}: continuação de {record.continuation_of} incoerente "
                    "(mesma especificação, papel, ordem e página seguinte)"
                )
    _check_changes(inventory, set(ids))
    _check_specification_pages(inventory)


def _read(path: Path) -> Any:
    try:
        return parse_json_strict(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, CanonicalJSONError) as exc:
        raise AppendixBFormatError(f"transcrição ilegível em {path.name}: {exc}") from exc


def load_appendix_b(path: Path, *, expected_pdf_sha256: str) -> AppendixBInventory:
    """Lê e valida a transcrição; projeta assertivas só para registros com categoria.

    ``expected_pdf_sha256`` é o hash do PDF efetivamente conferido por quem chama; a
    transcrição de outro PDF é recusada, mesmo bem formada.
    """
    raw = _read(path)
    try:
        inventory = AppendixBInventory.model_validate(raw)
    except ValidationError as exc:
        raise AppendixBFormatError(f"transcrição inválida em {path.name}: {exc}") from exc
    if inventory.source.pdf_sha256 != expected_pdf_sha256:
        raise AppendixBFormatError(
            f"pdf_sha256 declarado {inventory.source.pdf_sha256} difere do esperado "
            f"{expected_pdf_sha256}"
        )
    _check_inventory(inventory)
    _check_reviews(inventory)
    projected = tuple(
        record.model_validate({**record.model_dump(), "assertion": _projection(record, inventory)})
        for record in inventory.records
    )
    return inventory.model_validate({**inventory.model_dump(), "records": projected})


def appendix_b_totals(inventory: AppendixBInventory) -> AppendixBTotals:
    """Totais por especificação, papel, faceta e modalidade, sem contar continuações."""
    primary = list(inventory.iter_primary())
    by_spec_role: dict[str, Counter[str]] = {}
    for record in primary:
        by_spec_role.setdefault(record.specification or "DOC", Counter())[record.role] += 1
    modality: Counter[str] = Counter()
    for record in primary:
        if record.role == "requirement" or record.role == "unclassified":
            printed = record.structured.get("modality_literal")
            modality["nao_impressa" if printed is None else str(printed)] += 1
    return AppendixBTotals(
        records=len(inventory.records),
        continuations=len(inventory.records) - len(primary),
        by_role=dict(sorted(Counter(record.role for record in primary).items())),
        by_specification_role={
            spec: dict(sorted(counter.items())) for spec, counter in sorted(by_spec_role.items())
        },
        by_facet=dict(
            sorted(Counter(record.facet_literal or "sem_faceta" for record in primary).items())
        ),
        by_modality=dict(sorted(modality.items())),
        projected_assertions=sum(1 for record in inventory.records if record.assertion),
        not_projected=sum(1 for record in inventory.records if record.assertion is None),
        with_doubt=sum(1 for record in primary if record.transcription_state != "transcribed"),
        redacted=sum(1 for record in primary if record.transcription_state == "redacted"),
    )


def appendix_b_check_level(inventory: AppendixBInventory) -> CheckLevel:
    """Nível efetivo da conferência da transcrição, explícito e separado do status.

    ``curator`` só com ``checked_by_curator`` em todos os registros; ``assistant_only``
    quando todas as conferências aprovadas que sustentam ``checked_by_research`` foram
    declaradas por assistentes; ``includes_human`` se alguma foi declarada por pessoa;
    ``not_checked`` se algum registro não tem conferência. Declaração local, não
    autenticação de quem conferiu.
    """
    statuses = {record.transcription_status for record in inventory.records}
    if statuses == {"checked_by_curator"}:
        return "curator"
    if not statuses <= {"checked_by_research", "checked_by_curator"}:
        return "not_checked"
    kinds = {
        review.reviewer_kind
        for review in inventory.reviews
        if review.kind in _RESEARCH_CHECKS
        and review.outcome in PASSING_OUTCOMES
        and review.pdf_pages == APPENDIX_B_PDF_PAGES
    }
    return "includes_human" if "human" in kinds else "assistant_only"


def appendix_b_assertions(inventory: AppendixBInventory) -> tuple[SourceAssertion, ...]:
    """Assertivas projetadas, na ordem da fonte."""
    return tuple(record.assertion for record in inventory.records if record.assertion is not None)


__all__ = [
    "APPENDIX_B_PATH",
    "DISSERTATION_ID",
    "AppendixBFormatError",
    "appendix_b_assertions",
    "appendix_b_totals",
    "load_appendix_b",
    "transcription_artifact_id",
]
