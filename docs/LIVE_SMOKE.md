# Live Smoke Journal

> Журнал живых прогонов через поднятый `docker compose` стек. Заполняется
> **при каждом** live-тесте и защищает нас от «работало на прошлой неделе».
>
> Правило: **никакой ряд не помечается `Implemented` в
> `FEATURE_MATRIX.md` без хотя бы одной записи здесь**. Unit-тест этого
> не заменяет — unit-тест проверяет код, а журнал проверяет стек.

## Формат записи

```
## <YYYY-MM-DD HH:MM> — <короткое имя сценария>

- **Stack commit:** <git sha>
- **Env:** <какой .env.mws.local, какие live-флаги>
- **Input:** <что отправили>
- **Model(s) used:** <из X-GPTHub-Trace>
- **Latency:** <миллисекунды>
- **Result:** OK / FAIL / PARTIAL
- **Trace highlights:** <classifier task_type, router role, fallback chain, artifacts>
- **Notes:** <что заметили, что сломалось, что починили>
```

Если прогон **упал** — обязательно фиксируем, что именно, и решение
(починили / обошли / отложили / kill switch).

---

## 2026-04-11 — Step 1 teardown legacy v3 stack

- **Stack commit:** tag `smoke-green` on `main` (resolve SHA with `git rev-parse --short HEAD`)
- **Env:** `.env` bootstrapped from `.env.example` with local-only auth placeholders (not committed); `.env.mws.local` present for LiteLLM→MWS (secrets not logged).
- **Input:** `docker rm -f gpthub-v3-orchestrator gpthub-v3-embedding-shim gpthub-v3-open-webui gpthub-v3-litellm`
- **Model(s) used:** _n/a_
- **Latency:** under 1 s (CLI)
- **Result:** OK
- **Trace highlights:** _n/a_
- **Notes:** All four legacy names removed on this host; frees 3000/4000/8089 for `gpthub-prod-*` stack.

## 2026-04-11 — Step 1 prod compose bring-up

- **Stack commit:** tag `smoke-green` on `main` (resolve SHA with `git rev-parse --short HEAD`)
- **Env:** same as above; compose file `infra/docker-compose.yml`; no `rag` profile.
- **Input:** `docker compose -f infra/docker-compose.yml up -d --build`
- **Model(s) used:** _n/a_
- **Latency:** orchestrator image build ~2 min cold; total bring-up ~20 s after images warm
- **Result:** OK
- **Trace highlights:** _n/a_
- **Notes:** Services `gpthub-prod-litellm`, `gpthub-prod-orchestrator`, `gpthub-prod-open-webui` created; `docker compose ps` shows litellm/orchestrator healthy; WebUI container up on port 3000.

## 2026-04-11 — Step 1 health, readiness, WebUI HTTP, baseline curl

- **Stack commit:** tag `smoke-green` on `main` (resolve SHA with `git rev-parse --short HEAD`)
- **Env:** `ORCHESTRATOR_API_KEY` aligned with `LITELLM_MASTER_KEY` for curl/WebUI.
- **Input:** `GET /healthz`, `GET /readyz`, `GET http://localhost:3000/`, then `ORCHESTRATOR_URL=http://localhost:8089 ORCHESTRATOR_API_KEY=… ./scripts/demo.sh --skip-wow`
- **Model(s) used:** text + URL steps hit MWS via LiteLLM (see trace on successful rows); image-gen step WARN (fell through to chat — upstream `qwen-image` path not confirmed in this run).
- **Latency:** full `demo.sh --skip-wow` ~43 s end-to-end on this host
- **Result:** OK (API baseline); **WARN** on optional image-gen short-circuit
- **Trace highlights:** Row1/8/10 returned `X-GPTHub-Trace`; memory remember/recall OK.
- **Notes:** Fixed orchestrator bug where image-intent block shadowed `last_user_text()` helper ([`main.py`](../apps/orchestrator/gpthub_orchestrator/main.py) rename to `image_intent_user_text`). **WebUI manual Demo Lock chunk** (текст + PDF + «нарисуй кота» в браузере) — оператор должен прогнать отдельно; здесь зафиксированы compose + health + `demo.sh` как автоматический baseline.

---

## Шаг 1 — Docker bring-up (чеклист ROADMAP §0.4)

Сводка: три журнальных записи выше закрывают teardown / compose / health+curl.
Дополнительно вручную: три сценария **через WebUI** (текст, PDF+вопрос, image prompt) — перенести в отдельные записи шага 2 при первом полном P0-прогоне.

---

## Шаг 2 — Полный P0 smoke (ряды 1–12)

### [pending] Row 1 — Text chat

