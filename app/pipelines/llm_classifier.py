"""
LLM-based document classifier (gated fallback for low-confidence heuristics).

This module provides a lightweight LLM classifier that runs ONLY when:
- doc_profile_confidence < 0.6, OR
- domain_hint confidence < 0.6, OR
- doc_subtype == "unknown", OR
- language confidence is low / non-English with poor OCR

Returns:
- doc_family (TRANSACTIONAL / STATEMENT / LOGISTICS / etc)
- doc_subtype (POS_RESTAURANT / BILL_OF_LADING / TAX_INVOICE / etc)
- domain (telecom / logistics / insurance / ecommerce / banking / utility / medical)
- confidence (0.0 - 1.0)
- evidence (short list of phrases used for classification)
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
import json
import re


@dataclass
class LLMClassificationResult:
    """Result from LLM document classification."""
    doc_family: Optional[str] = None
    doc_subtype: Optional[str] = None
    domain: Optional[str] = None
    confidence: float = 0.0
    evidence: List[str] = None
    
    def __post_init__(self):
        if self.evidence is None:
            self.evidence = []
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Valid taxonomy for LLM to choose from
VALID_DOC_FAMILIES = [
    "TRANSACTIONAL",
    "LOGISTICS",
    "STATEMENT",
    "PAYMENT",
    "UNKNOWN"
]

VALID_DOC_SUBTYPES = [
    # Transactional - POS
    "POS_RESTAURANT", "POS_RETAIL", "POS_FUEL", "HOSPITALITY",
    "ECOMMERCE", "HOTEL_FOLIO", "FUEL", "PARKING", "TRANSPORT",
    
    # Transactional - Invoices
    "TAX_INVOICE", "VAT_INVOICE", "COMMERCIAL_INVOICE", "SALES_INVOICE",
    "SERVICE_INVOICE", "SHIPPING_INVOICE", "PROFORMA", "INVOICE",
    "CREDIT_NOTE", "DEBIT_NOTE",
    
    # Transactional - Bills
    "UTILITY", "UTILITY_BILL", "TELECOM", "TELECOM_BILL",
    "ELECTRICITY_BILL", "WATER_BILL", "SUBSCRIPTION", "RENT", "INSURANCE",
    
    # Logistics
    "SHIPPING_BILL", "BILL_OF_LADING", "AIR_WAYBILL", "DELIVERY_NOTE",
    "PACKING_LIST", "TRAVEL",
    
    # Payment
    "PAYMENT_RECEIPT", "BANK_RECEIPT", "BANK_SLIP", "CARD_CHARGE_SLIP",
    "REFUND_RECEIPT", "RECEIPT",
    
    # Statement
    "STATEMENT", "BANK_STATEMENT", "CARD_STATEMENT",
    
    # Claims
    "CLAIM", "MEDICAL_CLAIM", "INSURANCE_CLAIM", "WARRANTY_CLAIM",
    "EXPENSE_CLAIM", "EXPENSE_REPORT",
    
    # Fallback
    "UNKNOWN"
]

VALID_DOMAINS = [
    "telecom", "logistics", "insurance", "ecommerce", "banking",
    "utility", "medical", "healthcare", "transport", "hospitality",
    "retail", "fuel", "parking", "hr_expense", "expense"
]


def should_call_llm_classifier(
    doc_profile_confidence: float,
    domain_confidence: float,
    doc_subtype: Optional[str],
    lang_confidence: float,
    lang_guess: Optional[str],
    merchant_candidate: Optional[str] = None,
) -> bool:
    """
    Gate: only call LLM when heuristics are uncertain.
    
    Args:
        doc_profile_confidence: Confidence from geo_detection profiling
        domain_confidence: Confidence from domain_validation
        doc_subtype: Detected document subtype
        lang_confidence: Language detection confidence
        lang_guess: Detected language code
        merchant_candidate: Extracted merchant name (if present)
    
    Returns:
        True if LLM classifier should be called
    """
    # Gate 1: Low document profile confidence (more assertive when merchant exists)
    # If merchant present, call LLM earlier (< 0.4) to repair ambiguity
    if merchant_candidate:
        if doc_profile_confidence < 0.4:
            return True
    else:
        if doc_profile_confidence < 0.6:
            return True
    
    # Gate 2: Low domain confidence
    if domain_confidence < 0.6:
        return True
    
    # Gate 3: Unknown subtype
    if not doc_subtype or str(doc_subtype).strip().lower() in ("unknown", ""):
        return True
    
    # Gate 4: Low language confidence or non-English with potential OCR issues
    if lang_confidence < 0.5:
        return True
    
    # Gate 5: Non-English with moderate confidence (may have OCR issues)
    if lang_guess and str(lang_guess).lower() not in ["en", "english"] and lang_confidence < 0.8:
        return True
    
    return False


def _build_classification_prompt(text: str, max_chars: int = 2000) -> str:
    """
    Build a concise prompt for LLM document classification.
    
    Args:
        text: Full document text
        max_chars: Maximum characters to include in prompt
    
    Returns:
        Formatted prompt string
    """
    # Truncate text if too long (take first N chars for header/key info)
    text_sample = text[:max_chars] if len(text) > max_chars else text
    
    # Group subtypes by family for cleaner prompt
    subtypes_by_family = {
        "TRANSACTIONAL": [s for s in VALID_DOC_SUBTYPES if s in [
            "POS_RESTAURANT", "POS_RETAIL", "POS_FUEL", "HOSPITALITY",
            "ECOMMERCE", "HOTEL_FOLIO", "FUEL", "PARKING", "TRANSPORT",
            "TAX_INVOICE", "VAT_INVOICE", "COMMERCIAL_INVOICE", "SALES_INVOICE",
            "SERVICE_INVOICE", "SHIPPING_INVOICE", "PROFORMA", "INVOICE",
            "CREDIT_NOTE", "DEBIT_NOTE", "UTILITY", "UTILITY_BILL", "TELECOM",
            "TELECOM_BILL", "ELECTRICITY_BILL", "WATER_BILL", "SUBSCRIPTION",
            "RENT", "INSURANCE"
        ]],
        "LOGISTICS": [s for s in VALID_DOC_SUBTYPES if s in [
            "SHIPPING_BILL", "BILL_OF_LADING", "AIR_WAYBILL", "DELIVERY_NOTE",
            "PACKING_LIST", "TRAVEL"
        ]],
        "PAYMENT": [s for s in VALID_DOC_SUBTYPES if s in [
            "PAYMENT_RECEIPT", "BANK_RECEIPT", "BANK_SLIP", "CARD_CHARGE_SLIP",
            "REFUND_RECEIPT", "RECEIPT"
        ]],
        "STATEMENT": [s for s in VALID_DOC_SUBTYPES if s in [
            "STATEMENT", "BANK_STATEMENT", "CARD_STATEMENT"
        ]],
        "CLAIMS": [s for s in VALID_DOC_SUBTYPES if s in [
            "CLAIM", "MEDICAL_CLAIM", "INSURANCE_CLAIM", "WARRANTY_CLAIM",
            "EXPENSE_CLAIM", "EXPENSE_REPORT"
        ]],
    }
    
    subtypes_formatted = "\n".join(
        f"  {family}: {', '.join(subtypes)}"
        for family, subtypes in subtypes_by_family.items()
        if subtypes
    )
    
    prompt = f"""Classify this document. Return ONLY valid JSON with this exact structure:
{{
  "doc_family": "TRANSACTIONAL|LOGISTICS|STATEMENT|PAYMENT|UNKNOWN",
  "doc_subtype": "<choose from list below>",
  "domain": "<choose from list below>",
  "confidence": 0.0-1.0,
  "evidence": ["phrase1", "phrase2", "phrase3"]
}}

