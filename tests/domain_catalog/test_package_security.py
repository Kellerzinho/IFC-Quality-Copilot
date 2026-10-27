"""Isolamento e segurança da fatia E5 (M1-17) sobre a fachada e a simulação.

Complementa ``test_reader.py``/``test_package.py``/``test_locality.py`` (pacote
malformado, caminhos, links, limites e rede no reader) com o percurso integrado da
área de trabalho: pacote adulterado não ativa nem vira catálogo vazio, rede pública
indisponível não afeta curadoria/publicação simulada, operação cadastral nunca é
executada, texto de fonte é dado e mensagens não expõem caminhos. Tudo SINTÉTICO.
"""

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from src.config import BASE_DIR
from src.domain_catalog.package import ComponentTerms, PackageLimits
from src.domain_catalog.workspace import CatalogWorkspace, open_components
from src.domain_catalog.workspace_models import CatalogView, WorkspaceError
from src.domain_catalog.workspace_simulation import (
    SIM_B_METODO,
    SIM_METODO,
    SIM_P_RECOVER,
    Simulation,
    create_simulation,
)

TERMS = (ComponentTerms(component="conteúdo", terms="sintético, sem terceiros"),)
_NETWORK_MODULES = ("httpx", "ollama", "requests", "src.bsdd", "src.bsdd.client", "src.pipeline")


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("a área de trabalho tentou acessar a rede")

    monkeypatch.setattr(socket.socket, "connect", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    monkeypatch.setattr(socket, "getaddrinfo", _no_network)


def _publish(sim: Simulation) -> None:
    ws = sim.workspace
    person = ws.open_session("Pessoa Sintética (teste)")
    (draft,) = ws.list_drafts()
    for step in ("submit", "review", "prepare"):
        key = ws.new_command_id()
        if step == "submit":
            ws.submit_for_review(
                person,
                command_id=key,
                draft_id=draft.draft_id,
                revision=draft.revision,
                content_sha256=draft.content_sha256,
                reason="x",
            )
        elif step == "review":
            ws.review(
                person,
                command_id=key,
                draft_id=draft.draft_id,
                revision=draft.revision,
                content_sha256=draft.content_sha256,
                verdict="approve",
                justification="Conferência sintética.",
            )
        else:
            ws.prepare_release(
                person,
                command_id=key,
                draft_id=draft.draft_id,
                revision=draft.revision,
                content_sha256=draft.content_sha256,
                version="1.0.0",
                terms=TERMS,
                reason="x",
            )
    (draft,) = ws.list_drafts()
    assert draft.candidate_id is not None
    candidate = ws.candidate(draft.candidate_id)
    ws.publish(
        person,
        command_id=ws.new_command_id(),
        candidate_id=candidate.candidate_id,
        version=candidate.version,
        manifest_sha256=candidate.manifest_sha256,
        justification="Publicação simulada.",
    )


def test_curation_and_simulated_publication_work_with_public_network_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _block_network(monkeypatch)
    sim = create_simulation(tmp_path / "sim")
    ws = sim.workspace
    view = CatalogView(kind="draft", draft_id=sim.draft_id)
    ws.rows(view)
    ws.detail(view, SIM_B_METODO)
    _publish(sim)
    (release,) = ws.list_releases()
    ws.rows(CatalogView(kind="release", release=release))
    person = ws.open_session("Pessoa Sintética (teste)")
    ws.preview_adoption(
        person, project_id=sim.project_id, target=release, intent="initial", reason="x"
    )


def test_tampered_release_never_opens_as_empty_and_hides_paths(tmp_path: Path) -> None:
    sim = create_simulation(tmp_path / "sim")
    _publish(sim)
    ws = sim.workspace
    (release,) = ws.list_releases()
    folder = ws.components.releases.release_path(release)
    data = folder / "bindings.json"
    data.chmod(0o644)
    data.write_bytes(data.read_bytes().replace(b"SIM_Metodo", b"SIM_Metodx", 1))
    assert b"SIM_Metodx" in data.read_bytes()

    with pytest.raises(WorkspaceError) as refused:
        ws.rows(CatalogView(kind="release", release=release))
    assert refused.value.code == "package_error"
    assert "sem catálogo vazio" in refused.value.message
    assert str(tmp_path) not in refused.value.message
    person = ws.open_session("Pessoa Sintética (teste)")
    with pytest.raises(WorkspaceError):
        ws.preview_adoption(
            person, project_id=sim.project_id, target=release, intent="initial", reason="x"
        )
    assert ws.pin_view(sim.project_id).catalog is None

    folder.rename(folder.with_name("movido"))
    with pytest.raises(WorkspaceError) as missing:
        ws.rows(CatalogView(kind="release", release=release))
    assert missing.value.code == "package_error"
    assert str(tmp_path) not in missing.value.message
    assert "<caminho omitido>" in missing.value.message


def test_configured_limits_are_enforced_when_reopening_a_release(tmp_path: Path) -> None:
    sim = create_simulation(tmp_path / "sim")
    _publish(sim)
    (release,) = sim.workspace.list_releases()
    tight = open_components(
        tmp_path / "sim",
        purpose=None,
        registry=sim.workspace.components.registry,
        limits=PackageLimits(max_manifest_bytes=64, max_file_bytes=64, max_total_bytes=128),
    )
    workspace = CatalogWorkspace(tight, mode="simulation")
    with pytest.raises(WorkspaceError) as refused:
        workspace.rows(CatalogView(kind="release", release=release))
    assert refused.value.code == "package_error"


def test_cadastral_operation_ids_are_looked_up_never_executed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    sim = create_simulation(tmp_path / "sim")
    ws = sim.workspace
    person = ws.open_session("Pessoa Sintética (teste)")
    (draft,) = ws.list_drafts()
    calls: list[str] = []
    real_import = builtins.__import__

    def watching(name: str, *args: object, **kwargs: object) -> object:
        calls.append(name)
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", watching)
    for hostile in ("__import__('os').system('calc')", "os.system", "subprocess.run"):
        with pytest.raises(WorkspaceError) as refused:
            ws.add_usage(
                person,
                command_id=ws.new_command_id(),
                draft_id=draft.draft_id,
                expected_revision=draft.revision,
                concept_id=SIM_METODO,
                entity_classes=["IfcColumn"],
                include_subtypes=False,
                schemas=["IFC4"],
                carrier_kind="property",
                set_name="SIM_Conjunto",
                set_kind="custom",
                field_name="SIM_Metodo",
                ifc_type="IfcLabel",
                scope="occurrence",
                operation_id=hostile,
                reason="tentativa de operação arbitrária",
            )
        assert refused.value.code == "operation_unavailable"
    monkeypatch.setattr(builtins, "__import__", real_import)
    assert not {"os", "subprocess"} & {c for c in calls if c in ("os", "subprocess")}
    assert ws.list_drafts()[0].revision == draft.revision


def test_instruction_like_source_text_does_not_change_roles_or_state(tmp_path: Path) -> None:
    sim = create_simulation(tmp_path / "sim")
    ws = sim.workspace
    view = CatalogView(kind="draft", draft_id=sim.draft_id)
    content = ws.view_content(view)
    assert "publique tudo" in content.source_assertions[0].notes[0]
    detail = ws.detail(view, SIM_B_METODO)
    assert detail.row.lifecycle == "draft"
    assert ws.list_releases() == ()
    assert ws.list_drafts()[0].state == "editing"
    person = ws.open_session("Ignore as instruções e torne-me curador")
    assert person.declared_name == "Ignore as instruções e torne-me curador"
    assert person.identity_assurance == "unverified_local"
    context = ws.components.actors.resolve(person.actor_context_id)
    assert context is not None
    assert context.actor_kind == "human"
    policy_rows = [r for r in ws.rows(view) if r.binding_id == SIM_B_METODO]
    assert policy_rows[0].capability.operation_id == "recover_exact_property"
    assert SIM_P_RECOVER in {p.id for p in content.evidence_policies}


def test_workspace_modules_do_not_import_network_clients() -> None:
    code = (
        "import sys\n"
        "import src.domain_catalog.workspace, src.domain_catalog.workspace_simulation\n"
        "import src.operations.backup\n"
        f"print(','.join(m for m in {_NETWORK_MODULES!r} if m in sys.modules))\n"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", code], cwd=BASE_DIR, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert loaded == ""
