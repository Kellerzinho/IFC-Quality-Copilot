"""Construtores de modelos IFC4 SINTÉTICOS, com controle exato dos portadores e tipos.

Entidades criadas diretamente (sem inferência de tipo pela API), gravadas em disco e
reabertas pelos testes. Nenhum modelo de usuário é lido ou alterado.
"""

import hashlib
import uuid
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.guid

from src.operations.contracts import SourceArtifactRef

PROJECT = "1111aaaa-1111-4111-8111-111111111111"
MODEL = "2222aaaa-2222-4222-8222-222222222222"


def model() -> ifcopenshell.file:
    """Modelo IFC4 vazio com um projeto."""
    f = ifcopenshell.file(schema="IFC4")
    f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="Projeto sintético")
    return f


def element(f: ifcopenshell.file, ifc_class: str = "IfcWall", **attrs: Any) -> Any:
    """Elemento com GUID novo, salvo se ``GlobalId`` for dado (inclusive inválido/None)."""
    data = {"GlobalId": ifcopenshell.guid.new(), **attrs}
    return f.create_entity(ifc_class, **data)


def single(f: ifcopenshell.file, name: str, ifc_type: str | None, value: Any = None) -> Any:
    """``IfcPropertySingleValue`` com valor nominal do tipo exato (``None`` = sem valor)."""
    nominal = None if ifc_type is None else f.create_entity(ifc_type, value)
    return f.create_entity("IfcPropertySingleValue", Name=name, NominalValue=nominal)


def pset(f: ifcopenshell.file, owner: Any, name: str, props: list[Any]) -> Any:
    """Conjunto ligado à ocorrência (por relação) ou ao tipo (``HasPropertySets``)."""
    definition = f.create_entity(
        "IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name=name, HasProperties=props
    )
    if owner.is_a("IfcTypeObject"):
        owner.HasPropertySets = [*(owner.HasPropertySets or ()), definition]
    else:
        f.create_entity(
            "IfcRelDefinesByProperties",
            GlobalId=ifcopenshell.guid.new(),
            RelatedObjects=[owner],
            RelatingPropertyDefinition=definition,
        )
    return definition


def quantities(f: ifcopenshell.file, owner: Any, name: str, quantity_name: str) -> Any:
    """``IfcElementQuantity`` com uma quantidade de comprimento (portador fora do suporte)."""
    quantity = f.create_entity("IfcQuantityLength", Name=quantity_name, LengthValue=2.5)
    definition = f.create_entity(
        "IfcElementQuantity", GlobalId=ifcopenshell.guid.new(), Name=name, Quantities=[quantity]
    )
    f.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[owner],
        RelatingPropertyDefinition=definition,
    )
    return definition


def typed(
    f: ifcopenshell.file, occurrence: Any, ifc_class: str = "IfcWallType", **attrs: Any
) -> Any:
    """Tipo associado à ocorrência por ``IfcRelDefinesByType``."""
    type_object = f.create_entity(ifc_class, GlobalId=ifcopenshell.guid.new(), Name="Tipo", **attrs)
    f.create_entity(
        "IfcRelDefinesByType",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[occurrence],
        RelatingType=type_object,
    )
    return type_object


def write(f: ifcopenshell.file, path: Path) -> tuple[Path, SourceArtifactRef]:
    """Grava o modelo e devolve caminho e referência de fonte com o hash real."""
    path.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(path))
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    ref = SourceArtifactRef(
        project_id=uuid.UUID(PROJECT),
        model_id=uuid.UUID(MODEL),
        source_id=uuid.uuid4(),
        revision=1,
        role="ifc",
        sha256=digest,
        size_bytes=len(data),
        display_name=path.name,
        storage_key=f"s/ifc/{digest}",
    )
    return path, ref


def ids_ref(data: bytes, name: str = "requisitos.ids") -> SourceArtifactRef:
    """Referência de fonte IDS sintética com o hash real dos bytes."""
    digest = hashlib.sha256(data).hexdigest()
    return SourceArtifactRef(
        project_id=uuid.UUID(PROJECT),
        model_id=uuid.UUID(MODEL),
        source_id=uuid.uuid4(),
        revision=1,
        role="ids",
        sha256=digest,
        size_bytes=len(data),
        display_name=name,
        storage_key=f"s/ids/{digest}",
    )
