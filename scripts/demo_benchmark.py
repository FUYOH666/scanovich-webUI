#!/usr/bin/env python3
"""GPTHub Prod — timed demo smoke (same steps as scripts/demo.sh).

Measures wall time per HTTP call with time.perf_counter(). Same checks
and --skip-wow as demo.sh. Stdlib only (no pip install).

Environment variables are read from the process environment. If a key is
not set, values are loaded from a dotenv-style file (default:
``scanovich-webUI/.env`` next to this script). Variables already set in
the environment are not overwritten.

Usage:
  python3 scripts/demo_benchmark.py [--skip-wow] [--json report.json]
  python3 scripts/demo_benchmark.py --env-file /path/to/.env

Exit code: 1 if any mandatory step fails (FAIL > 0), else 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class HttpResult:
    status: int | None
    body: str
    headers: dict[str, str]
    seconds: float
    error: str | None = None


@dataclass
class TimingRow:
    step: str
    label: str
    seconds: float | None
    note: str


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def _load_dotenv_file(path: Path, *, verbose: bool = False) -> bool:
    """Populate os.environ from KEY=VALUE lines. Does not override existing keys."""
    if not path.is_file():
        return False
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.lower().startswith("export "):
            s = s[7:].strip()
        if "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        if key in os.environ and os.environ[key] != "":
            continue
        os.environ[key] = val
        n += 1
    if verbose:
        print(f"Merging {path} ({n} keys applied)", file=sys.stderr)
    return True


def _bootstrap_env(*, env_file: str | None, verbose: bool) -> None:
    """Apply .env files so ORCHESTRATOR_* can be omitted from the shell."""
    paths: list[Path] = []
    if env_file:
        paths.append(Path(env_file).expanduser().resolve())
    else:
        root = Path(__file__).resolve().parent.parent
        paths.append(root / ".env")
        cwd_env = Path.cwd() / ".env"
        if cwd_env.resolve() != paths[0].resolve():
            paths.append(cwd_env.resolve())
    seen: set[Path] = set()
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        _load_dotenv_file(p, verbose=verbose)


def http_call(
    url: str,
    *,
    method: str = "GET",
    bearer: str | None = None,
    json_body: dict[str, Any] | None = None,
) -> HttpResult:
    headers: dict[str, str] = {}
    payload: bytes | None = None
    if json_body is not None:
        payload = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read()
            t1 = time.perf_counter()
            h = {k.lower(): v for k, v in resp.headers.items()}
            text = raw.decode("utf-8", errors="replace")
            return HttpResult(resp.status, text, h, t1 - t0, None)
    except urllib.error.HTTPError as e:
        t1 = time.perf_counter()
        raw = e.read() if e.fp else b""
        text = raw.decode("utf-8", errors="replace")
        h = {k.lower(): v for k, v in e.headers.items()} if e.headers else {}
        return HttpResult(e.code, text, h, t1 - t0, None)
    except Exception as e:  # noqa: BLE001
        t1 = time.perf_counter()
        return HttpResult(None, "", {}, t1 - t0, str(e))


def ms(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    return f"{seconds * 1000:.1f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Timed GPTHub demo smoke")
    parser.add_argument("--skip-wow", action="store_true", help="Skip Council + PPTX steps")
    parser.add_argument("--json", metavar="FILE", help="Write timing + outcomes JSON here")
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        help="Dotenv file (default: scanovich-webUI/.env, then ./.env if different)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log which .env was merged")
    args = parser.parse_args()

    _bootstrap_env(env_file=args.env_file, verbose=args.verbose)

    base = _env("ORCHESTRATOR_URL", "http://localhost:8089") or "http://localhost:8089"
    base = base.rstrip("/")
    api_key = _env("ORCHESTRATOR_API_KEY") or _env("LITELLM_MASTER_KEY")
    if not api_key:
        print(
            "FATAL: set ORCHESTRATOR_API_KEY or LITELLM_MASTER_KEY "
            "(shell or .env next to scanovich-webUI, or pass --env-file)",
            file=sys.stderr,
        )
        return 2

    user_id = _env("DEMO_USER_ID", "demo") or "demo"
    skip_wow = args.skip_wow or _env("DEMO_SKIP_WOW") == "1"

    timings: list[TimingRow] = []
    pass_n = fail_n = warn_n = 0

    def step(title: str) -> None:
        print(f"\n=== {title} ===")

    def ok(msg: str) -> None:
        nonlocal pass_n
        pass_n += 1
        print(f"  OK: {msg}")

    def fail(msg: str) -> None:
        nonlocal fail_n
        fail_n += 1
        print(f"  FAIL: {msg}", file=sys.stderr)

    def warn(msg: str) -> None:
        nonlocal warn_n
        warn_n += 1
        print(f"  WARN: {msg}", file=sys.stderr)

    def record(step_id: str, label: str, seconds: float | None, note: str) -> None:
        timings.append(TimingRow(step_id, label, seconds, note))

    # --- 1 Health ---
    step("1/9 Health + readiness")

    r = http_call(f"{base}/healthz")
    print(f"  [{ms(r.seconds)} ms]", end=" ")
    if r.status == 200:
        ok("/healthz returns 200")
        record("1/9", "GET /healthz", r.seconds, "OK")
    elif r.error:
        fail(f"/healthz error: {r.error}")
        record("1/9", "GET /healthz", r.seconds, f"error {r.error}")
        print("Baseline BROKEN — stack not up?", file=sys.stderr)
        return 1
    else:
        fail(f"/healthz status={r.status}")
        record("1/9", "GET /healthz", r.seconds, f"HTTP {r.status}")
        print("Baseline BROKEN — stack not up?", file=sys.stderr)
        return 1

    r = http_call(f"{base}/readyz")
    print(f"  [{ms(r.seconds)} ms]", end=" ")
    if r.status == 200:
        ok("/readyz returns 200")
        record("1/9", "GET /readyz", r.seconds, "OK")
    else:
        warn("/readyz failed — LiteLLM may be unreachable")
        record("1/9", "GET /readyz", r.seconds, "WARN")

    # --- 2 Models ---
    step("2/9 GET /v1/models")
    r = http_call(f"{base}/v1/models", bearer=api_key)
    print(f"  [{ms(r.seconds)} ms]", end=" ")
    if r.body and '"id"' in r.body:
        ok("model catalog returned ids")
        record("2/9", "GET /v1/models", r.seconds, "OK")
    else:
        fail(f"model catalog empty / malformed: {r.body[:200]!r}")
        record("2/9", "GET /v1/models", r.seconds, "FAIL")

    # --- 3 Text chat ---
    step("3/9 Row 1 — text chat")
    text_json = {
        "model": "gpt-hub",
        "stream": False,
        "messages": [
            {"role": "user", "content": "Объясни, что такое RAG в двух предложениях."},
        ],
    }
    r = http_call(f"{base}/v1/chat/completions", bearer=api_key, json_body=text_json)
    print(f"  [{ms(r.seconds)} ms]", end=" ")
    if '"choices"' not in r.body:
        fail(f"text chat missing choices[]: {r.body[:200]!r}")
        record("3/9", "POST text chat", r.seconds, "FAIL")
    else:
        ok("text chat returned choices[]")
        record("3/9", "POST text chat", r.seconds, "OK choices")
        if r.headers.get("x-gpthub-trace"):
            ok(f"X-GPTHub-Trace present ({len(r.headers['x-gpthub-trace'])} chars)")
        else:
            warn("X-GPTHub-Trace missing")

    # --- 4 URL ---
    step("4/9 Row 8 — URL parsing")
    url_json = {
        "model": "gpt-hub",
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": "Прочитай https://example.com и скажи о чём страница одним предложением.",
            },
        ],
    }
    r = http_call(f"{base}/v1/chat/completions", bearer=api_key, json_body=url_json)
    print(f"  [{ms(r.seconds)} ms]", end=" ")
    if '"choices"' in r.body:
        ok("URL ingest returned choices[]")
        record("4/9", "POST URL ingest", r.seconds, "OK")
    else:
        warn(f"URL ingest missing choices: {r.body[:200]!r}")
        record("4/9", "POST URL ingest", r.seconds, "WARN")

    # --- 5 Image ---
    step("5/9 Row 3 — image generation")
    img_json = {
        "model": "gpt-hub",
        "stream": False,
        "messages": [{"role": "user", "content": "Нарисуй рыжего кота в шляпе."}],
    }
    r = http_call(f"{base}/v1/chat/completions", bearer=api_key, json_body=img_json)
    print(f"  [{ms(r.seconds)} ms]", end=" ")
    b = r.body
    if ("![" in b and "](http" in b) or "data:image/png;base64" in b:
        ok("image gen returned inline markdown image")
        record("5/9", "POST image gen", r.seconds, "OK")
    elif '"choices"' in b:
        warn("image gen fell through to regular chat (MWS qwen-image may be down)")
        record("5/9", "POST image gen", r.seconds, "WARN fallthrough")
    else:
        fail(f"image gen returned no choices: {b[:200]!r}")
        record("5/9", "POST image gen", r.seconds, "FAIL")

    # --- 6 Memory ---
    step("6/9 Row 9 — memory commands")
    remember_json = {
        "model": "gpt-hub",
        "stream": False,
        "messages": [
            {
                "role": "user",
                "name": user_id,
                "content": "Запомни, что я отвечаю за интеграцию MWS в наш продукт.",
            },
        ],
    }
    recall_json = {
        "model": "gpt-hub",
        "stream": False,
        "messages": [
            {"role": "user", "name": user_id, "content": "Что ты обо мне помнишь?"},
        ],
    }

    r = http_call(f"{base}/v1/chat/completions", bearer=api_key, json_body=remember_json)
    print(f"  [{ms(r.seconds)} ms]", end=" ")
    if "Запомнил" in r.body:
        ok("remember command short-circuited")
        record("6/9", "POST remember", r.seconds, "OK")
    else:
        warn(f"remember did not short-circuit: {r.body[:200]!r}")
        record("6/9", "POST remember", r.seconds, "WARN")

    r = http_call(f"{base}/v1/chat/completions", bearer=api_key, json_body=recall_json)
    print(f"  [{ms(r.seconds)} ms]", end=" ")
    if "интеграц" in r.body.lower():
        ok("recall returned the stored fact")
        record("6/9", "POST recall", r.seconds, "OK")
    else:
        warn(f"recall did not return the fact: {r.body[:200]!r}")
        record("6/9", "POST recall", r.seconds, "WARN")

    # --- 7 Reasoning ---
    step("7/9 Row 10 — classifier routing")
    reason_json = {
        "model": "gpt-hub",
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": "Напиши на Python функцию, которая находит N-е простое число.",
            },
        ],
    }
    r = http_call(f"{base}/v1/chat/completions", bearer=api_key, json_body=reason_json)
    print(f"  [{ms(r.seconds)} ms]", end=" ")
    if '"choices"' not in r.body:
        fail(f"reasoning task missing choices: {r.body[:200]!r}")
        record("7/9", "POST reasoning", r.seconds, "FAIL")
    else:
        ok("reasoning task returned choices[]")
        record("7/9", "POST reasoning", r.seconds, "OK choices")
        if r.headers.get("x-gpthub-trace"):
            ok(f"classifier trace present: {r.headers['x-gpthub-trace'][:120]}...")
        else:
            warn("no trace header on reasoning task")

    # --- 8 Council ---
    if skip_wow:
        step("8/9 WOW-1 Expert Council — SKIPPED")
        record("8/9", "WOW-1 Council", None, "SKIPPED")
    else:
        step("8/9 WOW-1 Expert Council (if merged)")
        council_json = {
            "model": "gpt-hub",
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "/research Проведи глубокое исследование по архитектурам "
                        "retrieval-augmented generation в корпоративных ассистентах."
                    ),
                },
            ],
        }
        r = http_call(f"{base}/v1/chat/completions", bearer=api_key, json_body=council_json)
        print(f"  [{ms(r.seconds)} ms]", end=" ")
        if '"choices"' in r.body:
            ok("council path returned a synthesized answer (check trace for 3 experts)")
            record("8/9", "POST council", r.seconds, "OK")
        else:
            warn(f"council path not merged yet or failed: {r.body[:200]!r}")
            record("8/9", "POST council", r.seconds, "WARN")

    # --- 9 PPTX ---
    if skip_wow:
        step("9/9 WOW-3 PPTX generation — SKIPPED")
        record("9/9", "WOW-3 PPTX", None, "SKIPPED")
    else:
        step("9/9 WOW-3 PPTX generation (if merged)")
        pptx_json = {
            "model": "gpt-hub",
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Сделай презентацию на 5 слайдов про GPTHub: проблема, архитектура, "
                        "mixed input, trace, вывод."
                    ),
                },
            ],
        }
        r = http_call(f"{base}/v1/chat/completions", bearer=api_key, json_body=pptx_json)
        print(f"  [{ms(r.seconds)} ms]", end=" ")
        low = r.body.lower()
        if "pptx" in low or "data:application/vnd.openxmlformats-officedocument.presentationml" in r.body:
            ok("pptx path returned inline .pptx attachment")
            record("9/9", "POST pptx", r.seconds, "OK")
        else:
            warn(f"pptx path not merged yet or failed: {r.body[:200]!r}")
            record("9/9", "POST pptx", r.seconds, "WARN")

    # --- Summary table ---
    print("")
    print("==============================================================")
    print(f"{'Step':<8} {'Label':<28} {'ms':>10}  Note")
    print("--------------------------------------------------------------")
    for row in timings:
        m = ms(row.seconds) if row.seconds is not None else "—"
        note = row.note[:52] + ("…" if len(row.note) > 52 else "")
        print(f"{row.step:<8} {row.label:<28} {m:>10}  {note}")
    print("==============================================================")
    print(f"Demo smoke finished: PASS={pass_n} FAIL={fail_n} WARN={warn_n}")

    if args.json:
        out = {
            "pass": pass_n,
            "fail": fail_n,
            "warn": warn_n,
            "timings": [
                {
                    "step": r.step,
                    "label": r.label,
                    "seconds": r.seconds,
                    "ms": round(r.seconds * 1000, 3) if r.seconds is not None else None,
                    "note": r.note,
                }
                for r in timings
            ],
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"Wrote {args.json}")

    if fail_n > 0:
        print("Baseline BROKEN — do not record the demo video.", file=sys.stderr)
        return 1
    if warn_n > 0:
        print("Baseline green, but some optional paths are soft-failing.")
        print("Record only after resolving the WARNs or deciding to drop those paths.")
        return 0
    print("All green. Baseline is ready for a demo recording.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
