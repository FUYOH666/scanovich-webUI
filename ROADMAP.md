# Дорожная карта GPTHub Prod — «до победного»

> Этот документ — единый источник правды о том, **что мы делаем
> дальше, в каком порядке, и при каких условиях мы что-то выкидываем**.
> Если что-то в репозитории противоречит этому файлу — правим канон.

## 0. Рабочий трекер

Обозначения: `[ ]` не начато, `[~]` в работе, `[x]` готово.

### 0.1. Обязательный чеклист организаторов (ряды 1–12)

| № | Фича | Путь реализации | Статус |
|---|---|---|---|
| 1 | Текстовый чат | WebUI → orchestrator → LiteLLM `gpt-hub-turbo/strong` → MWS `mws-gpt-alpha`/`glm-4.6-357b` | `[x]` код + тесты + **live `demo.sh` 2026-04-11** |
| 2 | Голосовой чат | STT/TTS Open WebUI → тот же orchestrator-путь | `[x]` UI-managed, `[ ]` operator live прогон |
| 3 | Генерация изображений | `image_gen.py` → MWS `/images/generations` (`qwen-image`) → inline `![](url)` | `[x]` + **live `demo.sh`** |
| 4 | Аудио + ASR | `Settings.resolved_asr_*()` → MWS `whisper-medium` | `[x]` код, `[ ]` operator live `.wav` upload |
| 5 | Изображения (VLM) | Role `vision` → alias chain → MWS multimodal | `[x]` код, `[ ]` operator live photo upload |
| 6 | Файлы (PDF/TXT/MD/JSON/code) | `ingest/pipeline.py` (PDF + ~30 text extensions); WebUI с `BYPASS_EMBEDDING_AND_RETRIEVAL=true` | `[x]` код, `[~]` ждём operator retry после fix 2026-04-12 (PDF upload крашился из-за WebUI RAG, fix `0d48f26`) |
| 7 | Поиск в интернете | Open WebUI + Tavily env toggle | `[x]` env vars in `.env` + container confirmed; UI-managed |
| 8 | Веб-парсинг по ссылке | `ingest/url_fetch.py` (SSRF + лимиты) | `[x]` + **live `demo.sh`** |
| 9 | Долгосрочная память | `memory/` (SQLite + `qwen3-embedding-8b` + command parser) | `[x]` + **live `demo.sh`** |
| 10 | Автовыбор модели | `classifier.py` → `router.py` → alias chain | `[x]` + **live trace в `demo.sh`** |
| 11 | Ручной выбор модели | `ORCHESTRATOR_MODELS_CATALOG=all` + `AUTO_ROUTE_MODEL=false` | `[x]` код, `[ ]` демо-режим с dropdown |
| 12 | Markdown / код | OpenAI-совместимый ответ, WebUI рендерит штатно | `[x]` |

### 0.2. Дополнительные фичи (ряды 13–15)

| № | Фича | Путь | Статус |
|---|---|---|---|
| 13 | Deep Research = **Expert Council** | `task_type=DEEP_RESEARCH` → fan-out в `strong` + `reasoning` + `doc` → synthesis через `strong` → один chat.completion наружу, все вызовы видны в `X-GPTHub-Trace` | `[x]` WOW-1: влито в `main` (`9393d30`), live + полный `demo.sh` — `docs/LIVE_SMOKE.md` 2026-04-11 |
| 14 | Генерация презентаций | `task_type=PPTX_GENERATION` → `pptx_gen.py`: JSON slide plan via `gpt-hub-strong` (retry) → `python-pptx` → download link `GET /v1/files/pptx/{token}` | `[x]` WOW-3: 56 тестов, **live PASS 2026-04-12**, FEATURE_MATRIX → `Implemented (WOW-3)` |
| 15 | `X-GPTHub-Trace` | Production-grade наблюдаемость routing/fallback/ingest | `[x]` |

### 0.3. Scope lock и non-goals

