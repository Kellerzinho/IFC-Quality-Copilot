from src.config import Settings


def test_settings_defaults_to_required_bsdd_grounding() -> None:
    settings = Settings()

    assert settings.grounding_mode == "ids_bsdd"


def test_settings_accepts_grounding_mode_ids_bsdd() -> None:
    settings = Settings(grounding_mode="ids_bsdd")

    assert settings.grounding_mode == "ids_bsdd"
    assert settings.bsdd_api_url == "https://api.bsdd.buildingsmart.org"
    assert settings.bsdd_cache_enabled is True
    assert settings.post_validation_enabled is True
    assert settings.ids_xsd_path == "data/ids_schema/ids.xsd"
