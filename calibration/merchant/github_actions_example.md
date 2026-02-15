# GitHub Actions for Merchant Confidence Calibration

This document provides ready-to-use GitHub Actions workflow blocks for automated calibration retraining.

## Basic Weekly Retraining Workflow

```yaml
name: Merchant Calibration Retraining

on:
  schedule:
    # Run weekly on Sundays at 2 AM UTC
    - cron: '0 2 * * 0'
  workflow_dispatch:
    inputs:
      method:
        description: 'Calibration method'
        required: false
        default: 'isotonic'
        type: choice
        options:
          - isotonic
          - logistic

jobs:
  retrain-calibration:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      actions: read
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Cache pip dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
        restore-keys: |
          ${{ runner.os }}-pip-
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install pandas numpy scikit-learn
        # Add any additional dependencies here
    
    - name: Find latest labeled dataset
      id: dataset
      run: |
        # Find the most recent dataset from last 14 days
        DATASET=$(find calibration/merchant/datasets -name "merchant_dataset_*.csv" -mtime -14 -type f | sort -r | head -1 || echo "")
        if [ -z "$DATASET" ]; then
          echo "No dataset found in last 14 days"
          exit 1
        fi
        echo "dataset_path=$DATASET" >> $GITHUB_OUTPUT
        echo "Found dataset: $DATASET"
    
    - name: Run calibration retraining
      run: |
        python calibration/merchant/retrain.py \
          --data "${{ steps.dataset.outputs.dataset_path }}" \
          --output calibration/merchant/artifacts \
          --method "${{ github.event.inputs.method || 'isotonic' }}" \
          --include-optional
    
    - name: Check for regression
      id: regression
      run: |
        # Get the latest version
        VERSION=$(python -c "
import sys
sys.path.insert(0, '.')
from calibration.merchant.versioning import get_latest_version
from pathlib import Path
latest = get_latest_version(Path('calibration/merchant/artifacts'))
print(latest if latest else 'unknown')
")
        
        REPORT_FILE="calibration/merchant/artifacts/calibration_report_${VERSION}.md"
        
        if [ -f "$REPORT_FILE" ]; then
          if grep -q "❌.*Regression Detected" "$REPORT_FILE"; then
            echo "regression=true" >> $GITHUB_OUTPUT
            echo "status=regression" >> $GITHUB_OUTPUT
          elif grep -q "✅.*Safe to Deploy" "$REPORT_FILE"; then
            echo "regression=false" >> $GITHUB_OUTPUT
            echo "status=safe" >> $GITHUB_OUTPUT
          else
            echo "regression=false" >> $GITHUB_OUTPUT
            echo "status=neutral" >> $GITHUB_OUTPUT
          fi
          echo "version=$VERSION" >> $GITHUB_OUTPUT
        else
          echo "regression=unknown" >> $GITHUB_OUTPUT
          echo "status=unknown" >> $GITHUB_OUTPUT
        fi
    
    - name: Upload artifacts
      uses: actions/upload-artifact@v3
      if: always()
      with:
        name: calibration-artifacts-${{ github.run_number }}
        path: |
          calibration/merchant/artifacts/calibration_${{ steps.regression.outputs.version }}.json
          calibration/merchant/artifacts/metrics_${{ steps.regression.outputs.version }}.json
          calibration/merchant/artifacts/calibration_report_${{ steps.regression.outputs.version }}.md
          calibration/merchant/artifacts/calibration_summary.csv
          calibration/merchant/artifacts/bucket_breakdown_${{ steps.regression.outputs.version }}.csv
        retention-days: 30
    
    - name: Create summary
      run: |
        echo "## 🔄 Calibration Retraining Results" >> $GITHUB_STEP_SUMMARY
        echo "" >> $GITHUB_STEP_SUMMARY
        echo "**Version:** ${{ steps.regression.outputs.version }}" >> $GITHUB_STEP_SUMMARY
        echo "**Status:** ${{ steps.regression.outputs.status }}" >> $GITHUB_STEP_SUMMARY
        echo "**Method:** ${{ github.event.inputs.method || 'isotonic' }}" >> $GITHUB_STEP_SUMMARY
        echo "" >> $GITHUB_STEP_SUMMARY
        
        if [ "${{ steps.regression.outputs.regression }}" == "true" ]; then
          echo "⚠️ **Regression Detected!** Manual review required before deployment." >> $GITHUB_STEP_SUMMARY
        elif [ "${{ steps.regression.outputs.status }}" == "safe" ]; then
          echo "✅ **Safe to Deploy** - No regression detected." >> $GITHUB_STEP_SUMMARY
        else
          echo "🟡 **Neutral Change** - Manual review recommended." >> $GITHUB_STEP_SUMMARY
        fi
    
    - name: Notify on regression (optional)
      if: steps.regression.outputs.regression == 'true'
      run: |
        # Add your notification logic here
        # Example: Slack webhook, email, etc.
        echo "Regression detected - notify team"
        # curl -X POST "your-webhook-url" -d '{"text":"Calibration regression detected in ${{ steps.regression.outputs.version }}"}'
```

