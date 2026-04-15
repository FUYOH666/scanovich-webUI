# Submission artifacts (track C)

Локальный Docker-стек для проверки перед сдачей: [`docs/LOCAL_RUN_RU.md`](../LOCAL_RUN_RU.md).

- **`GPTHub_features_matrix.xlsx`** — из [FEATURE_MATRIX.md](../../FEATURE_MATRIX.md) командой `uv run --with openpyxl python scripts/build_features_xlsx.py`. Лист **«Матрица фич»**: русские заголовки и пояснения, категория (обязательные / доп.), канонический статус EN + расшифровка RU + подробное описание реализации; лист **«Справка»** — словарь статусов. Канон формулировок — markdown-матрица.
- **`architecture.mmd`** — Mermaid: контур сервисов (User → Open WebUI → orchestrator → LiteLLM → MWS, ingest / memory / image-gen / PPTX / council / trace, опционально Tavily и embedding shim). Экспорт в PNG (нужен **`mmdc`** из пакета **`@mermaid-js/mermaid-cli`**):
  - один раз: `npm install -g @mermaid-js/mermaid-cli`
  - из корня репо: `mmdc -i docs/submission/architecture.mmd -o docs/submission/architecture.png`
  - или без установки: `npx -y @mermaid-js/mermaid-cli -i docs/submission/architecture.mmd -o docs/submission/architecture.png`
- **`user_flow.mmd`** — Mermaid: User Flow по **одному чату** (sequence: сообщение → orchestrator → ветки short-circuit / default chat → ответ + `X-GPTHub-Trace`). Экспорт: `mmdc -i docs/submission/user_flow.mmd -o docs/submission/user_flow.png`
- **`architecture.png`**, **`user_flow.png`** — опциональный рендер из `.mmd` (для слайдов / презентации); **не** входят в `GPTHub_architecture_submission.pdf`.
- **`ARCHITECTURE_SUBMISSION_RU.txt`** — исходный текст (сценарии, модели, зависимости); вклеивается в PDF.
- **`GPTHub_architecture_submission.pdf`** — **единственный файл для загрузки** (лимит «1 файл / до 10 МБ / `.pdf`»): **только текст** — описание сценариев, контур, user flow, модели, зависимости; затем **две схемы как полный Mermaid** (`architecture.mmd`, `user_flow.mmd`) моноширинным шрифтом (всё извлекается из PDF текстом, без растровых картинок). Сборка:
  `uv run --with reportlab python scripts/build_submission_architecture_pdf.py`
- **`ARCHITECTURE_FOR_AI.md`** — дубль в Markdown для репозитория; **для формы «1 файл»** достаточно PDF (текст + встроенный Mermaid, без PNG).
- **`gpthub-architecture.excalidraw`** — Empty Excalidraw scene placeholder; copy shapes from `architecture.mmd` or import the Mermaid where your Excalidraw build supports it.
- **`SLIDES_SKELETON.md`** — короткий англоязычный черновик (5–7 слайдов); полный сценарий на **10 слайдов (RU)** — [`SLIDES_10_RU.md`](SLIDES_10_RU.md).
- **`GPTHub_defence_10slides.pptx`** — презентация для сдачи (ровно 10 слайдов: проблема, решение, архитектура, user flow, критерии жюри 50/25/25, доказательства). Сборка из корня репо:
  `uv run --with python-pptx --with pillow python scripts/build_defence_deck_pptx.py`  
  Скрипт: [`scripts/build_defence_deck_pptx.py`](../../scripts/build_defence_deck_pptx.py). Рисунки подтягиваются из `architecture.png` и `user_flow.png` (см. выше `mmdc`).
- **PDF для формы** (лимит организаторов: до 15 слайдов, до 20 МБ, формат `.pdf`): откройте сгенерированный `.pptx` в **Keynote**, **Microsoft PowerPoint** или **LibreOffice Impress** → **Экспорт / Сохранить как PDF**. Типичный размер файла — сотни килобайт — **1–2 порядка ниже** лимита 20 МБ.
- **`docs/submission/assets/README.md`** — опциональные скриншоты (чат, `X-GPTHub-Trace`) для усиления слайдов 8–9; не коммитьте секреты.

Краткий текст для поля «архитектура + сценарии + модели + внешние зависимости»
(можно копировать в форму): см. конец [`docs/STUDY_PATH_RU.md`](../STUDY_PATH_RU.md) (раздел **«Текст для сабмисона»**).
