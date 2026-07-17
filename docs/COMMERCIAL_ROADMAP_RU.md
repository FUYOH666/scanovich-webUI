# SCANOVICH — коммерческая дорожная карта

> Точка входа для заказчиков и для команды: **что это сегодня**, **что оставить**,
> **что выкинуть**, **куда идти**, если делать продаваемый продукт с **базой знаний
> клиента** и inference **внутри периметра**.
>
> Допускаются глобальные реорганизации. Хакатонный стенд — учебный каркас, не
> финальная форма продукта.
>
> Статус документа: черновик стратегии (2026-07). Не заменяет `FEATURE_MATRIX.md`
> (что уже есть в коде) и не обещает сроки без контракта.

---

## 1. Вердикт за 30 секунд

**Сегодня в репозитории** — сильный **policy-spine** (orchestrator): классификация,
смешанный ingest, роутинг, память, council, PPTX, `X-GPTHub-Trace`, Docker-пакет.
Это уже можно показать заказчику как **прототип единого окна ИИ**.

**Нельзя продавать «как есть»** как enterprise: нет multi-tenant, нормальной
персистентности, SSO/квот, CI/CD, нормального Knowledge Plane; Open WebUI живёт
на **обходах RAG** (`BYPASS_*`); upstream жёстко заточен под MWS; UI «источников»
веб-поиска декоративно врёт.

**Коммерческий продукт** — это не «ещё один Open WebUI + LiteLLM», а:

1. **Workspace** (организация / отдел / проект) с изоляцией данных.
2. **Knowledge Plane** (индексация документов клиента → retrieval → цитаты).
3. **Model Plane** (любой OpenAI-compatible / vLLM / Ollama / облако по выбору).
4. **Chat + Tools** (один UX, политики, аудит).
5. **Deploy** (on-prem / VPC / air-gapped) с понятным TCO.

Хакатонный код — **донор идей и тестов**, не священная архитектура.

---

## 2. Что оставить (актив, не выкидывать)

| Актив | Почему ценно коммерчески |
|-------|--------------------------|
| **Orchestrator как OpenAI-compatible facade** | Любой чат-клиент / интеграция «как ChatGPT API» |
| **Классификатор + `model_roles.yaml` + fallback** | Политика моделей без хардкода в UI |
| **Mixed ingest** (PDF/Office/URL/ASR/image) | Реальные корпоративные входы |
| **`X-GPTHub-Trace`** | Аудит «почему эта модель / этот путь» — продаётся compliance |
| **Expert Council / research short-circuit** | Дифференциатор для «глубоких» задач |
| **PPTX pipeline (идея)** | Артефакты в чате; дизайн — переделать |
| **Пакет Docker + smoke (`demo.sh`)** | База для pilot deploy |
| **~245 pytest** в orchestrator | Регрессионный пол для рефакторинга |

---

## 3. Что выкинуть или радикально упростить

| Долг / запах | Действие |
|--------------|----------|
| Двойной RAG (WebUI vector + orchestrator ingest) + `BYPASS_*` | **Один** Knowledge Plane; WebUI не индексирует |
| `ENABLE_PERSISTENT_CONFIG` ловушки | Либо force env, либо config-as-code без Admin override |
| Память в `/tmp` SQLite, user_id=`default` | Postgres/pgvector + tenant_id |
| PPTX in-memory store | Object storage (S3/MinIO) + auth на скачивание |
| Жёсткая привязка к MWS model IDs в доках/алиасах | **Provider adapters** + каталог моделей заказчика |
| `embedding-shim` + `host.docker.internal` BGE | Входит в Knowledge Plane или managed embeddings |
| Fork Open WebUI без стратегии апгрейда | Pin + thin patch layer **или** свой thin UI |
| Открытый signup + один shared bearer | SSO / OIDC + service accounts |
| Нет CI на корне репо | GitHub Actions: pytest + build + smoke |

---

## 4. Целевая архитектура (допускается снос)

```text
                    ┌─────────────────────────────┐
                    │  Clients                    │
                    │  Chat UI · API · Slack/TG    │
                    └──────────────┬──────────────┘
                                   │ OpenAI-compatible + auth
                    ┌──────────────▼──────────────┐
                    │  SCANOVICH Gateway          │
                    │  auth · tenant · quotas     │
                    │  policy · tools · trace     │
                    └──────┬─────────────┬────────┘
           ┌───────────────┘             └───────────────┐
           ▼                                             ▼
┌─────────────────────┐                     ┌─────────────────────┐
│ Knowledge Plane     │                     │ Model Plane         │
│ ingest · chunk      │◄── citations ───────│ adapters:           │
│ embed · hybrid      │                     │ vLLM / Ollama /     │
│ rerank · ACL        │                     │ cloud / on-prem     │
│ connectors (Drive,  │                     │ LiteLLM optional    │
│ SharePoint, S3…)    │                     └─────────────────────┘
└─────────────────────┘
           │
           ▼
   Postgres + object store + vector (pgvector / Qdrant)
```

