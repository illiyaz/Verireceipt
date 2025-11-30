#!/usr/bin/env python3
"""
Compare Rule-Based Engine vs Vision LLM Analysis.

This script runs both approaches in parallel and compares results:
1. Rule-based engine (OCR + metadata + rules)
2. Vision LLM (Ollama with LLaVA/Qwen)

Goal: Determine which approach is more effective for fraud detection.
"""

import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any

from app.pipelines.rules import analyze_receipt
from app.pipelines.vision_llm import (
    analyze_receipt_with_vision,
    get_hybrid_verdict,
    DEFAULT_VISION_MODEL
)


def run_rule_based_analysis(image_path: str) -> Dict[str, Any]:
    """Run rule-based analysis and time it."""
    start = time.time()
    
    try:
        decision = analyze_receipt(image_path)
        elapsed = time.time() - start
        
        return {
            "success": True,
            "label": decision.label,
            "score": decision.score,
            "reasons": decision.reasons,
            "minor_notes": decision.minor_notes,
            "elapsed_seconds": elapsed,
            "features": {
                "text_features": decision.features.text_features,
                "file_features": decision.features.file_features,
                "layout_features": decision.features.layout_features,
                "forensic_features": decision.features.forensic_features,
            }
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed
        }


def run_vision_analysis(image_path: str, model: str = DEFAULT_VISION_MODEL) -> Dict[str, Any]:
    """Run vision LLM analysis and time it."""
    start = time.time()
    
    try:
        results = analyze_receipt_with_vision(image_path, model)
        elapsed = time.time() - start
        
        auth = results.get("authenticity_assessment", {})
        
        return {
            "success": True,
            "verdict": auth.get("verdict", "unknown"),
            "confidence": auth.get("confidence", 0.0),
            "authenticity_score": auth.get("authenticity_score", 0.5),
            "reasoning": auth.get("reasoning", ""),
            "red_flags": auth.get("red_flags", []),
            "extracted_data": results.get("extracted_data", {}),
            "fraud_detection": results.get("fraud_detection", {}),
            "elapsed_seconds": elapsed,
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed
        }


def compare_single_receipt(
    image_path: str,
    vision_model: str = DEFAULT_VISION_MODEL,
    parallel: bool = True
) -> Dict[str, Any]:
    """
    Compare rule-based and vision analysis for a single receipt.
    
    Args:
        image_path: Path to receipt image
        vision_model: Ollama vision model to use
        parallel: Run both analyses in parallel (faster)
    
    Returns:
        Comparison results
    """
    print(f"\n{'='*80}")
    print(f"Analyzing: {Path(image_path).name}")
    print(f"{'='*80}\n")
    
    if parallel:
        # Run both in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            rule_future = executor.submit(run_rule_based_analysis, image_path)
            vision_future = executor.submit(run_vision_analysis, image_path, vision_model)
            
            rule_results = rule_future.result()
            vision_results = vision_future.result()
    else:
        # Run sequentially
        rule_results = run_rule_based_analysis(image_path)
        vision_results = run_vision_analysis(image_path, vision_model)
    
    # Print results
    print("--- Rule-Based Engine ---")
    if rule_results["success"]:
        print(f"Label: {rule_results['label']}")
        print(f"Score: {rule_results['score']:.3f}")
        print(f"Time: {rule_results['elapsed_seconds']:.2f}s")
        if rule_results['reasons']:
            print(f"Reasons: {', '.join(rule_results['reasons'][:3])}")
    else:
        print(f"Error: {rule_results['error']}")
    
    print("\n--- Vision LLM ---")
    if vision_results["success"]:
        print(f"Verdict: {vision_results['verdict']}")
        print(f"Confidence: {vision_results['confidence']:.3f}")
        print(f"Authenticity Score: {vision_results['authenticity_score']:.3f}")
        print(f"Time: {vision_results['elapsed_seconds']:.2f}s")
        print(f"Reasoning: {vision_results['reasoning'][:100]}...")
        if vision_results['red_flags']:
            print(f"Red Flags: {', '.join(vision_results['red_flags'][:3])}")
    else:
        print(f"Error: {vision_results['error']}")
    
    # Compare
    if rule_results["success"] and vision_results["success"]:
        print("\n--- Comparison ---")
        
        # Agreement
        rule_label = rule_results['label']
        vision_verdict = vision_results['verdict']
        
        if rule_label == vision_verdict:
            print(f"✅ Agreement: Both say '{rule_label}'")
        else:
            print(f"⚠️  Disagreement: Rules say '{rule_label}', Vision says '{vision_verdict}'")
        
        # Speed
        speedup = vision_results['elapsed_seconds'] / rule_results['elapsed_seconds']
        if speedup > 1:
            print(f"⚡ Rule-based is {speedup:.1f}x faster")
        else:
            print(f"⚡ Vision is {1/speedup:.1f}x faster")
        
        # Hybrid verdict
        print("\n--- Hybrid Verdict ---")
        hybrid = get_hybrid_verdict(
            {"label": rule_label, "score": rule_results['score']},
            {"authenticity_assessment": {
                "verdict": vision_verdict,
                "confidence": vision_results['confidence'],
                "authenticity_score": vision_results['authenticity_score']
            }}
        )
        
        print(f"Final Label: {hybrid['final_label']}")
        print(f"Confidence: {hybrid['final_confidence']:.3f}")
        print(f"Reasoning: {hybrid['reasoning']}")
        print(f"Agreement Score: {hybrid['agreement_score']:.3f}")
    
    print(f"\n{'='*80}\n")
    
    return {
        "image_path": image_path,
        "rule_based": rule_results,
        "vision_llm": vision_results,
        "hybrid": hybrid if rule_results["success"] and vision_results["success"] else None
    }


