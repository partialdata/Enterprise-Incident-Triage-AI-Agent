#!/usr/bin/env python3
"""
Merge vetted candidate eval cases into the main eval set.

Usage:
  python scripts/merge_eval_cases.py \
    --base data/eval_cases.json \
    --candidates data/eval_cases_candidates.json \
    --mode skip    # or replace

Defaults:
  base = data/eval_cases.json
  candidates = data/eval_cases_candidates.json
  mode = skip (skip duplicates by ticket id)
"""
import argparse
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple


def load_cases(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_cases(path: Path, cases: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)


def merge_cases(
    base: List[Dict[str, Any]], candidates: List[Dict[str, Any]], mode: str
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Merge candidates into base.
    mode:
      - skip: keep existing cases, skip candidate with duplicate ticket id
      - replace: overwrite existing case with same ticket id
    Returns (merged_cases, added_count, replaced_count)
    """
    merged = list(base)
    index = {case["ticket"]["id"]: i for i, case in enumerate(base) if "ticket" in case}

    added = 0
    replaced = 0

    for cand in candidates:
        ticket = cand.get("ticket", {})
        ticket_id = ticket.get("id")
        if not ticket_id:
            continue

        if ticket_id in index:
            if mode == "skip":
                continue
            # replace
            merged[index[ticket_id]] = cand
            replaced += 1
        else:
            merged.append(cand)
            index[ticket_id] = len(merged) - 1
            added += 1
    return merged, added, replaced


def main():
    parser = argparse.ArgumentParser(description="Merge candidate eval cases into the main set.")
    parser.add_argument("--base", type=Path, default=Path("data/eval_cases.json"), help="Path to main eval cases file")
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path("data/eval_cases_candidates.json"),
        help="Path to vetted candidate cases file",
    )
    parser.add_argument(
        "--mode",
        choices=["skip", "replace"],
        default="skip",
        help="How to handle duplicate ticket ids (skip existing or replace with candidate)",
    )
    args = parser.parse_args()

    base_cases = load_cases(args.base)
    candidate_cases = load_cases(args.candidates)

    merged, added, replaced = merge_cases(base_cases, candidate_cases, args.mode)
    write_cases(args.base, merged)

    print(f"Base cases: {len(base_cases)}")
    print(f"Candidates: {len(candidate_cases)}")
    print(f"Added: {added}, Replaced: {replaced}")
    print(f"Total now: {len(merged)} -> {args.base}")


if __name__ == "__main__":
    main()
