# GPTHub Prod: Briefing Для Команды

**Зачем этот документ:** это один файл, который можно отправить команде,
чтобы все быстро поняли:

- что мы строим;
- какая архитектура;
- что уже соблюдено по условиям организаторов;
- что ещё не закрыто;
- как именно мы планируем побеждать;
- какие задачи можно брать в работу прямо сейчас.

> Файл должен оставаться актуальным. Если в `ROADMAP.md` или
> `FEATURE_MATRIX.md` что-то поменялось — обновить и этот брифинг.
> Политика выбора модели (роли, baseline vs текущий реестр): `docs/MODEL_ROUTING_POLICY.md`.

## 1. Что мы строим

Мы строим **единый AI workspace на базе Open WebUI**, где пользователь
работает в одном чате, а наш runtime сам собирает нужный контекст и
маршрутизирует запрос в модели MWS.

Ключевой продуктовый принцип:

`один чат → один запрос → один ответ → один понятный trace`

У нас **нет** второго флагманского режима, нет зоопарка вкладок и нет
параллельных продуктовых веток. Главная дифференциация одна:

**mixed input** — один запрос может сочетать текст, картинку, PDF, аудио,
текстовые файлы и URL в одном потоке.

Сверху мы добавляем **wow-фичи, которые не ломают «один chat flow»**:
Expert Council (внутренний fan-out в несколько MWS моделей с synthesis),
генерация презентаций, и подсветка `X-GPTHub-Trace` как production-grade
наблюдаемости.

## 2. Набор технологий

- **Open WebUI** — пользовательский интерфейс чата;
- **FastAPI orchestrator** (`apps/orchestrator/`) — продуктовая логика:
  routing, ingest (PDF/текст/URL/аудио/image), image-gen + **pptx** short-circuit,
  prompt policy, trace, memory, Expert Council fan-out;
- **LiteLLM** (`infra/litellm/config.yaml`) — единый gateway и alias layer
  над MWS;
- **MWS GPT** — основной upstream моделей;
- **embedding shim** (`apps/embedding_shim/`) — optional RAG-профиль;
- **Docker Compose** (`infra/docker-compose.yml`) — единый локальный запуск.

## 3. Что уже готово в коде

**226+ тестов в orchestrator, все зелёные** (`uv run pytest -q`).

### Обязательные ряды 1–12

- **Row 1 Текстовый чат** — orchestrator→LiteLLM→MWS (`mws-gpt-alpha` / `glm-4.6-357b`); **live PASS в `demo.sh` 2026-04-11**;
- **Row 2 Voice** — UI-managed STT/TTS Open WebUI, дальше общий путь; нужен оператор для micro-демо;
- **Row 3 Image generation** — `image_gen.py` ловит «нарисуй/draw/…» и зовёт MWS `/v1/images/generations` (`qwen-image`), inline `![](url)` в ответе (json + stream). Fall-through на обычный chat при ошибке; **live PASS в `demo.sh`**;
- **Row 4 Audio + ASR** — `Settings.resolved_asr_*()` делает автоматический fallback на `MWS_GPT_API_BASE/KEY` и по умолчанию использует MWS `whisper-medium`; нужен оператор для live `.wav` upload;
- **Row 5 Image understanding (VLM)** — image-aware routing через alias chain `gpt-hub-vision → vision-2 → vision-3 → vision-4 → fallback`; нужен оператор для live photo upload;
- **Row 6 Files** — ingest PDF + **DOCX/XLSX/PPTX** (via markitdown) + plain text (`.txt/.md/.json/.yaml/.py/.ts/.go/.sql/…` ��30 расширений). **Hot-fix 2026-04-12:** Open WebUI RAG-эмбеддинг и краш PDF — `BYPASS_EMBEDDING_AND_RETRIEVAL=true` (commit `0d48f26`); ждём operator retry → финальный `Implemented`;
- **Row 8 URL parsing** — `ingest/url_fetch.py`: SSRF-защита, size/timeout caps, HTML→text без внешних deps, 12 тестов; **live PASS в `demo.sh`**;
- **Row 9 Long-term memory** — `memory/`: SQLite store + MWS `qwen3-embedding-8b` retrieval + парсер команд «запомни X / забудь X / что ты помнишь» (RU + EN + `/remember`, `/forget`, `/memories`). Memory short-circuit + retrieval injection; **52+** теста в `test_memory_*.py`; **live:** recall ок; **save** иногда **ReadTimeout** на embeddings — см. `LIVE_SMOKE.md`, `memory_embedding_timeout_seconds`;
- **Row 10 Автовыбор модели** — classifier + router + alias chain (`data/model_roles.yaml`, **версия 1**, см. `docs/MODEL_ROUTING_POLICY.md`); **live trace в `demo.sh`**;
- **Row 11 Ручной выбор модели** — переключение `AUTO_ROUTE_MODEL=false` + `ORCHESTRATOR_MODELS_CATALOG=all`;
- **Row 12 Markdown / код** — OpenAI-совместимый ответ, WebUI рендерит штатно.

