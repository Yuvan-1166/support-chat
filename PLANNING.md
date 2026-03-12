# Support-Chat Backend Application Planning

This document describes the technical stack, features, and architectural approach for building the support-chat backend application. The primary goal is to provide an API service that translates natural-language questions about a data store into queries and returns results or insights.

---

## 🎯 Objectives

- Offer a **backend-only API** consumed by other applications.
- Accept user questions about a data source and produce the corresponding query (SQL, MongoDB, Pandas, etc.).
- Execute queries against configured data sources and return results.
- Maintain **conversational sessions** for stateful interactions and follow-ups.
- Provide natural-language insights using NLP/LLM when requested.
- Be **flexible and extensible**: support multiple data types, query languages, and business profiles.

---

## 🧩 Core Features

1. **Session Management**
   - Each chat is tied to a `session_id`.
   - Store conversation history (user messages, generated queries, data results, bot replies).
   - Session expiration and cleanup (configurable TTL).

2. **Query Translation**
   - Use an LLM to convert natural-language prompts into data queries.
   - Provide schema metadata (tables/fields, sample data) to inform the model.
   - Support multiple query dialects (SQL variants, MongoDB, Pandas, etc.).
   - Allow specification of target query type per session or per request.

3. **Execution Layer**
   - Pluggable adapters for each data backend:
     - SQL: SQLAlchemy connectors (MySQL, PostgreSQL, SQLite, etc.).
     - MongoDB: PyMongo or Motor.
     - Pandas: in-memory `DataFrame` operations.
   - Execute generated queries safely, in read-only mode, returning results or errors.

4. **Insight Generation**
   - Optionally pass query results to the LLM for natural-language insights.
   - This step is configurable per request.

5. **Configuration & Extensibility**
   - Provide a profile with:
     - Data model definitions (tables, fields, relationships).
     - Allowed question/response patterns.
     - Business rules (e.g., "no PII").
   - Easily add new adapters or query languages without touching core code.

6. **API Endpoints**
   - `POST /session` → create new session with optional profile.
   - `POST /session/{id}/message` → submit a message, returns bot response.
   - `GET /session/{id}/history` → fetch conversation history.
   - `DELETE /session/{id}` → terminate session.
   - Admin/config endpoints for adding/removing data sources.

7. **Security & Rate Limiting**
   - API key or JWT authentication.
   - Input validation and query sanitization.
   - Rate limiting and logging for auditing.

---

## 🛠 Technology Stack

| Layer              | Technology                                  | Rationale                                                                         |
|--------------------|---------------------------------------------|-----------------------------------------------------------------------------------|
| Language & Runtime | **Python 3.11+**                            | Strong ecosystem, async support, great libraries                               |
| Web framework      | **FastAPI**                                 | Async, pydantic models, auto-generated docs                                   |
| HTTP Server        | Uvicorn / Gunicorn                          | Production-ready ASGI servers                                                  |
| ORM / DB           | SQLAlchemy + Alembic                        | Database-agnostic, migrations                                                  |
| NoSQL              | PyMongo / Motor                             | Async-friendly MongoDB clients                                                 |
| Cache/Session      | Redis (or relational DB)                    | Fast session storage and expiration                                            |
| DI & Configuration | Pydantic settings + FastAPI dependencies    | Clean configuration management                                                 |
| LLM Integration    | OpenAI or local models via `langchain`      | Flexible, with plug-in adapters                                                 |
| Testing            | `pytest`, `httpx`                           | Standard Python testing tools                                                   |
| Containerization   | Docker                                      | Portable deployment                                                            |
| CI/CD              | GitHub Actions                              | Automate linting, type-checking, tests, builds                                 |

> 💡 Structure components modularly: separate **translator**, **executor**, and **session store** with clear interfaces.

---

## 📦 Suggested Project Structure

```
support-chat/
├─ app/
│  ├─ main.py             # FastAPI application entrypoint
│  ├─ api/                # Routers (sessions, messages, admin)
│  ├─ core/               # Settings, security, llm client setup
│  ├─ services/           # translator, executor, session manager
│  ├─ db/                 # models, adapters, migrations
│  ├─ schemas/            # Pydantic models for requests/responses
│  ├─ utils/              # Helpers (query sanitiser, prompt builder)
├─ tests/                 # pytest test cases
├─ Dockerfile
├─ requirements.txt
├─ alembic/               # migration scripts
└─ README.md
```

---

## 🚀 Development Roadmap

1. Finalize initial requirements (databases, query languages, profiles).
2. Scaffold the repository with FastAPI, settings, and basic endpoints.
3. Implement dummy translator returning hardcoded queries.
4. Add actual LLM client and iterate on prompt engineering.
5. Build adapters for the first database types and test query execution.
6. Introduce session storage using Redis or DB.
7. Implement history retrieval and cleanup.
8. Add insight generation with LLM.
9. Harden security (auth, sanitization) and add rate limiting.
10. Write comprehensive unit/integration tests.
11. Containerize and configure CI/CD.

---

## ✔️ Next Steps

- Begin scaffolding the codebase (FastAPI project layout).
- Create initial `POST /session` and `POST /session/{id}/message` routes with stub logic.
- Develop prompt templates and test basic LLM translation.

Let me know when you’re ready to start with the scaffold or if you want assistance generating the first files.