**Принцип 2026:** один источник истины на конфиг и политики; деградация явная
(если нет KB / нет GPU / нет web — флаг + лог, не тихий фоллбек).

### Почему не «просто допилить хакатон»

Хакатон оптимизировал **закрытие матрицы фич за дни**. Коммерция оптимизирует
**изоляцию данных, цитируемость KB, деплой у клиента, сопровождение 12 месяцев**.
Это другие инварианты → иначе будут вечные `BYPASS_*` и «на моём Mac работает».

---

## 5. Продуктовые ставки (что продаём)

### Ставка A — Private Chat Workspace (входной SKU)

Единое окно: чат, файлы, голос, модели заказчика.  
**Без** обязательной глубокой KB. Быстрый pilot за 2–4 недели.

### Ставка B — Knowledge Copilot (основной SKU)

Индексация корпуса клиента + ответы **с цитатами** + ACL по отделам.  
Медицина / юристы / банк / недра / разработка — один продукт, разные connectors
и политики retention.

### Ставка C — Agent Ops (апселл)

Tools (поиск по KB, CRM, тикеты), research-council, генерация артефактов
(PPTX/DOCX), eval harness, audit export.

**Не продавать первым** «красивые слайды» или «три эксперта» — это wow после
того, как KB и периметр не стыдят.

---

## 6. Дорожная карта по фазам

### Фаза 0 — Правда и упаковка (1–2 недели)

Цель: репозиторий = честная витрина для заказчика.

- [x] Публичный репо + продуктовый фасад README / обложка
- [ ] Этот документ в README как «для бизнеса / next»
- [ ] Одностраничный `docs/CUSTOMER_ONEPAGER_RU.md` (проблема → решение → деплой → контакт)
- [ ] Явный список **не для продакшена** (bypass, `/tmp`, shared key)
- [ ] Демо-видео 3–5 мин: чат + файл + «данные не уходят» narrative

### Фаза 1 — Sellable Pilot (6–10 недель)

Цель: платный/пилотный контракт у одного заказчика on-prem/VPC.

1. **Tenant + auth** — workspace_id, OIDC (Keycloak / Entra / Google), API keys на сервисы.
2. **Knowledge Plane v1** — загрузка PDF/DOCX/MD → chunk → embed → hybrid search → **обязательные citations** в ответе; ACL «кто видит какой корпус».
3. **Model Plane v1** — конфиг провайдеров YAML; убрать MWS из «обязательного ядра»; LiteLLM optional.
4. **Persistence** — Postgres (users, chats, memory, jobs), MinIO/S3 для файлов/PPTX.
5. **UI strategy** — либо: Open WebUI как thin shell + запрет своего RAG; либо thin Next/React chat (дольше, но чище).
6. **Ops** — CI, Helm или compose-prod, backup/restore runbook, `/metrics`, structured logs.
7. **Eval smoke** — набор вопросов заказчика + golden answers; регресс перед релизом.

**Критерий готовности пилота:** ИБ заказчика принимает периметр; юрист/врач/аналитик
получает ответ **со ссылкой на свой документ**; админ поднимает стенд по runbook
без «спроси Александра».

### Фаза 2 — Enterprise Packaging (квартал)

- Connectors: SharePoint, Google Drive, Confluence, S3, email archive (по отрасли).
- SSO + SCIM, роли (admin / editor / viewer / auditor).
- Quotas, rate limits, cost attribution per department.
- Air-gapped install (offline images + model bundle).
- Audit log export (SIEM), retention policies, PII redaction hooks.
- High availability: multi-replica gateway, shared vector/DB.
- Support SLA playbooks.

### Фаза 3 — Platform (6–12 месяцев)

- Marketplace tools / MCP servers под отрасль.
- Fine-tune / LoRA jobs на корпусе клиента (опционально).
- Multi-region, white-label UI.
- Managed cloud SKU (если юр. ок) + pure on-prem SKU.
- Partner channel (интеграторы).

---

## 7. Что бы я переделал «спустя три месяца» конкретно

### 7.1. Knowledge — центр продукта (сейчас — дыра)

Хакатон закрыл «файлы в чат» (ingest в prompt). Это **не** база знаний.

Нужно:

- отдельный сервис `knowledge` (или модуль с job queue);
- chunking + metadata (отдел, confidentiality, язык);
- hybrid (dense + sparse/BM25) + rerank;
- ответ всегда с citations UI (не панель WebUI Sources);
- re-index и delete-by-policy (GDPR / «удалить дело №»).

Без этого «для любого бизнеса» — маркетинг, не продукт.

### 7.2. UI — меньше магии Open WebUI

Open WebUI дал скорость на хакатоне и боль (`BYPASS_*`, PersistentConfig, Sources).

Варианты:

| Вариант | Когда |
|---------|--------|
| **A. Pin + config-as-code** | Быстрый pilot: один образ, RAG WebUI выключен навсегда |
| **B. Thin chat UI** | Когда KB citations и ACL важнее фич WebUI |
| **C. White-label fork** | Если нужен полный WebUI UX и контроль патчей |

Рекомендация для коммерции: **A → B**. Не инвестировать в «починить Sources».

