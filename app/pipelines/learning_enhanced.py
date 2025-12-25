"""
Enhanced learning functions for comprehensive feedback processing.

New functions to handle:
- Confirmed indicators (reinforce what AI got right)
- Data corrections (improve extraction accuracy)
- Detailed false indicator analysis with user explanations
"""

from typing import List, Tuple, Dict, Any
from datetime import datetime
import uuid

from app.models.feedback import ReceiptFeedback, LearningRule
from app.repository.feedback_store import get_feedback_store


def _reinforce_confirmed_indicators(feedback: ReceiptFeedback, store) -> Tuple[int, List[str]]:
    """
    Reinforce indicators that the user confirmed as correct.
    
    When users confirm an indicator, we increase its confidence slightly
    to make the system more confident in similar detections.
    """
    rules_updated = 0
    new_patterns = []
    
    for indicator in feedback.confirmed_indicators:
        # Extract pattern from confirmed indicator
        from app.pipelines.learning import _extract_pattern_from_indicator
        pattern = _extract_pattern_from_indicator(indicator)
        
        if pattern:
            # Find existing rule for this pattern
            existing_rules = store.get_learned_rules(enabled_only=False)
            matching_rule = next(
                (r for r in existing_rules if pattern.lower() in r.pattern.lower()),
                None
            )
            
            if matching_rule:
                # Increase confidence slightly (positive reinforcement)
                matching_rule.confidence_adjustment = min(0.5, matching_rule.confidence_adjustment + 0.02)
                matching_rule.learned_from_feedback_count += 1
                matching_rule.accuracy_on_validation = min(1.0, matching_rule.accuracy_on_validation + 0.05)
                matching_rule.last_updated = datetime.utcnow()
                store.save_learned_rule(matching_rule)
                rules_updated += 1
                new_patterns.append(f"Reinforced: {pattern}")
            else:
                # Create new rule with moderate confidence
                rule = LearningRule(
                    rule_id=f"lr_confirmed_{uuid.uuid4().hex[:8]}",
                    rule_type="confirmed_indicator",
                    pattern=pattern,
                    action="increase_fraud_score",
                    confidence_adjustment=0.10,
                    learned_from_feedback_count=1,
                    accuracy_on_validation=0.8,
                    auto_learned=True
                )
                store.save_learned_rule(rule)
                rules_updated += 1
                new_patterns.append(f"New confirmed pattern: {pattern}")
    
    return rules_updated, new_patterns


def _learn_from_data_corrections(feedback: ReceiptFeedback, store) -> Tuple[int, List[str]]:
    """
    Learn from user corrections to extracted data.
    
    This helps improve extraction accuracy by identifying patterns
    where OCR or extraction models make mistakes.
    
    Examples:
    - User corrects merchant name: Learn merchant name patterns
    - User corrects total: Learn amount extraction patterns
    - User corrects date: Learn date format patterns
    """
    rules_updated = 0
    new_patterns = []
    
    corrections = feedback.data_corrections
    
    # Learn from merchant corrections
    if 'merchant' in corrections and corrections['merchant']:
        corrected_merchant = corrections['merchant']
        
        # Create pattern for merchant name validation
        rule = LearningRule(
            rule_id=f"lr_merchant_{uuid.uuid4().hex[:8]}",
            rule_type="merchant_pattern",
            pattern=corrected_merchant[:50],  # Truncate for privacy
            action="validate_merchant",
            confidence_adjustment=0.0,  # Neutral - just for validation
            learned_from_feedback_count=1,
            auto_learned=True,
            metadata={
                "correction_type": "merchant_name",
                "original_extraction_failed": True
            }
        )
        store.save_learned_rule(rule)
        rules_updated += 1
        new_patterns.append(f"Merchant pattern learned")
    
    # Learn from total amount corrections
    if 'total' in corrections and corrections['total']:
        corrected_total = corrections['total']
        
        # Create pattern for amount validation
        rule = LearningRule(
            rule_id=f"lr_amount_{uuid.uuid4().hex[:8]}",
            rule_type="amount_pattern",
            pattern=f"total_range_{int(corrected_total)}",
            action="validate_amount",
            confidence_adjustment=0.0,
            learned_from_feedback_count=1,
            auto_learned=True,
            metadata={
                "correction_type": "total_amount",
                "corrected_value": corrected_total
            }
        )
        store.save_learned_rule(rule)
        rules_updated += 1
        new_patterns.append(f"Amount validation pattern learned")
    
    # Learn from date corrections
    if 'date' in corrections and corrections['date']:
        corrected_date = corrections['date']
        
        # Create pattern for date format validation
        rule = LearningRule(
            rule_id=f"lr_date_{uuid.uuid4().hex[:8]}",
            rule_type="date_pattern",
            pattern=f"date_format",
            action="validate_date",
            confidence_adjustment=0.0,
            learned_from_feedback_count=1,
            auto_learned=True,
            metadata={
                "correction_type": "date",
                "corrected_date": corrected_date
            }
        )
        store.save_learned_rule(rule)
        rules_updated += 1
        new_patterns.append(f"Date format pattern learned")
    
    # Learn from tax corrections
    if 'tax' in corrections and corrections['tax']:
        corrected_tax = corrections['tax']
        
        # Create pattern for tax validation
        rule = LearningRule(
            rule_id=f"lr_tax_{uuid.uuid4().hex[:8]}",
            rule_type="tax_pattern",
            pattern=f"tax_validation",
            action="validate_tax",
            confidence_adjustment=0.0,
            learned_from_feedback_count=1,
            auto_learned=True,
            metadata={
                "correction_type": "tax_amount",
                "corrected_value": corrected_tax
            }
        )
        store.save_learned_rule(rule)
        rules_updated += 1
        new_patterns.append(f"Tax validation pattern learned")
    
    return rules_updated, new_patterns


