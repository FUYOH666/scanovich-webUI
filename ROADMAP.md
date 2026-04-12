# Дорожная карта GPTHub Prod — «до победного»

> Этот документ — единый источник правды о том, **что мы делаем
> дальше, в каком порядке, и при каких условиях мы что-то выкидываем**.
> Если что-то в репозитории противоречит этому файлу — правим канон.

## 0. Рабочий трекер

Обозначения: `[ ]` не начато, `[~]` в работе, `[x]` готово.

### 0.1. Обязательный чеклист организаторов (ряды 1–12)

| № | Фича | Путь реализации | Статус |
|---|---|---|---|
| 1 | Текстовый чат | WebUI → orchestrator → LiteLLM `gpt-hub-turbo/strong` → MWS `mws-gpt-alpha`/`glm-4.6-357b` | `[x]` код + тесты, `[ ]` live docker smoke |
| 2 | Голосовой чат | STT/TTS Open WebUI → тот же orchestrator-путь | `[x]` UI-managed, `[ ]` live прогон |
| 3 | Генерация изображений | `image_gen.py` → MWS `/images/generations` (`qwen-image`) → inline `![](url)` | `[x]` |
| 4 | Аудио + ASR | `Settings.resolved_asr_*()` → MWS `whisper-medium` | `[x]` |
| 5 | Изображения (VLM) | Role `vision` → alias chain → MWS multimodal | `[x]` код, `[ ]` live smoke |
| 6 | Файлы (PDF/TXT/MD/JSON/code) | `ingest/pipeline.py` (PDF + ~30 text extensions) | `[x]` |
| 7 | Поиск в интернете | Open WebUI + Tavily env toggle | `[ ]` `ENABLE_WEB_SEARCH=true` + `TAVILY_API_KEY` |
| 8 | Веб-парсинг по ссылке | `ingest/url_fetch.py` (SSRF + лимиты) | `[x]` |
| 9 | Долгосрочная память | `memory/` (SQLite + `qwen3-embedding-8b` + command parser) | `[x]` |
| 10 | Автовыбор модели | `classifier.py` → `router.py` → alias chain | `[x]` |
| 11 | Ручной выбор модели | `ORCHESTRATOR_MODELS_CATALOG=all` + `AUTO_ROUTE_MODEL=false` | `[x]` код, `[ ]` демо-режим с dropdown |
| 12 | Markdown / код | OpenAI-совместимый ответ, WebUI рендерит штатно | `[x]` |

### 0.2. Дополнительные фичи (ряды 13–15)

| № | Фича | Путь | Статус |
|---|---|---|---|
| 13 | Deep Research = **Expert Council** | `task_type=DEEP_RESEARCH` → fan-out в `strong` + `reasoning` + `doc` → synthesis через `strong` → один chat.completion наружу, все вызовы видны в `X-GPTHub-Trace` | `[x]` WOW-1: влито в `main` (`9393d30`), live + полный `demo.sh` — `docs/LIVE_SMOKE.md` 2026-04-11 |
| 14 | Генерация презентаций | `task_type=pptx` → пакет `gpthub_orchestrator/pptx/`: план (параллельные slide-agents или монолитный JSON + retry) → `python-pptx` → markdown + **`GET /artifacts/pptx/{id}?token=…`** | `[x]` WOW-3: код + 36 тестов; live — см. `LIVE_SMOKE.md` |
| 15 | `X-GPTHub-Trace` | Production-grade наблюдаемость routing/fallback/ingest | `[x]` |

### 0.3. Scope lock и non-goals

Жёсткое правило: **один chat flow → один запрос → один ответ → один trace**.
Любая фича, которая заставляет пользователя переключать режим — non-goal.

Все три wow уважают scope lock:

- **Expert Council** делает fan-out **внутри** orchestrator. Пользователь
  отправляет один запрос и получает один ответ; fan-out виден только в
  `X-GPTHub-Trace`.
- **PPTX gen** — один ответ в том же чате: markdown-превью + HTTP-ссылка на
  скачивание `.pptx` (артефакт с одноразовым токеном), не отдельный продуктовый режим.
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

### Шаг 1 — Live docker smoke (приоритет #1, box: 3 часа)

**Почему первый:** у нас **226** unit/integration теста в orchestrator;
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
- `[ ]` `docker compose ps` показывает все сервисы `running`
- `[ ]` `curl http://localhost:8089/healthz` → `{"status":"ok"}`
- `[ ]` `curl http://localhost:8089/readyz` → `{"status":"ready"}`
- `[ ]` WebUI на `localhost:3000` открывается, видит модель `gpt-hub`
- `[ ]` Три сценария прогнаны вживую и записаны в `LIVE_SMOKE.md`
- `[ ]` git tag `smoke-green` проставлен

### Шаг 2 — Полный P0 smoke сценарий (box: 2 часа)

Прогоняем **все 12 рядов** вживую через WebUI и/или `scripts/demo.sh`:

