"""Contexto do elemento para o catálogo: PredefinedType lido pelo M2 (plano §5.2).

Leituras literais da ocorrência e do tipo associado são conservadas. Regra efetiva
desta condição: tipo associado único com valor diferente de ``NOTDEFINED`` prevalece;
na falta dele, vale a leitura da ocorrência (inclusive ``NOTDEFINED``, que é valor
declarado); só ``NOTDEFINED`` no tipo vale como tipo. Mais de um tipo associado é
indeterminado. Valor efetivo ``USERDEFINED`` depende de ``ObjectType``/``ElementType``,
que esta condição não avalia: indeterminado, sem trocar o enum pelo texto do nome.
Nenhuma leitura em nenhum nível consultado é ``absent``.
"""

from typing import Any

from src.domain_catalog.contracts import PredefinedTypeContext, PredefinedTypeReading
from src.ifc_analyzer.identity import ElementRef
from src.ifc_analyzer.read_only import ReadOnlyIfcSession


def _declared(instance: Any) -> str | None:
    try:
        value = instance.PredefinedType
    except AttributeError:
        return None
    return value if isinstance(value, str) and value else None


def predefined_type_context(
    session: ReadOnlyIfcSession, element: ElementRef
) -> PredefinedTypeContext:
    """PredefinedType efetivo, origem e todas as leituras do elemento na sessão retida."""
    instance = session.by_express_id(element.express_id)
    relations = list(getattr(instance, "IsTypedBy", None) or ())
    occurrence = _declared(instance)
    readings: list[PredefinedTypeReading] = []
    if occurrence is not None:
        readings.append(PredefinedTypeReading(origin="occurrence", value=occurrence))
    if len(relations) > 1:
        return PredefinedTypeContext(
            status="undetermined",
            readings=tuple(readings),
            reason="mais de um tipo associado; nenhum é escolhido",
        )
    type_value = _declared(relations[0].RelatingType) if relations else None
    if type_value is not None:
        readings.append(PredefinedTypeReading(origin="type", value=type_value))
    if type_value is not None and type_value != "NOTDEFINED":
        origin, value = "type", type_value
    elif occurrence is not None:
        origin, value = "occurrence", occurrence
    elif type_value is not None:
        origin, value = "type", type_value
    else:
        return PredefinedTypeContext(status="absent")
    if value == "USERDEFINED":
        return PredefinedTypeContext(
            status="undetermined",
            readings=tuple(readings),
            reason="USERDEFINED depende de ObjectType/ElementType, não avaliado nesta condição",
        )
    return PredefinedTypeContext(
        status="determined",
        effective_origin=origin,  # type: ignore[arg-type]
        readings=tuple(readings),
    )
