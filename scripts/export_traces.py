#!/usr/bin/env python3
"""
Export recent trace events into candidate eval cases.

Usage:
  python scripts/export_traces.py --traces data/traces.jsonl --out data/eval_cases_candidates.json

This builds eval-ready JSON (same shape as data/eval_cases.json) using:
- ticket payload captured at phase ticket_received
- severity captured at phase recommendation_finalized (as a starting label to review)
"""
import argparse
import json
from pathlib import Path
from typing import Dict, List


def load_traces(path: Path) -> List[dict]:
    events = []
    if not path.exists():
        raise FileNotFoundError(f"Trace file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def build_candidates(events: List[dict]) -> List[dict]:
    tickets: Dict[str, dict] = {}
    cases: List[dict] = []

    for event in events:
        data = event.get("data", {})
        phase = event.get("phase")
        if phase == "ticket_received":
            ticket = data.get("ticket")
            if ticket and "id" in ticket:
                tickets[ticket["id"]] = ticket
        elif phase == "recommendation_finalized":
            severity = data.get("severity")
            ticket_id = None
            # Prefer explicit ticket_id in data; otherwise derive from prior ticket capture
            if "ticket_id" in data:
                ticket_id = data["ticket_id"]
            elif tickets:
                # Fallback: best-effort—this assumes single active ticket per run
                ticket_id = next(iter(tickets))
            if not severity or not ticket_id or ticket_id not in tickets:
                continue
            cases.append(
                {
                    "ticket": tickets[ticket_id],
                    "expected_severity": severity,
                }
            )
    return cases


def main():
    parser = argparse.ArgumentParser(description="Export traces to candidate eval cases")
    parser.add_argument("--traces", default="data/traces.jsonl", type=Path, help="Input trace JSONL path")
    parser.add_argument("--out", default="data/eval_cases_candidates.json", type=Path, help="Output JSON path")
    args = parser.parse_args()

    events = load_traces(args.traces)
    cases = build_candidates(events)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)
    print(f"Wrote {len(cases)} candidate cases to {args.out}")
    print("Review and update expected_severity as ground truth before adding to data/eval_cases.json")


if __name__ == "__main__":
    main()
