from gpthub_orchestrator.trace import build_trace, compute_fallback_used


def test_fallback_used_false_when_absent():
    assert compute_fallback_used(None) is False


def test_fallback_used_false_stream_mode():
    assert compute_fallback_used({"mode": "stream_single_attempt"}) is False


def test_fallback_used_true_after_retry():
    assert compute_fallback_used({"retries_after_failure": 1, "attempts": [{"model": "a"}, {"model": "b"}]}) is True


def test_fallback_used_true_multiple_attempts_without_retry_field():
    assert compute_fallback_used({"attempts": [{"model": "a"}, {"model": "b"}]}) is True


def test_build_trace_image_gen_ok():
    t = build_trace(
        classification={"task_type": "simple_chat", "modalities": ["text"]},
        router_suggestion={"model_role": "fast_text", "fallback_aliases": []},
        model_used="gpt-hub",
        image_gen={"status": "ok", "model": "qwen-image"},
        prompt_version="gpthub-prod-1",
    )
    assert t["image_gen"] == {"status": "ok", "model": "qwen-image"}
    assert "orchestrator_fallback" not in t
