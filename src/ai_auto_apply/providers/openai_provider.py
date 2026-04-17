"""
OpenAI GPT AI Provider Implementation
"""

from openai import OpenAI
from typing import Dict, List, Any
import json
from src.ai_auto_apply.providers.ai_provider import AIProvider, AIResponse, RateLimits


class OpenAIProvider(AIProvider):
    """OpenAI GPT API provider implementation"""
    
    def __init__(self, api_key: str, model: str, config: Dict[str, Any]):
        super().__init__(api_key, model, config)
        self.client = OpenAI(api_key=api_key)
    
    def generate_planner_response(
        self, 
        prompt: str, 
        context: Dict[str, Any]
    ) -> AIResponse:
        """Generate JSON response using OpenAI's JSON mode"""
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
        """Generate tool-calling response using OpenAI's function calling"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(context, default=str)}
            ],
            tools=tools,
            tool_choice="auto"
        )
        
        tool_calls = []
        if response.choices[0].message.tool_calls:
            for tc in response.choices[0].message.tool_calls:
                tool_calls.append({
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                })
        
        return AIResponse(
            content=response.choices[0].message.content or "",
            tool_calls=tool_calls,
            finish_reason=response.choices[0].finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        )
    
    def get_provider_name(self) -> str:
        return "openai"
    
    def get_model_name(self) -> str:
        return self.model
    
    def get_rate_limits(self) -> RateLimits:
        # Default to conservative limits (user should configure based on tier)
        return RateLimits(
            requests_per_minute=self.config.get("requests_per_minute", 60),
            requests_per_day=self.config.get("requests_per_day", 10000),
            tokens_per_minute=self.config.get("tokens_per_minute", 90000)
        )
    
    def validate_availability(self) -> bool:
        try:
            self.client.models.retrieve(self.model)
            return True
        except Exception:
            return False
