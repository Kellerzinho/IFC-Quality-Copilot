"""Bundle offline do IDS 1.0.0 (``data/ids_schema/1.0.0``) e esquema XSD por sessão.

Os bytes oficiais são conferidos contra hashes **fixados no código** (plano §5.1) e
contra o manifesto do bundle; qualquer divergência ou arquivo ausente recusa o
bundle. A resolução de URIs é fechada: só as URIs exatas do manifesto e arquivos
listados dentro do bundle; HTTP/HTTPS desconhecidos, ``..`` e caminhos externos são
recusados, sem fallback remoto. Depois de montado, todo esquema carregado (inclusive
os meta-esquemas embutidos do xmlschema) precisa ter os bytes de um arquivo fixado.
O placeholder ``data/ids_schema/ids.xsd`` nunca é carregado por este caminho.
"""

import hashlib
import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal
from urllib.parse import urlparse
from urllib.request import url2pathname

BUNDLE_DIR: Final = Path(__file__).resolve().parents[2] / "data" / "ids_schema" / "1.0.0"
IDS_NAMESPACE: Final = "http://standards.buildingsmart.org/IDS"

PINNED_SHA256: Final[dict[str, str]] = {
    "ids.xsd": "8975dc18bd18f08a345a430a22bf317a54d94671b7db01400042fa43b6c0d1f3",
    "XML/xml.xsd": "61960fb3131e38022caad5360e2f33a3382578ab3c80cd58bd74320ede61b20c",
    "XSD_1.0/XMLSchema.xsd": "4ea1bb11bdc8894ef2bca08b36910a8ab2b123c3e6dc8c1723d56ff5dfc5a9b8",
    "XSD_1.0/datatypes.xsd": "9b7fa77be9372687f654f5013177e3f87db0ce598e43f534d6d7c1628d513b37",
    "XSI/XMLSchema-instance.xsd": (
        "21992a2e3e7825a9d6dedd65d74a2ff7c2e3eb537c82e3e32342189428413637"
    ),
}
"""Hashes dos esquemas oficiais (IDS v1.0.0 commit 1effec6f… e xmlschema 4.3.2)."""

BundleErrorReason = Literal["integrity", "unmapped_uri", "import_unresolved"]


class SchemaBundleError(Exception):
    """Bundle adulterado/incompleto, URI fora da resolução fechada ou import não resolvido."""

    code = "schema_bundle_error"

    def __init__(self, reason: BundleErrorReason, message: str) -> None:
        """Guarda o motivo estável."""
        self.reason: BundleErrorReason = reason
        super().__init__(f"[{reason}] {message}")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class SchemaBundle:
    """Bundle verificado: diretório, hashes por arquivo e mapa fechado de URIs."""

    directory: Path
    manifest_sha256: str
    files: dict[str, str]
    uri_map: dict[str, str]

    @classmethod
    def load(cls, directory: Path = BUNDLE_DIR) -> "SchemaBundle":
        """Confere manifesto, arquivos listados e hashes fixados; recusa qualquer desvio."""
        directory = directory.resolve()
        try:
            manifest_bytes = (directory / "manifest.json").read_bytes()
            manifest: dict[str, Any] = json.loads(manifest_bytes)
        except (OSError, ValueError) as exc:
            raise SchemaBundleError("integrity", f"manifesto do bundle ilegível: {exc}") from exc
        files: dict[str, str] = {}
        for name, record in manifest.get("files", {}).items():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory) or not path.is_file():
                raise SchemaBundleError("integrity", f"arquivo do bundle ausente: {name}")
            digest = _sha(path)
            if digest != record.get("sha256"):
                raise SchemaBundleError("integrity", f"{name} difere do manifesto")
            files[name] = digest
        for name, digest in PINNED_SHA256.items():
            if files.get(name) != digest:
                raise SchemaBundleError("integrity", f"{name} difere do hash oficial fixado")
        uri_map = dict(manifest.get("uri_map", {}))
        for target in uri_map.values():
            if target not in files:
                raise SchemaBundleError(
                    "integrity", f"URI mapeada para arquivo não listado: {target}"
                )
        return cls(
            directory=directory,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            files=files,
            uri_map=uri_map,
        )

    def _listed(self, path: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.directory):
            raise SchemaBundleError("unmapped_uri", f"caminho fora do bundle: {path}")
        relative = resolved.relative_to(self.directory).as_posix()
        if relative not in self.files:
            raise SchemaBundleError("unmapped_uri", f"arquivo não listado no bundle: {relative}")
        return resolved

    def map_uri(self, uri: str) -> str:
        """URI exata do manifesto ou arquivo listado do bundle; o resto é recusado."""
        if uri in self.uri_map:
            return (self.directory / self.uri_map[uri]).as_uri()
        parsed = urlparse(uri)
        if parsed.scheme == "file":
            if parsed.netloc not in ("", "localhost"):
                raise SchemaBundleError("unmapped_uri", "file URI com autoridade não local")
            return self._listed(Path(url2pathname(parsed.path))).as_uri()
        if parsed.scheme == "" or (len(parsed.scheme) == 1 and uri[1:2] == ":"):
            return str(self._listed(Path(uri)))
        raise SchemaBundleError("unmapped_uri", f"URI fora da resolução fechada: {uri}")

    def build_schema(self) -> Any:
        """``XMLSchema10`` novo, offline e sandboxed; avisos viram erro e imports são conferidos."""
        import xmlschema  # type: ignore[import-not-found,unused-ignore]

        def mapper(uri: str) -> str:
            return self.map_uri(uri)

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            try:
                schema = xmlschema.XMLSchema10(
                    str(self.directory / "ids.xsd"),
                    base_url=self.directory.as_uri() + "/",
                    allow="sandbox",
                    defuse="always",
                    use_fallback=False,
                    uri_mapper=mapper,
                )
            except SchemaBundleError:
                raise
            except Exception as exc:
                raise SchemaBundleError(
                    "import_unresolved", f"esquema IDS não montou: {exc}"
                ) from exc
        pinned = set(self.files.values())
        for loaded in schema.maps.iter_schemas():
            url = loaded.url
            parsed = urlparse(url or "")
            if parsed.scheme != "file":
                raise SchemaBundleError("import_unresolved", f"esquema sem origem local: {url!r}")
            path = Path(url2pathname(parsed.path))
            if _sha(path) not in pinned:
                raise SchemaBundleError(
                    "import_unresolved", f"esquema carregado sem hash fixado: {path.name}"
                )
        return schema
