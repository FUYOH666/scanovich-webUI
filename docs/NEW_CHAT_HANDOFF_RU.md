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
| 1 | Текстовый чат | Implemented (код + тесты; нужен live docker smoke) |
| 2 | Голосовой чат | Implemented (UI-managed STT/TTS Open WebUI) |
| 3 | Генерация изображений | **Implemented** (`image_gen.py` → MWS `qwen-image`) |
| 4 | Аудио + ASR | **Implemented** (ASR fallback → MWS `whisper-medium`) |
| 5 | Изображения (VLM) | Implemented (код + тесты; нужен live smoke) |
| 6 | Файлы | **Implemented** (PDF + TXT/MD/JSON/code ≈30 расширений) |
| 7 | Поиск в интернете | `[ ]` включить Tavily в Open WebUI env |
| 8 | Веб-парсинг URL | **Implemented** (`ingest/url_fetch.py`, SSRF, 12 тестов) |
| 9 | Долгосрочная память | **Implemented** (SQLite + `qwen3-embedding-8b`, commands «запомни / забудь / что ты помнишь») |
| 10 | Автовыбор модели | Implemented |
| 11 | Ручной выбор модели | Implemented (нужен демо-режим с dropdown) |
| 12 | Markdown / код | Implemented |

**182 unit/integration теста проходят** (`apps/orchestrator`).

### 3.2. Доп. ряды 13–15 (wow + trace)

- Row 13 **Expert Council** (WOW-1): **Implemented** в `main` (`9393d30`) —
  `council.py`, fan-out + synthesis, журнал `docs/LIVE_SMOKE.md` 2026-04-11
  (ручной council + полный `demo.sh` без `--skip-wow`).
- Row 14 **PPTX generation** (wow-3): `python-pptx` + классификатор на
  триггеры «сделай презентацию».
- Row 15 **X-GPTHub-Trace** уже есть — подсвечиваем на защите.

### 3.3. Готовность к сдаче

- `[x]` MWS контракты проверены напрямую (`docs/MWS_CATALOG.md`):
  text (`mws-gpt-alpha`), image (`qwen-image`), whisper (`whisper-medium`),
  embeddings (`qwen3-embedding-8b`, dim 4096).
- `[x]` `FEATURE_MATRIX.md` синхронизирован.
- `[ ]` Docker stack не поднят для полного E2E (требует остановки v3-стека).
- `[ ]` Архитектурная диаграмма PNG/SVG.
- `[ ]` Demo-видео 2–3 минуты.
- `[ ]` `GPTHub шаблон фич.xlsx` не заполнен.
- `[ ]` Презентация.

## 4. Что считается каноном

Если нужно быстро понять проект, читать в таком порядке:

1. `README.md`
2. `ARCHITECTURE.md`
3. `ROADMAP.md` (содержит рабочий трекер в разделе 0)
4. `FEATURE_MATRIX.md`
5. `docs/MWS_CATALOG.md` (живой snapshot моделей MWS)
6. `docs/PROMPT_PRECEDENCE.md`
7. `docs/WEBUI_PAYLOAD.md`
8. `docs/TEAM_BRIEF_RU.md`
9. `CHANGELOG.md`

Если какой-то новый документ начнёт противоречить этим файлам — править
нужно канон, а не плодить вторую правду.

## 5. Что уже реализовано в коде

### 5.1. Spine

- `apps/orchestrator/` — FastAPI runtime, 101 unit/integration тест;
- `apps/embedding_shim/` — optional RAG-профиль;
- `infra/docker-compose.yml` — единый запуск; `.env.mws.local` теперь
  прокидывается **и в orchestrator** (раньше только в litellm);
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
- `settings.py` — новые поля `mws_gpt_api_*`, `ingest_url_*`, `image_gen_*`,
  `memory_*` (включая `memory_db_path`, `memory_embedding_model`,
  `memory_retrieval_top_k`, `memory_retrieval_min_score`).
- `main.py` — lifespan поднимает `MemoryStore`; добавлены два новых
  вмешательства в pipeline: (1) memory-command short-circuit сразу после
  ingest и до image-gen, (2) retrieval-injection top-K фактов как
  system-блок перед применением role prompt.

