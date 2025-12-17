# Enterprise Incident Triage AI Agent

Production-style MVP for an AI agent that triages IT/security incidents with structured severity classification, summarization, and governance controls.

## What this solves

Large enterprises get flooded with incident tickets. Manual triage is slow and inconsistent, delaying response and increasing risk. This service automates triage: it classifies severity (P0–P4), summarizes, recommends next steps, and flags low-confidence cases for human review, with PII redaction and audit-friendly logging.

## How it works

- FastAPI service (`/triage`, `/triage/batch`, `/triage/file`, `/health`)
- Deterministic severity scoring with boosts from mock knowledge base/history tools
- PII detection and redaction before processing
- Confidence scoring with escalation when below threshold
- Pluggable LLM client (mock by default) for summaries/actions/rationale with JSON-schema prompting and cost/tokens logging
- Structured outputs via Pydantic; request-scoped structured logging
- Evaluation harness with labeled cases and unit tests

## What this demonstrates

- Builder mindset: designed and shipped a runnable agent service with clear interfaces (LLM, tools), Dockerization, and helper scripts.
- Governance: PII redaction, confidence thresholds with human-in-loop escalation, structured outputs, request-scoped logging.
- Evaluation-first: labeled cases with an accuracy harness plus unit tests to catch regressions.
- Operationalization: env-driven config, container image, health endpoint, and curl test script for quick smoke checks.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs on `http://127.0.0.1:8000`. Health check: `GET /health`.

## API Usage

`POST /triage`
```json
{
  "id": "ticket-1",
  "title": "Database latency alert",
  "description": "Primary database showing elevated latency after deploy",
  "tags": ["db", "latency"]
}
```

`POST /triage/batch` accepts a list of the same payload.  
`POST /triage/file` accepts `{"path": "path/to/local_ticket.json"}` for local JSON files. In both local and Docker runs, `data/sample_ticket.json` is available inside the service image.

## Behavior

- Severity classification (P0–P4) via deterministic rules + signals from mock knowledge base/history tools.
- PII detection & redaction (email/phone) when `REDACT_PII=true` (summary uses redacted text).
- Confidence scoring with human escalation when below `CONFIDENCE_THRESHOLD` (default 0.65) and request-scoped structured logging.
- LLM client abstraction (mock by default) with JSON schema enforcement and cost logging hooks.
- Structured responses validated via Pydantic models.

## Configuration

Environment variables:
- `LLM_PROVIDER` (default `mock`)
- `LLM_MODEL` (default `mock-001`)
- `MAX_TOKENS` (default `512`)
- `COST_PER_1K_TOKENS` (default `0.0` for offline mock)
- `CONFIDENCE_THRESHOLD` (default `0.65`)
- `REDACT_PII` (`true`/`false`, default `true`)
- `KNOWLEDGE_BASE_PATH`, `HISTORY_PATH`, `EVAL_CASES_PATH` (override data files)

## Evaluation

Run the labeled set:
```bash
python scripts/evaluate.py
```
Update `data/eval_cases.json` with new cases to expand coverage.

## Tests

```bash
pytest
```

## Docker

```bash
docker build -t incident-triage:local .
docker run -p 8000:8000 incident-triage:local
```

## Project Layout

- `app/main.py` — FastAPI service entrypoint
- `app/agent.py` — Triage logic, governance (PII redaction, escalation)
- `app/tools.py` — Mock knowledge base and history lookup tools
- `app/models.py` — Pydantic schemas for requests/responses/evaluation
- `app/config.py` — Environment-driven settings
- `data/` — Mock KB, history, evaluation cases
- `scripts/evaluate.py` — Severity accuracy runner
- `scripts/docker.sh` — Build/run/stop container
- `scripts/test_endpoints.sh` — Curl-based smoke tests

## Architecture (text diagram)

```
Clients (curl/script) 
   ↓ HTTP
FastAPI service (app/main.py)
   ↓
IncidentTriageAgent (app/agent.py)
   ├─ Severity/PII governance (redaction, confidence, escalation)
   ├─ LLM client (app/llm.py) for summary/actions/rationale (mock pluggable)
   ├─ Knowledge base tool (app/tools.py → data/knowledge_base.json)
   ├─ History tool (app/tools.py → data/history.json)
   └─ Structured logging + request IDs (app/logging_utils.py)
   ↓
Response: summary, severity, actions, confidence, escalation flag, refs, redaction status
```

## Notes

- No external model calls are required; deterministic rules satisfy the MVP and can be swapped with an API-based LLM client later.
- Keep secrets out of source control; configure via environment variables or secret management in production.
