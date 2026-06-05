# Support Chat API — Integration Manual

**Version**: 0.2.0 (Agent + MCP Update)  
**Base URL (production)**: `https://support-chat-6ajp.onrender.com`  
**Base URL (local dev)**: `http://localhost:8000`  
**Interactive docs**: `/docs`

---

## What Changed in This Version

This release adds two major capabilities on top of the original query-translation service.

### Agent Mode (NEW)
The chat endpoint now supports `"agent_mode": true`. Instead of doing a single NL → query translation, the API runs a **LangGraph-based multi-step reasoning loop** powered by Groq LLM. The agent decides which tools to call, calls them in sequence, and returns a full reasoning trace alongside the final answer.

This is the foundation for the CRM chatbot experience — a user can ask the chat to "find all leads with a score above 80 and create a follow-up task for each", and the agent will reason, query, and act without requiring the front-end to orchestrate each step.

### MCP Server (NEW)
A **Model Context Protocol (MCP)** server is now mounted at `/mcp`. It exposes the same agent tools in a standardised, discoverable format over Server-Sent Events (SSE). External MCP clients (Claude Desktop, custom tooling) can connect and call tools directly using the protocol, independent of the chat session flow.

### Response Envelope Change
The `ChatMessageResponse` schema gained a new optional field: `agent_reasoning`. In standard mode it is `null`. In agent mode it contains the full step-by-step trace of what the agent thought and did.

---

## Authentication

All endpoints require the `X-API-Key` header.

```
X-API-Key: your-api-key
```

In development (`APP_ENV=development` and `API_KEYS` empty), auth is bypassed. In production, the key must be present in the `API_KEYS` environment variable (comma-separated list).

---

## Endpoints

### `GET /health`

Health check.

```json
{ "status": "healthy", "version": "0.1.0" }
```

---

### `POST /sessions`

Create a new chat session. All subsequent chat calls reference this session.

**Request body**

```json
{
  "query_type": "mysql",
  "schema_context": [
    {
      "name": "contacts",
      "description": "CRM contact records",
      "fields": [
        { "name": "id",        "type": "INT",          "is_primary_key": true },
        { "name": "name",      "type": "VARCHAR(255)" },
        { "name": "status",    "type": "VARCHAR(50)"  },
        { "name": "score",     "type": "INT"          },
        { "name": "owner_id",  "type": "INT",          "foreign_key": "users.id" }
      ]
    }
  ],
  "db_url": "mysql://user:pass@host:3306/crm",
  "system_instructions": "Always use read-only queries. Prefer indexed columns."
}
```

| Field | Required | Notes |
|---|---|---|
| `query_type` | yes | `sql`, `mysql`, `postgresql`, `sqlite`, `mongodb`, `pandas` |
| `schema_context` | conditional | Required if `db_url` is not provided or auto-discovery fails |
| `db_url` | no | Enables query execution and auto schema discovery |
| `system_instructions` | no | Injected into every LLM prompt for this session |

**Validation rule**: at least one of `schema_context` or `db_url` must be present.

**SQL auto-discovery**: when `db_url` is provided and `query_type` is a SQL dialect, the API introspects the database to build `schema_context` automatically. If introspection fails and `schema_context` was also provided, the manual schema is used as a fallback. If introspection fails and no `schema_context` was given, the request returns `400`.

**Response — `201 Created`**

```json
{
  "session_id": "058b821fedfd4abba25c9228982d7850",
  "created_at": "2026-06-04T09:00:00.000000Z",
  "query_type": "mysql",
  "has_db_connection": true
}
```

---

### `GET /sessions/{session_id}`

Returns session metadata.

```json
{
  "session_id": "058b821fedfd4abba25c9228982d7850",
  "created_at": "2026-06-04T09:00:00.000000Z",
  "query_type": "mysql",
  "message_count": 6,
  "has_db_connection": true
}
```

---

### `GET /sessions/{session_id}/history`

Returns the full conversation history.

