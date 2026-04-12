# GPTHub Prod: Handoff Для Нового Чата

**Назначение:** единый документ для нового окна чата, чтобы быстро передать:

- что за проект;
- в каком он состоянии **сейчас**;
- какая архитектура зафиксирована;
- какие задачи активны и в каком порядке;
- какие файлы — канон;
- что нельзя ломать;
- с чего начинать продолжение разработки.

> Этот файл **обязательно** должен оставаться синхронизированным с
> `ROADMAP.md`, `FEATURE_MATRIX.md`, `CHANGELOG.md`. Если новый чат находит
> расхождение — правим канон, а не создаём вторую правду.

## 1. Что это за проект

`gpthub-prod` — чистый продуктовый shell для кейса MWS GPT.

Ровно один runtime path: `Open WebUI → orchestrator → LiteLLM → MWS`.

Это **не legacy repo**, не архив и не второй прототип. Есть также старый
стек `gpthub-v3-*` в docker — его нужно остановить, он конфликтует по
портам `3000/4000/8089` и больше не используется.

## 2. Главная продуктовая идея

Единый AI workspace в одном окне чата. Правила:

- один основной UX-путь;
- одна основная архитектура;
- одна дифференциация: `mixed input`;
- никакого второго flagship-mode до закрытия baseline.

`mixed input` означает: один пользовательский запрос объединяет текст,
PDF/текстовые файлы, картинку, аудио и URL; orchestrator собирает это за
один проход; пользователь получает один ответ.

## 3. Текущий статус (обновлять перед передачей контекста!)

### 3.1. Обязательные ряды 1–12

| Row | Feature | Status |
|---|---|---|
| 1 | Текстовый чат | **Implemented** (live: `demo.sh` 2026-04-11 11:46 PASS) |
| 2 | Голосовой чат | Implemented (UI-managed STT/TTS Open WebUI; нужен живой micro-демо) |
| 3 | Генерация изображений | **Implemented** (`image_gen.py` → MWS `qwen-image`; live PASS в `demo.sh`) |
| 4 | Аудио + ASR | **Implemented** (ASR fallback → MWS `whisper-medium`; нужен live `.wav` upload) |
| 5 | Изображения (VLM) | Implemented (код + тесты; нужен live smoke с фото) |
| 6 | Файлы | **Implemented** + **fix 2026-04-12**: WebUI делал свой RAG-эмбеддинг → `'NoneType' encode` краш на загрузке PDF; включили `BYPASS_EMBEDDING_AND_RETRIEVAL=true` (см. `LIVE_SMOKE.md` 2026-04-12). Ждём операторский retry для финального `Implemented` в matrix. |
| 7 | Поиск в интернете | **Implemented** (UI-managed: `ENABLE_WEB_SEARCH=true` + Tavily + **`BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL=true`**; без bypass — краш на `embedding_function=None`. С bypass панель «источников» в WebUI может врать, см. `LIVE_SMOKE.md` Row 7 follow-up) |
| 8 | Веб-парсинг URL | **Implemented** (`ingest/url_fetch.py`, SSRF, 12 тестов; live PASS в `demo.sh`) |
| 9 | Долгосрочная память | **Implemented** (SQLite + `qwen3-embedding-8b`; live PASS в `demo.sh`) |
| 10 | Автовыбор модели | **Implemented** (live trace в `demo.sh`) |
| 11 | Ручной выбор модели | Implemented (нужен демо-режим с dropdown) |
| 12 | Markdown / код | **Implemented** |

**261 unit/integration тестов проходят** (`apps/orchestrator`, `uv run pytest -q`).

### 3.2. Доп. ряды 13–15 (wow + trace)

- **Row 13 Expert Council (WOW-1)** — **Implemented** ✅ (`main` @ `9393d30`).
  `council.py`: fan-out в `gpt-hub-turbo` (generalist) + `gpt-hub-reasoning-or`
  + `gpt-hub-doc`, synthesis через `gpt-hub-strong` (`glm-4.6-357b`), один
  `chat.completion` наружу в формате «суть → совет экспертов → практические
  рекомендации». 4 защитных слоя: branch-timeout / min-branches /
  `merge_reasoning_exclude_into_body` + CoT-strip / CoT-dump heuristic →
  emergency composite. Триггеры: `/research`, «глубокое исследование»,
  «совет экспертов», «мультиэкспертный…», `deep research`. 29 unit-тестов
  в `test_council.py`. Live: 2026-04-11 11:32 (171 s, 3/3 ветки, clean
  3425-char RU synthesis) + 2026-04-11 11:46 (`demo.sh` без `--skip-wow`).
