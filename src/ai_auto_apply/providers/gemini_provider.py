"""
Google Gemini AI Provider Implementation

Migrated to the new google.genai SDK (replacing deprecated google.generativeai).
Supports both legacy AIzaSy-prefixed keys and new AQ.-prefixed keys from Google AI Studio.

Migration reference: https://ai.google.dev/gemini-api/docs/migrate
"""

import json
import logging
from typing import Dict, List, Any
from src.ai_auto_apply.providers.ai_provider import AIProvider, AIResponse, RateLimits

logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    """Google Gemini API provider using the new google.genai SDK"""

    def __init__(self, api_key: str, model: str, config: Dict[str, Any]):
        super().__init__(api_key, model, config)

        try:
            from google import genai
            # The new SDK uses a centralized Client object
            self.client = genai.Client(api_key=api_key)
            self._sdk_available = True
            logger.info("Gemini provider initialized with google.genai SDK (model: %s)", model)
        except ImportError:
            logger.error(
                "google-genai package not installed. "
                "Run: pip install google-genai"
            )
            self._sdk_available = False
            self.client = None

    def generate_planner_response(
        self,
        prompt: str,
        context: Dict[str, Any]
    ) -> AIResponse:
        """Generate JSON response using Gemini's JSON mode"""
        if not self._sdk_available:
            raise RuntimeError("google-genai SDK not available")

        from google.genai import types

        # Build the combined prompt with context
        combined_prompt = f"{prompt}\n\nContext:\n{json.dumps(context, default=str)}"

        response = self.client.models.generate_content(
            model=self.model,
            contents=combined_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,
            )
        )

        # Extract usage metadata safely
        usage = {}
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = {"total_tokens": getattr(response.usage_metadata, 'total_token_count', 0)}

        return AIResponse(
            content=response.text,
            finish_reason="stop",
            usage=usage
        )

    def generate_browser_response(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> AIResponse:
        """Generate tool-calling response using Gemini's function calling"""
        if not self._sdk_available:
            raise RuntimeError("google-genai SDK not available")

        from google.genai import types

        # Convert OpenAI-style tool definitions to Gemini function declarations
        function_declarations = []
        for tool in tools:
            func_def = tool.get("function", {})
            function_declarations.append(types.FunctionDeclaration(
                name=func_def.get("name", ""),
                description=func_def.get("description", ""),
                parameters=func_def.get("parameters", {})
            ))

        # Build the combined prompt with context
        combined_prompt = f"{prompt}\n\nContext:\n{json.dumps(context, default=str)}"

        response = self.client.models.generate_content(
            model=self.model,
            contents=combined_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(function_declarations=function_declarations)],
                temperature=0.7,
            )
        )

        # Extract tool calls from response
        tool_calls = []
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    tool_calls.append({
                        "name": part.function_call.name,
                        "arguments": dict(part.function_call.args) if part.function_call.args else {}
                    })

        # Extract text content safely
        text_content = ""
        try:
            text_content = response.text if response.text else ""
        except Exception:
            pass

        # Extract usage metadata safely
        usage = {}
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = {"total_tokens": getattr(response.usage_metadata, 'total_token_count', 0)}

        return AIResponse(
            content=text_content,
            tool_calls=tool_calls,
            finish_reason="stop",
            usage=usage
        )

    def get_provider_name(self) -> str:
        return "gemini"

    def get_model_name(self) -> str:
        return self.model

    def get_rate_limits(self) -> RateLimits:
        # Gemini Free Tier limits
        return RateLimits(
            requests_per_minute=15,
            requests_per_day=1500
        )

    def validate_availability(self) -> bool:
        """Test API key with a minimal request"""
        if not self._sdk_available:
            return False
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents="test"
            )
            return True
        except Exception as e:
            logger.warning("Gemini availability check failed: %s", e)
            return False
