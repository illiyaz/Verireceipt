"""
Vision LLM Feature Extraction using Ollama.

This module uses local vision models (LLaVA, Qwen2.5-VL, etc.) to extract
receipt features in parallel with the rule-based engine.

Advantages:
- Understands visual context (logos, layouts, fonts)
- Detects subtle editing artifacts
- Extracts structured data from images
- No API costs (runs locally)
"""

import json
import base64
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from PIL import Image
import io


OLLAMA_API_URL = "http://localhost:11434/api/generate"
DEFAULT_VISION_MODEL = "llama3.2-vision:latest"  # Smaller, faster model


def encode_image_to_base64(image_path: str) -> str:
    """Encode image to base64 for Ollama API."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def query_vision_model(
    image_path: str,
    prompt: str,
    model: str = DEFAULT_VISION_MODEL,
    temperature: float = 0.1
) -> str:
    """
    Query Ollama vision model with an image and prompt.
    
    Args:
        image_path: Path to receipt image
        prompt: Question/instruction for the model
        model: Ollama model name (must be a vision model)
        temperature: Lower = more deterministic (0.0-1.0)
    
    Returns:
        Model response as string
    """
    # Encode image
    image_b64 = encode_image_to_base64(image_path)
    
    # Prepare request
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "temperature": temperature,
        "options": {
            "num_predict": 500,  # Max tokens
        }
    }
    
    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "").strip()
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Ollama API error: {e}")
        return ""


def extract_receipt_data_with_vision(image_path: str, model: str = DEFAULT_VISION_MODEL) -> Dict[str, Any]:
    """
    Extract structured receipt data using vision LLM.
    
    This asks the model to extract:
    - Merchant name
    - Date
    - Total amount
    - Line items
    - Payment method
    """
    prompt = """Analyze this receipt image and extract the following information in JSON format:

{
  "merchant_name": "name of the business",
  "date": "transaction date (YYYY-MM-DD format if possible)",
  "total_amount": "total amount as a number",
  "currency": "currency code (USD, EUR, etc.)",
  "line_items": ["item 1", "item 2", ...],
  "payment_method": "cash, card, etc.",
  "receipt_number": "receipt or invoice number if visible"
}

If any field is not visible or unclear, use null. Only return the JSON, no other text."""

    response = query_vision_model(image_path, prompt, model)
    
    # Try to parse JSON response
    try:
        # Extract JSON from response (model might add extra text)
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = response[json_start:json_end]
            data = json.loads(json_str)
            return data
        else:
            print(f"⚠️  No JSON found in response: {response[:100]}")
            return {}
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON parse error: {e}")
        print(f"   Response: {response[:200]}")
        return {}


def detect_fraud_indicators_with_vision(image_path: str, model: str = DEFAULT_VISION_MODEL) -> Dict[str, Any]:
    """
    Ask vision model to detect fraud indicators.
    
    This leverages the model's visual understanding to detect:
    - Editing artifacts
    - Font inconsistencies
    - Layout anomalies
    - Suspicious patterns
    """
    prompt = """Analyze this receipt image for signs of fraud or manipulation. Look for:

1. Font inconsistencies (different fonts, sizes, or styles)
2. Alignment issues (misaligned text or numbers)
3. Editing artifacts (pixelation, blurring, color mismatches)
4. Suspicious elements (watermarks like "Canva", "Template", editing software traces)
5. Layout anomalies (unusual spacing, overlapping text)
6. Quality issues (parts of image look different quality)

Respond in JSON format:
{
  "is_suspicious": true/false,
  "confidence": 0.0-1.0,
  "fraud_indicators": ["indicator 1", "indicator 2", ...],
  "visual_anomalies": ["anomaly 1", "anomaly 2", ...],
  "overall_assessment": "brief explanation"
}

Only return the JSON, no other text."""

    response = query_vision_model(image_path, prompt, model, temperature=0.2)
    
    # Parse JSON
    try:
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = response[json_start:json_end]
            data = json.loads(json_str)
            return data
        else:
            return {"is_suspicious": False, "confidence": 0.0, "fraud_indicators": []}
    except json.JSONDecodeError:
        return {"is_suspicious": False, "confidence": 0.0, "fraud_indicators": []}


def assess_receipt_authenticity(image_path: str, model: str = DEFAULT_VISION_MODEL) -> Dict[str, Any]:
    """
    High-level authenticity assessment using vision model.
    
    This asks the model to make an overall judgment about the receipt.
    """
    prompt = """You are an expert at detecting fake receipts. Analyze this receipt image and determine if it appears authentic or fake.

