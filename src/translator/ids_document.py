"""Documento IDS estrito: XML seguro → XSD oficial offline → inventário fiel (plano §5.1).

O inventário vem da árvore original, na ordem do XML: especificações, facetas de
aplicabilidade e de requisito (inclusive intercaladas), todos os parâmetros com
``simpleValue`` literal (vazio e espaços preservados, sem strip) ou restrição com
**todas** as facetas, atributos e o fragmento XML canônico de cada faceta. Recursos
sem suporte na condição continuam inventariados; XML válido mas não suportado não é
XML inválido. Nada é inferido (nem quantidade por ``Qto_``, nem enum pelo primeiro
valor). O parser legado ``ids_parser.py`` não é usado.
"""

import copy
import hashlib
from typing import Annotated, Any, Final, Literal, Self

from pydantic import Field, PrivateAttr, StrictInt, model_validator

from src.domain_catalog.contracts import ContractModel
from src.domain_catalog.models import Sha256Hex
from src.validation.schema_bundle import IDS_NAMESPACE, SchemaBundle
from src.validation.source_gate import MiB, XmlGateError, XmlLimits, secure_parse

XS_NAMESPACE: Final = "http://www.w3.org/2001/XMLSchema"
IDSSection = Literal["applicability", "requirements"]
NonNegative = Annotated[StrictInt, Field(ge=0)]

IDSGateReason = Literal[
    "resource_limit_exceeded", "xml_unsafe", "xml_malformed", "xsd_invalid", "inventory_mismatch"
]


class RestrictionFacet(ContractModel):
    """Faceta de restrição XSD literal (``enumeration``, ``pattern``…)."""

    name: str
    value: str


