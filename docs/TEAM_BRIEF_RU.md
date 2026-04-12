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
  routing, ingest (PDF/текст/URL/аудио/image), image-gen short-circuit,
  prompt policy, trace, (будущая) memory, (будущий) council fan-out;
- **LiteLLM** (`infra/litellm/config.yaml`) — единый gateway и alias layer
  над MWS;
- **MWS GPT** — основной upstream моделей;
- **embedding shim** (`apps/embedding_shim/`) — optional RAG-профиль;
- **Docker Compose** (`infra/docker-compose.yml`) — единый локальный запуск.

## 3. Что уже готово в коде

**234 теста в orchestrator, все зелёные.**

### Обязательные ряды 1–12

- **Row 1 Текстовый чат** — orchestrator→LiteLLM→MWS (`mws-gpt-alpha` /
  `glm-4.6-357b`); **live PASS в `demo.sh` 2026-04-11**;
- **Row 2 Voice** — UI-managed STT/TTS Open WebUI; нужен оператор для
  micro-демо;
- **Row 3 Image generation** — `image_gen.py` → MWS
  `/v1/images/generations` (`qwen-image`), inline `![](url)`. **Live PASS
  в `demo.sh`**;
- **Row 4 Audio + ASR** — `Settings.resolved_asr_*()` → MWS
  `whisper-medium`. Нужен оператор для live `.wav` upload;
- **Row 5 Image understanding (VLM)** — alias chain
  `gpt-hub-vision → vision-2 → vision-3 → vision-4 → fallback`. Нужен
  оператор для live photo upload;
- **Row 6 Files** — ingest PDF + plain text (≈30 расширений) в orchestrator.
  **Hot-fix 2026-04-12:** Open WebUI пытался свой RAG-эмбеддинг и крашил
  PDF upload с `'NoneType' encode`; включили
  `BYPASS_EMBEDDING_AND_RETRIEVAL=true` (commit `0d48f26`). Ждём operator
  retry → финальный `Implemented`;
- **Row 8 URL parsing** — `ingest/url_fetch.py`: SSRF, size/timeout caps,
  HTML→text без внешних deps. **Live PASS в `demo.sh`**;
- **Row 9 Long-term memory** — `memory/`: SQLite store + MWS
  `qwen3-embedding-8b` retrieval + парсер команд «запомни / забудь /
  что ты помнишь». Memory short-circuit + retrieval injection. 52 теста.
  **Live PASS в `demo.sh`**;
- **Row 10 Автовыбор модели** — classifier + router + alias chain.
  **Live trace в `demo.sh`**;
- **Row 11 Ручной выбор модели** — `AUTO_ROUTE_MODEL=false` +
  `ORCHESTRATOR_MODELS_CATALOG=all`;
- **Row 12 Markdown / код** — OpenAI-совместимый ответ.

### Wow + trace (ряды 13–15)

- **Row 13 Expert Council (WOW-1)** — **Implemented** ✅ в `main`
  (`9393d30`). `council.py`: fan-out в `gpt-hub-turbo` + `gpt-hub-reasoning-or`
  + `gpt-hub-doc`, synthesis через `gpt-hub-strong` (`glm-4.6-357b`).
  Один `chat.completion` наружу, формат «суть → совет экспертов →
  практические рекомендации». 4 защитных слоя: branch-timeout /
  min-branches / `merge_reasoning_exclude_into_body` + CoT-strip /
  CoT-dump heuristic → emergency composite. 29 unit-тестов.
  **Live 2026-04-11 11:32: 171 s, 3/3 ветки, clean RU synthesis +
  полный `demo.sh` 11:46.**
- **Row 14 PPTX (WOW-3)** — **Implemented** ✅. `pptx_gen.py`:
  JSON slide plan via `gpt-hub-strong` (retry on parse failure) →
  `python-pptx` → download link `GET /v1/files/pptx/{token}`.
  52 unit-тестов.
- **Row 15 X-GPTHub-Trace** — есть, подсвечиваем на защите.

### Ещё не закрыто

- **Operator-сценарии** для Step 6: Row 2 voice, Row 4 .wav, Row 5 фото,
  Row 6 PDF post-fix, Row 11 manual dropdown.
- Submission артефакты (видео, финальная презентация, git tag `demo-ready`).

### Инфраструктура и smoke

- `docs/MWS_CATALOG.md` — snapshot живого каталога MWS. Все alias в
  `litellm/config.yaml` валидны; контракты text / image / whisper /
  embeddings проверены курлом.
- v3-стек остановлен; prod compose поднят, все три сервиса `Healthy`;
  tag `smoke-green` проставлен.
- `scripts/demo.sh` без `--skip-wow` — **PASS=12 FAIL=0 WARN=1**
  (единственный WARN — Row 14 PPTX до Step 7).

## 4. Соблюдаем ли условия организаторов

Коротко: **почти да:** row 7 (Tavily), полный WebUI/P0 чеклист, репетиция/видео,
wow PPTX (row 14) по желанию — см. `ROADMAP.md` §0.4.

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
   - **greeting canned short-circuit**: тривиальные приветствия;
   - **memory retrieval**: top-K фактов из SQLite по эмбеддингу
     последнего user-сообщения через MWS `qwen3-embedding-8b`, ложится
     дополнительным system-блоком перед role-prompt;
   - **(future) Expert Council**: если `task_type=DEEP_RESEARCH` —
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
разделы 0.4 / 0.5 / 0.6. Короткая версия (статус 2026-04-12):

