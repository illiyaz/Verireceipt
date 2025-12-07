"""
DONUT (Document Understanding Transformer) Integration.

DONUT is a document-specific vision transformer that:
- Extracts structured data from receipts (no OCR needed)
- Outputs native JSON format
- Trained specifically on documents (receipts, invoices, forms)
- More accurate than OCR for data extraction

Model: naver-clova-ix/donut-base-finetuned-cord-v2 (receipt understanding)
"""

from typing import Dict, Any, Optional
from pathlib import Path
import json

# DONUT requires transformers and torch
try:
    from transformers import DonutProcessor, VisionEncoderDecoderModel
    from PIL import Image
    import torch
    DONUT_AVAILABLE = True
except ImportError:
    DONUT_AVAILABLE = False
    print("⚠️  DONUT dependencies not installed. Install with:")
    print("   pip install transformers torch pillow")


class DonutExtractor:
    """
    DONUT-based receipt data extractor.
    
    This uses a pre-trained DONUT model fine-tuned on receipts (CORD dataset).
    """
    
    def __init__(self, model_name: str = "naver-clova-ix/donut-base-finetuned-cord-v2"):
        """
        Initialize DONUT model.
        
        Args:
            model_name: HuggingFace model name
                - donut-base-finetuned-cord-v2: Receipt understanding (recommended)
                - donut-base: Base model (needs fine-tuning)
        """
        if not DONUT_AVAILABLE:
            raise ImportError("DONUT dependencies not installed")
        
        self.model_name = model_name
        self.processor = None
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        print(f"🔧 Loading DONUT model: {model_name}")
        print(f"   Device: {self.device}")
    
    def load_model(self):
        """Load DONUT model and processor."""
        if self.processor is None:
            print("   Loading processor...")
            self.processor = DonutProcessor.from_pretrained(self.model_name)
            
            print("   Loading model...")
            try:
                # Load model directly to device to avoid meta tensor issues
                self.model = VisionEncoderDecoderModel.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.float32,
                    low_cpu_mem_usage=False  # Disable to avoid meta tensors
                )
                self.model.to(self.device)
                self.model.eval()
                print("✅ DONUT model loaded")
            except Exception as e:
                print(f"❌ Failed to load DONUT model: {e}")
                print("   Trying alternative loading method...")
                # Alternative: load with explicit device
                self.model = VisionEncoderDecoderModel.from_pretrained(
                    self.model_name,
                    device_map=None  # Don't use auto device mapping
                )
                self.model = self.model.to(self.device)
                self.model.eval()
                print("✅ DONUT model loaded (alternative method)")
    
    def extract_from_image(self, image_path: str, task_prompt: str = "<s_cord-v2>") -> Dict[str, Any]:
        """
        Extract structured data from receipt image using DONUT.
        
        Args:
            image_path: Path to receipt image
            task_prompt: Task-specific prompt (default for CORD receipts)
        
        Returns:
            Extracted data as dictionary
        """
        if self.model is None:
            self.load_model()
        
        # Load image
        from PIL import ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = True  # Allow truncated/corrupted images
        
        image = Image.open(image_path)
        image.load()  # Ensure image data is loaded
        image = image.convert("RGB")
        
        # Prepare inputs
        pixel_values = self.processor(image, return_tensors="pt").pixel_values
        pixel_values = pixel_values.to(self.device)
        
        # Generate
        decoder_input_ids = self.processor.tokenizer(
            task_prompt,
            add_special_tokens=False,
            return_tensors="pt"
        ).input_ids
        decoder_input_ids = decoder_input_ids.to(self.device)
        
        # Run model
        with torch.no_grad():
            outputs = self.model.generate(
                pixel_values,
                decoder_input_ids=decoder_input_ids,
                max_length=self.model.decoder.config.max_position_embeddings,
                pad_token_id=self.processor.tokenizer.pad_token_id,
                eos_token_id=self.processor.tokenizer.eos_token_id,
                use_cache=True,
                bad_words_ids=[[self.processor.tokenizer.unk_token_id]],
                return_dict_in_generate=True,
            )
        
        # Decode
        sequence = self.processor.batch_decode(outputs.sequences)[0]
        sequence = sequence.replace(self.processor.tokenizer.eos_token, "").replace(
            self.processor.tokenizer.pad_token, ""
        )
        sequence = sequence.replace(task_prompt, "")
        
        # Parse JSON output
        try:
            # DONUT outputs JSON-like structure
            result = self.processor.token2json(sequence)
            return result
        except Exception as e:
            print(f"⚠️  Failed to parse DONUT output: {e}")
            return {"raw_output": sequence}
    
    def extract_receipt_data(self, image_path: str) -> Dict[str, Any]:
        """
        Extract receipt data with standardized output format.
        
        Returns:
            {
                "merchant": str,
                "date": str,
                "total": float,
                "subtotal": float,
                "tax": float,
                "line_items": [{"name": str, "price": float, "quantity": int}, ...],
                "payment_method": str,
                "raw_donut_output": dict
            }
        """
        raw_output = self.extract_from_image(image_path)
        
        # Standardize output format
        standardized = {
            "merchant": None,
            "date": None,
            "total": None,
            "subtotal": None,
            "tax": None,
            "line_items": [],
            "payment_method": None,
            "raw_donut_output": raw_output
        }
        
        # Parse CORD format (if using cord-v2 model)
        if "menu" in raw_output:
            # Extract line items
            for item in raw_output.get("menu", []):
                standardized["line_items"].append({
                    "name": item.get("nm", ""),
                    "price": self._parse_price(item.get("price", "")),
                    "quantity": item.get("cnt", 1)
                })
        
        # Extract totals
        if "total" in raw_output:
            total_info = raw_output["total"]
            standardized["total"] = self._parse_price(total_info.get("total_price", ""))
            standardized["subtotal"] = self._parse_price(total_info.get("subtotal_price", ""))
            standardized["tax"] = self._parse_price(total_info.get("tax_price", ""))
        
        return standardized
    
    def _parse_price(self, price_str: str) -> Optional[float]:
        """Parse price string to float."""
        if not price_str:
            return None
        
        try:
            # Remove currency symbols and commas
            clean = price_str.replace("$", "").replace("€", "").replace(",", "").strip()
            return float(clean)
        except (ValueError, AttributeError):
            return None


