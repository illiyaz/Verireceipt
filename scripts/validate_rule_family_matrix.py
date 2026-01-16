#!/usr/bin/env python3
"""
Validate Rule × Family Matrix Compliance

Ensures that:
1. Every rule declares ALLOWED_DOC_FAMILIES in its header
2. Rule declarations match the canonical matrix
3. No rule executes outside its allow-list

Called by CI to enforce RAP-7 and RAP-8.

Usage:
    python scripts/validate_rule_family_matrix.py
"""

import sys
import re
from pathlib import Path
from typing import Dict, Set, List

# Import the canonical matrix
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.pipelines.rule_family_matrix import RULE_FAMILY_MATRIX, ExecutionMode


def extract_rule_declarations(rules_file: Path) -> Dict[str, Set[str]]:
    """Extract ALLOWED_DOC_FAMILIES declarations from rules.py"""
    content = rules_file.read_text()
    
    declarations = {}
    
    # Find all rule headers with ALLOWED_DOC_FAMILIES
    pattern = r'RULE_ID:\s*(\w+).*?ALLOWED_DOC_FAMILIES:\s*\[(.*?)\]'
    matches = re.finditer(pattern, content, re.DOTALL)
    
    for match in matches:
        rule_id = match.group(1)
        families_str = match.group(2)
        
        # Parse family list
        families = set()
        for family in re.findall(r'"([^"]+)"', families_str):
            families.add(family.upper())
        
        declarations[rule_id] = families
    
    return declarations


def get_matrix_allowed_families(rule_id: str) -> Set[str]:
    """Get allowed families from canonical matrix"""
    if rule_id not in RULE_FAMILY_MATRIX:
        return set()
    
    allowed = set()
    for family, mode in RULE_FAMILY_MATRIX[rule_id].items():
        if mode in (ExecutionMode.ALLOWED, ExecutionMode.SOFT):
            allowed.add(family.upper())
    
    return allowed


def validate_declarations(
    declarations: Dict[str, Set[str]],
    matrix: Dict[str, Dict[str, ExecutionMode]]
) -> List[str]:
    """Validate that declarations match the matrix"""
    errors = []
    
    # Check each rule in the matrix
    for rule_id in matrix.keys():
        matrix_families = get_matrix_allowed_families(rule_id)
        declared_families = declarations.get(rule_id, set())
        
        if not declared_families:
            errors.append(
                f"❌ {rule_id}: Missing ALLOWED_DOC_FAMILIES declaration in header"
            )
            continue
        
        # Check for mismatches
        missing = matrix_families - declared_families
        extra = declared_families - matrix_families
        
        if missing:
            errors.append(
                f"❌ {rule_id}: Missing families in declaration: {', '.join(missing)}"
            )
        
        if extra:
            errors.append(
                f"❌ {rule_id}: Extra families in declaration (not in matrix): {', '.join(extra)}"
            )
    
    # Check for rules with declarations but not in matrix
    for rule_id in declarations.keys():
        if rule_id not in matrix:
            errors.append(
                f"⚠️  {rule_id}: Has ALLOWED_DOC_FAMILIES but not in canonical matrix"
            )
    
    return errors


def check_enforcement(rules_file: Path) -> List[str]:
    """Check that rules enforce the matrix before execution"""
    content = rules_file.read_text()
    errors = []
    
    # Find all rule IDs
    rule_ids = re.findall(r'RULE_ID:\s*(\w+)', content)
    
    for rule_id in rule_ids:
        # Check if rule has enforcement call
        enforcement_pattern = rf'is_rule_allowed_for_family\(["\']?{rule_id}["\']?'
        if not re.search(enforcement_pattern, content):
            errors.append(
                f"⚠️  {rule_id}: Missing is_rule_allowed_for_family() enforcement call"
            )
    
    return errors


def main():
    """Main entry point"""
    rules_file = Path("app/pipelines/rules.py")
    
    if not rules_file.exists():
        print("❌ rules.py not found")
        sys.exit(1)
    
    print("🔍 Validating Rule × Family Matrix compliance...\n")
    
    # Extract declarations
    declarations = extract_rule_declarations(rules_file)
    
    print(f"Found {len(declarations)} rule(s) with ALLOWED_DOC_FAMILIES declarations:")
    for rule_id, families in sorted(declarations.items()):
        print(f"  - {rule_id}: {', '.join(sorted(families))}")
    print()
    
    # Validate against matrix
    validation_errors = validate_declarations(declarations, RULE_FAMILY_MATRIX)
    
    # Check enforcement
    enforcement_errors = check_enforcement(rules_file)
    
    all_errors = validation_errors + enforcement_errors
    
    if not all_errors:
        print("=" * 60)
        print("✅ All rules comply with Rule × Family Matrix")
        print("=" * 60)
        sys.exit(0)
    
    print("=" * 60)
    print("❌ RULE × FAMILY MATRIX VALIDATION FAILED")
    print("=" * 60)
    print()
    
    for error in all_errors:
        print(error)
    
    print()
    print("See RULE_FAMILY_MATRIX.md for the canonical matrix.")
    print()
    
    sys.exit(1)


if __name__ == "__main__":
    main()
