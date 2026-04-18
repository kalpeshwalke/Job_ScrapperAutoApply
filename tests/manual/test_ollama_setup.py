#!/usr/bin/env python3
"""
Ollama Setup Verification Script

This script verifies that Ollama is properly installed and configured
for use with the job scraper auto-apply feature.
"""

import sys
import requests
import json
from typing import Dict, Any


def print_header(text: str):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_success(text: str):
    """Print success message"""
    print(f"[OK] {text}")


def print_error(text: str):
    """Print error message"""
    print(f"[ERROR] {text}")


def print_warning(text: str):
    """Print warning message"""
    print(f"[WARN] {text}")


def print_info(text: str):
    """Print info message"""
    print(f"[INFO] {text}")


def check_ollama_running() -> bool:
    """Check if Ollama service is running"""
    print_header("Step 1: Checking if Ollama is running")
    
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            print_success("Ollama service is running on http://localhost:11434")
            return True
        else:
            print_error(f"Ollama returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to Ollama at http://localhost:11434")
        print_info("Make sure Ollama is installed and running")
        print_info("Install: https://ollama.com/download/windows")
        print_info("Or run: ollama serve")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


def check_model_available(model_name: str = "llama3") -> bool:
    """Check if the specified model is available"""
    print_header(f"Step 2: Checking if model '{model_name}' is available")
    
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        data = response.json()
        models = data.get("models", [])
        
        if not models:
            print_error("No models found in Ollama")
            print_info(f"Download the model: ollama pull {model_name}")
            return False
        
        # Check for exact match or with :latest tag
        model_names = [m["name"] for m in models]
        is_available = model_name in model_names or f"{model_name}:latest" in model_names
        
        if is_available:
            print_success(f"Model '{model_name}' is available")
            print_info(f"Available models: {', '.join(model_names)}")
            return True
        else:
            print_error(f"Model '{model_name}' not found")
            print_info(f"Available models: {', '.join(model_names)}")
            print_info(f"Download the model: ollama pull {model_name}")
            return False
            
    except Exception as e:
        print_error(f"Failed to check models: {e}")
        return False


def test_json_generation(model_name: str = "llama3") -> bool:
    """Test JSON generation capability"""
    print_header("Step 3: Testing JSON generation")
    
    try:
        print_info("Sending test prompt to Ollama...")
        
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model_name,
                "prompt": "Generate a JSON object with two fields: 'status' (string) and 'message' (string). Respond with valid JSON only.",
                "stream": False,
                "format": "json"
            },
            timeout=30
        )
        
        if response.status_code != 200:
            print_error(f"API returned status code: {response.status_code}")
            return False
        
        result = response.json()
        generated_text = result.get("response", "")
        
        # Try to parse as JSON
        try:
            parsed = json.loads(generated_text)
            print_success("Successfully generated valid JSON")
            print_info(f"Response: {json.dumps(parsed, indent=2)}")
            return True
        except json.JSONDecodeError:
            print_warning("Model generated text but not valid JSON")
            print_info(f"Response: {generated_text[:200]}")
            print_info("This may cause issues with auto-apply feature")
            return False
            
    except requests.exceptions.Timeout:
        print_error("Request timed out (>30 seconds)")
        print_info("Your machine may be too slow for this model")
        print_info("Try a smaller model: ollama pull phi3")
        return False
    except Exception as e:
        print_error(f"Test failed: {e}")
        return False


def test_tool_calling_format(model_name: str = "llama3") -> bool:
    """Test tool calling format (browser agent simulation)"""
    print_header("Step 4: Testing tool calling format")
    
    try:
        print_info("Testing browser agent tool calling...")
        
        prompt = """You are a browser automation agent. You need to fill a form field.

Available tools:
- fill_field: Fill a text input field
  Parameters: {"selector": "string", "value": "string"}

Context: You need to fill the email field with "test@example.com"

Respond with JSON in this format:
{
    "tool_name": "name_of_tool_to_call",
    "arguments": {...}
}
"""
        
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            },
            timeout=30
        )
        
        if response.status_code != 200:
            print_error(f"API returned status code: {response.status_code}")
            return False
        
        result = response.json()
        generated_text = result.get("response", "")
        
        # Try to parse as JSON
        try:
            parsed = json.loads(generated_text)
            
            # Check if it has the expected structure
            if "tool_name" in parsed and "arguments" in parsed:
                print_success("Tool calling format is correct")
                print_info(f"Tool: {parsed.get('tool_name')}")
                print_info(f"Arguments: {parsed.get('arguments')}")
                return True
            else:
                print_warning("JSON structure doesn't match expected format")
                print_info(f"Expected: {{'tool_name': '...', 'arguments': {{...}}}}")
                print_info(f"Got: {json.dumps(parsed, indent=2)}")
                return False
                
        except json.JSONDecodeError:
            print_error("Model didn't generate valid JSON")
            print_info(f"Response: {generated_text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print_error("Request timed out (>30 seconds)")
        return False
    except Exception as e:
        print_error(f"Test failed: {e}")
        return False


def check_config_file() -> bool:
    """Check if config.yaml is properly configured"""
    print_header("Step 5: Checking config.yaml")
    
    try:
        import yaml
        
        with open("config/config.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        auto_apply = config.get("auto_apply", {})
        
        # Check provider
        provider = auto_apply.get("ai_provider")
        if provider == "ollama":
            print_success("AI provider is set to 'ollama'")
        else:
            print_error(f"AI provider is set to '{provider}' (expected 'ollama')")
            return False
        
        # Check model
        model = auto_apply.get("ai_model")
        if model:
            print_success(f"AI model is set to '{model}'")
        else:
            print_error("AI model is not configured")
            return False
        
        # Check base URL
        base_url = auto_apply.get("ollama_base_url", "http://localhost:11434")
        print_info(f"Ollama base URL: {base_url}")
        
        return True
        
    except FileNotFoundError:
        print_error("config/config.yaml not found")
        return False
    except ImportError:
        print_warning("PyYAML not installed, skipping config check")
        print_info("Install: pip install pyyaml")
        return True  # Don't fail on this
    except Exception as e:
        print_error(f"Failed to read config: {e}")
        return False


def main():
    """Run all verification checks"""
    print("\n" + "*" * 30)
    print("  OLLAMA SETUP VERIFICATION")
    print("*" * 30)
    
    results = []
    
    # Run all checks
    results.append(("Ollama Running", check_ollama_running()))
    
    if results[-1][1]:  # Only continue if Ollama is running
        results.append(("Model Available", check_model_available("llama3")))
        
        if results[-1][1]:  # Only continue if model is available
            results.append(("JSON Generation", test_json_generation("llama3")))
            results.append(("Tool Calling", test_tool_calling_format("llama3")))
    
    results.append(("Config File", check_config_file()))
    
    # Print summary
    print_header("VERIFICATION SUMMARY")
    
    all_passed = True
    for check_name, passed in results:
        if passed:
            print_success(f"{check_name}: PASSED")
        else:
            print_error(f"{check_name}: FAILED")
            all_passed = False
    
    print("\n" + "=" * 60)
    
    if all_passed:
        print("[OK] All checks passed! ***")
        print_info("Your Ollama setup is ready for job auto-apply")
        print_info("Run your scraper with auto_apply enabled")
        return 0
    else:
        print_error("Some checks failed")
        print_info("Please fix the issues above before running auto-apply")
        print_info("See OLLAMA_SETUP.md for detailed instructions")
        return 1


if __name__ == "__main__":
    sys.exit(main())
