"""Testes para BSDDContextBuilder."""

from unittest.mock import MagicMock

import httpx

from src.bsdd.client import BSDDClient
from src.bsdd.context_builder import BSDDContextBuilder
from src.models import BSDDClassification, BSDDContext, BSDDProperty, Issue


def _make_issue(issue_type: str, **context_overrides) -> Issue:
    return Issue(
        element_guid="A" * 22,
        element_class="IfcSpace" if issue_type == "space_unnamed" else "IfcWall",
        element_name="Room 101" if issue_type == "space_unnamed" else "Parede Externa 01",
        issue_type=issue_type,  # type: ignore[arg-type]
        severity="high",
        description="Issue de teste",
        context=context_overrides,
    )


def test_build_pset_missing_returns_properties():
    client = MagicMock(spec=BSDDClient)
    client.search_class.return_value = [
        {
            "name": "IfcWall",
            "uri": "https://example.org/classes/ifcwall",
            "domain": "IFC",
        }
    ]
    client.get_class_properties.return_value = [
        BSDDProperty(name="FireRating", data_type="String", allowed_values=["REI 60"]),
        BSDDProperty(name="IsExternal", data_type="Boolean"),
    ]

    builder = BSDDContextBuilder(client)
    issue = _make_issue("pset_missing", check_property="FireRating", pset_name="Pset_WallCommon")

    context = builder.build(issue)

    assert context.class_name == "IfcWall"
    assert context.class_uri == "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall"
    assert [prop.name for prop in context.related_properties] == ["FireRating"]
    assert context.related_properties[0].uri == "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating"
    assert context.source_uris == [
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall",
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating",
    ]
    assert context.source_status == "live"


def test_build_space_unnamed_returns_classifications():
    client = MagicMock(spec=BSDDClient)
    client.search_class.return_value = [
        {
            "name": "Space",
            "uri": "https://example.org/classes/space",
            "domain": "IFC",
        },
        {
            "name": "Toilet room",
            "uri": "https://example.org/classifications/omniclass/table13/toilet-room",
            "domain": "OmniClass Table 13",
        },
        {
            "name": "Office",
            "uri": "https://example.org/classifications/uniclass/spaces/office",
            "domain": "Uniclass Spaces",
        },
    ]
    client.get_class_properties.return_value = []

    builder = BSDDContextBuilder(client)
    issue = _make_issue("space_unnamed")

    context = builder.build(issue)

    assert context.source_status == "live"
    assert len(context.classification_suggestions) == 2
    assert context.classification_suggestions[0].system_name == "OmniClass Table 13"
    assert context.classification_suggestions[1].system_name == "Uniclass Spaces"


def test_build_offline_returns_empty_context():
    client = MagicMock(spec=BSDDClient)
    client.search_class.side_effect = httpx.ConnectError("offline")

    builder = BSDDContextBuilder(client)
    issue = _make_issue("system_unclassified")

    context = builder.build(issue)

    assert context.class_name is None
    assert context.class_uri is None
    assert context.related_properties == []
    assert context.classification_suggestions == []
    assert context.source_status == "offline"


def test_build_context_text_formats_correctly():
    builder = BSDDContextBuilder(MagicMock(spec=BSDDClient))
    context = BSDDContext(
        class_name="Wall",
        class_uri="https://example.org/classes/wall",
        related_properties=[
            BSDDProperty(
                name="ThermalTransmittance",
                data_type="real",
                unit="W/(m²·K)",
                description="Pset_WallCommon thermal performance",
            ),
            BSDDProperty(
                name="IsExternal",
                data_type="boolean",
            ),
            BSDDProperty(
                name="FireRating",
                data_type="string",
                allowed_values=["REI 30", "REI 60", "REI 90", "REI 120"],
            ),
        ],
        classification_suggestions=[
            BSDDClassification(
                name="External wall",
                code="EF_25_10",
                uri="https://example.org/classifications/external-wall",
                system_name="Uniclass 2015",
            )
        ],
    )

    text = builder.build_context_text(context)

    assert "VOCABULARIO bSDD (classe: Wall, URI: https://example.org/classes/wall):" in text
    assert "Propriedades validas para Pset_WallCommon:" in text
    assert "- ThermalTransmittance (real, W/(m²·K))" in text
    assert "- IsExternal (boolean)" in text
    assert "- FireRating (string), valores: REI 30, REI 60, REI 90, REI 120" in text
    assert "Classificacoes relevantes:" in text
    assert "- External wall, codigo: EF_25_10, sistema: Uniclass 2015, URI: https://example.org/classifications/external-wall" in text


