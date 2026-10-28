"""Listagem somente leitura de elementos de uma revisão IFC."""

import ifcopenshell

from src.review_api.legacy_adapter import global_id_index
from src.review_api.schemas import ElementRecord, ElementRef

# PROVISÓRIO: aberturas (IfcOpeningElement) não são alvo de revisão nesta fatia.
_EXCLUDED_CLASSES = ("IfcOpeningElement",)


def _review_candidates(ifc_file: ifcopenshell.file) -> list[ifcopenshell.entity_instance]:
    """Retorna IfcElement e IfcSpace, sem aberturas, ordenados por express_id."""
    found: dict[int, ifcopenshell.entity_instance] = {}
    for ifc_class in ("IfcElement", "IfcSpace"):
        for entity in ifc_file.by_type(ifc_class):
            if not any(entity.is_a(excluded) for excluded in _EXCLUDED_CLASSES):
                found[entity.id()] = entity
    return [found[k] for k in sorted(found)]


def list_elements(
    ifc_file: ifcopenshell.file, model_id: str, ifc_revision_id: str
) -> list[ElementRecord]:
    """Produz ElementRecords com identidade composta e estado do GlobalId.

    Elementos sem representação geométrica continuam na lista com
    ``has_geometry=False``.
    """
    index = global_id_index(ifc_file)
    records: list[ElementRecord] = []
    for entity in _review_candidates(ifc_file):
        guid = getattr(entity, "GlobalId", None) or None
        if guid is None:
            state = "missing"
        elif len(index.get(guid, [])) > 1:
            state = "duplicated_in_file"
        else:
            state = "unique"
        records.append(
            ElementRecord(
                ref=ElementRef(
                    model_id=model_id,
                    ifc_revision_id=ifc_revision_id,
                    express_id=entity.id(),
                ),
                ifc_class=entity.is_a(),
                name=getattr(entity, "Name", None),
                global_id=guid,
                global_id_state=state,
                has_geometry=getattr(entity, "Representation", None) is not None,
            )
        )
    return records
