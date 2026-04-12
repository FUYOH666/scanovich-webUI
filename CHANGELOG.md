# Changelog

## [Unreleased]

### Added

- **Open WebUI web search prod default:** `.env.example` documents and defaults
  **`BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL=true`** so Tavily results are not
  routed through WebUI vector embedding when no embedding engine is configured
  (avoids `NoneType.encode`). `FEATURE_MATRIX.md` row 7, `docs/LIVE_SMOKE.md`,
  `docs/NEW_CHAT_HANDOFF_RU.md` aligned; follow-up notes UX of the Sources panel
  when bypass is on.
- **PPTX plan model benchmark:** LiteLLM aliases `gpt-hub-pptx-llama33` →
  `llama-3.3-70b-instruct` and `gpt-hub-pptx-qwen235a22` →
  `Qwen3-235B-A22B-Instruct-2507-FP8` in [`infra/litellm/config.yaml`](infra/litellm/config.yaml);
  script [`scripts/bench_pptx_plan_models.py`](scripts/bench_pptx_plan_models.py) runs the same
  `request_slide_plan` + `build_pptx_from_plan` path as production, reports median
  plan/build seconds per alias. Optional prod switch: `PPTX_PLAN_MODEL` env
  (default remains `gpt-hub-strong`).
- **Unit:** `tests/test_litellm_pptx_bench_aliases.py` asserts new YAML entries exist.

### Changed

- **Router / `model_roles.yaml`:** `doc_synthesis` now starts with **`gpt-hub-doc`**
  (qwen2.5-72b-instruct); `reasoning_code_local` / `reasoning_code_openrouter` start
  with **`gpt-hub-reasoning-or`** (qwen3-coder-480b), each with **`gpt-hub-turbo`**
  as second-step fallback before `gpt-hub-fallback`. Aligns classifier roles with
  MWS capabilities for submission demos (was alpha-first for all non-vision roles).
- **Docs (web search UX):** `ARCHITECTURE.md`, `FEATURE_MATRIX.md` row 7,
  `docs/LIVE_SMOKE.md` — зафиксировано поведение «счётчик источников / источники не
  найдены» при `BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL`: поиск встраивается в
  сообщения, панель цитат WebUI может оставаться пустой.
- **Docs:** новый канон [`docs/MODEL_ROUTING_POLICY.md`](docs/MODEL_ROUTING_POLICY.md)
  — исходная alpha-first политика baseline и текущая политика реестра ролей
  `model_roles.yaml` version 2; ссылки из `README.md`, `NEW_CHAT_HANDOFF_RU.md`,
  `TEAM_BRIEF_RU.md`, `ROADMAP.md`.
- **PPTX JSON parsing:** tolerate instruct models that append prose after a valid
  top-level JSON object (`json.JSONDecoder().raw_decode`) — improves compatibility
  when benchmarking or routing PPTX through chatty instruct checkpoints.
- **Docs:** full sync all canon docs (ROADMAP, README, TEAM_BRIEF_RU,
  NEW_CHAT_HANDOFF_RU, FEATURE_MATRIX) with WOW-1 Council + WOW-3 PPTX
  state, **261** tests, victory-plan step statuses (Steps 1–5, 7 closed,
  6/8/9 planned). Regenerated `docs/submission/GPTHub_features_matrix.xlsx`.
- **Docs drift fix:** Row 9 memory test count (было ошибочно «52») → ~30 в
  `test_memory_*.py`; убраны устаревшие **WARN=1** из‑за PPTX в `demo.sh`;
  `LIVE_SMOKE.md` — follow-up про флаппи **ReadTimeout** на MWS embeddings;
  `.env.example` — комментарий `MEMORY_EMBEDDING_TIMEOUT_SECONDS`.
- **Verification (2026-04-11):** `uv run pytest` → 261 passed, 2 skipped;
  `docker compose … up -d --build` + full `scripts/demo.sh` → **PASS=13**
  FAIL=0 WARN=0; запись в `docs/LIVE_SMOKE.md` (пояснение PASS=13 vs
  устаревшие PASS=12 в старых журналах).