def test_build_context_text_empty_when_no_data():
    builder = BSDDContextBuilder(MagicMock(spec=BSDDClient))

    assert builder.build_context_text(BSDDContext()) == ""


def test_build_preserves_non_ifc_uris_for_external_classifications():
    client = MagicMock(spec=BSDDClient)
    client.search_class.return_value = [
        {
            "name": "Space",
            "uri": "https://example.org/classes/space",
            "domain": "IFC",
        },
        {
            "name": "Office",
            "uri": "https://example.org/classifications/uniclass/spaces/office",
            "domain": "Uniclass Spaces",
        },
    ]
    client.get_class_properties.return_value = []

    builder = BSDDContextBuilder(client)
    issue = _make_issue("space_unnamed")

    context = builder.build(issue)

    assert context.class_uri == "https://example.org/classes/space"
    assert context.classification_suggestions[0].uri == "https://example.org/classifications/uniclass/spaces/office"


# ---------------------------------------------------------------------------
# Resolução robusta da consulta: o bSDD busca CLASSES, não classe+propriedade
# ---------------------------------------------------------------------------


def _client_that_only_answers(answers: dict[str, list[dict[str, str]]]) -> MagicMock:
    """Cliente falso que responde como o bSDD real: só casa nomes de classe.

    Consultas do tipo 'IfcWall FireRating' retornam vazio no endpoint de busca
    de classes — verificado ao vivo contra a API.
    """
    client = MagicMock(spec=BSDDClient)
    client.search_class.side_effect = lambda query, domain="IFC": answers.get(query, [])
    client.get_class_properties.return_value = []
    return client


def test_build_falls_back_to_bare_class_when_property_query_is_empty():
    """pset_missing resolve pela classe quando 'classe propriedade' não casa."""
    client = _client_that_only_answers(
        {"IfcWall": [{"name": "IfcWall", "uri": "https://example.org/c/ifcwall", "domain": "IFC"}]}
    )
    client.get_class_properties.return_value = [
        BSDDProperty(name="FireRating", data_type="String", allowed_values=["REI 60"]),
    ]

    builder = BSDDContextBuilder(client)
    issue = _make_issue("pset_missing", check_property="FireRating", pset_name="Pset_WallCommon")

    context = builder.build(issue)

    assert context.class_name == "IfcWall"
    assert context.source_status == "live"
    assert [p.name for p in context.related_properties] == ["FireRating"]


def test_build_resolves_space_unnamed_by_class():
    """space_unnamed não fica sem grounding quando as queries de tabela falham."""
    client = _client_that_only_answers(
        {"IfcSpace": [{"name": "IfcSpace", "uri": "https://example.org/c/ifcspace", "domain": "IFC"}]}
    )

    builder = BSDDContextBuilder(client)
    issue = _make_issue("space_unnamed")

    context = builder.build(issue)

    assert context.class_name == "IfcSpace"
    assert context.source_status == "live"


def test_build_normalizes_deprecated_standardcase_classes():
    """IfcWallStandardCase não existe no dicionário IFC 4.3; cai para IfcWall."""
    client = _client_that_only_answers(
        {"IfcWall": [{"name": "IfcWall", "uri": "https://example.org/c/ifcwall", "domain": "IFC"}]}
    )
    client.get_class_properties.return_value = [
        BSDDProperty(name="FireRating", data_type="String"),
    ]

    builder = BSDDContextBuilder(client)
    issue = Issue(
        element_guid="A" * 22,
        element_class="IfcWallStandardCase",
        element_name="Parede 01",
        issue_type="pset_missing",
        severity="high",
        description="FireRating ausente",
        context={"check_property": "FireRating", "pset_name": "Pset_WallCommon"},
    )

    context = builder.build(issue)

    assert context.class_name == "IfcWall"
    assert context.source_status == "live"


def test_build_stops_at_first_query_that_resolves():
    """A busca não continua depois de encontrar resultado (economia de chamadas)."""
    client = _client_that_only_answers(
        {
            "IfcWall FireRating": [
                {"name": "Fire Rating", "uri": "https://example.org/c/fr", "domain": "IFC"}
            ],
            "IfcWall": [
                {"name": "IfcWall", "uri": "https://example.org/c/ifcwall", "domain": "IFC"}
            ],
        }
    )

    builder = BSDDContextBuilder(client)
    issue = _make_issue("pset_missing", check_property="FireRating", pset_name="Pset_WallCommon")

    builder.build(issue)

    assert client.search_class.call_count == 1


