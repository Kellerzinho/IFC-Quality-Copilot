"""Composição local opt-in: reader fixado → adaptador real → envelope imutável."""

from src.domain_catalog.adapters import ScopedLocalCatalogAdapter
from src.domain_catalog.contracts import BindingRequest, CatalogReleaseRef
from src.domain_catalog.errors import CatalogProjectionError
from src.domain_catalog.projection_contracts import (
    CatalogProjection,
    LocalCatalogContext,
    LocalProjectedProperty,
    ProjectionScope,
)
from src.domain_catalog.reader import CatalogReader


class LocalCatalogContextBuilder:
    """Monta contexto semântico; não chama LLM, pipeline, rede ou builder histórico."""

    def __init__(
        self, reader: CatalogReader, *, catalog: CatalogReleaseRef, language: str = "pt-BR"
    ) -> None:
        """Exige referência exata do snapshot já aberto; não vigia alterações em disco."""
        if reader.ref != catalog:
            raise CatalogProjectionError(
                "release_mismatch", "reader difere do release solicitado", catalog=catalog
            )
        self._reader = reader
        self._catalog = catalog
        self._language = language

    def build(self, request: BindingRequest) -> LocalCatalogContext:
        """Preserva falhas previstas como indisponibilidade e propaga erros técnicos."""
        scope = ProjectionScope(catalog=self._catalog, request=request, language=self._language)
        adapter = ScopedLocalCatalogAdapter(self._reader, scope)
        projection: CatalogProjection | None = None
        try:
            projection = adapter.projection()
            assert request.entity is not None
            classes = adapter.search_class(request.entity)
            if len(classes) != 1:
                raise RuntimeError("adaptador não retornou o agrupamento do escopo resolvido")
            legacy = adapter.get_class_properties(classes[0]["uri"])
            if projection.effective_value_set is not None:
                values = adapter.get_property_values(projection.binding.id)
                if len(legacy) != 1 or legacy[0].allowed_values != values:
                    raise RuntimeError("wrappers discordam sobre os valores do uso")
            properties = tuple(
                LocalProjectedProperty.model_validate(prop.model_dump()) for prop in legacy
            )
        except CatalogProjectionError as exc:
            limitations = (
                projection.limitations
                if projection is not None
                else (exc.resolution.limitations if exc.resolution is not None else ())
            )
            return LocalCatalogContext(
                scope=scope,
                resolution=exc.resolution,
                status="unavailable",
                projection=projection,
                properties=(),
                error_reason=exc.reason,
                limitations=(*limitations, str(exc)),
            )
        return LocalCatalogContext(
            scope=scope,
            resolution=projection.resolution,
            status="available",
            projection=projection,
            properties=properties,
            error_reason=None,
            limitations=projection.limitations,
        )
