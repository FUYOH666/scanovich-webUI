# Changelog

## [Unreleased]

### Added

- **Authorship:** `README.md` (Author), root `AUTHORS.md`, and `authors` in
  `apps/orchestrator/pyproject.toml` and `apps/embedding_shim/pyproject.toml`.

### Fixed

- **Orchestrator chat 500 after image-gen enabled:** the image-intent block
  in `main.py` reused the name `last_user_text`, shadowing the
  `memory.service.last_user_text` helper and breaking normal chat when
  memory retrieval ran. Renamed the local string to `image_intent_user_text`.

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

- 63 → 153 tests passing (+90 new tests covering URL parsing, plain-text
  ingest, ASR settings fallback, image generation intent and response
  shape, memory command parser, SQLite store CRUD + cosine search,
  MWS embeddings client, and the end-to-end memory command executor with
  MockTransport).
- MWS contracts directly probed with curl against `.env.mws.local`:
  - `POST /v1/chat/completions` with `mws-gpt-alpha` → 200 OK.
  - `POST /v1/images/generations` with `qwen-image` → 200 OK (URL + b64).
  - `POST /v1/embeddings` with `qwen3-embedding-8b` → 200 OK (dim 4096).
  - `POST /v1/audio/transcriptions` with `whisper-medium` → 200 OK.

### Not yet done (tracked in ROADMAP section 0)

- Row 7: enable Open WebUI Tavily web search via env.
- Row 13 wow: Expert Council fan-out + synthesis.
- Row 14 wow: PPTX generation via `python-pptx`.
- Live E2E smoke through the docker stack (blocked on stopping the old
  `gpthub-v3-*` stack that holds ports 3000/4000/8089).
- Architecture diagram PNG/SVG.
- Demo video 2–3 minutes.
- Filled `GPTHub шаблон фич.xlsx`.
- Presentation deck.

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
