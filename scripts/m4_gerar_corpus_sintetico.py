"""Gera o corpus SINTÉTICO da M4 (par arquitetura + estrutura e um IDS de cada).

Uso:
    uv run python scripts/m4_gerar_corpus_sintetico.py [--out DIR]
    uv run python scripts/m4_gerar_corpus_sintetico.py --upload http://127.0.0.1:8765

Os arquivos gerados ficam em ``tests/fixtures/m4/generated/`` (ignorado pelo git).
A saída é determinística (GlobalIds e timestamp fixos) para a versão de
IfcOpenShell registrada em ``tests/fixtures/m4/manifest.json``.

Casos-limite incluídos (todos sintéticos):
- parede sem Pset (W-04);
- Pset com marcadores "A definir", 0 e FALSE (W-02; pilar C-03 com FALSE);
- mesmo GlobalId nos dois arquivos (laje ARQ × laje EST);
- GlobalId repetido DENTRO do arquivo de arquitetura (janelas J-01 e J-02);
- elemento sem geometria (proxy PX-01);
- nome com HTML/script (porta P-01) para teste de renderização inerte;
- um requisito impossível em cada IDS.
"""

import argparse
import hashlib
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings as owner_settings
import ifcopenshell.guid
import numpy as np
from loguru import logger

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "tests" / "fixtures" / "m4" / "generated"
TIMESTAMP = "2026-10-13T00:00:00"
_NAMESPACE = uuid.UUID("6f1c2d0e-4a8b-4f5e-9c3d-0a1b2c3d4e5f")

ARQ_IFC = "m4_sintetico_arquitetura.ifc"
EST_IFC = "m4_sintetico_estrutura.ifc"
ARQ_IDS = "m4_sintetico_arquitetura.ids"
EST_IDS = "m4_sintetico_estrutura.ids"

SHARED_SLAB_GUID_KEY = "laje-compartilhada"
DUPLICATED_WINDOW_GUID_KEY = "janela-duplicada"
SCRIPT_NAME = "Porta <script>alert(1)</script>"


def guid(key: str) -> str:
    """GlobalId determinístico a partir de uma chave legível."""
    return ifcopenshell.guid.compress(uuid.uuid5(_NAMESPACE, key).hex)


def _api(f: ifcopenshell.file, usecase: str, **kwargs: object) -> object:
    """Atalho para ifcopenshell.api.run."""
    return ifcopenshell.api.run(usecase, f, **kwargs)


def _placement(x: float, y: float, z: float, x_axis: tuple, z_axis: tuple) -> np.ndarray:
    """Matriz 4x4 com eixos locais x e z dados no referencial global."""
    xa = np.array(x_axis, dtype=float)
    za = np.array(z_axis, dtype=float)
    ya = np.cross(za, xa)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = xa, ya, za, (x, y, z)
    return m


