"""Bundle IDS 1.0.0 offline: bytes oficiais fixados, resolução fechada e nenhum fallback."""

import shutil
import socket
import warnings
from pathlib import Path

import pytest

pytest.importorskip("xmlschema", reason="extra e3 não instalado (xmlschema==4.3.2)")

from src.validation.schema_bundle import BUNDLE_DIR, SchemaBundle, SchemaBundleError
from tests.validation import ids_builders as x

PINNED = {
    "ids.xsd": "8975dc18bd18f08a345a430a22bf317a54d94671b7db01400042fa43b6c0d1f3",
    "XML/xml.xsd": "61960fb3131e38022caad5360e2f33a3382578ab3c80cd58bd74320ede61b20c",
    "XSD_1.0/XMLSchema.xsd": "4ea1bb11bdc8894ef2bca08b36910a8ab2b123c3e6dc8c1723d56ff5dfc5a9b8",
    "XSD_1.0/datatypes.xsd": "9b7fa77be9372687f654f5013177e3f87db0ce598e43f534d6d7c1628d513b37",
    "XSI/XMLSchema-instance.xsd": (
        "21992a2e3e7825a9d6dedd65d74a2ff7c2e3eb537c82e3e32342189428413637"
    ),
}


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("rede proibida")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


def test_bundle_files_match_the_pinned_official_hashes() -> None:
    bundle = SchemaBundle.load()

    assert bundle.directory == BUNDLE_DIR
    for name, digest in PINNED.items():
        assert bundle.files[name] == digest
    assert len(bundle.manifest_sha256) == 64


def test_tampered_or_incomplete_bundle_is_refused(tmp_path: Path) -> None:
    copy = tmp_path / "bundle"
    shutil.copytree(BUNDLE_DIR, copy)
    xsd = copy / "XSD_1.0" / "datatypes.xsd"
    xsd.write_bytes(xsd.read_bytes() + b"\n")
    with pytest.raises(SchemaBundleError) as tampered:
        SchemaBundle.load(copy)
    assert tampered.value.reason == "integrity"
    shutil.rmtree(copy)
    shutil.copytree(BUNDLE_DIR, copy)
    (copy / "XML" / "xml.xsd").unlink()
    with pytest.raises(SchemaBundleError) as missing:
        SchemaBundle.load(copy)
    assert missing.value.reason == "integrity"


def test_placeholder_schema_cannot_be_loaded_as_the_bundle(tmp_path: Path) -> None:
    copy = tmp_path / "bundle"
    shutil.copytree(BUNDLE_DIR, copy)
    shutil.copyfile(BUNDLE_DIR.parent / "ids.xsd", copy / "ids.xsd")
    with pytest.raises(SchemaBundleError):
        SchemaBundle.load(copy)


def test_schema_resolves_transitively_offline_without_warnings(no_network: None) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        schema = SchemaBundle.load().build_schema()
        assert schema.is_valid(x.ids(x.spec("S", x.entity("IFCWALL"))))
        assert not schema.is_valid(x.ids(x.spec("S", x.entity("IFCWALL"), ifc="IFC9")))
    import hashlib
    from urllib.parse import urlparse
    from urllib.request import url2pathname

    loaded = {s.url for s in schema.maps.iter_schemas() if s.url}
    assert loaded
    for url in loaded:
        parsed = urlparse(url)
        assert parsed.scheme == "file"
        path = Path(url2pathname(parsed.path))
        assert hashlib.sha256(path.read_bytes()).hexdigest() in PINNED.values()
    assert not any(url.endswith("ids_schema/ids.xsd") for url in loaded)


@pytest.mark.parametrize(
    "uri",
    ["https://example.invalid/outro.xsd", "http://www.w3.org/2009/01/xml.xsd", "ftp://x/y.xsd"],
)
def test_unknown_remote_uris_are_refused_not_fetched(uri: str, no_network: None) -> None:
    with pytest.raises(SchemaBundleError) as refused:
        SchemaBundle.load().map_uri(uri)
    assert refused.value.reason == "unmapped_uri"


def test_traversal_outside_the_bundle_is_refused() -> None:
    bundle = SchemaBundle.load()
    outside = (BUNDLE_DIR.parent / "ids.xsd").as_uri()
    with pytest.raises(SchemaBundleError):
        bundle.map_uri(outside)
    with pytest.raises(SchemaBundleError):
        bundle.map_uri(BUNDLE_DIR.as_uri() + "/../ids.xsd")


def test_xmlschema_is_the_pinned_version() -> None:
    import importlib.metadata

    assert importlib.metadata.version("xmlschema") == "4.3.2"
    assert importlib.util.find_spec("ifctester") is not None


@pytest.mark.parametrize("path", ["/tmp/bundle/ids.xsd", "/tmp/bundle with space/ids.xsd"])
def test_file_uri_keeps_the_posix_absolute_root(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    from pathlib import PurePosixPath
    from urllib.parse import unquote

    from src.validation import schema_bundle as module

    bundle = SchemaBundle.load()
    expected = PurePosixPath(path)

    def listed(self: SchemaBundle, candidate: PurePosixPath) -> PurePosixPath:
        assert candidate.is_absolute()
        assert candidate == expected
        return candidate

    # Emulate the POSIX stdlib/path boundary; real Windows paths remain covered above.
    monkeypatch.setattr(module, "url2pathname", unquote, raising=False)
    monkeypatch.setattr(module, "Path", PurePosixPath)
    monkeypatch.setattr(SchemaBundle, "_listed", listed)
    assert bundle.map_uri(expected.as_uri()) == expected.as_uri()


def test_file_uri_with_remote_authority_is_refused(no_network: None) -> None:
    bundle = SchemaBundle.load()
    local = (bundle.directory / "ids.xsd").as_uri()
    remote = local.replace("file:///", "file://remote.invalid/", 1)
    with pytest.raises(SchemaBundleError) as refused:
        bundle.map_uri(remote)
    assert refused.value.reason == "unmapped_uri"
