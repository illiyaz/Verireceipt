"""
Pydantic schema for language pack validation.

Ensures language packs are well-formed and fail fast on configuration errors.
"""

from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator, model_validator
import re


class KeywordGroup(BaseModel):
    """Group of keywords for specific document types or fields."""
    doc_titles: List[str] = Field(default_factory=list, description="Document title keywords")
    invoice: List[str] = Field(default_factory=list, description="Invoice-related keywords")
    receipt: List[str] = Field(default_factory=list, description="Receipt-related keywords")
    tax_invoice: List[str] = Field(default_factory=list, description="Tax invoice keywords")
    ecommerce: List[str] = Field(default_factory=list, description="E-commerce keywords")
    fuel: List[str] = Field(default_factory=list, description="Fuel station keywords")
    parking: List[str] = Field(default_factory=list, description="Parking keywords")
    hotel_folio: List[str] = Field(default_factory=list, description="Hotel folio keywords")
    utility: List[str] = Field(default_factory=list, description="Utility bill keywords")
    telecom: List[str] = Field(default_factory=list, description="Telecom keywords")
    commercial_invoice: List[str] = Field(default_factory=list, description="Commercial invoice keywords")
    air_waybill: List[str] = Field(default_factory=list, description="Air waybill keywords")
    shipping_bill: List[str] = Field(default_factory=list, description="Shipping bill keywords")
    bill_of_lading: List[str] = Field(default_factory=list, description="Bill of lading keywords")
    total: List[str] = Field(default_factory=list, description="Total amount keywords")
    subtotal: List[str] = Field(default_factory=list, description="Subtotal keywords")
    tax: List[str] = Field(default_factory=list, description="Tax keywords")
    date: List[str] = Field(default_factory=list, description="Date keywords")
    amount: List[str] = Field(default_factory=list, description="Amount keywords")
    logistics: List[str] = Field(default_factory=list, description="Logistics/shipping keywords")
    
    @validator('*', pre=True)
    def ensure_list_of_strings(cls, v):
        """Ensure all keyword fields are lists of strings."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(item) for item in v]
        raise ValueError("Keywords must be strings or lists of strings")


class LabelGroup(BaseModel):
    """Structural labels and next-line preferences."""
    structural: List[str] = Field(default_factory=list, description="Structural labels to reject as merchants")
    next_line_preference: List[str] = Field(default_factory=list, description="Labels where next line is likely merchant")
    
    @validator('*', pre=True)
    def ensure_list_of_strings(cls, v):
        """Ensure all label fields are lists of strings."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(item) for item in v]
        raise ValueError("Labels must be strings or lists of strings")


class CompanyInfo(BaseModel):
    """Company-related patterns and suffixes."""
    suffixes: List[str] = Field(default_factory=list, description="Company legal suffixes")
    prefixes: List[str] = Field(default_factory=list, description="Common company prefixes")
    
    @validator('*', pre=True)
    def ensure_list_of_strings(cls, v):
        """Ensure all company fields are lists of strings."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(item) for item in v]
        raise ValueError("Company info must be strings or lists of strings")


class AddressInfo(BaseModel):
    """Address-related keywords and patterns."""
    keywords: List[str] = Field(default_factory=list, description="Address-related keywords")
    postal_code_patterns: List[str] = Field(default_factory=list, description="Regex patterns for postal codes")
    
    @validator('postal_code_patterns', pre=True)
    def validate_regex_patterns(cls, v):
        """Ensure postal code patterns are valid regex."""
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        
        validated_patterns = []
        for pattern in v:
            try:
                re.compile(pattern)
                validated_patterns.append(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}")
        
        return validated_patterns
    
    @validator('keywords', pre=True)
    def ensure_list_of_strings(cls, v):
        """Ensure keywords are lists of strings."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(item) for item in v]
        raise ValueError("Address keywords must be strings or lists of strings")


class CurrencyInfo(BaseModel):
    """Currency symbols and codes."""
    symbols: List[str] = Field(default_factory=list, description="Currency symbols")
    codes: List[str] = Field(default_factory=list, description="Currency codes")
    
    @validator('*', pre=True)
    def ensure_list_of_strings(cls, v):
        """Ensure all currency fields are lists of strings."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(item) for item in v]
        raise ValueError("Currency info must be strings or lists of strings")


class LangPack(BaseModel):
    """Complete language pack definition."""
    id: str = Field(..., description="Language pack ID (e.g., 'en', 'ar', 'zh')")
    version: str = Field(..., description="Semantic version (e.g., '1.0.0')")
    name: str = Field(..., description="Human-readable language name")
    scripts: List[str] = Field(..., description="Unicode scripts this pack supports")
    locales: Optional[List[str]] = Field(default_factory=list, description="Locale codes this pack supports")
    priority: int = Field(default=0, description="Optional routing priority (higher wins when otherwise tied)")
    
    # Core components
    keywords: KeywordGroup = Field(default_factory=KeywordGroup)
    labels: LabelGroup = Field(default_factory=LabelGroup)
    company: CompanyInfo = Field(default_factory=CompanyInfo)
    address: AddressInfo = Field(default_factory=AddressInfo)
    currency: CurrencyInfo = Field(default_factory=CurrencyInfo)
    
    # Optional extensions
    extensions: Optional[Dict[str, Union[str, List[str], Dict]]] = Field(
        default_factory=dict, 
        description="Custom extensions for language-specific features"
    )
    
    @validator('id')
    def validate_id(cls, v):
        """Validate language pack ID format."""
        if v == 'common':
            return v
        if not re.match(r'^[a-z]{2}(-[A-Z]{2})?$', v):
            raise ValueError(f"Invalid language pack ID '{v}'. Expected format: 'en', 'zh-CN', etc.")
        return v
    
    @validator('version')
    def validate_version(cls, v):
        """Validate semantic version."""
        if not re.match(r'^\d+\.\d+\.\d+$', v):
            raise ValueError(f"Invalid version '{v}'. Expected semantic version: '1.0.0'")
        return v
    
    @validator('scripts')
    def validate_scripts(cls, v):
        """Validate script names."""
        valid_scripts = {
            'latin', 'arabic', 'cjk', 'hangul', 'thai', 'cyrillic', 
            'devanagari', 'hebrew', 'bengali', 'tamil', 'telugu'
        }
        for script in v:
            if script.lower() not in valid_scripts:
                raise ValueError(f"Invalid script '{script}'. Valid scripts: {valid_scripts}")
        return [s.lower() for s in v]
    
    @validator('locales')
    def validate_locales(cls, v):
        """Validate locale codes."""
        if v is None:
            return []
        for locale in v:
            if not re.match(r'^[a-z]{2}(-[A-Z]{2})?$', locale):
                raise ValueError(f"Invalid locale '{locale}'. Expected format: 'en', 'en-US', etc.")
        return v
    
    @model_validator(mode='after')
    def validate_required_keywords(self):
        """Ensure essential keyword groups are not empty."""
        keywords = self.keywords
        
        # Check for essential keywords
        essential_groups = ['invoice', 'receipt', 'total']
        for group in essential_groups:
            if not getattr(keywords, group, []):
                raise ValueError(f"Essential keyword group '{group}' cannot be empty")
        
        return self
    
    model_config = {
        "extra": 'forbid',  # Prevent unknown fields
        "validate_assignment": True
    }
