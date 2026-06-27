"""Modelos de dados Pydantic para o IFC Quality Copilot."""

import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


def _content_hash(*parts: str) -> str:
    """Hash SHA1 (12 chars) de um conteúdo-chave, para ids determinísticos e reprodutíveis."""
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


class MaterialLayer(BaseModel):
    """Camada individual de um material composto."""

    name: str
    thickness_m: float
    material_category: str | None = None  # "concreto", "alvenaria", "isolamento"


class MaterialInfo(BaseModel):
    """Informações de material de um elemento IFC."""

    material_name: str | None = None
    layers: list[MaterialLayer] = Field(default_factory=list)
    total_thickness_m: float | None = None


class GeometryInfo(BaseModel):
    """Informações geométricas extraídas de um elemento IFC."""

    area_m2: float | None = None
    volume_m3: float | None = None
    height_m: float | None = None
    width_m: float | None = None
    thickness_m: float | None = None
    bounding_box: dict[str, float] | None = None  # {min_x, min_y, min_z, max_x, max_y, max_z}


class IFCElement(BaseModel):
    """Representação de um elemento IFC com suas propriedades e relacionamentos."""

    guid: str  # GlobalId IFC (22 chars)
    ifc_class: str  # ex: "IfcWall", "IfcSpace"
    name: str | None = None
    long_name: str | None = None  # LongName (usado em IfcSpace)
    description: str | None = None
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)  # {pset_name: {prop_name: value}}
    relationships: list[dict[str, str]] = Field(default_factory=list)  # [{type: "IfcRelFillsElement", related_guid: "xxx"}]
    geometry_info: GeometryInfo | None = None
    floor: str | None = None  # andar/pavimento
    material_info: MaterialInfo | None = None

    @field_validator("guid")
    @classmethod
    def validate_guid(cls, v: str) -> str:
        """Valida que o GUID tem exatamente 22 caracteres."""
        if len(v) != 22:
            raise ValueError(f"GUID deve ter 22 caracteres, recebido: {len(v)}")
        return v

    @property
    def short_guid(self) -> str:
        """Retorna os primeiros 8 caracteres do GUID para exibição."""
        return self.guid[:8]

    def get_pset_value(self, pset_name: str, prop_name: str) -> Any | None:
        """Retorna o valor de uma propriedade em um Pset, ou None se não existir."""
        pset = self.properties.get(pset_name)
        if pset is None:
            return None
        return pset.get(prop_name)

    def has_pset(self, pset_name: str) -> bool:
        """Retorna True se o elemento possui o Pset informado."""
        return pset_name in self.properties


_ISSUE_TYPE_LABELS: dict[str, str] = {
    "space_unnamed": "Espaço sem classificação funcional",
    "pset_missing": "Propriedade ausente",
    "relation_broken": "Relação espacial quebrada",
    "system_unclassified": "Sistema construtivo não classificado",
    "quantity_missing": "Quantidade base ausente",
    "classification_missing": "Referência de classificação ausente",
    "material_unmapped": "Material não mapeado para padrão",
    "asset_unidentified": "Equipamento sem identificação",
    "thermal_incomplete": "Dados térmicos incompletos",
}

_SEVERITY_ORDER: dict[str, int] = {
    "high": 0,
    "medium": 1,
    "low": 2,
}


