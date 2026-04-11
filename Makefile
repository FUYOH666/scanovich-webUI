# GPTHub Prod — runs scripts/demo.sh. Loads ORCHESTRATOR_API_KEY from .env
# (ORCHESTRATOR_API_KEY or LITELLM_MASTER_KEY) when not already in the environment.

.PHONY: help demo demo-baseline

ORCHESTRATOR_URL ?= http://localhost:8089

# If both targets are requested in one make invocation, baseline flag wins for both.
DEMO_EXTRA := $(if $(filter demo-baseline,$(MAKECMDGOALS)),--skip-wow,)

help:
	@echo "Targets:"
	@echo "  make demo           - scripts/demo.sh"
	@echo "  make demo-baseline  - scripts/demo.sh --skip-wow"
	@echo "Env: ORCHESTRATOR_URL (default $(ORCHESTRATOR_URL)); ORCHESTRATOR_API_KEY overrides .env"

demo:
	@ORCHESTRATOR_URL="$(ORCHESTRATOR_URL)" bash -euo pipefail -c '\
	  key="$${ORCHESTRATOR_API_KEY:-}"; \
	  if [[ -z "$$key" && -f "$(CURDIR)/.env" ]]; then \
	    key="$$(python3 "$(CURDIR)/scripts/read_env_key.py" "$(CURDIR)/.env")"; \
	  fi; \
	  export ORCHESTRATOR_API_KEY="$$key"; \
	  [[ -n "$$ORCHESTRATOR_API_KEY" ]] || { echo "FATAL: ORCHESTRATOR_API_KEY empty — export it or set in .env (ORCHESTRATOR_API_KEY or LITELLM_MASTER_KEY)" >&2; exit 2; }; \
	  exec "$(CURDIR)/scripts/demo.sh" $(DEMO_EXTRA)'