### Fixed

- **PPTX plan JSON parse failures (MWS `<think>` CoT):** `gpt-hub-strong`
  (glm-4.6-357b) wraps output in `<think>...</think>` Chinese CoT blocks
  before the actual JSON. Added `_strip_cot_blocks()` to `pptx_gen.py`
  that removes `<think>` tags before JSON parsing. First live PPTX
  generation confirmed 2026-04-12: 7-slide deck, 35 KB, download OK.
- **PPTX intent patterns broadened:** added «в формате pptx», «формат pptx»
  patterns so natural-language phrases like «давай, в формате pptx будет?»
  now trigger the PPTX short-circuit. 52 → 56 unit tests.

### Added

- **Row 14 WOW-3 PPTX generation**: new
  `apps/orchestrator/gpthub_orchestrator/pptx_gen.py` with RU/EN/slash
  intent detection (`/pptx`, `/slides`, «сделай презентацию», «build a
  deck»), JSON slide-plan request to `gpt-hub-strong` (glm-4.6-357b)
  with one retry on parse failure, `python-pptx` deck builder (title +
  bullet slides), file storage + unguessable-token download endpoint
  `GET /v1/files/pptx/{token}`, OpenAI-compatible `chat.completion`
  response with markdown download link. Classifier
  `TaskType.PPTX_GENERATION`, router fallback, wired into `main.py`
  between council and image-gen short-circuits. 52 unit tests in
  `tests/test_pptx_gen.py` (intent detection, JSON parsing + fence
  strip, plan validation including edge cases, python-pptx round-trip,
  storage CRUD, mock LiteLLM plan request with retry, end-to-end
  generation, response builders, classifier + router wiring). Settings:
  `pptx_enabled`, `pptx_plan_model`, `pptx_plan_timeout_seconds`,
  `pptx_plan_max_tokens`, `pptx_min_slides`, `pptx_max_slides`,
  `pptx_storage_dir`, `pptx_public_base_url`. Row 14 moved from
  `Deferred (wow candidate)` to `Implemented (WOW-3)` in
  `FEATURE_MATRIX.md`.
- **Row 6 DOCX/XLSX/PPTX support via markitdown**: new
  `apps/orchestrator/gpthub_orchestrator/ingest/richdoc.py` — detection
  by MIME + extension for `.docx/.xlsx/.pptx/.doc/.xls/.ppt/.rtf/.epub`,
  conversion via Microsoft `markitdown` library to markdown text, wired
  into `ingest/pipeline.py` between PDF and plain-text routing. 21
  tests in `tests/test_ingest_richdoc.py` (detection, real DOCX/XLSX/PPTX
  round-trip, garbage fallback, empty rejection, pipeline routing).
- **Row 7 Tavily web search**: env vars already in `.env` and
  `.env.example` (`ENABLE_WEB_SEARCH=true`, `WEB_SEARCH_ENGINE=tavily`,
  `TAVILY_API_KEY`); confirmed loaded in running WebUI container.
  Row 7 status stays `Implemented (UI-managed)`.
- **Authorship:** `README.md` (Author), root `AUTHORS.md`, and `authors` in
  `apps/orchestrator/pyproject.toml` and `apps/embedding_shim/pyproject.toml`.

### Fixed

- **Web search (Tavily) caused ContextWindowExceededError:** Open WebUI
  injected full Tavily results into the chat messages, which combined
  with existing chat history exceeded the 131K token limit of MWS models.
  Added `WEB_SEARCH_RESULT_COUNT=2` and `TAVILY_EXTRACT_DEPTH=basic` to
  `.env.example` and `.env` to limit result volume.
