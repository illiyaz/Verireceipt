# app/utils/audit_formatter.py
"""
Human-readable audit trail formatter for auditors and human review.

This module provides comprehensive, auditor-friendly formatting of receipt
analysis decisions, including geo-aware context, missing-field gate reasoning,
and step-by-step decision explanations.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class AuditFormatter:
    """Format receipt analysis decisions for human auditors."""
    
    @staticmethod
    def _get_all_events(decision: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get all events from both audit_events (ensemble) and events (rules).
        This ensures we don't miss rule events like GATE_MISSING_FIELDS.
        """
        all_events = []
        
        # Get ensemble audit events (reconciliation events)
        audit_events = decision.get("audit_events", [])
        if audit_events:
            for e in audit_events:
                if isinstance(e, dict):
                    all_events.append(e)
        
        # Get rule-based events (includes GATE_MISSING_FIELDS, R5, R6, R8, R9, etc.)
        rule_events = decision.get("events", [])
        if rule_events:
            for e in rule_events:
                if isinstance(e, dict):
                    all_events.append(e)
        
        return all_events
    
    @staticmethod
    def format_decision_summary(decision: Dict[str, Any]) -> str:
        """
        Create a comprehensive, human-readable summary for auditors.
        
        Args:
            decision: ReceiptDecision as dict (from to_dict())
        
        Returns:
            Multi-section formatted string for auditor review
        """
        sections = []
        
        # Header
        sections.append(AuditFormatter._format_header(decision))
        
        # Executive Summary
        sections.append(AuditFormatter._format_executive_summary(decision))
        
        # Geo-Aware Context
        sections.append(AuditFormatter._format_geo_context(decision))
        
        # Decision Logic
        sections.append(AuditFormatter._format_decision_logic(decision))
        
        # Missing Field Analysis
        sections.append(AuditFormatter._format_missing_field_analysis(decision))
        
        # Critical Events
        sections.append(AuditFormatter._format_critical_events(decision))
        
        # Recommendations
        sections.append(AuditFormatter._format_recommendations(decision))
        
        return "\n\n".join(sections)
    
    @staticmethod
    def _format_header(decision: Dict[str, Any]) -> str:
        """Format the report header with basic decision info."""
        decision_id = decision.get("decision_id", "N/A")
        created_at = decision.get("created_at", "N/A")
        label = decision.get("label") or "UNKNOWN"
        score = decision.get("score") or 0.0
        policy_name = decision.get("policy_name") or "default"
        policy_version = decision.get("policy_version") or "0.0.0"
        rule_version = decision.get("rule_version") or "0.0.0"
        
        return f"""
╔═══════════════════════════════════════════════════════════════════════════╗
║                     VERIRECEIPT AUDIT REPORT                              ║
╚═══════════════════════════════════════════════════════════════════════════╝

Decision ID:     {decision_id}
Timestamp:       {created_at}
Final Verdict:   {label.upper()} (Score: {score:.2f})
Policy:          {decision.get("policy_name", "default")} v{decision.get("policy_version", "0.0.0")}
Rule Version:    {decision.get("rule_version", "0.0.0")}
"""
    
    @staticmethod
    def _format_executive_summary(decision: Dict[str, Any]) -> str:
        """Format executive summary section."""
        label = decision.get("label") or "UNKNOWN"
        score = decision.get("score") or 0.0
        reasons = decision.get("reasons", [])
        
        # Determine verdict explanation
        if label == "SUSPICIOUS":
            verdict_explanation = "⚠️  Document flagged as SUSPICIOUS - requires human review"
        elif label == "LEGITIMATE":
            verdict_explanation = "✅ Document appears LEGITIMATE - passed all checks"
        elif label == "HUMAN_REVIEW":
            verdict_explanation = "👤 Document routed to HUMAN_REVIEW - insufficient confidence"
        else:
            verdict_explanation = f"❓ Document classified as {label}"
        
        summary = f"""
═══════════════════════════════════════════════════════════════════════════
EXECUTIVE SUMMARY
═══════════════════════════════════════════════════════════════════════════

{verdict_explanation}

Fraud Risk Score: {score:.2f} / 1.00
"""
        
        if reasons:
            summary += "\nKey Concerns:\n"
            for i, reason in enumerate(reasons[:5], 1):
                summary += f"  {i}. {reason}\n"
            if len(reasons) > 5:
                summary += f"  ... and {len(reasons) - 5} more concerns\n"
        else:
            summary += "\nNo specific concerns identified.\n"
        
        return summary
    
    @staticmethod
    def _format_geo_context(decision: Dict[str, Any]) -> str:
        """Format geo-aware classification context."""
        lang = decision.get("lang_guess") or "UNKNOWN"
        lang_conf = decision.get("lang_confidence") or 0.0
        geo = decision.get("geo_country_guess") or "UNKNOWN"
        geo_conf = decision.get("geo_confidence") or 0.0
        doc_family = decision.get("doc_family") or "UNKNOWN"
        doc_subtype = decision.get("doc_subtype") or "UNKNOWN"
        doc_conf = decision.get("doc_profile_confidence") or 0.0
        
        # Get geo evidence from debug or audit events
        geo_evidence = []
        debug = decision.get("debug", {})
        if debug and "doc_profile" in debug:
            geo_evidence = debug["doc_profile"].get("geo_evidence", [])
        
        section = f"""
═══════════════════════════════════════════════════════════════════════════
GEO-AWARE CLASSIFICATION CONTEXT
═══════════════════════════════════════════════════════════════════════════

Language Detection:
  • Detected Language: {lang.upper()} (confidence: {lang_conf:.2f})
  • Interpretation: {AuditFormatter._interpret_language(lang, lang_conf)}

Geographic Origin:
  • Detected Country: {geo.upper()} (confidence: {geo_conf:.2f})
  • Interpretation: {AuditFormatter._interpret_geo(geo, geo_conf)}
"""
        
        if geo_evidence:
            section += "  • Evidence Found:\n"
            for evidence in geo_evidence[:5]:
                section += f"    - {evidence}\n"
        
        section += f"""
Document Classification:
  • Family: {doc_family}
  • Subtype: {doc_subtype} (confidence: {doc_conf:.2f})
  • Interpretation: {AuditFormatter._interpret_doc_subtype(doc_subtype, doc_conf)}
"""
        
        return section
    
    @staticmethod
    def _interpret_language(lang: str, confidence: float) -> str:
        """Provide human interpretation of language detection."""
        if lang == "unknown":
            return "Language could not be determined - document may be non-textual or use uncommon language"
        elif confidence < 0.3:
            return f"Low confidence in {lang.upper()} detection - mixed language or insufficient text"
        elif confidence < 0.6:
            return f"Moderate confidence - document appears to be in {lang.upper()}"
        else:
            return f"High confidence - document is clearly in {lang.upper()}"
    
    @staticmethod
    def _interpret_geo(geo: str, confidence: float) -> str:
        """Provide human interpretation of geo detection."""
        if geo == "UNKNOWN":
            if confidence < 0.3:
                return "⚠️  Country origin unclear - ambiguous signals (e.g., $ symbol, generic format)"
            else:
                return "Country could not be determined with confidence"
        elif confidence < 0.4:
            return f"Low confidence in {geo} origin - weak or conflicting signals"
        elif confidence < 0.7:
            return f"Moderate confidence - document likely from {geo}"
        else:
            return f"High confidence - document clearly from {geo}"
    
    @staticmethod
    def _interpret_doc_subtype(subtype: str, confidence: float) -> str:
        """Provide human interpretation of document subtype."""
        if subtype in ("MISC", "UNKNOWN"):
            return "⚠️  Document type unclear - fallback classification used"
        elif confidence < 0.4:
            return f"Low confidence in {subtype} classification - requires corroboration"
        elif confidence < 0.7:
            return f"Moderate confidence - document appears to be {subtype}"
        else:
            return f"High confidence - document is clearly {subtype}"
    
    @staticmethod
    def _format_decision_logic(decision: Dict[str, Any]) -> str:
        """Format decision logic explanation."""
        audit_events = AuditFormatter._get_all_events(decision)
        
        section = f"""
═══════════════════════════════════════════════════════════════════════════
DECISION LOGIC BREAKDOWN
═══════════════════════════════════════════════════════════════════════════

Total Events Logged: {len(audit_events)}
"""
        
        # Group events by severity
        hard_fails = [e for e in audit_events if e.get("severity") == "HARD_FAIL"]
        critical = [e for e in audit_events if e.get("severity") == "CRITICAL"]
        warnings = [e for e in audit_events if e.get("severity") == "WARNING"]
        info = [e for e in audit_events if e.get("severity") == "INFO"]
        
        section += f"""
Event Summary:
  • HARD_FAIL events: {len(hard_fails)} (automatic suspicious)
  • CRITICAL events: {len(critical)} (high fraud risk)
  • WARNING events: {len(warnings)} (moderate concern)
  • INFO events: {len(info)} (context/metadata)
"""
        
        return section
    
    @staticmethod
    def _format_missing_field_analysis(decision: Dict[str, Any]) -> str:
        """Format missing field analysis with gate reasoning."""
        audit_events = AuditFormatter._get_all_events(decision)
        
        # Check if missing-field gate was triggered
        gate_event = None
        for event in audit_events:
            if event.get("code") == "GATE_MISSING_FIELDS":
                gate_event = event
                break
        
        section = f"""
═══════════════════════════════════════════════════════════════════════════
MISSING FIELD ANALYSIS
═══════════════════════════════════════════════════════════════════════════
"""
        
        if gate_event:
            evidence = gate_event.get("evidence", {})
            section += f"""
⚠️  MISSING-FIELD PENALTIES DISABLED

Reason: {gate_event.get("message", "Unknown")}

Gate Trigger Conditions:
  • Geo Country: {evidence.get("geo_country_guess", "N/A")} (confidence: {evidence.get("geo_confidence", 0.0):.2f})
  • Doc Subtype: {evidence.get("doc_subtype_guess", "N/A")} (confidence: {evidence.get("doc_profile_confidence", 0.0):.2f})
  • Language: {evidence.get("lang_guess", "N/A")} (confidence: {evidence.get("lang_confidence", 0.0):.2f})

Auditor Guidance:
  ✓ Missing fields (merchant, date, phone, address, tax ID) were NOT penalized
  ✓ This is intentional - UNKNOWN geo or MISC subtype should not imply fraud
  ✓ Evaluate document based on:
    - Presence of editing software (ilovepdf, photoshop, etc.)
    - Tampering signals (checksum anomalies, metadata inconsistencies)
    - Visual realism (if vision model results available)
    - Layout consistency (if layout model results available)
  ✓ If no strong fraud signals exist, recommend LEGITIMATE or request more context
  ✓ Do NOT mark suspicious solely due to missing fields when gate is active
"""
        else:
            section += """
✓ Missing-field penalties ENABLED (normal mode)

This document has sufficient geo/doc classification confidence.
Missing critical fields (merchant, date, etc.) are treated as fraud indicators.
"""
            
            # Check for missing field events
            missing_events = [
                e for e in audit_events 
                if e.get("code") in ("R5_NO_AMOUNTS", "R6_NO_TOTAL_LINE", "R8_NO_DATE", "R9_NO_MERCHANT")
            ]
            
            if missing_events:
                section += "\nMissing Field Events Triggered:\n"
                for event in missing_events:
                    section += f"  • {event.get('code')}: {event.get('message')}\n"
        
        return section
    
    @staticmethod
    def _format_critical_events(decision: Dict[str, Any]) -> str:
        """Format critical and hard-fail events."""
        audit_events = AuditFormatter._get_all_events(decision)
        
        critical_events = [
            e for e in audit_events 
            if e.get("severity") in ("HARD_FAIL", "CRITICAL")
        ]
        
        if not critical_events:
            return """
═══════════════════════════════════════════════════════════════════════════
CRITICAL EVENTS
═══════════════════════════════════════════════════════════════════════════

✓ No critical fraud indicators detected.
"""
        
        section = f"""
═══════════════════════════════════════════════════════════════════════════
CRITICAL EVENTS ({len(critical_events)} found)
═══════════════════════════════════════════════════════════════════════════
"""
        
        for i, event in enumerate(critical_events, 1):
            severity = event.get("severity", "UNKNOWN")
            code = event.get("code", "UNKNOWN")
            message = event.get("message", "No message")
            evidence = event.get("evidence", {})
            
            section += f"""
{i}. [{severity}] {code}
   Message: {message}
   Source: {event.get("source", "unknown")}
"""
            if evidence:
                section += "   Evidence:\n"
                for key, value in list(evidence.items())[:5]:
                    section += f"     • {key}: {value}\n"
            section += "\n"
        
        return section
    
    @staticmethod
    def _format_recommendations(decision: Dict[str, Any]) -> str:
        """Format auditor recommendations."""
        label = decision.get("label") or "UNKNOWN"
        score = decision.get("score") or 0.0
        geo = decision.get("geo_country_guess") or "UNKNOWN"
        geo_conf = decision.get("geo_confidence") or 0.0
        doc_subtype = decision.get("doc_subtype") or "UNKNOWN"
        
        section = f"""
═══════════════════════════════════════════════════════════════════════════
AUDITOR RECOMMENDATIONS
═══════════════════════════════════════════════════════════════════════════
"""
        
        # Generate context-aware recommendations
        recommendations = []
        
        if label == "SUSPICIOUS" and score < 0.4:
            recommendations.append("⚠️  Low fraud score but marked suspicious - review for false positive")
        
        if geo == "UNKNOWN" and geo_conf < 0.3:
            recommendations.append("🌍 Geographic origin unclear - consider requesting additional context from submitter")
            recommendations.append("   (e.g., 'Where was this receipt from?' or 'What merchant is this?')")
        
        if doc_subtype in ("MISC", "UNKNOWN"):
            recommendations.append("📄 Document type unclear - visual inspection recommended")
            recommendations.append("   Check if document is actually a receipt/invoice or something else")
        
        if label == "LEGITIMATE" and score > 0.3:
            recommendations.append("⚠️  Marked legitimate but has elevated fraud score - spot check recommended")
        
        # Check for editing software
        audit_events = AuditFormatter._get_all_events(decision)
        has_editing_software = any(
            e.get("code") == "R1_SUSPICIOUS_SOFTWARE" 
            for e in audit_events
        )
        if has_editing_software:
            recommendations.append("🚨 EDITING SOFTWARE DETECTED - High priority for manual review")
            recommendations.append("   This is a strong fraud indicator regardless of other factors")
        
        # Check for missing-field gate
        has_gate = any(
            e.get("code") == "GATE_MISSING_FIELDS" 
            for e in audit_events
        )
        if has_gate:
            recommendations.append("🔓 Missing-field penalties were disabled for this document")
            recommendations.append("   Focus on tampering signals, not missing fields")
        
        if not recommendations:
            recommendations.append("✓ No special recommendations - standard review process applies")
        
        for rec in recommendations:
            section += f"\n{rec}"
        
        section += "\n"
        return section


