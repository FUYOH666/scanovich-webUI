from gpthub_orchestrator.classifier import classify_messages


def test_pptx_strong_ru():
    m = [{"role": "user", "content": "Сделай презентацию про квартальные метрики"}]
    assert classify_messages(m)["task_type"] == "pptx"


def test_pptx_strong_sgeneriruy_po_teme_priroda():
    m = [{"role": "user", "content": "Сгенерируй презентацию по теме природа"}]
    assert classify_messages(m)["task_type"] == "pptx"


def test_pptx_strong_prezentacia_po_teme():
    m = [{"role": "user", "content": "Презентация по теме устойчивое развитие, 5 слайдов"}]
    assert classify_messages(m)["task_type"] == "pptx"


def test_pptx_strong_generate_presentation_en():
    m = [{"role": "user", "content": "Generate a presentation about oceans"}]
    assert classify_messages(m)["task_type"] == "pptx"


def test_pptx_strong_slash_command():
    m = [{"role": "user", "content": "hey, /pptx on our roadmap"}]
    assert classify_messages(m)["task_type"] == "pptx"


def test_pptx_strong_build_deck():
    m = [{"role": "user", "content": "Please build deck for the board meeting"}]
    assert classify_messages(m)["task_type"] == "pptx"


def test_pptx_strong_presentation_po_etomu():
    m = [{"role": "user", "content": "Презентация по этому тексту ниже:\n\nfoo bar"}]
    assert classify_messages(m)["task_type"] == "pptx"


def test_pptx_weak_slides_ru():
    m = [{"role": "user", "content": "Подготовь слайды про инфраструктуру,5–7 штук"}]
    assert classify_messages(m)["task_type"] == "pptx"


def test_pptx_weak_deck_with_slides_long():
    m = [
        {
            "role": "user",
            "content": "I need a marketing deck with slides on pricing and GTM for Q2 review",
        }
    ]
    assert classify_messages(m)["task_type"] == "pptx"


def test_pptx_short_deck_only_not_triggered():
    m = [{"role": "user", "content": "deck"}]
    assert classify_messages(m)["task_type"] == "simple_chat"


def test_pptx_doc_heavy_weak_yield_summarization():
    m = [{"role": "user", "content": "Please summarize this PDF; also mention slides format"}]
    assert classify_messages(m)["task_type"] == "summarization"


def test_pptx_strong_overrides_summarize_intent():
    m = [
        {
            "role": "user",
            "content": "Summarize this report and make a presentation for executives",
        }
    ]
    assert classify_messages(m)["task_type"] == "pptx"


def test_pptx_code_hints_without_pptx_stays_code():
    m = [
        {
            "role": "user",
            "content": "async def foo():\n    raise RuntimeError('x')\n\nWhy does this traceback happen?",
        }
    ]
    assert classify_messages(m)["task_type"] == "code_help"


def test_pptx_multimodal_workflow_wins_over_pptx():
    m = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this architecture and build deck from it"},
                {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
            ],
        }
    ]
    assert classify_messages(m)["task_type"] == "multimodal_workflow"


def test_pptx_image_without_analyze_strong_phrase():
    m = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Сделай презентацию по этому скриншоту"},
                {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
            ],
        }
    ]
    assert classify_messages(m)["task_type"] == "pptx"