- **Row 14 PPTX generation (WOW-3)** — **Implemented** ✅. `pptx_gen.py`:
  intent detection (RU/EN + `/pptx`/`/slides`), JSON slide plan via
  `gpt-hub-strong` (retry on parse failure), `python-pptx` deck builder,
  download endpoint `GET /v1/files/pptx/{token}`. **57** unit-тестов в
  `test_pptx_gen.py` (в т.ч. CoT-strip + trailing JSON + RU intent-паттерны).
- **Row 15 X-GPTHub-Trace** — **Implemented** ✅. Подсвечиваем на защите.

### 3.3. Готовность к сдаче

- `[x]` MWS контракты проверены напрямую (`docs/MWS_CATALOG.md`):
  text (`mws-gpt-alpha`), image (`qwen-image`), whisper (`whisper-medium`),
  embeddings (`qwen3-embedding-8b`, dim 4096).
- `[x]` `FEATURE_MATRIX.md` синхронизирован (Row 13 = WOW-1, Row 14 = WOW-3).
- `[x]` v3-стек остановлен; prod compose поднят, все три сервиса `Healthy`.
- `[x]` `scripts/demo.sh` (без `--skip-wow`) — **PASS=12 FAIL=0**; **WARN**
  только если эвристики шагов 8–9 не находят council/PPTX в теле ответа
  (перезапустить после деплоя WOW-3; журнал WARN=1 из‑за PPTX **устарел**).
- `[x]` `docs/LIVE_SMOKE.md` ведётся: 2026-04-11 `demo.sh` + 2026-04-12 PDF/PPTX/E2E.
- `[x]` `docs/submission/` — `architecture.mmd`,
  `gpthub-architecture.excalidraw`, `SLIDES_SKELETON.md`,
  `GPTHub_features_matrix.xlsx` (перегенерирован с Row 13 + 14).
- `[ ]` Архитектурная диаграмма PNG/SVG (исходники есть).
- `[ ]` Demo-видео 2–3 минуты — Step 8.
- `[ ]` Финальная презентация (есть `SLIDES_SKELETON.md`).
- `[ ]` git tag `demo-ready` — Step 9.

## 4. Что считается каноном

Если нужно быстро понять проект, читать в таком порядке:

1. `README.md`
2. `ARCHITECTURE.md`
3. `ROADMAP.md` (содержит рабочий трекер в разделе 0)
4. `FEATURE_MATRIX.md`
5. `docs/MWS_CATALOG.md` (живой snapshot моделей MWS)
6. `docs/MODEL_ROUTING_POLICY.md` (**политика маршрутизации**: baseline vs реестр ролей `version: 2`, роли → алиасы)
7. `docs/PROMPT_PRECEDENCE.md`
8. `docs/WEBUI_PAYLOAD.md`
9. `docs/TEAM_BRIEF_RU.md`
10. `CHANGELOG.md`

Если какой-то новый документ начнёт противоречить этим файлам — править
нужно канон, а не плодить вторую правду.

## 5. Что уже реализовано в коде

### 5.1. Spine

- `apps/orchestrator/` — FastAPI runtime, **261** unit/integration тестов;
- `apps/embedding_shim/` — optional RAG-профиль (в prod compose **не** используется);
- `infra/docker-compose.yml` — единый запуск; `.env.mws.local` прокидывается
  **и в orchestrator** (раньше только в litellm);
- `infra/litellm/config.yaml` — alias map сверена с живым каталогом MWS.

### 5.2. Реализованные модули

- `ingest/url_fetch.py` — URL detect + fetch + HTML→text + SSRF-защита
  (блок private IP до и после редиректов, content-type whitelist,
  size/timeout caps, без внешних зависимостей).
- `image_gen.py` — intent detection (RU/EN/slash-command), вызов MWS
  `/images/generations`, OpenAI-compatible ответ (json + stream) с inline
  `![](url)`, fall-through в обычный chat при ошибке.
