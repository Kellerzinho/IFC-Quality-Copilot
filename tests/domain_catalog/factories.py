"""Fábricas de entidades SINTÉTICAS para testar contratos do catálogo.

Nada aqui vem da dissertação de Daiane nem de outra fonte real: nomes ``SYN_*``,
conjuntos ``SYN_Conjunto*`` e UUIDs literais existem só para exercitar regras de
validação, resolução e leitura de pacote. Exemplos reais ficam em
``data/catalogs/fixtures/daiane-e1-rascunho/`` e são marcados como tal.
"""

from pathlib import Path

from src.domain_catalog.content import CatalogContent
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.models import (
    AliasMapping,
    AliasScope,
    AllowedValue,
    AllowedValueSet,
    ApplicabilityRule,
    ConceptDefinition,
    Condition,
    IFCBinding,
    LifecycleState,
    LocalizedText,
    ReconciliationDecision,
    SourceArtifact,
    SourceAssertion,
    SourceLocator,
    UnitDefinition,
)
from src.domain_catalog.package import (
    CatalogIdentity,
    ComponentTerms,
    ReleaseFiles,
    build_release_files,
    write_release_dir,
)

SYN_SOURCE_ID = "synthetic:catalogo-teste"
SYN_ASSERTION_ID = "synthetic:linha-001"
CONCEPT_ID = "urn:uuid:00000000-0000-4000-8000-000000000001"
RULE_ID = "urn:uuid:00000000-0000-4000-8000-000000000002"
BINDING_ID = "urn:uuid:00000000-0000-4000-8000-000000000003"
VALUE_SET_ID = "urn:uuid:00000000-0000-4000-8000-000000000004"
UNIT_ID = "urn:uuid:00000000-0000-4000-8000-000000000005"


def pt(text: str) -> tuple[LocalizedText, ...]:
    """Texto único em pt-BR."""
    return (LocalizedText(lang="pt-BR", text=text),)


def source_artifact() -> SourceArtifact:
    """Fonte sintética declarada como tal."""
    return SourceArtifact(
        id=SYN_SOURCE_ID,
        title="Fixture sintética de teste",
        authors=("teste automatizado",),
        issued=None,
        artifact_type="synthetic_fixture",
        location=None,
        sha256=None,
        size_bytes=None,
        terms="sintético, sem conteúdo de terceiros",
        notes=None,
    )


def source_assertion() -> SourceAssertion:
    """Linha de fonte sintética, com literal tipado como texto."""
    return SourceAssertion(
        id=SYN_ASSERTION_ID,
        source_artifact_id=SYN_SOURCE_ID,
        transcription_artifact_id=None,
        locator=SourceLocator(printed_page=None, pdf_page=None, table="T1", row_ref="001"),
        category="custom_property",
        target_literal="SYN_Metodo",
        target_identifier_literal="SYN_Metodo",
        set_literal="SYN_Conjunto",
        datatype_literal="Texto (IfcLabel)",
        unit_literal=None,
        domain_literal_json='["A","B"]',
        notes=(),
        transcription_status="registered",
    )


def value_set(lifecycle: LifecycleState = "approved") -> AllowedValueSet:
    """Conjunto de códigos textuais A/B."""
    return AllowedValueSet(
        id=VALUE_SET_ID,
        value_type="code",
        values=(AllowedValue(code="A"), AllowedValue(code="B")),
        source_assertion_ids=(SYN_ASSERTION_ID,),
        lifecycle=lifecycle,
    )


def concept(lifecycle: LifecycleState = "approved") -> ConceptDefinition:
    """Conceito de código enumerado, sem grandeza física."""
    return ConceptDefinition(
        id=CONCEPT_ID,
        code="SYN_METODO",
        labels=pt("Método sintético"),
        definition=pt("Método escolhido entre as opções sintéticas A e B."),
        logical_type="code",
        dimension=None,
        unit_id=None,
        value_set_id=VALUE_SET_ID,
        source_assertion_ids=(SYN_ASSERTION_ID,),
        lifecycle=lifecycle,
    )


