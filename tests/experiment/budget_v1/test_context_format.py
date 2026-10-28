"""Estudo de formato de contexto: gerador determinístico, prompts, schema e harness dry-run."""

import json
import sys
from pathlib import Path

import pytest

from src.experiment.budget_v1 import context_format as cf

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import estudo_formato_contexto as cli  # noqa: E402


@pytest.fixture(scope="module")
def cases() -> list[cf.SyntheticCase]:
    """Conjunto padrão pequeno."""
    return cf.generate_cases(seed=7, per_kind=3)


# --- gerador -------------------------------------------------------------------------


def test_same_seed_gives_identical_jsonl(tmp_path: Path) -> None:
    a = cf.write_jsonl(cf.generate_cases(seed=11, per_kind=2), tmp_path / "a.jsonl")
    b = cf.write_jsonl(cf.generate_cases(seed=11, per_kind=2), tmp_path / "b.jsonl")
    assert a.read_bytes() == b.read_bytes()


def test_other_seed_changes_cases() -> None:
    assert cf.generate_cases(seed=1, per_kind=2) != cf.generate_cases(seed=2, per_kind=2)


def test_jsonl_round_trip(tmp_path: Path, cases: list[cf.SyntheticCase]) -> None:
    path = cf.write_jsonl(cases, tmp_path / "casos.jsonl")
    assert cf.read_jsonl(path) == cases
    assert path.read_bytes().count(b"\n") == len(cases)


def test_every_concept_and_kind_is_covered(cases: list[cf.SyntheticCase]) -> None:
    summary = cf.summarize_cases(cases)
    assert set(summary) == {"fck", "cobrimento", "caa"}
    assert set(summary["fck"]) == {
        "direto",
        "conversao",
        "unidade_no_nome",
        "classe",
        "abstencao_ausente",
        "abstencao_sem_unidade",
        "conflito",
    }
    assert "classe" not in summary["cobrimento"]
    assert set(summary["caa"]) == {"direto", "abstencao_ausente", "conflito"}
    assert all(n == 3 for kinds in summary.values() for n in kinds.values())


def test_case_ids_are_unique(cases: list[cf.SyntheticCase]) -> None:
    assert len({c.case_id for c in cases}) == len(cases)


def test_gold_source_is_one_of_the_native_properties(cases: list[cf.SyntheticCase]) -> None:
    for case in cases:
        names = {f"{p.pset}.{p.name}" for p in case.properties}
        if case.gold.outcome == "valor":
            assert case.gold.source in names, case.case_id
            assert case.gold.unit == cf.TARGET_UNIT[case.concept]
        else:
            assert case.gold.source is None
            assert case.gold.reason is not None


@pytest.mark.parametrize(
    ("unit", "written", "fck"),
    [("Pa", 25e6, 25), ("kN/cm²", 2.5, 25), ("kgf/cm²", 254.93, 25), ("MPa", 25.0, 25)],
)
def test_fck_unit_conversions_back_to_mpa(unit: str, written: float, fck: int) -> None:
    to_mpa = {"Pa": 1e-6, "kN/cm²": 10, "kgf/cm²": cf.KGF_CM2_IN_MPA, "MPa": 1}[unit]
    assert written * to_mpa == pytest.approx(fck, rel=1e-3)


def test_conversion_cases_carry_a_non_standard_unit(cases: list[cf.SyntheticCase]) -> None:
    for case in (c for c in cases if c.kind == "conversao"):
        [carrier] = [p for p in case.properties if f"{p.pset}.{p.name}" == case.gold.source]
        assert carrier.unit not in (None, cf.TARGET_UNIT[case.concept])
        factor = cf.VOCAB.conversions[str(cf.TARGET_UNIT[case.concept])][str(carrier.unit)]
        assert float(carrier.value) * factor == pytest.approx(case.gold.value, rel=1e-3)


def test_class_strings_map_to_fck(cases: list[cf.SyntheticCase]) -> None:
    for case in (c for c in cases if c.kind == "classe"):
        [carrier] = [p for p in case.properties if f"{p.pset}.{p.name}" == case.gold.source]
        fck = int(case.gold.value)
        assert str(carrier.value) in {f"C{fck}", f"C-{fck}", f"C{fck}/{cf.VOCAB.cube_of[fck]}"}
        assert carrier.unit is None


def test_absent_fck_cases_offer_fcd_as_trap(cases: list[cf.SyntheticCase]) -> None:
    """fcd (resistência de cálculo) não é fck: o gabarito é abstenção."""
    for case in (c for c in cases if c.concept == "fck" and c.kind == "abstencao_ausente"):
        assert any(p.name == "fcd" for p in case.properties)
        assert case.gold.reason == "ausente"


def test_unitless_and_conflict_cases_abstain(cases: list[cf.SyntheticCase]) -> None:
    for case in cases:
        if case.kind == "abstencao_sem_unidade":
            assert case.gold.reason == "unidade_desconhecida"
        if case.kind == "conflito":
            assert case.gold.reason == "conflito"
            same_name = [p for p in case.properties if p.pset.endswith("(tipo)")]
            assert len(same_name) == 1


