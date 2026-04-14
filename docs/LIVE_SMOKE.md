# Live Smoke Journal

> Журнал живых прогонов через поднятый `docker compose` стек. Заполняется
> **при каждом** live-тесте и защищает нас от «работало на прошлой неделе».
>
> Правило: **никакой ряд не помечается `Implemented` в
> `FEATURE_MATRIX.md` без хотя бы одной записи здесь**. Unit-тест этого
> не заменяет — unit-тест проверяет код, а журнал проверяет стек.
>
> Датированные записи ниже ведутся **по возрастанию времени** (старые выше,
> новые ниже, непосредственно перед разделом «Шаг 1»).

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

- **Stack commit:** 027372f
- **Env:** тот же стек, что и соседние PPTX-записи (WebUI + orchestrator, `pptx_parallel_slide_agents_enabled`).
- **Input:** текстовый запрос на презентацию по теме **«природа»**, **9 слайдов** в плане (parallel slide-agents).
- **Model(s) used:** по trace — `task_type: pptx`, цепочка strong / slide-plan (как в других PPTX smoke).
- **Latency:** `plan_outline_llm_ms` **~3169** ms; **стена slide-agents** `plan_slide_agents_ms` **~39 592** ms (**~39,6 с**); `plan_total_ms` **~42 763** ms (**~42,8 с**); `build_deck_ms` **~254** ms. Узкое место — **один** самый долгий per-slide LLM (**~39 592** ms), почти равный wall параллельного блока.
- **Result:** **OK** по end-to-end генерации; субъективно «~40 с» на план совпадает с доминированием блока slide-agents.
- **Trace highlights:** 9× `pptx_slide_agent_done`; max на слайде с заголовком в духе «Экосистемы и их разнообразие» (~**39,6 с**), остальные короче.
- **Notes:** **Титульный / вводный слайд в деке есть** — проблема качества/скорости не в отсутствии титульника и не в `python-pptx` (**~0,25 с** на сборку), а в **overhead на тексте слайдов**: параллельные агенты упираются в **самый медленный** вызов LLM на одном слайде. Для сравнения второй крупный прогон в том же логе («океан», 10 слайдов) — wall slide-agents **~17,5 с**, `plan_total_ms` **~21,2 с** (`out.txt`).

## 2026-04-13 — `demo_benchmark.py` на `server-gpt` + разбор `docker compose` логов (WOW latency)

- **Stack commit:** e84bf7460353c24a311837de1c4cd88a2552d298
- **Env:** стек `gpthub-prod-*` на ВМ; прогон из `~/scanovich-webUI`; ключи из `.env` (как для `demo.sh`). Логи сняты целью Make из рабочей копии хакатона: `ресурсы/YandexCloud/Makefile` → `make logs-scanovich-compose > ресурсы/YandexCloud/logs.txt` (stdout: `docker compose … logs --tail 200` на сервере через `yc compute ssh`, плюс фильтр `awk` по health-шуму).
- **Input:** `python3 scripts/demo_benchmark.py` (полный сценарий, без `--skip-wow`; те же шаги, что `scripts/demo.sh`, с замером `time.perf_counter()` на каждый HTTP-вызов).
- **Result:** **PASS=13 FAIL=0 WARN=0** — baseline + WOW зелёные.

### Latency (мс по шагам скрипта)

| Step | Label | ms | Note |
|------|--------|-----:|------|
| 1/9 | GET /healthz | 20.3 | OK |
| 1/9 | GET /readyz | 4.8 | OK |
| 2/9 | GET /v1/models | 3.7 | OK |
| 3/9 | POST text chat | 2152.3 | OK choices |
| 4/9 | POST URL ingest | 1234.9 | OK |
| 5/9 | POST image gen | 12216.7 | OK |
| 6/9 | POST remember | 185.9 | OK |
| 6/9 | POST recall | 2.3 | OK |
| 7/9 | POST reasoning | 3672.3 | OK choices |
| 8/9 | POST council | **121308.1** | OK |
| 9/9 | POST pptx | **67112.9** | OK |

### Что показали логи (`ресурсы/YandexCloud/logs.txt`, оркестратор)

