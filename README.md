# GPTHub Prod

`gpthub-prod` is a new minimal product repo for the GPTHub runtime spine. It keeps one core architecture path only:

`Open WebUI -> orchestrator -> LiteLLM -> MWS`

The repo is intentionally frozen around feature rows `1-12` and `P0` only. Everything outside that baseline stays out of scope until the core path is stable. The only differentiator this repo is allowed to optimize for is `mixed input` in one chat flow.

## What This Repo Contains

- `apps/orchestrator/`: the preserved FastAPI runtime spine and focused tests.
- `apps/embedding_shim/`: optional shim that normalizes host embeddings for Open WebUI RAG.
- `infra/docker-compose.yml`: self-contained stack wiring for WebUI, orchestrator, LiteLLM, and optional RAG support.
- `infra/litellm/config.yaml`: vendored LiteLLM alias config, rewritten for an MWS-first baseline.
- Canon docs that explain the architecture, frozen roadmap, and current feature baseline without legacy branch sprawl.

## Quick Start

```bash
cp .env.example .env
cp .env.mws.local.example .env.mws.local
# fill in the secrets

docker compose -f infra/docker-compose.yml up -d --build
```

For the optional RAG profile:

```bash
docker compose -f infra/docker-compose.yml --profile rag up -d --build
```

Run orchestrator tests locally with dev dependencies:

```bash
cd apps/orchestrator
uv sync --extra dev
uv run pytest -q
```

Open WebUI will be on `http://localhost:3000`, LiteLLM on `http://localhost:4000`, and the orchestrator health endpoint on `http://localhost:8089/healthz`.

## Demo Lock

The demo flow is deliberately narrow:

1. User sends one chat request in Open WebUI.
2. The request reaches the orchestrator through the OpenAI-compatible facade.
3. The orchestrator classifies the request, injects mixed-input artifacts when present, applies role/system policy, and calls LiteLLM.
4. LiteLLM forwards to MWS using the vendored alias map.
5. The user sees one answer, while routing evidence stays in logs and `X-GPTHub-Trace`.

The only demo differentiator is `mixed input`: one request can combine text, image, PDF, and audio-derived context without introducing extra product modes.

Optional `rag` support is infrastructure for Open WebUI, not a second flagship product mode. The same applies to `CODE_ROUTE_PREFERENCE`: it changes prompt flavor, not the core architecture path.

## Current State

This repo contains a runnable product spine with **182 passing unit +
integration tests**. What's live in code right now:

- text chat through the orchestrator facade (row 1)
- automatic + manual model choice via role-backed alias chain (rows 10, 11)
- markdown / code rendering via OpenAI-compatible passthrough (row 12)
- image-aware multimodal routing for VLM (row 5)
- mixed-input ingest: PDF, plain text (≈30 extensions), audio, and **URL
  fetch with SSRF protection** (rows 6, 8)
- audio ingest + automatic ASR against MWS `whisper-medium` (row 4)
- **in-chat image generation** via a MWS `/images/generations`
  short-circuit on `qwen-image` (row 3)
- **long-term memory**: SQLite facts store + MWS `qwen3-embedding-8b`
  retrieval + "запомни / забудь / что помнишь" command parser (row 9)
- **WOW-1 Expert Council (row 13)**: `/research` or «глубокое
  исследование» → parallel fan-out to `gpt-hub-turbo` (generalist),
  `gpt-hub-reasoning-or` (reasoning), `gpt-hub-doc` (doc) →
  `gpt-hub-strong` (glm-4.6-357b) synthesis, one OpenAI-compatible
  `chat.completion` in the «суть → Что говорит совет экспертов →
  Практические рекомендации» structure. Live smoke 2026-04-11 11:32:
  171 s, 3/3 branches, 3425-char clean Russian synthesis.
- voice chat through Open WebUI STT/TTS (row 2, UI-managed)
- `X-GPTHub-Trace` with full routing / fallback / ingest observability (row 15)
- optional embedding normalization for RAG mode (infra only)

Still open inside the P0 scope:

- row 7 web search — needs `ENABLE_WEB_SEARCH=true` + `TAVILY_API_KEY` in env;
- WOW-3 PPTX generation (row 14) — planned as a wow-feature inside
  the "one chat flow" constraint.

All gaps and phases are tracked in `ROADMAP.md` (section 0) and
`FEATURE_MATRIX.md`. Live model snapshot is in `docs/MWS_CATALOG.md`.

## Author

This repository is authored and maintained by **Aleksandr Mordvinov**
([@FUYOH666](https://github.com/FUYOH666)). There are no other listed code
contributors at this time; people invited on GitHub have repository access
only. A short machine-readable list is in `AUTHORS.md`.

## Read Next

- `docs/NEW_CHAT_HANDOFF_RU.md` — single-file handoff for a new chat window
- `docs/TEAM_BRIEF_RU.md` — single-file team briefing
- `ARCHITECTURE.md`
- `ROADMAP.md` — sections 0.4 (victory plan), 0.5 (kill switches), 0.6 (victory checklist)
- `FEATURE_MATRIX.md` — source of truth for the submission xlsx
- `docs/LIVE_SMOKE.md` — journal of every live run through the docker stack
- `docs/submission/` — track C exports (feature xlsx from matrix, diagram sources, slide skeleton)
- `docs/MWS_CATALOG.md` — live MWS model snapshot
- `docs/PROMPT_PRECEDENCE.md`
- `docs/WEBUI_PAYLOAD.md`
- `scripts/demo.sh` — idempotent curl smoke covering the Demo Lock scenario
- `CHANGELOG.md`
