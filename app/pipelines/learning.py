"""
Local learning engine that improves fraud detection from user feedback.

Privacy-first design:
- All learning happens locally
- No data transmission
- Rules learned from corrections
- Continuous improvement
"""

from typing import List, Tuple
from datetime import datetime
import uuid
import re

from app.models.feedback import ReceiptFeedback, LearningRule, FeedbackType, CorrectVerdict
from app.repository.feedback_store import get_feedback_store


def learn_from_feedback(feedback: ReceiptFeedback) -> Tuple[int, List[str]]:
    """
    Learn from user feedback and update rules.
    
    Enhanced to use:
    - Confirmed indicators (what AI got right)
    - False indicators with explanations (what AI got wrong and why)
    - Missed indicators (what AI should have caught)
    - Data corrections (improve extraction accuracy)
    
    Returns:
        Tuple of (rules_updated, new_patterns_learned)
    """
    store = get_feedback_store()
    rules_updated = 0
    new_patterns = []
    
    # Learn from false negatives (system said real, was fake)
    if feedback.feedback_type == FeedbackType.FALSE_NEGATIVE:
        rules_updated, new_patterns = _learn_from_false_negative(feedback, store)
    
    # Learn from false positives (system said fake, was real)
    elif feedback.feedback_type == FeedbackType.FALSE_POSITIVE:
        rules_updated, new_patterns = _learn_from_false_positive(feedback, store)
    
    # Reinforce confirmed indicators (AI got these right!)
    if feedback.confirmed_indicators:
        confirmed_rules, confirmed_patterns = _reinforce_confirmed_indicators(feedback, store)
        rules_updated += confirmed_rules
        new_patterns.extend(confirmed_patterns)
    
    # Learn from missed indicators
    if feedback.missed_indicators:
        missed_rules, missed_patterns = _learn_from_missed_indicators(feedback, store)
        rules_updated += missed_rules
        new_patterns.extend(missed_patterns)
    
    # Learn from false indicators (with explanations)
    if feedback.false_indicators:
        false_rules, false_patterns = _learn_from_false_indicators(feedback, store)
        rules_updated += false_rules
        new_patterns.extend(false_patterns)
    
    # Learn from data corrections
    if feedback.data_corrections:
        correction_rules, correction_patterns = _learn_from_data_corrections(feedback, store)
        rules_updated += correction_rules
        new_patterns.extend(correction_patterns)
    
    return rules_updated, new_patterns


def _learn_from_false_negative(feedback: ReceiptFeedback, store) -> Tuple[int, List[str]]:
    """
    Learn from cases where system missed fraud.
    
    System said "real" but user says "fake" - we need to be more strict.
    """
    rules_updated = 0
    new_patterns = []
    
    # If software was detected but not flagged strongly enough
    if feedback.software_detected:
        software = feedback.software_detected
        
        # Check if we have a rule for this software
        existing_rules = store.get_learned_rules(enabled_only=False)
        software_rule = next(
            (r for r in existing_rules if r.rule_type == "suspicious_software" and r.pattern == software),
            None
        )
        
        if software_rule:
            # Increase the confidence adjustment
            software_rule.confidence_adjustment = min(0.5, software_rule.confidence_adjustment + 0.05)
            software_rule.learned_from_feedback_count += 1
            software_rule.last_updated = datetime.utcnow()
            store.save_learned_rule(software_rule)
            rules_updated += 1
        else:
            # Create new rule
            rule = LearningRule(
                rule_id=f"lr_{uuid.uuid4().hex[:8]}",
                rule_type="suspicious_software",
                pattern=software,
                action="increase_fraud_score",
                confidence_adjustment=0.20,
                learned_from_feedback_count=1,
                accuracy_on_validation=0.0,
                auto_learned=True
            )
            store.save_learned_rule(rule)
            rules_updated += 1
            new_patterns.append(f"Suspicious software: {software}")
    
    # If spacing issues were present but not detected
    if feedback.has_spacing_issue:
        existing_rules = store.get_learned_rules(enabled_only=False)
        spacing_rule = next(
            (r for r in existing_rules if r.rule_type == "spacing_threshold" and r.pattern == "consecutive_spaces"),
            None
        )
        if spacing_rule:
            spacing_rule.confidence_adjustment = min(0.5, spacing_rule.confidence_adjustment + 0.03)
            spacing_rule.learned_from_feedback_count += 1
            spacing_rule.last_updated = datetime.utcnow()
            store.save_learned_rule(spacing_rule)
            rules_updated += 1
        else:
            spacing_rule = LearningRule(
                rule_id=f"lr_spacing_{uuid.uuid4().hex[:8]}",
                rule_type="spacing_threshold",
                pattern="consecutive_spaces",
                action="lower_threshold",
                confidence_adjustment=0.15,
                learned_from_feedback_count=1,
                auto_learned=True
            )
            store.save_learned_rule(spacing_rule)
            rules_updated += 1
            new_patterns.append("Spacing anomaly detection")
    
    # If date issues were present
    if feedback.has_date_issue:
        existing_rules = store.get_learned_rules(enabled_only=False)
        date_rule = next(
            (r for r in existing_rules if r.rule_type == "date_manipulation" and r.pattern == "creation_after_receipt"),
            None
        )
        if date_rule:
            date_rule.confidence_adjustment = min(0.5, date_rule.confidence_adjustment + 0.03)
            date_rule.learned_from_feedback_count += 1
            date_rule.last_updated = datetime.utcnow()
            store.save_learned_rule(date_rule)
            rules_updated += 1
        else:
            date_rule = LearningRule(
                rule_id=f"lr_date_{uuid.uuid4().hex[:8]}",
                rule_type="date_manipulation",
                pattern="creation_after_receipt",
                action="increase_fraud_score",
                confidence_adjustment=0.25,
                learned_from_feedback_count=1,
                auto_learned=True
            )
            store.save_learned_rule(date_rule)
            rules_updated += 1
            new_patterns.append("Date manipulation detection")
    
    return rules_updated, new_patterns