1. **Шаг 1 ✅ ЗАКРЫТО — Docker smoke baseline.** v3-стек погашен,
   prod compose поднят, три сервиса `Healthy`, tag `smoke-green`.
2. **Шаг 2 ✅ В ОСНОВНОМ ЗАКРЫТО — P0 smoke.** `demo.sh` без `--skip-wow`
   на 2026-04-11 11:46: PASS=12 FAIL=0 WARN=1. Остаются operator-сценарии
   (Шаг 6).
3. **Шаг 3 🟡 ЧЕРНОВИКИ ГОТОВЫ — submission артефакты.** xlsx, диаграмма,
   слайды есть в `docs/submission/`; финализация — после Шага 6.
4. **Шаг 4 ✅ ЗАКРЫТО — Row 7 Tavily** env vars в `.env`, container OK.
5. **Шаг 5 ✅ ЗАКРЫТО — WOW-1 Expert Council** в `main` (`9393d30`).
6. **Шаг 6 🔜 ОПЕРАТОР — operator-сценарии и репетиция** (Row 2 voice,
   Row 4 .wav, Row 5 фото, Row 6 PDF post-fix, Row 11 dropdown).
7. **Шаг 7 ✅ ЗАКРЫТО — WOW-3 PPTX** — `pptx_gen.py` + 52 теста в `main`.
8. **Шаг 8 🔜 ОПЕРАТОР — запись demo-видео** 2–3 минуты.
9. **Шаг 9 🔜 ФИНАЛ — финальная сверка** канона + git tag `demo-ready`.

Что показываем на защите:

- **один цельный сценарий**: PDF + скрин + аудио + ссылка → «запомни мои
  предпочтения» → (если успели) «исследуй глубоко» (Council) → (если
  успели) «сделай презентацию» (PPTX);
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
2. **Шаг 4 ✅ — Row 7 Tavily toggle** — env vars in `.env`, confirmed.
3. **Шаг 7 ✅ — WOW-3 PPTX** — `pptx_gen.py` + 52 теста в `main`.

Правило гигиены: следующие wow-ветки (напр. PPTX) — в `main` только после
зелёного прогона, как для Council.

### Трек B — infra / smoke (один человек)

1. **Шаг 1 ✅ — Docker smoke.** v3-стек погашен, prod compose поднят,
   все три сервиса `Healthy`, WebUI видит `gpt-hub-*`, tag `smoke-green`.
2. **Шаг 2 ✅ — Полный P0 smoke.** `demo.sh` 2026-04-11 11:46:
   PASS=12 FAIL=0 WARN=1, журнал в `docs/LIVE_SMOKE.md`.
3. **Шаг 6 🔜 — Operator-сценарии + репетиция** (Row 2 voice, Row 4 .wav,
   Row 5 фото, Row 6 PDF post-fix, Row 11 dropdown). Box: 1 ч.
4. **Шаг 8 🔜 — Запись demo-видео** (box: 1 ч, 2–3 дубля).

### Трек C — submission (один человек)

1. **Шаг 3 🟡 — Submission артефакты черновиками.** В `docs/submission/`
   уже лежат:
   - `GPTHub_features_matrix.xlsx` (регенерация после Row 13 — отдельная
     задача);
   - `architecture.mmd` + `gpthub-architecture.excalidraw`;
   - `SLIDES_SKELETON.md` (problem → architecture → mixed input → wow →
     demo → trade-offs → ask).
2. После Шага 6 — финализация слайдов со скриншотами живого демо.
3. **Шаг 9 🔜 — Финальная сверка** всех документов канона + git tag
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
раньше скучного». Докер-смоук был первым не потому что он лёгкий, а
потому что без него всё остальное рискует быть бесполезным; на 2026-04-12
он уже закрыт.

1. ✅ **Live docker smoke** (трек B, шаги 1–2) — закрыто, `smoke-green`.
2. 🟡 **Submission артефакты** (трек C, шаг 3) — черновики готовы,
   xlsx пересобран. Финализация после Шага 6.
3. ✅ **Row 7 Tavily** (трек A, шаг 4) — env vars в `.env`, confirmed.
4. ✅ **WOW-3 PPTX** (трек A, шаг 7) — код + 52 теста в `main`.
5. 🔜 **Operator-сценарии + репетиция** (трек B, шаг 6).
6. 🔜 **Видео + финализация** (треки B и C, шаги 8–9).

Если людей совсем мало — оставшиеся обязательные пункты:
Шаг 6 (operator + репетиция), Шаг 8 (видео), Шаг 9 (финал + tag
`demo-ready`). Весь код закрыт; Council и PPTX уже в baseline.

## 10. Какой один документ отправить команде

Отправлять команде нужно **этот файл**: `docs/TEAM_BRIEF_RU.md`.

Почему:

- коротко объясняет архитектуру;
- честно говорит, что закрыто, а что нет;
- фиксирует путь к победе;
- даёт трек-разбиение.

Если нужно открыть **новое окно чата и продолжить разработку** в
техническом режиме — использовать `docs/NEW_CHAT_HANDOFF_RU.md`.
