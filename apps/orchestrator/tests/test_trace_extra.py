from gpthub_orchestrator.trace import compute_fallback_used


def test_fallback_used_false_when_absent():
    assert compute_fallback_used(None) is False


def test_fallback_used_false_stream_mode():
    assert compute_fallback_used({"mode": "stream_single_attempt"}) is False


def test_fallback_used_true_after_retry():
    assert compute_fallback_used({"retries_after_failure": 1, "attempts": [{"model": "a"}, {"model": "b"}]}) is True


def test_fallback_used_true_multiple_attempts_without_retry_field():
    assert compute_fallback_used({"attempts": [{"model": "a"}, {"model": "b"}]}) is True
