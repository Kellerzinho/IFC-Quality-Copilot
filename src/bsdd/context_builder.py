"""Construcao de contexto bSDD para sugestoes guiadas."""

from __future__ import annotations

import re

import httpx
from loguru import logger

from src.bsdd.client import BSDDClient
from src.models import BSDDClassification, BSDDContext, BSDDProperty, IDSContext, Issue
from src.semantic.property_match import property_match_key, strip_boolean_prefix
from src.semantic_registry.registry import DEFAULT_SEMANTIC_REGISTRY


def format_ids_context(ids_ctx: IDSContext | None) -> str:
    """Formata IDSContext como bloco de texto para o prompt."""
    if ids_ctx is None:
        return ""

    lines = [
        "---",
        "REQUISITO IDS VIOLADO:",
        f'Especificacao: "{ids_ctx.specification_name}"',
        f"Check: {ids_ctx.requirement_text}",
    ]
    if ids_ctx.check_pset:
        lines.append(f"Pset esperado: {ids_ctx.check_pset}")
    if ids_ctx.check_property:
        lines.append(f"Propriedade esperada: {ids_ctx.check_property}")
    lines.append(f"Severidade: {ids_ctx.severity}")
    lines.append("---")
    return "\n".join(lines)


def format_bsdd_context(context: BSDDContext | None) -> str:
    """Formata BSDDContext como bloco de texto para o prompt."""
    if context is None:
        return ""

    if (
        not context.class_name
        and not context.class_uri
        and not context.related_properties
        and not context.classification_suggestions
    ):
        return ""

    header_bits = []
    if context.class_name:
        header_bits.append(f"classe: {context.class_name}")
    if context.class_uri:
        header_bits.append(f"URI: {context.class_uri}")
    header = "VOCABULARIO bSDD"
    if header_bits:
        header += f" ({', '.join(header_bits)})"

    lines = ["---", f"{header}:"]

    if context.related_properties:
        pset_name = _infer_pset_name(context.related_properties)
        if pset_name:
            lines.append(f"Propriedades validas para {pset_name}:")
        else:
            lines.append("Propriedades validas:")
        for prop in context.related_properties:
            lines.append(f"- {_format_property_line(prop)}")

    if context.classification_suggestions:
        lines.append("Classificacoes relevantes:")
        for classification in context.classification_suggestions:
            parts = [classification.name]
            if classification.code:
                parts.append(f"codigo: {classification.code}")
            if classification.system_name:
                parts.append(f"sistema: {classification.system_name}")
            if classification.uri:
                parts.append(f"URI: {classification.uri}")
            lines.append(f"- {', '.join(parts)}")

    lines.append("---")
    return "\n".join(lines)


def build_grounding_block(
    ids_context: IDSContext | None,
    bsdd_context: BSDDContext | None,
) -> str:
    """Combina os contextos IDS e bSDD para grounding do prompt."""
    blocks: list[str] = []
    ids_block = format_ids_context(ids_context)
    if ids_block:
        blocks.append(ids_block)

    bsdd_block = format_bsdd_context(bsdd_context)
    if bsdd_block:
        blocks.append(bsdd_block)

    return "\n\n".join(blocks)


