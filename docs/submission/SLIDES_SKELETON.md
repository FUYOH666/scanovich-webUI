# Defence deck skeleton (5–7 slides)

> Полный текст на **10 слайдов (RU)** и сборка PPTX: [`SLIDES_10_RU.md`](SLIDES_10_RU.md) и `scripts/build_defence_deck_pptx.py`. Ниже — короткий англоязычный черновик.

1. **Problem** — One chat surface must cover text, files, media, and observability without a second product mode.
2. **Architecture** — `Open WebUI → orchestrator → LiteLLM → MWS`; single spine; diagram from `architecture.mmd` / Excalidraw.
3. **Mixed input** — One request: PDF/text/audio/URL/image paths through `ingest` into one upstream completion; policy in orchestrator.
4. **Wow (optional)** — Expert Council / PPTX only if green baseline and branch policy allow; otherwise omit this slide or mark deferred.
5. **Demo** — Live or recorded: health, text, trace header, one differentiator moment (mixed input or memory).
6. **Trade-offs** — LiteLLM as alias owner; MWS as upstream; SSRF limits on URL fetch; kill switches from `ROADMAP.md` §0.5.
7. **Ask** — What you want from reviewers or sponsors (one line).
