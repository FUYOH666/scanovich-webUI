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


def test_transcript_artifacts_merged_into_routing_text():
    """ASR ingest artifacts extend the last user line so heuristics see spoken intent."""
    m = [{"role": "user", "content": "Прикреплённые документы: transcript — 1"}]
    arts = [{"type": "transcript", "title": "Recording.wav", "content": "Как тестировать веб-интерфейсы?"}]
    c = classify_messages(m, ingest_artifacts=arts)
    assert "веб-интерфейсы" in c["user_text_preview"]


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


def test_image_only_in_earlier_turn_does_not_set_image_modality():
    """Older vision turns must not force modalities.image on a text-only latest user message."""
    m = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe this"},
                {"type": "image_url", "image_url": {"url": "https://example.com/old.png"}},
            ],
        },
        {"role": "assistant", "content": "A diagram."},
        # Avoid words that trigger doc_hints (e.g. substring "document" in "document_text").
        {"role": "user", "content": "Прикреплённые файлы: вложение — 2"},
    ]
    c = classify_messages(m)
    assert c["modalities"] == ["text"]
    assert c["task_type"] == "simple_chat"
