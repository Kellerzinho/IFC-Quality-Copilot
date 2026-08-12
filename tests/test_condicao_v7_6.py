"""Condição v7.6 declarada: o que o estímulo passou a mostrar, e o que não mostra.

O benchmark v7.5 (rodada oficial de 2026-08-10) mediu, além dos modelos, o
próprio instrumento. Três estratos estavam medindo defeito de estímulo em vez de
decisão técnica:

- **AcousticRating**: tabela sem linha de porta; o menor valor ofertado (35 dB)
  fica acima do topo da banda aceita (30) — 214 itens inatingíveis.
- **relation_broken**: os templates pediam ação de correção em prosa, e o
  gabarito pontua o nome da relação — 0,00 em 10/10 modelos.
- **HasNonSkidSurface**: recebia a tabela de função portante — 7/10 modelos
  responderam False.

Estes testes travam a fronteira do v7.6: toda mudança é **evidência do arquivo**,
**vocabulário genérico** (tipologia de literatura ou classe de schema) ou
**formato**. Nenhuma entrega resposta — o princípio que o projeto policia desde o
vazamento do exemplar solar no v7.4.

Ver `docs/condicao-v7-6-2026-08-12.md`.
"""

from __future__ import annotations

import pytest

from src.experiment.evaluator import _coerce_bool
from src.models import Issue
from src.suggestion_engine.normalization import (
    normalize_acoustic_rating,
    normalize_fire_rating,
)
from src.suggestion_engine.prompt_templates import (
    TEMPLATES,
    _format_medida,
    _format_psets,
    _format_thickness_cm,
    _specialized_pset_template_key,
)


def _issue(check_property: str, element_class: str = "IfcWall") -> Issue:
    return Issue(
        element_guid="0" * 22,
        element_class=element_class,
        issue_type="pset_missing",
        severity="medium",
        description="teste",
        context={"check_property": check_property},
    )


# ---------------------------------------------------------------------------
# Acústico: a tabela passa a cobrir as tipologias que o dataset contém
# ---------------------------------------------------------------------------


def test_acoustic_table_covers_door_and_light_partition():
    """Sem linha de porta, acertar exigia contrariar a tabela dada.

    O ground truth espera Rw 25 dB em porta (banda 20–30) e o menor valor da
    tabela era Rw 35 dB, de alvenaria. As duas linhas novas são tipologia de
    literatura, na mesma natureza das três originais.
    """
    acoustic = TEMPLATES["pset_missing_acoustic"]

    assert "Porta interna de madeira" in acoustic
    assert "Rw 20 a 25 dB" in acoustic
    assert "Drywall simples" in acoustic
    assert "Rw 35 a 40 dB" in acoustic
    # As linhas originais continuam.
    assert "Alvenaria 14cm: Rw 35 dB" in acoustic
    assert "Concreto 12cm: Rw 42 dB" in acoustic
    assert "Drywall duplo: Rw 50 dB" in acoustic


def test_acoustic_template_receives_layers_and_predefined_type():
    """Era o template com menos evidência de arquivo do conjunto."""
    acoustic = TEMPLATES["pset_missing_acoustic"]

    assert "{material_layers}" in acoustic
    assert "{predefined_type}" in acoustic


def test_acoustic_table_does_not_state_the_ground_truth_values():
    """A tabela descreve tipologias; não entrega Rw 40 nem Rw 25 prontos."""
    acoustic = TEMPLATES["pset_missing_acoustic"]

    assert "Rw 40 dB" not in acoustic
    assert "Rw 25 dB" not in acoustic


# ---------------------------------------------------------------------------
# relation_broken: pergunta a classe da relação, com vocabulário de schema
# ---------------------------------------------------------------------------


def test_relation_template_is_unified():
    """Os dois templates anteriores viraram um; nenhum resquício."""
    assert "relation_missing" in TEMPLATES
    assert "relation_fills_missing" not in TEMPLATES
    assert "relation_orphan" not in TEMPLATES


def test_relation_template_asks_for_the_relationship_class():
    """O GT pontua o nome da classe; o template precisa cobrar isso."""
    relation = TEMPLATES["relation_missing"]

    assert "classe de relacionamento" in relation
    assert "VOCABULÁRIO FECHADO" in relation
    for classe in (
        "IfcRelFillsElement",
        "IfcRelVoidsElement",
        "IfcRelContainedInSpatialStructure",
        "IfcRelSpaceBoundary",
        "IfcRelAggregates",
    ):
        assert classe in relation


