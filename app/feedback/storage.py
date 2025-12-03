"""
Feedback Storage System
Stores human feedback for model training
100% offline, enterprise-ready
"""

import json
import os
import shutil
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path


class FeedbackStorage:
    """
    Store human feedback for model training.
    All data stored locally for enterprise compliance.
    
    Directory structure:
    data/training/feedback/
    ├── images/          # Receipt images
    ├── labels/          # Training labels (model-specific formats)
    │   ├── donut/       # Donut format
    │   └── layoutlm/    # LayoutLM format
    ├── metadata/        # Feedback metadata
    └── stats.json       # Training statistics
    """
    
    def __init__(self, storage_dir: str = "data/training/feedback"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Separate directories for organization
        self.images_dir = self.storage_dir / "images"
        self.labels_dir = self.storage_dir / "labels"
        self.donut_labels_dir = self.labels_dir / "donut"
        self.layoutlm_labels_dir = self.labels_dir / "layoutlm"
        self.metadata_dir = self.storage_dir / "metadata"
        
        for dir in [self.images_dir, self.labels_dir, self.donut_labels_dir, 
                    self.layoutlm_labels_dir, self.metadata_dir]:
            dir.mkdir(exist_ok=True)
        
        self.stats_file = self.storage_dir / "stats.json"
        self._init_stats()
    
    def _init_stats(self):
        """Initialize statistics file."""
        if not self.stats_file.exists():
            stats = {
                "total_feedback": 0,
                "pending_training": 0,
                "trained": 0,
                "last_training": None,
                "model_versions": []
            }
            with open(self.stats_file, 'w') as f:
                json.dump(stats, f, indent=2)
    
    def save_feedback(
        self,
        receipt_id: str,
        image_path: str,
        model_predictions: Dict[str, Any],
        human_feedback: Dict[str, Any],
        reviewer_id: str = "unknown"
    ) -> str:
        """
        Save feedback for training.
        
        Args:
            receipt_id: Original receipt ID
            image_path: Path to receipt image
            model_predictions: All model predictions
            human_feedback: Human review data
            reviewer_id: Email/ID of reviewer
        
        Returns:
            feedback_id
        """
        # Generate unique feedback ID
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        feedback_id = f"feedback_{timestamp}_{receipt_id}"
        
        # Copy receipt image
        image_dest = self.images_dir / f"{feedback_id}.jpg"
        shutil.copy(image_path, image_dest)
        
        # Save labels in model-specific formats
        self._save_donut_label(feedback_id, human_feedback)
        self._save_layoutlm_label(feedback_id, human_feedback)
        
        # Save metadata
        metadata = {
            "feedback_id": feedback_id,
            "receipt_id": receipt_id,
            "image_path": str(image_dest),
            "model_predictions": model_predictions,
            "human_feedback": human_feedback,
            "reviewer_id": reviewer_id,
            "timestamp": datetime.now().isoformat(),
            "status": "pending_training"
        }
        
        metadata_file = self.metadata_dir / f"{feedback_id}.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Update stats
        self._update_stats(increment_total=True, increment_pending=True)
        
        print(f"✅ Feedback saved: {feedback_id}")
        return feedback_id
    
    def _save_donut_label(self, feedback_id: str, feedback: Dict):
        """
        Save in Donut training format.
        
        Format:
        {
            "gt_parse": {
                "merchant": {...},
                "items": [...],
                "total": float,
                ...
            }
        }
        """
        corrections = feedback.get("corrections", {})
        
        donut_label = {
            "gt_parse": {
                "merchant": {
                    "name": corrections.get("merchant", ""),
                    "address": corrections.get("merchant_address", ""),
                    "phone": corrections.get("merchant_phone", "")
                },
                "items": corrections.get("items", []),
                "subtotal": corrections.get("subtotal"),
                "tax": {
                    "amount": corrections.get("tax"),
                    "cgst": corrections.get("cgst"),
                    "sgst": corrections.get("sgst"),
                    "igst": corrections.get("igst")
                },
                "total": corrections.get("total"),
                "payment_method": corrections.get("payment_method"),
                "date": corrections.get("date"),
                "time": corrections.get("time"),
                "receipt_number": corrections.get("receipt_number")
            }
        }
        
        label_file = self.donut_labels_dir / f"{feedback_id}.json"
        with open(label_file, 'w') as f:
            json.dump(donut_label, f, indent=2)
    
    def _save_layoutlm_label(self, feedback_id: str, feedback: Dict):
        """
        Save in LayoutLM training format.
        
        LayoutLM uses token-level labels with bounding boxes.
        This is a simplified version - full implementation would need OCR boxes.
        """
        corrections = feedback.get("corrections", {})
        
        # Simplified format - in practice would need token-level annotations
        layoutlm_label = {
            "entities": [
                {"type": "merchant", "value": corrections.get("merchant")},
                {"type": "total", "value": corrections.get("total")},
                {"type": "tax", "value": corrections.get("tax")},
                {"type": "date", "value": corrections.get("date")},
                {"type": "receipt_number", "value": corrections.get("receipt_number")}
            ]
        }
        
        label_file = self.layoutlm_labels_dir / f"{feedback_id}.json"
        with open(label_file, 'w') as f:
            json.dump(layoutlm_label, f, indent=2)
    
    def get_training_data(self, min_samples: int = 100) -> Optional[Dict[str, List]]:
        """
        Get all pending feedback data for training.
        Only returns if we have enough samples.
        
        Args:
            min_samples: Minimum samples needed for training
        
        Returns:
            {
                "images": [paths],
                "donut_labels": [paths],
                "layoutlm_labels": [paths],
                "metadata": [dicts]
            }
            or None if not enough samples
        """
        metadata_files = list(self.metadata_dir.glob("*.json"))
        
        # Filter for pending training
        pending = []
        for metadata_file in metadata_files:
            with open(metadata_file) as f:
                metadata = json.load(f)
            if metadata.get("status") == "pending_training":
                pending.append(metadata)
        
        if len(pending) < min_samples:
            print(f"Not enough samples for training. Have {len(pending)}, need {min_samples}")
            return None
        
        training_data = {
            "images": [],
            "donut_labels": [],
            "layoutlm_labels": [],
            "metadata": []
        }
        
        for metadata in pending:
            feedback_id = metadata["feedback_id"]
            
            training_data["images"].append(metadata["image_path"])
            training_data["donut_labels"].append(
                str(self.donut_labels_dir / f"{feedback_id}.json")
            )
            training_data["layoutlm_labels"].append(
                str(self.layoutlm_labels_dir / f"{feedback_id}.json")
            )
            training_data["metadata"].append(metadata)
        
        return training_data
    
    def mark_as_trained(self, feedback_ids: List[str], model_version: str):
        """
        Mark feedback as used in training.
        
        Args:
            feedback_ids: List of feedback IDs that were trained
            model_version: Version identifier of trained model
        """
        trained_count = 0
        
        for feedback_id in feedback_ids:
            metadata_file = self.metadata_dir / f"{feedback_id}.json"
            if metadata_file.exists():
                with open(metadata_file) as f:
                    metadata = json.load(f)
                
                metadata["status"] = "trained"
                metadata["trained_at"] = datetime.now().isoformat()
                metadata["model_version"] = model_version
                
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)
                
                trained_count += 1
        
        # Update stats
        self._update_stats(
            increment_pending=-trained_count,
            increment_trained=trained_count,
            model_version=model_version
        )
        
        print(f"✅ Marked {trained_count} samples as trained (version: {model_version})")
    
    def _update_stats(
        self,
        increment_total: bool = False,
        increment_pending: int = 0,
        increment_trained: int = 0,
        model_version: Optional[str] = None
    ):
        """Update statistics file."""
        with open(self.stats_file) as f:
            stats = json.load(f)
        
        if increment_total:
            stats["total_feedback"] += 1
        
        stats["pending_training"] += increment_pending
        stats["trained"] += increment_trained
        
        if model_version:
            stats["last_training"] = datetime.now().isoformat()
            stats["model_versions"].append({
                "version": model_version,
                "timestamp": datetime.now().isoformat(),
                "samples_trained": increment_trained
            })
        
        with open(self.stats_file, 'w') as f:
            json.dump(stats, f, indent=2)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get training statistics."""
        with open(self.stats_file) as f:
            return json.load(f)
    
    def export_dataset(self, output_dir: str, format: str = "donut"):
        """
        Export all feedback as a training dataset.
        
        Args:
            output_dir: Where to export
            format: "donut" or "layoutlm"
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Copy images and labels
        images_out = output_path / "images"
        labels_out = output_path / "labels"
        images_out.mkdir(exist_ok=True)
        labels_out.mkdir(exist_ok=True)
        
        metadata_files = list(self.metadata_dir.glob("*.json"))
        
        for metadata_file in metadata_files:
            with open(metadata_file) as f:
                metadata = json.load(f)
            
            feedback_id = metadata["feedback_id"]
            
            # Copy image
            src_image = Path(metadata["image_path"])
            if src_image.exists():
                shutil.copy(src_image, images_out / f"{feedback_id}.jpg")
            
            # Copy label
            if format == "donut":
                src_label = self.donut_labels_dir / f"{feedback_id}.json"
            else:
                src_label = self.layoutlm_labels_dir / f"{feedback_id}.json"
            
            if src_label.exists():
                shutil.copy(src_label, labels_out / f"{feedback_id}.json")
        
        print(f"✅ Dataset exported to {output_dir}")
        print(f"   Format: {format}")
        print(f"   Samples: {len(metadata_files)}")


if __name__ == "__main__":
    # Test the storage system
    storage = FeedbackStorage()
    
    # Print stats
    stats = storage.get_stats()
    print("\n📊 Training Statistics:")
    print(f"   Total Feedback: {stats['total_feedback']}")
    print(f"   Pending Training: {stats['pending_training']}")
    print(f"   Trained: {stats['trained']}")
    print(f"   Last Training: {stats['last_training'] or 'Never'}")
    print(f"   Model Versions: {len(stats['model_versions'])}")