def _learn_from_false_indicators_enhanced(feedback: ReceiptFeedback, store) -> Tuple[int, List[str]]:
    """
    Enhanced version that uses user explanations for false indicators.
    
    Format: "indicator_text: user_explanation"
    Example: "Suspicious Software: TCPDF: TCPDF is commonly used for invoicing"
    
    This allows us to learn WHY something is a false alarm, not just that it is.
    """
    rules_updated = 0
    new_patterns = []
    
    for false_indicator in feedback.false_indicators:
        # Parse indicator and explanation
        parts = false_indicator.split(':', 2)
        
        if len(parts) >= 2:
            indicator_text = parts[0].strip()
            explanation = parts[-1].strip() if len(parts) > 2 else "No reason provided"
            
            # Extract pattern
            from app.pipelines.learning import _extract_pattern_from_indicator
            pattern = _extract_pattern_from_indicator(indicator_text)
            
            if pattern:
                # Find existing rule
                existing_rules = store.get_learned_rules(enabled_only=False)
                matching_rule = next(
                    (r for r in existing_rules if pattern.lower() in r.pattern.lower()),
                    None
                )
                
                if matching_rule:
                    # Reduce confidence based on false alarm
                    matching_rule.confidence_adjustment = max(0.0, matching_rule.confidence_adjustment - 0.08)
                    
                    # Store the explanation in metadata
                    if not matching_rule.metadata:
                        matching_rule.metadata = {}
                    
                    if 'false_alarm_reasons' not in matching_rule.metadata:
                        matching_rule.metadata['false_alarm_reasons'] = []
                    
                    matching_rule.metadata['false_alarm_reasons'].append({
                        'explanation': explanation,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    
                    # Disable if confidence drops to zero
                    if matching_rule.confidence_adjustment <= 0.0:
                        matching_rule.enabled = False
                        new_patterns.append(f"Disabled rule: {pattern} (too many false alarms)")
                    else:
                        new_patterns.append(f"Reduced sensitivity: {pattern}")
                    
                    matching_rule.last_updated = datetime.utcnow()
                    store.save_learned_rule(matching_rule)
                    rules_updated += 1
                else:
                    # Create a negative rule (whitelist)
                    rule = LearningRule(
                        rule_id=f"lr_whitelist_{uuid.uuid4().hex[:8]}",
                        rule_type="whitelist",
                        pattern=pattern,
                        action="reduce_fraud_score",
                        confidence_adjustment=-0.10,  # Negative adjustment
                        learned_from_feedback_count=1,
                        auto_learned=True,
                        metadata={
                            'false_alarm_explanation': explanation,
                            'created_from': 'user_feedback'
                        }
                    )
                    store.save_learned_rule(rule)
                    rules_updated += 1
                    new_patterns.append(f"Whitelisted: {pattern}")
    
    return rules_updated, new_patterns
