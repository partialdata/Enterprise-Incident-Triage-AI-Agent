import json
import logging
import re
from typing import List, Tuple

from .config import get_settings
from .llm import LLMClient, build_llm_client
from .logging_utils import log_extra
from .models import AgentRecommendation, IncidentTicket, Severity
from .tools import HistoryTool, KnowledgeBaseTool

logger = logging.getLogger(__name__)


def _detect_pii(text: str) -> bool:
    email_pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    phone_pattern = r"(\+?\d{1,2}[\s-]?)?(\(\d{3}\)|\d{3})[\s-]?\d{3}[\s-]?\d{4}"
    return bool(re.search(email_pattern, text) or re.search(phone_pattern, text))


def _redact(text: str) -> str:
    text = re.sub(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", text
    )
    text = re.sub(
        r"(\+?\d{1,2}[\s-]?)?(\(\d{3}\)|\d{3})[\s-]?\d{3}[\s-]?\d{4}",
        "[REDACTED_PHONE]",
        text,
    )
    return text


def _score_severity(title: str, description: str, tags: List[str]) -> Tuple[Severity, float, str]:
    text = f"{title.lower()} {description.lower()} {' '.join(tags).lower()}"
    score = 0.5
    rationale_parts = []

    critical_keywords = ["outage", "down", "unreachable", "ransomware", "breach"]
    high_keywords = ["degraded", "latency", "data loss", "panic", "ddos"]
    medium_keywords = ["bug", "error", "failed job", "retry", "warning", "timeout"]
    low_keywords = ["request", "question"]
    info_keywords = ["informational", "notice"]

    if any(k in text for k in critical_keywords):
        score = 0.9
        severity = Severity.P0
        rationale_parts.append("critical keyword detected")
    elif any(k in text for k in high_keywords):
        score = 0.8
        severity = Severity.P1
        rationale_parts.append("high keyword detected")
    elif any(k in text for k in medium_keywords):
        score = 0.7
        severity = Severity.P2
        rationale_parts.append("medium keyword detected")
    elif any(k in text for k in low_keywords):
        score = 0.55
        severity = Severity.P3
        rationale_parts.append("request/question keyword detected")
    elif any(k in text for k in info_keywords):
        score = 0.35
        severity = Severity.P4
        rationale_parts.append("informational keyword detected")
    else:
        score = 0.45
        severity = Severity.P4
        rationale_parts.append("no strong signals")

    if "p0" in text:
        severity = Severity.P0
        score = max(score, 0.92)
        rationale_parts.append("explicit severity tag")

    return severity, score, "; ".join(rationale_parts)


def _summarize_text(text: str) -> str:
    description = text.strip().replace("\\n", " ")
    summary = description[:240]
    if len(description) > 240:
        summary += "..."
    return summary


def _recommend_actions(severity: Severity, has_pii: bool) -> List[str]:
    actions = []
    if severity in {Severity.P0, Severity.P1}:
        actions.append("Page on-call responder")
        actions.append("Create war room channel")
    if severity in {Severity.P0, Severity.P1, Severity.P2}:
        actions.append("Collect logs and metrics")
    if severity in {Severity.P3, Severity.P4}:
        actions.append("Schedule follow-up within 24h")
    if has_pii:
        actions.append("Apply PII handling protocol")
    actions.append("Update ticket with findings")
    return actions


class IncidentTriageAgent:
    def __init__(self, kb_tool: KnowledgeBaseTool, history_tool: HistoryTool, llm_client: LLMClient | None = None):
        self.kb_tool = kb_tool
        self.history_tool = history_tool
        self.settings = get_settings()
        self.llm = llm_client or build_llm_client()

    def _build_prompt(
        self,
        ticket: IncidentTicket,
        severity: Severity,
        knowledge_refs: List[str],
        history_refs: List[str],
        fallback_summary: str,
        fallback_actions: List[str],
        fallback_rationale: str,
    ) -> str:
        return f"""
You are an incident triage assistant. Produce a concise JSON response that strictly matches the schema.
Fields:
- summary: short summary (<=240 chars)
- recommended_actions: ordered list of concrete next steps
- rationale: brief reasoning for severity and actions
Context:
- ticket_id: {ticket.id}
- severity: {severity.value}
- tags: {', '.join(ticket.tags)}
- knowledge_refs: {', '.join(knowledge_refs) or 'none'}
- history_refs: {', '.join(history_refs) or 'none'}

Return JSON only. Use this template between markers:
<<JSON>>
{{
  "summary": "{fallback_summary}",
  "recommended_actions": {json.dumps(fallback_actions)},
  "rationale": "{fallback_rationale}"
}}
<</JSON>>
"""

    def process(self, ticket: IncidentTicket) -> AgentRecommendation:
        logger.info(
            "processing_ticket",
            extra=log_extra(
                ticket_id=ticket.id,
                source=ticket.source,
                service=self.settings.service_name,
            ),
        )

        has_pii = _detect_pii(ticket.description)
        redacted = False
        description = ticket.description
        if has_pii and self.settings.redact_pii:
            description = _redact(description)
            redacted = True

        severity, confidence, rationale = _score_severity(ticket.title, description, ticket.tags)
        knowledge_refs = self.kb_tool.search(description)
        history_refs = self.history_tool.search(description)

        if knowledge_refs:
            confidence += 0.05
            rationale += "; matched knowledge base"
        if history_refs:
            confidence += 0.05
            rationale += "; similar historical incident"

        confidence = min(confidence, 0.98)
        escalation_required = confidence < self.settings.confidence_threshold
        summary_source = description if redacted else ticket.description
        fallback_summary = _summarize_text(summary_source)
        fallback_actions = _recommend_actions(severity, has_pii)

        prompt = self._build_prompt(
            ticket=ticket,
            severity=severity,
            knowledge_refs=knowledge_refs,
            history_refs=history_refs,
            fallback_summary=fallback_summary,
            fallback_actions=fallback_actions,
            fallback_rationale=rationale,
        )

        try:
            llm_resp = self.llm.generate(prompt, max_tokens=self.settings.max_tokens)
            llm_payload = json.loads(llm_resp.content)
            logger.info(
                "llm_completed",
                extra=log_extra(
                    ticket_id=ticket.id,
                    cost_usd=round(llm_resp.cost_usd, 6),
                    prompt_tokens=llm_resp.prompt_tokens,
                    completion_tokens=llm_resp.completion_tokens,
                ),
            )
        except Exception as exc:
            logger.warning(
                "llm_failure_fallback",
                extra=log_extra(ticket_id=ticket.id, error=str(exc)),
            )
            llm_payload = {}
            llm_resp = None  # type: ignore[assignment]

        summary = llm_payload.get("summary", fallback_summary)
        actions = llm_payload.get("recommended_actions", fallback_actions)
        rationale_text = llm_payload.get("rationale", rationale)

        recommendation = AgentRecommendation(
            summary=summary,
            severity=severity,
            recommended_actions=actions,
            confidence=round(confidence, 3),
            escalation_required=escalation_required,
            rationale=rationale_text,
            redacted=redacted,
            knowledge_refs=knowledge_refs,
            history_refs=history_refs,
        )

        logger.info(
            "triage_decision",
            extra=log_extra(
                ticket_id=ticket.id,
                severity=recommendation.severity.value,
                confidence=recommendation.confidence,
                escalation=recommendation.escalation_required,
                redacted=recommendation.redacted,
            ),
        )

        return recommendation