class Issue(BaseModel):
    """Representa um problema de qualidade detectado em um elemento IFC."""

    id: str = ""
    element_guid: str
    element_class: str
    element_name: str | None = None
    issue_type: Literal[
        "space_unnamed",
        "pset_missing",
        "relation_broken",
        "system_unclassified",
        "quantity_missing",
        "classification_missing",
        "material_unmapped",
        "asset_unidentified",
        "thermal_incomplete",
    ]
    severity: Literal["high", "medium", "low"]
    description: str
    context: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "accepted", "edited", "rejected", "skipped"] = "pending"
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: datetime | None = None
    resolution_value: Any = None

    @model_validator(mode="before")
    @classmethod
    def _ensure_deterministic_id(cls, data: Any) -> Any:
        """Deriva um id determinístico do conteúdo-chave quando nenhum id é fornecido."""
        if isinstance(data, dict) and not data.get("id"):
            ctx = data.get("context") or {}
            data["id"] = _content_hash(
                str(data.get("element_guid", "")),
                str(data.get("issue_type", "")),
                str(ctx.get("check_pset", "")),
                str(ctx.get("check_property", "")),
            )
        return data

    @property
    def short_guid(self) -> str:
        """Retorna os primeiros 8 caracteres do GUID do elemento para exibição."""
        return self.element_guid[:8]

    @property
    def severity_order(self) -> int:
        """Retorna 0 para high, 1 para medium, 2 para low (para ordenação)."""
        return _SEVERITY_ORDER[self.severity]

    @property
    def type_label(self) -> str:
        """Retorna label legível em português para o tipo do problema."""
        return _ISSUE_TYPE_LABELS[self.issue_type]

    def to_llm_context(self) -> str:
        """Formata o contexto do problema como texto estruturado para o prompt do LLM."""
        short_guid = self.element_guid[:8]
        name_part = f", nome atual '{self.element_name}'" if self.element_name else ""
        lines = [f"{self.element_class} #{short_guid}{name_part}"]

        for key, value in self.context.items():
            lines.append(f"- {key}: {value}")

        return "\n".join(lines)

    def resolve(self, value: Any, decision: Literal["accepted", "edited", "rejected", "skipped"]) -> None:
        """Atualiza status, resolved_at e resolution_value após decisão do usuário."""
        self.status = decision
        self.resolved_at = datetime.now()
        self.resolution_value = value


class Suggestion(BaseModel):
    """Sugestão de correção gerada por LLM para um Issue."""

    label: str  # ex: "Lavabo Suíte" ou "2.48 W/(m².K)"
    value: Any  # valor a ser escrito no IFC
    justification: str  # ex: "4.2m² com WC e lavatório adjacente a dormitório"
    confidence: Literal["alta", "media", "baixa"]
    normative_ref: str | None = None  # ex: "NBR 15575-4 Tab. C.2"
    source: Literal["llm"] = "llm"
    canonical_term: str | None = None
    semantic_hint: str | None = None
    source_candidates: list[str] = Field(default_factory=list)
    review_required: bool = False
    semantic_status: Literal["resolved", "pending_review", "not_applicable"] = "not_applicable"
    semantic_source_origin: str | None = None
    bsdd_uri: str | None = None
    ids_requirement_id: str | None = None

    @property
    def confidence_emoji(self) -> str:
        """Retorna emoji colorido representando o nível de confiança."""
        return {"alta": "🟢", "media": "🟡", "baixa": "🔴"}[self.confidence]

    @property
    def confidence_order(self) -> int:
        """Retorna 0 para alta, 1 para media, 2 para baixa (para ordenação)."""
        return {"alta": 0, "media": 1, "baixa": 2}[self.confidence]


class SuggestionMetrics(BaseModel):
    """Métricas de geração de sugestão para uma issue (telemetria leve)."""

    issue_id: str
    queue_wait_ms: float = 0.0
    grounding_ms: float = 0.0
    cache_lookup_ms: float = 0.0
    llm_total_ms: float = 0.0
    ollama_load_ms: float = 0.0
    ollama_prompt_eval_ms: float = 0.0
    ollama_eval_ms: float = 0.0
    parse_ms: float = 0.0
    validation_ms: float = 0.0
    cache_hit: bool = False
    reused_from_issue_id: str | None = None
    prompt_tokens: int = 0
    output_tokens: int = 0
    final_status: str = "pending"
    group_id: str | None = None


class SuggestionSet(BaseModel):
    """Conjunto de sugestões geradas para um Issue específico."""

    issue_id: str
    suggestions: list[Suggestion] = Field(default_factory=list)  # 2-3 opções
    allow_custom: bool = True
    error: str | None = None  # se houve erro na geração
    prompt_hash: str | None = None
    metrics: SuggestionMetrics | None = None

    @property
    def has_suggestions(self) -> bool:
        """Retorna True se há pelo menos uma sugestão disponível."""
        return len(self.suggestions) > 0

    @property
    def top_suggestion(self) -> Suggestion | None:
        """Retorna a sugestão de maior confiança, ou None se não houver nenhuma."""
        if not self.suggestions:
            return None
        return sorted(self.suggestions, key=lambda s: s.confidence_order)[0]

    def get_by_index(self, index: int) -> Suggestion | None:
        """Retorna a sugestão pelo índice, ou None se fora do intervalo."""
        if 0 <= index < len(self.suggestions):
            return self.suggestions[index]
        return None


