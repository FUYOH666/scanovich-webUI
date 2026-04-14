# GPTHub Prod — runs scripts/demo.sh. Loads ORCHESTRATOR_API_KEY from .env
# (ORCHESTRATOR_API_KEY or LITELLM_MASTER_KEY) when not already in the environment.

.PHONY: help bootstrap-env demo demo-baseline demo-benchmark docker-rebuild docker-rebuild-rag docker-reset docker-logs-save docker-logs-filter-health pptx-bench-nature open-webui-up open-webui-down open-webui-image-up open-webui-image-down

ORCHESTRATOR_URL ?= http://localhost:8089
COMPOSE_FILE ?= infra/docker-compose.yml
OPEN_WEBUI_DIR ?= open-webui
OPEN_WEBUI_COMPOSE ?= $(CURDIR)/$(OPEN_WEBUI_DIR)/docker-compose.yaml
# Готовый образ форка (без локального build); см. open-webui-image-up
OPEN_WEBUI_IMAGE ?= ghcr.io/usatovpavel/open-webui:feature-audio
OPEN_WEBUI_CONTAINER ?= open-webui-prebuilt
OPEN_WEBUI_PORT ?= 3000
# Для связки с Ollama на хосте; для docker-сети с сервисом ollama — переопределить (например http://ollama:11434 + --network)
OPEN_WEBUI_OLLAMA_URL ?= http://host.docker.internal:11434
LOG_TAIL ?= 400
BOOTSTRAP_ENV_EXAMPLE ?= $(CURDIR)/bootstrap.env.example
BOOTSTRAP_MWS_EXAMPLE ?= $(CURDIR)/.env.mws.local.example

# If both targets are requested in one make invocation, baseline flag wins for both.
DEMO_EXTRA := $(if $(filter demo-baseline,$(MAKECMDGOALS)),--skip-wow,)

help:
	@echo "Targets:"
	@echo "  make bootstrap-env - .env из bootstrap.env.example + .env.mws.local из .env.mws.local.example (см. ниже)"
	@echo "  make demo              - scripts/demo.sh"
	@echo "  make demo-baseline     - scripts/demo.sh --skip-wow"
	@echo "  make demo-benchmark    - scripts/demo_benchmark.py (timed smoke)"
	@echo "  make docker-rebuild     - docker compose build + up -d orchestrator (pick up code changes)"
	@echo "  make docker-rebuild-rag  - same + embedding-shim (compose profile rag)"
	@echo "  make docker-reset        - compose --profile rag down + up -d (uses infra/docker-compose.yml)"
	@echo "  make docker-logs         - последние логи всех сервисов стека (LOG_TAIL=$(LOG_TAIL))"
	@echo "  make docker-logs-follow  - поток логов (-f), Ctrl+C выход"
	@echo "  make docker-logs-save    - записать логи в logs/compose-YYYYMMDD-HHMMSS.log"
	@echo "    (для rag: COMPOSE_PROFILES=rag make docker-logs-save)"
	@echo "  make docker-logs-filter-health - последний logs/compose-*.log → logs/filtered.log (без health/readyz)"
	@echo "  make pptx-bench-nature      - live PPTX bench (природа, все шаблоны assets/pttx) → tmp/*.pptx; нужен .env"
	@echo "  make open-webui-up - docker compose в $(OPEN_WEBUI_DIR)/ (Ollama + Open Web UI, порт OPEN_WEBUI_PORT)"
	@echo "  make open-webui-down        - остановить compose-проект $(OPEN_WEBUI_DIR)/"
	@echo "  make open-webui-image-up - docker pull OPEN_WEBUI_IMAGE + run (только UI; порт OPEN_WEBUI_PORT)"
	@echo "  make open-webui-image-down - остановить контейнер OPEN_WEBUI_CONTAINER"
	@echo "Env: ORCHESTRATOR_URL (default $(ORCHESTRATOR_URL)); ORCHESTRATOR_API_KEY overrides .env; OPEN_WEBUI_IMAGE (default $(OPEN_WEBUI_IMAGE))"
	@echo "Bootstrap: BOOTSTRAP_FORCE=1 перезаписать существующие .env / .env.mws.local из примеров"

