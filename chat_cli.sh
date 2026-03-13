#!/usr/bin/env bash
# =============================================================================
#  support-chat  —  Interactive CLI chatbot
#
#  Usage:
#    ./chat_cli.sh [--url URL] [--key API_KEY] [--type QUERY_TYPE] [--db DB_URL]
#
#  Flags (all optional, values can also be set interactively):
#    --url   Base URL of the API      (default: http://localhost:8000)
#    --key   X-API-Key header value   (default: empty — dev mode)
#    --type  Query dialect to use     (default: mysql)
#    --db    Database connection URL  (default: empty — query-only mode)
#
#  In-chat commands (prefix with !):
#    !help       Show available commands
#    !exec       Toggle auto-execution of generated queries (needs db_url)
#    !insight    Toggle natural-language insight generation
#    !history    Print full conversation history for the current session
#    !new        End current session and start a fresh one
#    !quit / !exit  Exit gracefully (session is deleted)
# =============================================================================

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
#  Colour helpers
# ─────────────────────────────────────────────────────────────────────────────

BOLD=$'\033[1m'
DIM=$'\033[2m'
RESET=$'\033[0m'
CYAN=$'\033[0;36m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
RED=$'\033[0;31m'
MAGENTA=$'\033[0;35m'
BLUE=$'\033[0;34m'

# ─────────────────────────────────────────────────────────────────────────────
#  JSON helpers — Python handles ALL serialisation so special chars are safe
# ─────────────────────────────────────────────────────────────────────────────

# Extract a top-level key's value from a JSON string (empty string if missing/null)
json_get() {
    local key="$1" json="$2"
    printf '%s' "$json" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); v=d.get('$key'); print('' if v is None else v)" \
        2>/dev/null
}

# Pretty-print JSON
json_pretty() {
    printf '%s' "$1" | python3 -m json.tool 2>/dev/null || printf '%s\n' "$1"
}

# Return a JSON-encoded string (with surrounding quotes) for a bash variable
json_str() {
    python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" <<< "$1"
}

# ─────────────────────────────────────────────────────────────────────────────
#  Defaults & argument parsing
# ─────────────────────────────────────────────────────────────────────────────

API_URL="http://localhost:8000"
API_KEY=""
QUERY_TYPE="mysql"
DB_URL=""
EXECUTE_QUERY=false
GENERATE_INSIGHT=false
SESSION_ID=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)   API_URL="$2";    shift 2 ;;
        --key)   API_KEY="$2";    shift 2 ;;
        --type)  QUERY_TYPE="$2"; shift 2 ;;
        --db)    DB_URL="$2";     shift 2 ;;
        *) printf "${RED}Unknown option: %s${RESET}\n" "$1"; exit 1 ;;
    esac
done

# ─────────────────────────────────────────────────────────────────────────────
#  curl wrapper — adds auth header only when API_KEY is set
# ─────────────────────────────────────────────────────────────────────────────

