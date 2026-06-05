#!/usr/bin/env bash
# =============================================================================
#  test_agent.sh — End-to-end API tests for Support Chat (including agent mode)
#
#  Usage:
#    ./test_agent.sh [--url URL] [--key API_KEY]
#
#  Requires: curl, jq
#  Start the server first:  uvicorn app.main:app --reload
# =============================================================================

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
API_URL="${API_URL:-http://127.0.0.1:8000}"
API_KEY="${API_KEY:-test-key}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) API_URL="$2"; shift 2 ;;
    --key) API_KEY="$2"; shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── State ─────────────────────────────────────────────────────────────────────
PASS=0
FAIL=0
SESSION_ID=""

# ── Helpers ───────────────────────────────────────────────────────────────────
ok()   { echo -e "${GREEN}  ✓${RESET} $*"; ((PASS++)) || true; }
fail() { echo -e "${RED}  ✗${RESET} $*"; ((FAIL++)) || true; }
info() { echo -e "${CYAN}  →${RESET} $*"; }
section() { echo -e "\n${BOLD}${YELLOW}══ $* ══${RESET}"; }

# Run curl, return body. Exit code reflects HTTP status >= 400.
api() {
  local method="$1"; shift
  local path="$1";   shift
  curl -s -X "$method" \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    "$@" \
    "${API_URL}${path}"
}

check_field() {
  local label="$1" json="$2" field="$3" expected="$4"
  local actual
  actual=$(echo "$json" | jq -r ".$field // empty" 2>/dev/null)
  if [[ "$actual" == "$expected" ]]; then
    ok "$label"
  else
    fail "$label (expected '$expected', got '$actual')"
  fi
}

check_present() {
  local label="$1" json="$2" field="$3"
  local actual
  actual=$(echo "$json" | jq -r ".$field // empty" 2>/dev/null)
  if [[ -n "$actual" && "$actual" != "null" ]]; then
    ok "$label"
  else
    fail "$label (field '$field' missing or null)"
  fi
}

check_http() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    ok "$label (HTTP $actual)"
  else
    fail "$label (expected HTTP $expected, got $actual)"
  fi
}

# ─────────────────────────────────────────────────────────────────────────────

echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║   Support Chat — API Test Suite          ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${RESET}"
echo "  URL: $API_URL"
echo "  Key: $API_KEY"

# ── 1. Health ─────────────────────────────────────────────────────────────────
section "1 · Health & Root"

HEALTH=$(api GET /health)
check_field "GET /health → status=healthy" "$HEALTH" "status" "healthy"

ROOT=$(api GET /)
check_field "GET / → Artifact=Support Chat" "$ROOT" "Artifact" "Support Chat"
check_present "GET / → version present" "$ROOT" "version"

# ── 2. Session lifecycle ──────────────────────────────────────────────────────
section "2 · Session Lifecycle"

CREATE=$(api POST /sessions -d '{
  "query_type": "mysql",
  "schema_context": [
    {
      "name": "contacts",
      "description": "Customer contact records",
      "fields": [
        {"name": "id",        "type": "INT",          "is_primary_key": true},
        {"name": "name",      "type": "VARCHAR(255)"},
        {"name": "score",     "type": "INT"},
        {"name": "is_active", "type": "BOOLEAN"}
      ]
    }
  ]
}')

HTTP_CREATE=$(api POST /sessions -d '{
  "query_type": "mysql",
  "schema_context": [{"name": "contacts","fields": [{"name": "id","type": "INT","is_primary_key": true}]}]
}' -w "%{http_code}" -o /dev/null)

check_http "POST /sessions → 201" "$HTTP_CREATE" "201"
check_present "POST /sessions → session_id" "$CREATE" "session_id"
check_field   "POST /sessions → query_type" "$CREATE" "query_type" "mysql"

SESSION_ID=$(echo "$CREATE" | jq -r '.session_id')
info "Session: $SESSION_ID"

# GET session
GET_SESSION=$(api GET "/sessions/$SESSION_ID")
check_field "GET /sessions/{id} → session_id" "$GET_SESSION" "session_id" "$SESSION_ID"
check_field "GET /sessions/{id} → query_type" "$GET_SESSION" "query_type" "mysql"

