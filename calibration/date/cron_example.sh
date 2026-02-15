#!/bin/bash
#
# Example cron script for scheduled date confidence calibration retraining
#
# This script demonstrates how to run calibration retraining on a schedule
# using the latest labeled data from the labeling workflow.
#
# CRON SCHEDULE EXAMPLES:
# Weekly retraining (Sundays at 2 AM):
#   0 2 * * 0 /path/to/verireceipt/calibration/date/cron_example.sh
#
# Bi-weekly retraining (1st and 15th at 3 AM):
#   0 3 1,15 * * /path/to/verireceipt/calibration/date/cron_example.sh
#
# Monthly retraining (1st of month at 4 AM):
#   0 4 1 * * /path/to/verireceipt/calibration/date/cron_example.sh
#

set -euo pipefail

# Configuration
PROJECT_ROOT="/path/to/verireceipt"
DATA_DIR="${PROJECT_ROOT}/calibration/date/datasets"
ARTIFACTS_DIR="${PROJECT_ROOT}/calibration/date/artifacts"
LOG_DIR="${PROJECT_ROOT}/logs/calibration"
RETENTION_DAYS=30

# Ensure directories exist
mkdir -p "${DATA_DIR}"
mkdir -p "${ARTIFACTS_DIR}"
mkdir -p "${LOG_DIR}"

# Logging
LOG_FILE="${LOG_DIR}/retrain_date_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "${LOG_FILE}")
exec 2>&1

echo "=========================================="
echo "Date Confidence Calibration Retraining"
echo "Started: $(date -u +%Y-%m-%d\ %H:%M:%S\ UTC)"
echo "=========================================="

# Change to project directory
cd "${PROJECT_ROOT}"

# Get latest labeled dataset (last 14 days)
echo "Finding latest labeled dataset..."
LATEST_DATASET=$(find "${DATA_DIR}" -name "date_dataset_*.csv" -mtime -14 -type f | sort -r | head -1)

if [ -z "${LATEST_DATASET}" ]; then
    echo "❌ ERROR: No labeled dataset found in last 14 days"
    echo "   Expected files: ${DATA_DIR}/date_dataset_YYYYMMDD.csv"
    exit 1
fi

echo "📊 Using dataset: ${LATEST_DATASET}"
echo "   Size: $(du -h "${LATEST_DATASET}" | cut -f1)"
echo "   Modified: $(stat -c %y "${LATEST_DATASET}" 2>/dev/null || stat -f %Sm "${LATEST_DATASET}")"

# Run retraining
echo ""
echo "🔄 Starting calibration retraining..."
RETRAIN_START=$(date +%s)

python calibration/date/retrain.py \
    --data "${LATEST_DATASET}" \
    --output "${ARTIFACTS_DIR}" \
    --method isotonic

RETRAIN_EXIT_CODE=$?
RETRAIN_END=$(date +%s)
RETRAIN_DURATION=$((RETRAIN_END - RETRAIN_START))

if [ ${RETRAIN_EXIT_CODE} -ne 0 ]; then
    echo "❌ ERROR: Retraining failed with exit code ${RETRAIN_EXIT_CODE}"
    echo "   Check logs: ${LOG_FILE}"
    exit ${RETRAIN_EXIT_CODE}
fi

echo "✅ Retraining completed successfully in ${RETRAIN_DURATION} seconds"

# Get the latest version for reporting
LATEST_VERSION=$(python -c "
import sys
sys.path.insert(0, '.')
from calibration.date.versioning import get_latest_version
from pathlib import Path
latest = get_latest_version(Path('${ARTIFACTS_DIR}'))
print(latest if latest else 'unknown')
")

echo ""
echo "📋 Retraining Results:"
echo "   Version: ${LATEST_VERSION}"
echo "   Artifacts: ${ARTIFACTS_DIR}"

# Check for regression
echo ""
echo "🔍 Checking for regression..."
REPORT_FILE="${ARTIFACTS_DIR}/calibration_report_${LATEST_VERSION}.md"

if [ -f "${REPORT_FILE}" ]; then
    if grep -q "❌.*Regression Detected" "${REPORT_FILE}"; then
        echo "⚠️  WARNING: Regression detected!"
        echo "   Review report: ${REPORT_FILE}"
        echo "   Manual approval required before deployment"
        
        # Send alert (example - integrate with your alerting system)
        # curl -X POST "https://your-alerting-system.com/webhook" \
        #   -d "message=Date calibration regression detected in ${LATEST_VERSION}"
        
    elif grep -q "✅.*Safe to Deploy" "${REPORT_FILE}"; then
        echo "✅ No regression detected - safe for deployment"
        echo "   Review report: ${REPORT_FILE}"
        
        # Optional: Auto-promote (uncomment if you want automatic promotion)
        # python calibration/date/promote.py --version "${LATEST_VERSION}" --auto
        
    else
        echo "⚠️  Neutral change detected"
        echo "   Review report: ${REPORT_FILE}"
        echo "   Manual review recommended"
    fi
else
    echo "❌ ERROR: Report file not found: ${REPORT_FILE}"
fi

# Cleanup old logs
echo ""
echo "🧹 Cleaning up old logs (older than ${RETENTION_DAYS} days)..."
find "${LOG_DIR}" -name "retrain_date_*.log" -mtime +${RETENTION_DAYS} -delete

# Cleanup old datasets (keep last 30 days)
echo "🧹 Cleaning up old datasets (older than 30 days)..."
find "${DATA_DIR}" -name "date_dataset_*.csv" -mtime +30 -delete

echo ""
echo "=========================================="
echo "Retraining completed successfully"
echo "Finished: $(date -u +%Y-%m-%d\ %H:%M:%S\ UTC)"
echo "Duration: ${RETRAIN_DURATION} seconds"
echo "Log file: ${LOG_FILE}"
echo "=========================================="

# Exit with success
exit 0