# Первый запуск: .env + .env.mws.local из шаблонов в этом репозитории (без внешних каталогов).
# bootstrap.env.example — сокращённый прод-шаблон; полный комментарий — .env.example.
bootstrap-env:
	@set -euo pipefail; \
	be="$(BOOTSTRAP_ENV_EXAMPLE)"; \
	me="$(BOOTSTRAP_MWS_EXAMPLE)"; \
	test -f "$$be" || { echo "FATAL: нет $$be" >&2; exit 1; }; \
	if [ -f "$(CURDIR)/.env" ] && [ "$${BOOTSTRAP_FORCE:-}" != "1" ]; then \
	  echo "OK: $(CURDIR)/.env уже есть — не перезаписываю (BOOTSTRAP_FORCE=1 — взять заново из bootstrap.env.example)"; \
	else \
	  cp "$$be" "$(CURDIR)/.env"; \
	  chmod 600 "$(CURDIR)/.env" 2>/dev/null || true; \
	  echo "Создан/обновлён $(CURDIR)/.env ← bootstrap.env.example"; \
	fi; \
	if [ -f "$(CURDIR)/.env.mws.local" ] && [ "$${BOOTSTRAP_FORCE:-}" != "1" ]; then \
	  echo "OK: $(CURDIR)/.env.mws.local уже есть — не перезаписываю"; \
	else \
	  if [ -f "$$me" ]; then \
	    cp "$$me" "$(CURDIR)/.env.mws.local"; \
	    chmod 600 "$(CURDIR)/.env.mws.local" 2>/dev/null || true; \
	    echo "Создан/обновлён $(CURDIR)/.env.mws.local ← .env.mws.local.example"; \
	  else \
	    : > "$(CURDIR)/.env.mws.local"; \
	    chmod 600 "$(CURDIR)/.env.mws.local" 2>/dev/null || true; \
	    echo "Пустой $(CURDIR)/.env.mws.local (нет $$me) — задай MWS_GPT_API_BASE и MWS_GPT_API_KEY"; \
	  fi; \
	fi; \
	echo ""; \
	echo "=== Дальше ==="; \
	echo "1) Отредактируй секреты в .env и .env.mws.local (замени replace-with-*, ключи MWS, TAVILY, GPTHUB_INTERNAL_EVENT_SECRET, …)."; \
	echo "2) Полный список переменных и пояснения: .env.example"; \
	echo "3) Поднять стек (два env-file + profile rag):"; \
	echo "   docker compose -f $(CURDIR)/$(COMPOSE_FILE) --env-file $(CURDIR)/.env --env-file $(CURDIR)/.env.mws.local --profile rag up -d --build"

docker-rebuild:
	docker compose -f "$(CURDIR)/$(COMPOSE_FILE)" build orchestrator
	docker compose -f "$(CURDIR)/$(COMPOSE_FILE)" up -d orchestrator

docker-rebuild-rag:
	docker compose -f "$(CURDIR)/$(COMPOSE_FILE)" --profile rag build orchestrator embedding-shim
	docker compose -f "$(CURDIR)/$(COMPOSE_FILE)" --profile rag up -d orchestrator embedding-shim

docker-logs-save:
	@mkdir -p "$(CURDIR)/logs"
	@ts=$$(date +%Y%m%d-%H%M%S); \
	out="$(CURDIR)/logs/compose-$$ts.log"; \
	docker compose -f "$(CURDIR)/$(COMPOSE_FILE)" logs --no-color --timestamps > "$$out"; \
	echo "Wrote $$out"

# Drop noisy probe lines from the newest saved compose log (see docker-logs-save).
docker-logs-filter-health:
	@bash -euo pipefail -c '\
	  d="$(CURDIR)/logs"; \
	  mkdir -p "$$d"; \
	  latest=$$(ls -t "$$d"/compose-*.log 2>/dev/null | head -1); \
	  [[ -n "$$latest" && -f "$$latest" ]] || { echo "No $$d/compose-*.log — run make docker-logs-save first" >&2; exit 2; }; \
	  grep -vE "(/health/liveliness|/readyz)" "$$latest" > "$$d/filtered.log"; \
	  echo "Wrote $$d/filtered.log (from $$(basename "$$latest"))"'