- **PDF / file upload via Open WebUI crashed with `'NoneType' object has
  no attribute 'encode'`:** Open WebUI v0.8.12 ran its own RAG/embedding
  pipeline on uploaded files (`chat_completion_files_handler` →
  `get_sources_from_items` → `query_collection` →
  `embedding_function(...)`), but no embedding engine was configured
  in our compose, so the lambda received `None` and crashed. The
  architecturally correct fix is **not** to wire a second embedding
  engine into WebUI — orchestrator already owns ingest via
  `ingest/pipeline.py` (PDF + ~30 plain-text extensions + URL + audio).
  Added `BYPASS_EMBEDDING_AND_RETRIEVAL=true` (and explicit empty
  `RAG_EMBEDDING_ENGINE=`) to `.env.example` and `.env`. With bypass on,
  the WebUI retrieval path takes the `file_object.data.get('content', '')`
  branch (`retrieval/utils.py:1028`) and inlines the already-extracted
  text directly into the chat payload, never touching the embedding
  function. Recreating the `open-webui` container makes the fix live;
  baseline `Row 6 Files` is unblocked for live PDF smoke.
- **Orchestrator chat 500 after image-gen enabled:** the image-intent block
  in `main.py` reused the name `last_user_text`, shadowing the
  `memory.service.last_user_text` helper and breaking normal chat when
  memory retrieval ran. Renamed the local string to `image_intent_user_text`.
- **`scripts/demo.sh` false WARN on image-gen:** bash glob was `*'!['`
  (no trailing `*`), so the check only matched if the response **ended**
  with `![`, which never happens. Fixed to `*'!['*'](http'*`. Row 3 is
  now green end-to-end: `PASS=11 FAIL=0 WARN=0` via `demo.sh --skip-wow`
  against live MWS `qwen-image`. Direct MWS probe from inside the
  orchestrator container also returns a 200 with a real image URL.

### Added

- **Track C submission bundle:** `docs/submission/` (`README.md`,
  `architecture.mmd`, `gpthub-architecture.excalidraw`, `SLIDES_SKELETON.md`,
  `GPTHub_features_matrix.xlsx`) plus `scripts/build_features_xlsx.py` to
  regenerate the spreadsheet from `FEATURE_MATRIX.md`.
- **Live smoke journal:** Step 1 entries in `docs/LIVE_SMOKE.md` for v3
  teardown, prod compose bring-up, and health / `demo.sh --skip-wow` baseline.

#### Phase B — close Deferred rows

- **Row 3 Image generation**: new `apps/orchestrator/gpthub_orchestrator/image_gen.py`
  with RU/EN/slash-command intent detection, MWS `/v1/images/generations`
  short-circuit on `qwen-image`, OpenAI-compatible json and SSE responses
  with inline markdown `![](url)`, graceful fall-through to regular chat
  on failure. 12 unit tests in `tests/test_image_gen.py`.
- **Row 8 Web URL parsing**: new `apps/orchestrator/gpthub_orchestrator/ingest/url_fetch.py`
  with stdlib-only HTML-to-text extractor, SSRF guard (private IP block
  before + after redirects), content-type whitelist, size + timeout caps,
  and parallel integration into `ingest/pipeline.py`. 12 unit / integration
  tests in `tests/test_ingest_url.py`.
- **Row 9 Long-term memory**: new `apps/orchestrator/gpthub_orchestrator/memory/`
  package with four modules:
  - `store.py` — thread-safe SQLite facts store with packed float32
    embeddings, user-scoped CRUD, in-memory cosine ranking.
  - `commands.py` — pure-Python parser for «запомни / забудь /
    forget_all / что ты помнишь» commands (RU + EN + `/remember`,
    `/forget`, `/memories`).
  - `embeddings.py` — direct MWS `POST /v1/embeddings` client for
    `qwen3-embedding-8b` (dim 4096), independent of LiteLLM.
  - `service.py` — command executor, retrieval (`top-K` cosine over
    stored facts), SSE / JSON short-circuit response builders.
  Wired into `main.py`: (1) lifespan now owns a `MemoryStore`;
  (2) a memory-command short-circuit runs after ingest and before
  image-gen; (3) on normal chat, relevant facts are injected as an
  extra system block before role-prompt. 52 unit / integration tests
  in `test_memory_commands.py`, `test_memory_store.py`,
  `test_memory_service.py`.

