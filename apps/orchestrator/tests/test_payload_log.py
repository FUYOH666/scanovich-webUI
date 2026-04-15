from gpthub_orchestrator.payload_log import build_messages_digest, sanitize_for_log


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


def test_build_messages_digest_plain_and_parts():
    messages = [
        {"role": "user", "content": "hello"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "x"},
                {
                    "type": "input_audio",
                    "input_audio": {"filename": "a.wav", "format": "wav", "base64": "YWI="},
                },
            ],
        },
    ]
    d = build_messages_digest(messages)
    assert d[0]["content_kind"] == "str"
    assert d[0]["str_len"] == 5
    assert d[1]["content_kind"] == "parts"
    assert d[1]["parts"][1]["type"] == "input_audio"
    assert "base64" in d[1]["parts"][1]
