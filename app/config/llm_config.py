"""
LLM configuration for document classification.

Supports:
- Ollama (local models)
- OpenAI (cloud API)
"""

import os
from typing import Optional, Literal
from dataclasses import dataclass


@dataclass
class LLMConfig:
    """Configuration for LLM document classifier."""
    
    provider: Literal["ollama", "openai", "none"] = "ollama"
    
    # Ollama settings
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"  # Fast, good for classification
    
    # OpenAI settings
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    
    # Common settings
    max_tokens: int = 300
    temperature: float = 0.0
    timeout: int = 30
    
    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load config from environment variables."""
        provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        
        return cls(
            provider=provider,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "300")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
            timeout=int(os.getenv("LLM_TIMEOUT", "30")),
        )


def get_llm_client(config: Optional[LLMConfig] = None):
    """
    Get LLM client based on configuration.
    
    Args:
        config: LLM configuration (defaults to env-based config)
    
    Returns:
        LLM client instance or None if disabled
    """
    if config is None:
        config = LLMConfig.from_env()
    
    if config.provider == "none":
        return None
    
    elif config.provider == "ollama":
        try:
            from ollama import Client
            client = Client(host=config.ollama_base_url)
            # Test connection
            client.list()
            return client
        except ImportError:
            print("⚠️  Ollama package not installed. Run: pip install ollama")
            return None
        except Exception as e:
            print(f"⚠️  Ollama connection failed: {e}")
            print(f"   Make sure Ollama is running at {config.ollama_base_url}")
            return None
    
    elif config.provider == "openai":
        try:
            from openai import OpenAI
            if not config.openai_api_key:
                print("⚠️  OPENAI_API_KEY not set")
                return None
            return OpenAI(api_key=config.openai_api_key)
        except ImportError:
            print("⚠️  OpenAI package not installed. Run: pip install openai")
            return None
    
    return None
