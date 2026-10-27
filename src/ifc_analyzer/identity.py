"""Identidade de elemento IFC numa revisão exata de fonte (M2, plano §2.1).

A chave é ``(source_id, revision, sha256, express_id)``; o GlobalId é atributo
observado, com estado próprio (válido, ausente, inválido ou duplicado), e nunca
identidade sozinho. O mesmo GUID em pares, revisões ou arquivos distintos é outro
elemento; GUID duplicado no mesmo arquivo continua dois elementos.
"""

import re
from collections.abc import Mapping
from typing import Annotated, Literal, Self

from pydantic import StringConstraints, model_validator

from src.domain_catalog.contracts import ContractModel
from src.domain_catalog.models import Sha256Hex
from src.operations.contracts import CanonicalUUID, PositiveInt, SchemaVersionOne

GuidState = Literal["valid", "missing", "invalid", "duplicate"]
GUID_PATTERN = re.compile(r"^[0-3][0-9A-Za-z_$]{21}$")
IfcClass = Annotated[str, StringConstraints(pattern=r"^Ifc[A-Za-z0-9]+$")]


def guid_state_of(global_id: str | None, counts: Mapping[str, int]) -> GuidState:
    """Estado do GlobalId: sintaxe IFC (22 caracteres) e unicidade no arquivo."""
    if global_id is None or global_id == "":
        return "missing"
    if GUID_PATTERN.match(global_id) is None:
        return "invalid"
    return "duplicate" if counts.get(global_id, 0) > 1 else "valid"


class ElementRef(ContractModel):
    """Elemento por fonte, revisão, bytes e express ID; o GUID é só observado."""

    schema_version: SchemaVersionOne = 1
    source_id: CanonicalUUID
    revision: PositiveInt
    sha256: Sha256Hex
    express_id: PositiveInt
    ifc_class: IfcClass
    global_id: str | None
    guid_state: GuidState

    @model_validator(mode="after")
    def _guid_coherent(self) -> Self:
        """Estado do GUID coerente com o texto observado."""
        if self.guid_state == "missing" and self.global_id not in (None, ""):
            raise ValueError("guid_state missing exige GlobalId ausente")
        if self.guid_state in ("valid", "duplicate") and (
            self.global_id is None or GUID_PATTERN.match(self.global_id) is None
        ):
            raise ValueError(f"guid_state {self.guid_state} exige GlobalId sintaticamente válido")
        if self.guid_state == "invalid" and (
            self.global_id is None or GUID_PATTERN.match(self.global_id) is not None
        ):
            raise ValueError("guid_state invalid exige GlobalId presente e fora da sintaxe")
        return self

    def key(self) -> tuple[str, int, str, int]:
        """Chave de identidade; nunca o GUID sozinho."""
        return str(self.source_id), self.revision, self.sha256, self.express_id
