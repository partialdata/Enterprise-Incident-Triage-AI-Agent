from app.tools import HistoryTool, KnowledgeBaseTool


def test_knowledge_base_search_matches_keyword():
    kb = KnowledgeBaseTool()
    matches = kb.search("We see ransomware activity in logs")
    assert "kb-001" in matches


def test_history_search_matches_signal():
    hist = HistoryTool()
    matches = hist.search("vpn latency during peak")
    assert "hist-200" in matches


def test_tools_handle_missing_files(tmp_path, monkeypatch):
    # Point tools to non-existent files; should not raise and return empty.
    kb_path = tmp_path / "kb.json"
    hist_path = tmp_path / "hist.json"
    monkeypatch.setenv("KNOWLEDGE_BASE_PATH", str(kb_path))
    monkeypatch.setenv("HISTORY_PATH", str(hist_path))

    kb = KnowledgeBaseTool()
    hist = HistoryTool()
    assert kb.search("anything") == []
    assert hist.search("anything") == []
