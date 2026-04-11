"""Long-term memory subsystem (Row 9).

- `store.py` — thread-safe SQLite facts store with optional embedding vectors.
- `embeddings.py` — MWS `qwen3-embedding-8b` client.
- `commands.py` — parse user intents: «запомни / забудь / что ты помнишь».
- `service.py` — high-level orchestration used from `main.py`.
"""
