from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    litellm_base_url: str = Field(
        ...,
        description="LiteLLM proxy base URL without trailing slash",
    )
    orchestrator_api_key: str = Field(
        ...,
        description="Bearer token from clients (same as LITELLM_MASTER_KEY for WebUI)",
    )
    litellm_timeout_seconds: float = Field(
        default=600.0,
        ge=5.0,
        le=3600.0,
        description="httpx timeout (connect/read/write/pool) for LiteLLM; raise for long RAG/PDF streams",
    )
    auto_route_model: bool = Field(
        default=True,
        description="If true, override the incoming model id with the router suggestion",
    )
    code_route_preference: Literal["local", "openrouter"] = Field(
        default="local",
        description="Historical compatibility toggle for code prompt flavor; no legacy path dependency",
    )
    orchestrator_litellm_fallback: bool = Field(
        default=True,
        description="Non-stream: retry LiteLLM with next alias in chain on 429/503",
    )
    orchestrator_fallback_max_attempts: int = Field(default=4, ge=1, le=8)
    model_roles_path: str | None = Field(
        default=None,
        description="Optional path to model_roles.yaml (default: packaged data)",
    )
    role_prompts_path: str | None = Field(
        default=None,
        description="Optional path to role_prompts.yaml (default: packaged data)",
    )
    default_text_model: str = Field(default="gpt-hub-turbo")
    default_vision_model: str = Field(default="gpt-hub-vision")
    default_code_heavy_model: str = Field(default="gpt-hub-turbo")
    log_level: str = Field(default="INFO")
    inject_request_datetime: bool = Field(
        default=True,
        description="Prepend server date/time to system message so the model can answer 'what time is it'",
    )
    orchestrator_clock_tz: str = Field(
        default="UTC",
        description="IANA timezone for inject_request_datetime (e.g. Europe/Moscow, UTC)",
    )
    orchestrator_models_catalog: Literal["all", "single_public"] = Field(
        default="single_public",
        description="GET /v1/models: expose all LiteLLM aliases or a single public facade id for Open WebUI",
    )
    orchestrator_public_model_id: str = Field(
        default="gpt-hub",
        min_length=1,
        description="Public model id shown in UI when catalog is single_public; must not be a LiteLLM alias",
    )
    greeting_canned_response_enabled: bool = Field(
        default=False,
        description="If true, greeting_or_tiny without images returns a fixed reply without calling LiteLLM",
    )
    greeting_canned_message: str = Field(
        default="Привет! Чем могу помочь?",
        min_length=1,
        description="Assistant text for canned greeting short-circuit",
    )
    orchestrator_strip_known_cot_preamble: bool = Field(
        default=False,
        description="If true, non-stream responses may strip known CoT preambles from assistant content (last resort)",
    )
    orchestrator_request_reasoning_exclude: bool = Field(
        default=True,
        description="If true, ask the upstream provider not to return reasoning tokens when supported",
    )
    orchestrator_strip_reasoning_from_response: bool = Field(
        default=True,
        description="If true, remove reasoning/thinking fields from JSON and stream chunks before the client",
    )
    ingest_enabled: bool = Field(
        default=True,
        description="If true, run perception ingest (PDF/audio) on last user message before routing",
    )
    mws_gpt_api_base: str | None = Field(
        default=None,
        description="MWS base URL (e.g. https://api.gpt.mws.ru/v1). Used as default for ASR/image-gen/embeddings.",
    )
    mws_gpt_api_key: str | None = Field(
        default=None,
        description="MWS API key. Used as default bearer for ASR/image-gen/embeddings.",
    )
    orchestrator_asr_base_url: str | None = Field(
        default=None,
        description="OpenAI-compatible ASR base URL. If unset, orchestrator falls back to mws_gpt_api_base.",
    )
    orchestrator_asr_api_key: str | None = Field(
        default=None,
        description="Bearer for ASR. If unset, orchestrator falls back to mws_gpt_api_key.",
    )
    orchestrator_asr_model: str = Field(
        default="whisper-medium",
        description="Model id for POST .../audio/transcriptions (default: MWS whisper-medium).",
    )

    def resolved_asr_base_url(self) -> str | None:
        return self.orchestrator_asr_base_url or self.mws_gpt_api_base

    def resolved_asr_api_key(self) -> str | None:
        return self.orchestrator_asr_api_key or self.mws_gpt_api_key
    ingest_pdf_max_bytes: int = Field(default=15_000_000, ge=1024, le=50_000_000)
    ingest_pdf_max_pages: int = Field(default=50, ge=1, le=500)
    ingest_fetch_max_bytes: int = Field(default=25_000_000, ge=1024, le=100_000_000)
    ingest_image_fetch_timeout: float = Field(default=60.0, ge=5.0, le=600.0)
    ingest_url_enabled: bool = Field(
        default=True,
        description="If true, detect http(s) URLs in last user message text and ingest their page text",
    )
    ingest_url_max_per_message: int = Field(default=3, ge=1, le=10)
    ingest_url_timeout_seconds: float = Field(default=10.0, ge=2.0, le=60.0)
    ingest_url_max_bytes: int = Field(default=2_000_000, ge=1024, le=25_000_000)
    ingest_url_allow_private_hosts: bool = Field(
        default=False,
        description="Dev/test only: allow fetching private/loopback IPs. Must stay false in prod.",
    )
    image_gen_enabled: bool = Field(
        default=True,
        description="If true, orchestrator detects image-generation intent and calls MWS /images/generations directly.",
    )
    image_gen_model: str = Field(
        default="qwen-image",
        description="MWS image model id used for /images/generations short-circuit.",
    )
    image_gen_timeout_seconds: float = Field(default=120.0, ge=5.0, le=600.0)
    pptx_gen_enabled: bool = Field(
        default=True,
        description="If true, task_type pptx short-circuits to slide-plan LLM + python-pptx deck.",
    )
    pptx_plan_timeout_seconds: float = Field(
        default=300.0,
        ge=15.0,
        le=600.0,
        description="Wall-clock limit for plan LLM + deck build in PPTX short-circuit.",
    )
    pptx_parallel_slide_agents_enabled: bool = Field(
        default=True,
        description=(
            "If true, first LLM call returns slide titles/outline only, then one LiteLLM call per slide "
            "in parallel (bounded by pptx_slide_agents_concurrency)."
        ),
    )
    pptx_slide_agents_concurrency: int = Field(
        default=7,
        ge=1,
        le=32,
        description="Max concurrent per-slide LLM calls when pptx_parallel_slide_agents_enabled.",
    )
    pptx_max_slides: int = Field(
        default=10,
        ge=1,
        le=10,
        description="Cap on slide count after outline/monolithic (must be ≤ MAX_SLIDES in pptx/schema).",
    )
    pptx_intro_slide_enabled: bool = Field(
        default=True,
        description="If true, prepend a title/intro slide (topic from first planned slide); layout is probed separately.",
    )
    pptx_plan_tone: str = Field(
        default="auto",
        description="Tone hint for slide-plan LLM (auto|general|persuasive|inspiring|instructive|engaging).",
    )
    pptx_plan_audience: str = Field(
        default="auto",
        description="Audience hint for slide-plan LLM (auto|general|business|investor|teacher|student).",
    )
    pptx_plan_scenario: str = Field(
        default="auto",
        description=(
            "Scenario hint for slide-plan LLM "
            "(auto|general|analysis-report|teaching-training|promotional-materials|public-speeches)."
        ),
    )
    pptx_plan_text_content: Literal["minimal", "concise", "detailed", "extensive"] = Field(
        default="concise",
        description="Target verbosity for bullets/slide text in PPTX plan (presentation-ai style).",
    )
    pptx_asset_templates_enabled: bool = Field(
        default=True,
        description="If true, use .pptx files from pptx_templates_dir or built-in assets/pttx paths.",
    )
    pptx_templates_dir: str = Field(
        default="",
        description="Override directory of .pptx templates; empty = auto (/app/assets/pttx or repo assets/pttx).",
    )
    pptx_template_index: int = Field(
        default=0,
        ge=0,
        le=64,
        description="Pick template from sorted *.pptx in directory (index wraps modulo file count).",
    )
    pptx_artifacts_public_base_url: str = Field(
        default="",
        description=(
            "Public base URL for PPTX download links (no trailing slash), e.g. http://YOUR_HOST:8089. "
            "Browsers must reach this host; inside Docker use published orchestrator port. "
            "If empty, the request Host from chat/completions is used (often only works with port-forward)."
        ),
    )
    pptx_artifact_ttl_seconds: float = Field(
        default=3600.0,
        ge=60.0,
        le=86400.0,
        description="TTL for one-time PPTX artifact tokens (monotonic clock).",
    )
    memory_enabled: bool = Field(
        default=True,
        description="If true, orchestrator detects memory commands and injects retrieved facts.",
    )
    memory_db_path: str = Field(
        default="/tmp/gpthub_memory.sqlite3",
        description="Filesystem path to the SQLite memory store.",
    )
    memory_embedding_model: str = Field(
        default="qwen3-embedding-8b",
        description="MWS embedding model id for memory facts (dim 4096).",
    )
    memory_embedding_timeout_seconds: float = Field(default=60.0, ge=5.0, le=600.0)
    memory_retrieval_enabled: bool = Field(
        default=True,
        description="If true, inject top-K relevant memory facts into normal chat flow.",
    )
    memory_retrieval_top_k: int = Field(default=5, ge=1, le=20)
    memory_retrieval_min_score: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Cosine similarity floor for retrieved facts.",
    )
    council_enabled: bool = Field(
        default=True,
        description="If true, orchestrator detects DEEP_RESEARCH intent and runs the Expert Council fan-out.",
    )
    council_branch_timeout_seconds: float = Field(
        default=120.0,
        ge=10.0,
        le=600.0,
        description="Per-expert timeout. Branches that miss the deadline are dropped from synthesis.",
    )
    council_synthesis_timeout_seconds: float = Field(
        default=240.0,
        ge=10.0,
        le=600.0,
        description="Timeout for the final synthesis call (glm-4.6 strong is slow on long context).",
    )
    council_expert_strong: str = Field(
        default="gpt-hub-turbo",
        description=(
            "LiteLLM alias for the 'fast generalist' expert in the council. "
            "Uses mws-gpt-alpha by default (fast, OpenAI-like baseline)."
        ),
    )
    council_expert_reasoning: str = Field(
        default="gpt-hub-reasoning-or",
        description="LiteLLM alias for the 'deep reasoning / code' expert in the council.",
    )
    council_expert_doc: str = Field(
        default="gpt-hub-doc",
        description="LiteLLM alias for the 'document / long-context' expert in the council.",
    )
    council_synthesis_model: str = Field(
        default="gpt-hub-strong",
        description=(
            "LiteLLM alias used to synthesize the final answer from expert opinions. "
            "Defaults to gpt-hub-strong (glm-4.6-357b) — the most capable model."
        ),
    )
    council_min_branches_for_synthesis: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Minimum number of successful expert branches required to run synthesis; otherwise fall back to strong-only.",
    )
    council_max_expert_tokens: int = Field(
        default=700,
        ge=100,
        le=4000,
        description="max_tokens passed to each expert branch (synthesis is capped separately).",
    )
    council_max_synthesis_tokens: int = Field(
        default=3000,
        ge=100,
        le=8000,
        description=(
            "max_tokens passed to the synthesis call. Must be generous enough "
            "that glm-4.6 / qwen3 reasoning models can still emit a real answer "
            "even if they leak some CoT despite reasoning-exclude."
        ),
    )

    @field_validator("model_roles_path", "role_prompts_path", mode="before")
    @classmethod
    def empty_str_paths_to_none(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("orchestrator_public_model_id", mode="after")
    @classmethod
    def strip_public_model_id(cls, v: str) -> str:
        return v.strip()

    @field_validator("greeting_canned_message", mode="after")
    @classmethod
    def strip_canned_message(cls, v: str) -> str:
        return v.strip()

    @field_validator(
        "orchestrator_asr_base_url",
        "orchestrator_asr_api_key",
        "mws_gpt_api_base",
        "mws_gpt_api_key",
        mode="before",
    )
    @classmethod
    def empty_optional_str_to_none(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


def load_settings() -> Settings:
    return Settings()