Жёсткое правило: **один chat flow → один запрос → один ответ → один trace**.
Любая фича, которая заставляет пользователя переключать режим — non-goal.

Все три wow уважают scope lock:

- **Expert Council** делает fan-out **внутри** orchestrator. Пользователь
  отправляет один запрос и получает один ответ; fan-out виден только в
  `X-GPTHub-Trace`.
- **PPTX gen** — это ещё один ответ в том же чате с inline-файлом.
- **X-GPTHub-Trace** — уже есть, «продаём» на защите.

Non-goals до самого конца:

- второй flagship UX-режим / отдельный UI;
- агентные tool-calls в стиле langchain;
- кастомный frontend;
- «красота» в ущерб живому P0.

---

## 0.4. Новый порядок работ (победный план)

Это **перестроенный** порядок по принципу «зелёный baseline раньше синих wow».
Каждый пункт имеет box времени и явный kill switch.

> **Снимок прогресса на 2026-04-12 (обновлено):**
> - ✅ Step 1 (live docker smoke) — закрыт; tag `smoke-green`.
> - ✅ Step 2 (полный P0 smoke через `demo.sh` без `--skip-wow`) — **PASS=12 FAIL=0**; WARN только soft-path шагов 8–9 (council/PPTX в теле ответа). WARN=1 из‑за PPTX **до** WOW-3 — устарело. Остаётся ручной WebUI-проход (Step 6).
> - 🟡 Step 3 (submission артефакты) — черновики готовы; xlsx пересобран. Финализация — после Step 6.
> - ✅ Step 4 (Row 7 Tavily toggle) — env vars в `.env` + container verified.
> - ✅ Step 5 (WOW-1 Expert Council) — закрыт; merge `9393d30` в `main`.
> - 🔜 Step 6 (operator-сценарии + репетиция) — требует оператора в WebUI.
> - ✅ Step 7 (WOW-3 PPTX) — код + 57 тестов в `test_pptx_gen.py` + YAML alias test; **261** тест total. **Live PASS 2026-04-12**: 7-slide deck, 35 KB, download OK. CoT `<think>` stripping fix applied.
> - 🔜 Step 8 (запись видео) — оператор.
> - 🔜 Step 9 (финальная сверка + git tag `demo-ready`).
>
> **Hot-fix 2026-04-12 #1:** Row 6 PDF upload крашился в WebUI с
> `'NoneType' encode` (WebUI пытался свой RAG-эмбеддинг). Применили
> `BYPASS_EMBEDDING_AND_RETRIEVAL=true` (commit `0d48f26`).
>
> **Hot-fix 2026-04-12 #2:** PPTX plan JSON parsing failed because MWS
> `gpt-hub-strong` (glm-4.6) returns `<think>…</think>` CoT blocks
> before JSON. Added `_strip_cot_blocks()` + broadened intent patterns
> («в формате pptx»). Live PPTX confirmed working.

### Шаг 1 — Live docker smoke (приоритет #1, box: 3 часа) — ✅ ЗАКРЫТО

**Почему первый:** у нас **261** unit/integration тестов в orchestrator;
подтверждение compose и части сценариев уже в `docs/LIVE_SMOKE.md` (в т.ч.
тег `smoke-green` и прогоны 2026-04-11). Оставшийся риск — полный P0/WebUI
чеклист без пробелов.

Что делаем:

1. Остановить v3-стек: `docker rm -f gpthub-v3-orchestrator gpthub-v3-embedding-shim gpthub-v3-open-webui gpthub-v3-litellm`.
2. Проверить `.env` и `.env.mws.local` (ключи на месте).
3. `docker compose -f infra/docker-compose.yml up -d --build`.
4. Проверить `/healthz`, `/readyz`, `GET /v1/models` (orchestrator 8089, LiteLLM 4000, WebUI 3000).
5. Три живых запроса через WebUI: текст, PDF + вопрос, «нарисуй кота».
6. **Записать результаты в `docs/LIVE_SMOKE.md`** с таймингами.
7. Git commit + tag `smoke-green`.

