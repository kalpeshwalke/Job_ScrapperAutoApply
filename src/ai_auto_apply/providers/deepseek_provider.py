"""
DeepSeek AI Provider Implementation

DeepSeek API is OpenAI-compatible, so we extend the OpenAIProvider
but with DeepSeek-specific configuration (base_url, rate limits).
"""

from openai import OpenAI
from typing import Dict, List, Any
import json
from src.ai_auto_apply.providers.ai_provider import AIProvider, AIResponse, RateLimits


class DeepSeekProvider(AIProvider):
    """DeepSeek API provider implementation (OpenAI-compatible)"""
    
    def __init__(self, api_key: str, model: str, config: Dict[str, Any]):
        super().__init__(api_key, model, config)
        # DeepSeek uses OpenAI-compatible API with custom base URL
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
    
    def generate_planner_response(
        self, 
        prompt: str, 
        context: Dict[str, Any]
    ) -> AIResponse:
        """Generate JSON response using DeepSeek's JSON mode"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(context, default=str)}
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        return AIResponse(
            content=response.choices[0].message.content,
            finish_reason=response.choices[0].finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        )
    
    def generate_browser_response(
        self, 
        prompt: str, 
        tools: List[Dict[str, Any]], 
        context: Dict[str, Any]
    ) -> AIResponse:
        """Generate tool-calling response using DeepSeek's function calling"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(context, default=str)}
            ],
            tools=tools,
            tool_choice="auto",
            temperature=0.7
        )
        
        message = response.choices[0].message
        tool_calls = None
        
        if message.tool_calls:
            tool_calls = []
            for tool_call in message.tool_calls:
                tool_calls.append({
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                })
        
        return AIResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=response.choices[0].finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        )
    
    def get_provider_name(self) -> str:
        """Get provider name"""
        return "deepseek"
    
    def get_model_name(self) -> str:
        """Get model name"""
        return self.model
    
    def get_rate_limits(self) -> RateLimits:
        """
        Get DeepSeek API rate limits.
        
        Default rate limits for DeepSeek API (may vary based on plan):
        - Free tier: 100 requests/min, 1000 requests/day
        - Can be configured in config.yaml
        """
        # Get rate limits from config or use defaults
        rate_config = self.config.get("rate_limiting", {})
        return RateLimits(
            requests_per_minute=rate_config.get("requests_per_minute", 100),
            requests_per_day=rate_config.get("requests_per_day", 1000)
        )
    
    def validate_availability(self) -> bool:
        """
        Validate that DeepSeek API is available.
        
        Returns:
            True if API is available, False otherwise
        """
        try:
            # Try a simple API call to validate
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            return True
        except Exception:
            return False