def rule(lifecycle: LifecycleState = "approved") -> ApplicabilityRule:
    """Aplicabilidade à classe exata IfcSlab, sem subtipos."""
    return ApplicabilityRule(
        id=RULE_ID,
        entity_classes=("IfcSlab",),
        include_subtypes=False,
        predefined_types=None,
        conditions=(),
        source_assertion_ids=(SYN_ASSERTION_ID,),
        lifecycle=lifecycle,
    )


def binding(lifecycle: LifecycleState = "approved") -> IFCBinding:
    """Propriedade em conjunto personalizado, portador aprovado, escrita desligada."""
    return IFCBinding(
        id=BINDING_ID,
        concept_id=CONCEPT_ID,
        applicability_rule_id=RULE_ID,
        declared_schemas=("IFC4",),
        carrier_kind="property",
        set_name="SYN_Conjunto",
        field_name="SYN_Metodo",
        set_kind="custom",
        ifc_type="IfcLabel",
        source_original_type="Texto (IfcLabel)",
        scope="occurrence",
        carrier_status="approved",
        value_set_id=None,
        evidence_policy_id=None,
        write_enabled=False,
        source_assertion_ids=(SYN_ASSERTION_ID,),
        lifecycle=lifecycle,
    )


def length_unit() -> UnitDefinition:
    """Metro, dimensão comprimento."""
    return UnitDefinition(id=UNIT_ID, symbol="m", dimension="length", lifecycle="approved")


def minimal_content(lifecycle: LifecycleState = "approved") -> CatalogContent:
    """Um conceito, uma regra, um binding e a fonte sintética que os sustenta."""
    return CatalogContent(
        source_artifacts=(source_artifact(),),
        source_assertions=(source_assertion(),),
        concepts=(concept(lifecycle),),
        value_sets=(value_set(lifecycle),),
        applicability_rules=(rule(lifecycle),),
        bindings=(binding(lifecycle),),
    )


# --- Conteúdo sintético para resolução (M1-05) ------------------------------------------


def _uid(n: int) -> str:
    """UUID literal sintético terminado em 1nnn."""
    return f"urn:uuid:00000000-0000-4000-8000-000000001{n:03d}"


class R:
    """IDs do conteúdo de resolução, para asserções legíveis."""

    RULE_WALL, RULE_DOOR, RULE_SLAB, RULE_COLUMN = _uid(1), _uid(2), _uid(3), _uid(4)
    RULE_FLOOR, RULE_CLADDING, RULE_MASONRY = _uid(5), _uid(6), _uid(7)
    RULE_WALL_SUBTYPES = _uid(8)
    STATUS_A, STATUS_B, METODO, ACAB_PISO = _uid(20), _uid(21), _uid(22), _uid(23)
    ACAB_PAREDE, BLOCO, ALTURA, SO_IFC4, AREA = _uid(24), _uid(25), _uid(26), _uid(27), _uid(28)
    B_STATUS_A, B_STATUS_B, B_METODO_SLAB, B_METODO_COLUMN = _uid(40), _uid(41), _uid(42), _uid(43)
    B_ACAB_PISO, B_ACAB_PAREDE, B_BLOCO, B_ALTURA = _uid(44), _uid(45), _uid(46), _uid(47)
    B_SO_IFC4, B_AREA_PENDENTE = _uid(48), _uid(49)
    ALIAS_HEIGTH, ALIAS_FORA_ESCOPO, ALIAS_RASCUNHO = _uid(60), _uid(61), _uid(62)
    ALIAS_METODO_1, ALIAS_METODO_2 = _uid(63), _uid(64)
    DECISION_AREA = _uid(80)
    UNIT_M, UNIT_M2 = _uid(90), _uid(91)


def _rule_for(rule_id: str, entity: str, **changes: object) -> ApplicabilityRule:
    data: dict[str, object] = {
        "id": rule_id,
        "entity_classes": (entity,),
        "include_subtypes": False,
        "lifecycle": "approved",
        "source_assertion_ids": (SYN_ASSERTION_ID,),
    }
    data.update(changes)
    return ApplicabilityRule.model_validate(data)