### Wow + trace (ряды 13–15)

- **Row 13 Expert Council (WOW-1)** — **Implemented** в `main` (`9393d30`): `council.py`, fan-out + synthesis, **29** unit-тестов; защитные слои: branch-timeout / min-branches / `merge_reasoning_exclude_into_body` + CoT-strip / CoT-dump heuristic → emergency composite. **Live 2026-04-11:** 171 s, 3/3 ветки, clean RU synthesis + полный `demo.sh` — `docs/LIVE_SMOKE.md`.
- **Row 14 PPTX (WOW-3)** — пакет `gpthub_orchestrator/pptx/`: `task_type=pptx`, router `pptx_slide_plan_json*`, план (parallel slide agents или монолит + retry), CoT/thinking stripping, `python-pptx`, ответ с markdown + **`GET /artifacts/pptx/{id}?token=…`**. **36** тестов (`test_pptx_module.py`, `test_classifier_pptx.py`, `test_main_pptx_short_circuit.py`); **live 2026-04-12** — `LIVE_SMOKE.md`.
- **Row 15 X-GPTHub-Trace** — есть, подсвечиваем на защите.


### Ещё не закрыто

- **Row 7 Web search** — ✅ env + toggle (см. шаг 4 / `ROADMAP.md`); перепроверить per-chat глобус в WebUI на стенде.

### Инфраструктура и smoke

- `docs/MWS_CATALOG.md` — snapshot живого каталога MWS. Все alias в
  `litellm/config.yaml` валидны; text / image / whisper / embeddings контракты проверены curl.
- Старый стек `gpthub-v3-*` при необходимости остановить (порты 3000/4000/8089); prod compose: три сервиса `Healthy`; tag `smoke-green` проставлен.
- Живые прогоны фиксировать в `docs/LIVE_SMOKE.md` (PPTX, council, `demo.sh`).
- `scripts/demo.sh` без `--skip-wow` — ожидаемый итог **PASS=12 FAIL=0**; **WARN>0** возможен, если эвристики шагов 8–9 не находят council/PPTX в теле ответа (см. вывод скрипта). Старые записи WARN из‑за PPTX до WOW-3 — см. журнал, не как текущий блокер.


## 4. Соблюдаем ли условия организаторов

Коротко: **почти да:** row 7 (Tavily), полный WebUI/P0 чеклист, репетиция/видео,
wow PPTX (row 14) **в коде** — см. `FEATURE_MATRIX.md` и `ROADMAP.md` §0.4 шаг 7.

### Закрыто кодом + тестами

- база на Open WebUI ✅
- Python product layer через orchestrator ✅
- MWS-first routing через LiteLLM ✅
- автоматический и ручной выбор модели ✅
- VLM ✅
- PDF / plain-text / URL ingest ✅
- ASR через MWS ✅
- image generation через MWS ✅
- долгосрочная память через SQLite + `qwen3-embedding-8b` ✅
- markdown ✅
- единый product flow без зоопарка ✅

### Осталось

- полный WebUI/P0 чеклист и репетиция (см. `LIVE_SMOKE.md`);
- operator checklist (голос, загрузки, Tavily, PPTX-ссылка) — `LIVE_SMOKE.md`;
- submission artifacts (видео, диаграмма, презентация, xlsx).

## 5. Как мы используем модели MWS

Сейчас `infra/litellm/config.yaml` делает MWS **основным model backend**.
Все alias сверены с живым `GET /v1/models` и зафиксированы в
`docs/MWS_CATALOG.md`:

