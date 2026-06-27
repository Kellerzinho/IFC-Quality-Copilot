from src.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.bsdd_api_url == "https://api.bsdd.buildingsmart.org"
    assert settings.bsdd_cache_enabled is True
    assert settings.post_validation_enabled is True
    assert settings.ids_xsd_path == "data/ids_schema/ids.xsd"
