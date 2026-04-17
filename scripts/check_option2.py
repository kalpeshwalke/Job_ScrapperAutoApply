import sys
sys.path.insert(0, '.')

from config.settings import Config

config = Config.load()
auto_apply = config.auto_apply_config

print("=" * 60)
print("OPTION 2 CONFIGURATION CHECK")
print("=" * 60)

print(f"\n[SUCCESS] Auto-apply enabled: {auto_apply.get('enabled')}")
print(f"[SUCCESS] AI Provider: {auto_apply.get('ai_provider')}")
print(f"[SUCCESS] AI Model: {auto_apply.get('ai_model')}")

user = auto_apply.get('user_details', {})
print(f"\n[SUCCESS] User Name: {user.get('name')}")
print(f"[SUCCESS] User Email: {user.get('email')}")

phone = user.get('phone', '')
if '+91-XXXXXXXXXX' in phone:
    print(f"[WARNING]  User Phone: {phone} (NEEDS UPDATING!)")
    print("   Update in config/config.yaml:")
    print("   user_details:")
    print("     phone: \"+91-YOUR-ACTUAL-NUMBER\"")
else:
    print(f"[SUCCESS] User Phone: {phone}")

resume = auto_apply.get('resume_path', '')
if resume:
    print(f"[SUCCESS] Resume: {resume}")
else:
    print("[SUCCESS] No resume configured (optional)")

print("\n" + "=" * 60)
print("TESTING OPTIONS:")
print("=" * 60)
print("\n1. SAFE TEST (recommended):")
print("   python test_option2_safe.py")
print("   - Shows what would happen")
print("   - No browser, no API calls, no submissions")
print("\n2. ACTUAL RUN (use with caution):")
print("   python main.py")
print("   Then choose '2' when prompted")
print("   - Opens browser")
print("   - Uses AI to fill forms")
print("   - WILL submit applications")
print("\n[WARNING]  WARNING: Actual run WILL submit job applications!")
print("   Make sure you're ready for this.")
print("=" * 60)
