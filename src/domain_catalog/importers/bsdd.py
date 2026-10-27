"""Importador offline de snapshot bSDD para staging revisável (E4, M1-10).

Lê um arquivo local no formato JSON oficial de importação do bSDD (``ModelVersion
2.0``), preserva bytes e campos, normaliza pela regra ``ifcqc-bsdd-normalization-1`` e
projeta, em rascunho, somente o que tem representação fiel no catálogo: conceito com
tipo escalar, rótulo e enumeração textual; classes viram apenas assertivas de fonte.
Não usa ``BSDDClient``, HTTP, cache legado nem segue URI ou caminho citado no
payload. Classe ou associação bSDD nunca vira ``IFCBinding``, alias, permissão de
escrita ou valor de elemento: mapeamento IFC exige curadoria explícita.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError

from src.domain_catalog.canonical import (
    CanonicalJSONError,
    canonical_json_bytes,
    canonical_json_text,
    load_canonical_json,
    parse_json_strict,
)
from src.domain_catalog.content import CatalogContent, validate_content
from src.domain_catalog.importers.bsdd_models import (
    BSDD_IMPORT_PROFILE,
    BSDD_INPUT_FORMAT,
    BSDD_UUID_NAMESPACE,
    NORMALIZATION_RULE,
    STAGING_FORMAT,
    SUPPORTED_MODEL_VERSION,
    AcquisitionLink,
    BSDDAcquisition,
    BSDDEntity,
    BSDDImportReport,
    BSDDImportResult,
    BSDDSnapshotEnvelope,
    BSDDStaging,
    BSDDStagingDiff,
    BSDDStagingManifest,
    DiffChange,
    DiffEntry,
    DistributionGate,
    PendingMigration,
    ReportItem,
    SnapshotLimits,
    StagingFile,
    UsageStatus,
    envelope_problem,
)
from src.domain_catalog.models import (
    AllowedValue,
    AllowedValueSet,
    ConceptDefinition,
    LocalizedText,
    LogicalType,
    SourceArtifact,
    SourceAssertion,
    SourceCategory,
    SourceLocator,
)

# --- Tabela do subconjunto suportado (documento oficial consultado em 22/10/2026) ---------

_T, _B, _I, _R, _D, _LT = "text", "bool", "int", "real", "datetime", "list_text"
DICTIONARY_FIELDS: dict[str, str] = {
    "ModelVersion": _T,
    "OrganizationCode": _T,
    "DictionaryCode": _T,
    "DictionaryName": _T,
    "DictionaryVersion": _T,
    "LanguageIsoCode": _T,
    "LanguageOnly": _B,
    "UseOwnUri": _B,
    "DictionaryUri": _T,
    "License": _T,
    "LicenseUrl": _T,
    "ChangeRequestEmailAddress": _T,
    "MoreInfoUrl": _T,
    "QualityAssuranceProcedure": _T,
    "QualityAssuranceProcedureUrl": _T,
    "ReleaseDate": _D,
    "Status": _T,
    "Classes": "list:class",
    "Properties": "list:property",
}
CLASS_FIELDS: dict[str, str] = {
    "Code": _T,
    "Name": _T,
    "ClassType": _T,
    "Definition": _T,
    "Description": _T,
    "ParentClassCode": _T,
    "RelatedIfcEntityNamesList": _LT,
    "Synonyms": _LT,
    "ActivationDateUtc": _D,
    "ReferenceCode": _T,
    "CountriesOfUse": _LT,
    "CountryOfOrigin": _T,
    "CreatorLanguageIsoCode": _T,
    "DeActivationDateUtc": _D,
    "DeprecationExplanation": _T,
    "DocumentReference": _T,
    "OwnedUri": _T,
    "ReplacedObjectCodes": _LT,
    "ReplacingObjectCodes": _LT,
    "RevisionDateUtc": _D,
    "RevisionNumber": _I,
    "Status": _T,
    "SubdivisionsOfUse": _LT,
    "Uid": _T,
    "VersionDateUtc": _D,
    "VersionNumber": _I,
    "VisualRepresentationUri": _T,
    "ClassProperties": "list:class_property",
    "ClassRelations": "list:class_relation",
}
PROPERTY_FIELDS: dict[str, str] = {
    "Code": _T,
    "Name": _T,
    "Definition": _T,
    "Description": _T,
    "DataType": _T,
    "Units": _LT,
    "Example": _T,
    "ActivationDateUtc": _D,
    "ConnectedPropertyCodes": _LT,
    "CountriesOfUse": _LT,
    "CountryOfOrigin": _T,
    "CreatorLanguageIsoCode": _T,
    "DeActivationDateUtc": _D,
    "DeprecationExplanation": _T,
    "Dimension": _T,
    "DimensionLength": _I,
    "DimensionMass": _I,
    "DimensionTime": _I,
    "DimensionElectricCurrent": _I,
    "DimensionThermodynamicTemperature": _I,
    "DimensionAmountOfSubstance": _I,
    "DimensionLuminousIntensity": _I,
    "DocumentReference": _T,
    "DynamicParameterPropertyCodes": _LT,
    "IsDynamic": _B,
    "MaxExclusive": _R,
    "MaxInclusive": _R,
    "MinExclusive": _R,
    "MinInclusive": _R,
    "MethodOfMeasurement": _T,
    "OwnedUri": _T,
    "Pattern": _T,
    "PhysicalQuantity": _T,
    "PropertyValueKind": _T,
    "ReplacedObjectCodes": _LT,
    "ReplacingObjectCodes": _LT,
    "RevisionDateUtc": _D,
    "RevisionNumber": _I,
    "Status": _T,
    "SubdivisionsOfUse": _LT,
    "TextFormat": _T,
    "Uid": _T,
    "VersionDateUtc": _D,
    "VersionNumber": _I,
    "VisualRepresentationUri": _T,
    "PropertyRelations": "list:property_relation",
    "AllowedValues": "list:allowed_value",
}
CLASS_PROPERTY_FIELDS: dict[str, str] = {
    "Code": _T,
    "PropertyCode": _T,
    "PropertyUri": _T,
    "Description": _T,
    "PropertySet": _T,
    "Unit": _T,
    "PredefinedValue": _T,
    "IsRequired": _B,
    "IsWritable": _B,
    "MaxExclusive": _R,
    "MaxInclusive": _R,
    "MinExclusive": _R,
    "MinInclusive": _R,
    "Pattern": _T,
    "OwnedUri": _T,
    "PropertyType": _T,
    "SortNumber": _I,
    "Symbol": _T,
    "AllowedValues": "list:allowed_value",
}
ALLOWED_VALUE_FIELDS: dict[str, str] = {
    "Code": _T,
    "Value": _T,
    "Description": _T,
    "Uri": _T,
    "SortNumber": _I,
    "OwnedUri": _T,
}
CLASS_RELATION_FIELDS: dict[str, str] = {
    "RelationType": _T,
    "RelatedClassUri": _T,
    "RelatedClassName": _T,
    "Fraction": _R,
    "OwnedUri": _T,
}
PROPERTY_RELATION_FIELDS: dict[str, str] = {
    "RelatedPropertyName": _T,
    "RelatedPropertyUri": _T,
    "RelationType": _T,
    "OwnedUri": _T,
}
FIELDS_BY_KIND: dict[str, dict[str, str]] = {
    "class": CLASS_FIELDS,
    "property": PROPERTY_FIELDS,
    "class_property": CLASS_PROPERTY_FIELDS,
    "allowed_value": ALLOWED_VALUE_FIELDS,
    "class_relation": CLASS_RELATION_FIELDS,
    "property_relation": PROPERTY_RELATION_FIELDS,
}
REQUIRED_BY_KIND: dict[str, tuple[str, ...]] = {
    "class": ("Code", "Name"),
    "property": ("Code", "Name", "DataType"),
    "allowed_value": ("Code", "Value"),
    "class_relation": ("RelationType", "RelatedClassUri"),
    "property_relation": ("RelatedPropertyUri", "RelationType"),
}
IDENTITY_FIELDS: tuple[str, ...] = (
    "OrganizationCode",
    "DictionaryCode",
    "DictionaryVersion",
    "LanguageIsoCode",
)
DATA_TYPES: frozenset[str] = frozenset(
    {"Boolean", "Character", "Integer", "Real", "String", "Time"}
)
_LOGICAL: dict[str, LogicalType] = {
    "Boolean": "boolean",
    "Integer": "integer",
    "Real": "decimal",
    "String": "string",
}
_CLASS_CATEGORY: dict[str, SourceCategory] = {"Class": "classification", "Material": "material"}
_PROJECTED_PROPERTY_FIELDS: frozenset[str] = frozenset(
    {"Code", "Name", "Definition", "DataType", "AllowedValues"}
)
_PROJECTED_CLASS_FIELDS: frozenset[str] = frozenset({"Code", "Name", "ClassType"})
_RESTRICTIONS: tuple[str, ...] = (
    "MinInclusive",
    "MinExclusive",
    "MaxInclusive",
    "MaxExclusive",
    "Pattern",
)
_UNIT_FIELDS: tuple[str, ...] = (
    "Units",
    "Dimension",
    "PhysicalQuantity",
    "DimensionLength",
    "DimensionMass",
    "DimensionTime",
    "DimensionElectricCurrent",
    "DimensionThermodynamicTemperature",
    "DimensionAmountOfSubstance",
    "DimensionLuminousIntensity",
)
_LANG_TAG = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
_FORBIDDEN_CODE_CHARS = frozenset('"#%/\\:`{}[]|;<>?~')
_MAX_CODE_CHARS = 100
_LIFECYCLE_FIELDS: tuple[str, ...] = (
    "Status",
    "DeActivationDateUtc",
    "ReplacingObjectCodes",
    "DeprecationExplanation",
)
NORMALIZED_FILE = "dictionary.normalized.json"
RAW_FILE = "source.raw.json"
_STAGING_FILES = ("staging.json", "report.json", "acquisition.json", "candidates.json")


class BSDDSnapshotError(ValueError):
    """Snapshot recusado com causa estável (``code``) e localização (``pointer``)."""

    def __init__(self, code: str, message: str, pointer: str | None = None) -> None:
        """Guarda causa e ponteiro JSON; a mensagem inclui ambos."""
        self.code = code
        self.pointer = pointer
        super().__init__(f"[{code}] {message}" + (f" em {pointer}" if pointer else ""))


def _pointer(*parts: str | int) -> str:
    """JSON Pointer (RFC 6901) a partir das partes."""
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _present(value: object) -> bool:
    """Valor informado: ``null`` e lista vazia não informam; ``false`` e ``0`` informam."""
    return value is not None and value != []


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- Leitura limitada e validação estrutural -------------------------------------------------


def _read_limited(path: Path, limit: int) -> bytes:
    """Lê no máximo ``limit + 1`` bytes; arquivo maior é recusado antes do parse."""
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise BSDDSnapshotError("limit_exceeded", f"{path.name} excede {limit} bytes")
    return data


def _walk(value: Any, limits: SnapshotLimits) -> None:
    """Profundidade e tamanho de strings, sem recursão."""
    pending: list[tuple[Any, int, str]] = [(value, 1, "")]
    while pending:
        item, level, where = pending.pop()
        if isinstance(item, str):
            if len(item) > limits.max_string_chars:
                raise BSDDSnapshotError(
                    "limit_exceeded", f"texto com {len(item)} caracteres", where or "/"
                )
        elif isinstance(item, (dict, list)):
            if level > limits.max_depth:
                raise BSDDSnapshotError(
                    "limit_exceeded", f"aninhamento acima de {limits.max_depth}", where or "/"
                )
            entries = item.items() if isinstance(item, dict) else enumerate(item)
            for key, child in entries:
                if isinstance(key, str) and len(key) > limits.max_string_chars:
                    raise BSDDSnapshotError("limit_exceeded", "chave longa demais", where or "/")
                pending.append((child, level + 1, f"{where}{_pointer(key)}"))


def _check_type(value: Any, kind: str, where: str) -> None:
    """Tipo JSON exato do campo documentado; ``null`` é ausência."""
    if value is None:
        return
    ok = {
        _T: isinstance(value, str),
        _D: isinstance(value, str),
        _B: type(value) is bool,
        _I: type(value) is int,
        _R: type(value) in (int, float),
        _LT: isinstance(value, list) and all(isinstance(x, str) for x in value),
    }.get(kind)
    if ok is None:
        ok = isinstance(value, list) and all(isinstance(x, dict) for x in value)
    if not ok:
        raise BSDDSnapshotError(
            "invalid_type", f"esperado {kind}, recebido {type(value).__name__}", where
        )


def _check_object(obj: dict[str, Any], kind: str, where: str) -> None:
    """Tipos e obrigatórios de um objeto do formato; percorre listas aninhadas."""
    fields = FIELDS_BY_KIND[kind]
    for name, value in obj.items():
        if name in fields:
            _check_type(value, fields[name], f"{where}{_pointer(name)}")
            nested = fields[name]
            if nested.startswith("list:") and value is not None:
                for index, child in enumerate(value):
                    _check_object(child, nested[5:], f"{where}{_pointer(name, index)}")
    for name in REQUIRED_BY_KIND.get(kind, ()):
        value = obj.get(name)
        if not isinstance(value, str) or not value.strip():
            raise BSDDSnapshotError("missing_required", f"{kind} sem {name}", where)
    if kind == "property" and obj["DataType"] not in DATA_TYPES:
        raise BSDDSnapshotError(
            "invalid_value",
            f"DataType {obj['DataType']!r} fora de {sorted(DATA_TYPES)}",
            f"{where}/DataType",
        )


def _check_counts(root: dict[str, Any], limits: SnapshotLimits) -> None:
    classes = root.get("Classes") or []
    properties = root.get("Properties") or []
    class_properties = [cp for c in classes for cp in (c.get("ClassProperties") or [])]
    values = sum(len(p.get("AllowedValues") or []) for p in [*properties, *class_properties])
    for label, count, limit in (
        ("classes", len(classes), limits.max_classes),
        ("propriedades", len(properties), limits.max_properties),
        ("associações", len(class_properties), limits.max_class_properties),
        ("valores permitidos", values, limits.max_allowed_values),
    ):
        if count > limit:
            raise BSDDSnapshotError("limit_exceeded", f"{count} {label} acima de {limit}")


def _parse(raw: bytes, limits: SnapshotLimits) -> dict[str, Any]:
    """JSON estrito, forma do perfil, versão do modelo, identidade e tipos."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BSDDSnapshotError("invalid_utf8", f"arquivo não é UTF-8: {exc}") from exc
    try:
        root = parse_json_strict(text)
    except CanonicalJSONError as exc:
        code = "limit_exceeded" if "aninhamento" in str(exc) else "invalid_json"
        raise BSDDSnapshotError(code, str(exc)) from exc
    _walk(root, limits)
    if (
        not isinstance(root, dict)
        or "Dictionary" in root
        or not {
            "Classes",
            "Properties",
        }
        & set(root)
    ):
        raise BSDDSnapshotError(
            "unsupported_format",
            "esperado objeto do modelo de importação com Classes/Properties na raiz "
            "(sem wrapper Dictionary; resposta de API não é snapshot)",
        )
    if root.get("ModelVersion") != SUPPORTED_MODEL_VERSION:
        raise BSDDSnapshotError(
            "unsupported_model_version",
            f"ModelVersion {root.get('ModelVersion')!r}; suportado {SUPPORTED_MODEL_VERSION!r}",
            "/ModelVersion",
        )
    for name, kind in DICTIONARY_FIELDS.items():
        if name in root:
            _check_type(root[name], kind, _pointer(name))
    for name in IDENTITY_FIELDS:
        value = root.get(name)
        if not isinstance(value, str) or not value.strip():
            raise BSDDSnapshotError("missing_identity", f"{name} ausente ou vazio", _pointer(name))
        _check_no_peripheral_space(value, name, _pointer(name))
    for name in ("Classes", "Properties"):
        if not isinstance(root.get(name), list):
            raise BSDDSnapshotError("invalid_type", f"{name} precisa ser lista", _pointer(name))
    for kind, name in (("class", "Classes"), ("property", "Properties")):
        for index, item in enumerate(root[name]):
            _check_object(item, kind, _pointer(name, index))
    _check_counts(root, limits)
    return root


