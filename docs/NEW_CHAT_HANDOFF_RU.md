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
| 1 | Текстовый чат | **Implemented** (код + тесты; `demo.sh` PASS — см. `LIVE_SMOKE.md` 2026-04-11) |
| 2 | Голосовой чат | Implemented (UI-managed STT/TTS; нужен живой micro-демо) |
| 3 | Генерация изображений | **Implemented** (`image_gen.py` → MWS `qwen-image`; live PASS в `demo.sh`) |
| 4 | Аудио + ASR | **Implemented** (ASR → MWS `whisper-medium`; нужен live `.wav` upload) |
| 5 | Изображения (VLM) | Implemented (код + тесты; нужен live smoke с фото) |
| 6 | Файлы | **Implemented** (PDF + rich formats через markitdown + plain text, примерно 30 расширений); **fix 2026-04-12:** `BYPASS_EMBEDDING_AND_RETRIEVAL=true` против краша WebUI на PDF — см. `LIVE_SMOKE.md` |
| 7 | Поиск в интернете | **Implemented** (`ENABLE_WEB_SEARCH` + Tavily + при необходимости **`BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL`**; панель Sources может расходиться с ответом — см. `LIVE_SMOKE.md`, `ROADMAP.md` шаг 4) |
| 8 | Веб-парсинг URL | **Implemented** (`ingest/url_fetch.py`, SSRF, 12 тестов; live PASS в `demo.sh`) |
| 9 | Долгосрочная память | **Implemented** (SQLite + `qwen3-embedding-8b`; live PASS в `demo.sh`; см. ReadTimeout в `LIVE_SMOKE.md`) |
| 10 | Автовыбор модели | **Implemented** (live trace в `demo.sh`; реестр v1 — `model_roles.yaml`) |

| 11 | Ручной выбор модели | Implemented (нужен демо-режим с dropdown) |
| 12 | Markdown / код | Implemented |

**226+ unit/integration тестов проходят** (`apps/orchestrator`, `uv run pytest -q`).

### 3.2. Доп. ряды 13–15 (wow + trace)

- Row 13 **Expert Council** (WOW-1): **Implemented** в `main` (`9393d30`) —
  `council.py`, fan-out + synthesis, **29** unit-тестов; защитные слои: branch-timeout /
  min-branches / `merge_reasoning_exclude_into_body` + CoT-strip / CoT-dump heuristic →
  emergency composite. Журнал `docs/LIVE_SMOKE.md` 2026-04-11 (council + полный `demo.sh` без `--skip-wow`).
- Row 14 **PPTX** (WOW-3): **Implemented** — пакет `gpthub_orchestrator/pptx/`,
  `task_type=pptx`, router `pptx_slide_plan_json*`, план (parallel slide agents
  или монолит + retry), CoT/thinking stripping, `python-pptx`, ответ с markdown + **`GET /artifacts/pptx/{id}?token=…`**.
  **36** тестов (`test_pptx_module.py`, `test_classifier_pptx.py`, `test_main_pptx_short_circuit.py`); live 2026-04-12 — `LIVE_SMOKE.md`.
- Row 15 **X-GPTHub-Trace** уже есть — подсвечиваем на защите.


### 3.3. Готовность к сдаче

- `[x]` MWS контракты проверены напрямую (`docs/MWS_CATALOG.md`):
  text (`mws-gpt-alpha`), image (`qwen-image`), whisper (`whisper-medium`),
  embeddings (`qwen3-embedding-8b`, dim 4096).
- `[x]` `FEATURE_MATRIX.md` синхронизирован (Row 13 = WOW-1, Row 14 = WOW-3).
- `[x]` v3-стек остановлен при необходимости; prod compose поднят, сервисы `Healthy` (см. `LIVE_SMOKE.md`).
- `[x]` `scripts/demo.sh` (без `--skip-wow`) — **PASS=12 FAIL=0**; **WARN**
  только если эвристики шагов 8–9 не находят council/PPTX в теле ответа
  (перезапустить после деплоя WOW-3).
