# Политика маршрутизации моделей (канон)

Документ фиксирует **одну правду** о том, как GPTHub prod выбирает модель для запроса: что было на старте baseline и что действует сейчас после выравнивания под тип задачи.

## Архитектурный инвариант

- Клиент (Open WebUI) шлёт запрос в **orchestrator** с фасадной моделью (например `gpt-hub`).
- **Classifier** определяет `task_type` и модальности (текст / картинка в сообщении и т.д.).
- **Router** (`apps/orchestrator/gpthub_orchestrator/router.py`) выбирает **роль** из фиксированного набора.
- **Реестр ролей** — `apps/orchestrator/gpthub_orchestrator/data/model_roles.yaml`: у каждой роли упорядоченный список **LiteLLM-алиасов** (первая строка — основной вызов, далее fallback внутри оркестратора при ретраях LiteLLM).
- Соответствие алиас → upstream MWS — в `infra/litellm/config.yaml` и в снимке `docs/MWS_CATALOG.md`.

Итоговое решение и цепочка попадают в **`X-GPTHub-Trace`** (ряд 15 / защита).

## Исходная политика baseline (hackathon / «тонкий» spine)

**Цель:** быстро получить **предсказуемый** end-to-end путь `WebUI → orchestrator → LiteLLM → MWS` с минимальным числом сюрпризов на smoke.

**Практика в раннем `model_roles.yaml` (логически «v1»):** для ролей `doc_synthesis` и `reasoning_code_local` / `reasoning_code_openrouter` первым в списке стоял **`gpt-hub-turbo`** (MWS `mws-gpt-alpha`) — тот же чекпоинт, что и для обычного чата.

**Зачем так делают:**

- одна «рабочая лошадь» на большинство эвристик классификатора — проще демо и журналирование;
- ниже средняя латентность и риск таймаутов на тяжёлых чекпоинтах;
- специализированные большие модели всё равно оставались в стеке для **WOW-1 Expert Council** (отдельные env-поля `council_expert_*`) и для ручного выбора алиасов в WebUI (`ORCHESTRATOR_MODELS_CATALOG=all`).

**Минус:** семантика роли («документ», «код») **не совпадала** с первым чекпоинтом — для сдачи продукта как «умный маршрутизатор под задачу» это слабее.

## Текущая политика (реестр в репозитории)

Файл `data/model_roles.yaml` сейчас с **`version: 1`**. Цепочки (первый алиас = основной вызов):

| Роль (`model_roles.yaml`) | Порядок алиасов | Назначение |
|---------------------------|-----------------|------------|
| `fast_text` / `fast_text_chat` | `gpt-hub-turbo` / `gpt-hub-fast` → … | обычный диалог, приветствия |
| `doc_synthesis` | **`gpt-hub-doc`** → `gpt-hub-turbo` → `gpt-hub-fallback` | summarization / file_analysis |
| `reasoning_code_local` | **`gpt-hub-strong`** → `gpt-hub-turbo` → `gpt-hub-fallback` | `code_help` при `CODE_ROUTE_PREFERENCE=local`, защитный маршрут для `pptx` |
| `reasoning_code_openrouter` | **`gpt-hub-reasoning-or`** → `gpt-hub-strong` → `gpt-hub-fallback` | `code_help` при `CODE_ROUTE_PREFERENCE=openrouter` |
| `vision_general` | `gpt-hub-vision` → … → `gpt-hub-fallback` | VLM |

**Целевая** политика «специалист первым, затем `gpt-hub-turbo`, затем fallback» для code-ролей описана выше как направление развития; пока локальный code-путь начинается с **`gpt-hub-strong`** (см. YAML). Если правите реестр — обновляйте этот файл в том же PR.

Отдельно от реестра (всегда смотреть `settings.py`):

- **Expert Council:** ветки `council_expert_*` + синтез `council_synthesis_model` (по умолчанию `gpt-hub-strong` / glm-4.6).
- **PPTX:** `pptx_plan_model` (по умолчанию `gpt-hub-strong`).
- **Картинки в чате:** `image_gen_model` (MWS `qwen-image`, не через LiteLLM chat).
- **Память:** эмбеддинги `memory_embedding_model` (прямой MWS `/v1/embeddings`).

## Что пересобирать при смене политики

- Изменился только **`gpthub_orchestrator/data/model_roles.yaml`** (или код роутера/classifier): достаточно пересобрать **orchestrator** из **корня** репозитория — **`make docker-rebuild`** (внутри те же `--env-file .env` / `.env.mws.local`, что и у `make docker-up`; эквивалент: `docker compose --env-file .env --env-file .env.mws.local -f infra/docker-compose.yml up -d --build orchestrator`). Запуск compose не из корня или без обоих `--env-file` ломает подстановку `OPEN_WEBUI_IMAGE` и пути `env_file` в YAML.
- Изменился **`infra/litellm/config.yaml`**: пересоздать сервис **`litellm`** (и при необходимости orchestrator).

## Где не искать эту политику

- **Поиск в интернете (Tavily)** настраивается в **Open WebUI**; оркестратор получает уже обогащённый текст.
- **RAG-эмбеддинги WebUI** отключены для prod-пути через `BYPASS_EMBEDDING_AND_RETRIEVAL` — см. `FEATURE_MATRIX` / `ROADMAP`, не путать с `memory_embedding_*`.

---

*Если этот файл противоречит `router.py` / `model_roles.yaml` — править код и этот документ в одном PR.*
