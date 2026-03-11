# Support-Chat Backend — Implementation Plan

Build a backend-only API (FastAPI, Python 3.11+) that translates natural-language questions into data queries, optionally executes them, maintains conversational sessions, and generates insights.

## User Review Required

> [!IMPORTANT]
> **LLM Provider**: The PLANNING.md prefers **Groq API**. This plan uses Groq (with `groq` Python SDK) as the primary LLM provider, falling back to a generic interface so other providers can be swapped in later.

> [!IMPORTANT]
> **Session Storage**: Starting with an **in-memory** dictionary-based session store for simplicity (no Redis dependency). The store implements an abstract interface so Redis can be swapped in later without changing any other code.

> [!IMPORTANT]
> **Database for app metadata**: Using **SQLite** via SQLAlchemy for storing session metadata persistently. This keeps the setup zero-dependency (no Postgres needed to start). Alembic is deferred to a later iteration.

> [!WARNING]
> **Query Execution Security**: Per PLANNING.md, queries are only executed when the caller provides a database connection URL at session creation. Otherwise, only the generated query string is returned. All executions are **read-only** (wrapped in read-only transactions / `EXPLAIN`-like safeguards).

---

## Proposed Changes

### Phase 1 — Project Scaffold & Core Config

#### [NEW] [requirements.txt](file:///home/yuvan/Programs/Development/support-chat/requirements.txt)
Pin production dependencies:
```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
pydantic>=2.0
pydantic-settings>=2.0
groq>=0.25.0
sqlalchemy>=2.0
pymongo>=4.6
pandas>=2.2
python-dotenv>=1.0
slowapi>=0.1.9
httpx>=0.28.0
pytest>=8.0
pytest-asyncio>=0.25.0
```

#### [NEW] [.env.example](file:///home/yuvan/Programs/Development/support-chat/.env.example)
Template env file with `GROQ_API_KEY`, `APP_ENV`, `LOG_LEVEL`, `SESSION_TTL_SECONDS`, etc.

#### [NEW] [app/__init__.py](file:///home/yuvan/Programs/Development/support-chat/app/__init__.py)
Empty, marks package.

#### [NEW] [app/main.py](file:///home/yuvan/Programs/Development/support-chat/app/main.py)
- Create the `FastAPI` application instance with metadata (title, description, version).
- Register routers: `sessions`, `chat`.
- Add startup/shutdown lifecycle hooks (close DB engines, etc.).
- Add CORS, rate-limiting, and API-key middleware.

#### [NEW] [app/core/__init__.py](file:///home/yuvan/Programs/Development/support-chat/app/core/__init__.py)
Empty.

#### [NEW] [app/core/config.py](file:///home/yuvan/Programs/Development/support-chat/app/core/config.py)
- `Settings(BaseSettings)` — reads from `.env` / environment.
- Fields: `GROQ_API_KEY`, `GROQ_MODEL` (default `"llama-3.3-70b-versatile"`), `APP_ENV`, `LOG_LEVEL`, `SESSION_TTL_SECONDS`, `API_KEYS` (comma-separated list).
- Singleton helper `get_settings()`.

#### [NEW] [app/core/logging.py](file:///home/yuvan/Programs/Development/support-chat/app/core/logging.py)
- Configure `structlog` or stdlib logging with JSON format in production and coloured console in dev.

---

### Phase 2 — Schemas & Models

#### [NEW] [app/schemas/__init__.py](file:///home/yuvan/Programs/Development/support-chat/app/schemas/__init__.py)
Empty.

#### [NEW] [app/schemas/session.py](file:///home/yuvan/Programs/Development/support-chat/app/schemas/session.py)
Pydantic models:
- `SchemaField(name, type, description?, is_primary_key?)` — describes one column/field.
- `SchemaTable(name, fields: list[SchemaField], description?)` — a table / collection.
- `SessionCreateRequest(query_type: Enum[sql,mysql,postgresql,mongodb,pandas], schema_context: list[SchemaTable], db_url: str | None, system_instructions: str | None)`.
- `SessionCreateResponse(session_id, created_at, query_type, has_db_connection)`.
- `SessionInfoResponse(session_id, created_at, query_type, message_count, has_db_connection)`.

