"""
LLM Semantic Verification Layer (SVL)

Role: LLM as Semantic Referee - decides WHAT rules apply, not WHAT verdict to give.

Key Principles:
1. LLM never outputs fake/real verdicts
2. LLM only answers constrained questions (strict JSON)
3. LLM separates semantic amounts from metadata numbers
4. LLM confidence gates arithmetic rules (R7_TOTAL_MISMATCH, etc.)

Use Cases:
✅ Line-item vs metadata number separation
✅ Intent detection (invoice vs receipt vs statement)
✅ Field relevance ("is this number money?")
✅ Explaining why something is suspicious

Do NOT Use For:
❌ Final verdict
❌ Score aggregation
❌ Hard fail decisions
❌ Compliance thresholds
"""

import json
import re
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# Try to import LLM backend (Ollama or OpenAI)
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests library not available - semantic verification disabled")


@dataclass
class SemanticAmounts:
    """Structured result from LLM semantic amount verification."""
    line_item_amounts: List[float]
    tax_amounts: List[float]
    total_amount: Optional[float]
    confidence: float  # 0.0-1.0
    ignore_numbers: List[str]  # Numbers that are NOT amounts (IDs, dates, etc.)
    reasoning: Optional[str] = None  # Optional explanation
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def llm_verify_amounts(
    text: str,
    extracted_amounts: List[float],
    ocr_confidence: Optional[float] = None,
    doc_subtype: Optional[str] = None,
    model: str = "llama3.2:latest",
    temperature: float = 0.1,
    timeout: int = 30
) -> Optional[SemanticAmounts]:
    """
    Use LLM to semantically verify which numbers are actual amounts vs metadata.
    
    This is the core "Semantic Referee" function that gates arithmetic rules.
    
    Args:
        text: Full OCR text from receipt/invoice
        extracted_amounts: All numeric candidates extracted by regex
        ocr_confidence: OCR quality (0.0-1.0), used to decide if LLM is needed
        doc_subtype: Document type hint (INVOICE, POS_RESTAURANT, etc.)
        model: LLM model name (Ollama or OpenAI)
        temperature: Sampling temperature (low for factual extraction)
        timeout: Request timeout in seconds
    
    Returns:
        SemanticAmounts with verified amounts and confidence, or None if LLM unavailable
    
    Design:
        - LLM receives OCR text + candidate amounts
        - LLM classifies each number as: line_item, tax, total, or metadata
        - LLM returns strict JSON (no prose)
        - Confidence >= 0.85 → use semantic amounts
        - Confidence < 0.85 → skip arithmetic rules
    """
    if not HAS_REQUESTS:
        logger.debug("Semantic verification skipped - requests library not available")
        return None
    
    # Build prompt
    prompt = _build_semantic_prompt(text, extracted_amounts, doc_subtype)
    
    # Query LLM
    try:
        response = _query_ollama(prompt, model, temperature, timeout)
        if not response:
            logger.warning("LLM semantic verification failed - no response")
            return None
        
        # Parse strict JSON response
        semantic = _parse_semantic_response(response)
        return semantic
    
    except Exception as e:
        logger.error(f"LLM semantic verification error: {e}")
        return None


def _build_semantic_prompt(
    text: str,
    extracted_amounts: List[float],
    doc_subtype: Optional[str]
) -> str:
    """
    Build prompt for LLM semantic amount verification.
    
    Prompt design:
    - Constrained task (classify numbers, don't judge authenticity)
    - Strict JSON output (no prose)
    - Clear categories (line_item, tax, total, metadata)
    """
    doc_type_hint = f" (Document type: {doc_subtype})" if doc_subtype else ""
    
    prompt = f"""You are a semantic document analyzer. Your ONLY job is to classify numbers in this receipt/invoice text{doc_type_hint}.

TASK: Identify which numbers are actual monetary amounts vs metadata (IDs, dates, addresses, etc.)

RECEIPT TEXT:
{text[:2000]}  

CANDIDATE NUMBERS EXTRACTED:
{extracted_amounts[:50]}

CLASSIFY each number into ONE category:
1. **line_item_amounts**: Money amounts for individual items/services purchased
2. **tax_amounts**: Tax/VAT/GST amounts
3. **total_amount**: Final total to pay (only ONE number)
4. **ignore_numbers**: NOT money (invoice IDs, dates, ZIP codes, phone numbers, addresses, quantities, item codes)

CRITICAL RULES:
- A number can only be in ONE category
- If unsure, put in ignore_numbers
- Total should be the FINAL amount to pay (after tax)
- Line items should NOT include subtotals/tax/total
- Dates, IDs, addresses, phone numbers → ignore_numbers
- **SANITY CHECK**: Line item amounts are typically < $10,000 for individual items
  - If a number is > $100,000, it's almost certainly an ID/invoice number, NOT a line item
  - Large numbers (> $10,000) should be carefully verified before classifying as line items
- **REASONABLENESS**: The sum of line items should be close to the total (within 2x)
  - If line items sum to 10x the total, you've likely included IDs as amounts
- Return confidence 0.0-1.0 based on clarity of the document

OUTPUT FORMAT (strict JSON, no other text):
```json
{{
  "line_item_amounts": [2000.0],
  "tax_amounts": [420.0],
  "total_amount": 2420.0,
  "confidence": 0.92,
  "ignore_numbers": ["4650", "07102", "2024", "12345"],
  "reasoning": "Clear invoice with itemized charges. Number 4650 is invoice ID, 07102 is ZIP code."
}}
```

Return ONLY the JSON object, no other text."""
    
    return prompt


