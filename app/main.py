import json
import logging
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .agent import IncidentTriageAgent
from .config import get_settings
from .logging_utils import configure_logging, log_extra, set_request_id
from .models import FileTriageRequest, IncidentResponse, IncidentTicket
from .tools import HistoryTool, KnowledgeBaseTool

configure_logging()
logger = logging.getLogger(__name__)

settings = get_settings()
kb_tool = KnowledgeBaseTool()
history_tool = HistoryTool()
agent = IncidentTriageAgent(kb_tool, history_tool)
app = FastAPI(title="Enterprise Incident Triage AI Agent", version="0.1.0")


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or set_request_id()
    set_request_id(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}


@app.post("/triage", response_model=IncidentResponse)
def triage(ticket: IncidentTicket):
    recommendation = agent.process(ticket)
    return IncidentResponse(ticket=ticket, recommendation=recommendation)


@app.post("/triage/batch", response_model=List[IncidentResponse])
def triage_batch(tickets: List[IncidentTicket]):
    responses: List[IncidentResponse] = []
    for ticket in tickets:
        recommendation = agent.process(ticket)
        responses.append(IncidentResponse(ticket=ticket, recommendation=recommendation))
    return responses


@app.post("/triage/file", response_model=IncidentResponse)
def triage_file(request: FileTriageRequest):
    file_path = Path(request.path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    with open(file_path, "r") as f:
        payload = json.load(f)
    try:
        ticket = IncidentTicket(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid ticket: {exc}") from exc
    recommendation = agent.process(ticket)
    return IncidentResponse(ticket=ticket, recommendation=recommendation)


@app.exception_handler(Exception)
def unhandled_exception_handler(request, exc):
    logger.exception("unhandled_exception", extra=log_extra(path=str(request.url)))
    return JSONResponse(status_code=500, content={"detail": "internal_error"})
