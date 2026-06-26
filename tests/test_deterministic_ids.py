"""Testes de IDs determinísticos por conteúdo — Issue e OperationalRule (F3).

Reprodutibilidade: duas execuções de `diagnose()` sobre o mesmo IFC devem produzir
os mesmos `Issue.id`/`OperationalRule.id`, para que cache de sugestões e ground truth
casem entre execuções. Os ids passam a ser derivados do conteúdo-chave (SHA1), não de
`uuid4()` aleatório.
"""

from src.models import Issue, OperationalRule


def _pset_issue(element_guid: str, check_property: str = "ThermalTransmittance") -> Issue:
    """Constrói uma issue pset_missing com o contexto-chave típico."""
    return Issue(
        element_guid=element_guid,
        element_class="IfcWall",
        issue_type="pset_missing",
        severity="high",
        description="propriedade ausente",
        context={"check_pset": "Pset_WallCommon", "check_property": check_property},
    )


class TestIssueDeterministicId:
    def test_same_content_yields_same_id(self):
        """Duas issues com o mesmo conteúdo-chave têm o mesmo id (reprodutível)."""
        a = _pset_issue("3nJOFsJsX8QO2odKZbQnBj")
        b = _pset_issue("3nJOFsJsX8QO2odKZbQnBj")
        assert a.id == b.id

    def test_different_element_yields_different_id(self):
        """Elementos distintos geram ids distintos."""
        a = _pset_issue("3nJOFsJsX8QO2odKZbQnBj")
        b = _pset_issue("1aBcDeFgHiJkLmNoPqRsTu")
        assert a.id != b.id

    def test_different_property_yields_different_id(self):
        """Propriedades distintas no mesmo elemento geram ids distintos."""
        a = _pset_issue("3nJOFsJsX8QO2odKZbQnBj", check_property="ThermalTransmittance")
        b = _pset_issue("3nJOFsJsX8QO2odKZbQnBj", check_property="FireRating")
        assert a.id != b.id

    def test_explicit_id_is_preserved(self):
        """Um id explicitamente fornecido não é sobrescrito (compat com testes legados)."""
        issue = Issue(
            id="custom123",
            element_guid="3nJOFsJsX8QO2odKZbQnBj",
            element_class="IfcWall",
            issue_type="pset_missing",
            severity="high",
            description="x",
            context={"check_pset": "Pset_WallCommon", "check_property": "ThermalTransmittance"},
        )
        assert issue.id == "custom123"

    def test_no_collisions_across_distinct_issues(self):
        """Issues com conteúdos distintos não colidem em id."""
        ids = {_pset_issue(f"{i:022d}").id for i in range(50)}
        assert len(ids) == 50


class TestOperationalRuleDeterministicId:
    def test_same_content_yields_same_id(self):
        """Duas regras com o mesmo conteúdo têm o mesmo id."""
        kwargs = dict(
            source_spec="Spec Thermal",
            filter_entity="IfcWall",
            check_pset="Pset_WallCommon",
            check_property="ThermalTransmittance",
            check_type="is_numeric",
        )
        assert OperationalRule(**kwargs).id == OperationalRule(**kwargs).id

    def test_different_property_yields_different_id(self):
        """Regras com check_property distinto geram ids distintos."""
        a = OperationalRule(
            source_spec="S", filter_entity="IfcWall", check_pset="Pset_WallCommon",
            check_property="ThermalTransmittance", check_type="is_numeric",
        )
        b = OperationalRule(
            source_spec="S", filter_entity="IfcWall", check_pset="Pset_WallCommon",
            check_property="FireRating", check_type="is_numeric",
        )
        assert a.id != b.id
