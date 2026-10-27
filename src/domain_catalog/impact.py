"""Impacto interno potencial entre releases: fechamento por snapshot (E3.2a §4).

Um grafo por snapshot (old e new), nunca a união dos dois: um trace jamais cruza
versões. As 21 referências cadastrais propagam do referenciado ao consumidor
(``reverse_dependency``); alias, decisão e participação em perfil contribuem para
seus alvos (``forward_contribution``), sem o sentido oposto. Binding é terminal.
Para cada raiz e snapshot em que ela existe, uma BFS com adjacências ordenadas pela
representação canônica da aresta fixa uma testemunha de caminho mínimo,
lexicograficamente menor. O limite conta cada trace emitido; excedê-lo recusa a
comparação inteira, sem resultado parcial. Não aponta requisitos, elementos IFC,
caches nem análises reais.
"""

from collections import deque
from collections.abc import Iterator
from typing import Literal

from src.domain_catalog.content import REFERENCES, CatalogContent
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.diff_contracts import (
    REFERENCE_DIRECTIONS,
    DiffLimits,
    EntityChange,
    EntityKey,
    ImpactEdge,
    ImpactTrace,
)
from src.domain_catalog.errors import CatalogComparisonError

Snapshot = Literal["old", "new"]
_SNAPSHOTS: dict[str, tuple[Snapshot, ...]] = {
    "added": ("new",),
    "removed": ("old",),
    "modified": ("old", "new"),
}


def _adjacency(content: CatalogContent) -> dict[EntityKey, tuple[ImpactEdge, ...]]:
    """Arestas de travessia por nó de partida, ordenadas pela representação canônica."""
    found: dict[EntityKey, list[ImpactEdge]] = {}
    for owner_kind, field, referenced_kind in REFERENCES:
        direction = REFERENCE_DIRECTIONS[(owner_kind, field, referenced_kind)]
        for entity in getattr(content, owner_kind):
            value = getattr(entity, field)
            items = value if isinstance(value, tuple) else (value,)
            for item in dict.fromkeys(v for v in items if v is not None):
                edge = ImpactEdge(
                    owner=EntityKey(kind=owner_kind, id=entity.id),  # type: ignore[arg-type]
                    field=field,
                    referenced=EntityKey(kind=referenced_kind, id=item),  # type: ignore[arg-type]
                    direction=direction,
                )
                start = edge.referenced if direction == "reverse_dependency" else edge.owner
                found.setdefault(start, []).append(edge)
    return {node: tuple(sorted(edges, key=ImpactEdge.sort_text)) for node, edges in found.items()}


def _closure(
    adjacency: dict[EntityKey, tuple[ImpactEdge, ...]], origin: EntityKey, snapshot: Snapshot
) -> Iterator[ImpactTrace]:
    """Raiz (distância 0) e cada alvo alcançado, com a primeira testemunha mínima."""
    paths: dict[EntityKey, tuple[ImpactEdge, ...]] = {origin: ()}
    queue: deque[EntityKey] = deque([origin])
    yield ImpactTrace(origin=origin, target=origin, snapshot=snapshot, distance=0, path=())
    while queue:
        node = queue.popleft()
        for edge in adjacency.get(node, ()):
            following = edge.step(node)
            if following is None or following in paths:
                continue
            path = (*paths[node], edge)
            paths[following] = path
            queue.append(following)
            yield ImpactTrace(
                origin=origin, target=following, snapshot=snapshot, distance=len(path), path=path
            )


def build_catalog_impacts(
    old: CatalogContent,
    new: CatalogContent,
    changes: tuple[EntityChange, ...],
    *,
    limits: DiffLimits,
    old_ref: CatalogReleaseRef,
    new_ref: CatalogReleaseRef,
) -> tuple[ImpactTrace, ...]:
    """Traces de todas as raízes, por snapshot, ordenados; limite excedido é recusa."""
    graphs = {"old": _adjacency(old), "new": _adjacency(new)}
    traces: list[ImpactTrace] = []
    for change in changes:
        for snapshot in _SNAPSHOTS[change.change_kind]:
            for trace in _closure(graphs[snapshot], change.entity, snapshot):
                traces.append(trace)
                if len(traces) > limits.max_impact_traces:
                    raise CatalogComparisonError(
                        "impact_limit_exceeded",
                        f"impacto excede {limits.max_impact_traces} traces; nada é devolvido",
                        old_ref=old_ref,
                        new_ref=new_ref,
                        limit=limits.max_impact_traces,
                    )
    traces.sort(key=ImpactTrace.sort_key)
    return tuple(traces)
