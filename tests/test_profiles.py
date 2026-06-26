"""Testes para src/profiles/registry.py."""

from pathlib import Path

from src.profiles.registry import create_default_registry, load_custom_profile_from_ids

IDS_PATH = str(Path(__file__).parent.parent / "data" / "ids_templates" / "residencial_nbr15575.ids")


class TestDefaultRegistry:
    def test_default_registry_has_expanded_profiles(self):
        """create_default_registry deve expor perfis base, ids e domínios principais."""
        registry = create_default_registry()

        assert len(registry.list_profiles()) == 10
        assert registry.get("base_ifc") is not None
        assert registry.get("ids_generic") is not None
        assert registry.get("hvac_readiness") is not None
        assert registry.get("fire_safety_readiness") is not None
        assert registry.get("acoustic_readiness") is not None
        assert registry.get("structural_readiness") is not None

    def test_default_registry_get_budget(self):
        """Perfil budget_readiness deve estar registrado com metadados ampliados."""
        registry = create_default_registry()

        profile = registry.get("budget_readiness")

        assert profile is not None
        assert profile.id == "budget_readiness"
        assert profile.name == "Orçamento-readiness"
        assert "quantities" in profile.required_extractors
        assert "pset_missing" in profile.issue_types
        assert profile.blocking_severities == ["high"]
        assert "IfcWall" in profile.entity_scope
        assert "classifications" in profile.supported_data_categories
        assert profile.is_custom is False

    def test_default_registry_energy_and_hvac_have_distinct_scope(self):
        registry = create_default_registry()

        energy = registry.get("energy_readiness")
        hvac = registry.get("hvac_readiness")

        assert energy is not None
        assert hvac is not None
        assert "IfcRelSpaceBoundary" in energy.entity_scope
        assert "IfcFlowTerminal" in hvac.entity_scope
        assert "boundaries" in energy.required_extractors
        assert "assets" in hvac.required_extractors


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
        assert "IfcWall" in profile.entity_scope
        assert "property" in profile.supported_data_categories

    def test_load_custom_profile_accepts_custom_name(self):
        """profile_name fornecido deve sobrescrever o nome inferido do filename."""
        profile = load_custom_profile_from_ids(IDS_PATH, profile_name="Meu Perfil Custom")

        assert profile.name == "Meu Perfil Custom"
        assert profile.id == "residencial_nbr15575"

    def test_custom_profile_is_custom_true(self):
        """Perfil carregado de IDS externo deve ter is_custom == True."""
        profile = load_custom_profile_from_ids(IDS_PATH)

        assert profile.ids_filename is None
        assert profile.is_custom is True