- `gpt-hub-turbo` → `mws-gpt-alpha` — базовый чатовый путь;
- `gpt-hub-fast` → `llama-3.1-8b-instruct` — быстрый текстовый;
- `gpt-hub-strong` → `glm-4.6-357b` — тяжёлый основной;
- `gpt-hub-doc` → `qwen2.5-72b-instruct` — document-oriented;
- `gpt-hub-reasoning-or` → `qwen3-coder-480b-a35b` — reasoning / code;
- `gpt-hub-vision*` → `qwen3-vl-30b` / `qwen2.5-vl*` / `cotype-pro-vl-32b`;
- `gpt-hub-fallback` → `gemma-3-27b-it`.

Отдельно orchestrator использует **не через LiteLLM alias**, а напрямую:

- `qwen-image` — для image generation (row 3);
- `whisper-medium` — для ASR (row 4);
- `qwen3-embedding-8b` (dim 4096) — для долгосрочной памяти (row 9) и
  будущего Council reranking.

Alias chain + direct-call — оба пути задокументированы и не пересекаются.

## 6. Архитектура простыми словами

1. Пользователь пишет в **Open WebUI**.
2. Запрос идёт в **orchestrator**:
   - ingest pipeline: PDF + текст-файлы + URL + audio → artifacts;
   - классификатор: определяет modalities + task_type;
   - **memory-command short-circuit**: если последнее сообщение —
     «запомни X / забудь X / что ты помнишь» — orchestrator сам читает/
     пишет SQLite-store и возвращает ответ, не ходя в LiteLLM;
  - **image-gen short-circuit**: если пользователь просит картинку —
     orchestrator сам зовёт MWS `/images/generations` и возвращает inline
     markdown, не ходя в LiteLLM;
  - **pptx short-circuit**: при `pptx_gen_enabled` и `task_type=pptx` —
     план слайдов + `python-pptx`, ответ с ссылкой **`/artifacts/pptx/…`**;
  - **greeting canned short-circuit**: тривиальные приветствия;
   - **memory retrieval**: top-K фактов из SQLite по эмбеддингу
     последнего user-сообщения через MWS `qwen3-embedding-8b`, ложится
     дополнительным system-блоком перед role-prompt;
   - **Expert Council**: если запрос council (`/research` и аналоги) —
     параллельный fan-out в 3 MWS модели и synthesis;
   - иначе: роль-бэкед alias chain → LiteLLM.
3. **LiteLLM** отправляет вызов в **MWS**.
4. Ответ возвращается пользователю, `X-GPTHub-Trace` фиксирует всё решение.

Главный architectural rule:

- **Open WebUI** — UX;
- **orchestrator** — product intelligence;
- **LiteLLM** — gateway;
- **MWS** — модели.

## 7. Как будем побеждать

Принцип номер один: **зелёный baseline раньше синих wow**. Wow без
работающего baseline = ноль баллов. Если выбор между «доводим wow» и
«сохраняем baseline» — всегда сохраняем baseline.

Полный план по шагам, kill switch'ам и victory checklist — в `ROADMAP.md`
разделы 0.4 / 0.5 / 0.6. Короткая версия:

1. **Шаг 1 ✅ — Docker smoke baseline.** v3-стек погашен при необходимости, prod compose поднят, три сервиса `Healthy`, tag `smoke-green`.
2. **Шаг 2 ✅ в основном — P0 smoke.** `demo.sh` без `--skip-wow` — **PASS=12 FAIL=0** (WARN см. вывод шагов 8–9). Остаются operator-сценарии (шаг 6).
3. **Шаг 3 (черновик) — submission артефакты.** xlsx, диаграмма, слайды; финализация после шага 6.
4. **Шаг 4 ✅ — Row 7 Tavily** — env в `.env` / `.env.example`, WebUI admin OK.
5. **Шаг 5 ✅ — WOW-1 Expert Council** в `main` (`9393d30`).
6. **Шаг 6 (оператор)** —** (голос, .wav, фото, PDF post-fix, dropdown) + репетиция.
7. **Шаг 7 ✅ — WOW-3 PPTX** — пакет `gpthub_orchestrator/pptx/` + тесты; **live 2026-04-12**.
8. **Шаг 8 (видео) — запись demo-видео** 2–3 минуты.
9. **Шаг 9 (финал) — финальная сверка** канона + git tag `demo-ready`.


Что показываем на защите:

- **один цельный сценарий**: PDF + скрин + аудио + ссылка → «запомни мои
  предпочтения» → (если успели) «исследуй глубоко» (Council) → «сделай
  презентацию» (PPTX → ссылка на `.pptx`);
