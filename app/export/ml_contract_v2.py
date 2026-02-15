"""
ML Contract V2 - Stable export format for ML training

This module provides a stable, versioned export format for ML training that includes:
- inputs.signals_emitted: Ordered list of unique signal IDs
- inputs.amounts: Reconciliation summary with confidence
- inputs.doc: Minimal document hints (geo, language, subtype)
- label: Final decision label
- score: Final decision score
- debug: Optional diagnostics

Design Goals:
- Stable schema for ML training
- Robust to missing fields (don't crash)
- Clear provenance and confidence tracking
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _extract_signals_emitted(decision) -> List[str]:
    """
    Extract ordered unique signal IDs from decision events.
    
    Uses the same logic as show_evidence.py to ensure consistency.
    """
    signals = []
    seen = set()
    
    try:
        events = getattr(decision, 'events', [])
        for event in events:
            # Handle both dict and object events
            if isinstance(event, dict):
                event_id = event.get('rule_id') or event.get('event_id') or event.get('signal_id')
            else:
                event_id = getattr(event, 'rule_id', None) or getattr(event, 'event_id', None) or getattr(event, 'signal_id', None)
            
            if event_id and event_id not in seen:
                seen.add(event_id)
                signals.append(event_id)
    except Exception as e:
        logger.warning(f"Failed to extract signals_emitted: {e}")
    
    return signals


def _extract_amounts_summary(decision) -> Optional[Dict[str, Any]]:
    """
    Extract amount reconciliation summary from AMOUNT_RECONCILIATION event.
    
    Returns None if not found.
    """
    try:
        events = getattr(decision, 'events', [])
        for event in events:
            # Handle both dict and object events
            if isinstance(event, dict):
                event_id = event.get('rule_id') or event.get('event_id')
                evidence = event.get('evidence', {})
            else:
                event_id = getattr(event, 'rule_id', None) or getattr(event, 'event_id', None)
                evidence = getattr(event, 'evidence', {})
            
            if event_id == "AMOUNT_RECONCILIATION" and evidence:
                # Defensive extraction of Phase-9.2/9.3 typed entities
                recon_v2 = evidence.get("reconciliation_v2")
                subtotal_e = evidence.get("subtotal_entity_v2")
                discount_e = evidence.get("discount_entity_v2")
                tip_e = evidence.get("tip_entity_v2")
                
                # Ensure dict shape (defensive)
                recon_v2 = recon_v2 if isinstance(recon_v2, dict) else None
                subtotal_e = subtotal_e if isinstance(subtotal_e, dict) else None
                discount_e = discount_e if isinstance(discount_e, dict) else None
                tip_e = tip_e if isinstance(tip_e, dict) else None
                
                # Defensive provenance extraction
                provenance = evidence.get('provenance')
                provenance = provenance if isinstance(provenance, dict) else {}
                source = provenance.get('total')
                
                # Extract key fields for ML
                return {
                    "total_amount": evidence.get('total_amount'),
                    "items_sum": evidence.get('items_sum'),
                    "tax_amount": evidence.get('tax_amount'),
                    "mismatch_ratio": evidence.get('mismatch_ratio'),
                    "confidence": evidence.get('confidence'),
                    "source": source,
                    # Phase-9.2/9.3 typed entities (observability)
                    "reconciliation_v2": recon_v2,
                    "subtotal_entity_v2": subtotal_e,
                    "discount_entity_v2": discount_e,
                    "tip_entity_v2": tip_e,
                }
    except Exception as e:
        logger.warning(f"Failed to extract amounts summary: {e}")
    
    return None


def _extract_doc_hints(decision) -> Dict[str, Any]:
    """
    Extract minimal document hints (geo, language, subtype).
    
    Returns empty dict if not found.
    """
    hints = {}
    
    try:
        # Try to get from decision attributes
        hints['geo_country'] = getattr(decision, 'geo_country_guess', None)
        hints['geo_confidence'] = getattr(decision, 'geo_confidence', None)
        hints['lang'] = getattr(decision, 'lang_guess', None)
        hints['lang_confidence'] = getattr(decision, 'lang_confidence', None)
        hints['doc_family'] = getattr(decision, 'doc_family', None)
        hints['doc_subtype'] = getattr(decision, 'doc_subtype', None)
        hints['doc_profile_confidence'] = getattr(decision, 'doc_profile_confidence', None)
        
        # Remove None values
        hints = {k: v for k, v in hints.items() if v is not None}
    except Exception as e:
        logger.warning(f"Failed to extract doc hints: {e}")
    
    return hints


def build_ml_contract_v2(decision) -> Dict[str, Any]:
    """
    Build ML contract v2 export format.
    
    Returns dict in v2 shape:
    {
      "schema_version": "2.0",
      "inputs": {
        "signals_emitted": [...],  # ordered unique IDs
        "amounts": {...},          # reconciliation summary if available
        "doc": {...},              # minimal doc hints: geo, language, subtype if available
      },
      "label": decision.label,
      "score": decision.score,
      "debug": {...}  # optional diagnostics, safe to omit
    }
    
    Args:
        decision: ReceiptDecision object
    
    Returns:
        Dict with v2 ML contract
    """
    # Extract signals
    signals_emitted = _extract_signals_emitted(decision)
    
    # Extract amounts
    amounts = _extract_amounts_summary(decision)
    
    # Extract doc hints
    doc_hints = _extract_doc_hints(decision)
    
    # Build contract
    contract = {
        "schema_version": "2.0",
        "inputs": {
            "signals_emitted": signals_emitted,
            "amounts": amounts,
            "doc": doc_hints,
        },
        "label": getattr(decision, 'label', None),
        "score": getattr(decision, 'score', None),
    }
    
    # Add optional debug info
    debug = {}
    
    # Add decision metadata if available
    if hasattr(decision, 'decision_id'):
        debug['decision_id'] = decision.decision_id
    if hasattr(decision, 'created_at'):
        debug['created_at'] = decision.created_at
    if hasattr(decision, 'rule_version'):
        debug['rule_version'] = decision.rule_version
    if hasattr(decision, 'policy_version'):
        debug['policy_version'] = decision.policy_version
    if hasattr(decision, 'engine_version'):
        debug['engine_version'] = decision.engine_version
    
    # Add debug info if any
    if debug:
        contract['debug'] = debug
    
    return contract
