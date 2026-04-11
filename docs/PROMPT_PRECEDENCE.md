# Prompt Precedence

The orchestrator produces one upstream system message before calling LiteLLM.

## Effective Order

1. Optional request datetime block from `build_session_clock_block()`
2. Role prompt selected by the router
3. Any incoming `system` messages already present on the request
4. The remaining non-system messages in their original order

## Important Detail

The ingest pipeline may insert a system message that contains mixed-input artifacts. That artifact block is treated the same way as any other incoming system message, so it is appended after the role prompt under the `Additional instructions (from chat client)` section.

## Why This Exists

- The router-owned role prompt must stay first so the orchestrator can enforce the product contract.
- Existing client or ingest system messages must still survive the merge.
- The user-visible answer must stay separate from trace and routing metadata.
