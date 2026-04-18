"""
Ollama Local Model AI Provider Implementation
"""

import requests
from typing import Dict, List, Any
import json
from src.ai_auto_apply.providers.ai_provider import AIProvider, AIResponse, RateLimits
from src.common.logger import get_logger

logger = get_logger("ollama_provider")


class OllamaProvider(AIProvider):
    """Ollama local model provider implementation"""
    
    def __init__(self, api_key: str, model: str, config: Dict[str, Any]):
        super().__init__(api_key, model, config)
        self.base_url = config.get("ollama_base_url", "http://localhost:11434")
    
    def generate_planner_response(
        self, 
        prompt: str, 
        context: Dict[str, Any]
    ) -> AIResponse:
        """Generate JSON response using Ollama"""
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": f"{prompt}\n\nContext: {context}\n\nRespond with valid JSON only.",
                    "stream": False,
                    "format": "json"
                },
                timeout=180
            )
            response.raise_for_status()
            
            result = response.json()
            
            return AIResponse(
                content=result["response"],
                finish_reason="stop",
                usage=None  # Ollama doesn't provide token counts
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API request failed: {e}")
            raise RuntimeError(f"Failed to connect to Ollama at {self.base_url}. Is Ollama running?") from e
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse Ollama response: {e}")
            raise RuntimeError("Ollama returned invalid response format") from e
    
    def generate_browser_response(
        self, 
        prompt: str, 
        tools: List[Dict[str, Any]], 
        context: Dict[str, Any]
    ) -> AIResponse:
        """Generate tool-calling response using Ollama with structured output"""
        # Ollama doesn't have native function calling, so we use structured prompting
        tools_description = self._format_tools_for_prompt(tools)
        
        full_prompt = f"""{prompt}

Available tools:
{tools_description}

Context: {context}

Respond with JSON in this format:
{{
    "tool_name": "name_of_tool_to_call",
    "arguments": {{...}}
}}
"""
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=180
            )
            response.raise_for_status()
            
            result = response.json()
            
            try:
                tool_response = json.loads(result["response"])
            except (json.JSONDecodeError, KeyError) as e:
                # Local models often return garbled JSON — return empty tool calls
                logger.warning(f"Ollama returned malformed JSON: {e}. Response: {result.get('response', '')[:200]}")
                return AIResponse(
                    content=result.get("response", ""),
                    tool_calls=None,
                    finish_reason="stop",
                    usage=None
                )
            
            tool_calls = [{
                "name": tool_response.get("tool_name", ""),
                "arguments": tool_response.get("arguments", {})
            }]
            
            return AIResponse(
                content="",
                tool_calls=tool_calls,
                finish_reason="stop",
                usage=None
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API request failed: {e}")
            raise RuntimeError(f"Failed to connect to Ollama at {self.base_url}. Is Ollama running?") from e
    
    def get_provider_name(self) -> str:
        return "ollama"
    
    def get_model_name(self) -> str:
        return self.model
    
    def get_rate_limits(self) -> RateLimits:
        # No rate limits for local models
        return RateLimits(
            requests_per_minute=999999,
            requests_per_day=999999
        )
    
    def validate_availability(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            models = response.json()["models"]
            model_names = [m["name"] for m in models]
            # Check both exact match and with :latest tag
            is_available = self.model in model_names or f"{self.model}:latest" in model_names
            if not is_available:
                logger.warning(f"Model '{self.model}' not found. Available models: {model_names}")
            return is_available
        except Exception as e:
            logger.error(f"Ollama availability check failed: {e}")
            return False
    
    def _format_tools_for_prompt(self, tools: List[Dict[str, Any]]) -> str:
        """Format tools as text for prompt"""
        formatted = []
        for tool in tools:
            func = tool["function"]
            formatted.append(f"- {func['name']}: {func['description']}")
            formatted.append(f"  Parameters: {json.dumps(func['parameters'], indent=2)}")
        return "\n".join(formatted)
