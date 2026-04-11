"""Settings: ASR/MWS fallback resolution."""

from __future__ import annotations

from gpthub_orchestrator.settings import Settings


def _mk(**over) -> Settings:
    base = {
        "litellm_base_url": "http://litellm:4000",
        "orchestrator_api_key": "t",
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def test_asr_falls_back_to_mws_when_asr_unset():
    s = _mk(
        mws_gpt_api_base="https://api.gpt.mws.ru/v1",
        mws_gpt_api_key="sk-test",
    )
    assert s.resolved_asr_base_url() == "https://api.gpt.mws.ru/v1"
    assert s.resolved_asr_api_key() == "sk-test"


def test_explicit_asr_overrides_mws():
    s = _mk(
        mws_gpt_api_base="https://api.gpt.mws.ru/v1",
        mws_gpt_api_key="sk-mws",
        orchestrator_asr_base_url="http://localhost:8001/v1",
        orchestrator_asr_api_key="local-key",
    )
    assert s.resolved_asr_base_url() == "http://localhost:8001/v1"
    assert s.resolved_asr_api_key() == "local-key"


def test_asr_empty_when_nothing_set():
    s = _mk()
    assert s.resolved_asr_base_url() is None
    assert s.resolved_asr_api_key() is None