- всё это — **в одном чате**;
- в DevTools открываем `X-GPTHub-Trace` — видно classifier, router,
  fallback chain, ingest artifacts, (если есть) council attempts. Это
  production-grade момент, которого у других команд не будет.

**Журнал живых прогонов:** `docs/LIVE_SMOKE.md`. Каждый прогон
фиксируется с датой, сценарием, моделью и таймингом. На защите это
убивает любые сомнения жюри.

## 8. Активные треки

### Трек A — code (один человек)

1. **Шаг 5 ✅ — WOW-1 Expert Council** в `main` (`9393d30`).
2. **Шаг 4 ✅ — Row 7 Tavily toggle** — env + compose; см. `.env.example`.
3. **Шаг 7 ✅ — WOW-3 PPTX** — `gpthub_orchestrator/pptx/`, **`GET /artifacts/pptx/…`**; live 2026-04-12.


Правило гигиены: новые wow-фичи — в `main` только после зелёного прогона.

### Трек B — infra / smoke (один человек)

1. **Шаг 1 ✅ — Docker smoke.** v3-стек погашен при необходимости, prod compose, `Healthy`, WebUI видит `gpt-hub-*`, tag `smoke-green`.
2. **Шаг 2 ✅ — полный P0 smoke.** `demo.sh`: **PASS=12 FAIL=0**; журнал `docs/LIVE_SMOKE.md`.
3. **Шаг 6 (оператор) — репетиция** (Row 2 voice, Row 4 .wav, Row 5 фото, Row 6 PDF post-fix, Row 11 dropdown). Box: 1 ч.
4. **Шаг 8 (видео) — запись demo-видео** (box: 1 ч, 2–3 дубля).


### Трек C — submission (один человек)

1. **Шаг 3 — Submission артефакты** (box: 4 ч, параллельно остальным).
   - `GPTHub шаблон фич.xlsx` по `FEATURE_MATRIX.md`.
   - Архитектурная диаграмма (Excalidraw / Mermaid → PNG).
   - Скелет слайдов 5–7 штук (problem, architecture, mixed input, wow,
     demo, trade-offs, ask).
2. После шага 6 — финализация слайдов со скриншотами живого демо.
3. **Шаг 9 — Финальная сверка** всех документов канона + git tag
   `demo-ready`.

### Общее правило для всех треков

- Все изменения статуса — синхронно в `ROADMAP.md` раздел 0.1/0.2,
  `FEATURE_MATRIX.md`, `docs/LIVE_SMOKE.md` и (если релевантно)
  `CHANGELOG.md`.
- При срабатывании kill switch — обновлять соответствующий ряд в
  matrix и фиксировать причину в `LIVE_SMOKE.md`.
- После git tag `demo-ready` — правки только критических багов.

## 9. Как распределять задачи (если людей мало)

**Важно:** порядок ниже отражает «baseline раньше wow», а не «интересное
раньше скучного». Докер-смоук идёт первым не потому что он лёгкий, а
потому что без него всё остальное рискует быть бесполезным.

1. ✅ **Live docker smoke** (трек B, шаги 1–2) — закрыто, `smoke-green`.
2. ��2. **Submission артефакты** (трек C, шаг 3) — черновики; финализация после шага 6.
3. ✅ **Row 7 Tavily** (трек A, шаг 4) — env готов.
4. ✅ **WOW-3 PPTX** (трек A, шаг 7) — код в `pptx/` + artifacts, live 2026-04-12.
5. ��5. **Оператор + репетиция** (трек B, шаг 6).
6. **Видео + финализация** (треки B и C, шаги 8–9).


Если людей совсем мало — делаем шаги 1, 2, 3, 6 (репетиция), 8, 9.
PPTX и Council уже в baseline; дальше — операторский live + упаковка сдачи.

## 10. Какой один документ отправить команде

Отправлять команде нужно **этот файл**: `docs/TEAM_BRIEF_RU.md`.

Почему:

- коротко объясняет архитектуру;
- честно говорит, что закрыто, а что нет;
- фиксирует путь к победе;
- даёт трек-разбиение.

Если нужно открыть **новое окно чата и продолжить разработку** в
техническом режиме — использовать `docs/NEW_CHAT_HANDOFF_RU.md`.