**Kill switch:** если за 3 часа стек не поднят — триаж, а не упорство.
Эскалировать в чат, получить решение «откатываем до минимального стека
без RAG-профиля» или «меняем порты».

**Definition of done шага 1:**
- `[x]` `docker compose ps` показывает все сервисы `running`
- `[x]` `curl http://localhost:8089/healthz` → `{"status":"ok"}`
- `[x]` `curl http://localhost:8089/readyz` → `{"status":"ready"}`
- `[x]` WebUI на `localhost:3000` открывается, видит модель `gpt-hub`
- `[x]` Сценарии прогнаны вживую и записаны в `LIVE_SMOKE.md`
- `[x]` git tag `smoke-green` проставлен

### Шаг 2 — Полный P0 smoke сценарий (box: 2 часа) — ✅ В ОСНОВНОМ ЗАКРЫТО

Прогоняем **все 12 рядов** вживую через WebUI и/или `scripts/demo.sh`:

1. ✅ текст → `mws-gpt-alpha` (`demo.sh` step 3)
2. 🔜 голос → STT → текст → тот же путь (operator, WebUI mic)
3. ✅ «нарисуй кота» → `qwen-image` → inline markdown (`demo.sh` step 5)
4. 🔜 загрузить .wav → ASR → текст в system → ответ (operator, WebUI upload)
5. 🔜 загрузить фото → VLM route → `qwen3-vl` (operator, WebUI upload)
6. 🟡 загрузить .py + .md + .pdf → ingest → ответ по содержимому
   (operator retry после fix `0d48f26` 2026-04-12)
7. 🔜 (после Step 4 Tavily) — `{{search}} последние новости MWS`
8. ✅ `прочитай https://example.com` → `url_fetch` → summary (`demo.sh` step 4)
9. ✅ «запомни, что я пью эспрессо» → recall later (`demo.sh` step 6)
10. ✅ classifier выбрал верную роль, видно в trace (`demo.sh` step 7)
11. 🔜 переключить `AUTO_ROUTE_MODEL=false`, выбрать вручную (operator)
12. ✅ markdown + код в ответе (rendered в WebUI; формально ловится через trace)

Каждый пункт фиксируется в `LIVE_SMOKE.md` с таймингом и моделью.

**Текущее состояние:** автоматизированная часть закрыта `scripts/demo.sh`
без `--skip-wow` — **PASS=12 FAIL=0**; **WARN=0** после деплоя WOW-3 PPTX,
если council и PPTX проходят эвристики шагов 8–9 (иначе см. вывод скрипта).
Остаются операторские сценарии (Row 2, 4, 5, 11) — отдаются Step 6
(репетиция).

**Kill switch:** если какой-то ряд падает — баг фикс box 30 минут. Если
не чиним за 30 минут → честно помечаем `Partial` в `FEATURE_MATRIX.md`
и едем дальше.

### Шаг 3 — Submission артефакты (box: 4 часа, параллельно) — 🟡 ЧЕРНОВИКИ ГОТОВЫ

Этот шаг **может идти параллельно** с шагом 1–2, если есть второй человек.
Не требует рабочего стека.

1. ✅ `GPTHub шаблон фич.xlsx` — собран из `FEATURE_MATRIX.md` через
   `scripts/build_features_xlsx.py` (`docs/submission/GPTHub_features_matrix.xlsx`).
   Перегенерировать после Row 13 / Step 7.
2. ✅ Архитектурная диаграмма исходники: `docs/submission/architecture.mmd`
   (Mermaid) + `docs/submission/gpthub-architecture.excalidraw`.
   `[ ]` Финальный экспорт PNG/SVG — Step 9.
3. ✅ Скелет слайдов: `docs/submission/SLIDES_SKELETON.md`
   (5–7 слайдов: problem, architecture, mixed input, wow, demo,
   trade-offs, ask). `[ ]` Финальная вёрстка слайдов — Step 9.