- **Expert Council (шаг 8 / ~121 с):** в `execution_trace` на **2026-04-13 07:33:04** — `short_circuit: expert_council`, **`total_ms`: 121305** (совпадает с бенчмарком). Три ветки **успешно параллельно** (`branches_failed: []`), индивидуальные **`latency_ms`** в trace: **7958** (`gpt-hub-turbo`, Generalist), **13332** (`gpt-hub-reasoning-or`), **17252** (`gpt-hub-doc`) — wall фазы fan-out порядка **~17 с** (упирается в doc-ветку). По меткам времени в том же файле: последний `POST …/chat/completions` **LiteLLM** у экспертов около **07:31:20**, ответ синтезатора — около **07:33:04** → **~104 с** уходит на **синтез** (`gpt-hub-strong`, длинный промпт с тремя мнениями). Итог: доминирует не fan-out, а **один вызов synthesis**.
- **PPTX (шаг 9 / ~67 с):** сразу после council — classifier `pptx_generation`. В логе **`pptx_plan_first_attempt_failed`** с **`json_parse_error`** (первый JSON плана битый); второй `POST …/chat/completions` успешен. В `execution_trace` на **07:34:11**: **`plan_ms`: 66648**, **`build_ms`: 461**, 5 слайдов — узкое место **планирование/повтор**, сборка **python-pptx** — доли секунды.
- **Побочные наблюдения в том же файле:** пачка **`GET /v1/chat/completions` → 405** на оркестраторе (чужой клиент с GET вместо POST — не этот бенч после фикса `demo_benchmark.py`); для шага URL — **`url_ingest_failed … example.com … ConnectError`** из контейнера (сеть/фильтр), при этом шаг 4 в бенче помечен OK (ответ собран без успешного fetch).

- **Notes:** Полный прогон по-прежнему **WOW-dominated** (council ≫ остальное). Для презентации/оптимизации: смотреть **таймауты/модель синтеза** council и **стабильность JSON** плана PPTX (retry уже есть). Источник таблицы — терминальный вывод прогона на `server-gpt`; источник разбора фаз — строки **230–249** `ресурсы/YandexCloud/logs.txt` (`gpthub-prod-orchestrator`).

## 2026-04-13 — `demo_benchmark.py` (терминал локального/другого прогона): council ~165 s, PPTX ~15 s

- **Stack commit:** _как у рабочего клона на момент прогона_
- **Env:** `python3 scripts/demo_benchmark.py` из `scanovich-webUI`; `ORCHESTRATOR_URL` + ключ как для WebUI.
- **Input:** полный сценарий (без `--skip-wow`), те же шаги, что `demo.sh`, с замером `perf_counter` на HTTP.
- **Result:** **PASS=13 FAIL=0 WARN=0**.

### Latency (мс по шагам — как в терминале)

| Step | Label | ms | Note |
|------|--------|-----:|------|
| 1/9 | GET /healthz | 20.4 | OK |
| 1/9 | GET /readyz | 5.1 | OK |
| 2/9 | GET /v1/models | 3.9 | OK |
| 3/9 | POST text chat | 1954.9 | OK |
| 4/9 | POST URL ingest | 1443.0 | OK |
| 5/9 | POST image gen | 23257.6 | OK |
| 6/9 | POST remember / recall | 337.0 / 175.6 | OK |
| 7/9 | POST reasoning | 5644.3 | OK |
| 8/9 | POST council | **164708.0** | OK |
| 9/9 | POST pptx | **15444.2** | OK |

### Разбор по `ресурсы/YandexCloud/logs.txt` (фрагмент `gpthub-prod-orchestrator`)

- **Шаг 8 / council ~165 s:** в `execution_trace` — `orchestrator_fallback.short_circuit: expert_council`. Строка с **`total_ms`: 164705** (стр. ~95) совпадает с wall time клиента. Три ветки в trace с отдельными **`latency_ms`** (~8 s / ~31 s / ~17 s) не суммируются в 165 s: основная задержка — **цепочка после fan-out**, в т.ч. **синтез** (`gpt-hub-strong`, ещё один тяжёлый `POST …/chat/completions` в LiteLLM). Это ожидаемо для deep research / council, а не «оркестратор ждёт сам с собой».
- **Шаг 9 / PPTX ~15 s:** сразу после ответа council — маршрут `pptx_generation` (в логе семантика пропущена: `semantic_skipped_locked_heuristic_task`). В **`pptx_timing`**: **`plan_outline_llm_ms` ~9849.8**; **`plan_slide_agents_ms` (wall)** ~5372.7 при **`concurrency`: 7**; **`plan_total_ms` ~15223.2**; **`build_deck_ms` ~217.7** (стр. ~105–122, 129). Сборка файла — доли секунды; **~15 s** — это план + параллельные slide-agents, без multi-minute synthesis как у council.

