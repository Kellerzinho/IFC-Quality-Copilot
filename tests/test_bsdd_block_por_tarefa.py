"""O bloco bSDD injetado precisa ser escopado pela tarefa da issue.

Medido em 2026-07-27 (breakdown por estrato, gemma2:9b sobre o prédio):
``system_unclassified`` ficou em **0,000 de top-1 em 872 issues**. O prompt
terminava com o despejo de TODAS as propriedades bSDD da classe (Warranty
Content, Net Volume, Surface Genus, Mean Time Between Failure...) logo após o
system prompt mandar "use apenas o vocabulário e os requisitos fornecidos" — e o
modelo obedecia à lista errada, respondendo ``Thickness``, ``Dimensions``,
``200 mm`` e ``Mean Time Between Failure`` como sistema construtivo.

Classificar sistema construtivo não é preencher propriedade: para essa tarefa o
bSDD contribui com **classes de domínio**, nunca com a lista de propriedades.
"""

from src.models import BSDDClassification, BSDDContext, BSDDProperty, Issue
from src.suggestion_engine.prompt_templates import build_prompt

_BUILDING_CTX = {"building_type": "Residencial multifamiliar", "bioclimatic_zone": "3"}

_RUIDO = ("Warranty Content", "Net Volume", "Mean Time Between Failure", "Surface Genus")


def _system_issue() -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede básica:parede interna 20cm",
        issue_type="system_unclassified",
        severity="medium",
        description="Parede sem classificação de sistema construtivo",
        context={
            "materials": [{"name": ".alvenaria deitado 18 cm", "thickness": 0.18}],
            "total_thickness": 0.20,
        },
    )


def _bsdd_ruidoso(issue: Issue) -> BSDDContext:
    """bSDD como ele volta de verdade: dezenas de propriedades irrelevantes."""
    return BSDDContext(
        issue_id=issue.id,
        element_class=issue.element_class,
        class_name="IfcWall",
        class_uri="https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall",
        classification_suggestions=[
            BSDDClassification(name="IfcWall", uri="https://example.org/IfcWall"),
            BSDDClassification(name="Alvenaria estrutural", uri="https://example.org/alv"),
        ],
        related_properties=[
            BSDDProperty(name="Warranty Content", data_type="String"),
            BSDDProperty(name="Net Volume", data_type="Real"),
            BSDDProperty(name="Mean Time Between Failure", data_type="Real"),
            BSDDProperty(name="Surface Genus Before Features", data_type="Real"),
            BSDDProperty(name="Thickness", data_type="Real"),
        ],
        source_status="cache",
    )


def test_system_unclassified_nao_recebe_lista_de_propriedades_bsdd():
    """Nomes de propriedade não podem entrar no prompt de classificação de sistema."""
    issue = _system_issue()

    _, user = build_prompt(issue, _BUILDING_CTX, bsdd_context=_bsdd_ruidoso(issue))

    for ruido in _RUIDO:
        assert ruido not in user, f"propriedade bSDD irrelevante vazou no prompt: {ruido}"


def test_system_unclassified_mantem_o_vocabulario_canonico_do_template():
    """O que deve guiar a resposta é a lista canônica de sistemas construtivos."""
    issue = _system_issue()

    _, user = build_prompt(issue, _BUILDING_CTX, bsdd_context=_bsdd_ruidoso(issue))

    assert "Alvenaria de vedação em bloco cerâmico" in user
    assert ".alvenaria deitado 18 cm" in user


def test_system_unclassified_preserva_classes_de_dominio_do_bsdd():
    """Classificações de domínio (não-IFC) continuam sendo grounding legítimo."""
    issue = _system_issue()

    _, user = build_prompt(issue, _BUILDING_CTX, bsdd_context=_bsdd_ruidoso(issue))

    assert "Alvenaria estrutural" in user


def test_pset_missing_continua_recebendo_o_bloco_bsdd_completo():
    """A restrição vale para classificação; preencher propriedade ainda usa o bSDD."""
    issue = Issue(
        element_guid="F" * 22,
        element_class="IfcWall",
        element_name="Parede",
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={"check_property": "FireRating", "check_pset": "Pset_WallCommon"},
    )
    bsdd = BSDDContext(
        issue_id=issue.id,
        element_class="IfcWall",
        class_name="IfcWall",
        related_properties=[
            BSDDProperty(name="Fire Rating", data_type="String", allowed_values=["REI 60"])
        ],
        source_status="cache",
    )

    _, user = build_prompt(issue, _BUILDING_CTX, bsdd_context=bsdd)

    assert "Fire Rating" in user
    assert "REI 60" in user
