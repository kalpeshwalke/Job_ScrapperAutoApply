"""
Anthropic Claude AI Provider Implementation
"""

from anthropic import Anthropic
from typing import Dict, List, Any
import json
from src.ai_auto_apply.providers.ai_provider import AIProvider, AIResponse, RateLimits


class AnthropicProvider(AIProvider):
    """Anthropic Claude API provider implementation"""
    
    def __init__(self, api_key: str, model: str, config: Dict[str, Any]):
        super().__init__(api_key, model, config)
        self.client = Anthropic(api_key=api_key)
    
    def generate_planner_response(
        self, 
        prompt: str, 
        context: Dict[str, Any]
    ) -> AIResponse:
        """Generate JSON response using Claude"""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=prompt + "\n\nYou must respond with valid JSON only.",
            messages=[
                {"role": "user", "content": json.dumps(context, default=str)}
            ]
        )
        
        return AIResponse(
            content=response.content[0].text,
            finish_reason=response.stop_reason,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens
            }
        )
    
    def generate_browser_response(
        self, 
        prompt: str, 
        tools: List[Dict[str, Any]], 
        context: Dict[str, Any]
    ) -> AIResponse:
        """Generate tool-calling response using Claude's tool use"""
        # Convert OpenAI-style tools to Anthropic format
        anthropic_tools = self._convert_tools_to_anthropic(tools)
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=prompt,
            tools=anthropic_tools,
            messages=[
                {"role": "user", "content": json.dumps(context, default=str)}
            ]
        )
        
        tool_calls = []
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append({
                    "name": block.name,
                    "arguments": block.input
                })
        
        return AIResponse(
            content=response.content[0].text if response.content[0].type == "text" else "",
            tool_calls=tool_calls,
            finish_reason=response.stop_reason,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens
            }
        )
    
    def get_provider_name(self) -> str:
        return "anthropic"
    
    def get_model_name(self) -> str:
        return self.model
    
    def get_rate_limits(self) -> RateLimits:
        # Default to conservative limits (user should configure based on tier)
        return RateLimits(
            requests_per_minute=self.config.get("requests_per_minute", 50),
            requests_per_day=self.config.get("requests_per_day", 10000)
        )
    
    def validate_availability(self) -> bool:
        try:
            # Test with a minimal request
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}]
            )
            return True
        except Exception:
            return False
    
    def _convert_tools_to_anthropic(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI-style tool definitions to Anthropic format"""
        anthropic_tools = []
        for tool in tools:
            anthropic_tools.append({
                "name": tool["function"]["name"],
                "description": tool["function"]["description"],
                "input_schema": tool["function"]["parameters"]
            })
        return anthropic_tools