def _query_ollama(
    prompt: str,
    model: str,
    temperature: float,
    timeout: int
) -> Optional[str]:
    """
    Query Ollama API for semantic verification.
    
    Args:
        prompt: Semantic verification prompt
        model: Ollama model name
        temperature: Sampling temperature
        timeout: Request timeout
    
    Returns:
        LLM response text or None if failed
    """
    try:
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        
        result = response.json()
        return result.get("response", "")
    
    except requests.exceptions.ConnectionError:
        logger.debug("Ollama not available - semantic verification skipped")
        return None
    except requests.exceptions.Timeout:
        logger.warning(f"Ollama timeout after {timeout}s")
        return None
    except Exception as e:
        logger.error(f"Ollama query error: {e}")
        return None


def _parse_semantic_response(response: str) -> Optional[SemanticAmounts]:
    """
    Parse LLM response into SemanticAmounts structure.
    
    Handles:
    - JSON in markdown code blocks
    - Bare JSON objects
    - Malformed responses
    
    Args:
        response: Raw LLM response
    
    Returns:
        SemanticAmounts or None if parsing failed
    """
    try:
        # Extract JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to parse if response starts with {
            stripped = response.strip()
            if stripped.startswith('{'):
                # Find balanced braces
                brace_count = 0
                end_pos = 0
                for i, char in enumerate(stripped):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_pos = i + 1
                            break
                if end_pos > 0:
                    json_str = stripped[:end_pos]
                else:
                    logger.warning("Semantic response: unbalanced braces")
                    return None
            else:
                logger.warning("Semantic response: no JSON found")
                return None
        
        # Parse JSON
        data = json.loads(json_str)
        
        # Validate required fields
        if not isinstance(data, dict):
            logger.warning("Semantic response: not a JSON object")
            return None
        
        # Extract and validate fields
        line_item_amounts = data.get("line_item_amounts", [])
        tax_amounts = data.get("tax_amounts", [])
        total_amount = data.get("total_amount")
        confidence = data.get("confidence", 0.0)
        ignore_numbers = data.get("ignore_numbers", [])
        reasoning = data.get("reasoning")
        
        # Type validation
        if not isinstance(line_item_amounts, list):
            line_item_amounts = []
        if not isinstance(tax_amounts, list):
            tax_amounts = []
        if not isinstance(ignore_numbers, list):
            ignore_numbers = []
        
        # Convert to floats
        line_item_amounts = [float(x) for x in line_item_amounts if isinstance(x, (int, float))]
        tax_amounts = [float(x) for x in tax_amounts if isinstance(x, (int, float))]
        if total_amount is not None:
            try:
                total_amount = float(total_amount)
            except (TypeError, ValueError):
                total_amount = None
        
        # POST-PROCESSING SANITY CHECKS
        # Filter out unrealistic line item amounts (likely IDs/invoice numbers)
        MAX_LINE_ITEM = 100000.0  # $100k threshold
        filtered_line_items = []
        rejected_items = []
        
        for amount in line_item_amounts:
            if amount > MAX_LINE_ITEM:
                # Likely an ID/invoice number, not a line item
                rejected_items.append(str(int(amount)))
                logger.warning(f"Rejected line item ${amount:,.0f} (> ${MAX_LINE_ITEM:,.0f} threshold)")
            else:
                filtered_line_items.append(amount)
        
        # Add rejected items to ignore_numbers
        if rejected_items:
            ignore_numbers.extend(rejected_items)
            line_item_amounts = filtered_line_items
            
            # Downgrade confidence if we had to filter out items
            confidence *= 0.9
            logger.info(f"Filtered {len(rejected_items)} unrealistic line items, confidence downgraded to {confidence:.2f}")
        
        # Reasonableness check: line items sum should be within 3x of total
        if total_amount and line_item_amounts:
            items_sum = sum(line_item_amounts)
            if total_amount > 0:
                ratio = items_sum / total_amount
                if ratio > 3.0 or ratio < 0.3:
                    # Sum is way off - likely still have wrong items
                    logger.warning(f"Line items sum ({items_sum:,.2f}) vs total ({total_amount:,.2f}) ratio {ratio:.2f} is unreasonable")
                    confidence *= 0.7
        
        # Clamp confidence to 0.0-1.0
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0
        
        # Convert ignore_numbers to strings
        ignore_numbers = [str(x) for x in ignore_numbers]
        
        return SemanticAmounts(
            line_item_amounts=line_item_amounts,
            tax_amounts=tax_amounts,
            total_amount=total_amount,
            confidence=confidence,
            ignore_numbers=ignore_numbers,
            reasoning=reasoning
        )
    
    except json.JSONDecodeError as e:
        logger.warning(f"Semantic response JSON parse error: {e}")
        return None
    except Exception as e:
        logger.error(f"Semantic response parse error: {e}")
        return None


def should_use_semantic_verification(
    ocr_confidence: Optional[float],
    line_items_confidence: float,
    total_mismatch_ratio: Optional[float]
) -> bool:
    """
    Decide if semantic verification should be used.
    
    Use LLM when:
    1. Total mismatch > 20% (likely extraction error)
    2. OCR confidence < 0.5 (poor quality)
    3. Line items confidence < 0.5 (ambiguous extraction)
    
    Args:
        ocr_confidence: OCR quality (0.0-1.0 or None)
        line_items_confidence: Line items extraction confidence (0.0-1.0)
        total_mismatch_ratio: Mismatch ratio (0.0-1.0 or None)
    
    Returns:
        True if semantic verification should be used
    """
    # Use semantic verification if:
    # 1. Large mismatch detected (> 20%)
    if total_mismatch_ratio is not None and total_mismatch_ratio > 0.20:
        return True
    
    # 2. Low OCR confidence
    if ocr_confidence is not None and ocr_confidence < 0.5:
        return True
    
    # 3. Low line items extraction confidence
    if line_items_confidence < 0.5:
        return True
    
    return False
