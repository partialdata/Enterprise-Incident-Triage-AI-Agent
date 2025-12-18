from functools import lru_cache
import os
from typing import Optional
from pydantic import BaseModel


_DEFAULT_LLM_MODELS = {
    "mock": "mock-001",
    "openai": "gpt-4o-mini",
    "ollama": "llama3",
}


class Settings(BaseModel):
    llm_provider: str = os.getenv("LLM_PROVIDER") or "mock"
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_fail_open: bool = os.getenv("LLM_FAIL_OPEN", "false").lower() == "true"
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_base_url: Optional[str] = os.getenv("OPENAI_BASE_URL")
    ollama_model: Optional[str] = os.getenv("OLLAMA_MODEL")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
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
    traces_path: str = os.getenv("TRACES_PATH", "data/traces.jsonl")
    service_name: str = os.getenv("SERVICE_NAME", "incident-triage-agent")

    def resolved_llm_model(self) -> str:
        provider = (self.llm_provider or "mock").strip().lower()
        if self.llm_model:
            return self.llm_model
        if provider == "ollama" and self.ollama_model:
            return self.ollama_model
        return _DEFAULT_LLM_MODELS.get(provider, "mock-001")


@lru_cache
def get_settings() -> Settings:
    return Settings()