```json
{
  "session_id": "058b821fedfd4abba25c9228982d7850",
  "messages": [
    {
      "role": "user",
      "content": "How many contacts have a score above 80?",
      "query": null,
      "query_result": null,
      "insight": null,
      "timestamp": "2026-06-04T09:01:00Z",
      "agent_reasoning": null
    },
    {
      "role": "assistant",
      "content": "There are 42 contacts with a score above 80.",
      "query": "SELECT COUNT(*) FROM contacts WHERE score > 80",
      "query_result": [{ "COUNT(*)": 42 }],
      "insight": "There are 42 contacts with a score above 80.",
      "timestamp": "2026-06-04T09:01:02Z",
      "agent_reasoning": null
    }
  ]
}
```

---

### `DELETE /sessions/{session_id}`

Deletes the session and all its history. Returns `204 No Content`.

---

### `POST /sessions/{session_id}/chat` ★ Main endpoint

Send a message. Supports two modes: standard and agent.

---

## Standard Mode

The original behaviour. One LLM call: translate the message into a query. Optionally execute it. Optionally generate a plain-English insight.

**Request**

```json
{
  "message": "How many active contacts signed up this month?",
  "execute_query": false,
  "generate_insight": true,
  "query_result": null,
  "agent_mode": false
}
```

| Field | Default | Notes |
|---|---|---|
| `message` | — | Required, min length 1 |
| `execute_query` | `false` | Runs the query if the session has a `db_url` |
| `generate_insight` | `true` | LLM summarises results in plain English |
| `query_result` | `null` | Client-supplied results; triggers insight generation directly |
| `agent_mode` | `false` | Set to `true` to activate agent mode (see below) |

**Response**

```json
{
  "role": "assistant",
  "content": "SELECT COUNT(*) FROM contacts WHERE is_active = 1 AND MONTH(signup_date) = MONTH(NOW())",
  "query": "SELECT COUNT(*) FROM contacts WHERE is_active = 1 AND MONTH(signup_date) = MONTH(NOW())",
  "query_result": null,
  "insight": null,
  "timestamp": "2026-06-04T09:01:02Z",
  "agent_reasoning": null
}
```

When `execute_query: true` and a DB connection exists, `query_result` is populated. When `generate_insight: true` and results exist, `content` and `insight` both contain the plain-English summary.

**Providing external results for insight**

If the front-end executes the query itself and only wants an insight:

```json
{
  "message": "Explain these results",
  "query_result": [{ "count": 142 }],
  "generate_insight": true
}
```

The translation step is skipped. The API generates and returns an insight directly.

---

## Agent Mode ★ NEW

Set `"agent_mode": true` to hand control to the LangGraph agent. Instead of a single translation, the agent runs a reasoning loop of up to 10 steps, selecting tools and calling them in sequence until the task is complete.

**Request**

```json
{
  "message": "Find all contacts with score above 80 and create a follow-up task for each.",
  "agent_mode": true
}
```

`execute_query`, `generate_insight`, and `query_result` are ignored in agent mode — the agent decides what to do based on the message.

**Response**

```json
{
  "role": "assistant",
  "content": "I completed 2 step(s):\n  ✓ execute_query: success\n  ✓ create_task: success",
  "query": "SELECT id, name FROM contacts WHERE score > 80",
  "query_result": [
    { "id": 1, "name": "Alice" },
    { "id": 2, "name": "Bob" }
  ],
  "insight": null,
  "timestamp": "2026-06-04T09:01:08Z",
  "agent_reasoning": [
    {
      "step": 1,
      "node": "execute_tool",
      "thought": null,
      "tool_name": "execute_query",
      "tool_input": null,
      "tool_result": {
        "query": "SELECT id, name FROM contacts WHERE score > 80",
        "query_result": [{ "id": 1, "name": "Alice" }, { "id": 2, "name": "Bob" }]
      },
      "action": "Executed execute_query: success"
    },
    {
      "step": 2,
      "node": "execute_tool",
      "thought": null,
      "tool_name": "create_task",
      "tool_input": null,
      "tool_result": {
        "task_id": "task_stub_123",
        "status": "pending"
      },
      "action": "Executed create_task: success"
    }
  ]
}
```

**Key response fields in agent mode**

