#!/usr/bin/env python3
"""
Validate Rule Headers - Enforces Rule Admission Policy (RAP)

Checks that new rules have mandatory header blocks with all required fields.
Called by CI to block PRs that violate RAP.

Usage:
    python scripts/validate_rule_headers.py /tmp/new_rules.txt
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Set


REQUIRED_HEADER_FIELDS = {
    "RULE_ID",
    "SCOPE",
    "INTENT",
    "CONFIDENCE_GATE",
    "FAILURE_MODE",
    "SEVERITY_RANGE",
    "GOLDEN_TEST",
    "VERSION",
}


def extract_rule_header(rules_file: Path, rule_id: str) -> Dict[str, str]:
    """Extract the header block for a specific rule"""
    content = rules_file.read_text()
    
    # Find the rule's docstring
    pattern = rf'RULE_ID:\s*{re.escape(rule_id)}.*?"""'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        return {}
    
    header_text = match.group(0)
    
    # Extract fields
    fields = {}
    for field in REQUIRED_HEADER_FIELDS:
        field_pattern = rf'{field}:\s*(.+?)(?=\n\s*[A-Z_]+:|""")'
        field_match = re.search(field_pattern, header_text, re.DOTALL)
        if field_match:
            fields[field] = field_match.group(1).strip()
    
    return fields


def validate_rule_header(rule_id: str, header: Dict[str, str]) -> List[str]:
    """Validate that a rule header has all required fields"""
    errors = []
    
    # Check for missing fields
    missing_fields = REQUIRED_HEADER_FIELDS - set(header.keys())
    if missing_fields:
        errors.append(f"Missing required fields: {', '.join(missing_fields)}")
    
    # Validate SCOPE format
    if "SCOPE" in header:
        scope = header["SCOPE"]
        valid_scope_keywords = ["doc_family", "doc_subtype", "doc_class", "intent"]
        if not any(kw in scope for kw in valid_scope_keywords):
            errors.append(f"Invalid SCOPE: must contain one of {valid_scope_keywords}")
    
    # Validate CONFIDENCE_GATE exists
    if "CONFIDENCE_GATE" in header:
        gate = header["CONFIDENCE_GATE"]
        if "confidence" not in gate.lower() and "gate" not in gate.lower():
            errors.append("CONFIDENCE_GATE must specify a confidence threshold or gating condition")
    
    # Validate GOLDEN_TEST path
    if "GOLDEN_TEST" in header:
        test_path = header["GOLDEN_TEST"]
        if not test_path.startswith("tests/golden/"):
            errors.append(f"GOLDEN_TEST must be in tests/golden/ directory")
        
        # Check if test file exists
        test_file = Path(test_path)
        if not test_file.exists():
            errors.append(f"GOLDEN_TEST file not found: {test_path}")
    
    # Validate VERSION format
    if "VERSION" in header:
        version = header["VERSION"]
        if not re.match(r'^\d+\.\d+$', version):
            errors.append(f"VERSION must be in format X.Y (e.g., 1.0)")
    
    return errors


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python validate_rule_headers.py <new_rules_file>")
        sys.exit(1)
    
    new_rules_file = Path(sys.argv[1])
    
    if not new_rules_file.exists():
        print("✅ No new rules detected")
        sys.exit(0)
    
    # Read new rule IDs
    new_rule_ids = new_rules_file.read_text().strip().split('\n')
    new_rule_ids = [r.strip() for r in new_rule_ids if r.strip()]
    
    if not new_rule_ids:
        print("✅ No new rules detected")
        sys.exit(0)
    
    print(f"🔍 Validating {len(new_rule_ids)} new rule(s)...")
    print()
    
    rules_file = Path("app/pipelines/rules.py")
    all_valid = True
    
    for rule_id in new_rule_ids:
        print(f"Checking {rule_id}...")
        
        header = extract_rule_header(rules_file, rule_id)
        
        if not header:
            print(f"  ❌ No header block found for {rule_id}")
            print(f"     Add mandatory header (see RULE_ADMISSION_POLICY.md)")
            all_valid = False
            continue
        
        errors = validate_rule_header(rule_id, header)
        
        if errors:
            print(f"  ❌ Header validation failed:")
            for error in errors:
                print(f"     - {error}")
            all_valid = False
        else:
            print(f"  ✅ Header valid")
        
        print()
    
    if not all_valid:
        print("=" * 60)
        print("❌ RULE PR GATE FAILED")
        print("=" * 60)
        print()
        print("New rules must comply with Rule Admission Policy (RAP).")
        print("See RULE_ADMISSION_POLICY.md for requirements.")
        print()
        sys.exit(1)
    
    print("=" * 60)
    print("✅ All rule headers valid")
    print("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    main()
