# Support Chat API Manual

This document explains how an application can integrate with the Support Chat API.

The API converts natural-language prompts into database queries, maintains chat sessions, optionally executes generated queries, and can produce insights from query results.

## Base URL

Use one of the following depending on your environment:

- Local: `http://127.0.0.1:8000`
- Production: `https://support-chat-nm8i.onrender.com`

## Interactive API Docs

If the server is running, OpenAPI docs are available at:

- `/docs`

Example:

- `http://127.0.0.1:8000/docs`

## Authentication

Most endpoints require an API key in the `X-API-Key` header.

### Header

```http
X-API-Key: your-api-key
```

### Development behavior

If `APP_ENV=development` and `API_KEYS` is empty, authentication is skipped.

### Production behavior

Set `API_KEYS` as a comma-separated list in environment variables.

Example:

```env
API_KEYS=test-key,another-key
```

---

# API Overview

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/sessions` | Create a new chat session |
| GET | `/sessions/{session_id}` | Get session metadata |
| GET | `/sessions/{session_id}/history` | Get full conversation history |
| DELETE | `/sessions/{session_id}` | Delete a session |
| POST | `/sessions/{session_id}/chat` | Send a user message and receive a query / result / insight |

---

# 1. Health Check

## Endpoint

`GET /health`

## Purpose

Confirms the server is running.

## Example Request

```bash
curl -s http://127.0.0.1:8000/health | jq
```

## Example Response

```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

## Status Codes

- `200 OK`

---

# 2. Create Session

## Endpoint

`POST /sessions`

## Purpose

Creates a chat session with:

- target query dialect
- schema context
- optional database connection URL
- optional system instructions

A session is required before sending chat messages.

## Headers

```http
Content-Type: application/json
X-API-Key: your-api-key
```

## Request Body

```json
{
  "query_type": "mysql",
  "schema_context": [
    {
      "name": "users",
      "description": "Store user accounts",
      "fields": [
        {
          "name": "id",
          "type": "INT",
          "description": "Primary key",
          "is_primary_key": true
        },
        {
          "name": "name",
          "type": "VARCHAR(100)",
          "description": "User full name",
          "is_primary_key": false
        },
        {
          "name": "is_active",
          "type": "BOOLEAN",
          "description": "Whether account is active",
          "is_primary_key": false
        },
        {
          "name": "signup_date",
          "type": "DATE",
          "description": "Date the user signed up",
          "is_primary_key": false
        }
      ]
    }
  ],
  "db_url": "mysql+pymysql://user:password@host:3306/dbname",
  "system_instructions": "Keep queries efficient and read-only."
}
```

## Fields

### `query_type`

Supported values:

- `sql`
- `mysql`
- `postgresql`
- `sqlite`
- `mongodb`
- `pandas`

### `schema_context`

A list describing the tables, collections, or DataFrames the LLM should use.

### `db_url`

Optional.

If provided, the service may execute generated queries directly when `execute_query=true` is sent later in chat.

If omitted, the API will return query text only.

### `system_instructions`

Optional.

Use this to add business rules or output constraints.

Examples:

- "Always filter deleted records out."
- "Never query PII columns."
- "Prefer aggregation queries over row-level output."

## Example Request

```bash
curl -s -X POST http://127.0.0.1:8000/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "query_type": "mysql",
    "schema_context": [
      {
        "name": "users",
        "description": "Store user accounts",
        "fields": [
          {"name": "id", "type": "INT", "is_primary_key": true},
          {"name": "name", "type": "VARCHAR(100)"},
          {"name": "is_active", "type": "BOOLEAN"},
          {"name": "signup_date", "type": "DATE"}
        ]
      }
    ],
    "system_instructions": "Keep queries optimal."
  }' | jq
```

## Example Response

```json
{
  "session_id": "8e84110abbe14d2295d96ef1f8ab591c",
  "created_at": "2026-03-12T10:13:35.156853Z",
  "query_type": "mysql",
  "has_db_connection": false
}
```

## Status Codes

- `201 Created`
- `401 Unauthorized`
- `422 Unprocessable Entity`
- `500 Internal Server Error`

---

# 3. Get Session Info

## Endpoint

`GET /sessions/{session_id}`

## Purpose

Returns metadata for a session.

## Example Request

```bash
curl -s -X GET http://127.0.0.1:8000/sessions/8e84110abbe14d2295d96ef1f8ab591c \
  -H "X-API-Key: test-key" | jq
```

## Example Response

```json
{
  "session_id": "8e84110abbe14d2295d96ef1f8ab591c",
  "created_at": "2026-03-12T10:13:35.156853Z",
  "query_type": "mysql",
  "message_count": 4,
  "has_db_connection": false
}
```

