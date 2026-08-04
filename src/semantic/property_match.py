"""Matcher compartilhado de nomes de propriedade entre IFC/IDS e bSDD.

O bSDD nomeia propriedades em forma humana ("Fire Rating", "Global ID"),
enquanto o IDS e o IFC usam PascalCase ("FireRating"). Antes da revisão de
2026-08-04, quatro consumidores comparavam esses nomes literalmente e nunca
casavam — a validação contra vocabulário bSDD, o tipo/unidade no grounding,
a URI canônica da sugestão aplicada e a URI padrão da auditoria eram no-ops
silenciosos. Este módulo é a fonte única da regra de casamento, a mesma já
usada (e testada) por ``BSDDContextBuilder._filter_properties``.
"""

from __future__ import annotations

import re

__all__ = ["property_match_key", "properties_match", "strip_boolean_prefix"]


def property_match_key(name: str) -> str:
    """Normaliza nome de propriedade para comparação entre bSDD e IFC.

    Ignora espaços, separadores e caixa: ``"Fire Rating"``, ``"FireRating"``
    e ``"fire_rating"`` produzem a mesma chave.
    """
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def strip_boolean_prefix(match_key: str) -> str:
    """Remove o prefixo ``is`` de propriedades booleanas já normalizadas.

    Os psets do IFC não são consistentes entre si (Pset_WallCommon usa
    IsLoadBearing, Pset_SlabCommon usa LoadBearing) e o bSDD guarda a forma
    sem o prefixo booleano.
    """
    if match_key.startswith("is") and len(match_key) > 4:
        return match_key[2:]
    return match_key


def properties_match(a: str, b: str) -> bool:
    """True quando os dois nomes referem a mesma propriedade IFC/bSDD.

    Compara as chaves normalizadas e, em seguida, as chaves sem o prefixo
    booleano ``is`` (regra de ``_filter_properties``, validada em campo).
    Strings vazias nunca casam.
    """
    key_a = property_match_key(a)
    key_b = property_match_key(b)
    if not key_a or not key_b:
        return False
    if key_a == key_b:
        return True
    return strip_boolean_prefix(key_a) == strip_boolean_prefix(key_b)
