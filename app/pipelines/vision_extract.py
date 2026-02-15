# app/pipelines/vision_extract.py
"""
Vision LLM Structured Receipt Extraction.

Sends the raw receipt image to a vision-capable LLM and extracts structured
fields (merchant, address, items, totals, dates, payment info) as JSON.

This runs IN PARALLEL with OCR-based extraction. The results are merged into
text_features so the rules engine can use the best available data per field.

Benchmark (Popeyes POS receipt, Feb 2026):
- Qwen2.5-VL:32B: 10/10 accuracy, ~20s
- Llama3.2-Vision: 9/10 accuracy, ~7s
- Gemma3:27B:      4/10 accuracy (hallucinations), ~14s

Model selection: Prefer llama3.2-vision for speed, qwen2.5vl for accuracy.
"""

import json
import base64
import logging
import os
import time
import requests
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Configuration
VISION_EXTRACT_ENABLED = os.getenv("VISION_EXTRACT_ENABLED", "true").lower() == "true"
VISION_EXTRACT_MODEL = os.getenv("VISION_EXTRACT_MODEL", "qwen2.5vl:32b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
VISION_EXTRACT_TIMEOUT = int(os.getenv("VISION_EXTRACT_TIMEOUT", "120"))

# The structured extraction prompt
EXTRACTION_PROMPT = """Look at this receipt/invoice image carefully and extract ALL visible information into JSON format.

{
  "merchant_name": "business name exactly as printed",
  "address": "full address if visible",
  "phone": "phone number if visible",
  "receipt_date": "date on the receipt (MM/DD/YY or as printed)",
  "receipt_time": "time if visible",
  "items": [{"qty": 1, "name": "item name", "price": 0.00}],
  "subtotal": null,
  "tax": null,
  "total": null,
  "currency_symbol": "$",
  "payment_method": "cash/card/debit/credit",
  "card_last4": "last 4 digits if visible",
  "card_type": "VISA/MASTERCARD/DEBIT etc",
  "card_entry_method": "CHIP/SWIPE/TAP",
  "card_transaction_date": "date on card transaction if different from receipt date",
  "receipt_number": "receipt or transaction number if visible",
  "status": "APPROVED/DECLINED if visible",
  "fuel_type": "petrol/diesel/premium if this is a fuel receipt",
  "quantity_litres": null,
  "rate_per_litre": null,
  "vehicle_number": "vehicle/registration number if visible",
  "gstin": "GSTIN number if visible (Indian tax ID)",
  "vat_tin": "VAT TIN number if visible"
}

Rules:
- Use null for any field that is NOT visible or unclear.
- For prices, use numeric values (e.g., 18.98 not "$18.98").
- Read the EXACT text from the image, do not guess or infer.
- If you see multiple dates (e.g., receipt date vs card transaction date), report BOTH.
- Include handwritten text if you can read it.
- Return ONLY the JSON object, no other text."""


def _encode_image(image_path: str) -> str:
    """Encode image file to base64, converting non-standard formats (HEIF/HEVC) to JPEG.
    
    Ollama only accepts JPEG/PNG/GIF/WEBP. iPhone photos are often HEIF despite
    having a .jpg extension. We detect this and convert through PIL.
    """
    import io
    from PIL import Image as PILImage
    
    try:
        # Try PIL first — handles HEIF (via pillow-heif), TIFF, BMP, etc.
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass
        
        img = PILImage.open(image_path)
        img.load()
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        # Fallback: send raw bytes (works for standard JPEG/PNG)
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")


def _query_ollama_vision(image_path: str, prompt: str, model: str, timeout: int) -> Optional[str]:
    """Query Ollama vision model and return raw response text."""
    try:
        image_b64 = _encode_image(image_path)
        
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("response", "")
    except requests.exceptions.ConnectionError:
        logger.warning("Vision extraction: Ollama not reachable at %s", OLLAMA_URL)
        return None
    except requests.exceptions.Timeout:
        logger.warning("Vision extraction: timeout after %ds (model=%s)", timeout, model)
        return None
    except Exception as e:
        logger.warning("Vision extraction failed: %s", e)
        return None


def _parse_json_response(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON extraction from model output."""
    if not text:
        return None
    
    # Fast path
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    
    # Strip markdown code fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = cleaned.find("\n")
        if first_newline > 0:
            cleaned = cleaned[first_newline + 1:]
        # Remove closing fence
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()
        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    
    # Fallback: find first { ... } block
    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        try:
            obj = json.loads(text[json_start:json_end])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    
    return None


def extract_receipt_fields(image_path: str) -> Dict[str, Any]:
    """
    Extract structured receipt fields from an image using Vision LLM.
    
    Returns a dict with extracted fields, plus metadata:
    {
        "merchant_name": "...",
        "total": 88.89,
        ...
        "_vlm_meta": {
            "model": "llama3.2-vision:latest",
            "latency_s": 7.4,
            "success": True,
        }
    }
    
    Returns empty dict with _vlm_meta.success=False on failure.
    """
    if not VISION_EXTRACT_ENABLED:
        logger.info("Vision extraction disabled (VISION_EXTRACT_ENABLED=false)")
        return {"_vlm_meta": {"success": False, "reason": "disabled"}}
    
    start = time.time()
    
    raw_response = _query_ollama_vision(
        image_path, EXTRACTION_PROMPT, VISION_EXTRACT_MODEL, VISION_EXTRACT_TIMEOUT
    )
    
    latency = time.time() - start
    
    if raw_response is None:
        return {"_vlm_meta": {"success": False, "reason": "query_failed", "latency_s": latency}}
    
    parsed = _parse_json_response(raw_response)
    
    if parsed is None:
        logger.warning("Vision extraction: could not parse JSON from response: %s", raw_response[:200])
        return {"_vlm_meta": {"success": False, "reason": "parse_failed", "latency_s": latency}}
    
    # Add metadata
    parsed["_vlm_meta"] = {
        "model": VISION_EXTRACT_MODEL,
        "latency_s": round(latency, 2),
        "success": True,
    }
    
    logger.info(
        "Vision extraction succeeded: merchant=%s, total=%s, date=%s (%.1fs, model=%s)",
        parsed.get("merchant_name"),
        parsed.get("total"),
        parsed.get("receipt_date"),
        latency,
        VISION_EXTRACT_MODEL,
    )
    
    return parsed


def _normalize_date_to_ymd(date_str: str) -> Optional[str]:
    """Convert various date formats to YYYY-MM-DD for conflict detection."""
    from datetime import datetime
    
    date_str = date_str.strip()
    
    # Try common formats
    for fmt in [
        "%Y-%m-%d",       # 2025-06-08
        "%m/%d/%Y",       # 06/08/2025
        "%m/%d/%y",       # 06/08/25
        "%d/%m/%Y",       # 08/06/2025
        "%m-%d-%Y",       # 06-08-2025
        "%Y/%m/%d",       # 2025/06/08
    ]:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    # If already in YYYY-MM-DD format (possibly with extra text)
    import re
    match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
    if match:
        return match.group(1)
    
    # Try MM/DD/YYYY with extra text
    match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', date_str)
    if match:
        m, d, y = match.groups()
        if len(y) == 2:
            y = "20" + y if int(y) < 50 else "19" + y
        try:
            dt = datetime(int(y), int(m), int(d))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    
    return None


def merge_vlm_into_features(vlm_data: Dict[str, Any], text_features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge Vision LLM extracted fields into text_features.
    
    Strategy: VLM fields OVERRIDE OCR-based fields when:
    1. The VLM field is non-null
    2. The OCR field is missing, empty, or clearly wrong (e.g., merchant = "{")
    
    VLM data is also stored in text_features["vlm_extraction"] for audit.
    
    Returns the updated text_features dict.
    """
    if not vlm_data or not vlm_data.get("_vlm_meta", {}).get("success"):
        text_features["vlm_extraction"] = vlm_data.get("_vlm_meta", {})
        return text_features
    
    # Store full VLM extraction for audit trail
    text_features["vlm_extraction"] = {
        k: v for k, v in vlm_data.items() if k != "_vlm_meta"
    }
    text_features["vlm_meta"] = vlm_data.get("_vlm_meta", {})
    
    # --- Merchant ---
    vlm_merchant = vlm_data.get("merchant_name")
    ocr_merchant = text_features.get("merchant_candidate", "") or text_features.get("merchant_guess", "")
    ocr_merchant_str = str(ocr_merchant or "").strip()
    # Override OCR merchant with VLM when: missing, very short, garbage chars, or merchant_guess is None
    _garble_chars = set("{|}[]~\\^`")
    ocr_looks_garbled = bool(set(ocr_merchant_str) & _garble_chars) if ocr_merchant_str else False
    if vlm_merchant and (
        not ocr_merchant_str
        or len(ocr_merchant_str) <= 2
        or ocr_looks_garbled
        or text_features.get("merchant_guess") is None
    ):
        text_features["merchant_candidate"] = vlm_merchant
        text_features["merchant_guess"] = vlm_merchant
        text_features["merchant_source"] = "vlm"
        logger.info("VLM override merchant: %r -> %r", ocr_merchant, vlm_merchant)
    
    # --- Total amount ---
    vlm_total = vlm_data.get("total")
    ocr_total = text_features.get("total_amount")
    if vlm_total is not None and vlm_total != 0:
        try:
            vlm_total_f = float(vlm_total)
            if not ocr_total or ocr_total == 0:
                # OCR missed total entirely
                text_features["total_amount"] = vlm_total_f
                text_features["total_source"] = "vlm"
                logger.info("VLM override total (OCR missing): -> %.2f", vlm_total_f)
            elif ocr_total and abs(float(ocr_total) - vlm_total_f) / max(vlm_total_f, 1) > 0.15:
                # OCR total diverges >15% from VLM total — trust VLM
                text_features["total_amount"] = vlm_total_f
                text_features["ocr_total_amount"] = float(ocr_total)
                text_features["total_source"] = "vlm"
                logger.info("VLM override total (OCR diverges): %.2f -> %.2f", float(ocr_total), vlm_total_f)
        except (ValueError, TypeError):
            pass
    
    # --- Subtotal ---
    vlm_subtotal = vlm_data.get("subtotal")
    if vlm_subtotal is not None:
        try:
            text_features["subtotal_amount"] = float(vlm_subtotal)
        except (ValueError, TypeError):
            pass
    
    # --- Tax ---
    vlm_tax = vlm_data.get("tax")
    if vlm_tax is not None:
        try:
            text_features["tax_amount"] = float(vlm_tax)
        except (ValueError, TypeError):
            pass
    
    # --- Receipt date ---
    # VLM reliably distinguishes receipt date from card transaction date,
    # while OCR date extractors often pick the wrong one (e.g., card date).
    vlm_date = vlm_data.get("receipt_date")
    ocr_date = text_features.get("receipt_date") or text_features.get("date_extracted")
    if vlm_date:
        text_features["receipt_date"] = str(vlm_date)
        if ocr_date and str(vlm_date) != str(ocr_date):
            text_features["ocr_receipt_date"] = str(ocr_date)
            text_features["date_source"] = "vlm"
            logger.info("VLM override date: %r -> %r", ocr_date, vlm_date)
    
    # --- Card transaction date (separate from receipt date — key for fraud detection) ---
    vlm_card_date = vlm_data.get("card_transaction_date")
    if vlm_card_date:
        text_features["card_transaction_date"] = str(vlm_card_date)
    
    # --- Ensure all_dates includes both receipt and card dates for conflict detection ---
    if vlm_date or vlm_card_date:
        all_dates = list(text_features.get("all_dates") or [])
        for raw_date in [vlm_date, vlm_card_date]:
            if not raw_date:
                continue
            normalized = _normalize_date_to_ymd(str(raw_date))
            if normalized and normalized not in all_dates:
                all_dates.append(normalized)
        text_features["all_dates"] = all_dates
    
    # --- Currency ---
    vlm_currency = vlm_data.get("currency_symbol")
    if vlm_currency and not text_features.get("currency_symbols"):
        text_features["currency_symbols"] = [vlm_currency]
        text_features["has_currency"] = True
    
    # --- Address ---
    vlm_address = vlm_data.get("address")
    if vlm_address:
        text_features["vlm_address"] = vlm_address
    
    # --- Phone ---
    vlm_phone = vlm_data.get("phone")
    if vlm_phone:
        text_features["vlm_phone"] = vlm_phone
    
    # --- Payment ---
    vlm_payment = vlm_data.get("payment_method")
    if vlm_payment:
        text_features["payment_method"] = vlm_payment
    
    # --- Line items (for total verification) ---
    vlm_items = vlm_data.get("items")
    if vlm_items and isinstance(vlm_items, list):
        vlm_item_totals = []
        for item in vlm_items:
            if isinstance(item, dict) and item.get("price") is not None:
                try:
                    price = float(item["price"])
                    qty = float(item.get("qty") or 1)
                    # For fuel receipts, item price is rate per unit.
                    # Compute actual line total: qty * price.
                    vlm_item_totals.append(qty * price)
                except (ValueError, TypeError):
                    pass
        if vlm_item_totals:
            vlm_sum = sum(vlm_item_totals)
            text_features["vlm_line_item_totals"] = vlm_item_totals
            text_features["vlm_line_items_sum"] = vlm_sum
            # Override OCR line_items_sum if it looks garbled
            ocr_sum = text_features.get("line_items_sum", 0) or 0
            vlm_total = vlm_data.get("total")
            if vlm_total is not None:
                try:
                    vlm_total_f = float(vlm_total)
                    # If VLM items+total are internally consistent but OCR sum diverges
                    if vlm_total_f > 0 and abs(vlm_sum - ocr_sum) / vlm_total_f > 0.15:
                        text_features["line_items_sum"] = vlm_sum
                        text_features["line_items_source"] = "vlm"
                        logger.info("VLM override line_items_sum: %.2f -> %.2f", ocr_sum, vlm_sum)
                except (ValueError, TypeError):
                    pass
    
    # --- Fuel-specific fields ---
    for fuel_key in ["fuel_type", "quantity_litres", "rate_per_litre", "vehicle_number"]:
        val = vlm_data.get(fuel_key)
        if val is not None:
            text_features[f"vlm_{fuel_key}"] = val
    
    # --- Tax IDs (GSTIN, VAT TIN) ---
    vlm_gstin = vlm_data.get("gstin")
    if vlm_gstin:
        text_features["has_tax_id"] = True
        text_features["vlm_gstin"] = vlm_gstin
    vlm_vat_tin = vlm_data.get("vat_tin")
    if vlm_vat_tin:
        text_features["has_tax_id"] = True
        text_features["vlm_vat_tin"] = vlm_vat_tin
    
    # --- Doc profile inference from VLM data ---
    # If the current doc_profile is weak, derive a better one from VLM fields
    current_dp_conf = 0.0
    try:
        current_dp_conf = float(text_features.get("doc_profile_confidence") or 0.0)
    except (ValueError, TypeError):
        pass
    
    if current_dp_conf < 0.6 and vlm_merchant:
        _infer_doc_profile_from_vlm(vlm_data, text_features)
    
    # --- Geo inference from VLM address ---
    vlm_address_str = vlm_data.get("address") or ""
    current_geo = text_features.get("geo_country_guess", "UNKNOWN")
    if vlm_address_str and current_geo in ("UNKNOWN", "AU", None):
        _infer_geo_from_vlm_address(vlm_address_str, text_features)
    
    return text_features


# US state abbreviations for geo inference
_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

# POS restaurant indicators (food/drink keywords in item names)
_FOOD_KEYWORDS = {
    "chicken", "combo", "biscuit", "fries", "drink", "sprite", "coke",
    "pepsi", "burger", "sandwich", "nugget", "wing", "wrap", "salad",
    "coffee", "tea", "latte", "pizza", "taco", "burrito", "meal",
    "rice", "soup", "steak", "fish", "shrimp", "soda", "juice",
    "water", "milkshake", "dessert", "pie", "cookie", "muffin",
}


def _infer_doc_profile_from_vlm(vlm_data: Dict[str, Any], tf: Dict[str, Any]) -> None:
    """Infer doc subtype from VLM-extracted items and merchant."""
    items = vlm_data.get("items") or []
    item_names = []
    for item in items:
        if isinstance(item, dict) and item.get("name"):
            item_names.append(str(item["name"]).lower())
    
    all_item_text = " ".join(item_names)
    food_hits = sum(1 for kw in _FOOD_KEYWORDS if kw in all_item_text)
    
    if food_hits >= 2:
        tf["doc_subtype_guess"] = "POS_RESTAURANT"
        tf["doc_profile_confidence"] = max(float(tf.get("doc_profile_confidence") or 0), 0.75)
        tf["doc_family_guess"] = "TRANSACTIONAL"
        tf["vlm_doc_profile_source"] = "food_items"
        logger.info("VLM inferred POS_RESTAURANT from %d food keywords in items", food_hits)
    elif len(items) >= 2 and vlm_data.get("total") is not None:
        # Has line items and a total — at least a generic receipt
        if float(tf.get("doc_profile_confidence") or 0) < 0.55:
            tf["doc_subtype_guess"] = "RECEIPT"
            tf["doc_profile_confidence"] = 0.55
            tf["doc_family_guess"] = "TRANSACTIONAL"
            tf["vlm_doc_profile_source"] = "has_items_and_total"
            logger.info("VLM inferred RECEIPT from items + total")


def _infer_geo_from_vlm_address(address: str, tf: Dict[str, Any]) -> None:
    """Infer geo country from VLM-extracted address."""
    import re
    
    # Check for US state abbreviation pattern: "City, ST ZIPCODE"
    us_pattern = re.search(r',\s*([A-Z]{2})\s+(\d{5})', address)
    if us_pattern:
        state = us_pattern.group(1)
        if state in _US_STATES:
            tf["geo_country_guess"] = "US"
            tf["geo_confidence"] = 0.9
            tf["vlm_geo_source"] = f"US state: {state}"
            logger.info("VLM inferred US geo from address state=%s", state)
            return
    
    # Check for common country patterns in address
    address_upper = address.upper()
    for country, patterns in [
        ("UK", [", UK", "UNITED KINGDOM", "ENGLAND", "SCOTLAND", "WALES"]),
        ("CA", [", CANADA", "ONTARIO", "QUEBEC", "BRITISH COLUMBIA"]),
        ("AU", [", AUSTRALIA", "NSW", "QLD", "VIC "]),
        ("IN", [", INDIA", "MAHARASHTRA", "KARNATAKA", "TAMIL NADU"]),
    ]:
        if any(p in address_upper for p in patterns):
            tf["geo_country_guess"] = country
            tf["geo_confidence"] = 0.8
            tf["vlm_geo_source"] = f"address pattern: {country}"
            logger.info("VLM inferred %s geo from address", country)
            return