# 404 for unknown session
HTTP_404=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: $API_KEY" "$API_URL/sessions/nonexistent-session-xyz")
check_http "GET /sessions/nonexistent → 404" "$HTTP_404" "404"

# History (empty)
HISTORY=$(api GET "/sessions/$SESSION_ID/history")
check_field "GET history → session_id" "$HISTORY" "session_id" "$SESSION_ID"
check_field "GET history → messages=[]" "$HISTORY" "messages | length" "0"

# ── 3. Validation checks ──────────────────────────────────────────────────────
section "3 · Input Validation"

HTTP_NO_SCHEMA=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  "$API_URL/sessions" -d '{"query_type":"mysql"}')
check_http "POST /sessions no schema → 422" "$HTTP_NO_SCHEMA" "422"

HTTP_EMPTY_MSG=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  "$API_URL/sessions/$SESSION_ID/chat" -d '{"message":""}')
check_http "POST /chat empty message → 422" "$HTTP_EMPTY_MSG" "422"

HTTP_BAD_TYPE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  "$API_URL/sessions" -d '{"query_type":"cobol","schema_context":[{"name":"t","fields":[]}]}')
check_http "POST /sessions bad query_type → 422" "$HTTP_BAD_TYPE" "422"

# ── 4. Standard chat (NL → query) ────────────────────────────────────────────
section "4 · Standard Chat (NL → Query)"

CHAT=$(api POST "/sessions/$SESSION_ID/chat" -d '{
  "message": "How many contacts have a score above 5?"
}')

check_present "POST /chat → content"     "$CHAT" "content"
check_present "POST /chat → query"       "$CHAT" "query"
check_field   "POST /chat → role"        "$CHAT" "role" "assistant"
QUERY=$(echo "$CHAT" | jq -r '.query // empty')
info "Generated query: $QUERY"

# Insight from external result
INSIGHT=$(api POST "/sessions/$SESSION_ID/chat" -d '{
  "message": "Explain these results",
  "query_result": [{"count": 42}],
  "generate_insight": true
}')
check_present "POST /chat with external result → content" "$INSIGHT" "content"

# ── 5. History after messages ──────────────────────────────────────────────────
section "5 · History After Messages"

HISTORY2=$(api GET "/sessions/$SESSION_ID/history")
MSG_COUNT=$(echo "$HISTORY2" | jq -r '.messages | length')
if [[ "$MSG_COUNT" -ge 2 ]]; then
  ok "History has $MSG_COUNT messages (≥ 2)"
else
  fail "History has $MSG_COUNT messages (expected ≥ 2)"
fi

# ── 6. Agent mode ─────────────────────────────────────────────────────────────
section "6 · Agent Mode"

# Create a fresh session for agent tests
AGENT_SESSION_RESP=$(api POST /sessions -d '{
  "query_type": "mysql",
  "schema_context": [
    {
      "name": "contacts",
      "fields": [
        {"name": "id",    "type": "INT", "is_primary_key": true},
        {"name": "name",  "type": "VARCHAR(255)"},
        {"name": "score", "type": "INT"}
      ]
    }
  ]
}')
AGENT_SESSION=$(echo "$AGENT_SESSION_RESP" | jq -r '.session_id')
info "Agent session: $AGENT_SESSION"

AGENT_RESP=$(api POST "/sessions/$AGENT_SESSION/chat" -d '{
  "message": "What tables do I have in my schema?",
  "agent_mode": true
}')

HTTP_AGENT=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  "$API_URL/sessions/$AGENT_SESSION/chat" \
  -d '{"message":"What tables do I have?","agent_mode":true}')
check_http "POST /chat agent_mode=true → 200" "$HTTP_AGENT" "200"
check_field "Agent response → role=assistant" "$AGENT_RESP" "role" "assistant"
check_present "Agent response → content" "$AGENT_RESP" "content"

