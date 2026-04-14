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


def test_open_webui_follow_up_prompt_not_code_help_when_history_has_compare():
    """Scraped web UI often contains 'compare' (nav); must not force code_help."""
    blob = """### Task:
Suggest 3-5 relevant follow-up questions or prompts that the user might naturally ask next in this conversation as a **user**, based on the chat history, to help continue or deepen the discussion.
### Chat History:
<chat_history>
USER: news?
ASSISTANT: See BenchmarksComparePlayground on example.com for CodingTop models.
</chat_history>"""
    c = classify_messages([{"role": "user", "content": blob}])
    assert c["task_type"] == "simple_chat"
    assert c["complexity_score"] == 0


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
