"""Testes do framework de avaliação multi-perfil."""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.models import (
    Issue,
    ProfileRegistry,
    ReadinessProfile,
    ReadinessScore,
    Suggestion,
    SuggestionSet,
)
from tests.evaluation.evaluation_framework import Evaluator, GroundTruth


# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------


def _make_profile(
    profile_id: str,
    issue_types: list[str],
    blocking_severities: list[str] | None = None,
) -> ReadinessProfile:
    return ReadinessProfile(
        id=profile_id,
        name=f"Perfil {profile_id}",
        description="Perfil de teste",
        issue_types=issue_types,
        blocking_severities=blocking_severities or ["high"],
    )


def _make_suggestion(value: str, confidence: str = "alta") -> Suggestion:
    return Suggestion(
        label=value,
        value=value,
        justification="justificativa de teste",
        confidence=confidence,  # type: ignore[arg-type]
        source="llm",
    )


def _make_issue(
    issue_id: str,
    issue_type: str,
    severity: str = "high",
    element_guid: str | None = None,
) -> Issue:
    return Issue(
        id=issue_id,
        element_guid=element_guid or ("A" * 22),
        element_class="IfcWall",
        issue_type=issue_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        description="issue de teste",
    )


def _make_pair(
    issue: Issue,
    top_value: str | None = None,
    extra_values: list[str] | None = None,
) -> tuple[Issue, SuggestionSet]:
    suggestions: list[Suggestion] = []
    if top_value is not None:
        suggestions.append(_make_suggestion(top_value))
    for v in extra_values or []:
        suggestions.append(_make_suggestion(v, confidence="baixa"))
    return issue, SuggestionSet(issue_id=issue.id, suggestions=suggestions)


# ---------------------------------------------------------------------------
# Fixtures compartilhadas
# ---------------------------------------------------------------------------


@pytest.fixture
def profile_thermal() -> ReadinessProfile:
    """Perfil que só avalia pset_missing (dados térmicos)."""
    return _make_profile("thermal", issue_types=["pset_missing"])


@pytest.fixture
def profile_spaces() -> ReadinessProfile:
    """Perfil que só avalia space_unnamed."""
    return _make_profile("spaces", issue_types=["space_unnamed"])


@pytest.fixture
def profile_full() -> ReadinessProfile:
    """Perfil que avalia todos os tipos de issue usados nos testes."""
    return _make_profile(
        "full",
        issue_types=["pset_missing", "space_unnamed", "relation_broken"],
    )


@pytest.fixture
def results_mixed() -> list[tuple[Issue, SuggestionSet]]:
    """Lista de pares com issues de tipos distintos e sugestões variadas."""
    i1 = _make_issue("i1", "pset_missing")
    i2 = _make_issue("i2", "pset_missing")
    i3 = _make_issue("i3", "space_unnamed")
    i4 = _make_issue("i4", "relation_broken")

    return [
        _make_pair(i1, top_value="2.48", extra_values=["3.00", "1.50"]),
        _make_pair(i2, top_value="wrong_val"),
        _make_pair(i3, top_value="Banheiro Social"),
        _make_pair(i4, top_value=None),  # sem sugestão
    ]


@pytest.fixture
def ground_truth_all(results_mixed) -> GroundTruth:
    """Ground truth com valor correto para i1, i2 e i3; sem entrada para i4."""
    return GroundTruth(
        corrections={
            "i1": "2.48",
            "i2": "2.48",  # i2 top suggestion é errada
            "i3": "Banheiro Social",
        }
    )


# ---------------------------------------------------------------------------
# test_evaluate_with_profile_filters
# ---------------------------------------------------------------------------


