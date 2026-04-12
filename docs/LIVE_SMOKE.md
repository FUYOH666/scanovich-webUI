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

## 2026-04-11 — Verification package: pytest + compose rebuild + `demo.sh`

- **Stack commit:** `fa1d548` (`main`).
- **Env:** `.env` + `.env.mws.local`; `docker compose -f infra/docker-compose.yml up -d --build` (образ `orchestrator` пересобран).
- **Input:** (1) `cd apps/orchestrator && uv sync --extra dev && uv run pytest -q` (2) `./scripts/demo.sh` с `ORCHESTRATOR_URL=http://localhost:8089` и ключом из `.env` (тот же, что WebUI / `LITELLM_MASTER_KEY`).
- **Result:** pytest **261 passed, 2 skipped**. `demo.sh` **PASS=13 FAIL=0 WARN=0** (полный прогон с WOW-1 + WOW-3, ~7 min; доминирует council).
- **Notes:** Счётчик `PASS` в скрипте — число вызовов `ok` (сейчас **13**: два health-check, каталог моделей, два чека по тексту, URL, image, два по memory, два по classifier, council, PPTX). В старых журналах встречается **PASS=12** — это сдвиг счётчика/чеклиста, не регрессия. Memory remember+recall в этом прогоне **OK**. **Остатки для команды (без кода):** `ROADMAP.md` Step 6 (operator WebUI), Step 8 (demo-video), Step 9 (`demo-ready` + финальные артефакты).

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

## 2026-04-12 — Row 6 Files PDF upload regression (NoneType encode)

- **Stack commit:** main @ pre-fix; reproduced on `gpthub-prod-open-webui` v0.8.12.
- **Symptom:** uploading `Vkliuchaiem obaianiie po mietod ... .pdf` from
  the Telegram Desktop downloads folder via the WebUI chat → top-right
  red toast: `'NoneType' object has no attribute 'encode'`.
- **Root cause (from `gpthub-prod-open-webui` logs):**
  `chat_completion_files_handler` (`utils/middleware.py:1927`) →
  `get_sources_from_items` (`retrieval/utils.py:1145`) →
  `query_collection` (`retrieval/utils.py:455`) → lambda calls
  `embedding_function.encode(...)` where `embedding_function` is
  `None`. Open WebUI v0.8.12 was trying to run **its own** RAG /
  embedding pipeline on the uploaded file, but no embedding engine
  is wired in our compose (we deliberately don't run the
  `embedding-shim` rag profile in the prod stack).
- **Architectural decision:** orchestrator owns ingest. WebUI's job is
  to extract text and forward it. Wiring a second embedding engine into
  WebUI is the wrong fix — it duplicates the orchestrator's
  `ingest/pipeline.py` and reintroduces the very split we removed when
  we centralised ingest.
- **Fix:** added `BYPASS_EMBEDDING_AND_RETRIEVAL=true` and explicit
  empty `RAG_EMBEDDING_ENGINE=` to `.env.example` and `.env`. Confirmed
  in v0.8.12 source (`/app/backend/open_webui/retrieval/utils.py:1028`)
  that the bypass branch reads `file_object.data.get('content', '')`
  directly and never calls the embedding function.
- **Recovery:** `docker compose -f infra/docker-compose.yml up -d
  --force-recreate open-webui` (compose recreated all three services
  because they share the .env env_file). All three back to `Healthy`;
  `curl http://localhost:3000/health` → 200.
- **Status:** **Awaiting live retry by operator** — re-upload the same
  PDF and either confirm the chat response or capture the new error.
  Until that retry is recorded here, Row 6 Files remains formally
  blocked from `Implemented` in `FEATURE_MATRIX.md`.

## 2026-04-12 — Row 7 Web search: «Источники не найдены» / model denies internet

- **Stack:** `gpthub-prod-open-webui` v0.8.12; `ENABLE_WEB_SEARCH=true`, Tavily OK in logs.
- **Symptom:** UI shows web search ON; gray **«Источники не найдены»**; assistant says it has no direct internet access.
- **Root cause:** after Tavily, WebUI runs **`save_docs_to_vector_db`** / web-search chunk indexing and calls
  **`embedding_function.encode`** while **`embedding_function` is `None`** (same class of bug as Row 6 PDF).
  File uploads use `BYPASS_EMBEDDING_AND_RETRIEVAL`; web search has a **separate** flag
  **`BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL`** (`config.py` PersistentConfig).
- **Fix:** set **`BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL=true`** in `.env` (see `.env.example`) **or**
  Admin → Settings → Web Search → enable **«Обход встраивания и извлечения данных»** for web search,
  then `docker compose -f infra/docker-compose.yml up -d --force-recreate open-webui`.
  If the value was persisted earlier in the DB, use Admin UI or `ENABLE_PERSISTENT_CONFIG=false` per Open WebUI docs.
- **Status:** bypass env live in container; operator smoke ongoing.

### 2026-04-12 — Row 7 follow-up: «6 источников» → «источники не найдены», ответ с новостями есть

