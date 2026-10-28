"""Modo real do estudo de formato de contexto, só com HTTP simulado (nenhum Ollama)."""

import json
import sys
from pathlib import Path

import httpx
import pytest

from src.experiment.budget_v1 import context_format as cf
from src.experiment.budget_v1 import context_format_runner as rn

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import estudo_formato_contexto as cli  # noqa: E402

PROSPECTION = Path(__file__).resolve().parents[3] / "research" / "M7" / "prospection"


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Qualquer HTTP de verdade (inclusive um Ollama local) falha neste módulo."""

    def refuse(*_a: object, **_k: object) -> httpx.Response:
        raise AssertionError("teste tentou HTTP real")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


@pytest.fixture(scope="module")
def cases() -> list[cf.SyntheticCase]:
    """Casos pequenos."""
    return cf.generate_cases(seed=3, per_kind=1)


class FakeOllama:
    """Ollama simulado: responde o gabarito (como o oráculo) e registra os pedidos."""

    def __init__(self, cases: list[cf.SyntheticCase], fail_every: int = 0) -> None:
        self.requests: list[dict] = []
        self.fail_every = fail_every
        self.by_prompt_case = cases

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if self.fail_every and len(self.requests) % self.fail_every == 0:
            return httpx.Response(500, json={"error": "boom"})
        prompt = body["messages"][0]["content"]
        case = next(
            c for c in self.by_prompt_case if c.element_name in prompt and _same_props(c, prompt)
        )
        content = cf.simulated_response(case, "oraculo")
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": content},
                "total_duration": 1_500_000_000,
                "load_duration": 200_000_000,
                "prompt_eval_count": 410,
                "eval_count": 48,
            },
        )


def _same_props(case: cf.SyntheticCase, prompt: str) -> bool:
    return all(p.name in prompt for p in cf.retrieve(case))


def _client(fake: FakeOllama) -> rn.OllamaStructuredClient:
    return rn.OllamaStructuredClient(
        "http://ollama.simulado", transport=httpx.MockTransport(fake.handler)
    )


class FakeSampler(rn.VramSampler):
    """Amostrador sem nvidia-smi."""

    def __init__(self) -> None:
        values = iter([3000, 4100, 4200, 3900] * 10_000)
        super().__init__(query=lambda: next(values), interval_s=0.001)


# --- cliente -------------------------------------------------------------------------


def test_chat_sends_structured_output_deterministic_options(cases: list[cf.SyntheticCase]) -> None:
    fake = FakeOllama(cases)
    case = cases[0]
    result = _client(fake).chat(
        "qwen3:4b-q4_K_M",
        cf.build_prompt(case, "tabela", "inteiro", "pt"),
        cf.output_json_schema(),
        7,
        4096,
    )
    [req] = fake.requests
    assert req["format"] == cf.output_json_schema()
    assert req["stream"] is False
    assert req["think"] is False
    assert req["options"] == {"temperature": 0, "seed": 7, "num_ctx": 4096}
    assert result.error is None
    assert result.total_ms == 1500.0
    assert result.load_ms == 200.0
    assert result.prompt_tokens == 410
    assert cf.score(case, result.raw or "").json_valido


def test_timeout_becomes_technical_failure_not_exception() -> None:
    def slow(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lento")

    client = rn.OllamaStructuredClient("http://x", transport=httpx.MockTransport(slow))
    result = client.chat("m", "p", {}, 1, 4096)
    assert result.raw is None
    assert result.error == "timeout"


def test_http_error_is_recorded() -> None:
    client = rn.OllamaStructuredClient(
        "http://x", transport=httpx.MockTransport(lambda r: httpx.Response(404))
    )
    assert client.chat("m", "p", {}, 1, 4096).error == "http_404"


# --- VRAM ----------------------------------------------------------------------------


def test_vram_sampler_keeps_peak() -> None:
    values = iter([1000, 5000, 2000] + [1500] * 1000)
    with rn.VramSampler(query=lambda: next(values), interval_s=0.001) as s:
        pass
    assert s.peak_mib is not None
    assert s.peak_mib >= 1000


def test_vram_sampler_tolerates_missing_nvidia_smi() -> None:
    with rn.VramSampler(query=lambda: None, interval_s=0.001) as s:
        pass
    assert s.peak_mib is None


# --- execução e retomada -------------------------------------------------------------


def test_run_real_writes_one_line_per_call_and_resumes(
    tmp_path: Path, cases: list[cf.SyntheticCase]
) -> None:
    out = tmp_path / "r.jsonl"
    fake = FakeOllama(cases)
    kw = dict(
        formats=("tabela",),
        scopes=("inteiro",),
        languages=("pt",),
        repetitions=2,
        sampler_factory=FakeSampler,
    )
    done, skipped = rn.run_real(cases, ["m1"], out, _client(fake), **kw)
    assert (done, skipped) == (2 * len(cases), 0)
    assert len(out.read_text(encoding="utf-8").splitlines()) == done

    done2, skipped2 = rn.run_real(cases, ["m1"], out, _client(fake), **kw)
    assert (done2, skipped2) == (0, 2 * len(cases))
    assert len(fake.requests) == 2 * len(cases)  # nada refeito


def test_resume_ignores_truncated_last_line(tmp_path: Path, cases: list[cf.SyntheticCase]) -> None:
    out = tmp_path / "r.jsonl"
    kw = dict(
        formats=("markdown",),
        scopes=("recuperado",),
        languages=("en",),
        repetitions=1,
        sampler_factory=FakeSampler,
    )
    rn.run_real(cases[:3], ["m1"], out, _client(FakeOllama(cases)), **kw)
    lines = out.read_text(encoding="utf-8").splitlines()
    out.write_text(
        "\n".join(lines[:2]) + "\n" + lines[2][:40], encoding="utf-8"
    )  # interrupção no meio
    fake = FakeOllama(cases)
    done, skipped = rn.run_real(cases[:3], ["m1"], out, _client(fake), **kw)
    assert (done, skipped) == (1, 2)


def test_failures_are_recorded_and_scored_as_invalid(
    tmp_path: Path, cases: list[cf.SyntheticCase]
) -> None:
    out = tmp_path / "r.jsonl"
    fake = FakeOllama(cases, fail_every=2)
    rn.run_real(
        cases,
        ["m1"],
        out,
        _client(fake),
        formats=("tabela",),
        scopes=("inteiro",),
        languages=("pt",),
        repetitions=1,
        sampler_factory=FakeSampler,
    )
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    failed = [r for r in rows if r["result"]["error"]]
    assert failed
    assert all(not r["json_valido"] for r in failed)
    assert all(r["vram_peak_mib"] is not None for r in rows)


def test_summary_separates_denominators_and_reports_latency(
    tmp_path: Path, cases: list[cf.SyntheticCase]
) -> None:
    out = tmp_path / "r.jsonl"
    rn.run_real(
        cases,
        ["m1"],
        out,
        _client(FakeOllama(cases)),
        formats=("tabela",),
        scopes=("inteiro",),
        languages=("pt",),
        repetitions=1,
        sampler_factory=FakeSampler,
    )
    [cell] = rn.summarize_real(out, cases)
    assert cell.chamadas == len(cases)
    assert cell.acerto_top1 == 1.0
    assert cell.abstencao_correta == 1.0
    assert cell.falhas_tecnicas == 0
    assert cell.latencia_mediana_ms is not None
    assert cell.vram_pico_mib is not None


# --- seleção de modelos --------------------------------------------------------------


@pytest.fixture(scope="module")
def choices() -> list[rn.ModelChoice]:
    """Seleção sobre os registros versionados da M7-09."""
    return rn.select_models(rn.load_prospection_records(PROSPECTION))


def test_default_selection_is_apache_with_tag_that_fits_6gb(choices: list[rn.ModelChoice]) -> None:
    selected = sorted(c.tag for c in choices if c.selected)
    assert selected == ["qwen3.5:4b-q4_K_M", "qwen3.5:4b-q8_0", "qwen3:4b-q4_K_M", "qwen3:4b-q8_0"]
    assert all(c.license == "apache-2.0" for c in choices if c.selected)


def test_llama_is_blocked_by_license_until_decision(choices: list[rn.ModelChoice]) -> None:
    llama = [c for c in choices if c.model.startswith("Llama-3.2")]
    assert llama
    assert not any(c.selected for c in llama)
    assert all(any("orientador" in r for r in c.reasons) for c in llama)


def test_llama_enters_only_with_registered_decision() -> None:
    choices = rn.select_models(
        rn.load_prospection_records(PROSPECTION),
        conditioned_license_decision="orientador, 2026-11-03",
    )
    tags = {c.tag for c in choices if c.selected}
    assert "llama3.2:3b-instruct-q4_K_M" in tags
    assert "llama3.1:8b-instruct-q8_0" not in tags  # não cabe em 6 GB


def test_models_that_do_not_fit_or_lack_tag_are_explained(choices: list[rn.ModelChoice]) -> None:
    by_id = {c.record_id: c for c in choices}
    assert any("não cabe" in r for r in by_id["qwen3-8b-q8_0"].reasons)
    assert any("sem tag" in r for r in by_id["qwen3-4b-q5_k_m"].reasons)


def test_selected_q8_warns_about_instant_memory(choices: list[rn.ModelChoice]) -> None:
    q8 = next(c for c in choices if c.tag == "qwen3.5:4b-q8_0")
    assert any(r.startswith("aviso") for r in q8.reasons)


# --- linha de comando ----------------------------------------------------------------


def test_cli_real_without_authorization_fails_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[object] = []
    monkeypatch.setattr(cli, "make_client", lambda *a: called.append(a))
    assert cli.main(["harness", "--real", "--out", str(tmp_path)]) == 2
    assert called == []


def test_cli_real_with_authorization_uses_client_and_writes_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cases: list[cf.SyntheticCase]
) -> None:
    cf.write_jsonl(cases, tmp_path / "casos.jsonl")
    fake = FakeOllama(cases)
    monkeypatch.setattr(cli, "make_client", lambda url, timeout: _client(fake))
    monkeypatch.setattr(rn, "VramSampler", FakeSampler)
    code = cli.main(
        [
            "harness",
            "--real",
            "--confirmo-autorizacao",
            "teste automatizado",
            "--modelos",
            "m1",
            "--repeticoes",
            "1",
            "--casos",
            str(tmp_path / "casos.jsonl"),
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 0
    report = json.loads((tmp_path / "relatorio-real.json").read_text(encoding="utf-8"))
    assert report["autorizacao"] == "teste automatizado"
    assert len(report["celulas"]) == 16
    assert len(fake.requests) == 16 * len(cases)


def test_default_client_without_transport_is_refused_here() -> None:
    """Prova de que a trava de HTTP real está ativa: o cliente padrão não chega à rede."""
    with pytest.raises(AssertionError, match="HTTP real"):
        rn.OllamaStructuredClient().chat("m", "p", {}, 1, 4096)
