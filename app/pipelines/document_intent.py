from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


class DocumentIntent(str, Enum):
    PURCHASE = "purchase"
    REIMBURSEMENT = "reimbursement"
    CLAIM = "claim"
    TRANSPORT = "transport"
    PROOF_OF_PAYMENT = "proof_of_payment"
    BILLING = "billing"
    STATEMENT = "statement"
    SUBSCRIPTION = "subscription"
    UNKNOWN = "unknown"


class IntentSource(str, Enum):
    HEURISTIC = "heuristic"
    DOMAIN_PACK = "domain_pack"
    LLM = "llm"
    HUMAN = "human"


@dataclass
class DocumentIntentResult:
    intent: DocumentIntent
    confidence: float
    source: IntentSource

    evidence: List[str] = field(default_factory=list)

    doc_family: Optional[str] = None
    doc_subtype: Optional[str] = None
    domain: Optional[str] = None

    requires_corroboration: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict (Enum values become strings)."""
        d = asdict(self)
        d["intent"] = self.intent.value if isinstance(self.intent, Enum) else self.intent
        d["source"] = self.source.value if isinstance(self.source, Enum) else self.source
        return d


SUBTYPE_TO_INTENT: Dict[str, DocumentIntent] = {
    "POS_RESTAURANT": DocumentIntent.PURCHASE,
    "POS_RETAIL": DocumentIntent.PURCHASE,
    "POS_FUEL": DocumentIntent.PURCHASE,
    "ECOMMERCE": DocumentIntent.PURCHASE,
    "HOTEL_FOLIO": DocumentIntent.PURCHASE,
    "FUEL": DocumentIntent.PURCHASE,
    "PARKING": DocumentIntent.PURCHASE,
    "TRANSPORT": DocumentIntent.TRANSPORT,
    "MISC": DocumentIntent.PURCHASE,
    "MISC_RECEIPT": DocumentIntent.PURCHASE,
    "EXPENSE_RECEIPT": DocumentIntent.PURCHASE,
    "CARD_SLIP": DocumentIntent.PURCHASE,
    "HOSPITALITY": DocumentIntent.PURCHASE,  # Hotels, resorts, hospitality services

    # Generic fallbacks (very common from profiler)
    "INVOICE": DocumentIntent.BILLING,
    "RECEIPT": DocumentIntent.PURCHASE,

    "TAX_INVOICE": DocumentIntent.BILLING,
    "VAT_INVOICE": DocumentIntent.BILLING,
    "COMMERCIAL_INVOICE": DocumentIntent.BILLING,
    "SALES_INVOICE": DocumentIntent.BILLING,
    "PURCHASE_INVOICE": DocumentIntent.BILLING,
    "VENDOR_INVOICE": DocumentIntent.BILLING,
    "SERVICE_INVOICE": DocumentIntent.BILLING,
    "SHIPPING_INVOICE": DocumentIntent.BILLING,
    "PROFORMA": DocumentIntent.BILLING,
    "PROFORMA_INVOICE": DocumentIntent.BILLING,
    "ESTIMATE": DocumentIntent.BILLING,
    "QUOTATION": DocumentIntent.BILLING,
    "CREDIT_NOTE": DocumentIntent.REIMBURSEMENT,
    "DEBIT_NOTE": DocumentIntent.BILLING,

    "UTILITY": DocumentIntent.SUBSCRIPTION,
    "UTILITY_BILL": DocumentIntent.SUBSCRIPTION,
    "TELECOM": DocumentIntent.SUBSCRIPTION,
    "TELECOM_BILL": DocumentIntent.SUBSCRIPTION,
    "ELECTRICITY_BILL": DocumentIntent.SUBSCRIPTION,
    "WATER_BILL": DocumentIntent.SUBSCRIPTION,
    "SUBSCRIPTION": DocumentIntent.SUBSCRIPTION,
    "RENT": DocumentIntent.SUBSCRIPTION,
    "INSURANCE": DocumentIntent.SUBSCRIPTION,

    "SHIPPING_BILL": DocumentIntent.TRANSPORT,
    "BILL_OF_LADING": DocumentIntent.TRANSPORT,
    "AIR_WAYBILL": DocumentIntent.TRANSPORT,
    "DELIVERY_NOTE": DocumentIntent.TRANSPORT,
    "PACKING_LIST": DocumentIntent.TRANSPORT,
    "TRAVEL": DocumentIntent.TRANSPORT,  # Generic travel docs (flights, trains, etc.)

    "PAYMENT_RECEIPT": DocumentIntent.PROOF_OF_PAYMENT,
    "UPI_SUCCESS": DocumentIntent.PROOF_OF_PAYMENT,
    "BANK_RECEIPT": DocumentIntent.PROOF_OF_PAYMENT,
    "BANK_SLIP": DocumentIntent.PROOF_OF_PAYMENT,
    "CARD_CHARGE_SLIP": DocumentIntent.PROOF_OF_PAYMENT,
    "REFUND_RECEIPT": DocumentIntent.REIMBURSEMENT,

    "STATEMENT": DocumentIntent.STATEMENT,
    "BANK_STATEMENT": DocumentIntent.STATEMENT,
    "CARD_STATEMENT": DocumentIntent.STATEMENT,

    "CLAIM": DocumentIntent.CLAIM,
    "MEDICAL_CLAIM": DocumentIntent.CLAIM,
    "INSURANCE_CLAIM": DocumentIntent.CLAIM,
    "WARRANTY_CLAIM": DocumentIntent.CLAIM,
    "EXPENSE_CLAIM": DocumentIntent.REIMBURSEMENT,
    "EXPENSE_REPORT": DocumentIntent.REIMBURSEMENT,
}


DOMAIN_DEFAULT_INTENT: Dict[str, DocumentIntent] = {
    "logistics": DocumentIntent.TRANSPORT,
    "transport": DocumentIntent.TRANSPORT,
    "telecom": DocumentIntent.SUBSCRIPTION,
    "insurance": DocumentIntent.SUBSCRIPTION,  # Premium/policy billing, not claim
    "healthcare": DocumentIntent.PURCHASE,
    "medical": DocumentIntent.PURCHASE,
    "hr_expense": DocumentIntent.REIMBURSEMENT,
    "expense": DocumentIntent.REIMBURSEMENT,
    "utility": DocumentIntent.SUBSCRIPTION,
    "banking": DocumentIntent.STATEMENT,
    "ecommerce": DocumentIntent.PURCHASE,
}


def resolve_document_intent(
    *,
    doc_subtype: Optional[str],
    doc_subtype_confidence: float,
    domain_hint: Optional[Dict[str, Any]] = None,
    source: IntentSource = IntentSource.HEURISTIC,
) -> DocumentIntentResult:

    dh = dict(domain_hint or {})
    domain = dh.get("domain")
    try:
        domain_conf = float(dh.get("confidence") or 0.0)
    except Exception:
        domain_conf = 0.0

    # Domain-bias fallback when subtype is missing or low-confidence.
    # This keeps intent routing stable without enumerating all subtypes.
    if ((not doc_subtype) or (doc_subtype_confidence < 0.5)) and (domain and domain_conf >= 0.6):
        ib = dh.get("intent_bias") if isinstance(dh.get("intent_bias"), dict) else {}
        default_intent_str = ib.get("default_intent") or domain
        try:
            default_intent_str = str(default_intent_str).strip().lower()
        except Exception:
            default_intent_str = ""

        default_intent = DOMAIN_DEFAULT_INTENT.get(default_intent_str, DOMAIN_DEFAULT_INTENT.get(str(domain).strip().lower(), DocumentIntent.UNKNOWN))

        try:
            mult = float(ib.get("confidence_multiplier") or 0.8)
        except Exception:
            mult = 0.8

        if default_intent != DocumentIntent.UNKNOWN:
            return DocumentIntentResult(
                intent=default_intent,
                confidence=max(0.0, min(1.0, domain_conf * mult)),
                source=IntentSource.DOMAIN_PACK,
                evidence=[f"domain_hint_bias:{domain}", f"domain_conf={domain_conf:.2f}"],
                doc_subtype=None,
                domain=str(domain),
                requires_corroboration=True,
            )

    # If subtype confidence is low, do not enforce subtype-derived intent.
    # Domain hint (if strong) may still provide a safe default.
    if (not doc_subtype) or (doc_subtype_confidence < 0.5):
        ev = ["low subtype confidence"]
        if domain and domain_conf < 0.6:
            ev.append(f"domain_hint_seen_but_low_conf:{domain}:{domain_conf:.2f}")
        return DocumentIntentResult(
            intent=DocumentIntent.UNKNOWN,
            confidence=0.0,
            source=source,
            requires_corroboration=True,
            evidence=ev,
            domain=str(domain) if (domain and domain_conf >= 0.6) else None,
        )

    try:
        doc_subtype_norm = str(doc_subtype).strip().upper()
    except Exception:
        doc_subtype_norm = ""

    intent = SUBTYPE_TO_INTENT.get(doc_subtype_norm, DocumentIntent.UNKNOWN)

    confidence = min(1.0, 0.5 + (doc_subtype_confidence * 0.5))

    # Only attach domain if confident (>= 0.6)
    ev_final = []
    if domain and domain_conf < 0.6:
        ev_final.append(f"domain_hint_seen_but_low_conf:{domain}:{domain_conf:.2f}")
    
    # Add evidence when subtype is confident but unmapped (actionable signal)
    if intent == DocumentIntent.UNKNOWN and doc_subtype_norm:
        ev_final.append(f"unmapped_subtype:{doc_subtype_norm}")
    
    return DocumentIntentResult(
        intent=intent,
        confidence=confidence,
        source=source,
        doc_subtype=doc_subtype_norm or doc_subtype,
        domain=str(domain) if (domain and domain_conf >= 0.6) else None,
        requires_corroboration=(intent == DocumentIntent.UNKNOWN),
        evidence=ev_final if ev_final else [],
    )