def _concept_for(concept_id: str, code: str, **changes: object) -> ConceptDefinition:
    data: dict[str, object] = {
        "id": concept_id,
        "code": code,
        "labels": pt(code),
        "definition": pt(f"Conceito sintético {code}."),
        "logical_type": "code",
        "lifecycle": "approved",
        "source_assertion_ids": (SYN_ASSERTION_ID,),
    }
    data.update(changes)
    return ConceptDefinition.model_validate(data)


def _binding_for(
    binding_id: str, concept_id: str, rule_id: str, set_name: str, field: str, **changes: object
) -> IFCBinding:
    data: dict[str, object] = {
        "id": binding_id,
        "concept_id": concept_id,
        "applicability_rule_id": rule_id,
        "declared_schemas": ("IFC4",),
        "carrier_kind": "property",
        "set_name": set_name,
        "field_name": field,
        "set_kind": "custom",
        "ifc_type": "IfcLabel",
        "scope": "occurrence",
        "carrier_status": "approved",
        "lifecycle": "approved",
        "source_assertion_ids": (SYN_ASSERTION_ID,),
    }
    data.update(changes)
    return IFCBinding.model_validate(data)


def _alias_for(
    alias_id: str, term: str, set_name: str, target: str, **changes: object
) -> AliasMapping:
    data: dict[str, object] = {
        "id": alias_id,
        "term": term,
        "purpose": "historical_spelling",
        "scope": AliasScope(set_names=(set_name,)),
        "target_binding_id": target,
        "lifecycle": "approved",
    }
    data.update(changes)
    return AliasMapping.model_validate(data)


def resolution_content() -> CatalogContent:
    """Catálogo sintético publicável com reuso, homônimos, alias, condição e pendência."""
    masonry = Condition(fact="construction_system", operator="in", values=("alvenaria",))
    rules = (
        _rule_for(R.RULE_WALL, "IfcWall"),
        _rule_for(R.RULE_DOOR, "IfcDoor"),
        _rule_for(R.RULE_SLAB, "IfcSlab"),
        _rule_for(R.RULE_COLUMN, "IfcColumn"),
        _rule_for(R.RULE_FLOOR, "IfcCovering", predefined_types=("FLOORING",)),
        _rule_for(R.RULE_CLADDING, "IfcCovering", predefined_types=("CLADDING",)),
        _rule_for(R.RULE_MASONRY, "IfcWall", conditions=(masonry,)),
        _rule_for(R.RULE_WALL_SUBTYPES, "IfcWall", include_subtypes=True),
    )
    concepts = (
        _concept_for(R.STATUS_A, "SYN_STATUS_A"),
        _concept_for(R.STATUS_B, "SYN_STATUS_B"),
        _concept_for(R.METODO, "SYN_METODO"),
        _concept_for(R.ACAB_PISO, "SYN_ACABAMENTO_PISO"),
        _concept_for(R.ACAB_PAREDE, "SYN_ACABAMENTO_PAREDE"),
        _concept_for(R.BLOCO, "SYN_BLOCO"),
        _concept_for(
            R.ALTURA, "SYN_ALTURA", logical_type="decimal", dimension="length", unit_id=R.UNIT_M
        ),
        _concept_for(R.SO_IFC4, "SYN_SO_IFC4"),
        _concept_for(
            R.AREA, "SYN_AREA", logical_type="decimal", dimension="area", unit_id=R.UNIT_M2
        ),
    )
    bindings = (
        _binding_for(R.B_STATUS_A, R.STATUS_A, R.RULE_WALL, "SYN_PsetA", "Status"),
        _binding_for(R.B_STATUS_B, R.STATUS_B, R.RULE_DOOR, "SYN_PsetB", "Status"),
        _binding_for(R.B_METODO_SLAB, R.METODO, R.RULE_SLAB, "SYN_Conjunto", "SYN_Metodo"),
        _binding_for(R.B_METODO_COLUMN, R.METODO, R.RULE_COLUMN, "SYN_Conjunto", "SYN_Metodo"),
        _binding_for(R.B_ACAB_PISO, R.ACAB_PISO, R.RULE_FLOOR, "SYN_Conjunto", "SYN_Acabamento"),
        _binding_for(
            R.B_ACAB_PAREDE, R.ACAB_PAREDE, R.RULE_CLADDING, "SYN_Conjunto", "SYN_Acabamento"
        ),
        _binding_for(R.B_BLOCO, R.BLOCO, R.RULE_MASONRY, "SYN_Conjunto", "SYN_Bloco"),
        _binding_for(
            R.B_ALTURA,
            R.ALTURA,
            R.RULE_WALL_SUBTYPES,
            "SYN_Qto",
            "Height",
            carrier_kind="quantity",
            set_kind="standard",
            ifc_type="IfcQuantityLength",
            declared_schemas=("IFC2X3", "IFC4"),
        ),
        _binding_for(R.B_SO_IFC4, R.SO_IFC4, R.RULE_SLAB, "SYN_Conjunto", "SYN_SoIfc4"),
        _binding_for(
            R.B_AREA_PENDENTE,
            R.AREA,
            R.RULE_SLAB,
            "SYN_Conjunto",
            "SYN_AreaPendente",
            ifc_type=None,
            source_original_type="IfcQuantityArea",
            carrier_status="pending_reconciliation",
            scope="unspecified",
        ),
    )
    equivalence = {"purpose": "approved_equivalence"}
    aliases = (
        _alias_for(R.ALIAS_HEIGTH, "Heigth", "SYN_Qto", R.B_ALTURA),
        _alias_for(R.ALIAS_FORA_ESCOPO, "Altura", "SYN_Outro", R.B_ALTURA),
        _alias_for(R.ALIAS_METODO_1, "Metodo", "SYN_Conjunto", R.B_METODO_SLAB, **equivalence),
        _alias_for(R.ALIAS_METODO_2, "Metodo", "SYN_Conjunto", R.B_SO_IFC4, **equivalence),
    )
    decision = ReconciliationDecision(
        id=R.DECISION_AREA,
        code="syn-area-portador",
        status="pending",
        source_assertion_ids=(SYN_ASSERTION_ID,),
        summary="Portador sintético declarado como quantidade dentro de conjunto de propriedades.",
        affected_binding_ids=(R.B_AREA_PENDENTE,),
    )
    units = (
        UnitDefinition(id=R.UNIT_M, symbol="m", dimension="length", lifecycle="approved"),
        UnitDefinition(id=R.UNIT_M2, symbol="m2", dimension="area", lifecycle="approved"),
    )
    return CatalogContent(
        source_artifacts=(source_artifact(),),
        source_assertions=(source_assertion(),),
        concepts=concepts,
        units=units,
        applicability_rules=rules,
        bindings=bindings,
        aliases=aliases,
        reconciliation_decisions=(decision,),
    )