def test_relation_template_does_not_seed_an_answer():
    """O exemplar do template antigo trazia uma frase de resposta pronta."""
    relation = TEMPLATES["relation_missing"]

    assert "<NOME_DA_CLASSE_DA_LISTA>" in relation
    assert "Verificar se o elemento foi inserido" not in relation
    # O corpo não pede ação de correção em software BIM.
    assert "Revit" not in relation
    assert "ações de diagnóstico" not in relation


def test_relation_symptom_never_names_the_expected_relation():
    """O sintoma descreve o que a verificação achou, não a resposta.

    O ramo de fronteira espacial chegava a **afirmar o nome errado** da relação
    ausente (``IfcRelContainedInSpatialStructure`` num caso cuja resposta é
    ``IfcRelSpaceBoundary``).
    """
    from src.suggestion_engine.prompt_templates import (
        _RELATION_SINTOMA_FALLBACK,
        _RELATION_SINTOMAS,
    )

    for esperada, sintoma in _RELATION_SINTOMAS.items():
        assert esperada not in sintoma, f"o sintoma de {esperada} nomeia a resposta"
        for outra in _RELATION_SINTOMAS:
            assert outra not in sintoma
    assert "IfcRel" not in _RELATION_SINTOMA_FALLBACK


# ---------------------------------------------------------------------------
# HasNonSkidSurface: template próprio, sem a tabela de função portante
# ---------------------------------------------------------------------------


def test_nonskid_has_its_own_template():
    assert _specialized_pset_template_key(_issue("HasNonSkidSurface", "IfcStair")) == (
        "pset_missing_nonskid"
    )
    assert _specialized_pset_template_key(_issue("IsLoadBearing")) == (
        "pset_missing_structural"
    )
    assert _specialized_pset_template_key(_issue("LoadBearing", "IfcSlab")) == (
        "pset_missing_structural"
    )


def test_nonskid_template_has_no_load_bearing_interpretation():
    """Recebia FLOOR→True / ROOF→False numa pergunta sobre piso antiderrapante."""
    nonskid = TEMPLATES["pset_missing_nonskid"]

    assert "portante" not in nonskid
    assert "PredefinedType=FLOOR" not in nonskid
    assert "NBR 9050" in nonskid
    # Nem mapa de classe para valor: escada não implica True por decreto.
    assert "escada" not in nonskid.casefold()


# ---------------------------------------------------------------------------
# Evidência estrutural agregada: contexto do arquivo, não o alias do elemento
# ---------------------------------------------------------------------------


def test_structural_inventory_reaches_the_templates_that_need_it():
    assert "{structural_inventory}" in TEMPLATES["pset_missing_structural"]
    assert "{structural_inventory}" in TEMPLATES["system_unclassified"]


def test_system_template_receives_load_bearing():
    """A omissão explica o erro de vedação→estrutural em 262 itens."""
    assert "{load_bearing}" in TEMPLATES["system_unclassified"]


def test_structural_inventory_counts_without_revealing_the_answer(tmp_path):
    """O inventário conta pilares e vigas; não menciona a propriedade avaliada."""
    import ifcopenshell

    from src.ifc_analyzer.model_evidence import format_structural_inventory

    modelo = ifcopenshell.file(schema="IFC4")
    for _ in range(3):
        modelo.create_entity("IfcColumn", GlobalId=ifcopenshell.guid.new())
    modelo.create_entity("IfcBeam", GlobalId=ifcopenshell.guid.new())

    frase = format_structural_inventory(modelo)

    assert "3 pilares" in frase
    assert "1 viga" in frase
    assert "LoadBearing" not in frase
    assert "vedação" not in frase


def test_structural_inventory_reports_absence():
    import ifcopenshell

    from src.ifc_analyzer.model_evidence import format_structural_inventory

    vazio = ifcopenshell.file(schema="IFC4")

    assert format_structural_inventory(vazio) == "o arquivo não declara pilares nem vigas"


