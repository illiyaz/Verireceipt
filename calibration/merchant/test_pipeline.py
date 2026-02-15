"""
Test script for merchant confidence calibration pipeline.

Creates synthetic data to validate the calibration workflow.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import sys
import os

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from config import (
    CALIBRATION_VERSION, FEATURES_USED, BUCKET_THRESHOLDS,
    OUTPUT_DIR, CALIBRATION_FILE
)

def create_synthetic_dataset(n_samples: int = 1000) -> pd.DataFrame:
    """Create synthetic labeled dataset for testing."""
    np.random.seed(42)
    
    # Generate synthetic features
    data = {
        'doc_id': [f'doc_{i:06d}' for i in range(n_samples)],
        'entity': ['merchant'] * n_samples,
        'extracted_value': [f'Merchant_{i}' for i in range(n_samples)],
        'best_score': np.random.uniform(5, 20, n_samples),
        'winner_margin': np.random.uniform(0, 10, n_samples),
        'candidate_count_filtered': np.random.randint(1, 8, n_samples),
        'mode': np.random.choice(['strict', 'relaxed'], n_samples, p=[0.7, 0.3]),
        'confidence_raw': np.random.uniform(0, 1, n_samples),
        'confidence_bucket': np.random.choice(['HIGH', 'MEDIUM', 'LOW'], n_samples),
    }
    
    # Generate boolean features
    boolean_features = [
        'seller_zone', 'buyer_zone_penalty', 'label_next_line',
        'company_name', 'uppercase_header', 'title_like', 'ref_like', 'digit_heavy'
    ]
    
    for feature in boolean_features:
        data[feature] = np.random.choice([True, False], n_samples, p=[0.3, 0.7])
    
    # Generate synthetic correctness based on features
    # Higher scores and certain features increase correctness probability
    correctness_prob = (
        0.3 +  # Base rate
        0.02 * data['best_score'] +  # Score contribution
        0.05 * data['winner_margin'] +  # Margin contribution
        0.1 * data['seller_zone'].astype(int) +  # Seller zone boost
        0.08 * data['company_name'].astype(int) +  # Company name boost
        (-0.1) * data['buyer_zone_penalty'].astype(int) +  # Buyer zone penalty
        (-0.05) * data['ref_like'].astype(int)  # Ref-like penalty
    )
    
    # Clip to [0, 1] and generate binary labels
    correctness_prob = np.clip(correctness_prob, 0.05, 0.95)
    data['is_correct'] = (np.random.random(n_samples) < correctness_prob).astype(int)
    
    # Add optional features
    data.update({
        'doc_subtype': np.random.choice(['receipt', 'invoice', 'other'], n_samples),
        'language': np.random.choice(['en', 'zh', 'ar', 'es'], n_samples),
        'ocr_quality_bucket': np.random.choice(['high', 'medium', 'low'], n_samples)
    })
    
    df = pd.DataFrame(data)
    
    print(f"Created synthetic dataset: {len(df)} samples")
    print(f"Correctness rate: {df['is_correct'].mean():.3f}")
    print(f"Feature distributions:")
    for feature in FEATURES_USED[:5]:  # Show first 5 features
        if feature in df.columns:
            if df[feature].dtype == 'object':
                print(f"  {feature}: {df[feature].value_counts().to_dict()}")
            else:
                print(f"  {feature}: mean={df[feature].mean():.2f}, std={df[feature].std():.2f}")
    
    return df

def test_calibration_pipeline():
    """Test the complete calibration pipeline with synthetic data."""
    print("🧪 Testing Merchant Confidence Calibration Pipeline")
    print("=" * 60)
    
    # Create synthetic dataset
    df = create_synthetic_dataset(1000)
    
    # Save test data
    test_data_path = Path(OUTPUT_DIR) / "test_synthetic_data.csv"
    test_data_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(test_data_path, index=False)
    print(f"✅ Test data saved to: {test_data_path}")
    
    # Test configuration
    try:
        from config import validate_config
        validate_config()
        print("✅ Configuration validation passed")
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        return False
    
    # Test calibration training
    try:
        import calibrate
        print("\n🔄 Testing calibration training...")
        
        calibration_path, metrics = calibrate.main(
            data_path=str(test_data_path),
            output_dir=OUTPUT_DIR,
            include_optional=False,
            test_size=0.2
        )
        
        print(f"✅ Calibration training completed")
        print(f"   Accuracy: {metrics['accuracy']:.4f}")
        print(f"   Precision: {metrics['precision']:.4f}")
        print(f"   Calibration artifact: {calibration_path}")
        
    except Exception as e:
        print(f"❌ Calibration training failed: {e}")
        return False
    
    # Test evaluation
    try:
        import evaluate
        print("\n📊 Testing evaluation...")
        
        report = evaluate.main(calibration_path, OUTPUT_DIR)
        
        print(f"✅ Evaluation completed")
        print(f"   ECE: {report['overall_metrics']['ece']:.4f}")
        print(f"   Monotonicity: {'✅' if report['monotonicity_check'] else '❌'}")
        print(f"   High-confidence errors: {report['high_confidence_errors']['count']}")
        
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        return False
    
    # Test plotting
    try:
        import plots
        print("\n📈 Testing plot generation...")
        
        plots.main(OUTPUT_DIR)
        
        plots_dir = Path(OUTPUT_DIR) / "plots"
        expected_plots = [
            "reliability_diagram.png",
            "confidence_histogram.png", 
            "bucket_precision.png",
            "calibration_comparison.png"
        ]
        
        missing_plots = []
        for plot_file in expected_plots:
            if not (plots_dir / plot_file).exists():
                missing_plots.append(plot_file)
        
        if missing_plots:
            print(f"❌ Missing plots: {missing_plots}")
            return False
        else:
            print(f"✅ All {len(expected_plots)} plots generated successfully")
        
    except Exception as e:
        print(f"❌ Plot generation failed: {e}")
        return False
    
    # Test calibration artifact loading
    try:
        calibration_file = Path(OUTPUT_DIR) / CALIBRATION_FILE
        if not calibration_file.exists():
            print(f"❌ Calibration artifact not found: {calibration_file}")
            return False
        
        import json
        with open(calibration_file, 'r') as f:
            artifact = json.load(f)
        
        required_keys = [
            'calibration_version', 'method', 'trained_at', 
            'features_used', 'bucket_thresholds', 'metrics'
        ]
        
        missing_keys = [key for key in required_keys if key not in artifact]
        if missing_keys:
            print(f"❌ Missing artifact keys: {missing_keys}")
            return False
        
        print(f"✅ Calibration artifact validation passed")
        print(f"   Version: {artifact['calibration_version']}")
        print(f"   Method: {artifact['method']}")
        print(f"   Features: {len(artifact['features_used'])}")
        
    except Exception as e:
        print(f"❌ Artifact validation failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("🎉 All calibration pipeline tests passed!")
    print(f"📁 Output directory: {OUTPUT_DIR}")
    print(f"📊 Check {Path(OUTPUT_DIR) / 'plots'} for visualizations")
    print(f"📋 Check {Path(OUTPUT_DIR) / 'metrics_merchant_v1.json'} for detailed metrics")
    
    return True

if __name__ == "__main__":
    success = test_calibration_pipeline()
    sys.exit(0 if success else 1)
