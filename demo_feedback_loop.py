#!/usr/bin/env python3
"""
Demo script showing the complete human feedback loop workflow.

This demonstrates:
1. Analyzing receipts
2. Collecting human feedback
3. Retraining the model
4. Using the improved model
"""

import time
from pathlib import Path
from app.pipelines.rules import analyze_receipt
from app.utils.feedback_logger import log_feedback
from app.ml.training import FeedbackLearner


def demo_workflow():
    print("=" * 80)
    print("VeriReceipt - Human Feedback Loop Demo")
    print("=" * 80)
    print()
    
    # Step 1: Analyze some receipts
    print("STEP 1: Analyzing receipts...")
    print("-" * 80)
    
    receipts = [
        "data/raw/Gas_bill.jpeg",
        "data/raw/Medplus_sample.jpg",
        "data/raw/Medplus_sample1.jpeg",
    ]
    
    analyses = []
    for receipt_path in receipts:
        if not Path(receipt_path).exists():
            print(f"⚠️  Skipping {receipt_path} (not found)")
            continue
        
        print(f"\nAnalyzing: {receipt_path}")
        decision = analyze_receipt(receipt_path)
        
        print(f"  Engine Label: {decision.label}")
        print(f"  Engine Score: {decision.score:.2f}")
        
        analyses.append({
            'path': receipt_path,
            'decision': decision
        })
    
    print()
    print(f"✅ Analyzed {len(analyses)} receipts")
    print()
    
    # Step 2: Simulate human feedback
    print("STEP 2: Collecting human feedback...")
    print("-" * 80)
    print()
    print("In a real scenario, humans would review these analyses.")
    print("For this demo, we'll simulate some corrections:")
    print()
    
    # Simulate feedback (in reality, this comes from reviewers)
    simulated_feedback = [
        {
            'analysis_ref': 'Gas_bill.jpeg',
            'given_label': 'real',
            'reviewer_id': 'demo@verireceipt.com',
            'comment': 'Verified with gas station',
            'reason_code': 'VERIFIED'
        },
        {
            'analysis_ref': 'Medplus_sample.jpg',
            'given_label': 'real',
            'reviewer_id': 'demo@verireceipt.com',
            'comment': 'Legitimate pharmacy receipt',
            'reason_code': 'VERIFIED'
        },
        {
            'analysis_ref': 'Medplus_sample1.jpeg',
            'given_label': 'suspicious',
            'reviewer_id': 'demo@verireceipt.com',
            'comment': 'Missing date, needs verification',
            'reason_code': 'NEEDS_REVIEW'
        },
    ]
    
    for feedback in simulated_feedback:
        # Find original analysis
        original = next((a for a in analyses if feedback['analysis_ref'] in a['path']), None)
        
        if original:
            engine_label = original['decision'].label
            engine_score = original['decision'].score
        else:
            engine_label = None
            engine_score = None
        
        timestamp = log_feedback(
            analysis_ref=feedback['analysis_ref'],
            given_label=feedback['given_label'],
            engine_label=engine_label,
            engine_score=engine_score,
            reviewer_id=feedback['reviewer_id'],
            comment=feedback['comment'],
            reason_code=feedback['reason_code']
        )
        
        print(f"✅ Feedback logged: {feedback['analysis_ref']}")
        print(f"   Engine said: {engine_label} ({engine_score:.2f})")
        print(f"   Human said: {feedback['given_label']}")
        print(f"   Reason: {feedback['comment']}")
        print()
    
    print(f"✅ Collected {len(simulated_feedback)} feedback entries")
    print()
    
    # Step 3: Check if we can retrain
    print("STEP 3: Checking training data...")
    print("-" * 80)
    print()
    
    learner = FeedbackLearner()
    X, y = learner.prepare_training_data()
    
    if len(X) < 10:
        print(f"⚠️  Only {len(X)} training samples available.")
        print("   Need at least 10 samples to train a model.")
        print()
        print("💡 To collect more feedback:")
        print("   1. Analyze more receipts (including fake ones)")
        print("   2. Submit corrections using: python submit_feedback.py")
        print("   3. Run this demo again")
        print()
        print("For now, the rule-based engine will continue to work.")
    else:
        print(f"✅ Found {len(X)} training samples")
        print()
        
        # Step 4: Train model
        print("STEP 4: Training ML model...")
        print("-" * 80)
        print()
        
        metrics = learner.train_model(X, y, model_type="random_forest")
        
        if metrics:
            learner.save_model(metadata=metrics)
            
            print()
            print("STEP 5: Using the trained model...")
            print("-" * 80)
            print()
            
            # Demonstrate prediction
            if len(analyses) > 0:
                test_receipt = analyses[0]
                print(f"Testing on: {test_receipt['path']}")
                print(f"  Rule-based: {test_receipt['decision'].label} ({test_receipt['decision'].score:.2f})")
                
                # Extract features (simplified for demo)
                features = learner.extract_feature_vector(
                    pd.Series({
                        'score': test_receipt['decision'].score,
                        'file_size_bytes': test_receipt['decision'].features.file_features.get('file_size_bytes', 0),
                        'num_pages': test_receipt['decision'].features.file_features.get('num_pages', 1),
                        'has_any_amount': test_receipt['decision'].features.text_features.get('has_any_amount', False),
                        'has_date': test_receipt['decision'].features.text_features.get('has_date', False),
                        'has_merchant': bool(test_receipt['decision'].features.text_features.get('merchant_candidate')),
                        'total_mismatch': test_receipt['decision'].features.text_features.get('total_mismatch', False),
                        'num_lines': test_receipt['decision'].features.layout_features.get('num_lines', 0),
                        'suspicious_producer': test_receipt['decision'].features.file_features.get('suspicious_producer', False),
                        'has_creation_date': test_receipt['decision'].features.file_features.get('has_creation_date', True),
                        'exif_present': test_receipt['decision'].features.file_features.get('exif_present', False),
                        'uppercase_ratio': test_receipt['decision'].features.forensic_features.get('uppercase_ratio', 0.0),
                        'unique_char_count': test_receipt['decision'].features.forensic_features.get('unique_char_count', 0),
                        'numeric_line_ratio': test_receipt['decision'].features.layout_features.get('numeric_line_ratio', 0.0),
                    })
                )
                
                ml_label, ml_confidence = learner.predict(features)
                print(f"  ML-enhanced: {ml_label} (confidence: {ml_confidence:.2f})")
    
    print()
    print("=" * 80)
    print("✅ Demo Complete!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Collect real receipts (both real and fake)")
    print("2. Analyze them: python test_all_samples.py")
    print("3. Submit feedback: python submit_feedback.py")
    print("4. Retrain model: python -m app.ml.training")
    print("5. Deploy improved system!")
    print()


if __name__ == "__main__":
    import pandas as pd  # Import here for the demo
    demo_workflow()
