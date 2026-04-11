from gpthub_orchestrator.classifier import classify_messages


def test_text_only_simple():
    m = [{"role": "user", "content": "What is a Python list in one sentence?"}]
    c = classify_messages(m)
    assert "text" in c["modalities"]
    assert c["task_type"] == "simple_chat"


def test_text_greeting_tiny():
    m = [{"role": "user", "content": "hello"}]
    c = classify_messages(m)
    assert c["task_type"] == "greeting_or_tiny"


def test_image_triggers_vision_task():
    m = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what is this"},
                {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
            ],
        }
    ]
    c = classify_messages(m)
    assert "image" in c["modalities"]
    assert c["task_type"] in ("image_analysis", "multimodal_workflow")