#### Phase D — WOW features

- **Row 13 Expert Council (WOW-1)**: new
  `apps/orchestrator/gpthub_orchestrator/council.py` with DEEP_RESEARCH
  intent detection (`/research`, «глубокое исследование», `deep research`,
  «совет экспертов», «мультиэкспертный…»), parallel fan-out via
  `asyncio.gather(return_exceptions=True)` into three MWS branches —
  `gpt-hub-turbo` (generalist persona), `gpt-hub-reasoning-or` (reasoning
  persona), `gpt-hub-doc` (doc/long-context persona) — and a single
  synthesis call through `gpt-hub-strong` (glm-4.6-357b) that produces
  one OpenAI-compatible `chat.completion` in the canonical structure
  «суть → Что говорит совет экспертов → Практические рекомендации».
  Four safety layers: (1) per-branch timeout, (2) min-branches threshold
  with strong-only fallback, (3) `merge_reasoning_exclude_into_body`
  on every council call + `_strip_cot_blocks` CoT cleaner that never
  returns empty, (4) CoT-dump heuristic that falls through to an
  emergency composite response when synthesis leaks a meta-plan instead
  of an answer. Wired into `main.py` between the memory-command and
  image-gen short-circuits; `classifier.py` gained a
  `TaskType.DEEP_RESEARCH` case; `router.py` defensively routes it to
  the reasoning role when the short-circuit is disabled. 29 unit tests
  in `tests/test_council.py` (happy / partial 2-of-3 / strong-only
  fallback / all-fail / emergency composite / intent parametrized /
  CoT strip / classifier wiring / response builders / empty-question
  guard). Settings: `council_enabled`, `council_branch_timeout_seconds`,
  `council_synthesis_timeout_seconds` (240 s), `council_expert_strong`,
  `council_expert_reasoning`, `council_expert_doc`,
  `council_synthesis_model`, `council_min_branches_for_synthesis`,
  `council_max_expert_tokens` (700), `council_max_synthesis_tokens`
  (3000). Live smoke: see `docs/LIVE_SMOKE.md` 2026-04-11 11:32 —
  171 s end-to-end, 3/3 branches OK, 3425-char clean Russian synthesis,
  `fallback_used=false`, no `<think>` leakage. Row 13 moved from
  `Deferred (wow candidate)` to `Implemented (WOW-1)` in
  `FEATURE_MATRIX.md`.

#### Phase C — Partial → Implemented

- **Row 4 ASR**: `Settings.resolved_asr_base_url()` and `resolved_asr_api_key()`
  with automatic fallback to `MWS_GPT_API_BASE / MWS_GPT_API_KEY`; default
  ASR model is now `whisper-medium`. 3 unit tests in `tests/test_settings_resolve.py`.
- **Row 6 Files**: `ingest/pipeline.py` extended to accept `.txt/.md/.markdown/
  .rst/.csv/.tsv/.log/.json/.yaml/.yml/.xml/.ini/.toml/.html/.py/.js/.ts/
  .go/.rs/.java/.c/.h/.cpp/.sql/.sh` etc. (≈30 extensions) via new
  `_is_plain_text_item` helper + `_process_one_plain_text` task. 3 unit
  tests in `tests/test_ingest_text.py`.

#### Infrastructure

- `docs/MWS_CATALOG.md`: snapshot of the live MWS `/v1/models` catalog
  (26 models) with the mapping to our LiteLLM aliases and the direct-call
  destinations (image-gen, ASR, embeddings).
- `infra/docker-compose.yml`: `orchestrator` service now loads
  `.env.mws.local` (optional) so `MWS_GPT_API_BASE / MWS_GPT_API_KEY` are
  available at orchestrator level, not just at LiteLLM.

