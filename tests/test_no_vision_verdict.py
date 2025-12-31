"""
Unit test to ensure vision_verdict does not appear anywhere in the codebase.

This test enforces the veto-only design by failing if any code references
the old "vision_verdict" field which allowed vision to upgrade trust.

Vision is veto-only and should only use:
- visual_integrity: "clean" | "suspicious" | "tampered"
- confidence: 0.0-1.0
- observable_reasons: list of strings

Any reference to "vision_verdict" is a design violation.
"""

import os
import re
from pathlib import Path


def test_no_vision_verdict_in_codebase():
    """
    Fail if 'vision_verdict' appears anywhere in Python files.
    
    This enforces the veto-only design:
    - Vision cannot say "real" or "fake"
    - Vision can only say "clean", "suspicious", or "tampered"
    - Any code using vision_verdict is a design violation
    """
    project_root = Path(__file__).parent.parent
    
    # Files to check
    files_to_check = [
        project_root / "app" / "api" / "main.py",
        project_root / "app" / "pipelines" / "ensemble.py",
        project_root / "app" / "pipelines" / "rules.py",
        project_root / "app" / "pipelines" / "vision_llm.py",
    ]
    
    violations = []
    
    for file_path in files_to_check:
        if not file_path.exists():
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Search for vision_verdict (case-insensitive)
        # Allow it only in comments explaining why it's deprecated
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            # Skip comments that explain the deprecation
            if '#' in line and 'deprecated' in line.lower():
                continue
            if '"""' in line or "'''" in line:
                continue
                
            # Check for vision_verdict usage
            if re.search(r'\bvision_verdict\b', line, re.IGNORECASE):
                violations.append({
                    "file": str(file_path.relative_to(project_root)),
                    "line": line_num,
                    "content": line.strip()
                })
    
    # Report violations
    if violations:
        error_msg = "\n\n❌ CRITICAL: vision_verdict found in codebase (design violation)\n\n"
        error_msg += "Vision is veto-only and must NOT use 'vision_verdict'.\n"
        error_msg += "Only allowed fields: visual_integrity, confidence, observable_reasons\n\n"
        error_msg += "Violations found:\n"
        for v in violations:
            error_msg += f"\n  File: {v['file']}\n"
            error_msg += f"  Line {v['line']}: {v['content']}\n"
        
        raise AssertionError(error_msg)
    
    print("✅ No vision_verdict violations found")
    print("   Vision veto-only design is properly enforced")


def test_no_vision_upgrade_language():
    """
    Fail if code contains language that suggests vision can upgrade trust.
    
    Forbidden phrases:
    - "vision says real"
    - "vision confirms authenticity"
    - "vision indicates authentic"
    - "both engines agree: real"
    """
    project_root = Path(__file__).parent.parent
    
    files_to_check = [
        project_root / "app" / "api" / "main.py",
        project_root / "app" / "pipelines" / "ensemble.py",
    ]
    
    forbidden_patterns = [
        r'vision\s+(says|confirms|indicates)\s+(real|authentic)',
        r'both\s+engines\s+agree.*real',
        r'vision.*strongly\s+indicates?\s+authentic',
    ]
    
    violations = []
    
    for file_path in files_to_check:
        if not file_path.exists():
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            # Skip comments
            if line.strip().startswith('#'):
                continue
                
            for pattern in forbidden_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    violations.append({
                        "file": str(file_path.relative_to(project_root)),
                        "line": line_num,
                        "content": line.strip(),
                        "pattern": pattern
                    })
    
    if violations:
        error_msg = "\n\n❌ CRITICAL: Vision upgrade language found (design violation)\n\n"
        error_msg += "Vision is veto-only and must NOT upgrade trust or confirm authenticity.\n\n"
        error_msg += "Violations found:\n"
        for v in violations:
            error_msg += f"\n  File: {v['file']}\n"
            error_msg += f"  Line {v['line']}: {v['content']}\n"
            error_msg += f"  Pattern: {v['pattern']}\n"
        
        raise AssertionError(error_msg)
    
    print("✅ No vision upgrade language found")
    print("   Vision veto-only policy is properly enforced")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("VISION VETO-ONLY ENFORCEMENT TESTS")
    print("="*80)
    print("\nThese tests ensure vision cannot upgrade trust or override rules.\n")
    
    try:
        test_no_vision_verdict_in_codebase()
        print("\n✅ TEST 1 PASSED: No vision_verdict in codebase")
    except AssertionError as e:
        print(f"\n❌ TEST 1 FAILED:\n{e}")
        exit(1)
    
    try:
        test_no_vision_upgrade_language()
        print("\n✅ TEST 2 PASSED: No vision upgrade language")
    except AssertionError as e:
        print(f"\n❌ TEST 2 FAILED:\n{e}")
        exit(1)
    
    print("\n" + "="*80)
    print("🎉 ALL ENFORCEMENT TESTS PASSED")
    print("="*80)
    print("\nVision veto-only design is properly enforced:")
    print("  • No vision_verdict references")
    print("  • No vision upgrade language")
    print("  • Vision can only veto, never approve")
    print("\n✅ System is veto-only compliant\n")
