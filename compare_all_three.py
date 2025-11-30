#!/usr/bin/env python3
"""
Compare all 3 approaches: Rule-Based + DONUT + Vision LLM.

This script demonstrates the optimal hybrid strategy:
1. Rule-Based: Fast filtering
2. DONUT: Accurate data extraction
3. Vision LLM: Fraud detection

Goal: Determine the best combination for production.
"""

import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional

from app.pipelines.rules import analyze_receipt
from app.pipelines.vision_llm import analyze_receipt_with_vision, DEFAULT_VISION_MODEL

# DONUT is optional
try:
    from app.pipelines.donut_extractor import extract_receipt_with_donut, DONUT_AVAILABLE
except ImportError:
    DONUT_AVAILABLE = False


def analyze_with_all_three(
    image_path: str,
    vision_model: str = DEFAULT_VISION_MODEL,
    use_donut: bool = True,
    parallel: bool = True
) -> Dict[str, Any]:
    """
    Analyze receipt with all 3 approaches and combine results.
    """
    print(f"\n{'='*80}")
    print(f"Complete Analysis: {Path(image_path).name}")
    print(f"{'='*80}\n")
    
    results = {
        "image_path": image_path,
        "rule_based": None,
        "donut": None,
        "vision_llm": None,
        "hybrid_verdict": None,
        "timing": {}
    }
    
    # Run analyses
    if parallel and use_donut and DONUT_AVAILABLE:
        # Run all 3 in parallel
        print("🚀 Running all 3 engines in parallel...\n")
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            start = time.time()
            
            rule_future = executor.submit(analyze_receipt, image_path)
            donut_future = executor.submit(extract_receipt_with_donut, image_path)
            vision_future = executor.submit(analyze_receipt_with_vision, image_path, vision_model)
            
            results["rule_based"] = rule_future.result()
            results["donut"] = donut_future.result()
            results["vision_llm"] = vision_future.result()
            
            results["timing"]["parallel_total"] = time.time() - start
    else:
        # Run sequentially
        print("🔄 Running engines sequentially...\n")
        
        # Rule-based
        start = time.time()
        results["rule_based"] = analyze_receipt(image_path)
        results["timing"]["rule_based"] = time.time() - start
        
        # DONUT
        if use_donut and DONUT_AVAILABLE:
            start = time.time()
            results["donut"] = extract_receipt_with_donut(image_path)
            results["timing"]["donut"] = time.time() - start
        
        # Vision LLM
        start = time.time()
        results["vision_llm"] = analyze_receipt_with_vision(image_path, vision_model)
        results["timing"]["vision_llm"] = time.time() - start
        
        results["timing"]["sequential_total"] = sum(
            v for k, v in results["timing"].items() if k != "parallel_total"
        )
    
    # Print results
    print_analysis_results(results)
    
    # Generate hybrid verdict
    results["hybrid_verdict"] = generate_hybrid_verdict(results)
    
    print("\n" + "="*80)
    print("HYBRID VERDICT")
    print("="*80)
    print_hybrid_verdict(results["hybrid_verdict"])
    
    return results


