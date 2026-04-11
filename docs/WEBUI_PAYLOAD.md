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