demo:
	@ORCHESTRATOR_URL="$(ORCHESTRATOR_URL)" bash -euo pipefail -c '\
	  key="$${ORCHESTRATOR_API_KEY:-}"; \
	  if [[ -z "$$key" && -f "$(CURDIR)/.env" ]]; then \
	    key="$$(python3 "$(CURDIR)/scripts/read_env_key.py" "$(CURDIR)/.env")"; \
	  fi; \
	  export ORCHESTRATOR_API_KEY="$$key"; \
	  [[ -n "$$ORCHESTRATOR_API_KEY" ]] || { echo "FATAL: ORCHESTRATOR_API_KEY empty — export it or set in .env (ORCHESTRATOR_API_KEY or LITELLM_MASTER_KEY)" >&2; exit 2; }; \
	  exec "$(CURDIR)/scripts/demo.sh" $(DEMO_EXTRA)'

demo-benchmark:
	@ORCHESTRATOR_URL="$(ORCHESTRATOR_URL)" bash -euo pipefail -c '\
	  key="$${ORCHESTRATOR_API_KEY:-}"; \
	  if [[ -z "$$key" && -f "$(CURDIR)/.env" ]]; then \
	    key="$$(python3 "$(CURDIR)/scripts/read_env_key.py" "$(CURDIR)/.env")"; \
	  fi; \
	  export ORCHESTRATOR_API_KEY="$$key"; \
	  [[ -n "$$ORCHESTRATOR_API_KEY" ]] || { echo "FATAL: ORCHESTRATOR_API_KEY empty — export it or set in .env (ORCHESTRATOR_API_KEY or LITELLM_MASTER_KEY)" >&2; exit 2; }; \
	  exec python3 "$(CURDIR)/scripts/demo_benchmark.py"'

docker-reset:
	docker compose -f "$(CURDIR)/$(COMPOSE_FILE)" --profile rag down
	docker compose -f "$(CURDIR)/$(COMPOSE_FILE)" --profile rag up -d

# Vendored fork: https://github.com/open-webui/open-webui style stack (ollama + open-webui).
# Compose file lives under OPEN_WEBUI_DIR; build context is that directory.
open-webui-up:
	@[ -f "$(OPEN_WEBUI_COMPOSE)" ] || { echo "FATAL: missing $(OPEN_WEBUI_COMPOSE) — clone or submodule open-webui" >&2; exit 2; }
	docker compose -f "$(OPEN_WEBUI_COMPOSE)" up -d --build

open-webui-down:
	@[ -f "$(OPEN_WEBUI_COMPOSE)" ] || { echo "FATAL: missing $(OPEN_WEBUI_COMPOSE)" >&2; exit 2; }
	docker compose -f "$(OPEN_WEBUI_COMPOSE)" down

# Готовый образ с registry (без каталога open-webui и без локального build).
# Имя контейнера по умолчанию — open-webui-prebuilt, чтобы не пересекаться с compose (container_name: open-webui).
open-webui-image-up:
	docker pull "$(OPEN_WEBUI_IMAGE)"
	-docker rm -f "$(OPEN_WEBUI_CONTAINER)" 2>/dev/null
	docker run -d \
	  --name "$(OPEN_WEBUI_CONTAINER)" \
	  --restart unless-stopped \
	  -p "$(OPEN_WEBUI_PORT):8080" \
	  -e "OLLAMA_BASE_URL=$(OPEN_WEBUI_OLLAMA_URL)" \
	  -e "WEBUI_SECRET_KEY=" \
	  --add-host=host.docker.internal:host-gateway \
	  -v "$(OPEN_WEBUI_CONTAINER)-data:/app/backend/data" \
	  "$(OPEN_WEBUI_IMAGE)"

open-webui-image-down:
	-docker rm -f "$(OPEN_WEBUI_CONTAINER)" 2>/dev/null

# Live LLM + LiteLLM: loads repo-root .env (same keys as compose / demo).
# Writes decks under $(CURDIR)/tmp/ (gitignored).
pptx-bench-nature:
	@[ -f "$(CURDIR)/.env" ] || { echo "FATAL: missing $(CURDIR)/.env (need ORCHESTRATOR_API_KEY, LITELLM_BASE_URL, …)" >&2; exit 2; }
	@cd "$(CURDIR)/apps/orchestrator" && \
	set -a && . "$(CURDIR)/.env" && set +a && \
	echo "KEY len: $${#ORCHESTRATOR_API_KEY}" && \
	PPTX_BENCH=1 \
	LITELLM_BASE_URL="$${LITELLM_BASE_URL:-http://127.0.0.1:4000}" \
	ORCHESTRATOR_API_KEY="$${ORCHESTRATOR_API_KEY}" \
	uv run pytest tests/pptx_tests/test_bench_nature_templates.py -s -rs