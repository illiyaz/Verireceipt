"""
Donut-Receipt Model for Structured Receipt Extraction
5th AI Engine - Specialized for receipt parsing
Runs completely offline, no API calls
"""

from transformers import DonutProcessor, VisionEncoderDecoderModel
import torch
from PIL import Image
from typing import Dict, Any, Optional
import re
import json


class DonutReceiptExtractor:
    """
    Donut-Receipt model for structured receipt extraction.
    Extracts: merchant, items, amounts, tax, payment method, etc.
    Runs offline after initial model download.
    """
    
    def __init__(self, model_name: str = "naver-clova-ix/donut-base-finetuned-cord-v2"):
        """
        Initialize Donut-Receipt model.
        
        Args:
            model_name: HuggingFace model identifier
                       Default: CORD v2 (receipt dataset)
        
        Note: Downloads model once (~1GB), then runs offline
        """
        print(f"Loading Donut-Receipt model: {model_name}")
        
        self.processor = DonutProcessor.from_pretrained(model_name)
        
        # Use GPU if available for faster inference
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load model with proper settings to avoid meta tensor issues
        try:
            self.model = VisionEncoderDecoderModel.from_pretrained(
                model_name,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=False  # Disable to avoid meta tensors
            )
            self.model.to(self.device)
            self.model.eval()
            print(f"Donut-Receipt loaded on {self.device}")
        except Exception as e:
            print(f"Failed to load with standard method: {e}")
            print("Trying alternative loading...")
            self.model = VisionEncoderDecoderModel.from_pretrained(
                model_name,
                device_map=None  # Don't use auto device mapping
            )
            self.model = self.model.to(self.device)
            self.model.eval()
            print(f"Donut-Receipt loaded on {self.device} (alternative method)")
    
    def extract(self, image_path: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Extract structured data from receipt image.
        
        Args:
            image_path: Path to receipt image
            timeout: Max seconds for extraction
        
        Returns:
            {
                "merchant": {
                    "name": str,
                    "address": str,
                    "phone": str
                },
                "items": [
                    {
                        "name": str,
                        "quantity": int,
                        "unit_price": float,
                        "total": float
                    }
                ],
                "subtotal": float,
                "tax": {
                    "type": str,  # "GST", "CGST+SGST", "VAT", etc.
                    "amount": float,
                    "rate": float,
                    "cgst": float,
                    "sgst": float,
                    "igst": float
                },
                "total": float,
                "payment_method": str,
                "date": str,
                "time": str,
                "receipt_number": str,
                "confidence": float,
                "status": "success" | "error",
                "error": str (if status == "error")
            }
        """
        try:
            # Load and preprocess image
            image = Image.open(image_path).convert("RGB")
            
            # Resize if too large (for memory efficiency)
            max_size = 1280
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.LANCZOS)
            
            # Prepare for model
            pixel_values = self.processor(image, return_tensors="pt").pixel_values
            pixel_values = pixel_values.to(self.device)
            
            # Generate structured output
            with torch.no_grad():
                outputs = self.model.generate(
                    pixel_values,
                    max_length=self.model.decoder.config.max_position_embeddings,
                    early_stopping=True,
                    pad_token_id=self.processor.tokenizer.pad_token_id,
                    eos_token_id=self.processor.tokenizer.eos_token_id,
                    use_cache=True,
                    num_beams=1,
                    bad_words_ids=[[self.processor.tokenizer.unk_token_id]],
                    return_dict_in_generate=True,
                )
            
            # Decode to structured JSON
            sequence = self.processor.batch_decode(outputs.sequences)[0]
            sequence = sequence.replace(self.processor.tokenizer.eos_token, "").replace(
                self.processor.tokenizer.pad_token, ""
            )
            sequence = re.sub(r"<.*?>", "", sequence, count=1).strip()
            
            # Parse JSON output from model
            try:
                result = self.processor.token2json(sequence)
            except:
                # Fallback: try to parse as JSON directly
                result = json.loads(sequence) if sequence.startswith('{') else {}
            
            # Normalize and enrich result
            normalized = self._normalize_result(result)
            
            # Add confidence score
            normalized["confidence"] = self._calculate_confidence(normalized)
            normalized["status"] = "success"
            
            return normalized
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "confidence": 0.0,
                "merchant": {},
                "items": [],
                "total": None,
                "tax": {},
                "subtotal": None,
                "payment_method": None,
                "date": None,
                "time": None,
                "receipt_number": None
            }
    
    def _normalize_result(self, raw_result: Dict) -> Dict[str, Any]:
        """
        Normalize model output to consistent format.
        Different models may return different field names.
        """
        normalized = {
            "merchant": {},
            "items": [],
            "subtotal": None,
            "tax": {},
            "total": None,
            "payment_method": None,
            "date": None,
            "time": None,
            "receipt_number": None
        }
        
        # Merchant info (various possible field names)
        merchant_keys = ['store', 'merchant', 'company', 'vendor']
        for key in merchant_keys:
            if key in raw_result:
                merchant_data = raw_result[key]
                if isinstance(merchant_data, dict):
                    normalized["merchant"] = {
                        "name": merchant_data.get('name') or merchant_data.get('nm'),
                        "address": merchant_data.get('address') or merchant_data.get('addr'),
                        "phone": merchant_data.get('phone') or merchant_data.get('tel')
                    }
                elif isinstance(merchant_data, str):
                    normalized["merchant"]["name"] = merchant_data
                break
        
        # Items (line items)
        items_keys = ['items', 'menu', 'products', 'line_items']
        for key in items_keys:
            if key in raw_result and isinstance(raw_result[key], list):
                for item in raw_result[key]:
                    if isinstance(item, dict):
                        normalized["items"].append({
                            "name": item.get('name') or item.get('nm') or item.get('item'),
                            "quantity": self._parse_number(item.get('quantity') or item.get('qty') or item.get('cnt'), int) or 1,
                            "unit_price": self._parse_number(item.get('unit_price') or item.get('price') or item.get('unitprice'), float),
                            "total": self._parse_number(item.get('total') or item.get('price') or item.get('amount'), float)
                        })
                break
        
        # Amounts
        normalized["subtotal"] = self._parse_number(
            raw_result.get('subtotal') or raw_result.get('sub_total') or raw_result.get('subtotal_price'),
            float
        )
        
        normalized["total"] = self._parse_number(
            raw_result.get('total') or raw_result.get('total_price') or raw_result.get('grand_total'),
            float
        )
        
        # Tax (complex for Indian GST)
        tax_data = raw_result.get('tax') or raw_result.get('vat') or {}
        if isinstance(tax_data, dict):
            normalized["tax"] = {
                "amount": self._parse_number(tax_data.get('amount') or tax_data.get('total'), float),
                "rate": self._parse_number(tax_data.get('rate') or tax_data.get('percent'), float),
                "type": tax_data.get('type') or tax_data.get('name'),
                "cgst": self._parse_number(tax_data.get('cgst'), float),
                "sgst": self._parse_number(tax_data.get('sgst'), float),
                "igst": self._parse_number(tax_data.get('igst'), float)
            }
        elif isinstance(tax_data, (int, float, str)):
            normalized["tax"]["amount"] = self._parse_number(tax_data, float)
        
        # Payment method
        normalized["payment_method"] = (
            raw_result.get('payment_method') or 
            raw_result.get('payment') or 
            raw_result.get('card_type')
        )
        
        # Date and time
        normalized["date"] = raw_result.get('date') or raw_result.get('transaction_date')
        normalized["time"] = raw_result.get('time') or raw_result.get('transaction_time')
        
        # Receipt number
        normalized["receipt_number"] = (
            raw_result.get('receipt_number') or 
            raw_result.get('invoice_number') or 
            raw_result.get('order_number') or
            raw_result.get('tid')
        )
        
        return normalized
    
    def _parse_number(self, value: Any, num_type: type) -> Optional[float]:
        """
        Safely parse number from various formats.
        """
        if value is None:
            return None
        
        try:
            if isinstance(value, str):
                # Remove currency symbols and commas
                value = re.sub(r'[₹$€£¥,]', '', value).strip()
            
            return num_type(value)
        except:
            return None
    
    def _calculate_confidence(self, result: Dict) -> float:
        """
        Calculate confidence score based on completeness and consistency.
        
        Scoring:
        - Merchant name: 15%
        - Items extracted: 25%
        - Total amount: 20%
        - Date: 10%
        - Receipt number: 10%
        - Tax info: 10%
        - Subtotal: 5%
        - Payment method: 5%
        """
        score = 0.0
        
        # Merchant name (15%)
        if result.get("merchant", {}).get("name"):
            score += 0.15
        
        # Items (25%)
        items = result.get("items", [])
        if items:
            # More items = higher confidence (up to 5 items)
            item_score = min(len(items) / 5.0, 1.0) * 0.25
            score += item_score
        
        # Total amount (20%)
        if result.get("total"):
            score += 0.20
        
        # Date (10%)
        if result.get("date"):
            score += 0.10
        
        # Receipt number (10%)
        if result.get("receipt_number"):
            score += 0.10
        
        # Tax info (10%)
        tax = result.get("tax", {})
        if tax.get("amount") or tax.get("cgst") or tax.get("sgst"):
            score += 0.10
        
        # Subtotal (5%)
        if result.get("subtotal"):
            score += 0.05
        
        # Payment method (5%)
        if result.get("payment_method"):
            score += 0.05
        
        return min(score, 1.0)


def analyze_receipt_donut(image_path: str) -> Dict[str, Any]:
    """
    Standalone function to analyze receipt with Donut.
    Can be called from API without instantiating class.
    
    Args:
        image_path: Path to receipt image
    
    Returns:
        Structured receipt data
    """
    extractor = DonutReceiptExtractor()
    return extractor.extract(image_path)


if __name__ == "__main__":
    # Test the extractor
    import sys
    
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        print(f"\nAnalyzing receipt: {image_path}\n")
        
        result = analyze_receipt_donut(image_path)
        
        print(json.dumps(result, indent=2))
        print(f"\nConfidence: {result['confidence']:.1%}")
    else:
        print("Usage: python donut_receipt.py <image_path>")
