"""Construtores de IDS XML SINTÉTICOS para os testes da E3 (M2).

Textos montados à mão, sem conteúdo de fonte real. ``simple("")`` produz
``<simpleValue></simpleValue>`` explícito; omitir o parâmetro omite o elemento.
"""

from xml.sax.saxutils import escape, quoteattr

NS = "http://standards.buildingsmart.org/IDS"


def simple(text: str) -> str:
    """Valor literal ``simpleValue`` (texto exato, inclusive vazio)."""
    return f"<simpleValue>{escape(text)}</simpleValue>"


def enum(*values: str, base: str = "xs:string") -> str:
    """Restrição de enumeração completa, na ordem dada."""
    items = "".join(f"<xs:enumeration value={quoteattr(v)}/>" for v in values)
    return f'<xs:restriction base="{base}">{items}</xs:restriction>'


def pattern(regex: str) -> str:
    """Restrição por padrão (fora do suporte nesta condição)."""
    return (
        f'<xs:restriction base="xs:string"><xs:pattern value={quoteattr(regex)}/></xs:restriction>'
    )


def entity(name: str, predefined: str | None = None) -> str:
    """Faceta entity com nome literal."""
    extra = "" if predefined is None else f"<predefinedType>{simple(predefined)}</predefinedType>"
    return f"<entity><name>{simple(name)}</name>{extra}</entity>"


def prop(
    pset: str,
    name: str,
    *,
    data_type: str | None = "IFCLABEL",
    value: str | None = None,
    cardinality: str | None = None,
    pset_value: str | None = None,
    name_value: str | None = None,
) -> str:
    """Faceta property; ``value`` é o conteúdo bruto do elemento ``<value>``."""
    attrs = ""
    if data_type is not None:
        attrs += f' dataType="{data_type}"'
    if cardinality is not None:
        attrs += f' cardinality="{cardinality}"'
    body = f"<propertySet>{pset_value or simple(pset)}</propertySet>"
    body += f"<baseName>{name_value or simple(name)}</baseName>"
    if value is not None:
        body += f"<value>{value}</value>"
    return f"<property{attrs}>{body}</property>"


def attribute(name: str) -> str:
    """Faceta attribute (fora do suporte de requisito)."""
    return f"<attribute><name>{simple(name)}</name></attribute>"


def spec(
    name: str,
    applicability: str,
    requirements: str = "",
    *,
    ifc: str = "IFC4",
    min_occurs: str | None = "0",
    max_occurs: str | None = "unbounded",
    identifier: str | None = None,
) -> str:
    """Especificação; ``None`` em min/max omite o atributo (default do XSD)."""
    occurs = ""
    if min_occurs is not None:
        occurs += f' minOccurs="{min_occurs}"'
    if max_occurs is not None:
        occurs += f' maxOccurs="{max_occurs}"'
    ident = "" if identifier is None else f" identifier={quoteattr(identifier)}"
    reqs = f"<requirements>{requirements}</requirements>" if requirements else ""
    return (
        f'<specification name={quoteattr(name)} ifcVersion="{ifc}"{ident}>'
        f"<applicability{occurs}>{applicability}</applicability>{reqs}</specification>"
    )


def ids(*specs: str, prolog: str = "", root_attrs: str = "") -> bytes:
    """Documento IDS completo em UTF-8."""
    return (
        f'{prolog}<ids xmlns="{NS}" xmlns:xs="http://www.w3.org/2001/XMLSchema"{root_attrs}>'
        f"<info><title>IDS sintético de teste</title></info>"
        f"<specifications>{''.join(specs)}</specifications></ids>"
    ).encode()
