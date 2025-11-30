# app/utils/logger.py
"""
Logger utilities for VeriReceipt.

Goal:
- Every time we analyze a receipt, we log a single row into a CSV file.
- This CSV becomes our dataset for ML training in Phase 2.

We log:
- filename, label, score, timestamp
- flattened features from:
  - file_features
  - text_features
  - layout_features
  - forensic_features
"""

import csv
import os
from datetime import datetime
from typing import Dict, Any

from app.schemas.receipt import ReceiptDecision, ReceiptFeatures

# Default log location (relative to project root)
LOG_DIR = "data/logs"
LOG_FILE = os.path.join(LOG_DIR, "decisions.csv")


def _ensure_log_dir() -> None:
    """
    Make sure the log directory exists.
    """
    os.makedirs(LOG_DIR, exist_ok=True)


def _flatten_features(features: ReceiptFeatures) -> Dict[str, Any]:
    """
    Flatten the nested ReceiptFeatures into a single dict with prefixes
    to avoid key collisions.

    Example output keys:
    - file_source_type
    - file_num_pages
    - text_has_any_amount
    - layout_num_lines
    - forensic_uppercase_ratio
    """
    flat: Dict[str, Any] = {}

    # File features
    for k, v in (features.file_features or {}).items():
        flat[f"file_{k}"] = v

    # Text features
    for k, v in (features.text_features or {}).items():
        flat[f"text_{k}"] = v

    # Layout features
    for k, v in (features.layout_features or {}).items():
        flat[f"layout_{k}"] = v

    # Forensic features
    for k, v in (features.forensic_features or {}).items():
        flat[f"forensic_{k}"] = v

    return flat


def _decision_to_row(file_path: str, decision: ReceiptDecision) -> Dict[str, Any]:
    """
    Convert a ReceiptDecision (and file path) into a flat dict suitable for CSV logging.
    """
    base_name = os.path.basename(file_path)
    timestamp = datetime.utcnow().isoformat()

    row: Dict[str, Any] = {
        "filename": base_name,
        "label": decision.label,
        "score": decision.score,
        "timestamp_utc": timestamp,
    }

    if decision.features is not None:
        flat_feats = _flatten_features(decision.features)
        row.update(flat_feats)

    return row


def log_decision(file_path: str, decision: ReceiptDecision, log_file: str = LOG_FILE) -> None:
    """
    Append a single analysis result as a row to the CSV log.

    - Creates `data/logs/decisions.csv` if it doesn't exist.
    - Writes header on first write.
    - Appends subsequent rows with the same header.
    """
    _ensure_log_dir()

    row = _decision_to_row(file_path, decision)
    file_exists = os.path.isfile(log_file)

    # IMPORTANT:
    # - We use row.keys() as the fieldnames.
    # - Because we always build rows in the same way, the columns stay consistent.
    fieldnames = list(row.keys())

    with open(log_file, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        # If the file is new, write the header first.
        if not file_exists:
            writer.writeheader()

        writer.writerow(row)