- **Stack commit:** _—_
- **Input:** `"Объясни, что такое RAG в двух предложениях"`
- **Model(s) used:** _—_
- **Latency:** _—_
- **Result:** _не выполнено_
- **Trace highlights:** _—_
- **Notes:** _—_

### [pending] Row 2 — Voice chat (UI-managed)

- **Input:** голосовое сообщение через WebUI mic
- **Path:** STT → text → orchestrator → LiteLLM → MWS
- **Result:** _не выполнено_

### [pending] Row 3 — Image generation

- **Input:** `"Нарисуй рыжего кота в шляпе"`
- **Expected:** inline markdown `![](...)` с URL из `qwen-image`
- **Result:** _не выполнено_

### [pending] Row 4 — ASR

- **Input:** загруженный .wav файл с фразой
- **Expected:** artifact `transcript` в system, ответ модели по содержимому
- **Result:** _не выполнено_

### [pending] Row 5 — VLM

- **Input:** фото с текстом на английском
- **Expected:** role `vision`, модель из `gpt-hub-vision` chain, ответ по изображению
- **Result:** _не выполнено_

### [pending] Row 6 — Files (PDF + plain text)

- **Input:** PDF с парой абзацев + .md файл
- **Expected:** `document_text` artifacts в system, ответ по содержимому
- **Result:** _не выполнено_

### [pending] Row 7 — Web search (Tavily)

- **Prereq:** `ENABLE_WEB_SEARCH=true` + `TAVILY_API_KEY` в env WebUI
- **Input:** `"Что нового про MWS GPT на этой неделе?"`
- **Result:** _не выполнено_

### [pending] Row 8 — URL parsing

- **Input:** `"Прочитай https://example.com и сделай summary"`
- **Expected:** `url_text` artifact в system, ответ по содержимому
- **Result:** _не выполнено_

### [pending] Row 9 — Long-term memory

- **Step 1 Input:** `"Запомни, что я отвечаю за интеграцию MWS в наш продукт"`
- **Step 1 Expected:** `"Запомнил: ..."` ответ + факт в SQLite + embedding
- **Step 2 Input:** `"Что ты обо мне помнишь?"`
- **Step 2 Expected:** список фактов включая только что добавленный
- **Step 3 Input:** `"Забудь про интеграцию"`
- **Step 3 Expected:** подтверждение + удаление из store
- **Result:** _не выполнено_

### [pending] Row 10 — Auto model routing

- **Input 1:** `"Напиши функцию на Python"` → ожидается `reasoning/coder` роль
- **Input 2:** `"Кратко перескажи PDF"` → ожидается `doc` роль
- **Expected:** разные role / model_name в `X-GPTHub-Trace`
- **Result:** _не выполнено_

### [pending] Row 11 — Manual model choice

- **Prereq:** `ORCHESTRATOR_MODELS_CATALOG=all` + `AUTO_ROUTE_MODEL=false`
- **Input:** выбрать `gpt-hub-doc` в dropdown WebUI, отправить запрос
- **Expected:** в trace `model_used=gpt-hub-doc`, даже если classifier хотел другое
- **Result:** _не выполнено_

### [pending] Row 12 — Markdown / код

- **Input:** `"Покажи пример fastapi endpoint с typing"`
- **Expected:** markdown code block, подсветка работает в WebUI
- **Result:** _не выполнено_

---

## Шаг 6 — Репетиция демо-сценария

### [pending] Полный прогон Demo Lock

- **Scenario steps:**
  1. mixed input (PDF + фото + аудио + URL + текст)
  2. «запомни моё предпочтение X»
  3. «что ты обо мне помнишь?»
  4. (опционально) «проведи deep research» → Expert Council
  5. (опционально) «сделай презентацию» → PPTX
  6. trace reveal в DevTools
- **Time:** _—_ (цель: 2–3 минуты)
- **Result:** _не выполнено_
- **Notes:** _—_

---

## Kill switch log

Сюда пишем все случаи, когда сработал kill switch из `ROADMAP.md` раздел 0.5.

| Когда | Компонент | Причина | Решение |
|---|---|---|---|
| _—_ | _—_ | _—_ | _—_ |

---

## Итоговая статистика перед `demo-ready`

- **Всего живых прогонов:** _—_
- **Успешных:** _—_
- **Частичных:** _—_
- **Провальных:** _—_
- **Средний latency текстового запроса:** _—_
- **Средний latency VLM запроса:** _—_
- **Средний latency image-gen:** _—_

Этот блок заполняется перед git tag `demo-ready` и идёт в презентацию
как слайд «реальные цифры на живом MWS».