class IDSValue(ContractModel):
    """Valor IDS literal: ``simpleValue`` exato ou restrição com todas as facetas."""

    kind: Literal["simple", "restriction"]
    text: str | None = None
    base: str | None = None
    facets: tuple[RestrictionFacet, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Texto só em valor simples; base só em restrição."""
        if self.kind == "simple" and (self.text is None or self.base is not None or self.facets):
            raise ValueError("simpleValue exige texto e nenhuma restrição")
        if self.kind == "restriction" and (self.text is not None or self.base is None):
            raise ValueError("restrição exige base e nenhum texto simples")
        return self


class IDSParameter(ContractModel):
    """Parâmetro de faceta na ordem original (``name``, ``propertySet``, ``value``…)."""

    name: str
    value: IDSValue


class IDSLocation(ContractModel):
    """Localizador por hash do IDS e índices originais; nunca por rótulo/identificador."""

    ids_sha256: Sha256Hex
    specification_index: NonNegative
    section: IDSSection
    index: NonNegative
    facet_tag: str
    specification_identifier: str | None = None
    specification_name: str

    def key(self) -> str:
        """Chave canônica (hash + índices); identificadores duplicados não colidem."""
        return f"{self.ids_sha256}/{self.specification_index}/{self.section}/{self.index}"


class IDSFacet(ContractModel):
    """Faceta original: localizador, ocorrência por tag, atributos, parâmetros e fragmento."""

    location: IDSLocation
    tag: str
    occurrence_index: NonNegative
    attributes: tuple[tuple[str, str], ...]
    parameters: tuple[IDSParameter, ...]
    fragment: str
    fragment_sha256: Sha256Hex

    def parameter(self, name: str) -> IDSValue | None:
        """Valor do parâmetro, ou ``None`` quando o elemento foi omitido."""
        return next((p.value for p in self.parameters if p.name == name), None)

    def attribute(self, name: str) -> str | None:
        """Atributo literal da faceta, ou ``None`` quando omitido."""
        return next((value for key, value in self.attributes if key == name), None)


Origin = Literal["explicit", "schema_default"]


class SpecificationCardinality(ContractModel):
    """Atributos originais e valores efetivos com os defaults do XSD fixado (``xs:occurs``)."""

    min_raw: str | None
    max_raw: str | None
    min_effective: NonNegative
    max_effective: NonNegative | Literal["unbounded"]
    min_origin: Origin
    max_origin: Origin


class IDSSpecification(ContractModel):
    """Especificação na ordem do XML, com inventário completo de facetas."""

    index: NonNegative
    name: str
    identifier: str | None
    description: str | None
    instructions: str | None
    ifc_versions: tuple[str, ...]
    cardinality: SpecificationCardinality
    applicability: tuple[IDSFacet, ...]
    requirements: tuple[IDSFacet, ...]
    fragment_sha256: Sha256Hex


class IDSDocument(ContractModel):
    """IDS validado pelo bundle oficial; o dicionário decodificado fica privado."""

    schema_version: Literal[1] = 1
    ids_sha256: Sha256Hex
    size_bytes: NonNegative
    title: str | None
    specifications: tuple[IDSSpecification, ...]
    _decoded: dict[str, Any] | None = PrivateAttr(default=None)

    def decoded(self) -> dict[str, Any]:
        """Cópia nova do documento decodificado pelo XSD (para o backend, por execução)."""
        if self._decoded is None:
            raise ValueError("documento sem decodificação XSD (inventário parcial)")
        return copy.deepcopy(self._decoded)


class IDSGateError(Exception):
    """IDS recusado antes de qualquer avaliação; ``partial`` é inventário quando possível."""

    code = "ids_refused"

    def __init__(
        self, reason: IDSGateReason, message: str, *, partial: IDSDocument | None = None
    ) -> None:
        """Guarda motivo e inventário parcial (nunca diagnóstico formal)."""
        self.reason: IDSGateReason = reason
        self.partial = partial
        super().__init__(f"[{reason}] {message}")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ids(name: str) -> str:
    return f"{{{IDS_NAMESPACE}}}{name}"


def _value(element: Any) -> IDSValue | None:
    simple = element.find(_ids("simpleValue"))
    if simple is not None:
        # Conteúdo textual completo: comentários/instruções de processamento são
        # inertes, mas o texto depois deles (tail) pertence ao valor (E3-03).
        text = (simple.text or "") + "".join(child.tail or "" for child in simple)
        return IDSValue(kind="simple", text=text)
    restriction = element.find(f"{{{XS_NAMESPACE}}}restriction")
    if restriction is not None:
        facets = tuple(
            RestrictionFacet(name=_local(child.tag), value=child.get("value", ""))
            for child in restriction
            if isinstance(child.tag, str) and _local(child.tag) != "annotation"
        )
        return IDSValue(kind="restriction", base=restriction.get("base", ""), facets=facets)
    return None


def _facets(
    section_element: Any, section: IDSSection, spec_index: int, spec: Any, ids_sha256: str
) -> tuple[IDSFacet, ...]:
    from lxml import etree  # type: ignore[import-untyped]

    facets: list[IDSFacet] = []
    seen: dict[str, int] = {}
    elements = [child for child in section_element if isinstance(child.tag, str)]
    for index, element in enumerate(elements):
        tag = _local(element.tag)
        occurrence = seen.get(tag, 0)
        seen[tag] = occurrence + 1
        parameters = []
        for child in element:
            if not isinstance(child.tag, str):
                continue
            value = _value(child)
            if value is not None:
                parameters.append(IDSParameter(name=_local(child.tag), value=value))
        fragment = etree.tostring(element, method="c14n").decode("utf-8")
        facets.append(
            IDSFacet(
                location=IDSLocation(
                    ids_sha256=ids_sha256,
                    specification_index=spec_index,
                    section=section,
                    index=index,
                    facet_tag=tag,
                    specification_identifier=spec.get("identifier"),
                    specification_name=spec.get("name", ""),
                ),
                tag=tag,
                occurrence_index=occurrence,
                attributes=tuple(sorted((str(k), str(v)) for k, v in element.attrib.items())),
                parameters=tuple(parameters),
                fragment=fragment,
                fragment_sha256=hashlib.sha256(fragment.encode("utf-8")).hexdigest(),
            )
        )
    return tuple(facets)


def _cardinality(applicability: Any) -> SpecificationCardinality:
    min_raw = None if applicability is None else applicability.get("minOccurs")
    max_raw = None if applicability is None else applicability.get("maxOccurs")
    maximum: int | Literal["unbounded"]
    if max_raw is None:
        maximum = 1
    elif max_raw == "unbounded":
        maximum = "unbounded"
    else:
        maximum = int(max_raw)
    return SpecificationCardinality(
        min_raw=min_raw,
        max_raw=max_raw,
        min_effective=1 if min_raw is None else int(min_raw),
        max_effective=maximum,
        min_origin="schema_default" if min_raw is None else "explicit",
        max_origin="schema_default" if max_raw is None else "explicit",
    )


def _inventory(root: Any, data: bytes) -> IDSDocument:
    from lxml import etree

    ids_sha256 = hashlib.sha256(data).hexdigest()
    title = root.find(f"{_ids('info')}/{_ids('title')}")
    specs = []
    container = root.find(_ids("specifications"))
    elements = [] if container is None else container.findall(_ids("specification"))
    for index, spec in enumerate(elements):
        applicability = spec.find(_ids("applicability"))
        requirements = spec.find(_ids("requirements"))
        specs.append(
            IDSSpecification(
                index=index,
                name=spec.get("name", ""),
                identifier=spec.get("identifier"),
                description=spec.get("description"),
                instructions=spec.get("instructions"),
                ifc_versions=tuple(spec.get("ifcVersion", "").split()),
                cardinality=_cardinality(applicability),
                applicability=()
                if applicability is None
                else _facets(applicability, "applicability", index, spec, ids_sha256),
                requirements=()
                if requirements is None
                else _facets(requirements, "requirements", index, spec, ids_sha256),
                fragment_sha256=hashlib.sha256(etree.tostring(spec, method="c14n")).hexdigest(),
            )
        )
    return IDSDocument(
        ids_sha256=ids_sha256,
        size_bytes=len(data),
        title=None if title is None else (title.text or ""),
        specifications=tuple(specs),
    )


def parse_ids_document(
    data: bytes,
    bundle: SchemaBundle,
    *,
    max_bytes: int = 8 * MiB,
    max_depth: int = 64,
    max_nodes: int = 100_000,
) -> IDSDocument:
    """Valida e inventaria um IDS; qualquer recusa é ``IDSGateError`` sem diagnóstico."""
    import xmlschema  # type: ignore[import-not-found,unused-ignore]

    try:
        root = secure_parse(data, XmlLimits(max_bytes, max_depth, max_nodes))
    except XmlGateError as exc:
        raise IDSGateError(exc.reason, str(exc)) from exc
    schema = bundle.build_schema()
    try:
        decoded = schema.decode(
            data,
            validation="strict",
            use_location_hints=False,
            strip_namespaces=True,
            namespaces={"": IDS_NAMESPACE},
        )
    except xmlschema.XMLSchemaValidationError as exc:
        try:
            partial = _inventory(root, data)
        except Exception:  # inventário parcial é melhor esforço; a recusa continua
            partial = None
        raise IDSGateError(
            "xsd_invalid", f"IDS inválido pelo XSD oficial: {exc.reason}", partial=partial
        ) from exc
    document = _inventory(root, data)
    mismatch = _decoded_mismatch(document, decoded)
    if mismatch is not None:
        raise IDSGateError(
            "inventory_mismatch", f"inventário diverge do decode XSD do backend: {mismatch}"
        )
    document._decoded = decoded
    return document


def _as_list(node: Any) -> list[Any]:
    if node is None:
        return []
    return node if isinstance(node, list) else [node]


def _decoded_value(node: Any) -> IDSValue | None:
    """Mesma forma de ``_value`` a partir do dicionário decodificado pelo XSD."""
    if not isinstance(node, dict):
        return None
    if "simpleValue" in node:
        simple = node["simpleValue"]
        return IDSValue(kind="simple", text="" if simple is None else str(simple))
    restriction = node.get("restriction")
    if isinstance(restriction, dict):
        facets = tuple(
            RestrictionFacet(name=name, value=str(item.get("@value", "")))
            for name, items in restriction.items()
            if not name.startswith("@") and name != "annotation"
            for item in _as_list(items)
            if isinstance(item, dict)
        )
        return IDSValue(kind="restriction", base=str(restriction.get("@base", "")), facets=facets)
    return None


def _decoded_mismatch(document: IDSDocument, decoded: dict[str, Any]) -> str | None:
    """Primeiro parâmetro cujo valor no inventário difere do decode do backend.

    O backend consome o decode XSD; o inventário (validador de candidato, M3) consome
    a árvore lxml. Valores literais e restrições têm de ser idênticos nos dois.
    """
    container = decoded.get("specifications") or {}
    specs = _as_list(container.get("specification") if isinstance(container, dict) else None)
    if len(specs) != len(document.specifications):
        return "número de especificações"
    for spec, raw in zip(document.specifications, specs, strict=True):
        for section in ("applicability", "requirements"):
            raw_section = raw.get(section) or {}
            for facet in getattr(spec, section):
                candidates = _as_list(raw_section.get(facet.tag))
                if facet.occurrence_index >= len(candidates):
                    return f"{facet.location.key()}: faceta ausente no decode"
                raw_facet = candidates[facet.occurrence_index]
                for parameter in facet.parameters:
                    value = parameter.value
                    other = _decoded_value(raw_facet.get(parameter.name))
                    if value.kind == "simple":
                        same = other == value
                    elif value.base != "xs:string":
                        # Decode tipa valores numéricos (1e3 → 1000.0); fora da matriz.
                        same = other is not None and other.kind == "restriction"
                    else:
                        same = (
                            other is not None
                            and other.base == value.base
                            and sorted((f.name, f.value) for f in other.facets)
                            == sorted((f.name, f.value) for f in value.facets)
                        )
                    if not same:
                        return f"{facet.location.key()}.{parameter.name}"
    return None