_curl() {
    if [[ -n "$API_KEY" ]]; then
        curl -s -H "X-API-Key: $API_KEY" "$@"
    else
        curl -s "$@"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
#  Cleanup on EXIT / Ctrl-C
# ─────────────────────────────────────────────────────────────────────────────

_cleanup() {
    printf "\n"
    if [[ -n "$SESSION_ID" ]]; then
        printf "${DIM}Ending session %s …${RESET}\n" "$SESSION_ID"
        _curl -X DELETE "$API_URL/sessions/$SESSION_ID" > /dev/null 2>&1 || true
        printf "${DIM}Session closed.${RESET}\n"
    fi
    printf "${CYAN}Goodbye!${RESET}\n"
    exit 0
}
trap _cleanup INT TERM EXIT

# ─────────────────────────────────────────────────────────────────────────────
#  Banner
# ─────────────────────────────────────────────────────────────────────────────

clear

echo -e "${CYAN}"
figlet -f slant -c "Support Chat"
echo -e "${RESET}"

printf "${CYAN}${BOLD}  Natural-language → data query assistant${RESET}\n"
printf "${DIM}  Type your question in plain English. Use !help for commands.\n${RESET}\n"

# ─────────────────────────────────────────────────────────────────────────────
#  Health check
# ─────────────────────────────────────────────────────────────────────────────

printf "${DIM}Connecting to %s …${RESET} " "$API_URL"
health=$(_curl "$API_URL/health" 2>/dev/null) || true
if [[ -z "$health" ]]; then
    printf "${RED}FAILED${RESET}\n"
    printf "${RED}Error:${RESET} Could not reach the API at %s\n" "$API_URL"
    printf "Start it with:  ${BOLD}uvicorn app.main:app --reload${RESET}\n"
    exit 1
fi
printf "${GREEN}OK${RESET}\n\n"

# ─────────────────────────────────────────────────────────────────────────────
#  Schema collection
#
#  All user inputs are stored in plain bash variables/arrays.
#  Nothing touches JSON at this stage — Python serialises everything later.
# ─────────────────────────────────────────────────────────────────────────────

declare -a _tnames=()
declare -a _tdescs=()
# _tfields[t] = newline-separated lines, each line is tab-delimited: name\ttype\tis_pk
declare -a _tfields=()

_collect_schema() {
    printf "${BOLD}${CYAN}── Session Setup ──────────────────────────────────────────${RESET}\n"

    # Query type
    printf "Query type ${DIM}[mysql/postgresql/sqlite/mongodb/pandas]${RESET} (${BOLD}%s${RESET}): " "$QUERY_TYPE"
    read -r _in || _in=""
    [[ -n "$_in" ]] && QUERY_TYPE="$_in"

    # DB URL (optional)
    printf "DB connection URL ${DIM}(leave blank for query-only mode)${RESET}: "
    read -r _in || _in=""
    [[ -n "$_in" ]] && DB_URL="$_in"

    # System instructions
    printf "Extra system instructions ${DIM}(optional, Enter to skip)${RESET}: "
    read -r SYSTEM_INSTRUCTIONS || SYSTEM_INSTRUCTIONS=""

    # Number of tables
    printf "\n${BOLD}Define your schema tables${RESET} ${DIM}(enter 0 to load the demo schema)${RESET}\n"
    printf "Number of tables: "
    read -r num_tables || num_tables="0"

    _tnames=(); _tdescs=(); _tfields=()

    if [[ -z "$num_tables" || "$num_tables" == "0" ]]; then
        # Demo schema
        _tnames=("contacts")
        _tdescs=("Stores customer contact records")
        _tfields=("idINTtrue
nameVARCHAR(255)false
emailVARCHAR(255)false
scoreINTfalse
is_activeBOOLEANfalse
created_atDATETIMEfalse")
        printf "${DIM}Using demo schema: contacts table.${RESET}\n"
        return
    fi

    local t
    for ((t = 0; t < num_tables; t++)); do
        printf "\n${BOLD}Table %d${RESET}\n" "$((t + 1))"
        printf "  Name: "; read -r _tnames[$t] || _tnames[$t]=""
        printf "  Description (optional): "; read -r _tdescs[$t] || _tdescs[$t]=""

        printf "  Number of fields: "; read -r num_fields || num_fields="0"

        local field_lines=""
        local f
        for ((f = 0; f < num_fields; f++)); do
            printf "  Field %d  name : " "$((f + 1))"; read -r _fname  || _fname=""
            printf "  Field %d  type : " "$((f + 1))"; read -r _ftype  || _ftype=""
            printf "  Field %d  primary key? [y/N]: " "$((f + 1))"; read -r _fpk || _fpk=""
            local _is_pk="false"
            [[ "$_fpk" =~ ^[Yy]$ ]] && _is_pk="true"
            # tab-delimited record
            local record="${_fname}${_ftype}${_is_pk}"
            if [[ -z "$field_lines" ]]; then
                field_lines="$record"
            else
                field_lines="${field_lines}
${record}"
            fi
        done
        _tfields[$t]="$field_lines"
    done
}

# ─────────────────────────────────────────────────────────────────────────────
#  Build the complete session-creation JSON payload in Python.
#  json.dumps() is used for every user-supplied string, so enum(...) types,
#  apostrophes, backslashes, and any other special character are handled safely.
# ─────────────────────────────────────────────────────────────────────────────

_build_session_payload() {
    # Serialise all collected inputs into a small TSV-like text stream that
    # Python reads from stdin, then builds the JSON structure.
    local stream=""

    local t
    for ((t = 0; t < ${#_tnames[@]}; t++)); do
        stream+="TABLE${_tnames[$t]}${_tdescs[$t]:-}"$'\n'
        if [[ -n "${_tfields[$t]:-}" ]]; then
            while IFS= read -r record; do
                [[ -z "$record" ]] && continue
                stream+="FIELD${record}"$'\n'
            done <<< "${_tfields[$t]}"
        fi
    done

    python3 - \
        "$QUERY_TYPE" \
        "$DB_URL" \
        "${SYSTEM_INSTRUCTIONS:-}" \
        <<< "$stream" <<'PYEOF'
import sys, json

args      = sys.argv[1:]
query_type   = args[0]
db_url       = args[1]
system_instr = args[2]
stream       = sys.stdin.read()

schema = []
current_table = None

for line in stream.splitlines():
    if not line:
        continue
    parts = line.split('\t')
    marker = parts[0]
    if marker == 'TABLE':
        tname = parts[1] if len(parts) > 1 else ''
        tdesc = parts[2] if len(parts) > 2 else ''
        current_table = {'name': tname, 'fields': []}
        if tdesc:
            current_table['description'] = tdesc
        schema.append(current_table)
    elif marker == 'FIELD' and current_table is not None:
        fname  = parts[1] if len(parts) > 1 else ''
        ftype  = parts[2] if len(parts) > 2 else ''
        is_pk  = (parts[3].strip().lower() == 'true') if len(parts) > 3 else False
        current_table['fields'].append({
            'name': fname,
            'type': ftype,
            'is_primary_key': is_pk,
        })

payload = {
    'query_type': query_type,
    'schema_context': schema,
    'db_url': db_url if db_url else None,
    'system_instructions': system_instr if system_instr else None,
}
print(json.dumps(payload))
PYEOF
}

# ─────────────────────────────────────────────────────────────────────────────
#  Session creation
# ─────────────────────────────────────────────────────────────────────────────

_create_session() {
    _collect_schema

    printf "\n${DIM}Creating session …${RESET}\n"

    local payload
    payload=$(_build_session_payload)

    if [[ "${DEBUG_CLI:-}" == "1" ]]; then
        printf "${DIM}DEBUG payload:\n%s\n${RESET}" "$(json_pretty "$payload")"
    fi

    local resp http_code
    resp=$(_curl -w '\n%{http_code}' -X POST "$API_URL/sessions" \
        -H "Content-Type: application/json" \
        -d "$payload")

    http_code=$(printf '%s' "$resp" | tail -n1)
    resp=$(printf '%s' "$resp" | head -n -1)

    if [[ "$http_code" != "201" ]]; then
        printf "${RED}Failed to create session (HTTP %s).${RESET}\n" "$http_code"
        printf "${DIM}Server response:${RESET}\n"
        json_pretty "$resp" | sed 's/^/  /'
        printf "\n${DIM}Tip: re-run with  DEBUG_CLI=1 ./chat_cli.sh  to inspect the payload sent.${RESET}\n"
        exit 1
    fi

    SESSION_ID=$(json_get "session_id" "$resp")
    local has_db
    has_db=$(json_get "has_db_connection" "$resp")

    if [[ -z "$SESSION_ID" ]]; then
        printf "${RED}Error: could not parse session_id from response.${RESET}\n"
        json_pretty "$resp" | sed 's/^/  /'
        exit 1
    fi

    printf "${GREEN}✓ Session started${RESET}  ${DIM}id=%s  type=%s  db=%s${RESET}\n\n" \
        "$SESSION_ID" "$QUERY_TYPE" "$has_db"

    if [[ "$has_db" == "True" || "$has_db" == "true" ]]; then
        EXECUTE_QUERY=true
        GENERATE_INSIGHT=true
        printf "${DIM}  Auto-enabled: query execution + insight generation (DB connected).${RESET}\n\n"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
#  Send a chat message
# ─────────────────────────────────────────────────────────────────────────────

_send_message() {
    local message="$1"

    local payload
    payload=$(python3 -c "
import sys, json
msg = sys.stdin.read()
print(json.dumps({
    'message': msg,
    'execute_query': $([ "$EXECUTE_QUERY" = "true" ] && echo 'True' || echo 'False'),
    'generate_insight': $([ "$GENERATE_INSIGHT" = "true" ] && echo 'True' || echo 'False'),
}))
" <<< "$message")

    local resp http_code
    resp=$(_curl -w '\n%{http_code}' -X POST "$API_URL/sessions/$SESSION_ID/chat" \
        -H "Content-Type: application/json" \
        -d "$payload")

    http_code=$(printf '%s' "$resp" | tail -n1)
    resp=$(printf '%s' "$resp" | head -n -1)

    # Clear the "Thinking …" line
    printf "\r\033[K"

    if [[ "$http_code" != "200" ]]; then
        printf "${RED}⚠  Request failed (HTTP %s).${RESET}\n" "$http_code"
        json_pretty "$resp" | sed 's/^/  /'
        return
    fi

    local content query query_result insight
    content=$(json_get "content" "$resp")
    query=$(json_get "query" "$resp")
    query_result=$(json_get "query_result" "$resp")
    insight=$(json_get "insight" "$resp")

    printf "\n"

    # Generated query
    if [[ -n "$query" && "$query" != "None" ]]; then
        printf "${BOLD}${YELLOW}Generated Query:${RESET}\n"
        printf "${YELLOW}┌─────────────────────────────────────────────────────────────┐${RESET}\n"
        while IFS= read -r line; do
            printf "${YELLOW}│${RESET}  %s\n" "$line"
        done <<< "$query"
        printf "${YELLOW}└─────────────────────────────────────────────────────────────┘${RESET}\n\n"
    fi

    # Query result
    if [[ -n "$query_result" && "$query_result" != "None" && "$query_result" != "null" ]]; then
        printf "${BOLD}${BLUE}Query Result:${RESET}\n"
        json_pretty "$query_result" | sed 's/^/  /'
        printf "\n"
    fi

    # Insight or answer
    if [[ -n "$insight" && "$insight" != "None" ]]; then
        printf "${BOLD}${GREEN}💡 Insight:${RESET}\n"
        printf '%s\n\n' "$insight" | fold -s -w 80 | sed 's/^/  /'
    elif [[ -n "$content" ]]; then
        printf "${BOLD}${GREEN}Assistant:${RESET}\n"
        printf '%s\n\n' "$content" | fold -s -w 80 | sed 's/^/  /'
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
#  Show conversation history
# ─────────────────────────────────────────────────────────────────────────────

_show_history() {
    local resp http_code
    resp=$(_curl -w '\n%{http_code}' "$API_URL/sessions/$SESSION_ID/history")
    http_code=$(printf '%s' "$resp" | tail -n1)
    resp=$(printf '%s' "$resp" | head -n -1)

    if [[ "$http_code" != "200" ]]; then
        printf "${RED}Could not fetch history (HTTP %s).${RESET}\n" "$http_code"; return
    fi

    printf "\n${BOLD}${CYAN}── Conversation History ────────────────────────────────────${RESET}\n"
    python3 -c "
import sys, json, textwrap
data = json.load(sys.stdin)
for m in data.get('messages', []):
    role    = m.get('role', '')
    content = m.get('content', '')
    query   = m.get('query') or ''
    if role == 'user':
        print(f'\n\033[1;36mYou:\033[0m {content}')
    else:
        print('\n\033[1;32mAssistant:\033[0m')
        for line in textwrap.wrap(content, 76):
            print(f'  {line}')
        if query:
            print(f'\033[33mQuery:\033[0m {query}')
" <<< "$resp"
    printf "\n${CYAN}─────────────────────────────────────────────────────────────${RESET}\n\n"
}

# ─────────────────────────────────────────────────────────────────────────────
#  Help
# ─────────────────────────────────────────────────────────────────────────────

_show_help() {
    printf "\n${BOLD}Commands:${RESET}\n"
    printf "  ${CYAN}!help${RESET}       Show this help\n"
    printf "  ${CYAN}!exec${RESET}       Toggle query auto-execution    ${DIM}(now: %s)${RESET}\n" "$EXECUTE_QUERY"
    printf "  ${CYAN}!insight${RESET}    Toggle LLM insight generation  ${DIM}(now: %s)${RESET}\n" "$GENERATE_INSIGHT"
    printf "  ${CYAN}!history${RESET}    Print full conversation history\n"
    printf "  ${CYAN}!new${RESET}        Start a new session\n"
    printf "  ${CYAN}!quit${RESET}       Exit\n"
    printf "\n"
}

# ─────────────────────────────────────────────────────────────────────────────
#  Chat loop
# ─────────────────────────────────────────────────────────────────────────────

_chat_loop() {
    local input
    while true; do
        printf "${BOLD}${MAGENTA}You${RESET}${DIM}(%s)${RESET}" "$QUERY_TYPE"
        $EXECUTE_QUERY    && printf "${DIM}[exec]${RESET}"
        $GENERATE_INSIGHT && printf "${DIM}[insight]${RESET}"
        printf "\n${BOLD}${MAGENTA}▶${RESET} "

        if ! IFS= read -r input; then break; fi

        # Trim whitespace
        input="${input#"${input%%[![:space:]]*}"}"
        input="${input%"${input##*[![:space:]]}"}"
        [[ -z "$input" ]] && continue

        case "$input" in
            !quit|!exit) break ;;
            !help)    _show_help ;;
            !history) _show_history ;;
            !exec)
                if $EXECUTE_QUERY; then
                    EXECUTE_QUERY=false;  printf "${DIM}Query execution: OFF${RESET}\n"
                else
                    EXECUTE_QUERY=true;   printf "${DIM}Query execution: ON${RESET}\n"
                fi ;;
            !insight)
                if $GENERATE_INSIGHT; then
                    GENERATE_INSIGHT=false; printf "${DIM}Insight generation: OFF${RESET}\n"
                else
                    GENERATE_INSIGHT=true;  printf "${DIM}Insight generation: ON${RESET}\n"
                fi ;;
            !new)
                printf "${DIM}Ending session %s …${RESET}\n" "$SESSION_ID"
                _curl -X DELETE "$API_URL/sessions/$SESSION_ID" > /dev/null 2>&1 || true
                SESSION_ID=""
                printf "\n"
                _create_session ;;
            !*)
                printf "${RED}Unknown command '%s'. Type !help.${RESET}\n" "$input" ;;
            *)
                printf "${DIM}Thinking …${RESET}"
                _send_message "$input" ;;
        esac
    done
}

# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

_create_session
_show_help
_chat_loop