import json
import logging
import os
from typing import List

from .config import get_settings

logger = logging.getLogger(__name__)


class KnowledgeBaseTool:
    def __init__(self, path: str | None = None):
        settings = get_settings()
        self.path = path or settings.knowledge_base_path
        self.entries = self._load()

    def _load(self) -> List[dict]:
        if not os.path.exists(self.path):
            logger.warning("knowledge_base_missing", extra={"path": self.path})
            return []
        with open(self.path, "r") as f:
            return json.load(f)

    def search(self, text: str) -> List[str]:
        matches = []
        lowered = text.lower()
        for entry in self.entries:
            if entry.get("keyword", "").lower() in lowered:
                matches.append(entry.get("id", "kb-entry"))
        return matches[:3]


class HistoryTool:
    def __init__(self, path: str | None = None):
        settings = get_settings()
        self.path = path or settings.history_path
        self.records = self._load()

    def _load(self) -> List[dict]:
        if not os.path.exists(self.path):
            logger.warning("history_missing", extra={"path": self.path})
            return []
        with open(self.path, "r") as f:
            return json.load(f)

    def search(self, text: str) -> List[str]:
        matches = []
        lowered = text.lower()
        for record in self.records:
            if record.get("signal", "").lower() in lowered:
                matches.append(record.get("id", "history-entry"))
        return matches[:3]
