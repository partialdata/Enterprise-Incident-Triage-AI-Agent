#!/usr/bin/env python
import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.agent import IncidentTriageAgent  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import EvaluationResult, IncidentTicket, Severity  # noqa: E402
from app.tools import HistoryTool, KnowledgeBaseTool  # noqa: E402


def load_cases(path: Path):
    with open(path, "r") as f:
        raw = json.load(f)
    for entry in raw:
        yield (
            IncidentTicket(**entry["ticket"]),
            Severity(entry["expected_severity"]),
        )


def evaluate():
    settings = get_settings()
    kb_tool = KnowledgeBaseTool()
    history_tool = HistoryTool()
    agent = IncidentTriageAgent(kb_tool, history_tool)

    path = Path(settings.evaluation_cases_path)
    cases = list(load_cases(path))

    results: list[EvaluationResult] = []
    for ticket, expected_severity in cases:
        rec = agent.process(ticket)
        results.append(
            EvaluationResult(
                ticket_id=ticket.id,
                expected_severity=expected_severity,
                predicted_severity=rec.severity,
                passed=rec.severity == expected_severity,
                confidence=rec.confidence,
                escalation_required=rec.escalation_required,
                rationale=rec.rationale,
            )
        )

    accuracy = mean([1.0 if r.passed else 0.0 for r in results]) if results else 0
    avg_confidence = mean([r.confidence for r in results]) if results else 0
    low_conf = [r for r in results if r.escalation_required]
    failures = [r for r in results if not r.passed]

    print(f"Evaluated {len(results)} tickets")
    print(f"Severity accuracy: {accuracy*100:.1f}%")
    print(f"Avg confidence: {avg_confidence:.2f}")
    print(f"Escalations: {len(low_conf)}")
    if failures:
        print("Failures:")
        for fail in failures:
            print(f" - {fail.ticket_id}: expected {fail.expected_severity}, got {fail.predicted_severity} (conf {fail.confidence})")
    return results


if __name__ == "__main__":
    evaluate()
