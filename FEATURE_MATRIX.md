# Feature Matrix

Единственный источник правды для `GPTHub шаблон фич.xlsx`. Любой
рассинхрон — чинить здесь и в xlsx одновременно.

Экспорт для сабмишена и синхронизации с шаблоном: из корня репозитория
`uv run --with openpyxl python scripts/build_features_xlsx.py` → файл
[docs/submission/GPTHub_features_matrix.xlsx](docs/submission/GPTHub_features_matrix.xlsx).

Статусы:

- `Implemented` — код в репе, тесты проходят, путь подтверждён живым
  контрактом MWS (`docs/MWS_CATALOG.md`) либо unit/integration тестом.
- `Implemented (UI-managed)` — работает через встроенные возможности Open
  WebUI, без доп. кода в orchestrator.
- `Wired, pending live smoke` — код есть, нужен end-to-end прогон через
  поднятый docker-stack.
- `Partial` — часть сценариев покрыта, часть нет.
- `Deferred` — не начато.

## Обязательный чеклист (ряды 1–12)

| Row | Feature | Status | How it works in this repo |
|-----|---------|--------|---------------------------|
| 1 | Текстовый чат | Implemented | Open WebUI → orchestrator `/v1/chat/completions` → LiteLLM (по умолчанию `gpt-hub-turbo` → `mws-gpt-alpha`; другие task_type см. ряд 10). Prompt precedence + `X-GPTHub-Trace`. |
| 2 | Голосовой чат | Implemented (UI-managed) | STT/TTS Open WebUI, далее обычный orchestrator-путь. Голосовой текст проходит тот же classifier / router. |
| 3 | Генерация изображений в чате | Implemented | `image_gen.py`: classifier ловит «нарисуй / draw / /image», orchestrator сам зовёт MWS `POST /v1/images/generations` с моделью `qwen-image`, возвращает inline markdown `![](url)` в OpenAI-совместимом ответе (json + stream). См. тесты `tests/test_image_gen.py`. |
| 4 | Аудиофайлы + автоматический ASR | Implemented | `ingest/asr_client.py` + `Settings.resolved_asr_*()`: по умолчанию ASR идёт в MWS `whisper-medium` по тому же `MWS_GPT_API_BASE/KEY`. Можно переопределить `ORCHESTRATOR_ASR_*` для альтернативного хоста. |
| 5 | Изображения (VLM) | Implemented | Ingest определяет image-part → роль `vision` → alias chain `gpt-hub-vision → vision-2 → vision-3 → vision-4 → fallback` → MWS multimodal (`qwen3-vl-30b-a3b-instruct`, `qwen2.5-vl*`, `cotype-pro-vl-32b`). |
| 6 | Файлы и ответы по содержимому | Implemented | Orchestrator `ingest/pipeline.py`: PDF через `pypdf`, DOCX/XLSX/PPTX/DOC/XLS/RTF/EPUB через `markitdown` (Microsoft), plain-text (≈30 расширений). Текст идёт как `document_text` artifact в system prompt. Тесты: `test_ingest_pdf.py`, `test_ingest_text.py`, `test_ingest_richdoc.py`. |
| 7 | Поиск в интернете | Implemented (UI-managed) | Включён через Open WebUI web search (`ENABLE_WEB_SEARCH=true`, `WEB_SEARCH_ENGINE=tavily`, `TAVILY_API_KEY`). Результаты приходят в сообщение, дальше общий orchestrator-путь. |
| 8 | Веб-парсинг по ссылке из сообщения | Implemented | `ingest/url_fetch.py`: детект `http(s)://` в последнем user-сообщении, fetch с таймаутом/лимитом размера, SSRF-блок приватных IP (до и после редиректов), HTML-парсер без внешних зависимостей, artifact `url_text` в system prompt. Тесты: `test_ingest_url.py` (12 тестов включая SSRF и лимиты). |
| 9 | Долгосрочная память | Implemented | `apps/orchestrator/gpthub_orchestrator/memory/`: SQLite store (`store.py`), command parser (`commands.py`), MWS `qwen3-embedding-8b` client (`embeddings.py`), высокоуровневый сервис (`service.py`). Orchestrator ловит «запомни X / забудь X / что ты помнишь», сохраняет факты с эмбеддингом, при обычном запросе подмешивает top-K релевантных фактов как system-блок. Тесты: `test_memory_commands.py`, `test_memory_store.py`, `test_memory_service.py` (~30 тестов; полный orchestrator suite — **261 passed**, 2 skipped). Live save к MWS `qwen3-embedding-8b` может редко давать **ReadTimeout** — см. `memory_embedding_timeout_seconds`, `docs/LIVE_SMOKE.md`. |
| 10 | Автовыбор модели под задачу | Implemented | `classifier.py` (task type + modalities) → `router.py` → `data/model_roles.yaml`: обычный чат → `gpt-hub-turbo` (alpha); summarization/file_analysis → **`gpt-hub-doc`** (72B) с fallback на turbo; code_help → **`gpt-hub-reasoning-or`** (coder) с fallback на turbo; vision → цепочка `gpt-hub-vision*`. Трейс: `X-GPTHub-Trace`. Канон политики: **`docs/MODEL_ROUTING_POLICY.md`**. |
| 11 | Ручной выбор модели | Implemented | Переключается через `ORCHESTRATOR_MODELS_CATALOG=all` + `AUTO_ROUTE_MODEL=false`. Для демо предусмотрен отдельный режим «все алиасы в dropdown WebUI». |
| 12 | Markdown и форматированный код | Implemented | Ответ остаётся OpenAI-совместимым, Open WebUI рендерит markdown/подсветку кода штатно. `reasoning_response_filter` убирает CoT-поля, чтобы они не утекали в `content`. |

