# Публичный репозиторий: гигиена + OSS-леверидж (80/20)

Документ для команды: **что можно пушить в public GitHub**, и **откуда брать
готовые куски**, чтобы не писать SCANOVICH с нуля.

Связано: [`COMMERCIAL_ROADMAP_RU.md`](COMMERCIAL_ROADMAP_RU.md), [`.gitignore`](../.gitignore).

---

## 1. Гигиена публичного репо

### Уже должно оставаться только локально

| Путь / класс | Почему |
|--------------|--------|
| `.env`, `.env.mws.local`, `bootstrap.env` | Секреты, ключи MWS/Tavily |
| `*.pem`, `credentials.*`, `secrets/` | Ключи и сертификаты |
| `/open-webui/` (локальный clone) | Upstream/fork UI — **не** продукт SCANOVICH; образ с GHCR |
| `logs/`, `*.sqlite3`, `tmp/`, бенч-дампы | Операционные артефакты |
| `.cursor/`, личные заметки | Редактор / черновики |

Правило: в git только **`.env*.example`** с placeholder-значениями
(`sk-your-…`, `replace-with-…`). Никогда реальные TailScale IP, токены туннелей,
пути `/Users/…`, hostname внутренних ВМ.

### Что сознательно публично

- `apps/orchestrator`, `apps/embedding_shim`, `infra/`
- Документация продукта / roadmap / matrix / smoke (без секретов)
- `docs/assets/` (обложки)
- Примеры env

### Open WebUI: решение

В `infra/docker-compose.yml` UI поднимается как **`OPEN_WEBUI_IMAGE`**
(форк на GHCR или upstream pin). Исходники Open WebUI **не должны** жить в этом
репозитории как vendored tree (~5k файлов / сотни MB истории).

- Локально можно клонировать fork рядом: `git clone … open-webui` — путь в
  `.gitignore`.
- Патчи форка — в **отдельном** репо образа (`ghcr.io/usatovpavel/open-webui:…`).
- Документы `docs/WEBUI_PAYLOAD.md` уже описывают ссылки на upstream tag, не на
  локальный tree.

**История git:** удаление из текущего дерева не вычищает старые коммиты. Если
нужен тонкий clone без blob’ов Open WebUI — отдельный `git filter-repo` /
новый orphan-репо (по согласованию с командой).

### Чеклист перед push

```bash
git status
git diff --cached   # нет .env, IP, токенов, абсолютных путей
rg -n 'sk-[a-zA-Z0-9]{20,}|tvly-|eyJ[A-Za-z0-9_-]{20,}|100\.\d+\.\d+\.\d+' \
  $(git diff --cached --name-only)
```

---

## 2. OSS-леверидж: откуда брать 80% результата

Идея: **не форкать весь Dify/RAGFlow**. Брать **слои**, закрывающие дыры
roadmap (KB, citations, multi-user, observability), а **своим** оставить
policy-spine (orchestrator + trace + периметр).

### Рекомендуемый стек заимствования

