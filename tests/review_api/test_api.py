"""API local M4 sobre o par sintético: identidade, lacunas e proteções."""

import hashlib
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from tests.review_api.conftest import OCTET, Pair, load_pair, upload


def _elements(client: TestClient, pair: Pair, model_id: str) -> list[dict]:
    resp = client.get(f"{pair.base(model_id)}/elements")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == len(body["items"])
    return body["items"]


def _by_name(items: list[dict], name: str) -> list[dict]:
    return [item for item in items if item["name"] == name]


def _gaps(client: TestClient, pair: Pair, model_id: str) -> dict:
    resp = client.get(f"{pair.base(model_id)}/gaps")
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- identidade --------------------------------------------------------------


def test_same_ifc_with_another_name_has_same_revision(
    client: TestClient, corpus_dir: Path, generator: ModuleType
) -> None:
    pair = load_pair(client, corpus_dir, generator, confirm=False)
    path = corpus_dir / generator.ARQ_IFC
    first = upload(client, pair.base(pair.architecture), "ifc", path, "original.ifc")
    second = upload(client, pair.base(pair.structure), "ifc", path, "copia-renomeada.ifc")
    assert first["ifc"]["revision_id"] == second["ifc"]["revision_id"]
    assert first["ifc"]["revision_id"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert first["ifc"]["display_name"] != second["ifc"]["display_name"]


def test_same_global_id_in_two_files_gives_two_element_refs(
    client: TestClient, pair: Pair
) -> None:
    """T4-03: GlobalId igual entre arquitetura e estrutura não colapsa identidades."""
    arq = _by_name(_elements(client, pair, pair.architecture), "Piso acabado")
    est = _by_name(_elements(client, pair, pair.structure), "Laje estrutural")
    assert len(arq) == len(est) == 1
    assert arq[0]["global_id"] == est[0]["global_id"]
    assert arq[0]["ref"] != est[0]["ref"]
    assert arq[0]["ref"]["model_id"] == pair.architecture
    assert est[0]["ref"]["model_id"] == pair.structure
    assert arq[0]["global_id_state"] == est[0]["global_id_state"] == "unique"


def test_duplicate_global_id_within_file_is_ambiguous_never_chosen(
    client: TestClient, pair: Pair
) -> None:
    """T4-04: GlobalId repetido no MESMO arquivo preserva as duas entidades."""
    items = _elements(client, pair, pair.architecture)
    windows = [i for i in items if i["ifc_class"] == "IfcWindow"]
    assert len(windows) == 2
    assert windows[0]["global_id"] == windows[1]["global_id"]
    assert {w["global_id_state"] for w in windows} == {"duplicated_in_file"}
    assert windows[0]["ref"] != windows[1]["ref"]

    gaps = _gaps(client, pair, pair.architecture)["items"]
    window_gaps = [g for g in gaps if g["ifc_class"] == "IfcWindow"]
    assert len(window_gaps) == 1
    gap = window_gaps[0]
    assert gap["resolution"] == "ambiguous"
    assert gap["element"] is None
    assert gap["current_value"] is None
    assert sorted(c["express_id"] for c in gap["candidates"]) == sorted(
        w["ref"]["express_id"] for w in windows
    )


def test_express_id_resolves_only_to_listed_element_of_that_model(
    client: TestClient, pair: Pair
) -> None:
    """T4-05 (parte API): id do viewer → ElementRecord explícito, por modelo."""
    for model_id in (pair.architecture, pair.structure):
        for item in _elements(client, pair, model_id):
            express_id = item["ref"]["express_id"]
            resp = client.get(f"{pair.base(model_id)}/elements/{express_id}")
            assert resp.status_code == 200
            assert resp.json() == item
    # #1 é o IfcProject, não um elemento revisável: nunca devolver "o mais parecido".
    resp = client.get(f"{pair.base(pair.architecture)}/elements/1")
    assert resp.status_code == 404
    assert resp.json()["code"] == "elemento_inexistente"


def test_element_without_geometry_stays_in_list(client: TestClient, pair: Pair) -> None:
    """T4-07: elemento sem malha continua no diagnóstico."""
    items = _elements(client, pair, pair.architecture)
    proxy = _by_name(items, "PX-01 Proxy sem geometria")
    assert len(proxy) == 1
    assert proxy[0]["has_geometry"] is False
    assert all(i["has_geometry"] for i in items if i is not proxy[0])


def test_name_with_markup_is_returned_as_literal_text(
    client: TestClient, pair: Pair, generator: ModuleType
) -> None:
    """T4-53 (parte API): conteúdo do IFC é dado JSON, nunca HTML."""
    resp = client.get(f"{pair.base(pair.architecture)}/elements")
    assert resp.headers["content-type"].startswith("application/json")
    door = [i for i in resp.json()["items"] if i["ifc_class"] == "IfcDoor"]
    assert door[0]["name"] == generator.SCRIPT_NAME


# --- lacunas -----------------------------------------------------------------


def test_gaps_are_provisional_and_labelled_with_legacy_source(
    client: TestClient, pair: Pair
) -> None:
    body = _gaps(client, pair, pair.architecture)
    assert body["schema_status"] == "provisorio_aguardando_M2_M3"
    assert body["source"].startswith("legado:")
    assert body["total"] == len(body["items"]) > 0
    assert all(g["schema_status"] == "provisorio_aguardando_M2_M3" for g in body["items"])
    assert body["limitations"]


def test_element_without_pset_reports_pset_absent(client: TestClient, pair: Pair) -> None:
    gaps = _gaps(client, pair, pair.architecture)["items"]
    w04 = [g for g in gaps if g["element_name"] == "W-04 Fachada oeste (sem Pset)"]
    assert {g["requirement"]["property_name"] for g in w04} == {
        "FireRating", "IsExternal", "ThermalTransmittance"
    }
    assert {g["current_value"]["state"] for g in w04} == {"pset_absent"}
    assert {g["origin"] for g in w04} == {"legacy_ifc_analyzer"}


def test_markers_are_adapter_observations_with_typed_values(
    client: TestClient, pair: Pair
) -> None:
    """T4-26: 'A definir', 0 e FALSE ficam tipados e marcados como provisórios pelo adaptador."""
    gaps = _gaps(client, pair, pair.architecture)["items"]
    w02 = {
        g["requirement"]["property_name"]: g
        for g in gaps
        if g["element_name"] == "W-02 Fachada leste (marcadores)"
    }
    assert set(w02) == {"FireRating", "IsExternal", "ThermalTransmittance"}

    fire, external, thermal = w02["FireRating"], w02["IsExternal"], w02["ThermalTransmittance"]
    assert fire["origin"] == external["origin"] == "m4_adapter_marker"
    assert thermal["origin"] == "legacy_ifc_analyzer"

    assert fire["current_value"] == {"state": "present", "kind": "string", "value": "A definir"}
    assert external["current_value"] == {"state": "present", "kind": "boolean", "value": False}
    assert thermal["current_value"]["kind"] == "real"
    assert thermal["current_value"]["value"] == 0.0
    assert thermal["current_value"]["value"] is not False

    for gap, marker in ((fire, "A definir"), (external, "FALSE"), (thermal, "0")):
        assert gap["provisional_marker"]["marker"] == marker
        assert gap["provisional_marker"]["observed_by"] == "m4_adapter"
        assert gap["provisional_marker"]["classification"] == "provisorio"


def test_impossible_structure_requirement_hits_every_beam(client: TestClient, pair: Pair) -> None:
    gaps = _gaps(client, pair, pair.structure)["items"]
    impossible = [g for g in gaps if g["requirement"]["expected_value"] == "IMPOSSIVEL-EST-999"]
    assert len(impossible) == 4
    assert {g["ifc_class"] for g in impossible} == {"IfcBeam"}
    assert all(g["element"]["model_id"] == pair.structure for g in impossible)


def test_gaps_never_cross_files(client: TestClient, pair: Pair) -> None:
    for model_id in (pair.architecture, pair.structure):
        for gap in _gaps(client, pair, model_id)["items"]:
            refs = [gap["element"]] if gap["element"] else gap["candidates"]
            assert {r["model_id"] for r in refs} == {model_id}


# --- vínculo -----------------------------------------------------------------


def test_gaps_require_explicit_confirmation(
    client: TestClient, corpus_dir: Path, generator: ModuleType
) -> None:
    pair = load_pair(client, corpus_dir, generator, confirm=False)
    resp = client.get(f"{pair.base(pair.architecture)}/gaps")
    assert resp.status_code == 409
    assert resp.json()["code"] == "vinculo_nao_confirmado"


def test_confirmation_with_stale_revision_is_rejected(
    client: TestClient, corpus_dir: Path, generator: ModuleType
) -> None:
    pair = load_pair(client, corpus_dir, generator, confirm=False)
    binding = client.get(f"/api/v1/projects/{pair.project_id}").json()["models"][0]
    resp = client.post(
        f"{pair.base(binding['model_id'])}/confirm",
        json={"ifc_revision_id": "0" * 64, "ids_revision_id": binding["ids"]["revision_id"]},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "revisao_divergente"


def test_reupload_invalidates_previous_confirmation(
    client: TestClient, pair: Pair, corpus_dir: Path, generator: ModuleType
) -> None:
    binding = upload(client, pair.base(pair.architecture), "ids", corpus_dir / generator.EST_IDS)
    assert binding["confirmed"] is False
    assert client.get(f"{pair.base(pair.architecture)}/gaps").status_code == 409


def test_ifc_file_is_served_with_its_revision(
    client: TestClient, pair: Pair, corpus_dir: Path, generator: ModuleType
) -> None:
    resp = client.get(f"{pair.base(pair.structure)}/ifc-file")
    assert resp.status_code == 200
    data = (corpus_dir / generator.EST_IFC).read_bytes()
    assert resp.content == data
    assert resp.headers["x-ifc-revision"] == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    ("role", "content", "code"),
    [("ifc", b"isto nao e IFC", "ifc_invalido"), ("ids", b"<nao-e-ids/>", "ids_invalido")],
)
def test_invalid_upload_is_rejected_without_leaking_paths(
    client: TestClient, pair: Pair, role: str, content: bytes, code: str
) -> None:
    resp = client.put(
        f"{pair.base(pair.architecture)}/{role}",
        params={"filename": "ruim"},
        content=content,
        headers=OCTET,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == code
    assert "\\" not in body["message"]
    assert "/" not in body["message"]


# --- acesso local ------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {"host": "evil.example"},
        {"origin": "http://evil.example"},
        {"origin": "null"},
        {"origin": "http://192.168.0.10:8765"},
    ],
)
def test_foreign_host_or_origin_is_refused(client: TestClient, headers: dict) -> None:
    resp = client.post("/api/v1/projects", json={"name": "x"}, headers=headers)
    assert resp.status_code == 403


def test_dev_ui_origin_is_allowed_only_on_loopback_ip(client: TestClient) -> None:
    """Proxy do Vite: só a Origin exata http://127.0.0.1:5173 é aceita."""
    resp = client.post("/api/v1/projects", json={"name": "x"},
                       headers={"origin": "http://127.0.0.1:5173"})
    assert resp.status_code == 201
    assert "access-control-allow-origin" not in resp.headers
    for origin in ("http://localhost:5173", "http://127.0.0.1:5174", "https://127.0.0.1:5173"):
        refused = client.post("/api/v1/projects", json={"name": "x"}, headers={"origin": origin})
        assert refused.status_code == 403, origin


def test_vite_proxy_host_header_is_accepted(client: TestClient) -> None:
    """O proxy (changeOrigin=false) repassa Host 127.0.0.1:5173."""
    resp = client.get("/api/v1/health", headers={"host": "127.0.0.1:5173"})
    assert resp.status_code == 200


def test_interactive_docs_are_disabled(client: TestClient) -> None:
    """Swagger/ReDoc do FastAPI carregam ativos de CDN; ficam desligados."""
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/api/v1/openapi.json").status_code == 200