1. текст → `mws-gpt-alpha`
2. голос → STT → текст → тот же путь
3. «нарисуй кота» → `qwen-image` → inline markdown
4. загрузить .wav → ASR → текст в system → ответ
5. загрузить фото → VLM route → `qwen3-vl`
6. загрузить .py + .md + .pdf → ingest → ответ по содержимому
7. (после шага 5 Tavily) — `{{search}} последние новости MWS`
8. `прочитай https://example.com` → `url_fetch` → summary
9. «запомни, что я пью эспрессо» → recall later
10. проверить, что classifier выбрал верную роль (смотрим trace)
11. переключить `AUTO_ROUTE_MODEL=false`, выбрать вручную — проверить
12. markdown + код в ответе — проверить рендер

Каждый пункт фиксируется в `LIVE_SMOKE.md` с таймингом и moделью.

**Kill switch:** если какой-то ряд падает — баг фикс box 30 минут. Если
не чиним за 30 минут → честно помечаем `Partial` в `FEATURE_MATRIX.md`
и едем дальше.

### Шаг 3 — Submission артефакты (box: 4 часа, параллельно другому человеку)

Этот шаг **может идти параллельно** с шагом 1–2, если есть второй человек.
Не требует рабочего стека.

1. `GPTHub шаблон фич.xlsx` — заполнить по `FEATURE_MATRIX.md`.
2. Архитектурная диаграмма (Excalidraw / Mermaid → PNG) — один лист,
   `WebUI ↔ orchestrator ↔ LiteLLM ↔ MWS` + stubbed блоки для ingest /
   memory / image-gen / trace.
3. Скелет слайдов (5–7 слайдов): problem, architecture, mixed input,
   wow, demo, trade-offs, ask.

**Kill switch:** слайды и диаграмма — это «пол». Видео записываем в шаге
6 уже на готовом стеке.

### Шаг 4 — Row 7 Tavily toggle (box: 30 минут)

Почему сейчас, а не раньше: этот ряд ничего не блокирует и живёт
целиком в env. Делаем его после smoke, чтобы не ломать baseline.

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

### Шаг 5 — WOW-1 Expert Council (box: 6 часов, жёсткий)

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

### Шаг 6 — Репетиция демо-сценария (box: 1 час)

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

### Шаг 7 — WOW-3 PPTX generation (box: 4 часа, условный) — **в коде**

Исторически был kill switch «выбросить, если не успели». Реализация уже в `main`:

1. **`apps/orchestrator/gpthub_orchestrator/pptx/`** — `plan.py` (outline + parallel slide agents или монолитный план, retry, `pptx_max_slides`), `build.py`, `parse.py`, `schema.py`, `response.py`, `artifacts.py`.
2. **`classifier.py`** — `TaskType.PPTX` → строка **`pptx`**; триггеры RU/EN + `/pptx` (см. тесты `test_classifier_pptx.py`).
3. **`router.py`** — для `task_type=pptx`: роль **`pptx_slide_plan_json`** (или `pptx_slide_plan_json_openrouter`).
4. **`main.py`** — short-circuit при `pptx_gen_enabled`: порядок после ingest/classify — **memory → council → image-gen → pptx** (комментарий в коде: PPTX после image-intent).
5. **Выдача файла** — `GET /artifacts/pptx/{artifact_id}?token=…`, база ссылки из `pptx_artifacts_public_base_url`, одноразовый токен, TTL `pptx_artifact_ttl_seconds`.
6. **Тесты** — **36** шт. (`test_pptx_module.py`, `test_classifier_pptx.py`, `test_main_pptx_short_circuit.py`).

**Kill switch (операционный):** при нестабильном JSON или проблемах зависимости —
`pptx_gen_enabled=false` в env; остальной чат не ломается.

Детальная схема фаз и логов — в **`../План pptx.md`** (раздел «Arch diagram»); канон для защиты — **`FEATURE_MATRIX.md`** row 14.

### Шаг 8 — Запись demo-видео (box: 1 час, 2–3 дубля)

1. Прогнать `scripts/demo.sh` один раз — всё ли зелёное.
2. Запись экрана (Loom / QuickTime / OBS) по сценарию Demo Lock.
3. Голосовой комментарий синхронно или монтаж (синхрон проще).
4. Монтаж: обрезать паузы, вставить 2–3 текстовых титра («Expert Council
   fan-out», «X-GPTHub-Trace in DevTools»).
5. Финальный рендер ≤ 3 минут.

**Правило:** если первый дубль не проходит — проблема в репетиции,
возвращаемся к шагу 6, не «прогоняем ещё разок».