## Status Codes

- `200 OK`
- `401 Unauthorized`
- `404 Not Found`

---

# 4. Send Chat Message

## Endpoint

`POST /sessions/{session_id}/chat`

## Purpose

Sends a natural-language message into the session.

The API can:

1. generate a query
2. optionally execute the query
3. optionally generate an insight from query results

## Headers

```http
Content-Type: application/json
X-API-Key: your-api-key
```

## Request Body

```json
{
  "message": "How many active users signed up this year?",
  "execute_query": false,
  "generate_insight": false,
  "query_result": null
}
```

## Fields

### `message`

Required natural-language prompt.

### `execute_query`

Default: `false`

When `true` and the session has a `db_url`, the backend attempts to execute the generated query and return results.

### `generate_insight`

Default: `false`

When `true`, the backend uses returned or supplied query results to produce a plain-English summary.

### `query_result`

Optional.

Use this when your application executes the query externally and wants the API to generate an explanation or insight.

## Mode A: Query Generation Only

### Request

```bash
curl -s -X POST http://127.0.0.1:8000/sessions/<session_id>/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "message": "How many active users signed up this year?"
  }' | jq
```

### Example Response

```json
{
  "role": "assistant",
  "content": "This query counts the number of active users who signed up this year by filtering the users table based on the is_active flag and the year of the signup date.",
  "query": "SELECT COUNT(id) FROM users WHERE is_active = 1 AND YEAR(signup_date) = YEAR(CURDATE())",
  "query_result": null,
  "insight": null,
  "timestamp": "2026-03-12T10:13:36.088449Z"
}
```

## Mode B: Generate Insight from External Results

### Request

```bash
curl -s -X POST http://127.0.0.1:8000/sessions/<session_id>/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "message": "Explain these results to me",
    "query_result": [{"count": 1250}],
    "generate_insight": true
  }' | jq
```

### Example Response

```json
{
  "role": "assistant",
  "content": "There are 1250 active users who signed up this year.",
  "query": null,
  "query_result": [
    {
      "count": 1250
    }
  ],
  "insight": "There are 1250 active users who signed up this year.",
  "timestamp": "2026-03-12T10:13:36.608897Z"
}
```

## Mode C: Execute Query in Backend

This only works if `db_url` was provided when the session was created.

### Request

```bash
curl -s -X POST http://127.0.0.1:8000/sessions/<session_id>/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "message": "Show the total number of users",
    "execute_query": true
  }' | jq
```

### Typical Response Shape

```json
{
  "role": "assistant",
  "content": "Here is the generated query and its result.",
  "query": "SELECT COUNT(*) AS total_users FROM users",
  "query_result": [
    {
      "total_users": 5421
    }
  ],
  "insight": null,
  "timestamp": "2026-03-12T10:13:36.608897Z"
}
```

## Status Codes

- `200 OK`
- `401 Unauthorized`
- `404 Not Found`
- `422 Unprocessable Entity`
- `500 Internal Server Error`

---

# 5. Get Session History

## Endpoint

`GET /sessions/{session_id}/history`

## Purpose

Returns all stored messages in the session.

## Example Request

```bash
curl -s -X GET http://127.0.0.1:8000/sessions/<session_id>/history \
  -H "X-API-Key: test-key" | jq
```

## Example Response

```json
{
  "session_id": "8e84110abbe14d2295d96ef1f8ab591c",
  "messages": [
    {
      "role": "user",
      "content": "How many active users signed up this year?",
      "query": null,
      "query_result": null,
      "insight": null,
      "timestamp": "2026-03-12T10:13:35"
    },
    {
      "role": "assistant",
      "content": "This query counts the number of active users who signed up this year by filtering the users table based on the is_active flag and the year of the signup date.",
      "query": "SELECT COUNT(id) FROM users WHERE is_active = 1 AND YEAR(signup_date) = YEAR(CURDATE())",
      "query_result": null,
      "insight": null,
      "timestamp": "2026-03-12T10:13:36"
    }
  ]
}
```

## Status Codes

- `200 OK`
- `401 Unauthorized`
- `404 Not Found`

---

# 6. Delete Session

## Endpoint

`DELETE /sessions/{session_id}`

## Purpose

Deletes the session and its stored history.

## Example Request

```bash
curl -i -X DELETE http://127.0.0.1:8000/sessions/<session_id> \
  -H "X-API-Key: test-key"
```

## Example Response

HTTP status only:

```http
HTTP/1.1 204 No Content
```

## Status Codes

- `204 No Content`
- `401 Unauthorized`
- `404 Not Found`

---

# Data Model Reference

## `SchemaField`

```json
{
  "name": "id",
  "type": "INT",
  "description": "Primary key",
  "is_primary_key": true
}
```

