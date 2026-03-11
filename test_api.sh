#!/bin/bash

# Configuration
API_URL="http://127.0.0.1:8000"
API_KEY="test-key"

echo "================================================="
echo "🧪 Testing Support-Chat API Flow"
echo "================================================="

# 1. Check health
echo -e "\n[1/6] Checking API Health..."
curl -s -X GET "$API_URL/health" | jq || echo "Error: API not running. Please start it with 'uvicorn app.main:app'."

# 2. Create a session
echo -e "\n[2/6] Creating a new session..."
CREATE_RESPONSE=$(curl -s -X POST "$API_URL/sessions" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
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
  }')

echo "$CREATE_RESPONSE" | jq
SESSION_ID=$(echo "$CREATE_RESPONSE" | jq -r '.session_id')

if [ "$SESSION_ID" == "null" ] || [ -z "$SESSION_ID" ]; then
    echo "❌ Failed to create session."
    exit 1
fi
echo "✅ Session created: $SESSION_ID"

# 3. Ask a question (NL to Query)
echo -e "\n[3/6] Asking a question..."
CHAT_RESPONSE=$(curl -s -X POST "$API_URL/sessions/$SESSION_ID/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "message": "How many active users signed up this year?"
  }')

echo "$CHAT_RESPONSE" | jq
QUERY=$(echo "$CHAT_RESPONSE" | jq -r '.query')
echo "🔍 Generated Query: $QUERY"

# 4. Provide simulated query results for insight generation
echo -e "\n[4/6] Providing external results for an insight summary..."
INSIGHT_RESPONSE=$(curl -s -X POST "$API_URL/sessions/$SESSION_ID/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "message": "Explain these results to me",
    "query_result": [{"count": 1250}],
    "generate_insight": true
  }')

echo "$INSIGHT_RESPONSE" | jq
INSIGHT=$(echo "$INSIGHT_RESPONSE" | jq -r '.insight')
echo "💡 Generated Insight: $INSIGHT"

# 5. Get conversation history
echo -e "\n[5/6] Retrieving session history..."
HISTORY_RESPONSE=$(curl -s -X GET "$API_URL/sessions/$SESSION_ID/history" \
  -H "X-API-Key: $API_KEY")

echo "$HISTORY_RESPONSE" | jq

# 6. Delete the session
echo -e "\n[6/6] Deleting session..."
DELETE_RESPONSE=$(curl -s -X DELETE "$API_URL/sessions/$SESSION_ID" \
  -H "X-API-Key: $API_KEY" \
  -w "%{http_code}")

if [ "$DELETE_RESPONSE" == "204" ]; then
    echo "✅ Session $SESSION_ID deleted."
else
    echo "❌ Failed to delete session (HTTP $DELETE_RESPONSE)."
fi

echo -e "\n🎉 Test Script Completed!"