class BSDDContextBuilder:
    """Constroi BSDDContext para uma issue consultando o bSDD."""

    _SPACE_SEARCH_HINTS = (
        "space",
        "room",
        "omniclass table 13",
        "uniclass spaces",
    )

    def __init__(self, client: BSDDClient):
        self._client = client
        self.client = client

    def build(self, issue: Issue, ids_context: IDSContext | None = None) -> BSDDContext:
        """Constroi contexto bSDD baseado no element_class e issue_type da issue."""
        queries = self._build_search_queries(issue, ids_context)
        domain = self._resolve_domain(issue)
        context = BSDDContext(
            issue_id=issue.id,
            element_class=issue.element_class,
            raw_query=queries[0],
            domain_name=domain,
            source_status="empty",
        )

        class_results: list[dict[str, str]] = []
        for query in queries:
            try:
                class_results = self._client.search_class(query, domain=domain or "IFC")
            except (httpx.TimeoutException, httpx.ConnectError, OSError):
                context.source_status = "offline"
                return context
            except Exception:
                context.source_status = "offline"
                return context
            if class_results:
                context.raw_query = query
                break

        if not class_results:
            logger.debug(
                "bSDD sem resultado para {} apos {} consulta(s): {}",
                issue.element_class,
                len(queries),
                queries,
            )
            return context

        primary_match = self._select_primary_match(class_results, issue.element_class)
        if primary_match is not None:
            context.class_name = primary_match.get("name")
            context.class_uri = self._canonicalize_class_uri(
                context.class_name,
                primary_match.get("uri"),
                context.domain_name,
            )
            if not context.domain_name:
                context.domain_name = primary_match.get("domain")

        context.classification_suggestions = self._build_classifications(
            issue=issue,
            class_results=class_results,
            primary_match=primary_match,
            domain=context.domain_name,
        )

        if primary_match is not None and primary_match.get("uri"):
            properties = self._load_properties(primary_match["uri"])
            properties = self._canonicalize_properties(properties, context.domain_name)
            relevant = self._filter_properties(issue, ids_context, properties)
            context.related_properties = self._enrich_allowed_values(relevant)
            context.source_uris = self._collect_source_uris(
                class_uri=context.class_uri,
                properties=context.related_properties,
                classifications=context.classification_suggestions,
            )
            # A classe resolveu ao vivo: a fonte oficial foi consultada e sua URI
            # canonica entra no grounding. Reportar "empty" aqui confundiria
            # "nao consultei" com "consultei e o dicionario nao tem a propriedade"
            # — o caso de IfcSpace.Category, por exemplo.
            context.source_status = "live"
            return context

        context.source_uris = self._collect_source_uris(
            class_uri=None,
            properties=[],
            classifications=context.classification_suggestions,
        )
        if context.classification_suggestions:
            context.source_status = "live"
        return context

    def build_context_text(self, context: BSDDContext) -> str:
        """Formata BSDDContext como bloco de texto estruturado para injecao no prompt."""
        return format_bsdd_context(context)

    def _build_search_queries(
        self, issue: Issue, ids_context: IDSContext | None = None
    ) -> list[str]:
        """Monta as consultas candidatas ao bSDD, da mais especifica a mais ampla.

        O endpoint de busca do bSDD procura **classes**: consultas do tipo
        ``"IfcWall FireRating"`` nao casam nada. Por isso a classe IFC (com os
        alias de classes depreciadas ja resolvidos) e sempre a ultima candidata,
        garantindo que exista grounding mesmo quando as consultas especificas
        nao retornam nada.
        """
        candidates: list[str] = []
        base_class = self._base_ifc_class(issue.element_class)

        specific_query = issue.context.get("classification_query")
        if specific_query:
            normalized = self._normalize_search_text(str(specific_query))
            if normalized:
                candidates.append(normalized)

        issue_type = issue.issue_type
        if issue_type == "pset_missing":
            target_property = self._target_property_name(issue, ids_context)
            if target_property:
                candidates.append(f"{base_class} {target_property}")
        elif issue_type in {"system_unclassified", "classification_missing"}:
            system_hint = issue.context.get("system_name") or issue.context.get("classification_system")
            if system_hint:
                candidates.append(f"{base_class} {system_hint}")
            candidates.append(f"{base_class} classification")
        elif issue_type == "space_unnamed":
            candidates.extend([
                "IfcSpace OmniClass Table 13",
                "IfcSpace Uniclass Spaces",
                "IfcSpace room space classification",
            ])

        if ids_context is not None and ids_context.check_property:
            candidates.append(f"{base_class} {ids_context.check_property}")

        # O nome do elemento no modelo (familia Revit, em portugues) NAO entra
        # aqui: a busca textual do bSDD casa qualquer coisa e devolve classe
        # oficial errada — "Room" casa IfcCooledBeamPASSIVE e "Sala" casa
        # IfcEvaporativeCooler..., verificado ao vivo. Grounding falso e pior
        # que ausencia de grounding.
        candidates.append(base_class)

        ordered: list[str] = []
        for candidate in candidates:
            cleaned = self._normalize_search_text(candidate) or candidate.strip()
            if cleaned and cleaned not in ordered:
                ordered.append(cleaned)
        return ordered or [base_class]

    def _base_ifc_class(self, element_class: str) -> str:
        """Resolve alias de classes IFC ausentes no dicionario oficial.

        ``IfcWallStandardCase`` e afins foram depreciados no IFC4 e nao existem
        no dicionario IFC 4.3 do bSDD — buscar por eles retorna vazio.
        """
        cleaned = (element_class or "").strip()
        if cleaned.endswith("StandardCase"):
            return cleaned[: -len("StandardCase")]
        return cleaned

    def _normalize_search_text(self, text: str) -> str:
        """Remove ruido de nomes de familia/tipo vindos do modelo IFC."""
        cleaned = text.strip()
        cleaned = re.sub(r"[_:]+", " ", cleaned)
        cleaned = re.sub(r"\b\d+\b", " ", cleaned)
        cleaned = re.sub(r"\bgrowarq\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b[A-Z]{2,}\d+\b", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        tokens = [token for token in cleaned.split() if len(token) >= 3 and not token.isdigit()]
        if not tokens:
            return ""
        return " ".join(tokens[:8])

    def _resolve_domain(self, issue: Issue) -> str | None:
        domain = issue.context.get("bsdd_domain") or issue.context.get("domain")
        if isinstance(domain, str) and domain.strip():
            return domain.strip()
        return "IFC"

    def _select_primary_match(
        self,
        class_results: list[dict[str, str]],
        element_class: str,
    ) -> dict[str, str] | None:
        """Escolhe a classe bSDD que corresponde a classe IFC do elemento.

        A busca do bSDD e textual e devolve candidatos por relevancia, nao por
        equivalencia: aceitar o primeiro resultado cegamente injeta vocabulario
        oficial de outra entidade no prompt. So vale como classe primaria quem
        casa com a classe IFC (com o prefixo ``Ifc`` opcional).
        """
        accepted = {
            self._class_match_key(element_class),
            self._class_match_key(self._base_ifc_class(element_class)),
        }
        for item in class_results:
            if self._class_match_key(str(item.get("name") or "")) in accepted:
                return item
        return None

    @staticmethod
    def _class_match_key(name: str) -> str:
        """Normaliza nome de classe para comparacao: sem prefixo Ifc, sem caixa."""
        cleaned = name.strip().casefold()
        if cleaned.startswith("ifc"):
            cleaned = cleaned[3:]
        return cleaned

    def _load_properties(self, class_uri: str) -> list[BSDDProperty]:
        """Busca as propriedades da classe, sem enriquecer valores permitidos."""
        try:
            return self._client.get_class_properties(class_uri)
        except (httpx.TimeoutException, httpx.ConnectError, OSError):
            return []
        except Exception:
            return []

    def _enrich_allowed_values(self, properties: list[BSDDProperty]) -> list[BSDDProperty]:
        """Completa os valores permitidos das propriedades que ficam no contexto.

        Roda depois do filtro: enriquecer antes custaria uma chamada HTTP por
        propriedade da classe (233 no caso de IfcWall) para descartar quase todas.
        """
        enriched: list[BSDDProperty] = []
        for prop in properties:
            if prop.allowed_values or not prop.uri:
                enriched.append(prop)
                continue
            try:
                allowed_values = self._client.get_property_values(prop.uri)
            except Exception:
                allowed_values = []
            if allowed_values:
                enriched.append(prop.model_copy(update={"allowed_values": allowed_values}))
            else:
                enriched.append(prop)
        return enriched

    def _filter_properties(
        self,
        issue: Issue,
        ids_context: IDSContext | None,
        properties: list[BSDDProperty],
    ) -> list[BSDDProperty]:
        if issue.issue_type != "pset_missing":
            return properties

        target_property = self._target_property_name(issue, ids_context)
        if not target_property:
            return properties

        normalized_target = self._property_match_key(target_property)
        exact = [
            prop for prop in properties
            if self._property_match_key(prop.name) == normalized_target
        ]
        if exact:
            return exact

        # Os psets do IFC nao sao consistentes entre si (Pset_WallCommon usa
        # IsLoadBearing, Pset_SlabCommon usa LoadBearing) e o bSDD guarda a forma
        # sem o prefixo booleano.
        sem_prefixo = self._strip_boolean_prefix(normalized_target)
        if sem_prefixo != normalized_target:
            por_prefixo = [
                prop for prop in properties
                if self._strip_boolean_prefix(self._property_match_key(prop.name)) == sem_prefixo
            ]
            if por_prefixo:
                return por_prefixo

        # O bSDD tem variantes ("Thermal Transmittance Summer") cuja descricao
        # menciona a propriedade pedida: so valem quando nao ha match exato.
        by_description = [
            prop for prop in properties
            if target_property.lower() in (prop.description or "").lower()
        ]
        if by_description:
            return by_description
        # Sem correspondencia, devolver a lista inteira encheria o prompt com
        # centenas de propriedades irrelevantes (IfcWall tem 233 no bSDD).
        return []

    # A regra de casamento IFC × bSDD vive em src/semantic/property_match.py
    # (fonte única desde 2026-08-04); estes wrappers preservam a API interna.
    _property_match_key = staticmethod(property_match_key)
    _strip_boolean_prefix = staticmethod(strip_boolean_prefix)

    def _target_property_name(self, issue: Issue, ids_context: IDSContext | None) -> str | None:
        if ids_context is not None and ids_context.check_property:
            return ids_context.check_property
        check_property = issue.context.get("check_property")
        if isinstance(check_property, str) and check_property.strip():
            return check_property.strip()
        return None

    def _build_classifications(
        self,
        issue: Issue,
        class_results: list[dict[str, str]],
        primary_match: dict[str, str] | None,
        domain: str | None,
    ) -> list[BSDDClassification]:
        if issue.issue_type not in {"space_unnamed", "system_unclassified", "classification_missing"}:
            return []

        relevant_results = class_results
        if issue.issue_type == "space_unnamed":
            # Sem fallback para class_results: sugerir uma classe qualquer que
            # nao seja classificacao de espaco injeta termo oficial irrelevante.
            relevant_results = [
                item for item in class_results
                if self._is_space_classification(item)
            ]
            if primary_match is not None:
                # Sem fallback: quando a classe IFC e o unico resultado, oferece-la
                # como candidato instruiria o LLM a responder "IfcSpace" onde se
                # espera "Sala de Estar".
                relevant_results = [
                    item for item in relevant_results
                    if item.get("uri") != primary_match.get("uri")
                ]
        elif primary_match is not None:
            relevant_results = [
                item for item in class_results
                if item.get("uri") != primary_match.get("uri")
            ] or class_results

        suggestions: list[BSDDClassification] = []
        for item in relevant_results[:5]:
            name = item.get("name")
            if not name:
                continue
            system_name = item.get("domain") or domain
            suggestions.append(
                BSDDClassification(
                    name=name,
                    code=self._extract_code(item),
                    uri=self._canonicalize_class_uri(name, item.get("uri"), system_name),
                    system_name=system_name,
                )
            )
        return suggestions

    def _canonicalize_class_uri(
        self,
        class_name: str | None,
        uri: str | None,
        domain: str | None,
    ) -> str | None:
        """Prefere URI canonica IFC quando o dominio e o dicionario IFC."""
        if str(domain or "").strip().upper() != "IFC":
            return uri
        reference = DEFAULT_SEMANTIC_REGISTRY.resolve_ifc_class(class_name or "")
        return reference.canonical_uri if reference is not None else uri

    def _canonicalize_properties(
        self,
        properties: list[BSDDProperty],
        domain: str | None,
    ) -> list[BSDDProperty]:
        """Converte propriedades IFC para URIs canonicas do identifier.buildingsmart."""
        if str(domain or "").strip().upper() != "IFC":
            return properties

        normalized: list[BSDDProperty] = []
        for prop in properties:
            reference = DEFAULT_SEMANTIC_REGISTRY.resolve_ifc_property(prop.name)
            normalized.append(
                prop.model_copy(update={"uri": reference.canonical_uri if reference is not None else prop.uri})
            )
        return normalized

    def _is_space_classification(self, item: dict[str, str]) -> bool:
        haystack = " ".join(
            str(item.get(key) or "")
            for key in ("name", "domain", "uri")
        ).lower()
        return any(hint in haystack for hint in self._SPACE_SEARCH_HINTS)

    def _extract_code(self, item: dict[str, str]) -> str | None:
        uri = item.get("uri")
        if not uri:
            return None
        return uri.rstrip("/").split("/")[-1] or None

    def _collect_source_uris(
        self,
        class_uri: str | None,
        properties: list[BSDDProperty],
        classifications: list[BSDDClassification],
    ) -> list[str]:
        seen: list[str] = []
        for uri in [class_uri, *[prop.uri for prop in properties], *[cls.uri for cls in classifications]]:
            if uri and uri not in seen:
                seen.append(uri)
        return seen


def _infer_pset_name(properties: list[BSDDProperty]) -> str | None:
    for prop in properties:
        for text in (prop.description, prop.uri):
            if not text:
                continue
            match = re.search(r"(Pset_[A-Za-z0-9_]+)", text)
            if match:
                return match.group(1)
    return None


def _format_property_line(prop: BSDDProperty) -> str:
    parts = [prop.name]
    meta = []
    if prop.data_type:
        meta.append(prop.data_type.lower())
    if prop.unit:
        meta.append(prop.unit)
    if meta:
        parts.append(f"({', '.join(meta)})")
    line = " ".join(parts)
    if prop.allowed_values:
        line += f", valores: {', '.join(prop.allowed_values)}"
    return line
