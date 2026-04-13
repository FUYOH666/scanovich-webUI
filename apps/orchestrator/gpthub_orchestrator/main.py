"""FastAPI entry: health + OpenAI-compatible proxy with trace."""

from __future__ import annotations

import asyncio
import codecs
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from gpthub_orchestrator.classifier import classify_messages
from gpthub_orchestrator.clock_context import build_session_clock_block
from gpthub_orchestrator.council import (
    build_council_chat_completion,
    build_council_sse_chunks,
    extract_council_question,
    is_council_request,
    run_council,
)
from gpthub_orchestrator.greeting_canned import (
    canned_chat_completion_json,
    canned_chat_completion_sse_chunks,
    client_visible_model_id,
    greeting_canned_eligible,
)
from gpthub_orchestrator.image_gen import (
    ImageGenError,
    build_image_chat_completion,
    build_image_sse_chunks,
    extract_image_prompt,
    generate_image_via_mws,
    is_image_generation_request,
)
from gpthub_orchestrator.pptx import (
    PptxGenError,
    build_pptx_artifact_download_url,
    build_pptx_chat_completion,
    build_pptx_error_chat_completion,
    build_pptx_error_sse_chunks,
    build_pptx_from_plan,
    build_pptx_sse_chunks,
    deck_title_for_intro,
    load_stripped_base_presentation,
    pptx_download_filename,
    request_slide_plan,
)
from gpthub_orchestrator.pptx.artifacts import get_pptx_artifact_store
from gpthub_orchestrator.memory.service import (
    build_memory_chat_completion,
    build_memory_sse_chunks,
    build_memory_system_message,
    execute_memory_command,
    last_user_text,
    resolve_user_id,
    retrieve_memory_context,
    try_parse_command,
)
from gpthub_orchestrator.memory.store import MemoryStore
from gpthub_orchestrator.messages import apply_role_system_messages
from gpthub_orchestrator.public_models import apply_models_catalog, map_facade_model_to_litellm
from gpthub_orchestrator.role_prompts import load_role_prompts
from gpthub_orchestrator.router import choose_model
from gpthub_orchestrator.settings import Settings, load_settings
from gpthub_orchestrator.reasoning_response_filter import (
    filter_sse_data_line_json,
    merge_reasoning_exclude_into_body,
    strip_reasoning_from_completion_payload,
)
from gpthub_orchestrator.response_preamble_strip import strip_known_cot_preamble
from gpthub_orchestrator.ingest.pipeline import run_ingest_pipeline
from gpthub_orchestrator.trace import build_trace, trace_to_header_value

logger = logging.getLogger("gpthub_orchestrator")


def _apply_preamble_strip_to_completion(payload: dict[str, Any], settings: Settings) -> None:
    if not settings.orchestrator_strip_known_cot_preamble:
        return
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return
    for ch in choices:
        if not isinstance(ch, dict):
            continue
        msg = ch.get("message")
        if not isinstance(msg, dict):
            continue
        c = msg.get("content")
        if not isinstance(c, str):
            continue
        new_c, applied = strip_known_cot_preamble(c)
        if applied:
            msg["content"] = new_c
            logger.info("preamble_strip_applied_to_completion")


def _apply_reasoning_strip_to_completion(payload: dict[str, Any], settings: Settings) -> None:
    if settings.orchestrator_strip_reasoning_from_response:
        strip_reasoning_from_completion_payload(payload)