def _learn_from_false_positive(feedback: ReceiptFeedback, store) -> Tuple[int, List[str]]:
    """
    Learn from cases where system incorrectly flagged real receipts.
    
    System said "fake" but user says "real" - we need to be less strict.
    """
    rules_updated = 0
    new_patterns = []
    
    # If software was flagged but shouldn't have been
    if feedback.software_detected and "Suspicious Software" in str(feedback.detected_indicators):
        software = feedback.software_detected
        
        # Check if we have a rule for this software
        existing_rules = store.get_learned_rules(enabled_only=False)
        software_rule = next(
            (r for r in existing_rules if r.rule_type == "suspicious_software" and r.pattern == software),
            None
        )
        
        if software_rule:
            # Decrease the confidence adjustment or disable
            if software_rule.confidence_adjustment > 0.05:
                software_rule.confidence_adjustment = max(0.0, software_rule.confidence_adjustment - 0.05)
                software_rule.learned_from_feedback_count += 1
                software_rule.last_updated = datetime.utcnow()
                store.save_learned_rule(software_rule)
                rules_updated += 1
            else:
                # Disable the rule if it's causing too many false positives
                software_rule.enabled = False
                software_rule.last_updated = datetime.utcnow()
                store.save_learned_rule(software_rule)
                rules_updated += 1
                new_patterns.append(f"Disabled overly strict rule for: {software}")
    
    return rules_updated, new_patterns


def _learn_from_missed_indicators(feedback: ReceiptFeedback, store) -> Tuple[int, List[str]]:
    """
    Learn from indicators that user says were missed.
    
    These are fraud signals the system should have detected but didn't.
    """
    rules_updated = 0
    new_patterns = []
    
    existing_rules = store.get_learned_rules(enabled_only=False)
    
    for indicator in feedback.missed_indicators:
        # Extract pattern from indicator description
        pattern = _extract_pattern_from_indicator(indicator)
        
        if pattern:
            # Check for existing rule with same type+pattern
            existing = next(
                (r for r in existing_rules
                 if r.rule_type == "user_identified_pattern" and r.pattern == pattern),
                None
            )
            if existing:
                existing.confidence_adjustment = min(0.5, existing.confidence_adjustment + 0.03)
                existing.learned_from_feedback_count += 1
                existing.last_updated = datetime.utcnow()
                store.save_learned_rule(existing)
                rules_updated += 1
            else:
                rule = LearningRule(
                    rule_id=f"lr_missed_{uuid.uuid4().hex[:8]}",
                    rule_type="user_identified_pattern",
                    pattern=pattern,
                    action="flag_suspicious",
                    confidence_adjustment=0.15,
                    learned_from_feedback_count=1,
                    auto_learned=True
                )
                store.save_learned_rule(rule)
                existing_rules.append(rule)  # Track for dedup within this loop
                rules_updated += 1
                new_patterns.append(pattern)
    
    return rules_updated, new_patterns