class BSDDProperty(BaseModel):
    """Representa uma propriedade relevante recuperada do bSDD."""

    name: str
    uri: str | None = None
    data_type: str | None = None
    unit: str | None = None
    allowed_values: list[str] | None = None
    description: str | None = None


class BSDDClassification(BaseModel):
    """Classificação sugerida ou recuperada do bSDD."""

    name: str
    code: str | None = None
    uri: str | None = None
    system_name: str | None = None


class BSDDClassCandidate(BSDDClassification):
    """Classe candidata recuperada do bSDD."""

    domain: str | None = None
    properties: list[BSDDProperty] = Field(default_factory=list)


class BSDDContext(BaseModel):
    """Contexto semântico do bSDD para uma issue."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    class_name: str | None = None
    class_uri: str | None = None
    domain_name: str | None = Field(default=None, validation_alias=AliasChoices("domain_name", "domain"))
    related_properties: list[BSDDProperty] = Field(
        default_factory=list,
        validation_alias=AliasChoices("related_properties", "properties"),
    )
    classification_suggestions: list[BSDDClassification] = Field(
        default_factory=list,
        validation_alias=AliasChoices("classification_suggestions", "classes"),
    )
    raw_query: str | None = Field(default=None, validation_alias=AliasChoices("raw_query", "search_query"))
    issue_id: str | None = None
    element_class: str | None = None
    source_uris: list[str] = Field(default_factory=list)
    source_status: Literal["live", "cache", "empty", "offline"] = "empty"

    def as_prompt_block(self) -> str:
        """Serializa o contexto bSDD como texto estruturado para o prompt."""
        if not self.classification_suggestions and not self.related_properties:
            return "bSDD: sem resultados."

        lines = [f"bSDD source_status: {self.source_status}"]
        if self.classification_suggestions:
            lines.append("Classes candidatas:")
            for cls in self.classification_suggestions:
                lines.append(f"- {cls.name} | URI: {cls.uri}")
        if self.related_properties:
            lines.append("Propriedades e valores permitidos:")
            for prop in self.related_properties:
                values = ", ".join(prop.allowed_values) if prop.allowed_values else "livre"
                meta = []
                if prop.uri:
                    meta.append(f"URI: {prop.uri}")
                if prop.data_type:
                    meta.append(f"tipo: {prop.data_type}")
                if prop.unit:
                    meta.append(f"unidade: {prop.unit}")
                suffix = f" ({'; '.join(meta)})" if meta else ""
                lines.append(f"- {prop.name}: {values}{suffix}")
        return "\n".join(lines)

    @property
    def domain(self) -> str | None:
        return self.domain_name

    @property
    def properties(self) -> list[BSDDProperty]:
        return self.related_properties

    @property
    def classes(self) -> list[BSDDClassification]:
        return self.classification_suggestions

    @property
    def search_query(self) -> str | None:
        return self.raw_query


class IDSContext(BaseModel):
    """Contexto do requisito IDS que gerou a issue."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    spec_name: str = Field(validation_alias=AliasChoices("spec_name", "specification_name"))
    requirement_description: str = Field(
        default="",
        validation_alias=AliasChoices("requirement_description", "requirement_text"),
    )
    check_type: str
    expected_pset: str | None = Field(default=None, validation_alias=AliasChoices("expected_pset", "check_pset"))
    expected_property: str | None = Field(
        default=None,
        validation_alias=AliasChoices("expected_property", "check_property"),
    )
    expected_value: Any | None = None
    expected_unit: str | None = Field(default=None, validation_alias=AliasChoices("expected_unit", "unit"))
    severity: str
    issue_id: str | None = Field(default=None, exclude=True)
    requirement_id: str | None = Field(default=None, exclude=True)

    def model_post_init(self, __context: Any) -> None:
        if self.requirement_description:
            return

        target = ".".join(part for part in [self.expected_pset, self.expected_property] if part)
        if self.check_type == "exists":
            self.requirement_description = f"{target} must exist"
        elif self.check_type == "is_numeric":
            self.requirement_description = f"{target} must exist and be numeric"
        elif self.check_type == "is_boolean":
            self.requirement_description = f"{target} must be boolean"
        elif self.check_type == "not_empty":
            self.requirement_description = f"{target} must not be empty"
        elif self.check_type == "equals":
            self.requirement_description = f"{target} must equal {self.expected_value}"
        else:
            self.requirement_description = f"{target} must satisfy {self.check_type}"

    def as_prompt_block(self) -> str:
        """Serializa o requisito IDS como texto estruturado para o prompt."""
        lines = [
            f"Specification: {self.spec_name}",
            f"Check: {self.expected_pset}.{self.expected_property} ({self.check_type})",
            f"Severity: {self.severity}",
        ]
        if self.requirement_id is not None:
            lines.insert(0, f"IDS requirement_id: {self.requirement_id}")
        if self.expected_value is not None:
            lines.append(f"Expected value: {self.expected_value}")
        if self.expected_unit is not None:
            lines.append(f"Unit: {self.expected_unit}")
        if self.requirement_description:
            lines.append(f"Requirement: {self.requirement_description}")
        return "\n".join(lines)

    @property
    def specification_name(self) -> str:
        return self.spec_name

    @property
    def check_pset(self) -> str:
        return self.expected_pset or ""

    @property
    def check_property(self) -> str:
        return self.expected_property or ""

    @property
    def unit(self) -> str | None:
        return self.expected_unit

    @property
    def requirement_text(self) -> str:
        return self.requirement_description


