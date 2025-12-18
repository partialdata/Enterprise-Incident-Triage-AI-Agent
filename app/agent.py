import json
import logging
import re
from typing import Any, List, Tuple

from .config import get_settings
from .llm import LLMClient, build_llm_client
from .logging_utils import log_extra
from .models import AgentRecommendation, IncidentTicket, Severity
from .tracing import AgentTracer, NullTracer
from .tools import HistoryTool, KnowledgeBaseTool

logger = logging.getLogger(__name__)
PROMPT_VERSION = "v1.1"


def _detect_pii(text: str) -> bool:
    email_pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    phone_pattern = r"(\+?\d{1,2}[\s\-.]?)?(\(\d{3}\)|\d{3})[\s\-.]?\d{3}[\s\-.]?\d{4}"
    ip_pattern = r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"
    return bool(
        re.search(email_pattern, text)
        or re.search(phone_pattern, text)
        or re.search(ip_pattern, text)
        or re.search(ssn_pattern, text)
    )


def _redact(text: str) -> str:
    text = re.sub(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", text
    )
    text = re.sub(
        r"(\+?\d{1,2}[\s\-.]?)?(\(\d{3}\)|\d{3})[\s\-.]?\d{3}[\s\-.]?\d{4}",
        "[REDACTED_PHONE]",
        text,
    )
    text = re.sub(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        "[REDACTED_IP]",
        text,
    )
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]", text)
    return text


def _score_severity(title: str, description: str, tags: List[str]) -> Tuple[Severity, float, str]:
    text = f"{title.lower()} {description.lower()} {' '.join(tags).lower()}"
    lowered_tags = [t.lower() for t in tags]
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

    if "p0" in lowered_tags:
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


