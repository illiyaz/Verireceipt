#!/usr/bin/env python3
"""
Live integration test with real receipt files.
Tests the complete pipeline including:
- Rule-based analysis with confidence-aware weighting
- Audit trail generation
- Extraction confidence tracking
- CSV and database persistence
"""

import sys
import json
import requests
from pathlib import Path
from typing import Dict, Any

# API endpoint
API_BASE = "http://localhost:8000"

def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def test_health_check():
    """Test API health endpoint."""
    print_section("Health Check")
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        if response.status_code == 200:
            print("✅ API Server is healthy")
            return True
        else:
            print(f"❌ API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API server. Is it running?")
        print(f"   Expected at: {API_BASE}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def analyze_receipt(file_path: str, engine: str = "rule_based") -> Dict[str, Any]:
    """Analyze a single receipt."""
    print(f"\n📄 Analyzing: {Path(file_path).name}")
    print(f"   Engine: {engine}")
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (Path(file_path).name, f)}
            response = requests.post(
                f"{API_BASE}/analyze",
                files=files,
                timeout=60
            )
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Status: {response.status_code}")
            return result
        else:
            print(f"   ❌ Status: {response.status_code}")
            print(f"   Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

def print_decision_summary(result: Dict[str, Any]):
    """Print a formatted summary of the decision."""
    if not result:
        return
    
    # API returns flat response, not nested under 'decision'
    decision = result
    
    print(f"\n   🎯 Decision Summary:")
    print(f"      Label: {decision.get('label', 'N/A')}")
    print(f"      Score: {decision.get('score', 0):.2f}")
    conf_score = decision.get('extraction_confidence_score')
    conf_level = decision.get('extraction_confidence_level', 'N/A')
    if conf_score is not None:
        print(f"      Confidence: {conf_level} ({conf_score:.2f})")
    else:
        print(f"      Confidence: {conf_level}")
    
    # Audit events
    audit_events = decision.get('audit_events', [])
    if audit_events:
        print(f"\n   📋 Audit Events: {len(audit_events)} events")
        
        # Count by severity
        severities = {}
        for event in audit_events:
            sev = event.get('severity', 'UNKNOWN')
            severities[sev] = severities.get(sev, 0) + 1
        
        for sev, count in sorted(severities.items()):
            print(f"      {sev}: {count}")
        
        # Show first 3 events
        print(f"\n   🔍 Sample Events:")
        for i, event in enumerate(audit_events[:3], 1):
            print(f"      {i}. [{event.get('severity', 'N/A')}] {event.get('code', 'N/A')}")
            print(f"         {event.get('message', 'N/A')}")
    
    # Reasons
    reasons = decision.get('reasons', [])
    if reasons:
        print(f"\n   ⚠️  Reasons: {len(reasons)} total")
        for i, reason in enumerate(reasons[:3], 1):
            print(f"      {i}. {reason[:80]}...")
    
    # Version info
    print(f"\n   📌 Version Info:")
    print(f"      Rule Version: {decision.get('rule_version', 'N/A')}")
    print(f"      Policy: {decision.get('policy_name', 'N/A')}")
    print(f"      Engine: {decision.get('engine_version', 'N/A')}")

def test_hybrid_analysis(file_path: str) -> Dict[str, Any]:
    """Test hybrid analysis with all 5 engines."""
    print(f"\n🔬 Hybrid Analysis: {Path(file_path).name}")
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (Path(file_path).name, f)}
            response = requests.post(
                f"{API_BASE}/analyze/hybrid",
                files=files,
                timeout=120
            )
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Status: {response.status_code}")
            
            # Print engine results
            print(f"\n   🤖 Engine Results:")
            
            engines = ['vision_llm', 'layoutlm', 'donut', 'donut_receipt', 'rule_based']
            for engine in engines:
                if engine in result:
                    eng_result = result[engine]
                    if isinstance(eng_result, dict):
                        label = eng_result.get('label') or eng_result.get('verdict', 'N/A')
                        score = eng_result.get('score') or eng_result.get('confidence', 0)
                        print(f"      {engine:15s}: {label:10s} (score={score:.2f})")
            
            # Ensemble verdict
            if 'ensemble_verdict' in result:
                verdict = result['ensemble_verdict']
                print(f"\n   🎯 Ensemble Verdict:")
                print(f"      Final Label: {verdict.get('final_label', 'N/A')}")
                print(f"      Confidence: {verdict.get('confidence', 0):.2f}")
                print(f"      Action: {verdict.get('recommended_action', 'N/A')}")
                print(f"      Agreement: {verdict.get('agreement_score', 0):.2f}")
            
            return result
        else:
            print(f"   ❌ Status: {response.status_code}")
            print(f"   Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

def test_feedback_submission(file_path: str):
    """Test feedback submission."""
    print_section("Feedback Submission Test")
    
    feedback = {
        "file_path": file_path,
        "user_verdict": "real",
        "confidence": "high",
        "notes": "Verified with merchant - legitimate receipt",
        "reviewer_id": "test_reviewer"
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/feedback",
            json=feedback,
            timeout=10
        )
        
        if response.status_code == 200:
            print("✅ Feedback submitted successfully")
            result = response.json()
            print(f"   Message: {result.get('message', 'N/A')}")
        else:
            print(f"❌ Status: {response.status_code}")
            print(f"   Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def run_live_tests():
    """Run live integration tests."""
    print("\n" + "="*80)
    print("🧪 VeriReceipt Live Integration Tests")
    print("="*80)
    
    # Check API health
    if not test_health_check():
        print("\n❌ Cannot proceed - API server not available")
        return 1
    
    # Test files
    data_dir = Path("/Users/LENOVO/Documents/Projects/VeriReceipt/data/raw")
    
    test_files = [
        "Gas_bill.jpeg",
        "Medplus_sample.jpg",
        "Pizza.jpg",
    ]
    
    # Test 1: Rule-based analysis
    print_section("TEST 1: Rule-Based Analysis")
    for file_name in test_files:
        file_path = data_dir / file_name
        if file_path.exists():
            result = analyze_receipt(str(file_path))
            if result:
                print_decision_summary(result)
        else:
            print(f"⚠️  File not found: {file_name}")
    
    # Test 2: Hybrid analysis (first file only - takes longer)
    print_section("TEST 2: Hybrid Analysis (All 5 Engines)")
    first_file = data_dir / test_files[0]
    if first_file.exists():
        hybrid_result = test_hybrid_analysis(str(first_file))
    
    # Test 3: Feedback submission
    test_feedback_submission(str(first_file))
    
    # Test 4: Check CSV logs
    print_section("TEST 4: Verify CSV Logging")
    csv_path = Path("/Users/LENOVO/Documents/Projects/VeriReceipt/data/logs/decisions.csv")
    if csv_path.exists():
        print(f"✅ CSV log exists: {csv_path}")
        
        # Read last few lines
        with open(csv_path, 'r') as f:
            lines = f.readlines()
            print(f"   Total entries: {len(lines) - 1}")  # -1 for header
            
            if len(lines) > 1:
                # Show header
                header = lines[0].strip().split(',')
                print(f"\n   📊 CSV Columns ({len(header)} total):")
                
                # Show new columns
                new_cols = [
                    'policy_name', 'decision_id', 'created_at', 'finalized',
                    'extraction_confidence_score', 'extraction_confidence_level',
                    'normalized_total', 'currency'
                ]
                
                for col in new_cols:
                    if col in header:
                        print(f"      ✅ {col}")
                    else:
                        print(f"      ❌ {col} (missing)")
    else:
        print(f"⚠️  CSV log not found: {csv_path}")
    
    print("\n" + "="*80)
    print("✅ Live Integration Tests Complete!")
    print("="*80)
    
    return 0

if __name__ == "__main__":
    sys.exit(run_live_tests())
