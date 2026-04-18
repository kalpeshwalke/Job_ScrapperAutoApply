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

    def generate_completion(
        self,
        prompt: str,
        system_prompt: str = "Respond only with valid JSON. No explanation.",
    ) -> AIResponse:
        """
        Generate a minimal JSON completion without planner/browser context.
        Used by NarrowAI for constrained schema-only calls.
        
        Default implementation delegates to generate_planner_response.
        Providers can override for a cleaner path.
        
        Args:
            prompt: The full prompt text
            system_prompt: Minimal system instruction
            
        Returns:
            AIResponse with JSON content
        """
        return self.generate_planner_response(
            prompt=f"{system_prompt}\n\n{prompt}",
            context={},
        )
    
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
        Currently supports only Ollama for unlimited free local usage.
        """
        provider_name = config.get("ai_provider", "ollama").lower()
        model = config.get("ai_model", "llama3")
        
        if provider_name != "ollama":
            raise ValueError(
                f"Only 'ollama' provider is supported. Got: '{provider_name}'\n"
                f"Please update config.yaml: ai_provider: 'ollama'"
            )
        
        # Ollama doesn't need an API key
        from src.ai_auto_apply.providers.ollama_provider import OllamaProvider
        return OllamaProvider("local", model, config)