### 7.3. PPTX / артефакты

Оставить short-circuit идею; **выкинуть** «голый python-pptx текст».

Новый путь:

1. Дизайн-система слайдов (2–3 темы, master layouts).
2. LLM только plan + copy.
3. Опционально картинки (локальный image model).
4. Агентный «арт-директор» — только как флаг, с бюджетом шагов и фоллбеком на шаблон.

### 7.4. Council / agents

Council оставить как **режим** (`/research`), но обернуть в:

- явный budget (токены / latency / $);
- partial failure UX;
- запись всех веток в audit.

Дальше — tool-calling агент с MCP к KB и внутренним API, не fan-out ради fan-out.

### 7.5. Observability и eval

`X-GPTHub-Trace` → OpenTelemetry + searchable store.  
Offline eval set на корпусе клиента = обязательный артефакт внедрения.

### 7.6. Безопасность периметра

- SSRF уже есть для URL — распространить на все connectors.
- Prompt injection defenses на retrieved chunks.
- Secret scanning в uploads.
- Network policy: default-deny egress кроме allowlist моделей/KB.

---

## 8. Упрощения «сделать современнее и проще»

Парадокс: **проще для заказчика** часто значит **жёстче границы** в коде.

1. Один compose-профиль `prod` (без `rag` shim и без MacBook BGE).
2. Один способ auth.
3. Один путь файлов → Knowledge Plane (не «иногда WebUI RAG»).
4. Каталог моделей = YAML заказчика, не `MWS_CATALOG.md` как истина.
5. Документация: Customer / Operator / Developer — три тонких гайда, не 15 handoff-файлов хакатона.

Технологии 2026 (ориентиры, не догма):

- FastAPI / async gateway (оставить Python spine или вынести hot path в Go — по нагрузке);
- pgvector или Qdrant;
- vLLM / llama.cpp / Ollama как first-class on-prem;
- OpenTelemetry;
- GitHub Actions + signed images;
- MCP для корпоративных tools.

---

## 9. Коммерческая упаковка (как продавать с этого репо)

Публичный GitHub = **витрина + due diligence**, не полный IP dump всех внутренних
плейбуков (секреты, ключи, хосты — никогда).

Рекомендуемый набор для лида:

| Артефакт | Назначение |
|----------|------------|
| README фасад + обложка | Хук в соцсетях |
| Этот roadmap | «Мы знаем, куда идём» |
| One-pager | Пересылка ЛПР |
| Architecture one-slide | ИБ / архитекторы |
| Pilot SOW шаблон | 4–8 недель, KPI = citations + latency + uptime |
| Reference deploy | compose-prod / Helm |

**Ценовой каркас (ориентир, не оферта):**

- Pilot fixed-price (внедрение + обучение админов);
- Annual license / support (on-prem);
- Optional managed inference или help with GPU sizing.

---

## 10. Риски

| Риск | Митигация |
|------|-----------|
| Заказчик думает, что хакатон = готовый продукт | Честный «не для продакшена» + pilot scope |
| Open WebUI апстрим ломает патчи | Pin digest + thin UI roadmap |
| KB без ACL = утечка между отделами | Tenant + corpus ACL с дня 1 пилота |
| Vendor lock на один cloud LLM | Model Plane adapters |
| WOW-фичи отвлекают от KB | Council/PPTX = phase 1.5+, не gate пилота |

---

## 11. Первые 10 инженерных эпиков (если начинать завтра)

1. `TENANT-01` — workspace_id во всех store и trace.
2. `AUTH-01` — OIDC + service API keys.
3. `KB-01` — ingest pipeline → vector store → retrieve API.
4. `KB-02` — citations в chat completion (structured).
5. `MODEL-01` — provider config без MWS hardcode.
6. `DATA-01` — Postgres + volume policy; убрать `/tmp` memory.
7. `UI-01` — disable WebUI RAG permanently; document.
8. `OPS-01` — CI pytest + docker build.
9. `OPS-02` — compose-prod + backup runbook.
10. `EVAL-01` — customer golden set harness.

---

## 12. Связь с репозиторием

| Документ | Роль |
|----------|------|
| [`FEATURE_MATRIX.md`](../FEATURE_MATRIX.md) | Что **уже** реализовано в стенде |
| [`ARCHITECTURE.md`](../ARCHITECTURE.md) | Текущий runtime path |
| [`ROADMAP.md`](../ROADMAP.md) | Исторический план хакатона / post-hack debt |
| **Этот файл** | Коммерческая стратегия и целевая форма |
| [`README.md`](../README.md) | Витрина SCANOVICH |

---

## 13. Авторы хакатонного каркаса

См. [`AUTHORS.md`](../AUTHORS.md). Спасибо команде из трёх человек — это был рабочий
тренажёр. Дальше продукт строится **поверх уроков**, а не копированием всех
компромиссов стенда.

---

*Вопросы по пилоту / внедрению — через контакты Owner в `AUTHORS.md` / GitHub
[@FUYOH666](https://github.com/FUYOH666).*