## Дополнительный функционал (ряды 13–15)

| Row | Feature | Status | How it works |
|-----|---------|--------|--------------|
| 13 | Deep Research / research-режим | Implemented (WOW-1) | **Expert Council**: `/research` или «глубокое исследование» → `task_type=DEEP_RESEARCH` → `apps/orchestrator/gpthub_orchestrator/council.py` делает параллельный fan-out в 3 MWS-модели (`gpt-hub-turbo` generalist, `gpt-hub-reasoning-or` reasoning, `gpt-hub-doc` doc-expert), каждая с собственной персоной, а затем `gpt-hub-strong` (glm-4.6-357b) синтезирует один финальный ответ в формате «суть → «что говорит совет экспертов» → практические рекомендации». CoT-очистка, partial-failure tolerant (≥2/3 веток), strong-only fallback, emergency composite если synthesis деградирует. Один `chat.completion` на выход. 29 unit-тестов (`test_council.py`) + live smoke через docker (171 s, 3/3 ветки, запись в LIVE_SMOKE.md 2026-04-11). Трейс: `{short_circuit:"expert_council", branches_ok:[...3 moderms...], synthesis_model, total_ms, fallback_used}`. |
| 14 | Генерация презентаций | Implemented (WOW-3) | **`gpthub_orchestrator/pptx/`** — intent (RU/EN + `/pptx`): `task_type=pptx`, router `pptx_slide_plan_json` (или `*_openrouter`). План слайдов: при `pptx_parallel_slide_agents_enabled` — outline LLM + параллельные per-slide агенты (семафор `pptx_slide_agents_concurrency`), иначе монолитный JSON с retry при ошибке парсинга; обрезка до `pptx_max_slides`. Сборка: `build_pptx_from_plan` (`python-pptx`, опционально шаблоны из `pptx_templates_dir` / bundled). Файл: `PptxArtifactStore` → ответ с markdown-превью + ссылка **`GET /artifacts/pptx/{id}?token=…`** (одноразовый токен, TTL `pptx_artifact_ttl_seconds`; публичный префикс `pptx_artifacts_public_base_url`). В `ingest/url_fetch.py` URL артефактов не тянутся повторно (избегаем «съедания» токена WebUI). Short-circuit в `main.py`: после memory и council, **после** image-gen. Опционально **`PPTX_PLAN_MODEL`** и алиасы `gpt-hub-pptx-*` — см. `scripts/bench_pptx_plan_models.py`. **36** тестов: `test_pptx_module.py`, `test_classifier_pptx.py`, `test_main_pptx_short_circuit.py`. В логах: `pptx_timing`, в trace — `pptx`. Живые прогоны: `docs/LIVE_SMOKE.md`. |
| 15 | Другой доп. функционал | Implemented | **`X-GPTHub-Trace`** — production-grade наблюдаемость: routing decision, model chain, fallback attempts, ingest artifacts, classifier source, prompt version, server clock, ingest latency. Header не утекает в `content`. На защите показывается в DevTools. |

## Правила ведения

- При любом изменении статуса — обновить одновременно этот файл и xlsx-шаблон.
- Никакой строки не помечать как `Implemented`, если нет либо теста, либо
  подтверждённого live-smoke.
- Для `Implemented (UI-managed)` явно указать env-переменные WebUI, без
  которых фича не работает.
- Ряды `13–15` идут только как wow-кандидаты и должны конкурировать с
  обязательными рядами за время — см. приоритеты в `ROADMAP.md`.