Valid doc_families:
{', '.join(VALID_DOC_FAMILIES)}

Valid doc_subtypes (grouped by family):
{subtypes_formatted}

Valid domains:
{', '.join(VALID_DOMAINS)}

IMPORTANT: Only use subtypes from the list above. If uncertain, use "UNKNOWN".

Document text:
---
{text_sample}
---

Return ONLY the JSON object wrapped in ```json code fence, no other text."""
    
    return prompt


def _parse_llm_response(response: str) -> LLMClassificationResult:
    """
    Parse LLM JSON response into structured result.
    
    Args:
        response: Raw LLM response string
    
    Returns:
        LLMClassificationResult with parsed data
    """
    try:
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to parse if response starts with { (safer than greedy regex)
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
                    return LLMClassificationResult(confidence=0.0, evidence=["parse_error:unbalanced_braces"])
            else:
                return LLMClassificationResult(confidence=0.0, evidence=["parse_error:no_json_found"])
        
        data = json.loads(json_str)
        
        # Validate and normalize
        doc_family = str(data.get("doc_family", "")).strip().upper()
        if doc_family not in VALID_DOC_FAMILIES:
            doc_family = "UNKNOWN"
        
        doc_subtype = str(data.get("doc_subtype", "")).strip().upper()
        if doc_subtype not in VALID_DOC_SUBTYPES:
            doc_subtype = "UNKNOWN"
        
        domain = str(data.get("domain", "")).strip().lower()
        if domain not in VALID_DOMAINS:
            domain = None
        
        try:
            confidence = float(data.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.0
        
        evidence = data.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []
        evidence = [str(e).strip() for e in evidence if e][:5]  # Max 5 evidence items
        
        return LLMClassificationResult(
            doc_family=doc_family if doc_family != "UNKNOWN" else None,
            doc_subtype=doc_subtype if doc_subtype != "UNKNOWN" else None,
            domain=domain,
            confidence=confidence,
            evidence=evidence
        )
    
    except Exception as e:
        return LLMClassificationResult(
            confidence=0.0,
            evidence=[f"parse_error:{str(e)[:50]}"]
        )


def _call_ollama(client: Any, model: str, prompt: str, max_tokens: int = 300) -> str:
    """Call Ollama API."""
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": "You are a document classification expert. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        options={
            "temperature": 0.0,
            "num_predict": max_tokens,
        }
    )
    return response["message"]["content"]


def _call_openai(client: Any, model: str, prompt: str, max_tokens: int = 300) -> str:
    """Call OpenAI API."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a document classification expert. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def classify_document_with_llm(
    text: str,
    llm_client: Any = None,
    provider: str = "ollama",
    model: str = None,
    max_chars: int = 2000,
    max_tokens: int = 300,
) -> LLMClassificationResult:
    """
    Classify document using LLM (gated fallback).
    
    Args:
        text: Full document text
        llm_client: LLM client instance (Ollama or OpenAI)
        provider: "ollama" or "openai"
        model: Model name to use (defaults based on provider)
        max_chars: Maximum characters to send to LLM
        max_tokens: Maximum tokens in response
    
    Returns:
        LLMClassificationResult with classification data
    """
    if not llm_client:
        return LLMClassificationResult(
            confidence=0.0,
            evidence=["llm_client_not_configured"]
        )
    
    if not text or len(text.strip()) < 10:
        return LLMClassificationResult(
            confidence=0.0,
            evidence=["text_too_short"]
        )
    
    # Set default model based on provider
    if model is None:
        model = "llama3.2:3b" if provider == "ollama" else "gpt-4o-mini"
    
    try:
        prompt = _build_classification_prompt(text, max_chars=max_chars)
        
        # Call appropriate API
        if provider == "ollama":
            llm_output = _call_ollama(llm_client, model, prompt, max_tokens)
        else:  # openai
            llm_output = _call_openai(llm_client, model, prompt, max_tokens)
        
        result = _parse_llm_response(llm_output)
        
        return result
    
    except Exception as e:
        return LLMClassificationResult(
            confidence=0.0,
            evidence=[f"llm_error:{str(e)[:50]}"]
        )


def integrate_llm_classification(
    llm_result: LLMClassificationResult,
    existing_domain_hint: Optional[Dict[str, Any]] = None,
    existing_doc_profile: Optional[Dict[str, Any]] = None,
    source_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Merge LLM classification with existing heuristic results.
    
    Strategy:
    - LLM must have confidence >= 0.7 AND beat existing by +0.15 margin to override
    - If source_text provided, verify evidence phrases exist in text (grounding)
    - Otherwise, keep existing result
    - Always preserve both in audit trail
    
    Args:
        llm_result: LLM classification result
        existing_domain_hint: Existing domain hint from domain_validation
        existing_doc_profile: Existing doc profile from geo_detection
        source_text: Optional source text for evidence grounding
    
    Returns:
        Merged result dict with updated domain_hint and doc_profile
    """
    MIN_LLM_CONFIDENCE = 0.7
    OVERRIDE_MARGIN = 0.15
    
    # Evidence grounding: verify LLM evidence exists in source text
    llm_grounded = True
    if source_text and llm_result.evidence:
        # Check if at least 50% of evidence phrases exist in text (case-insensitive)
        text_lower = source_text.lower()
        grounded_count = sum(1 for phrase in llm_result.evidence if phrase.lower() in text_lower)
        llm_grounded = grounded_count >= len(llm_result.evidence) * 0.5
        
        # Downgrade confidence if not grounded
        if not llm_grounded:
            llm_result.confidence *= 0.5
            llm_result.evidence.append("evidence_not_grounded")
    
    merged = {
        "domain_hint_updated": False,
        "doc_profile_updated": False,
        "llm_classification": llm_result.to_dict(),
        "llm_grounded": llm_grounded,
    }
    
    # Update domain_hint if LLM is more confident (with guardrails)
    if llm_result.domain and llm_result.confidence >= MIN_LLM_CONFIDENCE:
        existing_domain_conf = 0.0
        if existing_domain_hint:
            try:
                existing_domain_conf = float(existing_domain_hint.get("confidence", 0.0))
            except (TypeError, ValueError):
                existing_domain_conf = 0.0
        
        # Require margin to override
        if llm_result.confidence > existing_domain_conf + OVERRIDE_MARGIN:
            merged["domain_hint"] = {
                "domain": llm_result.domain,
                "confidence": llm_result.confidence,
                "evidence": llm_result.evidence + ["llm_override"],
                "source": "llm",
            }
            merged["domain_hint_updated"] = True
        else:
            merged["domain_hint"] = existing_domain_hint
    else:
        merged["domain_hint"] = existing_domain_hint
    
    # Update doc_profile if LLM is more confident (with guardrails)
    if llm_result.doc_subtype and llm_result.confidence >= MIN_LLM_CONFIDENCE:
        existing_profile_conf = 0.0
        if existing_doc_profile:
            try:
                existing_profile_conf = float(existing_doc_profile.get("doc_profile_confidence", 0.0))
            except (TypeError, ValueError):
                existing_profile_conf = 0.0
        
        # Require margin to override
        if llm_result.confidence > existing_profile_conf + OVERRIDE_MARGIN:
            merged["doc_profile"] = {
                "doc_family_guess": llm_result.doc_family or "UNKNOWN",
                "doc_subtype_guess": llm_result.doc_subtype,
                "doc_profile_confidence": llm_result.confidence,
                "doc_profile_evidence": llm_result.evidence + ["llm_override"],
                "doc_subtype_source": "llm",
            }
            merged["doc_profile_updated"] = True
        else:
            merged["doc_profile"] = existing_doc_profile
    else:
        merged["doc_profile"] = existing_doc_profile
    
    return merged