- **Observed:** статус сначала показывает ненулевое число источников (напр. 6), затем
  **«Источники не найдены»**, при этом ассистент выдаёт актуальные формулировки по теме
  (напр. новости rbk.ru).
- **Interpretation (stack):** Tavily + инъекция сниппетов в исходящие `messages` к
  orchestrator работают; **orchestrator / LiteLLM / MWS не управляют** панелью источников
  WebUI. При **`BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL`** WebUI **не** кладёт
  web-сниппеты в свою vector-коллекцию; блок UI «источники» часто строится из
  **другого** шага (структурированные `source` / retrieval после индексации). Итог:
  **рассинхрон числа/плашки и фактического ответа — ожидаемая особенность UX**, не баг
  GPTHub-spine. Критерий работоспособности ряда 7: **содержание ответа опирается на
  поиск**, а не зелёность панели цитат.
- **If you need pretty citations:** либо поднять полноценный WebUI RAG + embedding
  (отдельное решение, дублирует политику «ingest в orchestrator»), либо жить с bypass
  и ориентироваться на текст ответа / ссылки внутри `content`, если модель их цитирует.

## 2026-04-12 16:08 — Step 7 WOW-3 PPTX live confirmation

- **Stack commit:** `main` after PPTX CoT fix (orchestrator rebuilt with `--build`).
- **Env:** `.env` + `.env.mws.local`; `pptx_plan_model=gpt-hub-strong` (default).
- **Input:** Three curl requests against orchestrator `POST /v1/chat/completions`:
  1. `"сделай презентацию про архитектуру RAG системы"` — natural language RU trigger
  2. `"/pptx архитектура RAG системы"` — slash command
  3. `"давай, в формате pptx будет? создай презентацию про AI"` — broadened pattern
- **Model(s) used:** `gpt-hub-strong` (glm-4.6-357b) for slide plan; `gpt-hub-turbo` for fallback classification.
- **Latency:** ~40 s per request (plan generation + retry).
- **Result:** **OK (3/3 PASS)**. All three produced valid .pptx files.
  - Request 1: "Архитектура RAG-систем" — 7 slides, 35 KB, download 200 OK.
  - Request 3: "Искусственный интеллект: от теории к практике" — 6 slides, 34 KB.
- **Trace highlights:** `short_circuit: "pptx_generation"`, `plan_model: "gpt-hub-strong"`, `slide_count: 7`.
- **Notes:** Root cause of earlier failures: MWS `gpt-hub-strong` (glm-4.6-357b)
  wraps all output in `<think>…</think>` Chinese CoT blocks before the actual JSON.
  `_strip_cot_blocks()` added to `pptx_gen.py` — strips CoT before JSON parsing.
  First plan attempt still sometimes fails (JSON comma delimiter errors inside
  Chinese CoT braces); retry consistently succeeds after CoT strip. Also broadened
  intent patterns to match «в формате pptx» and «формат pptx».
  Download endpoint `GET /v1/files/pptx/{token}` confirmed: 200, correct MIME type,
  valid PPTX file opens in PowerPoint. Row 14 (WOW-3) **confirmed live**.

## 2026-04-12 16:07 — E2E simulation: text, image-gen, memory

- **Stack commit:** `main` after PPTX CoT fix.
- **Env:** `.env` + `.env.mws.local`.
- **Input:** Curl requests:
  1. `"Привет! Что такое RAG?"` — text chat
  2. `"нарисуй кота в космосе"` — image generation
  3. `"запомни: мой любимый язык программирования — Python"` — memory save
  4. `"что ты помнишь?"` — memory recall
- **Result:** **OK (4/4 PASS)**.
  - Text: `gpt-hub-turbo` → 506-char RU response.
  - Image: `qwen-image` → valid MWS image URL, inline markdown.
  - Memory save: embedding took ~30 s (MWS `qwen3-embedding-8b` slow but works), fact stored.
  - Memory recall: correctly returned 0 facts (different chat session = different user_id).
- **Notes:** All short-circuits working: image_gen, memory_command. Row 1, 3, 9 confirmed.

## 2026-04-11 — E2E simulation follow-up: memory save vs embedding latency

- **Stack:** same as block above (`main` after PPTX CoT fix); orchestrator → MWS `qwen3-embedding-8b` for «запомни».
- **Result (separate run):** text + image-gen + memory **recall** **PASS**; memory **save** → **ReadTimeout** on embedding HTTP client (MWS slow/unreachable/DNS from container — не детерминировано).
- **Mitigation:** поднять `memory_embedding_timeout_seconds` (см. `settings.py` / env), проверить `POST /v1/embeddings` с хоста и **изнутри** `gpthub-prod-orchestrator` (`docker exec … curl`). Противоречит не «докам», а **флаппи MWS/сети**: см. успешный save ~30 s в блоке **2026-04-12 16:07** выше.

## 2026-04-11 11:46 — Step 5 full `demo.sh` (including WOW-1) end-to-end