def _reinforce_confirmed_indicators(feedback: ReceiptFeedback, store) -> Tuple[int, List[str]]:
    """
    Reinforce indicators that the user confirmed as correct.
    
    When users confirm an indicator, we increase its confidence slightly.
    """
    rules_updated = 0
    new_patterns = []
    
    for indicator in feedback.confirmed_indicators:
        pattern = _extract_pattern_from_indicator(indicator)
        
        if pattern:
            existing_rules = store.get_learned_rules(enabled_only=False)
            matching_rule = next(
                (r for r in existing_rules if pattern.lower() in r.pattern.lower()),
                None
            )
            
            if matching_rule:
                matching_rule.confidence_adjustment = min(0.5, matching_rule.confidence_adjustment + 0.02)
                matching_rule.learned_from_feedback_count += 1
                matching_rule.last_updated = datetime.utcnow()
                store.save_learned_rule(matching_rule)
                rules_updated += 1
                new_patterns.append(f"Reinforced: {pattern}")
    
    return rules_updated, new_patterns


def _learn_from_data_corrections(feedback: ReceiptFeedback, store) -> Tuple[int, List[str]]:
    """
    Learn from user corrections to extracted data.
    """
    rules_updated = 0
    new_patterns = []
    
    corrections = feedback.data_corrections
    
    if 'merchant' in corrections and corrections['merchant']:
        merchant_val = corrections['merchant'][:50]
        existing_rules = store.get_learned_rules(enabled_only=False)
        existing = next(
            (r for r in existing_rules
             if r.rule_type == "merchant_pattern" and r.pattern == merchant_val),
            None
        )
        if existing:
            existing.learned_from_feedback_count += 1
            existing.last_updated = datetime.utcnow()
            store.save_learned_rule(existing)
            rules_updated += 1
        else:
            rule = LearningRule(
                rule_id=f"lr_merchant_{uuid.uuid4().hex[:8]}",
                rule_type="merchant_pattern",
                pattern=merchant_val,
                action="validate_merchant",
                confidence_adjustment=0.0,
                learned_from_feedback_count=1,
                auto_learned=True
            )
            store.save_learned_rule(rule)
            rules_updated += 1
            new_patterns.append("Merchant pattern learned")
    
    return rules_updated, new_patterns


def _learn_from_false_indicators(feedback: ReceiptFeedback, store) -> Tuple[int, List[str]]:
    """
    Learn from indicators that were incorrectly flagged.
    
    Enhanced to parse user explanations from format: "indicator: explanation"
    """
    rules_updated = 0
    new_patterns = []
    
    for false_indicator in feedback.false_indicators:
        # Parse indicator and explanation
        parts = false_indicator.split(':', 2)
        indicator_text = parts[0].strip()
        explanation = parts[-1].strip() if len(parts) > 2 else "No reason"
        
        pattern = _extract_pattern_from_indicator(indicator_text)
        
        if pattern:
            existing_rules = store.get_learned_rules(enabled_only=False)
            matching_rule = next(
                (r for r in existing_rules if pattern.lower() in r.pattern.lower()),
                None
            )
            
            if matching_rule:
                # Reduce confidence based on false alarm
                matching_rule.confidence_adjustment = max(0.0, matching_rule.confidence_adjustment - 0.08)
                
                if matching_rule.confidence_adjustment <= 0.0:
                    matching_rule.enabled = False
                    new_patterns.append(f"Disabled: {pattern}")
                else:
                    new_patterns.append(f"Reduced: {pattern}")
                
                matching_rule.last_updated = datetime.utcnow()
                store.save_learned_rule(matching_rule)
                rules_updated += 1
            else:
                # Create whitelist rule
                rule = LearningRule(
                    rule_id=f"lr_whitelist_{uuid.uuid4().hex[:8]}",
                    rule_type="whitelist",
                    pattern=pattern,
                    action="reduce_fraud_score",
                    confidence_adjustment=-0.10,
                    learned_from_feedback_count=1,
                    auto_learned=True
                )
                store.save_learned_rule(rule)
                rules_updated += 1
                new_patterns.append(f"Whitelisted: {pattern}")
    
    return rules_updated, new_patterns


