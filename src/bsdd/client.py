"""Cliente bSDD com resolucao estruturada e cache persistente."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from src.bsdd.cache import BSDDCacheStore
from src.bsdd.models import BSDDClassData, BSDDPropertyData
from src.config import Settings, get_settings
from src.models import BSDDProperty
from src.semantic_registry.registry import DEFAULT_SOURCE_POLICY


class BSDDClient:
    """Cliente para a API bSDD com resolucao canonica controlada."""

    _DEFAULT_DOMAIN_URIS = {
        "IFC": "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3",
    }

    def __init__(
        self,
        settings: Settings | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        cache_path: str | None = None,
    ) -> None:
        resolved_settings = settings or get_settings()
        self.base_url = (base_url or resolved_settings.bsdd_api_url).rstrip("/")
        self.timeout = timeout or resolved_settings.bsdd_timeout_seconds
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"User-Agent": "ifc-quality-copilot/0.1"},
        )
        self._cache: dict[str, Any] = {}
        self._unsupported_paths: set[str] = set()
        self._persistent_cache = BSDDCacheStore(
            cache_path or resolved_settings.bsdd_cache_path,
            enabled=resolved_settings.bsdd_cache_enabled,
        )

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Resolvers estruturados
    # ------------------------------------------------------------------

    def resolve_dictionary_uri(self, domain: str | None) -> str | None:
        """Resolve o URI do dicionario com cache persistente."""
        return self._resolve_dictionary_uri(domain)

    def search_classes_text(self, query: str, domain: str = "IFC") -> list[BSDDClassData]:
        """Executa busca textual controlada e retorna candidatos estruturados."""
        normalized_query = query.strip()
        dictionary_uri = self._resolve_dictionary_uri(domain)
        cache_key = f"{normalized_query}|{dictionary_uri or domain}"
        cached = self._persistent_cache.get("class_search", cache_key)
        if isinstance(cached, list):
            return [BSDDClassData.model_validate(item) for item in cached]

        data = self._get_cached_or_fetch(
            cache_key=f"search_class:{normalized_query}:{domain}",
            url="/api/Class/Search/v1",
            params={
                "SearchText": normalized_query,
                "DictionaryUris": [dictionary_uri] if dictionary_uri else None,
            },
        )
        if data is None:
            return []

        items = data.get("classes") or data.get("Classes") or []
        exact_matches = []
        query_upper = normalized_query.upper()
        for item in items:
            reference_code = str(item.get("referenceCode") or item.get("ReferenceCode") or "").strip().upper()
            item_name = str(item.get("name") or item.get("Name") or "").strip().upper()
            if query_upper and query_upper in {reference_code, item_name}:
                exact_matches.append(item)
        if exact_matches:
            items = exact_matches

        results = [self._class_from_search_item(item, dictionary_uri, normalized_query) for item in items]
        serializable = [item.model_dump() for item in results]
        self._persistent_cache.set("class_search", cache_key, serializable)
        return results

    def resolve_class(
        self,
        *,
        query: str | None = None,
        dictionary_uri: str | None = None,
        class_uri: str | None = None,
    ) -> BSDDClassData:
        """Resolve classe por URI ou por busca textual controlada."""
        if class_uri:
            cached = self._persistent_cache.get("class_uri", class_uri)
            if isinstance(cached, dict):
                return BSDDClassData.model_validate(cached)

            result = self._resolve_class_by_uri(class_uri)
            self._persistent_cache.set("class_uri", class_uri, result.model_dump())
            return result

        if query:
            effective_dictionary_uri = dictionary_uri or self._resolve_dictionary_uri("IFC")
            matches = self.search_classes_text(query, domain=effective_dictionary_uri or "IFC")
            if not matches:
                return BSDDClassData(
                    display_name=query.strip(),
                    dictionary_uri=effective_dictionary_uri,
                    source_origin="bsdd_search",
                    status="unresolved",
                    review_required=True,
                )
            if len(matches) == 1:
                return matches[0]
            top = matches[0]
            return top.model_copy(update={"status": "review_required", "review_required": True})

        return BSDDClassData(
            display_name="",
            dictionary_uri=dictionary_uri,
            source_origin="bsdd_search",
            status="unresolved",
            review_required=True,
        )

    def resolve_property(self, property_uri: str) -> BSDDPropertyData:
        """Resolve propriedade por URI oficial e retorna metadados estruturados."""
        cached = self._persistent_cache.get("property_uri", property_uri)
        if isinstance(cached, dict):
            return BSDDPropertyData.model_validate(cached)

        data = self._get_cached_or_fetch(
            cache_key=f"property_resolve:{property_uri}",
            url="/api/Property/v4",
            params={"uri": property_uri},
        )
        if data is None:
            result = BSDDPropertyData(
                canonical_uri=None,
                display_name=property_uri,
                property_uri=property_uri,
                source_origin="bsdd_property_uri",
                status="unresolved",
                review_required=True,
            )
            self._persistent_cache.set("property_uri", property_uri, result.model_dump())
            return result

        result = self._property_from_payload(data, property_uri=property_uri)
        self._persistent_cache.set("property_uri", property_uri, result.model_dump())
        return result

    def get_class_metadata(self, class_uri: str) -> BSDDClassData:
        """Retorna metadados de uma classe a partir de sua URI."""
        return self.resolve_class(class_uri=class_uri)

    def get_class_properties_structured(self, class_uri: str) -> list[BSDDPropertyData]:
        """Retorna propriedades estruturadas de uma classe."""
        cached = self._persistent_cache.get("class_properties_structured", class_uri)
        if isinstance(cached, list):
            return [BSDDPropertyData.model_validate(item) for item in cached]

        data = self._get_cached_or_fetch(
            cache_key=f"class_properties:{class_uri}",
            url="/api/Class/Properties/v1",
            params={"ClassUri": class_uri},
        )
        if data is None:
            return []

        raw_properties = data.get("classProperties") or data.get("ClassProperties") or []
        properties = [self._property_from_payload(item) for item in raw_properties]
        self._persistent_cache.set(
            "class_properties_structured",
            class_uri,
            [item.model_dump() for item in properties],
        )
        return properties

    # ------------------------------------------------------------------
    # Wrappers legados
    # ------------------------------------------------------------------

    def search_class(self, query: str, domain: str = "IFC") -> list[dict[str, Any]]:
        """Compatibilidade legada: retorna dicts simples para o context builder."""
        return [
            {
                "name": item.code or item.display_name,
                "uri": item.class_uri or item.canonical_uri,
                "domain": item.dictionary_name or domain,
            }
            for item in self.search_classes_text(query, domain=domain)
        ]

    def get_class_properties(self, class_uri: str) -> list[BSDDProperty]:
        """Compatibilidade legada: converte propriedades estruturadas para BSDDProperty."""
        return [
            BSDDProperty(
                name=item.display_name,
                code=item.code,
                uri=item.canonical_uri or item.property_uri,
                data_type=item.data_type,
                unit=item.unit,
                allowed_values=item.allowed_values,
                description=item.description,
            )
            for item in self.get_class_properties_structured(class_uri)
        ]

    def get_property_values(self, property_uri: str) -> list[str]:
        """Compatibilidade legada: retorna apenas allowed_values."""
        result = self.resolve_property(property_uri)
        return result.allowed_values or []

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _resolve_class_by_uri(self, class_uri: str) -> BSDDClassData:
        meta = self._find_class_in_search_backfill(class_uri)
        if meta is not None:
            return meta
        classification = DEFAULT_SOURCE_POLICY.classify(class_uri)
        return BSDDClassData(
            canonical_uri=class_uri if classification.is_official else None,
            class_uri=class_uri,
            display_name=class_uri.rstrip("/").split("/")[-1],
            dictionary_uri=None,
            source_origin="bsdd_class_uri",
            status="review_required" if classification.is_forbidden else "resolved",
            review_required=not classification.is_official,
        )

    def _find_class_in_search_backfill(self, class_uri: str) -> BSDDClassData | None:
        raw_search_cache = self._cache.get("last_class_search_items")
        if not isinstance(raw_search_cache, list):
            return None
        for item in raw_search_cache:
            uri = item.get("uri") or item.get("Uri")
            if uri == class_uri:
                return self._class_from_search_item(item, item.get("dictionaryUri") or item.get("DictionaryUri"))
        return None

    def _class_from_search_item(
        self,
        item: dict[str, Any],
        fallback_dictionary_uri: str | None = None,
        alias: str | None = None,
    ) -> BSDDClassData:
        uri = item.get("uri") or item.get("Uri")
        display_name = (
            item.get("name")
            or item.get("Name")
            or item.get("referenceCode")
            or item.get("ReferenceCode")
            or ""
        )
        code = item.get("referenceCode") or item.get("ReferenceCode") or self._extract_code(uri)
        dictionary_uri = (
            item.get("dictionaryUri")
            or item.get("DictionaryUri")
            or item.get("dictionaryNamespaceUri")
            or item.get("DictionaryNamespaceUri")
            or fallback_dictionary_uri
        )
        classification = DEFAULT_SOURCE_POLICY.classify(uri)
        return BSDDClassData(
            canonical_uri=uri if classification.is_official else None,
            class_uri=uri,
            display_name=str(display_name),
            code=str(code) if code is not None else None,
            dictionary_uri=dictionary_uri,
            dictionary_name=item.get("dictionaryName") or item.get("DictionaryName"),
            description=item.get("definition") or item.get("Definition") or item.get("description") or item.get("Description"),
            source_origin="bsdd_search",
            status="resolved" if classification.is_official else "review_required",
            review_required=not classification.is_official,
            aliases=[alias] if alias else [],
        )

    def _property_from_payload(
        self,
        item: dict[str, Any],
        property_uri: str | None = None,
    ) -> BSDDPropertyData:
        uri = (
            property_uri
            or item.get("propertyUri")
            or item.get("PropertyUri")
            or item.get("uri")
            or item.get("Uri")
        )
        allowed_values_raw = item.get("allowedValues") or item.get("AllowedValues") or []
        values_source = allowed_values_raw if isinstance(allowed_values_raw, list) else []
        allowed_values = [
            str(value.get("value") or value.get("Value") or value)
            for value in values_source
            if value is not None
        ] or None
        classification = DEFAULT_SOURCE_POLICY.classify(uri)
        return BSDDPropertyData(
            canonical_uri=uri if classification.is_official else None,
            property_uri=uri,
            display_name=str(item.get("name") or item.get("Name") or self._extract_code(uri) or ""),
            code=self._extract_code(uri),
            dictionary_uri=item.get("dictionaryUri") or item.get("DictionaryUri"),
            data_type=item.get("dataType") or item.get("DataType"),
            unit=self._extract_unit(item),
            allowed_values=allowed_values,
            description=(
                item.get("description")
                or item.get("Description")
                or item.get("definition")
                or item.get("Definition")
            ),
            source_origin="bsdd_property_uri",
            status="resolved" if classification.is_official else "review_required",
            review_required=not classification.is_official,
        )

    def _resolve_dictionary_uri(self, domain: str | None) -> str | None:
        if not domain:
            return None
        normalized_domain = domain.strip()
        if not normalized_domain:
            return None
        if normalized_domain.startswith(("http://", "https://")):
            return normalized_domain

        persistent_key = normalized_domain.upper()
        cached_persistent = self._persistent_cache.get("dictionary_uri", persistent_key)
        if isinstance(cached_persistent, str):
            return cached_persistent

        cache_key = f"dictionary_uri:{normalized_domain.upper()}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, str):
            return cached

        fallback_uri = self._DEFAULT_DOMAIN_URIS.get(normalized_domain.upper())
        if fallback_uri:
            self._cache[cache_key] = fallback_uri
            self._persistent_cache.set("dictionary_uri", persistent_key, fallback_uri)
            return fallback_uri

        data = self._get_cached_or_fetch(
            cache_key=f"dictionary_lookup:{normalized_domain.upper()}",
            url="/api/Dictionary/v1",
            params={"SearchText": normalized_domain},
        )
        items = data.get("dictionaries") or data.get("Dictionaries") or [] if data is not None else []
        target = normalized_domain.upper()
        for item in items:
            item_uri = item.get("uri") or item.get("Uri")
            item_name = str(item.get("name") or item.get("Name") or "").strip().upper()
            item_code = str(item.get("code") or item.get("Code") or "").strip().upper()
            if item_uri and target in {item_name, item_code}:
                self._cache[cache_key] = item_uri
                self._persistent_cache.set("dictionary_uri", persistent_key, item_uri)
                return item_uri
        return None

    def _get_cached_or_fetch(self, cache_key: str, url: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if isinstance(cached, dict):
                logger.debug("bSDD cache hit: {}", cache_key)
                return cached

        if url in self._unsupported_paths:
            logger.debug("bSDD endpoint desabilitado apos 404: {}", url)
            return None

        filtered_params = {key: value for key, value in params.items() if value is not None}
        try:
            logger.debug("bSDD GET {} params={}", url, filtered_params)
            response = self._client.get(url, params=filtered_params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                logger.warning("bSDD retornou JSON inesperado em {}: {}", url, type(payload).__name__)
                return None
            self._cache[cache_key] = payload
            if url == "/api/Class/Search/v1":
                self._cache["last_class_search_items"] = payload.get("classes") or payload.get("Classes") or []
            return payload
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                self._unsupported_paths.add(url)
                logger.warning("bSDD endpoint nao encontrado em {}: {}", url, exc)
            else:
                logger.warning("bSDD erro HTTP em {}: {}", url, exc)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            logger.warning("bSDD indisponivel em {}: {}", url, exc)
        except Exception as exc:
            logger.warning("Falha inesperada ao consultar bSDD em {}: {}", url, exc)
        return None

    def _extract_unit(self, item: dict[str, Any]) -> str | None:
        unit = item.get("unit") or item.get("Unit")
        if isinstance(unit, str):
            return unit
        if isinstance(unit, dict):
            return unit.get("name") or unit.get("Name") or unit.get("symbol") or unit.get("Symbol")
        units = item.get("units") or item.get("Units")
        if isinstance(units, list) and units:
            first_unit = units[0]
            if isinstance(first_unit, str):
                return first_unit
            if isinstance(first_unit, dict):
                return (
                    first_unit.get("name")
                    or first_unit.get("Name")
                    or first_unit.get("symbol")
                    or first_unit.get("Symbol")
                )
        return None

    def _extract_code(self, uri: str | None) -> str | None:
        if not uri:
            return None
        return uri.rstrip("/").split("/")[-1] or None

    @classmethod
    def is_trusted_uri(cls, uri: str | None) -> bool:
        classification = DEFAULT_SOURCE_POLICY.classify(uri)
        return classification.category in {"official", "trusted_secondary"} and not classification.is_documentation
