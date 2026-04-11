# Architecture

## Core Path

`gpthub-prod` keeps exactly one primary runtime path:

`Open WebUI -> orchestrator -> LiteLLM -> MWS`

That path is the product. Everything else in the repo is supporting infrastructure around it.

## Runtime Components

### Open WebUI

- User-facing chat surface.
- Sends OpenAI-compatible requests to the orchestrator.
- Can optionally use the embedding shim when the `rag` profile is enabled.

### Orchestrator

- Owns the runtime policy layer.
- Exposes `/healthz`, `/readyz`, `GET /v1/models`, and `POST /v1/chat/completions`.
- Classifies requests, merges prompt policy, injects mixed-input artifacts, and emits `X-GPTHub-Trace`.

### LiteLLM

- Owns the provider alias map.
- Provides a single gateway contract to the orchestrator.
- Is vendored locally in `infra/litellm/config.yaml` so the repo does not depend on legacy paths.
- `CODE_ROUTE_PREFERENCE` changes prompt/routing flavor inside the same gateway contract; it is not a second architecture path.

### MWS

- Final upstream for the default baseline.
- Hosts the chat and multimodal models referenced by the vendored LiteLLM aliases.

### Embedding Shim

- Optional support path for Open WebUI RAG mode.
- Converts upstream `dense_embedding` fields into OpenAI-style `embedding`.
- Stays outside the main chat path unless the `rag` profile is enabled.
- Exists as support infrastructure only; it is not part of the repo's single differentiator story.

## Request Flow

1. Open WebUI sends a chat completion request to the orchestrator.
2. The orchestrator validates auth and reads the request body.
3. The ingest pipeline inspects the last user message for supported payload parts.
4. The orchestrator classifies the request and chooses a role-backed alias chain.
5. Prompt precedence is applied once, producing a single system message for the upstream call.
6. LiteLLM receives one normalized request and forwards it to MWS.
7. The orchestrator optionally strips reasoning metadata, returns the response, and attaches `X-GPTHub-Trace`.

## Mixed-Input Differentiator

The repo has one allowed differentiator: `mixed input`.

That means the orchestrator may enrich a single chat turn with:

- text from the original prompt
- PDF text extracted from a file part
- audio transcript extracted from an audio part
- image-aware routing when an image part is present

The differentiator is not a new mode, a council workflow, or a second product path. It is one request flowing through one pipeline.

## Prompt And Trace Boundaries

- User-visible answer text must stay in `choices[].message.content` or stream deltas only.
- Routing and policy evidence belongs in logs and `X-GPTHub-Trace`, not in the answer body.
- Prompt merge order is documented in `docs/PROMPT_PRECEDENCE.md`.

## Scope Boundaries

Inside the current repo baseline:

- keep the architecture self-contained
- keep all runtime paths local to this repo
- keep docs focused on rows `1-12` and `P0`

Outside the current baseline:

- rows `13-15`
- expert-council style multi-agent flows
- legacy repo branches and handoff document bundles
