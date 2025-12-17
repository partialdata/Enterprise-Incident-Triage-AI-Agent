from app.agent import IncidentTriageAgent
from app.llm import MockLLMClient
from app.models import IncidentTicket, Severity
from app.tools import HistoryTool, KnowledgeBaseTool


def build_agent():
    return IncidentTriageAgent(
        kb_tool=KnowledgeBaseTool(),
        history_tool=HistoryTool(),
        llm_client=MockLLMClient(),
    )


def test_p0_outage_severity():
    agent = build_agent()
    ticket = IncidentTicket(
        id="t-1",
        title="Global outage",
        description="The main API is unreachable causing full outage.",
        tags=["api", "outage"],
    )
    rec = agent.process(ticket)
    assert rec.severity == Severity.P0
    assert rec.confidence >= 0.9


def test_pii_redaction_and_escalation():
    agent = build_agent()
    ticket = IncidentTicket(
        id="t-2",
        title="User emailed credentials",
        description="Customer sent password to jane.doe@example.com phone 555-123-4567",
        tags=["credentials"],
    )
    rec = agent.process(ticket)
    assert rec.redacted is True
    assert "[REDACTED_EMAIL]" in rec.summary or "[REDACTED_PHONE]" in rec.summary
    assert isinstance(rec.recommended_actions, list)
