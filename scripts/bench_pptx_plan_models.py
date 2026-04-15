#!/usr/bin/env python3
"""
Benchmark PPTX pipeline: slide-plan via LiteLLM (same contract as prod) + python-pptx build.

Requires a **running** LiteLLM reachable from `LITELLM_BASE_URL` and `.env` in
`apps/orchestrator/` (same as orchestrator). New aliases must exist in
`infra/litellm/config.yaml`; after editing config, recreate the litellm container.

**Reliability:** `llama-3.3-70b-instruct` often emits **invalid JSON** (not only
trailing prose) for this strict deck contract — expect `ok_runs < repeat` until
prompt/schema is tuned. `Qwen3-235B-A22B-Instruct` and `glm-4.6-357b` usually
parse; absolute speeds vary with MWS load — use ``--repeat 5`` and compare medians.

Usage (from repo root)::

    cd apps/orchestrator && uv sync --extra dev && uv run python ../../scripts/bench_pptx_plan_models.py

    cd apps/orchestrator && uv run python ../../scripts/bench_pptx_plan_models.py \\
        --models gpt-hub-strong gpt-hub-pptx-llama33 --repeat 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import patch

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = REPO_ROOT / "apps" / "orchestrator"

DEFAULT_MODELS = (
    "gpt-hub-strong",
    "gpt-hub-pptx-llama33",
    "gpt-hub-pptx-qwen235a22",
)

# Upstream OpenAI-style ids on MWS (for /v1/models presence check).
UPSTREAM_BY_ALIAS: dict[str, str] = {
    "gpt-hub-strong": "glm-4.6-357b",
    "gpt-hub-pptx-llama33": "llama-3.3-70b-instruct",
    "gpt-hub-pptx-qwen235a22": "Qwen3-235B-A22B-Instruct-2507-FP8",
}

logger = logging.getLogger("bench_pptx")


def _load_env_file(path: Path, *, override: bool) -> None:
    """Minimal KEY=VAL parser so bench works when only repo-root `.env` exists."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        if override or key not in os.environ:
            os.environ[key] = val


def _setup_runtime() -> None:
    # Repo `.env` first (docker-compose uses root env_file), then orchestrator-local.
    _load_env_file(REPO_ROOT / ".env", override=False)
    _load_env_file(REPO_ROOT / ".env.mws.local", override=False)
    _load_env_file(ORCH_DIR / ".env", override=False)
    # Docker compose sets this only inside the container; local bench targets host LiteLLM.
    if "LITELLM_BASE_URL" not in os.environ:
        os.environ["LITELLM_BASE_URL"] = "http://localhost:4000"
    os.chdir(ORCH_DIR)
    if str(ORCH_DIR) not in sys.path:
        sys.path.insert(0, str(ORCH_DIR))


