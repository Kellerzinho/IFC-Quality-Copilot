"""Comparação pareada entre modelos na unidade correta: estímulo, não issue.

Com ``--reuse-equivalent``, uma resposta do LLM é copiada para todas as issues
estruturalmente equivalentes: no prédio, **6 estímulos** de ``FireRating``
respondem por **1020 issues** (40% do ground truth). Testar no nível de issue
trata 1020 cópias de 6 respostas como 1020 observações independentes e produz
significância onde não há.

Medido em 2026-07-27: gemma2:9b vs qwen2.5:7b-instruct dava p < 0,0001 no nível
de issue (230 discordâncias) — mas as discordâncias eram cópias de **2**
respostas distintas, e no nível de estímulo o mesmo teste não rejeita.
"""

import pytest

from src.experiment.per_issue import IssueOutcome, paired_comparison


def _outcome(issue_id: str, acertou: bool, reused_from: str | None = None) -> IssueOutcome:
    return IssueOutcome(
        issue_id=issue_id,
        element_guid="G" * 22,
        element_class="IfcWall",
        issue_type="pset_missing",
        check_property="FireRating",
        stratum="pset_missing/FireRating",
        match_top1=acertou,
        match_top3=acertou,
        reused_from=reused_from,
    )


def _um_estimulo_replicado(prefixo: str, n_copias: int, acertou: bool) -> list[IssueOutcome]:
    """Uma primária + n cópias reusadas — tudo derivado de UMA chamada ao LLM."""
    primaria = _outcome(f"{prefixo}-p", acertou)
    copias = [
        _outcome(f"{prefixo}-c{i}", acertou, reused_from=f"{prefixo}-p")
        for i in range(n_copias)
    ]
    return [primaria, *copias]


def test_unidade_estimulo_conta_uma_observacao_por_chamada_ao_llm():
    a = _um_estimulo_replicado("s1", 199, acertou=True)
    b = _um_estimulo_replicado("s1", 199, acertou=False)

    resultado = paired_comparison(a, b, unit="stimulus")

    assert resultado["n"] == 1
    assert resultado["so_a"] == 1
    assert resultado["so_b"] == 0


def test_nivel_de_issue_infla_o_n_com_copias():
    """Documenta o comportamento errado que motivou o parâmetro."""
    a = _um_estimulo_replicado("s1", 199, acertou=True)
    b = _um_estimulo_replicado("s1", 199, acertou=False)

    resultado = paired_comparison(a, b, unit="issue")

    assert resultado["n"] == 200
    assert resultado["so_a"] == 200


def test_significancia_espuria_desaparece_na_unidade_certa():
    """Duas respostas de diferença viram 'p<0,0001' quando replicadas em cópias."""
    a: list[IssueOutcome] = []
    b: list[IssueOutcome] = []
    # 2 estímulos onde A ganha, replicados 100x cada
    for i in range(2):
        a += _um_estimulo_replicado(f"dif{i}", 99, acertou=True)
        b += _um_estimulo_replicado(f"dif{i}", 99, acertou=False)
    # 4 estímulos em que empatam
    for i in range(4):
        a += _um_estimulo_replicado(f"eq{i}", 99, acertou=True)
        b += _um_estimulo_replicado(f"eq{i}", 99, acertou=True)

    por_issue = paired_comparison(a, b, unit="issue")
    por_estimulo = paired_comparison(a, b, unit="stimulus")

    assert por_issue["p_value"] < 0.001, "cenário não reproduz a significância espúria"
    assert por_estimulo["p_value"] > 0.05, "no nível de estímulo não há evidência"
    assert por_estimulo["n"] == 6


def test_empate_total_nao_rejeita():
    a = _um_estimulo_replicado("s1", 10, acertou=True)
    b = _um_estimulo_replicado("s1", 10, acertou=True)

    resultado = paired_comparison(a, b, unit="stimulus")

    assert resultado["p_value"] == pytest.approx(1.0)


def test_so_compara_issues_presentes_nos_dois_modelos():
    a = [_outcome("comum", True), _outcome("so-em-a", True)]
    b = [_outcome("comum", False)]

    resultado = paired_comparison(a, b, unit="issue")

    assert resultado["n"] == 1