def _parse_llm_payload(content: str) -> dict:
    """
    Tolerant JSON extractor: try direct JSON, then look for a JSON block between markers,
    then fall back to first brace-delimited object.
    """
    if not content:
        return {}
    content = content.strip()
    try:
        return json.loads(content)
    except Exception:
        pass

    # Look for explicit markers
    start_marker = "<<JSON>>"
    end_marker = "<</JSON>>"
    if start_marker in content and end_marker in content:
        block = content.split(start_marker, 1)[1].split(end_marker, 1)[0].strip()
        try:
            return json.loads(block)
        except Exception:
            pass

    # Last resort: extract first JSON object
    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = content[first_brace : last_brace + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    return {}


def _validate_llm_payload(
    summary: Any,
    actions: Any,
    rationale: Any,
    fallback_summary: str,
    fallback_actions: List[str],
    fallback_rationale: str,
) -> Tuple[str, List[str], str]:
    """
    Validate and sanitize LLM outputs to avoid malformed content leaking into responses.
    """
    if not isinstance(summary, str) or not summary.strip():
        summary_str = fallback_summary
    else:
        summary_str = summary.strip()[:240]

    cleaned_actions: List[str] = []
    if isinstance(actions, list):
        for act in actions:
            if isinstance(act, str):
                cleaned = act.strip()
                if cleaned:
                    cleaned_actions.append(cleaned)
            if len(cleaned_actions) >= 5:
                break
    if not cleaned_actions:
        cleaned_actions = fallback_actions

    if not isinstance(rationale, str) or not rationale.strip():
        rationale_str = fallback_rationale
    else:
        rationale_str = rationale.strip()[:480]

    return summary_str, cleaned_actions, rationale_str


def _build_plan(
    severity: Severity,
    knowledge_refs: List[str],
    history_refs: List[str],
    fallback_actions: List[str],
) -> List[str]:
    plan = [
        f"Use severity={severity.value} from deterministic scoring",
        f"Knowledge refs: {', '.join(knowledge_refs) or 'none'}",
        f"History refs: {', '.join(history_refs) or 'none'}",
        f"Initial actions: {', '.join(fallback_actions)}",
    ]
    return plan


class IncidentTriageAgent:
    def __init__(
        self,
        kb_tool: KnowledgeBaseTool,
        history_tool: HistoryTool,
        llm_client: LLMClient | None = None,
        tracer: AgentTracer | None = None,
    ):
        self.kb_tool = kb_tool
        self.history_tool = history_tool
        self.settings = get_settings()
        self.llm = llm_client or build_llm_client()
        self.tracer = tracer or NullTracer()

    def _record_trace(self, phase: str, **data: Any) -> None:
        try:
            self.tracer.record(phase, **data)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("trace_record_failed %s", exc, extra=log_extra(phase=phase))

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
- severity is provided by upstream deterministic logic and must not be changed.
- Do not invent or modify severity; focus only on summary/actions/rationale.
- Keep actions concise and actionable; prefer <=5 items.
Context:
- ticket_id: {ticket.id}
- severity: {severity.value}
- tags: {', '.join(ticket.tags)}
- knowledge_refs: {', '.join(knowledge_refs) or 'none'}
- history_refs: {', '.join(history_refs) or 'none'}
- prompt_version: {PROMPT_VERSION}

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
        self._record_trace("ticket_received", ticket=ticket.model_dump())
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
        self._record_trace("pii_scan", has_pii=has_pii, redacted=redacted)

        severity, confidence, rationale = _score_severity(ticket.title, description, ticket.tags)
        knowledge_refs = self.kb_tool.search(description)
        history_refs = self.history_tool.search(description)
        self._record_trace(
            "severity_scored",
            severity=severity.value,
            confidence=confidence,
            rationale=rationale,
            knowledge_refs=knowledge_refs,
            history_refs=history_refs,
        )

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
        plan_steps = _build_plan(severity, knowledge_refs, history_refs, fallback_actions)
        self._record_trace(
            "contextual_hits",
            knowledge_refs=knowledge_refs,
            history_refs=history_refs,
            adjusted_confidence=confidence,
            escalation_required=escalation_required,
            plan=plan_steps,
        )

        prompt = self._build_prompt(
            ticket=ticket,
            severity=severity,
            knowledge_refs=knowledge_refs,
            history_refs=history_refs,
            fallback_summary=fallback_summary,
            fallback_actions=fallback_actions,
            fallback_rationale=rationale,
        )
        self._record_trace(
            "prompt_built",
            prompt_version=PROMPT_VERSION,
            fallback_summary=fallback_summary,
            fallback_actions=fallback_actions,
            plan=plan_steps,
        )

        llm_resp = None
        llm_payload = {}
        try:
            llm_resp = self.llm.generate(prompt, max_tokens=self.settings.max_tokens)
            llm_payload = _parse_llm_payload(llm_resp.content)
            if not llm_payload:
                raise ValueError("empty_or_invalid_llm_payload")
            logger.info(
                "llm_completed",
                extra=log_extra(
                    ticket_id=ticket.id,
                    cost_usd=round(llm_resp.cost_usd, 6),
                    prompt_tokens=llm_resp.prompt_tokens,
                    completion_tokens=llm_resp.completion_tokens,
                ),
            )
            self._record_trace(
                "llm_response",
                prompt_version=PROMPT_VERSION,
                provider=self.llm.__class__.__name__,
                prompt_tokens=llm_resp.prompt_tokens,
                completion_tokens=llm_resp.completion_tokens,
                cost_usd=round(llm_resp.cost_usd, 6),
            )
        except Exception as exc:
            logger.warning(
                "llm_failure_fallback error=%s content_snippet=%s",
                exc,
                (llm_resp.content[:240] if llm_resp else ""),
                extra=log_extra(ticket_id=ticket.id),
            )
            self._record_trace(
                "llm_failure",
                error=str(exc),
                prompt_version=PROMPT_VERSION,
                content_snippet=(llm_resp.content[:240] if llm_resp else ""),
            )

        summary = llm_payload.get("summary", fallback_summary)
        actions = llm_payload.get("recommended_actions", fallback_actions)
        rationale_text = llm_payload.get("rationale", rationale)

        summary, actions, rationale_text = _validate_llm_payload(
            summary=summary,
            actions=actions,
            rationale=rationale_text,
            fallback_summary=fallback_summary,
            fallback_actions=fallback_actions,
            fallback_rationale=rationale,
        )
        if escalation_required:
            # Help reviewers by surfacing the plan for low-confidence cases.
            rationale_text = f"{rationale_text}; plan: {' | '.join(plan_steps)}"

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
        self._record_trace(
            "recommendation_finalized",
            summary=summary,
            severity=recommendation.severity.value,
            confidence=recommendation.confidence,
            escalation_required=escalation_required,
            redacted=redacted,
            ticket_id=ticket.id,
        )

        return recommendation
