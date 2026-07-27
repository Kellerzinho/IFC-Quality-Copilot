"""Export por issue (P1): sem ele o agregado esconde qual estrato acerta.

O benchmark de 2026-07-27 só gravou agregados: um top-1 de 33% podia ser
"tudo mediano" ou "FireRating ótimo + ThermalTransmittance zero", e não havia
como distinguir depois do run — nem rodar teste pareado entre modelos, nem
saber se uma correção de prompt ajudou o estrato que ela mirava.

Estes testes fixam o registro por issue e a agregação por estrato.
"""

import json

from src.experiment.evaluator import Evaluator, GroundTruth, GroundTruthItem
from src.experiment.per_issue import (
    IssueOutcome,
    aggregate_by_stratum,
    build_issue_outcomes,
    write_outcomes_jsonl,
)
from src.models import Issue, Suggestion, SuggestionMetrics, SuggestionSet


def _issue(check_property: str = "FireRating", issue_type: str = "pset_missing") -> Issue:
    return Issue(
        element_guid="W" * 22,
        element_class="IfcWall",
        element_name="Parede 01",
        issue_type=issue_type,
        severity="high",
        description=f"{check_property} ausente",
        context={"check_property": check_property, "check_pset": "Pset_WallCommon"},
    )


def _suggestion_set(issue: Issue, values: list, **metric_kwargs) -> SuggestionSet:
    return SuggestionSet(
        issue_id=issue.id,
        suggestions=[
            Suggestion(label=str(v), value=v, justification="j", confidence="alta")
            for v in values
        ],
        metrics=SuggestionMetrics(issue_id=issue.id, **metric_kwargs),
    )


def _gt(issue: Issue, expected, alternatives: list | None = None) -> GroundTruth:
    return GroundTruth(
        items=[
            GroundTruthItem(
                element_guid=issue.element_guid,
                issue_type=issue.issue_type,
                check_property=str(issue.context.get("check_property") or ""),
                expected_value=expected,
                accepted_alternatives=alternatives or [],
            )
        ]
    )


# ---------------------------------------------------------------------------
# Registro por issue
# ---------------------------------------------------------------------------


def test_outcome_registra_acerto_top1_com_estrato_e_valores():
    issue = _issue()
    results = [(issue, _suggestion_set(issue, ["REI 60", "REI 90"]))]

    outcomes = build_issue_outcomes(results, _gt(issue, "REI 60"), Evaluator())

    assert len(outcomes) == 1
    out = outcomes[0]
    assert isinstance(out, IssueOutcome)
    assert out.stratum == "pset_missing/FireRating"
    assert out.match_top1 is True
    assert out.match_top3 is True
    assert out.expected == "REI 60"
    assert out.top_values == ["REI 60", "REI 90"]


def test_outcome_distingue_acerto_apenas_no_top3():
    """O caso que o revisor simulado conta como 'edited' precisa ser separável."""
    issue = _issue()
    results = [(issue, _suggestion_set(issue, ["EI 30", "REI 60"]))]

    out = build_issue_outcomes(results, _gt(issue, "REI 60"), Evaluator())[0]

    assert out.match_top1 is False
    assert out.match_top3 is True


def test_outcome_registra_abstencao_e_motivo_da_falha():
    """Abstenção (sem sugestão) não pode ser confundida com erro de conteúdo."""
    issue = _issue()
    empty = SuggestionSet(
        issue_id=issue.id,
        suggestions=[],
        metrics=SuggestionMetrics(issue_id=issue.id, attempts=3, failure_reason="empty"),
    )

    out = build_issue_outcomes([(issue, empty)], _gt(issue, "REI 60"), Evaluator())[0]

    assert out.match_top1 is False
    assert out.abstained is True
    assert out.failure_reason == "empty"
    assert out.top_values == []


