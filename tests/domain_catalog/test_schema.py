"""Schema JSON de intercâmbio do pacote (M1-03): artefato gerado, não editado à mão."""

from src.config import BASE_DIR
from src.domain_catalog.canonical import canonical_json_bytes, load_canonical_json
from src.domain_catalog.package import DATA_FILES, MANIFEST_FILE
from src.domain_catalog.schema import SCHEMA_PATH, catalog_json_schema


def test_committed_schema_matches_the_models() -> None:
    assert (BASE_DIR / SCHEMA_PATH).read_bytes() == canonical_json_bytes(catalog_json_schema())


def test_schema_describes_every_package_file() -> None:
    schema = load_canonical_json((BASE_DIR / SCHEMA_PATH).read_bytes())

    assert set(schema["properties"]) == {MANIFEST_FILE, *DATA_FILES.values()}
    assert set(schema["required"]) == set(schema["properties"])
