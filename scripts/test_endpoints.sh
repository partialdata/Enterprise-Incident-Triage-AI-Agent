#!/usr/bin/env sh
set -e

BASE_URL=${BASE_URL:-http://127.0.0.1:8000}

echo "Health check..."
curl -s "$BASE_URL/health" | jq .

echo "\nSingle triage..."
curl -s -X POST "$BASE_URL/triage" \
  -H "Content-Type: application/json" \
  -d '{
        "id": "ticket-1",
        "title": "Database latency alert",
        "description": "Primary DB showing elevated latency after deploy",
        "tags": ["db","latency"]
      }' | jq .

echo "\nBatch triage..."
curl -s -X POST "$BASE_URL/triage/batch" \
  -H "Content-Type: application/json" \
  -d '[{
        "id": "t1",
        "title": "VPN latency",
        "description": "Users report slow VPN connections after hours",
        "tags": ["vpn","latency"]
      }]' | jq .

echo "\nFile triage (uses repo data/sample_ticket.json)..."
curl -s -X POST "$BASE_URL/triage/file" \
  -H "Content-Type: application/json" \
  -d '{"path": "data/sample_ticket.json"}' | jq .
