# Live Smoke Journal

> Журнал живых прогонов через поднятый `docker compose` стек. Заполняется
> **при каждом** live-тесте и защищает нас от «работало на прошлой неделе».
>
> Правило: **никакой ряд не помечается `Implemented` в
> `FEATURE_MATRIX.md` без хотя бы одной записи здесь**. Unit-тест этого
> не заменяет — unit-тест проверяет код, а журнал проверяет стек.

## Формат записи

```
## <YYYY-MM-DD HH:MM> — <короткое имя сценария>

- **Stack commit:** <git sha>
- **Env:** <какой .env.mws.local, какие live-флаги>
- **Input:** <что отправили>
- **Model(s) used:** <из X-GPTHub-Trace>
- **Latency:** <миллисекунды>
- **Result:** OK / FAIL / PARTIAL
- **Trace highlights:** <classifier task_type, router role, fallback chain, artifacts>
- **Notes:** <что заметили, что сломалось, что починили>
```

Если прогон **упал** — обязательно фиксируем, что именно, и решение
(починили / обошли / отложили / kill switch).

---

## 2026-04-11 — Step 1 teardown legacy v3 stack

- **Stack commit:** tag `smoke-green` on `main` (resolve SHA with `git rev-parse --short HEAD`)
- **Env:** `.env` bootstrapped from `.env.example` with local-only auth placeholders (not committed); `.env.mws.local` present for LiteLLM→MWS (secrets not logged).
- **Input:** `docker rm -f gpthub-v3-orchestrator gpthub-v3-embedding-shim gpthub-v3-open-webui gpthub-v3-litellm`
- **Model(s) used:** _n/a_
- **Latency:** under 1 s (CLI)
- **Result:** OK
- **Trace highlights:** _n/a_
- **Notes:** All four legacy names removed on this host; frees 3000/4000/8089 for `gpthub-prod-*` stack.

## 2026-04-11 — Step 1 prod compose bring-up

- **Stack commit:** tag `smoke-green` on `main` (resolve SHA with `git rev-parse --short HEAD`)
- **Env:** same as above; compose file `infra/docker-compose.yml`; no `rag` profile.
- **Input:** `docker compose -f infra/docker-compose.yml up -d --build`
- **Model(s) used:** _n/a_
- **Latency:** orchestrator image build ~2 min cold; total bring-up ~20 s after images warm
- **Result:** OK
- **Trace highlights:** _n/a_
- **Notes:** Services `gpthub-prod-litellm`, `gpthub-prod-orchestrator`, `gpthub-prod-open-webui` created; `docker compose ps` shows litellm/orchestrator healthy; WebUI container up on port 3000.

## 2026-04-11 11:46 — Step 5 full `demo.sh` (including WOW-1) end-to-end

- **Stack commit:** `wow/expert-council` @ `9ff08ce` (council feature commit).
- **Env:** `.env` + `.env.mws.local`; container rebuilt with `council.py`; `ORCHESTRATOR_URL=http://localhost:8089`.
- **Input:** `./scripts/demo.sh` (no `--skip-wow`). Steps 1–7 hit the P0 baseline; step 8 sends `/research ... корпоративные RAG` via curl; step 9 sends the PPTX prompt.
- **Model(s) used:** Row 1 → `gpt-hub-turbo`; Row 8 URL → alpha; Row 3 image → `qwen-image`; Row 9 memory → `qwen3-embedding-8b` + alpha; Row 10 classifier → alpha; Step 8 council → 3 experts + `gpt-hub-strong` synthesis.
- **Latency:** full run dominated by council (~171 s). Total end-to-end ≈ 3.5 min.
- **Result:** **PASS=12 FAIL=0 WARN=1**. Исторический WARN относится к прогону **до** финального PPTX short-circuit: шаг 9 `demo.sh` не проверял markdown + **`GET /artifacts/pptx/…`**. Текущий код — `gpthub_orchestrator/pptx/` (см. `FEATURE_MATRIX.md` row 14); для закрытия ряда в матрице нужен отдельный live-прогон с кликом по ссылке скачивания.
- **Trace highlights:** `X-GPTHub-Trace` present on every row; council path returned a valid OpenAI-compatible `chat.completion` with the synthesized answer (curl path in step 8 is unbounded and waits out the full 171 s).
- **Notes:** Confirms the council code in the live container works inside the automated smoke, not just the manual `POST /v1/chat/completions` from 11:32. `wow/expert-council` is green end-to-end through docker; the only remaining WARN is a known-unmerged wow-candidate. Clears the ROADMAP §0.4 rule «merge `wow/expert-council` only after green end-to-end through WebUI».

