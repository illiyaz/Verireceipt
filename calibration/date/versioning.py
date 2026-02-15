"""
Calibration artifact versioning utilities for date entity.

Provides deterministic version resolution and management for date calibration artifacts.
"""

import re
from pathlib import Path
from typing import Optional, Tuple
import json
from datetime import datetime


def parse_version(version: str) -> Tuple[int, str]:
    """Parse version string like 'date_v1_20260125' into (number, date)."""
    match = re.match(r'date_v(\d+)(?:_(\d{8}))?', version)
    if not match:
        raise ValueError(f"Invalid version format: {version}")
    
    version_num = int(match.group(1))
    date_str = match.group(2) or datetime.now().strftime("%Y%m%d")
    
    return version_num, date_str


def generate_next_version(artifact_dir: Path, entity: str = "date") -> str:
    """Generate next version number based on existing artifacts."""
    if not artifact_dir.exists():
        artifact_dir.mkdir(parents=True, exist_ok=True)
    
    # Find existing calibration artifacts
    existing_versions = []
    for file_path in artifact_dir.glob("calibration_*.json"):
        if file_path.is_file():
            try:
                with open(file_path, 'r') as f:
                    artifact = json.load(f)
                version = artifact.get('version', '')
                if version.startswith(f'{entity}_v'):
                    existing_versions.append(version)
            except (json.JSONDecodeError, KeyError):
                continue
    
    # Find highest version number
    max_version = 0
    for version in existing_versions:
        try:
            version_num, _ = parse_version(version)
            max_version = max(max_version, version_num)
        except ValueError:
            continue
    
    # Generate next version
    next_version_num = max_version + 1
    date_str = datetime.now().strftime("%Y%m%d")
    next_version = f"{entity}_v{next_version_num}_{date_str}"
    
    return next_version


def get_latest_version(artifact_dir: Path, entity: str = "date") -> Optional[str]:
    """Get the latest version for an entity."""
    if not artifact_dir.exists():
        return None
    
    latest_version = None
    latest_version_num = -1
    
    for file_path in artifact_dir.glob("calibration_*.json"):
        if file_path.is_file():
            try:
                with open(file_path, 'r') as f:
                    artifact = json.load(f)
                version = artifact.get('version', '')
                if version.startswith(f'{entity}_v'):
                    version_num, _ = parse_version(version)
                    if version_num > latest_version_num:
                        latest_version_num = version_num
                        latest_version = version
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    
    return latest_version


def load_previous_artifact(artifact_dir: Path, entity: str = "date") -> Optional[dict]:
    """Load the previous version artifact for comparison."""
    latest_version = get_latest_version(artifact_dir, entity)
    if not latest_version:
        return None
    
    artifact_file = artifact_dir / f"calibration_{latest_version}.json"
    if not artifact_file.exists():
        return None
    
    try:
        with open(artifact_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def version_exists(artifact_dir: Path, version: str) -> bool:
    """Check if a version already exists."""
    artifact_file = artifact_dir / f"calibration_{version}.json"
    return artifact_file.exists()


def validate_version_format(version: str) -> bool:
    """Validate version format."""
    try:
        parse_version(version)
        return True
    except ValueError:
        return False


def get_artifact_path(artifact_dir: Path, version: str, entity: str = "date") -> Path:
    """Get the full path for an artifact file."""
    return artifact_dir / f"calibration_{version}.json"


def get_metrics_path(artifact_dir: Path, version: str, entity: str = "date") -> Path:
    """Get the full path for a metrics file."""
    return artifact_dir / f"metrics_{version}.json"


def get_report_path(artifact_dir: Path, version: str, entity: str = "date") -> Path:
    """Get the full path for a markdown report file."""
    return artifact_dir / f"calibration_report_{version}.md"


def get_summary_csv_path(artifact_dir: Path, entity: str = "date") -> Path:
    """Get the full path for the summary CSV file."""
    return artifact_dir / "calibration_summary.csv"


def get_bucket_csv_path(artifact_dir: Path, version: str, entity: str = "date") -> Path:
    """Get the full path for a bucket breakdown CSV file."""
    return artifact_dir / f"bucket_breakdown_{version}.csv"
