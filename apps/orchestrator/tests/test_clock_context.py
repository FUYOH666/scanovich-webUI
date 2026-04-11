from gpthub_orchestrator.clock_context import build_session_clock_block
from gpthub_orchestrator.settings import Settings


def _s(**kwargs: object) -> Settings:
    base: dict[str, object] = {"litellm_base_url": "http://x:9", "orchestrator_api_key": "k"}
    base.update(kwargs)
    return Settings(**base)


def test_clock_disabled_returns_none():
    prefix, iso = build_session_clock_block(_s(inject_request_datetime=False))
    assert prefix is None
    assert iso is None


def test_clock_utc_contains_iso():
    prefix, iso = build_session_clock_block(_s(orchestrator_clock_tz="UTC"))
    assert prefix is not None
    assert iso is not None
    assert iso in prefix
    assert "Session context" in prefix


def test_clock_invalid_tz_falls_back_utc():
    prefix, iso = build_session_clock_block(_s(orchestrator_clock_tz="NotA/Timezone"))
    assert prefix is not None
    assert "UTC" in prefix