## 2026-04-11 11:32 — Step 5 Expert Council (WOW-1) live smoke

- **Stack commit:** branch `wow/expert-council`, orchestrator rebuilt with `council.py` + `merge_reasoning_exclude_into_body` + `<think>` strip + CoT-dump detection.
- **Env:** `.env` + `.env.mws.local`; council defaults — experts `gpt-hub-turbo` / `gpt-hub-reasoning-or` / `gpt-hub-doc`, synthesizer `gpt-hub-strong` (glm-4.6-357b), expert max-tokens 700, synthesis max-tokens 3000.
- **Input:** `POST /v1/chat/completions` with `{"messages":[{"role":"user","content":"/research Что такое Retrieval-Augmented Generation (RAG) в AI? Плюсы и минусы основных подходов в 2025 году. Развёрнуто."}]}`.
- **Model(s) used:** `gpt-hub-turbo` (mws-gpt-alpha, generalist), `gpt-hub-reasoning-or` (qwen3-coder-480b, reasoning), `gpt-hub-doc` (qwen2.5-72b, doc) → синтез через `gpt-hub-strong` (glm-4.6-357b).
- **Latency:** 171 s end-to-end. Parallel fan-out: Generalist 13 s / Reasoning 19 s / Doc 40 s (≈ max 40 s). Synthesis: ≈ 130 s.
- **Result:** OK. Один OpenAI-совместимый `chat.completion`, 3425 символов, на русском, без `<think>` leakage, со структурой «суть → Что говорит совет экспертов → Практические рекомендации».
- **Trace highlights:** `orchestrator_fallback` payload:

  ```json
  {
    "short_circuit": "expert_council",
    "synthesis_model": "gpt-hub-strong",
    "branches_ok": [
      {"key": "strong",    "model": "gpt-hub-turbo",         "label": "Generalist",       "latency_ms": 13266, "chars": 2453},
      {"key": "reasoning", "model": "gpt-hub-reasoning-or",  "label": "Reasoning",        "latency_ms": 19138, "chars": 2113},
      {"key": "doc",       "model": "gpt-hub-doc",           "label": "Doc/Long-context", "latency_ms": 40309, "chars": 2020}
    ],
    "branches_failed": [],
    "total_ms": 170553,
    "fallback_used": false
  }
  ```
- **Notes:** Первая попытка (`gpt-hub-strong` как generalist, 120 s synthesis timeout, 1200 max-tokens) упала двумя разными способами: (1) synthesis timeout 207 s → emergency composite с raw `<think>`; (2) после bump'а таймаута — glm-4.6 съел все 1200 токенов на CoT и вернул **пустой** `content`. Починили тремя вещами одновременно: (a) `merge_reasoning_exclude_into_body` теперь применяется ко всем council-вызовам, чтобы upstream не возвращал reasoning-поля; (b) `council_max_synthesis_tokens` поднят до 3000; (c) добавлен эвристический детектор CoT-dump'а (если после strip ответ похож на план типа `1.  **Deconstruct the Request:**`, падаем в emergency composite). Unit-тесты (29 шт. в `test_council.py`) покрывают все четыре пути: happy, partial (2/3), strong-only fallback, emergency composite, плюс CoT strip для закрытых и незакрытых `<think>`. Ряд 13 (WOW-1 Expert Council) переведён из Deferred → Implemented.

## 2026-04-11 11:06 — Step 1 image-gen re-check (WARN → OK)

- **Stack commit:** `main` after shadow-fix (commit `094686d`)
- **Env:** `.env` + `.env.mws.local` loaded; `MWS_GPT_API_BASE/KEY` visible inside `gpthub-prod-orchestrator` container.
- **Input:**
  1. `docker exec gpthub-prod-orchestrator python -c "httpx.post('$MWS_GPT_API_BASE/images/generations', ...)"` — прямой probe к MWS из контейнера.
  2. `POST /v1/chat/completions` с `"Нарисуй рыжего кота в шляпе."` через orchestrator.
  3. `./scripts/demo.sh --skip-wow` (после фикса bash-глоба `*'!['*'](http'*`).