def _get_pattern_details(pattern_type: str, features: dict) -> str:
    """
    Get detailed context about what triggered a learned pattern.
    
    This provides audit-friendly explanations for learned rules.
    """
    if pattern_type == "missing_elements":
        # Check what's actually missing
        missing_items = []
        text_features = features.get("text_features", {})
        
        if not text_features.get("has_total"):
            missing_items.append("total amount")
        if not text_features.get("has_date"):
            missing_items.append("transaction date")
        if not text_features.get("has_merchant"):
            missing_items.append("merchant name")
        if not text_features.get("has_phone"):
            missing_items.append("contact phone")
        if not text_features.get("has_address"):
            missing_items.append("business address")
        
        if missing_items:
            return f"Missing critical elements: {', '.join(missing_items)}. Real receipts typically include all these fields."
        else:
            return "Document structure appears incomplete based on learned patterns."
    
    elif pattern_type == "spacing_anomaly":
        forensic = features.get("forensic_features", {})
        max_spaces = forensic.get("max_consecutive_spaces", 0)
        has_excessive = forensic.get("has_excessive_spacing", False)
        
        if has_excessive:
            return f"Unusual spacing detected (up to {max_spaces} consecutive spaces). This is often used to manipulate OCR or hide text alignment issues in fake receipts."
        else:
            return "Spacing patterns match previously flagged suspicious receipts."
    
    elif pattern_type == "invalid_address":
        text_features = features.get("text_features", {})
        has_address = text_features.get("has_address", False)
        
        if not has_address:
            return "No valid business address found. Legitimate receipts typically include a physical address for the business."
        else:
            return "Address format matches patterns previously identified as suspicious by users."
    
    elif pattern_type == "invalid_phone":
        text_features = features.get("text_features", {})
        has_phone = text_features.get("has_phone", False)
        
        if not has_phone:
            return "No valid phone number found. Real businesses typically include contact information on receipts."
        else:
            return "Phone number format matches patterns previously flagged as suspicious."
    
    else:
        # Generic fallback
        return f"Pattern '{pattern_type}' matches characteristics of receipts previously flagged by users."


def _build_detailed_rule_message(rule: LearningRule, features: dict) -> str:
    """
    Build a detailed audit message for a triggered rule.
    
    Fallback for cases where _rule_matches_features returns True instead of a string.
    """
    pattern_details = _get_pattern_details(rule.pattern, features)
    return f"Learned pattern detected: {rule.rule_type} - {rule.pattern}. {pattern_details} Confidence adjustment: +{rule.confidence_adjustment:.2f}. Learned from {rule.learned_from_feedback_count} user feedback(s)."


