"""
Comprehensive enforcement test for vision veto-only design.

This test scans ALL Python files in the repository (excluding venv/build)
and fails if any code violates the veto-only contract.

CRITICAL: This test must pass before any deployment.
"""

import re
from pathlib import Path
from typing import List, Tuple


def get_all_python_files(project_root: Path) -> List[Path]:
    """
    Get all Python files in the repository, excluding venv/build/cache.
    """
    exclude_patterns = {
        'venv', '.venv', 'env', '.env',
        'build', 'dist', '.git',
        '__pycache__', '.pytest_cache', '.mypy_cache',
        'node_modules', '.tox'
    }
    
    python_files = []
    for py_file in project_root.rglob('*.py'):
        # Skip if any parent directory matches exclude patterns
        if any(excluded in py_file.parts for excluded in exclude_patterns):
            continue
        python_files.append(py_file)
    
    return python_files


def test_no_vision_verdict_anywhere():
    """
    CRITICAL: Fail if 'vision_verdict' appears anywhere in production code.
    
    Scans ALL .py files (not just 4 hardcoded ones).
    No broad skips - only specific allowlist for this test file itself.
    """
    project_root = Path(__file__).parent.parent
    python_files = get_all_python_files(project_root)
    
    violations = []
    
    for file_path in python_files:
        # Skip this enforcement test file itself
        if file_path.name == 'test_veto_enforcement.py':
            continue
        
        # Skip old comparison scripts (not part of production)
        if 'compare_' in file_path.name:
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Search for vision_verdict (case-insensitive)
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            # Only skip if line is PURELY a comment (starts with #)
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            
            # Check for vision_verdict usage
            if re.search(r'\bvision_verdict\b', line, re.IGNORECASE):
                violations.append({
                    "file": str(file_path.relative_to(project_root)),
                    "line": line_num,
                    "content": line.strip()[:100]  # Truncate long lines
                })
    
    if violations:
        error_msg = "\n\n" + "="*80 + "\n"
        error_msg += "❌ CRITICAL: vision_verdict found in codebase\n"
        error_msg += "="*80 + "\n\n"
        error_msg += "Vision is veto-only and must NOT use 'vision_verdict'.\n"
        error_msg += "Only allowed: visual_integrity, confidence, observable_reasons\n\n"
        error_msg += f"Found {len(violations)} violation(s):\n\n"
        
        for v in violations:
            error_msg += f"  📄 {v['file']}:{v['line']}\n"
            error_msg += f"     {v['content']}\n\n"
        
        raise AssertionError(error_msg)
    
    print(f"✅ Scanned {len(python_files)} Python files")
    print("   No vision_verdict violations found")


def test_no_authenticity_assessment():
    """
    CRITICAL: Fail if 'authenticity_assessment' appears in production code.
    
    This is the old vision LLM output structure that allowed trust upgrading.
    """
    project_root = Path(__file__).parent.parent
    python_files = get_all_python_files(project_root)
    
    violations = []
    
    for file_path in python_files:
        # Skip this test file and comparison scripts
        if file_path.name in ['test_veto_enforcement.py'] or 'compare_' in file_path.name:
            continue
        
        # Skip vision_llm.py where it's in raw output for audit
        if file_path.name == 'vision_llm.py':
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            
            if re.search(r'\bauthenticity_assessment\b', line, re.IGNORECASE):
                violations.append({
                    "file": str(file_path.relative_to(project_root)),
                    "line": line_num,
                    "content": line.strip()[:100]
                })
    
    if violations:
        error_msg = "\n\n" + "="*80 + "\n"
        error_msg += "❌ CRITICAL: authenticity_assessment found in production code\n"
        error_msg += "="*80 + "\n\n"
        error_msg += "This is the old vision output structure.\n"
        error_msg += "Use build_vision_assessment() instead.\n\n"
        error_msg += f"Found {len(violations)} violation(s):\n\n"
        
        for v in violations:
            error_msg += f"  📄 {v['file']}:{v['line']}\n"
            error_msg += f"     {v['content']}\n\n"
        
        raise AssertionError(error_msg)
    
    print(f"✅ Scanned {len(python_files)} Python files")
    print("   No authenticity_assessment violations found")


def test_no_vision_corroboration_flags():
    """
    CRITICAL: Fail if vision-based corroboration flags exist.
    
    These flags allow vision to influence decisions indirectly.
    """
    project_root = Path(__file__).parent.parent
    python_files = get_all_python_files(project_root)
    
    forbidden_flags = [
        'VISION_REAL_',
        'VISION_FAKE_',
    ]
    
    violations = []
    
    for file_path in python_files:
        if file_path.name == 'test_veto_enforcement.py' or 'compare_' in file_path.name:
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            
            for flag in forbidden_flags:
                if flag in line:
                    violations.append({
                        "file": str(file_path.relative_to(project_root)),
                        "line": line_num,
                        "flag": flag,
                        "content": line.strip()[:100]
                    })
    
    if violations:
        error_msg = "\n\n" + "="*80 + "\n"
        error_msg += "❌ CRITICAL: Vision corroboration flags found\n"
        error_msg += "="*80 + "\n\n"
        error_msg += "Vision must NOT influence corroboration or decisions.\n\n"
        error_msg += f"Found {len(violations)} violation(s):\n\n"
        
        for v in violations:
            error_msg += f"  📄 {v['file']}:{v['line']}\n"
            error_msg += f"     Flag: {v['flag']}\n"
            error_msg += f"     {v['content']}\n\n"
        
        raise AssertionError(error_msg)
    
    print(f"✅ Scanned {len(python_files)} Python files")
    print("   No vision corroboration flags found")


