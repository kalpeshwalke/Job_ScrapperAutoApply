"""
AI Provider Abstraction Layer

Provides a unified interface for multiple AI API providers (Gemini, OpenAI, Anthropic, Ollama).
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import os


@dataclass
class AIResponse:
    """Unified response format for all AI providers"""
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: str = "stop"
    usage: Optional[Dict[str, int]] = None


@dataclass
class RateLimits:
    """Provider-specific rate limits"""
    requests_per_minute: int
    requests_per_day: int
    tokens_per_minute: Optional[int] = None


class AIProvider(ABC):
    """Abstract base class for AI API providers"""
    
    def __init__(self, api_key: str, model: str, config: Dict[str, Any]):
        self.api_key = api_key
        self.model = model
        self.config = config
    
    @abstractmethod
    def generate_planner_response(
        self, 
        prompt: str, 
        context: Dict[str, Any]
    ) -> AIResponse:
        """
        Generate a structured JSON response for the Planner Agent.
        
        Args:
            prompt: System prompt defining planner behavior
            context: Job details and current state
            
        Returns:
            AIResponse with JSON content: {next_step, reasoning, status}
        """
        pass
    
    @abstractmethod
    def generate_browser_response(
        self, 
        prompt: str, 
        tools: List[Dict[str, Any]], 
        context: Dict[str, Any]
    ) -> AIResponse:
        """
        Generate a tool-calling response for the Browser Agent.
        
        Args:
            prompt: System prompt defining browser agent behavior
            tools: Available DOM toolkit functions
            context: Current step and DOM state
            
        Returns:
            AIResponse with tool_calls for DOM manipulation
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider name (e.g., 'gemini', 'openai')"""
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """Return model name (e.g., 'gemini-2.0-flash-exp')"""
        pass
    
    @abstractmethod
    def get_rate_limits(self) -> RateLimits:
        """Return provider-specific rate limits"""
        pass
    
    @abstractmethod
    def validate_availability(self) -> bool:
        """Check if provider is available and API key is valid"""
        pass


class AIProviderFactory:
    """Factory for creating AI provider instances"""
    
    @staticmethod
    def create_provider(config: Dict[str, Any]) -> AIProvider:
        """
        Create an AI provider instance based on configuration.
        
        Args:
            config: Configuration dictionary with ai_provider, ai_model, etc.
            
        Returns:
            Concrete AIProvider instance
            
        Raises:
            ValueError: If provider is unsupported or API key is missing
        """
        provider_name = config.get("ai_provider", "gemini").lower()
        model = config.get("ai_model")
        
        # Map provider names to environment variable keys
        env_key_map = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "groq": "GROQ_API_KEY",
            "ollama": None  # No API key needed for local
        }
        
        # Get API key from environment
        env_key = env_key_map.get(provider_name)
        if env_key:
            api_key = os.getenv(env_key)
            if not api_key:
                raise ValueError(
                    f"API key not found for provider '{provider_name}'. "
                    f"Please set {env_key} environment variable."
                )
        else:
            api_key = ""  # Ollama doesn't need API key
        
        # Import and create provider instance
        if provider_name == "gemini":
            from src.ai_auto_apply.providers.gemini_provider import GeminiProvider
            return GeminiProvider(api_key, model, config)
        elif provider_name == "openai":
            from src.ai_auto_apply.providers.openai_provider import OpenAIProvider
            return OpenAIProvider(api_key, model, config)
        elif provider_name == "anthropic":
            from src.ai_auto_apply.providers.anthropic_provider import AnthropicProvider
            return AnthropicProvider(api_key, model, config)
        elif provider_name == "ollama":
            from src.ai_auto_apply.providers.ollama_provider import OllamaProvider
            return OllamaProvider(api_key, model, config)
        elif provider_name == "deepseek":
            from src.ai_auto_apply.providers.deepseek_provider import DeepSeekProvider
            return DeepSeekProvider(api_key, model, config)
        elif provider_name == "groq":
            from src.ai_auto_apply.providers.groq_provider import GroqProvider
            return GroqProvider(api_key, model, config)
        else:
            raise ValueError(
                f"Unsupported AI provider: {provider_name}. "
                f"Supported providers: gemini, openai, anthropic, ollama, deepseek, groq"
            )
