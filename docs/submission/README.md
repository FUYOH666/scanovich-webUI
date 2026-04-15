# Submission artifacts (track C)

- **`GPTHub_features_matrix.xlsx`** — regenerated from [FEATURE_MATRIX.md](../../FEATURE_MATRIX.md) via `uv run --with openpyxl python scripts/build_features_xlsx.py` from the repo root. Keep in sync with the matrix; treat the markdown file as canonical for wording and status rules.
- **`architecture.mmd`** — Mermaid: контур сервисов (User → Open WebUI → orchestrator → LiteLLM → MWS, ingest / memory / image-gen / PPTX / council / trace, опционально Tavily и embedding shim). Экспорт в PNG (нужен **`mmdc`** из пакета **`@mermaid-js/mermaid-cli`**):
  - один раз: `npm install -g @mermaid-js/mermaid-cli`
  - из корня репо: `mmdc -i docs/submission/architecture.mmd -o docs/submission/architecture.png`
  - или без установки: `npx -y @mermaid-js/mermaid-cli -i docs/submission/architecture.mmd -o docs/submission/architecture.png`
- **`user_flow.mmd`** — Mermaid: User Flow по **одному чату** (sequence: сообщение → orchestrator → ветки short-circuit / default chat → ответ + `X-GPTHub-Trace`). Экспорт: `mmdc -i docs/submission/user_flow.mmd -o docs/submission/user_flow.png`
- **`architecture.png`**, **`user_flow.png`** — сгенерированные из `.mmd` (можно приложить к форме как отдельные PNG, если платформа позволяет несколько файлов).
- **`ARCHITECTURE_SUBMISSION_RU.txt`** — краткий текст для поля «описание» + перечень файлов в архиве.
- **`GPTHub_architecture_submission.zip`** — **один файл** для площадок с лимитом «макс. 1 файл / 10 МБ / zip»: внутри два PNG + текст (~100 KiB). Загрузить этот `.zip` в форму.
- **`gpthub-architecture.excalidraw`** — Empty Excalidraw scene placeholder; copy shapes from `architecture.mmd` or import the Mermaid where your Excalidraw build supports it.
- **`SLIDES_SKELETON.md`** — Outline for 5–7 defence slides.

Краткий текст для поля «архитектура + сценарии + модели + внешние зависимости»
(можно копировать в форму): см. конец [`docs/STUDY_PATH_RU.md`](../STUDY_PATH_RU.md) (раздел **«Текст для сабмисона»**).
