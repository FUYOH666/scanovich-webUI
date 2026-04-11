#!/usr/bin/env bash
# GPTHub Prod — idempotent demo smoke script.
#
# Runs the full Demo Lock scenario (ROADMAP.md §2) against a live
# docker stack using plain curl. Safe to run repeatedly. If everything
# here is green, recording the demo video is a formality.
#
# Usage:
#   ORCHESTRATOR_URL=http://localhost:8089 \
#   ORCHESTRATOR_API_KEY=... \
#   ./scripts/demo.sh [--skip-wow]
#
# Environment:
#   ORCHESTRATOR_URL       default http://localhost:8089
#   ORCHESTRATOR_API_KEY   required — same as LITELLM_MASTER_KEY for WebUI
#   DEMO_SKIP_WOW          if set to 1, skip Expert Council + PPTX checks
#   DEMO_USER_ID           optional user id for memory tests (default: demo)
#
# Exit code is non-zero if any mandatory step fails. Optional steps
# (image gen, URL fetch, memory) only warn on failure so the baseline
# smoke still goes green when upstream hiccups.

set -u

ORCHESTRATOR_URL="${ORCHESTRATOR_URL:-http://localhost:8089}"
ORCHESTRATOR_API_KEY="${ORCHESTRATOR_API_KEY:-}"
DEMO_USER_ID="${DEMO_USER_ID:-demo}"

if [[ -z "${ORCHESTRATOR_API_KEY}" ]]; then
  echo "FATAL: ORCHESTRATOR_API_KEY is required" >&2
  exit 2
fi

SKIP_WOW=0
for arg in "$@"; do
  case "${arg}" in
    --skip-wow) SKIP_WOW=1 ;;
    *) echo "Unknown arg: ${arg}" >&2; exit 2 ;;
  esac
done

PASS=0
FAIL=0
WARN=0

step() {
  printf '\n=== %s ===\n' "$1"
}

ok() {
  PASS=$((PASS + 1))
  printf '  OK: %s\n' "$1"
}

fail() {
  FAIL=$((FAIL + 1))
  printf '  FAIL: %s\n' "$1" >&2
}

warn() {
  WARN=$((WARN + 1))
  printf '  WARN: %s\n' "$1" >&2
}

auth_header() {
  printf 'Authorization: Bearer %s' "${ORCHESTRATOR_API_KEY}"
}

# -----------------------------------------------------------------------------
# 1. Health + readiness
# -----------------------------------------------------------------------------

step "1/9 Health + readiness"

if curl -sSf "${ORCHESTRATOR_URL}/healthz" >/dev/null; then
  ok "/healthz returns 200"
else
  fail "/healthz unreachable — stack not up?"
  exit 1
fi

if curl -sSf "${ORCHESTRATOR_URL}/readyz" >/dev/null; then
  ok "/readyz returns 200"
else
  warn "/readyz failed — LiteLLM may be unreachable"
fi

# -----------------------------------------------------------------------------
# 2. Model catalog
# -----------------------------------------------------------------------------

step "2/9 GET /v1/models"

models_body="$(curl -sS -H "$(auth_header)" "${ORCHESTRATOR_URL}/v1/models" || true)"
if [[ -n "${models_body}" && "${models_body}" == *'"id"'* ]]; then
  ok "model catalog returned ids"
else
  fail "model catalog empty / malformed: ${models_body:0:200}"
fi

# -----------------------------------------------------------------------------
# 3. Row 1 — text chat
# -----------------------------------------------------------------------------

step "3/9 Row 1 — text chat"

text_body=$(cat <<'JSON'
{
  "model": "gpt-hub",
  "stream": false,
  "messages": [
    {"role": "user", "content": "Объясни, что такое RAG в двух предложениях."}
  ]
}
JSON
)

resp="$(curl -sS -D /tmp/gpthub_demo_headers.txt \
  -H "Content-Type: application/json" \
  -H "$(auth_header)" \
  -X POST "${ORCHESTRATOR_URL}/v1/chat/completions" \
  -d "${text_body}" || true)"