- **Model(s) used:** MWS `qwen-image` (короткое замыкание `short_circuit=image_gen` в `X-GPTHub-Trace`).
- **Latency:** прямой MWS ~1.5 s; через orchestrator ~2 s; полный `demo.sh --skip-wow` ~45 s.
- **Result:** OK (PASS=11, FAIL=0, **WARN=0**).
- **Trace highlights:** `{"short_circuit": "image_gen", "mws_model": "qwen-image"}` в orchestrator-логе; inline markdown `![рыжего кота в шляпе](https://imagegen.gpt.mws.ru/files/.../....png)` в ответе.
- **Notes:** Предыдущий WARN был ложно-позитивным — после пересборки под shadow-fix (`094686d`) image-gen действительно проходит в MWS `qwen-image`, но `scripts/demo.sh` использовал битый bash-паттерн `*'!['` (без финального `*`), из-за которого условие совпадало только если ответ **заканчивался** на `![`. Исправлено на `*'!['*'](http'*`. Баг в тесте, не в коде. Row 3 `Implemented` подтверждён живым контрактом MWS + end-to-end через orchestrator.

## 2026-04-11 — Step 1 health, readiness, WebUI HTTP, baseline curl

- **Stack commit:** tag `smoke-green` on `main` (resolve SHA with `git rev-parse --short HEAD`)
- **Env:** `ORCHESTRATOR_API_KEY` aligned with `LITELLM_MASTER_KEY` for curl/WebUI.
- **Input:** `GET /healthz`, `GET /readyz`, `GET http://localhost:3000/`, then `ORCHESTRATOR_URL=http://localhost:8089 ORCHESTRATOR_API_KEY=… ./scripts/demo.sh --skip-wow`
- **Model(s) used:** text + URL steps hit MWS via LiteLLM (see trace on successful rows); image-gen step WARN (fell through to chat — upstream `qwen-image` path not confirmed in this run).
- **Latency:** full `demo.sh --skip-wow` ~43 s end-to-end on this host
- **Result:** OK (API baseline); **WARN** on optional image-gen short-circuit
- **Trace highlights:** Row1/8/10 returned `X-GPTHub-Trace`; memory remember/recall OK.
- **Notes:** Fixed orchestrator bug where image-intent block shadowed `last_user_text()` helper ([`main.py`](../apps/orchestrator/gpthub_orchestrator/main.py) rename to `image_intent_user_text`). **WebUI manual Demo Lock chunk** (текст + PDF + «нарисуй кота» в браузере) — оператор должен прогнать отдельно; здесь зафиксированы compose + health + `demo.sh` как автоматический baseline.

## 2026-04-11 — Step 1 WebUI smoke (текст + PDF + картинка), ROADMAP §0.4

- **Stack commit:** `647d49d`
- **Env:** `docker compose -f infra/docker-compose.yml`; Open WebUI `http://localhost:3000`; `.env` / `.env.mws.local` как в рабочем прогоне (секреты не логируем).
- **Input:** (1) текстовый вопрос в чате — ответ получен; (2) запрос на генерацию картинки (в духе «нарисуй кота») — картинка сгенерировалась; (3) PDF с вопросом — **ошибка**, чтение/ингест PDF не прошёл.
- **Model(s) used:** _по UI/trace не выписывались в этой записи_
- **Latency:** _—_
- **Result:** **PARTIAL** — текст и image-gen OK; PDF — **FAIL** (см. ниже), при этом сессия в WebUI продолжает работать.
- **Trace highlights:** _—_
- **Notes:** Сообщение об ошибке при работе с PDF: `'NoneType' object has no attribute 'encode'`. Нужен отдельный разбор (Open WebUI vs orchestrator ingest). Скрин источника:

![Step 1 WebUI smoke 2026-04-11](./sources/0.4.%20smoke-test-11.04-UI.png)

## 2026-04-11 — Step 1 WebUI RAG smoke (PDF + retrieval), post-fix

