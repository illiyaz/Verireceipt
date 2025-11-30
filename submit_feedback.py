#!/usr/bin/env python3
"""
Script to submit human feedback for receipt analyses.

This allows reviewers to correct the engine's predictions,
which will be used to retrain and improve the ML model.
"""

import requests
import sys
from pathlib import Path


API_BASE_URL = "http://localhost:8080"


def submit_feedback(
    analysis_ref: str,
    given_label: str,
    reviewer_id: str = None,
    comment: str = None,
    reason_code: str = None
):
    """
    Submit feedback to the API.
    
    Args:
        analysis_ref: Reference to the analysis (filename)
        given_label: Corrected label (real/suspicious/fake)
        reviewer_id: Email or ID of reviewer
        comment: Free-text explanation
        reason_code: Structured reason code
    """
    payload = {
        "analysis_ref": analysis_ref,
        "given_label": given_label,
        "reviewer_id": reviewer_id,
        "comment": comment,
        "reason_code": reason_code,
    }
    
    response = requests.post(f"{API_BASE_URL}/feedback", json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Feedback submitted successfully!")
        print(f"   Reference: {result['feedback_ref']}")
        print(f"   Message: {result['message']}")
        return True
    else:
        print(f"❌ Error submitting feedback: {response.status_code}")
        print(f"   {response.text}")
        return False


def interactive_feedback():
    """
    Interactive mode to review and provide feedback on receipts.
    """
    print("=" * 80)
    print("VeriReceipt - Human Feedback Submission")
    print("=" * 80)
    print()
    
    # Check if API is running
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        if response.status_code != 200:
            print("❌ API is not responding. Please start the API server first:")
            print("   python run_api.py")
            return
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Please start the API server first:")
        print("   python run_api.py")
        return
    
    print("✅ Connected to VeriReceipt API")
    print()
    
    # Get analysis reference
    print("Enter the receipt filename (e.g., Gas_bill.jpeg):")
    analysis_ref = input("> ").strip()
    
    if not analysis_ref:
        print("❌ Analysis reference is required")
        return
    
    # Get corrected label
    print("\nWhat is the CORRECT label for this receipt?")
    print("  1. real")
    print("  2. suspicious")
    print("  3. fake")
    choice = input("> ").strip()
    
    label_map = {"1": "real", "2": "suspicious", "3": "fake"}
    given_label = label_map.get(choice, choice.lower())
    
    if given_label not in ["real", "suspicious", "fake"]:
        print(f"❌ Invalid label: {given_label}")
        return
    
    # Get reviewer ID
    print("\nYour email or ID (optional, press Enter to skip):")
    reviewer_id = input("> ").strip() or None
    
    # Get comment
    print("\nWhy did you correct this? (optional, press Enter to skip):")
    comment = input("> ").strip() or None
    
    # Get reason code
    print("\nReason code (optional, e.g., FAKE_MERCHANT, EDITED_TOTAL, press Enter to skip):")
    reason_code = input("> ").strip() or None
    
    print()
    print("Submitting feedback...")
    
    success = submit_feedback(
        analysis_ref=analysis_ref,
        given_label=given_label,
        reviewer_id=reviewer_id,
        comment=comment,
        reason_code=reason_code
    )
    
    if success:
        print()
        print("💡 Tip: After collecting enough feedback, retrain the model with:")
        print("   python -m app.ml.training")


def batch_feedback_from_csv(csv_file: str):
    """
    Submit feedback in batch from a CSV file.
    
    CSV format:
    analysis_ref,given_label,reviewer_id,comment,reason_code
    """
    import csv
    
    csv_path = Path(csv_file)
    if not csv_path.exists():
        print(f"❌ File not found: {csv_file}")
        return
    
    print(f"Reading feedback from {csv_file}...")
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        count = 0
        errors = 0
        
        for row in reader:
            success = submit_feedback(
                analysis_ref=row['analysis_ref'],
                given_label=row['given_label'],
                reviewer_id=row.get('reviewer_id'),
                comment=row.get('comment'),
                reason_code=row.get('reason_code')
            )
            
            if success:
                count += 1
            else:
                errors += 1
    
    print()
    print(f"✅ Submitted {count} feedback entries")
    if errors > 0:
        print(f"❌ {errors} errors")


def main():
    if len(sys.argv) > 1:
        # Batch mode from CSV
        csv_file = sys.argv[1]
        batch_feedback_from_csv(csv_file)
    else:
        # Interactive mode
        interactive_feedback()


if __name__ == "__main__":
    main()