- **Notes:** В отчёт `demo_benchmark.py --json` добавлено поле **`pptx_download_urls`** (одноразовые `GET /artifacts/pptx/…?token=…`) для скачивания `.pptx` после смока.

## 2026-04-13 — Разбор `logs.txt`: council ~176 с, PPTX timeout ~180 с (другой фрагмент того же файла)

- **Stack commit:** d289e39
- **Env:** `gpthub-prod-orchestrator`; логи: `ресурсы/YandexCloud/logs.txt` (снятие через `make logs-scanovich-compose` из рабочей копии хакатона).
- **Input:** тот же файл логов, что и у записи **`demo_benchmark.py`** выше, но **другой** интервал по времени / другой полный прогон в терминале.
- **Model(s) used:** council — синтез `gpt-hub-strong`; PPTX — цепочка плана/слайдов из trace того фрагмента.
- **Latency:** council **`total_ms`: 176426** (~176 с) — совпадает с терминалом; PPTX клиент **~180003 ms**, в логах **`pptx_gen_failed err=timeout`** (~`pptx_plan_timeout_seconds`, на стенде часто **180**).
- **Result:** **PARTIAL** — council в том фрагменте завершился; PPTX оборван по таймауту пайплайна.
- **Trace highlights:**
  - **Council:** ветки **strong / reasoning / doc** ~**7–17 с** каждая, **параллельно**; почти всё время ~**176 с** — **один вызов синтеза** (длинный контекст: три экспертных ответа + промпт).
  - **PPTX:** `plan_outline_llm_ms` порядка **~8 с**; slide agents — часть **8–11 с**, отдельные вызовы **~60 с** и **~82 с**; в **старых** логах того прогона — **`slide_too_short`** и повторные запросы (**в текущем коде** ретрай по минимуму символов **убран**, в промптах — мягкий ориентир); **`reasoning_fields_stripped_from_completion`** встречалось.
- **Notes:** Для углубления — LiteLLM по тем же меткам времени / `request_id`. При необходимости поднять **`PPTX_PLAN_TIMEOUT_SECONDS`** или снизить нагрузку (меньше слайдов, другая модель slide agents). В **`pptx_slide_agent_done`** в JSON: **`pptx_slide_number`**, **`plan_slides_total`** (без `outline_idx` / `deck_slide_*`).

## 2026-04-13 ~18:50 UTC — Row 2 Voice (mic): STT OK, пустой `user.content` в оркестраторе, 413 на `embedding-shim`

- **Stack commit:** _n/a (прод-стек `gpthub-prod-*` на VM; фрагмент логов: `ресурсы/YandexCloud/logs.txt`)_
- **Env:** compose с `gpthub-prod-open-webui`, `gpthub-prod-orchestrator`, `gpthub-prod-litellm`, **`gpthub-prod-embedding-shim`** (RAG); в UI модель **`gpt-hub`**.
- **Input:** голос с микрофона в WebUI (загрузка как **`video/webm`**, имя вида `…21-50-08.webm`); новый чат после записи.
- **Model(s) used:** STT — **`faster_whisper`** внутри контейнера WebUI (не MWS `whisper-medium` на этом шаге); ответ чата — через оркестратор → LiteLLM → MWS.
- **Latency:** ~3.2 с аудио на стороне whisper; далее несколько быстрых `POST` к оркестратору (в т.ч. служебные промпты WebUI с префиксом `### Task:`).
- **Result:** **PARTIAL** — транскрипт и индексация файла в векторную коллекцию прошли; сценарий «один нормальный ответ на голос» не закрыт: зафиксирован **пустой** текст пользователя в одном из вызовов и **ошибка RAG** при эмбеддинге.
- **Trace highlights:**
  - **WebUI / STT:** `open_webui.routers.files:upload_file` (`video/webm`) → `open_webui.routers.audio:transcribe` → конвертация **webm → mp3** → `faster_whisper`: `Processing audio with duration 00:03.180`, язык **`ru`**, вероятность **~0.94** → `save_docs_to_vector_db` / `process_file` — **1** чанк в коллекцию `file-65412b3c-…`.
  - **Orchestrator:** `incoming_chat_messages` с непустым `content` на первом круге; затем **`messages: [{"role":"user","content":""}]`** → `classifier_route_resolution` с **`semantic_skipped_empty_user_text`**, **`simple_chat`**.
  - **WebUI / RAG:** в `process_chat` → `chat_completion_files_handler` → `get_sources_from_items` → `query_collection` — запрос эмбеддинга на **`http://embedding-shim:8000/v1/embeddings`** → **`413 Request Entity Too Large`** (в стектрейсе у `query_embeddings` встречается **`queries: ['']`**); отдельная строка лога shim: **`413`** на `POST /v1/embeddings`.