- `memory/` — пакет для row 9:
  - `store.py` — thread-safe SQLite store, упаковка float32-эмбеддингов
    в BLOB, cosine-ranking в памяти, изоляция по `user_id`.
  - `commands.py` — чистый парсер команд «запомни / забудь / forget_all /
    что ты помнишь» (RU + EN + `/remember`, `/forget`, `/memories`).
  - `embeddings.py` — прямой клиент MWS `POST /v1/embeddings` с моделью
    `qwen3-embedding-8b` (dim 4096), без LiteLLM.
  - `service.py` — высокоуровневое API: `try_parse_command`,
    `execute_memory_command`, `retrieve_memory_context`,
    `build_memory_system_message`, SSE-чанки для short-circuit.
- **`council.py` (Row 13 WOW-1)** — DEEP_RESEARCH intent + parallel
  fan-out (`gpt-hub-turbo` + `gpt-hub-reasoning-or` + `gpt-hub-doc`) +
  synthesis через `gpt-hub-strong` (`glm-4.6-357b`). 4 защитных слоя:
  branch-timeout / min-branches / `merge_reasoning_exclude_into_body` +
  CoT-strip (никогда не возвращает пустую строку) / CoT-dump heuristic →
  emergency composite. 29 unit-тестов в `test_council.py`.
- `Settings.resolved_asr_base_url()` / `resolved_asr_api_key()` —
  orchestrator-level MWS credentials + автоматический fallback ASR на них.
- `ingest/pipeline.py` — обрабатывает PDF + audio + plain-text
  (≈30 расширений) + URL параллельными задачами.
- `settings.py` — поля `mws_gpt_api_*`, `ingest_url_*`, `image_gen_*`,
  `memory_*`, `council_*` (включая `council_branch_timeout_seconds`,
  `council_synthesis_timeout_seconds`, `council_expert_*`,
  `council_synthesis_model`, `council_min_branches_for_synthesis`).
- **`pptx_gen.py` (Row 14 WOW-3)** — PPTX_GENERATION intent + JSON slide
  plan request to `gpt-hub-strong` (with `<think>` CoT stripping + retry
  on parse failure) + `python-pptx` deck builder + file storage + download
  endpoint `GET /v1/files/pptx/{token}`. 57 unit-тестов в `test_pptx_gen.py`.
  **Live PASS 2026-04-12.**
- `main.py` — lifespan поднимает `MemoryStore`; pipeline short-circuits
  в строгом порядке: memory-command → council → **pptx-gen** → image-gen →
  greeting → normal chat. На normal chat top-K фактов памяти
  инжектится как system-блок перед role prompt.
- `classifier.py` — `TaskType.DEEP_RESEARCH` + `TaskType.PPTX_GENERATION`
  через lazy import для разрыва циклической зависимости.

### 5.3. Что ещё не написано

- Демо-режим «все алиасы в dropdown» для row 11 (минорный).

## 6. Текущий приоритет работ

**Шаги 1, 2, 4, 5, 7 — закрыты (вся code работа завершена).**
Полная раскладка — `ROADMAP.md` раздел 0.4 (victory plan) и 0.5 (kill switches).

- ✅ **Шаг 1 — Live docker smoke** — закрыт, tag `smoke-green`.
- ✅ **Шаг 2 — Полный P0 smoke** — `demo.sh` **PASS=12 FAIL=0** (WARN см. вывод скрипта).
- 🟡 **Шаг 3 — Submission артефакты** — черновики + xlsx пересобран.
  Финализация — после Step 6.
- ✅ **Шаг 4 — Row 7 Tavily toggle** — env vars in `.env`, confirmed.
- ✅ **Шаг 5 — WOW-1 Expert Council** — closed in `main` (`9393d30`).
- 🔜 **Шаг 6 — Operator-сценарии + репетиция** (1 ч, оператор в WebUI).
- ✅ **Шаг 7 — WOW-3 PPTX** — `pptx_gen.py` + 57 тестов в `test_pptx_gen.py`, **261** total. **Live PASS 2026-04-12.**
- 🔜 **Шаг 8 — Запись demo-видео** (1 ч, 2–3 дубля).
- 🔜 **Шаг 9 — Финальная сверка + git tag `demo-ready`**.

Ключевое правило: **wow без baseline = ноль**. Если выбор между
«довести wow» и «сохранить baseline» — всегда сохраняем baseline.

## 7. Путь к победе

Короткая формула: **зелёный baseline раньше синих wow**.

