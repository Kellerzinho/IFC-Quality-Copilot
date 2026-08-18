"""Contratos da condição de ablação de grounding bSDD (2026-08-18).

Trava o que a condição pré-registrou em
``docs/condicao-ablacao-bsdd-2026-08-18.md``:

- o braço entra na identidade de execução (§5) — sem isso a rodada de ablação
  seria indistinguível da baseline e seus estágios seriam PULADOS;
- o kill-switch desliga o bSDD de fato, e nada mais (§1);
- braço e identidade não podem divergir em nenhuma das duas pontas.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

import scripts.run_benchmark as run_benchmark
from src.experiment.execution_identity import canonical_identity_sha256
from tests.test_run_benchmark import official_identity

# --------------------------------------------------------------------------
# Identidade: o braço é uma dimensão da execução
# --------------------------------------------------------------------------


def test_grounding_bsdd_muda_o_hash_canonico():
    """Sem isto, a ablação herdaria a identidade da baseline e seria pulada."""
    com = official_identity()
    sem = official_identity(grounding_bsdd=False)

    assert com.grounding_bsdd is True
    assert sem.grounding_bsdd is False
    assert canonical_identity_sha256(com) != canonical_identity_sha256(sem)


def test_default_preserva_o_braco_das_rodadas_anteriores():
    """Toda rodada até 2026-08-18 usou bSDD; o default precisa refletir isso."""
    assert official_identity().grounding_bsdd is True


def test_identidade_recusa_grounding_nao_booleano():
    with pytest.raises(TypeError, match="grounding_bsdd deve ser booleano"):
        official_identity(grounding_bsdd="sim")


# --------------------------------------------------------------------------
# Snapshot JSON: o campo é obrigatório e tipado
# --------------------------------------------------------------------------


def test_snapshot_sem_grounding_bsdd_e_recusado():
    """Identidade antiga (pré-ablação) não roda: campos exatos, sem default."""
    payload = asdict(official_identity())
    del payload["grounding_bsdd"]

    with pytest.raises(ValueError, match="execution_identity possui campos"):
        run_benchmark._parse_execution_identity(payload)


def test_snapshot_com_grounding_bsdd_nao_booleano_e_recusado():
    payload = asdict(official_identity())
    payload["grounding_bsdd"] = "false"

    with pytest.raises(TypeError, match="grounding_bsdd deve ser booleano"):
        run_benchmark._parse_execution_identity(payload)


@pytest.mark.parametrize("braco", [True, False])
def test_snapshot_preserva_o_braco_no_roundtrip(braco):
    payload = asdict(official_identity(grounding_bsdd=braco))

    identity = run_benchmark._parse_execution_identity(
        json.loads(json.dumps(payload))
    )

    assert identity.grounding_bsdd is braco
    assert canonical_identity_sha256(identity) == canonical_identity_sha256(
        official_identity(grounding_bsdd=braco)
    )


# --------------------------------------------------------------------------
# Kill-switch: o pipeline realmente deixa de consultar o bSDD
# --------------------------------------------------------------------------


@pytest.fixture
def ifc_minimo(tmp_path) -> str:
    """IFC mínimo em disco: o pipeline recebe caminho, não objeto."""
    import ifcopenshell
    import ifcopenshell.api

    f = ifcopenshell.file(schema="IFC4")
    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject")
    ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite")
    building = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding")
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey")
    ifcopenshell.api.run(
        "aggregate.assign_object", f, relating_object=project, products=[site]
    )
    ifcopenshell.api.run(
        "aggregate.assign_object", f, relating_object=site, products=[building]
    )
    ifcopenshell.api.run(
        "aggregate.assign_object", f, relating_object=building, products=[storey]
    )
    path = str(tmp_path / "ablacao.ifc")
    f.write(path)
    return path


def test_pipeline_sem_bsdd_nao_instancia_cliente(monkeypatch, ifc_minimo):
    """`use_bsdd=False` impede a construção do cliente bSDD no __init__ real."""
    from src.pipeline import QualityPipeline

    construidos: list[str] = []

    class _ClienteProibido:
        def __init__(self, *args, **kwargs):
            construidos.append("cliente")

        def close(self) -> None:
            pass

    monkeypatch.setattr("src.pipeline.BSDDClient", _ClienteProibido)

    pipeline = QualityPipeline(ifc_minimo, {}, use_bsdd=False)
    try:
        assert construidos == []
        assert pipeline.bsdd_client is None
        assert pipeline.bsdd_builder is None
        assert pipeline.use_bsdd is False
    finally:
        pipeline.close()


def test_pipeline_com_bsdd_instancia_cliente(monkeypatch, ifc_minimo):
    """O default — e o braço de toda rodada publicada — continua consultando."""
    from src.pipeline import QualityPipeline

    construidos: list[str] = []

    class _ClienteFalso:
        def __init__(self, *args, **kwargs):
            construidos.append("cliente")

        def close(self) -> None:
            pass

    monkeypatch.setattr("src.pipeline.BSDDClient", _ClienteFalso)

    pipeline = QualityPipeline(ifc_minimo, {})
    try:
        assert construidos == ["cliente"]
        assert pipeline.bsdd_builder is not None
        assert pipeline.use_bsdd is True
    finally:
        pipeline.close()


def test_issue_bsdd_context_devolve_none_sem_builder():
    """A guarda que faz o prompt perder o bloco BSDD_CONTEXT."""
    from src.models import Issue
    from src.pipeline import QualityPipeline

    pipeline = QualityPipeline.__new__(QualityPipeline)
    pipeline.bsdd_builder = None
    pipeline.bsdd_context_map = {}
    pipeline._bsdd_context_by_key = {}

    issue = Issue(
        element_guid="0" * 22,
        element_class="IfcWall",
        issue_type="pset_missing",
        severity="high",
        description="teste",
        context={"check_property": "FireRating"},
    )

    assert pipeline._issue_bsdd_context(issue) is None


# --------------------------------------------------------------------------
# Coerência: braço e identidade não divergem
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("identidade", "braco"),
    [(True, False), (False, True)],
)
def test_runner_recusa_braco_divergente_da_identidade(identidade, braco):
    """Rodar o braço errado sob uma identidade rotularia a rodada de forma falsa."""
    from src.experiment.runner import ExperimentRunner

    identity = official_identity(grounding_bsdd=identidade)

    with pytest.raises(ValueError, match="use_bsdd diverge"):
        ExperimentRunner().run_single(
            ifc_path="ignorado.ifc",
            ground_truth_path="ignorado.yaml",
            building_context={},
            dataset_key="casa",
            execution_identity=identity,
            use_bsdd=braco,
        )


def test_cli_oficial_expoe_no_bsdd_com_default_ligado():
    parser = run_benchmark._build_parser()

    padrao = parser.parse_args(
        ["--execution-identity", "i.json", "--no-cache", "--reuse-equivalent"]
    )
    ablacao = parser.parse_args(
        [
            "--execution-identity",
            "i.json",
            "--no-cache",
            "--reuse-equivalent",
            "--no-bsdd",
        ]
    )

    assert padrao.use_bsdd is True
    assert ablacao.use_bsdd is False


def test_identidade_do_par_v77_permanece_reproduzivel_no_braco_padrao():
    """A baseline da comparação é uma rodada com bSDD: o default não pode mudá-la.

    O hash muda (o campo é novo), mas o BRAÇO precisa continuar sendo o mesmo
    das rodadas já publicadas — senão a baseline da condição não seria baseline.
    """
    baseline = official_identity()
    recarregada = run_benchmark._parse_execution_identity(
        json.loads(json.dumps(asdict(baseline)))
    )

    assert recarregada.grounding_bsdd is True
    assert canonical_identity_sha256(recarregada) == canonical_identity_sha256(baseline)
