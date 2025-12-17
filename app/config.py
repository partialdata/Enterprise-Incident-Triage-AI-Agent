from functools import lru_cache
import os
from pydantic import BaseModel


class Settings(BaseModel):
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    llm_model: str = os.getenv("LLM_MODEL", "mock-001")
    max_tokens: int = int(os.getenv("MAX_TOKENS", "512"))
    cost_per_1k_tokens: float = float(os.getenv("COST_PER_1K_TOKENS", "0.0"))
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.65"))
    redact_pii: bool = os.getenv("REDACT_PII", "true").lower() == "true"
    knowledge_base_path: str = os.getenv(
        "KNOWLEDGE_BASE_PATH", "data/knowledge_base.json"
    )
    history_path: str = os.getenv("HISTORY_PATH", "data/history.json")
    evaluation_cases_path: str = os.getenv(
        "EVAL_CASES_PATH", "data/eval_cases.json"
    )
    service_name: str = os.getenv("SERVICE_NAME", "incident-triage-agent")


@lru_cache
def get_settings() -> Settings:
    return Settings()
