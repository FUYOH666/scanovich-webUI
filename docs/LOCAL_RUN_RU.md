# Локальный запуск GPTHub Prod (Docker + ENV)

Один канонический путь: **корень репозитория**, два файла окружения в корне, **`infra/docker-compose.yml`**, профиль **`rag`** (LiteLLM + orchestrator + Open WebUI + **embedding-shim**). Подробности стека — [`README.md`](../README.md) и [`infra/docker-compose.yml`](../infra/docker-compose.yml).

---

## Зачем два env-файла и почему только из корня

1. **`.env`** — общие переменные (в т.ч. `OPEN_WEBUI_IMAGE`, ключи для демо, флаги WebUI). Файл **в git не коммитится**; шаблон: [`bootstrap.env.example`](../bootstrap.env.example), полный комментарий: [`.env.example`](../.env.example).
2. **`.env.mws.local`** — секреты MWS (`MWS_GPT_API_BASE`, `MWS_GPT_API_KEY` и т.д.). Шаблон: [`.env.mws.local.example`](../.env.mws.local.example).

`docker compose` в этом проекте **обязан** видеть оба файла через **`--env-file`** из **корня** репо: иначе не подставится `${OPEN_WEBUI_IMAGE}` в YAML, а пути `env_file: ../.env` в [`infra/docker-compose.yml`](../infra/docker-compose.yml) разрешатся относительно каталога `infra/` и могут указывать **мимо** вашего репозитория.

**Не используйте** `--project-directory` на корень вместо явных `--env-file` — это ломало подстановку путей (см. комментарий в [`Makefile`](../Makefile)).

---

## Быстрый туториал (первый запуск)

### 1. Создать env из шаблонов

```bash
cd /path/to/gpthub-prod
make bootstrap-env
```

При необходимости перезаписать существующие файлы: `BOOTSTRAP_FORCE=1 make bootstrap-env`.

### 2. Заполнить секреты

Отредактируйте **`.env`** и **`.env.mws.local`**: замените placeholder-значения на реальные ключи MWS, при необходимости Tavily, `GPTHUB_INTERNAL_EVENT_SECRET` для моста статусов WebUI и т.д. (список полей — `.env.example`).

### 3. Подтянуть образы и поднять стек

Из **корня** репозитория:

```bash
make docker-pull    # опционально, перед up
make docker-up      # --profile rag up -d --build
```

Эквивалент в одну строку (как в конце `make bootstrap-env`):

```bash
docker compose \
  --env-file .env --env-file .env.mws.local \
  -f infra/docker-compose.yml \
  --profile rag up -d --build
```

### 4. Проверить готовность

| Что | URL / команда |
|-----|----------------|
| Open WebUI | http://localhost:3000 |
| LiteLLM | http://localhost:4000 (liveliness в compose) |
| Orchestrator | http://localhost:8089/readyz |

Автоматический смок по API:

```bash
make demo
```

Ожидайте в выводе `PASS=12 FAIL=0` (допустим `WARN` на опциональных шагах).

### 5. Остановить стек

```bash
make docker-down
```

**Быстрый перезапуск** без пересборки образов: `make docker-reset` (= `down` + `up -d` **без** `--build`). После **смены кода** оркестратора используйте `make docker-rebuild` или снова `make docker-up`.

---

## Частые проблемы

### Порты 3000 / 4000 / 8089 заняты

Остановите старые стеки (**`gpthub-v3-*`** и любые другие compose на этих портах).

### `make demo` падает с пустым ключом

В shell не должно висеть устаревший **`export ORCHESTRATOR_API_KEY=...`**, он перебивает чтение из `.env`. Выполните `unset ORCHESTRATOR_API_KEY` или проверьте, что в `.env` задан `ORCHESTRATOR_API_KEY` или `LITELLM_MASTER_KEY` (см. [`Makefile`](../Makefile) цель `demo`).

### WebUI не тот образ

Проверьте **`OPEN_WEBUI_IMAGE`** в `.env` (см. `Makefile` / `bootstrap.env.example`). После смены тега снова **`make docker-pull`**.

---

## Такс-лист (чек-лист перед демо / приёмкой)

Отметьте по порядку:

1. [ ] Репозиторий: актуальная `main`, работа из **корня** `gpthub-prod`.
2. [ ] В корне есть **`.env`** и **`.env.mws.local`** (не пустые критичные ключи).
3. [ ] Выполнен `make bootstrap-env` (или ручная сверка с шаблонами).
4. [ ] Секреты MWS и оркестратора в `.env` / `.env.mws.local` не placeholder.
5. [ ] `unset ORCHESTRATOR_API_KEY` в shell (если раньше экспортировали вручную).
6. [ ] Порты **3000, 4000, 8089** свободны (`lsof` / `docker ps`).
7. [ ] Старые контейнеры **`gpthub-v3-*`** не мешают.
8. [ ] `make docker-pull` (по желанию перед подъёмом).
9. [ ] `make docker-up` (или эквивалентная `docker compose` строка с **двумя** `--env-file` и **`--profile rag`**).
10. [ ] Дождаться healthy: WebUI открывается на :3000.
11. [ ] `curl -sS http://localhost:8089/readyz` — успех.
12. [ ] `make demo` — `PASS=12 FAIL=0` (WARN на опциональных шагах допустим).
13. [ ] Ручные сценарии по матрице (голос, `.wav`, фото VLM, Tavily, ручная модель, PPTX) — по необходимости.
14. [ ] Обновить xlsx при смене матрицы: `uv run --with openpyxl python scripts/build_features_xlsx.py`.
15. [ ] `make docker-down` после работы (или оставить стек — по политике машины).

---

## См. также

- [`README.md`](../README.md) — Quick Start, таблица сервисов.
- [`docs/REPO_HYGIENE.md`](REPO_HYGIENE.md) — что нельзя коммитить в public.
- [`docs/submission/README.md`](submission/README.md) — артефакты сдачи (PDF архитектуры, xlsx, слайды).
