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
    
    # Learn from missed indicators
    if feedback.missed_indicators:
        missed_rules, missed_patterns = _learn_from_missed_indicators(feedback, store)
        rules_updated += missed_rules
        new_patterns.extend(missed_patterns)
    
    # Learn from false indicators
    if feedback.false_indicators:
        false_rules, false_patterns = _learn_from_false_indicators(feedback, store)
        rules_updated += false_rules
        new_patterns.extend(false_patterns)
    
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
        # Increase spacing detection sensitivity
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
    
    for indicator in feedback.missed_indicators:
        # Extract pattern from indicator description
        pattern = _extract_pattern_from_indicator(indicator)
        
        if pattern:
            # Create or update rule for this pattern
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
            rules_updated += 1
            new_patterns.append(pattern)
    
    return rules_updated, new_patterns


def _learn_from_false_indicators(feedback: ReceiptFeedback, store) -> Tuple[int, List[str]]:
    """
    Learn from indicators that were incorrectly flagged.
    
    These are false alarms that should be reduced or disabled.
    """
    rules_updated = 0
    new_patterns = []
    
    for indicator in feedback.false_indicators:
        # Find and reduce/disable the rule that caused this false indicator
        pattern = _extract_pattern_from_indicator(indicator)
        
        if pattern:
            existing_rules = store.get_learned_rules(enabled_only=False)
            matching_rule = next(
                (r for r in existing_rules if pattern.lower() in r.pattern.lower()),
                None
            )
            
            if matching_rule:
                # Reduce confidence or disable
                matching_rule.confidence_adjustment = max(0.0, matching_rule.confidence_adjustment - 0.05)
                if matching_rule.confidence_adjustment == 0.0:
                    matching_rule.enabled = False
                matching_rule.last_updated = datetime.utcnow()
                store.save_learned_rule(matching_rule)
                rules_updated += 1
                new_patterns.append(f"Reduced sensitivity for: {pattern}")
    
    return rules_updated, new_patterns


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
    
    for rule in rules:
        # Check if rule applies to these features
        if _rule_matches_features(rule, features):
            score_adjustment += rule.confidence_adjustment
            triggered_rules.append(f"{rule.rule_type}: {rule.pattern}")
    
    return score_adjustment, triggered_rules


def _rule_matches_features(rule: LearningRule, features: dict) -> bool:
    """
    Check if a learned rule matches the given features.
    
    This is a simple pattern matching - can be enhanced with ML later.
    """
    if rule.rule_type == "suspicious_software":
        producer = features.get("file_features", {}).get("producer", "")
        return rule.pattern.lower() in producer.lower()
    
    elif rule.rule_type == "spacing_threshold":
        spacing_issues = features.get("forensic_features", {}).get("has_excessive_spacing", False)
        return spacing_issues
    
    elif rule.rule_type == "date_manipulation":
        # Check for date issues
        return features.get("file_features", {}).get("has_date_issue", False)
    
    elif rule.rule_type == "user_identified_pattern":
        # Generic pattern matching
        # This would need to be more sophisticated in production
        return True  # For now, always apply user-identified patterns
    
    return False