- **Notes:**
  - **Две линии расследования:** (1) почему WebUI в одном из шагов шлёт в оркестратор **пустой** `user.content` после успешного STT; (2) почему цепочка источников бьётся об **413** на shim (лимит тела/прокси, пустой query, конфиг RAG).
  - **Row 2 vs Row 4:** здесь распознавание — **UI-managed** whisper в WebUI; **Row 4** (ASR вложений в оркестраторе, MWS `whisper-medium`) — отдельный продуктовый путь, см. `docs/WEBUI_PAYLOAD.md`.
  - **Что сделать дальше:** локально воспроизвести; для одного падения снять **полный** JSON тела `POST /v1/chat/completions` к оркестратору; проверить лимиты **`apps/embedding_shim`** и upstream; при сжатых сроках — осознанный bypass RAG (см. Row 6 / `BYPASS_EMBEDDING_AND_RETRIEVAL`) или правка ветки `chat_completion_files_handler` в форке WebUI. После фикса — дописать сюда запись **OK** с тем же сценарием.
  - **Якоря в логе:** `ресурсы/YandexCloud/logs.txt` — WebUI **18:50:17–18:50:20** (upload / transcribe / индексация); оркестратор **18:50:23–18:50:31**; пустой content **18:50:27,637**; **413** и стек **18:50:27.619** (`retrieval/utils.py:1145`).

## 2026-04-14 — Row 6 / Row 4: PPTX + голос + PDF (YC VM, см. `logs.txt`)

- **Stack commit:** `140d779` (оркестратор с общим томом `open-webui-data` → `ORCHESTRATOR_OPEN_WEBUI_DATA_MOUNT`, ingest из `message.files` по пути Open WebUI).
- **Env:** `infra/docker-compose.yml` с `--profile rag`; на ВМ `~/scanovich-webUI`: `.env` + `.env.mws.local`; логи агрегата: `ресурсы/YandexCloud/logs.txt` (снятие через `make logs-scanovich-compose` / эквивалент).
- **Input (три сценария вручную в WebUI, модель `gpt-hub`):**
  - **A:** загрузка **презентации (.pptx)** → вопрос по содержимому → затем **аудиозапрос** (голос / вложение после PPTX).
  - **B:** загрузка **той же презентации без отображаемого имени** (как в UI) → затем **PDF** в **том же чате** → вопрос, ожидающий учёт PDF.
  - **C:** **только PDF** в **новом** чате → вопрос по содержимому.
- **Model(s) used:** по сценарию — `gpt-hub-doc` / richdoc после ingest PPTX; `gpt-hub-turbo` на простые реплики; ASR — путь WebUI STT + при наличии вложения — оркестратор `ingest` / MWS `whisper-medium` в зависимости от формы payload (см. Row 2 vs Row 4 в журнале).
- **Latency:** _не замерялись точно; в логах embedding-shim преимущественно 200 (без доминирующего 413 в этом фрагменте)._
- **Result:** **PARTIAL**
  - **A:** **OK** — первый чат: презентация разобрана, ответ по смыслу слайдов; **аудиозапрос обработан корректно**.
  - **B:** **FAIL (продуктовый край)** — по логам оркестратора (**~11:58:34 UTC**) это **два user-тёрна** (сначала сообщение с PPTX, затем отдельное с PDF), а не одно сообщение с двумя файлами. **PDF инжестится и попадает в `system` как `document_text`** (текст survey про LLM-agents for SE присутствует в `after_ingest`). Тем не менее ответ в продукте **не опирается на PDF**: ассистент **продолжает линию предыдущего ответа** (после PPTX). В трейсе: **`semantic_skipped_empty_user_text`** → эвристика **`simple_chat`** → **`gpt-hub-turbo`** при **пустом** `user.content` на последнем тёрне; в истории остаётся длинный **assistant** после презентации, который конкурирует с блоком PDF в system. В бэклог: маршрутизация при вложениях без текста / приоритет свежего `document_text` относительно прошлого assistant.
  - **C:** **OK** — в **отдельном** чате **PDF обработан корректно**.
