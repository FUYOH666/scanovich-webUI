# Submission artifacts (track C)

- **`GPTHub_features_matrix.xlsx`** — regenerated from [FEATURE_MATRIX.md](../../FEATURE_MATRIX.md) via `uv run --with openpyxl python scripts/build_features_xlsx.py` from the repo root. Keep in sync with the matrix; treat the markdown file as canonical for wording and status rules.
- **`architecture.mmd`** — Mermaid source for the one-slide architecture diagram (WebUI ↔ orchestrator ↔ LiteLLM ↔ MWS with ingest / memory / image-gen / trace). Export to PNG from your editor or `mmdc` if needed for slides.
- **`gpthub-architecture.excalidraw`** — Empty Excalidraw scene placeholder; copy shapes from `architecture.mmd` or import the Mermaid where your Excalidraw build supports it.
- **`SLIDES_SKELETON.md`** — Outline for 5–7 defence slides.
