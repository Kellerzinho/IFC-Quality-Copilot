"""Schema JSON de intercâmbio do pacote de catálogo, formato 1 (M1-03).

Gerado a partir dos modelos Pydantic para não divergir deles. O arquivo versionado
``data/catalogs/schemas/catalog-v1.json`` é uma projeção: regenerar com
``python -m src.domain_catalog.schema`` sempre que o formato mudar. Mudança
incompatível de formato exige ``format_version`` novo, não edição deste arquivo.
"""

from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from src.config import BASE_DIR
from src.domain_catalog.canonical import canonical_json_bytes
from src.domain_catalog.package import (
    DATA_FILES,
    ENTITY_MODELS,
    MANIFEST_FILE,
    PACKAGE_FORMAT_VERSION,
    CatalogManifest,
)

SCHEMA_PATH = Path("data") / "catalogs" / "schemas" / f"catalog-v{PACKAGE_FORMAT_VERSION}.json"


def catalog_json_schema() -> dict[str, Any]:
    """Schema do pacote como objeto cujas propriedades são os arquivos do release."""
    models: list[type[BaseModel]] = [CatalogManifest, *ENTITY_MODELS.values()]
    _, definitions = models_json_schema(
        [(model, "validation") for model in models], ref_template="#/$defs/{model}"
    )
    properties: dict[str, Any] = {MANIFEST_FILE: {"$ref": "#/$defs/CatalogManifest"}}
    for kind, file_name in DATA_FILES.items():
        properties[file_name] = {
            "type": "array",
            "items": {"$ref": f"#/$defs/{ENTITY_MODELS[kind].__name__}"},
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:ifcqc:catalog-package:{PACKAGE_FORMAT_VERSION}",
        "title": f"Pacote de catálogo do IFC Quality Copilot, formato {PACKAGE_FORMAT_VERSION}",
        "description": (
            "Cada propriedade é um arquivo JSON canônico da pasta do release. "
            "Gerado de src/domain_catalog; não editar à mão."
        ),
        "type": "object",
        "properties": properties,
        "required": sorted(properties),
        "additionalProperties": False,
        "$defs": definitions["$defs"],
    }


def main() -> int:
    """Regrava o schema versionado a partir dos modelos atuais."""
    destination = BASE_DIR / SCHEMA_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical_json_bytes(catalog_json_schema()))
    logger.info("Schema do catálogo gravado em {}", SCHEMA_PATH.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