def _envelope(
    raw: bytes, source: SourceArtifact, limits: SnapshotLimits, usage_status: UsageStatus
) -> BSDDSnapshotEnvelope:
    if source.sha256 is not None and (
        source.sha256 != _sha256(raw)
        or (source.size_bytes is not None and source.size_bytes != len(raw))
    ):
        raise BSDDSnapshotError(
            "identity_mismatch",
            f"SourceArtifact declara {source.sha256}/{source.size_bytes}; bytes lidos têm "
            f"{_sha256(raw)}/{len(raw)}",
        )
    root = _parse(raw, limits)
    return BSDDSnapshotEnvelope(
        profile=BSDD_IMPORT_PROFILE,
        input_format=BSDD_INPUT_FORMAT,
        source=source,
        raw_bytes=raw,
        raw_sha256=_sha256(raw),
        raw_size_bytes=len(raw),
        payload_json=canonical_json_text(root),
        model_version=SUPPORTED_MODEL_VERSION,
        organization_code=root["OrganizationCode"],
        dictionary_code=root["DictionaryCode"],
        dictionary_version=root["DictionaryVersion"],
        language_iso_code=root["LanguageIsoCode"],
        origin="synthetic" if source.artifact_type == "synthetic_fixture" else "real",
        declared_license=root.get("License"),
        declared_license_url=root.get("LicenseUrl"),
        usage_status=usage_status,
        limits=limits,
    )