def _ascii_content_disposition_filename(filename: str) -> str:
    """RFC 6266: filename= must be ASCII; non-ASCII goes in filename*."""
    ascii_fn = re.sub(r"[^\x20-\x7e]", "_", filename).strip("._") or "presentation"
    if not ascii_fn.lower().endswith(".pptx"):
        ascii_fn = f"{ascii_fn}.pptx"
    return ascii_fn


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _retryable_litellm_status(status_code: int) -> bool:
    return status_code in (429, 503)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    _configure_logging(settings.log_level)
    load_role_prompts(settings.role_prompts_path)
    sec = float(settings.litellm_timeout_seconds)
    timeout = httpx.Timeout(
        connect=min(60.0, sec),
        read=sec,
        write=sec,
        pool=min(60.0, sec),
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        app.state.settings = settings
        app.state.http = client
        memory_store: MemoryStore | None = None
        if settings.memory_enabled:
            try:
                memory_store = MemoryStore(settings.memory_db_path)
                logger.info("memory_store_ready path=%s", settings.memory_db_path)
            except Exception as e:  # noqa: BLE001
                logger.warning("memory_store_init_failed err=%s", e)
                memory_store = None
        app.state.memory_store = memory_store
        try:
            yield
        finally:
            if memory_store is not None:
                memory_store.close()


app = FastAPI(title="GPTHub Orchestrator", version="0.1.0", lifespan=lifespan)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def get_memory_store(request: Request) -> MemoryStore | None:
    return getattr(request.app.state, "memory_store", None)


def verify_bearer(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if token != settings.orchestrator_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "gpthub-orchestrator"}


@app.get("/readyz")
async def readyz(
    settings: Settings = Depends(get_settings),
    http: httpx.AsyncClient = Depends(get_http),
) -> dict[str, str]:
    """Readiness: LiteLLM liveliness reachable (no Bearer required)."""
    url = f"{settings.litellm_base_url.rstrip('/')}/health/liveliness"
    try:
        r = await http.get(url, timeout=httpx.Timeout(5.0, connect=2.0))
    except httpx.HTTPError:
        logger.exception("readyz_litellm_unreachable")
        raise HTTPException(status_code=503, detail="LiteLLM unreachable") from None
    if r.status_code >= 400:
        logger.warning("readyz_litellm_bad_status %s", r.status_code)
        raise HTTPException(status_code=503, detail="LiteLLM not ready")
    return {"status": "ready", "service": "gpthub-orchestrator", "litellm": "ok"}


@app.get("/artifacts/pptx/{artifact_id}")
async def download_pptx_artifact(
    artifact_id: str,
    token: Annotated[str, Query(min_length=8)],
    settings: Settings = Depends(get_settings),
) -> Response:
    """One-time download: token is invalidated after a successful response."""
    store = get_pptx_artifact_store(settings.pptx_artifact_ttl_seconds)
    result = store.consume(artifact_id, token)
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    blob, filename = result
    ascii_fn = _ascii_content_disposition_filename(filename)
    disp = f'attachment; filename="{ascii_fn}"; filename*=UTF-8\'\'{quote(filename)}'
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": disp},
    )


@app.get("/v1/models")
async def openai_list_models(
    request: Request,
    settings: Settings = Depends(get_settings),
    http: httpx.AsyncClient = Depends(get_http),
    _: None = Depends(verify_bearer),
) -> JSONResponse:
    """Proxy for Open WebUI: it calls GET /v1/models to populate the model dropdown."""
    url = f"{settings.litellm_base_url.rstrip('/')}/v1/models"
    resp = await http.get(url, headers={"Authorization": request.headers.get("Authorization", "")})
    if resp.status_code >= 400:
        logger.warning("litellm_models_error %s %s", resp.status_code, resp.text[:400])
        return _error_json_response(resp)
    ct = resp.headers.get("content-type", "")
    if "application/json" not in ct:
        return _error_json_response(resp)
    try:
        payload = resp.json()
    except json.JSONDecodeError:
        return _error_json_response(resp)
    if not isinstance(payload, dict):
        return _error_json_response(resp)
    filtered = apply_models_catalog(payload, settings)
    return JSONResponse(status_code=200, content=filtered)