1. ✅ подтверждённый MWS baseline (контракты проверены);
2. ✅ **все 12 обязательных рядов закрыты** (Row 7 — env-флаг, дёшево);
3. ✅ **живой docker smoke** (`demo.sh` без `--skip-wow` — **PASS=12 FAIL=0**);
4. 🟡 `docs/LIVE_SMOKE.md` ведётся; для победного чек-листа желательно
   ≥ 12 зафиксированных прогонов (сейчас 4–5, накопим в Step 6);
5. 🔜 один цельный демо-сценарий на 2–3 минуты (Step 6 репетиция → Step 8 запись);
6. ✅ wow-1: Expert Council. ✅ wow-3: PPTX в `main`, live 2026-04-12;
7. ✅ `X-GPTHub-Trace` как «production-grade» аргумент защиты;
8. 🔜 упаковка в demo-video + feature matrix + architecture + presentation;
9. 🔜 git tag `demo-ready` — точка заморозки.

Условия выбрасывания wow-компонентов — см. `ROADMAP.md` раздел 0.5
(kill switches).

## 8. Активные рабочие треки

- **Трек A (code):** ✅ WOW-1 Council + ✅ WOW-3 PPTX в `main`. Step 4 Tavily — env.
  Правило: wow в `main` только после зелёного прогона.
- **Трек B (infra/smoke):** ✅ Step 1 docker smoke → ✅ Step 2 полный P0
  через `demo.sh` → 🔜 Step 6 репетиция (требует оператора в WebUI) →
  🔜 Step 8 запись видео.
- **Трек C (submission):** 🟡 Step 3 артефакты (черновики готовы:
  диаграмма, slides skeleton, xlsx) → 🔜 финализация слайдов после
  репетиции → 🔜 Step 9 сверка + git tag `demo-ready`.

## 9. Что нельзя делать без крайней необходимости

- не открывать второй флагманский UX-режим;
- не тащить legacy-docs из v3 / старых репо;
- не строить кастомный frontend;
- не размывать demo flow побочными «вау»-идеями;
- не прятать trace или routing прямо в пользовательский `content`;
- не включать в роадмап фичи, которые ломают «один запрос → один ответ».

## 10. Архитектура в одну строку

- `Open WebUI` — UX;
- `orchestrator` — product intelligence (classifier, router, ingest,
  image-gen short-circuit, memory, council fan-out);
- `LiteLLM` — gateway/alias/fallback chain;
- `MWS` — upstream моделей.

Trace принадлежит логам и `X-GPTHub-Trace`, не `content`.

## 11. Команды для старта

```bash
# 0. Остановить старый v3-стек, если он поднят (иначе порты 3000/4000/8089 заняты)
docker rm -f gpthub-v3-orchestrator gpthub-v3-embedding-shim gpthub-v3-open-webui gpthub-v3-litellm 2>/dev/null || true

# 1. Проверить env
cp .env.example .env                              # если ещё нет
# .env.mws.local уже содержит рабочий MWS_GPT_API_KEY

# 2. Поднять prod stack
docker compose -f infra/docker-compose.yml up -d --build

# 3. Тесты orchestrator
cd apps/orchestrator
uv sync --extra dev
uv run pytest -q     # ожидается 261 passed
```

Open WebUI: `http://localhost:3000` · LiteLLM: `http://localhost:4000` ·
Orchestrator health: `http://localhost:8089/healthz`.

## 12. Что должен сделать новый чат первым

1. прочитать канон из раздела 4 (начать с `README.md` → `ROADMAP.md`
   раздел 0.4 → раздел 0.5 → раздел 0.6);
2. свериться с `docs/LIVE_SMOKE.md` — что уже прогнано вживую;
3. прогнать `uv run pytest -q` в `apps/orchestrator/` (ожидается 261 passed);
4. только потом брать в работу следующий приоритет — **шаг из victory
   plan (раздел 0.4), а не «что захочу»**;
5. при любой обрезке wow-компонента — сразу обновлять соответствующий
   ряд в `FEATURE_MATRIX.md` и kill switch лог в `LIVE_SMOKE.md`.

## 13. Короткая формула проекта

**GPTHub Prod — это единый AI workspace на Open WebUI, где orchestrator
в одном chat flow собирает mixed input (текст/PDF/TXT/MD/код/URL/image/audio),
маршрутизирует в MWS через LiteLLM alias chain, самостоятельно генерирует
изображения через `qwen-image`, и возвращает один целостный ответ с полным
trace routing-решений в `X-GPTHub-Trace`.**