def load_bsdd_snapshot(
    path: Path,
    *,
    source: SourceArtifact,
    limits: SnapshotLimits,
    usage_status: UsageStatus = "unknown",
) -> BSDDSnapshotEnvelope:
    """Lê o arquivo local com limites e confere identidade, versão do modelo e tipos.

    O hash e o tamanho são recalculados dos bytes; se ``source`` os declarar e divergirem,
    a leitura é recusada. ``usage_status`` é a declaração de quem fornece o arquivo.
    """
    return _envelope(_read_limited(path, limits.max_bytes), source, limits, usage_status)


# --- Identidade, referências e normalização ---------------------------------------------------


def _check_no_peripheral_space(value: str, label: str, where: str) -> None:
    """Identidade com espaço periférico é ambígua: recusada, nunca corrigida em silêncio."""
    if value != value.strip():
        raise BSDDSnapshotError(
            "identity_whitespace",
            f"{label} {value!r} tem espaço periférico; '1.0' e '1.0 ' não se distinguem com "
            "segurança e a fonte não é editada pelo importador",
            where,
        )


def _check_code_form(code: str, label: str, where: str) -> None:
    """Forma de código do documento primário fixado em 22/10/2026.

    ``bsdd-fontes-primarias.json``: códigos com até 100 caracteres e sem
    ``"#%/\\:`{}[]|;<>?~``. Aplicada aos códigos de identidade (Class, Property e
    ClassProperty); códigos de ``AllowedValues`` não são cobertos pela observação fixada.
    """
    _check_no_peripheral_space(code, label, where)
    bad = sorted(set(code) & _FORBIDDEN_CODE_CHARS)
    if bad or len(code) > _MAX_CODE_CHARS:
        raise BSDDSnapshotError(
            "invalid_code",
            f"{label} {code!r} fora da forma documentada (caracteres proibidos {bad}, "
            f"{len(code)} de no máximo {_MAX_CODE_CHARS} caracteres)",
            where,
        )


def _check_codes(items: list[dict[str, Any]], key: str, where: str, label: str) -> None:
    """Código único sem caixa; literal idêntico é duplicata, caixa diferente é colisão."""
    seen: dict[str, tuple[str, int]] = {}
    for index, item in enumerate(items):
        literal = item.get(key)
        if literal is None:
            continue
        folded = literal.casefold()
        if folded in seen:
            first, first_index = seen[folded]
            code = "duplicate_code" if first == literal else "code_case_collision"
            raise BSDDSnapshotError(
                code,
                f"{label} {literal!r} repete {first!r} (posição {first_index}); códigos bSDD "
                "não distinguem caixa",
                f"{where}{_pointer(index, key)}",
            )
        seen[folded] = (literal, index)


def _is_uri(text: str) -> bool:
    return "://" in text or text.startswith("urn:")


def _class_property_key(cp: dict[str, Any], where: str) -> tuple[str, str]:
    """Identidade da associação: Code; senão referência local ou URI (exclusivas)."""
    code, uri = cp.get("PropertyCode"), cp.get("PropertyUri")
    if bool(code and code.strip()) == bool(uri and uri.strip()):
        raise BSDDSnapshotError(
            "property_reference_conflict",
            "associação precisa de exatamente um entre PropertyCode (local) e PropertyUri "
            "(externa)",
            where,
        )
    if cp.get("Code"):
        return ("code", cp["Code"].casefold())
    return ("property_code", str(code).casefold()) if code else ("property_uri", str(uri))


