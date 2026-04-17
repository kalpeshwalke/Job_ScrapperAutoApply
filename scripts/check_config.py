import sys
sys.path.insert(0, '.')

from config.settings import Config

config = Config.load()

# Check if we can access the raw data
if hasattr(config, '_data'):
    print("[SUCCESS] _data attribute exists")
    data = config._data
    
    if 'auto_apply' in data:
        print("[SUCCESS] auto_apply section found in config.yaml")
        auto_apply = data['auto_apply']
        print(f"  Enabled: {auto_apply.get('enabled', 'Not found')}")
        print(f"  AI Provider: {auto_apply.get('ai_provider', 'Not found')}")
        print(f"  AI Model: {auto_apply.get('ai_model', 'Not found')}")
        
        # Check user details
        user_details = auto_apply.get('user_details', {})
        print(f"  User Name: {user_details.get('name', 'Not set')}")
        print(f"  User Email: {user_details.get('email', 'Not set')}")
        print(f"  User Phone: {user_details.get('phone', 'Not set')}")
    else:
        print("[ERROR] auto_apply not found in config.yaml")
        print("Available sections:")
        for key in data.keys():
            print(f"  - {key}")
else:
    print("[ERROR] Cannot access raw config data")
    
# Also check if main.py can access it
print("\nChecking main.py compatibility...")
try:
    # Simulate what main.py does
    auto_apply_config = None
    if hasattr(config, '_data') and 'auto_apply' in config._data:
        auto_apply_config = config._data['auto_apply']
        print("[SUCCESS] main.py can access auto_apply via config._data['auto_apply']")
    else:
        print("[ERROR] main.py cannot access auto_apply")
except Exception as e:
    print(f"Error: {e}")