def test_conflict_cases_have_units_so_conflict_is_the_only_reason(
    cases: list[cf.SyntheticCase],
) -> None:
    for case in (c for c in cases if c.kind == "conflito" and c.concept != "caa"):
        carriers = [p for p in case.properties if p.unit == cf.TARGET_UNIT[case.concept]]
        values = {
            p.value for p in carriers if p.name not in {"fcd", "fct,m", "Módulo de elasticidade"}
        }
        assert len(values) == 2, case.case_id


def test_cover_follows_nbr6118_table_by_caa() -> None:
    assert cf.COVER_BY_CAA["II"] == {"viga_pilar": 30, "laje": 25}
    assert cf.COVER_BY_CAA["IV"]["viga_pilar"] == 50


# --- prompts e formatos ------------------------------------------------------------


@pytest.mark.parametrize("fmt", cf.FORMATS)
@pytest.mark.parametrize("language", cf.LANGUAGES)
def test_prompt_never_leaks_gold_metadata(
    cases: list[cf.SyntheticCase], fmt: str, language: str
) -> None:
    for case in cases:
        prompt = cf.build_prompt(case, fmt, "inteiro", language)  # type: ignore[arg-type]
        assert case.case_id not in prompt
        if "_" in case.kind:  # rótulos internos; "direto"/"classe" são palavras comuns
            assert case.kind not in prompt
        assert "gold" not in prompt
        assert "gabarito" not in prompt


def test_json_formats_parse_and_hold_the_same_facts(cases: list[cf.SyntheticCase]) -> None:
    case = cases[0]
    indented = json.loads(cf.render_context(case, "json_indentado", "inteiro"))
    compact = json.loads(cf.render_context(case, "json_compacto", "inteiro"))
    assert indented == compact
    assert len(indented["propriedades"]) == len(case.properties)


def test_compact_json_is_shorter_than_indented(cases: list[cf.SyntheticCase]) -> None:
    case = cases[0]
    assert len(cf.render_context(case, "json_compacto", "inteiro")) < len(
        cf.render_context(case, "json_indentado", "inteiro")
    )


@pytest.mark.parametrize("fmt", ["markdown", "tabela"])
def test_text_formats_list_every_property(cases: list[cf.SyntheticCase], fmt: str) -> None:
    for case in cases[:5]:
        text = cf.render_context(case, fmt, "inteiro")  # type: ignore[arg-type]
        for p in case.properties:
            assert p.name in text


def test_missing_unit_is_shown_explicitly_not_as_dimensionless(
    cases: list[cf.SyntheticCase],
) -> None:
    case = next(c for c in cases if c.kind == "abstencao_sem_unidade")
    assert "—" in cf.render_context(case, "tabela", "inteiro")
    assert '"unidade": null' in cf.render_context(case, "json_indentado", "inteiro")


def test_retrieval_is_bounded_and_deterministic(cases: list[cf.SyntheticCase]) -> None:
    for case in cases:
        got = cf.retrieve(case)
        assert len(got) == min(cf.RETRIEVE_TOP_K, len(case.properties))
        assert got == cf.retrieve(case)


def test_retrieved_scope_is_never_larger_than_full(cases: list[cf.SyntheticCase]) -> None:
    for case in cases:
        assert cf.approx_tokens(
            cf.build_prompt(case, "json_compacto", "recuperado", "pt")
        ) <= cf.approx_tokens(cf.build_prompt(case, "json_compacto", "inteiro", "pt"))


def test_approx_tokens_rounds_up() -> None:
    assert cf.approx_tokens("") == 0
    assert cf.approx_tokens("abcd") == 1
    assert cf.approx_tokens("abcde") == 2


# --- schema e pontuação --------------------------------------------------------------


def test_output_schema_is_draft_2020_12() -> None:
    schema = cf.output_json_schema()
    assert schema["$schema"].endswith("2020-12/schema")
    assert set(schema["required"]) == {
        "resultado",
        "propriedade_origem",
        "valor",
        "unidade",
        "motivo",
    }


@pytest.mark.parametrize(
    ("raw", "motivo"),
    [
        ('{"resultado": "valor"', "json_invalido"),
        (
            '{"resultado": "talvez", "propriedade_origem": null, "valor": null, '
            '"unidade": null, "motivo": null}',
            "schema",
        ),
        (
            '{"resultado": "valor", "propriedade_origem": "a.b", "valor": 25, '
            '"unidade": "kgf/cm²", "motivo": null}',
            "schema",
        ),
        ('{"resultado": "valor", "valor": 25}', "schema"),
    ],
)
def test_invalid_outputs_are_refused_with_reason(raw: str, motivo: str) -> None:
    out, error = cf.parse_output(raw)
    assert out is None
    assert error is not None
    assert error.startswith(motivo)


def test_oracle_answers_score_perfectly(cases: list[cf.SyntheticCase]) -> None:
    for case in cases:
        s = cf.score(case, cf.simulated_response(case, "oraculo"))
        assert s.json_valido
        if case.gold.outcome == "valor":
            assert s.acerto_top1
            assert not s.erro_unidade
        else:
            assert s.abstencao_correta
            assert s.motivo_abstencao_correto