def _validate_semantics(root: dict[str, Any]) -> None:
    """LanguageOnly, URIs próprias, códigos e referências locais."""
    if root.get("LanguageOnly") is True:
        raise BSDDSnapshotError(
            "language_only",
            "arquivo LanguageOnly traz só tradução de dicionário existente; não é snapshot "
            "completo e não gera candidatos",
            "/LanguageOnly",
        )
    if root.get("UseOwnUri") is True:
        if not root.get("DictionaryUri"):
            raise BSDDSnapshotError(
                "owned_uri_required", "UseOwnUri exige DictionaryUri", "/DictionaryUri"
            )
        for name in ("Classes", "Properties"):
            for index, item in enumerate(root[name]):
                if not item.get("OwnedUri"):
                    raise BSDDSnapshotError(
                        "owned_uri_required", "UseOwnUri exige OwnedUri", _pointer(name, index)
                    )
    for index, cls in enumerate(root["Classes"]):
        _check_code_form(cls["Code"], "classe", _pointer("Classes", index, "Code"))
        for cp_index, cp in enumerate(cls.get("ClassProperties") or []):
            if cp.get("Code") is not None:
                _check_code_form(
                    cp["Code"],
                    "associação",
                    _pointer("Classes", index, "ClassProperties", cp_index, "Code"),
                )
    for index, prop in enumerate(root["Properties"]):
        _check_code_form(prop["Code"], "propriedade", _pointer("Properties", index, "Code"))
    _check_codes(root["Classes"], "Code", "/Classes", "classe")
    _check_codes(root["Properties"], "Code", "/Properties", "propriedade")
    classes = {c["Code"].casefold() for c in root["Classes"]}
    properties = {p["Code"].casefold() for p in root["Properties"]}
    for index, prop in enumerate(root["Properties"]):
        where = _pointer("Properties", index)
        _check_codes(prop.get("AllowedValues") or [], "Code", f"{where}/AllowedValues", "valor")
        for field in ("ConnectedPropertyCodes", "DynamicParameterPropertyCodes"):
            for ref in prop.get(field) or []:
                if not _is_uri(ref) and ref.casefold() not in properties:
                    raise BSDDSnapshotError(
                        "impossible_local_reference",
                        f"{field} cita {ref!r}, inexistente no dicionário",
                        f"{where}/{field}",
                    )
    for index, cls in enumerate(root["Classes"]):
        where = _pointer("Classes", index)
        parent = cls.get("ParentClassCode")
        if parent is not None and parent.casefold() not in classes:
            raise BSDDSnapshotError(
                "impossible_local_reference",
                f"ParentClassCode {parent!r} inexistente",
                f"{where}/ParentClassCode",
            )
        keys: set[tuple[str, str]] = set()
        for cp_index, cp in enumerate(cls.get("ClassProperties") or []):
            cp_where = f"{where}{_pointer('ClassProperties', cp_index)}"
            key = _class_property_key(cp, cp_where)
            if key in keys:
                raise BSDDSnapshotError(
                    "duplicate_code", f"associação indistinguível {key} na classe", cp_where
                )
            keys.add(key)
            code = cp.get("PropertyCode")
            if code and code.casefold() not in properties:
                raise BSDDSnapshotError(
                    "impossible_local_reference",
                    f"PropertyCode {code!r} não existe em Properties",
                    f"{cp_where}/PropertyCode",
                )
            _check_codes(
                cp.get("AllowedValues") or [], "Code", f"{cp_where}/AllowedValues", "valor"
            )


def _sort_key(item: dict[str, Any]) -> tuple[str, str]:
    code = item.get("Code") or ""
    return (code.casefold(), code)


