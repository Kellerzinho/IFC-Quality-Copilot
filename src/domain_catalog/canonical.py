"""Serialização JSON canônica do catálogo.

Mesma convenção de ``src/experiment/execution_identity.py`` (UTF-8, chaves
ordenadas, separadores compactos), acrescida das regras do plano M1 §7.1: fim de
linha LF, nenhum número não finito e nenhuma chave duplicada. A forma canônica é
única: os mesmos dados produzem os mesmos bytes, e bytes fora dessa forma são
recusados na leitura em vez de normalizados em silêncio.

Toda falha de interpretação vira ``CanonicalJSONError``: texto sem forma UTF-8
(surrogate isolado), inteiro acima do limite de conversão do interpretador e
aninhamento acima de ``MAX_JSON_DEPTH`` (ou além da recursão do decodificador). O
limite próprio torna a aceitação igual em qualquer interpretador; os limites do
Python não são elevados.
"""

import json
import math
from typing import Any

__all__ = [
    "MAX_JSON_DEPTH",
    "CanonicalJSONError",
    "canonical_json_bytes",
    "canonical_json_text",
    "load_canonical_json",
    "parse_json_strict",
]

MAX_JSON_DEPTH = 64
"""Níveis de aninhamento aceitos; muito acima de qualquer estrutura do catálogo."""


class CanonicalJSONError(ValueError):
    """JSON inválido, ambíguo (chave duplicada, NaN) ou fora da forma canônica."""


def canonical_json_text(value: Any) -> str:
    """Texto JSON canônico de um valor, sem quebra de linha final."""
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except ValueError as exc:
        raise CanonicalJSONError(f"valor não serializável de forma canônica: {exc}") from exc


def _without_utf8_form(exc: UnicodeEncodeError) -> CanonicalJSONError:
    return CanonicalJSONError(f"texto com surrogate isolado não tem forma UTF-8: {exc.reason}")


def canonical_json_bytes(value: Any) -> bytes:
    """Bytes UTF-8 canônicos de um valor, terminados por LF."""
    try:
        return (canonical_json_text(value) + "\n").encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _without_utf8_form(exc) from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Monta o objeto recusando chave repetida, que o ``json`` padrão sobrescreveria."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalJSONError(f"chave duplicada no JSON: {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> Any:
    """Recusa ``NaN``/``Infinity``, que JSON estrito não admite."""
    raise CanonicalJSONError(f"número não finito no JSON: {name}")


def _reject_non_finite_float(text: str) -> float:
    """Recusa floats que transbordam para infinito (ex.: ``1e999``)."""
    value = float(text)
    if not math.isfinite(value):
        raise CanonicalJSONError(f"número não finito no JSON: {text}")
    return value


def _parse_int(text: str) -> int:
    """Converte inteiro; acima do limite do interpretador, recusa sem elevar o limite."""
    try:
        return int(text)
    except ValueError as exc:
        raise CanonicalJSONError(
            f"inteiro com {len(text)} dígitos excede o limite de conversão do interpretador"
        ) from exc


def _check_text(text: str) -> None:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _without_utf8_form(exc) from exc


def _check_structure(value: Any) -> None:
    """Recusa aninhamento acima do limite e texto sem forma UTF-8; percorre sem recursão."""
    pending: list[tuple[Any, int]] = [(value, 1)]
    while pending:
        item, level = pending.pop()
        if isinstance(item, str):
            _check_text(item)
        elif isinstance(item, (list, dict)):
            if level > MAX_JSON_DEPTH:
                raise CanonicalJSONError(f"JSON excede {MAX_JSON_DEPTH} níveis de aninhamento")
            if isinstance(item, dict):
                for key, child in item.items():
                    _check_text(key)
                    pending.append((child, level + 1))
            else:
                pending.extend((child, level + 1) for child in item)


def parse_json_strict(text: str) -> Any:
    """Interpreta JSON recusando chave duplicada, número não finito e estrutura inválida."""
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_reject_non_finite_float,
            parse_int=_parse_int,
        )
    except json.JSONDecodeError as exc:
        raise CanonicalJSONError(f"JSON inválido: {exc}") from exc
    except RecursionError as exc:
        raise CanonicalJSONError(
            "JSON excede a profundidade de aninhamento que o decodificador interpreta"
        ) from exc
    _check_structure(value)
    return value


def load_canonical_json(data: bytes) -> Any:
    """Lê bytes que precisam estar exatamente na forma canônica."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CanonicalJSONError(f"conteúdo não é UTF-8: {exc}") from exc
    value = parse_json_strict(text)
    if canonical_json_bytes(value) != data:
        raise CanonicalJSONError("JSON fora da forma canônica (ordem, espaços ou fim de linha)")
    return value