def test_outcome_marca_issue_reusada_de_outra():
    """Issues que reaproveitam a primária não são observações independentes."""
    issue = _issue()
    reused = _suggestion_set(issue, ["REI 60"], reused_from_issue_id="primaria-123")

    out = build_issue_outcomes([(issue, reused)], _gt(issue, "REI 60"), Evaluator())[0]

    assert out.reused_from == "primaria-123"


def test_issues_sem_ground_truth_ficam_de_fora():
    """O denominador do breakdown é o mesmo do Evaluator: issues com GT."""
    com_gt = _issue("FireRating")
    sem_gt = _issue("Reference")
    results = [
        (com_gt, _suggestion_set(com_gt, ["REI 60"])),
        (sem_gt, _suggestion_set(sem_gt, ["qualquer"])),
    ]

    outcomes = build_issue_outcomes(results, _gt(com_gt, "REI 60"), Evaluator())

    assert [o.stratum for o in outcomes] == ["pset_missing/FireRating"]


def test_estrato_de_issue_sem_propriedade_usa_o_issue_type():
    issue = Issue(
        element_guid="S" * 22,
        element_class="IfcSpace",
        element_name="43",
        issue_type="space_unnamed",
        severity="low",
        description="sem nome",
        context={},
    )
    results = [(issue, _suggestion_set(issue, ["Dormitório"]))]

    out = build_issue_outcomes(results, _gt(issue, "Dormitório"), Evaluator())[0]

    assert out.stratum == "space_unnamed"


# ---------------------------------------------------------------------------
# Agregação por estrato
# ---------------------------------------------------------------------------


def test_aggregate_by_stratum_separa_forte_de_fraco():
    """Dois estratos com desempenho oposto não podem virar uma média única."""
    fire_ok = _issue("FireRating")
    thermal_ruim = _issue("ThermalTransmittance")
    gt = GroundTruth(
        items=[
            GroundTruthItem(
                element_guid=fire_ok.element_guid,
                issue_type="pset_missing",
                check_property="FireRating",
                expected_value="REI 60",
            ),
            GroundTruthItem(
                element_guid=thermal_ruim.element_guid,
                issue_type="pset_missing",
                check_property="ThermalTransmittance",
                expected_value=2.35,
            ),
        ]
    )
    results = [
        (fire_ok, _suggestion_set(fire_ok, ["REI 60"])),
        (thermal_ruim, _suggestion_set(thermal_ruim, [9.99])),
    ]

    outcomes = build_issue_outcomes(results, gt, Evaluator())
    rows = aggregate_by_stratum(outcomes)

    por_estrato = {r["stratum"]: r for r in rows}
    assert por_estrato["pset_missing/FireRating"]["top1"] == 1.0
    assert por_estrato["pset_missing/ThermalTransmittance"]["top1"] == 0.0
    assert por_estrato["pset_missing/FireRating"]["n"] == 1


def test_aggregate_reporta_taxa_de_abstencao_por_estrato():
    issue = _issue()
    vazio = SuggestionSet(
        issue_id=issue.id,
        suggestions=[],
        metrics=SuggestionMetrics(issue_id=issue.id, attempts=3, failure_reason="empty"),
    )

    outcomes = build_issue_outcomes([(issue, vazio)], _gt(issue, "REI 60"), Evaluator())
    row = aggregate_by_stratum(outcomes)[0]

    assert row["abstencao"] == 1.0


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------


def test_write_outcomes_jsonl_grava_uma_linha_por_issue(tmp_path):
    issue = _issue()
    outcomes = build_issue_outcomes(
        [(issue, _suggestion_set(issue, ["REI 60"]))], _gt(issue, "REI 60"), Evaluator()
    )
    destino = tmp_path / "run_0_issues.jsonl"

    write_outcomes_jsonl(outcomes, destino)

    linhas = destino.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 1
    registro = json.loads(linhas[0])
    assert registro["stratum"] == "pset_missing/FireRating"
    assert registro["match_top1"] is True
    assert registro["issue_id"] == issue.id