| Field | Description |
|---|---|
| `content` | Summary of what the agent completed |
| `query` | Populated if an `execute_query` step ran successfully |
| `query_result` | Populated if an `execute_query` step returned data |
| `agent_reasoning` | Array of step objects — full trace of the agent's work |

**`agent_reasoning` step object**

| Field | Type | Description |
|---|---|---|
| `step` | int | Step number (1-indexed) |
| `node` | string | LangGraph node name: `execute_tool` |
| `tool_name` | string | Name of the tool called |
| `tool_result` | object | Raw data returned by the tool |
| `action` | string | Human-readable description |

---

## Agent Tools

These are the tools the agent can call autonomously. They are also exposed via the MCP server for direct external use.

### `execute_query`
Translates a natural language question into a data query. Executes it if the session has a DB connection.

| Input | Required | Description |
|---|---|---|
| `question` | yes | Natural language question |
| `translate_only` | no (default `false`) | Only generate the query, skip execution |

Returns: `{ query, explanation, confidence, query_result, note }`

### `search_schema`
Inspects the schema context attached to the session. Useful for the agent to understand what tables and fields are available before composing a query.

| Input | Required | Description |
|---|---|---|
| `search_term` | no | Filter tables by name |

Returns: `{ total_tables, matching_tables, search_term }`

### `get_context`
Retrieves recent conversation history and session metadata. The agent uses this to stay aware of what was previously discussed.

| Input | Required | Description |
|---|---|---|
| `last_n` | no (default `5`) | Number of recent messages to return |

Returns: `{ query_type, system_instructions, has_db_connection, recent_messages, message_count }`

### `create_task` ⚠ stub
Creates a task in the CRM.

| Input | Required | Description |
|---|---|---|
| `title` | yes | Task title |
| `description` | no | Longer description |
| `priority` | no (default `"normal"`) | `low`, `normal`, or `high` |

Returns: `{ task_id, title, priority, status, note }`

> **CRM integration note**: currently returns a stub response. To activate, replace `_create_task_tool` in `app/services/agent_tools.py` with a real `POST /api/tasks` call to your CRM backend.

### `update_contact` ⚠ stub
Updates fields on a CRM contact.

| Input | Required | Description |
|---|---|---|
| `contact_id` | yes | CRM contact ID |
| `fields` | yes | Dict of fields to update, e.g. `{ "status": "customer" }` |

Returns: `{ contact_id, updated_fields, note }`

> **CRM integration note**: stub. Replace `_update_contact_tool` with a `PATCH /api/contacts/:id` call.

### `send_email` ⚠ stub
Sends an email through the CRM.

| Input | Required | Description |
|---|---|---|
| `to` | yes | Recipient address |
| `subject` | yes | Subject line |
| `body` | yes | Email body |
| `cc` | no | CC address |
| `bcc` | no | BCC address |

Returns: `{ email_id, to, subject, status, note }`

> **CRM integration note**: stub. Replace `_send_email_tool` with a `POST /api/emails` call.

---

## MCP Server ★ NEW

The MCP server is mounted at `/mcp` using Server-Sent Events (SSE) transport. It makes all six agent tools and two resources available to any MCP-compatible client.

**Mount point**: `GET /mcp` → redirects to `/mcp/` (307)

### Connecting from a JavaScript/TypeScript client

```typescript
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";

const transport = new SSEClientTransport(
  new URL("https://support-chat-6ajp.onrender.com/mcp/")
);
const client = new Client({ name: "crm-frontend", version: "1.0.0" });
await client.connect(transport);

// Call a tool directly
const result = await client.callTool({
  name: "execute_query",
  arguments: {
    session_id: "058b821fedfd4abba25c9228982d7850",
    question: "How many contacts have score above 80?",
    translate_only: false,
  },
});
```

### MCP Resources

Resources provide read-only contextual data to MCP clients.

| URI pattern | Description |
|---|---|
| `session://{session_id}` | Full session context: schema, query type, DB status, message count |
| `contacts://list` | Placeholder contact list (stub — wire to CRM API) |

### MCP Tools

Same tools as the agent toolkit, callable directly from any MCP client without going through the chat session flow.

