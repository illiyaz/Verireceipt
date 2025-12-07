"""
Test feedback submission with empty reasons and corrections
"""

import requests
import json

# Test data - simulating what the frontend sends
feedback_data = {
    "receipt_id": "test_receipt_001",
    "human_label": "real",
    "reasons": [],  # Empty - user didn't select any reasons
    "corrections": {},  # Empty - user didn't make any corrections
    "reviewer_id": "test_user",
    "timestamp": "2024-12-07T12:27:00.000Z"
}

print("Testing feedback submission with empty reasons and corrections...")
print(f"\nPayload:")
print(json.dumps(feedback_data, indent=2))

try:
    response = requests.post(
        "http://localhost:8000/api/feedback",
        json=feedback_data,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"\nStatus Code: {response.status_code}")
    print(f"\nResponse:")
    print(json.dumps(response.json(), indent=2))
    
    if response.status_code == 200:
        print("\n✅ SUCCESS! Feedback submitted successfully.")
    else:
        print(f"\n❌ FAILED! Status: {response.status_code}")
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