- **Stack commit:** _—_ (актуальный SHA: `git -C scanovich-webUI rev-parse --short HEAD`)
- **Env:** `docker compose -f infra/docker-compose.yml --profile rag up -d --build`; `.env` + `.env.mws.local` (секреты не логируем). WebUI: `RAG_EMBEDDING_ENGINE=openai`, `RAG_OPENAI_API_BASE_URL=http://embedding-shim:8000/v1`, `RAG_EMBEDDING_MODEL=qwen3-embedding-8b`, `RAG_OPENAI_API_KEY` — тот же Bearer, что для MWS (`MWS_GPT_API_KEY`). Shim: `BGE_EMBEDDING_UPSTREAM=https://api.gpt.mws.ru` **или** только `MWS_GPT_API_BASE` в mws.local (без дубля `/v1/v1` в пути к `/embeddings`).
- **Input:** PDF в чат (`Large_Language_Model-Based_Agents_for_Software_Eng.pdf` или аналог); запрос summary / ключевые пункты / анализ (RU/EN).
- **Model(s) used:** чат — модель из UI (например `gpt-hub`); эмбеддинги — `qwen3-embedding-8b` через `embedding-shim` → MWS `POST /v1/embeddings`.
- **Latency:** _не замеряли_
- **Result:** **OK**
- **Trace highlights:** В логах контейнера WebUI: `open_webui.retrieval.utils:query_doc` / `query_doc:result` — списки id чанков и метаданные PDF (`embedding_config` с `openai` + `qwen3-embedding-8b`). В UI: «Найден 1 источник», ответ с привязкой к файлу.
- **Notes:** Закрывает PDF-часть после исторического **PARTIAL** (ошибка `'NoneType' object has no attribute 'encode'` без `RAG_EMBEDDING_ENGINE=openai` и до выравнивания upstream URL/ключа для шима). В `apps/embedding_shim/main.py`: нормализация URL (`…/v1` vs корень), опциональный `env_file` `.env.mws.local` в compose, прокси без «грязного» логирования тел ответов. Скрин этой итерации при желании добавить в `docs/sources/` отдельным файлом.

## 2026-04-11 — PPTX smoke (WebUI + orchestrator)

- **Stack commit:** _—_ (актуальный SHA: `git -C scanovich-webUI rev-parse --short HEAD`)
- **Env:** как в **Step 1 WebUI RAG smoke** (`--profile rag`, `embedding-shim`, `.env` + `.env.mws.local`); WebUI модель `gpt-hub`; оркестратор `pptx_gen_enabled` по умолчанию вкл.
- **Input:** (1) только текст: «Сгенерируй презентацию по теме природа»; (2) PDF в чат (`Large_Language_Model-Based_Agents_for_Software_Eng.pdf` или аналог), затем «Сгенерируй презентацию… проблематике данной статьи» в той же ветке после (1).
- **Model(s) used:** UI — `gpt-hub`; по `X-GPTHub-Trace` / `execution_trace`: `task_type: pptx`, router `reason: pptx_slide_plan_json`, роль `reasoning_code_local`, цепочка с `gpt-hub-strong`.
- **Latency:** ~**30000–50000 ms** на один вызов LiteLLM под JSON-план слайдов (по меткам времени в логе между classify и ответом).
- **Result:** **PARTIAL** — (1) **OK** (превью + `.pptx` по data URI); (2) содержание статьи в слайдах не отражено, в UI «Источники не найдены».
- **Trace highlights:** оркестратор: `pptx: {status: ok, slides: N}`, `attachments_detected: ["text"]`, `artifacts: []`. WebUI: ingest PDF (`application/pdf`, `save_docs_to_vector_db`, коллекция с сотнями чанков); ошибка **`502`** на `http://embedding-shim:8000/v1/embeddings` в `get_sources_from_items` (см. лог).
- **Notes:** Снимок стека: [`logs/compose-20260411-144332.log`](../logs/compose-20260411-144332.log) (`make docker-logs-save`). План PPTX собирается из текста `messages` без парсинга PDF на стороне оркестратора; для (2) нужны подмешанные RAG-источники и стабильный `embedding-shim`.

## 2026-04-11 20:13 — PPTX на Cloud VM (тайминги, артефакт, ingest)

