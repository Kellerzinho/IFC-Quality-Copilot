"""Sessão IFC somente leitura sobre a fonte retida (M2, plano §5.4).

Abre exatamente os bytes da revisão registrada (hash e tamanho conferidos), dentro
dos limites da condição, e calcula uma assinatura estrutural determinística de todas
as entidades (express ID, classe, atributos e referências serializados) sem
modificar o modelo. ``verify_unchanged`` confere de novo bytes no disco, contagem e
assinatura: qualquer diferença é ``source_mutated``. A assinatura detecta mutação
desta sessão; não é alegação de equivalência semântica entre arquivos. A sessão não
oferece escritor nem métodos de mutação; ``backend_model`` existe só para os
avaliadores somente leitura (IDS e observações).
"""

import hashlib
from collections import Counter
from functools import cached_property
from pathlib import Path
from typing import Any, Final, Literal

from src.ifc_analyzer.identity import ElementRef, guid_state_of
from src.operations.contracts import SourceArtifactRef

MiB: Final = 1024 * 1024

IfcSourceReason = Literal[
    "artifact_unavailable",
    "artifact_integrity_error",
    "resource_limit_exceeded",
    "ifc_unreadable",
    "source_mutated",
    "unknown_entity_name",
    "foreign_reference",
]


class IfcSourceError(Exception):
    """Fonte IFC indisponível, adulterada, fora do limite, ilegível ou mutada."""

    code = "ifc_source_error"

    def __init__(self, reason: IfcSourceReason, message: str) -> None:
        """Guarda o motivo estável."""
        self.reason: IfcSourceReason = reason
        super().__init__(f"[{reason}] {message}")


def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _signature(model: Any) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for instance in sorted(model, key=lambda inst: inst.id()):
        digest.update(str(instance).encode("utf-8"))
        digest.update(b"\n")
        count += 1
    return digest.hexdigest(), count


class ReadOnlyIfcSession:
    """Modelo IFC aberto da fonte retida, com detecção de mutação antes/depois."""

    def __init__(self, source: SourceArtifactRef, path: Path, model: Any) -> None:
        """Use ``ReadOnlyIfcSession.open``."""
        self.source = source
        self._path = path
        self._model = model
        self.signature, self.entity_count = _signature(model)

    @classmethod
    def open(
        cls,
        source: SourceArtifactRef,
        path: Path,
        *,
        max_bytes: int = 256 * MiB,
        max_entities: int = 250_000,
    ) -> "ReadOnlyIfcSession":
        """Confere bytes e limites e abre o IFC; nunca abre outro arquivo de mesmo nome."""
        import ifcopenshell

        if source.role != "ifc":
            raise IfcSourceError("foreign_reference", "sessão IFC exige fonte de papel ifc")
        if source.size_bytes > max_bytes:
            raise IfcSourceError("resource_limit_exceeded", f"IFC excede {max_bytes} bytes")
        try:
            digest = _file_digest(path)
        except FileNotFoundError as exc:
            raise IfcSourceError("artifact_unavailable", "fonte IFC retida ausente") from exc
        if digest != (source.sha256, source.size_bytes):
            raise IfcSourceError("artifact_integrity_error", "bytes do IFC diferem da revisão")
        try:
            model = ifcopenshell.open(str(path))
        except Exception as exc:  # erro do leitor nativo vira motivo tipado
            raise IfcSourceError("ifc_unreadable", f"IFC ilegível: {exc}") from exc
        count = sum(1 for _ in model)
        if count > max_entities:
            raise IfcSourceError("resource_limit_exceeded", f"IFC excede {max_entities} entidades")
        if _file_digest(path) != (source.sha256, source.size_bytes):
            raise IfcSourceError("source_mutated", "fonte mudou durante a abertura")
        return cls(source, path, model)

    @property
    def schema(self) -> str:
        """Identificador de schema declarado no arquivo (ex.: ``IFC4``)."""
        return str(self._model.schema_identifier)

    def backend_model(self) -> Any:
        """Modelo para avaliadores somente leitura; mutação é detectada por ``verify_unchanged``."""
        return self._model

    @cached_property
    def _guid_counts(self) -> Counter[str]:
        return Counter(inst.GlobalId for inst in self._model.by_type("IfcRoot") if inst.GlobalId)

    def by_express_id(self, express_id: int) -> Any:
        """Instância pelo express ID; inexistente é ``foreign_reference``."""
        try:
            return self._model.by_id(express_id)
        except RuntimeError as exc:
            raise IfcSourceError("foreign_reference", f"#{express_id} não existe na fonte") from exc

    def element_ref(self, instance: Any) -> ElementRef:
        """Identidade do elemento nesta revisão exata da fonte."""
        global_id = getattr(instance, "GlobalId", None) if instance.is_a("IfcRoot") else None
        return ElementRef(
            source_id=self.source.source_id,
            revision=self.source.revision,
            sha256=self.source.sha256,
            express_id=instance.id(),
            ifc_class=instance.is_a(),
            global_id=global_id,
            guid_state=guid_state_of(global_id, self._guid_counts),
        )

    def owns(self, element: ElementRef) -> bool:
        """Se a referência pertence a esta fonte/revisão/bytes."""
        return (element.source_id, element.revision, element.sha256) == (
            self.source.source_id,
            self.source.revision,
            self.source.sha256,
        )

    def guid_index(self) -> dict[str, tuple[ElementRef, ...]]:
        """Índice GUID → lista de elementos (duplicatas preservadas)."""
        index: dict[str, list[ElementRef]] = {}
        for instance in self._model.by_type("IfcRoot"):
            if instance.GlobalId:
                index.setdefault(instance.GlobalId, []).append(self.element_ref(instance))
        return {guid: tuple(refs) for guid, refs in index.items()}

    def verify_unchanged(self) -> None:
        """Bytes no disco, contagem e assinatura estrutural iguais aos da abertura."""
        try:
            digest = _file_digest(self._path)
        except OSError as exc:
            raise IfcSourceError("source_mutated", "fonte retida desapareceu") from exc
        if digest != (self.source.sha256, self.source.size_bytes):
            raise IfcSourceError("source_mutated", "bytes do IFC mudaram durante a sessão")
        if _signature(self._model) != (self.signature, self.entity_count):
            raise IfcSourceError("source_mutated", "modelo em memória foi alterado")