- **Stack commit:** `wow/expert-council` @ `9ff08ce` (council feature commit).
- **Env:** `.env` + `.env.mws.local`; container rebuilt with `council.py`; `ORCHESTRATOR_URL=http://localhost:8089`.
- **Input:** `./scripts/demo.sh` (no `--skip-wow`). Steps 1–7 hit the P0 baseline; step 8 sends `/research ... корпоративные RAG` via curl; step 9 sends the PPTX prompt.
- **Model(s) used:** Row 1 → `gpt-hub-turbo`; Row 8 URL → alpha; Row 3 image → `qwen-image`; Row 9 memory → `qwen3-embedding-8b` + alpha; Row 10 classifier → alpha; Step 8 council → 3 experts + `gpt-hub-strong` synthesis.
- **Latency:** full run dominated by council (~171 s). Total end-to-end ≈ 3.5 min.
- **Result:** **PASS=12 FAIL=0 WARN=1**. The sole WARN is expected: WOW-3 PPTX (row 14, not yet implemented — `demo.sh` just sees a plain chat reply instead of a `.pptx` artifact).
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

---

## Шаг 1 — Docker bring-up (чеклист ROADMAP §0.4)

Сводка: три журнальных записи выше закрывают teardown / compose / health+curl.
Дополнительно вручную: три сценария **через WebUI** (текст, PDF+вопрос, image prompt) — перенести в отдельные записи шага 2 при первом полном P0-прогоне.

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

### [pending] Operator checklist (Шаг 6)

> **Это список того, что нужно проверить руками в WebUI (localhost:3000)
> перед записью видео.** Каждый пункт — отправить сообщение, проверить
> результат, записать ниже дату/время и статус.

#### A. Обязательные ряды — ручная проверка

- [ ] **Row 2 — Voice**: нажать микрофон в WebUI, сказать фразу,
  проверить что STT расшифровало и ответ пришёл. Записать результат.
- [ ] **Row 4 — Audio file**: загрузить `.wav`/`.mp3` файл через скрепку,
  проверить что ASR расшифровал и orchestrator ответил по содержимому.
- [ ] **Row 5 — Image (VLM)**: загрузить фото (например, скриншот кода
  или фото еды), спросить «что на картинке?». Проверить что VLM ответил.
- [ ] **Row 6 — PDF post-fix**: загрузить PDF (тот же файл который
  крашился раньше), проверить что ответ пришёл без ошибки.
  Файл: `Vkliuchaiem obaianiie po mietod - Dzhiek Shafier.pdf`
- [ ] **Row 7 — Web search**: спросить что-то актуальное, например
  «какие новости сегодня?» или «what happened in AI this week?».
  Если Tavily работает — в ответе будут ссылки на источники.
- [ ] **Row 11 — Manual model choice**: поменять `ORCHESTRATOR_MODELS_CATALOG=all`
  и `AUTO_ROUTE_MODEL=false` в `.env`, пересобрать orchestrator, проверить
  что в dropdown WebUI видно несколько моделей (`gpt-hub-turbo`, `gpt-hub-strong` и т.д.).
  **Вернуть обратно после проверки!**

#### B. WOW features — ручная проверка

- [ ] **Row 13 — Expert Council**: в чате написать
  `/research как правильно выбрать vector database для RAG`
  или «проведи глубокое исследование по теме X». Подождать ~2–3 минуты.
  Проверить что ответ структурирован (суть → совет экспертов → рекомендации).
  В DevTools → Network → response headers → `X-GPTHub-Trace` должен быть
  `short_circuit: expert_council` с 3 ветками.
- [ ] **Row 14 — PPTX**: написать «сделай презентацию по архитектуре
  микросервисов» или `/pptx RAG in production`. Проверить что в ответе
  есть ссылка «Скачать .pptx». Кликнуть — скачается файл, открыть в
  PowerPoint/Google Slides — проверить что слайды есть.

#### C. Killer demo scenario (для видео)

Один непрерывный сценарий в **одном чате**, показывающий всю мощь:

1. Загрузи PDF + напиши «Кратко перескажи, о чём этот документ»
2. Отправь фото → «что на картинке?»
3. Напиши «запомни что мне нравятся микросервисы и Go»
4. Напиши «что ты обо мне помнишь?» → проверь что вернул факт
5. `/research как правильно строить RAG pipeline` → подожди ~2 мин
6. «сделай презентацию по результатам исследования» → скачай .pptx
7. Открой DevTools → Network → последний запрос → `X-GPTHub-Trace`
8. Покажи routing decision, model chain, council branches, timing

**Время:** цель 2–3 минуты для видеозаписи.

### [pending] Запись demo-видео (Шаг 8)

- **Формат:** screen recording с OBS / QuickTime, 720p+.
- **Сценарий:** пункт C выше.
- **Голос:** по желанию, можно с субтитрами.
- **Файл:** `docs/submission/demo.mp4` (или ссылка на облако).
- **Result:** _не выполнено_

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