| Tool | Key inputs | Returns |
|---|---|---|
| `execute_query` | `session_id`, `question`, `translate_only` | JSON string with query/results |
| `search_schema` | `session_id`, `search_term` | JSON string with matching tables |
| `get_context` | `session_id`, `last_n` | JSON string with recent messages |
| `create_task` | `session_id`, `title`, `description`, `priority` | JSON string with task_id |
| `update_contact` | `session_id`, `contact_id`, `fields` (JSON string) | JSON string with confirmation |
| `send_email` | `session_id`, `to`, `subject`, `body` | JSON string with message_id |

All tools return a JSON-encoded string. Parse with `JSON.parse()` on the client side. Errors are returned inside the JSON under the `error` key rather than as exceptions.

---

## Integrating the Chatbot into the CRM Frontend

### Recommended session lifecycle

```
User opens chat panel
  → POST /sessions  (pass CRM schema + optional db_url)
  → Store session_id in component state

User types message
  → POST /sessions/{id}/chat

User closes panel or navigates away
  → DELETE /sessions/{id}
```

### Standard mode — query-only chatbot

Use this when the CRM frontend will execute queries itself or only needs the generated SQL.

```typescript
const response = await fetch(`${API}/sessions/${sessionId}/chat`, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
  body: JSON.stringify({ message: userText }),
});
const data = await response.json();
// data.query   → SQL to execute
// data.content → plain-English answer
```

### Standard mode — with DB execution

When you provide `db_url` at session creation and set `execute_query: true`, the API executes the query and returns results.

```typescript
body: JSON.stringify({
  message: userText,
  execute_query: true,
  generate_insight: true,
})
// data.query_result → raw results array
// data.content      → insight summary
```

### Agent mode — autonomous assistant

Use this for power-user scenarios where the chat should take actions, not just answer questions.

```typescript
body: JSON.stringify({
  message: userText,
  agent_mode: true,
})
// data.content          → summary of what the agent did
// data.agent_reasoning  → step-by-step trace (useful for "show thinking" UI)
// data.query            → populated if a query ran
// data.query_result     → populated if a query ran and returned data
```

### Rendering agent reasoning (optional)

`agent_reasoning` is an array you can render as a collapsible "Show thinking" panel:

```typescript
interface AgentStep {
  step: number;
  node: string;
  tool_name: string | null;
  tool_result: Record<string, unknown> | null;
  action: string;
}

// Example rendering
reasoning.map((step: AgentStep) => (
  <div key={step.step}>
    <span>Step {step.step}: {step.tool_name}</span>
    <span>{step.action}</span>
  </div>
))
```

### Providing the CRM schema

Pass the CRM tables the chatbot should know about in `schema_context`. The richer the metadata, the better the query quality.

```typescript
const session = await fetch(`${API}/sessions`, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
  body: JSON.stringify({
    query_type: "mysql",
    schema_context: [
      {
        name: "contacts",
        description: "CRM contacts and leads",
        fields: [
          { name: "id",         type: "INT",          is_primary_key: true },
          { name: "name",       type: "VARCHAR(255)",  description: "Full name" },
          { name: "status",     type: "VARCHAR(50)",   description: "lead | customer | churned" },
          { name: "score",      type: "INT",           description: "Lead score 0-100" },
          { name: "owner_id",   type: "INT",           foreign_key: "users.id" },
          { name: "created_at", type: "DATETIME" },
        ],
      },
      {
        name: "deals",
        description: "Sales pipeline deals",
        fields: [
          { name: "id",          type: "INT",    is_primary_key: true },
          { name: "contact_id",  type: "INT",    foreign_key: "contacts.id" },
          { name: "stage",       type: "VARCHAR(50)" },
          { name: "value",       type: "DECIMAL(10,2)" },
          { name: "closed_at",   type: "DATETIME" },
        ],
      },
    ],
    system_instructions:
      "You are a CRM assistant. Use contacts.status to distinguish leads from customers. " +
      "Never modify data. Keep queries efficient.",
  }),
});
```

---

## Activating the CRM Tool Stubs

The three CRM action tools (`create_task`, `update_contact`, `send_email`) currently return mock data. To wire them to your CRM backend, edit `app/services/agent_tools.py`:

