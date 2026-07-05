#!/bin/bash
set -e

echo "Waiting for LangGraph API to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "LangGraph API is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "Timeout waiting for LangGraph API"
        exit 1
    fi
    sleep 2
done

echo "Creating assistant 'agent'..."

# Try to create the assistant
RESPONSE=$(curl -s -X POST "http://localhost:8000/assistants" \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "agent",
    "graph_id": "agent",
    "config": {},
    "metadata": {"created_by": "system"}
  }' 2>&1)

echo "Response: $RESPONSE"

if echo "$RESPONSE" | grep -q "not_found\|error\|Error"; then
    echo "Graph may need to be registered first, trying alternative approach..."

    # Check if graph exists
    GRAPHS=$(curl -s http://localhost:8000/graphs 2>&1)
    echo "Available graphs: $GRAPHS"
fi

echo "Assistant registration complete!"
echo "Starting LangGraph API server..."