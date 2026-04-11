"""Content part extraction for ingest."""

import base64

from gpthub_orchestrator.ingest.parts import extract_file_work_items, work_item_from_part


def test_work_item_from_pdf_file_part():
    raw = b"%PDF-1.4 minimal"
    b64 = base64.standard_b64encode(raw).decode("ascii")
    part = {
        "type": "file",
        "file": {"filename": "x.pdf", "file_data": f"data:application/pdf;base64,{b64}"},
    }
    w = work_item_from_part(part)
    assert w is not None
    assert w.filename == "x.pdf"
    assert w.mime == "application/pdf"
    assert w.raw == raw


def test_extract_from_last_user_pdf():
    pdf_b64 = base64.standard_b64encode(b"%PDF-1.4 test").decode("ascii")
    messages = [
        {"role": "user", "content": "old"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Summarize"},
                {
                    "type": "file",
                    "file": {
                        "filename": "doc.pdf",
                        "file_data": f"data:application/pdf;base64,{pdf_b64}",
                    },
                },
            ],
        },
    ]
    idx, items = extract_file_work_items(messages)
    assert idx == 1
    assert len(items) == 1
    assert items[0][1].filename == "doc.pdf"
