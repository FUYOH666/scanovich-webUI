#!/usr/bin/env python3
"""Print ORCHESTRATOR_API_KEY or LITELLM_MASTER_KEY from a dotenv-style file (first match)."""
from __future__ import annotations

import re
import sys
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
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        return v
    return None


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: read_env_key.py PATH/.env", file=sys.stderr)
        sys.exit(2)
    path = Path(sys.argv[1])
    if not path.is_file():
        sys.exit(1)
    raw = path.read_text(encoding="utf-8")
    for k in ("ORCHESTRATOR_API_KEY", "LITELLM_MASTER_KEY"):
        v = val_for(k, raw)
        if v:
            print(v, end="")
            return
    sys.exit(1)


if __name__ == "__main__":
    main()
