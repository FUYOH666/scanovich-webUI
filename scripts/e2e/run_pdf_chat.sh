#!/usr/bin/env bash
# E2E: PDF file part → orchestrator ingest → chat completion (non-stream).
#
# Requires a running stack (orchestrator on ORCHESTRATOR_URL).
#
# Usage (from repo root scanovich-webUI):
#   ./scripts/e2e/run_pdf_chat.sh
# ORCHESTRATOR_API_KEY=override ./scripts/e2e/run_pdf_chat.sh   # optional
#
# Reads ORCHESTRATOR_API_KEY from scanovich-webUI/.env if unset (falls back to
# LITELLM_MASTER_KEY in the same file). Does not use `source` on .env (avoids
# broken lines like unquoted GREETING_CANNED_MESSAGE).
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

ORCHESTRATOR_URL="${ORCHESTRATOR_URL:-http://localhost:8089}"
ORCHESTRATOR_API_KEY="${ORCHESTRATOR_API_KEY:-}"
PDF_PATH="${PDF_PATH:-${REPO_ROOT}/apps/orchestrator/tests/sources/Large_Language_Model-Based_Agents_for_Software_Eng.pdf}"

if [[ -z "${ORCHESTRATOR_API_KEY}" ]]; then
  if [[ -f "${ENV_FILE}" ]]; then
    ORCHESTRATOR_API_KEY="$(
      ENV_FILE="${ENV_FILE}" python3 -c '
import os
import re
from pathlib import Path

def val_for(key: str, text: str) -> str | None:
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(rf"^{re.escape(key)}=(.*)$", s)
        if not m:
            continue
        v = m.group(1).strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in (chr(34), chr(39)):
            v = v[1:-1]
        return v
    return None

path = Path(os.environ["ENV_FILE"])
raw = path.read_text(encoding="utf-8")
for k in ("ORCHESTRATOR_API_KEY", "LITELLM_MASTER_KEY"):
    v = val_for(k, raw)
    if v:
        print(v, end="")
        break
'
    )"
  fi
fi

if [[ -z "${ORCHESTRATOR_API_KEY}" ]]; then
  echo "FATAL: ORCHESTRATOR_API_KEY empty — set it or add to ${ENV_FILE}" >&2
  exit 2
fi

if [[ ! -f "${PDF_PATH}" ]]; then
  echo "FATAL: PDF not found: ${PDF_PATH}" >&2
  exit 2
fi

BODY="$(mktemp)"
trap 'rm -f "${BODY}"' EXIT

BODY_OUT="${BODY}" PDF_PATH="${PDF_PATH}" python3 -c '
import base64
import json
import os
from pathlib import Path

pdf = Path(os.environ["PDF_PATH"])
raw = pdf.read_bytes()
b64 = base64.standard_b64encode(raw).decode("ascii")
payload = {
    "model": "gpt-hub",
    "stream": False,
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Дай 3 коротких тезиса о чём документ (на русском). "
                        "Опирайся только на извлечённый из PDF текст."
                    ),
                },
                {
                    "type": "file",
                    "file": {
                        "filename": pdf.name,
                        "file_data": f"data:application/pdf;base64,{b64}",
                    },
                },
            ],
        }
    ],
}
Path(os.environ["BODY_OUT"]).write_text(
    json.dumps(payload, ensure_ascii=False),
    encoding="utf-8",
)
'

echo "=== E2E PDF chat → ${ORCHESTRATOR_URL} ==="
echo "PDF: ${PDF_PATH} ($(wc -c < "${PDF_PATH}") bytes)"

curl -sS \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ORCHESTRATOR_API_KEY}" \
  -X POST "${ORCHESTRATOR_URL}/v1/chat/completions" \
  --data-binary "@${BODY}" \
  | tee /tmp/gpthub_e2e_pdf_response.json

echo ""
if python3 <<'PY'
import json
import sys
with open("/tmp/gpthub_e2e_pdf_response.json", encoding="utf-8") as f:
    r = json.load(f)
sys.exit(0 if r.get("choices") else 1)
PY
then
  echo "OK: response has choices[]"
  python3 <<'PY'
import json
with open("/tmp/gpthub_e2e_pdf_response.json", encoding="utf-8") as f:
    r = json.load(f)
msg = r["choices"][0]["message"]["content"]
print("--- assistant (preview) ---")
print(msg[:1200] + ("…" if len(msg) > 1200 else ""))
PY
  exit 0
fi

echo "FAIL: missing choices or invalid JSON — see /tmp/gpthub_e2e_pdf_response.json" >&2
exit 1