def _error_json_response(resp: httpx.Response) -> JSONResponse:
    ct = resp.headers.get("content-type", "")
    if "application/json" in ct:
        try:
            payload = resp.json()
        except json.JSONDecodeError:
            payload = {"detail": resp.text}
    else:
        payload = {"detail": resp.text}
    return JSONResponse(status_code=resp.status_code, content=payload)


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    settings: Settings = Depends(get_settings),
    http: httpx.AsyncClient = Depends(get_http),
    _: None = Depends(verify_bearer),
) -> Response:
    try:
        body: dict[str, Any] = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from e

    messages = body.get("messages")
    if not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="messages must be a list")

    ingested, ingest_artifacts, ingest_ms = await run_ingest_pipeline(messages, settings, http)
    body["messages"] = ingested

    map_facade_model_to_litellm(body, settings)

    classification = classify_messages(body["messages"])
    router_suggestion = choose_model(classification, settings)
    clock_prefix, server_clock_iso = build_session_clock_block(settings)
    auth_header = request.headers.get("Authorization", "")

    # Memory command short-circuit: «запомни / забудь / что ты помнишь».
    memory_store: MemoryStore | None = getattr(request.app.state, "memory_store", None)
    if settings.memory_enabled and memory_store is not None:
        mem_cmd = try_parse_command(body["messages"])
        if mem_cmd is not None:
            user_id = resolve_user_id(body["messages"])
            try:
                mem_result = await execute_memory_command(
                    mem_cmd,
                    store=memory_store,
                    user_id=user_id,
                    http=http,
                    settings=settings,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("memory_command_failed kind=%s err=%s", mem_cmd.kind, e)
            else:
                model_vis = client_visible_model_id(body, settings.orchestrator_public_model_id)
                mem_fb = {
                    "enabled": False,
                    "short_circuit": "memory_command",
                    "memory_kind": mem_result.kind,
                    "memory_fact_count": mem_result.fact_count,
                }
                trace = build_trace(
                    classification=classification,
                    router_suggestion=router_suggestion,
                    model_used=model_vis,
                    artifacts=ingest_artifacts,
                    orchestrator_fallback=mem_fb,
                    prompt_version=load_role_prompts(settings.role_prompts_path).prompt_version,
                    classifier_source="heuristic",
                    server_clock_iso=server_clock_iso,
                    ingest_ms=ingest_ms,
                )
                logger.info("execution_trace %s", json.dumps(trace, ensure_ascii=False))
                trace_hdr = trace_to_header_value(trace)
                if bool(body.get("stream")):
                    chunks = build_memory_sse_chunks(model_vis, mem_result.reply_text)

                    async def memory_sse():
                        for ch in chunks:
                            yield ch

                    return StreamingResponse(
                        memory_sse(),
                        media_type="text/event-stream",
                        headers={"X-GPTHub-Trace": trace_hdr},
                    )
                out = build_memory_chat_completion(
                    model_label=model_vis,
                    text=mem_result.reply_text,
                )
                return JSONResponse(content=out, headers={"X-GPTHub-Trace": trace_hdr})

    # Expert Council short-circuit (WOW-1): fan-out to 3 MWS experts and synthesize.
    if settings.council_enabled:
        council_user_text = ""
        for m in reversed(body["messages"]):
            if m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    council_user_text = c
                elif isinstance(c, list):
                    parts = [str(p.get("text", "")) for p in c if isinstance(p, dict) and p.get("type") == "text"]
                    council_user_text = " ".join(parts).strip()
                break
        if council_user_text and is_council_request(council_user_text):
            question = extract_council_question(council_user_text)
            model_vis = client_visible_model_id(body, settings.orchestrator_public_model_id)
            try:
                council_result = await run_council(
                    http,
                    settings=settings,
                    base_url=settings.litellm_base_url,
                    auth_header=request.headers.get("Authorization", ""),
                    question=question,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("council_run_failed err=%s", e)
                council_result = None
            if council_result is not None:
                council_fb = council_result.trace_payload()
                trace = build_trace(
                    classification=classification,
                    router_suggestion=router_suggestion,
                    model_used=model_vis,
                    artifacts=ingest_artifacts,
                    orchestrator_fallback=council_fb,
                    prompt_version=load_role_prompts(settings.role_prompts_path).prompt_version,
                    classifier_source="heuristic",
                    server_clock_iso=server_clock_iso,
                    ingest_ms=ingest_ms,
                )
                logger.info("execution_trace %s", json.dumps(trace, ensure_ascii=False))
                trace_hdr = trace_to_header_value(trace)
                if bool(body.get("stream")):
                    chunks = build_council_sse_chunks(model_vis, council_result.final_text)

                    async def council_sse():
                        for ch in chunks:
                            yield ch

                    return StreamingResponse(
                        council_sse(),
                        media_type="text/event-stream",
                        headers={"X-GPTHub-Trace": trace_hdr},
                    )
                out = build_council_chat_completion(
                    model_label=model_vis,
                    text=council_result.final_text,
                )
                return JSONResponse(content=out, headers={"X-GPTHub-Trace": trace_hdr})

    # Image-generation short-circuit: detect intent on the last user text and call MWS directly.
    if settings.image_gen_enabled:
        image_intent_user_text = ""
        for m in reversed(body["messages"]):
            if m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    image_intent_user_text = c
                elif isinstance(c, list):
                    parts = [str(p.get("text", "")) for p in c if isinstance(p, dict) and p.get("type") == "text"]
                    image_intent_user_text = " ".join(parts).strip()
                break
        if image_intent_user_text and is_image_generation_request(image_intent_user_text):
            img_prompt = extract_image_prompt(image_intent_user_text)
            model_vis = client_visible_model_id(body, settings.orchestrator_public_model_id)
            try:
                image_ref, mws_model = await generate_image_via_mws(
                    http,
                    settings=settings,
                    prompt=img_prompt,
                )
            except ImageGenError as e:
                logger.warning("image_gen_failed err=%s", e)
                # Fall through to normal chat routing; do not raise to client.
            else:
                trace = build_trace(
                    classification=classification,
                    router_suggestion=router_suggestion,
                    model_used=model_vis,
                    artifacts=ingest_artifacts,
                    image_gen={"status": "ok", "model": mws_model},
                    prompt_version=load_role_prompts(settings.role_prompts_path).prompt_version,
                    classifier_source="heuristic",
                    server_clock_iso=server_clock_iso,
                    ingest_ms=ingest_ms,
                )
                logger.info("execution_trace %s", json.dumps(trace, ensure_ascii=False))
                trace_hdr = trace_to_header_value(trace)
                if bool(body.get("stream")):
                    chunks = build_image_sse_chunks(model_vis, img_prompt, image_ref)

                    async def image_sse():
                        for ch in chunks:
                            yield ch

                    return StreamingResponse(
                        image_sse(),
                        media_type="text/event-stream",
                        headers={"X-GPTHub-Trace": trace_hdr},
                    )
                out = build_image_chat_completion(
                    model_label=model_vis,
                    prompt=img_prompt,
                    image_ref=image_ref,
                )
                return JSONResponse(content=out, headers={"X-GPTHub-Trace": trace_hdr})

    # PPTX short-circuit: slide-plan via LiteLLM (strong chain) + python-pptx (after image intent).
    # Classifier uses ``pptx_generation`` when ``is_pptx_request`` matches; weaker cues → ``pptx`` only.
    if settings.pptx_gen_enabled and classification.get("task_type") in ("pptx", "pptx_generation"):
        model_vis = client_visible_model_id(body, settings.orchestrator_public_model_id)
        prompt_version = load_role_prompts(settings.role_prompts_path).prompt_version
        pptx_user_err = (
            "Не удалось собрать презентацию. Попробуйте упростить запрос или повторить позже."
        )

        def _pptx_error_response(pptx_meta: dict[str, Any]) -> Response:
            trace = build_trace(
                classification=classification,
                router_suggestion=router_suggestion,
                model_used=model_vis,
                artifacts=ingest_artifacts,
                pptx=pptx_meta,
                prompt_version=prompt_version,
                classifier_source="heuristic",
                server_clock_iso=server_clock_iso,
                ingest_ms=ingest_ms,
            )
            logger.info("execution_trace %s", json.dumps(trace, ensure_ascii=False))
            trace_hdr = trace_to_header_value(trace)
            if bool(body.get("stream")):

                async def pptx_err_sse():
                    for ch in build_pptx_error_sse_chunks(model_label=model_vis, message=pptx_user_err):
                        yield ch

                return StreamingResponse(
                    pptx_err_sse(),
                    media_type="text/event-stream",
                    headers={"X-GPTHub-Trace": trace_hdr},
                )
            out = build_pptx_error_chat_completion(model_label=model_vis, message=pptx_user_err)
            return JSONResponse(content=out, headers={"X-GPTHub-Trace": trace_hdr})

        try:
            async with asyncio.timeout(settings.pptx_plan_timeout_seconds):
                plan, base_prs = await asyncio.gather(
                    request_slide_plan(
                        http,
                        settings,
                        body["messages"],
                        authorization=auth_header,
                    ),
                    asyncio.to_thread(load_stripped_base_presentation, settings),
                )
                t_build = time.perf_counter()
                pptx_blob = await asyncio.to_thread(
                    build_pptx_from_plan,
                    plan,
                    settings=settings,
                    base_prs=base_prs,
                )
                logger.info(
                    "pptx_timing %s",
                    json.dumps(
                        {
                            "phase": "build_deck_ms",
                            "ms": round((time.perf_counter() - t_build) * 1000, 1),
                            "pptx_bytes": len(pptx_blob),
                        },
                        ensure_ascii=False,
                    ),
                )
        except TimeoutError:
            logger.warning("pptx_gen_failed err=timeout")
            return _pptx_error_response({"status": "error", "reason": "timeout"})
        except PptxGenError as e:
            reason = str(e) if e.args else "unknown"
            if reason == "slide_plan_json_invalid":
                logger.warning("pptx_plan_invalid err=%s", e)
            else:
                logger.warning("pptx_gen_failed err=%s", e)
            return _pptx_error_response({"status": "error", "reason": reason})
        except Exception as e:  # noqa: BLE001
            logger.warning("pptx_gen_failed err=%s", e)
            return _pptx_error_response({"status": "error", "reason": type(e).__name__})
        else:
            trace = build_trace(
                classification=classification,
                router_suggestion=router_suggestion,
                model_used=model_vis,
                artifacts=ingest_artifacts,
                pptx={"status": "ok", "slides": len(plan.slides)},
                prompt_version=prompt_version,
                classifier_source="heuristic",
                server_clock_iso=server_clock_iso,
                ingest_ms=ingest_ms,
            )
            logger.info("execution_trace %s", json.dumps(trace, ensure_ascii=False))
            trace_hdr = trace_to_header_value(trace)
            store = get_pptx_artifact_store(settings.pptx_artifact_ttl_seconds)
            artifact_id, one_time_token = store.create(
                pptx_blob,
                filename=pptx_download_filename(plan),
            )
            download_url = build_pptx_artifact_download_url(
                public_base=settings.pptx_artifacts_public_base_url,
                request_base_url=str(request.base_url),
                artifact_id=artifact_id,
                token=one_time_token,
            )
            intro_title = deck_title_for_intro(plan) if settings.pptx_intro_slide_enabled else None
            if bool(body.get("stream")):

                async def pptx_ok_sse():
                    for ch in build_pptx_sse_chunks(
                        model_label=model_vis,
                        plan=plan,
                        download_url=download_url,
                        intro_title=intro_title,
                    ):
                        yield ch

                return StreamingResponse(
                    pptx_ok_sse(),
                    media_type="text/event-stream",
                    headers={"X-GPTHub-Trace": trace_hdr},
                )
            out = build_pptx_chat_completion(
                model_label=model_vis,
                plan=plan,
                download_url=download_url,
                intro_title=intro_title,
            )
            return JSONResponse(content=out, headers={"X-GPTHub-Trace": trace_hdr})

    if settings.greeting_canned_response_enabled and greeting_canned_eligible(classification):
        role_prompts = load_role_prompts(settings.role_prompts_path)
        prompt_version = role_prompts.prompt_version
        model_vis = client_visible_model_id(body, settings.orchestrator_public_model_id)
        canned_text = settings.greeting_canned_message
        trace = build_trace(
            classification=classification,
            router_suggestion=router_suggestion,
            model_used=model_vis,
            artifacts=ingest_artifacts,
            prompt_version=prompt_version,
            classifier_source="heuristic",
            server_clock_iso=server_clock_iso,
            canned_response=True,
            ingest_ms=ingest_ms,
        )
        logger.info("execution_trace %s", json.dumps(trace, ensure_ascii=False))
        trace_hdr = trace_to_header_value(trace)
        stream = bool(body.get("stream"))
        if stream:

            async def canned_sse():
                for chunk in canned_chat_completion_sse_chunks(model=model_vis, content=canned_text):
                    yield chunk

            return StreamingResponse(
                canned_sse(),
                media_type="text/event-stream",
                headers={"X-GPTHub-Trace": trace_hdr},
            )
        out = canned_chat_completion_json(model=model_vis, content=canned_text)
        return JSONResponse(content=out, headers={"X-GPTHub-Trace": trace_hdr})

    # Memory retrieval: inject top-K relevant facts as an extra system block
    # so the upstream model can use them without extra round-trips.
    retrieved_facts_meta: list[dict[str, Any]] = []
    if (
        settings.memory_enabled
        and settings.memory_retrieval_enabled
        and memory_store is not None
    ):
        query_text = last_user_text(body["messages"])
        if query_text:
            try:
                facts = await retrieve_memory_context(
                    store=memory_store,
                    user_id=resolve_user_id(body["messages"]),
                    query_text=query_text,
                    http=http,
                    settings=settings,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("memory_retrieve_failed err=%s", e)
                facts = []
            if facts:
                mem_sys = build_memory_system_message(facts)
                if mem_sys is not None:
                    body["messages"] = [mem_sys, *body["messages"]]
                retrieved_facts_meta = [
                    {"id": f.id, "content": f.content[:300]} for f in facts
                ]

    role_prompts = load_role_prompts(settings.role_prompts_path)
    role_key = str(router_suggestion["model_role"])
    body["messages"] = apply_role_system_messages(
        list(body["messages"]),
        role_key,
        role_prompts,
        session_clock_prefix=clock_prefix,
    )
    prompt_version = role_prompts.prompt_version
    if retrieved_facts_meta:
        ingest_artifacts = list(ingest_artifacts) + [
            {
                "type": "memory_facts",
                "title": f"{len(retrieved_facts_meta)} relevant facts",
                "content": "\n".join(f"- {m['content']}" for m in retrieved_facts_meta),
            }
        ]

    chain: list[str] = list(router_suggestion.get("fallback_aliases") or [router_suggestion["model_name"]])

    model_used = str(body.get("model") or chain[0])
    if settings.auto_route_model:
        model_used = chain[0]
        body["model"] = model_used

    merge_reasoning_exclude_into_body(
        body,
        enabled=settings.orchestrator_request_reasoning_exclude,
    )

    stream = bool(body.get("stream"))
    url = f"{settings.litellm_base_url.rstrip('/')}/v1/chat/completions"

    if stream:
        stream_fb: dict[str, Any] = {
            "mode": "stream_single_attempt",
            "auto_route_model": settings.auto_route_model,
            "note": "orchestrator does not chain fallback for stream; LiteLLM fallbacks apply",
        }
        trace = build_trace(
            classification=classification,
            router_suggestion=router_suggestion,
            model_used=str(body.get("model", model_used)),
            artifacts=ingest_artifacts,
            orchestrator_fallback=stream_fb,
            prompt_version=prompt_version,
            classifier_source="heuristic",
            server_clock_iso=server_clock_iso,
            ingest_ms=ingest_ms,
        )
        logger.info("execution_trace %s", json.dumps(trace, ensure_ascii=False))

        def _sse_error_event(message: str, *, err_type: str = "upstream_error", code: int | None = None) -> bytes:
            err_obj: dict[str, Any] = {"error": {"message": message, "type": err_type}}
            if code is not None:
                err_obj["error"]["code"] = code
            return f"data: {json.dumps(err_obj, ensure_ascii=False)}\n\n".encode("utf-8")

        async def passthrough():
            try:
                async with http.stream(
                    "POST",
                    url,
                    json=body,
                    headers={"Authorization": auth_header},
                ) as r:
                    if r.status_code >= 400:
                        err_bytes = await r.aread()
                        preview = err_bytes[:1200].decode("utf-8", errors="replace")
                        logger.warning(
                            "litellm_stream_upstream_error status=%s preview=%s",
                            r.status_code,
                            preview,
                        )
                        try:
                            parsed = json.loads(err_bytes)
                            inner = parsed.get("error")
                            if isinstance(inner, dict):
                                msg = str(inner.get("message", preview))
                            elif isinstance(inner, str):
                                msg = inner
                            else:
                                msg = preview
                        except json.JSONDecodeError:
                            msg = preview
                        yield _sse_error_event(msg, code=r.status_code)
                        yield b"data: [DONE]\n\n"
                        return
                    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                    pending = ""
                    async for chunk in r.aiter_bytes():
                        pending += decoder.decode(chunk)
                        while "\n" in pending:
                            line, pending = pending.split("\n", 1)
                            if settings.orchestrator_strip_reasoning_from_response:
                                line = filter_sse_data_line_json(
                                    line,
                                    strip_enabled=True,
                                )
                            yield (line + "\n").encode("utf-8")
                    pending += decoder.decode(b"", final=True)
                    if pending:
                        line = pending.rstrip("\r")
                        if settings.orchestrator_strip_reasoning_from_response:
                            line = filter_sse_data_line_json(line, strip_enabled=True)
                        yield (line + "\n").encode("utf-8")
            except httpx.TimeoutException:
                logger.exception("litellm_stream_timeout")
                yield _sse_error_event(
                    "Upstream LLM stream timed out (increase LITELLM_TIMEOUT_SECONDS)",
                    err_type="timeout",
                    code=504,
                )
                yield b"data: [DONE]\n\n"
            except httpx.HTTPError:
                logger.exception("litellm_stream_http_error")
                yield _sse_error_event("Upstream LLM connection error", err_type="connection_error", code=502)
                yield b"data: [DONE]\n\n"

        return StreamingResponse(
            passthrough(),
            media_type="text/event-stream",
            headers={"X-GPTHub-Trace": trace_to_header_value(trace)},
        )

    use_chain = (
        settings.auto_route_model
        and settings.orchestrator_litellm_fallback
        and len(chain) > 0
    )
    max_t = min(len(chain), settings.orchestrator_fallback_max_attempts) if use_chain else 1

    if not use_chain:
        trace = build_trace(
            classification=classification,
            router_suggestion=router_suggestion,
            model_used=model_used,
            artifacts=ingest_artifacts,
            prompt_version=prompt_version,
            classifier_source="heuristic",
            server_clock_iso=server_clock_iso,
            ingest_ms=ingest_ms,
        )
        logger.info("execution_trace %s", json.dumps(trace, ensure_ascii=False))
        resp = await http.post(url, json=body, headers={"Authorization": auth_header})
        if resp.status_code >= 400:
            logger.warning("litellm_error %s %s", resp.status_code, resp.text[:500])
            return _error_json_response(resp)
        out = resp.json()
        if isinstance(out, dict):
            _apply_reasoning_strip_to_completion(out, settings)
            _apply_preamble_strip_to_completion(out, settings)
        return JSONResponse(
            content=out,
            headers={"X-GPTHub-Trace": trace_to_header_value(trace)},
        )

    attempts_log: list[dict[str, Any]] = []
    last_resp: httpx.Response | None = None
    winning_model = model_used

    for i in range(max_t):
        alias = chain[i]
        body_attempt = dict(body)
        body_attempt["model"] = alias
        winning_model = alias
        resp = await http.post(url, json=body_attempt, headers={"Authorization": auth_header})
        attempts_log.append({"model": alias, "status_code": resp.status_code})
        if resp.status_code < 400:
            fb_meta: dict[str, Any] = {
                "enabled": True,
                "attempts": attempts_log,
                "model_selected": alias,
                "retries_after_failure": max(0, i),
            }
            trace = build_trace(
                classification=classification,
                router_suggestion=router_suggestion,
                model_used=winning_model,
                artifacts=ingest_artifacts,
                orchestrator_fallback=fb_meta,
                prompt_version=prompt_version,
                classifier_source="heuristic",
                server_clock_iso=server_clock_iso,
                ingest_ms=ingest_ms,
            )
            logger.info("execution_trace %s", json.dumps(trace, ensure_ascii=False))
            out = resp.json()
            if isinstance(out, dict):
                _apply_reasoning_strip_to_completion(out, settings)
                _apply_preamble_strip_to_completion(out, settings)
            return JSONResponse(
                content=out,
                headers={"X-GPTHub-Trace": trace_to_header_value(trace)},
            )
        last_resp = resp
        logger.warning(
            "litellm_attempt_failed status=%s model=%s body_preview=%s",
            resp.status_code,
            alias,
            resp.text[:300],
        )
        if i < max_t - 1 and _retryable_litellm_status(resp.status_code):
            continue
        break

    assert last_resp is not None
    fb_meta = {
        "enabled": True,
        "attempts": attempts_log,
        "failed": True,
    }
    trace = build_trace(
        classification=classification,
        router_suggestion=router_suggestion,
        model_used=winning_model,
        artifacts=ingest_artifacts,
        orchestrator_fallback=fb_meta,
        prompt_version=prompt_version,
        classifier_source="heuristic",
        server_clock_iso=server_clock_iso,
        ingest_ms=ingest_ms,
    )
    logger.info("execution_trace %s", json.dumps(trace, ensure_ascii=False))
    logger.warning("litellm_error %s %s", last_resp.status_code, last_resp.text[:500])
    trace_hdr = trace_to_header_value(trace)
    err_resp = _error_json_response(last_resp)
    err_payload: Any
    if isinstance(err_resp.body, (bytes, memoryview)):
        err_payload = json.loads(bytes(err_resp.body).decode("utf-8"))
    else:
        err_payload = err_resp.body
    return JSONResponse(
        status_code=err_resp.status_code,
        content=err_payload,
        headers={**dict(err_resp.headers), "X-GPTHub-Trace": trace_hdr},
    )