- `[x]` `docs/LIVE_SMOKE.md` ведётся: council + PPTX + PDF/E2E (2026-04-11/12).
- `[x]` `docs/submission/` — исходники артефактов (см. репозиторий); xlsx/diagram/slides по мере финализации.
- `[ ]` Архитектурная диаграмма PNG/SVG (исходники есть).
- `[ ]` Demo-видео 2–3 минуты — шаг 8.
- `[ ]` Финальная презентация (есть `SLIDES_SKELETON.md` или аналог).
- `[ ]` git tag `demo-ready` — шаг 9.


## 4. Что считается каноном

Если нужно быстро понять проект, читать в таком порядке:

1. `README.md`
2. `ARCHITECTURE.md`
3. `ROADMAP.md` (содержит рабочий трекер в разделе 0)
4. `FEATURE_MATRIX.md`
5. `docs/MWS_CATALOG.md` (живой snapshot моделей MWS)
6. `docs/MODEL_ROUTING_POLICY.md` (**политика маршрутизации**: baseline vs реестр ролей `version: 1`, роли → алиасы)
7. `docs/PROMPT_PRECEDENCE.md`
8. `docs/WEBUI_PAYLOAD.md`
9. `docs/TEAM_BRIEF_RU.md`
10. `CHANGELOG.md`

Если какой-то новый документ начнёт противоречить этим файлам — править
нужно канон, а не плодить вторую правду.

## 5. Что уже реализовано в коде

### 5.1. Spine

- `apps/orchestrator/` — FastAPI runtime, **226+** unit/integration тестов;
- `apps/embedding_shim/` — optional RAG-профиль (в prod compose обычно не на критическом пути);
- `infra/docker-compose.yml` — единый запуск; `.env.mws.local` прокидывается
  **и в orchestrator** (раньше только в litellm);

- `infra/litellm/config.yaml` — alias map сверена с живым каталогом MWS.

### 5.2. Новые модули за текущую фазу работ

- `ingest/url_fetch.py` — URL detect + fetch + HTML→text + SSRF-защита
  (блок private IP до и после редиректов, content-type whitelist,
  size/timeout caps, без внешних зависимостей).
- `image_gen.py` — intent detection (RU/EN/slash-command), вызов MWS
  `/images/generations`, OpenAI-compatible ответ (json + stream) с inline
  `![](url)`, fall-through в обычный chat при ошибке.
- `memory/` — новый пакет для row 9:
  - `store.py` — thread-safe SQLite store, упаковка float32-эмбеддингов
    в BLOB, cosine-ranking в памяти, изоляция по `user_id`.
  - `commands.py` — чистый парсер команд «запомни / забудь / forget_all /
    что ты помнишь» (RU + EN + `/remember`, `/forget`, `/memories`).
  - `embeddings.py` — прямой клиент MWS `POST /v1/embeddings` с моделью
    `qwen3-embedding-8b` (dim 4096), без LiteLLM.
  - `service.py` — высокоуровневое API: `try_parse_command`,
    `execute_memory_command`, `retrieve_memory_context`,
    `build_memory_system_message`, SSE-чанки для short-circuit.
- `Settings.resolved_asr_base_url()` / `resolved_asr_api_key()` —
  orchestrator-level MWS credentials + автоматический fallback ASR на них.
- `ingest/pipeline.py` — теперь обрабатывает PDF + audio + plain-text
  (≈30 расширений) + URL параллельными задачами.
- `settings.py` — поля `mws_gpt_api_*`, `ingest_url_*`, `image_gen_*`,
  `memory_*`, `council_*` (включая `council_branch_timeout_seconds`,
  `council_synthesis_timeout_seconds`, `council_expert_*`,
  `council_synthesis_model`, `council_min_branches_for_synthesis`), `pptx_*`.
- **`gpthub_orchestrator/pptx/`** (row 14 WOW-3): план слайдов, сборка дека,
  артефакты, URL **`GET /artifacts/pptx/{id}?token=…`**, см. `settings.pptx_*`.
- `main.py` — lifespan поднимает `MemoryStore`; short-circuit порядок после
  classify: memory-command → council → **image-gen** → **pptx** (`pptx_gen_enabled`,
  `task_type=pptx`) → greeting → обычный chat; перед role prompt — retrieval-injection
  top-K фактов памяти.