```python
# Example: _create_task_tool replacement
import httpx

def _create_task_tool(self, session, tool_input):
    title = tool_input.get("title")
    if not title:
        return ToolResult(tool_name="create_task", success=False, error="'title' is required")

    resp = httpx.post(
        "https://your-crm.com/api/tasks",
        headers={"Authorization": f"Bearer {CRM_API_KEY}"},
        json={
            "title": title,
            "description": tool_input.get("description"),
            "priority": tool_input.get("priority", "normal"),
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return ToolResult(
        tool_name="create_task",
        success=True,
        data={"task_id": data["id"], "status": "created"},
    )
```

Apply the same pattern for `_update_contact_tool` (`PATCH /api/contacts/:id`) and `_send_email_tool` (`POST /api/emails`).

---

## Session Management

Sessions have a sliding TTL controlled by `SESSION_TTL_SECONDS` (default 3600 seconds / 1 hour). `last_accessed` is updated on every read or chat call. Expired sessions return `404`.

For a CRM chatbot, a good pattern is:
- Create a session when the user opens the chat panel
- Delete it when they close or navigate away
- Let TTL act as a safety net for abandoned tabs

---

## SSL and Database Connections

When passing a `db_url` to sessions, you can configure SSL inline:

```
# Disable cert verification (use only for trusted private networks)
mysql://user:pass@host:3306/db?ssl_verify=false

# Per-session CA cert (base64-encoded, URL-encoded in the query param)
mysql://user:pass@host:3306/db?ssl_ca_b64=<BASE64>
```

For the app persistence database (not per-session), set `DB_SSL_CA_B64` in `.env`.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | — | Required. Groq API key for LLM calls |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model to use |
| `APP_ENV` | `development` | `development` bypasses auth when `API_KEYS` is empty |
| `LOG_LEVEL` | `INFO` | Python log level |
| `SESSION_TTL_SECONDS` | `3600` | Session expiry in seconds (sliding) |
| `API_KEYS` | — | Comma-separated valid API keys. Empty = auth bypassed in dev |
| `RATE_LIMIT` | `60/minute` | Per-IP rate limit |
| `DATABASE_URL` | — | SQLAlchemy URL for the app persistence DB |
| `DB_SSL_CA_B64` | — | Base64-encoded CA cert for the app DB |

---

## Error Responses

All errors follow a consistent envelope:

```json
{ "detail": "Human-readable error message" }
```

| Status | Cause |
|---|---|
| `400` | DB auto-discovery failed with no fallback schema |
| `401` | Missing or invalid `X-API-Key` |
| `404` | Session not found or expired |
| `422` | Validation error (missing required fields, invalid enum value) |
| `429` | Rate limit exceeded |
| `500` | Unexpected server error (check server logs) |

---

## Quick Reference

### Create session + ask in agent mode

```bash
# 1. Create session
SESSION=$(curl -s -X POST https://support-chat-6ajp.onrender.com/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "query_type": "mysql",
    "schema_context": [{
      "name": "contacts",
      "fields": [
        {"name": "id",     "type": "INT", "is_primary_key": true},
        {"name": "name",   "type": "VARCHAR(255)"},
        {"name": "score",  "type": "INT"},
        {"name": "status", "type": "VARCHAR(50)"}
      ]
    }]
  }' | jq -r '.session_id')

# 2. Ask in agent mode
curl -s -X POST https://support-chat-6ajp.onrender.com/sessions/$SESSION/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"message": "Which tables do I have and what are the top 5 contacts by score?", "agent_mode": true}' \
  | jq '{content, query, agent_steps: (.agent_reasoning | length)}'

# 3. Clean up
curl -X DELETE https://support-chat-6ajp.onrender.com/sessions/$SESSION \
  -H "X-API-Key: your-key"
```

### Standard mode with external result

```bash
curl -s -X POST https://support-chat-6ajp.onrender.com/sessions/$SESSION/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "message": "Explain what these numbers mean for our pipeline",
    "query_result": [{"stage": "Proposal", "count": 12, "total_value": 48000}],
    "generate_insight": true
  }' | jq '.content'
```