#### [NEW] [app/schemas/chat.py](file:///home/yuvan/Programs/Development/support-chat/app/schemas/chat.py)
Pydantic models:
- `ChatMessageRequest(message: str, execute_query: bool = False, generate_insight: bool = False, query_result: Any | None)`.
- `ChatMessageResponse(role, content, query: str | None, query_result: Any | None, insight: str | None, timestamp)`.
- `ChatHistoryResponse(session_id, messages: list[ChatMessageResponse])`.

---

### Phase 3 — Session Management

#### [NEW] [app/services/__init__.py](file:///home/yuvan/Programs/Development/support-chat/app/services/__init__.py)
Empty.

#### [NEW] [app/services/session_store.py](file:///home/yuvan/Programs/Development/support-chat/app/services/session_store.py)
- `SessionStoreBase(ABC)` — abstract class with `create`, `get`, `delete`, `add_message`, `get_history`, `cleanup_expired`.
- `InMemorySessionStore(SessionStoreBase)` — dict-backed, with TTL eviction on access.
- Each session stores: `session_id`, `created_at`, `query_type`, `schema_context`, `db_url`, `system_instructions`, `messages: list[dict]`, `last_accessed`.
- Factory `get_session_store()` returns singleton.

#### [NEW] [app/api/__init__.py](file:///home/yuvan/Programs/Development/support-chat/app/api/__init__.py)
Empty.

#### [NEW] [app/api/sessions.py](file:///home/yuvan/Programs/Development/support-chat/app/api/sessions.py)
Endpoints:
- `POST /sessions` → create session, returns `SessionCreateResponse`.
- `GET /sessions/{session_id}` → returns `SessionInfoResponse`.
- `GET /sessions/{session_id}/history` → returns `ChatHistoryResponse`.
- `DELETE /sessions/{session_id}` → 204 No Content.

---

### Phase 4 — LLM Integration & Query Translation

#### [NEW] [app/core/llm.py](file:///home/yuvan/Programs/Development/support-chat/app/core/llm.py)
- `LLMClient` class wrapping the Groq SDK.
- `async chat_completion(messages: list[dict], temperature, max_tokens, response_format) → str` — calls `groq.chat.completions.create`.
- Handles retries, error logging.
- Singleton `get_llm_client()`.

#### [NEW] [app/utils/__init__.py](file:///home/yuvan/Programs/Development/support-chat/app/utils/__init__.py)
Empty.

#### [NEW] [app/utils/prompt_builder.py](file:///home/yuvan/Programs/Development/support-chat/app/utils/prompt_builder.py)
- `build_system_prompt(query_type, schema_context, system_instructions)` → system prompt string.
  - Injects table/field descriptions, query dialect rules, output format spec.
- `build_chat_messages(system_prompt, conversation_history, user_message)` → `list[dict]` ready for LLM.

#### [NEW] [app/services/translator.py](file:///home/yuvan/Programs/Development/support-chat/app/services/translator.py)
- `QueryTranslator` service class.
- `async translate(session, user_message) → TranslationResult(query, explanation, confidence)`.
- Builds prompt via `prompt_builder`, calls `LLMClient`, parses structured JSON response.

---

### Phase 5 — Query Execution Adapters

#### [NEW] [app/services/adapters/__init__.py](file:///home/yuvan/Programs/Development/support-chat/app/services/adapters/__init__.py)
Exports `get_adapter(query_type, db_url)`.

#### [NEW] [app/services/adapters/base.py](file:///home/yuvan/Programs/Development/support-chat/app/services/adapters/base.py)
- `BaseAdapter(ABC)` with `async execute(query: str) → list[dict]` and `close()`.

#### [NEW] [app/services/adapters/sql_adapter.py](file:///home/yuvan/Programs/Development/support-chat/app/services/adapters/sql_adapter.py)
- Creates a SQLAlchemy engine from `db_url` in **read-only** mode.
- Executes raw SQL via `text()`, returns rows as list of dicts.
- Wraps in try/except, returns structured errors.

#### [NEW] [app/services/adapters/mongodb_adapter.py](file:///home/yuvan/Programs/Development/support-chat/app/services/adapters/mongodb_adapter.py)
- Uses PyMongo / Motor client from `db_url`.
- Parses the generated MongoDB query (JSON) and runs `find`/`aggregate`.
- Returns results as list of dicts.

#### [NEW] [app/services/adapters/pandas_adapter.py](file:///home/yuvan/Programs/Development/support-chat/app/services/adapters/pandas_adapter.py)
- Accepts a DataFrame reference (or CSV/data URL).
- Executes Pandas query string via `df.query()` or `eval()`.
- Returns result rows as list of dicts.