**Kill switch:** слайды и диаграмма — это «пол». Видео записываем в шаге
8 уже на готовом стеке.

### Шаг 4 — Row 7 Tavily toggle (box: 30 минут) — ✅ ЗАКРЫТО

**Статус (2026-04-12):** закрыто. Env vars в `.env` + `.env.example`.
WebUI admin подтверждает: Tavily ON, 2 results, basic depth.
Примечание: web search в Open WebUI v0.8 — **per-chat toggle** (иконка
глобуса в строке ввода); admin-настройка делает фичу доступной, но
пользователь активирует её в каждом чате отдельно.

1. Добавить в `.env.example` и `infra/docker-compose.yml` (open-webui):
   ```
   ENABLE_WEB_SEARCH=true
   WEB_SEARCH_ENGINE=tavily
   TAVILY_API_KEY=...
   ```
2. Пересобрать только контейнер WebUI: `docker compose up -d --force-recreate open-webui`.
3. Проверить через WebUI: кнопка «web search» появилась, запрос возвращает
   результаты.
4. Записать в `LIVE_SMOKE.md` и обновить row 7 в `FEATURE_MATRIX.md`.

### Шаг 5 — WOW-1 Expert Council (box: 6 часов, жёсткий) — ✅ ЗАКРЫТО

**Статус (2026-04):** выполнено и влито в `main` (merge `9393d30`).
Реализация: `council.py`, short-circuit в `main.py`, `DEEP_RESEARCH` в
`classifier.py`, 29 тестов в `tests/test_council.py`; живые прогоны —
`docs/LIVE_SMOKE.md` (11:32 council, 11:46 полный `demo.sh`).

Ниже — исходный дизайн и kill switch (архив постмортема; после успешного
мержа к откату не призываем).

**Это был самый рискованный компонент.** Kill switch оставлен для истории.

Дизайн:

1. В `classifier.py` добавить `task_type=DEEP_RESEARCH` с триггерами:
   «исследуй подробно», «глубокое исследование», «/research», «deep research», «council».
2. Новый модуль `apps/orchestrator/gpthub_orchestrator/council.py`:
   - `council_fan_out(http, settings, messages, trace_sink) -> str`
   - Параллельно через `asyncio.gather` три запроса в LiteLLM с разными
     role prompts: `strong` (главный), `reasoning` (логика/числа), `doc`
     (факты/документы). У каждого свой system.
   - Таймаут на ветку — 60 секунд. Если ветка упала — не блокируем
     синтез, только помечаем в trace.
   - Минимум 2 из 3 ответов должны прийти, иначе `fallback` в обычный
     путь `strong`.
3. Synthesis: ещё один вызов `strong` с промптом «вот три экспертных
   мнения — собери один аргументированный ответ, указывая где эксперты
   сошлись/разошлись».
4. В `main.py` — short-circuit после classifier, если task_type == DEEP_RESEARCH.
5. Все вызовы (3 эксперта + 1 синтез) логируются в `X-GPTHub-Trace`
   как массив `council_attempts`.
6. Тесты: mock три LiteLLM ответа, проверить synthesis шаг, проверить
   fallback при падении одной ветки.

**Жёсткий kill switch:**
- Если за 6 часов нет зелёного end-to-end через WebUI — **выбрасываем**.
  `git reset --hard smoke-green` на ветке main, ветку `wow/expert-council`
  оставляем как «backlog».
- Если synthesis промпт стабильно даёт плохой результат — **выбрасываем**.
  Лучше честно не показать Council, чем показать «три эксперта, и каша
  на выходе».

**Правило гигиены (выполнено):** разработка шла в ветке `wow/expert-council`;
в `main` влито после зелёного end-to-end (в т.ч. `scripts/demo.sh` без
`--skip-wow`, см. журнал).