if [[ "${resp}" == *'"choices"'* ]]; then
  ok "text chat returned choices[]"
  if grep -qi '^x-gpthub-trace:' /tmp/gpthub_demo_headers.txt; then
    ok "X-GPTHub-Trace present"
  else
    warn "X-GPTHub-Trace missing"
  fi
else
  fail "text chat missing choices[]: ${resp:0:200}"
fi

# -----------------------------------------------------------------------------
# 4. Row 8 — URL parsing (ingest)
# -----------------------------------------------------------------------------

step "4/9 Row 8 — URL parsing"

url_body=$(cat <<'JSON'
{
  "model": "gpt-hub",
  "stream": false,
  "messages": [
    {"role": "user", "content": "Прочитай https://example.com и скажи о чём страница одним предложением."}
  ]
}
JSON
)

resp="$(curl -sS \
  -H "Content-Type: application/json" \
  -H "$(auth_header)" \
  -X POST "${ORCHESTRATOR_URL}/v1/chat/completions" \
  -d "${url_body}" || true)"
if [[ "${resp}" == *'"choices"'* ]]; then
  ok "URL ingest returned choices[]"
else
  warn "URL ingest missing choices: ${resp:0:200}"
fi

# -----------------------------------------------------------------------------
# 5. Row 3 — image generation
# -----------------------------------------------------------------------------

step "5/9 Row 3 — image generation"

img_body=$(cat <<'JSON'
{
  "model": "gpt-hub",
  "stream": false,
  "messages": [
    {"role": "user", "content": "Нарисуй рыжего кота в шляпе."}
  ]
}
JSON
)

resp="$(curl -sS \
  -H "Content-Type: application/json" \
  -H "$(auth_header)" \
  -X POST "${ORCHESTRATOR_URL}/v1/chat/completions" \
  -d "${img_body}" || true)"
if [[ "${resp}" == *'![' && "${resp}" == *'](http'* ]] || [[ "${resp}" == *'data:image/png;base64'* ]]; then
  ok "image gen returned inline markdown image"
elif [[ "${resp}" == *'"choices"'* ]]; then
  warn "image gen fell through to regular chat (MWS qwen-image may be down)"
else
  fail "image gen returned no choices: ${resp:0:200}"
fi

# -----------------------------------------------------------------------------
# 6. Row 9 — memory commands
# -----------------------------------------------------------------------------

step "6/9 Row 9 — memory commands"

remember_body=$(cat <<JSON
{
  "model": "gpt-hub",
  "stream": false,
  "messages": [
    {"role": "user", "name": "${DEMO_USER_ID}", "content": "Запомни, что я отвечаю за интеграцию MWS в наш продукт."}
  ]
}
JSON
)

resp="$(curl -sS \
  -H "Content-Type: application/json" \
  -H "$(auth_header)" \
  -X POST "${ORCHESTRATOR_URL}/v1/chat/completions" \
  -d "${remember_body}" || true)"
if [[ "${resp}" == *'Запомнил'* ]]; then
  ok "remember command short-circuited"
else
  warn "remember did not short-circuit: ${resp:0:200}"
fi

recall_body=$(cat <<JSON
{
  "model": "gpt-hub",
  "stream": false,
  "messages": [
    {"role": "user", "name": "${DEMO_USER_ID}", "content": "Что ты обо мне помнишь?"}
  ]
}
JSON
)

resp="$(curl -sS \
  -H "Content-Type: application/json" \
  -H "$(auth_header)" \
  -X POST "${ORCHESTRATOR_URL}/v1/chat/completions" \
  -d "${recall_body}" || true)"
if [[ "${resp}" == *'интеграц'* ]]; then
  ok "recall returned the stored fact"
else
  warn "recall did not return the fact: ${resp:0:200}"
fi

# -----------------------------------------------------------------------------
# 7. Row 10 — classifier routes reasoning task
# -----------------------------------------------------------------------------

