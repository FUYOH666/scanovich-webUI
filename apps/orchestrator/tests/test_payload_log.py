from gpthub_orchestrator.payload_log import sanitize_for_log


def test_sanitize_redacts_data_url():
    out = sanitize_for_log({"url": "data:image/png;base64,AAAA"})
    assert out["url"].startswith("<redacted str len=")


def test_sanitize_truncates_long_plain_string():
    s = "x" * 20_000
    out = sanitize_for_log(s, content_str_clip=100)
    assert "<truncated 20000 chars>" in out
    assert len(out) < 200


def test_sanitize_nested_image_url():
    out = sanitize_for_log(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_url", "image_url": {"url": "data:xxx," + "y" * 800}},
            ],
        }
    )
    url = out["content"][1]["image_url"]["url"]
    assert url.startswith("<redacted str len=")
