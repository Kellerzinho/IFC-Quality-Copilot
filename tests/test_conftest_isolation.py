"""Garante que a suíte nunca aponte para os caches reais em ``data/cache``."""

from pathlib import Path

from src.config import BASE_DIR, get_settings


def test_suggestion_cache_points_to_temporary_path_in_tests(tmp_path: Path) -> None:
    settings = get_settings()

    assert Path(settings.suggestion_cache_path) == tmp_path / "suggestion_cache.db"
    assert not Path(settings.suggestion_cache_path).is_relative_to(BASE_DIR)


def test_bsdd_cache_points_to_temporary_path_in_tests(tmp_path: Path) -> None:
    settings = get_settings()

    assert Path(settings.bsdd_cache_path) == tmp_path / "bsdd_cache.json"
    assert not Path(settings.bsdd_cache_path).is_relative_to(BASE_DIR)
