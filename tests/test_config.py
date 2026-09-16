from decisionlayer_cli.config import Settings


def test_require_falls_back_to_default():
    settings = Settings(profiles={"default": "dvarb_default"})
    assert settings.require_api_key("claimant") == "dvarb_default"


def test_profile_overrides_default():
    settings = Settings(profiles={"default": "dvarb_default", "respondent": "dvarb_resp"})
    assert settings.require_api_key("respondent") == "dvarb_resp"