def print_analysis_results(results: Dict[str, Any]):
    """Print results from all 3 engines."""
    
    # Rule-Based
    print("--- 1. Rule-Based Engine ---")
    rule = results.get("rule_based")
    if rule:
        print(f"Label: {rule.label}")
        print(f"Score: {rule.score:.3f}")
        if results["timing"].get("rule_based"):
            print(f"Time: {results['timing']['rule_based']:.2f}s")
        if rule.reasons:
            print(f"Reasons: {', '.join(rule.reasons[:2])}")
    print()
    
    # DONUT
    print("--- 2. DONUT Extraction ---")
    donut = results.get("donut")
    if donut and not donut.get("error"):
        print(f"Merchant: {donut.get('merchant', 'N/A')}")
        print(f"Total: ${donut.get('total', 'N/A')}")
        print(f"Line Items: {len(donut.get('line_items', []))}")
        if results["timing"].get("donut"):
            print(f"Time: {results['timing']['donut']:.2f}s")
    elif donut and donut.get("error"):
        print(f"Error: {donut.get('message', 'Unknown error')}")
    else:
        print("Not available")
    print()
    
    # Vision LLM
    print("--- 3. Vision LLM ---")
    vision = results.get("vision_llm")
    if vision:
        auth = vision.get("authenticity_assessment", {})
        print(f"Verdict: {auth.get('verdict', 'unknown')}")
        print(f"Confidence: {auth.get('confidence', 0.0):.3f}")
        print(f"Authenticity Score: {auth.get('authenticity_score', 0.0):.3f}")
        if results["timing"].get("vision_llm"):
            print(f"Time: {results['timing']['vision_llm']:.2f}s")
        if auth.get('red_flags'):
            print(f"Red Flags: {', '.join(auth['red_flags'][:2])}")
    print()
    
    # Timing
    print("--- Timing ---")
    if results["timing"].get("parallel_total"):
        print(f"Parallel Total: {results['timing']['parallel_total']:.2f}s")
        print(f"  (All 3 engines ran simultaneously)")
    elif results["timing"].get("sequential_total"):
        print(f"Sequential Total: {results['timing']['sequential_total']:.2f}s")
        print(f"  Rule: {results['timing'].get('rule_based', 0):.2f}s")
        if results["timing"].get("donut"):
            print(f"  DONUT: {results['timing']['donut']:.2f}s")
        if results["timing"].get("vision_llm"):
            print(f"  Vision: {results['timing']['vision_llm']:.2f}s")


