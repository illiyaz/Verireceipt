"""
SROIE Dataset Loader

Downloads and processes the SROIE (Scanned Receipts OCR and Information Extraction)
dataset from ICDAR 2019 to generate template fingerprints.

Dataset structure:
- images/: Receipt images
- annotations/: Text annotations (OCR ground truth)
- entities/: Entity annotations (company, date, address, total)
"""

import os
import re
import json
import shutil
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

from .fingerprint import TemplateFingerprint, compute_fingerprint

logger = logging.getLogger(__name__)

# SROIE dataset URL (GitHub mirror)
SROIE_GITHUB_URL = "https://github.com/zzzDavid/ICDAR-2019-SROIE/archive/refs/heads/master.zip"
SROIE_DATASET_NAME = "ICDAR-2019-SROIE-master"


@dataclass
class SROIEReceipt:
    """Parsed SROIE receipt data."""
    receipt_id: str
    text_lines: List[str]
    company: Optional[str] = None
    date: Optional[str] = None
    address: Optional[str] = None
    total: Optional[float] = None
    
    def to_dict(self) -> Dict:
        return {
            "receipt_id": self.receipt_id,
            "text_lines": self.text_lines,
            "company": self.company,
            "date": self.date,
            "address": self.address,
            "total": self.total,
        }


