# MWS Catalog Snapshot

Снимок живого каталога MWS (`GET /v1/models`), снят с рабочего `.env.mws.local`.

> Это референсный snapshot. Если MWS поменяет список, обновить файл и сверить
> `infra/litellm/config.yaml`.

## Raw list (26 моделей)

| id | Используется как |
|---|---|
| `mws-gpt-alpha` | alias `gpt-hub-turbo` (baseline chat) |
| `llama-3.1-8b-instruct` | alias `gpt-hub-fast` |
| `glm-4.6-357b` | alias `gpt-hub-strong` |
| `qwen2.5-72b-instruct` | alias `gpt-hub-doc` |
| `qwen3-coder-480b-a35b` | alias `gpt-hub-reasoning-or` |
| `qwen3-vl-30b-a3b-instruct` | alias `gpt-hub-vision` |
| `qwen2.5-vl` | alias `gpt-hub-vision-2` |
| `cotype-pro-vl-32b` | alias `gpt-hub-vision-3` |
| `qwen2.5-vl-72b` | alias `gpt-hub-vision-4` |
| `gemma-3-27b-it` | alias `gpt-hub-fallback` |
| `qwen-image` | **IMAGE GEN** → alias `gpt-hub-image` (row 3) |
| `qwen-image-lightning` | fast image gen fallback |
| `whisper-medium` | **ASR** → `ORCHESTRATOR_ASR_MODEL` (row 4) |
| `whisper-turbo-local` | ASR fast path |
| `qwen3-embedding-8b` | **Embeddings** → long-term memory (row 9) |
| `bge-m3` | embeddings / reranker alt |
| `BAAI/bge-multilingual-gemma2` | embeddings alt |
| `QwQ-32B` | reasoning alt |
| `Qwen3-235B-A22B-Instruct-2507-FP8` | strong alt |
| `T-pro-it-1.0` | RU-focused alt |
| `deepseek-r1-distill-qwen-32b` | reasoning alt |
| `gpt-oss-120b` | strong alt |
| `gpt-oss-20b` | fast alt |
| `kimi-k2-instruct` | strong alt |
| `llama-3.3-70b-instruct` | strong alt |
| `qwen3-32b` | mid-tier alt |

## Выводы, которые меняют roadmap

- Все текущие alias в `infra/litellm/config.yaml` имеют валидный upstream id — config трогать не нужно, только дополнить новыми alias для image gen и embeddings.
- Row 3 (image generation) закрывается через `qwen-image` — отдельный локальный stable-diffusion не нужен.
- Row 4 (ASR) закрывается через `whisper-medium` / `whisper-turbo-local` напрямую из MWS — не нужен `host.docker.internal:8001`.
- Row 9 (memory) получает готовые эмбеддинги `qwen3-embedding-8b` — не нужно внешнее embedding-hosting.

## API base

- `MWS_GPT_API_BASE=https://api.gpt.mws.ru/v1`
- Auth: `Authorization: Bearer <MWS_GPT_API_KEY>`
- OpenAI-compatible endpoint family.