### Шаг 6 — Репетиция демо-сценария (box: 1 час) — 🔜 СЛЕДУЮЩИЙ (требует оператора)

После шагов 1–5 делаем **реальный прогон** сценария из раздела «Demo
Lock» ниже. Это **не запись**, а именно репетиция.

Что проверяем:
- все переходы отрабатывают на одном стеке без ручных вмешательств;
- markdown рендерится в WebUI корректно;
- `X-GPTHub-Trace` виден в DevTools → Network → Headers;
- сценарий укладывается в 2–3 минуты без резких пауз.

Баги из репетиции → box 30 минут на фикс, либо обрезаем сценарий.

**Kill switch:** если сценарий не прогоняется вживую — упрощаем до
минимума (3 шага вместо 6) и делаем так, чтобы минимум прогонялся.

### Шаг 7 — WOW-3 PPTX generation (box: 4 часа, условный) — ✅ ЗАКРЫТО

**Статус (2026-04-12):** реализовано, live подтверждено. `pptx_gen.py` +
56 тестов. Hot-fix: `<think>` CoT stripping для MWS glm-4.6; broadened
intent patterns. Live 2026-04-12: 7-slide deck, 35 KB, download endpoint OK.

Дизайн:

1. В `pyproject.toml` добавить `python-pptx`.
2. В `classifier.py` добавить `task_type=PPTX` с триггерами «сделай
   презентацию», «build deck», «/pptx», «презентация по этому».
3. Новый `apps/orchestrator/gpthub_orchestrator/pptx_gen.py`:
   - `request_slide_plan(http, settings, messages) -> SlidePlan`
   - Strong-модель возвращает строгий JSON `{slides: [{title, bullets, notes}, ...]}`.
   - JSON-парсер с двухшаговым retry (если модель вернула что-то кроме JSON).
4. `build_pptx_from_plan(plan) -> bytes` через `python-pptx`.
5. В ответе: markdown-превью с заголовками слайдов + inline
   `[Скачать презентацию](data:application/vnd.openxmlformats-officedocument.presentationml.presentation;base64,...)`.
6. Тесты: mock JSON plan, проверить количество слайдов, проверить bytes
   валидные ZIP/pptx.

**Kill switch:** если JSON plan нестабильный или `python-pptx` не
ставится в образ за 30 минут — выбрасываем.

### Шаг 8 — Запись demo-видео (box: 1 час, 2–3 дубля) — 🔜 ОПЕРАТОР

1. Прогнать `scripts/demo.sh` один раз — всё ли зелёное.
2. Запись экрана (Loom / QuickTime / OBS) по сценарию Demo Lock.
3. Голосовой комментарий синхронно или монтаж (синхрон проще).
4. Монтаж: обрезать паузы, вставить 2–3 текстовых титра («Expert Council
   fan-out», «X-GPTHub-Trace in DevTools»).
5. Финальный рендер ≤ 3 минут.

**Правило:** если первый дубль не проходит — проблема в репетиции,
возвращаемся к шагу 6, не «прогоняем ещё разок».

### Шаг 9 — Финальная сверка и git tag `demo-ready` (box: 1 час) — 🔜 ФИНАЛ

1. `README.md`, `ROADMAP.md`, `FEATURE_MATRIX.md`, `CHANGELOG.md`,
   `docs/NEW_CHAT_HANDOFF_RU.md`, `docs/TEAM_BRIEF_RU.md` — все
   документы отражают финальное состояние.
2. `GPTHub шаблон фич.xlsx` синхронизирован с `FEATURE_MATRIX.md`.
3. Финальные слайды готовы (`docs/presentation/` или аналог).
4. `scripts/demo.sh` работает идемпотентно.
5. Видео загружено в то место, откуда будет показываться.
6. git tag `demo-ready`. **После этого тега правки только критических багов.**

---

## 0.5. Kill switches (сводка)