def _extract_pattern_from_indicator(indicator: str) -> str:
    """
    Extract a pattern from an indicator description.
    
    Examples:
    - "Spacing anomalies in total amount" → "spacing_anomaly"
    - "Invalid phone number format" → "invalid_phone"
    - "Suspicious merchant name: ABC Corp" → "ABC Corp"
    """
    indicator_lower = indicator.lower()
    
    # Common patterns
    if "spacing" in indicator_lower:
        return "spacing_anomaly"
    elif "phone" in indicator_lower:
        return "invalid_phone"
    elif "address" in indicator_lower:
        return "invalid_address"
    elif "merchant" in indicator_lower:
        # Try to extract merchant name
        match = re.search(r'merchant[:\s]+([A-Za-z0-9\s]+)', indicator, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return "suspicious_merchant"
    elif "software" in indicator_lower or "pdf" in indicator_lower:
        # Try to extract software name
        match = re.search(r'[:\s]+([A-Za-z0-9]+)', indicator)
        if match:
            return match.group(1).strip()
        return "suspicious_software"
    elif "date" in indicator_lower:
        return "date_manipulation"
    else:
        # Generic pattern
        return indicator[:50]  # First 50 chars


def apply_learned_rules(features: dict) -> Tuple[float, List[str]]:
    """
    Apply learned rules to adjust fraud score.
    
    Args:
        features: Receipt features dictionary
        
    Returns:
        Tuple of (score_adjustment, triggered_rules)
    """
    store = get_feedback_store()
    rules = store.get_learned_rules(enabled_only=True)
    
    score_adjustment = 0.0
    triggered_rules = []
    _matched_types = set()  # Per-rule-type dedup to prevent score inflation
    
    for rule in rules:
        # Deduplicate: only allow one rule per (rule_type, pattern) combo
        dedup_key = (rule.rule_type, rule.pattern)
        if dedup_key in _matched_types:
            continue
        
        # Check if rule applies to these features
        match_result = _rule_matches_features(rule, features)
        if match_result:
            score_adjustment += rule.confidence_adjustment
            _matched_types.add(dedup_key)
            
            # Create detailed message for audit trail
            if isinstance(match_result, str):
                message = match_result
            else:
                message = _build_detailed_rule_message(rule, features)
            
            triggered_rules.append(message)
    
    # Cap total adjustment to prevent runaway scores
    score_adjustment = min(score_adjustment, 0.40)
    
    return score_adjustment, triggered_rules


def _rule_matches_features(rule: LearningRule, features: dict):
    """
    Check if a learned rule matches the given features.
    
    Returns:
        - False if no match
        - True for basic match
        - String with detailed message for audit trail
    """
    if rule.rule_type == "suspicious_software":
        producer = features.get("file_features", {}).get("producer", "")
        if rule.pattern.lower() in producer.lower():
            return f"Learned pattern detected: Suspicious software '{rule.pattern}' found in document metadata (Producer: {producer}). Confidence adjustment: +{rule.confidence_adjustment:.2f}. Learned from {rule.learned_from_feedback_count} user feedback(s)."
        return False
    
    elif rule.rule_type == "spacing_threshold":
        spacing_issues = features.get("forensic_features", {}).get("has_excessive_spacing", False)
        if spacing_issues:
            consecutive_spaces = features.get("forensic_features", {}).get("max_consecutive_spaces", 0)
            return f"Learned pattern detected: Excessive spacing anomaly (max {consecutive_spaces} consecutive spaces). This pattern was flagged by users {rule.learned_from_feedback_count} time(s) as suspicious. Confidence adjustment: +{rule.confidence_adjustment:.2f}."
        return False
    
    elif rule.rule_type == "date_manipulation":
        has_date_issue = features.get("file_features", {}).get("has_date_issue", False)
        if has_date_issue:
            return f"Learned pattern detected: Date manipulation indicators found. Receipt date appears after file creation date. This pattern was confirmed by users {rule.learned_from_feedback_count} time(s). Confidence adjustment: +{rule.confidence_adjustment:.2f}."
        return False
    
    elif rule.rule_type == "user_identified_pattern":
        # Check if this pattern actually matches the receipt features
        pattern_type = rule.pattern
        forensic = features.get("forensic_features", {})
        text_feat = features.get("text_features", {})
        
        matched = False
        if pattern_type == "spacing_anomaly" and forensic.get("has_excessive_spacing"):
            matched = True
        elif pattern_type == "invalid_address" and not text_feat.get("has_address"):
            matched = True
        elif pattern_type == "invalid_phone" and not text_feat.get("has_phone"):
            matched = True
        elif pattern_type == "date_manipulation" and features.get("file_features", {}).get("has_date_issue"):
            matched = True
        elif pattern_type == "amount_inflation":
            # Only match if there's evidence of amount issues (round total, mismatch, etc.)
            total = text_feat.get("total_amount")
            if total and isinstance(total, (int, float)) and total > 0 and total == int(total) and int(total) % 100 == 0:
                matched = True
        elif pattern_type not in ("spacing_anomaly", "invalid_address", "invalid_phone", "date_manipulation", "amount_inflation"):
            # Unknown pattern types: don't auto-match, require explicit feature presence
            matched = False
        
        if matched:
            detail_msg = _get_pattern_details(pattern_type, features)
            return f"Learned pattern detected: {pattern_type}. {detail_msg} This pattern was identified by users {rule.learned_from_feedback_count} time(s). Confidence adjustment: +{rule.confidence_adjustment:.2f}."
        return False
    
    return False
