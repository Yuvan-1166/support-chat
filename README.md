# Support Chat API

Natural-language → data-query translation service with session management, optional query execution, and insight generation.

## Quick Start

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set your GROQ_API_KEY
```

### 3. Run the server

```bash
uvicorn app.main:app --reload
```

The API docs are available at **http://127.0.0.1:8000/docs**.

---

## API Overview

| Method | Endpoint | Description |
|--------|-------------------------------------|----------------------------------------------|
| POST | `/sessions` | Create a new chat session |
| GET | `/sessions/{id}` | Get session info |
| GET | `/sessions/{id}/history` | Get conversation history |
| DELETE | `/sessions/{id}` | Delete a session |
| POST | `/sessions/{id}/chat` | Send a message, get query + optional insight |
| GET | `/health` | Health check |

### Example: Create a session

```bash
curl -X POST http://127.0.0.1:8000/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "query_type": "mysql",
    "schema_context": [
      {
        "name": "contacts",
        "fields": [
          {"name": "id", "type": "INT", "is_primary_key": true},
          {"name": "name", "type": "VARCHAR(255)"},
          {"name": "score", "type": "INT"}
        ]
      }
    ]
  }'
```

### Example: Ask a question

```bash
curl -X POST http://127.0.0.1:8000/sessions/<session_id>/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{"message": "How many contacts have a score above 5?"}'
```

### Example: Provide external results for insight

```bash
curl -X POST http://127.0.0.1:8000/sessions/<session_id>/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "message": "Explain these results",
    "query_result": [{"count": 42}],
    "generate_insight": true
  }'
```

---

## Docker

```bash
cp .env.example .env
docker compose up --build
```

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Security

- **API Key Auth**: Set `API_KEYS` in `.env` (comma-separated). All endpoints require `X-API-Key` header.
- **Query Execution**: Only allowed when `db_url` is provided at session creation. All queries are **read-only** — write operations are blocked.
- **Rate Limiting**: Default `60/minute` per IP, configurable via `RATE_LIMIT`.
