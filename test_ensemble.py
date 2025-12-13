#!/usr/bin/env python
"""Test ensemble system directly to see errors"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.pipelines.ensemble import get_ensemble
from app.pipelines.rules import analyze_receipt

# Simulate results from engines
results = {
    'rule_based': {
        'label': 'suspicious',
        'score': 0.5,
        'reasons': ['No total found'],
        'minor_notes': []
    },
    'donut': {
        'total': None,
        'merchant': None
    },
    'donut_receipt': {
        'error': 'Failed'
    },
    'layoutlm': {
        'total': '68.89',
        'merchant': 'Popeyes',
        'date': '11/20/2019'
    },
    'vision_llm': {
        'verdict': 'real',
        'confidence': 0.8,
        'reasoning': 'Looks real'
    }
}

print("=" * 60)
print("Testing Ensemble System")
print("=" * 60)

try:
    print("\n1. Creating ensemble instance...")
    ensemble = get_ensemble()
    print("✅ Ensemble created")
    
    print("\n2. Converging extraction data...")
    converged_data = ensemble.converge_extraction(results)
    print(f"✅ Converged data:")
    print(f"   Total: {converged_data.get('total')}")
    print(f"   Merchant: {converged_data.get('merchant')}")
    print(f"   Date: {converged_data.get('date')}")
    
    print("\n3. Testing Rule-Based with converged data...")
    test_file = "data/raw/Popeyes-download.png"
    if os.path.exists(test_file):
        print(f"   Using file: {test_file}")
        enhanced_decision = analyze_receipt(
            test_file,
            extracted_total=converged_data.get('total'),
            extracted_merchant=converged_data.get('merchant'),
            extracted_date=converged_data.get('date')
        )
        print(f"✅ Rule-Based enhanced:")
        print(f"   Label: {enhanced_decision.label}")
        print(f"   Score: {enhanced_decision.score}")
        print(f"   Reasons: {enhanced_decision.reasons[:2]}")  # First 2 reasons
    else:
        print(f"⚠️ Test file not found: {test_file}")
    
    print("\n4. Building ensemble verdict...")
    ensemble_verdict = ensemble.build_ensemble_verdict(results, converged_data)
    print(f"✅ Ensemble verdict:")
    print(f"   Label: {ensemble_verdict['final_label']}")
    print(f"   Confidence: {ensemble_verdict['confidence']}")
    print(f"   Action: {ensemble_verdict['recommended_action']}")
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED - Ensemble is working!")
    print("=" * 60)
    
except Exception as e:
    import traceback
    print("\n" + "=" * 60)
    print("❌ ERROR DETECTED")
    print("=" * 60)
    print(f"\nError: {e}")
    print(f"\nFull traceback:")
    print(traceback.format_exc())
    sys.exit(1)