### 5.3. Что ещё не написано

- PPTX (row 14, wow-3): `python-pptx` dep + slide plan generator.
- Web search env-тумблер (row 7).
- Демо-режим «все алиасы в dropdown» для row 11.

## 6. Текущий приоритет работ

**Правильный порядок переставлен: baseline раньше wow.** Полная раскладка —
`ROADMAP.md` раздел 0.4 (victory plan) и 0.5 (kill switches).

1. **Шаг 1 — Live docker smoke** (box: 3 ч). Остановить v3-стек, поднять
   prod стек, проверить `/healthz` + `/readyz`, записать в
   `docs/LIVE_SMOKE.md`, git tag `smoke-green`. **Это приоритет #1.**
2. **Шаг 2 — Полный P0 smoke** (box: 2 ч). Прогнать все 12 рядов вживую
   через WebUI / `scripts/demo.sh`, зафиксировать тайминги.
3. **Шаг 3 — Submission артефакты** (box: 4 ч, параллельно). Заполнить
   `GPTHub шаблон фич.xlsx`, нарисовать архитектурную диаграмму, собрать
   скелет слайдов.
4. **Шаг 4 — Row 7 Tavily toggle** (box: 30 мин). env-флаг + пересборка
   open-webui контейнера.
5. **Шаг 5 — WOW-1 Expert Council** — **готово** в `main` (`9393d30`).
6. **Шаг 6 — Репетиция демо-сценария** (box: 1 ч). Реальный прогон,
   не запись.
7. **Шаг 7 — WOW-3 PPTX** (box: 4 ч, **условный** — только если осталось
   время до дедлайна). Иначе выбрасываем без сожалений.
8. **Шаг 8 — Запись demo-видео** (box: 1 ч, 2–3 дубля).
9. **Шаг 9 — Финальная сверка + git tag `demo-ready`**.

Ключевое правило: **wow без baseline = ноль**. Если выбор между
«довести wow» и «сохранить baseline» — всегда сохраняем baseline.

## 7. Путь к победе

Короткая формула: **зелёный baseline раньше синих wow**.

1. подтверждённый MWS baseline (✅ контракты проверены);
2. **все 12 обязательных рядов закрыты** (осталось row 7 Tavily env-toggle);
3. **живой docker smoke** (пока не сделан — приоритет #1);
4. `docs/LIVE_SMOKE.md` с ≥ 12 зафиксированных прогонов (журнал наблюдений);
5. один цельный демо-сценарий на 2–3 минуты (сначала репетиция, потом запись);
6. wow-дифференциация: mixed input + (условно) Expert Council + (условно) PPTX;
7. `X-GPTHub-Trace` как «production-grade» аргумент защиты;
8. упаковка в demo-video + feature matrix + architecture + presentation;
9. git tag `demo-ready` — точка заморозки.

Условия выбрасывания wow-компонентов — см. `ROADMAP.md` раздел 0.5
(kill switches).

## 8. Активные рабочие треки

- **Трек A (code):** WOW-1 Council **влит в `main`** (`9393d30`) → row 7
  Tavily toggle → (условно) WOW-3 PPTX в ветке `wow/pptx`.
  Правило: следующие wow-ветки в `main` только после зелёного прогона.
- **Трек B (infra/smoke):** шаг 1 docker smoke → шаг 2 полный P0 →
  шаг 6 репетиция → шаг 8 запись видео.
- **Трек C (submission):** шаг 3 артефакты (xlsx + диаграмма + скелет
  слайдов) → финализация слайдов после репетиции → шаг 9 сверка +
  git tag `demo-ready`.

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
uv run pytest -q     # ожидается 182 passed
```

Open WebUI: `http://localhost:3000` · LiteLLM: `http://localhost:4000` ·
Orchestrator health: `http://localhost:8089/healthz`.

## 12. Что должен сделать новый чат первым

1. прочитать канон из раздела 4 (начать с `README.md` → `ROADMAP.md`
   раздел 0.4 → раздел 0.5 → раздел 0.6);
2. свериться с `docs/LIVE_SMOKE.md` — что уже прогнано вживую;
3. прогнать `uv run pytest -q` в `apps/orchestrator/` (ожидается 182 passed);
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