### Шаг 9 — Финальная сверка и git tag `demo-ready` (box: 1 час)

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
| Docker smoke (шаг 1) | >3 часов не взлетает | Триаж, минимальный стек без RAG-профиля |
| Полный ряд smoke (шаг 2) | Ряд падает >30 минут | Честный `Partial` в matrix, едем дальше |
| Expert Council (шаг 5) | >6 часов без зелёного end-to-end | Откат до `smoke-green`, Council в backlog |
| Expert Council synthesis | Плохое качество synthesis | Отключаем Council, оставляем `strong`-only |
| Repetition (шаг 6) | Сценарий не прогоняется вживую | Урезаем до 3 шагов |
| PPTX (шаг 7) | JSON plan нестабильный / политика продукта | `pptx_gen_enabled=false`; без замены wow |
| Demo video (шаг 8) | Первый дубль не проходит | Возврат к шагу 6, не «ещё разок» |

**Общее правило:** wow без baseline = ноль. Если выбор между «довести
wow» и «сохранить baseline» — всегда сохраняем baseline.

---

## 0.6. Victory readiness checklist

Это **единственный** критерий «готовы к защите». Все пункты проверяемы.

### Runtime
- `[ ]` `docker compose -f infra/docker-compose.yml up -d --build` без ручных действий
- `[ ]` `curl localhost:8089/healthz` → 200
- `[ ]` `curl localhost:8089/readyz` → 200
- `[ ]` WebUI на `localhost:3000` показывает модель `gpt-hub`

### Feature baseline (ряды 1–12)
- `[ ]` все 12 рядов прогнаны вживую и записаны в `LIVE_SMOKE.md`
- `[ ]` каждому ряду в `FEATURE_MATRIX.md` соответствует либо `Implemented`, либо честный `Partial/Deferred` с причиной
- `[ ]` `scripts/demo.sh` проходит без ошибок идемпотентно

### Differentiation
- `[ ]` mixed input: один запрос с PDF + image + audio + URL даёт один ответ
- `[ ]` `X-GPTHub-Trace` виден в DevTools → Network → Headers для одного живого запроса
- `[ ]` memory: «запомни X» → «что ты помнишь» работает end-to-end
- `[x]` Expert Council (WOW-1): `/research` и аналоги — fan-out + synthesis, см. `X-GPTHub-Trace` и `docs/LIVE_SMOKE.md` 2026-04-11
- `[x]` (wow-3) PPTX: «сделай презентацию» → markdown + ссылка на **`GET /artifacts/pptx/…`** (код + тесты); `[ ]` финальный live-прогон в вашем стенде — в `LIVE_SMOKE.md`

### Submission artifacts
- `[ ]` `GPTHub шаблон фич.xlsx` заполнен
- `[ ]` Архитектурная диаграмма (PNG/SVG) готова
- `[ ]` Demo-видео ≤ 3 минут записано
- `[ ]` Презентация 5–7 слайдов готова
- `[ ]` `docs/LIVE_SMOKE.md` содержит журнал живых прогонов

### Docs consistency
- `[ ]` `README.md`, `ROADMAP.md`, `FEATURE_MATRIX.md`, `CHANGELOG.md`, `docs/NEW_CHAT_HANDOFF_RU.md`, `docs/TEAM_BRIEF_RU.md` — синхронны
- `[ ]` git tag `demo-ready` проставлен

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
5. **(wow-3) PPTX:** «сделай презентацию по этому разбору»
   → markdown-превью + ссылка на скачивание `.pptx` (`/artifacts/pptx/…`).
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
2. ✅ **Шаг 4 — Tavily toggle** — env + compose; см. `.env.example`.
3. ✅ **Шаг 7 — PPTX (WOW-3)** — в `main`: пакет `gpthub_orchestrator/pptx/`, markdown + **`GET /artifacts/pptx/{id}?token=…`**.
   Дальше по коду — пост-конкурс §5; по продукту — **оператор** (шаги 6/8/9).

### Трек B — Infra / Smoke (один человек)

1. **Шаг 1 — Docker smoke** (остановить v3, поднять prod).
2. **Шаг 2 — Полный ряд smoke** по всем 12 фичам.
3. **Шаг 6 — Репетиция** после того, как wow-компоненты в main.
4. **Шаг 8 — Запись видео**.

### Трек C — Submission (один человек)

1. **Шаг 3 — Артефакты** (xlsx, диаграмма, скелет слайдов).
2. После шага 6 — финализация слайдов с реальными скриншотами.
3. **Шаг 9 — Финальная сверка** перед `demo-ready`.

---

## 5. Как читать roadmap

- Нужен **следующий шаг прямо сейчас** — раздел 0.4 (victory plan).
- Нужны **условия обрезки** — раздел 0.5 (kill switches).
- Нужна **проверка «готовы ли» к защите** — раздел 0.6 (checklist).
- Нужен **документ для команды** — `docs/TEAM_BRIEF_RU.md`.
- Нужен **документ для нового окна чата** — `docs/NEW_CHAT_HANDOFF_RU.md`.

Если в этих файлах расхождение с `ROADMAP.md` — правим канон, а не плодим
вторую правду.
