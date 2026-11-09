"""Portão de XML seguro antes de qualquer validação de esquema (plano §5.1, etapa 1).

Recusa por tamanho, DOCTYPE/DTD/entidades (internas ou externas), XML malformado e
profundidade/número de elementos acima do limite. Igualdade ao limite é aceita.
O parser não resolve entidades, não carrega DTD e não acessa rede. Recurso XML
válido porém não suportado pela condição **não** é tratado aqui: isso é capacidade
semântica, decidida depois da validação XSD.
"""

from dataclasses import dataclass
from typing import Any, Final, Literal

MiB: Final = 1024 * 1024

XmlGateReason = Literal["resource_limit_exceeded", "xml_unsafe", "xml_malformed"]


class XmlGateError(Exception):
    """XML recusado pelo portão seguro; nada foi interpretado semanticamente."""

    code = "xml_gate_refused"

    def __init__(self, reason: XmlGateReason, message: str) -> None:
        """Guarda o motivo estável."""
        self.reason: XmlGateReason = reason
        super().__init__(f"[{reason}] {message}")


@dataclass(frozen=True)
class XmlLimits:
    """Limites determinísticos do documento; não são garantia de tempo ou memória."""

    max_bytes: int = 8 * MiB
    max_depth: int = 64
    max_nodes: int = 100_000


def secure_parse(data: bytes, limits: XmlLimits) -> Any:
    """Elemento raiz lxml de um XML seguro, dentro dos limites; senão ``XmlGateError``."""
    from lxml import etree  # type: ignore[import-untyped]

    if len(data) > limits.max_bytes:
        raise XmlGateError("resource_limit_exceeded", f"XML excede {limits.max_bytes} bytes")
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise XmlGateError("xml_unsafe", "DOCTYPE/DTD/entidades não são aceitos")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        collect_ids=False,
    )
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise XmlGateError("xml_malformed", f"XML malformado: {exc}") from exc
    info = root.getroottree().docinfo
    if info.doctype or info.internalDTD is not None or info.externalDTD is not None:
        raise XmlGateError("xml_unsafe", "DOCTYPE/DTD não são aceitos")
    nodes = 0
    pending: list[tuple[Any, int]] = [(root, 1)]
    while pending:
        element, depth = pending.pop()
        if not isinstance(element.tag, str):
            continue
        nodes += 1
        if depth > limits.max_depth:
            raise XmlGateError("resource_limit_exceeded", f"XML excede {limits.max_depth} níveis")
        if nodes > limits.max_nodes:
            raise XmlGateError(
                "resource_limit_exceeded", f"XML excede {limits.max_nodes} elementos"
            )
        pending.extend((child, depth + 1) for child in element)
    return root
