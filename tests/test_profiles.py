"""Testes para src/profiles/registry.py."""

from pathlib import Path

import pytest

from src.profiles.registry import create_default_registry, load_custom_profile_from_ids

IDS_PATH = str(Path(__file__).parent.parent / "data" / "ids_templates" / "residencial_nbr15575.ids")


class TestDefaultRegistry:
    def test_default_registry_has_4_profiles(self):
        """create_default_registry deve retornar registro com exatamente 4 perfis."""
        registry = create_default_registry()

        assert len(registry.list_profiles()) == 4

    def test_default_registry_get_budget(self):
        """Perfil budget_readiness deve estar registrado com nome correto."""
        registry = create_default_registry()

        profile = registry.get("budget_readiness")

        assert profile is not None
        assert profile.id == "budget_readiness"
        assert profile.name == "Orçamento-readiness"
        assert "quantities" in profile.required_extractors
        assert "pset_missing" in profile.issue_types
        assert profile.blocking_severities == ["high"]
        assert profile.is_custom is False  # ids_filename definido


class TestLoadCustomProfile:
    def test_load_custom_profile_from_ids(self):
        """Deve criar ReadinessProfile a partir do IDS residencial_nbr15575.ids."""
        profile = load_custom_profile_from_ids(IDS_PATH)

        assert profile.id == "residencial_nbr15575"
        assert profile.name == "residencial_nbr15575"
        assert "pset_missing" in profile.issue_types
        assert "space_unnamed" in profile.issue_types
        assert "quantities" in profile.required_extractors
        assert "materials" in profile.required_extractors
        assert "spaces" in profile.required_extractors
        assert "thermal" in profile.required_extractors

    def test_load_custom_profile_accepts_custom_name(self):
        """profile_name fornecido deve sobrescrever o nome inferido do filename."""
        profile = load_custom_profile_from_ids(IDS_PATH, profile_name="Meu Perfil Custom")

        assert profile.name == "Meu Perfil Custom"
        assert profile.id == "residencial_nbr15575"  # id vem sempre do filename

    def test_custom_profile_is_custom_true(self):
        """Perfil carregado de IDS externo deve ter is_custom == True."""
        profile = load_custom_profile_from_ids(IDS_PATH)

        assert profile.ids_filename is None
        assert profile.is_custom is True