Consider:
- Does it look like a real printed receipt or a digital creation?
- Are there signs of editing or manipulation?
- Does the layout match typical receipts from real businesses?
- Are there any suspicious watermarks or artifacts?
- Does the text quality look consistent?

Respond in JSON format:
{
  "verdict": "real" or "fake" or "suspicious",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation of your assessment",
  "red_flags": ["flag 1", "flag 2", ...],
  "authenticity_score": 0.0-1.0 (0=definitely fake, 1=definitely real)
}

Only return the JSON, no other text."""

    response = query_vision_model(image_path, prompt, model, temperature=0.1)
    
    # Parse JSON
    try:
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = response[json_start:json_end]
            data = json.loads(json_str)
            return data
        else:
            return {"verdict": "unknown", "confidence": 0.0, "reasoning": "Failed to parse response"}
    except json.JSONDecodeError:
        return {"verdict": "unknown", "confidence": 0.0, "reasoning": "Failed to parse response"}


def analyze_receipt_with_vision(
    image_path: str,
    model: str = DEFAULT_VISION_MODEL,
    extract_data: bool = True,
    detect_fraud: bool = True,
    assess_authenticity: bool = True
) -> Dict[str, Any]:
    """
    Complete vision-based receipt analysis.
    
    Args:
        image_path: Path to receipt image
        model: Ollama vision model to use
        extract_data: Extract structured data
        detect_fraud: Detect fraud indicators
        assess_authenticity: Overall authenticity assessment
    
    Returns:
        Dictionary with all vision analysis results
    """
    results = {
        "model": model,
        "image_path": image_path,
        "extracted_data": None,
        "fraud_detection": None,
        "authenticity_assessment": None,
    }
    
    print(f"🔍 Analyzing with vision model: {model}")
    
    if extract_data:
        print("   Extracting receipt data...")
        results["extracted_data"] = extract_receipt_data_with_vision(image_path, model)
    
    if detect_fraud:
        print("   Detecting fraud indicators...")
        results["fraud_detection"] = detect_fraud_indicators_with_vision(image_path, model)
    
    if assess_authenticity:
        print("   Assessing authenticity...")
        results["authenticity_assessment"] = assess_receipt_authenticity(image_path, model)
    
    return results


def compare_with_ocr_features(vision_results: Dict, ocr_features: Dict) -> Dict[str, Any]:
    """
    Compare vision model results with OCR-based features.
    
    This helps identify discrepancies and improve accuracy.
    """
    comparison = {
        "data_match": {},
        "discrepancies": [],
        "confidence_boost": 0.0,
    }
    
    # Compare extracted data
    vision_data = vision_results.get("extracted_data", {})
    
    if vision_data and ocr_features:
        # Compare merchant
        vision_merchant = vision_data.get("merchant_name", "").lower()
        ocr_merchant = ocr_features.get("text_features", {}).get("merchant_candidate", "").lower()
        
        if vision_merchant and ocr_merchant:
            if vision_merchant in ocr_merchant or ocr_merchant in vision_merchant:
                comparison["data_match"]["merchant"] = True
            else:
                comparison["data_match"]["merchant"] = False
                comparison["discrepancies"].append(f"Merchant mismatch: Vision={vision_merchant}, OCR={ocr_merchant}")
        
        # Compare total amount
        vision_total = vision_data.get("total_amount")
        ocr_total = ocr_features.get("text_features", {}).get("total_amount")
        
        if vision_total and ocr_total:
            try:
                vision_total_num = float(str(vision_total).replace("$", "").replace(",", ""))
                ocr_total_num = float(str(ocr_total))
                
                if abs(vision_total_num - ocr_total_num) < 0.01:
                    comparison["data_match"]["total"] = True
                else:
                    comparison["data_match"]["total"] = False
                    comparison["discrepancies"].append(f"Total mismatch: Vision={vision_total}, OCR={ocr_total}")
            except (ValueError, TypeError):
                pass
    
    # Calculate confidence boost
    matches = sum(1 for v in comparison["data_match"].values() if v)
    total_checks = len(comparison["data_match"])
    
    if total_checks > 0:
        comparison["confidence_boost"] = matches / total_checks
    
    return comparison


def get_hybrid_verdict(
    rule_based_decision: Dict,
    vision_results: Dict
) -> Dict[str, Any]:
    """
    Combine rule-based and vision-based analysis for final verdict.
    
    Strategy:
    1. If both agree → high confidence
    2. If both disagree → flag for human review
    3. Use vision as tiebreaker for suspicious cases
    """
    rule_label = rule_based_decision.get("label", "unknown")
    rule_score = rule_based_decision.get("score", 0.5)
    
    vision_auth = vision_results.get("authenticity_assessment", {})
    vision_verdict = vision_auth.get("verdict", "unknown")
    vision_confidence = vision_auth.get("confidence", 0.0)
    vision_score = vision_auth.get("authenticity_score", 0.5)
    
    # Map labels
    label_map = {
        "real": 0.0,
        "suspicious": 0.5,
        "fake": 1.0,
        "unknown": 0.5
    }
    
    rule_numeric = label_map.get(rule_label, 0.5)
    vision_numeric = 1.0 - vision_score  # Invert (0=real, 1=fake)
    
    # Calculate agreement
    agreement = 1.0 - abs(rule_numeric - vision_numeric)
    
    # Hybrid decision
    if agreement > 0.7:
        # Both agree
        final_label = rule_label
        final_confidence = min(1.0, (1.0 + vision_confidence) / 2)
        reasoning = "Rule-based and vision models agree"
    elif rule_score < 0.3 and vision_score > 0.7:
        # Rules say real, vision says real → high confidence real
        final_label = "real"
        final_confidence = 0.9
        reasoning = "Both models strongly indicate authentic receipt"
    elif rule_score > 0.7 and vision_score < 0.3:
        # Rules say fake, vision says fake → high confidence fake
        final_label = "fake"
        final_confidence = 0.9
        reasoning = "Both models strongly indicate fraudulent receipt"
    else:
        # Disagreement → flag for review
        final_label = "suspicious"
        final_confidence = 0.5
        reasoning = "Rule-based and vision models disagree - needs human review"
    
    return {
        "final_label": final_label,
        "final_confidence": final_confidence,
        "reasoning": reasoning,
        "agreement_score": agreement,
        "rule_based": {"label": rule_label, "score": rule_score},
        "vision_based": {"verdict": vision_verdict, "score": vision_score, "confidence": vision_confidence},
    }


# Convenience function for testing
def quick_vision_check(image_path: str, model: str = DEFAULT_VISION_MODEL):
    """Quick vision check for testing."""
    print(f"\n{'='*80}")
    print(f"Vision Analysis: {Path(image_path).name}")
    print(f"Model: {model}")
    print(f"{'='*80}\n")
    
    results = analyze_receipt_with_vision(image_path, model)
    
    print("\n--- Extracted Data ---")
    print(json.dumps(results.get("extracted_data", {}), indent=2))
    
    print("\n--- Fraud Detection ---")
    print(json.dumps(results.get("fraud_detection", {}), indent=2))
    
    print("\n--- Authenticity Assessment ---")
    auth = results.get("authenticity_assessment", {})
    print(f"Verdict: {auth.get('verdict', 'unknown')}")
    print(f"Confidence: {auth.get('confidence', 0.0):.2f}")
    print(f"Authenticity Score: {auth.get('authenticity_score', 0.0):.2f}")
    print(f"Reasoning: {auth.get('reasoning', 'N/A')}")
    if auth.get('red_flags'):
        print(f"Red Flags: {', '.join(auth.get('red_flags', []))}")
    
    print(f"\n{'='*80}\n")
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_VISION_MODEL
        quick_vision_check(image_path, model)
    else:
        print("Usage: python -m app.pipelines.vision_llm <image_path> [model_name]")
        print(f"Default model: {DEFAULT_VISION_MODEL}")
