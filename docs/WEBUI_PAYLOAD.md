# WebUI Payload

The orchestrator expects OpenAI-style `messages` payloads from Open WebUI.

## Supported Shapes

### Plain text

```json
{
  "model": "gpt-hub",
  "messages": [
    { "role": "user", "content": "Summarize this" }
  ]
}
```

### Text plus image

```json
{
  "model": "gpt-hub",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "What is visible here?" },
        { "type": "image_url", "image_url": { "url": "https://example.com/image.png" } }
      ]
    }
  ]
}
```

### Text plus PDF file part

```json
{
  "model": "gpt-hub",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "Summarize the attached PDF" },
        {
          "type": "file",
          "file": {
            "filename": "brief.pdf",
            "file_data": "data:application/pdf;base64,<base64>"
          }
        }
      ]
    }
  ]
}
```

### Audio part

```json
{
  "model": "gpt-hub",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "Transcribe and answer" },
        {
          "type": "input_audio",
          "input_audio": {
            "filename": "note.wav",
            "format": "wav",
            "base64": "<base64>"
          }
        }
      ]
    }
  ]
}
```

## Current Ingest Rule

- The ingest pipeline looks only at the last user message.
- PDF and audio parts are converted into system-context artifacts before the upstream call.
- Image parts are not extracted into text by default; they affect routing and stay in the request body.

## Отладка: пустой `content`, голос, RAG (Open WebUI)

Исходники Open WebUI в этом репозитории **не** форкаются — в prod используется образ `ghcr.io/open-webui/open-webui` (см. `infra/docker-compose.yml`). Трассировка «где пропал текст» на стороне **GPTHub**:

- **`gpthub_orchestrator`**: на каждый `POST /v1/chat/completions` пишутся **`incoming_chat_digest`** (длины и `sha256` по частям multimodal), **`incoming_chat_non_messages`** (всё тело кроме `messages`: `metadata`, `stream`, `model`, …) и **`incoming_chat_full`** — **полный JSON** запроса (очень длинные тела режутся на части `json_part=` в логах).
- **`ingest_peek` / `ingest_extract` / `asr_ingest_*`**: видно, пришли ли в оркестратор файловые части и сработал ли **MWS ASR** (`ORCHESTRATOR_ASR_*` / `MWS_GPT_API_*`).
- **`gpthub_embedding_shim`**: **`embeddings_in`** / **`embeddings_out`** — размер тела, разбор `input`, ответ upstream (в т.ч. **413**).

Если нужны логи **внутри** WebUI (цепочка до прокси на оркестратор), ориентир по стеку из прод-логов:

1. `open_webui/main.py` — `process_chat` → `process_chat_payload`
2. `open_webui/utils/middleware.py` — `process_chat_payload`, **`chat_completion_files_handler`** (часто здесь `get_sources_from_items` / эмбеддинги RAG)
3. `open_webui/routers/audio.py` — STT (например `faster_whisper`) — текст должен попасть в исходящий payload к модели

**Пошаговая цепочка по строкам v0.8.12:** см. [`OPEN_WEBUI_CHAT_PAYLOAD_CHAIN_v0.8.12.md`](./OPEN_WEBUI_CHAT_PAYLOAD_CHAIN_v0.8.12.md).

Кастомный образ WebUI с `logger.info` в этих точках — отдельный шаг; до него достаточно **полного тела** на оркестраторе, чтобы увидеть, что именно WebUI отправил в момент `content: ""`.