| Слой SCANOVICH | Брать идеи / код из | Лицензия* | Как использовать (80/20) |
|----------------|---------------------|-----------|---------------------------|
| **Chat UI** | [open-webui/open-webui](https://github.com/open-webui/open-webui) или [LibreChat](https://github.com/danny-avila/LibreChat) | см. upstream | **Образ + конфиг**, не vendor; LibreChat — если нужны multi-user/auth «из коробки» |
| **Model gateway** | [BerriAI/litellm](https://github.com/BerriAI/litellm) | — | Уже есть; расширить providers YAML, cost/budget |
| **Knowledge / RAG** | [infiniflow/ragflow](https://github.com/infiniflow/ragflow) | Apache-2.0 | Парсинг доков, chunk, hybrid retrieval, citations UX — **главный рычаг** |
| **KB workspace UX** | [Mintplex-Labs/anything-llm](https://github.com/Mintplex-Labs/anything-llm) | MIT | Workspaces, docs→chat, простой onboarding для пилота |
| **Enterprise agents RU/CN** | [1Panel-dev/MaxKB](https://github.com/1Panel-dev/MaxKB) | GPL-3.0 | Идеи ACL/отделов; **GPL = осторожно** с копипастой в закрытый код |
| **Workflow platform** | [langgenius/dify](https://github.com/langgenius/dify) | смешанная | Смотреть product UX и pipelines; не тащить целиком (тяжёлый монолит) |
| **RAG pipelines (lib)** | [deepset-ai/haystack](https://github.com/deepset-ai/haystack) | Apache-2.0 | Библиотека пайплайнов в своём `knowledge` сервисе |
| **Observability / eval** | [langfuse/langfuse](https://github.com/langfuse/langfuse) | — | Замена «только X-GPTHub-Trace header» на searchable traces + datasets |
| **Local AI pack** | [coleam00/local-ai-packaged](https://github.com/coleam00/local-ai-packaged) | — | Идеи compose «всё локально» для демо |
| **RU RAG reference** | [chatchat-space/Langchain-Chatchat](https://github.com/chatchat-space/Langchain-Chatchat) | — | Паттерны локальной KB; код часто устаревает — брать идеи |

\*Перед копированием файла — проверить LICENSE репозитория и NOTICE. GPL-3.0
(MaxKB) **не** смешивать в Apache/MIT продукт без юр. решения.

### Что **не** копировать целиком

- Весь Dify / RAGFlow как «наш бренд» — вы конкурируете с ними и тонете в чужом roadmap.
- Полный Open WebUI tree в product repo — уже доказанный антипаттерн (bypass RAG, вес git).

### Практичный путь пилота (минимум своей работы)

```text
1) UI:  Open WebUI или LibreChat  →  OPENAI_API_BASE = SCANOVICH Gateway
2) Gateway:  ваш orchestrator (policy + trace)  →  LiteLLM  →  vLLM/Ollama/cloud
3) KB:  RAGFlow (sidecar) ИЛИ Haystack-сервис  →  retrieve + citations в gateway
4) Obs:  Langfuse (optional) на gateway
```

Так вы продаёте **периметр + политику + внедрение**, а не «написали RAG с нуля».

### Эпики roadmap ↔ готовые куски

| Эпик (roadmap) | Готовый рычаг |
|----------------|---------------|
| `KB-01` / `KB-02` | RAGFlow API или Haystack pipeline + свой citation formatter |
| `AUTH-01` | LibreChat auth / Keycloak + gateway JWT |
| `MODEL-01` | LiteLLM multi-provider (уже) |
| `OPS-01` | Шаблоны CI из любого зрелого OSS; свой pytest оставить |
| `EVAL-01` | Langfuse datasets / promptfoo-подобные harness |

---

## 3. Решение «делать сами vs взять»

| Компонент | Сами | Взять |
|-----------|------|-------|
| Policy / classifier / council short-circuit | да (дифференциатор) | — |
| Trace contract | да (бренд) | экспорт в Langfuse |
| Document parse + hybrid RAG | нет | RAGFlow / Haystack |
| Full chat UI | нет | образ Open WebUI / LibreChat |
| PPTX «красивый» | шаблоны + тонкий planner | python-pptx themes; не агент-с-нуля |
| Multi-tenant ACL | да (тонкий слой) | идеи из AnythingLLM / MaxKB |

---

## 4. Следующие действия команды

1. Держать `.gitignore` и не возвращать `/open-webui/` в индекс.
2. Форк UI — только отдельный репо + GHCR digest pin в `.env.example`.
3. Spike 1 неделя: RAGFlow sidecar → citations в orchestrator (доказательство SKU B).
4. Spike 1 неделя: LibreChat **или** pinned Open WebUI без WebUI-RAG.
5. Перед каждым публичным релизом — чеклист §1.

---

*Обновлять этот файл при выборе конкретного upstream (digest, license review).*
