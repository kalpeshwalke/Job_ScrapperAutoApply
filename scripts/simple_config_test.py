import sys
sys.path.insert(0, '.')

from config.settings import Config

config = Config.load()
print("Config loaded successfully")

# Check structure
print("\nChecking config structure...")
print(f"Type of config: {type(config)}")

# Try to access auto_apply
try:
    if hasattr(config, 'auto_apply'):
        print("[SUCCESS] config.auto_apply exists")
        auto_apply = config.auto_apply
        print(f"  Enabled: {auto_apply.get('enabled', 'Not found')}")
        print(f"  AI Provider: {auto_apply.get('ai_provider', 'Not found')}")
    else:
        print("[ERROR] config.auto_apply not found")
        print("Available attributes:")
        for attr in dir(config):
            if not attr.startswith('_'):
                print(f"  {attr}")
except Exception as e:
    print(f"Error: {e}")
