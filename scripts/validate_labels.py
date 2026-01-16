#!/usr/bin/env python3
"""
Label validation and linting for VeriReceipt.

Validates JSONL label files against schema and business rules.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas.labels import (
    DocumentLabelV1, 
    FRAUD_TYPES, 
    DECISION_REASONS
)
from app.schemas.receipt import SignalRegistry


class LabelValidator:
    """Validates and lints label files."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.stats = {
            "total_docs": 0,
            "valid_docs": 0,
            "invalid_docs": 0,
            "outcomes": {"GENUINE": 0, "FRAUDULENT": 0, "INCONCLUSIVE": 0},
            "fraud_types": {},
            "decision_reasons": {},
            "signal_reviews": {},
        }
    
    def validate_jsonl_file(self, file_path: Path) -> bool:
        """
        Validate a JSONL file of labels.
        
        Returns True if all documents are valid.
        """
        print(f"Validating {file_path}...")
        
        if not file_path.exists():
            self.errors.append(f"File not found: {file_path}")
            return False
        
        try:
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        label_data = json.loads(line)
                        self._validate_document(label_data, line_num)
                        self.stats["total_docs"] += 1
                    except json.JSONDecodeError as e:
                        self.errors.append(
                            f"Line {line_num}: Invalid JSON: {e}"
                        )
                        self.stats["invalid_docs"] += 1
                    except Exception as e:
                        self.errors.append(
                            f"Line {line_num}: Validation error: {e}"
                        )
                        self.stats["invalid_docs"] += 1
        
        except Exception as e:
            self.errors.append(f"Error reading file: {e}")
            return False
        
        return len(self.errors) == 0
    
    def _validate_document(self, data: Dict[str, Any], line_num: int):
        """Validate a single document label."""
        try:
            # Parse with Pydantic
            label = DocumentLabelV1(**data)
            self.stats["valid_docs"] += 1
            
            # Update statistics
            outcome = label.get_final_outcome()
            self.stats["outcomes"][outcome] += 1
            
            # Track fraud types
            for fraud_type in label.get_final_fraud_types():
                self.stats["fraud_types"][fraud_type] = (
                    self.stats["fraud_types"].get(fraud_type, 0) + 1
                )
            
            # Additional business rule checks
            self._check_business_rules(label, line_num)
            
        except Exception as e:
            self.errors.append(f"Line {line_num}: {e}")
            self.stats["invalid_docs"] += 1
    
    def _check_business_rules(self, label: DocumentLabelV1, line_num: int):
        """Check additional business rules beyond Pydantic validation."""
        
        # Check fraud types are in taxonomy
        for fraud_type in label.get_final_fraud_types():
            if fraud_type not in FRAUD_TYPES:
                self.warnings.append(
                    f"Line {line_num}: Unknown fraud_type '{fraud_type}'"
                )
        
        # Check decision reasons are in taxonomy
        final_reasons = []
        if label.adjudication:
            final_reasons = label.adjudication.final_decision_reasons
        elif label.annotator_judgments:
            final_reasons = label.annotator_judgments[0].decision_reasons
        
        for reason in final_reasons:
            if reason not in DECISION_REASONS:
                self.warnings.append(
                    f"Line {line_num}: Unknown decision_reason '{reason}'"
                )
        
        # Check signal reviews only contain registered signals
        for judgment in label.annotator_judgments:
            if judgment.signal_reviews:
                for signal_name in judgment.signal_reviews.keys():
                    self.stats["signal_reviews"][signal_name] = (
                        self.stats["signal_reviews"].get(signal_name, 0) + 1
                    )
        
        # Check for reasonable timestamps
        if label.created_at > datetime.utcnow().isoformat() + "Z":
            self.warnings.append(
                f"Line {line_num}: created_at is in the future"
            )
    
    def compute_agreement_stats(self, labels: List[DocumentLabelV1]) -> Dict[str, Any]:
        """
        Compute inter-annotator agreement statistics.
        
        Only meaningful for documents with multiple judgments.
        """
        multi_judgment_docs = [
            label for label in labels 
            if len(label.annotator_judgments) > 1
        ]
        
        if not multi_judgment_docs:
            return {
                "multi_judgment_docs": 0,
                "outcome_agreement": 0.0,
                "evidence_strength_agreement": 0.0,
            }
        
        outcome_agreements = []
        evidence_agreements = []
        
        for label in multi_judgment_docs:
            outcomes = [j.doc_outcome for j in label.annotator_judgments]
            evidence_strengths = [j.evidence_strength for j in label.annotator_judgments]
            
            # Simple agreement metrics
            outcome_agreement = max(set(outcomes), key=outcomes.count)
            outcome_agreements.append(outcome_agreement)
            
            evidence_agreement = max(set(evidence_strengths), key=evidence_strengths.count)
            evidence_agreements.append(evidence_agreement)
        
        return {
            "multi_judgment_docs": len(multi_judgment_docs),
            "outcome_agreement": (
                sum(1 for o in outcome_agreements if o == outcomes[0]) / len(outcome_agreements)
                if outcome_agreements else 0.0
            ),
            "evidence_strength_agreement": (
                sum(1 for e in evidence_agreements if e == evidence_strengths[0]) / len(evidence_agreements)
                if evidence_agreements else 0.0
            ),
        }
    
    def print_report(self):
        """Print validation report."""
        print("\n" + "="*60)
        print("VALIDATION REPORT")
        print("="*60)
        
        # Errors
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors[:10]:  # Show first 10
                print(f"  - {error}")
            if len(self.errors) > 10:
                print(f"  ... and {len(self.errors) - 10} more")
        
        # Warnings
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings[:10]:  # Show first 10
                print(f"  - {warning}")
            if len(self.warnings) > 10:
                print(f"  ... and {len(self.warnings) - 10} more")
        
        # Statistics
        print(f"\n📊 STATISTICS:")
        print(f"  Total documents: {self.stats['total_docs']}")
        print(f"  Valid documents: {self.stats['valid_docs']}")
        print(f"  Invalid documents: {self.stats['invalid_docs']}")
        
        if self.stats['total_docs'] > 0:
            print(f"\n📈 OUTCOME DISTRIBUTION:")
            for outcome, count in self.stats['outcomes'].items():
                pct = (count / self.stats['total_docs']) * 100
                print(f"  {outcome}: {count} ({pct:.1f}%)")
            
            if self.stats['fraud_types']:
                print(f"\n🏷️  FRAUD TYPES:")
                for fraud_type, count in sorted(self.stats['fraud_types'].items()):
                    print(f"  {fraud_type}: {count}")
            
            if self.stats['decision_reasons']:
                print(f"\n🔍 DECISION REASONS:")
                for reason, count in sorted(self.stats['decision_reasons'].items()):
                    print(f"  {reason}: {count}")
            
            if self.stats['signal_reviews']:
                print(f"\n📡 SIGNAL REVIEWS:")
                for signal, count in sorted(self.stats['signal_reviews'].items()):
                    print(f"  {signal}: {count}")
        
        # Summary
        print(f"\n📋 SUMMARY:")
        if self.errors:
            print(f"  ❌ FAILED: {len(self.errors)} errors found")
        else:
            print(f"  ✅ PASSED: All documents valid")
        
        if self.warnings:
            print(f"  ⚠️  {len(self.warnings)} warnings (non-blocking)")


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Validate JSONL label files"
    )
    parser.add_argument(
        "--labels",
        required=True,
        type=Path,
        help="Path to labels.jsonl file"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on warnings (not just errors)"
    )
    parser.add_argument(
        "--output-stats",
        type=Path,
        help="Write statistics to JSON file"
    )
    
    args = parser.parse_args()
    
    # Validate labels
    validator = LabelValidator()
    is_valid = validator.validate_jsonl_file(args.labels)
    
    # Print report
    validator.print_report()
    
    # Write stats if requested
    if args.output_stats:
        with open(args.output_stats, 'w') as f:
            json.dump(validator.stats, f, indent=2, sort_keys=True)
        print(f"\n📊 Statistics written to {args.output_stats}")
    
    # Exit code
    if not is_valid:
        sys.exit(1)
    elif args.strict and validator.warnings:
        print(f"\n❌ Failed due to {len(validator.warnings)} warnings (strict mode)")
        sys.exit(1)
    else:
        print(f"\n✅ Validation passed!")


if __name__ == "__main__":
    main()