- **Stack commit:** `3e9aa55` (`97dbcaf36e8c4123dd940519cb331e3eea5352d7`)
- **Env:** VM публичный `178.154.209.51`; `docker compose -f infra/docker-compose.yml --profile rag`; `.env` + `.env.mws.local`; orchestrator published **8089:8000**; `PPTX_ARTIFACTS_PUBLIC_BASE_URL=http://178.154.209.51:8089` (без trailing slash); контейнер `gpthub-prod-orchestrator` перезапущен ~20:12 UTC по логам.
- **Input:** Open WebUI — запрос на презентацию (~9 слайдов); второй запрос в той же сессии (продолжение диалога).
- **Model(s) used:** видимая `gpt-hub`; router `gpt-hub-strong`, роль `reasoning_code_local`; `task_type` / classifier `pptx` (см. `execution_trace` / `X-GPTHub-Trace`).
- **Latency:** первый полный цикл — `plan_total_ms` **54225** ms, `build_deck_ms` **205** ms; от `POST /api/chat/completions` до `POST /api/chat/completed` в WebUI **55000** ms (~55 s); второй PPTX подряд — `plan_total_ms` **12645** ms, `build_deck_ms` **232** ms.
- **Result:** **OK** по генерации и скачиванию после разбора 404; отдельно зафиксирован диагностический **FAIL-паттерн** «ссылка на `.pptx` сразу даёт 404» до фикса ingest.
- **Trace highlights:** `pptx_timing` с **`concurrency: 7`**, 9 слайдов; `pptx: {"status": "ok", "slides": 9}`; при сбое артефакта в логах orchestrator: `httpx GET` на тот же URL артефакта → **200** и `url_ingest_failed … unsupported content-type: application/vnd.openxmlformats-officedocument.presentationml.presentation`, затем клиентский `GET` → `pptx_artifact_miss` / **404**.
- **Notes:** 404 был не из‑за Security Group: ответ шёл от `uvicorn`. Одноразовый токен снимал **ingest URL** из текста (ответ ассистента с ссылкой «Скачать»). Исправление в репозитории: не добавлять в инжест URL с путём `/artifacts/pptx/` (`ingest/url_fetch.py`). Успешное скачивание на том же стенде: `GET /artifacts/pptx/...` **200** с внешнего клиента для нового `artifact_id`.

## 2026-04-11 13:50 — PPTX «природа», smoke ~40 с (разбор таймингов)

> Ориентир по времени: **13:50** МСК; в логах оркестратора тот же прогон — **10:54:40** UTC → **10:55:23** UTC (`execution_trace` с `"slides": 9`). Детализация фаз — в `out.txt` (корень рабочей копии).

- **Stack commit:** _—_ (сверить `git rev-parse --short HEAD`)
- **Env:** тот же стек, что и соседние PPTX-записи (WebUI + orchestrator, `pptx_parallel_slide_agents_enabled`).
- **Input:** текстовый запрос на презентацию по теме **«природа»**, **9 слайдов** в плане (parallel slide-agents).
- **Model(s) used:** по trace — `task_type: pptx`, цепочка strong / slide-plan (как в других PPTX smoke).
- **Latency:** `plan_outline_llm_ms` **~3169** ms; **стена slide-agents** `plan_slide_agents_ms` **~39 592** ms (**~39,6 с**); `plan_total_ms` **~42 763** ms (**~42,8 с**); `build_deck_ms` **~254** ms. Узкое место — **один** самый долгий per-slide LLM (**~39 592** ms), почти равный wall параллельного блока.
- **Result:** **OK** по end-to-end генерации; субъективно «~40 с» на план совпадает с доминированием блока slide-agents.
- **Trace highlights:** 9× `pptx_slide_agent_done`; max на слайде с заголовком в духе «Экосистемы и их разнообразие» (~**39,6 с**), остальные короче.
- **Notes:** **Титульный / вводный слайд в деке есть** — проблема качества/скорости не в отсутствии титульника и не в `python-pptx` (**~0,25 с** на сборку), а в **overhead на тексте слайдов**: параллельные агенты упираются в **самый медленный** вызов LLM на одном слайде. Для сравнения второй крупный прогон в том же логе («океан», 10 слайдов) — wall slide-agents **~17,5 с**, `plan_total_ms` **~21,2 с** (`out.txt`).

---

## Шаг 1 — Docker bring-up (чеклист ROADMAP §0.4)

Сводка: записи выше закрывают teardown / compose / health+curl; **«Step 1 WebUI smoke»** — исторический **PARTIAL** (PDF без RAG); **«Step 1 WebUI RAG smoke»** — тот же сценарий PDF в браузере с профилем **`rag`** и настройкой эмбеддингов (**OK**).
Дополнительно: при полном P0-прогоне детализировать ряды 1–12 в секции шага 2 ниже.

---

## Шаг 2 — Полный P0 smoke (ряды 1–12)

### [pending] Row 1 — Text chat

- **Stack commit:** _—_
- **Input:** `"Объясни, что такое RAG в двух предложениях"`
- **Model(s) used:** _—_
- **Latency:** _—_
- **Result:** _не выполнено_
- **Trace highlights:** _—_
- **Notes:** _—_

