# Support Chat API Manual

This manual documents the current API behavior of the Support Chat backend.

## What This API Does

- Creates conversational sessions for data Q&A.
- Translates natural language to data queries (SQL/MongoDB/Pandas).
- Optionally executes queries when a `db_url` is attached to the session.
- Optionally generates plain-English insights from query results.
- Persists sessions and message history in the app database.

## Base URLs

- Local: `http://localhost:8000`
- Deployed: https://support-chat-6ajp.onrender.com

## Interactive Docs

- OpenAPI UI: `/docs`

## Authentication

The API uses `X-API-Key` header.

```http
X-API-Key: your-api-key
```

Behavior:
- Production: key is required and must exist in `API_KEYS`.
- Development: if `API_KEYS` is empty, auth is bypassed.

---

## Endpoint Summary

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Basic service info |
| GET | `/health` | Health check |
| POST | `/sessions` | Create a chat session |
| GET | `/sessions/{session_id}` | Session metadata |
| GET | `/sessions/{session_id}/history` | Full chat history |
| DELETE | `/sessions/{session_id}` | Delete session |
| POST | `/sessions/{session_id}/chat` | Send message / execute / insight |

---

## 1. Root

### `GET /`

Returns basic service metadata.

Example response:

```json
{
  "Artifact": "Support Chat",
  "version": "0.1.0"
}
```

---

## 2. Health Check

### `GET /health`

Example response:

```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

Status codes:
- `200 OK`

---

## 3. Create Session

### `POST /sessions`

Creates a session and stores schema context for future query generation.

### Request body

```json
{
  "query_type": "mysql",
  "schema_context": [],
  "db_url": "mysql://user:pass@host:3306/dbname",
  "system_instructions": "Keep queries read-only and efficient."
}
```

### Field details

- `query_type` required
  - allowed: `sql`, `mysql`, `postgresql`, `sqlite`, `mongodb`, `pandas`
- `schema_context` optional if `db_url` is provided
- `db_url` optional
- `system_instructions` optional

Validation rule:
- At least one of `schema_context` or `db_url` must be provided.

### SQL auto-discovery behavior

When `db_url` is provided and `query_type` is one of `sql/mysql/postgresql/sqlite`:
- API tries to introspect DB schema automatically (tables, columns, PKs).
- If introspection succeeds, discovered schema is used.
- If introspection fails and request already has `schema_context`, API falls back to provided schema.
- If introspection fails and `schema_context` is empty, API returns `400`.

### Response

```json
{
  "session_id": "97be706886d64df89c32935f221f9a8f",
  "created_at": "2026-03-14T10:00:00.000000Z",
  "query_type": "mysql",
  "has_db_connection": true
}
```

Status codes:
- `201 Created`
- `400 Bad Request` (for failed auto-discovery with no fallback schema)
- `401 Unauthorized`
- `422 Unprocessable Entity`

---

## 4. Get Session Info

### `GET /sessions/{session_id}`

Returns metadata and message count.

Example response:

```json
{
  "session_id": "97be706886d64df89c32935f221f9a8f",
  "created_at": "2026-03-14T10:00:00.000000Z",
  "query_type": "mysql",
  "message_count": 4,
  "has_db_connection": true
}
```

Status codes:
- `200 OK`
- `401 Unauthorized`
- `404 Not Found`

---

## 5. Send Chat Message

### `POST /sessions/{session_id}/chat`

Main conversation endpoint.

### Request body

```json
{
  "message": "Which table tells whether the customer is available or not?",
  "execute_query": true,
  "generate_insight": true,
  "query_result": null
}
```

Field behavior:
- `message` required
- `execute_query` default `false`
- `generate_insight` default `false`
- `query_result` optional (used when client executes query externally)

### Response shape

```json
{
  "role": "assistant",
  "content": "This query checks availability...",
  "query": "SELECT ...",
  "query_result": [{"count": 42}],
  "insight": "There are 42 matching records.",
  "timestamp": "2026-03-14T10:02:00.000000Z"
}
```

Status codes:
- `200 OK`
- `401 Unauthorized`
- `404 Not Found`
- `422 Unprocessable Entity`
- `500 Internal Server Error`

### Execution behavior

If `execute_query=true` and session has `db_url`:
- API selects adapter by `query_type`.
- Runs query in read-only mode.
- Appends execution errors in assistant content as `⚠️ Execution error: ...`.

If `query_result` is provided in request:
- Translation step is skipped.
- API can directly generate insight from provided result.

---

## 6. Get History

### `GET /sessions/{session_id}/history`

Returns all user/assistant messages for the session.

Response:

```json
{
  "session_id": "97be706886d64df89c32935f221f9a8f",
  "messages": [
    {
      "role": "user",
      "content": "How many contacts?",
      "query": null,
      "query_result": null,
      "insight": null,
      "timestamp": "2026-03-14T10:05:00"
    }
  ]
}
```

Status codes:
- `200 OK`
- `401 Unauthorized`
- `404 Not Found`

---

## 7. Delete Session

### `DELETE /sessions/{session_id}`

Deletes session and history.

Status codes:
- `204 No Content`
- `401 Unauthorized`
- `404 Not Found`

---

## Session Lifecycle and Expiration

- Session TTL is controlled by `SESSION_TTL_SECONDS`.
- Default is `3600` seconds (1 hour).
- TTL is sliding: `last_accessed` is updated when session is read/used.
- Expired sessions are deleted and treated as not found.

---

## DB URL Rules and SSL Options

For SQL-family sessions with `db_url`:

- MySQL URLs are normalized to `mysql+pymysql://...` internally.
- You can pass SSL options in DB URL query params:

1. `ssl_ca_b64`
- Base64-encoded CA cert for that specific DB URL.
- Used for schema introspection and query execution.
- Preferred for secure custom cert chains.

2. `ssl_verify`
- `true` (default): cert verification enabled.
- `false`: disables cert verification for that DB URL.

Example:

```text
mysql://user:pass@host:3306/db?ssl_verify=false
```

Secure per-DB CA example:

```text
mysql://user:pass@host:3306/db?ssl_ca_b64=<URL-ENCODED-BASE64>
```

Security note:
- `ssl_verify=false` should be used only when you cannot obtain a valid CA chain.

---

## Query Safety Rules

### SQL adapter

- Blocks write/DDL keywords at start or inline (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `REPLACE`, `GRANT`, `REVOKE`).
- Blocks stacked statements like `SELECT ...; DROP ...`.
- Allows read-only statements such as `SELECT`, `SHOW`, `DESCRIBE`.

### MongoDB adapter

- Expects JSON query spec.
- Supports `find` and `aggregate`.
- Blocks write operations (`insert`, `update`, `delete`, etc.).

### Pandas adapter

- Supports JSON spec with `expression`, optional `columns`, optional `limit`.
- Also accepts plain expression fallback.

---

## JSON Normalization of Query Results

Before persistence/response, results are converted into JSON-safe values.

Examples:
- `timedelta` -> `HH:MM:SS`
- `datetime/date/time` -> ISO strings
- `Decimal` -> string
- `bytes` -> UTF-8 string
- nested values converted recursively

This prevents DB JSON column serialization errors during chat message storage.

---

## Error Model (Common)

Typical error response shape:

```json
{
  "detail": "Human-readable error"
}
```

Common statuses:
- `400` invalid DB/schema discovery conditions
- `401` missing/invalid API key
- `404` missing/expired session
- `422` payload validation issues
- `429` in-memory rate limiter exceeded
- `500` unexpected server error

---

## Environment Variables

Key runtime settings:

- `APP_ENV` (`development`/`production`)
- `LOG_LEVEL`
- `API_KEYS` (comma-separated)
- `SESSION_TTL_SECONDS`
- `GROQ_API_KEY`
- `GROQ_MODEL`
- `DATABASE_URL` (app persistence DB)
- `DB_SSL_CA_B64` (base64 CA for app persistence DB)

---

## End-to-End cURL Example

### 1) Create session (query-only)

```bash
curl -s -X POST https://support-chat-6ajp.onrender.com/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "query_type": "mysql",
    "schema_context": [
      {
        "name": "contacts",
        "description": "Stores customer contacts",
        "fields": [
          {"name": "id", "type": "INT", "is_primary_key": true},
          {"name": "name", "type": "VARCHAR(255)"},
          {"name": "is_active", "type": "BOOLEAN"}
        ]
      }
    ]
  }' | jq
```

### 2) Ask question

```bash
curl -s -X POST https://support-chat-6ajp.onrender.com/sessions/<session_id>/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{"message": "How many active contacts do we have?"}' | jq
```

### 3) Ask for insight from external result

```bash
curl -s -X POST https://support-chat-6ajp.onrender.com/sessions/<session_id>/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "message": "Explain these results",
    "query_result": [{"count": 1250}],
    "generate_insight": true
  }' | jq
```

### 4) Fetch history

```bash
curl -s -X GET https://support-chat-6ajp.onrender.com/sessions/<session_id>/history \
  -H "X-API-Key: test-key" | jq
```

### 5) Delete session

```bash
curl -i -X DELETE https://support-chat-6ajp.onrender.com/sessions/<session_id> \
  -H "X-API-Key: test-key"
```

---

## Notes for Integrators

- For best query quality, provide rich table/field metadata if not using auto-discovery.
- For SQL `db_url` sessions, auto-discovery is attempted automatically.
- If target DB uses self-signed certs, provide `ssl_ca_b64`; use `ssl_verify=false` only as last resort.
- Session context matters: reuse `session_id` for follow-up questions.