## Advanced Workflow with Dataset Generation

```yaml
name: Merchant Calibration Full Pipeline

on:
  schedule:
    # Run bi-weekly on Tuesdays at 3 AM UTC
    - cron: '0 3 * * 2'
  workflow_dispatch:

jobs:
  generate-dataset:
    runs-on: ubuntu-latest
    outputs:
      dataset_path: ${{ steps.dataset.outputs.dataset_path }}
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install pandas numpy
    
    - name: Generate labeled dataset
      run: |
        # Run your labeling workflow to generate the latest dataset
        python scripts/export_merchant_labeling_dataset.py \
          --input_dir data/receipts \
          --output_dir calibration/merchant/datasets \
          --limit 1000 \
          --redact
        
        DATASET=$(find calibration/merchant/datasets -name "merchant_dataset_*.csv" -type f | sort -r | head -1)
        echo "dataset_path=$DATASET" >> $GITHUB_OUTPUT
    
    - name: Upload dataset
      uses: actions/upload-artifact@v3
      with:
        name: labeled-dataset
        path: ${{ steps.dataset.outputs.dataset_path }}
        retention-days: 7

  retrain-calibration:
    needs: generate-dataset
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Download dataset
      uses: actions/download-artifact@v3
      with:
        name: labeled-dataset
        path: calibration/merchant/datasets/
    
    - name: Install dependencies
      run: |
        pip install pandas numpy scikit-learn
    
    - name: Run calibration retraining
      run: |
        python calibration/merchant/retrain.py \
          --data "${{ needs.generate-dataset.outputs.dataset_path }}" \
          --output calibration/merchant/artifacts \
          --method isotonic \
          --include-optional
    
    - name: Validate artifacts
      run: |
        # Validate that all required files were created
        VERSION=$(python -c "
import sys
sys.path.insert(0, '.')
from calibration.merchant.versioning import get_latest_version
from pathlib import Path
latest = get_latest_version(Path('calibration/merchant/artifacts'))
print(latest if latest else 'unknown')
")
        
        REQUIRED_FILES=(
          "calibration_${VERSION}.json"
          "metrics_${VERSION}.json"
          "calibration_report_${VERSION}.md"
          "bucket_breakdown_${VERSION}.csv"
        )
        
        for file in "${REQUIRED_FILES[@]}"; do
          if [ ! -f "calibration/merchant/artifacts/$file" ]; then
            echo "❌ Missing required file: $file"
            exit 1
          fi
        done
        
        echo "✅ All required artifacts generated"
    
    - name: Upload artifacts
      uses: actions/upload-artifact@v3
      with:
        name: calibration-results-${{ github.run_number }}
        path: calibration/merchant/artifacts/
        retention-days: 30
```

## Manual Trigger Workflow

```yaml
name: Manual Calibration Retraining

on:
  workflow_dispatch:
    inputs:
      dataset_path:
        description: 'Path to labeled dataset CSV'
        required: true
        type: string
      method:
        description: 'Calibration method'
        required: false
        default: 'isotonic'
        type: choice
        options:
          - isotonic
          - logistic
      version_tag:
        description: 'Optional version tag (auto-generated if empty)'
        required: false
        type: string

jobs:
  manual-retrain:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install pandas numpy scikit-learn
    
    - name: Validate dataset exists
      run: |
        if [ ! -f "${{ github.event.inputs.dataset_path }}" ]; then
          echo "❌ Dataset not found: ${{ github.event.inputs.dataset_path }}"
          exit 1
        fi
        
        echo "✅ Dataset found: ${{ github.event.inputs.dataset_path }}"
    
    - name: Run manual retraining
      run: |
        ARGS=(
          "--data" "${{ github.event.inputs.dataset_path }}"
          "--output" "calibration/merchant/artifacts"
          "--method" "${{ github.event.inputs.method }}"
        )
        
        if [ -n "${{ github.event.inputs.version_tag }}" ]; then
          ARGS+=("--version" "${{ github.event.inputs.version_tag }}")
        fi
        
        python calibration/merchant/retrain.py "${ARGS[@]}"
    
    - name: Upload results
      uses: actions/upload-artifact@v3
      with:
        name: manual-calibration-${{ github.run_number }}
        path: calibration/merchant/artifacts/
        retention-days: 30
```

## Environment Variables

Set these repository secrets or environment variables:

```bash
# Optional: For notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your-email@gmail.com
EMAIL_PASSWORD=your-app-password

# Optional: For dataset storage
AWS_S3_BUCKET=your-calibration-datasets
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

## Usage Instructions

1. **Copy the desired workflow** to `.github/workflows/calibration.yml`
2. **Configure environment variables** in your repository settings
3. **Customize the schedule** in the `on.schedule` section
4. **Test manually** using the "workflow_dispatch" trigger
5. **Monitor results** in the Actions tab and artifact downloads

## Security Considerations

- **Dataset Privacy**: Ensure sensitive data is redacted before upload
- **Artifact Storage**: Use appropriate retention periods
- **Access Control**: Limit who can trigger manual workflows
- **Secrets Management**: Store webhook URLs and credentials as repository secrets