- `classifier.py` — `TaskType.DEEP_RESEARCH`, `TaskType.PPTX` (и триггеры RU/EN + `/pptx`).


### 5.3. Что ещё не написано / мелочи

- Web search env-тумблер (row 7) — в Open WebUI.
- Демо-режим «все алиасы в dropdown» для row 11.

## 6. Текущий приоритет работ

**Правильный порядок переставлен: baseline раньше wow.** Полная раскладка —
`ROADMAP.md` раздел 0.4 (victory plan) и 0.5 (kill switches).

- ✅ **Шаг 1 — Live docker smoke** — закрыт, tag `smoke-green` (см. журнал).
- ✅ **Шаг 2 — полный P0 smoke** — `demo.sh` **PASS=12 FAIL=0** (WARN см. вывод скрипта).
- **Шаг 3 — Submission артефакты** — черновики; финализация после шага 6.
- ✅ **Шаг 4 — Row 7 Tavily toggle** — env в `.env` / `.env.example`.
- ✅ **Шаг 5 — WOW-1 Expert Council** — в `main` (`9393d30`).
- **Шаг 6 — оператор + репетиция** (1 ч, оператор в WebUI).
- ✅ **Шаг 7 — WOW-3 PPTX** — пакет `gpthub_orchestrator/pptx/`, **226+** тестов всего suite; live 2026-04-12.
- **Шаг 8 — запись demo-видео** (1 ч, 2–3 дубля).
- **Шаг 9 — финальная сверка + git tag `demo-ready`**.


Ключевое правило: **wow без baseline = ноль**. Если выбор между
«довести wow» и «сохранить baseline» — всегда сохраняем baseline.

## 7. Путь к победе

Короткая формула: **зелёный baseline раньше синих wow**.

1. ✅ подтверждённый MWS baseline (контракты проверены);
2. ✅ **все 12 обязательных рядов закрыты кодом**; Row 7 — env-флаг + per-chat toggle в WebUI;
3. ✅ **живой docker smoke** (`demo.sh` без `--skip-wow` — **PASS=12 FAIL=0**);
4. `docs/LIVE_SMOKE.md` ведётся; для чек-листа накопить операторские прогоны (шаг 6);
5. один цельный демо-сценарий на 2–3 минуты (репетиция → запись видео);
6. ✅ wow-1: Expert Council; ✅ wow-3: PPTX в `main` (`pptx/` + artifacts), live 2026-04-12;
7. ✅ `X-GPTHub-Trace` как «production-grade» аргумент защиты;
8. упаковка в demo-video + feature matrix + architecture + presentation;
9. git tag `demo-ready` — точка заморозки.


Условия выбрасывания wow-компонентов — см. `ROADMAP.md` раздел 0.5
(kill switches).

## 8. Активные рабочие треки

- **Трек A (code):** ✅ WOW-1 Council + ✅ WOW-3 PPTX в `main` (`pptx/`). Row 7 — env готов.
  Правило: wow в `main` только после зелёного прогона.
- **Трек B (infra/smoke):** ✅ шаг 1 docker smoke → ✅ шаг 2 полный P0
  через `demo.sh` → шаг 6 репетиция (оператор в WebUI) → шаг 8 запись видео.
- **Трек C (submission):** шаг 3 артефакты (черновики в `docs/submission/` при наличии) → финализация слайдов после
  репетиции → шаг 9 сверка + git tag `demo-ready`.


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
  image-gen + pptx short-circuits, memory, council fan-out);
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
uv run pytest -q     # ожидается 226+ passed
```

Open WebUI: `http://localhost:3000` · LiteLLM: `http://localhost:4000` ·
Orchestrator health: `http://localhost:8089/healthz`.

## 12. Что должен сделать новый чат первым

1. прочитать канон из раздела 4 (начать с `README.md` → `ROADMAP.md`
   раздел 0.4 → раздел 0.5 → раздел 0.6);
2. свериться с `docs/LIVE_SMOKE.md` — что уже прогнано вживую;
3. прогнать `uv run pytest -q` в `apps/orchestrator/` (ожидается 226+ passed);
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
