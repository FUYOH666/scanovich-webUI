"""Structured help for GET /help (capabilities of GPTHub orchestrator)."""

from __future__ import annotations

from typing import Any

from gpthub_orchestrator import __version__


def build_orchestrator_help() -> dict[str, Any]:
    """Return JSON-serializable description of features and entrypoints."""
    return {
        "service": "gpthub-orchestrator",
        "version": __version__,
        "documentation": {
            "help_http": "GET /help — этот объект",
            "chat": "POST /v1/chat/completions — основной чат (OpenAI-совместимый)",
            "models": "GET /v1/models — каталог моделей (Bearer)",
            "health": "GET /healthz, GET /readyz — живость и готовность",
        },
        "capabilities": [
            {
                "id": "text_chat",
                "title": "Текстовый диалог",
                "description": "Маршрутизация по типу задачи, роли и цепочки моделей через LiteLLM → MWS.",
            },
            {
                "id": "routing_trace",
                "title": "Трассировка",
                "description": "Заголовок ответа X-GPTHub-Trace (base64 JSON): task_type, модель, short_circuit, тайминги.",
            },
            {
                "id": "pptx",
                "title": "Генерация PPTX",
                "description": "Запросы на презентацию / слайды → план (LLM) + сборка .pptx; ссылка на скачивание в ответе.",
                "hints": ["/pptx …", "создай презентацию …", "pptx в запросе"],
            },
            {
                "id": "expert_council",
                "title": "Expert Council (исследование)",
                "description": "Глубокий запрос → несколько экспертных веток + синтез (если включено в настройках).",
                "hints": ["/research …", "глубокое исследование …"],
            },
            {
                "id": "image_gen",
                "title": "Генерация изображений",
                "description": "Распознавание запроса на картинку → MWS /images/generations, ответ с markdown-изображением.",
                "hints": ["нарисуй …", "сгенерируй изображение …"],
            },
            {
                "id": "memory",
                "title": "Память (long-term)",
                "description": "Команды «запомни / что помнишь / забудь» и опционально подмешивание фактов в контекст (если включено).",
            },
            {
                "id": "ingest",
                "title": "Ингест вложений",
                "description": "PDF, URL и др. восприятие перед ответом (если ingest_enabled).",
            },
            {
                "id": "datetime",
                "title": "Дата и время сервера",
                "description": "Опциональная подстановка времени в system для ответов «который час» (inject_request_datetime).",
            },
        ],
        "notes": [
            "Часть функций включается переменными окружения / Settings (PPTX, council, memory, semantic classifier и т.д.).",
            "OpenAPI/Swagger: при стандартном деплое FastAPI — /docs и /openapi.json.",
        ],
    }


def greeting_help_footer() -> str:
    """Short line appended to canned greeting so users discover /help."""
    return "\n\nПодробнее о возможностях оркестратора: **GET /help** (на этом же хосте и порту)."


def format_help_for_chat() -> str:
    """Human-readable summary for chat short-circuit (``user_help`` task_type)."""
    h = build_orchestrator_help()
    lines = [
        f"**{h['service']}** v{h['version']}",
        "",
        "Кратко, что умеет оркестратор:",
    ]
    for cap in h["capabilities"]:
        title = str(cap.get("title", ""))
        desc = str(cap.get("description", ""))
        lines.append(f"- **{title}**: {desc}")
    lines.append("")
    lines.append("**Основные HTTP-ручки:**")
    for v in h["documentation"].values():
        lines.append(f"- {v}")
    lines.append("")
    lines.append("Полное описание в JSON: **GET /help**.")
    return "\n".join(lines)