class ValidationResult(BaseModel):
    """Resultado da validação pós-correção."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    schema_valid: bool = True
    ids_compliant: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    guid: str | None = None
    status: Literal["pass", "fail", "skip"] = "skip"
    schema_errors: list[str] = Field(default_factory=list)
    ids_errors: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if self.schema_errors:
            self.errors.extend(error for error in self.schema_errors if error not in self.errors)
            self.schema_valid = False
        if self.ids_errors:
            self.errors.extend(error for error in self.ids_errors if error not in self.errors)
            self.ids_compliant = False
        if self.status == "fail":
            if self.schema_errors:
                self.schema_valid = False
            if self.ids_errors:
                self.ids_compliant = False
        if self.status == "pass":
            self.schema_valid = True
            self.ids_compliant = True

    @property
    def is_valid(self) -> bool:
        return self.schema_valid and self.ids_compliant and not self.errors


class AuditEntry(BaseModel):
    """Registro imutável de uma ação de correção aplicada a um elemento IFC."""

    element_guid: str
    element_class: str
    action: str  # ex: "renomear_espaco", "preencher_pset"
    field: str  # ex: "LongName", "ThermalTransmittance"
    old_value: Any = None
    new_value: Any
    decision: Literal["accepted", "edited", "rejected"]
    confidence: str
    normative_ref: str | None = None
    source: Literal["llm"]
    user: str = "engineer"
    timestamp: datetime = Field(default_factory=datetime.now)
    session_id: str | None = None
    grounding_sources: list[str] = Field(default_factory=list)
    bsdd_uri: str | None = None
    ids_requirement_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ids_requirement_id", "ids_requirement"),
    )
    post_validation: Literal["pass", "fail", "skip"] = "skip"
    prompt_hash: str | None = None

    def to_csv_row(self) -> dict[str, str]:
        """Retorna dict com todos os campos serializados para escrita em CSV."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id or "",
            "element_guid": self.element_guid,
            "element_class": self.element_class,
            "action": self.action,
            "field": self.field,
            "old_value": str(self.old_value),
            "new_value": str(self.new_value),
            "decision": self.decision,
            "confidence": self.confidence,
            "normative_ref": self.normative_ref or "",
            "source": self.source,
            "user": self.user,
            "grounding_sources": "|".join(self.grounding_sources),
            "bsdd_uri": self.bsdd_uri or "",
            "ids_requirement_id": self.ids_requirement_id or "",
            "post_validation": self.post_validation,
            "prompt_hash": self.prompt_hash or "",
        }

    @property
    def ids_requirement(self) -> str | None:
        return self.ids_requirement_id