def compare_multiple_receipts(
    receipt_paths: list,
    vision_model: str = DEFAULT_VISION_MODEL,
    output_file: str = "data/logs/engine_comparison.json"
):
    """
    Compare both engines on multiple receipts and generate report.
    """
    print("=" * 80)
    print("VeriReceipt - Engine Comparison")
    print("=" * 80)
    print(f"\nRule-Based Engine vs Vision LLM ({vision_model})")
    print(f"Receipts to analyze: {len(receipt_paths)}\n")
    
    results = []
    
    for receipt_path in receipt_paths:
        if not Path(receipt_path).exists():
            print(f"⚠️  Skipping {receipt_path} (not found)")
            continue
        
        result = compare_single_receipt(receipt_path, vision_model)
        results.append(result)
    
    # Generate summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80 + "\n")
    
    successful_comparisons = [r for r in results if r["rule_based"]["success"] and r["vision_llm"]["success"]]
    
    if not successful_comparisons:
        print("No successful comparisons to summarize.")
        return
    
    # Agreement rate
    agreements = sum(1 for r in successful_comparisons 
                     if r["rule_based"]["label"] == r["vision_llm"]["verdict"])
    agreement_rate = agreements / len(successful_comparisons)
    
    print(f"Total Receipts: {len(successful_comparisons)}")
    print(f"Agreement Rate: {agreement_rate:.1%} ({agreements}/{len(successful_comparisons)})")
    print()
    
    # Average times
    avg_rule_time = sum(r["rule_based"]["elapsed_seconds"] for r in successful_comparisons) / len(successful_comparisons)
    avg_vision_time = sum(r["vision_llm"]["elapsed_seconds"] for r in successful_comparisons) / len(successful_comparisons)
    
    print(f"Average Time - Rule-Based: {avg_rule_time:.2f}s")
    print(f"Average Time - Vision LLM: {avg_vision_time:.2f}s")
    print(f"Speed Ratio: {avg_vision_time/avg_rule_time:.1f}x")
    print()
    
    # Label distribution
    print("Rule-Based Labels:")
    rule_labels = {}
    for r in successful_comparisons:
        label = r["rule_based"]["label"]
        rule_labels[label] = rule_labels.get(label, 0) + 1
    for label, count in rule_labels.items():
        print(f"  {label}: {count}")
    
    print("\nVision LLM Verdicts:")
    vision_verdicts = {}
    for r in successful_comparisons:
        verdict = r["vision_llm"]["verdict"]
        vision_verdicts[verdict] = vision_verdicts.get(verdict, 0) + 1
    for verdict, count in vision_verdicts.items():
        print(f"  {verdict}: {count}")
    
    print("\nHybrid Verdicts:")
    hybrid_labels = {}
    for r in successful_comparisons:
        if r.get("hybrid"):
            label = r["hybrid"]["final_label"]
            hybrid_labels[label] = hybrid_labels.get(label, 0) + 1
    for label, count in hybrid_labels.items():
        print(f"  {label}: {count}")
    
    # Save results
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump({
            "summary": {
                "total_receipts": len(successful_comparisons),
                "agreement_rate": agreement_rate,
                "avg_rule_time": avg_rule_time,
                "avg_vision_time": avg_vision_time,
                "rule_labels": rule_labels,
                "vision_verdicts": vision_verdicts,
                "hybrid_labels": hybrid_labels,
            },
            "detailed_results": results
        }, f, indent=2)
    
    print(f"\n✅ Results saved to {output_path}")
    print()
    print("=" * 80)


def main():
    import sys
    
    # Get receipts to analyze
    if len(sys.argv) > 1:
        # Specific files provided
        receipt_paths = sys.argv[1:]
    else:
        # Use sample receipts
        receipt_paths = [
            "data/raw/Gas_bill.jpeg",
            "data/raw/Medplus_sample.jpg",
            "data/raw/Medplus_sample1.jpeg",
        ]
    
    # Ask which vision model to use
    print("Available vision models:")
    print("1. llama3.2-vision:latest (7.9 GB, faster)")
    print("2. llama3.2-vision:11b (21 GB, more accurate)")
    print("3. qwen2.5vl:32b (21 GB, most accurate)")
    print()
    
    choice = input("Select model (1-3) or press Enter for default [1]: ").strip()
    
    model_map = {
        "1": "llama3.2-vision:latest",
        "2": "llama3.2-vision:11b",
        "3": "qwen2.5vl:32b",
        "": "llama3.2-vision:latest"
    }
    
    vision_model = model_map.get(choice, "llama3.2-vision:latest")
    
    print(f"\nUsing vision model: {vision_model}\n")
    
    # Run comparison
    compare_multiple_receipts(receipt_paths, vision_model)


if __name__ == "__main__":
    main()