| Компонент | Когда выбрасываем | Что делаем вместо |
|---|---|---|
| ~~Docker smoke (шаг 1)~~ | ~~>3 часов не взлетает~~ | ✅ закрыт; tag `smoke-green` |
| Полный ряд smoke (шаг 2) | Ряд падает >30 минут | ✅ автоматический smoke зелёный; для operator-рядов — честный `Partial` если падает |
| ~~Expert Council (шаг 5)~~ | ~~>6 часов без зелёного end-to-end~~ | ✅ закрыт; merge `9393d30` в `main` |
| ~~Expert Council synthesis~~ | ~~Плохое качество synthesis~~ | ✅ closed; CoT-strip + emergency composite + glm-4.6-357b прижились |
| Repetition (шаг 6) | Сценарий не прогоняется вживую | Урезаем до 3 шагов |
| ~~PPTX (шаг 7)~~ | ~~JSON plan нестабильный~~ | ✅ закрыт; CoT strip fix + live confirmed |
| Demo video (шаг 8) | Первый дубль не проходит | Возврат к шагу 6, не «ещё разок» |

**Общее правило:** wow без baseline = ноль. Если выбор между «довести
wow» и «сохранить baseline» — всегда сохраняем baseline.

---

## 0.6. Victory readiness checklist

Это **единственный** критерий «готовы к защите». Все пункты проверяемы.

### Runtime
- `[x]` `docker compose -f infra/docker-compose.yml up -d --build` без ручных действий
- `[x]` `curl localhost:8089/healthz` → 200
- `[x]` `curl localhost:8089/readyz` → 200
- `[x]` WebUI на `localhost:3000` показывает модель `gpt-hub`

### Feature baseline (ряды 1–12)
- `[~]` все 12 рядов прогнаны вживую и записаны в `LIVE_SMOKE.md` (автоматическая часть закрыта `demo.sh`; operator-рядов 2/4/5/6/11 — Step 6)
- `[x]` каждому ряду в `FEATURE_MATRIX.md` соответствует либо `Implemented`, либо честный `Partial/Deferred`
- `[x]` `scripts/demo.sh` проходит без ошибок идемпотентно (**PASS=12 FAIL=0**; WARN только soft-fail 8–9; PPTX live с 2026-04-12)

### Differentiation
- `[~]` mixed input: один запрос с PDF + image + audio + URL даёт один ответ (компоненты в коде, операторский end-to-end — Step 6)
- `[~]` `X-GPTHub-Trace` виден в DevTools → Network → Headers для одного живого запроса (хидер выставляется во всех ответах; визуальная проверка — Step 6)
- `[~]` memory: «запомни X» → «что ты помнишь» — закрыто на curl-уровне в `demo.sh`; нужен живой WebUI-проход для слайдов
- `[x]` Expert Council (WOW-1): `/research` и аналоги — fan-out + synthesis, см. `X-GPTHub-Trace` и `docs/LIVE_SMOKE.md` 2026-04-11
- `[x]` PPTX (WOW-3): «сделай презентацию» / «в формате pptx» → скачиваемый .pptx — **live 2026-04-12**

### Submission artifacts
- `[~]` `GPTHub шаблон фич.xlsx` — есть `docs/submission/GPTHub_features_matrix.xlsx`; перегенерация после Row 13/Step 7
- `[~]` Архитектурная диаграмма — исходники `architecture.mmd` + `gpthub-architecture.excalidraw`; PNG/SVG — Step 9
- `[ ]` Demo-видео ≤ 3 минут — Step 8
- `[~]` Презентация 5–7 слайдов — `SLIDES_SKELETON.md` готов, финал — Step 9
- `[x]` `docs/LIVE_SMOKE.md` содержит журнал живых прогонов

### Docs consistency
- `[x]` `README.md`, `ROADMAP.md`, `FEATURE_MATRIX.md`, `CHANGELOG.md`, `docs/NEW_CHAT_HANDOFF_RU.md`, `docs/TEAM_BRIEF_RU.md`, `docs/MODEL_ROUTING_POLICY.md` — синхронны (261 тест, PPTX live, политика маршрутизации v2, 2026-04-12)
- `[ ]` git tag `demo-ready` проставлен — Step 9

