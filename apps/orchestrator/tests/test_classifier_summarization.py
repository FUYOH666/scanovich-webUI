from gpthub_orchestrator.classifier import classify_messages


def test_summarize_keyword():
    m = [{"role": "user", "content": "Please summarize this PDF attachment"}]
    c = classify_messages(m)
    assert c["task_type"] == "summarization"


def test_long_text_file_analysis():
    long = "x" * 7000
    m = [{"role": "user", "content": long}]
    c = classify_messages(m)
    assert c["task_type"] == "file_analysis"
