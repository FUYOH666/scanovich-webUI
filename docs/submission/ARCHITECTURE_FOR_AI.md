# GPTHub Prod — архитектура и User Flow (машиночитаемая версия для ИИ)

Этот файл **UTF-8 Markdown** — зеркало для репозитория и RAG. **Файл сдачи**
[`GPTHub_architecture_submission.pdf`](GPTHub_architecture_submission.pdf) —
**текстовый PDF** (ReportLab): кириллица + мета `MachineReadableMeta` + полный
Mermaid из `architecture.mmd` и `user_flow.mmd` **внутри PDF**, **без** встроенных
PNG. ИИ и человек читают схемы как текст.

Если форма допускает только один PDF — **загружайте его**; этот `.md` не обязателен.

При правках [`architecture.mmd`](architecture.mmd) / [`user_flow.mmd`](user_flow.mmd)
обновите соответствующие fenced-блоки `mermaid` ниже (или держите канон только в
`.mmd` и генерируйте этот файл скриптом — пока копия вручную).

---

## Сопроводительный текст (как в ARCHITECTURE_SUBMISSION_RU.txt)

Продукт: один чат в Open WebUI; сценарии (текст, файлы, картинка, аудио, URL, голос через STT/TTS UI, веб-поиск при включении, WOW: совет моделей, WOW: PPTX) идут в один OpenAI-совместимый запрос к orchestrator, без второго флагманского режима.

Контур сервисов: Open WebUI → orchestrator (FastAPI: ingest, classifier/router, memory, council, image-gen, PPTX, trace) → LiteLLM (алиасы) → MWS (upstream чат/VLM/doc/reasoning). Наблюдаемость: заголовок X-GPTHub-Trace.

Модели (см. infra/litellm/config.yaml, docs/MWS_CATALOG.md): baseline mws-gpt-alpha (gpt-hub-turbo), тяжёлый glm-4.6-357b (gpt-hub-strong), документный qwen2.5-72b-instruct (gpt-hub-doc), код/рассуждения qwen3-coder-480b-a35b (gpt-hub-reasoning-or), VLM-цепочка qwen3-vl-* / qwen2.5-vl* / cotype-pro-vl-32b, fallback gemma-3-27b-it; image-gen — qwen-image (MWS /v1/images/generations); ASR — whisper-medium; память — qwen3-embedding-8b; план PPTX — алиасы gpt-hub-pptx-* и др.

Внешние зависимости: MWS (API, .env / .env.mws.local); Docker Compose; SQLite для фактов памяти; опционально Tavily (WebUI web search, ENABLE_WEB_SEARCH, TAVILY_API_KEY, bypass эмбеддинга сниппетов); markitdown для DOCX/XLSX/PPTX ingest; опционально embedding shim (профиль rag). Без MWS основной чат не работает.

Исходники диаграмм (Mermaid): docs/submission/architecture.mmd, docs/submission/user_flow.mmd. Рендер: mmdc (пакет @mermaid-js/mermaid-cli).

---

## Схема 1 — контур сервисов (текстовый пересказ для ИИ без vision)

- Узлы верхнего уровня: **User** → **OpenWebUI** → **Orchestrator** (центральный блок).
- Внутри оркестратора: **Ingest_pipeline**, **Memory** (SQLite + эмбеддинги MWS), **Image_gen** (MWS), **PPTX** (план, сборка, артефакты), **Expert_Council** (fan-out), **X-GPTHub-Trace**.
- Основной путь чата: **Orchestrator** → **LiteLLM** (слой алиасов) → **MWS** (чат, VLM, doc, reasoning).
- Отдельные стрелки: оркестратор → **whisper_ASR** (MWS); **Image_gen** → **qwen_image** (MWS); **Memory** → **qwen3_embedding** (MWS).
- Пунктир из **OpenWebUI**: опционально **Tavily** (веб-поиск через UI) и **Embedding_shim** (профиль rag).

### Схема 1 — исходник Mermaid (копия architecture.mmd)