# Convenience functions
_donut_extractor = None


def get_donut_extractor() -> DonutExtractor:
    """Get singleton DONUT extractor instance."""
    global _donut_extractor
    if _donut_extractor is None:
        _donut_extractor = DonutExtractor()
    return _donut_extractor


def extract_receipt_with_donut(image_path: str) -> Dict[str, Any]:
    """
    Extract receipt data using DONUT.
    
    Args:
        image_path: Path to receipt image
    
    Returns:
        Extracted data dictionary
    """
    if not DONUT_AVAILABLE:
        return {
            "error": "DONUT not available",
            "merchant": None,
            "total": None,
            "date": None,
            "line_items": []
        }
    
    # Check if file is PDF - DONUT only handles images
    from pathlib import Path
    if Path(image_path).suffix.lower() == '.pdf':
        return {
            "error": "DONUT does not support PDF files (image-only model)",
            "merchant": None,
            "total": None,
            "date": None,
            "line_items": []
        }
    
    extractor = get_donut_extractor()
    return extractor.extract_from_image(image_path)


def compare_donut_with_ocr(donut_data: Dict, ocr_features: Dict) -> Dict[str, Any]:
    """
    Compare DONUT extraction with OCR-based features.
    
    This helps validate data and improve confidence.
    """
    comparison = {
        "matches": {},
        "discrepancies": [],
        "confidence_boost": 0.0
    }
    
    # Compare total
    donut_total = donut_data.get("total")
    ocr_total = ocr_features.get("text_features", {}).get("total_amount")
    
    if donut_total and ocr_total:
        try:
            diff = abs(float(donut_total) - float(ocr_total))
            if diff < 0.01:
                comparison["matches"]["total"] = True
            else:
                comparison["matches"]["total"] = False
                comparison["discrepancies"].append(
                    f"Total mismatch: DONUT=${donut_total}, OCR=${ocr_total}"
                )
        except (ValueError, TypeError):
            pass
    
    # Compare line item count
    donut_items = len(donut_data.get("line_items", []))
    ocr_lines = ocr_features.get("layout_features", {}).get("num_lines", 0)
    
    if donut_items > 0 and ocr_lines > 0:
        # Line items should be less than total lines
        if donut_items <= ocr_lines:
            comparison["matches"]["line_items"] = True
        else:
            comparison["matches"]["line_items"] = False
            comparison["discrepancies"].append(
                f"Line item count suspicious: DONUT={donut_items}, OCR lines={ocr_lines}"
            )
    
    # Calculate confidence boost
    matches = sum(1 for v in comparison["matches"].values() if v)
    total_checks = len(comparison["matches"])
    
    if total_checks > 0:
        comparison["confidence_boost"] = matches / total_checks
    
    return comparison


# Testing
if __name__ == "__main__":
    import sys
    
    if not DONUT_AVAILABLE:
        print("❌ DONUT dependencies not installed")
        print("\nInstall with:")
        print("   pip install transformers torch pillow")
        sys.exit(1)
    
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        
        print(f"\n{'='*80}")
        print(f"DONUT Extraction: {Path(image_path).name}")
        print(f"{'='*80}\n")
        
        result = extract_receipt_with_donut(image_path)
        
        print("Extracted Data:")
        print(json.dumps(result, indent=2))
        
        print(f"\n{'='*80}\n")
    else:
        print("Usage: python -m app.pipelines.donut_extractor <image_path>")