## `SchemaTable`

```json
{
  "name": "users",
  "description": "Store user accounts",
  "fields": [
    {
      "name": "id",
      "type": "INT",
      "description": "Primary key",
      "is_primary_key": true
    }
  ]
}
```

## `SessionCreateResponse`

```json
{
  "session_id": "string",
  "created_at": "2026-03-12T10:13:35.156853Z",
  "query_type": "mysql",
  "has_db_connection": false
}
```

## `ChatMessageResponse`

```json
{
  "role": "assistant",
  "content": "string",
  "query": "string or null",
  "query_result": {},
  "insight": "string or null",
  "timestamp": "2026-03-12T10:13:36.088449Z"
}
```

---

# Error Handling

## `401 Unauthorized`

Returned when API key is missing or invalid.

Example:

```json
{
  "detail": "Invalid or missing API key."
}
```

## `404 Not Found`

Returned when the session does not exist or has expired.

Example:

```json
{
  "detail": "Session 'abc123' not found or expired."
}
```

## `422 Unprocessable Entity`

Returned when request payload is invalid.

Examples:

- missing `message`
- invalid `query_type`
- malformed JSON
- missing required fields inside `schema_context`

## `500 Internal Server Error`

Returned for unexpected backend failures.

In development, the response may contain the raw error string.

---

# Integration Patterns

## Pattern 1: Query Generation Only

Use this when your application wants to:

- ask business questions in natural language
- receive a safe query
- execute it in your own infrastructure

Flow:

1. Create a session without `db_url`
2. Call chat endpoint with `message`
3. Read `query`
4. Execute query yourself
5. Optionally send `query_result` back with `generate_insight=true`

## Pattern 2: End-to-End Execution in Backend

Use this when your application wants the API to:

- generate the query
- execute it directly
- optionally summarize the results

Flow:

1. Create a session with `db_url`
2. Call chat endpoint with `execute_query=true`
3. Read `query_result`
4. Optionally call again with `generate_insight=true`

## Pattern 3: Persistent Conversation

Use one `session_id` across multiple user turns to preserve context.

Example:

- "How many active users signed up this year?"
- "Break that down by month"
- "Now only for premium users"

---

# Best Practices

- Create one session per user conversation.
- Always store `session_id` in your client application.
- Provide rich `schema_context`; better schema descriptions lead to better queries.
- Use `system_instructions` for business constraints.
- If you need strict control over DB execution, omit `db_url` and execute queries yourself.
- Use `/history` to sync chat history into your frontend.
- Delete sessions when they are no longer needed.

---

# Example End-to-End cURL Flow

## Step 1: Create session

```bash
SESSION_ID=$(curl -s -X POST http://127.0.0.1:8000/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "query_type": "mysql",
    "schema_context": [
      {
        "name": "users",
        "description": "Store user accounts",
        "fields": [
          {"name": "id", "type": "INT", "is_primary_key": true},
          {"name": "name", "type": "VARCHAR(100)"},
          {"name": "is_active", "type": "BOOLEAN"},
          {"name": "signup_date", "type": "DATE"}
        ]
      }
    ],
    "system_instructions": "Keep queries optimal."
  }' | jq -r '.session_id')

echo "$SESSION_ID"
```

## Step 2: Ask a question

```bash
curl -s -X POST http://127.0.0.1:8000/sessions/$SESSION_ID/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "message": "How many active users signed up this year?"
  }' | jq
```

## Step 3: Provide external result for summary

```bash
curl -s -X POST http://127.0.0.1:8000/sessions/$SESSION_ID/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-key" \
  -d '{
    "message": "Explain these results to me",
    "query_result": [{"count": 1250}],
    "generate_insight": true
  }' | jq
```

## Step 4: Fetch history

```bash
curl -s -X GET http://127.0.0.1:8000/sessions/$SESSION_ID/history \
  -H "X-API-Key: test-key" | jq
```

## Step 5: Delete session

```bash
curl -i -X DELETE http://127.0.0.1:8000/sessions/$SESSION_ID \
  -H "X-API-Key: test-key"
```

---

# Notes for Docker / Render Deployments

If you deploy to Render or another container platform:

- set `DATABASE_URL`
- set `GROQ_API_KEY`
- set `API_KEYS`
- if using Aiven CA cert, use `DB_SSL_CA_B64`

Generate `DB_SSL_CA_B64` locally with:

```bash
base64 -w0 ca.pem
```

Paste that output into your deployment environment variable.

---

# Summary

To integrate another application:

1. authenticate with `X-API-Key`
2. create a session with schema context
3. send chat messages to generate queries
4. optionally execute queries through backend or externally
5. optionally generate insights from results
6. read history or delete the session when done
