"""Optional embedding-based task_type hint (MWS /v1/embeddings).

Uses the same model/endpoint as memory (`memory_embedding_model`). When disabled or
on failure, callers keep heuristic `classify_messages` output unless
``AMBIGUOUS_RU_UTTERANCES`` matches exactly (always applied here).

Phrases from ``AMBIGUOUS_RU_UTTERANCES`` are also merged into embedding prototypes
(кроме метки ``help``) для мягкого смещения похожих реплик.

Does not override locked heuristic labels: strong PPTX / council / tiny greeting
(unless ``classifier_semantic_override_locked_heuristic`` is true). Skips entirely
when the last user message carries image parts (multimodal stays heuristic).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from gpthub_orchestrator.classifier import classify_messages
from gpthub_orchestrator.memory.embeddings import EmbeddingError, embed_one, embed_texts
from gpthub_orchestrator.memory.store import cosine_similarity
from gpthub_orchestrator.settings import Settings

logger = logging.getLogger(__name__)

# Exemplar phrases per router task_type (RU + EN). Tuned for broad coverage; adjust with logs.
SEMANTIC_TASK_PROTOTYPES: dict[str, list[str]] = {
    "simple_chat": [
        "Расскажи интересный факт про космос",
        "What is the capital of France?",
        "Почему небо голубое простыми словами",
        "How do I boil pasta",
        "Что такое блокчейн одним абзацем",
        "Explain photosynthesis to a child",
        "Какой смысл жизни по твоему мнению",
        "Difference between SQL and NoSQL",
    ],
    "greeting_or_tiny": [
        "Привет",
        "Спасибо большое",
        "Ок понял",
        "Hi there",
        "Thank you so much",
        "Добрый день",
        "bye",
        "thx",
    ],
    "code_help": [
        "Почему этот Python код падает с TypeError",
        "Напиши функцию на FastAPI для загрузки файла",
        "Fix this React useEffect infinite loop",
        "Как сделать async await правильно в asyncio",
        "Refactor this class to use dependency injection",
        "Ошибка ImportError cannot import name",
        "Write a unit test for this function",
        "Docker compose healthcheck example",
    ],
    "file_analysis": [
        "Вот длинный текст документа — что в нём главное",
        "Проанализируй структуру этого отчёта",
        "Extract action items from the meeting notes below",
        "Сравни два подхода из текста",
    ],
    "summarization": [
        "Сделай краткое резюме этого PDF",
        "TLDR of the article",
        "Конспект глав по документу",
        "Summarize the key points in 5 bullets",
        "Перескажи коротко для руководства",
    ],
    "image_analysis": [
        "Что изображено на этой картинке",
        "Describe the chart and trends",
        "Прочитай текст со скриншота",
        "What colors and objects do you see in the photo",
    ],
    "multimodal_workflow": [
        "Вот скриншот кода — найди баг и объясни",
        "Using this diagram explain the architecture",
        "Photo of a whiteboard plus question about the flow",
    ],
    "pptx": [
        "Нужна презентация про устойчивое развитие в 6 слайдов",
        "Слайды про маркетинговую стратегию",
        "Outline a deck about quarterly results",
        "Подготовь powerpoint по теме онбординга",
    ],
    "pptx_generation": [
        "/pptx архитектура микросервисов",
        "Создай презентацию про RAG системы",
        "Generate a presentation about cloud security",
        "Сделай ppt по этой теме в формате pptx",
        "build a deck on machine learning basics",
    ],
    "deep_research": [
        "/research сравни vector databases для RAG в 2026",
        "Проведи глубокое исследование рынка EV в Европе",
        "Deep dive: trade-offs of CRDT vs OT for collaborative editing",
        "Expert council style analysis of regulatory risks",
        "Compare PostgreSQL vs MongoDB for analytics workloads in depth",
    ],
    # Заполняется фразами из ``AMBIGUOUS_RU_UTTERANCES`` (метка ``image``) + эмбеддинги.
    "image_generation": [],
}

# Пограничные RU-реплики (pptx / картинка / council / чат / help).
# Точное совпадение нормализованного текста → ``task_type`` в ``classify_messages_for_route``;
# кроме ``help`` фразы подмешиваются в прототипы для семантики.
AMBIGUOUS_RU_UTTERANCES: tuple[tuple[str, str], ...] = (
    ("/help", "help"),
    # Короткие разговорные формы (golden / эвристика pptx_gen их не ловит).
    ("бахни презу", "pptx"),
    ("надоел. дай презу уже", "pptx"),
    ("ты всё испортил. я хочу презу.", "pptx"),
    ("делай картинку по презентации", "image"),
    ("верни картинку", "image"),
    (
        "хорошо подумай. как вернуть данные сервера после падения",
        "deep_research",
    ),
    ("бахни презу про наш стек", "pptx"),
    ("надоел, дай презу уже без воды", "pptx"),
    ("презу накинь на завтра, тема любая", "pptx"),
    ("сделай мне не презу, а просто текстом тезисы", "chat"),
    ("хочу презу, но только если успеешь за минуту", "pptx"),
    ("верни картинку как было до правок", "image"),
    ("покажи картинку из прошлого ответа ещё раз", "image"),
    ("сгенерь иллюстрацию к этому слайду", "image"),
    ("нарисуй логотип и вставь в презентацию", "help"),
    ("делай картинку по моей презентации, стиль корпоративный", "image"),
    ("нужна картинка, но не знаю какую — предложи", "image"),
    ("сделай обложку для слайдов, не весь файл", "image"),
    ("это для слайда или для чата? решай сам", "chat"),
    ("оформи как bullet list, без pptx", "chat"),
    ("как считаешь, стоит ли вообще делать презентацию", "chat"),
    ("расскажи как правильно структурировать презентацию, без файла", "chat"),
    ("я не про файл, я про содержание — только текст", "chat"),
    ("презентация нужна, но сначала обсудим план в чате", "chat"),
    ("не генери файл, просто ответь", "chat"),
    ("что ты сгенерировал? объясни словами", "chat"),
    ("ты всё испортил, я хотел презу, а ты текст написал", "chat"),
    ("ладно забей на презу, ответь нормально", "chat"),
    ("хорошо подумай и скажи как восстановить сервер после падения", "deep_research"),
    ("нужен глубокий разбор, но коротко и без совета экспертов", "chat"),
    ("это вопрос на подумать, не исследование на 10 страниц", "chat"),
    ("сравни два подхода как для доклада, но без council", "chat"),
    ("дай экспертное мнение одного человека, не совет из трёх", "chat"),
    ("это research или обычный ответ? я сам не знаю", "chat"),
    ("проведи мини-исследование в двух абзацах", "chat"),
    ("не /research, просто объясни", "chat"),
    ("слушай, сделай как для руководства: тезисы и риски", "chat"),
    ("нужен питч в чате, не файл", "chat"),
    ("собери инфу как для слайдов, но выведи здесь", "chat"),
    ("дай структуру доклада: введение, проблема, вывод", "chat"),
    ("оформи ответ как список слайдов без создания pptx", "chat"),
    ("презентация про безопасность — только заголовки слайдов", "chat"),
    ("сделай черновик слайдов текстом, потом решим про файл", "chat"),
    ("мне нужен pdf, но ты умеешь только pptx?", "help"),
    ("сгенери диаграмму словами, не картинкой", "chat"),
    ("опиши визуал для дизайнера, без генерации", "chat"),
    ("верни то что было, я ничего не просил менять", "chat"),
    ("переделай ответ: меньше маркетинга, больше фактов", "chat"),
    ("это был вопрос или приказ? интерпретируй как вопрос", "chat"),
    ("не коротко и не длинно — средне, и по делу", "chat"),
    ("ответь как для коллеги, не как для инвестора", "chat"),
    ("если не уверен — спроси уточнение вместо файла", "chat"),
    ("я имел в виду презентацию, но написал «презу» специально", "pptx"),
    ("не надо wow, надо скучно и точно", "chat"),
    ("это тест роутинга: презу или чат?", "help"),
)

_AMBIGUOUS_LABEL_TO_TASK: dict[str, str] = {
    "help": "user_help",
    "chat": "simple_chat",
    "pptx": "pptx_generation",
    "image": "image_generation",
    "deep_research": "deep_research",
}

# Куда подмешивать фразы для эмбеддингов (``help`` только точное совпадение, без прототипов).
_AMBIGUOUS_LABEL_TO_PROTOTYPE_KEY: dict[str, str] = {
    "chat": "simple_chat",
    "pptx": "pptx_generation",
    "image": "image_generation",
    "deep_research": "deep_research",
}

_AMBIGUOUS_NORMALIZED_TO_TASK_CACHE: dict[str, str] | None = None


def _normalize_utterance_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _ambiguous_normalized_to_task_map() -> dict[str, str]:
    global _AMBIGUOUS_NORMALIZED_TO_TASK_CACHE
    if _AMBIGUOUS_NORMALIZED_TO_TASK_CACHE is None:
        m: dict[str, str] = {}
        for phrase, lab in AMBIGUOUS_RU_UTTERANCES:
            t = _AMBIGUOUS_LABEL_TO_TASK.get(lab)
            if t:
                m[_normalize_utterance_key(phrase)] = t
        _AMBIGUOUS_NORMALIZED_TO_TASK_CACHE = m
    return _AMBIGUOUS_NORMALIZED_TO_TASK_CACHE


def ambiguous_ru_exact_task_type(last_user: str) -> str | None:
    """Точное совпадение последней реплики с таблицей (после нормализации пробелов и регистра)."""
    key = _normalize_utterance_key(last_user)
    if not key:
        return None
    return _ambiguous_normalized_to_task_map().get(key)


def normalized_user_help_phrases() -> frozenset[str]:
    """Нормализованные фразы с меткой ``help`` (для тестов и внешних вызовов)."""
    return frozenset(k for k, v in _ambiguous_normalized_to_task_map().items() if v == "user_help")


def _task_prototypes_for_embeddings() -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {k: list(v) for k, v in SEMANTIC_TASK_PROTOTYPES.items()}
    for phrase, lab in AMBIGUOUS_RU_UTTERANCES:
        if lab == "help":
            continue
        pkey = _AMBIGUOUS_LABEL_TO_PROTOTYPE_KEY.get(lab)
        if not pkey:
            continue
        if pkey not in merged:
            merged[pkey] = []
        if phrase not in merged[pkey]:
            merged[pkey].append(phrase)
    return merged


_HEURISTIC_TASK_LOCKED: frozenset[str] = frozenset(
    {"pptx_generation", "deep_research", "greeting_or_tiny", "user_help"},
)


def _flatten_user_content(parts: list[dict[str, Any]] | str) -> str:
    if isinstance(parts, str):
        return parts
    chunks: list[str] = []
    for p in parts:
        if isinstance(p, dict) and p.get("type") == "text":
            chunks.append(str(p.get("text", "")))
    return " ".join(chunks)


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return _flatten_user_content(c)
            return ""
    return ""


def _last_user_has_image(messages: list[dict[str, Any]]) -> bool:
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        c = m.get("content")
        if not isinstance(c, list):
            return False
        for p in c:
            if isinstance(p, dict) and p.get("type") in ("image_url", "image"):
                return True
        return False
    return False


@dataclass
class _ProtoCache:
    model: str
    by_task: dict[str, list[list[float]]]


_proto_cache: _ProtoCache | None = None


async def _prototype_vectors_by_task(
    http: httpx.AsyncClient,
    settings: Settings,
) -> dict[str, list[list[float]]]:
    global _proto_cache
    if _proto_cache is not None and _proto_cache.model == settings.memory_embedding_model:
        return _proto_cache.by_task

    proto = _task_prototypes_for_embeddings()
    order: list[tuple[str, str]] = []
    for task, texts in proto.items():
        for t in texts:
            order.append((task, t))
    unique_texts: list[str] = []
    seen: set[str] = set()
    for _, t in order:
        if t not in seen:
            seen.add(t)
            unique_texts.append(t)
    vecs = await embed_texts(http, settings=settings, texts=unique_texts)
    text_to_vec = dict(zip(unique_texts, vecs, strict=True))
    by_task: dict[str, list[list[float]]] = {}
    for task, texts in proto.items():
        if not texts:
            continue
        by_task[task] = [text_to_vec[t] for t in texts]
    _proto_cache = _ProtoCache(model=settings.memory_embedding_model, by_task=by_task)
    return by_task


def _score_tasks(query_vec: list[float], by_task: dict[str, list[list[float]]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for task, vectors in by_task.items():
        scores[task] = max(cosine_similarity(query_vec, v) for v in vectors)
    return scores


async def classify_messages_for_route(
    messages: list[dict[str, Any]],
    settings: Settings,
    http: httpx.AsyncClient,
) -> tuple[dict[str, Any], str]:
    """Heuristic classification, optionally overridden by embedding similarity to prototypes."""
    base = classify_messages(messages)
    last_user = _last_user_text(messages).strip()
    if last_user:
        amb_task = ambiguous_ru_exact_task_type(last_user)
        if amb_task is not None:
            out = dict(base)
            out["task_type"] = amb_task
            logger.info(
                "ambiguous_ru_exact task=%s (heuristic_was=%s)",
                amb_task,
                base.get("task_type"),
            )
            return out, "ambiguous_ru"

    if not settings.classifier_semantic_enabled:
        return base, "heuristic"

    if _last_user_has_image(messages):
        return base, "heuristic"

    h_task = str(base.get("task_type") or "")
    if h_task in _HEURISTIC_TASK_LOCKED and not settings.classifier_semantic_override_locked_heuristic:
        return base, "heuristic"

    if not last_user:
        return base, "heuristic"

    try:
        by_task = await _prototype_vectors_by_task(http, settings)
        qv = await embed_one(http, settings=settings, text=last_user[:8000])
    except EmbeddingError as e:
        logger.warning("semantic_classifier_embed_failed err=%s", e)
        return base, "semantic_fallback"

    scores = _score_tasks(qv, by_task)
    best_task = max(scores, key=scores.get)
    sorted_vals = sorted(scores.values(), reverse=True)
    best = sorted_vals[0]
    second = sorted_vals[1] if len(sorted_vals) > 1 else 0.0
    margin = best - second

    if best < settings.classifier_semantic_min_similarity or margin < settings.classifier_semantic_min_margin:
        logger.info(
            "semantic_classifier_low_confidence best=%s margin=%s scores=%s",
            round(best, 4),
            round(margin, 4),
            json.dumps({k: round(v, 4) for k, v in sorted(scores.items(), key=lambda x: -x[1])[:5]}, ensure_ascii=False),
        )
        return base, "semantic_fallback"

    out = dict(base)
    out["task_type"] = best_task
    out["semantic_task_score"] = round(best, 4)
    out["semantic_task_margin"] = round(margin, 4)
    logger.info(
        "semantic_classifier_chosen task=%s score=%s margin=%s (heuristic_was=%s)",
        best_task,
        round(best, 4),
        round(margin, 4),
        h_task,
    )
    return out, "semantic"