def test_structural_template_vocabulary_is_closed_and_unseeded():
    """Era o único template de sistema sem vocabulário fechado, e semeava rótulo."""
    structural = TEMPLATES["system_unclassified_structural"]

    assert "VOCABULÁRIO FECHADO" in structural
    assert "<ROTULO_DA_LISTA>" in structural
    assert '"sistema": "Viga de concreto armado moldada in loco"' not in structural


# ---------------------------------------------------------------------------
# Formato da evidência: milímetro preservado, float sem ruído binário
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metros", "esperado"),
    [
        (0.015, "1.5cm"),
        (0.16, "16cm"),
        (0.1, "10cm"),
        (0.02, "2cm"),
        (0.0126, "1.3cm"),
    ],
)
def test_layer_thickness_keeps_the_millimetre(metros: float, esperado: str):
    """1,5 cm virava "2cm": o modelo fiel à evidência calculava U 6,4% menor."""
    assert _format_thickness_cm(metros) == esperado


@pytest.mark.parametrize(
    ("valor", "casas", "esperado"),
    [
        (0.19999999999999998, 3, "0.2"),
        (9.240000000001922, 2, "9.24"),
        (0.15000000000000002, 3, "0.15"),
    ],
)
def test_measurements_lose_the_binary_noise(valor: float, casas: int, esperado: str):
    assert _format_medida(valor, casas) == esperado


def test_psets_render_as_text_not_python_repr():
    """Chegava como repr de dict, com aspas simples e float sujo."""
    rendered = _format_psets(
        {
            "Pset_WindowCommon": {"IsExternal": False, "Reference": "1.5 x 1.0"},
            "Qto_WindowBaseQuantities": {"Width": 1.4999999999999998},
            "Vazio": {},
        }
    )

    assert "Pset_WindowCommon (IsExternal=False, Reference=1.5 x 1.0)" in rendered
    assert "Width=1.5" in rendered
    assert "{" not in rendered
    assert "'" not in rendered
    assert "Vazio" not in rendered


def test_solar_template_labels_the_psets_honestly():
    """A linha dizia "ThermalTransmittance (U)" e renderizava o resumo de Psets."""
    solar = TEMPLATES["pset_missing_solar"]

    assert "- ThermalTransmittance (U): {existing_psets}" not in solar
    assert "Conjuntos de propriedades já presentes no elemento" in solar


# ---------------------------------------------------------------------------
# Comparador: notação deixa de contar como erro; classe deixa de ser presumida
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cru", "esperado"),
    [
        ("REI 60", "REI 60"),
        ("rei60", "REI 60"),
        ("EI 30", "EI 30"),
        ("REI de 60 minutos", "REI 60"),
        ("EI de 30 min", "EI 30"),
    ],
)
def test_fire_rating_accepts_declared_class(cru: str, esperado: str):
    assert normalize_fire_rating(cru) == esperado


@pytest.mark.parametrize("cru", ["60", "120", "60 minutos", "1h", "90"])
def test_fire_rating_rejects_duration_without_class(cru: str):
    """A classe é a substância da resposta; presumir REI dava o difícil de graça.

    Medido no log da rodada v7.5: 108 respostas cruas eram duração pura e
    entravam na avaliação como ``REI n``.
    """
    assert normalize_fire_rating(cru) is None


@pytest.mark.parametrize(
    ("cru", "esperado"),
    [
        ("Rw 40 dB", "Rw 40 dB"),
        ("Rw 40dB", "Rw 40 dB"),
        ("RW40DB", "Rw 40 dB"),
        ("40 dB", "Rw 40 dB"),
        (42, "Rw 42 dB"),
    ],
)
def test_acoustic_rating_normalises_notation(cru, esperado: str):
    assert normalize_acoustic_rating(cru) == esperado


@pytest.mark.parametrize("cru", ["40", "Rw NN dB", "Rw 5 dB", ""])
def test_acoustic_rating_rejects_non_values(cru: str):
    """Número solto não é índice, e o eco do placeholder não é resposta."""
    assert normalize_acoustic_rating(cru) is None


@pytest.mark.parametrize(
    ("cru", "esperado"),
    [("não", False), ("nao", False), ("NÃO", False), ("sim", True), ("talvez", None)],
)
def test_boolean_accepts_accented_portuguese(cru: str, esperado: bool | None):
    """O prompt é em português; ``não`` não casava com nada."""
    assert _coerce_bool(cru) is esperado