class DiagnosticReport(BaseModel):
    """Relatório completo de diagnóstico de qualidade de um modelo IFC."""

    model_name: str
    model_path: str
    total_elements: int
    total_spaces: int
    total_walls: int
    total_doors: int
    total_windows: int
    total_slabs: int
    issues: list[Issue] = Field(default_factory=list)

    @property
    def total_issues(self) -> int:
        """Retorna o número total de issues encontrados."""
        return len(self.issues)

    @property
    def issues_by_type(self) -> dict[str, int]:
        """Retorna contagem de issues agrupados por tipo."""
        counter: dict[str, int] = {}
        for issue in self.issues:
            counter[issue.issue_type] = counter.get(issue.issue_type, 0) + 1
        return counter

    @property
    def issues_by_severity(self) -> dict[str, int]:
        """Retorna contagem de issues agrupados por severidade."""
        counter: dict[str, int] = {}
        for issue in self.issues:
            counter[issue.severity] = counter.get(issue.severity, 0) + 1
        return counter

    @property
    def sorted_issues(self) -> list[Issue]:
        """Retorna issues ordenados por severidade (high primeiro)."""
        return sorted(self.issues, key=lambda i: i.severity_order)

    def filter_issues(
        self,
        issue_type: str | None = None,
        severity: str | None = None,
        status: str | None = None,
    ) -> list[Issue]:
        """Filtra issues por tipo, severidade e/ou status."""
        result = self.issues
        if issue_type:
            result = [i for i in result if i.issue_type == issue_type]
        if severity:
            result = [i for i in result if i.severity == severity]
        if status:
            result = [i for i in result if i.status == status]
        return result


class IDSSpecification(BaseModel):
    """Representa uma specification parseada de um arquivo IDS."""

    name: str
    description: str | None = None
    applicability_entity: str  # ex: "IFCWALL"
    applicability_filters: list[dict[str, str]] = Field(default_factory=list)  # [{pset, prop, value}]
    requirements: list[dict[str, str]] = Field(default_factory=list)  # [{pset, prop, constraint}]


class OperationalRule(BaseModel):
    """Regra verificável gerada a partir de uma IDSSpecification."""

    id: str = ""
    source_spec: str
    filter_entity: str  # ex: "IfcWall"
    filter_conditions: list[dict[str, str]] = Field(default_factory=list)  # [{pset, prop, operator, value}]
    check_pset: str  # ex: "Pset_WallCommon"
    check_property: str  # ex: "ThermalTransmittance"
    check_type: Literal["exists", "is_numeric", "is_boolean", "equals", "not_empty"]
    expected_value: str | None = None  # valor esperado para check_type == "equals"
    issue_type: str = "pset_missing"
    severity: Literal["high", "medium", "low"] = "high"
    normative_ref: str | None = None
    on_fail: Literal["create_issue", "auto_fix"] = "create_issue"
    profile_id: str | None = None
    suggestion_strategy: Literal[
        "lookup_table",
        "llm_inference",
        "geometric_calc",
        "copy_from_source",
        "user_input_only",
    ] = "llm_inference"
    write_action: Literal[
        "preencher_pset",
        "renomear_espaco",
        "criar_relacao_fills",
        "classificar_sistema",
        "preencher_base_quantities",
        "mapear_classificacao",
        "noop",
    ] = "preencher_pset"
    required_context: list[str] = Field(default_factory=list)
    evidence_source: str | None = None
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _ensure_deterministic_id(cls, data: Any) -> Any:
        """Deriva um id determinístico do conteúdo-chave quando nenhum id é fornecido."""
        if isinstance(data, dict) and not data.get("id"):
            data["id"] = _content_hash(
                str(data.get("source_spec", "")),
                str(data.get("filter_entity", "")),
                str(data.get("check_pset", "")),
                str(data.get("check_property", "")),
                str(data.get("check_type", "")),
                str(data.get("expected_value") or ""),
            )
        return data

    def _ids_requirement_description(self) -> str:
        """Retorna descrição legível do requisito IDS representado pela regra."""
        target = ".".join(part for part in [self.check_pset, self.check_property] if part) or self.check_property
        if self.check_type == "exists":
            return f"{target} must exist"
        if self.check_type == "is_numeric":
            return f"{target} must exist and be numeric"
        if self.check_type == "is_boolean":
            return f"{target} must be boolean"
        if self.check_type == "not_empty":
            return f"{target} must not be empty"
        if self.check_type == "equals":
            value = self.expected_value
            if self.evidence_source:
                value = f"{value} {self.evidence_source}" if value is not None else self.evidence_source
            return f"{target} must equal {value}"
        return f"{target} must satisfy {self.check_type}"

    def to_ids_context(self) -> IDSContext:
        """Converte a regra operacional em IDSContext serializável."""
        return IDSContext(
            spec_name=self.source_spec,
            requirement_description=self._ids_requirement_description(),
            check_type=self.check_type,
            expected_pset=self.check_pset or None,
            expected_property=self.check_property or None,
            expected_value=self.expected_value,
            expected_unit=self.evidence_source,
            severity=self.severity,
            requirement_id=self.id,
        )

    def matches_profile(self, profile_id: str) -> bool:
        """Retorna True se a regra pertence ao perfil informado ou não tem perfil restrito."""
        return self.profile_id == profile_id or self.profile_id is None

    def describe(self) -> str:
        """Descrição legível da regra em português."""
        if self.filter_conditions:
            conds = " AND ".join(
                f"{c['pset']}.{c['prop']} {c['operator']} {c['value']}"
                for c in self.filter_conditions
            )
            where_clause = f" WHERE {conds}"
        else:
            where_clause = ""
        return (
            f"Para cada {self.filter_entity}{where_clause}: "
            f"verificar {self.check_pset}.{self.check_property} ({self.check_type})"
        )