class _Builder:
    """Monta um IFC4 mínimo em metros com projeto, terreno, edifício e pavimento."""

    def __init__(self, project_name: str, prefix: str) -> None:
        """Cria a estrutura espacial e o contexto Body."""
        self.prefix = prefix
        self._named: set[int] = set()
        self.f = ifcopenshell.api.run("project.create_file", version="IFC4")
        f = self.f
        project = self._root("IfcProject", project_name, "projeto")
        lengths = _api(f, "unit.add_si_unit", unit_type="LENGTHUNIT")
        areas = _api(f, "unit.add_si_unit", unit_type="AREAUNIT")
        volumes = _api(f, "unit.add_si_unit", unit_type="VOLUMEUNIT")
        _api(f, "unit.assign_unit", units=[lengths, areas, volumes])
        model = _api(f, "context.add_context", context_type="Model")
        self.body = _api(
            f, "context.add_context", context_type="Model", context_identifier="Body",
            target_view="MODEL_VIEW", parent=model,
        )
        site = self._root("IfcSite", "Terreno sintético", "terreno")
        building = self._root("IfcBuilding", "Edifício sintético", "edificio")
        self.storey = self._root("IfcBuildingStorey", "Térreo", "terreo")
        _api(f, "aggregate.assign_object", products=[site], relating_object=project)
        _api(f, "aggregate.assign_object", products=[building], relating_object=site)
        _api(f, "aggregate.assign_object", products=[self.storey], relating_object=building)
        for spatial in (site, building, self.storey):
            _api(f, "geometry.edit_object_placement", product=spatial)

    def _root(self, ifc_class: str, name: str, key: str) -> ifcopenshell.entity_instance:
        """Cria entidade com GlobalId determinístico."""
        entity = _api(self.f, "root.create_entity", ifc_class=ifc_class, name=name)
        entity.GlobalId = guid(f"{self.prefix}:{key}")
        self._named.add(entity.id())
        return entity

    def element(
        self,
        ifc_class: str,
        name: str,
        key: str,
        representation: ifcopenshell.entity_instance | None,
        matrix: np.ndarray,
        psets: dict[str, dict[str, object]] | None = None,
        global_id: str | None = None,
    ) -> ifcopenshell.entity_instance:
        """Cria elemento contido no pavimento, com geometria e Psets opcionais."""
        entity = self._root(ifc_class, name, key)
        if global_id is not None:
            entity.GlobalId = global_id
        _api(self.f, "spatial.assign_container", products=[entity], relating_structure=self.storey)
        _api(self.f, "geometry.edit_object_placement", product=entity, matrix=matrix)
        if representation is not None:
            _api(self.f, "geometry.assign_representation", product=entity,
                 representation=representation)
        for pset_name, props in (psets or {}).items():
            pset = _api(self.f, "pset.add_pset", product=entity, name=pset_name)
            _api(self.f, "pset.edit_pset", pset=pset, properties=props)
        return entity

    def box(self, length: float, thickness: float, height: float) -> ifcopenshell.entity_instance:
        """Prisma retangular (usa a representação de parede: comprimento em x)."""
        return _api(self.f, "geometry.add_wall_representation", context=self.body,
                    length=length, height=height, thickness=thickness)

    def profile(self, xdim: float, ydim: float, depth: float) -> ifcopenshell.entity_instance:
        """Extrusão de perfil retangular centrado (pilares e vigas)."""
        rect = self.f.create_entity("IfcRectangleProfileDef", ProfileType="AREA",
                                    XDim=xdim, YDim=ydim)
        return _api(self.f, "geometry.add_profile_representation", context=self.body,
                    profile=rect, depth=depth)

    def slab(self, width: float, depth_y: float, thickness: float) -> ifcopenshell.entity_instance:
        """Laje retangular a partir da origem local."""
        return _api(self.f, "geometry.add_slab_representation", context=self.body,
                    depth=thickness,
                    polyline=[(0.0, 0.0), (width, 0.0), (width, depth_y), (0.0, depth_y)])

    def write(self, path: Path) -> None:
        """Grava de forma determinística: timestamp fixo, GlobalIds das relações
        derivados do express_id e conjuntos contidos ordenados."""
        for entity in self.f.by_type("IfcRoot"):
            if entity.id() not in self._named:
                entity.GlobalId = guid(f"{self.prefix}:auto:{entity.id()}")
        for rel in self.f.by_type("IfcRelContainedInSpatialStructure"):
            rel.RelatedElements = sorted(rel.RelatedElements, key=lambda e: e.id())
        for assignment in self.f.by_type("IfcUnitAssignment"):
            assignment.Units = sorted(assignment.Units, key=lambda u: u.id())
        self.f.header.file_name.time_stamp = TIMESTAMP
        self.f.write(str(path))


_X = (1.0, 0.0, 0.0)
_Y = (0.0, 1.0, 0.0)
_Z = (0.0, 0.0, 1.0)


def _wall_matrix(x: float, y: float, direction: tuple) -> np.ndarray:
    """Parede com eixo x local na direção dada e z vertical."""
    return _placement(x, y, 0.0, direction, _Z)