def format_audit_for_human_review(decision_dict: Dict[str, Any]) -> str:
    """
    Main entry point: Format a ReceiptDecision for human auditor review.
    
    Args:
        decision_dict: ReceiptDecision.to_dict() output
    
    Returns:
        Comprehensive, formatted audit report string
    """
    return AuditFormatter.format_decision_summary(decision_dict)


def format_audit_events_table(audit_events: List[Dict[str, Any]]) -> str:
    """
    Format audit events as a readable table.
    
    Args:
        audit_events: List of AuditEvent dicts
    
    Returns:
        Formatted table string
    """
    if not audit_events:
        return "No audit events recorded."
    
    lines = []
    lines.append("=" * 120)
    lines.append(f"{'#':<4} {'SEVERITY':<12} {'CODE':<30} {'MESSAGE':<60}")
    lines.append("=" * 120)
    
    for i, event in enumerate(audit_events, 1):
        severity = event.get("severity", "INFO")
        code = event.get("code", "UNKNOWN")
        message = event.get("message", "")
        
        # Truncate message if too long
        if len(message) > 57:
            message = message[:54] + "..."
        
        lines.append(f"{i:<4} {severity:<12} {code:<30} {message:<60}")
    
    lines.append("=" * 120)
    return "\n".join(lines)