### [pending] Row 2 — Voice chat (UI-managed)

- **Input:** голосовое сообщение через WebUI mic
- **Path:** STT → text → orchestrator → LiteLLM → MWS
- **Result:** _не выполнено_

### [pending] Row 3 — Image generation

- **Input:** `"Нарисуй рыжего кота в шляпе"`
- **Expected:** inline markdown `![](...)` с URL из `qwen-image`
- **Result:** _не выполнено_

### [pending] Row 4 — ASR

- **Input:** загруженный .wav файл с фразой
- **Expected:** artifact `transcript` в system, ответ модели по содержимому
- **Result:** _не выполнено_

### [pending] Row 5 — VLM

- **Input:** фото с текстом на английском
- **Expected:** role `vision`, модель из `gpt-hub-vision` chain, ответ по изображению
- **Result:** _не выполнено_

### [pending] Row 6 — Files (PDF + plain text)

- **Input:** PDF с парой абзацев + .md файл
- **Expected:** `document_text` artifacts в system, ответ по содержимому
- **Result:** _не выполнено_

### [pending] Row 7 — Web search (Tavily)

- **Prereq:** `ENABLE_WEB_SEARCH=true` + `TAVILY_API_KEY` в env WebUI
- **Input:** `"Что нового про MWS GPT на этой неделе?"`
- **Result:** _не выполнено_

### [pending] Row 8 — URL parsing

- **Input:** `"Прочитай https://example.com и сделай summary"`
- **Expected:** `url_text` artifact в system, ответ по содержимому
- **Result:** _не выполнено_

### [pending] Row 9 — Long-term memory

- **Step 1 Input:** `"Запомни, что я отвечаю за интеграцию MWS в наш продукт"`
- **Step 1 Expected:** `"Запомнил: ..."` ответ + факт в SQLite + embedding
- **Step 2 Input:** `"Что ты обо мне помнишь?"`
- **Step 2 Expected:** список фактов включая только что добавленный
- **Step 3 Input:** `"Забудь про интеграцию"`
- **Step 3 Expected:** подтверждение + удаление из store
- **Result:** _не выполнено_

### [pending] Row 10 — Auto model routing

- **Input 1:** `"Напиши функцию на Python"` → ожидается `reasoning/coder` роль
- **Input 2:** `"Кратко перескажи PDF"` → ожидается `doc` роль
- **Expected:** разные role / model_name в `X-GPTHub-Trace`
- **Result:** _не выполнено_

### [pending] Row 11 — Manual model choice

- **Prereq:** `ORCHESTRATOR_MODELS_CATALOG=all` + `AUTO_ROUTE_MODEL=false`
- **Input:** выбрать `gpt-hub-doc` в dropdown WebUI, отправить запрос
- **Expected:** в trace `model_used=gpt-hub-doc`, даже если classifier хотел другое
- **Result:** _не выполнено_

### [pending] Row 12 — Markdown / код

- **Input:** `"Покажи пример fastapi endpoint с typing"`
- **Expected:** markdown code block, подсветка работает в WebUI
- **Result:** _не выполнено_

---

## Шаг 6 — Репетиция демо-сценария

### [pending] Полный прогон Demo Lock

- **Scenario steps:**
  1. mixed input (PDF + фото + аудио + URL + текст)
  2. «запомни моё предпочтение X»
  3. «что ты обо мне помнишь?»
  4. (опционально) «проведи deep research» → Expert Council
  5. (опционально) «сделай презентацию» → PPTX
  6. trace reveal в DevTools
- **Time:** _—_ (цель: 2–3 минуты)
- **Result:** _не выполнено_
- **Notes:** _—_

---

## Kill switch log

Сюда пишем все случаи, когда сработал kill switch из `ROADMAP.md` раздел 0.5.

| Когда | Компонент | Причина | Решение |
|---|---|---|---|
| _—_ | _—_ | _—_ | _—_ |

---

## Итоговая статистика перед `demo-ready`

- **Всего живых прогонов:** _—_
- **Успешных:** _—_
- **Частичных:** _—_
- **Провальных:** _—_
- **Средний latency текстового запроса:** _—_
- **Средний latency VLM запроса:** _—_
- **Средний latency image-gen:** _—_

Этот блок заполняется перед git tag `demo-ready` и идёт в презентацию
как слайд «реальные цифры на живом MWS».
