"""Resolução de binding com estados explícitos (M1-05).

Procura o caminho literal (conjunto e nome exatos, com caixa e acentos) e, só na
falta dele, aliases de resolução aprovados e dentro do escopo. Avalia a
aplicabilidade de cada candidato e decide apenas quando resta um único uso (binding)
elegível: aplicável e com o schema pedido declarado. Usos de outro schema ficam como
candidatos informativos; vários aliases do mesmo binding são um só uso. Caso contrário
devolve ambiguidade, ausência ou falta de suporte com motivos. Nunca escolhe o
primeiro, nunca casa por semelhança textual e nunca produz URI.
"""

from src.domain_catalog.applicability import ApplicabilityContext, evaluate_applicability
from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import (
    BindingRequest,
    CatalogReleaseRef,
    ResolutionCandidate,
    ResolutionResult,
    ResolutionStatus,
)
from src.domain_catalog.models import RESOLUTION_ALIAS_PURPOSES, AliasMapping, IFCBinding

_FACET_CARRIERS: dict[str, frozenset[str]] = {
    "attribute": frozenset({"attribute"}),
    "property": frozenset({"property", "quantity", "property_or_quantity"}),
    "classification": frozenset({"classification"}),
    "material": frozenset({"material"}),
}


class Resolver:
    """Índices de um conteúdo fixo para resolver muitos requisitos sem recalcular."""

    def __init__(self, content: CatalogContent, catalog: CatalogReleaseRef | None = None) -> None:
        """Indexa bindings por caminho, aliases por termo e decisões por binding."""
        self._catalog = catalog
        self._concepts = {concept.id: concept for concept in content.concepts}
        self._rules = {rule.id: rule for rule in content.applicability_rules}
        self._bindings = {binding.id: binding for binding in content.bindings}
        self._by_field: dict[str, list[IFCBinding]] = {}
        for binding in content.bindings:
            self._by_field.setdefault(binding.field_name, []).append(binding)
        self._aliases: dict[str, list[AliasMapping]] = {}
        for alias in content.aliases:
            if alias.purpose in RESOLUTION_ALIAS_PURPOSES:
                self._aliases.setdefault(alias.term, []).append(alias)
        self._decisions: dict[str, list[str]] = {}
        for decision in content.reconciliation_decisions:
            for binding_id in decision.affected_binding_ids:
                self._decisions.setdefault(binding_id, []).append(decision.id)

    def _literal_bindings(self, request: BindingRequest) -> list[IFCBinding]:
        carriers = _FACET_CARRIERS[request.facet]
        return [
            binding
            for binding in self._by_field.get(request.field_name, [])
            if binding.carrier_kind in carriers
            and (request.set_name is None or binding.set_name == request.set_name)
        ]

    @staticmethod
    def _alias_in_scope(alias: AliasMapping, request: BindingRequest) -> bool:
        scope = alias.scope
        if scope.set_names is not None and request.set_name not in scope.set_names:
            return False
        if scope.entity_classes is not None and (
            request.entity is None
            or request.entity.upper() not in {name.upper() for name in scope.entity_classes}
        ):
            return False
        return scope.schemas is None or request.ifc_schema in scope.schemas

    def _candidate(
        self, binding: IFCBinding, request: BindingRequest, alias: AliasMapping | None
    ) -> tuple[ResolutionCandidate, bool]:
        """Candidato com aplicabilidade e motivos; o booleano diz se pode ser escolhido."""
        context = ApplicabilityContext(
            ifc_schema=request.ifc_schema,
            entity=request.entity,
            predefined_type=request.predefined_type,
            facts=request.facts,
        )
        applicability = evaluate_applicability(self._rules[binding.applicability_rule_id], context)
        schema_declared = request.ifc_schema in binding.declared_schemas
        reasons = list(applicability.reasons)
        if not schema_declared:
            reasons.append(f"schema {request.ifc_schema} não declarado no binding")
        usable = True
        if alias is not None and alias.lifecycle != "approved":
            usable = False
            reasons.append(f"alias {alias.term!r} não aprovado ({alias.lifecycle})")
        candidate = ResolutionCandidate(
            binding_id=binding.id,
            concept_id=binding.concept_id,
            concept_code=self._concepts[binding.concept_id].code,
            match="literal_path" if alias is None else "alias",
            alias_id=None if alias is None else alias.id,
            applicability=applicability.state,
            schema_declared=schema_declared,
            carrier_status=binding.carrier_status,
            lifecycle=binding.lifecycle,
            write_enabled=binding.write_enabled,
            reasons=tuple(reasons),
        )
        return candidate, usable

    def _limitations(self, binding: IFCBinding, candidate: ResolutionCandidate) -> tuple[str, ...]:
        """Limites que acompanham uma resolução única; nada aqui autoriza escrita."""
        limitations: list[str] = []
        if candidate.match == "alias":
            limitations.append(
                "resolvido por alias aprovado: o caminho exigido pelo requisito continua "
                "sendo o literal pedido"
            )
        if binding.carrier_status != "approved":
            limitations.append("portador pendente de reconciliação")
        if binding.carrier_kind == "property_or_quantity":
            limitations.append(
                "portador não determinado entre propriedade (IfcPropertySet) e quantidade "
                "(IfcElementQuantity): nenhum dos dois é eleito nem autorizado"
            )
        if not binding.write_enabled:
            limitations.append("escrita desabilitada para este binding")
        if binding.scope == "unspecified":
            limitations.append(
                "escopo ocorrência/tipo não esclarecido pela fonte: não autoriza escrever na "
                "ocorrência, no tipo nem nos dois"
            )
        elif binding.scope == "occurrence_or_type":
            limitations.append(
                "escopo admite ocorrência ou tipo: escrita futura exige destino explícito e "
                "avaliação do alcance em tipo compartilhado"
            )
        rule = self._rules[binding.applicability_rule_id]
        concept = self._concepts[binding.concept_id]
        if {binding.lifecycle, rule.lifecycle, concept.lifecycle} - {"approved"}:
            limitations.append("conteúdo fora de release aprovado; resultado não operacional")
        limitations.append("schema declarado pela curadoria; capacidade de leitura não ensaiada")
        return tuple(limitations)

    def resolve(self, request: BindingRequest) -> ResolutionResult:
        """Resolve o caminho pedido no contexto informado.

        Todos os candidatos são devolvidos com seus motivos, mas a unicidade só é decidida
        entre os elegíveis: alias aprovado (ou caminho literal), aplicabilidade não
        excluída e schema pedido declarado. Usos de outro schema são informativos e não
        criam ambiguidade; vários aliases do mesmo binding contam como um único uso.
        """
        found: list[tuple[ResolutionCandidate, bool]] = [
            self._candidate(binding, request, None) for binding in self._literal_bindings(request)
        ]
        if not found:
            carriers = _FACET_CARRIERS[request.facet]
            for alias in self._aliases.get(request.field_name, []):
                target = self._bindings.get(alias.target_binding_id or "")
                if (
                    target is not None
                    and target.carrier_kind in carriers
                    and self._alias_in_scope(alias, request)
                ):
                    found.append(self._candidate(target, request, alias))
        found.sort(key=lambda item: (item[0].binding_id, item[0].alias_id or ""))
        candidates = tuple(candidate for candidate, _ in found)
        in_context = [
            candidate
            for candidate, usable in found
            if usable and candidate.applicability != "not_applicable"
        ]
        eligible: dict[str, list[ResolutionCandidate]] = {}
        for candidate in in_context:
            if candidate.schema_declared:
                eligible.setdefault(candidate.binding_id, []).append(candidate)
        decision_ids = tuple(
            sorted({d for c in candidates for d in self._decisions.get(c.binding_id, [])})
        )

        def unresolved(status: ResolutionStatus, *reasons: str) -> ResolutionResult:
            return ResolutionResult(
                status=status,
                request=request,
                candidates=candidates,
                reasons=reasons,
                decision_ids=decision_ids,
                catalog=self._catalog,
            )

        if not candidates:
            return unresolved("unmapped", "nenhum uso cadastrado para o caminho")
        if not in_context:
            return unresolved("unmapped", "nenhum uso aprovado se aplica ao contexto informado")
        if not eligible:
            return unresolved(
                "unsupported",
                f"schema {request.ifc_schema} não declarado em nenhum uso possível no contexto",
            )
        if len(eligible) > 1:
            return unresolved(
                "ambiguous", f"{len(eligible)} usos possíveis; nenhum é escolhido automaticamente"
            )
        ((binding_id, matches),) = eligible.items()
        chosen = matches[0]
        if chosen.applicability == "indeterminate":
            return unresolved(
                "ambiguous",
                "1 uso possível com aplicabilidade indeterminada; falta informação para "
                "confirmá-lo",
                *chosen.reasons,
            )
        binding = self._bindings[binding_id]
        literal = chosen.match == "literal_path"
        return ResolutionResult(
            status="exact" if literal else "approved_mapping",
            request=request,
            binding_id=binding.id,
            concept_id=binding.concept_id,
            alias_ids=() if literal else tuple(c.alias_id for c in matches if c.alias_id),
            candidates=candidates,
            limitations=self._limitations(binding, chosen),
            decision_ids=tuple(sorted(self._decisions.get(binding.id, []))),
            catalog=self._catalog,
        )


def resolve_binding(
    content: CatalogContent, request: BindingRequest, catalog: CatalogReleaseRef | None = None
) -> ResolutionResult:
    """Resolve um único pedido; para lotes, reutilize um ``Resolver``."""
    return Resolver(content, catalog).resolve(request)