class TestEvaluateWithProfileFilters:
    """Avaliação filtrada por perfil considera apenas issues do issue_types do perfil."""

    def test_filtra_issues_pelo_perfil(
        self, results_mixed, ground_truth_all, profile_thermal
    ):
        """Apenas issues pset_missing devem ser avaliadas para o perfil thermal."""
        evaluator = Evaluator()
        metrics = evaluator.evaluate(results_mixed, ground_truth_all, profile=profile_thermal)

        # i1 (correto) e i2 (errado) são pset_missing → total_evaluated = 2
        assert metrics.total_evaluated == 2
        assert metrics.profile_id == "thermal"

    def test_acuracia_top1_com_filtro(
        self, results_mixed, ground_truth_all, profile_thermal
    ):
        """i1 acerta top1; i2 erra → accuracy_top1 = 0.5."""
        evaluator = Evaluator()
        metrics = evaluator.evaluate(results_mixed, ground_truth_all, profile=profile_thermal)
        assert metrics.accuracy_top1 == pytest.approx(0.5, abs=1e-4)

    def test_acuracia_top3_com_filtro(
        self, results_mixed, ground_truth_all, profile_thermal
    ):
        """i1 acerta top1 (conta no top3); i2 não tem "2.48" entre as top3 → acc3 = 0.5."""
        evaluator = Evaluator()
        metrics = evaluator.evaluate(results_mixed, ground_truth_all, profile=profile_thermal)
        assert metrics.accuracy_top3 == pytest.approx(0.5, abs=1e-4)

    def test_perfil_sem_issues_correspondentes(
        self, results_mixed, ground_truth_all
    ):
        """Perfil cujo issue_type não aparece nos resultados retorna métricas zeradas."""
        profile = _make_profile("asset", issue_types=["asset_unidentified"])
        evaluator = Evaluator()
        metrics = evaluator.evaluate(results_mixed, ground_truth_all, profile=profile)

        assert metrics.total_evaluated == 0
        assert metrics.accuracy_top1 == 0.0
        assert metrics.accuracy_top3 == 0.0

    def test_sem_perfil_avalia_todos(self, results_mixed, ground_truth_all):
        """Sem perfil, todas as issues com GT são avaliadas (i1, i2, i3)."""
        evaluator = Evaluator()
        metrics = evaluator.evaluate(results_mixed, ground_truth_all, profile=None)
        assert metrics.total_evaluated == 3
        assert metrics.profile_id is None


# ---------------------------------------------------------------------------
# test_readiness_before_after
# ---------------------------------------------------------------------------


class TestReadinessBeforeAfter:
    """ReadinessScore calculado antes e após aplicação das correções do GT."""

    def test_readiness_before_inclui_todos(
        self, results_mixed, ground_truth_all, profile_thermal
    ):
        """readiness_before é calculado com todas as issues do perfil presentes."""
        evaluator = Evaluator()
        metrics = evaluator.evaluate(results_mixed, ground_truth_all, profile=profile_thermal)

        assert metrics.readiness_before is not None
        assert isinstance(metrics.readiness_before, ReadinessScore)
        assert metrics.readiness_before.failed == 2  # i1 e i2
        assert metrics.readiness_before.profile_id == "thermal"

    def test_readiness_after_remove_corrigidos(
        self, results_mixed, ground_truth_all, profile_thermal
    ):
        """readiness_after remove issues presentes no GT (i1 e i2 → 0 restantes)."""
        evaluator = Evaluator()
        metrics = evaluator.evaluate(results_mixed, ground_truth_all, profile=profile_thermal)

        assert metrics.readiness_after is not None
        assert metrics.readiness_after.failed == 0
        assert metrics.readiness_after.score_percent == pytest.approx(100.0, abs=1e-1)

    def test_readiness_improvement_positivo_quando_gt_cobre_issues(
        self, results_mixed, ground_truth_all, profile_thermal
    ):
        """Com todas as issues cobertas pelo GT, o improvement deve ser positivo."""
        evaluator = Evaluator()
        metrics = evaluator.evaluate(results_mixed, ground_truth_all, profile=profile_thermal)

        assert metrics.readiness_improvement > 0.0

    def test_readiness_nulo_sem_perfil(self, results_mixed, ground_truth_all):
        """Sem perfil, readiness_before e readiness_after são None."""
        evaluator = Evaluator()
        metrics = evaluator.evaluate(results_mixed, ground_truth_all, profile=None)

        assert metrics.readiness_before is None
        assert metrics.readiness_after is None
        assert metrics.readiness_improvement == 0.0

    def test_improvement_zero_quando_gt_vazio(
        self, results_mixed, profile_thermal
    ):
        """GT vazio → nenhuma issue removida → before == after → improvement = 0."""
        evaluator = Evaluator()
        metrics = evaluator.evaluate(results_mixed, GroundTruth(), profile=profile_thermal)

        assert metrics.readiness_improvement == pytest.approx(0.0, abs=1e-4)
        assert metrics.readiness_before is not None
        assert metrics.readiness_after is not None
        assert metrics.readiness_before.score_percent == metrics.readiness_after.score_percent


