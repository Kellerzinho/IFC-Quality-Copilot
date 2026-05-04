"""Testes para a politica central de fontes e classificacao de links."""

from src.semantic_registry.registry import DEFAULT_SOURCE_POLICY


def test_classify_official_canonical_uri() -> None:
    result = DEFAULT_SOURCE_POLICY.classify(
        "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall"
    )

    assert result.category == "official"
    assert result.reference_kind == "canonical_uri"
    assert result.is_canonical_uri


def test_classify_official_documentation_link() -> None:
    result = DEFAULT_SOURCE_POLICY.classify(
        "https://docs.ifcopenshell.org/ifcopenshell-python/validation.html"
    )

    assert result.category == "official"
    assert result.reference_kind == "documentation"
    assert result.is_documentation


def test_classify_official_repository_link() -> None:
    result = DEFAULT_SOURCE_POLICY.classify("https://github.com/buildingSMART/IDS")

    assert result.category == "official"
    assert result.reference_kind == "repository"


def test_classify_unregistered_github_as_forbidden() -> None:
    result = DEFAULT_SOURCE_POLICY.classify("https://github.com/fake-org/fake-repo")

    assert result.category == "forbidden"
    assert result.reference_kind == "unregistered"
    assert result.is_forbidden


def test_classify_invalid_reference() -> None:
    result = DEFAULT_SOURCE_POLICY.classify("not-a-url")

    assert result.category == "forbidden"
    assert result.reference_kind == "invalid"
    assert result.is_invalid


def test_classify_unregistered_https_as_trusted_secondary() -> None:
    result = DEFAULT_SOURCE_POLICY.classify("https://example.org/reference")

    assert result.category == "trusted_secondary"
    assert result.reference_kind == "secondary_link"
    assert result.is_secondary_link