Когда все чекбоксы зелёные — можно защищаться. Ни минутой раньше.

---

## 1. Definition of Done (высокоуровневый)

Проект считается готовым к защите, если одновременно:

- `docker compose up` на чистой машине даёт рабочий стек;
- все ряды 1–12 закрыты либо имеют честный статус в `FEATURE_MATRIX.md`;
- demo-сценарий проигрывается без «магии за кадром»;
- `X-GPTHub-Trace` показывает все решения orchestrator'а;
- видео, диаграмма, xlsx, презентация синхронизированы с кодом;
- `docs/LIVE_SMOKE.md` содержит ≥ 12 зафиксированных живых прогонов.

Всё перечисленное выше и есть раздел 0.6 (victory checklist). Если
чекбокс не зелёный — продолжаем работать, а не «ну и так сойдёт».

---

## 2. Demo Lock — единственный сценарий на защите

**Время:** 2–3 минуты. **Цель:** показать один цельный AI workspace на
`mixed input + memory + (optional) council/pptx`.

### Сценарий

1. **Mixed input (один запрос):**
   - PDF с архитектурной схемой MWS
   - фото доски со скетчем
   - голосовое описание задачи (через WebUI mic)
   - ссылка на документ MWS GPT
   - текст: «собери резюме по всем материалам и запомни, что я отвечаю
     за интеграцию MWS в наш продукт».
2. **Один ответ:** orchestrator собирает mixed input, маршрутизирует в
   `vision` / `doc` / `strong` по классификатору, возвращает один
   markdown-ответ со ссылками на источники.
3. **Memory:** следующее сообщение — «что ты обо мне помнишь?» —
   возвращается сохранённый факт об интеграции MWS.
4. **Expert Council (WOW-1, в `main`):** «проведи глубокое исследование
   по этой теме» → три эксперта внутри → один synthesis ответ.
5. **(wow-3, если есть) PPTX:** «сделай презентацию по этому разбору»
   → возвращается скачиваемый .pptx.
6. **Trace reveal:** открываем DevTools → Network → последний запрос
   → `X-GPTHub-Trace` → видно classifier, router, fallback chain,
   artifacts, council attempts. Один кадр, 10 секунд.

### Жёсткие правила

- Никакой второй «главной» фичи не конкурирует с этим сценарием.
- Порядок шагов — фиксирован. Если шаг 4 или 5 выброшен — значит
  сценарий короче, но остальное не трогаем.
- Репетиция **обязательна** до записи видео (шаг 6 плана работ).
- После git tag `demo-ready` сценарий замораживается — правки только по
  критическим багам.

---

## 3. Scope lock и non-goals

Этот репозиторий сознательно зафиксирован вокруг одного продуктового ядра:

- feature rows `1-12` — обязательный чеклист;
- одна архитектура: `Open WebUI → orchestrator → LiteLLM → MWS`;
- одна дифференциация: `mixed input` + `X-GPTHub-Trace`;
- ряды `13–15` — wow-кандидаты с kill switch'ами, не блокеры.

**Non-goals** (не трогаем до финала, даже если появится время):

- второй flagship UX-режим / отдельный UI;
- agentic tool-calls в стиле langchain;
- кастомный frontend поверх WebUI;
- оптимизации latency / cost сверх того, что дают alias chain + fallback;
- «красота» в ущерб живому P0;
- любая фича, которая заставляет пользователя переключать режимы.

---

## 4. Треки параллельной работы

Одновременно работаем по трём трекам. У каждого трека свой владелец и
свой next action.

### Трек A — Code (один человек)