def test_build_never_searches_bsdd_by_element_name():
    """O nome do elemento no modelo não é vocabulário bSDD.

    Nomes de família do Revit ("Parede Externa", "Sala", "Room") produzem
    correspondências textuais absurdas na busca do bSDD — verificado ao vivo:
    "Room" casa IfcCooledBeamPASSIVE e "Sala" casa IfcEvaporativeCooler...
    Usar esses nomes como consulta injeta vocabulário oficial errado no prompt.
    """
    client = _client_that_only_answers({})

    builder = BSDDContextBuilder(client)
    issue = _make_issue("pset_missing", check_property="FireRating", pset_name="Pset_WallCommon")

    builder.build(issue)

    consultadas = [call.args[0] for call in client.search_class.call_args_list]
    assert "Parede Externa" not in consultadas
    assert not any("Parede" in q for q in consultadas), consultadas


def test_build_rejects_class_match_unrelated_to_the_ifc_class():
    """Uma classe bSDD que não corresponde à classe IFC não vira grounding."""
    client = _client_that_only_answers(
        {
            "IfcSpace": [
                {
                    "name": "IfcCooledBeamPASSIVE",
                    "uri": "https://example.org/c/cooledbeam",
                    "domain": "IFC",
                }
            ]
        }
    )

    builder = BSDDContextBuilder(client)
    issue = _make_issue("space_unnamed")

    context = builder.build(issue)

    assert context.class_name != "IfcCooledBeamPASSIVE"
    assert context.source_status == "empty"


def test_build_accepts_class_match_without_ifc_prefix():
    """'Space' é correspondência válida para IfcSpace (prefixo Ifc opcional)."""
    client = _client_that_only_answers(
        {"IfcSpace": [{"name": "Space", "uri": "https://example.org/c/space", "domain": "IFC"}]}
    )

    builder = BSDDContextBuilder(client)
    issue = _make_issue("space_unnamed")

    context = builder.build(issue)

    assert context.class_name == "Space"


def test_build_matches_bsdd_human_property_names():
    """O bSDD nomeia propriedades com espaços: 'Fire Rating' casa 'FireRating'.

    Verificado ao vivo: get_class_properties(IfcWall) devolve 233 propriedades
    com nomes humanos ("Fire Rating", "Global ID", "Thermal Transmittance").
    Comparar com o nome IFC sem normalizar descartava todas elas.
    """
    client = _client_that_only_answers(
        {"IfcWall": [{"name": "IfcWall", "uri": "https://example.org/c/ifcwall", "domain": "IFC"}]}
    )
    client.get_class_properties.return_value = [
        BSDDProperty(name="Fire Rating", data_type="String", allowed_values=["REI 60"]),
        BSDDProperty(name="Global ID", data_type="String"),
        BSDDProperty(name="Thermal Transmittance", data_type="Real", unit="W/(m²·K)"),
    ]

    builder = BSDDContextBuilder(client)
    issue = _make_issue("pset_missing", check_property="FireRating", pset_name="Pset_WallCommon")

    context = builder.build(issue)

    assert [p.name for p in context.related_properties] == ["Fire Rating"]
    assert context.source_status == "live"


def test_build_only_fetches_allowed_values_for_relevant_properties():
    """Valores permitidos são buscados só das propriedades que ficam no contexto.

    IfcWall tem 233 propriedades no bSDD; enriquecer todas antes de filtrar
    custaria 233 chamadas HTTP por issue — inviável numa corrida de dias.
    """
    client = _client_that_only_answers(
        {"IfcWall": [{"name": "IfcWall", "uri": "https://example.org/c/ifcwall", "domain": "IFC"}]}
    )
    client.get_class_properties.return_value = [
        BSDDProperty(name="Fire Rating", data_type="String", uri="https://example.org/p/fr"),
        BSDDProperty(name="Global ID", data_type="String", uri="https://example.org/p/gid"),
        BSDDProperty(name="Name", data_type="String", uri="https://example.org/p/name"),
    ]
    client.get_property_values.return_value = ["REI 60", "REI 90"]

    builder = BSDDContextBuilder(client)
    issue = _make_issue("pset_missing", check_property="FireRating", pset_name="Pset_WallCommon")

    context = builder.build(issue)

    assert client.get_property_values.call_count == 1
    assert client.get_property_values.call_args.args[0] == "https://example.org/p/fr"
    assert context.related_properties[0].allowed_values == ["REI 60", "REI 90"]