def generate_hybrid_verdict(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate final verdict combining all 3 approaches.
    
    Strategy:
    1. Use rule-based for initial assessment
    2. Use DONUT to validate extracted data
    3. Use vision LLM for fraud indicators
    4. Combine all signals for final verdict
    """
    verdict = {
        "final_label": "unknown",
        "confidence": 0.0,
        "reasoning": [],
        "data_quality": "unknown",
        "fraud_indicators": [],
        "recommended_action": "unknown"
    }
    
    rule = results.get("rule_based")
    donut = results.get("donut")
    vision = results.get("vision_llm")
    
    if not rule:
        verdict["reasoning"].append("Rule-based analysis failed")
        return verdict
    
    # Start with rule-based assessment
    rule_label = rule.label
    rule_score = rule.score
    
    # Get vision assessment
    vision_verdict = "unknown"
    vision_confidence = 0.0
    vision_score = 0.5
    
    if vision:
        auth = vision.get("authenticity_assessment", {})
        vision_verdict = auth.get("verdict", "unknown")
        vision_confidence = auth.get("confidence", 0.0)
        vision_score = auth.get("authenticity_score", 0.5)
        
        # Collect fraud indicators
        fraud = vision.get("fraud_detection", {})
        if fraud.get("fraud_indicators"):
            verdict["fraud_indicators"].extend(fraud["fraud_indicators"])
    
    # Check data quality with DONUT
    data_quality_score = 0.5
    if donut and not donut.get("error"):
        # Check if DONUT extracted meaningful data
        has_merchant = bool(donut.get("merchant"))
        has_total = donut.get("total") is not None
        has_items = len(donut.get("line_items", [])) > 0
        
        data_quality_score = sum([has_merchant, has_total, has_items]) / 3
        
        if data_quality_score > 0.7:
            verdict["data_quality"] = "good"
            verdict["reasoning"].append("DONUT extracted structured data successfully")
        elif data_quality_score > 0.3:
            verdict["data_quality"] = "partial"
            verdict["reasoning"].append("DONUT extracted some data")
        else:
            verdict["data_quality"] = "poor"
            verdict["reasoning"].append("DONUT could not extract structured data")
            verdict["fraud_indicators"].append("Poor data structure")
    
    # Decision logic
    signals = []
    
    # Signal 1: Rule-based
    if rule_score < 0.3:
        signals.append(("real", 0.8))
        verdict["reasoning"].append(f"Rule-based: {rule_label} (score: {rule_score:.2f})")
    elif rule_score > 0.7:
        signals.append(("fake", 0.8))
        verdict["reasoning"].append(f"Rule-based: {rule_label} (score: {rule_score:.2f})")
    else:
        signals.append(("suspicious", 0.5))
        verdict["reasoning"].append(f"Rule-based: {rule_label} (score: {rule_score:.2f})")
    
    # Signal 2: Vision LLM
    if vision_verdict == "real" and vision_confidence > 0.7:
        signals.append(("real", vision_confidence))
        verdict["reasoning"].append(f"Vision: {vision_verdict} (confidence: {vision_confidence:.2f})")
    elif vision_verdict == "fake" and vision_confidence > 0.7:
        signals.append(("fake", vision_confidence))
        verdict["reasoning"].append(f"Vision: {vision_verdict} (confidence: {vision_confidence:.2f})")
    elif vision_verdict != "unknown":
        signals.append(("suspicious", 0.5))
        verdict["reasoning"].append(f"Vision: {vision_verdict} (low confidence)")
    
    # Signal 3: Data quality (from DONUT)
    if data_quality_score > 0.7:
        signals.append(("real", 0.6))  # Good structure suggests real
    elif data_quality_score < 0.3:
        signals.append(("suspicious", 0.7))  # Poor structure is suspicious
    
    # Combine signals
    label_scores = {"real": 0.0, "suspicious": 0.0, "fake": 0.0}
    total_confidence = 0.0
    
    for label, conf in signals:
        label_scores[label] += conf
        total_confidence += conf
    
    # Normalize
    if total_confidence > 0:
        for label in label_scores:
            label_scores[label] /= total_confidence
    
    # Final verdict
    final_label = max(label_scores, key=label_scores.get)
    final_confidence = label_scores[final_label]
    
    verdict["final_label"] = final_label
    verdict["confidence"] = final_confidence
    
    # Recommended action
    if final_label == "real" and final_confidence > 0.8:
        verdict["recommended_action"] = "approve"
    elif final_label == "fake" and final_confidence > 0.8:
        verdict["recommended_action"] = "reject"
    else:
        verdict["recommended_action"] = "human_review"
    
    return verdict


def print_hybrid_verdict(verdict: Dict[str, Any]):
    """Print the hybrid verdict in a nice format."""
    print(f"\nFinal Label: {verdict['final_label'].upper()}")
    print(f"Confidence: {verdict['confidence']:.1%}")
    print(f"Data Quality: {verdict['data_quality']}")
    print(f"Recommended Action: {verdict['recommended_action'].replace('_', ' ').title()}")
    
    if verdict['fraud_indicators']:
        print(f"\nFraud Indicators:")
        for indicator in verdict['fraud_indicators'][:3]:
            print(f"  - {indicator}")
    
    print(f"\nReasoning:")
    for reason in verdict['reasoning']:
        print(f"  • {reason}")


def main():
    import sys
    
    # Get receipts to analyze
    if len(sys.argv) > 1:
        receipt_paths = sys.argv[1:]
    else:
        receipt_paths = [
            "data/raw/Gas_bill.jpeg",
            "data/raw/Medplus_sample.jpg",
            "data/raw/Medplus_sample1.jpeg",
        ]
    
    print("=" * 80)
    print("VeriReceipt - Complete 3-Way Analysis")
    print("=" * 80)
    print("\nEngines:")
    print("  1. Rule-Based (OCR + Metadata + Rules)")
    print("  2. DONUT (Document Understanding Transformer)")
    print("  3. Vision LLM (Ollama - Visual Fraud Detection)")
    print()
    
    # Check DONUT availability
    if not DONUT_AVAILABLE:
        print("⚠️  DONUT not available (will use 2 engines only)")
        print("   Install with: pip install transformers torch pillow")
        print()
    
    # Analyze each receipt
    all_results = []
    
    for receipt_path in receipt_paths:
        if not Path(receipt_path).exists():
            print(f"⚠️  Skipping {receipt_path} (not found)\n")
            continue
        
        result = analyze_with_all_three(
            receipt_path,
            use_donut=DONUT_AVAILABLE,
            parallel=True
        )
        all_results.append(result)
    
    # Save results
    output_file = "data/logs/three_way_comparison.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\n✅ Results saved to {output_file}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