---

### Phase 6 — Chat Service & Orchestration

#### [NEW] [app/services/chat_service.py](file:///home/yuvan/Programs/Development/support-chat/app/services/chat_service.py)
Central orchestrator:
1. Receives user message + session_id.
2. Loads session from store.
3. Calls `QueryTranslator.translate()` → gets the generated query.
4. If `execute_query=True` **and** session has `db_url` → calls adapter → gets results.
5. If `query_result` is provided in request (user executed externally) → uses that.
6. If `generate_insight=True` and results exist → calls LLM again for NL summary.
7. Stores full exchange in session history.
8. Returns `ChatMessageResponse`.

#### [NEW] [app/api/chat.py](file:///home/yuvan/Programs/Development/support-chat/app/api/chat.py)
- `POST /sessions/{session_id}/chat` → accepts `ChatMessageRequest`, returns `ChatMessageResponse`.

---

### Phase 7 — Security & Middleware

#### [NEW] [app/core/security.py](file:///home/yuvan/Programs/Development/support-chat/app/core/security.py)
- API key validation dependency (`X-API-Key` header checked against `settings.API_KEYS`).
- Applied globally to all routes via FastAPI dependency injection.

#### [NEW] [app/core/rate_limiter.py](file:///home/yuvan/Programs/Development/support-chat/app/core/rate_limiter.py)
- `slowapi` rate-limiter configured per IP / per API key.
- Default limits: 60 requests/minute.

---

### Phase 8 — Docker & Testing

#### [NEW] [Dockerfile](file:///home/yuvan/Programs/Development/support-chat/Dockerfile)
- Multi-stage: builder image installs deps, slim image copies.
- Entrypoint: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

#### [NEW] [docker-compose.yml](file:///home/yuvan/Programs/Development/support-chat/docker-compose.yml)
- `api` service exposing port 8000.
- `.env` file binding.

#### [NEW] [tests/__init__.py](file:///home/yuvan/Programs/Development/support-chat/tests/__init__.py)
Empty.

#### [NEW] [tests/conftest.py](file:///home/yuvan/Programs/Development/support-chat/tests/conftest.py)
- Shared fixtures: `test_client` (httpx `AsyncClient` against the app), fresh `session_store`, mocked LLM client.

#### [NEW] [tests/test_sessions.py](file:///home/yuvan/Programs/Development/support-chat/tests/test_sessions.py)
- Test create, get, delete sessions.
- Test history retrieval.
- Test expired session returns 404.

#### [NEW] [tests/test_chat.py](file:///home/yuvan/Programs/Development/support-chat/tests/test_chat.py)
- Test sending a message returns a query.
- Test with `execute_query=True` but no `db_url` returns query only.
- Test providing `query_result` generates an insight.
- Test conversation history is maintained across messages.

---

### Phase 9 — Documentation

#### [MODIFY] [README.md](file:///home/yuvan/Programs/Development/support-chat/README.md)
- Quickstart guide: install, configure `.env`, run `uvicorn`.
- API overview with example `curl` calls.
- Docker instructions.

---

## Verification Plan

### Automated Tests

Run the full test suite after build:
```bash
cd /home/yuvan/Programs/Development/support-chat
pip install -r requirements.txt
pytest tests/ -v
```

Tests will mock the Groq LLM client so no real API key is needed for CI.

### Manual Verification

1. **Start the server**: `uvicorn app.main:app --reload` from project root.
2. **Check docs**: Open `http://127.0.0.1:8000/docs` — Swagger UI should show all endpoints.
3. **Create a session**:
   ```bash
   curl -X POST http://127.0.0.1:8000/sessions \
     -H "Content-Type: application/json" \
     -H "X-API-Key: test-key" \
     -d '{"query_type":"mysql","schema_context":[{"name":"contacts","fields":[{"name":"id","type":"INT"},{"name":"name","type":"VARCHAR"},{"name":"score","type":"INT"}]}]}'
   ```
4. **Send a chat message** (with a valid `GROQ_API_KEY` in `.env`):
   ```bash
   curl -X POST http://127.0.0.1:8000/sessions/<session_id>/chat \
     -H "Content-Type: application/json" \
     -H "X-API-Key: test-key" \
     -d '{"message":"How many contacts have a score above 5?"}'
   ```
5. Verify the response contains a `query` field with something like `SELECT COUNT(*) FROM contacts WHERE score > 5`.