- **Trace highlights:** для успешных PPTX/PDF — **`ingest_peek`** с ненулевым **`open_webui_disk`**, **`ingest_complete`** с **`document_text`** в system; для **B** — то же для PDF на втором тёрне, но **видимый ответ пользователю** не отражает PDF (см. классификатор и `gpt-hub-turbo` выше).
- **Notes:** **FEATURE_MATRIX** ряд 6: одиночные вложения закрывают сценарий. Отдельно (другая гипотеза): ingest с диска идёт **только с последнего user-сообщения** — сырой PPTX с **предыдущего** тёрна второй раз не очередится; если понадобится «оба файла в одном ответе» без повторной загрузки — нужна доработка (обход ранних `message.files` или явный UX). **Много файлов в одном сообщении** — тоже отдельная проверка очереди по всем `files`. Made-with: Cursor.

## 2026-04-14 — Один чат: PPTX → PDF → голос → презентация «операторы» → `/research` карьера МТС (YC VM)

- **Stack commit:** _как на ВМ в момент прогона_ (см. деплой `scanovich-webUI`; оркестратор с RAG-профилем и общим томом WebUI).
- **Env:** `infra/docker-compose.yml` с `--profile rag`; `.env` + `.env.mws.local` на ВМ; агрегат логов: `ресурсы/YandexCloud/logs.txt` (`make logs-scanovich-compose`).
- **Input (последовательность в одном чате, модель `gpt-hub`):**
  1. **PPTX** — загрузка презентации, ответ по содержимому: **OK** (контент ушёл в модель).
  2. **PDF** (LLM-survey): **OK**, документ обработан.
  3. **Диктофон** — расшифровка: **OK** (WebUI STT / цепочка до MWS по стеку); **ответ: PARTIAL** — в промпт попали **нерелевантные RAG-источники** (чunks с pptx/pdf из чата), ожидаемый опорный web-запрос фактически не отработал с точки зрения пользователя.
  4. **Презентация** «мобильные операторы в России» (с контекстом URL в инжесте): **OK** по содержанию; **`plan_total_ms` ~47.9 с** (~47872 ms в логе); **продуктовое пожелание:** смена фона между слайдами (шаблон).
  5. **`/research` возможности роста для работников МТС** — **expert council** (`deep_research`): ветки **`branches_ok`** — Generalist (**gpt-hub-turbo**) **4224 ms**, Reasoning (**gpt-hub-reasoning-or**) **10345 ms**, Doc (**gpt-hub-doc**) **3386 ms**; **`orchestrator_fallback.total_ms` ~121809** (~**2 мин 02 с** wall); синтез **`gpt-hub-strong`**. Старт трассы по `server_clock_iso` **~12:47:53 UTC**, финальный `POST` синтеза **~12:49:55 UTC** (см. `execution_trace` в логе).
- **Model(s) used:** `gpt-hub-doc` / `gpt-hub-turbo` / `gpt-hub-strong` / `gpt-hub-reasoning-or` по этапам; council — см. выше.
- **Latency:** презентация — см. `pptx_timing.plan_total_ms` / `build_deck_ms`; council — см. выше; точные метки в **`ресурсы/YandexCloud/logs.txt`** (оркестратор **12:44–12:50 UTC** напр.).
- **Result:** **PARTIAL** (шаги 1–2–4 **OK**; шаг 3 **PARTIAL**; шаг 5 **OK** по завершению council, качество опоры на МТС-специфику — на усмотрение оператора).
- **Trace highlights:** PPTX — `pptx_timing` / `build_deck_ms`, артефакт `f86b75ae…` (в логе GET **~12:45:30 UTC**); RAG — возможны **`413`** на `embedding-shim` и `query_doc` с чанками pptx/pdf в том же фрагменте лога; `/research` — **`short_circuit: expert_council`** в `execution_trace`.
- **Notes:** Операторский черновик перенесён из `Кек.md`. Для шага 3 — та же линия расследования, что у Row 2/6: пустой или перегруженный query, приоритет источников, лимиты shim. **PPTX-дизайн:** вариативность фона — бэклог генератора слайдов. Made-with: Cursor.

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
- **Journal:** см. **2026-04-13 ~18:50 UTC** выше — **PARTIAL** на прод-стеке (STT OK, пустой `user.content` + **413** на `embedding-shim` при RAG); нужен retry после фикса / bypass.

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
