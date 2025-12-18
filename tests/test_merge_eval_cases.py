from scripts.merge_eval_cases import merge_cases


def _case(ticket_id: str, severity: str) -> dict:
    return {"ticket": {"id": ticket_id}, "expected_severity": severity}


def test_merge_skip_mode_does_not_overwrite_existing():
    base = [_case("a", "P1"), _case("b", "P2")]
    candidates = [_case("b", "P0"), _case("c", "P3")]

    merged, added, replaced = merge_cases(base, candidates, mode="skip")

    assert added == 1  # only "c" added
    assert replaced == 0
    # existing "b" stays P2
    ids = {c["ticket"]["id"]: c["expected_severity"] for c in merged}
    assert ids == {"a": "P1", "b": "P2", "c": "P3"}


def test_merge_replace_mode_overwrites_existing():
    base = [_case("a", "P1"), _case("b", "P2")]
    candidates = [_case("b", "P0"), _case("c", "P3")]

    merged, added, replaced = merge_cases(base, candidates, mode="replace")

    assert added == 1  # "c" added
    assert replaced == 1  # "b" replaced
    ids = {c["ticket"]["id"]: c["expected_severity"] for c in merged}
    assert ids == {"a": "P1", "b": "P0", "c": "P3"}


def test_merge_ignores_candidates_without_ticket_id():
    base = []
    candidates = [{"ticket": {}}, {"expected_severity": "P1"}]

    merged, added, replaced = merge_cases(base, candidates, mode="skip")

    assert merged == []
    assert added == 0
    assert replaced == 0