def test_unit_factor_error_is_counted_as_unit_error() -> None:
    case = next(
        c
        for c in cf.generate_cases(seed=3, per_kind=2)
        if c.kind == "direto" and c.concept == "fck"
    )
    raw = json.dumps(
        {
            "resultado": "valor",
            "propriedade_origem": case.gold.source,
            "valor": case.gold.value * 1000,
            "unidade": "MPa",
            "motivo": None,
        }
    )
    s = cf.score(case, raw)
    assert s.erro_unidade
    assert not s.acerto_top1


def test_value_on_abstention_case_is_an_undue_proposal() -> None:
    case = next(c for c in cf.generate_cases(seed=3, per_kind=1) if c.kind == "conflito")
    raw = json.dumps(
        {
            "resultado": "valor",
            "propriedade_origem": "x.y",
            "valor": 30.0,
            "unidade": "MPa",
            "motivo": None,
        }
    )
    assert cf.score(case, raw).proposta_indevida


def test_caa_comparison_ignores_case() -> None:
    case = next(
        c
        for c in cf.generate_cases(seed=5, per_kind=1)
        if c.concept == "caa" and c.kind == "direto"
    )
    raw = json.dumps(
        {
            "resultado": "valor",
            "propriedade_origem": case.gold.source,
            "valor": str(case.gold.value).lower(),
            "unidade": None,
            "motivo": None,
        }
    )
    assert cf.score(case, raw).acerto_top1


# --- harness ------------------------------------------------------------------------


def test_dry_run_covers_full_grid(cases: list[cf.SyntheticCase]) -> None:
    reports = cf.run_dry(cases)
    assert len(reports) == len(cf.FORMATS) * len(cf.SCOPES) * len(cf.LANGUAGES) * 2
    oracle = [r for r in reports if r.simulador == "oraculo"]
    assert all(
        r.json_valido == 1.0 and r.acerto_top1 == 1.0 and r.abstencao_correta == 1.0 for r in oracle
    )
    noisy = [r for r in reports if r.simulador == "ruidoso"]
    assert any(r.json_valido < 1.0 for r in noisy)
    assert all(r.latencia_ms is None for r in reports)
    assert all(r.vram_mib is None for r in reports)


def test_dry_run_is_deterministic(cases: list[cf.SyntheticCase]) -> None:
    assert cf.run_dry(cases) == cf.run_dry(cases)


def test_retrieval_coverage_is_reported_only_for_retrieved_scope(
    cases: list[cf.SyntheticCase],
) -> None:
    for r in cf.run_dry(cases, simulators=("oraculo",)):
        assert (r.recuperacao_cobre_gabarito is None) == (r.escopo == "inteiro")


@pytest.mark.parametrize("authorization", [None, "", "   "])
def test_real_mode_is_blocked_without_explicit_authorization(authorization: str | None) -> None:
    with pytest.raises(cf.RealModeBlocked, match="--confirmo-autorizacao"):
        cf.require_mode("real", authorization)


def test_real_mode_passes_only_with_authorization_record() -> None:
    cf.require_mode("real", "orientador, 2026-11-03, e-mail")
    cf.require_mode("dry_run")
    with pytest.raises(cf.RealModeBlocked):
        cf.require_mode("outro", "x")


def test_module_has_no_llm_client_or_network_import() -> None:
    source = Path(cf.__file__).read_text(encoding="utf-8")
    imports = [ln for ln in source.splitlines() if ln.startswith(("import ", "from "))]
    for forbidden in ("ollama", "httpx", "requests", "urllib", "socket", "suggestion_engine"):
        assert not any(forbidden in ln for ln in imports), forbidden
    assert "11434" not in source


def test_report_files_are_written(tmp_path: Path, cases: list[cf.SyntheticCase]) -> None:
    json_path, md_path = cf.write_report(cases, cf.run_dry(cases), tmp_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["mode"] == "dry_run"
    assert "SIMULADAS" in data["aviso"]
    assert len(data["celulas"]) == 32
    assert "| json_compacto | recuperado | en | oraculo |" in md_path.read_text(encoding="utf-8")


# --- linha de comando ---------------------------------------------------------------


def test_cli_generate_then_dry_run(tmp_path: Path) -> None:
    assert cli.main(["gerar", "--seed", "9", "--por-tipo", "1", "--out", str(tmp_path)]) == 0
    assert (
        cli.main(
            [
                "harness",
                "--dry-run",
                "--casos",
                str(tmp_path / "casos.jsonl"),
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert (tmp_path / "relatorio-dry-run.md").exists()


def test_cli_real_mode_exits_with_error(tmp_path: Path) -> None:
    assert cli.main(["harness", "--real", "--out", str(tmp_path)]) == 2
    assert not (tmp_path / "relatorio-dry-run.json").exists()


def test_default_output_dir_is_git_ignored() -> None:
    gitignore = (Path(__file__).resolve().parents[3] / ".gitignore").read_text(encoding="utf-8")
    assert "research/M7/estudo-formato-contexto/" in gitignore