```mermaid
flowchart TB
  subgraph ux [User]
    U[User_single_chat]
  end
  subgraph webui [OpenWebui]
    OW[OpenWebUI_UI]
  end
  subgraph orchLayer [Orchestrator_FastAPI]
    OR[Orchestrator]
    IN[Ingest_pipeline]
    MEM[Memory_SQLite_plus_MWS_embeddings]
    IMG[Image_gen_MWS]
    PPTX[PPTX_plan_build_artifacts]
    COUNCIL[Expert_Council_fanout]
    TR[X-GPTHub-Trace]
  end
  subgraph gateway [LiteLLM]
    LL[LiteLLM_alias_layer]
  end
  subgraph mws [MWS_upstream]
    M[MWS_models_chat_VLM_doc_reasoning]
    MW[whisper_ASR]
    MI[qwen_image]
    ME[qwen3_embedding]
  end
  subgraph ext [External_optional]
    TV[Tavily_via_WebUI_web_search]
    SH[Embedding_shim_optional_rag_profile]
  end
  U --> OW
  OW -->|"OpenAI_compatible_POST"| OR
  OR --> IN
  OR --> MEM
  OR --> IMG
  OR --> PPTX
  OR --> COUNCIL
  OR --> TR
  OR -->|"chat_completion_path"| LL
  LL --> M
  OR -->|"ASR_path"| MW
  IMG --> MI
  MEM --> ME
  OW -.-> TV
  OW -.-> SH
```

---

## Схема 2 — User Flow (текстовый пересказ для ИИ без vision)

- Пользователь и вложения в **одном** треде WebUI → **POST /v1/chat/completions** в форме OpenAI → **Orchestrator**.
- После ingest/classify/route оркестратор выбирает ветку:
  - **Memory_command**: ответ без LiteLLM;
  - **Image_intent**: MWS images/generations → markdown с картинкой + trace;
  - **PPTX_intent**: план через LiteLLM/MWS → превью + ссылка на скачивание + trace;
  - **Expert_council**: параллельные эксперты через LiteLLM/MWS → один синтез + trace;
  - **Default_chat**: маршрутизированный алиас → LiteLLM → MWS → поток токенов → ответ + **X-GPTHub-Trace**.

### Схема 2 — исходник Mermaid (копия user_flow.mmd)

```mermaid
sequenceDiagram
  participant User
  participant WebUI as OpenWebUI
  participant Orch as Orchestrator
  participant Lite as LiteLLM
  participant MWS as MWS_models
  User->>WebUI: Message_and_optional_attachments_same_thread
  WebUI->>Orch: POST_v1_chat_completions_OpenAI_shape
  Note over Orch: Ingest_files_URL_audio_classify_route
  alt Memory_command_short_circuit
    Orch-->>WebUI: Reply_without_LiteLLM
  else Image_intent_short_circuit
    Orch->>MWS: Images_generations
    Orch-->>WebUI: Markdown_inline_image_plus_trace
  else PPTX_intent_short_circuit
    Orch->>Lite: Slide_plan_models_alias
    Lite->>MWS: Plan_completion
    Orch-->>WebUI: Markdown_preview_plus_download_link_plus_trace
  else Expert_council_short_circuit
    Orch->>Lite: Parallel_expert_models
    Lite->>MWS: Fanout_and_synthesis
    Orch-->>WebUI: Single_synthesized_reply_plus_trace
  else Default_chat_path
    Orch->>Lite: Routed_alias_gpt-hub-asterisk
    Lite->>MWS: Upstream_chat_completion
    MWS-->>Lite: Tokens
    Lite-->>Orch: OpenAI_compatible_chunk_or_json
    Orch-->>WebUI: Assistant_content_plus_X-GPTHub-Trace
  end
```

---

## Примечание

Канон схем — `.mmd` в этой папке; PDF дублирует их как текст. Визуальный PNG для
слайдов — отдельно (`mmdc`). Пересборка PDF: [`docs/submission/README.md`](README.md).