### Changed

- `ROADMAP.md` restructured around a working tracker (section 0) with
  per-row status, phase ordering (A–E), and an explicit WOW-features
  section for row 13 (Expert Council), row 14 (PPTX generation), and
  row 15 (`X-GPTHub-Trace`). Phase D is no longer implicitly blocked by
  Phase C.
- `FEATURE_MATRIX.md` rewritten as the single source of truth for the
  `GPTHub шаблон фич.xlsx` submission file. Row statuses reflect the
  actual state of code + tests + live MWS contracts.
- `README.md` current-state section reflects the 101-test baseline and
  lists real feature status by row.
- `docs/TEAM_BRIEF_RU.md` updated with current row statuses, MWS catalog
  details, Expert Council / PPTX wow plan, track split, and the v3-stack
  shutdown note.
- `docs/NEW_CHAT_HANDOFF_RU.md` updated with current row statuses, list
  of newly implemented modules, and the next-priority task order.
- `.env.example`: ASR variables default to empty so the orchestrator
  auto-falls-back to MWS whisper via `MWS_GPT_API_BASE/KEY`.
- `apps/orchestrator/gpthub_orchestrator/settings.py`: added
  `mws_gpt_api_base`, `mws_gpt_api_key`, `ingest_url_*`, `image_gen_*`,
  `memory_*` fields (including `memory_db_path`, `memory_embedding_model`,
  `memory_retrieval_top_k`, `memory_retrieval_min_score`); ASR fields
  became fully optional; default ASR model is now `whisper-medium`.

### Validation

- 63 → 259 tests passing (+171 new tests covering URL parsing, plain-text
  ingest, ASR settings fallback, image generation intent and response
  shape, memory command parser, SQLite store CRUD + cosine search,
  MWS embeddings client, the end-to-end memory command executor with
  MockTransport, the Expert Council fan-out / synthesis / fallback
  / CoT-strip / classifier wiring, and PPTX intent detection / JSON plan
  parsing / python-pptx builder / storage / end-to-end generation /
  response builders / classifier + router wiring).
- MWS contracts directly probed with curl against `.env.mws.local`:
  - `POST /v1/chat/completions` with `mws-gpt-alpha` → 200 OK.
  - `POST /v1/images/generations` with `qwen-image` → 200 OK (URL + b64).
  - `POST /v1/embeddings` with `qwen3-embedding-8b` → 200 OK (dim 4096).
  - `POST /v1/audio/transcriptions` with `whisper-medium` → 200 OK.

### Not yet done (tracked in ROADMAP section 0)

- Operator-level live verification for rows 2, 4, 5, 6, 11 (Step 6).
- Architecture diagram PNG/SVG.
- Demo video 2–3 minutes.
- Presentation deck finalization.
- git tag `demo-ready`.

## [earlier]

### Added

- Created the `gpthub-prod` baseline repo around the self-contained runtime spine.
- Vendored the orchestrator package, focused tests, embedding shim, compose stack, and LiteLLM config into the new layout.
- Rewrote canon docs for the frozen `P0` and feature rows `1-12` baseline.
- Added `docs/TEAM_BRIEF_RU.md` as the single Russian team briefing for architecture, win path, organizer-status check, and task lanes.
- Added `docs/NEW_CHAT_HANDOFF_RU.md` as the dedicated technical handoff for a new chat window.

### Changed

- `ROADMAP.md` marks the next natural step: load real `.env` / `.env.mws.local`, raise `infra/docker-compose.yml`, and run live `P0` smoke for text, `VLM`, and `mixed input`.
- `README.md` points to `docs/TEAM_BRIEF_RU.md` as the fastest team-facing entry document.
- `ROADMAP.md` was expanded into a near-final Russian roadmap with target end state, phases, team lanes, and submission lock.
- `TEAM_BRIEF_RU.md` points technical continuation work to `docs/NEW_CHAT_HANDOFF_RU.md`.
