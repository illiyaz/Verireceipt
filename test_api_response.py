"""
Test API response to see actual structure
"""
import requests
import json
from pathlib import Path

# Find a test image
test_images = list(Path("test_receipts").glob("*.jpg")) if Path("test_receipts").exists() else []
if not test_images:
    test_images = list(Path(".").glob("*.jpg"))[:1]

if not test_images:
    print("❌ No test images found. Please provide a receipt image.")
    print("   You can:")
    print("   1. Create test_receipts/ folder and add images")
    print("   2. Or place a .jpg file in the current directory")
    exit(1)

test_image = test_images[0]
print(f"📸 Using test image: {test_image}")

# Test the API
print("\n🚀 Testing /analyze/hybrid endpoint...")
print("=" * 60)

try:
    with open(test_image, 'rb') as f:
        files = {'file': f}
        response = requests.post(
            'http://localhost:8000/analyze/hybrid',
            files=files,
            timeout=60
        )
    
    print(f"\n📊 Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("\n✅ SUCCESS! Response received:")
        print("=" * 60)
        print(json.dumps(data, indent=2))
        print("=" * 60)
        
        # Check hybrid_verdict structure
        if 'hybrid_verdict' in data:
            verdict = data['hybrid_verdict']
            print("\n🔍 Hybrid Verdict Structure:")
            print(f"   final_label: {verdict.get('final_label')}")
            print(f"   confidence: {verdict.get('confidence')}")
            print(f"   recommended_action: {verdict.get('recommended_action')}")
            print(f"   reasoning: {verdict.get('reasoning')}")
            print(f"   reasoning type: {type(verdict.get('reasoning'))}")
            
            # Check for issues
            issues = []
            if verdict.get('final_label') is None:
                issues.append("❌ final_label is None")
            if verdict.get('confidence') is None:
                issues.append("❌ confidence is None")
            if verdict.get('recommended_action') is None:
                issues.append("❌ recommended_action is None")
            if verdict.get('reasoning') is None:
                issues.append("❌ reasoning is None")
            elif not isinstance(verdict.get('reasoning'), list):
                issues.append(f"❌ reasoning is not a list, it's {type(verdict.get('reasoning'))}")
            
            if issues:
                print("\n⚠️  ISSUES FOUND:")
                for issue in issues:
                    print(f"   {issue}")
            else:
                print("\n✅ All fields present and correct types!")
        else:
            print("\n❌ No hybrid_verdict in response!")
            
    else:
        print(f"\n❌ FAILED! Status: {response.status_code}")
        print(f"Response: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("\n❌ ERROR: Cannot connect to API")
    print("   Make sure the API is running:")
    print("   python -m app.api.main")
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