1. ✅ **Шаг 5 — Expert Council** — в `main` (`9393d30`).
2. ✅ **Шаг 4 — Tavily toggle** — env + compose; см. `.env.example` и коммит `ff9d574`.
3. ✅ **Шаг 7 — PPTX (WOW-3)** — в `main` (`ff9d574`), `pptx_gen.py` + download link.
   Дальше по коду — только пост-конкурс §5; по продукту — **оператор** (шаги 6/8/9).

### Трек B — Infra / Smoke (один человек)

1. ✅ **Шаг 1 — Docker smoke** (v3 остановлен, prod поднят, tag `smoke-green`).
2. ✅ **Шаг 2 — Полный ряд smoke** через `demo.sh` без `--skip-wow`
   (**PASS=12 FAIL=0**; WARN по Row 14 PPTX **снят** после WOW-3). Operator-ряды (2/4/5/6/11)
   собираем в Step 6.
3. 🔜 **Шаг 6 — Репетиция** (требует оператора в WebUI).
4. 🔜 **Шаг 8 — Запись видео** (после Step 6).

### Трек C — Submission (один человек)

1. 🟡 **Шаг 3 — Артефакты** (xlsx + диаграмма + скелет слайдов — есть в `docs/submission/`; перегенерировать xlsx после Step 7).
2. После шага 6 — финализация слайдов с реальными скриншотами.
3. **Шаг 9 — Финальная сверка** перед `demo-ready`.

---

---

## 5. После конкурса — production roadmap (опционально)

Эти идеи **не нужны для конкурса**, но показывают зрелость мышления.
Если жюри спросит «а что дальше?» — у нас есть ответ.

### 5.1. Инфраструктура

- [ ] Persistent storage для PPTX и memory (Docker volume / S3 вместо `/tmp`).
- [ ] Auth на download-эндпоинтах (JWT или session cookie от WebUI).
- [ ] CI/CD pipeline: lint + pytest + docker build на каждый PR.
- [ ] Rate-limits на orchestrator (token bucket per user).
- [ ] Healthcheck dashboard (Grafana + Prometheus metrics из orchestrator).

### 5.2. Расширение форматов

- [x] [markitdown](https://github.com/microsoft/markitdown) — DOCX, XLSX,
  PPTX → markdown ingestion. Реализовано в `ingest/richdoc.py` (21 тестов).
- [ ] OCR fallback для сканированных PDF (Tesseract / MWS vision).

### 5.3. UX-улучшения

- [ ] Streaming PPTX preview — показать slide plan в чате как markdown
  пока `.pptx` собирается; файл прикрепляется вторым сообщением.
- [ ] Council progress indicator — SSE-обновления «эксперт 1/3 ответил…»
  во время fan-out.
- [ ] Мультиязычный TTS через MWS (синтез голоса на ответ).
- [ ] Smart model suggestion — если пользователь задаёт вопрос по коду,
  WebUI подсвечивает «для этого подойдёт reasoning-модель».

### 5.4. Аналитика и observability

- [ ] `X-GPTHub-Trace` → structured log → ClickHouse / Loki.
- [ ] Token cost tracking per user per session.
- [ ] A/B тестирование моделей (какой alias даёт лучший user satisfaction).

### 5.5. Enterprise readiness

- [ ] Multi-tenant memory isolation (сейчас — по `user_id`, но в одной
  SQLite; нужен PostgreSQL + pgvector).
- [ ] SSO / LDAP интеграция через Open WebUI.
- [ ] Audit log для compliance.

---

## 6. Как читать roadmap

- Нужен **следующий шаг прямо сейчас** — раздел 0.4 (victory plan).
- Нужны **условия обрезки** — раздел 0.5 (kill switches).
- Нужна **проверка «готовы ли» к защите** — раздел 0.6 (checklist).
- Нужен **документ для команды** — `docs/TEAM_BRIEF_RU.md`.
- Нужен **документ для нового окна чата** — `docs/NEW_CHAT_HANDOFF_RU.md`.

Если в этих файлах расхождение с `ROADMAP.md` — правим канон, а не плодим
вторую правду.
