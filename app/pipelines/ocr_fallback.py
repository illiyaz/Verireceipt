# app/pipelines/ocr_fallback.py
"""
Vision LLM fallback for failed OCR extractions.
When OCR confidence is low or critical fields are missing, use vision LLM to extract data.
"""

import os
import logging
from typing import Dict, Any, Optional, List
from PIL import Image
import json

logger = logging.getLogger(__name__)

# Import vision LLM if available
try:
    from app.pipelines.vision_llm import (
        query_vision_model,
        extract_receipt_data_with_vision,
        detect_fraud_indicators_with_vision,
        build_vision_assessment
    )
    HAS_VISION_LLM = True
    logger.info("✅ Vision LLM successfully imported and available")
except ImportError as e:
    HAS_VISION_LLM = False
    logger.warning(f"Vision LLM not available for OCR fallback: {e}")
    logger.debug(f"ImportError details: {type(e).__name__}: {str(e)}")
except Exception as e:
    HAS_VISION_LLM = False
    logger.error(f"Unexpected error importing vision_llm: {type(e).__name__}: {str(e)}")


def should_use_vision_fallback(
    ocr_confidence: float,
    missing_fields: List[str],
    doc_subtype: Optional[str] = None
) -> bool:
    """
    Determine if vision LLM fallback should be used.
    
    Args:
        ocr_confidence: Average OCR confidence (0.0-1.0)
        missing_fields: List of critical missing fields
        doc_subtype: Document subtype (e.g., POS_RESTAURANT)
    
    Returns:
        True if vision fallback should be used
    """
    if not HAS_VISION_LLM:
        return False
    
    # Use vision fallback if:
    # 1. OCR confidence is very low (< 0.3)
    # 2. Critical fields are missing (total_amount, merchant_name)
    
    critical_missing = any(field in missing_fields for field in [
        "total_amount", "merchant_name", "merchant_candidate"
    ])
    
    low_confidence = ocr_confidence < 0.3
    
    # For POS receipts, be more aggressive with fallback
    is_pos = doc_subtype and str(doc_subtype).upper().startswith("POS_")
    if is_pos and (low_confidence or critical_missing):
        return True
    
    # For other docs, only use fallback if both conditions met
    if low_confidence and critical_missing:
        return True
    
    return False


def extract_fields_with_vision(
    image_path: str,
    missing_fields: List[str],
    doc_subtype: Optional[str] = None
) -> Dict[str, Any]:
    """
    Use vision LLM to extract missing fields from receipt image.
    
    Args:
        image_path: Path to receipt image
        missing_fields: List of fields to extract
        doc_subtype: Document subtype hint
    
    Returns:
        Dictionary of extracted fields with confidence scores
    """
    if not HAS_VISION_LLM:
        return {}
    
    try:
        # Build targeted prompt based on missing fields
        field_prompts = []
        if "total_amount" in missing_fields:
            field_prompts.append("- Total amount (the final amount to pay)")
        if "merchant_name" in missing_fields or "merchant_candidate" in missing_fields:
            field_prompts.append("- Merchant/business name")
        if "receipt_date" in missing_fields or "issue_date" in missing_fields:
            field_prompts.append("- Transaction date")
        if "receipt_time" in missing_fields:
            field_prompts.append("- Transaction time")
        if "receipt_number" in missing_fields:
            field_prompts.append("- Receipt/bill number")
        
        prompt = f"""Extract the following information from this receipt image:
{chr(10).join(field_prompts)}

Return ONLY a JSON object with the extracted values. Use null for missing fields.
Example format:
{{
    "total_amount": 150.50,
    "merchant_name": "Pizza Hut",
    "receipt_date": "2024-01-10",
    "receipt_time": "14:30",
    "receipt_number": "12345"
}}"""
        
        # Query vision model
        response = query_vision_model(
            image_path=image_path,
            prompt=prompt,
            temperature=0.1  # Low temperature for factual extraction
        )
        
        # Parse JSON response
        try:
            # Extract JSON from response (may have extra text)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                extracted = json.loads(json_str)
                
                # Add metadata
                result = {
                    "extracted_fields": extracted,
                    "vision_confidence": 0.7,  # Vision LLM confidence (conservative)
                    "source": "vision_llm_fallback",
                    "model_response": response
                }
                
                logger.info(f"✅ Vision LLM extracted {len(extracted)} fields")
                return result
            else:
                logger.warning("No JSON found in vision LLM response")
                return {}
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse vision LLM JSON: {e}")
            return {}
    
    except Exception as e:
        logger.error(f"Vision LLM fallback failed: {e}")
        return {}


def integrate_vision_fallback(
    text_features: Dict[str, Any],
    ocr_metadata: Dict[str, Any],
    image_path: str,
    doc_subtype: Optional[str] = None
) -> Dict[str, Any]:
    """
    Integrate vision LLM fallback into text features.
    
    Args:
        text_features: Existing text features from OCR
        ocr_metadata: OCR confidence and metadata
        image_path: Path to receipt image
        doc_subtype: Document subtype
    
    Returns:
        Updated text_features with vision fallback data
    """
    # Check if fallback needed
    ocr_confidence = ocr_metadata.get("avg_confidence", 1.0)
    
    missing_fields = []
    if not text_features.get("total_amount"):
        missing_fields.append("total_amount")
    if not text_features.get("merchant_candidate"):
        missing_fields.append("merchant_candidate")
    if not text_features.get("receipt_date"):
        missing_fields.append("receipt_date")
    if not text_features.get("receipt_time"):
        missing_fields.append("receipt_time")
    if not text_features.get("receipt_number"):
        missing_fields.append("receipt_number")
    
    if not should_use_vision_fallback(ocr_confidence, missing_fields, doc_subtype):
        return text_features
    
    logger.info(f"🔍 Triggering vision LLM fallback (OCR conf={ocr_confidence:.2f}, missing={missing_fields})")
    
    # Extract fields with vision
    vision_result = extract_fields_with_vision(image_path, missing_fields, doc_subtype)
    
    if not vision_result:
        return text_features
    
    # Integrate extracted fields
    extracted = vision_result.get("extracted_fields", {})
    vision_conf = vision_result.get("vision_confidence", 0.7)
    
    # Only override if field is missing or OCR confidence is very low
    if not text_features.get("total_amount") and extracted.get("total_amount"):
        text_features["total_amount"] = extracted["total_amount"]
        text_features["total_amount_source"] = "vision_llm"
        text_features["total_amount_confidence"] = vision_conf
    
    if not text_features.get("merchant_candidate") and extracted.get("merchant_name"):
        text_features["merchant_candidate"] = extracted["merchant_name"]
        text_features["merchant_source"] = "vision_llm"
        text_features["merchant_confidence"] = vision_conf
    
    if not text_features.get("receipt_date") and extracted.get("receipt_date"):
        text_features["receipt_date"] = extracted["receipt_date"]
        text_features["receipt_date_source"] = "vision_llm"
    
    if not text_features.get("receipt_time") and extracted.get("receipt_time"):
        text_features["receipt_time"] = extracted["receipt_time"]
        text_features["receipt_time_source"] = "vision_llm"
    
    if not text_features.get("receipt_number") and extracted.get("receipt_number"):
        text_features["receipt_number"] = extracted["receipt_number"]
        text_features["receipt_number_source"] = "vision_llm"
    
    # Store vision metadata
    text_features["vision_fallback_used"] = True
    text_features["vision_fallback_metadata"] = vision_result
    
    logger.info(f"✅ Vision fallback integrated: {len(extracted)} fields added")
    
    return text_features
