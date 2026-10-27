"""Serialização JSON canônica do catálogo (M1-03/M1-06): uma única forma de bytes."""

import pytest

from src.domain_catalog.canonical import (
    MAX_JSON_DEPTH,
    CanonicalJSONError,
    canonical_json_bytes,
    load_canonical_json,
    parse_json_strict,
)


def test_keys_are_sorted_compact_and_terminated_by_lf() -> None:
    assert canonical_json_bytes({"b": 1, "a": [2, 1]}) == b'{"a":[2,1],"b":1}\n'


def test_non_ascii_text_is_written_as_utf8_not_escaped() -> None:
    assert canonical_json_bytes({"conjunto": "EB_Orçamento"}) == (
        '{"conjunto":"EB_Orçamento"}\n'.encode()
    )


def test_canonical_bytes_round_trip() -> None:
    data = canonical_json_bytes({"zero": 0, "falso": False, "nulo": None, "texto": "1"})

    assert load_canonical_json(data) == {"zero": 0, "falso": False, "nulo": None, "texto": "1"}


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a": 1}\n',
        b'{"a":1}',
        b'{"b":1,"a":2}\n',
        b'\xef\xbb\xbf{"a":1}\n',
        b'{"a":1}\r\n',
    ],
)
def test_non_canonical_layout_is_rejected(raw: bytes) -> None:
    with pytest.raises(CanonicalJSONError):
        load_canonical_json(raw)


def test_duplicate_keys_are_rejected() -> None:
    with pytest.raises(CanonicalJSONError, match="duplicada"):
        load_canonical_json(b'{"a":1,"a":2}\n')


@pytest.mark.parametrize("raw", [b'{"a":NaN}\n', b'{"a":Infinity}\n', b'{"a":1e999}\n'])
def test_non_finite_numbers_are_rejected(raw: bytes) -> None:
    with pytest.raises(CanonicalJSONError, match="não finito"):
        load_canonical_json(raw)


def test_serializing_non_finite_number_is_refused() -> None:
    with pytest.raises(CanonicalJSONError):
        canonical_json_bytes({"a": float("nan")})


# --- Revisão E1-04: toda falha de interpretação vira CanonicalJSONError -----------------


def test_unpaired_surrogate_is_rejected_on_reading() -> None:
    # JSON sintaticamente aceito pelo ``json``, mas sem representação em UTF-8.
    with pytest.raises(CanonicalJSONError, match="surrogate"):
        load_canonical_json(b'["\\ud800"]\n')


@pytest.mark.parametrize("raw", ['["\\ud800"]', '{"\\udfff":1}'], ids=["valor", "chave"])
def test_unpaired_surrogate_is_rejected_by_the_strict_parser(raw: str) -> None:
    # Rascunho e matriz usam o parser estrito sem passar pela forma canônica.
    with pytest.raises(CanonicalJSONError, match="surrogate"):
        parse_json_strict(raw)


def test_valid_surrogate_pair_is_accepted() -> None:
    assert parse_json_strict('["\\ud83d\\ude00"]') == ["\U0001f600"]


def test_text_without_utf8_form_cannot_be_serialized() -> None:
    with pytest.raises(CanonicalJSONError, match="surrogate"):
        canonical_json_bytes({"a": "\ud800"})


def test_integer_beyond_interpreter_limit_is_rejected() -> None:
    with pytest.raises(CanonicalJSONError, match="dígitos"):
        parse_json_strict("[" + "1" * 5000 + "]")


def test_nesting_up_to_the_limit_is_accepted_and_beyond_is_rejected() -> None:
    deepest = "[" * MAX_JSON_DEPTH + "]" * MAX_JSON_DEPTH

    assert parse_json_strict(deepest) is not None
    with pytest.raises(CanonicalJSONError, match="aninhamento"):
        parse_json_strict("[" + deepest + "]")
    with pytest.raises(CanonicalJSONError, match="aninhamento"):
        parse_json_strict('{"a":' + "[" * MAX_JSON_DEPTH + "]" * MAX_JSON_DEPTH + "}")


def test_nesting_beyond_the_parser_recursion_is_rejected() -> None:
    # Profundidade que estoura a recursão do decodificador C antes da checagem própria.
    with pytest.raises(CanonicalJSONError, match="aninhamento"):
        parse_json_strict("[" * 100_000 + "]" * 100_000)
