# Цепочка: от `POST /api/chat/completions` до прокси на модель (Open WebUI v0.8.12)

Контейнер: `ghcr.io/open-webui/open-webui:v0.8.12`. Исходники в репозитории не форкаются; ссылки ниже — на тег **`v0.8.12`** в GitHub.

## 1. Точка входа

- **`backend/open_webui/main.py`** — обработчик чата вызывает **`process_chat_payload`** (в логах стек: `process_chat` → `process_chat_payload`).
- После обогащения payload уходит в **`generate_chat_completion`** → для внешних моделей — **`open_webui/routers/openai.py`** → `generate_openai_chat_completion` (тело с `messages` уходит на ваш оркестратор как OpenAI-compatible).

## 2. Ядро: `process_chat_payload`

**Файл:** [`backend/open_webui/utils/middleware.py`](https://github.com/open-webui/open-webui/blob/v0.8.12/backend/open_webui/utils/middleware.py) (функция `process_chat_payload`, ~строка **2076**).

Упорядоченные шаги (упрощённо):

1. **`apply_params_to_form_data`** — модель, `stream`, кастомные параметры.
2. Подстановка сообщений из БД при `chat_id` / `parent_message_id`.
3. **Встраивание вложений в `content` только для картинок** (~**2124–2146**): для каждого user-сообщения собираются `image_files` из `message['files']`; если есть — `content` превращается в массив `[{type: text, ...}, {type: image_url, ...}]`, поле **`files` снимается** с сообщения.  
   **Аудио здесь не обрабатывается** — ветка только для `type == 'image'` или `content_type` с префиксом `image/`.
4. **`process_messages_with_output`**, system prompt, **`convert_url_images_to_base64`**.
5. Pipeline inlet, фильтры, фичи:
   - при **`features.voice`** — в системное сообщение добавляется **`VOICE_MODE_PROMPT_TEMPLATE`** (~**2291–2301**), но это **не подставляет транскрипт** в `user.content`;
   - web search / image generation / code interpreter и т.д.
6. **`form_data.pop('files', None)`** (~**2349**): список файлов из тела запроса переносится в **`metadata['files']`** (~**2415–2420**), затем **`form_data['metadata'] = metadata`**.

## 3. Файлы и RAG: `chat_completion_files_handler`

**Та же `middleware.py`**, функция **`chat_completion_files_handler`**, ~строка **1842**.

- Берёт **`files = body.get('metadata', {}).get('files')`**.
- При необходимости вызывает **`generate_queries`** (отдельный completion к модели — у вас в логах это первый запрос с `### Task: Analyze the chat history...` и пустым `USER:` в шаблоне).
- Вызывает **`get_sources_from_items`** (эмбеддинги, в т.ч. `embedding-shim`). При ошибке (например **413**) исключение логируется; контекст источников может не попасть в сообщения.
- Возвращает обновлённый **`body`** и флаги с **`sources`**.

Дальше в **`process_chat_payload`** (~**2664–2669**) при включённом **`file_context`** для модели вызывается этот handler; затем при наличии **`sources`** и **`prompt`** может вызываться **`apply_source_context_to_messages`**.

**Важно:** RAG дополняет контекст из файлов/коллекций, но **не заменяет собой обязанность иметь текст пользователя в `messages`**, если апстрим (оркестратор) ожидает явный запрос. При **пустом** последнем user-тексте поведение остаётся хрупким.

## 4. Перед отдачей наружу: `strip_empty_content_blocks`

**Файл:** [`backend/open_webui/utils/misc.py`](https://github.com/open-webui/open-webui/blob/v0.8.12/backend/open_webui/utils/misc.py), функция ~**425**.

- Для **`content` типа list** удаляются блоки **`{type: text, text: ""}`** (пустой текст), чтобы не ломать Gemini/Claude.
- Если **`content` — строка `""`**, функция **ничего не меняет** (ветка только для `list`).

Вызывается в конце **`process_chat_payload`** (~**2706–2708**), сразу перед `return form_data, metadata, events`.

## 5. Прокси на модель

**Файл:** [`backend/open_webui/utils/chat.py`](https://github.com/open-webui/open-webui/blob/v0.8.12/backend/open_webui/utils/chat.py), **`generate_chat_completion`** (~**141**).

- Для не-Ollama моделей: **`generate_openai_chat_completion`** с тем же **`form_data`**, включая **`messages`**.
- **`metadata`** на стороне OpenAI-роутера может обрезаться/не пересылаться целиком на ваш бэкенд — ориентир для отладки: **фактическое тело upstream = в основном `messages` + `model` + `stream`**.

## 6. Почему при «пустой строке + аудио» оркестратор видит `content: ""`

Сводка по коду v0.8.12:

1. Аудио после STT попадает в **файл / коллекцию** и в **`metadata.files`**, но **не копируется в `user.content`** автоматически.
2. Блок **2124–2146** **не** превращает аудио-вложения в части **`input_audio` / `file`** внутри `messages` (в отличие от картинок).
3. Итоговый запрос к внешней модели часто содержит **`messages: [{"role":"user","content":""}]`** — это совпадает с вашими логами **`incoming_chat_full`**.

## 7. Где править (форк или патч образа)

Приоритетные точки:

| Место | Идея |
|--------|------|
| **`middleware.py` ~2124–2146** | Расширить логику: для user-сообщений с **аудио** в `message['files']` либо подмешивать **транскрипт** в текстовую часть `content`, либо добавлять части **`input_audio` / `file`** в формате OpenAI (как в `docs/WEBUI_PAYLOAD.md`). |
| **После успешного STT** (`routers/audio.py`) | Гарантировать обновление **последнего user message** в данных чата / в теле исходящего completion (если транскрипт сейчас только в индексе RAG). |
| **`chat_completion_files_handler`** | При **пустом** `get_last_user_message` и наличии файлов с извлекаемым текстом — опционально подставлять первый фрагмент текста как query / в user (осторожно с размером и PII). |
| **`strip_empty_content_blocks`** | Не трогать без нужды; для строки `""` она всё равно пассивна. Корень — **не пустой list**, а **отсутствие текста/частей** до этого шага. |

## 8. Ссылки на строки (raw)

- middleware `process_chat_payload`:  https://github.com/open-webui/open-webui/blob/v0.8.12/backend/open_webui/utils/middleware.py  
- middleware `chat_completion_files_handler`: тот же файл, ~L1842.  
- misc `strip_empty_content_blocks`:  
  https://github.com/open-webui/open-webui/blob/v0.8.12/backend/open_webui/utils/misc.py#L425  
- chat `generate_chat_completion`:  
  https://github.com/open-webui/open-webui/blob/v0.8.12/backend/open_webui/utils/chat.py#L141  

Дополнение по смежной отладке: **`docs/WEBUI_PAYLOAD.md`** (формат оркестратора) и журнал **`docs/LIVE_SMOKE.md`** (голос + пустой content + 413).
