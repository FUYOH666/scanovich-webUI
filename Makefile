# GPTHub Prod — runs scripts/demo.sh. Loads ORCHESTRATOR_API_KEY from .env
# (ORCHESTRATOR_API_KEY or LITELLM_MASTER_KEY) when not already in the environment.

.PHONY: help demo demo-baseline docker-rebuild docker-rebuild-rag docker-reset docker-logs-save docker-logs-filter-health

ORCHESTRATOR_URL ?= http://localhost:8089
COMPOSE_FILE ?= infra/docker-compose.yml
LOG_TAIL ?= 400

# If both targets are requested in one make invocation, baseline flag wins for both.
DEMO_EXTRA := $(if $(filter demo-baseline,$(MAKECMDGOALS)),--skip-wow,)

help:
	@echo "Targets:"
	@echo "  make demo              - scripts/demo.sh"
	@echo "  make demo-baseline     - scripts/demo.sh --skip-wow"
	@echo "  make docker-rebuild     - docker compose build + up -d orchestrator (pick up code changes)"
	@echo "  make docker-rebuild-rag  - same + embedding-shim (compose profile rag)"
	@echo "  make docker-reset        - compose --profile rag down + up -d (uses infra/docker-compose.yml)"
	@echo "  make docker-logs         - последние логи всех сервисов стека (LOG_TAIL=$(LOG_TAIL))"
	@echo "  make docker-logs-follow  - поток логов (-f), Ctrl+C выход"
	@echo "  make docker-logs-save    - записать логи в logs/compose-YYYYMMDD-HHMMSS.log"
	@echo "    (для rag: COMPOSE_PROFILES=rag make docker-logs-save)"
	@echo "  make docker-logs-filter-health - последний logs/compose-*.log → logs/filtered.log (без health/readyz)"
	@echo "Env: ORCHESTRATOR_URL (default $(ORCHESTRATOR_URL)); ORCHESTRATOR_API_KEY overrides .env"

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

docker-reset:
	docker compose -f "$(CURDIR)/$(COMPOSE_FILE)" --profile rag down
	docker compose -f "$(CURDIR)/$(COMPOSE_FILE)" --profile rag up -d