def build_architecture(path: Path) -> None:
    """Gera o IFC de arquitetura (10 m × 6 m, pé-direito 3 m)."""
    b = _Builder("M4 sintético — Arquitetura", "arq")
    complete = {"Pset_WallCommon": {"IsExternal": True, "FireRating": "EI 60",
                                    "ThermalTransmittance": 2.3}}
    b.element("IfcWall", "W-01 Fachada sul", "w01", b.box(10.0, 0.2, 3.0),
              _wall_matrix(0.0, 0.0, _X), complete)
    b.element("IfcWall", "W-02 Fachada leste (marcadores)", "w02", b.box(6.0, 0.2, 3.0),
              _wall_matrix(10.0, 0.0, _Y),
              {"Pset_WallCommon": {"IsExternal": False, "FireRating": "A definir",
                                   "ThermalTransmittance": 0.0}})
    b.element("IfcWall", "W-03 Fachada norte", "w03", b.box(10.0, 0.2, 3.0),
              _wall_matrix(10.0, 6.0, (-1.0, 0.0, 0.0)), complete)
    b.element("IfcWall", "W-04 Fachada oeste (sem Pset)", "w04", b.box(6.0, 0.2, 3.0),
              _wall_matrix(0.0, 6.0, (0.0, -1.0, 0.0)))
    b.element("IfcSlab", "Piso acabado", "laje", b.slab(10.0, 6.0, 0.05),
              _placement(0.0, 0.0, 0.0, _X, _Z),
              {"Pset_SlabCommon": {"IsExternal": False}},
              global_id=guid(SHARED_SLAB_GUID_KEY))
    duplicated = guid(DUPLICATED_WINDOW_GUID_KEY)
    for key, name, x in (("j01", "J-01 Janela sala", 2.0), ("j02", "J-02 Janela quarto", 6.0)):
        b.element("IfcWindow", name, key, b.box(1.2, 0.1, 1.2),
                  _placement(x, 0.05, 1.0, _X, _Z),
                  {"Pset_WindowCommon": {"IsExternal": True}},
                  global_id=duplicated)
    b.element("IfcDoor", SCRIPT_NAME, "p01", b.box(0.9, 0.1, 2.1),
              _placement(4.0, 5.95, 0.0, _X, _Z),
              {"Pset_DoorCommon": {"IsExternal": True, "FireRating": "EI 30"}})
    b.element("IfcBuildingElementProxy", "PX-01 Proxy sem geometria", "px01", None,
              _placement(5.0, 3.0, 0.0, _X, _Z))
    b.write(path)


def build_structure(path: Path) -> None:
    """Gera o IFC de estrutura nas mesmas coordenadas da arquitetura."""
    b = _Builder("M4 sintético — Estrutura", "est")
    corners = (("c01", 0.0, 0.0, True), ("c02", 10.0, 0.0, True),
               ("c03", 10.0, 6.0, False), ("c04", 0.0, 6.0, True))
    for key, x, y, load_bearing in corners:
        b.element("IfcColumn", f"{key.upper().replace('C0', 'C-0')} Pilar", key,
                  b.profile(0.3, 0.3, 3.0), _placement(x, y, 0.0, _X, _Z),
                  {"Pset_ColumnCommon": {"LoadBearing": load_bearing}})
    beams = (("v01", 0.0, 0.0, _X, 10.0, (0.0, 1.0, 0.0)),
             ("v02", 10.0, 0.0, _Y, 6.0, (-1.0, 0.0, 0.0)),
             ("v03", 10.0, 6.0, (-1.0, 0.0, 0.0), 10.0, (0.0, -1.0, 0.0)),
             ("v04", 0.0, 6.0, (0.0, -1.0, 0.0), 6.0, (1.0, 0.0, 0.0)))
    for key, x, y, axis, span, local_x in beams:
        psets = {"Pset_BeamCommon": {"LoadBearing": True}}
        if key != "v02":
            psets["Pset_BeamCommon"]["Span"] = span
        b.element("IfcBeam", f"{key.upper().replace('V0', 'V-0')} Viga", key,
                  b.profile(0.2, 0.4, span), _placement(x, y, 2.8, local_x, axis), psets)
    b.element("IfcSlab", "Laje estrutural", "laje", b.slab(10.0, 6.0, 0.2),
              _placement(0.0, 0.0, -0.2, _X, _Z),
              {"Pset_SlabCommon": {"LoadBearing": True}},
              global_id=guid(SHARED_SLAB_GUID_KEY))
    b.write(path)


def _spec(name: str, entity: str, pset: str, prop: str, datatype: str,
          value: str | None = None) -> str:
    """Especificação IDS com um requisito de propriedade."""
    value_xml = f"\n          <value><simpleValue>{value}</simpleValue></value>" if value else ""
    return f"""
    <specification name="{name}">
      <applicability>
        <entity><name><simpleValue>{entity}</simpleValue></name></entity>
      </applicability>
      <requirements>
        <property datatype="{datatype}">
          <propertySet><simpleValue>{pset}</simpleValue></propertySet>
          <baseName><simpleValue>{prop}</simpleValue></baseName>{value_xml}
        </property>
      </requirements>
    </specification>"""


def _ids(title: str, specs: list[str]) -> str:
    """Documento IDS no formato dos templates do repositório (aceito pelo legado)."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ids xmlns="http://standards.buildingsmart.org/IDS"
     xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <info>
    <title>{title}</title>
    <description>SINTÉTICO — corpus M4, não representa projeto real.</description>
    <author>IFC Quality Copilot</author>
    <date>2026-10-13</date>
    <version>1</version>
  </info>
  <specifications>{"".join(specs)}
  </specifications>
</ids>
"""


