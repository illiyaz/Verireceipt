#!/usr/bin/env python3
"""
Template Setup Script

Downloads SROIE dataset and generates receipt templates.
Also provides utilities for adding custom templates.

Usage:
    # Download SROIE and generate templates
    python scripts/setup_templates.py --download-sroie
    
    # Add custom template from receipt text file
    python scripts/setup_templates.py --add-custom receipt.txt --name "My Store"
    
    # List all templates
    python scripts/setup_templates.py --list
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.pipelines.templates.sroie_loader import SROIELoader, setup_sroie_templates
from app.pipelines.templates.registry import TemplateRegistry, get_registry
from app.pipelines.templates.fingerprint import compute_fingerprint


def download_sroie(force: bool = False):
    """Download SROIE dataset and generate templates."""
    print("=" * 60)
    print("SROIE Template Setup")
    print("=" * 60)
    
    loader = SROIELoader()
    
    print("\n[1/3] Downloading SROIE dataset...")
    if loader.download(force=force):
        print("✓ Download complete")
    else:
        print("✗ Download failed")
        return False
    
    print("\n[2/3] Loading and parsing receipts...")
    receipts = loader.load("train")
    print(f"✓ Loaded {len(receipts)} receipts")
    
    print("\n[3/3] Generating template fingerprints...")
    templates = loader.generate_templates()
    print(f"✓ Generated {len(templates)} templates")
    
    print("\n[4/4] Saving templates...")
    output_path = loader.save_templates(templates)
    print(f"✓ Saved to {output_path}")
    
    print("\n" + "=" * 60)
    print(f"SUCCESS: {len(templates)} templates ready for use")
    print("=" * 60)
    
    return True


def add_custom_template(
    text_file: Path,
    name: str,
    template_id: str = None
):
    """Add a custom template from a text file."""
    if not text_file.exists():
        print(f"Error: File not found: {text_file}")
        return False
    
    print(f"Adding custom template: {name}")
    
    # Read lines from file
    with open(text_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    if not lines:
        print("Error: Empty file")
        return False
    
    print(f"  Lines: {len(lines)}")
    
    # Generate fingerprint
    fp = compute_fingerprint(
        lines,
        template_id=template_id,
        template_name=name,
        source="custom"
    )
    
    print(f"  Template ID: {fp.template_id}")
    print(f"  Merchant keywords: {len(fp.merchant_keywords)}")
    print(f"  Has tax line: {fp.has_tax_line}")
    print(f"  Has total line: {fp.has_total_line}")
    
    # Save to custom templates
    registry = TemplateRegistry(auto_load=False)
    output_path = registry.save_custom_template(fp, filename=template_id)
    
    print(f"\n✓ Saved to {output_path}")
    return True


def list_templates():
    """List all loaded templates."""
    registry = get_registry()
    templates = registry.get_all()
    
    print("=" * 60)
    print(f"Template Registry: {len(templates)} templates")
    print("=" * 60)
    
    # Group by source
    by_source = {}
    for t in templates:
        source = t.source
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(t)
    
    for source, source_templates in sorted(by_source.items()):
        print(f"\n[{source.upper()}] ({len(source_templates)} templates)")
        print("-" * 40)
        for t in source_templates[:10]:  # Show first 10
            print(f"  {t.template_id}: {t.template_name}")
            print(f"    Lines: {t.line_count_range}, Keywords: {len(t.merchant_keywords)}")
        if len(source_templates) > 10:
            print(f"  ... and {len(source_templates) - 10} more")


def test_match(text_file: Path):
    """Test template matching against a receipt."""
    from app.pipelines.templates.matcher import TemplateMatcher
    
    if not text_file.exists():
        print(f"Error: File not found: {text_file}")
        return
    
    with open(text_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    print(f"Testing match for: {text_file.name}")
    print(f"Lines: {len(lines)}")
    print("-" * 40)
    
    registry = get_registry()
    matcher = TemplateMatcher(registry.get_all())
    
    matches = matcher.match(lines, top_k=5, min_confidence=0.3)
    
    if not matches:
        print("No matches found")
        return
    
    print(f"\nTop {len(matches)} matches:")
    for i, match in enumerate(matches, 1):
        print(f"\n{i}. {match.template.template_name}")
        print(f"   Confidence: {match.confidence:.2%}")
        print(f"   Template ID: {match.template.template_id}")
        print(f"   Match details:")
        for feature, score in sorted(match.match_details.items(), key=lambda x: -x[1])[:5]:
            print(f"     {feature}: {score:.2%}")


def main():
    parser = argparse.ArgumentParser(
        description="Receipt Template Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download SROIE dataset and generate templates
  python scripts/setup_templates.py --download-sroie
  
  # Add custom template from receipt text
  python scripts/setup_templates.py --add-custom receipt.txt --name "Starbucks"
  
  # List all templates  
  python scripts/setup_templates.py --list
  
  # Test template matching
  python scripts/setup_templates.py --test receipt.txt
"""
    )
    
    parser.add_argument(
        "--download-sroie",
        action="store_true",
        help="Download SROIE dataset and generate templates"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if exists"
    )
    parser.add_argument(
        "--add-custom",
        type=Path,
        metavar="FILE",
        help="Add custom template from text file"
    )
    parser.add_argument(
        "--name",
        type=str,
        help="Template name (for --add-custom)"
    )
    parser.add_argument(
        "--template-id",
        type=str,
        help="Template ID (optional, for --add-custom)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all loaded templates"
    )
    parser.add_argument(
        "--test",
        type=Path,
        metavar="FILE",
        help="Test template matching against a receipt file"
    )
    
    args = parser.parse_args()
    
    if args.download_sroie:
        download_sroie(force=args.force)
    elif args.add_custom:
        if not args.name:
            print("Error: --name is required with --add-custom")
            sys.exit(1)
        add_custom_template(args.add_custom, args.name, args.template_id)
    elif args.list:
        list_templates()
    elif args.test:
        test_match(args.test)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