def _fetch_mws_model_ids(settings: object) -> set[str] | None:
    base = settings.mws_gpt_api_base
    key = settings.mws_gpt_api_key
    if not base or not key:
        logger.warning("mws_gpt_api_base/key unset — skip MWS /v1/models check")
        return None
    url = base.rstrip("/") + "/models"
    try:
        r = httpx.get(
            url,
            headers={"Authorization": f"Bearer {key}"},
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.error("MWS models fetch failed: %s", e)
        return None
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return set()
    out: set[str] = set()
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            out.add(row["id"])
    return out


def _bench_router_stub(model_alias: str):
    """Force a single LiteLLM alias (prod path uses ``choose_model`` from task_type)."""

    def _fake(classification: dict, settings: object) -> dict:
        _ = classification, settings
        return {
            "model_name": model_alias,
            "model_role": "reasoning_code_local",
            "fallback_aliases": [model_alias],
            "reason": "bench_override",
            "task_type": "pptx_generation",
        }

    return _fake


async def _bench_one(
    *,
    settings: object,
    model_alias: str,
    topic: str,
    client: httpx.AsyncClient,
) -> tuple[bool, float, float, int, str | None]:
    """Returns ok, plan_seconds, build_seconds, pptx_bytes, error_message."""
    from gpthub_orchestrator.pptx import PptxGenError, build_pptx_from_plan, request_slide_plan
    from gpthub_orchestrator.pptx.build import load_stripped_base_presentation

    s = settings.model_copy(
        update={
            "pptx_parallel_slide_agents_enabled": False,
        }
    )
    auth = f"Bearer {s.orchestrator_api_key}"
    err: str | None = None
    t0 = time.perf_counter()
    try:
        with patch("gpthub_orchestrator.pptx.plan.choose_model", _bench_router_stub(model_alias)):
            plan = await request_slide_plan(
                client,
                s,
                [{"role": "user", "content": topic}],
                authorization=auth,
            )
        t1 = time.perf_counter()
        base_prs = load_stripped_base_presentation(s)
        blob = build_pptx_from_plan(plan, settings=s, base_prs=base_prs)
        t2 = time.perf_counter()
        return True, t1 - t0, t2 - t1, len(blob), None
    except PptxGenError as e:
        err = str(e)
        return False, time.perf_counter() - t0, 0.0, 0, err
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        return False, time.perf_counter() - t0, 0.0, 0, err


async def _async_main(args: argparse.Namespace) -> int:
    _setup_runtime()
    from gpthub_orchestrator.settings import Settings as SettingsCls

    settings = SettingsCls()
    mws_ids = _fetch_mws_model_ids(settings)

    if mws_ids is not None:
        for alias in args.models:
            want = UPSTREAM_BY_ALIAS.get(alias)
            if want and want not in mws_ids:
                logger.warning("MWS catalog missing id %r (alias %s) — bench may fail", want, alias)

    topic = args.topic
    rows: list[dict[str, object]] = []

    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(limits=limits) as client:
        for alias in args.models:
            plans: list[float] = []
            builds: list[float] = []
            oks = 0
            last_err: str | None = None
            last_bytes = 0
            for i in range(args.repeat):
                logger.info("run model=%s iteration=%s/%s", alias, i + 1, args.repeat)
                ok, ps, bs, nbytes, err = await _bench_one(
                    settings=settings,
                    model_alias=alias,
                    topic=topic,
                    client=client,
                )
                if ok:
                    oks += 1
                    plans.append(ps)
                    builds.append(bs)
                    last_bytes = nbytes
                else:
                    last_err = err
            row: dict[str, object] = {
                "model_alias": alias,
                "upstream_id": UPSTREAM_BY_ALIAS.get(alias, ""),
                "ok_runs": oks,
                "repeat": args.repeat,
                "median_plan_s": statistics.median(plans) if plans else None,
                "median_build_s": statistics.median(builds) if builds else None,
                "median_total_s": statistics.median([p + b for p, b in zip(plans, builds)]) if plans else None,
                "pptx_bytes": last_bytes,
                "last_error": last_err,
            }
            rows.append(row)

    # Human table on stdout
    print(f"topic: {topic[:80]}{'…' if len(topic) > 80 else ''}")
    print(f"repeat: {args.repeat}  litellm: {settings.litellm_base_url}")
    hdr = f"{'alias':<28} {'upstream':<36} {'ok':>4} {'med_plan_s':>12} {'med_build_s':>13} {'med_total_s':>12} {'bytes':>8}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        mp = r["median_plan_s"]
        mb = r["median_build_s"]
        mt = r["median_total_s"]
        print(
            f"{str(r['model_alias']):<28} {str(r['upstream_id']):<36} {int(r['ok_runs']):>4} "
            f"{mp if mp is not None else 'n/a':>12} "
            f"{mb if mb is not None else 'n/a':>13} "
            f"{mt if mt is not None else 'n/a':>12} "
            f"{int(r.get('pptx_bytes') or 0):>8}"
        )
        if r.get("last_error") and int(r["ok_runs"]) < args.repeat:
            print(f"  !! last_error: {r['last_error']}")

    print("\nJSON:", json.dumps(rows, ensure_ascii=False))
    return 0 if all(int(r["ok_runs"]) == args.repeat for r in rows) else 1


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Benchmark PPTX plan+build across LiteLLM aliases.")
    p.add_argument(
        "--models",
        nargs="+",
        default=list(DEFAULT_MODELS),
        help="LiteLLM model_name aliases (default: three PPTX bench aliases).",
    )
    p.add_argument("--repeat", type=int, default=3, help="Runs per model (median reported).")
    p.add_argument(
        "--topic",
        default=(
            "Сделай презентацию на 5 слайдов про GPTHub: проблема, архитектура, "
            "mixed input, trace, вывод."
        ),
        help="User message passed to the plan model (PPTX-style topic).",
    )
    args = p.parse_args()
    if args.repeat < 1:
        print("repeat must be >= 1", file=sys.stderr)
        sys.exit(2)
    rc = asyncio.run(_async_main(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
