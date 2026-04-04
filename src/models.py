"""Modelos de dados Pydantic para o IFC Quality Copilot."""

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


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
}

_SEVERITY_ORDER: dict[str, int] = {
    "high": 0,
    "medium": 1,
    "low": 2,
}


class Issue(BaseModel):
    """Representa um problema de qualidade detectado em um elemento IFC."""

    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    element_guid: str
    element_class: str
    element_name: str | None = None
    issue_type: Literal["space_unnamed", "pset_missing", "relation_broken", "system_unclassified"]
    severity: Literal["high", "medium", "low"]
    description: str
    context: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "accepted", "edited", "rejected", "skipped"] = "pending"
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: datetime | None = None
    resolution_value: Any = None

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
    """Sugestão de correção gerada por heurística ou LLM para um Issue."""

    label: str  # ex: "Lavabo Suíte" ou "2.48 W/(m².K)"
    value: Any  # valor a ser escrito no IFC
    justification: str  # ex: "4.2m² com WC e lavatório adjacente a dormitório"
    confidence: Literal["alta", "media", "baixa"]
    normative_ref: str | None = None  # ex: "NBR 15575-4 Tab. C.2"
    source: Literal["heuristic", "llm"]

    @property
    def confidence_emoji(self) -> str:
        """Retorna emoji colorido representando o nível de confiança."""
        return {"alta": "🟢", "media": "🟡", "baixa": "🔴"}[self.confidence]

    @property
    def confidence_order(self) -> int:
        """Retorna 0 para alta, 1 para media, 2 para baixa (para ordenação)."""
        return {"alta": 0, "media": 1, "baixa": 2}[self.confidence]


class SuggestionSet(BaseModel):
    """Conjunto de sugestões geradas para um Issue específico."""

    issue_id: str
    suggestions: list[Suggestion] = Field(default_factory=list)  # 2-3 opções
    allow_custom: bool = True
    error: str | None = None  # se houve erro na geração

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
    source: Literal["heuristic", "llm"]
    user: str = "engineer"
    timestamp: datetime = Field(default_factory=datetime.now)
    session_id: str | None = None

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
        }


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

    id: str = Field(default_factory=lambda: str(uuid4())[:8])
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
    ids_filename: str | None = None
    required_extractors: list[str] = Field(default_factory=list)
    rule_pack: str | None = None
    prompt_pack: str | None = None
    issue_types: list[str] = Field(default_factory=list)
    blocking_severities: list[str] = Field(default=["high"])

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