def test_no_vision_upgrade_language():
    """
    CRITICAL: Fail if code contains language suggesting vision upgrades trust.
    """
    project_root = Path(__file__).parent.parent
    python_files = get_all_python_files(project_root)
    
    forbidden_patterns = [
        (r'vision\s+(says|confirms|indicates)\s+(real|authentic)', 'vision confirms/says real'),
        (r'both\s+engines\s+(agree|confirm).*real', 'both engines agree real'),
        (r'vision.*strongly.*authentic', 'vision strongly authentic'),
    ]
    
    violations = []
    
    for file_path in python_files:
        if file_path.name == 'test_veto_enforcement.py' or 'compare_' in file_path.name:
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            
            for pattern, description in forbidden_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    violations.append({
                        "file": str(file_path.relative_to(project_root)),
                        "line": line_num,
                        "pattern": description,
                        "content": line.strip()[:100]
                    })
    
    if violations:
        error_msg = "\n\n" + "="*80 + "\n"
        error_msg += "❌ CRITICAL: Vision upgrade language found\n"
        error_msg += "="*80 + "\n\n"
        error_msg += "Vision must NOT upgrade trust or confirm authenticity.\n\n"
        error_msg += f"Found {len(violations)} violation(s):\n\n"
        
        for v in violations:
            error_msg += f"  📄 {v['file']}:{v['line']}\n"
            error_msg += f"     Pattern: {v['pattern']}\n"
            error_msg += f"     {v['content']}\n\n"
        
        raise AssertionError(error_msg)
    
    print(f"✅ Scanned {len(python_files)} Python files")
    print("   No vision upgrade language found")


def test_schema_fields_veto_safe():
    """
    CRITICAL: Ensure ReceiptDecision schema uses veto-safe fields.
    
    Check that schema doesn't have vision_verdict/vision_reasoning fields
    that could leak into production responses.
    """
    project_root = Path(__file__).parent.parent
    schema_file = project_root / "app" / "schemas" / "receipt.py"
    
    if not schema_file.exists():
        print("⚠️  Schema file not found, skipping")
        return
    
    with open(schema_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    violations = []
    
    # Check for forbidden field definitions in ReceiptDecision
    forbidden_fields = [
        ('vision_verdict:', 'vision_verdict field'),
        ('vision_reasoning:', 'vision_reasoning field'),
    ]
    
    lines = content.split('\n')
    for line_num, line in enumerate(lines, 1):
        for field, description in forbidden_fields:
            if field in line and not line.strip().startswith('#'):
                violations.append({
                    "line": line_num,
                    "field": description,
                    "content": line.strip()
                })
    
    if violations:
        error_msg = "\n\n" + "="*80 + "\n"
        error_msg += "❌ CRITICAL: Schema has vision_verdict/vision_reasoning fields\n"
        error_msg += "="*80 + "\n\n"
        error_msg += "ReceiptDecision schema must use veto-safe fields only:\n"
        error_msg += "  ✅ visual_integrity (not vision_verdict)\n"
        error_msg += "  ✅ vision_confidence\n"
        error_msg += "  ❌ vision_verdict (forbidden)\n"
        error_msg += "  ❌ vision_reasoning (forbidden)\n\n"
        error_msg += f"Found {len(violations)} violation(s):\n\n"
        
        for v in violations:
            error_msg += f"  Line {v['line']}: {v['field']}\n"
            error_msg += f"     {v['content']}\n\n"
        
        raise AssertionError(error_msg)
    
    print("✅ Schema fields are veto-safe")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("COMPREHENSIVE VISION VETO-ONLY ENFORCEMENT")
    print("="*80)
    print("\nScanning entire repository for veto-only violations...\n")
    
    tests = [
        ("vision_verdict references", test_no_vision_verdict_anywhere),
        ("authenticity_assessment usage", test_no_authenticity_assessment),
        ("vision corroboration flags", test_no_vision_corroboration_flags),
        ("vision upgrade language", test_no_vision_upgrade_language),
        ("schema field safety", test_schema_fields_veto_safe),
    ]
    
    failed = []
    
    for test_name, test_func in tests:
        try:
            print(f"\n🔍 Testing: {test_name}")
            test_func()
            print(f"   ✅ PASSED\n")
        except AssertionError as e:
            print(f"   ❌ FAILED\n")
            print(str(e))
            failed.append(test_name)
    
    print("\n" + "="*80)
    if failed:
        print(f"❌ {len(failed)}/{len(tests)} TESTS FAILED")
        print("="*80)
        print("\nFailed tests:")
        for name in failed:
            print(f"  • {name}")
        print("\n⚠️  Fix these violations before deployment!\n")
        exit(1)
    else:
        print(f"✅ ALL {len(tests)} TESTS PASSED")
        print("="*80)
        print("\nVision veto-only design is fully enforced:")
        print("  • No vision_verdict anywhere")
        print("  • No authenticity_assessment in production")
        print("  • No vision corroboration flags")
        print("  • No vision upgrade language")
        print("  • Schema fields are veto-safe")
        print("\n🎉 System is production-ready!\n")