# ---------------------------------------------------------------------------
# test_evaluate_all_profiles
# ---------------------------------------------------------------------------


class TestEvaluateAllProfiles:
    """evaluate_all_profiles percorre todos os perfis do registry."""

    @pytest.fixture
    def registry_two_profiles(
        self, profile_thermal, profile_spaces
    ) -> ProfileRegistry:
        registry = ProfileRegistry()
        registry.register(profile_thermal)
        registry.register(profile_spaces)
        return registry

    @pytest.fixture
    def mock_pipeline(self, results_mixed):
        """Pipeline mock com issues_suggestions pré-definidas."""
        pipeline = MagicMock()
        pipeline.issues_suggestions = results_mixed
        return pipeline

    def test_retorna_metrica_para_cada_perfil(
        self, mock_pipeline, ground_truth_all, registry_two_profiles
    ):
        """Deve retornar um EvaluationMetrics por perfil registrado."""
        evaluator = Evaluator()
        all_metrics = evaluator.evaluate_all_profiles(
            mock_pipeline, ground_truth_all, registry_two_profiles
        )

        assert set(all_metrics.keys()) == {"thermal", "spaces"}

    def test_profile_id_preenchido_corretamente(
        self, mock_pipeline, ground_truth_all, registry_two_profiles
    ):
        """profile_id em cada EvaluationMetrics deve corresponder ao perfil."""
        evaluator = Evaluator()
        all_metrics = evaluator.evaluate_all_profiles(
            mock_pipeline, ground_truth_all, registry_two_profiles
        )

        assert all_metrics["thermal"].profile_id == "thermal"
        assert all_metrics["spaces"].profile_id == "spaces"

    def test_by_profile_preenchido(
        self, mock_pipeline, ground_truth_all, registry_two_profiles
    ):
        """by_profile deve conter entradas para todos os perfis em cada métrica."""
        evaluator = Evaluator()
        all_metrics = evaluator.evaluate_all_profiles(
            mock_pipeline, ground_truth_all, registry_two_profiles
        )

        for pid, metrics in all_metrics.items():
            assert "thermal" in metrics.by_profile, f"thermal ausente em by_profile de {pid}"
            assert "spaces" in metrics.by_profile, f"spaces ausente em by_profile de {pid}"

    def test_by_profile_contem_campos_esperados(
        self, mock_pipeline, ground_truth_all, registry_two_profiles
    ):
        """Cada entrada de by_profile deve ter os campos compactos definidos."""
        evaluator = Evaluator()
        all_metrics = evaluator.evaluate_all_profiles(
            mock_pipeline, ground_truth_all, registry_two_profiles
        )

        expected_keys = {"accuracy_top1", "accuracy_top3", "precision", "recall", "f1", "readiness_improvement"}
        for metrics in all_metrics.values():
            for summary in metrics.by_profile.values():
                assert expected_keys == set(summary.keys())

    def test_registry_vazio_retorna_dict_vazio(self, mock_pipeline, ground_truth_all):
        """Registry sem perfis deve retornar dicionário vazio."""
        evaluator = Evaluator()
        all_metrics = evaluator.evaluate_all_profiles(
            mock_pipeline, ground_truth_all, ProfileRegistry()
        )
        assert all_metrics == {}