def draft_alias() -> AliasMapping:
    """Alias ainda em rascunho, que não pode resolver nem entrar em release."""
    return _alias_for(R.ALIAS_RASCUNHO, "Hght", "SYN_Qto", R.B_ALTURA, lifecycle="draft")


# --- Pacotes sintéticos (M1-06) -----------------------------------------------------------

SYN_CATALOG_ID = "urn:uuid:00000000-0000-4000-8000-0000000000e1"


def catalog_identity() -> CatalogIdentity:
    """Identidade de um catálogo sintético, explicitamente provisório."""
    return CatalogIdentity(
        catalog_id=SYN_CATALOG_ID,
        namespace="ifcqc.teste.sintetico",
        namespace_status="provisional",
        name="Catálogo sintético de teste",
        maintainer="testes automatizados",
        language="pt-BR",
    )


def build_synthetic_release(
    content: CatalogContent | None = None, version: str = "1.0.0"
) -> ReleaseFiles:
    """Bytes de um release sintético, rotulado como ``synthetic_fixture``."""
    return build_release_files(
        content if content is not None else resolution_content(),
        catalog=catalog_identity(),
        version=version,
        created_at="2026-10-13T12:00:00Z",
        content_origin="synthetic_fixture",
        terms=(ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),),
    )


def write_synthetic_release(
    base: Path, content: CatalogContent | None = None, version: str = "1.0.0"
) -> tuple[CatalogReleaseRef, Path]:
    """Grava um release sintético em ``base/<versão>`` e devolve referência e pasta."""
    release = build_synthetic_release(content, version)
    destination = base / version
    return write_release_dir(release, destination), destination