class ReadinessProfile(BaseModel):
    """Define um perfil de prontidão para uso downstream do IFC."""

    id: str
    name: str
    description: str
    version: str = "1.0"
    profile_group: str = "general"
    ids_filename: str | None = None
    ids_sources: list[str] = Field(default_factory=list)
    required_extractors: list[str] = Field(default_factory=list)
    rule_pack: str | None = None
    prompt_pack: str | None = None
    issue_types: list[str] = Field(default_factory=list)
    blocking_severities: list[str] = Field(default_factory=lambda: ["high"])
    entity_scope: list[str] = Field(default_factory=list)
    supported_data_categories: list[str] = Field(default_factory=list)
    external_classification_systems: list[str] = Field(default_factory=list)

    @property
    def is_custom(self) -> bool:
        """True se o perfil veio de IDS uploadado pelo usuário."""
        return self.ids_filename is None


class ReadinessScore(BaseModel):
    """Score de prontidão de um modelo para um perfil."""

    profile_id: str
    profile_name: str
    total_checks: int
    passed: int
    failed: int
    blocking_issues: int
    score_percent: float
    status: Literal["ready", "partially_ready", "not_ready"]

    @classmethod
    def compute(
        cls,
        profile: "ReadinessProfile",
        issues: list["Issue"],
        total_checks: int,
    ) -> "ReadinessScore":
        """Calcula score a partir do perfil e das issues detectadas."""
        failed = len(issues)
        passed = total_checks - failed
        blocking = len([i for i in issues if i.severity in profile.blocking_severities])
        pct = (passed / total_checks * 100) if total_checks > 0 else 0.0
        if blocking == 0 and pct >= 90:
            status: Literal["ready", "partially_ready", "not_ready"] = "ready"
        elif pct >= 50:
            status = "partially_ready"
        else:
            status = "not_ready"
        return cls(
            profile_id=profile.id,
            profile_name=profile.name,
            total_checks=total_checks,
            passed=passed,
            failed=failed,
            blocking_issues=blocking,
            score_percent=round(pct, 1),
            status=status,
        )


class ProfileRegistry(BaseModel):
    """Registro central de perfis disponíveis."""

    profiles: dict[str, ReadinessProfile] = Field(default_factory=dict)

    def register(self, profile: ReadinessProfile) -> None:
        """Adiciona um perfil ao registro, indexado pelo seu id."""
        self.profiles[profile.id] = profile

    def get(self, profile_id: str) -> ReadinessProfile | None:
        """Retorna o perfil pelo id, ou None se não encontrado."""
        return self.profiles.get(profile_id)

    def list_profiles(self) -> list[ReadinessProfile]:
        """Retorna todos os perfis registrados."""
        return list(self.profiles.values())