def _normalize(root: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Documento normalizado e mapa ponteiro bruto → ponteiro normalizado.

    Classes e Properties ordenadas pelo código sem caixa; associações pela identidade;
    listas de valores e listas desconhecidas mantêm a ordem da fonte.
    """
    mapping: dict[str, str] = {}
    normalized = {k: v for k, v in root.items() if k not in ("Classes", "Properties")}
    props = sorted(enumerate(root["Properties"]), key=lambda pair: _sort_key(pair[1]))
    normalized["Properties"] = [item for _, item in props]
    for new, (old, _) in enumerate(props):
        mapping[_pointer("Properties", old)] = _pointer("Properties", new)
    classes_out: list[dict[str, Any]] = []
    ordered = sorted(enumerate(root["Classes"]), key=lambda pair: _sort_key(pair[1]))
    for new, (old, cls) in enumerate(ordered):
        mapping[_pointer("Classes", old)] = _pointer("Classes", new)
        cps = list(enumerate(cls.get("ClassProperties") or []))
        cps.sort(key=lambda pair: _class_property_key(pair[1], ""))
        clone = dict(cls)
        if "ClassProperties" in cls:
            clone["ClassProperties"] = [cp for _, cp in cps]
        for cp_new, (cp_old, _) in enumerate(cps):
            mapping[_pointer("Classes", old, "ClassProperties", cp_old)] = _pointer(
                "Classes", new, "ClassProperties", cp_new
            )
        classes_out.append(clone)
    normalized["Classes"] = classes_out
    return normalized, mapping


def _origin_key(root: dict[str, Any], kind: str, *parts: str) -> str:
    return canonical_json_text(
        [root["OrganizationCode"].casefold(), root["DictionaryCode"].casefold(), kind, *parts]
    )


def _source_key(origin_key: str, version: str) -> str:
    return canonical_json_text([json.loads(origin_key), version])


def _entities(root: dict[str, Any], normalized: dict[str, Any]) -> list[BSDDEntity]:
    """Entidades na ordem do documento normalizado: classes (cada uma seguida de suas
    associações) e depois propriedades."""
    version = root["DictionaryVersion"]
    out: list[BSDDEntity] = []
    for index, cls in enumerate(normalized["Classes"]):
        origin = _origin_key(root, "class", cls["Code"].casefold())
        fields = {k: v for k, v in cls.items() if k != "ClassProperties"}
        out.append(
            BSDDEntity(
                entity_kind="class",
                origin_key=origin,
                source_key=_source_key(origin, version),
                code_literal=cls["Code"],
                name_literal=cls["Name"],
                owned_uri_literal=cls.get("OwnedUri"),
                normalized_pointer=_pointer("Classes", index),
                fields_json=canonical_json_text(fields),
            )
        )
        for cp_index, cp in enumerate(cls.get("ClassProperties") or []):
            key_kind, key_value = _class_property_key(cp, "")
            cp_origin = _origin_key(
                root, "class_property", cls["Code"].casefold(), key_kind, key_value
            )
            code = cp.get("PropertyCode")
            out.append(
                BSDDEntity(
                    entity_kind="class_property",
                    origin_key=cp_origin,
                    source_key=_source_key(cp_origin, version),
                    code_literal=cp.get("Code"),
                    owned_uri_literal=cp.get("OwnedUri"),
                    class_code_literal=cls["Code"],
                    property_ref="local_code" if code else "external_uri",
                    property_code_literal=code,
                    property_uri_literal=cp.get("PropertyUri"),
                    normalized_pointer=_pointer("Classes", index, "ClassProperties", cp_index),
                    fields_json=canonical_json_text(cp),
                )
            )
    for index, prop in enumerate(normalized["Properties"]):
        origin = _origin_key(root, "property", prop["Code"].casefold())
        out.append(
            BSDDEntity(
                entity_kind="property",
                origin_key=origin,
                source_key=_source_key(origin, version),
                code_literal=prop["Code"],
                name_literal=prop["Name"],
                owned_uri_literal=prop.get("OwnedUri"),
                normalized_pointer=_pointer("Properties", index),
                fields_json=canonical_json_text(prop),
            )
        )
    return out


# --- Projeção conservadora --------------------------------------------------------------


def _digest(text: str) -> str:
    return _sha256(text.encode("utf-8"))


def _item(pointer: str, code: str, status: str, reason: str, **extra: Any) -> ReportItem:
    severity = {"projected": "info", "preserved_without_projection": "loss", "pending": "pending"}
    effect = {
        "projected": "projected",
        "preserved_without_projection": "not_projected",
        "pending": "pending_external",
    }
    return ReportItem.model_validate(
        {
            "pointer": pointer,
            "code": code,
            "status": status,
            "severity": extra.pop("severity", severity.get(status, "info")),
            "effect": extra.pop("effect", effect.get(status, "none")),
            "reason": reason,
            **extra,
        }
    )


def _lifecycle_obstacle(fields: dict[str, Any]) -> tuple[str, str] | None:
    """Código e motivo quando a entrada não está ativa na própria fonte.

    ``inactive_or_deprecated``: ``Status`` ``Inactive``, ``DeActivationDateUtc``,
    ``ReplacingObjectCodes`` ou ``DeprecationExplanation`` informados (texto vazio não
    informa). ``status_not_active``: outro ``Status`` diferente do literal ``Active``
    (por exemplo ``Preview`` ou outra grafia), sem presumir o que significa. Nos dois
    casos a projeção fica bloqueada e os campos seguem no staging; validade da entrada
    é revisão humana.
    """
    signals = [
        f"{name}={fields[name]!r}"
        for name in _LIFECYCLE_FIELDS
        if name != "Status" and _present(fields.get(name)) and fields[name] != ""
    ]
    status = fields.get("Status")
    if status == "Inactive":
        signals.insert(0, "Status='Inactive'")
    if signals:
        return (
            "inactive_or_deprecated",
            "entrada inativa, desativada ou depreciada na fonte (" + ", ".join(signals) + "); "
            "não vira candidato sem decisão curatorial explícita",
        )
    if status not in (None, "", "Active"):
        return (
            "status_not_active",
            f"Status {status!r} diferente de 'Active'; significado não presumido, entrada "
            "não vira candidato sem decisão curatorial explícita",
        )
    return None


def _property_obstacle(prop: dict[str, Any], lang_ok: bool) -> str | None:
    """Motivo para não projetar a propriedade, ou ``None`` se a representação é fiel."""
    data_type = prop["DataType"]
    if not lang_ok:
        return "LanguageIsoCode fora da forma de idioma do catálogo; rótulo não representável"
    if data_type not in _LOGICAL:
        return (
            f"DataType {data_type} fora do subconjunto projetável (String, Boolean, Integer, Real)"
        )
    if any(_present(prop.get(field)) for field in _UNIT_FIELDS):
        return (
            "unidade/dimensão não representável sem escolher uma unidade entre várias ou inferir "
            "dimensão pelo nome; preservada no staging"
        )
    if any(_present(prop.get(field)) for field in _RESTRICTIONS):
        return "restrição (Min/Max/Pattern) sem representação fiel no conceito"
    if prop.get("IsDynamic") is True or prop.get("PropertyValueKind") not in (None, "Single"):
        return "valor dinâmico ou não simples (PropertyValueKind) sem representação no conceito"
    values = prop.get("AllowedValues") or []
    if values and data_type != "String":
        return (
            f"enumeração numérica/booleana ({data_type}): o Code identificador não se confunde "
            "com valor; preservada sem projeção"
        )
    if any(not (v.get("Value") or "").strip() for v in values):
        return "valor permitido sem rótulo (Value) não vira rótulo inventado"
    return None


def _dictionary_artifact(
    root: dict[str, Any], normalized_bytes: bytes, synthetic: bool
) -> SourceArtifact:
    key = canonical_json_text(
        [
            root["OrganizationCode"].casefold(),
            root["DictionaryCode"].casefold(),
            root["DictionaryVersion"],
        ]
    )
    terms = root.get("License") or "não declarados no snapshot"
    if root.get("LicenseUrl"):
        terms = f"{terms} ({root['LicenseUrl']})"
    return SourceArtifact(
        id=f"bsdd:dictionary-{_digest(key)[:32]}",
        title=(
            f"bSDD {root['OrganizationCode']}/{root['DictionaryCode']} "
            f"{root['DictionaryVersion']} — normalizado ({NORMALIZATION_RULE})"
        ),
        authors=(root["OrganizationCode"],),
        issued=root.get("ReleaseDate"),
        artifact_type="synthetic_fixture" if synthetic else "dictionary_snapshot",
        location=NORMALIZED_FILE,
        sha256=_sha256(normalized_bytes),
        size_bytes=len(normalized_bytes),
        terms=terms,
        notes=(
            "Artefato normalizado materializado a partir da aquisição bruta; o recibo bruto "
            "(hash e ponteiros) fica em acquisition.json. "
            + ("Fixture sintética." if synthetic else "Snapshot local; termos a conferir.")
        ),
    )


def _project(
    root: dict[str, Any],
    normalized: dict[str, Any],
    entities: list[BSDDEntity],
    normalized_bytes: bytes,
    synthetic: bool,
) -> tuple[CatalogContent | None, list[ReportItem], dict[str, str]]:
    """Candidatos em rascunho, itens do relatório e ID de assertiva por source_key."""
    lang = root["LanguageIsoCode"]
    lang_ok = bool(_LANG_TAG.fullmatch(lang))
    artifact = _dictionary_artifact(root, normalized_bytes, synthetic)
    items: list[ReportItem] = []
    if not lang_ok:
        items.append(
            _item(
                "/LanguageIsoCode",
                "language_not_representable",
                "preserved_without_projection",
                f"idioma {lang!r} fora da forma xx ou xx-YY do catálogo; nenhum rótulo é projetado",
                field="LanguageIsoCode",
            )
        )
    assertions: list[SourceAssertion] = []
    concepts: list[ConceptDefinition] = []
    value_sets: list[AllowedValueSet] = []
    assertion_of: dict[str, str] = {}
    by_pointer = {e.normalized_pointer: e for e in entities}
    for index, cls in enumerate(normalized["Classes"]):
        entity = by_pointer[_pointer("Classes", index)]
        class_type = cls.get("ClassType") or "Class"
        category = _CLASS_CATEGORY.get(class_type)
        lifecycle = _lifecycle_obstacle(cls)
        if lifecycle is not None:
            items.append(
                _item(
                    entity.normalized_pointer,
                    lifecycle[0],
                    "preserved_without_projection",
                    lifecycle[1],
                    severity="warning",
                    entity_code=cls["Code"],
                )
            )
        elif category is None:
            items.append(
                _item(
                    entity.normalized_pointer,
                    "class_not_projected",
                    "preserved_without_projection",
                    f"ClassType {class_type} sem categoria de fonte correspondente",
                    entity_code=cls["Code"],
                )
            )
        else:
            assertion_id = f"bsdd:class-{_digest(entity.source_key)[:32]}"
            assertion_of[entity.source_key] = assertion_id
            assertions.append(
                SourceAssertion(
                    id=assertion_id,
                    source_artifact_id=artifact.id,
                    locator=SourceLocator(table="Classes", row_ref=entity.normalized_pointer),
                    category=category,
                    target_literal=cls["Name"],
                    target_identifier_literal=cls["Code"],
                    notes=(f"origin_key={entity.origin_key}", f"source_key={entity.source_key}"),
                    transcription_status="registered",
                )
            )
            items.append(
                _item(
                    entity.normalized_pointer,
                    "class_source_assertion",
                    "projected",
                    "classe registrada como assertiva de fonte; nenhum binding IFC é criado",
                    entity_code=cls["Code"],
                )
            )
        for field in sorted(set(cls) - _PROJECTED_CLASS_FIELDS - {"ClassProperties"}):
            if field not in CLASS_FIELDS:
                items.append(
                    _item(
                        f"{entity.normalized_pointer}/{field}",
                        "unknown_field",
                        "preserved_without_projection",
                        "campo fora do subconjunto documentado; preservado",
                        field=field,
                        entity_code=cls["Code"],
                    )
                )
            elif _present(cls[field]):
                items.append(
                    _item(
                        f"{entity.normalized_pointer}/{field}",
                        "field_preserved",
                        "preserved_without_projection",
                        "campo preservado no staging; sem destino no catálogo",
                        field=field,
                        entity_code=cls["Code"],
                    )
                )
        for cp_index, cp in enumerate(cls.get("ClassProperties") or []):
            cp_pointer = _pointer("Classes", index, "ClassProperties", cp_index)
            if cp.get("PropertyUri"):
                items.append(
                    _item(
                        cp_pointer,
                        "external_reference_pending",
                        "pending",
                        "PropertyUri externa mantida pendente; nada é baixado nem resolvido",
                        field="PropertyUri",
                        entity_code=cls["Code"],
                    )
                )
            items.append(
                _item(
                    cp_pointer,
                    "class_property_staged",
                    "preserved_without_projection",
                    "associação classe–propriedade (e restrições de classe) só em staging; "
                    "binding IFC exige mapeamento curado",
                    entity_code=cls["Code"],
                )
            )
        for rel_index, _rel in enumerate(cls.get("ClassRelations") or []):
            items.append(
                _item(
                    f"{entity.normalized_pointer}/ClassRelations/{rel_index}",
                    "external_reference_pending",
                    "pending",
                    "relação de classe por URI mantida pendente",
                    entity_code=cls["Code"],
                )
            )
    for index, prop in enumerate(normalized["Properties"]):
        entity = by_pointer[_pointer("Properties", index)]
        where = entity.normalized_pointer
        for field in sorted(prop):
            if field not in PROPERTY_FIELDS:
                items.append(
                    _item(
                        f"{where}/{field}",
                        "unknown_field",
                        "preserved_without_projection",
                        "campo fora do subconjunto documentado; preservado",
                        field=field,
                        entity_code=prop["Code"],
                    )
                )
        for ref_field in ("ConnectedPropertyCodes", "DynamicParameterPropertyCodes"):
            if any(_is_uri(ref) for ref in prop.get(ref_field) or []):
                items.append(
                    _item(
                        f"{where}/{ref_field}",
                        "external_reference_pending",
                        "pending",
                        "referência por URI mantida pendente",
                        field=ref_field,
                        entity_code=prop["Code"],
                    )
                )
        lifecycle = _lifecycle_obstacle(prop)
        if lifecycle is not None:
            items.append(
                _item(
                    where,
                    lifecycle[0],
                    "preserved_without_projection",
                    lifecycle[1],
                    severity="warning",
                    entity_code=prop["Code"],
                )
            )
            continue
        obstacle = _property_obstacle(prop, lang_ok)
        if obstacle is not None:
            items.append(
                _item(
                    where,
                    "property_not_projected",
                    "preserved_without_projection",
                    obstacle,
                    entity_code=prop["Code"],
                )
            )
            continue
        values = prop.get("AllowedValues") or []
        assertion_id = f"bsdd:property-{_digest(entity.source_key)[:32]}"
        assertion_of[entity.source_key] = assertion_id
        domain = [{"Code": v["Code"], "Value": v["Value"]} for v in values]
        assertions.append(
            SourceAssertion(
                id=assertion_id,
                source_artifact_id=artifact.id,
                locator=SourceLocator(table="Properties", row_ref=where),
                category="custom_property",
                target_literal=prop["Name"],
                target_identifier_literal=prop["Code"],
                datatype_literal=prop["DataType"],
                domain_literal_json=canonical_json_text(domain) if domain else None,
                notes=(
                    f"origin_key={entity.origin_key}",
                    f"source_key={entity.source_key}",
                    "categoria de fonte: propriedade definida em dicionário bSDD; não indica "
                    "conjunto nem portador IFC",
                ),
                transcription_status="registered",
            )
        )
        value_set_id = None
        if values:
            value_set_id = (
                f"urn:uuid:{uuid.uuid5(BSDD_UUID_NAMESPACE, entity.source_key + '#AllowedValues')}"
            )
            value_sets.append(
                AllowedValueSet(
                    id=value_set_id,
                    value_type="code",
                    values=tuple(
                        AllowedValue(
                            code=v["Code"], labels=(LocalizedText(lang=lang, text=v["Value"]),)
                        )
                        for v in values
                    ),
                    source_assertion_ids=(assertion_id,),
                    lifecycle="draft",
                )
            )
        definition = prop.get("Definition")
        concepts.append(
            ConceptDefinition(
                id=f"urn:uuid:{uuid.uuid5(BSDD_UUID_NAMESPACE, entity.source_key)}",
                code=f"BSDD_{_digest(entity.source_key).upper()}",
                labels=(LocalizedText(lang=lang, text=prop["Name"]),),
                definition=(LocalizedText(lang=lang, text=definition),) if definition else (),
                logical_type="code" if values else _LOGICAL[prop["DataType"]],
                value_set_id=value_set_id,
                source_assertion_ids=(assertion_id,),
                lifecycle="draft",
                notes=(
                    "Proposta importada de snapshot bSDD; sem equivalência com conceito local, "
                    "sem binding IFC e sem aprovação."
                ),
            )
        )
        items.append(
            _item(
                where,
                "property_projected",
                "projected",
                "conceito em rascunho com tipo, rótulo e valores fiéis",
                entity_code=prop["Code"],
            )
        )
        for field in sorted(set(prop) - _PROJECTED_PROPERTY_FIELDS):
            if field in PROPERTY_FIELDS and _present(prop[field]):
                items.append(
                    _item(
                        f"{where}/{field}",
                        "field_preserved",
                        "preserved_without_projection",
                        "campo preservado no staging; sem destino no conceito",
                        field=field,
                        entity_code=prop["Code"],
                    )
                )
        for v_index, value in enumerate(values):
            for field in sorted(set(value) - {"Code", "Value"}):
                if _present(value[field]):
                    items.append(
                        _item(
                            f"{where}/AllowedValues/{v_index}/{field}",
                            "field_preserved",
                            "preserved_without_projection",
                            "atributo do valor preservado no staging",
                            field=field,
                            entity_code=prop["Code"],
                        )
                    )
    for name in sorted(set(root) - set(DICTIONARY_FIELDS)):
        items.append(
            _item(
                _pointer(name),
                "unknown_field",
                "preserved_without_projection",
                "campo de dicionário fora do subconjunto; preservado",
                field=name,
            )
        )
    if not assertions:
        return None, items, assertion_of
    content = CatalogContent(
        source_artifacts=(artifact,),
        source_assertions=tuple(assertions),
        concepts=tuple(concepts),
        value_sets=tuple(value_sets),
    )
    validate_content(content, for_release=False)
    return content, items, assertion_of


def _diff(before: BSDDStaging, after: BSDDStaging) -> BSDDStagingDiff:
    old = {e.origin_key: e for e in before.entities}
    new = {e.origin_key: e for e in after.entities}
    changed: list[DiffChange] = []
    unchanged = 0
    for key in sorted(set(old) & set(new)):
        a, b = json.loads(old[key].fields_json), json.loads(new[key].fields_json)
        fields = tuple(
            sorted(
                f
                for f in set(a) | set(b)
                if a.get(f, None) != b.get(f, None) or (f in a) != (f in b)
            )
        )
        if fields:
            changed.append(
                DiffChange(
                    origin_key=key,
                    entity_kind=new[key].entity_kind,
                    code_literal=new[key].code_literal,
                    fields=fields,
                )
            )
        else:
            unchanged += 1
    da, db = json.loads(before.dictionary_json), json.loads(after.dictionary_json)
    dictionary_changed = tuple(
        sorted(f for f in set(da) | set(db) if f != "DictionaryVersion" and da.get(f) != db.get(f))
    )

    def entries(keys: set[str], source: dict[str, BSDDEntity]) -> tuple[DiffEntry, ...]:
        return tuple(
            DiffEntry(
                origin_key=k, entity_kind=source[k].entity_kind, code_literal=source[k].code_literal
            )
            for k in sorted(keys)
        )

    return BSDDStagingDiff(
        before_version=before.dictionary_version,
        after_version=after.dictionary_version,
        before_semantic_sha256=before.semantic_sha256,
        after_semantic_sha256=after.semantic_sha256,
        dictionary_fields_changed=dictionary_changed,
        added=entries(set(new) - set(old), new),
        removed=entries(set(old) - set(new), old),
        changed=tuple(changed),
        unchanged=unchanged,
    )


def diff_bsdd_staging(before: BSDDStaging, after: BSDDStaging) -> BSDDStagingDiff:
    """Inclusões, remoções e campos alterados por identidade de origem.

    Não exige lifecycle aprovado, não gera release e não usa ``diff_releases``.
    """
    return _diff(before, after)


def import_bsdd_snapshot(
    snapshot: BSDDSnapshotEnvelope, *, prior: BSDDStaging | None = None
) -> BSDDImportResult:
    """Staging, relatório, recibo e candidatos em rascunho de um snapshot lido.

    Com ``prior``: mesma versão com semântica diferente é conflito; versão nova gera
    candidatos novos, delta e migração pendente por origem, sem associar nada sozinho.
    Envelope cujos bytes, hash, payload ou identidade não coincidem (cópia alterada sem
    validação) é recusado antes de qualquer projeção.
    """
    problem = envelope_problem(snapshot)
    if problem is not None:
        raise BSDDSnapshotError("envelope_integrity", problem)
    root = parse_json_strict(snapshot.payload_json)
    _validate_semantics(root)
    normalized, mapping = _normalize(root)
    normalized_bytes = canonical_json_bytes(normalized)
    semantic = _sha256(normalized_bytes)
    entities = _entities(root, normalized)
    staging = BSDDStaging(
        profile=BSDD_IMPORT_PROFILE,
        normalization_rule=NORMALIZATION_RULE,
        model_version=SUPPORTED_MODEL_VERSION,
        organization_code=root["OrganizationCode"],
        dictionary_code=root["DictionaryCode"],
        dictionary_version=root["DictionaryVersion"],
        language_iso_code=root["LanguageIsoCode"],
        semantic_sha256=semantic,
        dictionary_json=canonical_json_text(
            {k: v for k, v in normalized.items() if k not in ("Classes", "Properties")}
        ),
        entities=tuple(entities),
    )
    diff: BSDDStagingDiff | None = None
    migrations: list[PendingMigration] = []
    if prior is not None:
        if (prior.organization_code.casefold(), prior.dictionary_code.casefold()) != (
            staging.organization_code.casefold(),
            staging.dictionary_code.casefold(),
        ):
            raise BSDDSnapshotError("identity_conflict", "staging anterior é de outro dicionário")
        if (
            prior.dictionary_version == staging.dictionary_version
            and prior.semantic_sha256 != semantic
        ):
            raise BSDDSnapshotError(
                "version_conflict",
                f"DictionaryVersion {staging.dictionary_version} já importada com outro conteúdo "
                f"({prior.semantic_sha256} ≠ {semantic}); exige nova versão ou revisão explícita",
            )
        diff = _diff(prior, staging)
        if prior.dictionary_version != staging.dictionary_version:
            old = {e.origin_key: e for e in prior.entities}
            migrations = [
                PendingMigration(
                    origin_key=e.origin_key,
                    entity_kind=e.entity_kind,
                    from_source_key=old[e.origin_key].source_key,
                    to_source_key=e.source_key,
                )
                for e in entities
                if e.origin_key in old
            ]
    content, items, assertion_of = _project(
        root, normalized, entities, normalized_bytes, snapshot.origin == "synthetic"
    )
    inverse = {new: old for old, new in mapping.items()}
    links = tuple(
        AcquisitionLink(
            entity_kind=e.entity_kind,
            origin_key=e.origin_key,
            source_key=e.source_key,
            raw_pointer=inverse[e.normalized_pointer],
            normalized_pointer=e.normalized_pointer,
            assertion_id=assertion_of.get(e.source_key),
        )
        for e in entities
    )
    gates: dict[str, DistributionGate] = {
        "permitted": "terms_declared_permitted",
        "unknown": "blocked_terms_unknown",
        "restricted": "blocked_terms_restricted",
    }
    gate = gates[snapshot.usage_status]
    counts: dict[str, int] = {
        "classes": sum(1 for e in entities if e.entity_kind == "class"),
        "properties": sum(1 for e in entities if e.entity_kind == "property"),
        "class_properties": sum(1 for e in entities if e.entity_kind == "class_property"),
        "concepts_projected": 0 if content is None else len(content.concepts),
        "assertions_projected": 0 if content is None else len(content.source_assertions),
    }
    for status in ("projected", "preserved_without_projection", "pending"):
        counts[f"items_{status}"] = sum(1 for i in items if i.status == status)
    report = BSDDImportReport(
        profile=BSDD_IMPORT_PROFILE,
        origin=snapshot.origin,
        usage_status=snapshot.usage_status,
        distribution_gate=gate,
        counts=counts,
        items=tuple(items),
    )
    acquisition = BSDDAcquisition(
        profile=BSDD_IMPORT_PROFILE,
        normalization_rule=NORMALIZATION_RULE,
        source=snapshot.source,
        origin=snapshot.origin,
        usage_status=snapshot.usage_status,
        limits=snapshot.limits,
        raw_sha256=snapshot.raw_sha256,
        raw_size_bytes=snapshot.raw_size_bytes,
        normalized_sha256=semantic,
        normalized_size_bytes=len(normalized_bytes),
        links=links,
    )
    logger.info(
        "Snapshot bSDD {}/{} {} em staging: {} entidades, {} conceitos em rascunho",
        staging.organization_code,
        staging.dictionary_code,
        staging.dictionary_version,
        len(entities),
        counts["concepts_projected"],
    )
    return BSDDImportResult(
        staging=staging,
        report=report,
        acquisition=acquisition,
        content=content,
        raw_bytes=snapshot.raw_bytes,
        normalized_bytes=normalized_bytes,
        prior=prior,
        diff=diff,
        migrations=tuple(migrations),
    )


# --- Gravação, reabertura verificada e CLI ------------------------------------------------


def _documents(result: BSDDImportResult) -> Iterator[tuple[str, bytes]]:
    yield RAW_FILE, result.raw_bytes
    yield NORMALIZED_FILE, result.normalized_bytes
    yield "staging.json", canonical_json_bytes(result.staging.model_dump(mode="json"))
    yield "report.json", canonical_json_bytes(result.report.model_dump(mode="json"))
    yield "acquisition.json", canonical_json_bytes(result.acquisition.model_dump(mode="json"))
    yield (
        "candidates.json",
        canonical_json_bytes(
            None if result.content is None else result.content.model_dump(mode="json")
        ),
    )
    if result.prior is not None:
        yield "prior.staging.json", canonical_json_bytes(result.prior.model_dump(mode="json"))
        yield (
            "diff.json",
            canonical_json_bytes(
                None if result.diff is None else result.diff.model_dump(mode="json")
            ),
        )
        yield (
            "migrations.json",
            canonical_json_bytes([m.model_dump(mode="json") for m in result.migrations]),
        )


def _content_sha256(content: CatalogContent | None) -> str | None:
    return (
        None if content is None else _sha256(canonical_json_bytes(content.model_dump(mode="json")))
    )


def write_bsdd_staging(result: BSDDImportResult, out_dir: Path) -> BSDDStagingManifest:
    """Grava staging numa pasta nova, de modo atômico, e a reabre/verifica.

    Pasta existente não é tocada (``FileExistsError``). Os arquivos são gravados numa
    pasta temporária irmã, reabertos e conferidos por ``read_bsdd_staging``; só então a
    pasta é renomeada para o destino. Qualquer falha remove o temporário: o destino
    nunca fica parcial (``staging_write_failed`` para erro de E/S, ``staging_integrity``
    para verificação).
    """
    if out_dir.exists():
        raise FileExistsError(f"staging {out_dir} já existe; escolha uma pasta nova")
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    temp = out_dir.with_name(f".{out_dir.name}.tmp-{uuid.uuid4().hex[:12]}")
    temp.mkdir()
    try:
        manifest = _write_and_verify(result, temp)
        os.rename(temp, out_dir)
    except OSError as exc:
        shutil.rmtree(temp, ignore_errors=True)
        if out_dir.exists():
            raise
        raise BSDDSnapshotError(
            "staging_write_failed", f"gravação do staging falhou e foi descartada: {exc}"
        ) from exc
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return manifest


def _write_and_verify(result: BSDDImportResult, out_dir: Path) -> BSDDStagingManifest:
    """Grava os documentos e o manifesto em ``out_dir`` e exige reabertura idêntica."""
    files: list[StagingFile] = []
    for name, data in _documents(result):
        (out_dir / name).write_bytes(data)
        files.append(StagingFile(path=name, bytes=len(data), sha256=_sha256(data)))
    manifest = BSDDStagingManifest(
        format=STAGING_FORMAT,
        format_version=1,
        profile=BSDD_IMPORT_PROFILE,
        normalization_rule=NORMALIZATION_RULE,
        source=result.acquisition.source,
        limits=result.acquisition.limits,
        usage_status=result.acquisition.usage_status,
        raw_sha256=result.acquisition.raw_sha256,
        semantic_sha256=result.staging.semantic_sha256,
        content_sha256=_content_sha256(result.content),
        files=tuple(files),
    )
    (out_dir / "manifest.json").write_bytes(canonical_json_bytes(manifest.model_dump(mode="json")))
    reopened = read_bsdd_staging(out_dir)
    if reopened != result:
        raise BSDDSnapshotError(
            "staging_integrity", "staging gravado não reabre igual ao resultado"
        )
    return manifest


def _integrity(message: str) -> BSDDSnapshotError:
    return BSDDSnapshotError("staging_integrity", message)


def read_bsdd_staging(
    path: Path, *, expected_prior_semantic_sha256: str | None = None
) -> BSDDImportResult:
    """Reabre o staging: confere bytes e hashes, reaplica a normalização a partir da
    aquisição bruta e exige que normalizado, staging, relatório, recibo, candidatos e
    delta coincidam. Só o resultado reaberto e íntegro segue para a curadoria E2.

    Isso é consistência interna: um ``prior.staging.json`` forjado e regravado junto do
    manifesto e do delta continua consistente. Autenticidade do prior exige âncora
    externa: ``expected_prior_semantic_sha256`` é o hash semântico do staging anterior
    que quem chama conferiu por conta própria (a CLI relê ``--previous``); divergência ou
    ausência de prior é recusada. Hash não é assinatura nem identifica autor.
    """
    try:
        manifest = BSDDStagingManifest.model_validate(
            load_canonical_json((path / "manifest.json").read_bytes())
        )
    except (OSError, CanonicalJSONError, ValidationError) as exc:
        raise _integrity(f"manifesto ilegível: {exc}") from exc
    expected = {RAW_FILE, NORMALIZED_FILE, *_STAGING_FILES}
    listed = {item.path for item in manifest.files}
    if not expected <= listed or listed - expected - {
        "prior.staging.json",
        "diff.json",
        "migrations.json",
    }:
        raise _integrity(f"arquivos do staging inesperados: {sorted(listed)}")
    data: dict[str, bytes] = {}
    for item in manifest.files:
        try:
            blob = (path / item.path).read_bytes()
        except OSError as exc:
            raise _integrity(f"{item.path} listado no manifesto não pôde ser lido: {exc}") from exc
        if len(blob) != item.bytes or _sha256(blob) != item.sha256:
            raise _integrity(f"{item.path} difere do manifesto")
        data[item.path] = blob
    if _sha256(data[RAW_FILE]) != manifest.raw_sha256:
        raise _integrity("aquisição bruta difere do hash registrado")
    prior = None
    if "prior.staging.json" in data:
        try:
            prior = BSDDStaging.model_validate(load_canonical_json(data["prior.staging.json"]))
        except (CanonicalJSONError, ValidationError) as exc:
            raise _integrity(f"prior.staging.json inválido: {exc}") from exc
    if expected_prior_semantic_sha256 is not None and (
        prior is None or prior.semantic_sha256 != expected_prior_semantic_sha256
    ):
        raise _integrity(
            "staging anterior ausente ou diferente da âncora externa "
            f"{expected_prior_semantic_sha256}"
        )
    try:
        snapshot = _envelope(
            data[RAW_FILE], manifest.source, manifest.limits, manifest.usage_status
        )
        result = import_bsdd_snapshot(snapshot, prior=prior)
    except BSDDSnapshotError as exc:
        raise _integrity(f"aquisição bruta não reimporta: {exc}") from exc
    for name, blob in _documents(result):
        if data.get(name) != blob:
            raise _integrity(f"{name} não corresponde à reimportação da aquisição bruta")
    if (
        manifest.semantic_sha256 != result.staging.semantic_sha256
        or manifest.content_sha256 != _content_sha256(result.content)
    ):
        raise _integrity("hashes semântico/de conteúdo do manifesto incoerentes")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Importa um snapshot local para staging revisável; nunca publica nem escreve no catálogo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="arquivo JSON local do snapshot")
    parser.add_argument("--source", type=Path, required=True, help="JSON de SourceArtifact")
    parser.add_argument("--out", type=Path, required=True, help="pasta nova do staging")
    parser.add_argument("--previous", type=Path, help="staging anterior (pasta) para delta")
    parser.add_argument(
        "--usage-status", choices=("permitted", "unknown", "restricted"), default="unknown"
    )
    args = parser.parse_args(argv)
    source = SourceArtifact.model_validate(
        parse_json_strict(args.source.read_text(encoding="utf-8"))
    )
    prior = None if args.previous is None else read_bsdd_staging(args.previous).staging
    snapshot = load_bsdd_snapshot(
        args.input, source=source, limits=SnapshotLimits(), usage_status=args.usage_status
    )
    result = import_bsdd_snapshot(snapshot, prior=prior)
    manifest = write_bsdd_staging(result, args.out)
    logger.info(
        "Staging gravado em {}: semântico {}, candidatos {}, portão {}",
        args.out,
        manifest.semantic_sha256,
        manifest.content_sha256,
        result.report.distribution_gate,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
