#!/usr/bin/env python3
"""
Simple test client for VeriReceipt API.

Demonstrates how to use the API endpoints.
"""

import requests
from pathlib import Path


API_BASE_URL = "http://localhost:8080"


def test_health():
    """Test health check endpoint."""
    print("Testing /health endpoint...")
    response = requests.get(f"{API_BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")


def test_analyze_receipt(file_path: str):
    """Test single receipt analysis."""
    print(f"Analyzing receipt: {file_path}")
    
    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f, "image/jpeg")}
        response = requests.post(f"{API_BASE_URL}/analyze", files=files)
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Label: {result['label']}")
        print(f"Score: {result['score']:.2f}")
        print(f"Processing Time: {result.get('processing_time_ms', 'N/A')} ms")
        print("Reasons:")
        for reason in result['reasons']:
            print(f"  • {reason}")
        if result.get('minor_notes'):
            print("Minor Notes:")
            for note in result['minor_notes']:
                print(f"  • {note}")
    else:
        print(f"Error: {response.text}")
    print()


def test_stats():
    """Test statistics endpoint."""
    print("Testing /stats endpoint...")
    response = requests.get(f"{API_BASE_URL}/stats")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        stats = response.json()
        print(f"Total Analyses: {stats['total_analyses']}")
        print(f"Real: {stats['real_count']}")
        print(f"Suspicious: {stats['suspicious_count']}")
        print(f"Fake: {stats['fake_count']}")
        print(f"Average Score: {stats['avg_score']:.3f}")
    else:
        print(f"Response: {response.text}")
    print()


def main():
    print("=" * 80)
    print("VeriReceipt API Test Client")
    print("=" * 80)
    print()
    
    # Test health
    test_health()
    
    # Test analyzing receipts
    receipts = [
        "data/raw/Gas_bill.jpeg",
        "data/raw/Medplus_sample.jpg",
        "data/raw/Medplus_sample1.jpeg",
    ]
    
    for receipt in receipts:
        if Path(receipt).exists():
            test_analyze_receipt(receipt)
        else:
            print(f"⚠️  Receipt not found: {receipt}\n")
    
    # Test stats
    test_stats()
    
    print("=" * 80)
    print("✅ API testing complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