def test_build_prefers_exact_property_name_over_description_match():
    """Match exato de nome vem antes de match por descrição.

    O bSDD tem variantes como "Thermal Transmittance Summer", cuja descrição
    menciona a propriedade pedida. A propriedade exata deve vir primeiro.
    """
    client = _client_that_only_answers(
        {"IfcWindow": [{"name": "IfcWindow", "uri": "https://example.org/c/w", "domain": "IFC"}]}
    )
    client.get_class_properties.return_value = [
        BSDDProperty(
            name="Thermal Transmittance Summer",
            data_type="Real",
            description="ThermalTransmittance no verao",
        ),
        BSDDProperty(name="Thermal Transmittance", data_type="Real", unit="W/(m²·K)"),
    ]

    builder = BSDDContextBuilder(client)
    issue = Issue(
        element_guid="A" * 22,
        element_class="IfcWindow",
        element_name="Janela J1",
        issue_type="pset_missing",
        severity="high",
        description="ThermalTransmittance ausente",
        context={"check_property": "ThermalTransmittance", "pset_name": "Pset_WindowCommon"},
    )

    context = builder.build(issue)

    assert context.related_properties[0].name == "Thermal Transmittance"


def test_build_matches_boolean_property_without_is_prefix():
    """'IsLoadBearing' (IFC) casa 'Load Bearing' (bSDD).

    Os psets do IFC não são consistentes entre si — Pset_WallCommon usa
    IsLoadBearing e Pset_SlabCommon usa LoadBearing — enquanto o bSDD tem a
    propriedade genérica "Load Bearing".
    """
    client = _client_that_only_answers(
        {"IfcWall": [{"name": "IfcWall", "uri": "https://example.org/c/w", "domain": "IFC"}]}
    )
    client.get_class_properties.return_value = [
        BSDDProperty(name="Load Bearing", data_type="Boolean"),
        BSDDProperty(name="Fire Rating", data_type="String"),
    ]

    builder = BSDDContextBuilder(client)
    issue = _make_issue("pset_missing", check_property="IsLoadBearing", pset_name="Pset_WallCommon")

    context = builder.build(issue)

    assert [p.name for p in context.related_properties] == ["Load Bearing"]


def test_resolved_class_without_matching_property_is_still_live():
    """Classe resolvida ao vivo é fonte consultada, mesmo sem a propriedade.

    IfcSpace.Category não existe no bSDD: a classe resolve com URI canônica e a
    propriedade não. Reportar "empty" nesse caso confunde "não consultei" com
    "consultei e o dicionário não tem a propriedade".
    """
    client = _client_that_only_answers(
        {"IfcSpace": [{"name": "IfcSpace", "uri": "https://example.org/c/s", "domain": "IFC"}]}
    )
    client.get_class_properties.return_value = [
        BSDDProperty(name="Composition Type", data_type="String"),
    ]

    builder = BSDDContextBuilder(client)
    issue = Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="Sala 101",
        issue_type="pset_missing",
        severity="high",
        description="Category ausente",
        context={"check_property": "Category", "pset_name": "Pset_SpaceCommon"},
    )

    context = builder.build(issue)

    assert context.class_name == "IfcSpace"
    assert context.related_properties == []
    assert context.source_status == "live"


def test_space_naming_never_offers_the_ifc_class_as_a_name_candidate():
    """A própria classe IFC não é candidata a nome de ambiente.

    Quando o único resultado do bSDD é a classe (IfcSpace), oferecê-la como
    candidato instrui o LLM a responder "IfcSpace" onde se espera "Sala de
    Estar" — a mesma falha que zerou a acurácia da nomeação no benchmark.
    """
    client = _client_that_only_answers(
        {"IfcSpace": [{"name": "IfcSpace", "uri": "https://example.org/c/s", "domain": "IFC"}]}
    )

    builder = BSDDContextBuilder(client)
    issue = _make_issue("space_unnamed")

    context = builder.build(issue)

    assert context.class_name == "IfcSpace"
    assert [c.name for c in context.classification_suggestions] == []
