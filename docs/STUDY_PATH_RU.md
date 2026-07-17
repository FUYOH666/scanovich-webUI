# План изучения репозитория (onboarding)

Чеклист по фазам A–C из внутреннего плана изучения. Отмечай `[x]` по мере
прохождения. Канон продуктовых требований: [`FEATURE_MATRIX.md`](../FEATURE_MATRIX.md),
[`ROADMAP.md`](../ROADMAP.md), [`docs/TEAM_BRIEF_RU.md`](TEAM_BRIEF_RU.md).

## Фаза A — документация (порядок чтения)

- [ ] **A1** [`docs/TEAM_BRIEF_RU.md`](TEAM_BRIEF_RU.md) — продукт, архитектура, что закрыто / что нет.
- [ ] **A2** [`FEATURE_MATRIX.md`](../FEATURE_MATRIX.md) — ряды 1–15, статусы, как доказывается Implemented.
- [ ] **A3** [`ROADMAP.md`](../ROADMAP.md) — §0.1 чеклист, §0.4–0.6 шаги победы, kill switches.
- [ ] **A4** [`docs/LIVE_SMOKE.md`](LIVE_SMOKE.md) — фактические прогоны, PASS/WARN, регрессии.
- [ ] **A5** [`ARCHITECTURE.md`](../ARCHITECTURE.md) + [`docs/MODEL_ROUTING_POLICY.md`](MODEL_ROUTING_POLICY.md) — поток запроса и политика моделей.

**После A:** сверить `ROADMAP` §0.1 (Row 7 live `[ ]`) с `FEATURE_MATRIX` row 7
(`Implemented (UI-managed)`): для сдачи ориентир — **ROADMAP + LIVE_SMOKE**.

## Фаза B — карта кода по рядам матрицы

| Тема | Путь |
|------|------|
| Chat / routing / trace | [`apps/orchestrator/gpthub_orchestrator/main.py`](../apps/orchestrator/gpthub_orchestrator/main.py), [`router.py`](../apps/orchestrator/gpthub_orchestrator/router.py), [`trace.py`](../apps/orchestrator/gpthub_orchestrator/trace.py) |
| Ingest | [`ingest/pipeline.py`](../apps/orchestrator/gpthub_orchestrator/ingest/pipeline.py), `url_fetch.py`, richdoc / markitdown |
| WOW-1 Council | [`council.py`](../apps/orchestrator/gpthub_orchestrator/council.py) |
| WOW-3 PPTX | [`gpthub_orchestrator/pptx/`](../apps/orchestrator/gpthub_orchestrator/pptx/) |
| LiteLLM / MWS | [`infra/litellm/config.yaml`](../infra/litellm/config.yaml), [`docs/MWS_CATALOG.md`](MWS_CATALOG.md) |
| Open WebUI | образ `OPEN_WEBUI_IMAGE` (GHCR), [`infra/docker-compose.yml`](../infra/docker-compose.yml); исходники UI **не** в этом репо — см. [`PUBLIC_HYGIENE_AND_OSS_LEVERAGE_RU.md`](PUBLIC_HYGIENE_AND_OSS_LEVERAGE_RU.md) |

- [ ] Пройти таблицу сверху вниз, открывая только нужные модули (не читать весь orchestrator линейно).

## Фаза C — готовность к организаторам (hands-on)

Выполнять по [`ROADMAP.md`](../ROADMAP.md) §0.4; результаты фиксировать в
[`docs/LIVE_SMOKE.md`](LIVE_SMOKE.md). Полный туториал по Docker/ENV: [`docs/LOCAL_RUN_RU.md`](LOCAL_RUN_RU.md).

- [ ] **C1** Поднять стек из **корня** репо с двумя env и профилем `rag`, например **`make docker-up`** (эквивалент: `docker compose --env-file .env --env-file .env.mws.local -f infra/docker-compose.yml --profile rag up -d --build`) — сервисы healthy.
- [ ] **C2** `curl` health/ready/models (orchestrator 8089, LiteLLM 4000, WebUI 3000).
- [ ] **C3** [`scripts/demo.sh`](../scripts/demo.sh) — ожидание `PASS=12 FAIL=0`, понять `WARN`.
- [ ] **C4** Оператор: Row 2 голос, 4 `.wav`, 5 фото VLM, 7 Tavily (per-chat глобус), 11 ручная модель, 14 PPTX ссылка.
- [ ] **C5** Обновить [`docs/LIVE_SMOKE.md`](LIVE_SMOKE.md) и xlsx:
  `uv run --with openpyxl python scripts/build_features_xlsx.py` из корня репо.
- [ ] **C6** Сабмишен: [`docs/submission/README.md`](submission/README.md) — PDF архитектуры (текст + Mermaid внутри PDF), xlsx матрицы, pptx/экспорт PDF слайдов; при необходимости PNG через `mmdc` для презентации; тег по ROADMAP.

## Тесты (верификация после синков)

Из корня orchestrator:

```bash
cd apps/orchestrator && uv sync --extra dev && uv run pytest -q
```

Ориентир по количеству тестов — только вывод pytest на вашей машине.

---

## Текст для сабмисона (краткая архитектура)

**Продукт:** один чат в **Open WebUI**; сценарии (текст, файлы, картинка, аудио, URL, голос через STT/TTS UI, веб-поиск при включении, WOW: совет моделей, WOW: PPTX) идут **в один OpenAI-совместимый запрос** к **orchestrator**, без второго флагманского режима.

**Контур сервисов:** `Open WebUI` → `orchestrator` (FastAPI: ingest, classifier/router, memory, council, image-gen, PPTX, trace) → `LiteLLM` (алиасы) → **MWS** (upstream чат/VLM/doc/reasoning). Наблюдаемость: заголовок **`X-GPTHub-Trace`**.

**Модели** (см. `infra/litellm/config.yaml`, `docs/MWS_CATALOG.md`): baseline `mws-gpt-alpha` (`gpt-hub-turbo`), тяжёлый `glm-4.6-357b` (`gpt-hub-strong`), документный `qwen2.5-72b-instruct` (`gpt-hub-doc`), код/рассуждения `qwen3-coder-480b-a35b` (`gpt-hub-reasoning-or`), VLM-цепочка `qwen3-vl-*` / `qwen2.5-vl*` / `cotype-pro-vl-32b`, fallback `gemma-3-27b-it`; image-gen — `qwen-image` (MWS `/v1/images/generations`); ASR — `whisper-medium`; память — `qwen3-embedding-8b`; план PPTX — алиасы `gpt-hub-pptx-*` и др.

**Внешние зависимости:** **MWS** (API, `.env` / `.env.mws.local`); **Docker Compose**; **SQLite** для фактов памяти; опционально **Tavily** (WebUI web search, `ENABLE_WEB_SEARCH`, `TAVILY_API_KEY`, bypass эмбеддинга сниппетов); **markitdown** для DOCX/XLSX/PPTX ingest; опционально **embedding shim** (профиль `rag`). Без MWS основной чат не работает.