# agent_reasoning should be a list
REASONING_TYPE=$(echo "$AGENT_RESP" | jq -r '.agent_reasoning | type' 2>/dev/null)
if [[ "$REASONING_TYPE" == "array" ]]; then
  ok "Agent response → agent_reasoning is array"
else
  fail "Agent response → agent_reasoning is $REASONING_TYPE (expected array)"
fi

# Agent 404 for missing session
HTTP_AGENT_404=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  "$API_URL/sessions/ghost-session/chat" \
  -d '{"message":"hello","agent_mode":true}')
check_http "Agent mode unknown session → 404" "$HTTP_AGENT_404" "404"

# ── 7. MCP server ─────────────────────────────────────────────────────────────
section "7 · MCP Server"

# FastMCP mounts at /mcp/ (trailing slash). /mcp redirects → /mcp/ (307).
# Follow the redirect with -L and accept 200/405 as "reachable".
HTTP_MCP=$(curl -sL -o /dev/null -w "%{http_code}" "$API_URL/mcp/")
if [[ "$HTTP_MCP" =~ ^(200|405|406)$ ]]; then
  ok "/mcp/ is reachable (HTTP $HTTP_MCP)"
else
  # Also accept 307 pointing to /mcp/ — server is up, just redirecting.
  HTTP_MCP_REDIR=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/mcp")
  if [[ "$HTTP_MCP_REDIR" == "307" ]]; then
    ok "/mcp redirects to /mcp/ (HTTP 307 → MCP server is mounted)"
  else
    fail "/mcp returned unexpected HTTP $HTTP_MCP_REDIR"
  fi
fi

# ── 8. Auth ────────────────────────────────────────────────────────────────────
section "8 · Authentication"

# In dev mode (API_KEYS=""), auth is bypassed → 200.
# When API_KEYS is set, missing key → 401.
HTTP_NO_KEY=$(curl -s -o /dev/null -w "%{http_code}" \
  -X GET "$API_URL/sessions/$AGENT_SESSION")
if [[ "$HTTP_NO_KEY" == "401" ]]; then
  ok "GET without key → 401 (API_KEYS configured)"
elif [[ "$HTTP_NO_KEY" == "200" ]]; then
  ok "GET without key → 200 (dev mode, API_KEYS empty)"
else
  fail "GET without key → unexpected HTTP $HTTP_NO_KEY"
fi

# ── 9. Session deletion ────────────────────────────────────────────────────────
section "9 · Session Deletion"

HTTP_DEL=$(curl -s -o /dev/null -w "%{http_code}" \
  -X DELETE -H "X-API-Key: $API_KEY" "$API_URL/sessions/$SESSION_ID")
check_http "DELETE /sessions/{id} → 204" "$HTTP_DEL" "204"

# Second delete should 404
HTTP_DEL2=$(curl -s -o /dev/null -w "%{http_code}" \
  -X DELETE -H "X-API-Key: $API_KEY" "$API_URL/sessions/$SESSION_ID")
check_http "DELETE already-deleted session → 404" "$HTTP_DEL2" "404"

# Confirm session is gone
HTTP_GONE=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "X-API-Key: $API_KEY" "$API_URL/sessions/$SESSION_ID")
check_http "GET deleted session → 404" "$HTTP_GONE" "404"

# ── 10. Rate limiter smoke test ────────────────────────────────────────────────
section "10 · Rate Limiter (smoke)"

# Fire 5 quick health checks — should all succeed (well within the 60/min default)
RATE_FAILS=0
for i in {1..5}; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health")
  if [[ "$CODE" != "200" ]]; then
    RATE_FAILS=$((RATE_FAILS + 1))
  fi
done
if [[ $RATE_FAILS -eq 0 ]]; then
  ok "5 rapid /health calls all returned 200"
else
  fail "$RATE_FAILS of 5 rapid /health calls failed"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════${RESET}"
TOTAL=$((PASS + FAIL))
if [[ $FAIL -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}  ALL $TOTAL TESTS PASSED${RESET}"
else
  echo -e "${RED}${BOLD}  $FAIL / $TOTAL TESTS FAILED${RESET}"
fi
echo -e "${BOLD}════════════════════════════════════════════${RESET}"

exit $FAIL