step "7/9 Row 10 — classifier routing"

reason_body=$(cat <<'JSON'
{
  "model": "gpt-hub",
  "stream": false,
  "messages": [
    {"role": "user", "content": "Напиши на Python функцию, которая находит N-е простое число."}
  ]
}
JSON
)

resp="$(curl -sS -D /tmp/gpthub_demo_headers.txt \
  -H "Content-Type: application/json" \
  -H "$(auth_header)" \
  -X POST "${ORCHESTRATOR_URL}/v1/chat/completions" \
  -d "${reason_body}" || true)"
if [[ "${resp}" == *'"choices"'* ]]; then
  ok "reasoning task returned choices[]"
  trace_line="$(grep -i '^x-gpthub-trace:' /tmp/gpthub_demo_headers.txt || true)"
  if [[ -n "${trace_line}" ]]; then
    ok "classifier trace present: ${trace_line:0:120}..."
  else
    warn "no trace header on reasoning task"
  fi
else
  fail "reasoning task missing choices: ${resp:0:200}"
fi

# -----------------------------------------------------------------------------
# 8. Optional wow — Expert Council
# -----------------------------------------------------------------------------

if [[ "${SKIP_WOW}" -eq 1 ]]; then
  step "8/9 WOW-1 Expert Council — SKIPPED"
else
  step "8/9 WOW-1 Expert Council (if merged)"
  council_body=$(cat <<'JSON'
{
  "model": "gpt-hub",
  "stream": false,
  "messages": [
    {"role": "user", "content": "/research Проведи глубокое исследование по архитектурам retrieval-augmented generation в корпоративных ассистентах."}
  ]
}
JSON
)

  resp="$(curl -sS \
    -H "Content-Type: application/json" \
    -H "$(auth_header)" \
    -X POST "${ORCHESTRATOR_URL}/v1/chat/completions" \
    -d "${council_body}" || true)"
  if [[ "${resp}" == *'"choices"'* ]]; then
    ok "council path returned a synthesized answer (check trace for 3 experts)"
  else
    warn "council path not merged yet or failed: ${resp:0:200}"
  fi
fi

# -----------------------------------------------------------------------------
# 9. Optional wow — PPTX generation
# -----------------------------------------------------------------------------

if [[ "${SKIP_WOW}" -eq 1 ]]; then
  step "9/9 WOW-3 PPTX generation — SKIPPED"
else
  step "9/9 WOW-3 PPTX generation (if merged)"
  pptx_body=$(cat <<'JSON'
{
  "model": "gpt-hub",
  "stream": false,
  "messages": [
    {"role": "user", "content": "Сделай презентацию на 5 слайдов про GPTHub: проблема, архитектура, mixed input, trace, вывод."}
  ]
}
JSON
)

  resp="$(curl -sS \
    -H "Content-Type: application/json" \
    -H "$(auth_header)" \
    -X POST "${ORCHESTRATOR_URL}/v1/chat/completions" \
    -d "${pptx_body}" || true)"
  if [[ "${resp}" == *'pptx'* || "${resp}" == *'data:application/vnd.openxmlformats-officedocument.presentationml'* ]]; then
    ok "pptx path returned inline .pptx attachment"
  else
    warn "pptx path not merged yet or failed: ${resp:0:200}"
  fi
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------

echo ""
echo "=============================================================="
printf "Demo smoke finished: PASS=%d FAIL=%d WARN=%d\n" "${PASS}" "${FAIL}" "${WARN}"
echo "=============================================================="

if [[ "${FAIL}" -gt 0 ]]; then
  echo "Baseline BROKEN — do not record the demo video." >&2
  exit 1
fi

if [[ "${WARN}" -gt 0 ]]; then
  echo "Baseline green, but some optional paths are soft-failing."
  echo "Record only after resolving the WARNs or deciding to drop those paths."
  exit 0
fi

echo "All green. Baseline is ready for a demo recording."
exit 0