def build_ids(out: Path) -> None:
    """Gera um IDS por disciplina, cada um com um requisito impossível."""
    arq = [
        _spec("Paredes: resistência ao fogo", "IFCWALL", "Pset_WallCommon", "FireRating",
              "IfcLabel"),
        _spec("Paredes: transmitância térmica", "IFCWALL", "Pset_WallCommon",
              "ThermalTransmittance", "IfcThermalTransmittanceMeasure"),
        _spec("Paredes: externa", "IFCWALL", "Pset_WallCommon", "IsExternal", "IfcBoolean"),
        _spec("Portas: resistência ao fogo", "IFCDOOR", "Pset_DoorCommon", "FireRating",
              "IfcLabel"),
        _spec("Janelas: externa", "IFCWINDOW", "Pset_WindowCommon", "IsExternal", "IfcBoolean"),
        _spec("IMPOSSÍVEL: janelas com referência inexistente", "IFCWINDOW",
              "Pset_WindowCommon", "Reference", "IfcIdentifier", "IMPOSSIVEL-ARQ-999"),
    ]
    est = [
        _spec("Pilares: estrutural", "IFCCOLUMN", "Pset_ColumnCommon", "LoadBearing",
              "IfcBoolean"),
        _spec("Vigas: vão", "IFCBEAM", "Pset_BeamCommon", "Span", "IfcPositiveLengthMeasure"),
        _spec("Lajes: estrutural", "IFCSLAB", "Pset_SlabCommon", "LoadBearing", "IfcBoolean"),
        _spec("IMPOSSÍVEL: vigas com referência inexistente", "IFCBEAM", "Pset_BeamCommon",
              "Reference", "IfcIdentifier", "IMPOSSIVEL-EST-999"),
    ]
    (out / ARQ_IDS).write_text(_ids("M4 sintético — Arquitetura", arq), encoding="utf-8",
                               newline="\n")
    (out / EST_IDS).write_text(_ids("M4 sintético — Estrutura", est), encoding="utf-8",
                               newline="\n")


@contextmanager
def _without_owner_history() -> Iterator[None]:
    """Desliga IfcOwnerHistory (opcional em IFC4) mesmo se o processo configurou
    um dono global; restaura a configuração anterior ao sair."""
    saved = (owner_settings.get_user, owner_settings.get_application)
    owner_settings.get_user = lambda _ifc: None
    owner_settings.get_application = lambda _ifc: None
    try:
        yield
    finally:
        owner_settings.get_user, owner_settings.get_application = saved


def generate(out: Path) -> dict[str, str]:
    """Gera os quatro arquivos e devolve {nome: sha256}."""
    out.mkdir(parents=True, exist_ok=True)
    with _without_owner_history():
        build_architecture(out / ARQ_IFC)
        build_structure(out / EST_IFC)
    build_ids(out)
    return {
        name: hashlib.sha256((out / name).read_bytes()).hexdigest()
        for name in (ARQ_IFC, ARQ_IDS, EST_IFC, EST_IDS)
    }


def upload(base_url: str, out: Path) -> str:
    """Cria projeto, envia os dois pares pela API e confirma os vínculos."""
    import httpx

    files = {"architecture": (ARQ_IFC, ARQ_IDS), "structure": (EST_IFC, EST_IDS)}
    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        project = client.post("/api/v1/projects", json={"name": "M4 sintético"}).json()
        for model in project["models"]:
            ifc_name, ids_name = files[model["discipline"]]
            base = f"/api/v1/projects/{project['project_id']}/models/{model['model_id']}"
            for role, name in (("ifc", ifc_name), ("ids", ids_name)):
                resp = client.put(f"{base}/{role}", params={"filename": name},
                                  content=(out / name).read_bytes(),
                                  headers={"Content-Type": "application/octet-stream"})
                resp.raise_for_status()
            binding = resp.json()
            client.post(f"{base}/confirm", json={
                "ifc_revision_id": binding["ifc"]["revision_id"],
                "ids_revision_id": binding["ids"]["revision_id"],
            }).raise_for_status()
            logger.info("{}: model_id={}", model["discipline"], model["model_id"])
    return project["project_id"]


def main() -> None:
    """Gera o corpus e, opcionalmente, envia à API local."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--upload", metavar="URL", help="ex.: http://127.0.0.1:8765")
    args = parser.parse_args()
    for name, digest in generate(args.out).items():
        logger.info("{}  {}", digest, name)
    if args.upload:
        if not args.upload.startswith(("http://127.0.0.1:", "http://localhost:")):
            sys.exit("--upload aceita apenas a API local em loopback.")
        logger.info("project_id={}", upload(args.upload, args.out))


if __name__ == "__main__":
    main()