# ---------------------------------------------------------------------------
# test_compare_profiles_dataframe
# ---------------------------------------------------------------------------


class TestCompareProfilesDataFrame:
    """compare_profiles retorna DataFrame estruturado para comparação cross-profile."""

    @pytest.fixture
    def multi_profile_metrics(
        self, results_mixed, ground_truth_all, profile_thermal, profile_spaces, profile_full
    ) -> dict:
        evaluator = Evaluator()
        return {
            "thermal": evaluator.evaluate(results_mixed, ground_truth_all, profile=profile_thermal),
            "spaces": evaluator.evaluate(results_mixed, ground_truth_all, profile=profile_spaces),
            "full": evaluator.evaluate(results_mixed, ground_truth_all, profile=profile_full),
        }

    def test_retorna_dataframe(self, multi_profile_metrics):
        """compare_profiles deve retornar um pd.DataFrame."""
        evaluator = Evaluator()
        df = evaluator.compare_profiles(multi_profile_metrics)
        assert isinstance(df, pd.DataFrame)

    def test_colunas_obrigatorias(self, multi_profile_metrics):
        """DataFrame deve conter exatamente as colunas especificadas."""
        evaluator = Evaluator()
        df = evaluator.compare_profiles(multi_profile_metrics)
        expected = {
            "profile", "accuracy_top1", "accuracy_top3",
            "precision", "recall", "f1",
            "readiness_before", "readiness_after", "improvement",
        }
        assert set(df.columns) == expected

    def test_uma_linha_por_perfil(self, multi_profile_metrics):
        """Deve haver exatamente uma linha por perfil no dicionário de entrada."""
        evaluator = Evaluator()
        df = evaluator.compare_profiles(multi_profile_metrics)
        assert len(df) == len(multi_profile_metrics)

    def test_coluna_profile_contem_ids(self, multi_profile_metrics):
        """A coluna 'profile' deve conter os IDs dos perfis avaliados."""
        evaluator = Evaluator()
        df = evaluator.compare_profiles(multi_profile_metrics)
        assert set(df["profile"].tolist()) == {"thermal", "spaces", "full"}

    def test_valores_numericos_em_accuracy(self, multi_profile_metrics):
        """Colunas de acurácia devem ser numéricas e estar no intervalo [0, 1]."""
        evaluator = Evaluator()
        df = evaluator.compare_profiles(multi_profile_metrics)
        for col in ("accuracy_top1", "accuracy_top3", "precision", "recall", "f1"):
            assert df[col].between(0.0, 1.0).all(), f"Coluna {col} fora do intervalo [0, 1]"

    def test_readiness_before_none_quando_sem_issues(self):
        """Perfil sem issues correspondentes resulta em readiness_before com score 0."""
        profile = _make_profile("empty", issue_types=["asset_unidentified"])
        i1 = _make_issue("x1", "pset_missing")
        results = [_make_pair(i1, top_value="2.48")]
        gt = GroundTruth(corrections={"x1": "2.48"})

        evaluator = Evaluator()
        metrics = evaluator.evaluate(results, gt, profile=profile)
        df = evaluator.compare_profiles({"empty": metrics})

        # Sem issues filtradas, readiness_before.score_percent == 100 (0 falhas / 1 check)
        assert df.loc[df["profile"] == "empty", "readiness_before"].iloc[0] == pytest.approx(100.0, abs=1e-1)

    def test_dataframe_vazio_com_dict_vazio(self):
        """Dict vazio retorna DataFrame vazio com colunas corretas."""
        evaluator = Evaluator()
        df = evaluator.compare_profiles({})

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert "profile" in df.columns
        assert "accuracy_top1" in df.columns
