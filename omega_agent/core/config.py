"""OMEGA system configuration."""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict

from omega_agent.core.env_config import env_bool, env_int, env_optional_str

# 2026 Free Model Mappings 
# (Mistral models removed due to 404 upstream deprecation)
DEFAULT_MODELS = {
    "primary":   "openai/gpt-oss-120b:free",       # OpenAI open-weight flagship
    "backup":    "meta-llama/llama-3.3-70b-instruct:free", # Reliable Meta fallback
    "fast":      "openai/gpt-oss-20b:free",         # Lighter, faster OSS model
    "reasoning": "nvidia/nemotron-3-super-120b-a12b:free",  # Strong reasoning/agents
}

@dataclass
class Config:
    """OMEGA system configuration."""

    # Provider Configuration
    llm_provider: Optional[str] = field(
        default_factory=lambda: os.environ.get("OMEGA_LLM_PROVIDER", "openrouter")
    )
    
    # Model configuration (Defaults to OpenRouter slugs)
    primary_model: str = DEFAULT_MODELS["primary"]
    backup_model: str = DEFAULT_MODELS["backup"]
    fast_model: str = DEFAULT_MODELS["fast"]
    reasoning_model: str = DEFAULT_MODELS["reasoning"]

    # API Keys
    openrouter_api_key: Optional[str] = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY"))
    groq_api_key: Optional[str] = field(default_factory=lambda: os.environ.get("GROQ_API_KEY"))
    anthropic_api_key: Optional[str] = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY"))
    openai_api_key: Optional[str] = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY"))

    # Provider and Execution
    use_mock_llm: bool = field(default_factory=lambda: env_bool("OMEGA_USE_MOCK_LLM", False))
    gradio_concurrency: int = field(default_factory=lambda: env_int("OMEGA_GRADIO_CONCURRENCY", 4))
    
    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None
    
    # Paths and Infrastructure
    workspace_root: str = field(default_factory=lambda: os.environ.get("OMEGA_WORKSPACE_ROOT", "./outputs/workspaces"))
    build_output_dir: str = "./outputs"
    memory_db_path: str = field(default_factory=lambda: os.environ.get("OMEGA_MEMORY_DB", "./outputs/memory.db"))
    
    # Feature Flags and Limits
    enable_semantic_memory: bool = field(default_factory=lambda: env_bool("OMEGA_ENABLE_SEMANTIC_MEMORY", True))
    enable_episodic_memory: bool = field(default_factory=lambda: env_bool("OMEGA_ENABLE_EPISODIC_MEMORY", True))
    enable_faiss: bool = field(default_factory=lambda: env_bool("OMEGA_ENABLE_FAISS", False))
    enable_learning: bool = field(default_factory=lambda: env_bool("OMEGA_ENABLE_LEARNING", False))
    recursion_limit: int = field(default_factory=lambda: env_int("OMEGA_RECURSION_LIMIT", 5))
    max_task_timeout: int = 600
    
    # Networking / Misc
    default_tenant_id: str = field(default_factory=lambda: os.environ.get("OMEGA_DEFAULT_TENANT_ID", "default"))
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    def active_llm_provider(self) -> Optional[str]:
        """Return active LLM provider or None for mock mode."""
        if self.use_mock_llm:
            return None
        
        forced = (self.llm_provider or "openrouter").lower().strip()
        if forced in ("groq", "anthropic", "openai", "openrouter"):
            return forced
            
        return "groq" if self.groq_api_key else None

    def has_llm_credentials(self) -> bool:
        return self.active_llm_provider() is not None