class SROIELoader:
    """
    Loader for SROIE dataset.
    
    Handles downloading, parsing, and template generation from the dataset.
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize SROIE loader.
        
        Args:
            data_dir: Directory to store/load SROIE data
        """
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).parent.parent.parent.parent / "data" / "sroie"
        self.receipts: List[SROIEReceipt] = []
        self._loaded = False
    
    def download(self, force: bool = False) -> bool:
        """
        Download SROIE dataset from GitHub.
        
        Args:
            force: Force re-download even if exists
        
        Returns:
            True if download successful
        """
        import urllib.request
        import zipfile
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        zip_path = self.data_dir / "sroie.zip"
        extract_marker = self.data_dir / ".extracted"
        
        if extract_marker.exists() and not force:
            logger.info("SROIE dataset already downloaded")
            return True
        
        try:
            logger.info(f"Downloading SROIE dataset from {SROIE_GITHUB_URL}...")
            urllib.request.urlretrieve(SROIE_GITHUB_URL, zip_path)
            
            logger.info("Extracting dataset...")
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(self.data_dir)
            
            # Create marker file
            extract_marker.touch()
            
            # Clean up zip
            zip_path.unlink()
            
            logger.info("SROIE dataset downloaded and extracted successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download SROIE dataset: {e}")
            return False
    
    def load(self, subset: str = "train") -> List[SROIEReceipt]:
        """
        Load receipts from SROIE dataset.
        
        Args:
            subset: "train" or "test"
        
        Returns:
            List of parsed receipts
        """
        dataset_dir = self.data_dir / SROIE_DATASET_NAME / "data" / subset
        
        if not dataset_dir.exists():
            logger.warning(f"SROIE {subset} directory not found: {dataset_dir}")
            logger.info("Attempting to download dataset...")
            if not self.download():
                return []
        
        # Find annotation files
        box_dir = dataset_dir / "box"
        entities_dir = dataset_dir / "entities"
        
        if not box_dir.exists():
            # Try alternate structure
            box_dir = dataset_dir
            entities_dir = dataset_dir
        
        receipts = []
        
        # Get all text files
        txt_files = list(box_dir.glob("*.txt"))
        logger.info(f"Found {len(txt_files)} receipt files in {subset}")
        
        for txt_file in txt_files:
            try:
                receipt = self._parse_receipt(txt_file, entities_dir)
                if receipt and receipt.text_lines:
                    receipts.append(receipt)
            except Exception as e:
                logger.debug(f"Failed to parse {txt_file.name}: {e}")
        
        self.receipts = receipts
        self._loaded = True
        logger.info(f"Loaded {len(receipts)} receipts from SROIE {subset}")
        
        return receipts
    
    def _parse_receipt(
        self,
        txt_file: Path,
        entities_dir: Path
    ) -> Optional[SROIEReceipt]:
        """Parse a single receipt from SROIE format."""
        receipt_id = txt_file.stem
        
        # Read text lines (SROIE format: x1,y1,x2,y2,x3,y3,x4,y4,text)
        lines = []
        with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Extract text after coordinates
                parts = line.split(',', 8)
                if len(parts) >= 9:
                    text = parts[8].strip()
                    if text:
                        lines.append(text)
                elif len(parts) == 1:
                    # Plain text format
                    lines.append(line)
        
        if not lines:
            return None
        
        # Try to load entities
        company, date, address, total = None, None, None, None
        entities_file = entities_dir / f"{receipt_id}.txt"
        
        if entities_file.exists():
            try:
                with open(entities_file, 'r', encoding='utf-8', errors='ignore') as f:
                    entity_data = json.load(f)
                    company = entity_data.get("company")
                    date = entity_data.get("date")
                    address = entity_data.get("address")
                    total_str = entity_data.get("total", "")
                    if total_str:
                        # Parse total amount
                        total_match = re.search(r'[\d,.]+', str(total_str))
                        if total_match:
                            total = float(total_match.group().replace(',', ''))
            except (json.JSONDecodeError, ValueError):
                pass
        
        return SROIEReceipt(
            receipt_id=receipt_id,
            text_lines=lines,
            company=company,
            date=date,
            address=address,
            total=total,
        )
    
    def generate_templates(
        self,
        min_receipts_per_template: int = 3,
        similarity_threshold: float = 0.7
    ) -> List[TemplateFingerprint]:
        """
        Generate template fingerprints from loaded receipts.
        
        Groups similar receipts and creates templates for common patterns.
        
        Args:
            min_receipts_per_template: Minimum receipts to form a template
            similarity_threshold: Similarity threshold for grouping
        
        Returns:
            List of generated templates
        """
        if not self._loaded:
            self.load()
        
        if not self.receipts:
            logger.warning("No receipts loaded for template generation")
            return []
        
        # Compute fingerprint for each receipt
        fingerprints = []
        for receipt in self.receipts:
            try:
                fp = compute_fingerprint(
                    receipt.text_lines,
                    template_id=f"sroie_{receipt.receipt_id}",
                    template_name=receipt.company or f"SROIE_{receipt.receipt_id}",
                    source="sroie"
                )
                # Add extraction hints from ground truth
                if receipt.company:
                    fp.extraction_hints["merchant"] = receipt.company
                if receipt.date:
                    fp.extraction_hints["date_format"] = receipt.date
                fingerprints.append((receipt, fp))
            except Exception as e:
                logger.debug(f"Failed to fingerprint {receipt.receipt_id}: {e}")
        
        # Group by merchant keywords (simple clustering)
        groups = self._cluster_by_merchant(fingerprints)
        
        # Generate templates from groups
        templates = []
        for group_name, group_fps in groups.items():
            if len(group_fps) >= min_receipts_per_template:
                template = self._merge_fingerprints(group_name, group_fps)
                templates.append(template)
                logger.debug(f"Generated template '{group_name}' from {len(group_fps)} receipts")
        
        # Also include individual fingerprints as templates
        for receipt, fp in fingerprints:
            if fp.template_id not in [t.template_id for t in templates]:
                templates.append(fp)
        
        logger.info(f"Generated {len(templates)} templates from {len(self.receipts)} receipts")
        return templates
    
    def _cluster_by_merchant(
        self,
        fingerprints: List[Tuple[SROIEReceipt, TemplateFingerprint]]
    ) -> Dict[str, List[TemplateFingerprint]]:
        """Group fingerprints by merchant keywords."""
        groups = defaultdict(list)
        
        for receipt, fp in fingerprints:
            # Use company name if available, else first merchant keyword
            if receipt.company:
                group_key = receipt.company.lower().split()[0][:20]
            elif fp.merchant_keywords:
                group_key = sorted(fp.merchant_keywords)[0][:20]
            else:
                group_key = "unknown"
            
            groups[group_key].append(fp)
        
        return dict(groups)
    
    def _merge_fingerprints(
        self,
        group_name: str,
        fingerprints: List[TemplateFingerprint]
    ) -> TemplateFingerprint:
        """Merge multiple fingerprints into a single template."""
        # Aggregate features
        all_merchant_kw = set()
        all_header_kw = set()
        all_footer_kw = set()
        line_counts = []
        amount_counts = []
        date_formats = set()
        
        for fp in fingerprints:
            all_merchant_kw.update(fp.merchant_keywords)
            all_header_kw.update(fp.header_keywords)
            all_footer_kw.update(fp.footer_keywords)
            line_counts.append(fp.line_count_range[0])
            amount_counts.append(fp.amount_count_range[0])
            date_formats.update(fp.date_formats)
        
        # Compute ranges
        line_range = (
            max(1, min(line_counts) - 5),
            max(line_counts) + 5
        )
        amount_range = (
            max(1, min(amount_counts) - 3),
            max(amount_counts) + 5
        )
        
        # Check feature presence (majority vote)
        has_tax = sum(fp.has_tax_line for fp in fingerprints) > len(fingerprints) // 2
        has_subtotal = sum(fp.has_subtotal_line for fp in fingerprints) > len(fingerprints) // 2
        has_total = sum(fp.has_total_line for fp in fingerprints) > len(fingerprints) // 2
        has_time = sum(fp.has_time for fp in fingerprints) > len(fingerprints) // 2
        has_separator = sum(fp.has_separator_lines for fp in fingerprints) > len(fingerprints) // 2
        has_table = sum(fp.has_table_structure for fp in fingerprints) > len(fingerprints) // 2
        
        return TemplateFingerprint(
            template_id=f"sroie_group_{group_name}",
            template_name=f"SROIE {group_name.title()}",
            source="sroie",
            line_count_range=line_range,
            header_line_count=max(fp.header_line_count for fp in fingerprints),
            footer_line_count=max(fp.footer_line_count for fp in fingerprints),
            merchant_keywords=all_merchant_kw,
            header_keywords=all_header_kw,
            footer_keywords=all_footer_kw,
            amount_count_range=amount_range,
            has_tax_line=has_tax,
            has_subtotal_line=has_subtotal,
            has_total_line=has_total,
            date_formats=list(date_formats),
            has_time=has_time,
            has_table_structure=has_table,
            has_separator_lines=has_separator,
        )
    
    def save_templates(
        self,
        templates: List[TemplateFingerprint],
        output_dir: Optional[Path] = None
    ) -> Path:
        """
        Save generated templates to index file.
        
        Args:
            templates: Templates to save
            output_dir: Output directory
        
        Returns:
            Path to saved index file
        """
        if output_dir is None:
            output_dir = Path(__file__).parent.parent.parent.parent / "resources" / "templates" / "sroie"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        index_file = output_dir / "index.json"
        
        index = {
            "source": "SROIE ICDAR 2019",
            "version": "1.0.0",
            "template_count": len(templates),
            "templates": [t.to_dict() for t in templates]
        }
        
        with open(index_file, 'w') as f:
            json.dump(index, f, indent=2)
        
        logger.info(f"Saved {len(templates)} templates to {index_file}")
        return index_file


def setup_sroie_templates(force_download: bool = False) -> int:
    """
    Convenience function to download SROIE and generate templates.
    
    Args:
        force_download: Force re-download even if exists
    
    Returns:
        Number of templates generated
    """
    loader = SROIELoader()
    
    # Download if needed
    loader.download(force=force_download)
    
    # Load and generate templates
    loader.load("train")
    templates = loader.generate_templates()
    
    # Save templates
    loader.save_templates(templates)
    
    return len(templates)
